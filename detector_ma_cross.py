"""
detector_ma_cross.py — MA5 x MA20 상향 교차 **단독** 진입 (2026-09-12, 진단 전용).

사전 등록 registry `yyy_cross_prereg_2026_09_12` 의 진단 arm.
캔들 조건 없이 교차 봉에서만 진입한다 — "크로스가 하는 일인가, 양양양이 하는 일인가"
에 직접 답한다. cross_only 가 yyy_cross 와 비슷하면 양양양이 보태는 게 없다는 뜻.

**판정 아님.** universe/scheduler 미등재.
"""
import detector_kakao_base as kb

load_ohlcv = kb.load_ohlcv


def detect(rows):
    f, s = kb.sma(rows, kb.MA_FAST), kb.sma(rows, kb.MA_SLOW)
    out = []
    for i in range(1, len(rows)):
        if None in (f[i], s[i], f[i - 1], s[i - 1]):
            continue
        if f[i - 1] <= s[i - 1] and f[i] > s[i]:
            out.append(i)
    return out
