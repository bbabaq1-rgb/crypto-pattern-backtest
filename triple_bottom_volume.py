"""
삼중바닥(Triple Bottom) detector + 거래량 확인 프레임워크

elliott_detect.py 와 같은 폴더에 둔다 (zigzag/Signal 재사용).
입력은 ccxt OHLCV 형식 필수: [ts, open, high, low, close, volume]
  → 거래량 확인을 하려면 volume 컬럼이 반드시 있어야 한다.

핵심 설계 (대표님 요건 반영):
  '패턴 일치'는 '모양 일치 AND 거래량 일치'일 때만 True (matched).
  거래량이 안 맞으면 모양이 맞아도 matched=False 로 거른다 → 가짜 돌파 방지.

삼중바닥 거래량 규칙(고전 TA):
  - 형성 구간: 저점 3개로 갈수록 거래량 '감소'(매도 소진)        ⚙️ 가이드라인
  - 돌파 구간: 저항선 상향 돌파 시 거래량 '급증'                ✅ 핵심 확인
"""

from dataclasses import dataclass
from elliott_detect import zigzag, Signal, Pivot


# ======================================================================
# 거래량 확인 프레임워크 (모든 패턴 공용)
# ======================================================================
@dataclass
class VolumeProfile:
    """패턴별 거래량 요건 명세. 패턴마다 이 명세만 바꿔 끼우면 된다."""
    breakout_mult: float = 1.5      # 돌파 거래량 ≥ 형성구간 평균 × 이 배수
    expect_decline: bool = True     # 형성 구간 거래량 감소(소진)를 기대하는가


def _avg(xs):
    return sum(xs) / len(xs) if xs else 0.0


def _win_avg(volumes, idx, half=2):
    """피벗 단일 봉 노이즈를 줄이려 idx 주변 구간 평균을 쓴다."""
    lo = max(0, idx - half)
    hi = min(len(volumes), idx + half + 1)
    return _avg(volumes[lo:hi])


def confirm_volume(volumes, form_lo, form_hi, breakout_idx,
                   low_pivot_idxs, profile: VolumeProfile):
    """
    거래량 일치 여부를 (confirmed, score, info)로 반환.
      - form_lo:form_hi  형성 구간 인덱스 범위
      - breakout_idx     돌파가 발생한 캔들 인덱스
      - low_pivot_idxs   저점 피벗들의 인덱스(감소 추세 확인용)
    """
    form_avg = _avg(volumes[form_lo:form_hi])
    bo_vol = volumes[breakout_idx] if breakout_idx is not None else 0.0

    # ✅ 핵심: 돌파 거래량 급증
    breakout_ok = bo_vol >= form_avg * profile.breakout_mult

    # ⚙️ 가이드라인: 저점들로 갈수록 거래량 감소 (단일 봉 대신 구간 평균)
    low_vols = [_win_avg(volumes, i, half=2) for i in low_pivot_idxs]
    declining = all(low_vols[k] >= low_vols[k + 1] * 0.98
                    for k in range(len(low_vols) - 1)) if len(low_vols) >= 2 else False

    confirmed = breakout_ok                       # 돌파 거래량은 필수
    score = 0.0
    if breakout_ok:                       score += 0.70
    if profile.expect_decline and declining:  score += 0.30
    elif not profile.expect_decline:          score += 0.30

    info = dict(form_avg=round(form_avg, 1), breakout_vol=round(bo_vol, 1),
                breakout_ratio=round(bo_vol / form_avg, 2) if form_avg else None,
                low_volumes=[round(v, 1) for v in low_vols],
                breakout_ok=breakout_ok, declining=declining)
    return confirmed, round(score, 3), info


