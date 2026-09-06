"""detector_ma180_breakout.py — 일봉 장기 이평(기본 180일) 상향 돌파 롱.

study_ma_breakout.py(2026-09-06 탐색적 스터디)에서 '슈팅률이 무작위 진입의 1.3~1.6배'로 나온
이벤트를 **실거래 디텍터 형태**로 옮긴 것. 사전 등록 시험(validate_ma180.py) 대상이며
**게이트 통과 여부와 무관하게 실거래 미등재** — 사용자 지시로 이번 시험은 기록용이다
(registry/universe/scheduler 어디에도 넣지 않는다).

신호 정의(동결)
  MA = 종가 단순이동평균 ma_n 일.
  돌파 = close[i] > MA[i] 이고 close[i-1] <= MA[i-1].
  fresh = 그 직전 BELOW_MIN(20)봉 이상 연속으로 close <= MA 였던 경우만 신호로 센다
          (이평선 근처 톱질 재돌파 제외 — 스터디에서 재돌파는 무작위보다 나빴다).
  filt  = "decisive"(기본) 이면 종가 >= MA x DECISIVE(1.02) 까지 요구, "raw" 면 돌파만.
  진입  = 돌파봉 종가. 인과적 — 그 봉이 닫힌 뒤 알 수 있는 정보만 쓴다.

study_ma_breakout 의 crosses()/passes() 와 같은 신호 집합을 낸다(test_ma180.py 가 고정).
"""
from detlib import SYMBOLS, load_ohlcv, outcome, make_evaluate

PATTERN = "ma180_breakout"
MA_N = 180
BELOW_MIN = 20
DECISIVE = 1.02
FILTERS = ("decisive", "raw")


def sma(vals, n):
    """단순이동평균. 앞 n-1 개는 None."""
    out = [None] * len(vals)
    s = 0.0
    for i, v in enumerate(vals):
        s += v
        if i >= n:
            s -= vals[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def detect(rows, ma_n=MA_N, filt="decisive"):
    if filt not in FILTERS:
        raise ValueError(filt)
    cl = [r["c"] for r in rows]
    ma = sma(cl, ma_n)
    sig, below = [], 0
    for i in range(1, len(rows)):
        if ma[i] is not None and ma[i - 1] is not None and cl[i] > ma[i] and cl[i - 1] <= ma[i - 1]:
            if below >= BELOW_MIN and (filt == "raw" or cl[i] >= ma[i] * DECISIVE):
                sig.append(i)
        below = below + 1 if (ma[i] is not None and cl[i] <= ma[i]) else 0
    return sig


evaluate = make_evaluate(detect, "long")
if __name__ == "__main__":
    import statistics as st
    r = evaluate(); rr = r["rets"]
    print(PATTERN, r["agg"], f"mean={st.mean(rr)*100:+.2f}%" if rr else "")
