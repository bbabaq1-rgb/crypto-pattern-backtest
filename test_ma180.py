"""
MA 장기 이평 돌파 사전 등록 시험(detector_ma180_breakout + validate_ma180) 고정 — 2026-09-06.

확인 대상:
  - 디텍터: sma 정확성 · fresh(20봉 이상 아래) 요건 · decisive(×1.02) 필터 · 재돌파 제외 · 인과성
  - study_ma_breakout(탐색 스터디)와 **같은 신호 집합** — 두 구현이 갈라지지 않게 고정
  - 사전 등록 상수 동결: MA180/BELOW_MIN 20/DECISIVE 1.02, 주 판정 셀, holdout 365, TRAIN_MIN_RATIO
  - **기록용 성질**: DEPLOY_ON_PASS=False, registry/universe/scheduler 어디에도 미등재, 실거래 코드 미import
  - C2b(train 자체 게이트 + train n >= holdout n/2) 와 confirmed 의 4조건 합성
  - 워크플로·tests.yml 등재

실행: python test_ma180.py
"""
import json
import random
import sys

import detector_ma180_breakout as det
import study_ma_breakout as sm
import validate_ma180 as vm
import validate_revival as vr

fails = []


def check(n, c, d=""):
    print(("PASS " if c else "FAIL ") + n + ("" if c else f" — {d}"))
    c or fails.append(n)


def rows_from(closes, vol=100.0):
    return [dict(o=c, h=c * 1.01, l=c * 0.99, c=c, v=vol, date=f"2024-{1+i//28:02d}-{1+i%28:02d}", ts=i * 86_400_000)
            for i, c in enumerate(closes)]


# ── 1. 디텍터 정의 ───────────────────────────────────────────────────────────
check("sma: 초기 None, 값 정확", det.sma([1, 2, 3, 4, 5], 3) == [None, None, 2.0, 3.0, 4.0])
check("sma 는 study 와 동일", det.sma([3.0, 1.0, 4.0, 1.5, 9.0, 2.6], 3) == sm.sma([3.0, 1.0, 4.0, 1.5, 9.0, 2.6], 3))

up = [100.0 + 0.1 * i for i in range(200)]
rows = rows_from(up + [90.0] * 60 + [130.0] * 30)          # 60봉 아래 → 강한 돌파
check("fresh + decisive 돌파 1건(위치 260)", det.detect(rows) == [260], det.detect(rows))
check("인과성: rows[:i+1] 만으로 같은 신호", det.detect(rows[:261]) == [260])
rows_short = rows_from(up + [90.0] * 5 + [130.0] * 30)     # 5봉만 아래 → 재돌파, 제외
check("BELOW_MIN 미만 아래(재돌파) 는 신호 아님", det.detect(rows_short) == [], det.detect(rows_short))
rows_weak = rows_from(up + [90.0] * 60 + [107.0] * 30)     # MA≈106 → 돌파지만 ×1.02 미달
check("decisive: 약한 돌파 탈락", det.detect(rows_weak) == [], det.detect(rows_weak))
check("raw: 약한 돌파도 신호", len(det.detect(rows_weak, filt="raw")) == 1)
check("교차 없으면 신호 없음", det.detect(rows_from([100.0] * 300)) == [])
check("MA 창 인자 반영(250 은 데이터 부족)", det.detect(rows, ma_n=250) == [])
try:
    det.detect(rows, filt="nope"); bad = False
except ValueError:
    bad = True
check("알 수 없는 filt 는 ValueError", bad)

# study 와 신호 집합 동일 (무작위 시계열 25개)
ok_d = ok_r = True
for seed in range(25):
    random.seed(seed)
    px, rr = 100.0, []
    for i in range(600):
        px *= (1 + random.gauss(0, 0.035))
        rr.append(px)
    r = rows_from(rr)
    cr, ma = sm.crosses(r, 180)
    ok_d &= det.detect(r) == [i for i, k in cr if k == "fresh" and sm.passes("decisive", r, i, ma)]
    ok_r &= det.detect(r, filt="raw") == [i for i, k in cr if k == "fresh"]
check("study_ma_breakout 와 신호 집합 동일 (decisive)", ok_d)
check("study_ma_breakout 와 신호 집합 동일 (raw)", ok_r)

