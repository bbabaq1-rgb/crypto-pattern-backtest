"""
detector_crab.py — Bullish Crab 하모닉 패턴 (롱 진입).

비율: AB/XA=0.382-0.618, BC/AB=0.382-0.886, CD/BC=2.618-3.618, AD/XA=1.618±0.05
가장 극단적인 확장 패턴. CD/BC가 2.618~3.618 수준으로 D가 X 훨씬 아래.
"""
from detector_harmonic_base import make_evaluate, make_detect, HARMONIC_SYMBOLS
from detlib import load_ohlcv, outcome

PATTERN = "crab"
SYMBOLS = HARMONIC_SYMBOLS
CFG = {
    "ab_xa": (0.332, 0.668),   # 0.382-0.618
    "bc_ab": (0.382, 0.886),
    "cd_bc": (2.618, 3.618),
    "ad_xa": (1.568, 1.668),   # 1.618 ± 0.05
}
evaluate = make_evaluate(CFG)
detect = make_detect(CFG)

if __name__ == "__main__":
    import statistics as st
    r = evaluate()
    rr = r["rets"]
    print(PATTERN, r["agg"], f"mean={st.mean(rr)*100:+.2f}%" if rr else "신호 없음")
