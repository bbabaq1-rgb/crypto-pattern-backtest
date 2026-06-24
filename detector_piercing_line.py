"""detector_piercing_line.py — Piercing Line (롱).
음봉 다음날 양봉이 전 음봉 종가 이하 시작, 전 음봉 몸통 절반 이상 관통(완전포함 전)."""
from detlib import SYMBOLS, load_ohlcv, outcome, make_evaluate
PATTERN = "piercing_line"


def detect(rows):
    sig = []
    for i in range(1, len(rows)):
        po, pc = rows[i - 1]["o"], rows[i - 1]["c"]
        o, c = rows[i]["o"], rows[i]["c"]
        if pc < po and c > o:                       # 전 음봉, 당 양봉
            mid = (po + pc) / 2
            if o <= pc and c >= mid and c < po:     # 종가이하 시작 + 절반관통(미완전포함)
                sig.append(i)
    return sig


evaluate = make_evaluate(detect, "long")
if __name__ == "__main__":
    import statistics as st
    r = evaluate(); rr = r["rets"]; print(PATTERN, r["agg"], f"mean={st.mean(rr)*100:+.2f}%" if rr else "")
