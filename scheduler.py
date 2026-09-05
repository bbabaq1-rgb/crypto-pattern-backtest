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

# ── 실행 주기 분기 ──────────────────────────────────────────────────────────
# 크론은 매시(UTC 정시) 발화하지만, **느린 TF 탐지는 종전 6개 틱에서만** 돈다.
#
# 왜 나누는가: scheduler 는 `rows[last]`(= 아직 형성 중인 봉)에서 탐지하고,
# paper_executor 의 중복 진입 방어 키는 (symbol, pattern, direction, date) 로
# 날짜 단위다. 그래서 실행 횟수를 6->24 로 늘리면 '하루 1회 진입' 상한은 유지돼도
# **그 1회가 하루 중 더 이른 시각·덜 형성된 봉에서 잡히게 된다.** 이미 배포된
# 1d/4h/1w/1h 패턴의 진입 신호 분포가 검증 당시와 달라진다는 뜻이다.
#
# 따라서 매시 도는 것은 **exit_spec 을 가진 하위TF 패턴뿐**이다. 그 패턴들은
# 진입 지연에 민감해 시간당 진입이 배포 전제조건으로 측정됐고
# (cascade_realistic_2026_09: 1h 크론 +1.54% PASSED / 4h -0.37% REJECTED),
# 닫힌 봉 기준으로 탐지해 검증 프레임과 정렬한다(_closed_idx 참조).
# bat_1h / butterfly_1h 는 exit_spec 이 없으므로 종전 6틱을 그대로 유지한다.
#
# **틱 판정은 워크플로가 플래그로 명시한다(--slow / --fast).** 2026-09-02 발견:
# 실행 시각의 hour 로 판정하면 큐 지연이 정각을 넘긴 실행(4h 시대 364건 중 27%,
# 8/05·8/06·8/27 은 6틱 전부)이 느린틱으로 인식되지 않아 1d/4h 탐지가 조용히
# 빠진다. 그래서 4h 크론 워크플로(daily_scheduler.yml)는 항상 --slow, 매시
# 워크플로(fast_scheduler.yml)는 항상 --fast 를 넘긴다. 시간 기반 판정은 플래그가
# 없을 때(로컬 수동 실행)의 폴백일 뿐이다.
SLOW_TICK_HOURS = (0, 4, 8, 12, 16, 20)


def is_slow_tick(now=None):
    """(폴백) 실행 시각으로 느린 TF 탐지 여부 추정. 워크플로 플래그가 우선한다."""
    now = now or datetime.now(timezone.utc)
    return now.hour in SLOW_TICK_HOURS


def _tick_flag(argv):
    """argv 의 --slow / --fast → True / False. 둘 다 없으면 None(시간 기반 폴백)."""
    if "--slow" in argv and "--fast" in argv:
        raise SystemExit("--slow 와 --fast 는 동시에 줄 수 없다")
    if "--slow" in argv:
        return True
    if "--fast" in argv:
        return False
    return None


def _closed_idx(rows):
    """
    마지막 **닫힌** 봉의 인덱스. 데이터가 부족하면 None.

    CSV 마지막 행은 거래소가 주는 '형성 중'인 봉이다(fetch_data 는 이를 걸러내지
    않는다). 검증은 닫힌 봉의 종가로 신호를 판정했으므로, 검증 프레임과 같은
    신호 집합을 내려면 형성 중인 봉을 빼고 봐야 한다.
    """
    return len(rows) - 2 if len(rows) >= 2 else None


MAX_HOLD = 30
DETMOD = {("engulfing", "long"): "detector_engulfing",
          ("engulfing", "short"): "detector_engulfing_short",
          ("fvg", "long"): "detector_fvg",
          ("fvg", "short"): "detector_fvg_short"}

