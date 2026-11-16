"""test_minorder_equity.py — validate_minorder_equity 로직 고정 (네트워크 없음)"""
import random
import validate_minorder_equity as d
import validate_portfolio as vp

ok = fail = 0
def chk(n, c, x=""):
    global ok, fail
    if c: ok += 1
    else: fail += 1; print("  FAIL", n, x)

chk("DEPLOY False", d.DEPLOY_ON_PASS is False)
chk("격자·주판정·기준", d.EQ_LADDER == (160.0, 240.0, 355.0) and d.PRIMARY_EQ == 240.0 and d.REF_EQ == 1000.0)
rng = random.Random(1)
def mk(n):
    ts = []
    for i in range(n):
        t_in = 740000.0 + i * 0.5
        ts.append(dict(t_in=t_in, t_out=t_in + 3 + rng.random() * 5, ret=rng.uniform(-0.08, 0.15), pattern="p%d" % (i % 3),
                       sym="S%d" % i, rank=i % 30, vol=rng.choice([None, 0.5, 0.9, 1.6])))
    return ts
T = mk(80)
# taken_out 은 읽기 전용 — 결과 동일
a = vp.simulate(T, "current", None)
b = vp.simulate(T, "current", None, taken_out=[])
chk("taken_out 훅은 결과 불변", {k: v for k, v in a.items()} == {k: v for k, v in b.items()})
# START_EQ 복원
e0 = vp.START_EQ
d.run_at(T, 160.0)
chk("START_EQ 복원", vp.START_EQ == e0)
# 기준 1000 에서 시뮬 = 종전 기본값 시뮬(START_EQ 1000)
r, m, n = d.run_at(T, 1000.0)
chk("기준 equity 1000 은 종전 시뮬과 같다", abs(r["final"] - a["final"]) < 1e-9 and r["taken"] == a["taken"])
chk("체결 수 = taken", n == r["taken"])
# 낮은 equity 는 최소주문 스킵이 더 많다
r2, _, n2 = d.run_at(T, 100.0)
chk("낮은 equity 는 증거금 스킵 >= 기준", r2["skip_margin"] >= r["skip_margin"], (r2["skip_margin"], r["skip_margin"]))
# 판정 함수
chk("HURTS", d.verdict(0.95, 0.04, -0.3, -0.2, 50) == "SKIP_HURTS")
chk("HELPS", d.verdict(0.03, 0.97, 0.3, 0.2, 50) == "SKIP_HELPS")
chk("전후반 부호 불일치면 NO_EFFECT", d.verdict(0.95, 0.04, 0.3, -0.2, 50) == "NO_EFFECT")
chk("CI 안이면 NO_EFFECT", d.verdict(0.6, 0.4, -0.1, -0.1, 50) == "NO_EFFECT")
chk("부트 없으면 INSUFFICIENT", d.verdict(None, None, 0, 0, 0) == "INSUFFICIENT")
# 짝지음 부트 결정론
x = d.paired_calmar_diff(T, 240.0, seed=3, n=20)
y = d.paired_calmar_diff(T, 240.0, seed=3, n=20)
chk("부트 결정론", x == y)
chk("기준 대 기준은 차 0 → P(d<=0)=P(d>=0)=1", d.paired_calmar_diff(T, d.REF_EQ, seed=3, n=10)[:2] == (1.0, 1.0))
print(f"{ok} passed, {fail} failed")
raise SystemExit(1 if fail else 0)
