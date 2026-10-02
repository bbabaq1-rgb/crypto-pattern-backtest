"""
test_elliott_watch.py — 엘리엇 일일 점검의 성질 고정 (네트워크 없이 도는 순수 로직)

가장 중요한 두 가지:
  §1 이 스크립트는 **매매 경로와 완전히 단절**돼 있다 (양방향 import 0).
  §2 동결 카운트는 코드가 아니라 파일에 있고, 라벨은 코드가 못 바꾼다.
"""
import ast
import json
import os
import sys

import elliott_watch as ew

FAIL = []


def check(name, cond):
    print(("  OK   " if cond else "  FAIL ") + name)
    if not cond:
        FAIL.append(name)


# ---------------------------------------------------------------- §1 격리
print("[1] 매매 경로와의 격리")
SRC = open("elliott_watch.py").read()
TRADING = ("scheduler", "paper_executor", "exchange", "sizing", "registry",
           "universe", "direction_switch", "detlib", "supabase_client")
tree = ast.parse(SRC)
imported = set()
for node in ast.walk(tree):
    if isinstance(node, ast.Import):
        imported |= {a.name.split(".")[0] for a in node.names}
    elif isinstance(node, ast.ImportFrom) and node.module:
        imported.add(node.module.split(".")[0])
check("elliott_watch 가 매매 모듈을 import 하지 않는다",
      not (imported & set(TRADING)))
for mod in ("scheduler.py", "paper_executor.py", "exchange.py", "sizing.py"):
    if os.path.exists(mod):
        body = open(mod).read()
        check(f"{mod} 가 elliott_watch/elliott_count 를 읽지 않는다",
              "elliott_watch" not in body and "elliott_count" not in body)
REG = json.load(open("registry.json"))
check("registry 의 어떤 패턴도 elliott 계열이 아니다",
      not any("elliott" in str(p.get("id", "")).lower()
              for p in REG.get("patterns", [])))
check("universe.json 에 elliott 항목이 없다",
      "elliott" not in open("universe.json").read().lower())
check("주문 함수를 부르지 않는다",
      not any(k in SRC for k in ("place_swap_entry", "close_swap_position",
                                 "place_stop_algo", "create_order")))

# ---------------------------------------------------------------- §2 동결
print("[2] 카운트 동결")
COUNT = json.load(open(ew.COUNT_FILE))
labels = [w["label"] for w in COUNT["waves"]]
check("파동 라벨이 0,1,2,3,4,5", labels == ["0", "1", "2", "3", "4", "5"])
px = {w["label"]: w["price"] for w in COUNT["waves"]}
check("0파 저점 57717.55", px["0"] == 57717.55)
check("5파 고점 87397.0", px["5"] == 87397.0)
check("코드에 파동 가격 하드코딩 없음 — 파일이 유일한 원천",
      not any(str(int(v)) in SRC for v in px.values()))
check("elliott_watch 에 판정 임계(레벨) 하드코딩 없음",
      "69055" not in SRC and "76059" not in SRC)

# 엘리엇 3대 규칙 — 동결 카운트가 실제로 만족하는지 파일 값으로 재계산
print("[3] 임펄스 3대 규칙 (파일 값으로 재계산)")
check("2파가 0파 저점 아래로 안 감", px["2"] > px["0"])
w1, w3, w5 = px["1"] - px["0"], px["3"] - px["2"], px["5"] - px["4"]
check("3파가 최단이 아님", not (w3 < w1 and w3 < w5))
check("4파가 1파 고점과 중첩 안 함", px["4"] > px["1"])
check("rule_checks 표기가 재계산과 일치",
      COUNT["rule_checks"]["w4_no_overlap_w1"] is True
      and abs(COUNT["rule_checks"]["w4_low_minus_w1_high"] - (px["4"] - px["1"])) < 1e-6)

# ---------------------------------------------------------------- §4 지그재그
print("[4] 지그재그")
flat = [{"d": str(i), "o": 100, "h": 100, "l": 100, "c": 100} for i in range(50)]
check("평평한 구간은 피벗 2개(시작·끝)뿐", len(ew.zigzag(flat, 0.05)) == 2)


def bar(lo, hi):
    return {"d": "x", "o": lo, "h": hi, "l": lo, "c": hi}


up = [bar(100, 100)] + [bar(100 + i, 101 + i) for i in range(20)] \
     + [bar(120 - 2 * i, 121 - 2 * i) for i in range(12)]
zz = ew.zigzag(up, 0.05)
check("상승 뒤 5% 하락에서 고점 피벗이 잡힌다",
      any(k == "H" for k, _i, _v in zz[1:-1]))
