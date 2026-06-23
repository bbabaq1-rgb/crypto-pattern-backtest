"""
detector_bos_choch.py — Bullish Break of Structure.
가장 최근 확정 swing high를 당일 종가가 신규 상향 돌파(직전봉은 미돌파)하면
구조 상향 전환 롱 신호.
"""
from detlib import SYMBOLS, load_ohlcv, outcome, make_evaluate

PATTERN = "bos_choch"


def detect(rows):
    n = len(rows)
    hi = [r["h"] for r in rows]; cl = [r["c"] for r in rows]
    piv = [i for i in range(2, n - 2) if hi[i] == max(hi[i - 2:i + 3])]
    sig = []; pi = 0; last_sh = None
    for i in range(n):
        while pi < len(piv) and piv[pi] <= i - 3:   # 확정된 swing high만
            last_sh = piv[pi]; pi += 1
        if (i >= 20 and last_sh is not None
                and cl[i] > hi[last_sh] and cl[i - 1] <= hi[last_sh]):
            sig.append(i)
    return sig


evaluate = make_evaluate(detect)

if __name__ == "__main__":
    import statistics as st
    r = evaluate(); rr = r["rets"]
    print(PATTERN, r["agg"], f"mean={st.mean(rr)*100:+.2f}%" if rr else "")
