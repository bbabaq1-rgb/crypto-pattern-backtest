"""detector_morning_star.py — Morning Star (롱).
큰 음봉 -> 소형봉(몸통<=전봉30%) -> 큰 양봉이 첫 봉 몸통 절반 이상 회복."""
from detlib import SYMBOLS, load_ohlcv, outcome, make_evaluate
PATTERN = "morning_star"


def detect(rows):
    sig = []
    for i in range(2, len(rows)):
        o1, c1 = rows[i - 2]["o"], rows[i - 2]["c"]
        o2, c2 = rows[i - 1]["o"], rows[i - 1]["c"]
        o3, c3 = rows[i]["o"], rows[i]["c"]
        b1 = o1 - c1                                 # 첫 봉 음봉 몸통(>0)
        if b1 <= 0:
            continue
        if abs(c2 - o2) > 0.3 * b1:                  # 둘째 소형봉
            continue
        if c3 > o3 and c3 >= (o1 + c1) / 2:          # 셋째 양봉, 첫봉 절반 회복
            sig.append(i)
    return sig


evaluate = make_evaluate(detect, "long")
if __name__ == "__main__":
    import statistics as st
    r = evaluate(); rr = r["rets"]; print(PATTERN, r["agg"], f"mean={st.mean(rr)*100:+.2f}%" if rr else "")