check("피벗은 H/L 이 교대로 나온다",
      all(zz[i][0] != zz[i + 1][0] for i in range(len(zz) - 1)))
check("빈 입력에 안전", ew.zigzag([], 0.05) == [])

# ---------------------------------------------------------------- §5 고점 봉 제외
print("[5] after_top — 고점 당일 봉을 넣지 않는다")
rows = [bar(80, 82), {"d": "top", "o": 81, "h": 87.4, "l": 80.8, "c": 86.6},
        bar(85, 86.6), bar(85.1, 86.7)]
aft = ew.after_top(rows, 87.4)
check("고점 봉 자체는 제외", len(aft) == 2 and aft[0]["l"] == 85)
check("고점 봉의 저가(80.8)가 '고점 이후 저가'로 새지 않는다",
      min(r["l"] for r in aft) == 85)
check("고점을 못 찾으면 빈 목록", ew.after_top(rows, 999) == [])

# ---------------------------------------------------------------- §6 레벨 판정
print("[6] 레벨 판정 방향")
lv = ew.level_table([{"px": 100.0, "dir": "below", "name": "a", "means": ""},
                     {"px": 100.0, "dir": "above", "name": "b", "means": ""}], 90.0)
check("below 레벨은 가격이 그 아래일 때만 HIT", lv[0]["hit"] is True)
check("above 레벨은 가격이 그 위일 때만 HIT", lv[1]["hit"] is False)
check("거리 부호가 맞다(+면 위)", lv[0]["dist_pct"] > 0)

# ---------------------------------------------------------------- §7 시나리오
print("[7] 시나리오 생사")
alive_hi = ew.scenarios_alive(COUNT, 86000, 85059)
check("얕은 눌림에서는 S1·S2 둘 다 생존",
      alive_hi["S1_wave1_of_new_impulse"] and alive_hi["S2_still_in_wave3"])
check("얕은 눌림에서 고점 확정 아님",
      alive_hi["_impulse_top_confirmed"] is False)
alive_mid = ew.scenarios_alive(COUNT, 73000, 72000)
check("50% 되돌림에서 S2 사망·S1 생존",
      alive_mid["S1_wave1_of_new_impulse"] and not alive_mid["S2_still_in_wave3"])
check("4파 영역 진입이면 고점 확정",
      alive_mid["_impulse_top_confirmed"] is True)
alive_lo = ew.scenarios_alive(COUNT, 57000, 56000)
check("0파 저점 이탈이면 S1 사망", not alive_lo["S1_wave1_of_new_impulse"])
check("S3 는 반증 불가라 항상 생존",
      all(a["S3_wave_A_of_larger_correction"]
          for a in (alive_hi, alive_mid, alive_lo)))

# ---------------------------------------------------------------- §8 RSI
print("[8] RSI")
r = ew.rsi([100 + i for i in range(40)])
check("단조 상승이면 RSI 100 에 수렴", r[-1] > 99)
r = ew.rsi([100 - i for i in range(40)])
check("단조 하락이면 RSI 0 에 수렴", r[-1] < 1)
check("워밍업 구간은 None", ew.rsi([1, 2, 3])[1] is None)

# ---------------------------------------------------------------- §9 2파 조정 추적
print("[9] 2파 A-B-C 추적 (2026-09-25)")
cor = COUNT.get("correction")
check("correction 블록 존재", bool(cor))
check("A 크기 = start - end", abs(cor["A"]["start"] - cor["A"]["end"] - cor["A"]["size"]) < 1e-6)
check("A 끝 = 4파 저점보다 위 (2파는 4파 영역 밖에서 시작)", cor["A"]["end"] > px["4"])
check("B 최소 레벨이 A 시작점 기준으로 단조", all(
    cor["B_min_levels"][a] < cor["B_min_levels"][b]
    for a, b in (("0.618", "0.90"), ("0.90", "1.00"), ("1.00", "1.236"))))
check("B 100% = A 시작점", cor["B_min_levels"]["1.00"] == cor["A"]["start"])
st = ew.correction_status(COUNT, 84000, 85250, 82709)
check("B 진행률 = (고점-A끝)/A", abs(st["B_retrace_pct"] - (85250 - 82709) / 4688 * 100) < 1e-6)
check("B 54% 는 61.8% 최소 미달", st["B_min"]["0.618"]["hit"] is False)
st2 = ew.correction_status(COUNT, 86000, 87000, 82709)
check("B 가 90% 넘으면 0.90 HIT", st2["B_min"]["0.90"]["hit"] is True and st2["B_min"]["1.00"]["hit"] is False)
st3 = ew.correction_status(COUNT, 82000, 85250, 81900)
check("A 저점 이탈 플래그", st3["A_end_broken"] is True)
check("A 파 안의 b 반등(87,283)은 B 고점이 아니다 — run() 이 A 종료 다음 봉부터 잰다",
      'r["d"] > a_date' in SRC)
