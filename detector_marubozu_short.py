"""detector_marubozu_short.py — Marubozu 숏(음봉). 몸통>=봉전체95%, 꼬리 거의 없음."""
from detlib import SYMBOLS, load_ohlcv, outcome as _oc, make_evaluate
PATTERN = "marubozu_short"


def outcome(rows, si):
    return _oc(rows, si, "short")


def detect(rows):
    sig = []
    for i in range(len(rows)):
        o, h, l, c = rows[i]["o"], rows[i]["h"], rows[i]["l"], rows[i]["c"]
        rng = h - l
        if rng <= 0:
            continue
        if c < o and (o - c) >= 0.95 * rng:          # 음봉 마루보주
            sig.append(i)
    return sig


evaluate = make_evaluate(detect, "short")
if __name__ == "__main__":
    import statistics as st
    r = evaluate(); rr = r["rets"]; print(PATTERN, r["agg"], f"mean={st.mean(rr)*100:+.2f}%" if rr else "")
