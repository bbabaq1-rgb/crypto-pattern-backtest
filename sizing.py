"""
sizing.py — 실거래 포지션 사이징·레버리지 (결정론적, 계산 가능).

왜 새로 만드는가 (2026-09-02)
----------------------------
현행 규칙은 '가용잔고(free) x 20%, 레버리지 2x 고정'이다. 두 가지 문제가 있다.
  1) free 는 포지션을 열수록 줄어 **진입 순서**가 크기를 정한다 — 같은 날 첫 신호가
     세 번째 신호의 3배를 받는다. 신호 품질(등급·확증)은 실주문에 반영되지 않았다
     (GRADE_SIZE_MULT 는 페이퍼 기록에만 곱해졌다).
  2) 레버리지를 올린다고 '최적 포지션'이 커지지 않는다. 포지션 크기는 **감수할 위험**
     (risk_frac)이 정하고, 레버리지는 같은 명목가를 여는 데 필요한 증거금을 줄일 뿐이다
     (= 더 많은 포지션을 동시에 들 수 있게 함). 레버리지의 유일한 진짜 제약은
     **청산가가 손절가보다 먼저 오면 안 된다**는 것이다.

규칙 (risk-based)
-----------------
  risk_usd  = equity x RISK_FRAC x grade_mult x regime_mult x vol_scale
  notional  = risk_usd / stop_pct            ← 손절에 걸리면 정확히 risk_usd 를 잃는다
  notional  = min(notional, equity x MAX_POS_NOTIONAL_FRAC,
                            equity x MAX_TOTAL_NOTIONAL_FRAC - open_notional)
  leverage  = min(LEV_CAP, floor(1 / (LIQ_SAFETY x stop_pct + MMR)))
              ← 청산 거리(≈1/L - MMR)가 손절 거리의 LIQ_SAFETY 배 이상
  margin    = notional / leverage  (free x 0.95 이하, MIN_MARGIN 미만이면 스킵)

변동성 타겟팅 (2026-09-04 채택)
------------------------------
`vol_scale` 이 그 층이다. 손절폭이 8% 로 고정이라 명목가가 자산 변동성과 무관했다 —
연율 40% 코인과 140% 밈코인이 같은 크기로 들어갔다. 진입 시점 20봉 실현변동성 σ 로

    s_raw = clip(VOL_TARGET_VOL / σ, VOL_LO, VOL_HI)
    vol_scale = s_raw / VOL_S_NORM

를 곱한다. VOL_S_NORM 은 s_raw 의 평균으로, **평균 노출을 채택 전과 같게** 맞추는 상수다
(sizing_vol.py 의 vol_matched arm 이 쓰는 인과적 확장평균의 수렴값). 이게 없으면 개선분이
'재분배'가 아니라 '레버리지를 더 쓴 것'이 되어 검증 판정이 성립하지 않는다.

주의 — **건당 달러 위험은 더 이상 1% 고정이 아니다.** 손절폭이 8% 로 고정인 채 명목가만
움직이므로 risk_usd = equity x RISK_FRAC x vol_scale 이다(대략 0.4~1.7%). 일정하게 유지되는
것은 달러 위험이 아니라 **변동성 기여(명목가 x σ)** 이고, 검증에서 개선된 것도 그쪽이다.

숫자(RISK_FRAC/LEV_CAP 등)는 sizing_study.py 가 실제 신호 분포로 자산곡선을 돌려
정한다. 여기 기본값은 보수적 출발점이며, 연구 결과로 갱신한다.
"""
import math

