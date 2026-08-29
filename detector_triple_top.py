"""
detector_triple_top.py — 삼중천장 탐지 (숏 반전). 삼중바닥의 거울상.

정의는 detector_triple_bottom.py 와 완전 대칭:
  스윙 고점 3개 동일수준(천장 깊이 상위 EQ_DEPTH_FRAC 이내) + 깊이 >= ATR x 2.5
  + 마지막 고점 후 MAX_WAIT 봉 내 종가가 넥라인(사이 저점의 최저) 하향 이탈
  + 이탈봉 거래량 >= 형성구간 평균 x VOL_BREAK_MULT.
파라미터는 triple_bottom 것을 그대로 import — 두 패턴이 따로 튜닝되지 않도록
(자유도 축소, 거울상 보장).
"""
import detlib
from detector_triple_bottom import (
    PIVOT_HALF, N_LOWS, MIN_SPACING, MAX_SPAN, MAX_WAIT,
    DEPTH_ATR_MULT, EQ_DEPTH_FRAC, VOL_BREAK_MULT, _atr, _swing_pivots,
)

PATTERN = "triple_top"
load_ohlcv = detlib.load_ohlcv


def detect(rows):
    n = len(rows)
    if n < MAX_SPAN // 2:
        return []
    lo = [r["l"] for r in rows]
    hi = [r["h"] for r in rows]
    cl = [r["c"] for r in rows]
    vo = [r["v"] for r in rows]
    piv = _swing_pivots(rows, "h", cmp_min=False)

    sig = []
    used_brk = set()
    for c_i in range(len(piv) - 1, 1, -1):
        H3 = piv[c_i]
        cand = [p for p in piv[:c_i] if H3 - p <= MAX_SPAN]
        picked = None
        for b_i in range(len(cand) - 1, 0, -1):
            H2 = cand[b_i]
            if H3 - H2 < MIN_SPACING:
                continue
            for a_i in range(b_i - 1, -1, -1):
                H1 = cand[a_i]
                if H2 - H1 < MIN_SPACING:
                    continue
                picked = (H1, H2, H3)
                break
            if picked:
                break
        if not picked:
            continue
        H1, H2, H3 = picked

        neck = min(lo[H1:H3 + 1])
        base_high = max(hi[H1:H3 + 1])
        depth = base_high - neck
        atr = _atr(rows, H3)
        if atr is None or depth < DEPTH_ATR_MULT * atr:
            continue
        # 세 고점 동일 수준: 모두 천장 상위 EQ_DEPTH_FRAC 이내
        if min(hi[H1], hi[H2], hi[H3]) < base_high - EQ_DEPTH_FRAC * depth:
            continue

        brk = None
        for j in range(H3 + 1, min(H3 + 1 + MAX_WAIT, n)):
            if cl[j] < neck:
                brk = j
                break
        if brk is None or brk in used_brk:
            continue
        form_avg = sum(vo[H1:H3 + 1]) / max(1, H3 + 1 - H1)
        if form_avg > 0 and vo[brk] < form_avg * VOL_BREAK_MULT:
            continue
        used_brk.add(brk)
        sig.append(brk)
    return sorted(set(sig))


evaluate = detlib.make_evaluate(detect, "short")

if __name__ == "__main__":
    import statistics as st
    r = evaluate()
    a, rr = r["agg"], r["rets"]
    print(PATTERN, a, f"mean={st.mean(rr)*100:+.2f}%" if rr else "")
