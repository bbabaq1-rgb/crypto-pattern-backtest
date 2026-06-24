"""detector_dark_cloud_cover.py — Dark Cloud Cover (Piercing Line의 숏 버전).
양봉 다음날 음봉이 전 양봉 종가 이상 시작, 전 양봉 몸통 절반 이상 하향 관통."""
from detlib import SYMBOLS, load_ohlcv, outcome as _oc, make_evaluate
PATTERN = "dark_cloud_cover"


def outcome(rows, si):
    return _oc(rows, si, "short")


def detect(rows):
    sig = []
    for i in range(1, len(rows)):
        po, pc = rows[i - 1]["o"], rows[i - 1]["c"]
        o, c = rows[i]["o"], rows[i]["c"]
        if pc > po and c < o:                       # 전 양봉, 당 음봉
            mid = (po + pc) / 2
            if o >= pc and c <= mid and c > po:
                sig.append(i)
    return sig


evaluate = make_evaluate(detect, "short")
if __name__ == "__main__":
    import statistics as st
    r = evaluate(); rr = r["rets"]; print(PATTERN, r["agg"], f"mean={st.mean(rr)*100:+.2f}%" if rr else "")