# ======================================================================
# 삼중바닥 detector
# ======================================================================
def detect_triple_bottom(ohlcv, zigzag_threshold=0.04,
                         level_tol=0.03, profile: VolumeProfile = None) -> Signal:
    """
    삼중바닥: 비슷한 가격대의 저점 3개 + 사이 반등 고점 2개, 저항 돌파 시 확정.
    level_tol: 저점 3개가 '같은 수준'으로 인정되는 허용 편차(기본 3%).
    """
    if not ohlcv or not isinstance(ohlcv[0], (list, tuple)) or len(ohlcv[0]) < 6:
        return Signal("error", "none", 0.0, None,
                      {"reason": "OHLCV(volume 포함) 형식 필요"})
    if profile is None:
        profile = VolumeProfile()

    closes  = [c[4] for c in ohlcv]
    volumes = [c[5] for c in ohlcv]
    pivots = zigzag(closes, zigzag_threshold)
    if len(pivots) < 5:
        return Signal("none", "none", 0.0, "forming", {"pivots": len(pivots)})

    # 저-고-저-고-저 (low1,high1,low2,high2,low3) 후보를 뒤에서부터 탐색
    for s in range(len(pivots) - 5, -1, -1):
        w = pivots[s:s + 5]
        if [x.kind for x in w] != ["L", "H", "L", "H", "L"]:
            continue
        low1, high1, low2, high2, low3 = w
        lows = [low1.price, low2.price, low3.price]

        # --- 모양 조건 ---
        level_spread = (max(lows) - min(lows)) / (_avg(lows) or 1)
        equal_lows = level_spread <= level_tol           # 저점 3개가 같은 수준
        resistance = max(high1.price, high2.price)        # 돌파 기준선
        if not equal_lows:
            continue

        # 돌파 캔들: low3 이후 종가가 저항선을 처음 넘는 지점
        breakout_idx = None
        for i in range(low3.index + 1, len(closes)):
            if closes[i] > resistance:
                breakout_idx = i
                break
        breakout_confirmed = breakout_idx is not None

        # 모양 confidence (거래량 전, 순수 형태 점수)
        shape_score = 0.45
        if level_spread <= level_tol / 2:  shape_score += 0.15   # 저점 정렬 우수
        if breakout_confirmed:             shape_score += 0.25   # 저항 돌파 완성
        # 두 반등 고점이 비슷하면(수평 저항) 가산
        if abs(high1.price - high2.price) / (_avg([high1.price, high2.price]) or 1) <= 0.03:
            shape_score += 0.15
        shape_score = min(shape_score, 1.0)

        # --- 거래량 확인 ---
        vol_confirmed, vol_score, vol_info = confirm_volume(
            volumes, form_lo=low1.index, form_hi=(breakout_idx or low3.index) + 1,
            breakout_idx=breakout_idx,
            low_pivot_idxs=[low1.index, low2.index, low3.index],
            profile=profile)

        # --- 패턴 일치 = 모양 AND 거래량 (대표님 요건) ---
        matched = bool(breakout_confirmed and vol_confirmed)
        # 최종 confidence: 모양×거래량 결합. 거래량 미확인 시 강한 감점.
        confidence = round(shape_score * (0.5 + 0.5 * vol_score), 3) if matched \
            else round(shape_score * 0.30, 3)

        height = resistance - min(lows)
        return Signal(
            pattern="triple_bottom",
            direction="up",                       # 삼중바닥 → 상승 반등
            confidence=confidence,
            current_wave="confirmed_breakout" if breakout_confirmed else "forming_no_breakout",
            detail={
                "matched": matched,               # ★ 모양+거래량 동시 충족 여부
                "shape_score": round(shape_score, 3),
                "volume_confirmed": vol_confirmed,
                "volume_score": vol_score,
                "volume_info": vol_info,
                "resistance": round(resistance, 2),
                "low_level": round(min(lows), 2),
                "level_spread_pct": round(level_spread * 100, 2),
                "measured_target": round(resistance + height, 2),  # 돌파목표
                "stop_suggestion": round(min(lows) * 0.99, 2),     # 손절 참고선
                "pivots": [(p.index, round(p.price, 2), p.kind) for p in w],
            },
        )

    return Signal("no_triple_bottom", "none", 0.0, "forming", {"pivots": len(pivots)})


# ======================================================================
if __name__ == "__main__":
    import math, random
    random.seed(3)

    def leg(a, b, n, vol):
        """가격 leg + 그 구간 거래량(vol 기준 ±10% 노이즈)"""
        ps = [a + (b - a) * (i / (n - 1)) for i in range(n)]
        vs = [vol * (1 + random.uniform(-0.1, 0.1)) for _ in range(n)]
        return ps, vs

    P, V = [], []
    for (a, b, n, vol) in [
        (115, 100, 20, 1000),   # 하락 → 저점1
        (100, 111, 15, 800),    # 반등1
        (111,  99, 15, 700),    # 하락 → 저점2
        ( 99, 112, 15, 600),    # 반등2
        (112, 100.5, 15, 500),  # 하락 → 저점3 (거래량 최소 = 소진)
        (100.5, 122, 18, 1800), # 저항(112) 상향 돌파 (거래량 급증)
    ]:
        ps, vs = leg(a, b, n, vol)
        P += ps; V += vs
    P = [round(p + 0.3 * math.sin(i / 2), 4) for i, p in enumerate(P)]
    ohlcv = [[i, p, p, p, p, round(v, 1)] for i, (p, v) in enumerate(zip(P, V))]

    sig = detect_triple_bottom(ohlcv)
    print("=== detect_triple_bottom() — 거래량 정상(돌파 급증) ===")
    print(f"pattern   : {sig.pattern} | dir {sig.direction} | conf {sig.confidence}")
    print(f"state     : {sig.current_wave}")
    for k, v in sig.detail.items():
        print(f"  {k:16}: {v}")

    # 대조군: 돌파 거래량을 형성구간 수준으로 낮춤 → 모양은 같지만 matched=False 여야 함
    ohlcv_weak = [row[:] for row in ohlcv]
    for i in range(80, len(ohlcv_weak)):       # 돌파 구간 거래량을 죽임
        ohlcv_weak[i][5] = 550.0
    sig2 = detect_triple_bottom(ohlcv_weak)
    print("\n=== 대조군 — 돌파 거래량 약함 ===")
    print(f"pattern   : {sig2.pattern} | conf {sig2.confidence}")
    print(f"  matched          : {sig2.detail['matched']}")
    print(f"  volume_confirmed : {sig2.detail['volume_confirmed']}")
    print(f"  volume_info      : {sig2.detail['volume_info']}")


