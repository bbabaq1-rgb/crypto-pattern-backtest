"""validate_pit_cohort 고정 — 동결 파라미터·PIT 순위(룩어헤드 없음)·적격·코호트 경계·코인별 분산·안정성 라벨·실거래 무변경.
실행: python test_pit_cohort.py"""
import json
import random
import statistics as st
from datetime import date, timedelta

import validate_pit_cohort as pc
import validate_guard_v4 as g4

fails = []
def check(n, c, d=""):
    print(("PASS " if c else "FAIL ") + n + ("" if c else f" — {d}")); c or fails.append(n)

# ── 1. 동결 ──────────────────────────────────────────────────────────────────────────────
check("순위 창 30 · 적격 60 · 코호트 20/30/liquid/mid · OKX 구간 2022-01", pc.RANK_WINDOW == 30 and pc.MIN_HISTORY == 60 and pc.COHORT_BOUNDS["core20"] == (1, 20)
      and pc.COHORT_BOUNDS["top30"] == (1, 30) and pc.COHORT_BOUNDS["mid"][0] == 21 and pc.COHORT_BOUNDS["liquid"][0] == 1 and pc.OKX_FROM == "2022-01-01")
check("배포 반영 없음", pc.DEPLOY_ON_PASS is False)
reg = json.load(open("registry.json", encoding="utf-8"))["pit_cohort_prereg_2026_09_06"]
cc = reg["cohort_construction_frozen"]
check("registry 사전 등록과 일치(월말·30일·60봉·경계)", "30" in cc["rebalance"] and "60" in cc["eligibility"] and "1~20" in cc["cohorts"]["core20"] and "21~80" in cc["cohorts"]["mid"])

# ── 2. PIT 순위 — 합성 3코인 ───────────────────────────────────────────────────────────────
def rows_for(n, start, vol_fn, seed=0):
    d0 = date.fromisoformat(start); out = []
    for i in range(n):
        d = (d0 + timedelta(days=i)).isoformat()
        out.append(dict(date=d, ts=None, o=1.0, h=1.01, l=0.99, c=1.0, v=float(vol_fn(d, i))))
    return out
# A: 항상 큰 거래량 / B: 2024-03 부터 A 보다 큼 / C: 이력 40일뿐(적격 미달)
rows = {"A": rows_for(200, "2024-01-01", lambda d, i: 100),
        "B": rows_for(200, "2024-01-01", lambda d, i: 50 if d < "2024-03-01" else 500),
        "C": rows_for(40, "2024-06-10", lambda d, i: 10000)}
pm = pc.pit_membership(rows)
check("첫 달(2024-01)은 적용월 없음, 2024-02 부터", "2024-01" not in pm and "2024-02" in pm)
check("2024-02 적용월: 1월 말 이력 31봉 < 60 → 적격 코인 0", pm["2024-02"] == {})
check("2024-03 적용 순위는 2월 말 기준(B 는 아직 50) → A 1위 B 2위", pm["2024-03"]["A"] == 1 and pm["2024-03"]["B"] == 2)
check("2024-04 적용 순위는 3월 말 기준(B 500) → B 1위 — 다음 달부터 적용", pm["2024-04"]["B"] == 1 and pm["2024-04"]["A"] == 2)
check("적격 60봉 미달 코인 C(이력 40봉)는 어느 달에도 없음", all("C" not in v for v in pm.values()))
check("2024-03 적용월: 2월 말 이력 60봉 → A/B 적격", set(pm["2024-03"]) == {"A", "B"})
# 룩어헤드 없음: 4월 이후 데이터를 바꿔도 2024-04 이전 적용 순위 불변
rows2 = {k: [dict(r) for r in v] for k, v in rows.items()}
for r in rows2["A"]:
    if r["date"] >= "2024-04-01": r["v"] = 1e9
pm2 = pc.pit_membership(rows2)
check("룩어헤드 없음: 4월 이후 거래량 변경이 2024-04 적용 순위(3월 말 기준)를 바꾸지 않음", pm2["2024-04"] == pm["2024-04"] and pm2["2024-05"] != pm["2024-05"])
check("코호트 경계: rank 1 → core20/top30/liquid, mid 아님", pc.in_cohort(pm, "core20", "B", "2024-04-15") and pc.in_cohort(pm, "top30", "B", "2024-04-15")
      and pc.in_cohort(pm, "liquid", "B", "2024-04-15") and not pc.in_cohort(pm, "mid", "B", "2024-04-15"))
