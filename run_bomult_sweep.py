"""
triple_bottom_desc x breakout_mult sweep
  - BTC/USDT 1h, SOL/USDT 1h
  - min_conf=0.0, hold=10 고정
  - breakout_mult: 1.5 / 1.4 / 1.3 / 1.2 / 1.1
  - 직전 단계 대비 신호 증가수 포함
  - breakout_mult=1.1 케이스 per-trade 수익 원시값 출력
"""
import sys
import statistics as st
sys.path.insert(0, ".")

from triple_bottom_volume import detect_triple_bottom_descending
from backtest import load_csv, signal_is_match, signal_signature

HOLD      = 10
MIN_CONF  = 0.0
FEE       = 0.001
WARMUP    = 60
FILES = {
    "BTC/USDT": "data/btc_1h.csv",
    "SOL/USDT": "data/sol_1h.csv",
}
MULTS = [1.5, 1.4, 1.3, 1.2, 1.1]


def run_sweep(ohlcv, bm):
    trades = []
    traded_sig = set()
    next_allowed = WARMUP

    for i in range(WARMUP, len(ohlcv) - HOLD):
        if i < next_allowed:
            continue
        sig = detect_triple_bottom_descending(ohlcv[:i + 1], breakout_mult=bm)
        if not signal_is_match(sig) or sig.confidence < MIN_CONF:
            continue
        sigkey = signal_signature(sig)
        if sigkey in traded_sig:
            continue

        entry = ohlcv[i][4]
        exitp = ohlcv[i + HOLD][4]
        ret   = (exitp - entry) / entry - 2 * FEE

        trades.append(ret)
        traded_sig.add(sigkey)
        next_allowed = i + HOLD

    return trades


def summarize(rets):
    if not rets:
        return dict(n=0, wr=None, avg=None, med=None)
    wins = sum(r > 0 for r in rets)
    return dict(
        n   = len(rets),
        wr  = round(wins / len(rets), 4),
        avg = round(st.mean(rets), 4),
        med = round(st.median(rets), 4),
    )


def fmt(v, pct=False):
    if v is None:
        return "  -  "
    if pct:
        return f"{v*100:+.1f}%"
    return f"{v:.4f}"


# ── 실행 ──────────────────────────────────────────────────────────────
print("계산 중...", flush=True)

results = {}   # (sym, bm) -> list[ret]

for sym, path in FILES.items():
    print(f"  {sym} 로드...", flush=True)
    ohlcv = load_csv(path)
    for bm in MULTS:
        print(f"    breakout_mult={bm} ...", flush=True)
        results[(sym, bm)] = run_sweep(ohlcv, bm)

# ── 결과 표 ───────────────────────────────────────────────────────────
print("\n" + "=" * 64)
print("triple_bottom_desc  x  breakout_mult sweep")
print(f"hold={HOLD}, min_conf={MIN_CONF}, fee={FEE}")
print("=" * 64)

for sym in FILES:
    print(f"\n>> {sym}")
    print(f"  {'mult':>5}  {'신호수':>5}  {'전단계+':>6}  {'승률':>7}  {'평균수익':>8}  {'중앙값':>8}")
    print("  " + "-" * 50)
    prev_n = None
    for bm in MULTS:
        rets = results[(sym, bm)]
        s = summarize(rets)
        delta = f"+{s['n'] - prev_n}" if prev_n is not None else "  -"
        prev_n = s['n']
        print(f"  {bm:>5}  {s['n']:>5}  {delta:>6}  "
              f"{fmt(s['wr']):>7}  {fmt(s['avg'], pct=True):>8}  "
              f"{fmt(s['med'], pct=True):>8}")

# ── breakout_mult=1.1 per-trade 원시값 ────────────────────────────────
print("\n" + "=" * 64)
print("per-trade 수익 원시값  (breakout_mult=1.1)")
print("=" * 64)

for sym in FILES:
    rets = results[(sym, 1.1)]
    print(f"\n>> {sym}  (n={len(rets)})")
    if not rets:
        print("  (신호 없음)")
        continue
    for i, r in enumerate(rets, 1):
        sign = "+" if r >= 0 else ""
        print(f"  [{i:>2}]  {sign}{r*100:.2f}%")
    wins  = sum(r > 0 for r in rets)
    print(f"\n  승: {wins}  패: {len(rets)-wins}  "
          f"최대: {max(rets)*100:+.2f}%  최소: {min(rets)*100:+.2f}%  "
          f"평균: {st.mean(rets)*100:+.2f}%")
