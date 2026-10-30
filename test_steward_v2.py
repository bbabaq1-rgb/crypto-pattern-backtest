"""test_steward_v2.py — validate_steward_v2 로직 고정 (네트워크 없음, 합성 풀)"""
import numpy as np

import steward as sw
import validate_steward_v2 as v

ok = fail = 0
def chk(n, c, x=""):
    global ok, fail
    if c: ok += 1
    else: fail += 1; print("  FAIL", n, x)

print("§1 동결")
c0 = v.CANDS["C0_current"]
chk("C0 = 현행 steward 상수", c0["s1"] == (sw.S1_MIN_N, None) and c0["s2"] == (sw.S2_MIN_N, sw.S2_ALPHA, sw.S2_MIN_SPAN_DAYS))
chk("후보", v.CANDS["C1"] == dict(s1=(20, 0.20), s2=(20, 0.005, 28)) and v.ORDER == ("C1", "C2", "C3"))
chk("기준", (v.Q1_MAX, v.Q2_MIN, v.Q2_MED, v.Q3_MAX, v.Q4_MAX) == (0.15, 0.80, 40, 0.05, 0.20))
chk("DEPLOY", v.DEPLOY_ON_PASS is False)
chk("steward 상수 불변", (sw.S1_MIN_N, sw.S2_MIN_N, sw.S2_MIN_SPAN_DAYS, sw.S2_ALPHA) == (10, 20, 28, 0.05))

print("§2 경로 — 후보 간 같은 거래열, 결정성")
rng = np.random.default_rng(1)
pool = rng.normal(0, 17, 500)
a = v.sim_once(5, pool - pool.mean(), -2.0, 3, v.CANDS)
b = v.sim_once(5, pool - pool.mean(), -2.0, 3, v.CANDS)
chk("결정성", a == b)
# 엄격한 후보는 현행보다 먼저 정지할 수 없다(S1 n 문턱이 크고 α 가 작다)
for sd in range(30):
    st = v.sim_once(sd, pool - pool.mean(), -1.0, 3, v.CANDS)
    cur = st["C0_current"][0]
    for c in ("C1", "C2", "C3"):
        s1 = st[c][0]
        if s1 and cur and s1[0] < cur[0]:
            chk("엄격 후보가 현행 S1 보다 일찍 정지 안 함", False, (sd, c, s1, cur)); break
chk("엄격 후보 S1 순서 검사 완료", True)

print("§3 mu 효과 단조")
r = v.part_b(pool, sims=60, seed=3, rules={"C0_current": v.CANDS["C0_current"], "C1": v.CANDS["C1"]})
chk("현행: mu=-2 정지 > mu=+2 정지", r[("C0_current", 3, -2.0)]["p_u"] > r[("C0_current", 3, 2.0)]["p_u"])
chk("C1 은 현행보다 mu=+1 오정지 적거나 같다", r[("C1", 3, 1.0)]["p_u"] <= r[("C0_current", 3, 1.0)]["p_u"])
chk("V 정지 ≤ U 정지", all(x["p_v"] <= x["p_u"] + 1e-12 for x in r.values()))

print("§4 판정 함수")
def fake(o=None):
    b = {}
    for c in v.CANDS:
        for lam in v.LAMS:
            for mu in v.MUS:
                b[(c, lam, mu)] = dict(p_u=0.1, p_v=0.02, med_n=30)
        b[(c, 3, -2.0)] = dict(p_u=0.9, p_v=0.5, med_n=30)
    b.update(o or {})
    return b
ver, f = v.verdict(fake())
chk("전부 통과 → C1 채택", ver == "V2_ADOPTABLE:C1", ver)
ver, f = v.verdict(fake({("C1", 3, 1.0): dict(p_u=0.3, p_v=0.02, med_n=30)}))
chk("C1 실패 시 C2", ver == "V2_ADOPTABLE:C2" and "Q1_FALSE_STOP_U" in f["C1"], ver)
slow = {(c, 3, -2.0): dict(p_u=0.9, p_v=0.5, med_n=90) for c in v.CANDS}
ver, f = v.verdict(fake(slow))
chk("느림만 실패 → TRADEOFF", ver.startswith("TRADEOFF"), ver)
bad = {(c, 3, 1.0): dict(p_u=0.4, p_v=0.2, med_n=30) for c in v.CANDS}
ver, f = v.verdict(fake(bad))
chk("전부 오정지 → NO_CANDIDATE", ver == "NO_CANDIDATE", ver)

print(f"\n{ok} passed, {fail} failed")
raise SystemExit(1 if fail else 0)