check("majors 는 고정 7종", pc.in_cohort(pm, "majors", "BTC", "2024-04-15") and not pc.in_cohort(pm, "majors", "A", "2024-04-15"))
check("미등재 월/코인은 False", not pc.in_cohort(pm, "top30", "C", "2024-07-01") and not pc.in_cohort(pm, "top30", "A", "2023-12-15"))
chg, nm = pc.cohort_turnover(pm, "top30")
check("구성 변화 집계: 월 수 = 적용월 수", nm == len(pm) and chg is not None)

# ── 3. 코인별 분산 ─────────────────────────────────────────────────────────────────────────
sigs = ([dict(sym="X", ret=0.10, date="2024-02-01")] * 3 + [dict(sym="Y", ret=-0.02, date="2024-02-02")] * 3
        + [dict(sym="Z", ret=0.01, date="2024-02-03")] * 3 + [dict(sym="W", ret=0.5, date="2024-02-04")])
pcn = pc.per_coin(sigs, [0.0] * 50, min_n=3, drop_top=1)
check("코인 중앙값·양수 비율(n>=3 코인만)", abs(pcn["coin_median"] - 0.01) < 1e-12 and abs(pcn["coin_pos_share"] - 2 / 3) < 1e-12 and pcn["coins_n3"] == 3 and pcn["coins"] == 4)
check("기여 상위 1 제외(W 0.5) 후 평균", pcn["dropped"] == ["W"] and pcn["n_after_drop"] == 9 and abs(pcn["mean_after_drop"] - (0.3 - 0.06 + 0.03) / 9) < 1e-12)
check("비용 0.4% 후 평균 = 평균 − 0.2%p", abs(pcn["mean_cost04"] - (st.mean(s["ret"] for s in sigs) - 0.002)) < 1e-12)

# ── 4. 안정성 라벨 ─────────────────────────────────────────────────────────────────────────
check("같은 판정·같은 부호 → STABLE", pc.stability("UNCONFIRMED_SHADOW", "UNCONFIRMED_SHADOW", 0.03, 0.01) == "STABLE")
check("판정 다름 → SHIFTED", pc.stability("UNCONFIRMED_SHADOW", "REJECTED", 0.03, 0.01) == "SHIFTED")
check("부호 다름 → SHIFTED", pc.stability("REJECTED", "REJECTED", 0.03, -0.01) == "SHIFTED")

# ── 5. PIT 풀·필터가 코호트 구성원만 쓰는지 (합성 outcome) ────────────────────────────────
rng = random.Random(3)
def px_rows(n, start):
    d0 = date.fromisoformat(start); out = []; px = 100.0
    for i in range(n):
        o = px; c = o * (1 + rng.uniform(-0.02, 0.02)); out.append(dict(date=(d0 + timedelta(days=i)).isoformat(), ts=None, o=o, h=max(o, c) * 1.01, l=min(o, c) * 0.99, c=c, v=100.0 + (i if i % 2 else 0))); px = c
    return out
rb = {"A": px_rows(300, "2024-01-01"), "B": px_rows(300, "2024-01-01")}
for r in rb["B"]: r["v"] = 1000.0     # B 가 항상 1위
regmap = {r["date"]: "bull_btc" for r in rb["A"]}
pmb = pc.pit_membership(rb)
oc = g4.Outcomes("1d", rb, regmap, "long")
pool = pc.pit_pool(oc, ["A", "B"], pmb, "core20", "bull_btc")
check("PIT 풀: 적격 전(첫 2달) 봉 없음, 적격 후 봉은 포함", pool and min(dt for dt, _ in pool) >= "2024-03-01")
sig = [dict(sym="A", date="2024-05-10", ret=0.0), dict(sym="A", date="2024-02-10", ret=0.0)]
check("PIT 필터: 적격 전 신호 제외", [s["date"] for s in pc.pit_filter(sig, pmb, "top30")] == ["2024-05-10"])
bounds1 = {"core20": (1, 1)}
old = pc.COHORT_BOUNDS; pc.COHORT_BOUNDS = {**old, "core20": (1, 1)}
check("경계 (1,1) 이면 B(1위)만 코호트", pc.in_cohort(pmb, "core20", "B", "2024-05-10") and not pc.in_cohort(pmb, "core20", "A", "2024-05-10"))
pc.COHORT_BOUNDS = old

