"""test_iso_skip.py — validate_iso_skip 로직 고정 (네트워크 없음)"""
import random

import validate_iso_skip as d
import validate_vol_burst as vb

ok = fail = 0
def chk(n, c, x=""):
    global ok, fail
    if c: ok += 1
    else: fail += 1; print("  FAIL", n, x)

def T(a, b, ret, pat="engulfing", sym="S"):
    return dict(t_in=float(a), t_out=float(b), ret=ret, pattern=pat, sym=sym, vol=0.8, rank=1, tf="4h" if pat == d.TARGET else "1d")

print("§1 동결")
chk("상수", d.SEED == 75 and d.RAND_N == 200 and d.P_BOOT == 0.10 and d.MDD_TOL == 0.05 and d.TARGET == "vol_awakening_4h")
chk("DEPLOY False", d.DEPLOY_ON_PASS is False)

print("§2 c_open 인과성 — 미래 진입은 세지 않는다")
b = [T(10, 20, 0.0), T(12, 15, 0.0), T(30, 40, 0.0)]
ca = d.attach_c_open(b)
chk("겹침", ca[0]["c_open"] == 0 and ca[1]["c_open"] == 1)
chk("나중 거래 영향 없음", ca[2]["c_open"] == 0)
b2 = sorted(b + [T(35, 60, 0.0)], key=lambda t: t["t_in"])
ca2 = d.attach_c_open(b2)
chk("미래 진입 추가는 앞 거래 값을 안 바꿈", [t["c_open"] for t in ca2[:3]] == [t["c_open"] for t in ca[:3]])

print("§3 LO 는 train 에서만")
rows = [T(739000 + i, 739000 + i + 4, 0.01, pat=d.TARGET) for i in range(30)] + [T(739500 + i, 739501 + i, 0.01, pat=d.TARGET) for i in range(10)]
rc = d.attach_c_open(sorted(rows, key=lambda t: t["t_in"]))
lo = d.train_cut(rc, 739200.0)
chk("LO 정수", lo is not None)
rc2 = [dict(t) for t in rc]
for t in rc2:
    if t["t_in"] >= 739200: t["c_open"] = 99
chk("holdout 값 바꿔도 LO 불변", d.train_cut(rc2, 739200.0) == lo)
chk("train 표본<3 이면 None", d.train_cut(rc, 700000.0) is None)
chk("is_skipped 패턴·경계", d.is_skipped(dict(pattern=d.TARGET, c_open=lo), lo) and not d.is_skipped(dict(pattern="engulfing", c_open=0), lo) and not d.is_skipped(dict(pattern=d.TARGET, c_open=lo + 1), lo))

print("§4 analyse_split / 결정론")
r = random.Random(3)
tr = [dict(T(739000 + i * 2, 739000 + i * 2 + 3, r.uniform(-0.08, 0.1), pat=(d.TARGET if i % 2 == 0 else "engulfing"), sym=f"S{i%7}"), c_open=i % 5) for i in range(60)]
a = d.analyse_split(tr, 1, random.Random(1), n=20)
chk("제거 수", a["n_removed"] == sum(1 for t in tr if d.is_skipped(t, 1)))
chk("결정론", d.analyse_split(tr, 1, random.Random(1), n=20)["ctrl_p95"] == a["ctrl_p95"])
chk("LO None 이면 제거 0·iso==cur", d.analyse_split(tr, None, random.Random(1), n=5)["n_removed"] == 0)

print("§5 판정 — 하나라도 실패면 REJECTED")
def A(cc, ic, p95, cg=0.0, ig=0.1, cm=-0.3, im=-0.3):
    return dict(cur=dict(calmar=cc, cagr=cg, mdd=cm), iso=dict(calmar=ic, cagr=ig, mdd=im), ctrl_p95=p95)
v, f = d.judge(A(.5, 1, .8), A(.5, 1, .8), .02, -.01, -.01)
chk("전부 통과", v == "PASSED_NOT_DEPLOYED", f)
chk("I1", not d.judge(A(.5, 1, .8), A(.5, .4, .8), .02, -.01, -.01)[1]["I1"])
chk("I2", not d.judge(A(.5, 1, 1.5), A(.5, 1, .8), .02, -.01, -.01)[1]["I2"])
chk("I3 부트", not d.judge(A(.5, 1, .8), A(.5, 1, .8), .5, -.01, -.01)[1]["I3"])
chk("I3 전후반 역전", not d.judge(A(.5, 1, .8), A(.5, 1, .8), .02, -.01, .01)[1]["I3"])
chk("I4 MDD", not d.judge(A(.5, 1, .8), A(.5, 1, .8, im=-.4), .02, -.01, -.01)[1]["I4"])

print("§6 skipped_stats")
base = [dict(T(739000 + i, 739001 + i, (-0.03 if i % 2 else 0.01), pat=d.TARGET), c_open=i % 4) for i in range(40)]
s = d.skipped_stats(base, 739020.0, 1, random.Random(2))
chk("스킵 수", s["n"] == sum(1 for t in base if t["c_open"] <= 1) and s["kept_n"] == 40 - s["n"])

print(f"\n{ok} passed, {fail} failed")
raise SystemExit(1 if fail else 0)
