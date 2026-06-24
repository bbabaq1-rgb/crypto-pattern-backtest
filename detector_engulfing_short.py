"""
detector_engulfing_short.py — Bearish Engulfing (engulfing의 direction='short').
상승 끝(최근 고점 부근)에서 큰 음봉이 직전 양봉 몸통을 완전 포함 + 거래량 동반 -> 숏.
라벨 반전: -10% 선도달=real, +10% 선도달=fake (detlib.outcome short).
"""
from detlib import SYMBOLS, load_ohlcv, outcome as _oc, make_evaluate

PATTERN = "engulfing_short"
LOOKBACK = 10
HIGH_TOL = 0.02
VOL_LOOKBACK = 20
VOL_MULT = 1.5


def outcome(rows, si):
    return _oc(rows, si, "short")


def detect(rows):
    n = len(rows)
    o = [r["o"] for r in rows]; c = [r["c"] for r in rows]
    hi = [r["h"] for r in rows]; v = [r["v"] for r in rows]
    sig = []
    start = max(LOOKBACK, VOL_LOOKBACK) + 1
    for i in range(start, n):
        # 베어리시 엔걸핑: 직전 양봉, 당일 음봉이 직전 몸통 포함
        if not (c[i] < o[i] and c[i - 1] > o[i - 1]
                and o[i] >= c[i - 1] and c[i] <= o[i - 1]):
            continue
        win_high = max(hi[i - LOOKBACK:i])
        if max(hi[i], hi[i - 1]) < win_high * (1 - HIGH_TOL):   # 최근 고점 부근
            continue
        base = sum(v[i - VOL_LOOKBACK:i]) / VOL_LOOKBACK
        if base <= 0 or v[i] < VOL_MULT * base:
            continue
        sig.append(i)
    return sig


evaluate = make_evaluate(detect, "short")

if __name__ == "__main__":
    import statistics as st
    r = evaluate(); rr = r["rets"]
    print(PATTERN, r["agg"], f"mean={st.mean(rr)*100:+.2f}%" if rr else "")
