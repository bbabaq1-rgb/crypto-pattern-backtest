"""
reversal_patterns.py — 반전 패턴 detector 모음

포함:
  detect_inverse_hs   역헤드앤숄더 (강세 반전, direction=up)
  detect_hs           헤드앤숄더    (약세 반전, direction=down)
  detect_double_bottom 쌍바닥/이중바닥 (강세, direction=up)
  detect_double_top    쌍천정/이중천정 (약세, direction=down)

설계: ZigZag 피벗 + 넥라인/저항 돌파 + 거래량 확인(triple_bottom 프레임워크 재사용).
모두 동일한 Signal(pattern, direction, confidence, current_wave, detail) 반환.
detail['matched'] = 모양 AND 거래량(돌파 거래량 급증) 동시 충족.

입력은 ccxt OHLCV: [ts, open, high, low, close, volume]
"""

from elliott_detect import zigzag, Signal
from triple_bottom_volume import confirm_volume, VolumeProfile, _avg


def _closes_vols(ohlcv):
    if not ohlcv or not isinstance(ohlcv[0], (list, tuple)) or len(ohlcv[0]) < 6:
        return None, None
    return [c[4] for c in ohlcv], [c[5] for c in ohlcv]


def _first_break(closes, start_idx, level, above):
    """start_idx 이후 종가가 level 을 (above=True면 상향, 아니면 하향) 처음 돌파한 인덱스."""
    for i in range(start_idx + 1, len(closes)):
        if (above and closes[i] > level) or (not above and closes[i] < level):
            return i
    return None


# ======================================================================
# 헤드앤숄더 (역=강세 / 정=약세)
# ======================================================================
def _detect_hs(ohlcv, bullish, zz=0.04, shoulder_tol=0.06, head_min=0.02):
    closes, vols = _closes_vols(ohlcv)
    if closes is None:
        return Signal("error", "none", 0.0, None, {"reason": "OHLCV 필요"})
    pivots = zigzag(closes, zz)
    if len(pivots) < 5:
        return Signal("none", "none", 0.0, "forming", {"pivots": len(pivots)})

    # 역H&S: L-H-L-H-L (어깨-목-머리-목-어깨), 정H&S: H-L-H-L-H
    want = ["L", "H", "L", "H", "L"] if bullish else ["H", "L", "H", "L", "H"]
    for s in range(len(pivots) - 5, -1, -1):
        w = pivots[s:s + 5]
        if [x.kind for x in w] != want:
            continue
        sh1, nk1, head, nk2, sh2 = w
        shoulders = [sh1.price, sh2.price]
        neckline = (nk1.price + nk2.price) / 2.0

        if bullish:
            head_extreme = head.price < min(shoulders)          # 머리가 가장 낮음
            head_far = head.price <= min(shoulders) * (1 - head_min)
            sym = abs(sh1.price - sh2.price) / (_avg(shoulders) or 1) <= shoulder_tol
            valid = head_extreme and head_far and sym
            break_level = max(nk1.price, nk2.price)             # 넥라인 상향 돌파
            bo = _first_break(closes, sh2.index, break_level, above=True)
        else:
            head_extreme = head.price > max(shoulders)          # 머리가 가장 높음
            head_far = head.price >= max(shoulders) * (1 + head_min)
            sym = abs(sh1.price - sh2.price) / (_avg(shoulders) or 1) <= shoulder_tol
            valid = head_extreme and head_far and sym
            break_level = min(nk1.price, nk2.price)             # 넥라인 하향 이탈
            bo = _first_break(closes, sh2.index, break_level, above=False)

        if not valid:
            continue

        broke = bo is not None
        shape = 0.45
        if sym:                                   shape += 0.15
        if head_far:                              shape += 0.15
        if broke:                                 shape += 0.25
        shape = min(shape, 1.0)

        confirmed, vscore, vinfo = confirm_volume(
            vols, form_lo=w[0].index, form_hi=(bo or w[-1].index) + 1,
            breakout_idx=bo, low_pivot_idxs=[head.index],
            profile=VolumeProfile(breakout_mult=1.5, expect_decline=False))
        matched = bool(broke and confirmed)
        conf = round(shape * (0.5 + 0.5 * vscore), 3) if matched else round(shape * 0.3, 3)

        height = abs(head.price - neckline)
        target = (break_level + height) if bullish else (break_level - height)
        return Signal(
            pattern="inverse_head_shoulders" if bullish else "head_shoulders",
            direction="up" if bullish else "down",
            confidence=conf,
            current_wave="confirmed_breakout" if broke else "forming_no_breakout",
            detail=dict(matched=matched, shape_score=round(shape, 3),
                        volume_confirmed=confirmed, volume_score=vscore,
                        volume_info=vinfo, neckline=round(neckline, 2),
                        head=round(head.price, 2),
                        measured_target=round(target, 2),
                        pivots=[(p.index, round(p.price, 2), p.kind) for p in w]))
    return Signal("none", "none", 0.0, "forming", {"pivots": len(pivots)})


