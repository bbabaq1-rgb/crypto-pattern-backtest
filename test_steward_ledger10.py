"""test_steward_ledger10.py — R-096 동결·배선 (합성, 네트워크 없음)"""
import numpy as np

import steward as sw
import validate_steward_ledger as S
import validate_steward_ledger10 as T
import validate_steward_loss as L

ok = fail = 0
def chk(n, c, x=""):
    global ok, fail
    if c: ok += 1
    else: fail += 1; print("  FAIL", n, x)

chk("동결 상수", (T.MIN_UNIT_N, T.MIN_UNITS, T.DEPLOY_ON_PASS) == (10, 4, False))
chk("R-092 원본 상수 불변(import 시)", (S.MIN_UNIT_N, S.MIN_UNITS) == (20, 3))
T.configure()
chk("configure 후 값", (S.MIN_UNIT_N, S.MIN_UNITS) == (10, 4))
chk("규칙 격자 R-082 그대로", list(L.RULES) == ["NEVER", "C0_current", "C1", "C2", "C3", "L1", "L2", "L3"])

def row(p, r):
    return dict(method="D", live_mode=True, return_pct=r, entry_date="2026-10-01", pattern=p, direction="long")
rs = np.random.default_rng(1)
tr = []
for p, m, n in (("a", -2.0, 12), ("b", 1.0, 15), ("c", 0.5, 11), ("d", 0.0, 10), ("tiny", 5.0, 9)):
    tr += [row(p, float(x)) for x in rs.normal(m, 8, n)]
w, info = S.prior(S.ledger_base(tr))
chk("n>=10 단위 4개·tiny 제외", info["units"] == 4 and abs(w.sum() - 1) < 1e-12, info)
chk("MIN_UNIT_N 복원", L.MIN_UNIT_N == 40)
pool = rs.normal(0, 10, 200)
pay, stp = L.simulate(pool, sims=20, seed=5)
r = S.judge(pay, stp, w, w, w, n_units=3, n_total=500)
chk("단위 3 이면 INCONCLUSIVE(MIN_UNITS 4)", r["verdict"] == "INCONCLUSIVE")
r = S.judge(pay, stp, w, w, w, n_units=4, n_total=500)
chk("단위 4 면 판정 어휘", r["verdict"].split(":")[0] in ("ADOPT", "NEVER_PREFERRED", "CURRENT_RETAINED"))
chk("steward 상수 불변", (sw.S1_MIN_N, sw.S2_MIN_N, sw.S2_MIN_SPAN_DAYS, sw.S2_ALPHA) == (10, 20, 28, 0.05))
print(f"\n{ok} 통과 / {fail} 실패")
raise SystemExit(1 if fail else 0)
