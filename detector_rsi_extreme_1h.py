"""
detector_rsi_extreme_1h.py — RSI 극단 + 저볼륨 반전 (1h).

롱: RSI(14) 전봉 < 25 → 당봉 RSI 반등 + 양봉 마감.
숏: RSI(14) 전봉 > 75 → 당봉 RSI 하락 + 음봉 마감.
필터: 당봉 거래량 <= 20봉 평균 거래량 × 0.8.
"""
import detlib

RSI_N   = 14
RSI_LO  = 25.0
RSI_HI  = 75.0
VOL_N   = 20
VOL_MAX = 0.8


def _rsi(rows, n=RSI_N):
    """Wilder RSI 시리즈. 표본 부족 구간은 None."""
    out = [None] * len(rows)
    if len(rows) <= n:
        return out
    gains = losses = 0.0
    for i in range(1, n + 1):
        d = rows[i]["c"] - rows[i - 1]["c"]
        gains += max(d, 0); losses += max(-d, 0)
    ag, al = gains / n, losses / n
    out[n] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    for i in range(n + 1, len(rows)):
        d = rows[i]["c"] - rows[i - 1]["c"]
        ag = (ag * (n - 1) + max(d, 0)) / n
        al = (al * (n - 1) + max(-d, 0)) / n
        out[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def _low_vol(rows, i):
    if i < VOL_N:
        return False
    avg = sum(r["v"] for r in rows[i - VOL_N: i]) / VOL_N
    return avg > 0 and rows[i]["v"] <= avg * VOL_MAX


def detect_long(rows):
    rsi = _rsi(rows)
    sig = []
    for i in range(RSI_N + 1, len(rows)):
        if rsi[i] is None or rsi[i - 1] is None:
            continue
        cur = rows[i]
        if (rsi[i - 1] < RSI_LO                # 전봉 RSI 극단(과매도)
                and rsi[i] > rsi[i - 1]        # 반등
                and cur["c"] > cur["o"]        # 양봉 마감
                and _low_vol(rows, i)):
            sig.append(i)
    return sig


def detect_short(rows):
    rsi = _rsi(rows)
    sig = []
    for i in range(RSI_N + 1, len(rows)):
        if rsi[i] is None or rsi[i - 1] is None:
            continue
        cur = rows[i]
        if (rsi[i - 1] > RSI_HI                # 전봉 RSI 극단(과매수)
                and rsi[i] < rsi[i - 1]        # 하락 전환
                and cur["c"] < cur["o"]        # 음봉 마감
                and _low_vol(rows, i)):
            sig.append(i)
    return sig


detect = detect_long   # 기본(스케줄러 픽업용) — 통과 방향으로 등재 시 조정


def load_ohlcv(sym, tf="1h"):
    return detlib.load_ohlcv(sym, tf)


evaluate = detlib.make_evaluate(detect_long, direction="long")
