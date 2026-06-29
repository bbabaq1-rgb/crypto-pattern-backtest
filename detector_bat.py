"""
detector_bat.py — Bullish Bat 하모닉 패턴 (롱 진입).

비율: AB/XA=0.382-0.500, BC/AB=0.382-0.886, CD/BC=1.618-2.618, AD/XA=0.886±0.05
D가 XA의 88.6% 되돌림 지점. Gartley보다 깊은 D.
"""
from detector_harmonic_base import make_evaluate, make_detect, HARMONIC_SYMBOLS
from detlib import load_ohlcv, outcome

PATTERN = "bat"
SYMBOLS = HARMONIC_SYMBOLS
CFG = {
    "ab_xa": (0.332, 0.550),   # 0.382-0.50 (여유 ±0.05)
    "bc_ab": (0.382, 0.886),
    "cd_bc": (1.618, 2.618),
    "ad_xa": (0.836, 0.936),   # 0.886 ± 0.05
}
evaluate = make_evaluate(CFG)
detect = make_detect(CFG)

if __name__ == "__main__":
    import statistics as st
    r = evaluate()
    rr = r["rets"]
    print(PATTERN, r["agg"], f"mean={st.mean(rr)*100:+.2f}%" if rr else "신호 없음")
