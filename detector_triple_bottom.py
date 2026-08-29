"""
detector_triple_bottom.py — 삼중바닥 탐지 (롱 반전). TF 무관(15m~1M).

사용자 정의 패턴 (2026-08-29, 차트 5장 기반 데이터화):
  (1) 베이스: 스윙 저점(±PIVOT_HALF 국소 최저) N_LOWS(3)개 이상이
      MAX_SPAN 봉 이내에 형성. 연속 저점 간격 >= MIN_SPACING 봉.
  (2) 넥라인: 첫 저점~마지막 저점 사이 고점의 최댓값.
  (3) 깊이: (넥라인 - 최저점) >= DEPTH_ATR_MULT x ATR(14). 얕은 노이즈 배제.
      -> 고정 % 대신 ATR 배수라 15m~1M 모든 TF에서 같은 정의가 성립.
  (4) 저점 동일수준: 세 저점 모두 베이스 깊이 하위 EQ_DEPTH_FRAC 이내.
      -> 허용폭이 패턴 자체 깊이에 비례(스케일 프리). 완만한 하락/상승 저점 허용.
  (5) 트리거: 마지막 저점 이후 MAX_WAIT 봉 내 종가가 넥라인 상향 돌파.
      신호 = 돌파봉 인덱스 (사용자 차트의 진입 시점과 동일).
  (6) 거래량 확인: 돌파봉 거래량 >= 형성구간 평균 x VOL_BREAK_MULT
      (triple_bottom_volume.py 의 고전 TA 규칙 재사용 — 가짜 돌파 방지).

거울상(삼중천장->숏)은 detector_triple_top.py.
라벨/수익 동결: detlib 트리플배리어 ±10%/20봉/수수료 0.2%.
"""
import detlib

PIVOT_HALF     = 3      # 스윙 저점 = ±3봉 국소 최저
N_LOWS         = 3      # 최소 저점 수 (3 = 삼중바닥)
MIN_SPACING    = 5      # 연속 저점 최소 간격(봉) — 같은 바닥 중복 집계 방지
MAX_SPAN       = 90     # 첫~마지막 저점 최대 간격(봉)
MAX_WAIT       = 30     # 마지막 저점 후 돌파 대기 한도(봉)
DEPTH_ATR_MULT = 2.5    # 베이스 깊이 >= ATR14 x 2.5
EQ_DEPTH_FRAC  = 0.35   # 저점들이 베이스 깊이 하위 35% 이내
VOL_BREAK_MULT = 1.5    # 돌파 거래량 >= 형성구간 평균 x 1.5

PATTERN = "triple_bottom"
load_ohlcv = detlib.load_ohlcv


def _atr(rows, i, period=14):
    """i 시점 ATR(단순평균). 데이터 부족 시 None."""
    if i < period + 1:
        return None
    trs = []
    for j in range(i - period + 1, i + 1):
        hi, lo, pc = rows[j]["h"], rows[j]["l"], rows[j - 1]["c"]
        trs.append(max(hi - lo, abs(hi - pc), abs(lo - pc)))
    return sum(trs) / period


def _swing_pivots(rows, key, cmp_min=True):
    """±PIVOT_HALF 국소 극값 인덱스 목록."""
    vals = [r[key] for r in rows]
    out = []
    for i in range(PIVOT_HALF, len(rows) - PIVOT_HALF):
        seg = vals[i - PIVOT_HALF:i + PIVOT_HALF + 1]
        if (min(seg) if cmp_min else max(seg)) == vals[i]:
            out.append(i)
    return out


def detect(rows):
    n = len(rows)
    if n < MAX_SPAN // 2:
        return []
    lo = [r["l"] for r in rows]
    hi = [r["h"] for r in rows]
    cl = [r["c"] for r in rows]
    vo = [r["v"] for r in rows]
    piv = _swing_pivots(rows, "l", cmp_min=True)

    sig = []
    used_brk = set()
    # 마지막 저점 L3 후보를 순회, 뒤로 저점 2개(L1, L2)를 찾는다
    for c_i in range(len(piv) - 1, 1, -1):
        L3 = piv[c_i]
        # L3보다 앞이며 spacing/span을 만족하는 저점 조합 중 가장 최근 것
        cand = [p for p in piv[:c_i] if L3 - p <= MAX_SPAN]
        picked = None
        for b_i in range(len(cand) - 1, 0, -1):
            L2 = cand[b_i]
            if L3 - L2 < MIN_SPACING:
                continue
            for a_i in range(b_i - 1, -1, -1):
                L1 = cand[a_i]
                if L2 - L1 < MIN_SPACING:
                    continue
                picked = (L1, L2, L3)
                break
            if picked:
                break
        if not picked:
            continue
        L1, L2, L3 = picked

        neck = max(hi[L1:L3 + 1])
        base_low = min(lo[L1:L3 + 1])
        depth = neck - base_low
        atr = _atr(rows, L3)
        if atr is None or depth < DEPTH_ATR_MULT * atr:
            continue
        # 세 저점 동일 수준: 모두 베이스 하위 EQ_DEPTH_FRAC 이내
        if max(lo[L1], lo[L2], lo[L3]) > base_low + EQ_DEPTH_FRAC * depth:
            continue

        # 돌파 탐색: L3 이후 MAX_WAIT 봉 내 종가 > 넥라인
        brk = None
        for j in range(L3 + 1, min(L3 + 1 + MAX_WAIT, n)):
            if cl[j] > neck:
                brk = j
                break
        if brk is None or brk in used_brk:
            continue
        # 거래량 확인: 돌파봉 >= 형성구간 평균 x 배수
        form_avg = sum(vo[L1:L3 + 1]) / max(1, L3 + 1 - L1)
        if form_avg > 0 and vo[brk] < form_avg * VOL_BREAK_MULT:
            continue
        used_brk.add(brk)
        sig.append(brk)
    return sorted(set(sig))


evaluate = detlib.make_evaluate(detect, "long")

if __name__ == "__main__":
    import statistics as st
    r = evaluate()
    a, rr = r["agg"], r["rets"]
    print(PATTERN, a, f"mean={st.mean(rr)*100:+.2f}%" if rr else "")
