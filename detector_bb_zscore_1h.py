"""
detector_bb_zscore_1h.py — 볼린저 Z-score 반전 (1h).

롱: 전봉 종가가 20봉 볼린저 하단(2σ) 이탈 → 당봉이 밴드 안으로 복귀하며 양봉 마감.
숏: 상단 대칭 (전봉 상단 이탈 → 당봉 복귀 음봉).
필터: 당봉 거래량 <= 20봉 평균 거래량 × 0.8 (저볼륨 구간에서 평균회귀 우위).
"""
import statistics

import detlib

BB_N     = 20
BB_K     = 2.0
VOL_N    = 20
VOL_MAX  = 0.8


def _bands(rows):
    """봉별 (하단, 상단). 표본 부족 구간은 None."""
    closes = [r["c"] for r in rows]
    lo, hi = [None] * len(rows), [None] * len(rows)
    for i in range(BB_N - 1, len(rows)):
        w = closes[i - BB_N + 1: i + 1]
        m = sum(w) / BB_N
        sd = statistics.pstdev(w)
        lo[i] = m - BB_K * sd
        hi[i] = m + BB_K * sd
    return lo, hi


def _low_vol(rows, i):
    if i < VOL_N:
        return False
    avg = sum(r["v"] for r in rows[i - VOL_N: i]) / VOL_N
    return avg > 0 and rows[i]["v"] <= avg * VOL_MAX


def detect_long(rows):
    lo, _ = _bands(rows)
    sig = []
    for i in range(BB_N, len(rows)):
        if lo[i] is None or lo[i - 1] is None:
            continue
        prev, cur = rows[i - 1], rows[i]
        if (prev["c"] < lo[i - 1]              # 전봉 하단 이탈
                and cur["c"] > lo[i]           # 당봉 밴드 복귀
                and cur["c"] > cur["o"]        # 양봉 마감
                and _low_vol(rows, i)):
            sig.append(i)
    return sig


def detect_short(rows):
    _, hi = _bands(rows)
    sig = []
    for i in range(BB_N, len(rows)):
        if hi[i] is None or hi[i - 1] is None:
            continue
        prev, cur = rows[i - 1], rows[i]
        if (prev["c"] > hi[i - 1]              # 전봉 상단 이탈
                and cur["c"] < hi[i]           # 당봉 밴드 복귀
                and cur["c"] < cur["o"]        # 음봉 마감
                and _low_vol(rows, i)):
            sig.append(i)
    return sig


detect = detect_long   # 기본(스케줄러 픽업용) — 통과 방향으로 등재 시 조정


def load_ohlcv(sym, tf="1h"):
    return detlib.load_ohlcv(sym, tf)


evaluate = detlib.make_evaluate(detect_long, direction="long")
