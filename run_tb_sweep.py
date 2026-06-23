"""
triple_bottom vs triple_bottom_desc 스윕 (BTC/SOL 1h, hold=10 고정).
  min_conf: 0.0 / 0.6 / 0.7 / 0.8
  출력: (변형 × 종목 × conf)별 신호수·1000봉당·승률·평균·중앙값.
  conf=0.0 케이스는 per-trade 수익 원시값도 출력.

최적화: 봉마다 1회만 탐지하고 conf 4단계의 쿨다운/dedup 상태를 동시 유지.
  (min_conf은 confidence 필터일 뿐 탐지를 안 바꾸므로, run_backtest를 conf별로
   따로 도는 것과 결과가 동일하면서 4배 빠름.)
"""
import sys
import statistics as st
sys.path.insert(0, ".")
from backtest import DETECTORS, load_csv, signal_is_match, signal_signature

HOLD   = 10
FEE    = 0.001
WARMUP = 60
CONFS  = [0.0, 0.6, 0.7, 0.8]
VARIANTS = ["triple_bottom", "triple_bottom_desc"]
FILES = {"BTC/USDT": "data/btc_1h.csv", "SOL/USDT": "data/sol_1h.csv"}


def sweep(ohlcv, det):
    """봉마다 1회 탐지, conf 4단계 동시 백테스트. conf->list[ret] 반환."""
    state = {mc: dict(rets=[], traded=set(), next_allowed=WARMUP) for mc in CONFS}
    n = len(ohlcv)
    for i in range(WARMUP, n - HOLD):
        # 모든 conf가 쿨다운 중이면 스킵
        if all(i < s["next_allowed"] for s in state.values()):
            continue
        sig = det(ohlcv[:i + 1])
        if not signal_is_match(sig):
            continue
        conf = sig.confidence
        sigkey = signal_signature(sig)
        entry = ohlcv[i][4]; exitp = ohlcv[i + HOLD][4]
        raw = (exitp - entry) / entry
        ret = (raw if sig.direction == "up" else -raw) - 2 * FEE
        for mc in CONFS:
            s = state[mc]
            if conf < mc or i < s["next_allowed"] or sigkey in s["traded"]:
                continue
            s["rets"].append(ret)
            s["traded"].add(sigkey)
            s["next_allowed"] = i + HOLD
    return {mc: state[mc]["rets"] for mc in CONFS}


def stats(rets):
    if not rets:
        return dict(n=0, wr=None, avg=None, med=None)
    return dict(n=len(rets), wr=round(sum(r > 0 for r in rets) / len(rets), 4),
                avg=round(st.mean(rets), 4), med=round(st.median(rets), 4))


def fmt(v, pct=False):
    if v is None:
        return "  -  "
    return f"{v*100:+.2f}%" if pct else f"{v:.4f}"


data = {sym: load_csv(path) for sym, path in FILES.items()}
results, raw00 = {}, {}
for variant in VARIANTS:
    det = DETECTORS[variant]
    for sym, ohlcv in data.items():
        by_conf = sweep(ohlcv, det)
        ntot = len(ohlcv)
        for mc in CONFS:
            results[(variant, sym, mc)] = (stats(by_conf[mc]), ntot)
        raw00[(variant, sym)] = by_conf[0.0]

print("=" * 80)
print("triple_bottom vs triple_bottom_desc  (BTC/SOL 1h, hold=10, fee=0.001)")
print(f"기간: BTC {len(data['BTC/USDT'])}봉, SOL {len(data['SOL/USDT'])}봉 (2021-01-01~)")
print("=" * 80)
for variant in VARIANTS:
    print(f"\n  {variant:<22} {'종목':<9} {'conf':>4} {'신호':>5} {'/1000':>7} {'승률':>7} {'평균':>8} {'중앙':>8}")
    print("  " + "-" * 76)
    for sym in FILES:
        for mc in CONFS:
            s, ntot = results[(variant, sym, mc)]
            per1k = round(s["n"] / ntot * 1000, 2) if ntot else 0
            print(f"  {'':<22} {sym:<9} {mc:>4.1f} {s['n']:>5} {per1k:>7} "
                  f"{fmt(s['wr']):>7} {fmt(s['avg'], True):>8} {fmt(s['med'], True):>8}")

print("\n" + "=" * 80)
print("conf=0.0 per-trade 수익 원시값 (%)")
print("=" * 80)
for variant in VARIANTS:
    for sym in FILES:
        vals = raw00[(variant, sym)]
        print(f"\n>> {variant} | {sym}  (n={len(vals)})")
        print("  " + ("  ".join(f"{v*100:+.2f}" for v in vals) if vals else "(신호 없음)"))