check("현재가가 고점보다 높으면 B 고점을 현재가로", ew.correction_status(COUNT, 86500, 85250, 82709)["B_high"] == 86500)
no_cor = {k: v for k, v in COUNT.items() if k != "correction"}
check("correction 없으면 None (종전 동작)", ew.correction_status(no_cor, 84000, 85250, 82709) is None)
check("revisions 에 2026-09-25 항목 + 사용자 승인",
      any(r["date"] == "2026-09-25" and r.get("approved_by") == "user" for r in COUNT["revisions"]))
check("87,397 레벨에 확장 플랫 읽기 병기",
      any(lv["px"] == 87397.0 and "확장 플랫" in lv["means"] for lv in COUNT["levels"]))
check("파동 라벨·가격은 재라벨 없음", [w["price"] for w in COUNT["waves"]] == [57717.55, 66924.0, 62210.0, 82283.0, 74888.0, 87397.0])

# ---------------------------------------------------------------- §10 확률표
print("[10] 확률표 outlook (2026-09-28)")
ol = COUNT.get("outlook")
check("outlook 블록 존재", bool(ol))
check("S1+S2+S3 = 100", sum(ol["scenarios_pct"].values()) == 100)
check("S1 안 지그재그+플랫+WXY = 100", sum(ol["wave2_shape_pct_within_S1"].values()) == 100)
check("트리거 가격은 레벨 표·A 저점·B 최소 레벨에 이미 있는 값 (새 숫자를 만들지 않는다)", all(
    t["px"] in {lv["px"] for lv in COUNT["levels"]} | set(COUNT["correction"]["B_min_levels"].values())
    | {COUNT["correction"]["A"]["end"]}
    for t in ol["triggers"]))
check("코드에 확률 숫자·트리거 가격 하드코딩 없음",
      "85606" not in SRC and "86928" not in SRC and '"S1": 55' not in SRC)
bar_ = lambda d, lo, hi: {"d": d, "o": lo, "h": hi, "l": lo, "c": hi}
quiet = [bar_("2026-09-28", 83190, 84992), bar_("2026-09-29", 83000, 84500)]
o = ew.outlook_status(COUNT, quiet)
check("상자 안이면 트리거 0 발동", not o["reassess"] and not any(t["fired"] for t in o["triggers"]))
shp = ol["wave2_shape_pct_within_S1"]
check("ABC(S1 안) = 지그재그 + 플랫", o["abc_within_S1"] == shp["zigzag_abc"] + shp["flat_abc"]
      and o["wxy_within_S1"] == shp["wxy"])
check("무조건부 = S1 비중 곱", abs(o["abc_uncond"] - (shp["zigzag_abc"] + shp["flat_abc"]) * ol["scenarios_pct"]["S1"] / 100) < 1e-9)
downs = sorted((t["px"] for t in ol["triggers"] if t["dir"] == "below"), reverse=True)
brk = ew.outlook_status(COUNT, quiet + [bar_("2026-09-30", downs[0] - 1, 83100)])
fired = [t["px"] for t in brk["triggers"] if t["fired"]]
check("가장 가까운 하향 트리거 바로 아래 저가 → 그것만 발동", fired == [downs[0]] and brk["reassess"])
up = ew.outlook_status(COUNT, quiet + [bar_("2026-09-30", 85000, 87500)])
check("87,500 고가 → 87,500 아래의 상향 트리거 전부 발동",
      sorted(t["px"] for t in up["triggers"] if t["fired"]) ==
      sorted(t["px"] for t in ol["triggers"] if t["dir"] == "above" and t["px"] < 87500))
check("트리거가 발동해도 코드는 확률을 바꾸지 않는다", brk["scenarios"] == ol["scenarios_pct"]
      and brk["shape"] == ol["wave2_shape_pct_within_S1"])
check("기준일 당일 포함 이후 봉만 본다", 'r["d"] >= count["outlook"]["as_of"]' in SRC)
no_ol = {k: v for k, v in COUNT.items() if k != "outlook"}
check("outlook 없으면 None (종전 동작)", ew.outlook_status(no_ol, quiet) is None)
check("revisions 에 2026-09-28 항목 + 사용자 승인",
      any(r["date"] == "2026-09-28" and r.get("approved_by") == "user" for r in COUNT["revisions"]))

