"""
test_tp_regime.py — 배리어 격자 레짐 분해 사전 등록 고정 (2026-09-09).

지키는 성질:
  · 격자·규칙·비용은 tp_1h 에서 **import** 한다 — 재정의해서 몰래 바꾸지 않는다
  · 주 판정 8셀 = 사용자 지목 4셀 × {bull_btc, bull_altseason}, Holm m=8
  · 무작위 베이스라인이 **레짐 매칭**이다 — 같은 레짐 봉에서만 뽑는다
  · 커버리지 미달은 REJECTED 가 아니라 INCONCLUSIVE
  · 드리프트 수확(수익 기준 통과·엣지 없음)은 숨기지 않고 따로 표기된다
  · DEPLOY_ON_PASS=False, 실거래 경로 미등재
"""
import inspect
import json

import validate_tp_1h as T
import validate_tp_regime as R

fails = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


# ── 동결 ────────────────────────────────────────────────────────────────────
check("주 판정 TF 1h, 1d 는 진단", R.PRIMARY_TF == "1h" and R.TFS == ("1h", "1d"))
check("레짐 4 (bull_btc/bull_altseason/bear/ALL)",
      R.REGIMES == ("bull_btc", "bull_altseason", "bear", "ALL"), R.REGIMES)
check("주 판정 = 사용자 4셀 × 상승 레짐 2 = 8", len(R.PRIMARY) == 8
      and all(m in T.PRIMARY_ARMS and g in ("bull_btc", "bull_altseason") for m, g in R.PRIMARY))
check("격자·셀 이름은 tp_1h 것을 그대로 쓴다(재정의 없음)",
      R.PRIMARY_CELLS is T.PRIMARY_ARMS and "TP_LEVELS =" not in inspect.getsource(R)
      and "SL_LEVELS =" not in inspect.getsource(R))
check("커버리지 하한 1h 100 / 1d 20, holdout 10", R.COV_MIN == {"1h": 100, "1d": 20} and R.HOLDOUT_MIN_N == 10)
check("DEPLOY_ON_PASS=False", R.DEPLOY_ON_PASS is False)

# ── 레짐 매칭 베이스라인 ────────────────────────────────────────────────────
def bar(o, h, l, c, d, ts):
    return dict(date=d, ts=ts, o=o, h=h, l=l, c=c, v=1)

rows = [bar(100, 100.3, 99.7, 100, f"2024-01-{i+1:02d}", i) for i in range(60)]
regmap = {f"2024-01-{i+1:02d}": ("bull_btc" if i < 45 else "bear") for i in range(60)}   # 무작위 풀(i>=30)에 두 레짐이 다 들어가게
rb = R.random_baseline({"AAA": rows}, regmap, "long", 50)
check("무작위 베이스라인이 레짐별로 따로 나온다", "bull_btc" in rb["T1S8"] and "bear" in rb["T1S8"] and "ALL" in rb["T1S8"])
src = inspect.getsource(R.random_baseline)
check("풀을 만들 때 봉의 레짐 라벨로 버킷을 나눈다", 'regmap.get(rows[i]["date"])' in src)

# collect 가 레짐으로 버킷을 나누는지 — 합성 디텍터
def det(rows):
    return [10, 20, 40, 50]           # 앞 셋은 bull(<45), 마지막은 bear
b, opt, n_all, n_used = R.collect({"AAA": rows}, regmap, "long", 50, det)
check("신호가 진입 봉 레짐으로 분류된다",
      len(b["T1S8"]["bull_btc"]) == 3 and len(b["T1S8"]["bear"]) == 1 and len(b["T1S8"]["ALL"]) == 4,
      {g: len(v) for g, v in b["T1S8"].items()})
check("낙관 판은 주 판정 셀에만 있다", set(opt) == set(T.PRIMARY_ARMS))

# ── 판정 우선순위 ───────────────────────────────────────────────────────────
good = [(f"2024-01-{i+1:02d}", 0.008, 1, "target", False) for i in range(150)]   # 승률 100% 합성
hs = set(f"2024-01-{i+1:02d}" for i in range(120, 150))
j = R.judge("T1S8", "bull_btc", good, 0.5, hs, 100, 0.001)
check("성능·커버리지 다 통과 → PASS", j["verdict"] == "PASS", j["verdict"])
j2 = R.judge("T1S8", "bull_btc", good[:50], 0.5, set(), 100, 0.001)
check("train n < COV_MIN 이면 성능이 좋아도 INCONCLUSIVE", j2["verdict"] == "INCONCLUSIVE", j2["verdict"])
bad = [(f"2024-01-{i+1:02d}", -0.082, 1, "stop", False) for i in range(150)]
j3 = R.judge("T1S8", "bull_btc", bad, 0.5, hs, 100, 0.001)
check("성능 실패 → REJECTED (커버리지와 무관)", j3["verdict"] == "REJECTED", j3["verdict"])
# 드리프트 수확: 수익은 양수인데 엣지가 무작위보다 못한 경우
j4 = R.judge("T1S8", "bull_btc", good, 0.999, hs, 100, 0.90)
check("수익 기준 통과·엣지 실패 → DRIFT_HARVEST 표기 (숨기지 않는다)",
      j4["verdict"] != "PASS" and j4["drift_harvest"] is True, (j4["verdict"], j4.get("drift_harvest")))
vs = inspect.getsource(R.judge)
check("판정이 T.verdict 를 그대로 쓴다(기준 7개 재정의 없음)", "T.verdict(" in vs)

# ── 무관성 ──────────────────────────────────────────────────────────────────
ms = inspect.getsource(R)
check("실거래 엔진 import 없음", "import paper_executor" not in ms and "import exchange" not in ms)
check("스케줄러가 모른다", "tp_regime" not in open("scheduler.py", encoding="utf-8").read())
check("registry 사전 등록", "tp_regime_prereg_2026_09_09" in json.load(open("registry.json", encoding="utf-8")))
wf = open(".github/workflows/tp_regime.yml", encoding="utf-8").read()
check("워크플로가 테스트를 먼저 돌린다", "python test_tp_regime.py" in wf)
check("tests.yml 등재", "test_tp_regime.py" in open(".github/workflows/tests.yml", encoding="utf-8").read())

print(f"\n{len(fails)} failed")
raise SystemExit(1 if fails else 0)
