"""
detector_spring_wyckoff.py — Wyckoff Spring.
직전 LB봉 박스권 지지선(최저) 아래로 1% 침투(스프링)한 뒤 4봉 내 종가가
지지선 위로 회복하면 롱 신호. 신호 = 회복봉.
"""
from detlib import SYMBOLS, load_ohlcv, outcome, make_evaluate

PATTERN = "spring_wyckoff"
LB = 30
UNDERCUT = 0.01
RECLAIM_BARS = 4


def detect(rows):
    n = len(rows)
    lo = [r["l"] for r in rows]; cl = [r["c"] for r in rows]
    sig = []; i = LB + 1
    while i < n - 1:
        support = min(lo[i - LB:i])
        if lo[i] < support * (1 - UNDERCUT):
            rec = None
            for j in range(i, min(i + RECLAIM_BARS, n)):
                if cl[j] > support:
                    rec = j; break
            if rec is not None:
                sig.append(rec); i = rec + 1; continue
        i += 1
    return sig


evaluate = make_evaluate(detect)

if __name__ == "__main__":
    import statistics as st
    r = evaluate(); rr = r["rets"]
    print(PATTERN, r["agg"], f"mean={st.mean(rr)*100:+.2f}%" if rr else "")