check("시나리오마다 풀어 쓴 label 이 있다 (약자 표기 금지, 2026-09-28 요청)",
      all(v.get("label") for v in COUNT["scenarios"].values()))
check("확률표 약자 → 시나리오 키 매핑이 전부 실제 시나리오를 가리킨다",
      set(ol["scenario_keys"].values()) == set(COUNT["scenarios"].keys()))
check("outlook_status 가 풀어 쓴 이름을 넘긴다",
      o["scenario_names"]["S1"] == COUNT["scenarios"]["S1_wave1_of_new_impulse"]["label"])
check("C 목표마다 풀어 쓴 설명", set(COUNT["correction"]["C_target_labels"]) == set(COUNT["correction"]["C_targets"]))

# ---------------------------------------------------------------- §11 채점 장부
print("[11] 채점 장부 scorebook (2026-09-28)")
sb = COUNT.get("scorebook")
check("scorebook 존재 + 질문 2개 이상", bool(sb) and len(sb["questions"]) >= 2)
check("모든 질문에 예측·무작위 보행·반반 기준·판정 규칙·사건 정의",
      all({"forecast", "baselines", "rule", "event", "as_of"} <= set(q) and
          {"random_walk", "coin"} <= set(q["baselines"]) for q in sb["questions"]))
check("예측은 0~1 확률", all(0 < q["forecast"] < 1 for q in sb["questions"]))
q1 = next(q for q in sb["questions"] if q["id"] == "Q1")
check("Q1 무작위 보행 기준 = 기준가에서 두 가격까지 거리 비율",
      abs(q1["baselines"]["random_walk"] - (q1["basis_px"] - q1["rule"]["down"]) /
          (q1["rule"]["up"] - q1["rule"]["down"])) < 1e-3)
check("Q1 판정 가격은 기존 레벨에서만", {q1["rule"]["up"], q1["rule"]["down"]} <=
      {lv["px"] for lv in COUNT["levels"]})
check("Q2 예측은 등록 당시 값 그대로 (사후 조정 없음, 9/28 첫 표의 W-X-Y 40%)",
      next(q for q in sb["questions"] if q["id"] == "Q2")["forecast"] == 0.40)
wxy_qs = [q for q in sb["questions"] if q["event"] == "wxy"]
TABLES = [ol] + list(ol.get("previous") or [])
tbl_of = lambda q: next((t for t in TABLES if t.get("basis_px") == q["basis_px"]), None)
check("W-X-Y 질문 예측 = 등록 당시(같은 기준가) 확률표의 W-X-Y 비중",
      all(tbl_of(q) and abs(q["forecast"] * 100 - tbl_of(q)["wave2_shape_pct_within_S1"]["wxy"]) < 1e-9
          for q in wxy_qs))
check("재평가해도 Q1 예측은 그대로 (새 질문 추가 방식)",
      next(q for q in sb["questions"] if q["id"] == "Q1")["forecast"] == 0.275)
check("재평가 전 확률표가 previous 에 보존", ol.get("previous") and ol["previous"][0]["scenarios_pct"] == {"S1": 55, "S2": 20, "S3": 25})
B = lambda d, lo, hi: {"d": d, "o": lo, "h": hi, "l": lo, "c": hi}
fq = {"rule": {"type": "first_touch", "up": 100.0, "down": 80.0}, "void_if_below": 50.0}
check("first_touch 미결", ew.resolve_question(fq, [B("a", 85, 95)])["state"] == "open")
check("first_touch 위 먼저", ew.resolve_question(fq, [B("a", 85, 95), B("b", 90, 101), B("c", 70, 90)])["outcome"] == "up")
check("first_touch 아래 먼저", ew.resolve_question(fq, [B("a", 79, 95), B("b", 90, 101)])["outcome"] == "down")
check("한 봉이 양쪽 → 보류", ew.resolve_question(fq, [B("a", 79, 101)])["state"] == "ambiguous")
check("무효선 이탈 → void", ew.resolve_question(fq, [B("a", 49, 90)])["state"] == "void")
wq = {"rule": {"type": "wxy_after_c", "top": 100.0, "c_zone": 90.0, "x_frac": 0.382}, "void_if_below": 50.0}
# L=80 → X 성립선 80+0.382*20=87.64
check("W-X-Y: C 영역 → 저점 80 → 38.2% 반등 → 새 저점",
      ew.resolve_question(wq, [B("a", 89, 95), B("b", 80, 88), B("c", 84, 88), B("d", 79, 86)])["outcome"] == "wxy")
