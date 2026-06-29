"""
detector_butterfly.py — Bullish Butterfly 하모닉 패턴 (롱 진입).

비율: AB/XA=0.786±0.05, BC/AB=0.382-0.886, CD/BC=1.618-2.618, AD/XA=1.272±0.05
D가 XA 기점(X)보다 아래 — 신저점 갱신 후 반전 기대.
"""
from detector_harmonic_base import make_evaluate, make_detect, HARMONIC_SYMBOLS
from detlib import load_ohlcv, outcome

PATTERN = "butterfly"
SYMBOLS = HARMONIC_SYMBOLS
CFG = {
    "ab_xa": (0.736, 0.836),   # 0.786 ± 0.05
    "bc_ab": (0.382, 0.886),
    "cd_bc": (1.618, 2.618),
    "ad_xa": (1.222, 1.322),   # 1.272 ± 0.05  (D는 X 아래)
}
evaluate = make_evaluate(CFG)
detect = make_detect(CFG)

if __name__ == "__main__":
    import statistics as st
    r = evaluate()
    rr = r["rets"]
    print(PATTERN, r["agg"], f"mean={st.mean(rr)*100:+.2f}%" if rr else "신호 없음")