# 패턴별 탐지 유니버스 (2026-07-06 사용자 결정, 거래대금 코호트 분석 반영):
#   코호트별 엣지 측정(research_log tier/cohort 행, report.md) 결과 —
#   engulfing top20까지 유지(mean +2.65%/median +9.94%), fvg는 top30이 전체보다
#   질 우위(+2.36%/median +6.53%), inverted_hammer·marubozu는 top7 밖 급감/불안정.
#   "majors"=검증 7종목 / "topN"=30일 평균 거래대금 상위 N(매 실행 재계산) / "all"=전체.
MAJORS = list(detlib.SYMBOLS)   # BTC SOL ETH BNB XRP ADA AVAX
PATTERN_UNIVERSE = {
    # engulfing: 검증이 통과한 셀은 거래대금 1~20위(무기한 기준 2026-09-04 스캔 +3.65% PASS,
    # 21~30위는 median -4.5%/boot_p .141 REJECT). **top30 은 사용자 강제(2026-09-04)** —
    # "ARB 가 기준 변경으로 빠질까 봐"(실제 ARB 는 무기한 기준 13위로 top20 안). 21~30위
    # 구간의 진입은 검증되지 않은 셀에서 나가는 것임을 기록해 둔다. 되돌리려면 "top20".
    "engulfing":       "top30",
    "fvg":             "top30",
    "inverted_hammer": "majors",
    "marubozu":        "majors",
}

_VOL_RANKED: list = []          # 실행당 1회 계산 캐시


def _volume_ranked():
    """trading_universe를 30일 평균 거래대금(close×volume) 내림차순 정렬.
    로컬 1d CSV 기준 — 결정론적(같은 데이터 → 같은 순위)."""
    global _VOL_RANKED
    if _VOL_RANKED:
        return _VOL_RANKED
    scored = []
    for s in SYMBOLS:
        try:
            rows = detlib.load_ohlcv(s, "1d")
        except Exception:
            continue
        if len(rows) < 35:
            continue
        qv = sum(r["c"] * r["v"] for r in rows[-30:]) / 30
        scored.append((s, qv))
    scored.sort(key=lambda x: -x[1])
    _VOL_RANKED = [s for s, _ in scored]
    return _VOL_RANKED


# 채택 패턴의 레짐 게이트 (2026-09-05). universe.json adopted 항목의 선택 필드 `regimes`:
#   없음        → 종전 동작 그대로. 1d 는 게이트 없음(ih/marubozu), 4h 는 전역 bull-only(three_soldiers).
#   "all"       → 전 레짐 허용 (예: 레짐 무관으로 검증된 4h 패턴)
#   [레짐, ...] → 그 레짐에서만 (예: bull_btc 셀만 통과한 패턴)
# 검증이 레짐 셀 단위로 통과한 패턴을 그 셀에서만 켜기 위한 것이다. 기존 항목은 필드가 없어 불변.
ADOPTED4H_REGIME = {"bull_btc": "long", "bull_altseason": "long"}


def adopted_regime_ok(ap, regime, tf):
    rg = ap.get("regimes")
    if rg is None:
        return True if tf == "1d" else (regime in ADOPTED4H_REGIME)
    if rg == "all":
        return True
    return regime in rg


def _cohort_symbols(rule, base):
    """
    adopted 항목의 선택 필드 `cohort` (2026-09-05). 검증이 특정 거래대금 코호트에서만 통과한
    패턴을 그 코호트에서만 켜기 위한 것이다.
      없음 / "all" → base 그대로(종전 동작)
      "topN"       → 30일 평균 거래대금 상위 N(_volume_ranked, 매 실행 재계산) ∩ base
      "majors"     → 검증 7종목 ∩ base
    확인 시험(revival)의 top30 코호트(turnover_rank: 최근 30봉 close×volume 평균)와 같은 정의다.
    """
    if not rule or rule == "all":
        return list(base)
    bs = set(base)
    if rule == "majors":
        return [s for s in MAJORS if s in bs]
    if isinstance(rule, str) and rule.startswith("top"):
        return [s for s in _volume_ranked()[:int(rule[3:])] if s in bs]
    return list(base)


def _syms_for_pattern(pattern):
    """패턴별 탐지 대상 심볼 목록. 미지정 패턴은 전체 유니버스."""
    rule = PATTERN_UNIVERSE.get(pattern, "all")
    if rule == "majors":
        return MAJORS
    if rule.startswith("top"):
        return _volume_ranked()[:int(rule[3:])]
    return SYMBOLS