# ── 파라미터 (sizing_study.py 결과로 갱신) ─────────────────────────────────
# sizing_study.py (2026-09-02, 7패턴 방식D 1,093건 · 블록부트스트랩 300회) 결과:
#   선택 기준 "boot MDD중앙 >= -35% AND P(ruin) < 5%" 를 만족하는 규칙은 risk 0.5% 뿐이었다.
#   legacy(free x20%, 2x) 는 boot MDD중앙 -59.9%(p10 -77%) 로 이미 기준 밖 — 현행이 '작다'가
#   아니라 '크다'. 레버리지는 같은 위험에서 2→3→5x 로 올려도 CAGR 이 오르지 않고(43→39→36%)
#   MDD 만 깊어졌다(-67→-76→-76%): 증거금 제약이 풀려 동시 노출이 커진 효과.
#   주의: equity 가 작으면 위험 기준 크기가 최소 증거금($10)에 못 미쳐 스킵된다.
#   문턱 = 10 x lev x stop / risk_frac. 0.5% 라면 $320(C등급 $457) 로 현 계좌($285)엔 작동 불가.
#
# 채택값 1% (2026-09-02, 사용자 결정 ③ '절충'):
#   권고값 0.5% 는 현 계좌 규모에서 주문 자체가 안 나가므로 실사용이 불가능했다. 1% 는
#   문턱이 $160 이라 지금 작동하고, legacy 대비 **수익은 사실상 같은데 낙폭만 줄인다**:
#     legacy   CAGR +39.3% / boot MDD중앙 -59.9% (p10 -77.1%)
#     risk 1%  CAGR +38.8% / boot MDD중앙 -43.1% (p10 -60.7%)
#   단 사전 기준(MDD중앙 >= -35%)은 여전히 미충족 — 기준을 만족하는 건 0.5% 뿐이다.
#   즉 1% 는 '기준 통과'가 아니라 '현 계좌에서 가능한 가장 큰 개선'이다. equity 가 $320 을
#   넘으면 0.5% 로 낮추는 것을 재검토할 것.
#
# 상향 1.5% (2026-09-04, 사용자 결정 — 계좌 $400+ 충전 후 "리스크 1.5% 로 올려줘"):
#   sizing_vol.py --routing --grid (991건, 변동성 타겟팅·유니버스 80·라우팅 복제) 결과를 보고
#   내린 결정이다. **사전 기준(boot MDD중앙 >= -35%)은 통과하지 않는다** — 통과 셀은 여전히
#   risk 0.5% 뿐이다. 그럼에도 이 값을 쓰는 근거는 격자가 보여준 성질에 있다:
#     boot Calmar 가 15셀 전체에서 0.99~1.14 로 **평평**하다. risk 를 0.5%->3% 로 6배 올려도
#     Calmar 는 안 움직이고 CAGR 과 MDD 가 같은 비율로 커진다. 즉 '최적 위험'이 존재하지 않고
#     한 직선 위에서 어느 점에 설지는 통계가 아니라 **감내할 낙폭**이 정한다.
#   1.5% 지점의 뜻(lev 2 기준): boot CAGR +63.0% / boot MDD중앙 -59.7% / **p10 -80.5%** /
#   Calmar 1.03 / P(ruin) 2.3%. 종전 1% 는 +49.1% / -45.4% / p10 -65.1% 였다.
#   **5번 중 1번은 -80% 낙폭을 본다**는 것을 받아들인 선택이다.
#   부수 효과 둘:
#     (a) 최소주문 문턱이 낮아진다 — 문턱 = 10 x lev x stop / (risk x vol_scale) 이므로
#         1%->1.5% 로 3분의 2가 된다(스케일 1.0 에서 $160 -> $107). 고변동 신호 스킵은 줄어든다.
#     (b) **증거금이 제약이 되기 시작한다** — equity $400 에서 포지션당 증거금 $37.5 라
#         MAX_POS 12 를 채우려면 $450 이 필요해 10개쯤에서 free 가 마른다. 격자에서도 risk
#         1.5%/lev2 는 증거금 스킵 109건이었고, lev 3 에서 15건으로 줄며 Calmar 1.03->1.13 이
#         된다. **risk 1% 에서는 무의미했던 레버리지 상향이 1.5% 부터는 의미가 생긴다** —
#         별도 사용자 결정 사항으로 남긴다(LEV_CAP 은 2 유지).
RISK_FRAC               = 0.015  # 건당 감수 위험 = equity 의 1.5% (사용자 결정 2026-09-04, 문턱 $107)
LEV_CAP                 = 2      # 레버리지 상한 (연구: 올려도 이득 없음, MDD 만 악화)
LIQ_SAFETY              = 2.0    # 청산 거리 >= 손절 거리 x 2
MMR                     = 0.01   # 유지증거금률 근사 (OKX 소형 알트 tier1 ~0.5~1.5%)
MAX_POS_NOTIONAL_FRAC   = 0.60   # 포지션 하나 명목가 <= equity x 60%
MAX_TOTAL_NOTIONAL_FRAC = 2.50   # 전 포지션 명목가 합 <= equity x 250%
MIN_MARGIN              = 10.0   # OKX 최소 주문 여유 (paper_executor.LIVE_MIN_USD 와 동일)
FREE_USE_MAX            = 0.95   # 가용잔고의 95% 까지만 증거금으로

