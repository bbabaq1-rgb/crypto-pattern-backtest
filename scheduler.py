"""
scheduler.py — 매일 UTC 00:00 자동 파이프라인 (페이퍼테스트 준비, 실주문 없음).

순서:
  (1) 7종목 일봉 최신 fetch (fetch_data.py)
  (2) regime_switch 로 현재 레짐 판정
  (3) direction_switch.json 갱신(레짐->방향 라우팅)
  (4) engulfing/fvg detector로 '오늘(최신봉)' 신호 탐지 (레짐이 켠 방향만)
  (5) 신호를 signals_today.json 에 저장
      (패턴/방향/종목/강도/레짐/권장진입가/손절가/익절조건)

사용:
  python scheduler.py once     # 1회 실행(fetch 생략, 데이터 최신 가정)
  python scheduler.py oncefull # 1회 실행(fetch 포함)
  python scheduler.py          # 데몬: 매 UTC 00:00 자동 실행(while+sleep)
실주문은 넣지 않는다 — 신호만 기록.
"""
import sys
import os
import json
import time
import subprocess
from datetime import datetime, timezone, timedelta

import detlib
import regime_switch as rs
import direction_switch as ds

def _universe():
    if os.path.exists("universe.json"):
        u = json.load(open("universe.json", encoding="utf-8")).get("trading_universe")
        if u:
            return u
    return list(detlib.SYMBOLS)


SYMBOLS = _universe()
FOCUS = ["engulfing", "fvg"]
STOP = 0.08
MAX_HOLD = 30
DETMOD = {("engulfing", "long"): "detector_engulfing",
          ("engulfing", "short"): "detector_engulfing_short",
          ("fvg", "long"): "detector_fvg",
          ("fvg", "short"): "detector_fvg_short"}

# 하모닉 패턴 4h (PASSED: gartley/bat/butterfly)
HARMONIC_FOCUS = [
    ("gartley",   "detector_gartley"),
    ("bat",       "detector_bat"),
    ("butterfly", "detector_butterfly"),
]
HARMONIC_TF = "4h"


def _harmonic_symbols():
    """4h 데이터가 있는 종목 전체(data/*_4h.csv 기준). 없으면 SYMBOLS 폴백."""
    import glob as _glob
    syms = sorted({os.path.basename(f)[:-7].upper() for f in _glob.glob("data/*_4h.csv")})
    return syms if syms else SYMBOLS


def _1h_symbols():
    """1h 데이터가 있는 종목 전체(data/*_1h.csv 기준). 없으면 SYMBOLS 폴백."""
    import glob as _glob
    syms = sorted({os.path.basename(f)[:-7].upper() for f in _glob.glob("data/*_1h.csv")})
    return syms if syms else SYMBOLS


EXCHANGES = ["binance", "bybit", "okx"]   # 451 지역차단 시 순서대로 폴백

# ── 앙상블 스코어링 설정 ─────────────────────────────────────────────────────
# TF별 기본 점수
TF_BASE_PTS = {"1d": 3, "4h": 2, "1h": 1}

# 패턴별 검증 p값 (research_log/registry 기준)
PATTERN_PVAL = {
    "engulfing":         0.0001,
    "engulfing_short":   0.0001,
    "fvg":               0.0001,
    "fvg_short":         0.0001,
    "inverted_hammer":   0.005,
    "marubozu":          0.005,
    "gartley":           0.001,     # 4h
    "bat":               0.001,     # 4h
    "butterfly":         0.001,     # 4h
    "three_soldiers_4h": 0.0001,
    "bat_1h":            0.034,     # boot_p
    "butterfly_1h":      0.024,     # boot_p
}

def _pval_mult(pattern):
    """p값 기반 검증강도 가중치."""
    p = PATTERN_PVAL.get(pattern, 0.05)
    if p < 0.001:
        return 1.2
    elif p < 0.01:
        return 1.1
    return 1.0

