"""test_vol_burst.py — validate_vol_burst 로직 고정 (네트워크 없음)"""
import random

import validate_gap as g
import validate_vol_burst as v

ok = fail = 0
def chk(n, c, x=""):
    global ok, fail
    if c: ok += 1
    else: fail += 1; print("  FAIL", n, x)

print("§1 c_open — 데이터만, 자기 제외, 동시 진입 포함")
T = lambda a, b: dict(t_in=float(a), t_out=float(b), ret=0.0, pattern="x", sym="s", vol=1.0, rank=1, tf="4h")
tr = [T(0, 10), T(1, 3), T(2, 5), T(5, 6), T(5, 9)]
co = v.c_open_all(tr)
# i=2 (t=2): 0~10, 1~3 열려 있음 → 2.  i=3 (t=5): 0~10, 5~9(동시), (2~5 는 t_out==5 라 닫힘) → 2
chk("c_open 값", co == [0, 1, 2, 2, 2], co)
rng = random.Random(1)
big = [T(rng.randrange(50), 0) for _ in range(80)]
for t in big: t["t_out"] = t["t_in"] + rng.randrange(1, 6)
brute = [sum(1 for j, u in enumerate(big) if j != i and u["t_in"] <= t["t_in"] < u["t_out"]) for i, t in enumerate(big)]
chk("무차별 대입 일치", v.c_open_all(big) == brute)

print("§2 Spearman")
chk("완전 단조", abs(v.spearman([1, 2, 3, 4], [10, 20, 30, 40]) - 1) < 1e-12 and abs(v.spearman([1, 2, 3, 4], [4, 3, 2, 1]) + 1) < 1e-12)
chk("동률 처리(평균 순위)", abs(v.spearman([1, 1, 2, 2], [1, 2, 3, 4]) - 0.8944271909999159) < 1e-9, v.spearman([1, 1, 2, 2], [1, 2, 3, 4]))
chk("상수 입력은 None", v.spearman([1, 1, 1], [1, 2, 3]) is None)

print("§3 burst 순번 / month_key / demean")
tt = [dict(t_in=10.2, sym="B"), dict(t_in=10.1, sym="A"), dict(t_in=11.0, sym="C")]
chk("같은 날 순번", v.burst_ordinal(tt) == {1: 0, 0: 1, 2: 0}, v.burst_ordinal(tt))
xs, ys = v.demean_by_month([(1, 1, 1.0), (1, 3, 3.0), (2, 5, 9.0)])
chk("월 내 평균 0", abs(sum(xs)) < 1e-12 and abs(sum(ys)) < 1e-12)

print("§4 합성 신호 — 음의 관계를 잡고, 무관계는 기각")
def synth(slope, n=900, seed=3):
    r = random.Random(seed); out = []
    for i in range(n):
        t_in = 739000 + r.randrange(0, 700)
        out.append(dict(t_in=float(t_in), t_out=t_in + r.randrange(2, 8), pattern=v.TARGET if i % 2 == 0 else "fvg",
                        sym="S%d" % i, vol=1.0, rank=1, tf="4h", ret=0.0))
    co = v.c_open_all(out)
    for t, c in zip(out, co):
        t["ret"] = slope * c + r.gauss(0, 0.05)
    return out
cutd = 739000 + 350.0
rs_, _, _ = v.analyse(synth(-0.01), cutd)
vd, fl = v.judge(rs_)
chk("음의 기울기 → SELECTION_BIAS", vd.startswith("SELECTION_BIAS"), (vd, fl))
rn_, _, _ = v.analyse(synth(0.0), cutd)
vn, fn = v.judge(rn_)
chk("무관계 → NO_SELECTION_BIAS", vn == "NO_SELECTION_BIAS", (vn, fn, rn_["rho"]))
rp_, _, _ = v.analyse(synth(+0.01), cutd)
chk("양의 기울기 → NO_SELECTION_BIAS", v.judge(rp_)[0] == "NO_SELECTION_BIAS")

print("§5 judge 경계 — 한 기준만 실패해도 기각")
good = dict(rho=-0.1, p_boot=0.02, rho_tr=-0.1, rho_ho=-0.1, ter_tr=(0.01, 0, -0.01, (1, 1, 1)), ter_ho=(0.01, 0, -0.01, (1, 1, 1)),
            ter_full=(0.01, 0.0, -0.01, (1, 1, 1)), rho_dm=-0.1, p_dm=0.02)
chk("전부 통과 → WITHIN_MONTH", v.judge(good)[0] == "SELECTION_BIAS_WITHIN_MONTH")
chk("월 내 약함 → TIME_EFFECT", v.judge(dict(good, p_dm=0.5))[0] == "SELECTION_BIAS_TIME_EFFECT")
for k, bad in (("S1", dict(p_boot=0.2)), ("S2", dict(rho_ho=0.01)), ("S3", dict(ter_ho=(0.0, 0, 0.01, (1, 1, 1)))),
               ("S4", dict(ter_full=(0.0, 0.01, -0.01, (1, 1, 1))))):
    vd2, fl2 = v.judge(dict(good, **bad))
    chk(f"{k} 실패 → NO_SELECTION_BIAS", vd2 == "NO_SELECTION_BIAS" and not fl2[k], (vd2, fl2))

print("§6 validate_gap.simulate open_at 훅은 동작 불변")
r = random.Random(9); trs = []
for i in range(120):
    d = float(739000 + r.randrange(200))
    trs.append(dict(pattern=r.choice(["engulfing", "fvg", v.TARGET]), t_in=d, t_out=d + r.randrange(1, 9), ret=r.uniform(-.1, .15),
                    sym="S%d" % i, vol=r.uniform(.4, 1.5), rank=r.randrange(30), tf="4h" if i % 3 == 0 else "1d"))
trs.sort(key=lambda t: t["t_in"])
a = g.simulate(trs); oa = {}; b = g.simulate(trs, open_at=oa)
chk("결과 동일", all(abs(a[k] - b[k]) < 1e-12 for k in ("final", "cagr", "mdd")) and a["took"] == b["took"])
chk("체결마다 open_at 기록, 상한 MAX_POS 미만", set(oa) == set(b["took"]) and all(0 <= x < 13 for x in oa.values()))

print("§7 동결 상수 / DEPLOY")
chk("상수", v.SEED == 72 and v.BOOT_N == 1000 and v.P_BOOT == 0.10 and v.TARGET == "vol_awakening_4h" and v.DEPLOY_ON_PASS is False)
print(f"\n{ok} 통과, {fail} 실패")
raise SystemExit(1 if fail else 0)
