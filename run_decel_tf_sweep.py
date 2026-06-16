"""
triple_bottom_desc x decel_ratio sweep  (2종목 x 2타임프레임)
  - BTC/USDT, SOL/USDT  x  1h, 15m
  - min_conf=0.0, hold=10, breakout_mult=1.1 고정
  - decel_ratio: None / 1.0 / 0.7 / 0.5
  - decel_ratio=None 상태에서 각 신호의 decel_actual 원시값 출력
"""
import sys
import statistics as st
sys.path.insert(0, ".")

from triple_bottom_volume import detect_triple_bottom_descending
from backtest import load_csv, signal_is_match, signal_signature

HOLD         = 10
MIN_CONF     = 0.0
FEE          = 0.001
WARMUP       = 60
BREAKOUT_MULT = 1.1

# (종목, 타임프레임) -> csv 경로
DATASETS = [
    ("BTC/USDT", "1h",  "data/btc_1h.csv"),
    ("SOL/USDT", "1h",  "data/sol_1h.csv"),
    ("BTC/USDT", "15m", "data/btc_15m.csv"),
    ("SOL/USDT", "15m", "data/sol_15m.csv"),
]
DECEL_SETTINGS = [None, 1.0, 0.7, 0.5]


def run_all_decels(ohlcv):
    """
    봉마다 decel_ratio=None 으로 1회만 탐지(가장 느슨).
    decel 은 matched 에만 AND로 들어가므로 같은 window·decel_actual 에서
    각 임계값의 matched 를 직접 계산할 수 있다. 설정별 쿨다운/ dedup 만 분리.
    → 4개 설정을 1회 탐지로 동시 백테스트(독립 실행과 결과 동일).
    """
    state = {dr: dict(trades=[], traded=set(), next_allowed=WARMUP)
             for dr in DECEL_SETTINGS}

    for i in range(WARMUP, len(ohlcv) - HOLD):
        # 모든 설정이 쿨다운 중이면 탐지 자체를 건너뛴다
        if all(i < s["next_allowed"] for s in state.values()):
            continue

        sig = detect_triple_bottom_descending(
            ohlcv[:i + 1], decel_ratio=None, breakout_mult=BREAKOUT_MULT)
        # None 기준 matched = (broke and vconf). 여기 False면 어떤 설정도 매치 불가.
        if not signal_is_match(sig) or sig.confidence < MIN_CONF:
            continue

        sigkey = signal_signature(sig)
        decel  = sig.detail.get("decel_actual")
        entry  = ohlcv[i][4]
        exitp  = ohlcv[i + HOLD][4]
        ret    = (exitp - entry) / entry - 2 * FEE     # direction 항상 up

        for dr in DECEL_SETTINGS:
            s = state[dr]
            if i < s["next_allowed"] or sigkey in s["traded"]:
                continue
            # 감속 조건: None이면 통과, 아니면 decel <= dr
            if dr is not None and not (decel is not None and decel <= dr):
                continue
            s["trades"].append(dict(ret=ret, decel=decel))
            s["traded"].add(sigkey)
            s["next_allowed"] = i + HOLD

    return {dr: state[dr]["trades"] for dr in DECEL_SETTINGS}


def summarize(trades):
    if not trades:
        return dict(n=0, wr=None, avg=None, med=None)
    rets = [t["ret"] for t in trades]
    wins = sum(r > 0 for r in rets)
    return dict(n=len(rets),
                wr=round(wins / len(rets), 4),
                avg=round(st.mean(rets), 4),
                med=round(st.median(rets), 4))


def fmt(v, pct=False):
    if v is None:
        return "  -  "
    return f"{v*100:+.1f}%" if pct else f"{v:.4f}"


# ── 실행 ──────────────────────────────────────────────────────────────
print("계산 중...", flush=True)

results = {}   # (sym, tf, dr) -> summary
actuals = {}   # (sym, tf) -> [decel_actual ...]  (dr=None 기준)

for sym, tf, path in DATASETS:
    print(f"  {sym} {tf} 로드 후 탐지...", flush=True)
    ohlcv = load_csv(path)
    by_dr = run_all_decels(ohlcv)
    for dr in DECEL_SETTINGS:
        trades = by_dr[dr]
        results[(sym, tf, dr)] = summarize(trades)
        if dr is None:
            actuals[(sym, tf)] = [t["decel"] for t in trades if t["decel"] is not None]
    print(f"    완료 (None 신호 {len(by_dr[None])}개)", flush=True)

# ── 결과 표 (타임프레임별로 구분) ────────────────────────────────────────
print("\n" + "=" * 66)
print("triple_bottom_desc  x  decel_ratio sweep")
print(f"hold={HOLD}, min_conf={MIN_CONF}, fee={FEE}, breakout_mult={BREAKOUT_MULT}")
print("=" * 66)

SYMBOLS = ["BTC/USDT", "SOL/USDT"]
for tf in ["1h", "15m"]:
    print(f"\n############  타임프레임: {tf}  ############")
    for sym in SYMBOLS:
        print(f"\n>> {sym} ({tf})")
        print(f"  {'decel':>9}  {'신호수':>5}  {'승률':>7}  {'평균수익':>8}  {'중앙값':>8}")
        print("  " + "-" * 46)
        for dr in DECEL_SETTINGS:
            s = results[(sym, tf, dr)]
            label = f"{dr}" if dr is not None else "None(끔)"
            print(f"  {label:>9}  {s['n']:>5}  "
                  f"{fmt(s['wr']):>7}  {fmt(s['avg'], pct=True):>8}  "
                  f"{fmt(s['med'], pct=True):>8}")

# ── decel_actual 원시값 (decel=None 기준) ────────────────────────────────
print("\n" + "=" * 66)
print("decel_actual 원시값  (decel_ratio=None 상태, 신호 발생 순)")
print("  = 2차낙폭 / 1차낙폭.  값 < 1.0 → 감속,  > 1.0 → 가속")
print("=" * 66)

for tf in ["1h", "15m"]:
    for sym in SYMBOLS:
        vals = actuals.get((sym, tf), [])
        print(f"\n>> {sym} ({tf})  (n={len(vals)})")
        if not vals:
            print("  (신호 없음)")
            continue
        print("  " + "  ".join(f"{v:.3f}" for v in vals))
        print(f"  min={min(vals):.3f}  max={max(vals):.3f}  "
              f"mean={st.mean(vals):.3f}  median={st.median(vals):.3f}")
