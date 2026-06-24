"""detector_hammer.py — Hammer (롱).
아래꼬리>=몸통2배, 위꼬리<=몸통0.5배, 몸통이 봉 상단 1/3 이내."""
from detlib import SYMBOLS, load_ohlcv, outcome, make_evaluate
PATTERN = "hammer"


def detect(rows):
    sig = []
    for i in range(len(rows)):
        o, h, l, c = rows[i]["o"], rows[i]["h"], rows[i]["l"], rows[i]["c"]
        body = abs(c - o); rng = h - l
        if body <= 0 or rng <= 0:
            continue
        uw = h - max(o, c); lw = min(o, c) - l
        if lw >= 2 * body and uw <= 0.5 * body and min(o, c) >= h - rng / 3:
            sig.append(i)
    return sig


evaluate = make_evaluate(detect, "long")
if __name__ == "__main__":
    import statistics as st
    r = evaluate(); rr = r["rets"]; print(PATTERN, r["agg"], f"mean={st.mean(rr)*100:+.2f}%" if rr else "")
