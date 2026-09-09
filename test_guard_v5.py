"""
test_guard_v5.py — 확인 프레임 v5 고정 (2026-09-09, 사용자 결정 "1,2는 진행").

지키는 성질:
  · v4 파일은 불변(사전 등록본) — v5 는 v4 의 기계를 import 만 하고 판정만 바꾼다
  · 규칙 1: B 는 판정에 안 들어간다 — B 가 아무리 나빠도 판정이 안 바뀐다
  · 규칙 2: 레짐 셀 · n<200 · boot_p 단독 탈락 → INCONCLUSIVE. ALL 셀·n≥200·다른 사유는 종전대로
  · A 게이트 문턱·OOS A·비용 스트레스는 v4 와 동일(상수 재정의 없음)
  · DEPLOY_ON_PASS=False, 실거래 경로 미등재
"""
import inspect
import json

import validate_guard_v4 as g4
import validate_guard_v5 as V

fails = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


check("SMALL_N=200", V.SMALL_N == 200)
check("JUDGE_B=False (규칙 1)", V.JUDGE_B is False)
check("DEPLOY_ON_PASS=False", V.DEPLOY_ON_PASS is False)
check("셀 = v4 11 + 4h adopted 3 = 14", len(V.CELLS) == 14 and V.CELLS[:11] == g4.CELLS)
check("v4 상수를 재정의하지 않는다 (WIN_MIN/ALPHA/OOS_MIN_N/STRESS_REQUIRED/SPLIT)",
      all(f"{c} =" not in inspect.getsource(V).split("def _only_boot_p")[0].replace("SPLIT = g4.SPLIT_DATE", "")
          for c in ("WIN_MIN", "ALPHA", "OOS_MIN_N", "STRESS_REQUIRED")))
check("v4 파일 자체는 import 만 한다(수정 없음 — verdict 원본이 그대로 호출된다)",
      "g4.verdict(" in inspect.getsource(V.main))

# ── 규칙 1: B 무관 ──────────────────────────────────────────────────────────
good_a = dict(n=300, mean=0.03, win=0.5, boot_p=0.01, edge=0.02)
tg_pass = dict(verdict="PASSED", reason="")
oos_good = dict(n=50, mean=0.03, win=0.5, boot_p=0.01)
cell_all = dict(regime="ALL")
vs = inspect.getsource(V.verdict_v5)
check("verdict_v5 시그니처에 B 인자가 없다", "train_b" not in vs and "oos_b" not in vs)
vd, f, r2 = V.verdict_v5(cell_all, good_a, tg_pass, oos_good, 0.03)
check("A 전부 통과 → CONFIRMED (B 가 무엇이든)", vd == "CONFIRMED" and not f, (vd, f))

# ── 규칙 2 ──────────────────────────────────────────────────────────────────
cell_reg = dict(regime="bull_btc")
small_a = dict(n=111, mean=0.06, win=0.45, boot_p=0.368, edge=0.01)
tg_bp = dict(verdict="REJECTED", reason="boot_p=0.368")
vd, f, r2 = V.verdict_v5(cell_reg, small_a, tg_bp, oos_good, 0.07)
check("레짐 셀 · n<200 · boot_p 단독 탈락 → INCONCLUSIVE (규칙 2)", vd == "INCONCLUSIVE" and r2 is True, (vd, f))
vd, f, r2 = V.verdict_v5(cell_all, small_a, tg_bp, oos_good, 0.07)
check("ALL 셀은 규칙 2 대상 아님 → 종전대로 train A gate 실패", vd != "INCONCLUSIVE" and "train A gate" in f, (vd, f))
big_a = dict(n=500, mean=0.06, win=0.45, boot_p=0.368, edge=0.01)
vd, f, r2 = V.verdict_v5(cell_reg, big_a, tg_bp, oos_good, 0.07)
check("n>=200 이면 규칙 2 적용 안 됨", vd != "INCONCLUSIVE" and r2 is False, (vd, f))
tg_multi = dict(verdict="REJECTED", reason="OOS 1/4, boot_p=0.368")
vd, f, r2 = V.verdict_v5(cell_reg, small_a, tg_multi, oos_good, 0.07)
check("boot_p 외 다른 사유가 있으면 규칙 2 적용 안 됨", r2 is False and "train A gate" in f, (vd, f))
check("_only_boot_p 판별", V._only_boot_p("boot_p=0.368") and not V._only_boot_p("n<20, boot_p=0.5") and not V._only_boot_p(""))

# ── v4 와 같은 나머지 ────────────────────────────────────────────────────────
bad_a = dict(n=100, mean=-0.01, win=0.3, boot_p=0.5, edge=-0.01)
vd, f, r2 = V.verdict_v5(cell_reg, bad_a, tg_pass, oos_good, 0.01)
check("전체 A 음수/승률<35% → REJECTED (v4 동일)", vd == "REJECTED")
oos_thin = dict(n=5, mean=0.03, win=0.5, boot_p=0.01)
vd, f, r2 = V.verdict_v5(cell_all, good_a, tg_pass, oos_thin, 0.03)
check("OOS n<10 → INCONCLUSIVE (v4 동일)", vd == "INCONCLUSIVE")
oos_neg = dict(n=50, mean=-0.01, win=0.3, boot_p=0.6)
vd, f, r2 = V.verdict_v5(cell_all, good_a, tg_pass, oos_neg, -0.01)
check("OOS A 실패 → UNCONFIRMED_SHADOW (v4 동일)", vd == "UNCONFIRMED_SHADOW" and "OOS A" in f)
vd, f, r2 = V.verdict_v5(cell_all, good_a, tg_pass, dict(n=50, mean=0.001, win=0.5, boot_p=0.01), 0.001)
check("비용 0.4% 스트레스 (v4 동일)", "OOS cost@0.4%" in f)

# ── 무관 ────────────────────────────────────────────────────────────────────
ms = inspect.getsource(V)
check("실거래 엔진 import 없음", "import paper_executor" not in ms and "import exchange" not in ms)
check("스케줄러가 모른다", "guard_v5" not in open("scheduler.py", encoding="utf-8").read())
check("registry 기록", "frame_v5_2026_09_09" in json.load(open("registry.json", encoding="utf-8")))
wf = open(".github/workflows/guard_v5.yml", encoding="utf-8").read()
check("워크플로가 테스트를 먼저 돌린다", "python test_guard_v5.py" in wf)
check("tests.yml 등재", "test_guard_v5.py" in open(".github/workflows/tests.yml", encoding="utf-8").read())

print(f"\n{len(fails)} failed")
raise SystemExit(1 if fails else 0)
