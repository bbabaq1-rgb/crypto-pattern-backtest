"""
detector_equal_highs_4h.py — Equal Highs SMC (4h, SHORT).

정의:
  최근 LOOKBACK봉 내 피봇 고점(양쪽보다 높은 봉)이 최소 2개,
  그 중 최고 피봇과 0.3% 이내인 피봇이 2개 이상,
  AND 현재봉 고가가 그 레벨 ± 0.3% 이내 (유동성 존 재시험).
  → 숏 신호 (유동성 스윕 후 반전 예상).
"""
import detlib

LOOKBACK  = 30
TOLERANCE = 0.003   # 0.3%


def _pivot_highs(rows, start, end):
    """rows[start:end] 구간에서 피봇 고점 인덱스 목록."""
    pivots = []
    for j in range(start + 1, end - 1):
        if rows[j]["h"] >= rows[j-1]["h"] and rows[j]["h"] >= rows[j+1]["h"]:
            pivots.append(j)
    return pivots


def detect(rows):
    signals = []
    n = len(rows)
    for i in range(LOOKBACK, n):
        start = i - LOOKBACK
        pivots = _pivot_highs(rows, start, i)
        if len(pivots) < 2:
            continue
        highs = [rows[j]["h"] for j in pivots]
        ref   = max(highs)
        near  = [h for h in highs if abs(h - ref) / ref <= TOLERANCE]
        if len(near) < 2:
            continue
        # 현봉 고가가 equal-highs 레벨 근처
        curr_h = rows[i]["h"]
        if abs(curr_h - ref) / ref <= TOLERANCE:
            signals.append(i)
    return signals


def load_ohlcv(sym, tf="4h"):
    return detlib.load_ohlcv(sym, tf)


evaluate = detlib.make_evaluate(detect, direction="short")
