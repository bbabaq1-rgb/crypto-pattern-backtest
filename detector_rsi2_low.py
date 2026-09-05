"""detector_rsi2_low.py — RSI(2) 과매도 롱 (1d 평균회귀, Connors 계열).
Wilder RSI 2기간 < 10. 200MA 추세 필터는 넣지 않는다 — 레짐 셀이 그 역할을 한다.
2026-09-05 사전 등록 후보. 게이트 통과 전까지 실거래 미등재."""
from detlib import SYMBOLS, load_ohlcv, outcome, make_evaluate
PATTERN = "rsi2_low"
PERIOD, THR = 2, 10.0


def rsi_series(closes, period=PERIOD):
    out = [None] * len(closes)
    if len(closes) <= period:
        return out
    gains = losses = 0.0
    for i in range(1, period + 1):
        d = closes[i] - closes[i - 1]
        gains += max(d, 0.0); losses += max(-d, 0.0)
    ag, al = gains / period, losses / period
    out[period] = 100.0 if al == 0 else 100.0 - 100.0 / (1 + ag / al)
    for i in range(period + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        ag = (ag * (period - 1) + max(d, 0.0)) / period
        al = (al * (period - 1) + max(-d, 0.0)) / period
        out[i] = 100.0 if al == 0 else 100.0 - 100.0 / (1 + ag / al)
    return out


def detect(rows):
    rsi = rsi_series([r["c"] for r in rows])
    return [i for i, v in enumerate(rsi) if v is not None and v < THR]


evaluate = make_evaluate(detect, "long")
if __name__ == "__main__":
    import statistics as st
    r = evaluate(); rr = r["rets"]; print(PATTERN, r["agg"], f"mean={st.mean(rr)*100:+.2f}%" if rr else "")
