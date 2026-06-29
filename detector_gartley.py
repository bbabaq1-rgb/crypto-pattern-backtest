"""
detector_gartley.py — Bullish Gartley 하모닉 패턴 (롱 진입).

비율: AB/XA=0.618±0.05, BC/AB=0.382-0.886, CD/BC=1.272-1.618, AD/XA=0.786±0.05
신호 = D 피벗 봉 종가(롱 진입 기대), ±10% 트리플배리어 라벨.
"""
from detector_harmonic_base import make_evaluate, make_detect, HARMONIC_SYMBOLS
from detlib import load_ohlcv, outcome

PATTERN = "gartley"
SYMBOLS = HARMONIC_SYMBOLS
CFG = {
    "ab_xa": (0.568, 0.668),   # 0.618 ± 0.05
    "bc_ab": (0.382, 0.886),
    "cd_bc": (1.272, 1.618),
    "ad_xa": (0.736, 0.836),   # 0.786 ± 0.05
}
evaluate = make_evaluate(CFG)
detect = make_detect(CFG)

if __name__ == "__main__":
    import statistics as st
    r = evaluate()
    rr = r["rets"]
    print(PATTERN, r["agg"], f"mean={st.mean(rr)*100:+.2f}%" if rr else "신호 없음")