check("반등이 저점을 먼저 깨지 않고 38.2% 성립해야 X — 같은 봉에 저점 갱신이면 L 갱신",
      ew.resolve_question(wq, [B("a", 89, 95), B("b", 80, 85), B("c", 78, 88)])["state"] == "open")
check("단일 ABC: X 반등 뒤 고점 돌파가 먼저",
      ew.resolve_question(wq, [B("a", 85, 95), B("b", 82, 89), B("c", 88, 101)])["outcome"] == "abc")
check("C 영역 전에 고점 돌파 → 2파 아님, 무효",
      ew.resolve_question(wq, [B("a", 95, 101)])["state"] == "void")
check("브리어 점수", abs(ew.brier(0.275, False) - 0.075625) < 1e-12 and abs(ew.brier(0.4, True) - 0.36) < 1e-12)
rec = {**COUNT, "scorebook": {"questions": [dict(q1, status="resolved", outcome="down", resolved_on="x")]}}
st = ew.scorebook_status(rec, [])
check("파일에 기록된 결과만 누적에 들어간다 + 기준과 나란히 채점",
      st["cumulative"]["n"] == 1 and abs(st["cumulative"]["forecast"] - 0.275 ** 2) < 1e-12
      and abs(st["cumulative"]["random_walk"] - 0.6524 ** 2) < 1e-12)
st2 = ew.scorebook_status(COUNT, [B("2026-09-29 00:00", 76000, 83000)])
check("봉으로 판정만 나고 파일 미기록이면 누적에 안 들어간다 (커밋 전 점수 없음)",
      st2["cumulative"]["n"] == 0 and st2["rows"][0]["state"] == "resolved")
check("채점 코드는 매매 모듈과 무관 (§1 격리 유지)", "scorebook" not in open("scheduler.py").read()
      and "scorebook" not in open("paper_executor.py").read())

# ---------------------------------------------------------------- §12 C 내부 5파
print("[12] C 내부 5파 카운트 (2026-09-28)")
zu = COUNT["correction"]["zigzag_update_2026_09_28"]
cc = zu["C_count"]
check("C 시작 = B 고점, i < 시작, ii 는 i 와 시작 사이",
      cc["start"]["px"] > cc["ii"]["px"] > cc["i"]["px"])
check("A 구조 점검 기록 (5파·3파 둘 다 가능, 깊이 규칙으로 판정)", "4파 고점 84,665" in zu["A_structure_check"])
check("코드에 C 카운트 가격 하드코딩 없음 (85250 은 파일 키 이름에만)", "83091" not in SRC and "85158" not in SRC
      and all("zigzag_C_targets_from_B_85250" in ln for ln in SRC.splitlines() if "85250" in ln))
H = lambda d, lo, hi: {"d": d, "o": lo, "h": hi, "l": lo, "c": hi}
bars = [H("2026-09-27 12:00", 84400, 85100), H("2026-09-27 14:00", 84400, 84900),
        H("2026-09-28 05:00", 82675, 83500), H("2026-09-28 06:00", 82900, 83300)]
st = ew.c_count_status(cc, bars, 83200)
check("iii 저가 = ii 이후 최저", st["iii_low"] == 82675)
check("iii 길이 배수 = (ii-저가)/i", abs(st["iii_len_x_i"] - (cc["ii"]["px"] - 82675) / (cc["start"]["px"] - cc["i"]["px"])) < 1e-9)
check("iii 목표 1.618배 = ii - 1.618×i", abs(st["iii_targets"][1.618] - (cc["ii"]["px"] - 1.618 * (cc["start"]["px"] - cc["i"]["px"]))) < 1e-6)
check("저점 뒤 반등이 i 저점 위 → iv 아님 플래그", st["above_i_low"] is True and st["invalid"] is False)
st2 = ew.c_count_status(cc, bars[:3] + [H("2026-09-28 06:00", 82800, 82950)], 82900)
check("반등이 i 저점 아래면 iv 가능", st2["above_i_low"] is False)
st3 = ew.c_count_status(cc, bars + [H("2026-09-28 07:00", 84000, 85300)], 85200)
check("ii 고점 돌파 → 카운트 무효", st3["invalid"] is True)
check("ii 시각 이전 봉은 안 본다", ew.c_count_status(cc, [H("2026-09-26 00:00", 70000, 80000)], 83000) is None)
check("C_count 없으면 None", ew.c_count_status(None, bars, 83000) is None)

