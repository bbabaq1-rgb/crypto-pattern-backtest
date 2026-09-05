"""detector_down_streak3.py — 3연속 하락 + 10일 신저가 롱 (1d 평균회귀).
종가가 3봉 연속 내리고, 그 종가가 직전 10봉 최저 종가보다 낮다.
2026-09-05 사전 등록 후보. 게이트 통과 전까지 실거래 미등재."""
from detlib import SYMBOLS, load_ohlcv, outcome, make_evaluate
PATTERN = "down_streak3"
STREAK, LOOKBACK = 3, 10


def detect(rows):
    sig = []
    cs = [r["c"] for r in rows]
    for i in range(LOOKBACK + STREAK, len(rows)):
        if all(cs[i - k] < cs[i - k - 1] for k in range(STREAK)) and cs[i] < min(cs[i - LOOKBACK:i]):
            sig.append(i)
    return sig


evaluate = make_evaluate(detect, "long")
if __name__ == "__main__":
    import statistics as st
    r = evaluate(); rr = r["rets"]; print(PATTERN, r["agg"], f"mean={st.mean(rr)*100:+.2f}%" if rr else "")
