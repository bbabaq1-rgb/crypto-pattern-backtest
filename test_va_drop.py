"""test_va_drop.py — validate_va_drop 로직 고정 (네트워크 없음)"""
import random

import validate_gap as g
import validate_portfolio as vp
import validate_va_drop as d

ok = fail = 0
def chk(n, c, x=""):
    global ok, fail
    if c: ok += 1
    else: fail += 1; print("  FAIL", n, x)

def T(a, b, ret, pat="engulfing", sym="S", vol=0.8, rank=1, tf="1d"):
    return dict(t_in=float(a), t_out=float(b), ret=ret, pattern=pat, sym=sym, vol=vol, rank=rank, tf=tf)

print("§1 동결 상수 · 안전")
chk("상수", d.SEED == 89 and d.RAND_N == 200 and d.P_BOOT == 0.10 and d.MDD_TOL == 0.05 and d.TARGET == "vol_awakening_4h")
chk("DEPLOY_ON_PASS False", d.DEPLOY_ON_PASS is False)

print("§2 run: 공통 span 연율화 · g.simulate 와 일치")
r = random.Random(5)
tr = [T(739000 + i * 2, 739000 + i * 2 + 3, r.uniform(-0.08, 0.1), pat=("vol_awakening_4h" if i % 3 == 0 else "engulfing"),
        sym=f"S{i%7}", tf=("4h" if i % 3 == 0 else "1d")) for i in range(60)]
sp = d.span_of(tr)
a = d.run(tr, sp); b = g.simulate(tr)
chk("동일 span 이면 simulate 와 CAGR 같음", abs(a["cagr"] - b["cagr"]) < 1e-9 and a["taken"] == b["taken"])
chk("더 긴 span 이면 연율화가 완만", abs(d.run(tr, sp * 2)["cagr"]) <= abs(a["cagr"]) + 1e-12)
chk("빈 집합", d.run([], 10.0)["taken"] == 0)

print("§3 percentile / split")
chk("p95", abs(d.percentile(list(range(101)), 0.95) - 95) < 1e-9)
a1, a2 = d.split_trades(tr, 739060.0)
chk("분할 합집합", len(a1) + len(a2) == len(tr) and all(t["t_in"] < 739060 for t in a1))

print("§4 analyse_split: 제거 수 = 대조 제거 수, 대조는 타깃 패턴을 안 건드림")
res = d.analyse_split(tr, random.Random(1), n=20)
chk("제거 수", res["n_removed"] == sum(t["pattern"] == "vol_awakening_4h" for t in tr))
chk("p95 존재", res["ctrl_p95"] is not None)
chk("결정론", d.analyse_split(tr, random.Random(1), n=20)["ctrl_p95"] == res["ctrl_p95"])

print("§5 판정 규칙 — 하나라도 실패면 REJECTED")
def A(cur_c, nov_c, p95, cur_cg=0.0, nov_cg=0.1, cur_m=-0.3, nov_m=-0.3):
    return dict(cur=dict(calmar=cur_c, cagr=cur_cg, mdd=cur_m), nov=dict(calmar=nov_c, cagr=nov_cg, mdd=nov_m), ctrl_p95=p95)
v, f = d.judge(A(0.5, 1.0, 0.8), A(0.5, 1.0, 0.8), 0.02, -0.001)
chk("전부 통과", v == "PASSED_NOT_DEPLOYED" and all(f.values()), f)
v, f = d.judge(A(0.5, 1.0, 0.8), A(0.5, 0.4, 0.8), 0.02, -0.001)
chk("K1 실패(holdout 악화)", v == "REJECTED" and not f["K1"])
v, f = d.judge(A(0.5, 1.0, 1.5), A(0.5, 1.0, 0.8), 0.02, -0.001)
chk("K2 실패(대조 p95 미달)", v == "REJECTED" and not f["K2"])
v, f = d.judge(A(0.5, 1.0, 0.8), A(0.5, 1.0, 0.8), 0.5, -0.001)
chk("K3 실패(부트)", v == "REJECTED" and not f["K3"])
v, f = d.judge(A(0.5, 1.0, 0.8), A(0.5, 1.0, 0.8), 0.02, 0.01)
chk("K3 실패(holdout 평균 양수)", v == "REJECTED" and not f["K3"])
v, f = d.judge(A(0.5, 1.0, 0.8), A(0.5, 1.0, 0.8, nov_m=-0.4), 0.02, -0.001)
chk("K4 실패(MDD 악화>5%p)", v == "REJECTED" and not f["K4"])

print("§6 target_stats")
base = [T(739000 + i, 739001 + i, (0.02 if i % 2 else -0.05), pat="vol_awakening_4h") for i in range(40)] + [T(739100, 739101, 0.01)]
s = d.target_stats(base, 739020.0, random.Random(2))
chk("n·분할", s["n"] == 40 and s["n_tr"] == 20 and s["n_ho"] == 20)

print(f"\n{ok} 통과 / {fail} 실패")
raise SystemExit(1 if fail else 0)