# ── 6. 무변경·등재 ─────────────────────────────────────────────────────────────────────────
src = open("validate_pit_cohort.py", encoding="utf-8").read()
check("실거래·배포 코드 없음", "import paper_executor" not in src and "adopted_" not in src and "ROUTING_OVERRIDES" not in src)
wf = open(".github/workflows/pit_cohort.yml", encoding="utf-8").read()
check("워크플로 등재 + 테스트 선행", "python validate_pit_cohort.py" in wf and "python test_pit_cohort.py" in wf and "python test_guard_v4.py" in wf)
check("tests.yml 등재", "test_pit_cohort.py" in open(".github/workflows/tests.yml", encoding="utf-8").read())


# ── 판정 규칙 v5 (2026-09-09 사용자 결정 ①②) ─────────────────────────────────────────────
import validate_guard_v5 as g5
check("기본 판정 규칙은 v5 (B 진단 · 레짐 셀 n<200 boot_p 단독 → INCONCLUSIVE)", pc.RULES_DEFAULT == "v5", pc.RULES_DEFAULT)
_cell = dict(cid="x|bull_btc", regime="bull_btc", status="deployed")
_rec = lambda: dict(cell=_cell, full_a=dict(n=150, mean=0.02, win=0.5), train_gate=dict(verdict="REJECTED", reason="boot_p=0.300"),
                    train_b=dict(nw=-0.01, p_nw=0.9, eq_month=0.0, eq_coin_month=0.0), oos_a=dict(n=20, mean=0.03, win=0.5, boot_p=0.01),
                    oos_b=dict(nw=-0.02, p_nw=0.95, months=6, eq_month=-0.01, eq_coin_month=-0.01))
r5 = {"x|bull_btc": _rec()}; pc.judge_family(r5, "v5")
r4 = {"x|bull_btc": _rec()}; pc.judge_family(r4, "v4")
check("v5: 레짐 셀 n<200 · train boot_p 단독 탈락 → INCONCLUSIVE (규칙 2)", r5["x|bull_btc"]["verdict"] == "INCONCLUSIVE" and r5["x|bull_btc"]["rule2"], r5["x|bull_btc"])
check("v4 원판은 같은 레코드를 UNCONFIRMED_SHADOW 로 (B 탈락 포함)", r4["x|bull_btc"]["verdict"] == "UNCONFIRMED_SHADOW" and "OOS B" in r4["x|bull_btc"]["fails"], r4["x|bull_btc"])
check("v5 는 B 사유를 판정에 넣지 않는다", not any("B" in f for f in r5["x|bull_btc"]["fails"]), r5["x|bull_btc"]["fails"])
check("규칙 표기가 레코드에 남는다", r5["x|bull_btc"]["rules"] == "v5" and r4["x|bull_btc"]["rules"] == "v4")
_big = _rec(); _big["full_a"]["n"] = 250
rb = {"x|bull_btc": _big}; pc.judge_family(rb, "v5")
check("v5: n>=200 이면 규칙 2 미적용 → train A gate 탈락 유지(UNCONFIRMED_SHADOW)", rb["x|bull_btc"]["verdict"] == "UNCONFIRMED_SHADOW" and not rb["x|bull_btc"]["rule2"], rb["x|bull_btc"])
check("v5 판정 함수는 validate_guard_v5.verdict_v5 (v4 파일 불변)", pc.g5.verdict_v5 is g5.verdict_v5)
wf5 = open(".github/workflows/pit_cohort.yml", encoding="utf-8").read()
check("워크플로가 --rules v5 로 돌리고 test_guard_v5 를 먼저 돈다", "--rules v5" in wf5 and "python test_guard_v5.py" in wf5 and "_pit_cohort_v5.json" in wf5)
check("registry 에 v5 재판정 사전 등록", "pit_cohort_v5_2026_09_09" in open("registry.json", encoding="utf-8").read())

print(f"\n{'ALL PASS' if not fails else 'FAILED: ' + ', '.join(fails)} ({len(fails)} fail)")
import sys; sys.exit(1 if fails else 0)
