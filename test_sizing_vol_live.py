"""
변동성 타겟팅의 **실거래 반영분** 검증 (합성 데이터, 네트워크 없음).

채택(2026-09-04) 후 실주문 크기가 σ 에 따라 달라진다. 여기서 고정하는 성질:
  - 연구(sizing_vol)와 실거래(sizing)가 **같은 함수**를 쓴다 — 구현이 갈라지지 않는다
  - vol_scale 이 위험액·명목가를 정확히 그 배율만큼 바꾼다(손절가·레버리지는 불변)
  - 스케일 1.0 이면 채택 전과 **완전히 동일한 주문**이 나온다
  - 폴백 3종(타겟팅 off / 상수 미설정 / σ 산출 불가)에서 1.0
  - realized_vol 의 인과성 — 진입 봉 **이후**를 바꿔도 값이 불변
  - min_equity_for 가 '이 스케일에서 주문이 나가는 최소 equity' 를 정확히 준다
    (변동성 타겟팅이 고변동 신호를 계좌 크기 때문에 통째로 스킵시키는 지점)
실행: python test_sizing_vol_live.py
"""
import math
import random
import sys
from datetime import date, timedelta

import sizing as sz
import sizing_vol as sv

fails = []


def check(n, c, d=""):
    print(("PASS " if c else "FAIL ") + n + ("" if c else f" — {d}"))
    c or fails.append(n)


def rows_of(n, seed, vol=0.02):
    random.seed(seed)
    px, out = 100.0, []
    for i in range(n):
        nx = px * (1 + random.gauss(0, vol))
        d = date(2024, 1, 1) + timedelta(days=i)
        out.append(dict(date=d.isoformat(), o=px, h=max(px, nx), l=min(px, nx), c=nx, v=1000.0))
        px = nx
    return out


# ── 1. 연구와 실거래가 같은 구현 ───────────────────────────────────────────
check("sizing_vol.realized_vol 이 sizing.realized_vol 그 자체", sv.realized_vol is sz.realized_vol)
check("sizing_vol.scale_of 가 sizing.vol_scale_raw 그 자체", sv.scale_of is sz.vol_scale_raw)
check("파라미터도 sizing 이 원본",
      (sv.TARGET_VOL, sv.LO, sv.HI, sv.VOL_LB)
      == (sz.VOL_TARGET_VOL, sz.VOL_LO, sz.VOL_HI, sz.VOL_LB))

# ── 2. realized_vol 의 인과성·경계 ─────────────────────────────────────────
r = rows_of(80, 7, vol=0.03)
v0 = sz.realized_vol(r, 50)
r2 = [dict(x) for x in r]
for j in range(51, 80):
    r2[j]["c"] *= 3.0                      # 진입 이후만 바꾼다
check("realized_vol: 진입 이후 봉을 바꿔도 불변", sz.realized_vol(r2, 50) == v0)
check("realized_vol: 표본 부족이면 None", sz.realized_vol(r, sz.VOL_LB - 1) is None)
flat = [dict(date="2024-01-01", o=1, h=1, l=1, c=1.0, v=1) for _ in range(60)]
check("realized_vol: 변동 0 이면 None", sz.realized_vol(flat, 50) is None)
check("realized_vol: TF 별 연율화가 다르다",
      sz.realized_vol(r, 50, tf="1h") > sz.realized_vol(r, 50, tf="1d") > sz.realized_vol(r, 50, tf="1w"))

# ── 3. scale 클리핑 ────────────────────────────────────────────────────────
check("vol_scale_raw: σ=TARGET 이면 1.0", abs(sz.vol_scale_raw(sz.VOL_TARGET_VOL) - 1.0) < 1e-12)
check("vol_scale_raw: 초고변동은 하한", sz.vol_scale_raw(99.0) == sz.VOL_LO)
check("vol_scale_raw: 초저변동은 상한", sz.vol_scale_raw(0.001) == sz.VOL_HI)
check("vol_scale_raw: σ 없으면 중립 1.0", sz.vol_scale_raw(None) == 1.0 and sz.vol_scale_raw(0) == 1.0)

