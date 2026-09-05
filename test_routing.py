"""
validate_routing 로직 검증 (합성 데이터, 네트워크 없음).

고정하는 성질:
  - route arm 이 **실거래 라우팅과 같은 표**를 만든다 (direction_switch.json 과 일치)
  - uncond 는 게이트가 검증한 방향(둘 다 롱), gated 는 PASSED 셀만
  - 분기 셀 집계가 '두 표가 다른 방향을 고른 셀'만 잡고, FLAT 쪽을 수익 0 이 아니라
    표본 없음으로 다룬다
  - 짝지음 블록 부트스트랩이 arm 마다 **같은 블록**을 쓴다(시드 고정)
  - 사전 등록 7기준이 하나라도 깨지면 '현행 유지'
  - 자산곡선은 method_x.equity_curve 를 그대로 쓴다(연구/실거래 사이징 일치)
  - 실거래 코드가 이 모듈을 import 하지 않는다
실행: python test_routing.py
"""
import json
import os
import random
import sys

import method_x as mx
import validate_routing as vr

fails = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f" — {detail}"))
    cond or fails.append(name)


# ── 1. route 표가 실거래와 일치 ──────────────────────────────────────────────
tabs = vr.build_tables()
check("route/uncond arm 이 만들어진다", "route" in tabs and "uncond" in tabs, list(tabs))
check("uncond 는 모든 셀이 롱", set(tabs["uncond"].values()) == {"long"}, tabs["uncond"])

if os.path.exists("direction_switch.json"):
    live = json.load(open("direction_switch.json", encoding="utf-8"))["routing"]
    same = all(tabs["route"].get((rg, pat), "FLAT") == live.get(rg, {}).get(pat, "FLAT")
               for rg in live for pat in live[rg])
    check("route 표가 direction_switch.json(실거래)과 완전히 같다", same,
          (tabs["route"], live))
else:
    print("SKIP direction_switch.json 없음 — 실거래 표 대조 생략")

check("ROUTING_OVERRIDES 가 반영된다 (있는 항목은 전부 표에 그대로)",
      all(tabs["route"].get(k) == v for k, v in vr.ds.ROUTING_OVERRIDES.items()), tabs["route"])
check("bear fvg 는 오버라이드 FLAT (2026-09-05 저녁 사용자 결정)", tabs["route"][("bear", "fvg")] == "FLAT",
      tabs["route"][("bear", "fvg")])

# route_bfl — route 와 정확히 한 셀만 다르다
diff = [k for k in tabs["route"] if tabs["route"][k] != tabs["route_bfl"].get(k)]
check("route_bfl 은 route 와 (bear, fvg) 한 셀만 다르다", diff == [("bear", "fvg")], diff)
check("route_bfl 의 그 셀은 long", tabs["route_bfl"][("bear", "fvg")] == "long")
check("route_bfl 은 셀별 부호 arm 으로 등록", "route_bfl" in vr.PER_CELL_ARMS)
check("uncond/gated 는 종전 합산 규칙 유지(사후 변경 금지)",
      not ({"uncond", "gated"} & vr.PER_CELL_ARMS))


# ── 2. gated 표 ──────────────────────────────────────────────────────────────
TMP = "_test_split.json"
json.dump({"results": {
    "engulfing": {"top20:bull_btc": {"verdict": "PASSED", "mean": 0.04},
                  "top20:bull_altseason": {"verdict": "REJECTED", "mean": 0.01},
                  "top20:bear": {"verdict": "REJECTED", "mean": 0.02},
                  "top20:sideways": {"verdict": "REJECTED", "mean": 0.0}},
    "engulfing_short": {"top20:bull_altseason": {"verdict": "PASSED", "mean": 0.06},
                        "top20:bull_btc": {"verdict": "PASSED", "mean": 0.09}},
    "fvg": {"top30:bear": {"verdict": "PASSED", "mean": 0.03}},
    "fvg_short": {}}},
    open(TMP, "w", encoding="utf-8"))
_orig = vr.SPLIT_FILE
vr.SPLIT_FILE = TMP
g = vr.gated_table({"engulfing": "top20", "fvg": "top30"})
vr.SPLIT_FILE = _orig
os.remove(TMP)