# ---------------------------------------------------------------- §13 네 번째 시나리오 (삼각수렴)
print("[13] 네 번째 시나리오 — 1파의 5파 안 4파 삼각수렴 (2026-09-28 사용자 가설)")
s4 = COUNT["scenarios"].get("S4_wave4_triangle_in_wave5")
check("네 번째 시나리오 존재 + 제안자 기록", bool(s4) and s4.get("proposed_by") == "user" and s4.get("label"))
tr = s4["triangle"]
check("삼각형 무효선·D 상한은 레벨 표에 있다", {tr["kill_close_below"], tr["D_max"]} <= {lv["px"] for lv in COUNT["levels"]})
check("확률표에 네 번째 시나리오 포함, 합 100", "S4" in ol["scenarios_pct"] and sum(ol["scenarios_pct"].values()) == 100)
check("코드에 삼각형 가격 하드코딩 없음", "82400" not in SRC and "82675" not in SRC and "4688" not in SRC)
S = lambda d, lo, hi, c: {"d": d, "o": c, "h": hi, "l": lo, "c": c}
base = [S("2026-09-28 00:00", 82675, 84992, 83300), S("2026-09-28 06:00", 83000, 83500, 83100)]
t0 = ew.triangle_status(COUNT, base)
check("상자 안이면 살아 있음·경고 없음", t0["alive"] and not t0["killed"] and not t0["d_over"] and not t0["confirmed"])
check("감시 시작 이전 봉은 무시", ew.triangle_status(COUNT, [S("2026-09-27 18:00", 70000, 90000, 70000)] + base)["alive"])
t1 = ew.triangle_status(COUNT, base + [S("2026-09-28 12:00", 82300, 83100, tr["kill_close_below"] - 1)])
check("6시간봉 종가가 무효선 아래 → 무효", t1["killed"] and not t1["alive"])
t2 = ew.triangle_status(COUNT, base + [S("2026-09-28 12:00", 82300, 83100, tr["kill_close_below"] + 50)])
check("저가만 찌르고 종가는 위 → 살아 있음 + C 저점 갱신 표시", t2["alive"] and t2["new_low_below_C"])
t3 = ew.triangle_status(COUNT, base + [S("2026-09-28 12:00", 84000, tr["D_max"] + 100, 85000)])
check("D 상한 초과 → 경고", t3["d_over"] and t3["alive"])
t4 = ew.triangle_status(COUNT, base + [S("2026-09-28 12:00", 84000, tr["confirm_above"] + 10, 87000)])
check("1파 고점 돌파 → 확인 (D 경고 아님)", t4["confirmed"] and not t4["d_over"])
no4 = {**COUNT, "scenarios": {k: v for k, v in COUNT["scenarios"].items() if k != "S4_wave4_triangle_in_wave5"}}
check("삼각형 블록 없으면 None", ew.triangle_status(no4, base) is None)
q5 = next(q for q in sb["questions"] if q["id"] == "Q5")
q6 = next(q for q in sb["questions"] if q["id"] == "Q6")
t5 = tbl_of(q5)
check("Q5 예측 = 등록 당시 표의 삼각형 + 큰 3파 비중",
      bool(t5) and abs(q5["forecast"] * 100 - (t5["scenarios_pct"]["S4"] + t5["scenarios_pct"]["S2"])) < 1e-9)
check("Q6 무작위 보행 = 거리 비율", abs(q6["baselines"]["random_walk"] - (q6["basis_px"] - q6["rule"]["down"]) /
      (q6["rule"]["up"] - q6["rule"]["down"])) < 1e-3)
check("기존 Q1~Q4 예측 무변경", [next(q for q in sb["questions"] if q["id"] == i)["forecast"] for i in ("Q1", "Q2", "Q3", "Q4")]
      == [0.275, 0.40, 0.20, 0.55])

# ---------------------------------------------------------------- §14 ETH 교차 확인
print("[14] ETH 교차 확인 (2026-09-28)")
ec = COUNT.get("eth_cross")
check("eth_cross 블록 존재, 고점 > B > A", bool(ec) and ec["top"]["px"] > ec["B_end"]["px"] > ec["A_end"]["px"])
check("ETH 기준 시각이 BTC 와 같다 (A 끝 날짜·B 끝 시각)",
      ec["A_end"]["ts"][:10] == COUNT["correction"]["A"]["end_date"]
      and ec["B_end"]["ts"] == COUNT["correction"]["zigzag_update_2026_09_28"]["C_count"]["start"]["ts"])
