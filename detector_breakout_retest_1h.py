"""
detector_breakout_retest_1h.py — 브레이크아웃+리테스트 롱 신호 (1h).

정의:
  i-1봉: close > 직전 LOOKBACK봉 최고가(pivot_high)  <- 브레이크아웃
  i봉:   low <= pivot_high * (1 + TOLERANCE)           <- 리테스트(풀백)
         AND close > pivot_high                         <- 종가는 pivot 위 유지
"""
import detlib

LOOKBACK  = 20
TOLERANCE = 0.02


def detect(rows):
    signals = []
    n = len(rows)
    for i in range(LOOKBACK + 1, n):
        pivot_high = max(rows[j]["h"] for j in range(i - LOOKBACK - 1, i - 1))
        prev = rows[i - 1]
        curr = rows[i]
        if prev["c"] <= pivot_high:
            continue
        if curr["l"] <= pivot_high * (1 + TOLERANCE) and curr["c"] > pivot_high:
            signals.append(i)
    return signals


def load_ohlcv(sym, tf="1h"):
    return detlib.load_ohlcv(sym, tf)


evaluate = detlib.make_evaluate(detect, direction="long")
