"""validate_dclose(R-002) 고정 — 청산 함수 성질·판정 진리표·셀=실거래 범위·워크플로/tests.yml 등재. 실행: python test_dclose.py"""
import json
import random
import sys

import detlib
import method_s as ms
import scheduler as sch
import validate_dclose as vd

fails = []


def check(n, c, d=""):
    print(("PASS " if c else "FAIL ") + n + ("" if c else f" — {d}"))
    c or fails.append(n)


def flat(n=60, px=100.0):
    return [dict(o=px, h=px, l=px, c=px, v=1, date=f"2024-{1 + i // 28:02d}-{1 + i % 28:02d}", ts=i * 86400000) for i in range(n)]


lab = lambda j: "bear"
# 1. 저가만 −8% 를 찍고 종가 회복 → D 는 손절, D_close 는 보유
rows = flat()
rows[35]["l"] = 90.0            # 저가 −10%
r_d = ms.outcome(rows, 30, "long", set(), lab, use_regime=True, max_hold=30)
r_c = vd.outcome_d_close(rows, 30, lab)
check("저가 스파이크: D 손절 / D_close 보유(만기)", r_d[2] == "stop" and r_c[2] == "maxhold", (r_d, r_c))
# 2. 종가가 −9% → D_close 는 그 종가(−9%−fee)에 청산
rows = flat(); rows[35]["c"] = 91.0; rows[35]["l"] = 90.5
r_c = vd.outcome_d_close(rows, 30, lab)
check("종가 손절: 종가 기준 실현(−9%)", r_c[2] == "sl_close" and abs(r_c[0] - (-0.09 - detlib.FEE)) < 1e-12 and r_c[1] == 5, r_c)
# 3. 재해 손절 −15% 는 저가로 선행
rows = flat(); rows[33]["l"] = 80.0; rows[33]["c"] = 95.0
r_c = vd.outcome_d_close(rows, 30, lab)
check("재해 손절 −15% (저가)", r_c[2] == "cat_stop" and abs(r_c[0] - (-0.15 - detlib.FEE)) < 1e-12, r_c)
r_n = vd.outcome_d_close(rows, 30, lab, cat=None)
check("cat=None 이면 재해 손절 없음(진단 arm)", r_n[2] == "maxhold", r_n)
# 4. 손절 없는 경로에서 D 와 완전 동일(레짐 전환·만기 포함)
random.seed(7)
same = True
for k in range(300):
    px, rr = 100.0, []
    for i in range(80):
        nxt = px * (1 + random.gauss(0, 0.01))
        rr.append(dict(o=px, h=max(px, nxt) * 1.001, l=min(px, nxt) * 0.999, c=nxt, v=1, date=f"2024-{1 + i // 28:02d}-{1 + i % 28:02d}"))
        px = nxt
    sw = random.randint(32, 70)
    lb = lambda j, sw=sw: "bear" if j < sw else "bull_btc"
    a = ms.outcome(rr, 30, "long", set(), lb, use_regime=True, max_hold=30)
    b = vd.outcome_d_close(rr, 30, lb)
    if not any(rr[j]["l"] <= rr[30]["c"] * 0.92 for j in range(31, 61)):
        same &= (abs(a[0] - b[0]) < 1e-12 and a[1] == b[1] and a[2] == b[2])
check("손절 미발동 경로에서 D 와 동일(300판, 레짐 전환 포함)", same)
# 5. 동결 상수
check("동결: 재해 15% · 손절 8% · 30봉 · 365일 · 시드 42", vd.CAT == 0.15 and vd.STOP_D == 0.08 and vd.HOLD_D == 30
      and vd.HOLDOUT_DAYS == 365 and vd.SEED == 42 and vd.ARMS == ("D", "D_close", "D_close_nocat"))
# 6. 판정 진리표
ok = dict(P1=True, P2=True, P3=True, P4=True, P5=True, P6=True)
check("PASSED", vd.judge(ok) == "PASSED")
check("MIXED(P1·P2 통과, 일부 실패)", vd.judge({**ok, "P5": False}) == "MIXED")
check("REJECTED(P1 실패)", vd.judge({**ok, "P1": False}) == "REJECTED")
check("REJECTED(P2 실패)", vd.judge({**ok, "P2": False}) == "REJECTED")
# 7. 통계
d = [("2024-01-01", 0.01)] * 5 + [("2024-02-01", 0.02)] * 5
m, t = vd.mean_t(d)
check("mean_t 부호·값", abs(m - 0.015) < 1e-12 and t > 2, (m, t))
check("월 부트 결정론", vd.month_boot_nonpos(d) == vd.month_boot_nonpos(d))
check("양수 전용 입력은 부트 비율 0", vd.month_boot_nonpos(d) == 0.0)
neg = [("2024-01-01", -0.01)] * 4
check("음수 입력은 부트 비율 1", vd.month_boot_nonpos(neg) == 1.0)
# 8. 셀 = 실거래 배포 범위
u = json.load(open("universe.json", encoding="utf-8"))
cells = {c[0]: c for c in vd.CELLS}
ad = {a["pattern"]: a for a in u.get("adopted_patterns", []) + u.get("adopted_4h_patterns", [])}
check("배포 중 1d/4h 롱 패턴(ih·4h 4종)이 셀에 전부 있음", set(ad) <= set(cells) | {"marubozu"}, set(ad) - set(cells))
check("engulfing/fvg(FOCUS) 포함", set(sch.FOCUS) <= set(cells))
check("코호트 = scheduler.PATTERN_UNIVERSE", sch.PATTERN_UNIVERSE.get("engulfing") == "top30" and cells["engulfing"][3] == "top30"
      and sch.PATTERN_UNIVERSE.get("fvg") == "top30" and cells["fvg"][3] == "top30"
      and sch.PATTERN_UNIVERSE.get("inverted_hammer") == "majors" and cells["inverted_hammer"][3] == "majors")
check("정지 패턴 marubozu 제외", "marubozu" not in cells)
# 9. 이 시험이 실거래 코드를 바꾸지 않음
src = open("validate_dclose.py", encoding="utf-8").read()
check("실거래 모듈 미수정 — paper_executor/exchange import 없음", "import paper_executor" not in src and "import exchange" not in src)
check("DEPLOY_ON_PASS 문구(자율 반영 없음) 명시", "DEPLOY_ON_PASS=False" in src)
# 10. 등재
wf = open(".github/workflows/dclose.yml", encoding="utf-8").read()
check("워크플로: dispatch + 시험 실행", "workflow_dispatch" in wf and "python validate_dclose.py" in wf and "python test_dclose.py" in wf)
tw = open(".github/workflows/tests.yml", encoding="utf-8").read()
check("tests.yml 등재", "test_dclose.py" in tw)
reg = json.load(open("registry.json", encoding="utf-8"))
k = [x for x in reg if x.startswith("dclose_prereg")]
check("registry 사전 등록 항목 존재", len(k) == 1 and reg[k[0]].get("DEPLOY_ON_PASS") is False, k)
print("\nFAILED: %s" % fails if fails else "\nALL PASS")
sys.exit(1 if fails else 0)