check("코드에 ETH 가격 하드코딩 없음", "2626" not in SRC and "2742" not in SRC and "2807" not in SRC)
check("fetch 가 상품 인자를 받는다 (기본 BTC-USD)", "def fetch(granularity, days, product=PRODUCT)" in SRC)
E = lambda d, lo, hi, c: {"d": d, "o": c, "h": hi, "l": lo, "c": c}
btcA = COUNT["correction"]["A"]["end"]
eth_ok = [E("2026-09-25 10:00", 2700, 2745, 2720), E("2026-09-28 05:00", 2634.38, 2660, 2650)]
btc_brk = [E("2026-09-25 10:00", 84000, 85300, 85000), E("2026-09-28 05:00", btcA - 34, 83533, 83160)]
btc_ok = [E("2026-09-25 10:00", 84000, 85300, 85000), E("2026-09-28 05:00", btcA + 100, 83533, 83160)]
eth_brk = [E("2026-09-25 10:00", 2700, 2745, 2720), E("2026-09-28 05:00", ec["A_end"]["px"] - 1, 2660, 2640)]
r1 = ew.eth_cross_status(ec, eth_ok, btc_brk, btcA)
check("BTC 만 이탈 → 비확인 + 수렴 삼각형 모양", r1["verdict"].startswith("비확인") and r1["contracting"])
check("B 되돌림 % = (B-A)/(고점-A)", abs(r1["B_retrace_pct"] - (ec["B_end"]["px"] - ec["A_end"]["px"]) /
      (ec["top"]["px"] - ec["A_end"]["px"]) * 100) < 1e-9)
check("B 고점 시각 이전 봉은 안 본다 (09-25 10:00 봉 무시)", r1["eth_high"] == 2660)
check("둘 다 이탈 → 확인", ew.eth_cross_status(ec, eth_brk, btc_brk, btcA)["verdict"].startswith("확인"))
check("둘 다 위", ew.eth_cross_status(ec, eth_ok, btc_ok, btcA)["verdict"].startswith("둘 다"))
check("ETH 만 이탈 → 역비확인", ew.eth_cross_status(ec, eth_brk, btc_ok, btcA)["verdict"].startswith("역비확인"))
r5 = ew.eth_cross_status(ec, eth_ok + [E("2026-09-28 10:00", 2700, ec["B_end"]["px"] + 5, 2745)], btc_ok, btcA)
check("ETH 가 B 고점을 넘으면 표시 + 수렴 모양 해제", r5["eth_over_B"] and not r5["contracting"])
check("eth_cross 없으면 None", ew.eth_cross_status(None, eth_ok, btc_ok, btcA) is None)

# ---------------------------------------------------------------- §15 A/W 재계산
print("[15] A/W 재계산 (2026-09-30)")
cor = COUNT["correction"]
aw = cor.get("aw_update_2026_09_30")
check("aw 블록 존재: A/W 시작 > 끝, 끝 시각 기록", bool(aw) and aw["AW"]["start"] > aw["AW"]["end"] and aw["AW"]["end_ts"])
AWs = aw["AW"]["start"] - aw["AW"]["end"]
check("B/X 레벨 가격 = 끝 + 비율 × A/W 크기 (반올림 1달러)",
      all(abs(v["px"] - (aw["AW"]["end"] + float(r) * AWs)) <= 1.0 for r, v in aw["B_levels"].items()))
check("A/W 시작 = 카운트의 5파(=1파) 고점", aw["AW"]["start"] == COUNT["waves"][-1]["price"])
check("9/28 C 내부 카운트는 무효로 기록(지우지 않음)",
      cor["zigzag_update_2026_09_28"]["C_count"].get("status") == "invalid"
      and cor["zigzag_update_2026_09_28"]["C_count"].get("start"))
H = lambda d, lo, hi: {"d": d, "o": lo, "h": hi, "l": lo, "c": hi}
end_ts = aw["AW"]["end_ts"]
before = H("2026-09-27 00:00", 60000, 99999)
after = [H("2026-09-29 00:00", aw["AW"]["end"] + 100, aw["AW"]["end"] + 2000),
         H("2026-09-30 12:00", aw["AW"]["end"] + 500, aw["AW"]["end"] + 3104)]