# 하모닉 패턴 4h — **등재 정지 (2026-09-03)**. 디텍터가 D 피벗 봉을 신호로 찍는데
# 피벗 확정에 이후 3봉이 필요해 마지막 봉에서는 절대 발화하지 못했고(배포 이래 진입 0건),
# 백테스트는 그 미래 3봉을 보고 D 를 골라 룩어헤드였다. detector_harmonic_base 를
# 확정 봉(D+3) 기준으로 고친 뒤 재검증(validate_confirm_bar.py)을 통과해야 복귀한다.
# 복귀 시 HARMONIC_FOCUS 에 다시 넣는다 — 그 전까지 이 블록은 돌지 않는다.
HARMONIC_SUSPENDED = [
    ("gartley",   "detector_gartley"),
    ("bat",       "detector_bat"),
    ("butterfly", "detector_butterfly"),
]
HARMONIC_FOCUS = []
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


_EXIT_SPECS: dict | None = None


def _exit_specs():
    """
    registry.json 의 exit_spec — 하위 TF ATR 배리어 패턴의 청산 규격.

    paper_executor.load_exit_specs 와 같은 원천을 읽는다. 스케줄러는 이 값으로
    신호의 손절/익절 표시가를 맞춘다. 이게 없으면 ±8% 로 표기돼 실제 집행값
    (±1.5xATR ≈ 0.75~1.5%)과 5~10배 어긋난 알림이 나간다.
    """
    global _EXIT_SPECS
    if _EXIT_SPECS is None:
        try:
            reg = json.load(open("registry.json", encoding="utf-8"))
            _EXIT_SPECS = {p["id"]: p["exit_spec"] for p in reg.get("patterns", [])
                           if p.get("exit_spec") and p.get("id")}
        except Exception:
            _EXIT_SPECS = {}
    return _EXIT_SPECS


EXCHANGES = ["binance", "bybit", "okx"]   # 451 지역차단 시 순서대로 폴백

# ── 앙상블 스코어링 설정 ─────────────────────────────────────────────────────
# TF별 기본 점수
TF_BASE_PTS = {"1w": 3, "1d": 3, "4h": 2, "1h": 1}

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
    # 미배포(passed_not_deployed) — 1시간 이내 진입 보장 시에만 활성화.
    # 활성화 경로: universe.json 의 adopted_1h_patterns 에 추가.
    "cascade_fade_long_1h": 0.0001,   # 2차 재시험 boot_p 0.000
    "bat_1h":            0.034,     # boot_p
    "butterfly_1h":      0.024,     # boot_p
    "triple_bottom":     0.023,     # boot_p (1w, 2026-08-29 2차 검증 PASSED — 4h는 3년치 재검증서 기각)
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
        vol_rank.get(s["symbol"], 9999),   # RS 정렬 폐기(2026-07-08, 레짐 중복)
    ))

    for rank, s in enumerate(signals, 1):
        s["priority_rank"] = rank

    return signals


# 하위호환 alias
def _build_priority(signals):
    return _build_ensemble(signals)


# ── BTC 대비 상대강도(RS) — 표시 전용 (필터 폐기) ──────────────────────────────
# rs_score/cap_score는 계산·표시만. 사이징/필터/앙상블 정렬에 사용하지 않는다.
#   - weak_rs(롱 rs<0.2 ×0.5): 2026-07-08 폐기. 레짐 통제 검증(backtest_rs_controlled.py)
#     결과 rs 순진 엣지(+2.76%p)는 시장 레짐(cap)의 교란 — 통제 후 cap구간 우위 1/3,
#     Welch p=0.38로 독립 엣지 소멸. 자유도 감소 위해 필터 제거.
#   - cap_score: 개별 필터로는 역효과(backtest_capture.py) → 표시만.
# 사이징에 남은 시장 신호는 레짐 오버레이(avg_cap>0 롱 ×0.6)뿐 — 이건 검증 유지.


