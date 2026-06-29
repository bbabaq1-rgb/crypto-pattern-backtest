"""
detector_cypher.py — Bullish Cypher 하모닉 패턴 (롱 진입).

비율:
  AB/XA = 0.382-0.618
  BC/AB = 1.272-1.414  (C가 A를 돌파, 연장)
  XD/XC = 0.786 ± 0.05 (D = X에서 XC의 78.6% 지점)

Cypher는 C가 A를 상회한 뒤, D가 XC의 78.6% 되돌림 지점에서 반전.
"""
from detector_harmonic_base import make_evaluate, make_detect, HARMONIC_SYMBOLS
from detlib import load_ohlcv, outcome

PATTERN = "cypher"
SYMBOLS = HARMONIC_SYMBOLS
CFG = {
    "ab_xa": (0.332, 0.668),   # 0.382-0.618
    "bc_ab": (1.272, 1.414),   # 연장 (C > A)
    "xd_xc": (0.736, 0.836),   # 0.786 ± 0.05
}
evaluate = make_evaluate(CFG)
detect = make_detect(CFG)

if __name__ == "__main__":
    import statistics as st
    r = evaluate()
    rr = r["rets"]
    print(PATTERN, r["agg"], f"mean={st.mean(rr)*100:+.2f}%" if rr else "신호 없음")