# ── 4. vol_scale 폴백 3종 ──────────────────────────────────────────────────
orig_on, orig_norm = sz.VOL_TARGETING, sz.VOL_S_NORM
try:
    sz.VOL_TARGETING, sz.VOL_S_NORM = False, 1.15
    check("폴백: 타겟팅 off 면 1.0", sz.vol_scale(r, 50) == 1.0)
    sz.VOL_TARGETING, sz.VOL_S_NORM = True, None
    check("폴백: 정규화 상수 미설정이면 1.0 (채택 전 동작)", sz.vol_scale(r, 50) == 1.0)
    sz.VOL_TARGETING, sz.VOL_S_NORM = True, 1.15
    check("폴백: σ 산출 불가(봉 부족)면 1.0", sz.vol_scale(r, 5) == 1.0)
    got = sz.vol_scale(r, 50)
    check("정상: s_raw / S_NORM 과 일치",
          abs(got - sz.vol_scale_raw(v0) / 1.15) < 1e-12, str(got))
finally:
    sz.VOL_TARGETING, sz.VOL_S_NORM = orig_on, orig_norm

# ── 5. risk_based_size 에서의 vol_scale ────────────────────────────────────
EQ, FREE, STOP = 1000.0, 500.0, 0.08
base = sz.risk_based_size(EQ, FREE, STOP)
half = sz.risk_based_size(EQ, FREE, STOP, vol_scale=0.5)
dbl = sz.risk_based_size(EQ, FREE, STOP, vol_scale=2.0)
check("vol_scale=1.0 은 인자 미지정과 완전히 동일",
      sz.risk_based_size(EQ, FREE, STOP, vol_scale=1.0) == base)
check("vol_scale 이 명목가를 정확히 배율만큼 바꾼다",
      abs(half["notional"] - base["notional"] * 0.5) < 0.01
      and abs(dbl["notional"] - base["notional"] * 2.0) < 0.01,
      f"{base['notional']} / {half['notional']} / {dbl['notional']}")
check("위험액도 같은 배율", abs(half["risk_usd"] - base["risk_usd"] * 0.5) < 0.01)
check("레버리지는 vol_scale 과 무관 (청산 안전은 손절폭만의 함수)",
      base["leverage"] == half["leverage"] == dbl["leverage"])
check("stop_pct 는 불변 — 손절가를 건드리지 않는다",
      base["stop_pct"] == half["stop_pct"] == STOP)
check("반환에 vol_scale 이 기록된다", half["vol_scale"] == 0.5 and base["vol_scale"] == 1.0)
check("vol_scale<=0 은 진입 없음(None)", sz.risk_based_size(EQ, FREE, STOP, vol_scale=0.0) is None)
check("risk_frac 스케일과 vol_scale 은 수식상 동치 (연구 프레임과의 정합)",
      sz.risk_based_size(EQ, FREE, STOP, risk_frac=sz.RISK_FRAC * 0.7)["notional"]
      == sz.risk_based_size(EQ, FREE, STOP, vol_scale=0.7)["notional"])

# ── 6. 최소 증거금 문턱 — 계좌가 작으면 고변동 신호가 통째로 스킵된다 ──────
for vs in (0.5, 0.8, 1.0, 1.5):
    need = sz.min_equity_for(vs, STOP)
    just_below = sz.risk_based_size(need * 0.99, 1e9, STOP, vol_scale=vs)
    just_above = sz.risk_based_size(need * 1.01, 1e9, STOP, vol_scale=vs)
    check(f"min_equity_for({vs}) = ${need:.0f} 가 실제 문턱과 일치",
          just_below is None and just_above is not None,
          f"below={just_below} above={just_above}")
