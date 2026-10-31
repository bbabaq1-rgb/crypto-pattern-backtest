"""test_risk_grid.py — validate_risk_grid 로직 고정 (네트워크 없음)"""
import random
from datetime import date

import sizing as sz
import validate_gap as vg
import validate_portfolio as vp
import validate_risk_grid as rg

ok = fail = 0
def chk(n, c, x=""):
    global ok, fail
    if c: ok += 1
    else: fail += 1; print("  FAIL", n, x)

rng = random.Random(9)
trs = []
for i in range(220):
    d = float(date.fromordinal(739000 + rng.randrange(400)).toordinal())
    trs.append(dict(pattern=rng.choice(["engulfing", "fvg", "vol_awakening_4h"]), t_in=d, t_out=d + rng.randrange(1, 9),
                    ret=rng.uniform(-.1, .15), sym="S%d" % i, vol=rng.uniform(.4, 1.5), rank=rng.randrange(30),
                    tf="4h" if i % 3 == 0 else "1d"))
trs.sort(key=lambda t: t["t_in"])

print("§1 동결 파라미터·기준선 동치")
chk("현행 셀 = 실거래 상수", rg.CURRENT == (sz.RISK_FRAC, vp.MAX_POS), (rg.CURRENT, sz.RISK_FRAC, vp.MAX_POS))
chk("격자 6셀·현행 포함", len(rg.cells()) == 6 and rg.CURRENT in rg.cells())
chk("주 판정 셀은 MAX_POS 13 의 0.5·1.0%", set(rg.PRIMARY) == {(0.005, 13), (0.010, 13)})
a = rg.run_cell(trs, rg.CURRENT); b = vp.simulate(trs, "current")
chk("현행 셀은 vp.simulate(current) 와 동치", abs(a["final"] - b["final"]) < 1e-9 and a["taken"] == b["taken"], (a["final"], b["final"]))
chk("문턱 동결", rg.J4_WIN == 0.60 and rg.J3_TOL == 0.90 and rg.BOOT_N == 300 and rg.SEED == 73)
chk("DEPLOY_ON_PASS False", rg.DEPLOY_ON_PASS is False)

print("§2 노브 성질")
lo, hi = rg.run_cell(trs, (0.005, 13)), rg.run_cell(trs, (0.015, 13))
chk("위험을 낮추면 MDD 가 얕아지거나 같다", lo["mdd"] >= hi["mdd"] - 1e-12, (lo["mdd"], hi["mdd"]))
chk("슬롯 8 은 슬롯 13 보다 체결이 같거나 적다", rg.run_cell(trs, (0.015, 8))["taken"] <= hi["taken"])

print("§3 판정 규칙")
def R(cur, cell, c=1.0):
    return {rg.CURRENT: dict(calmar=cur), (0.005, 13): dict(calmar=cell), (0.010, 13): dict(calmar=c)}
full, train, hold = R(1.0, 2.0), R(1.0, 1.0), R(-0.5, -0.2)
v, d = rg.classify(full, train, hold, {(0.005, 13): .7, (0.010, 13): .5})
chk("전 기준 통과면 SUPPORTED", v == "SUPPORTED" and d[(0.005, 13)]["passed"])
v, d = rg.classify(full, R(1.0, 0.5), hold, {(0.005, 13): .7, (0.010, 13): .5})
chk("J3(train 이득 포기) 실패면 REJECTED", v == "REJECTED" and not d[(0.005, 13)]["J3"])
v, d = rg.classify(full, train, hold, {(0.005, 13): .59, (0.010, 13): .5})
chk("J4 0.59 는 실패", v == "REJECTED" and not d[(0.005, 13)]["J4"])
v, d = rg.classify(full, train, R(-0.5, -0.6), {(0.005, 13): .7, (0.010, 13): .5})
chk("J2 holdout 열세면 실패", not d[(0.005, 13)]["J2"])
v, d = rg.classify(R(1.0, 0.9), train, hold, {(0.005, 13): .9, (0.010, 13): .9})
chk("J1 전기간 열세면 실패", not d[(0.005, 13)]["J1"])
chk("train 현행이 음수면 > 비교", rg.judge_cell((0.005, 13), R(-1.0, -0.5), R(-1.0, -0.5), hold, .7)[1]["J3"])

print("§4 부트 결정성·짝지음")
r1 = rg.boot(trs, random.Random(3)); r2 = rg.boot(trs, random.Random(3))
chk("시드 결정적", all(abs(r1[c]["final"] - r2[c]["final"]) < 1e-9 for c in rg.cells()))
sm = rg.boot_summary([r1, r2])
chk("현행 자기 우위 0", sm[rg.CURRENT]["win"] == 0.0)
chk("요약 키", set(sm[rg.CURRENT]) >= {"win", "calmar_med", "mdd_med", "cagr_med", "ruin"})

print(f"\n{ok} passed, {fail} failed")
raise SystemExit(1 if fail else 0)