# ======================================================================
# 하강형(descending) 삼중바닥 — a > c > e, e가 최저
# 수평형(triple_bottom)과 배타적: 수평은 저점 spread ≤ 3%, 하강은 총하락 > 3%
# ======================================================================
def detect_triple_bottom_descending(ohlcv, zigzag_threshold=0.04,
                                    step_min=0.008, step_max=0.06,
                                    total_min=0.03, total_max=0.12,
                                    profile: VolumeProfile = None,
                                    decel_ratio=None,
                                    breakout_mult=1.5) -> Signal:
    """
    하강 채널형 삼중바닥: 저점이 a>c>e로 계단식 하강(e 최저)한 뒤 저항 돌파.
    저점 하락폭이 수평형 허용오차(3%)를 넘으므로 triple_bottom 과 절대 안 겹친다.
    """
    if not ohlcv or not isinstance(ohlcv[0], (list, tuple)) or len(ohlcv[0]) < 6:
        return Signal("error", "none", 0.0, None, {"reason": "OHLCV(volume) 필요"})
    if profile is None:
        profile = VolumeProfile(breakout_mult=breakout_mult)
    else:
        # 호출자가 profile을 직접 넘긴 경우 breakout_mult로 덮어쓴다
        profile = VolumeProfile(breakout_mult=breakout_mult,
                                expect_decline=profile.expect_decline)

    closes  = [c[4] for c in ohlcv]
    volumes = [c[5] for c in ohlcv]
    pivots = zigzag(closes, zigzag_threshold)
    if len(pivots) < 5:
        return Signal("none", "none", 0.0, "forming", {"pivots": len(pivots)})

    for s in range(len(pivots) - 5, -1, -1):
        w = pivots[s:s + 5]
        if [x.kind for x in w] != ["L", "H", "L", "H", "L"]:
            continue
        a_p, h1, c_p, h2, e_p = w
        a, c, e = a_p.price, c_p.price, e_p.price

        # --- 하강형 핵심 조건 ---
        monotonic = a > c > e                       # 계단식 하강, e가 최저
        if not monotonic:
            continue
        step1 = (a - c) / a
        step2 = (c - e) / c
        total = (a - e) / a
        steps_ok = (step_min <= step1 <= step_max) and (step_min <= step2 <= step_max)
        total_ok = total_min < total <= total_max    # >3% : 수평형과 배타
        if not (steps_ok and total_ok):
            continue

        # 감속 조건: 2차낙폭/1차낙폭 <= decel_ratio (None이면 조건 끔)
        decel_ratio_actual = step2 / step1 if step1 > 0 else float("inf")
        if decel_ratio is not None and decel_ratio_actual > decel_ratio:
            continue

        resistance = max(h1.price, h2.price)
        breakout_idx = None
        for i in range(e_p.index + 1, len(closes)):
            if closes[i] > resistance:
                breakout_idx = i
                break
        broke = breakout_idx is not None

        # 모양 점수
        shape = 0.45
        if 0.01 <= step1 <= 0.04 and 0.01 <= step2 <= 0.04:  shape += 0.15  # 완만·균등한 계단
        if broke:                                            shape += 0.25
        if abs(h1.price - h2.price) / (_avg([h1.price, h2.price]) or 1) <= 0.03:
            shape += 0.15                                                   # 수평 저항(넥라인)
        shape = min(shape, 1.0)

        # 거래량 확인
        vconf, vscore, vinfo = confirm_volume(
            volumes, form_lo=a_p.index, form_hi=(breakout_idx or e_p.index) + 1,
            breakout_idx=breakout_idx,
            low_pivot_idxs=[a_p.index, c_p.index, e_p.index], profile=profile)

        matched = bool(broke and vconf)
        confidence = round(shape * (0.5 + 0.5 * vscore), 3) if matched else round(shape * 0.3, 3)

        height = resistance - e
        return Signal(
            pattern="triple_bottom_descending",
            direction="up",
            confidence=confidence,
            current_wave="confirmed_breakout" if broke else "forming_no_breakout",
            detail=dict(matched=matched, shape_score=round(shape, 3),
                        volume_confirmed=vconf, volume_score=vscore, volume_info=vinfo,
                        lows=[round(a, 2), round(c, 2), round(e, 2)],
                        step1_pct=round(step1 * 100, 2), step2_pct=round(step2 * 100, 2),
                        total_drop_pct=round(total * 100, 2),
                        decel_ratio_actual=round(decel_ratio_actual, 4),
                        resistance=round(resistance, 2),
                        measured_target=round(resistance + height, 2),
                        stop_suggestion=round(e * 0.99, 2),
                        pivots=[(p.index, round(p.price, 2), p.kind) for p in w]))
    return Signal("none", "none", 0.0, "forming", {"pivots": len(pivots)})
