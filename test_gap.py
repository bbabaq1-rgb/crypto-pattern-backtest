"""test_gap.py — validate_gap 로직 고정 (네트워크 없음)"""
import random
from datetime import date

import validate_gap as g
import validate_portfolio as vp

ok = fail = 0
def chk(n, c, x=""):
    global ok, fail
    if c: ok += 1
    else: fail += 1; print("  FAIL", n, x)

rng = random.Random(5)
trs = []
for i in range(150):
    d = float(date.fromordinal(739000 + rng.randrange(300)).toordinal())
    trs.append(dict(pattern=rng.choice(["engulfing", "fvg", "vol_awakening_4h"]), t_in=d, t_out=d + rng.randrange(1, 9),
                    ret=rng.uniform(-.1, .15), sym="S%d" % i, vol=rng.uniform(.4, 1.5), rank=rng.randrange(30),
                    tf="4h" if i % 3 == 0 else "1d"))
trs.sort(key=lambda t: t["t_in"])

print("§1 기본 설정은 vp.simulate(current) 와 동일 (회계 동치)")
a, b = g.simulate(trs), vp.simulate(trs, "current")
chk("final/cagr/mdd/taken", all(abs(a[k] - b[k]) < 1e-9 for k in ("final", "cagr", "mdd")) and a["taken"] == b["taken"], (a, b))
chk("스킵 합 = 슬롯+증거금", a["skipped"] == b["skip_slot"] + b["skip_margin"])

print("§2 노브 성질")
chk("슬롯 무제한은 체결 >= 현행", g.simulate(trs, max_pos=g.INF)["taken"] >= a["taken"])
nc = g.simulate(trs, max_pos=g.INF, no_caps=True)
chk("no_caps 는 스킵 0", nc["skipped"] == 0 and nc["taken"] == len(trs))
chk("flat 은 변동성 배율을 무시(결과가 달라짐)", g.simulate(trs, flat=True)["final"] != a["final"])
chk("risk 인자 반영", g.simulate(trs, risk=0.005)["final"] != a["final"])
r1 = g.simulate(trs, rng=random.Random(1)); r2 = g.simulate(trs, rng=random.Random(1))
chk("무작위 우선순위는 시드 결정적", r1["final"] == r2["final"])
chk("stage_run 이 G4 에서 vol_awakening 제거", g.stage_run(trs, "G4")["taken"] <= a["taken"])
chk("G5 는 4h 제거", g.stage_run(trs, "G5")["taken"] <= a["taken"])
p = []
g.simulate(trs, path=p)
chk("path 기록", len(p) > 0 and abs(p[-1][1] - a["final"]) < 1e-6)

print("§3 판정 규칙")
def R(**kw):
    d = {s: dict(cagr=-.1) for s in g.STAGES}
    for k, v in kw.items(): d[k] = dict(cagr=v)
    return d
chk("G0 양수면 NO_GAP", g.classify(R(G0=.1))[0] == "NO_GAP")
chk("아무것도 안 돌아서면 PATH_DEPENDENT", g.classify(R())[0] == "PATH_DEPENDENT")
chk("G1 만 돌아서면 변동성 가중", g.classify(R(G1=.05))[0] == "a_vol_weight")
chk("G3 면 슬롯·증거금", g.classify(R(G3=.05))[0] == "c_slot_margin")
chk("G4 면 4h 버스트", g.classify(R(G4=.05))[0] == "b_4h_burst")
chk("G6 만이면 RISK_LEVEL", g.classify(R(G6=.01))[0] == "RISK_LEVEL")
chk("복수면 개선 최대가 primary", g.classify(R(G1=.01, G4=.2))[0] == "b_4h_burst")
chk("DEPLOY_ON_PASS False", g.DEPLOY_ON_PASS is False)

print("§4 진단 함수")
sel = g.selection_diag(trs, [0, 1, 2])
chk("체결/미체결 분할", sel["n_taken"] == 3 and sel["n_skipped"] == len(trs) - 3)
chk("독립 로그성장 유한", abs(g.indep_log_growth(trs)) < 1e3)
w = g.weekly_loss_concentration([(739000.0, 1000.0), (739010.0, 900.0)])
chk("주별 집중", w["weeks"] >= 1)

print(f"\n{ok} passed, {fail} failed")
raise SystemExit(1 if fail else 0)
