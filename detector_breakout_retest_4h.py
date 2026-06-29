"""
detector_breakout_retest_4h.py — 브레이크아웃 + 리테스트 (4h, LONG).

정의:
  (1) i-1봉: 최근 20봉 고점(pivot_high) 돌파 — close > pivot_high
  (2) i봉:   저가가 pivot_high ± 2% 안에 닿아 리테스트,
             AND 종가가 pivot_high 위에서 마감 (재상승 확인)
신호 = i봉, 종가 기준 라벨링(롱 방향).
"""
import detlib

LOOKBACK  = 20
TOLERANCE = 0.02   # 리테스트 허용 범위 ±2%


def detect(rows):
    signals = []
    n = len(rows)
    for i in range(LOOKBACK + 1, n):
        # pivot_high: i-1 직전 20봉의 최고가
        pivot = max(r["h"] for r in rows[i - LOOKBACK - 1: i - 1])
        prev  = rows[i - 1]
        curr  = rows[i]

        # (1) 전봉이 돌파봉
        if prev["c"] <= pivot:
            continue

        # (2) 현봉 리테스트 + 재상승
        low_touches = curr["l"] <= pivot * (1 + TOLERANCE)
        close_above = curr["c"] > pivot
        if low_touches and close_above:
            signals.append(i)
    return signals


def load_ohlcv(sym, tf="4h"):
    return detlib.load_ohlcv(sym, tf)


evaluate = detlib.make_evaluate(detect, direction="long")