# ── 변동성 타겟팅 파라미터 (sizing_vol.py 연구, 2026-09-04 사용자 채택) ───────────
# 사전 등록 4조건을 전 표본(6,640건)·실거래 라우팅 복제(991건) 두 판에서 모두 통과.
# 라우팅 복제 판: boot Calmar 0.65 -> 1.06 / boot MDD -51.8% -> -45.4% / 노출 0.96배.
# 값은 연구에서 **동결**된 것이고 여기서 튜닝하지 않는다 — 바꾸면 재검증 대상이다.
VOL_TARGETING  = True    # False 면 vol_scale 이 항상 1.0 = 채택 전 동작으로 되돌아간다
VOL_TARGET_VOL = 0.80    # 목표 연율 변동성 80%
VOL_LB         = 20      # 실현변동성 lookback(봉)
VOL_LO, VOL_HI = 0.5, 2.0
# 정규화 상수 = s_raw 의 평균. 연구의 vol_matched 는 '지금까지 본 s_raw 의 평균'(인과적
# 확장평균)으로 나눈다. 앞으로 나갈 거래는 그 확장평균이 이미 수렴한 지점에 있으므로
# 수렴값을 상수로 쓰는 것이 실거래에서의 충실한 구현이다(초기 구간의 과도기만 생략된다).
# sizing_vol.py --routing 이 출력하는 s_norm 으로 갱신한다.
VOL_S_NORM     = 1.1094  # sizing_vol.py --routing (2026-09-04, run 33849739625) 의 s_norm.
                         # 표본이 크게 달라지면(유니버스·라우팅 개편) 재산출 — sizing_vol 이
                         # 매 실행 이 값과 비교해 0.02 이상 벌어지면 경고를 찍는다.
VOL_BARS_PER_YEAR = {"1d": 365.0, "4h": 365.0 * 6, "1h": 365.0 * 24, "1w": 52.0}


def realized_vol(rows, si, lb=VOL_LB, tf="1d"):
    """진입 봉까지만 보고 계산한 연율 실현변동성. 표본 부족·0 이면 None(=스케일 1.0).

    **연구(sizing_vol)와 실거래가 같은 이 함수를 쓴다.** 구현을 이중화하면 검증한 규칙과
    주문이 조용히 갈라진다.
    """
    if si < lb:
        return None
    rets = []
    for j in range(si - lb + 1, si + 1):
        p0, p1 = rows[j - 1]["c"], rows[j]["c"]
        if p0 <= 0 or p1 <= 0:
            return None
        rets.append(math.log(p1 / p0))
    if len(rets) < 2:
        return None
    sd = _pstdev(rets)
    if sd <= 0:
        return None
    return sd * math.sqrt(VOL_BARS_PER_YEAR.get(tf, 365.0))


def _pstdev(xs):
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / len(xs))


def vol_scale_raw(vol):
    """s_raw = clip(TARGET/σ, LO, HI). σ 없으면 1.0(중립)."""
    if vol is None or vol <= 0:
        return 1.0
    return max(VOL_LO, min(VOL_HI, VOL_TARGET_VOL / vol))


def vol_scale(rows, si, tf="1d"):
    """실거래에 곱할 스케일. 타겟팅 off / σ 산출 불가 / 상수 미설정이면 1.0(현행 동작)."""
    if not VOL_TARGETING or not VOL_S_NORM:
        return 1.0
    v = realized_vol(rows, si, tf=tf)
    if v is None:
        return 1.0
    return vol_scale_raw(v) / VOL_S_NORM


def min_equity_for(vol_scale_=1.0, stop_pct=0.08, risk_frac=RISK_FRAC, lev_cap=LEV_CAP,
                   min_margin=MIN_MARGIN):
    """이 스케일에서 주문이 나가는 최소 equity. margin = eq x risk x s / stop / lev >= min_margin.

    변동성 타겟팅은 고변동 신호의 명목가를 줄이므로 **계좌가 작으면 그 신호가 통째로
    스킵된다.** 얼마나 작아야 그런지를 숨기지 않고 계산해 로그로 남기기 위한 함수다.
    """
    lev = liq_safe_leverage(stop_pct, cap=lev_cap)
    if vol_scale_ <= 0 or risk_frac <= 0:
        return float("inf")
    return min_margin * lev * stop_pct / (risk_frac * vol_scale_)


