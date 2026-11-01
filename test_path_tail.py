"""test_path_tail.py — validate_path_tail 로직 고정 (네트워크 없음)"""
import random
from datetime import date

import validate_path_tail as pt
import validate_portfolio as vp

ok = fail = 0
def chk(n, c, x=""):
    global ok, fail
    if c: ok += 1
    else: fail += 1; print("  FAIL", n, x)

rng = random.Random(4)
trs = []
for i in range(300):
    d = float(date.fromordinal(739000 + rng.randrange(500)).toordinal())
    trs.append(dict(pattern="fvg", t_in=d, t_out=d + rng.randrange(1, 9), ret=rng.uniform(-.1, .15), sym="S%d" % i,
                    vol=rng.uniform(.4, 1.5), rank=rng.randrange(30), tf="1d"))
trs.sort(key=lambda t: t["t_in"])

print("§1 동결")
chk("현행 셀", pt.CURRENT == (0.015, 13) and pt.CURRENT in pt.cells())
chk("상수", pt.BOOT_N == 300 and pt.SEED == 84 and pt.Q_TAIL == 0.05 and pt.MED_DROP == 0.75 and pt.DEPLOY_ON_PASS is False)

print("§2 재표집")
for b in pt.BLOCKS:
    idx = pt.boot_index(trs, b, random.Random(1))
    chk(f"{b} 길이 n·범위", len(idx) == len(trs) and all(0 <= j < len(trs) for j in idx))
    bt = pt._reassign(trs, idx)
    chk(f"{b} 날짜 골격 유지", [t["t_in"] for t in bt] == [t["t_in"] for t in trs])
chk("B20 은 연속 20개 런", all(b - a == 1 for a, b in zip(pt.boot_index(trs, "B20", random.Random(2))[:19], pt.boot_index(trs, "B20", random.Random(2))[1:20])))
i7 = pt.boot_index(trs, "T7", random.Random(3))
wk = {int(t["t_in"] // 7) for t in trs}
chk("T7 은 창 단위(한 창의 거래가 통째로)", len(set(int(trs[j]["t_in"] // 7) for j in i7)) <= len(wk))

print("§3 분위·판정")
chk("분위", pt.percentile_le([1, 2, 3, 4], 2) == 0.5)
chk("NO_TAIL", pt.classify(0.2, 0.2, 4, 2) == "NO_TAIL")
chk("BLOCK_INSENSITIVE", pt.classify(0.01, 0.01, 4, 3.5) == "BLOCK_INSENSITIVE")
chk("PATH_CLUSTER", pt.classify(0.01, 0.2, 4, 2) == "PATH_CLUSTER")
chk("UNLUCKY_TAIL", pt.classify(0.01, 0.01, 4, 2) == "UNLUCKY_TAIL")

print("§4 시뮬 동치")
a = pt.run_cell(trs, pt.CURRENT); b = vp.simulate(trs, "current")
chk("현행 셀 = vp.simulate", abs(a["final"] - b["final"]) < 1e-9)

print(f"{ok} 통과 / {fail} 실패")
raise SystemExit(1 if fail else 0)
