"""
detector_macd_divergence.py — MACD Bullish Divergence.
연속 swing low 두 곳에서 가격은 더 낮은 저점, MACD(12,26)는 더 높은 저점,
그리고 첫 저점 MACD<0(약세 구간)일 때 롱 신호. 신호 = 둘째 저점 확정(+2봉).
"""
from detlib import SYMBOLS, load_ohlcv, outcome, make_evaluate

PATTERN = "macd_divergence"
MAX_GAP = 40


def _ema(x, p):
    k = 2 / (p + 1); out = [x[0]]
    for i in range(1, len(x)):
        out.append(x[i] * k + out[-1] * (1 - k))
    return out


def detect(rows):
    n = len(rows)
    cl = [r["c"] for r in rows]; lo = [r["l"] for r in rows]
    e12, e26 = _ema(cl, 12), _ema(cl, 26)
    macd = [e12[i] - e26[i] for i in range(n)]
    piv = [i for i in range(2, n - 2) if lo[i] == min(lo[i - 2:i + 3])]
    sig = []
    for a in range(len(piv) - 1):
        L1 = piv[a]
        if macd[L1] >= 0:
            continue
        for b in range(a + 1, len(piv)):
            L2 = piv[b]
            if L2 - L1 > MAX_GAP:
                break
            if lo[L2] < lo[L1] and macd[L2] > macd[L1]:
                e = L2 + 2
                if e < n:
                    sig.append(e)
                break
    return sorted(set(sig))


evaluate = make_evaluate(detect)

if __name__ == "__main__":
    import statistics as st
    r = evaluate(); rr = r["rets"]
    print(PATTERN, r["agg"], f"mean={st.mean(rr)*100:+.2f}%" if rr else "")
