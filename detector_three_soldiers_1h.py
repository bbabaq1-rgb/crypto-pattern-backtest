"""detector_three_soldiers_1h.py — Three White Soldiers (1h, LONG)."""
import detlib

BODY_RATIO  = 0.60
UPPER_RATIO = 0.20


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


def load_ohlcv(sym, tf="1h"):
    return detlib.load_ohlcv(sym, tf)


evaluate = detlib.make_evaluate(detect, direction="long")
