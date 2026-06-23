"""
detector_fvg.py — Bullish Fair Value Gap.
3봉 갭업(high[i-2] < low[i]) + 거래량 동반(직전 20봉 평균의 1.3배 이상)이면
모멘텀 롱 신호. 신호 = 갭 완성봉(i) 종가.
"""
from detlib import SYMBOLS, load_ohlcv, outcome, make_evaluate

PATTERN = "fvg"
VOL_MULT = 1.3


def detect(rows):
    n = len(rows)
    v = [r["v"] for r in rows]
    sig = []
    for i in range(22, n):
        if rows[i - 2]["h"] < rows[i]["l"]:        # 3봉 갭업
            base = sum(v[i - 20:i]) / 20
            if base > 0 and v[i] >= VOL_MULT * base:
                sig.append(i)
    return sig


evaluate = make_evaluate(detect)

if __name__ == "__main__":
    import statistics as st
    r = evaluate(); rr = r["rets"]
    print(PATTERN, r["agg"], f"mean={st.mean(rr)*100:+.2f}%" if rr else "")
