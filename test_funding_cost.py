"""
test_funding_cost.py — validate_funding_cost 로직 고정 (네트워크 없음)

이 시험의 결론은 '얼마를 떼는가'라는 **산술** 하나에 달려 있다. 그래서 고정하는 것도
산술이다 — 정산 구간 경계, 방향 부호, 커버리지 경계, 합치 게이트, 판정 세 조건.
실데이터 수치는 여기서 만들지 않는다(러너가 공식).
"""
from datetime import date

import validate_funding_cost as vf

ok = fail = 0


def chk(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
    else:
        fail += 1
        print(f"  FAIL {name} {extra}")


DAY = 86400000
ORD = date(1970, 1, 1).toordinal()

print("§1 시각 변환 — 봉 종가 시각")
# 1d: ordinal 정수는 그 날짜 00:00 UTC → 종가는 다음 날 00:00
d = date(2026, 1, 2)
chk("1d 종가 = 다음날 00:00", vf.close_ms(d.toordinal(), "1d")
    == (d.toordinal() - ORD) * DAY + DAY)
chk("1d 2026-01-02 종가 = 01-03 00:00", vf._ms_day(vf.close_ms(d.toordinal(), "1d")) == "2026-01-03")
# 4h: 분수 일수(봉 시작) → 종가는 +4h
t4 = (date(2026, 1, 2).toordinal() - ORD) + 8 / 24.0 + ORD      # 08:00 UTC 시작 봉
chk("4h 종가 = +4h", vf.close_ms(t4, "4h")
    == int(round((t4 - ORD) * DAY)) + 4 * 3600 * 1000)
chk("4h 08:00 봉 종가 = 12:00", vf._ms_day(vf.close_ms(t4, "4h")) == "2026-01-02")
chk("BAR_MS 4h", vf.BAR_MS["4h"] == 14400000 and vf.BAR_MS["1d"] == 86400000)

print("§2 charge — (t0, t1] 반개구간")
ts = [1000, 2000, 3000, 4000, 5000]
rates = [0.001, 0.002, -0.003, 0.004, 0.005]
curve = (ts, rates)
chk("진입 시각 정산은 제외(t0 배타)", abs(vf.charge(curve, 2000, 4000, 1) - (-0.003 + 0.004)) < 1e-12)
chk("청산 시각 정산은 포함(t1 포함)", abs(vf.charge(curve, 1500, 3000, 1) - (0.002 - 0.003)) < 1e-12)
chk("구간 밖이면 0", vf.charge(curve, 5001, 9000, 1) == 0)
chk("전 구간", abs(vf.charge(curve, 0, 9999, 1) - sum(rates)) < 1e-12)
chk("숏은 부호 반전", abs(vf.charge(curve, 0, 9999, -1) + sum(rates)) < 1e-12)
chk("빈 커브는 0", vf.charge(([], []), 0, 9999, 1) == 0)
# 롱이 양의 요율에서 '지불' 한다 = ret 에서 빼진다
chk("롱 양요율 → 비용 양수(차감)", vf.charge(([100], [0.0001]), 0, 200, 1) > 0)
chk("숏 양요율 → 비용 음수(수취)", vf.charge(([100], [0.0001]), 0, 200, -1) < 0)

print("§3 covered — 창 밖이면 추정치로 채우지 않는다")
chk("온전히 안", vf.covered(curve, 1500, 4500))
chk("진입이 창 앞", not vf.covered(curve, 500, 4500))
chk("청산이 창 뒤", not vf.covered(curve, 1500, 6000))
chk("경계 포함", vf.covered(curve, 1000, 5000))
chk("빈 커브", not vf.covered(([], []), 1, 2))

print("§4 합치 게이트")
a = {i: 0.0001 * (i % 7) for i in range(200)}
b = dict(a)
rho, mad, n = vf.agreement(a, b)
chk("동일 계열 ρ=1", abs(rho - 1.0) < 1e-9 and mad == 0.0 and n == 200)
chk("동일 계열은 게이트 통과", vf.agree_ok(rho, mad, n))
b2 = {k: v + 0.0002 for k, v in a.items()}          # 완전 상관이지만 차이가 크다
rho2, mad2, n2 = vf.agreement(a, b2)
chk("평행이동은 ρ=1", abs(rho2 - 1.0) < 1e-9)
chk("평균차 초과 → 미통과", not vf.agree_ok(rho2, mad2, n2), f"mad={mad2}")
b3 = {k: (0.00001 if k % 2 else -0.00001) for k in a}
rho3, mad3, n3 = vf.agreement(a, b3)
chk("무상관은 ρ 낮음 → 미통과", not vf.agree_ok(rho3, mad3, n3), f"rho={rho3}")
small = {i: 0.0001 * (i % 7) for i in range(10)}
r4, m4, n4 = vf.agreement(small, dict(small))
chk("겹침 부족 → 미통과", not vf.agree_ok(r4, m4, n4) and n4 == 10)
chk("겹침 <3 이면 rho None", vf.agreement({1: 0.1}, {1: 0.1})[0] is None)
chk("상수 계열은 rho None(0 나누기 방어)", vf.agreement({1: 0.1, 2: 0.1, 3: 0.1},
                                                       {1: 0.2, 2: 0.2, 3: 0.2})[0] is None)

print("§5 merge_curve — 겹치면 OKX 우선")
okx = {100: 0.001, 200: 0.002}
byb = {100: 0.009, 300: 0.003}
ts_m, rt_m = vf.merge_curve(okx, byb, True)
chk("확장 사용 시 합집합", ts_m == [100, 200, 300])
chk("겹치는 점은 OKX 값", rt_m[0] == 0.001)
ts_o, rt_o = vf.merge_curve(okx, byb, False)
chk("미사용이면 OKX 만", ts_o == [100, 200] and rt_o == [0.001, 0.002])

print("§6 방향 부호")
chk("engulfing 롱 +1", vf.sign_of("engulfing") == 1.0)
chk("engulfing_short −1", vf.sign_of("engulfing_short") == -1.0)
chk("fvg_short −1", vf.sign_of("fvg_short") == -1.0)
chk("4h 배포 4종 전부 롱", all(vf.sign_of(p) == 1.0 for p, _, _ in vf.ADOPTED_4H if True)
    if hasattr(vf, "ADOPTED_4H") else all(vf.sign_of(p) == 1.0 for p, _, _ in vf.vp.ADOPTED_4H))
chk("미지의 패턴은 롱 폴백", vf.sign_of("nonexistent") == 1.0)

print("§7 판정 — 세 조건이 각각 발화하는가")
PFG = dict(calmar=1.00)
PFN = dict(calmar=1.00)
base_cells = {"a": dict(n=10, gross=0.05, net=0.04)}
v, h = vf.verdict(dict(n=10, gross=0.05, fund=0.001), base_cells, PFG, PFN)
chk("아무것도 안 걸리면 IMMATERIAL", v == "IMMATERIAL" and not h)
v, h = vf.verdict(dict(n=10, gross=0.05, fund=0.010), base_cells, PFG, PFN)
chk("(i) 비용 20% 정확히 → MATERIAL", v == "MATERIAL" and h[0].startswith("(i)"))
v, h = vf.verdict(dict(n=10, gross=0.05, fund=0.0099), base_cells, PFG, PFN)
chk("(i) 문턱 미만은 통과", v == "IMMATERIAL")
v, h = vf.verdict(dict(n=10, gross=0.05, fund=0.001),
                  {"a": dict(n=10, gross=0.002, net=-0.001)}, PFG, PFN)
chk("(ii) 부호 역전 → MATERIAL", v == "MATERIAL" and "(ii)" in h[0])
v, h = vf.verdict(dict(n=10, gross=0.05, fund=0.001),
                  {"a": dict(n=10, gross=-0.01, net=-0.02)}, PFG, PFN)
chk("(ii) 원래 음수 셀은 역전 아님", v == "IMMATERIAL")
v, h = vf.verdict(dict(n=10, gross=0.05, fund=0.001), base_cells, dict(calmar=1.0), dict(calmar=0.90))
chk("(iii) Calmar 10% 하락 → MATERIAL", v == "MATERIAL" and "(iii)" in h[0])
v, h = vf.verdict(dict(n=10, gross=0.05, fund=0.001), base_cells, dict(calmar=1.0), dict(calmar=0.91))
chk("(iii) 9% 하락은 통과", v == "IMMATERIAL")
v, h = vf.verdict(dict(n=10, gross=0.05, fund=0.001), base_cells,
                  dict(calmar=float("inf")), dict(calmar=float("inf")))
chk("(iii) inf Calmar 는 판정 안 함", v == "IMMATERIAL")
v, h = vf.verdict(dict(n=0), {}, PFG, PFN)
chk("표본 0 이면 조건 (i) 미발화", v == "IMMATERIAL")

print("§8 동결 상수 / 배포 금지")
chk("DEPLOY_ON_PASS False", vf.DEPLOY_ON_PASS is False)
chk("합치 게이트 ρ 0.80", vf.AGREE_RHO == 0.80)
chk("합치 게이트 차 0.005%/8h", vf.AGREE_DIFF == 0.00005)
chk("합치 최소 겹침 100", vf.AGREE_MIN_N == 100)
chk("(i) 문턱 20%", vf.MAT_SHARE == 0.20)
chk("(iii) 문턱 10%", vf.MAT_CALMAR_DROP == 0.10)
chk("거래 집합은 validate_portfolio 정의 그대로",
    vf.vp.ADOPTED_4H == [("three_soldiers_4h", {"bull_btc", "bull_altseason"}, None),
                         ("triple_bottom_4h", None, "top30"),
                         ("equal_lows_4h", None, "top30"),
                         ("vol_awakening_4h", None, "top30")])

print(f"\n{'='*60}\n통과 {ok} / 실패 {fail}\n{'='*60}")
raise SystemExit(1 if fail else 0)
