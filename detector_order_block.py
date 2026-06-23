"""
detector_order_block.py — Bullish Order Block (구조 돌파형).
직전 봉 음봉(마지막 매도 캔들) 다음 당일 양봉이 직전 20봉 고점을 돌파하면
(구조 상향 전환) 롱 신호. 신호 = 돌파 양봉(i).
"""
from detlib import SYMBOLS, load_ohlcv, outcome, make_evaluate

PATTERN = "order_block"
LB = 20


def detect(rows):
    n = len(rows)
    op = [r["o"] for r in rows]; cl = [r["c"] for r in rows]; hi = [r["h"] for r in rows]
    sig = []
    for i in range(LB, n):
        if cl[i - 1] < op[i - 1] and cl[i] > op[i] and cl[i] > max(hi[i - LB:i]):
            sig.append(i)
    return sig


evaluate = make_evaluate(detect)

if __name__ == "__main__":
    import statistics as st
    r = evaluate(); rr = r["rets"]
    print(PATTERN, r["agg"], f"mean={st.mean(rr)*100:+.2f}%" if rr else "")