check("gated: 통과 셀 없으면 FLAT", g[("sideways", "engulfing")] == "FLAT", g)
check("gated: 롱만 통과하면 롱", g[("bear", "fvg")] == "long", g)
check("gated: 숏만 통과하면 숏", g[("bull_altseason", "engulfing")] == "short", g)
check("gated: 둘 다 통과하면 평균 높은 쪽", g[("bull_btc", "engulfing")] == "short", g)
check("gated: 결측 셀은 FLAT", g[("bull_altseason", "fvg")] == "FLAT", g)

vr.SPLIT_FILE = "_definitely_missing_.json"
check("gated: 파일 없으면 arm 자체를 건너뛴다", vr.gated_table({"engulfing": "top20", "fvg": "top30"}) is None)
vr.SPLIT_FILE = _orig


# ── 3. 합성 후보로 arm 필터·분기 셀 ─────────────────────────────────────────
def cand(rg, direction, ret, day, sym="AAA"):
    d = f"2024-{1 + day // 28:02d}-{1 + day % 28:02d}"
    return dict(sym=sym, i=day, date=d, regime=rg, direction=direction, ret=ret,
                hold=5, reason="maxhold", exit_date=f"2024-{1 + (day + 5) // 28:02d}-{1 + (day + 5) % 28:02d}",
                stop_pct=0.08, vol=0.8)


cands = {"engulfing": ([cand("bull_altseason", "short", 0.05, d) for d in range(40)]
                       + [cand("bull_altseason", "long", -0.03, d) for d in range(40)]
                       + [cand("bull_btc", "long", 0.02, d) for d in range(40, 80)]),
         "fvg": [cand("bear", "long", 0.01, d) for d in range(80, 120)]}

TAB_A = {("bull_altseason", "engulfing"): "short", ("bull_btc", "engulfing"): "long",
         ("bear", "fvg"): "FLAT", ("sideways", "engulfing"): "FLAT", ("sideways", "fvg"): "FLAT",
         ("bull_altseason", "fvg"): "long", ("bull_btc", "fvg"): "long", ("bear", "engulfing"): "long"}
TAB_B = {(rg, p): "long" for rg in vr.ds.REGIMES for p in vr.ds.FOCUS}

ta, tb = vr.arm_trades(cands, TAB_A), vr.arm_trades(cands, TAB_B)
check("arm 은 자기 표에 맞는 방향만 가져간다",
      all(t["direction"] == "short" for t in ta if t["regime"] == "bull_altseason" and t["base"] == "engulfing"),
      [t["direction"] for t in ta[:3]])
check("FLAT 셀은 거래가 없다", not [t for t in ta if t["base"] == "fvg"], len([t for t in ta if t["base"] == "fvg"]))
check("uncond 는 FLAT 셀도 롱으로 잡는다", len([t for t in tb if t["base"] == "fvg"]) == 40)
check("거래는 날짜 오름차순", [t["date"] for t in ta] == sorted(t["date"] for t in ta))
check("레짐이 None 인 후보는 제외",
      not vr.arm_trades({"engulfing": [cand(None, "long", 0.1, 1)]}, TAB_B))

dv = vr.divergence(cands, TAB_A, TAB_B)
cells = {(c["regime"], c["pattern"]): c for c in dv["cells"]}
check("두 표가 같은 방향인 셀은 분기가 아니다", ("bull_btc", "engulfing") not in cells, list(cells))
check("방향이 다른 셀만 분기로 잡힌다",
      set(cells) == {("bull_altseason", "engulfing"), ("bear", "fvg")}, set(cells))
c_fvg = cells[("bear", "fvg")]
check("FLAT 쪽은 표본 없음(None)이지 수익 0 이 아니다",
      c_fvg["a_n"] == 0 and c_fvg["a_mean"] is None, c_fvg)
check("분기 집계가 arm 별 n 을 센다", dv["a_n"] == 40 and dv["b_n"] == 80, (dv["a_n"], dv["b_n"]))


# ── 4. 자산곡선은 method_x 를 그대로 쓴다 ───────────────────────────────────
check("equity_curve 는 method_x 의 것", vr.mx.equity_curve is mx.equity_curve)
p = vr.perf(tb)
check("perf 가 n·CAGR·MDD·Calmar 를 낸다",
      p and p["n"] == len(tb) and "cagr" in p and "mdd" in p and "calmar" in p, p)
