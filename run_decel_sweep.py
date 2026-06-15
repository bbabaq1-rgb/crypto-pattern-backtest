"""
triple_bottom_desc × decel_ratio 스윕
  - 종목: BTC/USDT 1h, SOL/USDT 1h
  - min_conf=0.0, hold=10 고정
  - decel_ratio: None / 1.0 / 0.7 / 0.5
  - None 조건에서 decel_ratio_actual 원시값 출력
"""
import sys
import statistics as st
sys.path.insert(0, ".")

from triple_bottom_volume import detect_triple_bottom_descending
from backtest import load_csv, signal_is_match, signal_signature

HOLD     = 10
MIN_CONF = 0.0
FEE      = 0.001
WARMUP   = 60
FILES = {
    "BTC/USDT": "data/btc_1h.csv",
    "SOL/USDT": "data/sol_1h.csv",
}
DECEL_SETTINGS = [None, 1.0, 0.7, 0.5]


def run_sweep(ohlcv, dr):
    """봉마다 탐지 → matched 신호만 수집. detail도 저장."""
    trades = []
    traded_sig = set()
    next_allowed = WARMUP
    n = len(ohlcv)

    for i in range(WARMUP, n - HOLD):
        if i < next_allowed:
            continue
        sig = detect_triple_bottom_descending(ohlcv[:i + 1], decel_ratio=dr)
        if not signal_is_match(sig) or sig.confidence < MIN_CONF:
            continue
        sigkey = signal_signature(sig)
        if sigkey in traded_sig:
            continue

        entry = ohlcv[i][4]
        exitp = ohlcv[i + HOLD][4]
        raw   = (exitp - entry) / entry
        ret   = raw - 2 * FEE          # direction 항상 up

        trades.append(dict(ret=ret,
                           decel_actual=sig.detail.get("decel_ratio_actual")))
        traded_sig.add(sigkey)
        next_allowed = i + HOLD

    return trades


def summarize(trades):
    if not trades:
        return dict(n=0, wr=None, avg=None, med=None)
    rets = [t["ret"] for t in trades]
    wins = sum(r > 0 for r in rets)
    return dict(
        n   = len(rets),
        wr  = round(wins / len(rets), 4),
        avg = round(st.mean(rets), 4),
        med = round(st.median(rets), 4),
    )


def fmt(v, pct=False):
    if v is None:
        return "  —  "
    if pct:
        return f"{v*100:+.1f}%"
    return f"{v:.4f}"


# ── 실행 ─────────────────────────────────────────────────────────────────
print("계산 중...", flush=True)

results  = {}   # (sym, dr) -> summary
actuals  = {}   # sym -> [decel_ratio_actual, ...]

for sym, path in FILES.items():
    print(f"  {sym} 로드...", flush=True)
    ohlcv = load_csv(path)
    actuals[sym] = []

    for dr in DECEL_SETTINGS:
        print(f"    decel={dr} ...", flush=True)
        trades = run_sweep(ohlcv, dr)
        results[(sym, dr)] = summarize(trades)
        if dr is None:
            actuals[sym] = [t["decel_actual"] for t in trades
                            if t["decel_actual"] is not None]

# ── 결과 표 ──────────────────────────────────────────────────────────────
print("\n" + "=" * 58)
print("triple_bottom_desc  ×  decel_ratio 스윕")
print(f"hold={HOLD}, min_conf={MIN_CONF}, fee={FEE}")
print("=" * 58)

for sym in FILES:
    print(f"\n▶ {sym}")
    print(f"  {'decel':>9}  {'신호수':>5}  {'승률':>7}  {'평균수익':>8}  {'중앙값':>8}")
    print("  " + "-" * 44)
    for dr in DECEL_SETTINGS:
        s = results[(sym, dr)]
        label = f"{dr}" if dr is not None else "None(끔)"
        print(f"  {label:>9}  {s['n']:>5}  "
              f"{fmt(s['wr']):>7}  {fmt(s['avg'], pct=True):>8}  "
              f"{fmt(s['med'], pct=True):>8}")

# ── decel_ratio_actual 원시값 ────────────────────────────────────────────
print("\n" + "=" * 58)
print("decel_ratio_actual 원시값  (None 조건, 신호 발생 순)")
print("  값 < 1.0 → 2차낙폭 < 1차낙폭 (감속)")
print("  값 > 1.0 → 2차낙폭 > 1차낙폭 (가속)")
print("=" * 58)

for sym in FILES:
    vals = actuals[sym]
    print(f"\n▶ {sym}  (n={len(vals)})")
    if not vals:
        print("  (신호 없음)")
        continue
    print("  " + "  ".join(f"{v:.3f}" for v in vals))
    print(f"\n  min={min(vals):.3f}  max={max(vals):.3f}  "
          f"mean={st.mean(vals):.3f}  median={st.median(vals):.3f}")

    # 0.2 단위 히스토그램
    buckets = {}
    for v in vals:
        b = round(int(v / 0.2) * 0.2, 1)
        buckets[b] = buckets.get(b, 0) + 1
    print("  히스토그램 (버킷 0.2):")
    for b in sorted(buckets):
        bar = "#" * buckets[b]
        print(f"    {b:.1f}~{b+0.2:.1f}: {bar} ({buckets[b]})")