def _attach_rs(signals):
    """각 신호에 rs_score / cap_score 부착 (표시 전용). BTC는 기준점(None)."""
    try:
        from relative_strength import compute_rs, compute_capture
        btc = detlib.load_ohlcv("BTC", "1d")
    except Exception as e:
        print(f"    [RS] BTC 데이터 없음 — RS 스킵({str(e)[:40]})")
        return signals
    cache = {}
    for s in signals:
        sym = s["symbol"]
        if sym == "BTC":
            s["rs_score"], s["cap_score"] = None, None
            continue
        if sym not in cache:
            try:
                rows = detlib.load_ohlcv(sym, "1d")
                cache[sym] = (compute_rs(rows, btc, symbol=sym)["rs_score"],
                              compute_capture(rows, btc, symbol=sym)["cap_score"])
            except Exception:
                cache[sym] = (None, None)
        s["rs_score"], s["cap_score"] = cache[sym]
    return signals


def _avg_alt_metrics():
    """유니버스 알트 평균 rs_score / cap_score.
    avg_alt_rs = 알트시즌 근접도(관측).
    avg_alt_cap = 시장 비대칭 국면 — 백테스트상 롱 타이밍 레짐 지표
      (매우 음수=집단 bleed→반전 롱 최적, 양수=complacent→롱 축소). backtest_regime_capture.py
    """
    try:
        from relative_strength import compute_rs, compute_capture
        btc = detlib.load_ohlcv("BTC", "1d")
    except Exception:
        return None, None
    rs_vals, cap_vals = [], []
    for sym in SYMBOLS:
        if sym == "BTC":
            continue
        try:
            rows = detlib.load_ohlcv(sym, "1d")
            rs_vals.append(compute_rs(rows, btc, symbol=sym)["rs_score"])
            c = compute_capture(rows, btc, symbol=sym)["cap_score"]
            if c is not None:
                cap_vals.append(c)
        except Exception:
            continue
    avg_rs  = round(sum(rs_vals) / len(rs_vals), 4) if rs_vals else None
    avg_cap = round(sum(cap_vals) / len(cap_vals), 4) if cap_vals else None
    return avg_rs, avg_cap


def fetch_all(tfs=("1d", "4h", "1h")):
    """유니버스 전체 CSV 증분 fetch (in-process, okx 우선).

    tfs: 수집할 타임프레임. 하위TF 전용 실행(느린 TF 탐지를 건너뛰는 시각)에서는
         ("1h",) 만 넘겨 러너 시간과 거래소 호출을 3분의 1로 줄인다.

    - fetch_data.update_csv: 기존 CSV 있으면 마지막 봉 이후만 append,
      없으면 WINDOW_DAYS(1d 900일/4h 130일/1h 40일) 최근 구간만 수집.
    - 과거 subprocess+since2021 방식은 러너에서 100분+ 걸려 폐기.
    """
    import os
    import fetch_data
    os.makedirs("data", exist_ok=True)

    for tf in tfs:
        t0 = time.time()
        ok = fail = new_total = 0
        for s in SYMBOLS:
            new_n, total_n = fetch_data.update_csv(
                f"{s}/USDT", tf, f"data/{s.lower()}_{tf}.csv")
            if total_n > 0:
                ok += 1; new_total += new_n
            else:
                fail += 1
        print(f"  [fetch] {tf} 완료 {ok}/{len(SYMBOLS)}종목 "
              f"(+{new_total}봉, 실패 {fail}, {time.time()-t0:.0f}s)", flush=True)


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


