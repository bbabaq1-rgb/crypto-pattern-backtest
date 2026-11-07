"""test_steward_phase.py — R-099 동결·배선 (합성, 네트워크 없음)"""
import numpy as np

import steward as sw
import validate_steward_ledger as S
import validate_steward_loss as L
import validate_steward_phase as T

ok = fail = 0
def chk(n, c, x=""):
    global ok, fail
    if c: ok += 1
    else: fail += 1; print("  FAIL", n, x)

chk("동결 상수", (T.SPLIT, T.MIN_UNIT_N, T.MIN_UNITS, T.MIN_ARM_N, T.DEPLOY_ON_PASS) == ("2026-10-10", 10, 3, 60, False))
chk("규칙 격자 R-082 그대로", list(L.RULES) == ["NEVER", "C0_current", "C1", "C2", "C3", "L1", "L2", "L3"])

rs = np.random.default_rng(3)
def row(p, r, d):
    return dict(method="D", live_mode=True, return_pct=float(r), entry_date=d, pattern=p, direction="long")
tr = []
for p, m in (("a", -1.0), ("b", 1.0), ("c", 0.5), ("d", -0.5)):
    tr += [row(p, x, "2026-09-20") for x in rs.normal(m, 8, 20)]       # 전
    tr += [row(p, x, "2026-10-15") for x in rs.normal(m - 2, 8, 20)]   # 후
tr += [row("a", 1.0, "2026-10-10")]                                    # 경계일은 '후'
rows = sw.live_d(tr)
pre, post = T.split_base(rows)
chk("분할 경계(<SPLIT 전, >=SPLIT 후)", len(pre) == 80 and len(post) == 81, (len(pre), len(post)))
chk("입력 보존", len(pre) + len(post) == len(rows))
a = T.arm_prior(pre)
chk("arm prior 단위 4", a is not None and a[1]["units"] == 4)
chk("S.MIN_UNIT_N 복원", S.MIN_UNIT_N == 20 and L.MIN_UNIT_N == 40)
chk("표본 부족 arm = None", T.arm_prior(pre[:30]) is None)
chk("단위 부족 arm = None", T.arm_prior([r for r in pre if r["pattern"].startswith("a")] * 1) is None)
chk("w 합 1", abs(a[0].sum() - 1) < 1e-12)
pool = rs.normal(0, 10, 200)
pay, stp = L.simulate(pool, sims=20, seed=5)
r = T.judge(pay, None, a)
chk("pre 부족이면 INCONCLUSIVE", r["verdict"] == "INCONCLUSIVE")
r = T.judge(pay, a, a)
chk("판정 어휘", r["verdict"] in ("UNIT_ROBUST", "PHASE_DEPENDENT", "NOT_SEPARABLE"))
chk("같은 prior 를 양쪽에 주면 PHASE_DEPENDENT 불가", r["verdict"] != "PHASE_DEPENDENT")
chk("steward 상수 불변", (sw.S1_MIN_N, sw.S2_MIN_N, sw.S2_MIN_SPAN_DAYS, sw.S2_ALPHA) == (10, 20, 28, 0.05))
print(f"\n{ok} 통과 / {fail} 실패")
raise SystemExit(1 if fail else 0)