def _multitf_bonus(tfs):
    """다중 TF 동시 발화 보너스."""
    has_1d = "1d" in tfs
    has_4h = "4h" in tfs
    has_1h = "1h" in tfs
    if has_1d and has_4h and has_1h:
        return 3
    if has_1d and has_4h:
        return 2
    if has_1d and has_1h:
        return 1
    if has_4h and has_1h:
        return 1
    return 0

def _ensemble_grade(score):
    if score >= 8:
        return "A"
    elif score >= 5:
        return "B"
    elif score >= 3:
        return "C"
    return "D"


def _pattern_strength(pat, rows, idx):
    """패턴별 강도 점수. 미지원 패턴은 1.0 반환."""
    try:
        r = rows[idx]
        if pat in ("engulfing", "engulfing_short"):
            body = abs(r["c"] - r["o"])
            if idx >= 1:
                prev_body = abs(rows[idx-1]["c"] - rows[idx-1]["o"]) or 1e-9
                return round(body / prev_body, 4)
        elif pat in ("fvg", "fvg_short"):
            if idx >= 2:
                gap = max(
                    rows[idx]["l"] - rows[idx-2]["h"],   # 불리시 갭
                    rows[idx-2]["l"] - rows[idx]["h"],   # 베어리시 갭
                    0)
                return round(gap / (r["c"] or 1e-9), 6)
        elif pat in ("inverted_hammer", "hammer"):
            body = abs(r["c"] - r["o"]) or 1e-9
            upper_wick = r["h"] - max(r["c"], r["o"])
            return round(max(upper_wick, 0) / body, 4)
        elif pat in ("marubozu", "marubozu_short"):
            body = abs(r["c"] - r["o"])
            rng  = (r["h"] - r["l"]) or 1e-9
            return round(body / rng, 4)
    except Exception:
        pass
    return 1.0


def _normalize(values):
    mn, mx = min(values), max(values)
    if mx == mn:
        return [1.0] * len(values)
    return [(v - mn) / (mx - mn) for v in values]


