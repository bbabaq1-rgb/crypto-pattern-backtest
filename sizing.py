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
  risk_usd  = equity x RISK_FRAC x grade_mult x regime_mult
  notional  = risk_usd / stop_pct            ← 손절에 걸리면 정확히 risk_usd 를 잃는다
  notional  = min(notional, equity x MAX_POS_NOTIONAL_FRAC,
                            equity x MAX_TOTAL_NOTIONAL_FRAC - open_notional)
  leverage  = min(LEV_CAP, floor(1 / (LIQ_SAFETY x stop_pct + MMR)))
              ← 청산 거리(≈1/L - MMR)가 손절 거리의 LIQ_SAFETY 배 이상
  margin    = notional / leverage  (free x 0.95 이하, MIN_MARGIN 미만이면 스킵)

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
RISK_FRAC               = 0.01   # 건당 감수 위험 = equity 의 1% (사용자 채택 ③, 문턱 $160)
LEV_CAP                 = 2      # 레버리지 상한 (연구: 올려도 이득 없음, MDD 만 악화)
LIQ_SAFETY              = 2.0    # 청산 거리 >= 손절 거리 x 2
MMR                     = 0.01   # 유지증거금률 근사 (OKX 소형 알트 tier1 ~0.5~1.5%)
MAX_POS_NOTIONAL_FRAC   = 0.60   # 포지션 하나 명목가 <= equity x 60%
MAX_TOTAL_NOTIONAL_FRAC = 2.50   # 전 포지션 명목가 합 <= equity x 250%
MIN_MARGIN              = 10.0   # OKX 최소 주문 여유 (paper_executor.LIVE_MIN_USD 와 동일)
FREE_USE_MAX            = 0.95   # 가용잔고의 95% 까지만 증거금으로

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


def risk_based_size(equity, free, stop_pct, *, grade_mult=1.0, regime_mult=1.0,
                    open_notional=0.0, risk_frac=RISK_FRAC, lev_cap=LEV_CAP,
                    max_pos_frac=MAX_POS_NOTIONAL_FRAC,
                    max_total_frac=MAX_TOTAL_NOTIONAL_FRAC, min_margin=MIN_MARGIN):
    """
    반환 dict(margin_usd, leverage, notional, risk_usd, stop_pct, capped_by) 또는 None(스킵).
    capped_by: 어떤 제약이 크기를 결정했는지 — 'risk'(위험 기준 그대로) / 'pos_cap' /
               'total_cap' / 'free'.
    """
    if equity <= 0 or stop_pct <= 0:
        return None
    risk_usd = equity * risk_frac * grade_mult * regime_mult
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
                risk_usd=round(notional * stop_pct, 2), stop_pct=stop_pct, capped_by=capped_by)


def legacy_size(free, live_filled_count, regime_mult=1.0, first=LEGACY_FIRST_USD,
                pct=LEGACY_BAL_PCT, min_margin=MIN_MARGIN):
    """현행 규칙 재현: 첫 주문 $20 고정, 이후 free x 20%, complacent 롱 x0.6. 미만이면 None."""
    m = first if live_filled_count == 0 else free * pct
    m = round(m * regime_mult, 2)
    if m < min_margin:
        return None
    return dict(margin_usd=m, leverage=LEGACY_LEVERAGE, notional=round(m * LEGACY_LEVERAGE, 2),
                risk_usd=None, stop_pct=None, capped_by="legacy")