check("스케일이 작을수록 문턱이 높다 (= 고변동 신호가 먼저 잘린다)",
      sz.min_equity_for(0.5) > sz.min_equity_for(1.0) > sz.min_equity_for(2.0))

# ── 7. 검증 프레임과 실거래가 같은 수치를 낸다 ─────────────────────────────
# sizing_vol.simulate 는 risk_frac 을 s 로 스케일한다. 실거래는 vol_scale 인자를 쓴다.
# 두 경로가 같은 진입에서 같은 명목가를 내는지 — 갈라지면 검증치가 무의미해진다.
for seed, vol in ((1, 0.01), (2, 0.03), (3, 0.09)):
    rr = rows_of(80, seed, vol=vol)
    v = sz.realized_vol(rr, 60)
    s_raw = sz.vol_scale_raw(v)
    research = sz.risk_based_size(EQ, FREE, STOP, risk_frac=sz.RISK_FRAC * s_raw)
    live = sz.risk_based_size(EQ, FREE, STOP, vol_scale=s_raw)
    check(f"연구/실거래 명목가 일치 (σ={v*100:.0f}%/yr, s={s_raw:.2f})",
          research["notional"] == live["notional"] and research["margin_usd"] == live["margin_usd"])

# ── 8. 방향 — 고변동일수록 작게 ────────────────────────────────────────────
calm = sz.vol_scale_raw(sz.realized_vol(rows_of(80, 11, vol=0.005), 60))
wild = sz.vol_scale_raw(sz.realized_vol(rows_of(80, 11, vol=0.06), 60))
check("고변동 신호가 저변동 신호보다 작게 들어간다", wild < calm, f"{wild} vs {calm}")
check("명목가 x σ 가 클립 구간 안에서 일정 (변동성 기여 균등화)",
      abs(sz.vol_scale_raw(0.6) * 0.6 - sz.vol_scale_raw(1.2) * 1.2) < 1e-12)


# ── 9. 채택 상태 고정 (2026-09-04 사용자 채택) ─────────────────────────────
# 이 절이 깨지면 '채택했다고 기록해 뒀는데 실제로는 안 걸려 있다'는 뜻이다.
check("변동성 타겟팅이 켜져 있다", sz.VOL_TARGETING is True)
check("정규화 상수가 설정돼 있다 (라우팅 표본 s_norm)",
      sz.VOL_S_NORM is not None and abs(sz.VOL_S_NORM - 1.1094) < 1e-9, str(sz.VOL_S_NORM))
check("실제 배율 범위가 클립/정규화에서 유도한 값과 일치",
      abs(sz.VOL_LO / sz.VOL_S_NORM - 0.4507) < 5e-4
      and abs(sz.VOL_HI / sz.VOL_S_NORM - 1.8028) < 5e-4)
check("동결 파라미터 (튜닝 금지 — 바꾸면 재검증 대상)",
      (sz.VOL_TARGET_VOL, sz.VOL_LB, sz.VOL_LO, sz.VOL_HI) == (0.80, 20, 0.5, 2.0))
# 현 계좌 규모($276 대)에서 실제로 잘리는 구간 — 숨기지 않고 수치로 고정한다.
vs_min_276 = sz.MIN_MARGIN * sz.liq_safe_leverage(0.08) * 0.08 / (sz.RISK_FRAC * 276)
check("equity $276 에서 고변동 신호가 실제로 스킵된다 (문턱 σ ≈ 124%/yr)",
      0.57 < vs_min_276 < 0.59
      and sz.risk_based_size(276, 276, 0.08, vol_scale=sz.VOL_LO / sz.VOL_S_NORM) is None,
      f"vs_min={vs_min_276:.3f}")
check("같은 계좌에서 중간 변동성(스케일 1.0) 신호는 정상 진입",
      sz.risk_based_size(276, 276, 0.08, vol_scale=1.0) is not None)

print("\n" + ("ALL PASS" if not fails else f"FAILS: {fails}"))
sys.exit(1 if fails else 0)