def _sort_universe_by_volume():
    """
    30일 평균 USDT 거래대금 기준 내림차순으로 trading_universe 정렬.
    universe.json 순서 갱신 후 정렬된 심볼 리스트 반환.
    """
    if not os.path.exists("universe.json"):
        return SYMBOLS
    uni = json.load(open("universe.json", encoding="utf-8"))
    syms = uni.get("trading_universe", [])
    if not syms:
        return SYMBOLS
    vol_usd = {}
    for sym in syms:
        try:
            rows = detlib.load_ohlcv(sym, "1d")
            if not rows:
                vol_usd[sym] = 0; continue
            window = rows[-30:] if len(rows) >= 30 else rows
            vol_usd[sym] = sum(r["c"] * r["v"] for r in window) / len(window)
        except Exception:
            vol_usd[sym] = 0
    sorted_syms = sorted(syms, key=lambda s: -vol_usd.get(s, 0))
    if sorted_syms != syms:
        uni["trading_universe"] = sorted_syms
        json.dump(uni, open("universe.json", "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
    return sorted_syms


def _build_ensemble(signals):
    """
    앙상블 스코어링 — TF 가중치 + 멀티TF 보너스 + 검증강도.

    ensemble_score = sum(TF_BASE_PTS[tf] × p_mult(pat)) + multitf_bonus
    ensemble_grade: A(>=8) / B(5-7) / C(3-4) / D(1-2)

    추가 필드:
      pattern_count   : 동시 발화 패턴 수
      patterns_fired  : 발화 패턴 목록
      ensemble_score  : 최종 앙상블 점수
      score_breakdown : {1d_pts, 4h_pts, 1h_pts, bonus}
      ensemble_grade  : A/B/C/D
      priority_score  : ensemble_score (하위호환)
      priority_rank   : 전체 순위
    """
    if not signals:
        return signals

    from collections import defaultdict

    # (symbol, direction) 그룹별 집계
    groups = defaultdict(list)
    for s in signals:
        groups[(s["symbol"], s["direction"])].append(s)

    group_meta = {}
    for (sym, dirn), sigs in groups.items():
        base_score  = 0.0
        tfs_present = set()
        breakdown   = {"1d_pts": 0.0, "4h_pts": 0.0, "1h_pts": 0.0, "bonus": 0}

        for s in sigs:
            tf  = s.get("tf", "1d")
            pat = s["pattern"]
            pts = TF_BASE_PTS.get(tf, 1) * _pval_mult(pat)
            base_score += pts
            tfs_present.add(tf)
            key = f"{tf}_pts"
            breakdown[key] = round(breakdown.get(key, 0.0) + pts, 2)

        bonus = _multitf_bonus(tfs_present)
        breakdown["bonus"] = bonus
        final = round(base_score + bonus, 2)

        group_meta[(sym, dirn)] = dict(
            ensemble_score  = final,
            score_breakdown = breakdown,
            ensemble_grade  = _ensemble_grade(final),
            pattern_count   = len(sigs),
            patterns_fired  = sorted({s["pattern"] for s in sigs}),
        )

    # 각 신호에 그룹 메타 반영
    for s in signals:
        m = group_meta[(s["symbol"], s["direction"])]
        s.update({
            "ensemble_score":  m["ensemble_score"],
            "score_breakdown": m["score_breakdown"],
            "ensemble_grade":  m["ensemble_grade"],
            "pattern_count":   m["pattern_count"],
            "patterns_fired":  m["patterns_fired"],
            "priority_score":  m["ensemble_score"],   # 하위호환
        })

    # 거래대금 순위
    uni_syms = SYMBOLS
    if os.path.exists("universe.json"):
        uni_syms = json.load(open("universe.json", encoding="utf-8")).get(
            "trading_universe", SYMBOLS)
    vol_rank = {sym: i for i, sym in enumerate(uni_syms)}

    signals.sort(key=lambda s: (
        -s["ensemble_score"],
        -s["pattern_count"],
        vol_rank.get(s["symbol"], 9999),
    ))

    for rank, s in enumerate(signals, 1):
        s["priority_rank"] = rank

    return signals


# 하위호환 alias
def _build_priority(signals):
    return _build_ensemble(signals)


def _fetch_one(sym, exchange, tf="1d"):
    """단일 종목 fetch. 성공=True, 실패=False. 출력은 터미널에 바로 표시."""
    out = f"data/{sym.lower()}_{tf}.csv"
    r = subprocess.run(
        [sys.executable, "fetch_data.py", "--exchange", exchange,
         "--symbol", f"{sym}/USDT", "--timeframe", tf,
         "--since", "2021-01-01", "--out", out])
    return r.returncode == 0


def fetch_all():
    """유니버스 전체 1d CSV + 하모닉용 4h CSV 순차 fetch."""
    import os
    os.makedirs("data", exist_ok=True)

    # BTC로 살아있는 거래소 탐색 (binance 451 차단 → bybit → okx)
    active_ex = None
    for ex in EXCHANGES:
        print(f"  [fetch] {ex} 테스트 중 (BTC)...", flush=True)
        if _fetch_one(SYMBOLS[0], ex, "1d"):
            active_ex = ex
            print(f"  [fetch] {ex} OK -> 전 종목 이 거래소 사용", flush=True)
            break
        print(f"  [fetch] {ex} 실패 -> 다음 거래소 시도", flush=True)

    if active_ex is None:
        print("  [fetch] 모든 거래소 실패 — 기존 CSV로 진행", flush=True)
        return

    # 1d fetch (유니버스 전체)
    ok = 1   # BTC는 이미 성공
    err = 0
    for s in SYMBOLS[1:]:
        if _fetch_one(s, active_ex, "1d"):
            ok += 1
        else:
            print(f"  [fetch] {s} 실패 ({active_ex})", flush=True)
            err += 1
    print(f"  [fetch] 1d 완료 {ok}/{len(SYMBOLS)}종목 (거래소={active_ex})", flush=True)

    # 4h fetch (하모닉 유니버스 — trading_universe 기준)
    h_syms = _harmonic_symbols()
    ok4 = 0
    for s in h_syms:
        if _fetch_one(s, active_ex, "4h"):
            ok4 += 1
    print(f"  [fetch] 4h 완료 {ok4}/{len(h_syms)}종목 (하모닉용)", flush=True)


def _tf_confirm(sym, direction):
    """
    4h 최근 3봉으로 1d 신호 방향 확증.
    long  → 양봉 2개 이상이면 True
    short → 음봉 2개 이상이면 True
    데이터 없거나 로드 실패 시 True 반환(확증으로 처리).
    """
    try:
        rows4h = detlib.load_ohlcv(sym, "4h")
        if not rows4h or len(rows4h) < 3:
            return True
        recent = rows4h[-3:]
        if direction == "long":
            return sum(1 for r in recent if r["c"] > r["o"]) >= 2
        else:
            return sum(1 for r in recent if r["c"] < r["o"]) >= 2
    except Exception:
        return True


def run_once(do_fetch=True, quick=False):
    global SYMBOLS
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    if do_fetch:
        print(f"[1] fetch {len(SYMBOLS)}종목 일봉 (순차, 완료 후 진행)...")
        fetch_all()
        print("[1] fetch 완료 -> 레짐 판정 시작")
    elif quick:
        print("[1] oncequick 모드 — fetch 생략, 기존 CSV로 진행")

    print("[2] 레짐 판정..."); regmap = rs.build_regime_map()
    latest = max(regmap); regime = regmap[latest]
    primary_regime = regime
    print(f"    현재 레짐(primary): {regime} ({latest})")

    print("[2.5] 온체인 보조 신호 수집...")
    onchain = {}
    try:
        import onchain_signals as oc
        onchain = oc.fetch(use_cache=True)
        regime  = oc.adjust_regime(primary_regime, onchain)
        if regime != primary_regime:
            print(f"    온체인 조정: {primary_regime} → {regime} "
                  f"(score={onchain.get('score', 0)})")
        else:
            print(f"    온체인 점수: {onchain.get('score', 0):+d} (레짐 변화 없음)")
    except Exception as e:
        print(f"    온체인 수집 실패(무시): {str(e)[:80]}")

    print("[3] direction_switch 갱신..."); ds.main()
    routing = json.load(open("direction_switch.json", encoding="utf-8"))["routing"]
    route = routing.get(regime, {})

    # fetch 모드에서만 거래대금 기준 재정렬 (quick 모드는 기존 순서 유지)
    if not quick:
        SYMBOLS = _sort_universe_by_volume() or SYMBOLS

    print("[4] 오늘 신호 탐지...")
    import importlib
    signals = []
    for pat in FOCUS:
        d = route.get(pat, "FLAT")
        if d not in ("long", "short"):
            continue
        mod = importlib.import_module(DETMOD[(pat, d)])
        for sym in SYMBOLS:
            try:
                rows = mod.load_ohlcv(sym, "1d")
            except FileNotFoundError:
                continue
            sigset = set(mod.detect(rows))
            last = len(rows) - 1
            if last in sigset:                 # 최신봉이 신호
                v = [r["v"] for r in rows]
                vr = round(v[last] / (sum(v[last - 20:last]) / 20), 2) if last >= 20 else None
                ps = _pattern_strength(pat, rows, last)
                entry = rows[last]["c"]
                stop_px = round(entry * (1 - STOP), 4) if d == "long" else round(entry * (1 + STOP), 4)
                tf_conf = _tf_confirm(sym, d)
                signals.append(dict(
                    pattern=pat, direction=d, symbol=sym, date=rows[last]["date"],
                    strength_vol_ratio=vr, pattern_strength=ps, regime=regime,
                    entry=round(entry, 4), stop=stop_px,
                    tf_confirmed=tf_conf,
                    take_profit="반대패턴 신호 or 레짐전환 or 최대30봉 시가청산"))
    # 채택된 추가 패턴(1d) — 방향 고정, 레짐 라우팅 없이 최신봉 신호 탐지
    adopted = []
    if os.path.exists("universe.json"):
        adopted = json.load(open("universe.json", encoding="utf-8")).get("adopted_patterns", [])
    for ap in adopted:
        ap_tf = ap.get("tf", "1d")
        mod   = importlib.import_module(ap["module"])
        if ap_tf == "1d":
            sym_list = SYMBOLS
        elif ap_tf == "4h":
            sym_list = _harmonic_symbols()
        else:  # "1h"
            sym_list = _1h_symbols()
        for sym in sym_list:
            try:
                rows = mod.load_ohlcv(sym, ap_tf)
            except FileNotFoundError:
                continue
            last = len(rows) - 1
            if last in set(mod.detect(rows)):
                v_ap = [r["v"] for r in rows]
                vr   = round(v_ap[last] / (sum(v_ap[last-20:last]) / 20), 2) if last >= 20 else None
                ps   = _pattern_strength(ap["pattern"], rows, last)
                entry = rows[last]["c"]
                dd = ap["direction"]
                stop_px = round(entry * (1 - 0.08), 4) if dd == "long" else round(entry * (1 + 0.08), 4)
                tf_conf = _tf_confirm(sym, dd) if ap_tf == "1d" else True
                signals.append(dict(pattern=ap["pattern"], direction=dd, symbol=sym,
                                    date=rows[last]["date"], strength_vol_ratio=vr,
                                    pattern_strength=ps, regime=regime,
                                    entry=round(entry, 4), stop=stop_px,
                                    tf_confirmed=tf_conf, tf=ap_tf,
                                    take_profit="반대패턴 신호 or 레짐전환 or 최대30봉 시가청산"))

    # 채택된 4h 전용 패턴 (three_soldiers_4h 등) — bull 레짐에서만 롱
    ADOPTED4H_REGIME = {"bull_btc": "long", "bull_altseason": "long"}
    adopted4h_dir = ADOPTED4H_REGIME.get(regime)
    adopted_4h = json.load(open("universe.json", encoding="utf-8")).get(
        "adopted_4h_patterns", []) if os.path.exists("universe.json") else []
    if adopted4h_dir and adopted_4h:
        h_syms = _harmonic_symbols()
        for ap in adopted_4h:
            try:
                mod4 = importlib.import_module(ap["module"])
            except ImportError:
                continue
            for sym in h_syms:
                try:
                    rows4h = mod4.load_ohlcv(sym, "4h")
                except (FileNotFoundError, RuntimeError):
                    continue
                last4 = len(rows4h) - 1
                if last4 not in set(mod4.detect(rows4h)):
                    continue
                entry4  = rows4h[last4]["c"]
                stop4   = round(entry4 * (1 - STOP), 4)
                signals.append(dict(
                    pattern=ap["pattern"], direction=adopted4h_dir, symbol=sym, tf="4h",
                    date=rows4h[last4]["date"], pattern_strength=1.0,
                    strength_vol_ratio=None, regime=regime,
                    entry=round(entry4, 4), stop=stop4,
                    tf_confirmed=True,
                    take_profit="레짐전환 or 최대30봉 시가청산"))
    elif adopted_4h:
        print(f"    [4h 패턴] 레짐={regime} -> bull 아님, 4h 전용 패턴 스킵")

    # 채택된 1h 전용 패턴 (bat_1h / butterfly_1h 등) — 레짐 무관 롱 (OOS 4/4 전구간 양수)
    adopted_1h = json.load(open("universe.json", encoding="utf-8")).get(
        "adopted_1h_patterns", []) if os.path.exists("universe.json") else []
    if adopted_1h:
        h1_syms = _1h_symbols()
        for ap in adopted_1h:
            try:
                mod1 = importlib.import_module(ap["module"])
            except ImportError:
                continue
            for sym in h1_syms:
                try:
                    rows1h = mod1.load_ohlcv(sym, "1h")
                except (FileNotFoundError, RuntimeError):
                    continue
                last1 = len(rows1h) - 1
                if last1 not in set(mod1.detect(rows1h)):
                    continue
                entry1 = rows1h[last1]["c"]
                stop1  = round(entry1 * (1 - STOP), 4)
                signals.append(dict(
                    pattern=ap["pattern"], direction=ap["direction"], symbol=sym, tf="1h",
                    date=rows1h[last1]["date"], pattern_strength=1.0,
                    strength_vol_ratio=None, regime=regime,
                    entry=round(entry1, 4), stop=stop1,
                    tf_confirmed=True,
                    take_profit="레짐전환 or 최대20봉 시가청산"))

    # 하모닉 4h 신호 탐지 (gartley / bat / butterfly)
    # 레짐 라우팅: bull_btc → long, 나머지 → 숏 디텍터 없으므로 스킵
    HARMONIC_REGIME = {"bull_btc": "long"}
    harmonic_dir = HARMONIC_REGIME.get(regime)
    if harmonic_dir:
        h_syms = _harmonic_symbols()
        for pat, modname in HARMONIC_FOCUS:
            try:
                mod = importlib.import_module(modname)
            except ImportError:
                continue
            for sym in h_syms:
                try:
                    rows4h = mod.load_ohlcv(sym, HARMONIC_TF)
                except (FileNotFoundError, RuntimeError):
                    continue
                sigset = set(mod.detect(rows4h))
                last = len(rows4h) - 1
                if last not in sigset:
                    continue
                entry = rows4h[last]["c"]
                stop_px = round(entry * (1 - STOP), 4)
                signals.append(dict(
                    pattern=pat, direction=harmonic_dir, symbol=sym, tf=HARMONIC_TF,
                    date=rows4h[last]["date"], pattern_strength=1.0,
                    strength_vol_ratio=None, regime=regime,
                    entry=round(entry, 4), stop=stop_px,
                    take_profit="레짐전환 or 최대30봉 시가청산"))
    else:
        print(f"    [하모닉] 레짐={regime} → 롱 조건 미충족, 하모닉 스킵", flush=True)

    # 앙상블 스코어링 (TF 가중치 + 멀티TF 보너스 + 검증강도)
    signals = _build_ensemble(signals)

    onchain_detail = {
        "funding": onchain.get("funding", {}).get("signal", "neutral"),
        "etf":     onchain.get("etf",     {}).get("signal", "neutral"),
        "stable":  onchain.get("stable",  {}).get("signal", "neutral"),
        "funding_avg_rate": onchain.get("funding", {}).get("avg_rate"),
        "etf_flows_3d":     onchain.get("etf",     {}).get("flows_3d", []),
        "stable_7d_pct":    onchain.get("stable",  {}).get("avg_7d_pct"),
    }
    out = dict(
        generated_at=stamp,
        regime=regime,
        primary_regime=primary_regime,
        regime_date=latest,
        onchain_score=onchain.get("score", 0),
        onchain_detail=onchain_detail,
        routing=route,
        n_signals=len(signals),
        signals=signals,
        note="페이퍼테스트용 신호 기록 - 실주문 없음",
    )
    json.dump(out, open("signals_today.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"[5] signals_today.json 저장: 신호 {len(signals)}건 (앙상블 스코어링 완료)")
    GRADE_ICON = {"A": "🔥", "B": "⭐", "C": "🔵", "D": "⚪"}
    for s in signals:
        cnt   = s.get("pattern_count", 1)
        rank  = s.get("priority_rank", "-")
        score = s.get("ensemble_score", 0)
        grade = s.get("ensemble_grade", "D")
        fired = s.get("patterns_fired", [s.get("pattern")])
        icon  = GRADE_ICON.get(grade, "")
        multi = " [멀티]" if cnt > 1 else ""
        bd    = s.get("score_breakdown", {})
        print(f"    #{rank} {icon}{grade}[{score:.1f}] {s['symbol']} {fired} {s['direction']}{multi} "
              f"@ {s['entry']} 손절 {s['stop']} "
              f"(1d={bd.get('1d_pts',0):.1f} 4h={bd.get('4h_pts',0):.1f} 1h={bd.get('1h_pts',0):.1f} +보너스{bd.get('bonus',0)})")

    # Supabase signals 테이블 동기화 (대시보드용)
    try:
        import supabase_client as sc
        if sc.available():
            today_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            sig_rows = [{"date": today_date, "symbol": s["symbol"], "pattern": s["pattern"],
                         "direction": s["direction"], "entry_price": s.get("entry"),
                         "stop_loss": s.get("stop"), "strength_vol_ratio": s.get("strength_vol_ratio"),
                         "pattern_strength": s.get("pattern_strength"),
                         "priority_score": s.get("priority_score"),
                         "regime": s.get("regime")} for s in signals]
            if sig_rows:
                sc.get_client("service").table("signals").upsert(
                    sig_rows, on_conflict="date,symbol,pattern,direction").execute()
                print(f"    signals Supabase UPSERT 완료 ({len(sig_rows)}건)")
    except Exception as e:
        print("    signals DB 동기화 실패(무시):", str(e)[:80])

    print("[6] 페이퍼 체결(진입+청산 모니터링)...")
    import exchange, paper_executor
    conn = exchange.connect()
    print(f"    거래소: {conn['mode']} | {conn['note']}")
    pr = paper_executor.run(stamp)
    out["paper"] = pr

    print("[7] daily_summary 기록...")
    try:
        import supabase_client as sc
        if sc.available():
            tr = json.load(open("paper_trades.json", encoding="utf-8")) if os.path.exists("paper_trades.json") else []
            cra = round(sum(t["pnl_usd"] for t in tr if t["method"] == "A") / 2000 * 100, 2)
            crd = round(sum(t["pnl_usd"] for t in tr if t["method"] == "D") / 2000 * 100, 2)
            day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            sc.get_client("service").table("daily_summary").upsert(
                {"date": day, "total_open": pr["open"], "signals_count": len(signals),
                 "cumulative_return_a": cra, "cumulative_return_d": crd},
                on_conflict="date").execute()
            print(f"    daily_summary UPSERT 완료 (open={pr['open']}, sig={len(signals)}, A={cra}%, D={crd}%)")
        else:
            print("    DB 미설정 - daily_summary 스킵(로컬 JSON 유지)")
    except Exception as e:
        print("    daily_summary 실패(무시):", str(e)[:80])
    return out


def daemon():
    print("scheduler 데몬 시작 - 매 UTC 00:00 실행 (Ctrl+C 중단)")
    while True:
        now = datetime.now(timezone.utc)
        nxt = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        wait = (nxt - now).total_seconds()
        print(f"  다음 실행까지 {wait/3600:.1f}시간 대기...")
        time.sleep(wait)
        try:
            run_once(do_fetch=True)
        except Exception as e:
            print("  run_once 오류:", e)


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "once":
        run_once(do_fetch=False)
    elif arg == "oncefull":
        run_once(do_fetch=True)
    elif arg == "oncequick":
        # 4h 마다 호출 — fetch 생략, 레짐 판정 + 신호 탐지 + 페이퍼 체결만
        run_once(do_fetch=False, quick=True)
    else:
        daemon()
