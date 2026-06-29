"""
detector_three_soldiers_4h.py — Three White Soldiers (4h, LONG).

정의:
  연속 3개 장대 양봉 (body >= range 의 60%), 각 봉의 종가가 전봉보다 높음,
  위꼬리 <= range 의 20%.
신호 = 3번째 봉(완성 시점), 종가 기준 라벨링.
"""
import detlib

BODY_RATIO  = 0.60   # 몸통 / 전체 range 최소 비율
UPPER_RATIO = 0.20   # 위꼬리 / 전체 range 최대 비율


def _is_white(r):
    body  = r["c"] - r["o"]
    rng   = (r["h"] - r["l"]) or 1e-9
    upper = r["h"] - r["c"]
    return body > 0 and body / rng >= BODY_RATIO and upper / rng <= UPPER_RATIO


def detect(rows):
    signals = []
    for i in range(2, len(rows)):
        r0, r1, r2 = rows[i-2], rows[i-1], rows[i]
        if (_is_white(r0) and _is_white(r1) and _is_white(r2)
                and r1["c"] > r0["c"] and r2["c"] > r1["c"]):
            signals.append(i)
    return signals


def load_ohlcv(sym, tf="4h"):
    return detlib.load_ohlcv(sym, tf)


evaluate = detlib.make_evaluate(detect, direction="long")
