"""
triple_bottom_desc x decel_ratio sweep  (6종목, 15m)
  - SOL, ETH, BNB, XRP, ADA, AVAX  /  15m
  - min_conf=0.0, hold=10, breakout_mult=1.1 고정
  - decel_ratio: None / 1.0 / 0.7 / 0.5
  - 종목별 None->0.5 방향 중앙값(및 평균) 단조 추세 판정
"""
import sys
import statistics as st
sys.path.insert(0, ".")

from triple_bottom_volume import detect_triple_bottom_descending
from backtest import load_csv, signal_is_match, signal_signature

HOLD          = 10
MIN_CONF      = 0.0
FEE           = 0.001
WARMUP        = 60
BREAKOUT_MULT = 1.1

# 표시 순서대로 (종목, csv)
DATASETS = [
    ("SOL/USDT",  "data/sol_15m.csv"),
    ("ETH/USDT",  "data/eth_15m.csv"),
    ("BNB/USDT",  "data/bnb_15m.csv"),
    ("XRP/USDT",  "data/xrp_15m.csv"),
    ("ADA/USDT",  "data/ada_15m.csv"),
    ("AVAX/USDT", "data/avax_15m.csv"),
]
DECEL_SETTINGS = [None, 1.0, 0.7, 0.5]   # None -> 0.5 (조이는 방향)


def run_all_decels(ohlcv):
    """
    decel는 matched에만 AND로 들어가므로 decel=None 1회 탐지로
    각 임계값 matched를 동시 계산(독립 실행과 결과 동일). 설정별 쿨다운/dedup 분리.
    """
    state = {dr: dict(trades=[], traded=set(), next_allowed=WARMUP)
             for dr in DECEL_SETTINGS}

    for i in range(WARMUP, len(ohlcv) - HOLD):
        if all(i < s["next_allowed"] for s in state.values()):
            continue
        sig = detect_triple_bottom_descending(
            ohlcv[:i + 1], decel_ratio=None, breakout_mult=BREAKOUT_MULT)
        if not signal_is_match(sig) or sig.confidence < MIN_CONF:
            continue

        sigkey = signal_signature(sig)
        decel  = sig.detail.get("decel_actual")
        entry  = ohlcv[i][4]
        exitp  = ohlcv[i + HOLD][4]
        ret    = (exitp - entry) / entry - 2 * FEE

        for dr in DECEL_SETTINGS:
            s = state[dr]
            if i < s["next_allowed"] or sigkey in s["traded"]:
                continue
            if dr is not None and not (decel is not None and decel <= dr):
                continue
            s["trades"].append(ret)
            s["traded"].add(sigkey)
            s["next_allowed"] = i + HOLD

    return {dr: state[dr]["trades"] for dr in DECEL_SETTINGS}


def summarize(rets):
    if not rets:
        return dict(n=0, wr=None, avg=None, med=None)
    wins = sum(r > 0 for r in rets)
    return dict(n=len(rets),
                wr=round(wins / len(rets), 4),
                avg=round(st.mean(rets), 4),
                med=round(st.median(rets), 4))


def monotonic_trend(seq):
    """None->0.5 순서 값 리스트(일부 None 가능)에서 단조 추세 판정."""
    vals = [v for v in seq if v is not None]
    if len(vals) < 2:
        return "판정불가(표본부족)"
    incr = all(vals[i] <= vals[i + 1] for i in range(len(vals) - 1))
    decr = all(vals[i] >= vals[i + 1] for i in range(len(vals) - 1))
    strict_incr = all(vals[i] < vals[i + 1] for i in range(len(vals) - 1))
    if strict_incr:
        return "↗ 단조증가(우상향)"
    if incr:
        return "↗ 비감소(약우상향)"
    if decr:
        return "↘ 비증가(우하향)"
    return "↔ 비단조(혼조)"


def fmt(v, pct=False):
    if v is None:
        return "  -  "
    return f"{v*100:+.1f}%" if pct else f"{v:.4f}"


# ── 실행 ──────────────────────────────────────────────────────────────
print("계산 중...", flush=True)
results = {}   # (sym, dr) -> summary
for sym, path in DATASETS:
    print(f"  {sym} 로드 후 탐지...", flush=True)
    ohlcv = load_csv(path)
    by_dr = run_all_decels(ohlcv)
    for dr in DECEL_SETTINGS:
        results[(sym, dr)] = summarize(by_dr[dr])
    print(f"    완료 (None 신호 {results[(sym, None)]['n']}개)", flush=True)

# ── 결과 표 ───────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("triple_bottom_desc  x  decel_ratio sweep  (15m, 6종목)")
print(f"hold={HOLD}, min_conf={MIN_CONF}, fee={FEE}, breakout_mult={BREAKOUT_MULT}")
print("=" * 60)

for sym, _ in DATASETS:
    print(f"\n>> {sym}")
    print(f"  {'decel':>9}  {'신호수':>5}  {'승률':>7}  {'평균수익':>8}  {'중앙값':>8}")
    print("  " + "-" * 46)
    for dr in DECEL_SETTINGS:
        s = results[(sym, dr)]
        label = f"{dr}" if dr is not None else "None(끔)"
        print(f"  {label:>9}  {s['n']:>5}  "
              f"{fmt(s['wr']):>7}  {fmt(s['avg'], pct=True):>8}  "
              f"{fmt(s['med'], pct=True):>8}")

# ── 종목별 단조 추세 판정 (None -> 0.5) ─────────────────────────────────
print("\n" + "=" * 60)
print("decel 조일수록(None->1.0->0.7->0.5) 평균·중앙값 단조 추세")
print("=" * 60)
print(f"  {'종목':>10}  {'중앙값 추세':>16}  {'평균 추세':>16}")
print("  " + "-" * 48)
for sym, _ in DATASETS:
    med_seq = [results[(sym, dr)]["med"] for dr in DECEL_SETTINGS]
    avg_seq = [results[(sym, dr)]["avg"] for dr in DECEL_SETTINGS]
    print(f"  {sym:>10}  {monotonic_trend(med_seq):>16}  {monotonic_trend(avg_seq):>16}")

print("\n  중앙값 수열(None->1.0->0.7->0.5):")
for sym, _ in DATASETS:
    seq = [results[(sym, dr)]["med"] for dr in DECEL_SETTINGS]
    txt = "  ".join(fmt(v, pct=True) for v in seq)
    print(f"    {sym:>10}: {txt}")
