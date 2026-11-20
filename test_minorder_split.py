"""test_minorder_split.py — validate_minorder_split / vg.simulate(skips=) 고정 (네트워크 없음)"""
import random
import validate_gap as vg
import validate_killswitch as ks
import validate_minorder_split as d
import validate_portfolio as vp

ok = fail = 0
def chk(n, c, x=""):
    global ok, fail
    if c: ok += 1
    else: fail += 1; print("  FAIL", n, x)

chk("DEPLOY False", d.DEPLOY_ON_PASS is False)
chk("동결", d.RISKS == (0.010, 0.015) and d.EQS == (240.0, 355.0, 500.0, 750.0) and d.SEED == 124
    and d.BOOT_N == 500 and d.HI == 0.20 and d.LO == 0.10)

rng = random.Random(7)
T = []
for i in range(400):
    t_in = 740000.0 + i * 0.4
    T.append(dict(t_in=t_in, t_out=t_in + 3 + rng.random() * 6, ret=rng.uniform(-0.09, 0.12), pattern="p%d" % (i % 3),
                  sym="S%d" % i, rank=i % 30, vol=rng.choice([None, 0.4, 0.9, 1.6, 2.0])))
e0 = vp.START_EQ
for eq0 in (160.0, 240.0, 750.0):
    for risk in (None, 0.010, 0.015):
        for fl in (None, 100.0):
            vp.START_EQ = eq0
            a = vg.simulate(T, risk=risk, floor=fl)
            sk = {}
            b = vg.simulate(T, risk=risk, floor=fl, skips=sk)
            vp.START_EQ = e0
            chk("훅 동작 불변 %s %s %s" % (eq0, risk, fl), {k: v for k, v in a.items()} == {k: v for k, v in b.items()})
            chk("스킵 합 = skipped %s %s %s" % (eq0, risk, fl), sum(sk.values()) == b["skipped"], (sk, b["skipped"]))
            chk("원인 키 한정", set(sk) <= set(d.CAUSES))

vp.START_EQ = 240.0
sk = {}
vg.simulate(T, risk=0.010, floor=100.0, skips=sk)
vp.START_EQ = e0
chk("저 equity 에서 최소주문 스킵 발생", sk.get("minorder", 0) > 0, sk)
vp.START_EQ = 5000.0
sk2 = {}
vg.simulate(T, risk=0.010, floor=100.0, skips=sk2)
vp.START_EQ = e0
chk("큰 equity 에서 최소주문 스킵 없음", sk2.get("minorder", 0) == 0, sk2)

def mk(a, b):
    s = {}
    for r in d.RISKS:
        for e in d.EQS:
            s[(r, e)] = dict(mo_reach=0.0)
    s[(0.010, 240.0)]["mo_reach"] = a
    s[(0.010, 355.0)]["mo_reach"] = b
    return s
chk("CONFIRMED", d.verdict(mk(0.4, 0.05)) == "CONFIRMED")
chk("NOT_BINDING", d.verdict(mk(0.1, 0.0)) == "MINORDER_NOT_BINDING")
chk("THRESHOLD_HIGHER", d.verdict(mk(0.5, 0.2)) == "THRESHOLD_HIGHER")
chk("경계 HI", d.verdict(mk(0.20, 0.0)) == "CONFIRMED")
chk("경계 LO", d.verdict(mk(0.5, 0.10)) == "THRESHOLD_HIGHER")

r = d.run_cell(ks.one_year_path(ks.windows_of(T), random.Random(1)), 240.0, 0.010)
chk("run_cell 합계", r["taken"] + sum(r[k] for k in d.CAUSES) == r["total"], r)
print(f"\n{ok} passed, {fail} failed")
raise SystemExit(1 if fail else 0)
