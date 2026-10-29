"""test_steward_char.py — validate_steward_char 로직 고정 (네트워크 없음, 합성 거래)"""
import random
from datetime import date

import numpy as np

import steward as sw
import validate_steward_char as v

ok = fail = 0
def chk(n, c, x=""):
    global ok, fail
    if c: ok += 1
    else: fail += 1; print("  FAIL", n, x)

D0 = date(2025, 1, 6).toordinal()
def T(day, ret, hold=2, pat="x"):
    return dict(t_in=float(D0 + day), t_out=float(D0 + day + hold), ret=ret, pattern=pat, sym="s", vol=1.0, rank=1, tf="4h")

print("§1 규칙 상수 — steward 와 동일")
chk("상수", (sw.S1_MIN_N, sw.S2_MIN_N, sw.S2_MIN_SPAN_DAYS, sw.S2_ALPHA) == (10, 20, 28, 0.05))
chk("V 단위 = steward.CONFIRMED 4h", all((u, "long") in sw.CONFIRMED for u in v.V_UNITS))
chk("등급", v.tier_for("vol_awakening_4h") == "V" and v.tier_for("fvg") == "U")
chk("DEPLOY", v.DEPLOY_ON_PASS is False)

print("§2 순차 적용 — S1")
neg = [T(i * 3, -0.02) for i in range(30)]
stop, rest = v.run_unit(neg, "U")
chk("전부 음수 U: S1 이 n=10 근처에서", stop is not None and stop["rule"].startswith("S1") and 10 <= stop["at"] <= 14, stop)
chk("정지 이후 잔여 수", rest["n_rest"] == 30 - stop["at"])
pos = [T(i * 3, 0.03) for i in range(60)]
stop, rest = v.run_unit(pos, "U")
chk("전부 양수는 정지 없음", stop is None and rest["n_rest"] == 0)
stop, _ = v.run_unit(neg, "V")
chk("V 등급은 S1 면제(S2 만)", stop is None or stop["rule"] == "S2", stop)
few = [T(i, -0.05) for i in range(9)]
stop, _ = v.run_unit(few, "U")
chk("n<10 은 정지 없음", stop is None)

print("§3 S2 — 충분한 표본·기간에서만")
neg2 = [T(i * 2, -0.03) for i in range(60)]  # 120일
stop, _ = v.run_unit(neg2, "V")
chk("V 라도 일관 음수면 S2", stop is not None and stop["rule"] == "S2" and stop["at"] >= 20, stop)
chk("S2 전제 함수", v.s2_pre(20, -0.1, 28) and not v.s2_pre(19, -0.1, 28) and not v.s2_pre(20, 0.1, 28) and not v.s2_pre(20, -0.1, 27))

print("§4 파트 A 분류")
tr = neg + [T(200 + i, 0.04, pat="x") for i in range(40)]
a = v.part_a([dict(t, pattern="x") for t in tr])
chk("정지 후 잔여 양수 = FALSE_STOP", a["x"]["cls"] == "FALSE_STOP", a["x"])
tr2 = [T(i * 3, -0.02, pat="y") for i in range(60)]
a2 = v.part_a(tr2)
chk("잔여 음수 = CORRECT_STOP", a2["y"]["cls"] == "CORRECT_STOP", a2["y"])
tr3 = [T(i * 2, -0.03, pat="vol_awakening_4h") for i in range(60)]
chk("V 정지 분류", v.part_a(tr3)["vol_awakening_4h"]["cls"] == "V_STOPPED")

print("§5 몬테카를로 — 결정성·단조성")
rg = np.random.default_rng(1)
pool = list(rg.normal(0, 8, 2000))
b1 = v.part_b(pool, sims=40, seed=5)
b2 = v.part_b(pool, sims=40, seed=5)
chk("시드 결정성", b1 == b2)
chk("mu 단조(S1 정지확률 감소)", b1[(3, -2.0)]["p_s1"] >= b1[(3, 0.0)]["p_s1"] >= b1[(3, 2.0)]["p_s1"], [b1[(3, m)]["p_s1"] for m in (-2.0, 0.0, 2.0)])
chk("강한 음수는 거의 항상 정지", b1[(3, -2.0)]["p_any"] > 0.7, b1[(3, -2.0)])
chk("확률 범위", all(0 <= x["p_s1"] <= 1 and 0 <= x["p_s2"] <= 1 for x in b1.values()))

print("§6 판정 함수")
good_a = {"u": dict(cls="NEVER_STOPPED")}
bad_a = {"u": dict(cls="V_STOPPED")}
mk = lambda p1, p2, pany, med: {(3, 1.0): dict(p_s1=p1, p_s2=p2), (3, -2.0): dict(p_any=pany, med_n=med)}
chk("전부 충족", v.verdict(good_a, mk(0.1, 0.02, 0.9, 20))[0] == "RULES_OK")
chk("S1 과민", v.verdict(good_a, mk(0.6, 0.02, 0.9, 20))[1] == ["S1_OVERTRIGGER"])
chk("복수 실패", v.verdict(bad_a, mk(0.6, 0.2, 0.5, 80))[1] == ["V_FALSE_STOP", "S1_OVERTRIGGER", "SLOW_DETECTION", "S2_MISCALIBRATED"])
chk("med None 이면 느린 탐지", "SLOW_DETECTION" in v.verdict(good_a, mk(0.1, 0.02, 0.9, None))[1])

print(f"\n{ok} 통과 / {fail} 실패")
raise SystemExit(1 if fail else 0)
