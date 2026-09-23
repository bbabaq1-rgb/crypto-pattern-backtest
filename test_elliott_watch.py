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

print()
if FAIL:
    print(f"실패 {len(FAIL)}건: " + " | ".join(FAIL))
    sys.exit(1)
print("전부 통과")
