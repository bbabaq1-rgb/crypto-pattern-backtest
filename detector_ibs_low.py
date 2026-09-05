"""detector_ibs_low.py — IBS(Internal Bar Strength) 저점 롱 (1d 평균회귀).
IBS = (c - l) / (h - l). 종가가 봉 하단에 붙은 하락 봉(IBS < 0.2, c < 전일 c) 다음 봉 진입.
캔들 가족(hammer/morning_star/piercing 등)과 달리 몸통·꼬리 형태를 보지 않는다 — 다른 정보다.
2026-09-05 사전 등록 후보. 게이트 통과 전까지 실거래 미등재."""
from detlib import SYMBOLS, load_ohlcv, outcome, make_evaluate
PATTERN = "ibs_low"
IBS_THR = 0.2


def detect(rows):
    sig = []
    for i in range(1, len(rows)):
        h, l, c = rows[i]["h"], rows[i]["l"], rows[i]["c"]
        rng = h - l
        if rng <= 0:
            continue
        if (c - l) / rng < IBS_THR and c < rows[i - 1]["c"]:
            sig.append(i)
    return sig


evaluate = make_evaluate(detect, "long")
if __name__ == "__main__":
    import statistics as st
    r = evaluate(); rr = r["rets"]; print(PATTERN, r["agg"], f"mean={st.mean(rr)*100:+.2f}%" if rr else "")
