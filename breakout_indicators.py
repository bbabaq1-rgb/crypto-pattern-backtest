"""
breakout_indicators.py — 돌파형 + 지표 신호 detector

포함:
  detect_breakout         박스권(횡보) 돌파 + 거래량 (양방향)
  detect_rsi_divergence   RSI 다이버전스 (강세/약세)
  detect_ma_cross         이동평균 교차 (골든/데드크로스)

모두 동일한 Signal 인터페이스. 지표 신호(RSI/MA)는 완전 결정론적이라
백테스트가 가장 깨끗하게 재현된다. 거래량 확인은 돌파형에만 적용.

입력은 ccxt OHLCV: [ts, open, high, low, close, volume]
"""

from elliott_detect import zigzag, Signal
from triple_bottom_volume import _avg


def _closes_vols(ohlcv):
    if not ohlcv or not isinstance(ohlcv[0], (list, tuple)) or len(ohlcv[0]) < 6:
        return None, None
    return [c[4] for c in ohlcv], [c[5] for c in ohlcv]


# ----------------------------------------------------------------------
# 지표 계산
# ----------------------------------------------------------------------
def sma(closes, period):
    out = [None] * len(closes)
    s = 0.0
    for i, c in enumerate(closes):
        s += c
        if i >= period:
            s -= closes[i - period]
        if i >= period - 1:
            out[i] = s / period
    return out


def rsi(closes, period=14):
    out = [None] * len(closes)
    if len(closes) <= period:
        return out
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    ag = sum(max(d, 0) for d in deltas[:period]) / period
    al = sum(-min(d, 0) for d in deltas[:period]) / period
    out[period] = 100 - 100 / (1 + (ag / al if al else float("inf")))
    for i in range(period + 1, len(closes)):
        d = deltas[i - 1]
        ag = (ag * (period - 1) + max(d, 0)) / period
        al = (al * (period - 1) + max(-d, 0)) / period
        out[i] = 100 - 100 / (1 + (ag / al if al else float("inf")))
    return out


# ----------------------------------------------------------------------
# 돌파형 (박스권 횡보 후 이탈 + 거래량)
# ----------------------------------------------------------------------
def detect_breakout(ohlcv, lookback=20, range_tol=0.06, buffer=0.002, vol_mult=1.5):
    closes, vols = _closes_vols(ohlcv)
    if closes is None:
        return Signal("error", "none", 0.0, None, {"reason": "OHLCV 필요"})
    if len(closes) < lookback + 2:
        return Signal("none", "none", 0.0, "forming", {"n": len(closes)})

    i = len(closes) - 1
    band = closes[i - lookback:i]                    # 직전 lookback봉(현재 제외)
    res, sup = max(band), min(band)
    width = (res - sup) / (sup or 1)
    if width > range_tol:                            # 충분히 좁은 박스가 아님
        return Signal("none", "none", 0.0, "forming", {"width_pct": round(width * 100, 2)})

    price = closes[i]
    band_vol = _avg(vols[i - lookback:i])
    vol_ok = vols[i] >= band_vol * vol_mult
    up = price > res * (1 + buffer)
    down = price < sup * (1 - buffer)
    if not (up or down):
        return Signal("none", "none", 0.0, "in_range", {"width_pct": round(width * 100, 2)})

    matched = bool(vol_ok)
    shape = 0.6 + (0.2 if width <= range_tol / 2 else 0.0)
    conf = round(shape * (0.6 + 0.4), 3) if matched else round(shape * 0.4, 3)
    height = res - sup
    return Signal(
        pattern="range_breakout",
        direction="up" if up else "down",
        confidence=conf,
        current_wave="breakout",
        detail=dict(matched=matched, volume_confirmed=vol_ok,
                    breakout_ratio=round(vols[i] / band_vol, 2) if band_vol else None,
                    resistance=round(res, 2), support=round(sup, 2),
                    width_pct=round(width * 100, 2),
                    measured_target=round((res + height) if up else (sup - height), 2),
                    pivots=[(i, round(price, 2), "B")]))


