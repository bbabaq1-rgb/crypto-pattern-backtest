"""test_risk_equity.py — validate_risk_equity 로직 고정 (네트워크 없음)"""
import random
import validate_gap as vg
import validate_killswitch as ks
import validate_risk_equity as d
import validate_portfolio as vp

ok = fail = 0
def chk(n, c, x=""):
    global ok, fail
    if c: ok += 1
    else: fail += 1; print("  FAIL", n, x)

chk("DEPLOY False", d.DEPLOY_ON_PASS is False)
chk("동결", d.RISKS == (0.005, 0.010, 0.015) and d.EQS == (240.0, 355.0, 500.0, 750.0) and d.SEED == 120
    and d.BOOT_N == 500 and d.SAFE_P == 0.05 and d.LOW_RISK_EQ == 355.0)
chk("R-118 상수 재사용", ks.FLOOR == 100.0 and ks.WINDOWS == 52)

def pv(f):
    return {(r, e): f(r, e) for r in d.RISKS for e in d.EQS}
chk("전부 위험 -> NO_SAFE_CELL", d.verdict(pv(lambda r, e: 0.2)) == "NO_SAFE_CELL")
chk("risk 비례 -> RISK_SCALES", d.verdict(pv(lambda r, e: 0.01 if e * 0.005 / 0.005 >= {0.005: 355, 0.01: 500, 0.015: 750}[r] else 0.2)) == "RISK_SCALES")
chk("0.5%도 500부터 -> SAFE_BUT_LARGE", d.verdict(pv(lambda r, e: 0.01 if e >= 500 else 0.2)) == "SAFE_BUT_LARGE")
chk("역전(1.5%만 안전) -> SAFE_BUT_LARGE", d.verdict(pv(lambda r, e: 0.01 if (r == 0.015 and e >= 355) else 0.2)) == "SAFE_BUT_LARGE")
chk("min_safe", d.min_safe(pv(lambda r, e: 0.01 if e >= 500 else 0.2), 0.005) == 500)

rng = random.Random(5)
T = []
for i in range(300):
    t_in = 740000.0 + i * 0.5
    T.append(dict(t_in=t_in, t_out=t_in + 3 + rng.random() * 5, ret=rng.uniform(-0.09, 0.12), pattern="p%d" % (i % 3),
                  sym="S%d" % i, rank=i % 30, vol=rng.choice([None, 0.5, 0.9, 1.6])))
e0 = vp.START_EQ
a = d.run_cell(T, 240.0, 0.015)
chk("START_EQ 복원", vp.START_EQ == e0)
chk("risk 1.5% 셀 == R-118 run_path", a == ks.run_path(T, 240.0)["reached"])
b1 = d.boot(T, n=6); b2 = d.boot(T, n=6)
chk("시드 결정성", b1 == b2)
chk("12셀", len(b1) == 12)
print(f"test_risk_equity: {ok} ok, {fail} fail")
raise SystemExit(1 if fail else 0)
