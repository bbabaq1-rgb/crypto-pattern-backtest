"""test_risk_cost.py — validate_risk_cost 로직 고정 (네트워크 없음)"""
import random
import validate_gap as vg
import validate_killswitch as ks
import validate_risk_cost as d
import validate_risk_equity as re_
import validate_portfolio as vp

ok = fail = 0
def chk(n, c, x=""):
    global ok, fail
    if c: ok += 1
    else: fail += 1; print("  FAIL", n, x)

chk("DEPLOY False", d.DEPLOY_ON_PASS is False)
chk("동결", d.RISKS == re_.RISKS and d.EQS == re_.EQS and d.BOOT_N == 500 and d.SEED == 122
    and d.RATIO_MIN == 0.70 and d.SKIP_MAX == 0.20 and d.RATIO_EQS == (355.0, 500.0, 750.0))
chk("R-118 상수", ks.FLOOR == 100.0 and ks.WINDOWS == 52)

def mk(g10, g15, skip=0.1):
    s = {}
    for r in d.RISKS:
        for e in d.EQS:
            g = {0.005: 1.2, 0.010: g10, 0.015: g15}[r]
            s[(r, e)] = dict(final_med=g * e, growth_med=g, mdd_med=-0.3, taken_med=50, skip_med=skip if (r, e) == (0.010, 240.0) else 0.0, p_loss=0.1)
    return s
chk("COST_SMALL", d.verdict(mk(1.45, 1.6)) == "COST_SMALL")   # 비율 .45/.6=.75
chk("COST_LARGE", d.verdict(mk(1.2, 1.7)) == "COST_LARGE")    # .2/.7=.29
chk("MIXED(skip 실패)", d.verdict(mk(1.45, 1.6, skip=0.3)) == "MIXED")
chk("INCONCLUSIVE(1.5% 성장<=1)", d.verdict(mk(1.1, 0.9)) == "INCONCLUSIVE")
chk("ratio 값", abs(d.ratio(mk(1.45, 1.6), 355.0) - 0.75) < 1e-12)
chk("ratio 정의 불가", d.ratio(mk(1.1, 1.0), 355.0) is None)

rng = random.Random(5)
T = []
for i in range(300):
    t_in = 740000.0 + i * 0.5
    T.append(dict(t_in=t_in, t_out=t_in + 3 + rng.random() * 5, ret=rng.uniform(-0.09, 0.12), pattern="p%d" % (i % 3),
                  sym="S%d" % i, rank=i % 30, vol=rng.choice([None, 0.5, 0.9, 1.6])))
e0 = vp.START_EQ
c = d.run_cell(T, 355.0, 0.010)
chk("START_EQ 복원", vp.START_EQ == e0)
vp.START_EQ = 355.0
r = vg.simulate(T, floor=100.0, risk=0.010)
vp.START_EQ = e0
chk("run_cell == vg.simulate", c["final"] == r["final"] and c["mdd"] == r["mdd"] and c["taken"] == r["taken"])
chk("risk 1.5% 도달 판정과 동일 경로", re_.run_cell(T, 240.0, 0.015) == (min(e for _, e in (lambda p: (vg.simulate(T, path=p, floor=100.0, risk=0.015), p)[1])([])) < 100.0))
b1 = d.summarize(d.boot(T, n=6)); b2 = d.summarize(d.boot(T, n=6))
chk("시드 결정성", b1 == b2)
chk("12셀", len(b1) == 12)
print(f"test_risk_cost: {ok} ok, {fail} fail")
raise SystemExit(1 if fail else 0)
