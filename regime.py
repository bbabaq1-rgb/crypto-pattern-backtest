"""
regime.py — 시장 레짐 분류 (200봉 이동평균 기울기 기준).

규칙: MA(MA_PERIOD)의 최근 SLOPE_LB봉 변화율이
  > +SLOPE_THR  -> 'up'
  < -SLOPE_THR  -> 'down'
  그 사이        -> 'side'
(타임프레임 무관하게 '200봉' 기준 — 1d면 ~200일.)
"""
MA_PERIOD = 200
SLOPE_LB  = 20      # 기울기 측정 구간(봉)
SLOPE_THR = 0.02    # ±2% 변화율


def _sma(closes, p):
    out = [None] * len(closes)
    s = 0.0
    for i, c in enumerate(closes):
        s += c
        if i >= p:
            s -= closes[i - p]
        if i >= p - 1:
            out[i] = s / p
    return out


def classify(rows):
    """각 봉의 레짐 리스트(up/down/side/None)."""
    closes = [r["c"] for r in rows]
    m = _sma(closes, MA_PERIOD)
    reg = [None] * len(rows)
    for i in range(len(rows)):
        if m[i] is None or i - SLOPE_LB < 0 or m[i - SLOPE_LB] is None:
            continue
        slope = (m[i] - m[i - SLOPE_LB]) / m[i - SLOPE_LB]
        reg[i] = "up" if slope > SLOPE_THR else "down" if slope < -SLOPE_THR else "side"
    return reg
