"""
detector_fvg_short.py — Bearish Fair Value Gap (fvg의 direction='short').
3봉 갭다운(low[i-2] > high[i]) + 거래량 동반 -> 하방 모멘텀 숏.
라벨 반전(detlib.outcome short).
"""
from detlib import SYMBOLS, load_ohlcv, outcome as _oc, make_evaluate

PATTERN = "fvg_short"
VOL_MULT = 1.3


def outcome(rows, si):
    return _oc(rows, si, "short")


def detect(rows):
    n = len(rows)
    v = [r["v"] for r in rows]
    sig = []
    for i in range(22, n):
        if rows[i - 2]["l"] > rows[i]["h"]:        # 3봉 갭다운
            base = sum(v[i - 20:i]) / 20
            if base > 0 and v[i] >= VOL_MULT * base:
                sig.append(i)
    return sig


evaluate = make_evaluate(detect, "short")

if __name__ == "__main__":
    import statistics as st
    r = evaluate(); rr = r["rets"]
    print(PATTERN, r["agg"], f"mean={st.mean(rr)*100:+.2f}%" if rr else "")
