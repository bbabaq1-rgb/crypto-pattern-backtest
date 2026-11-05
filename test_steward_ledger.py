"""test_steward_ledger.py — validate_steward_ledger 로직 고정 (네트워크 없음, 합성)"""
import numpy as np

import steward as sw
import validate_steward_ledger as S
import validate_steward_loss as L

ok = fail = 0
def chk(n, c, x=""):
    global ok, fail
    if c: ok += 1
    else: fail += 1; print("  FAIL", n, x)

print("§1 동결")
chk("DEPLOY·상수", S.DEPLOY_ON_PASS is True and (S.MIN_UNIT_N, S.MIN_UNITS, S.MIN_TOTAL_N) == (20, 3, 100))
chk("규칙 격자는 R-082 그대로", list(L.RULES) == ["NEVER", "C0_current", "C1", "C2", "C3", "L1", "L2", "L3"])
chk("MIN_UNIT_N 복원", (lambda: (S.prior([dict(pattern="a|long", ret=0.01)] * 25 + [dict(pattern="b|long", ret=-0.01)] * 25), L.MIN_UNIT_N)[1])() == 40)

print("§2 장부 → base")
def row(p, d, r, live=True):
    return dict(method="D", live_mode=live, return_pct=r, entry_date="2026-10-01", pattern=p, direction=d)
trades = [row("a", "long", 1.0)] * 3 + [row("a", "long", 2.0, live=False), dict(row("b", "long", 1.0), method="A")]
base = S.ledger_base(trades)
chk("실거래 방식D 만", len(base) == 3 and base[0]["pattern"] == "a|long" and abs(base[0]["ret"] - 0.01) < 1e-12)

print("§3 prior — n>=20 단위만")
rs = np.random.default_rng(3)
tr = []
for p, m, n in (("a", -2.0, 30), ("b", 1.0, 40), ("c", 0.5, 25), ("tiny", 9.0, 10)):
    tr += [row(p, "long", float(x)) for x in rs.normal(m, 8, n)]
w, info = S.prior(S.ledger_base(tr))
chk("tiny 제외·합 1", info["units"] == 3 and abs(w.sum() - 1) < 1e-12)
wd, _ = S.prior(S.ledger_base(tr), shift=-1.0)
mean = lambda ww: float(sum(ww[i] * L.GRID[i] for i in range(len(L.GRID))))
chk("decay 는 평균을 낮춘다", mean(wd) < mean(w))

print("§4 판정 — 장부 부족은 INCONCLUSIVE, 코드만 판정")
pool = rs.normal(0, 10, 300)
pay, stp = L.simulate(pool, sims=20, seed=5)
r = S.judge(pay, stp, w, w, wd, n_units=2, n_total=500)
chk("단위 부족 INCONCLUSIVE", r["verdict"] == "INCONCLUSIVE")
r = S.judge(pay, stp, w, w, wd, n_units=3, n_total=50)
chk("표본 부족 INCONCLUSIVE", r["verdict"] == "INCONCLUSIVE")
r = S.judge(pay, stp, w, w, wd, n_units=3, n_total=500)
chk("판정 어휘", r["verdict"].split(":")[0] in ("ADOPT", "NEVER_PREFERRED", "CURRENT_RETAINED"))
chk("NEVER 손익 0", abs(r["J"]["NEVER"]) == 0)
wneg = np.zeros(len(L.GRID)); wneg[L.GRID.index(-4.0)] = 1.0
rn = S.judge(pay, stp, wneg, wneg, wneg, 3, 500)
chk("전 단위 mu=-4 면 정지 규칙이 NEVER 를 이긴다", rn["J"]["L3"] > 0 and rn["J"]["C0_current"] > 0)

print("§5 steward 상수 불변(이 시험은 연구 전용)")
chk("상수", (sw.S1_MIN_N, sw.S2_MIN_N, sw.S2_MIN_SPAN_DAYS, sw.S2_ALPHA) == (10, 20, 28, 0.05))

print(f"\n{ok} 통과 / {fail} 실패")
raise SystemExit(1 if fail else 0)
