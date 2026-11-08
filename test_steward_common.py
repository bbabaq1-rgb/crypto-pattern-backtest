"""test_steward_common.py — R-100 동결·배선 (합성, 네트워크 없음)"""
import numpy as np

import steward as sw
import validate_steward_common as C
import validate_steward_phase as P

ok = fail = 0
def chk(n, c, x=""):
    global ok, fail
    if c: ok += 1
    else: fail += 1; print("  FAIL", n, x)

chk("동결", (C.SPLIT, C.MIN_UNIT_N, C.MIN_COMMON, C.MIN_ARM_N, C.DEPLOY_ON_PASS) == (P.SPLIT, 10, 2, 40, False))
rs = np.random.default_rng(1)
pre = {"a|long": list(rs.normal(2, 3, 30)), "b|long": list(rs.normal(2, 3, 30)), "c|long": list(rs.normal(2, 3, 30))}
post = {"a|long": list(rs.normal(-3, 3, 30)), "b|long": list(rs.normal(-3, 3, 30)), "d|long": list(rs.normal(-3, 3, 30))}
u = C.common_units(pre, post)
chk("공통 단위만", u == ["a|long", "b|long"], u)
post["b|long"] = post["b|long"][:5]
chk("arm 중 한쪽 n<10 이면 제외", C.common_units(pre, post) == ["a|long"])
post["b|long"] = list(rs.normal(-3, 3, 30))
r = C.strat_boot(pre, post, u, b=300)
chk("점추정", r["pre"] > 1 and r["post"] < -1 and r["diff"] < -3)
chk("PHASE_EFFECT", C.judge(r, 2, 60, 60) == "PHASE_EFFECT")
chk("공통 단위 부족 INCONCLUSIVE", C.judge(r, 1, 60, 60) == "INCONCLUSIVE")
chk("표본 부족 INCONCLUSIVE", C.judge(r, 2, 30, 60) == "INCONCLUSIVE")
same = {k: list(rs.normal(0, 3, 40)) for k in ("a|long", "b|long")}
same2 = {k: list(rs.normal(0, 3, 40)) for k in ("a|long", "b|long")}
r2 = C.strat_boot(same, same2, ["a|long", "b|long"], b=300)
chk("차이 없음 UNIT_COMPOSITION", C.judge(r2, 2, 80, 80) == "UNIT_COMPOSITION")
dp = {k: list(rs.normal(3, 3, 40)) for k in ("a|long", "b|long")}
dq = {k: list(rs.normal(1.0, 3, 40)) for k in ("a|long", "b|long")}
r3 = C.strat_boot(dp, dq, ["a|long", "b|long"], b=300)
chk("하락만 PARTIAL_DROP", C.judge(r3, 2, 80, 80) == "PARTIAL_DROP", r3)
chk("결정론", C.strat_boot(pre, post, u, b=100) == C.strat_boot(pre, post, u, b=100))
print(f"test_steward_common {ok} ok / {fail} fail")
raise SystemExit(1 if fail else 0)
