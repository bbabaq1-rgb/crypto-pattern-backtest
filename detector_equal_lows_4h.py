"""
detector_equal_lows_4h.py — Equal Lows SMC (4h, LONG).

정의:
  최근 LOOKBACK봉 내 피봇 저점(양쪽보다 낮은 봉)이 최소 2개,
  그 중 최저 피봇과 0.3% 이내인 피봇이 2개 이상,
  AND 현재봉 저가가 그 레벨 ± 0.3% 이내 (유동성 존 재시험).
  → 롱 신호 (유동성 스윕 후 반전 예상).
"""
import detlib

LOOKBACK  = 30
TOLERANCE = 0.003


def _pivot_lows(rows, start, end):
    pivots = []
    for j in range(start + 1, end - 1):
        if rows[j]["l"] <= rows[j-1]["l"] and rows[j]["l"] <= rows[j+1]["l"]:
            pivots.append(j)
    return pivots


def detect(rows):
    signals = []
    n = len(rows)
    for i in range(LOOKBACK, n):
        start = i - LOOKBACK
        pivots = _pivot_lows(rows, start, i)
        if len(pivots) < 2:
            continue
        lows = [rows[j]["l"] for j in pivots]
        ref  = min(lows)
        near = [l for l in lows if abs(l - ref) / (ref or 1e-9) <= TOLERANCE]
        if len(near) < 2:
            continue
        curr_l = rows[i]["l"]
        if abs(curr_l - ref) / (ref or 1e-9) <= TOLERANCE:
            signals.append(i)
    return signals


def load_ohlcv(sym, tf="4h"):
    return detlib.load_ohlcv(sym, tf)


evaluate = detlib.make_evaluate(detect, direction="long")