def run_once(do_fetch=True, quick=False, slow_tick=None):
    global SYMBOLS
    now_utc = datetime.now(timezone.utc)
    stamp = now_utc.strftime("%Y-%m-%dT%H:%MZ")
    # 느린 TF 탐지 여부. None 이면 현재 시각으로 판정(테스트에서 주입 가능).
    src = "플래그"
    if slow_tick is None:
        slow_tick = is_slow_tick(now_utc)
        src = "시간폴백"
    print(f"[0] 실행 주기: {'느린TF 포함(1d/4h/1w + 1h 일반)' if slow_tick else '하위TF 전용(exit_spec 패턴만)'} "
          f"| 판정={src} | UTC {now_utc:%H:%M}")
    # 느린 TF 탐지를 건너뛰는 실행은 1h 만 받으면 된다. 단 청산 평가는 보유 중인
    # 포지션의 TF(1d/4h 포함) 봉을 읽으므로, 그 CSV 는 직전 느린 틱에서 받아둔 것을
    # 쓴다 — 러너 파일시스템이 매번 비므로 fetch 범위를 줄이면 이전 봉이 없다.
    # 따라서 포지션이 있을 수 있는 한 1d/4h 도 함께 받는다(안전 우선).
    tfs = ("1d", "4h", "1h")
    if do_fetch:
        print(f"[1] fetch {len(SYMBOLS)}종목 {'/'.join(tfs)} (증분)...")
        fetch_all(tfs)
        print("[1] fetch 완료 -> 레짐 판정 시작")
    elif quick:
        # 러너는 매번 빈 파일시스템 → 증분 fetch 필수 (최근 구간만이라 수 분)
        print(f"[1] oncequick — {len(SYMBOLS)}종목 {'/'.join(tfs)} 증분 fetch...")
        fetch_all(tfs)

    print("[2] 레짐 판정..."); regmap = rs.build_regime_map()
    latest = max(regmap); regime = regmap[latest]
    primary_regime = regime
    print(f"    현재 레짐(primary): {regime} ({latest})")

    print("[2.5] 온체인 보조 신호 수집 (표시 전용)...")
    # 펀딩비 일별 이력 적재 (2026-09-04) — **매매 무관, 데이터 축적 전용**.
    # OKX 이력이 94일뿐이라 '펀딩비 극단 청산'을 지금 시험할 수 없다. 6개월 뒤 시험이
    # 가능하도록 지금부터 쌓아 둔다. 어떤 실패도 매매를 막지 않는다(모듈이 예외를 삼킨다).
    try:
        import funding_accrual as _fa
        _n, _msg = _fa.accrue(quiet=True)
        if _n:
            print(f"    [funding 적재] {_n}일 (시험용 축적, 매매 미사용)")
        elif "테이블 없음" in _msg:
            print(f"    [funding 적재] 건너뜀 — {_msg}")
    except Exception as _e:
        print(f"    [funding 적재] 건너뜀 ({str(_e)[:50]})")
    # 2026-09-03: 온체인 조정(bear/bull_btc → sideways)은 어떤 검증도 거치지 않은 실거래
    # 전용 필터였다(orchestrator/method_* 미참조). 라우팅·게이팅은 raw 레짐만 쓰고,
    # 조정값은 로그·대시보드 표시로만 남긴다(RS 필터 폐기 2026-07-08 과 같은 원칙).
    onchain = {}
    onchain_adjusted_regime = primary_regime
    try:
        import onchain_signals as oc
        onchain = oc.fetch(use_cache=True)
        onchain_adjusted_regime = oc.adjust_regime(primary_regime, onchain)
        if onchain_adjusted_regime != primary_regime:
            print(f"    온체인 힌트: {primary_regime} → {onchain_adjusted_regime} "
                  f"(score={onchain.get('score', 0)}) — 표시 전용, 라우팅 미반영")
        else:
            print(f"    온체인 점수: {onchain.get('score', 0):+d} (레짐 변화 없음)")
    except Exception as e:
        print(f"    온체인 수집 실패(무시): {str(e)[:80]}")
    regime = primary_regime

    print("[3] direction_switch 갱신..."); ds.main()
    routing = json.load(open("direction_switch.json", encoding="utf-8"))["routing"]
    route = routing.get(regime, {})

    # fetch 모드에서만 거래대금 기준 재정렬 (quick 모드는 기존 순서 유지)
    if not quick:
        SYMBOLS = _sort_universe_by_volume() or SYMBOLS

    print("[4] 오늘 신호 탐지...")
    import importlib
    signals = []
    # 느린 TF 블록(1d FOCUS / adopted 1d·4h·1w / 4h 전용 / 하모닉)은 SLOW_TICK_HOURS
    # 에서만 돈다 — 매시 돌리면 배포된 패턴의 진입 분포가 검증 당시와 달라진다.
    for pat in (FOCUS if slow_tick else []):
        d = route.get(pat, "FLAT")
        if d not in ("long", "short"):
            continue
        mod = importlib.import_module(DETMOD[(pat, d)])
        pat_syms = _syms_for_pattern(pat)   # 패턴별 차등 유니버스(fvg=전체, 나머지=메이저)
        for sym in pat_syms:
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
                    ts=rows[last].get("ts"),
                    strength_vol_ratio=vr, pattern_strength=ps, regime=regime,
                    entry=round(entry, 4), stop=stop_px,
                    tf_confirmed=tf_conf,
                    take_profit="반대패턴 신호 or 레짐전환 or 최대30봉 시가청산"))
    # 채택된 추가 패턴(1d) — 방향 고정, 레짐 라우팅 없이 최신봉 신호 탐지
    adopted = []
    if os.path.exists("universe.json"):
        adopted = json.load(open("universe.json", encoding="utf-8")).get("adopted_patterns", [])
    for ap in (adopted if slow_tick else []):
        ap_tf = ap.get("tf", "1d")
        if not adopted_regime_ok(ap, regime, ap_tf):
            print(f"    [adopted] {ap['pattern']} 레짐={regime} -> {ap.get('regimes')} 아님, 스킵")
            continue
        mod   = importlib.import_module(ap["module"])
        if ap_tf == "1d":
            # 패턴별 차등 유니버스(inverted_hammer/marubozu → 메이저 한정)
            sym_list = _syms_for_pattern(ap["pattern"])
        elif ap_tf == "4h":
            sym_list = _harmonic_symbols()
        elif ap_tf == "1w":
            sym_list = SYMBOLS          # 1d 리샘플이라 1d 보유 전 종목
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
                                    date=rows[last]["date"], ts=rows[last].get("ts"),
                                    strength_vol_ratio=vr,
                                    pattern_strength=ps, regime=regime,
                                    entry=round(entry, 4), stop=stop_px,
                                    tf_confirmed=tf_conf, tf=ap_tf,
                                    take_profit="반대패턴 신호 or 레짐전환 or 최대30봉 시가청산"))

    # 채택된 4h 전용 패턴 (three_soldiers_4h 등). 항목에 `regimes` 가 없으면 종전 전역 규칙
    # (bull_btc/bull_altseason 에서만) — adopted_regime_ok 참조. 방향은 항목의 direction.
    adopted_4h = json.load(open("universe.json", encoding="utf-8")).get(
        "adopted_4h_patterns", []) if os.path.exists("universe.json") else []
    if slow_tick and adopted_4h:
        h_syms = _harmonic_symbols()
        for ap in adopted_4h:
            if not adopted_regime_ok(ap, regime, "4h"):
                print(f"    [4h 패턴] {ap['pattern']} 레짐={regime} -> 허용 레짐 아님, 스킵")
                continue
            try:
                mod4 = importlib.import_module(ap["module"])
            except ImportError:
                continue
            dd4 = ap.get("direction", "long")
            # 항목별 코호트(없으면 4h 데이터 보유 전 종목 = 종전) / 닫힌 봉 탐지(없으면 마지막 행 = 종전).
            # 2026-09-05 게이트 v2 통과 셀은 top30 코호트·닫힌 봉 종가 기준으로 검증됐으므로 그 조건을
            # 그대로 건다. three_soldiers_4h 는 두 필드가 없어 동작 불변.
            syms4 = _cohort_symbols(ap.get("cohort"), h_syms)
            closed4 = bool(ap.get("detect_on_closed_bar"))
            for sym in syms4:
                try:
                    rows4h = mod4.load_ohlcv(sym, "4h")
                except (FileNotFoundError, RuntimeError):
                    continue
                last4 = _closed_idx(rows4h) if closed4 else len(rows4h) - 1
                if last4 is None or last4 not in set(mod4.detect(rows4h)):
                    continue
                entry4  = rows4h[last4]["c"]
                stop4   = round(entry4 * (1 - STOP), 4) if dd4 == "long" else round(entry4 * (1 + STOP), 4)
                signals.append(dict(
                    pattern=ap["pattern"], direction=dd4, symbol=sym, tf="4h",
                    date=rows4h[last4]["date"], ts=rows4h[last4].get("ts"),
                    pattern_strength=1.0,
                    strength_vol_ratio=None, regime=regime,
                    entry=round(entry4, 4), stop=stop4,
                    tf_confirmed=True,
                    take_profit="레짐전환 or 최대30봉 시가청산"))

    # 채택된 1h 전용 패턴 (bat_1h / butterfly_1h 등) — 레짐 무관 롱 (OOS 4/4 전구간 양수)
    adopted_1h = json.load(open("universe.json", encoding="utf-8")).get(
        "adopted_1h_patterns", []) if os.path.exists("universe.json") else []
    if adopted_1h:
        h1_syms = _1h_symbols()
        for ap in adopted_1h:
            spec_ap = _exit_specs().get(ap["pattern"])
            # exit_spec 패턴만 매시 돈다. 나머지(bat_1h/butterfly_1h)는 exit_spec 이
            # 없어 진입 지연 민감도가 측정된 적이 없으므로 종전 6틱을 유지한다 —
            # 매시로 늘리면 탐지 기회가 4배가 돼 검증 당시와 진입 분포가 달라진다.
            if not spec_ap and not slow_tick:
                continue
            try:
                mod1 = importlib.import_module(ap["module"])
            except ImportError:
                continue
            for sym in h1_syms:
                try:
                    rows1h = mod1.load_ohlcv(sym, "1h")
                except (FileNotFoundError, RuntimeError):
                    continue
                # exit_spec 패턴은 **닫힌 봉**에서 탐지한다. CSV 마지막 행은 형성
                # 중인 봉이라, 그걸 보면 검증(닫힌 봉 종가 기준)과 다른 신호 집합이
                # 된다. 종전 패턴은 동작을 바꾸지 않기 위해 마지막 행 그대로 둔다.
                if spec_ap:
                    last1 = _closed_idx(rows1h)
                    if last1 is None:
                        continue
                else:
                    last1 = len(rows1h) - 1
                if last1 not in set(mod1.detect(rows1h)):
                    continue
                entry1 = rows1h[last1]["c"]
                # exit_spec 이 있는 패턴(하위TF ATR 배리어)은 손절·익절을 ATR 로
                # 산출한다. paper_executor 가 진입 시 같은 식으로 다시 계산하므로
                # 값이 일치하며, 여기서 맞춰야 알림·대시보드 표기가 실제 집행과 같다.
                spec1 = spec_ap
                target1 = None
                if spec1:
                    import intraday_lab as _ilab
                    atr1 = _ilab.atr_series(rows1h, spec1.get("atr_period", 14))[last1]
                    if not atr1 or atr1 <= 0:
                        continue          # ATR 미산출 → 청산 규칙 정의 불가, 스킵
                    dist1 = spec1.get("k_atr", 1.5) * atr1
                    if ap["direction"] == "long":
                        stop1, target1 = entry1 - dist1, entry1 + dist1
                    else:
                        stop1, target1 = entry1 + dist1, entry1 - dist1
                    stop1, target1 = round(stop1, 8), round(target1, 8)
                    tp_txt = (f"±{spec1.get('k_atr', 1.5)}xATR{spec1.get('atr_period', 14)} "
                              f"거래소 OCO 브래킷 / {spec1.get('horizon_bars', 12)}봉 시간청산")
                else:
                    stop1 = round(entry1 * (1 - STOP), 4)
                    tp_txt = "레짐전환 or 최대20봉 시가청산"
                signals.append(dict(
                    pattern=ap["pattern"], direction=ap["direction"], symbol=sym, tf="1h",
                    date=rows1h[last1]["date"], ts=rows1h[last1].get("ts"),
                    pattern_strength=1.0,
                    strength_vol_ratio=None, regime=regime,
                    entry=round(entry1, 4), stop=stop1, target=target1,
                    tf_confirmed=True,
                    take_profit=tp_txt))

    # 하모닉 4h 신호 탐지 (gartley / bat / butterfly)
    # 레짐 라우팅: bull_btc → long, 나머지 → 숏 디텍터 없으므로 스킵
    HARMONIC_REGIME = {"bull_btc": "long"}
    harmonic_dir = HARMONIC_REGIME.get(regime)
    if slow_tick and harmonic_dir:
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
                    date=rows4h[last]["date"], ts=rows4h[last].get("ts"),
                    pattern_strength=1.0,
                    strength_vol_ratio=None, regime=regime,
                    entry=round(entry, 4), stop=stop_px,
                    take_profit="레짐전환 or 최대30봉 시가청산"))
    elif slow_tick:
        print(f"    [하모닉] 레짐={regime} → 롱 조건 미충족, 하모닉 스킵", flush=True)

    # RS(BTC 대비 상대강도) 부착 → 앙상블 스코어링(RS 보조 정렬 포함)
    signals = _attach_rs(signals)
    signals = _build_ensemble(signals)
    avg_alt_rs, avg_alt_cap = _avg_alt_metrics()
    if avg_alt_rs is not None:
        print(f"    [RS] 유니버스 평균 alt RS = {avg_alt_rs:+.3f} "
              f"({'알트 강세' if avg_alt_rs > 0 else '알트 약세'})")
    if avg_alt_cap is not None:
        state = ("집단 bleed(반전 롱 우호)" if avg_alt_cap < -0.2
                 else "complacent(롱 축소)" if avg_alt_cap > 0 else "중립")
        print(f"    [RS] 시장 비대칭 avg_cap = {avg_alt_cap:+.3f} → {state}")

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
        onchain_adjusted_regime=onchain_adjusted_regime,
        regime_date=latest,
        onchain_score=onchain.get("score", 0),
        onchain_detail=onchain_detail,
        avg_alt_rs=avg_alt_rs,             # 알트시즌 근접도(관측 지표)
        avg_alt_cap=avg_alt_cap,           # 시장 비대칭 국면(롱 타이밍 레짐 지표)
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
                         "ensemble_score": s.get("ensemble_score"),
                         "ensemble_grade": s.get("ensemble_grade"),
                         "patterns_fired": json.dumps(s.get("patterns_fired", [s.get("pattern")])),
                         "tf_confirmed": s.get("tf_confirmed", True),
                         "rs_score": s.get("rs_score"),
                         "cap_score": s.get("cap_score"),
                         "regime": s.get("regime")} for s in signals]
            if sig_rows:
                cli = sc.get_client("service")
                # insert 먼저(스키마 내성) → 성공 후에만 오늘 자 이전 행 삭제.
                # (과거 delete→insert 순서는 insert가 컬럼 오류로 실패하면
                #  테이블이 비워지는 사고를 냈다)
                inserted, dropped = sc.insert_tolerant(cli, "signals", sig_rows)
                new_ids = [r["id"] for r in inserted if r.get("id")]
                if new_ids:
                    q = cli.table("signals").delete().eq("date", today_date)
                    q = q.not_.in_("id", new_ids)
                    q.execute()
                msg = f" (스키마 미존재 컬럼 제외: {dropped})" if dropped else ""
                print(f"    signals Supabase 동기화 완료 ({len(sig_rows)}건){msg}")
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
            row = {"date": day, "total_open": pr["open"], "signals_count": len(signals),
                   "cumulative_return_a": cra, "cumulative_return_d": crd,
                   "avg_alt_rs": avg_alt_rs, "avg_alt_cap": avg_alt_cap}
            import re as _re
            for _ in range(4):                # 없는 컬럼 자동 제외 후 재시도
                try:
                    sc.get_client("service").table("daily_summary").upsert(
                        row, on_conflict="date").execute()
                    break
                except Exception as _e:
                    mm = _re.search(r"'(\w+)' column", str(_e))
                    if mm and mm.group(1) in row:
                        row.pop(mm.group(1))
                    else:
                        raise
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
    flags = [a for a in sys.argv[1:] if a.startswith("--")]
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    arg = args[0] if args else ""
    tick = _tick_flag(flags)          # --slow / --fast / None(시간 폴백)
    if arg == "once":
        run_once(do_fetch=False, slow_tick=tick)
    elif arg == "oncefull":
        run_once(do_fetch=True, slow_tick=tick)
    elif arg == "oncequick":
        # daily_scheduler.yml(4h, --slow): 증분 fetch + 전체 탐지 + 체결/청산.
        # fast_scheduler.yml(매시, --fast): 증분 fetch + exit_spec 패턴 탐지 + 체결/청산.
        run_once(do_fetch=False, quick=True, slow_tick=tick)
    else:
        daemon()
