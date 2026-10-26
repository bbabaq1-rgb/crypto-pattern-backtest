"""validate_dclose_vol(R-020) 고정 — 판정 진리표·통계·대조군 성질·셀=R-002 정의·등재. 실행: python test_dclose_vol.py"""
import json
import random
import sys

import validate_dclose as vd
import validate_dclose_vol as v

fails = []


def check(n, c, d=""):
    print(("PASS " if c else "FAIL ") + n + ("" if c else f" — {d}"))
    c or fails.append(n)


# 1. 판정 진리표
check("3/3 REAL", v.judge(True, True, True, True) == "REAL_CELL_EFFECT")
check("2/3 MIXED", v.judge(True, True, False, True) == "MIXED")
check("1/3 NOISE", v.judge(True, True, False, False) == "NOISE")
check("선결 실패(평균차≤0) NOISE", v.judge(False, True, True, True) == "NOISE")
# 2. 백분위·부트
check("pctile 선형보간", abs(v.pctile([0, 1, 2, 3, 4], 0.95) - 3.8) < 1e-12 and v.pctile([], 0.5) is None)
d = [("2024-01-01", 0.01)] * 5 + [("2024-02-01", 0.02)] * 5
b = v.month_boot_means(d)
check("월 부트 결정론·양수 입력 하한>0", b == v.month_boot_means(d) and v.pctile(b, 0.025) > 0)
check("음수 입력 하한<0", v.pctile(v.month_boot_means([("2024-01-01", -0.01)] * 4), 0.025) < 0)
# 3. 대조군 성질
rows = [dict(o=1, h=1, l=1, c=1, v=1, date=f"2024-{1 + i // 28:02d}-{1 + i % 28:02d}") for i in range(200)]
el = set(v.eligible(rows))
a = v.draw_control(rows, 25, random.Random(1))
check("대조군: 개수 동일·적격 범위·중복 없음·시드 결정론", len(a) == 25 and set(a) <= el and len(set(a)) == 25
      and a == v.draw_control(rows, 25, random.Random(1)))
check("대조군: 적격 수 초과 요청은 상한 절단", len(v.draw_control(rows, 10_000, random.Random(1))) == len(el))
anch = [rows[40]["date"]] * 3 + [rows[100]["date"]] * 2
m = v.draw_control(rows, 5, random.Random(3), anchor_dates=anch)
chk = {}
for i in m:
    chk[rows[i]["date"][:7]] = chk.get(rows[i]["date"][:7], 0) + 1
check("C_month: 달별 신호 수 보존", chk == {rows[40]["date"][:7]: 3, rows[100]["date"][:7]: 2}, chk)
# 4. 두 arm 이 R-002 와 같은 청산 함수
check("collect2 가 vd.outcome_arm 사용·arm 은 D/D_close", v.ARMS2 == ("D", "D_close"))
# 5. 동결·셀 정의
check("동결: 시드 42·부트 1000·대조 30·95백분위", v.SEED == 42 and v.BOOT_N == 1000 and v.CTRL_REPS == 30 and v.CTRL_Q == 0.95)
cell = [c for c in vd.CELLS if c[0] == v.CELL]
check("셀 = R-002 vol_awakening_4h top30 4h", len(cell) == 1 and cell[0][1] == "4h" and cell[0][3] == "top30" and cell[0][4] is None)
check("동료 셀이 모두 R-002 CELLS 에 있음", all(any(c[0] == p for c in vd.CELLS) for p in v.PEERS))
# 6. 실거래 무접촉·등재
src = open("validate_dclose_vol.py", encoding="utf-8").read()
check("paper_executor/exchange import 없음", "import paper_executor" not in src and "import exchange" not in src)
check("DEPLOY_ON_PASS=False 명시", "DEPLOY_ON_PASS=False" in src)
wf = open(".github/workflows/dclose_vol.yml", encoding="utf-8").read()
check("워크플로: dispatch + 시험 실행", "workflow_dispatch" in wf and "python validate_dclose_vol.py" in wf and "python test_dclose_vol.py" in wf)
check("tests.yml 등재", "test_dclose_vol.py" in open(".github/workflows/tests.yml", encoding="utf-8").read())
reg = json.load(open("registry.json", encoding="utf-8"))
k = [x for x in reg if x.startswith("dclose_vol_prereg")]
check("registry 사전 등록", len(k) == 1 and reg[k[0]]["DEPLOY_ON_PASS"] is False, k)
print("\nFAILED: %s" % fails if fails else "\nALL PASS")
sys.exit(1 if fails else 0)