r = ew.aw_status(aw, [before] + after, aw["AW"]["end"] + 1500)
hi = aw["AW"]["end"] + 3104
check("A/W 끝 이전 봉은 무시", r["bx_high"] == hi and not r["broke_AW_low"])
check("B/X 되돌림 % = (고점-끝)/크기", abs(r["bx_retrace_pct"] - 3104 / AWs * 100) < 1e-9)
check("현재 되돌림 % = (현재가-끝)/크기", abs(r["now_retrace_pct"] - 1500 / AWs * 100) < 1e-9)
check("레벨 도달 = B/X 고점 이상", all(v["hit"] == (hi >= v["px"]) for v in r["levels"].values()))
check("C/Y 잠정 목표 = B/X 고점 - 비율 × 크기",
      all(abs(r["cy_targets"][k] - (hi - k * AWs)) < 1e-9 for k in aw["CY_ratios_of_AW"]))
check("현재가가 B/X 고점보다 높으면 고점으로 반영", ew.aw_status(aw, after, hi + 10)["bx_high"] == hi + 10)
brk = after + [H("2026-09-30 18:00", aw["AW"]["end"] - 1, aw["AW"]["end"] + 200)]
check("A/W 저점 아래 봉 → 이탈 표시", ew.aw_status(aw, brk, aw["AW"]["end"] + 100)["broke_AW_low"])
check("aw 블록 없으면 None", ew.aw_status(None, after, 1.0) is None)
lv_px = {lv["px"] for lv in COUNT["levels"]}
check("새 트리거 가격은 전부 레벨에 있다", all(t["px"] in lv_px for t in COUNT["outlook"]["triggers"]))
alt = COUNT["scenarios"]["S4_wave4_triangle_in_wave5"].get("iv_alternative_2026_09_30")
check("대안 4파 읽기: 겹침선 < A/W 저점 (임펄스 규칙 통과)", bool(alt) and alt["overlap_line"] < aw["AW"]["end"])
q7 = next(q for q in sb["questions"] if q["id"] == "Q7")
check("Q7 무작위 보행 = 거리 비율", abs(q7["baselines"]["random_walk"] - (q7["basis_px"] - q7["rule"]["down"]) /
      (q7["rule"]["up"] - q7["rule"]["down"])) < 1e-3)
check("Q7 판정 가격은 기존 레벨에서만", {q7["rule"]["up"], q7["rule"]["down"]} <= lv_px)
check("Q7 기준가 = 등록 당시 확률표 기준가", bool(tbl_of(q7)))
check("기존 Q1~Q6 예측 무변경", [next(q for q in sb["questions"] if q["id"] == i)["forecast"]
      for i in ("Q1", "Q2", "Q3", "Q4", "Q5", "Q6")] == [0.275, 0.40, 0.20, 0.55, 0.35, 0.40])
check("삼각형 판 표가 previous 에 보존",
      any(t["scenarios_pct"] == {"S1": 40, "S4": 25, "S2": 10, "S3": 25} for t in ol["previous"]))
check("코드에 A/W 가격·레벨 하드코딩 없음",
      not any(x in SRC for x in ("82510", "82,510", "4887", "86908", "81925", "84750", "85614")))

print("[16] 90% 회복 재평가 (2026-10-02)")
q8 = next(q for q in sb["questions"] if q["id"] == "Q8")
check("Q8 무작위 보행 = 거리 비율", abs(q8["baselines"]["random_walk"] - (q8["basis_px"] - q8["rule"]["down"]) /
      (q8["rule"]["up"] - q8["rule"]["down"])) < 1e-3)
check("Q8 판정 가격은 기존 레벨에서만", {q8["rule"]["up"], q8["rule"]["down"]} <= lv_px)
check("Q8 기준가 = 현재 확률표 기준가", q8["basis_px"] == ol["basis_px"])
check("확률표 합 100 · 형태 합 100", sum(ol["scenarios_pct"].values()) == 100 and sum(ol["wave2_shape_pct_within_S1"].values()) == 100)
check("직전 표(9/30 판)가 previous 끝에 보존", ol["previous"][-1]["basis_px"] == 84750.0)
check("발동한 트리거(86,908)는 목록에서 빠짐", all(t["px"] != 86908.0 for t in ol["triggers"]))
check("Q1~Q7 예측 무변경", [next(q for q in sb["questions"] if q["id"] == i)["forecast"]
      for i in ("Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7")] == [0.275, 0.40, 0.20, 0.55, 0.35, 0.40, 0.48])
check("코드에 89,547 하드코딩 없음", "89547" not in SRC and "89,547" not in SRC)

print()
if FAIL:
    print(f"실패 {len(FAIL)}건: " + " | ".join(FAIL))
    sys.exit(1)
print("전부 통과")
