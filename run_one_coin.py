"""
단일 종목 triple_bottom_desc x decel 백테스트 (병렬 실행용).
  사용: python run_one_coin.py <LABEL> <CSV> [OUTJSON]
  - 전체이력 정확 방식(봉마다 ohlcv[:i+1] 탐지). dedup은 절대 피벗인덱스.
  - 속도: 피벗 스캔을 최근 SCAN_CAP개로 제한(결과 불변, 상승추세 종목 가속).
  - decel는 matched에만 AND → decel=None 1회 탐지로 4단계 동시 계산.
"""
import sys, json
import statistics as st
sys.path.insert(0, ".")
from triple_bottom_volume import detect_triple_bottom_descending
from backtest import load_csv, signal_is_match, signal_signature

HOLD, MIN_CONF, FEE, WARMUP, BREAKOUT_MULT = 10, 0.0, 0.001, 60, 1.1
SCAN_CAP = 300
DECEL_SETTINGS = [None, 1.0, 0.7, 0.5]


def run(ohlcv):
    state = {dr: dict(rets=[], traded=set(), next_allowed=WARMUP)
             for dr in DECEL_SETTINGS}
    for i in range(WARMUP, len(ohlcv) - HOLD):
        if all(i < s["next_allowed"] for s in state.values()):
            continue
        sig = detect_triple_bottom_descending(
            ohlcv[:i + 1], decel_ratio=None,
            breakout_mult=BREAKOUT_MULT, max_lookback_pivots=SCAN_CAP)
        if not signal_is_match(sig) or sig.confidence < MIN_CONF:
            continue
        sigkey = signal_signature(sig)
        decel  = sig.detail.get("decel_actual")
        ret    = (ohlcv[i + HOLD][4] - ohlcv[i][4]) / ohlcv[i][4] - 2 * FEE
        for dr in DECEL_SETTINGS:
            s = state[dr]
            if i < s["next_allowed"] or sigkey in s["traded"]:
                continue
            if dr is not None and not (decel is not None and decel <= dr):
                continue
            s["rets"].append(ret)
            s["traded"].add(sigkey)
            s["next_allowed"] = i + HOLD
    return {dr: state[dr]["rets"] for dr in DECEL_SETTINGS}


def summ(rets):
    if not rets:
        return dict(n=0, wr=None, avg=None, med=None)
    return dict(n=len(rets), wr=round(sum(r > 0 for r in rets) / len(rets), 4),
                avg=round(st.mean(rets), 4), med=round(st.median(rets), 4))


label = sys.argv[1]
csv   = sys.argv[2]
out   = sys.argv[3] if len(sys.argv) > 3 else None

print(f"[{label}] 로드...", flush=True)
by_dr = run(load_csv(csv))
res = {("None" if dr is None else str(dr)): summ(by_dr[dr]) for dr in DECEL_SETTINGS}

print(f"[{label}] 결과:")
for dr in DECEL_SETTINGS:
    k = "None" if dr is None else str(dr)
    s = res[k]
    print(f"  decel={k:>5}  n={s['n']:>3}  wr={s['wr']}  avg={s['avg']}  med={s['med']}")

if out:
    with open(out, "w") as f:
        json.dump({"label": label, "res": res}, f)
    print(f"[{label}] -> {out}")
