"""sizing.py 검증 (네트워크 없음). 실행: python test_sizing.py"""
import sys
import sizing as sz

fails = []
def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f" — {detail}"))
    if not cond: fails.append(name)

# ── 레버리지: 청산이 손절보다 먼저 오면 안 된다 ─────────────────────────────
for stop in (0.08, 0.05, 0.02, 0.012):
    L = sz.liq_safe_leverage(stop, cap=50)
    liq_dist = 1.0 / L - sz.MMR
    check(f"stop {stop:.3f}: L={L} 청산거리 {liq_dist:.3f} >= {sz.LIQ_SAFETY}x손절",
          liq_dist >= sz.LIQ_SAFETY * stop - 1e-12)
    check(f"stop {stop:.3f}: L+1 이면 조건 깨짐(최대값임)",
          L >= 50 or (1.0 / (L + 1) - sz.MMR) < sz.LIQ_SAFETY * stop)
check("8% 손절의 청산-안전 레버리지는 5", sz.liq_safe_leverage(0.08, cap=50) == 5)
check("LEV_CAP 이 청산-안전값보다 작으면 CAP 이 이긴다", sz.liq_safe_leverage(0.012, cap=3) == 3)
check("레버리지는 정수", isinstance(sz.liq_safe_leverage(0.08), int))
check("손절 0 이면 1x", sz.liq_safe_leverage(0.0) == 1)

# ── 위험 기준 사이징 ────────────────────────────────────────────────────────
r = sz.risk_based_size(equity=1000, free=1000, stop_pct=0.08, risk_frac=0.02, lev_cap=3)
check("notional = risk/stop", abs(r["notional"] - 1000*0.02/0.08) < 1e-6, r)
check("손절 시 손실 = 정확히 risk_usd", abs(r["risk_usd"] - 20.0) < 1e-6, r)
check("margin = notional / lev", abs(r["margin_usd"] - r["notional"]/r["leverage"]) < 0.01, r)
check("위험 기준이 결정(capped_by=risk)", r["capped_by"] == "risk", r)

# free 는 상한일 뿐 — free 가 달라도 equity 가 같으면 크기 동일 (진입 순서 의존성 제거)
a = sz.risk_based_size(equity=1000, free=900, stop_pct=0.08)
b = sz.risk_based_size(equity=1000, free=300, stop_pct=0.08)
check("free 가 충분하면 free 와 무관하게 같은 크기", a["notional"] == b["notional"], (a, b))

# 등급/레짐 배수가 실거래 크기에 반영된다 (기존엔 페이퍼에만 곱해짐)
c = sz.risk_based_size(equity=1000, free=1000, stop_pct=0.08, grade_mult=0.7, risk_frac=0.02, lev_cap=3)
check("등급 배수 0.7 반영", abs(c["notional"] - r["notional"]*0.7) < 1e-6, (c, r))
d = sz.risk_based_size(equity=1000, free=1000, stop_pct=0.08, regime_mult=0.6, risk_frac=0.02, lev_cap=3)
check("레짐 배수 0.6 반영", abs(d["notional"] - r["notional"]*0.6) < 1e-6)

# 캡들
e = sz.risk_based_size(equity=1000, free=1000, stop_pct=0.01, risk_frac=0.02, lev_cap=3)
check("좁은 손절(1%)은 포지션 캡에 걸림", e["capped_by"] == "pos_cap"
      and abs(e["notional"] - 1000*sz.MAX_POS_NOTIONAL_FRAC) < 1e-6, e)
f = sz.risk_based_size(equity=1000, free=1000, stop_pct=0.08, open_notional=2400, risk_frac=0.02, lev_cap=3)
check("총 노출 캡: 남은 여유만", f["capped_by"] == "total_cap"
      and abs(f["notional"] - (1000*sz.MAX_TOTAL_NOTIONAL_FRAC - 2400)) < 1e-6, f)
g = sz.risk_based_size(equity=1000, free=1000, stop_pct=0.08, open_notional=2500)
check("총 노출 다 찼으면 스킵", g is None)
h = sz.risk_based_size(equity=1000, free=30, stop_pct=0.08)
check("free 부족 시 free x0.95 로 축소", h["capped_by"] == "free"
      and abs(h["margin_usd"] - 30*sz.FREE_USE_MAX) < 0.01, h)
i = sz.risk_based_size(equity=1000, free=5, stop_pct=0.08)
check("최소 증거금 미만이면 스킵", i is None)
check("equity 0 이면 스킵", sz.risk_based_size(0, 100, 0.08) is None)

# 결정론
check("같은 입력 → 같은 출력", sz.risk_based_size(271.31, 73.63, 0.08) == sz.risk_based_size(271.31, 73.63, 0.08))

# ── 현행 규칙 재현 (실거래 로그와 대조) ─────────────────────────────────────
check("legacy: 8/31 16:10 POL  free 479.79 → $95.96", sz.legacy_size(479.79, 5)["margin_usd"] == 95.96)
check("legacy: 8/31 20:09 ARB  free 384.14 → $76.83", sz.legacy_size(384.14, 5)["margin_usd"] == 76.83)
check("legacy: 9/1  09:08 ADA  free 157.23 → $31.45", sz.legacy_size(157.23, 5)["margin_usd"] == 31.45)
check("legacy: 첫 주문 $20 고정", sz.legacy_size(500, 0)["margin_usd"] == 20.0)
check("legacy: $10 미만 스킵", sz.legacy_size(40, 5) is None)

