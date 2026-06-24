"""
detector_order_block_short.py — Bearish Order Block (order_block의 direction='short').
직전 봉 양봉(마지막 매수 캔들) 다음 당일 음봉이 직전 20봉 저점을 하향 돌파하면
(구조 하향 전환) 숏. 라벨 반전(detlib.outcome short).
"""
from detlib import SYMBOLS, load_ohlcv, outcome as _oc, make_evaluate

PATTERN = "order_block_short"
LB = 20


def outcome(rows, si):
    return _oc(rows, si, "short")


def detect(rows):
    n = len(rows)
    op = [r["o"] for r in rows]; cl = [r["c"] for r in rows]; lo = [r["l"] for r in rows]
    sig = []
    for i in range(LB, n):
        if cl[i - 1] > op[i - 1] and cl[i] < op[i] and cl[i] < min(lo[i - LB:i]):
            sig.append(i)
    return sig


evaluate = make_evaluate(detect, "short")

if __name__ == "__main__":
    import statistics as st
    r = evaluate(); rr = r["rets"]
    print(PATTERN, r["agg"], f"mean={st.mean(rr)*100:+.2f}%" if rr else "")