# ----------------------------------------------------------------------
# RSI 다이버전스
# ----------------------------------------------------------------------
def detect_rsi_divergence(ohlcv, zz=0.04, period=14, oversold=45, overbought=55):
    closes, _ = _closes_vols(ohlcv)
    if closes is None:
        return Signal("error", "none", 0.0, None, {"reason": "OHLCV 필요"})
    r = rsi(closes, period)
    pivots = zigzag(closes, zz)

    lows = [p for p in pivots if p.kind == "L" and r[p.index] is not None]
    highs = [p for p in pivots if p.kind == "H" and r[p.index] is not None]

    # 강세 다이버전스: 가격 저점은 더 낮은데(LL) RSI 저점은 더 높음(HL)
    if len(lows) >= 2:
        a, b = lows[-2], lows[-1]
        if b.price < a.price and r[b.index] > r[a.index] and r[b.index] < oversold:
            strength = (r[b.index] - r[a.index]) / 100.0
            conf = round(min(0.5 + strength * 3 + (oversold - r[b.index]) / 100, 0.95), 3)
            return Signal("rsi_bullish_divergence", "up", conf, "divergence",
                          dict(matched=True, price_lows=[round(a.price, 2), round(b.price, 2)],
                               rsi_lows=[round(r[a.index], 1), round(r[b.index], 1)],
                               pivots=[(b.index, round(b.price, 2), "L")]))

    # 약세 다이버전스: 가격 고점은 더 높은데(HH) RSI 고점은 더 낮음(LH)
    if len(highs) >= 2:
        a, b = highs[-2], highs[-1]
        if b.price > a.price and r[b.index] < r[a.index] and r[b.index] > overbought:
            strength = (r[a.index] - r[b.index]) / 100.0
            conf = round(min(0.5 + strength * 3 + (r[b.index] - overbought) / 100, 0.95), 3)
            return Signal("rsi_bearish_divergence", "down", conf, "divergence",
                          dict(matched=True, price_highs=[round(a.price, 2), round(b.price, 2)],
                               rsi_highs=[round(r[a.index], 1), round(r[b.index], 1)],
                               pivots=[(b.index, round(b.price, 2), "H")]))
    return Signal("none", "none", 0.0, "forming", {"pivots": len(pivots)})


# ----------------------------------------------------------------------
# 이동평균 교차 (골든/데드크로스)
# ----------------------------------------------------------------------
def detect_ma_cross(ohlcv, fast=20, slow=50):
    closes, _ = _closes_vols(ohlcv)
    if closes is None:
        return Signal("error", "none", 0.0, None, {"reason": "OHLCV 필요"})
    if len(closes) < slow + 2:
        return Signal("none", "none", 0.0, "forming", {"n": len(closes)})
    f, s = sma(closes, fast), sma(closes, slow)
    i = len(closes) - 1
    if None in (f[i], s[i], f[i - 1], s[i - 1]):
        return Signal("none", "none", 0.0, "forming", {})

    golden = f[i - 1] <= s[i - 1] and f[i] > s[i]
    death = f[i - 1] >= s[i - 1] and f[i] < s[i]
    if not (golden or death):
        return Signal("none", "none", 0.0, "no_cross", {})

    sep = abs(f[i] - s[i]) / (s[i] or 1)
    conf = round(min(0.5 + sep * 8, 0.9), 3)         # 이격이 클수록 신뢰↑
    return Signal(
        pattern="golden_cross" if golden else "death_cross",
        direction="up" if golden else "down",
        confidence=conf, current_wave="cross",
        detail=dict(matched=True, fast=round(f[i], 2), slow=round(s[i], 2),
                    sep_pct=round(sep * 100, 2),
                    pivots=[(i, round(closes[i], 2), "X")]))