def detect_inverse_hs(ohlcv, **kw):
    return _detect_hs(ohlcv, bullish=True, **kw)


def detect_hs(ohlcv, **kw):
    return _detect_hs(ohlcv, bullish=False, **kw)


# ======================================================================
# 쌍바닥 / 쌍천정 (이중바닥/이중천정)
# ======================================================================
def _detect_double(ohlcv, bullish, zz=0.04, level_tol=0.03):
    closes, vols = _closes_vols(ohlcv)
    if closes is None:
        return Signal("error", "none", 0.0, None, {"reason": "OHLCV 필요"})
    pivots = zigzag(closes, zz)
    if len(pivots) < 3:
        return Signal("none", "none", 0.0, "forming", {"pivots": len(pivots)})

    want = ["L", "H", "L"] if bullish else ["H", "L", "H"]
    for s in range(len(pivots) - 3, -1, -1):
        w = pivots[s:s + 3]
        if [x.kind for x in w] != want:
            continue
        a, mid, b = w
        spread = abs(a.price - b.price) / (_avg([a.price, b.price]) or 1)
        equal = spread <= level_tol
        if not equal:
            continue

        if bullish:
            bo = _first_break(closes, b.index, mid.price, above=True)   # 가운데 고점 돌파
        else:
            bo = _first_break(closes, b.index, mid.price, above=False)  # 가운데 저점 이탈
        broke = bo is not None

        shape = 0.5
        if spread <= level_tol / 2:  shape += 0.2
        if broke:                    shape += 0.3
        shape = min(shape, 1.0)

        confirmed, vscore, vinfo = confirm_volume(
            vols, form_lo=a.index, form_hi=(bo or b.index) + 1, breakout_idx=bo,
            low_pivot_idxs=[a.index, b.index],
            profile=VolumeProfile(breakout_mult=1.5, expect_decline=False))
        matched = bool(broke and confirmed)
        conf = round(shape * (0.5 + 0.5 * vscore), 3) if matched else round(shape * 0.3, 3)

        height = abs(mid.price - (a.price + b.price) / 2)
        target = (mid.price + height) if bullish else (mid.price - height)
        return Signal(
            pattern="double_bottom" if bullish else "double_top",
            direction="up" if bullish else "down",
            confidence=conf,
            current_wave="confirmed_breakout" if broke else "forming_no_breakout",
            detail=dict(matched=matched, shape_score=round(shape, 3),
                        volume_confirmed=confirmed, volume_score=vscore,
                        volume_info=vinfo, neckline=round(mid.price, 2),
                        spread_pct=round(spread * 100, 2),
                        measured_target=round(target, 2),
                        pivots=[(p.index, round(p.price, 2), p.kind) for p in w]))
    return Signal("none", "none", 0.0, "forming", {"pivots": len(pivots)})


def detect_double_bottom(ohlcv, **kw):
    return _detect_double(ohlcv, bullish=True, **kw)


def detect_double_top(ohlcv, **kw):
    return _detect_double(ohlcv, bullish=False, **kw)
