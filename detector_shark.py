"""
detector_shark.py — Bullish Shark 하모닉 패턴 (롱 진입).

비율:
  AB/XA = 0.382-0.618
  BC/AB = 1.130-1.618  (C가 A를 돌파, 연장)
  XD/XC = 0.886 ± 0.05 (D = X에서 XC의 88.6% 지점)

일반 XABCD와 달리 C가 A(고점)를 상회하는 연장 패턴.
D는 C보다 낮지만 A보다 높은 구간 (A~C 사이).
"""
from detector_harmonic_base import make_evaluate, make_detect, HARMONIC_SYMBOLS
from detlib import load_ohlcv, outcome

PATTERN = "shark"
SYMBOLS = HARMONIC_SYMBOLS
CFG = {
    "ab_xa": (0.332, 0.668),   # 0.382-0.618
    "bc_ab": (1.130, 1.618),   # 연장 (C > A)
    "xd_xc": (0.836, 0.936),   # 0.886 ± 0.05
    # cd_bc / ad_xa 불사용 — XD/XC 가 주 조건
}
evaluate = make_evaluate(CFG)
detect = make_detect(CFG)

if __name__ == "__main__":
    import statistics as st
    r = evaluate()
    rr = r["rets"]
    print(PATTERN, r["agg"], f"mean={st.mean(rr)*100:+.2f}%" if rr else "신호 없음")