# 현행(legacy) 규칙 상수 — 동작 재현·비교용
LEGACY_FIRST_USD = 20.0
LEGACY_BAL_PCT   = 0.20
LEGACY_LEVERAGE  = 2


def liq_safe_leverage(stop_pct, safety=LIQ_SAFETY, mmr=MMR, cap=LEV_CAP):
    """
    청산가가 손절가보다 safety 배 멀리 있도록 하는 최대 정수 레버리지.
    격리마진 청산 거리 ≈ 1/L - mmr  →  1/L - mmr >= safety x stop  →  L <= 1/(safety x stop + mmr)
    """
    if stop_pct <= 0:
        return 1
    l = math.floor(1.0 / (safety * stop_pct + mmr))
    return max(1, min(cap, l))


# 2026-09-03: paper_executor 는 grade_mult 를 실주문에서 1.0 으로 넘긴다(등급은 페이퍼 전용).
# 이 함수의 인자는 연구·테스트 호환용으로 남긴다.
def risk_based_size(equity, free, stop_pct, *, grade_mult=1.0, regime_mult=1.0,
                    vol_scale=1.0, open_notional=0.0, risk_frac=RISK_FRAC, lev_cap=LEV_CAP,
                    max_pos_frac=MAX_POS_NOTIONAL_FRAC,
                    max_total_frac=MAX_TOTAL_NOTIONAL_FRAC, min_margin=MIN_MARGIN):
    """
    반환 dict(margin_usd, leverage, notional, risk_usd, vol_scale, stop_pct, capped_by)
    또는 None(스킵).
    capped_by: 어떤 제약이 크기를 결정했는지 — 'risk'(위험 기준 그대로) / 'pos_cap' /
               'total_cap' / 'free'.
    vol_scale: 변동성 타겟팅 배율(1.0 = 미적용). 위험액에 곱해져 명목가를 같은 비율로 바꾼다.
               연구(sizing_vol)는 risk_frac 을 직접 스케일했는데 수식상 동일하며, 인자를
               분리한 건 로그·기록에서 '어떤 배율이 걸렸는지'가 보이게 하기 위해서다.
    """
    if equity <= 0 or stop_pct <= 0 or vol_scale <= 0:
        return None
    risk_usd = equity * risk_frac * grade_mult * regime_mult * vol_scale
    notional = risk_usd / stop_pct
    capped_by = "risk"

    pos_cap = equity * max_pos_frac
    if notional > pos_cap:
        notional, capped_by = pos_cap, "pos_cap"
    total_room = equity * max_total_frac - max(0.0, open_notional)
    if notional > total_room:
        notional, capped_by = total_room, "total_cap"
    if notional <= 0:
        return None

    lev = liq_safe_leverage(stop_pct, cap=lev_cap)
    margin = notional / lev
    free_cap = max(0.0, free) * FREE_USE_MAX
    if margin > free_cap:
        margin, capped_by = free_cap, "free"
        notional = margin * lev
    if margin < min_margin:
        return None
    return dict(margin_usd=round(margin, 2), leverage=lev, notional=round(notional, 2),
                risk_usd=round(notional * stop_pct, 2), vol_scale=round(vol_scale, 4),
                stop_pct=stop_pct, capped_by=capped_by)


def legacy_size(free, live_filled_count, regime_mult=1.0, first=LEGACY_FIRST_USD,
                pct=LEGACY_BAL_PCT, min_margin=MIN_MARGIN):
    """현행 규칙 재현: 첫 주문 $20 고정, 이후 free x 20%, complacent 롱 x0.6. 미만이면 None."""
    m = first if live_filled_count == 0 else free * pct
    m = round(m * regime_mult, 2)
    if m < min_margin:
        return None
    return dict(margin_usd=m, leverage=LEGACY_LEVERAGE, notional=round(m * LEGACY_LEVERAGE, 2),
                risk_usd=None, stop_pct=None, capped_by="legacy")
