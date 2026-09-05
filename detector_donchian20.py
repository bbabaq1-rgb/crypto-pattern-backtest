"""detector_donchian20.py — 20일 고가 돌파 롱 (1d 추세추종).
종가 > 직전 20봉 고가 최대. 배포 패턴 중 추세추종은 three_soldiers_4h 하나라 가족을 넓힌다.
같은 봉 연속 돌파는 첫 봉만(직전 봉이 이미 돌파 상태면 제외).
2026-09-05 사전 등록 후보. 게이트 통과 전까지 실거래 미등재."""
from detlib import SYMBOLS, load_ohlcv, outcome, make_evaluate
PATTERN = "donchian20"
N = 20


def detect(rows):
    sig = []
    hs = [r["h"] for r in rows]; cs = [r["c"] for r in rows]
    for i in range(N + 1, len(rows)):
        hi_prev = max(hs[i - N:i])
        if cs[i] > hi_prev:
            hi_prev2 = max(hs[i - N - 1:i - 1])
            if not cs[i - 1] > hi_prev2:          # 첫 돌파 봉만
                sig.append(i)
    return sig


evaluate = make_evaluate(detect, "long")
if __name__ == "__main__":
    import statistics as st
    r = evaluate(); rr = r["rets"]; print(PATTERN, r["agg"], f"mean={st.mean(rr)*100:+.2f}%" if rr else "")
