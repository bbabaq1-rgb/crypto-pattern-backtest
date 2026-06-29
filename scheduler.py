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


EXCHANGES = ["binance", "bybit", "okx"]   # 451 지역차단 시 순서대로 폴백

TIER_RANK = {"BTC": 0, "ETH": 1, "SOL": 2}   # 동점 시 시총 기준 (낮을수록 우선)


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


def _rank_signals(signals):
    """패턴강도 0.5 + 거래량배수 0.5 합산 후 내림차순 정렬. 동점 시 TIER_RANK 우선."""
    if not signals:
        return signals
    strengths = [s.get("pattern_strength") or 1.0 for s in signals]
    vols      = [float(s.get("strength_vol_ratio") or 1.0) for s in signals]
    norm_s    = _normalize(strengths)
    norm_v    = _normalize(vols)
    for i, s in enumerate(signals):
        s["pattern_strength"] = round(strengths[i], 4)
        s["priority_score"]   = round(0.5 * norm_s[i] + 0.5 * norm_v[i], 4)
    signals.sort(key=lambda s: (-s["priority_score"], TIER_RANK.get(s["symbol"], 99)))
    return signals


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


def run_once(do_fetch=True):
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    if do_fetch:
        print(f"[1] fetch {len(SYMBOLS)}종목 일봉 (순차, 완료 후 진행)...")
        fetch_all()
        print("[1] fetch 완료 -> 레짐 판정 시작")

    print("[2] 레짐 판정..."); regmap = rs.build_regime_map()
    latest = max(regmap); regime = regmap[latest]
    print(f"    현재 레짐: {regime} ({latest})")

    print("[3] direction_switch 갱신..."); ds.main()
    routing = json.load(open("direction_switch.json", encoding="utf-8"))["routing"]
    route = routing.get(regime, {})

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
                signals.append(dict(
                    pattern=pat, direction=d, symbol=sym, date=rows[last]["date"],
                    strength_vol_ratio=vr, pattern_strength=ps, regime=regime,
                    entry=round(entry, 4), stop=stop_px,
                    take_profit="반대패턴 신호 or 레짐전환 or 최대30봉 시가청산"))
    # 채택된 추가 패턴(캔들 등) — 방향 고정, 레짐 라우팅 없이 최신봉 신호 탐지
    adopted = []
    if os.path.exists("universe.json"):
        adopted = json.load(open("universe.json", encoding="utf-8")).get("adopted_patterns", [])
    for ap in adopted:
        mod = importlib.import_module(ap["module"])
        for sym in SYMBOLS:
            try:
                rows = mod.load_ohlcv(sym, "1d")
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
                signals.append(dict(pattern=ap["pattern"], direction=dd, symbol=sym,
                                    date=rows[last]["date"], strength_vol_ratio=vr,
                                    pattern_strength=ps, regime=regime,
                                    entry=round(entry, 4), stop=stop_px,
                                    take_profit="반대패턴 신호 or 레짐전환 or 최대30봉 시가청산"))

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

    # 우선순위 정렬 (패턴강도 0.5 + 거래량배수 0.5)
    signals = _rank_signals(signals)

    out = dict(generated_at=stamp, regime=regime, regime_date=latest,
               routing=route, n_signals=len(signals), signals=signals,
               note="페이퍼테스트용 신호 기록 - 실주문 없음")
    json.dump(out, open("signals_today.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"[5] signals_today.json 저장: 신호 {len(signals)}건 (우선순위 정렬 완료)")
    for s in signals:
        pri = s.get("priority_score", 0)
        print(f"    [{pri:.3f}] {s['symbol']} {s['pattern']} {s['direction']} "
              f"@ {s['entry']} 손절 {s['stop']} "
              f"(강도={s.get('pattern_strength','-')}, 거래량배수={s.get('strength_vol_ratio','-')})")

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
    else:
        daemon()