# ── 2. 사전 등록 상수 ────────────────────────────────────────────────────────
check("동결 상수 MA180 / BELOW_MIN 20 / DECISIVE 1.02", det.MA_N == 180 and det.BELOW_MIN == 20 and det.DECISIVE == 1.02)
check("주 판정 셀 = (ma180_decisive, bull_btc)", vm.PRIMARY == ("ma180_decisive", "bull_btc"))
check("판정 코호트 = 실거래 코호트 top30", vm.CONFIRM_COHORT == "top30" == vr.CONFIRM_COHORT)
check("holdout 365일 / 최소 10건 / TRAIN_MIN_RATIO 0.5", vm.HOLDOUT_DAYS == 365 and vm.HOLDOUT_MIN_N == 10 and vm.TRAIN_MIN_RATIO == 0.5)
check("셀 목록에 주 판정 셀이 있고, 나머지는 진단", ("ma180_decisive", 180, "decisive") in [(c[0], c[1], c[2]) for c in vm.CELLS]
      and len([1 for cid, _, _, gs in vm.CELLS for g in gs if (cid, g) == vm.PRIMARY]) == 1)
check("청산은 방식D(1d) — vr.live_outcome 경유", vm.TF == "1d" and vm.DIRECTION == "long")

# ── 3. 기록용 성질 ──────────────────────────────────────────────────────────
check("DEPLOY_ON_PASS=False (통과해도 자동 반영 없음)", vm.DEPLOY_ON_PASS is False)
u = json.load(open("universe.json", encoding="utf-8"))
adopted = {a["pattern"] for k in ("adopted_patterns", "adopted_4h_patterns", "adopted_1h_patterns") for a in u.get(k, [])}
check("universe adopted 어디에도 미등재", not any(p.startswith("ma180") or p.startswith("ma200") for p in adopted), adopted)
reg = json.load(open("registry.json", encoding="utf-8"))
deployed = {k for k, v in reg.items() if isinstance(v, dict) and v.get("status") == "deployed"}
check("registry deployed 에 미등재", not any("ma180" in k or "ma200" in k for k in deployed))
sch = open("scheduler.py", encoding="utf-8").read()
check("scheduler 가 이 디텍터를 import 하지 않음", "detector_ma180_breakout" not in sch)
src = open("validate_ma180.py", encoding="utf-8").read()
check("시험 모듈은 paper_executor 를 import 하지 않음", "import paper_executor" not in src)
check("기록용 명시", "기록용" in src and "실거래에 반영하지 않는다" in src)

# ── 4. C2b · confirmed 합성 ─────────────────────────────────────────────────
def sig(i, ret, dstr):
    return dict(sym="X", date=dstr, regime="bull_btc", ret=ret, hold=5, reason="target", stop_pct=0.08,
                vol=0.8, exit_date=dstr, t_in=738000.0 + i, t_out=738000.0 + i + 5)


pool = [-0.02] * 200
train_good = [sig(i, 0.10 if i % 3 else -0.05, f"2023-{1+i%12:02d}-{1+i%27:02d}") for i in range(40)]
hold_few = [sig(100 + i, 0.08, f"2026-{1+i%8:02d}-{1+i%27:02d}") for i in range(12)]
cells_ok = {"top30": dict(gate={}, sigs=train_good + hold_few), "all": dict(gate={}, sigs=[])}
cf = vm.confirm_ma180(cells_ok, "2025-09-06", 1000, pool)
check("C2b: train 충분·게이트 통과 → True", cf["c2b_train"] is True, (cf["train_n"], cf["train_gate"]["verdict"]))
check("C2b: train n 기록", cf["train_n"] == 40)

train_tiny = [sig(i, 0.10, f"2023-{1+i%12:02d}-{1+i%27:02d}") for i in range(3)]
hold_many = [sig(100 + i, 0.08, f"2026-{1+i%8:02d}-{1+i%27:02d}") for i in range(30)]
cf2 = vm.confirm_ma180({"top30": dict(gate={}, sigs=train_tiny + hold_many), "all": dict(gate={}, sigs=[])},
                       "2025-09-06", 1000, pool)
check("C2b: train 이 holdout 의 절반 미만 → False (vwap_rev 형 통과 차단)", cf2["c2b_train"] is False)
check("C2b False 면 confirmed 도 False", cf2["confirmed"] is False)
for c in (cf, cf2):
    comp = bool(c["c1_live_cohort"] and c["c2_holdout"] and c["c2b_train"] and c["c3_equity"])
    check(f"confirmed = C1∧C2∧C2b∧C3 (train_n={c['train_n']})", c["confirmed"] == comp)
check("vr.confirm 의 C1/C2/C3 키를 그대로 유지", {"c1_live_cohort", "c2_holdout", "c3_equity", "holdout", "equity"} <= set(cf))

# ── 5. 등재 ─────────────────────────────────────────────────────────────────
wf = open(".github/workflows/ma180.yml", encoding="utf-8").read()
check("워크플로: 테스트 → 시험 → 아티팩트", "python test_ma180.py" in wf and "python validate_ma180.py" in wf and "_ma180.json" in wf)
check("tests.yml 등재", "test_ma180.py" in open(".github/workflows/tests.yml", encoding="utf-8").read())

print(f"\n{len(fails)} failed")
sys.exit(1 if fails else 0)