check("perf: 거래 없으면 None", vr.perf([]) is None)

# 연율화 분모: arm 마다 거래 간격이 다르면 CAGR 이 비교 불가능해진다.
# (실측 회귀: holdout 41건 arm 이 MDD -36.6% 인데 CAGR -92.2% 로 찍혔다.)
short_span = [t for t in tb if t["date"] < "2024-02-15"]
p_own = vr.perf(short_span)                      # 자기 간격으로 연율화
p_common = vr.perf(short_span, span_days=1000)   # 공통 창으로 연율화
check("공통 창을 주면 연율화 분모가 바뀐다", p_own["cagr"] != p_common["cagr"],
      (p_own["cagr"], p_common["cagr"]))
check("같은 거래면 MDD 는 분모와 무관", abs(p_own["mdd"] - p_common["mdd"]) < 1e-12,
      (p_own["mdd"], p_common["mdd"]))
check("긴 창으로 늘리면 손익이 희석된다(절대값 감소)",
      abs(p_common["cagr"]) < abs(p_own["cagr"]), (p_own["cagr"], p_common["cagr"]))
check("method_x.equity_curve 기본값은 종전과 같다(자기 간격)",
      mx.equity_curve(vr.as_tuples(short_span))["cagr"] == p_own["cagr"])


# ── 5. 짝지음 블록 부트스트랩 ───────────────────────────────────────────────
b1 = vr.paired_block_boot({"route": ta, "uncond": tb}, random.Random(vr.SEED), n_boot=12)
b2 = vr.paired_block_boot({"route": ta, "uncond": tb}, random.Random(vr.SEED), n_boot=12)
check("시드 고정 시 재현된다", b1["route"]["calmar"] == b2["route"]["calmar"])
check("arm 마다 같은 횟수의 draw",
      len(b1["route"]["calmar"]) == len(b1["uncond"]["calmar"]) > 0,
      (len(b1["route"]["calmar"]), len(b1["uncond"]["calmar"])))
# 같은 블록을 쓰는지: route 거래가 하나도 없는 arm 을 넣어도 draw 수가 유지된다
b3 = vr.paired_block_boot({"route": ta, "empty": []}, random.Random(vr.SEED), n_boot=5)
check("거래 0건 arm 이 있어도 다른 arm 의 draw 는 유지", len(b3["route"]["calmar"]) == 5,
      len(b3["route"]["calmar"]))
# 회귀: draw 마다 arm 별 정확히 한 값. 건너뛰면 기준 6) 의 zip 짝지음이 어긋난다.
check("거래 0건 arm 도 draw 수가 같다(짝지음 정렬)",
      len(b3["empty"]["calmar"]) == len(b3["route"]["calmar"]) == 5,
      (len(b3["empty"]["calmar"]), len(b3["route"]["calmar"])))
check("아무것도 안 한 arm 의 Calmar 는 0", set(b3["empty"]["calmar"]) == {0.0}, b3["empty"]["calmar"])
check("거래 없는 데이터면 빈 결과", vr.paired_block_boot({"a": []}, random.Random(1), n_boot=3)["a"]["calmar"] == [])


# ── 6. 사전 등록 7기준 ──────────────────────────────────────────────────────
def mk(cagr, calmar, mdd):
    return dict(n=100, mean=0.01, median=0.0, win=0.5, hold=10.0,
                cagr=cagr, mdd=mdd, calmar=calmar, taken=100, skipped=0)


def res_for(arm_cagr=0.5, arm_calmar=1.2, arm_mdd=-0.40, div_b_n=40, div_b_mean=0.03,
            div_a_mean=0.01, h1=(0.4, 0.5), h2=(0.4, 0.5), ho=(0.2, 0.3)):
    return {"route": dict(train=mk(0.4, 1.0, -0.40), holdout=mk(ho[0], 1.0, -0.3),
                          divergence=dict(cells=[], a_n=0, b_n=0, a_mean=None, b_mean=None), halves={}),
            "X": dict(train=mk(arm_cagr, arm_calmar, arm_mdd), holdout=mk(ho[1], 1.0, -0.3),
                      divergence=dict(cells=[], a_n=30, b_n=div_b_n,
                                      a_mean=div_a_mean, b_mean=div_b_mean),
                      halves=dict(first=dict(base=h1[0], arm=h1[1]),
                                  second=dict(base=h2[0], arm=h2[1])))}


