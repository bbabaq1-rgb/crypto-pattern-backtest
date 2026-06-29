"""detector_three_crows_1h.py — Three Black Crows (1h, SHORT)."""
import detlib

BODY_RATIO  = 0.60
LOWER_RATIO = 0.20


def _is_black(r):
    body  = r["o"] - r["c"]
    rng   = (r["h"] - r["l"]) or 1e-9
    lower = r["c"] - r["l"]
    return body > 0 and body / rng >= BODY_RATIO and lower / rng <= LOWER_RATIO


def detect(rows):
    signals = []
    for i in range(2, len(rows)):
        r0, r1, r2 = rows[i-2], rows[i-1], rows[i]
        if (_is_black(r0) and _is_black(r1) and _is_black(r2)
                and r1["c"] < r0["c"] and r2["c"] < r1["c"]):
            signals.append(i)
    return signals


def load_ohlcv(sym, tf="1h"):
    return detlib.load_ohlcv(sym, tf)


evaluate = detlib.make_evaluate(detect, direction="short")
