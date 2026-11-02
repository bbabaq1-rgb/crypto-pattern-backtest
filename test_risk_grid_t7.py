"""test_risk_grid_t7.py — validate_risk_grid_t7 로직 고정 (네트워크 없음)"""
import random
from datetime import date

import validate_risk_grid as rg
import validate_risk_grid_t7 as t7

ok = fail = 0
def chk(n, c, x=""):
    global ok, fail
    if c: ok += 1
    else: fail += 1; print("  FAIL", n, x)

rng = random.Random(6)
trs = []
for i in range(300):
    d = float(date.fromordinal(739000 + rng.randrange(500)).toordinal())
    trs.append(dict(pattern="fvg", t_in=d, t_out=d + rng.randrange(1, 9), ret=rng.uniform(-.1, .15), sym="S%d" % i,
                    vol=rng.uniform(.4, 1.5), rank=rng.randrange(30), tf="1d"))
trs.sort(key=lambda t: t["t_in"])

print("§1 동결")
chk("R-073 셀·기준 재사용", t7.rg is rg and rg.CURRENT == (0.015, 13) and rg.PRIMARY == ((0.005, 13), (0.010, 13)))
chk("J4 문턱 0.60·300회·블록 T7·seed 86", rg.J4_WIN == 0.60 and t7.BOOT_N == 300 and t7.BLOCK == "T7" and t7.SEED == 86)
chk("seed 가 R-073 과 다름", t7.SEED != rg.SEED)
chk("DEPLOY_ON_PASS", t7.DEPLOY_ON_PASS is False)

print("§2 짝지음 재표집")
a = t7.boot_t7(trs, random.Random(1)); b = t7.boot_t7(trs, random.Random(1))
chk("셀 6개", set(a) == set(rg.cells()))
chk("같은 seed 재현", all(abs(a[c]["final"] - b[c]["final"]) < 1e-9 for c in a))
chk("일부 셀이 서로 다른 결과(위험 수준이 실제 반영)", len({round(a[c]["final"], 6) for c in a}) > 1)

print("§3 판정 재사용")
res = {c: dict(calmar=1.0, cagr=.1, mdd=-.3) for c in rg.cells()}
res[(0.005, 13)] = dict(calmar=2.0, cagr=.2, mdd=-.2)
v, d = rg.classify(res, res, res, {c: 0.7 for c in rg.cells()})
chk("J4 0.7 이면 SUPPORTED", v == "SUPPORTED" and d[(0.005, 13)]["passed"])
v2, _ = rg.classify(res, res, res, {c: 0.5 for c in rg.cells()})
chk("J4 0.5 이면 REJECTED", v2 == "REJECTED")

print(f"{ok} 통과 / {fail} 실패")
raise SystemExit(1 if fail else 0)
