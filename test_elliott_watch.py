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
check("가장 최근 W-X-Y 질문의 예측 = 현재 확률표의 W-X-Y 비중",
      abs(wxy_qs[-1]["forecast"] * 100 - ol["wave2_shape_pct_within_S1"]["wxy"]) < 1e-9)
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

print()
if FAIL:
    print(f"실패 {len(FAIL)}건: " + " | ".join(FAIL))
    sys.exit(1)
print("전부 통과")
