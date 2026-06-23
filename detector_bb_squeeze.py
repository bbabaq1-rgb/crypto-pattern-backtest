"""
detector_bb_squeeze.py — Bollinger Band Squeeze 상방돌파.
20봉 볼린저밴드 폭(2sigma/MA)이 최근 20봉 중 최저(스퀴즈)이면서
당일 종가가 상단밴드(MA+2sigma)를 돌파하면 롱 신호.
"""
from detlib import SYMBOLS, load_ohlcv, outcome, make_evaluate

PATTERN = "bb_squeeze"
P = 20


def detect(rows):
    n = len(rows)
    cl = [r["c"] for r in rows]
    bw = [None] * n
    upper = [None] * n
    for i in range(P - 1, n):
        w = cl[i - P + 1:i + 1]
        m = sum(w) / P
        sd = (sum((x - m) ** 2 for x in w) / P) ** 0.5
        bw[i] = (2 * sd / m) if m else 0.0
        upper[i] = m + 2 * sd
    sig = []
    for i in range(P + 20, n):
        recent = [bw[j] for j in range(i - 20, i) if bw[j] is not None]
        if recent and bw[i] is not None and bw[i] <= min(recent) and cl[i] > upper[i]:
            sig.append(i)
    return sig


evaluate = make_evaluate(detect)

if __name__ == "__main__":
    import statistics as st
    r = evaluate(); rr = r["rets"]
    print(PATTERN, r["agg"], f"mean={st.mean(rr)*100:+.2f}%" if rr else "")
