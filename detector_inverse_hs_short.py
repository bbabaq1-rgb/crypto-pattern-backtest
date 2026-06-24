"""
detector_inverse_hs_short.py — Head & Shoulders Top (inverse_hs의 direction='short').
연속 swing high 3개(좌어깨/머리/우어깨): 머리 최고, 양어깨 유사하며 머리보다 낮음.
어깨 사이 저점 넥라인을 우어깨 이후 하향 이탈하면 숏.
라벨 반전(detlib.outcome short).
"""
from detlib import SYMBOLS, load_ohlcv, outcome as _oc, make_evaluate

PATTERN = "inverse_hs_short"
EQ_TOL = 0.05
MAX_SPAN = 90


def outcome(rows, si):
    return _oc(rows, si, "short")


def detect(rows):
    n = len(rows)
    lo = [r["l"] for r in rows]; hi = [r["h"] for r in rows]; cl = [r["c"] for r in rows]
    piv = [i for i in range(2, n - 2) if hi[i] == max(hi[i - 2:i + 3])]   # swing highs
    sig = []; used = set()
    for a in range(len(piv) - 2):
        L, H, R = piv[a], piv[a + 1], piv[a + 2]
        if R - L > MAX_SPAN:
            continue
        if not (hi[H] > hi[L] and hi[H] > hi[R]):           # 머리 최고
            continue
        if abs(hi[L] - hi[R]) / hi[L] > EQ_TOL:             # 어깨 유사
            continue
        neck = min(lo[L + 1:R])                              # 넥라인(저점)
        if neck <= 0:
            continue
        for j in range(R + 1, min(R + MAX_SPAN, n)):
            if cl[j] < neck:                                # 하향 이탈
                if j not in used:
                    used.add(j); sig.append(j)
                break
    return sorted(set(sig))


evaluate = make_evaluate(detect, "short")

if __name__ == "__main__":
    import statistics as st
    r = evaluate(); rr = r["rets"]
    print(PATTERN, r["agg"], f"mean={st.mean(rr)*100:+.2f}%" if rr else "")