# ── 현재 계좌에 대입 (equity 285.34 / free 73.63) ───────────────────────────
# 채택값 1% 의 존재 이유가 여기다: 권고값 0.5% 는 이 계좌에서 주문이 아예 안 나갔다.
now = sz.risk_based_size(285.34, 73.63, 0.08)
leg = sz.legacy_size(73.63, 5)
print(f"\n[참고] 현 계좌 8% 손절 신호: risk-based {now} | legacy {leg}")
thr = sz.MIN_MARGIN * sz.LEV_CAP * 0.08 / sz.RISK_FRAC
print(f"[참고] risk-based 최소 주문 가능 equity(8% 손절, B등급) = ${thr:.0f}")
check("채택값(1%/2x)에서 현 계좌는 주문 가능 — 0.5% 를 못 쓴 이유", now is not None, now)

# 낙폭 축소의 실체는 '항상 더 작다'가 아니라 **진입 순서 의존성이 사라진다**는 것.
# legacy 는 free x20% 라 첫 진입이 크고 뒤로 갈수록 잘게 쪼개진다(실측 $95.96 → $76.83 →
# $31.45). risk 는 equity 기준이라 같은 equity·같은 손절거리면 몇 번째 진입이든 같다.
# MDD 를 만드는 건 '큰 첫 진입들이 동시에 물리는 것'이므로, 잘리는 쪽은 초기 대형 진입이다.
eq_early = 502.0     # POL 진입 당시 equity
r_early = sz.risk_based_size(eq_early, 479.79, 0.08)
l_early = sz.legacy_size(479.79, 5)
check("초기 대형 진입은 risk 가 legacy 를 크게 깎는다",
      r_early and l_early and r_early["margin_usd"] < l_early["margin_usd"] * 0.5,
      (r_early, l_early))
check("risk 는 진입 순서와 무관 — free 만 달라도 같은 크기",
      sz.risk_based_size(285.34, 200.0, 0.08)["margin_usd"] == now["margin_usd"])
check("legacy 는 진입 순서에 따라 크기가 요동",
      sz.legacy_size(479.79, 5)["margin_usd"] > sz.legacy_size(157.23, 5)["margin_usd"] * 3)
check("문턱은 $160 — 현 계좌보다 낮아야 작동", abs(thr - 160.0) < 1e-9, thr)
check("문턱 바로 위 equity 에서는 주문 가능",
      sz.risk_based_size(thr * 1.01, thr, 0.08) is not None)
check("문턱 바로 아래 equity 에서는 스킵",
      sz.risk_based_size(thr * 0.99, thr, 0.08) is None)
check("채택 기본값 고정: RISK_FRAC 1% (사용자 결정 ③)", sz.RISK_FRAC == 0.01)
check("채택 기본값 고정: LEV_CAP 2", sz.LEV_CAP == 2)


# ── 엔진 연결 (소스 단언) ────────────────────────────────────────────────────
pe = open("paper_executor.py", encoding="utf-8").read()
ex = open("exchange.py", encoding="utf-8").read()
check("SIZING_MODE 는 risk (2026-09-02 사용자 결정 ③ — 실거래 반영됨)",
      'SIZING_MODE = "risk"' in pe)
check("risk 모드는 sizing.risk_based_size 를 호출", "sizing.risk_based_size(" in pe)
check("legacy 모드는 sizing.legacy_size 로 종전 규칙 재현", "sizing.legacy_size(" in pe)
check("위험 기준은 equity(free 아님)", "eq_now, usdt_free, stop_pct" in pe)
check("손절 거리는 실제 손절가로 계산(ATR 패턴도 동일 식)", "abs(entry - stop_px) / entry" in pe)
check("등급 배수가 실주문 사이징에 전달", "grade_mult=grade_mult" in pe)
check("총 노출 캡용 open_notional 전달", "open_notional=open_notional" in pe)
check("레버리지는 risk 모드에서만 주문에 전달(legacy 스텁 호환)", '**({"leverage": live_lev} if live_lev else {})' in pe)
check("페이퍼 사이징 로그가 실주문과 구분됨", "[사이징·페이퍼]" in pe)
check("place_swap_entry 가 leverage 인자를 받음", "target_px=None, leverage=None" in ex)
check("set_leverage 가 주문별 lev 사용", "ex.set_leverage(lev, ccxt_sym," in ex)
check("명목가 계산이 주문별 lev 사용", "notional  = eff_size * lev" in ex)
check("결과 dict 가 실제 lev 기록", '"leverage":       lev,' in ex)
check("leverage 미지정 시 OKX_LEVERAGE 폴백", "int(leverage or OKX_LEVERAGE)" in ex)

print("\n실패", len(fails), "건" if fails else "— 전체 통과")
sys.exit(1 if fails else 0)
