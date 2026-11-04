"""test_steward_loss.py — validate_steward_loss 로직 고정 (네트워크 없음, 합성)"""
import numpy as np

import steward as sw
import validate_steward_loss as L
import validate_steward_v2 as v2

ok = fail = 0
def chk(n, c, x=""):
    global ok, fail
    if c: ok += 1
    else: fail += 1; print("  FAIL", n, x)

print("§1 동결")
chk("현행 = steward 상수", L.RULES["C0_current"]["s1"] == (sw.S1_MIN_N, None)
    and L.RULES["C0_current"]["s2"] == (sw.S2_MIN_N, sw.S2_ALPHA, sw.S2_MIN_SPAN_DAYS))
chk("R-080 후보 재사용", all(L.RULES[c] == v2.CANDS[c] for c in ("C1", "C2", "C3")))
chk("신규 후보", L.RULES["L1"] == dict(s1=(30, 0.20), s2=(30, 0.02, 28)) and L.RULES["L3"]["s1"] == (60, 0.30))
chk("DEPLOY·상수", L.DEPLOY_ON_PASS is True and (L.SEED, L.SIMS, L.MIN_DETECT, L.DECAY) == (82, 400, 0.70, -1.0))
chk("steward 상수 불변", (sw.S1_MIN_N, sw.S2_MIN_N, sw.S2_MIN_SPAN_DAYS, sw.S2_ALPHA) == (10, 20, 28, 0.05))
chk("격자에 0 과 -2 와 +1 포함", all(x in L.GRID for x in (0.0, -2.0, 1.0)))

print("§2 NEVER 는 손익 0, 정지 없음")
rng = np.random.default_rng(1)
pool = rng.normal(0, 17, 400)
rest, _ = L.sim_path(3, pool - pool.mean(), -2.0, 3, L.RULES)
chk("NEVER 정지 없음", rest["NEVER"] is None)
pay, stp = L.simulate(pool, sims=20, seed=4)
chk("NEVER 손익 전부 0", all(float(np.abs(a).sum()) == 0 for lam in L.LAMS for a in pay["NEVER"][lam]))
chk("NEVER 정지율 0", all(x == 0 for lam in L.LAMS for x in stp["NEVER"][lam]))

print("§3 부호 — 손실 mu 정지는 +, 이익 mu 정지는 −")
j_neg = [j for j, m in enumerate(L.GRID) if m < 0]
j_pos = [j for j, m in enumerate(L.GRID) if m > 0]
chk("mu<0 에서 정지 손익 >= 0", all(pay["C0_current"][3][j].min() >= 0 for j in j_neg))
chk("mu>0 에서 정지 손익 <= 0", all(pay["C0_current"][3][j].max() <= 0 for j in j_pos))
chk("mu=0 손익 0", float(np.abs(pay["C0_current"][3][L.GRID.index(0.0)]).sum()) == 0)

print("§4 결정성·짝지음")
pay2, _ = L.simulate(pool, sims=20, seed=4)
chk("결정성", all(np.array_equal(pay["C1"][3][j], pay2["C1"][3][j]) for j in range(len(L.GRID))))
w = np.zeros(len(L.GRID)); w[L.GRID.index(-2.0)] = 1.0
pt, lo, hi = L.diff_ci(pay, "C0_current", "C0_current", w, B=50)
chk("자기 자신과의 차 = 0", pt == 0 and lo == 0 and hi == 0)

print("§5 사전분포")
base = []
rs = np.random.default_rng(2)
for u, m in (("a", 3.0), ("b", -1.0), ("c", 1.0)):
    for r in rs.normal(m, 10, 200):
        base.append(dict(pattern=u, ret=r / 100))
for r in rs.normal(5, 10, 10):
    base.append(dict(pattern="tiny", ret=r / 100))
w, info = L.prior_weights(base)
chk("합 1", abs(w.sum() - 1) < 1e-12)
chk("n<40 단위 제외", info["units"] == 3)
wr, _ = L.prior_weights(base, shrink=False)
chk("수축은 퍼짐을 줄인다", max(info["mu"]) <= 3.5 and min(info["mu"]) >= -1.5)
wd, _ = L.prior_weights(base, shift=-1.0)
mean = lambda ww: float(sum(ww[i] * L.GRID[i] for i in range(len(L.GRID))))
chk("감쇠 진단은 평균을 낮춘다", mean(wd) < mean(w))

print("§6 판정 함수")
def fake_pay(best_better):
    pay = {r: {lam: [np.zeros(30) for _ in L.GRID] for lam in L.LAMS} for r in L.RULES}
    stp = {r: {lam: [0.9] * len(L.GRID) for lam in L.LAMS} for r in L.RULES}
    if best_better:
        for lam in L.LAMS:
            for j, m in enumerate(L.GRID):
                pay["L3"][lam][j] = np.full(30, 1.0 + m)   # 모든 mu 에서 양의 손익
    return pay, stp
wm = np.full(len(L.GRID), 1 / len(L.GRID))
pay_f, stp_f = fake_pay(True)
r = L.judge(pay_f, stp_f, wm, wm, wm)
chk("명백한 개선 → ADOPT", r["verdict"] == "ADOPT:L3", r)
pay_f, stp_f = fake_pay(False)
r = L.judge(pay_f, stp_f, wm, wm, wm)
chk("동률 → 유지", r["verdict"] == "CURRENT_RETAINED")
pay_f, stp_f = fake_pay(True)
stp_f["L3"][3][L.GRID.index(-2.0)] = 0.5
r = L.judge(pay_f, stp_f, wm, wm, wm)
chk("탐지 가드 미달 → 유지", r["verdict"] == "CURRENT_RETAINED" and not r["criteria"]["c4_detect"])

print(f"\n{ok} passed, {fail} failed")
raise SystemExit(1 if fail else 0)