v = vr.verdict("X", res_for(), 0.7)
check("7기준 모두 만족하면 채택 권고", v["pass_"], v)
check("CAGR 열세면 탈락", not vr.verdict("X", res_for(arm_cagr=0.3), 0.7)["pass_"])
check("Calmar 열세면 탈락", not vr.verdict("X", res_for(arm_calmar=0.9), 0.7)["pass_"])
check("분기 표본 부족(n<30)이면 탈락",
      not vr.verdict("X", res_for(div_b_n=10), 0.7)["pass_"])
check("분기 평균이 음수면 탈락 (route 보다 높아도)",
      not vr.verdict("X", res_for(div_b_mean=-0.01, div_a_mean=-0.05), 0.7)["pass_"])
check("후반이 열세면 탈락", not vr.verdict("X", res_for(h2=(0.5, 0.4)), 0.7)["pass_"])
check("MDD 가 허용폭 넘게 악화되면 탈락",
      not vr.verdict("X", res_for(arm_mdd=-0.40 - vr.MDD_TOLERANCE - 0.01), 0.7)["pass_"])
check("MDD 가 허용폭 안이면 통과 유지",
      vr.verdict("X", res_for(arm_mdd=-0.40 - vr.MDD_TOLERANCE + 0.01), 0.7)["pass_"])
check("부트 우위 60% 미만이면 탈락", not vr.verdict("X", res_for(), 0.59)["pass_"])
check("holdout 열세면 탈락", not vr.verdict("X", res_for(ho=(0.3, 0.2)), 0.7)["pass_"])
# 셀별 부호 규칙: 합산 분기 평균이 양수라도 어느 한 셀이 음수면 탈락 (1차 시험의 uncond 사례)
def res_cells(cells, **kw):
    r = res_for(**kw)
    r["X"]["divergence"]["cells"] = cells
    return r


good_cells = [dict(pattern="fvg", regime="bear", a_dir="FLAT", b_dir="long", a_n=0, b_n=100, a_mean=None, b_mean=0.02)]
bad_cells = good_cells + [dict(pattern="engulfing", regime="bull_altseason", a_dir="short", b_dir="long",
                               a_n=50, b_n=40, a_mean=0.003, b_mean=-0.03)]
_saved = set(vr.PER_CELL_ARMS); vr.PER_CELL_ARMS.add("X")
check("셀별 부호: 모든 분기 셀이 양수·우위면 통과", vr.verdict("X", res_cells(good_cells), 0.7)["pass_"])
check("셀별 부호: 한 셀이 음수면 합산이 양수라도 탈락",
      not vr.verdict("X", res_cells(bad_cells), 0.7)["pass_"])
check("셀별 부호: 셀 n<30 이면 탈락",
      not vr.verdict("X", res_cells([dict(good_cells[0], b_n=10)]), 0.7)["pass_"])
check("셀별 부호: 분기 셀이 없으면 탈락", not vr.verdict("X", res_cells([]), 0.7)["pass_"])
vr.PER_CELL_ARMS.clear(); vr.PER_CELL_ARMS.update(_saved)
check("합산 규칙 arm 은 셀 하나가 음수여도 합산으로 판정(종전 동작 불변)",
      vr.verdict("X", res_cells(bad_cells), 0.7)["pass_"])

check("train 표본 없으면 탈락",
      not vr.verdict("X", {"route": dict(train=None, holdout=None, divergence={}, halves={}),
                           "X": dict(train=None, holdout=None, divergence={}, halves={})}, 0.9)["pass_"])


# ── 7. 실거래 코드 비의존 ───────────────────────────────────────────────────
for f in ("paper_executor.py", "scheduler.py", "exchange.py", "direction_switch.py"):
    src = open(f, encoding="utf-8").read()
    check(f"{f} 는 validate_routing 를 import 하지 않음", "validate_routing" not in src)

print(f"\n{len(fails)} failed")
sys.exit(1 if fails else 0)
