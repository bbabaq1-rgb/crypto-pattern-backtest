"""
detector_inverse_hs.py — Inverse Head & Shoulders.
연속 swing low 3개(좌어깨 L, 머리 H, 우어깨 R): 머리가 최저, 양어깨가 비슷(EQ_TOL)
하고 머리보다 높음. 어깨 사이 고점 넥라인을 R 이후 상향 돌파하면 롱 신호.
"""
from detlib import SYMBOLS, load_ohlcv, outcome, make_evaluate

PATTERN = "inverse_hs"
EQ_TOL = 0.05
MAX_SPAN = 90


def detect(rows):
    n = len(rows)
    lo = [r["l"] for r in rows]; hi = [r["h"] for r in rows]; cl = [r["c"] for r in rows]
    piv = [i for i in range(2, n - 2) if lo[i] == min(lo[i - 2:i + 3])]
    sig = []; used = set()
    for a in range(len(piv) - 2):
        L, H, R = piv[a], piv[a + 1], piv[a + 2]
        if R - L > MAX_SPAN:
            continue
        if not (lo[H] < lo[L] and lo[H] < lo[R]):           # 머리 최저
            continue
        if abs(lo[L] - lo[R]) / lo[L] > EQ_TOL:             # 어깨 유사
            continue
        neck = max(hi[L + 1:R])                              # 넥라인
        if neck <= 0:
            continue
        for j in range(R + 1, min(R + MAX_SPAN, n)):
            if cl[j] > neck:
                if j not in used:
                    used.add(j); sig.append(j)
                break
    return sorted(set(sig))


evaluate = make_evaluate(detect)

if __name__ == "__main__":
    import statistics as st
    r = evaluate(); rr = r["rets"]
    print(PATTERN, r["agg"], f"mean={st.mean(rr)*100:+.2f}%" if rr else "")
