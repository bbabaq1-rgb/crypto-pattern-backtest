"""
direction_switch 라우팅 오버라이드 검증 (네트워크 없음).

  - ROUTING_OVERRIDES 가 decide() 결과를 덮어쓰고, 없는 셀은 decide() 그대로
  - (bear, fvg) 는 FLAT 으로 고정 — 2026-09-04 사용자 결정("bear 숏 끄고").
    regime_switch.json 이 bear fvg 숏을 +2.54% 로 보고 있어도 표는 FLAT 이어야 한다
  - main() 이 direction_switch.json 에 routing/overrides/current 를 쓰고 bear/fvg 가 FLAT
  - 스케줄러 소비 방식(route.get(pat, "FLAT")) 기준으로 bear 에서 fvg 신호가 나가지 않음
실행: python test_direction_switch.py
"""
import json
import os
import sys
import tempfile

import direction_switch as ds
import regime_switch as rs

fails = []


def check(n, c, d=""):
    print(("PASS " if c else "FAIL ") + n + ("" if c else f" — {d}"))
    c or fails.append(n)


# 1. decide() 기본 동작
check("decide: 롱만 양수 -> long", ds.decide(0.02, 30, -0.01, 30)[0] == "long")
check("decide: 숏만 양수 -> short", ds.decide(-0.02, 30, 0.01, 30)[0] == "short")
check("decide: 둘 다 양수면 큰 쪽", ds.decide(0.01, 30, 0.03, 30)[0] == "short")
check("decide: n<MIN_N 은 무시 -> FLAT", ds.decide(0.05, ds.MIN_N - 1, 0.05, 5)[0] == "FLAT")
check("decide: 둘 다 음수 -> FLAT", ds.decide(-0.01, 50, -0.02, 50)[0] == "FLAT")

# 2. 오버라이드 표 자체
check("override: (bear, fvg) 는 FLAT", ds.ROUTING_OVERRIDES.get(("bear", "fvg")) == "FLAT")
check("override: bear engulfing 은 건드리지 않음", ("bear", "engulfing") not in ds.ROUTING_OVERRIDES)
check("override: 값은 long/short/FLAT 만",
      all(v in ("long", "short", "FLAT") for v in ds.ROUTING_OVERRIDES.values()))
check("override: 키는 (REGIMES x FOCUS) 안",
      all(rg in ds.REGIMES and pat in ds.FOCUS for rg, pat in ds.ROUTING_OVERRIDES))

# 3. main() 을 임시 디렉터리에서 실행 — regime_switch.json 은 bear fvg 숏이 강하게 양수인
#    합성 표(현 저장소 값과 같은 방향)로 만들어 decide() 만이면 'short' 가 나오게 한다.
def cell(n, mean):
    return {"n": n, "mean": mean}


bp = {}
for pat in ds.FOCUS:
    bp[pat] = {}
    bp[pat + "_short"] = {}
    for rg in ds.REGIMES:
        bp[pat][rg] = cell(0, None)
        bp[pat + "_short"][rg] = cell(0, None)
bp["fvg"]["bear"] = cell(140, 0.0021)
bp["fvg_short"]["bear"] = cell(164, 0.0254)          # decide() 만이면 short
bp["engulfing"]["bear"] = cell(22, 0.0247)
bp["engulfing_short"]["bear"] = cell(21, 0.0088)     # decide() -> long (더 큼)
bp["fvg"]["bull_btc"] = cell(265, 0.0258)
bp["fvg_short"]["bull_btc"] = cell(198, -0.0365)

decided = {}
for rg in ds.REGIMES:
    for pat in ds.FOCUS:
        lo = bp[pat][rg]; sh = bp[pat + "_short"][rg]
        decided[(rg, pat)] = ds.decide(lo["mean"], lo["n"], sh["mean"], sh["n"])[0]
check("합성 표: decide() 만이면 bear fvg 는 short", decided[("bear", "fvg")] == "short")

cwd = os.getcwd()
with tempfile.TemporaryDirectory() as td:
    os.chdir(td)
    try:
        json.dump({"by_pattern": bp}, open("regime_switch.json", "w"))
        rs.build_regime_map = lambda *a, **k: {"2026-09-04": "bear"}
        ds.main()
        out = json.load(open("direction_switch.json", encoding="utf-8"))
    finally:
        os.chdir(cwd)

routing = out["routing"]
check("main: bear/fvg 는 FLAT (오버라이드 적용)", routing["bear"]["fvg"] == "FLAT")
check("main: bear/engulfing 은 decide() 그대로 long", routing["bear"]["engulfing"] == "long")
check("main: bull_btc/fvg 는 decide() 그대로 long", routing["bull_btc"]["fvg"] == "long")
check("main: 오버라이드 없는 셀은 전부 decide() 와 동일",
      all(routing[rg][pat] == decided[(rg, pat)]
          for rg in ds.REGIMES for pat in ds.FOCUS if (rg, pat) not in ds.ROUTING_OVERRIDES))
check("main: overrides 블록 기록", out.get("overrides", {}).get("bear/fvg") == "FLAT")
check("main: current.action 도 FLAT", out["current"]["action"]["fvg"] == "FLAT")

# 4. 스케줄러 소비 경로 재현 — d = route.get(pat, "FLAT"); d != direction 이면 스킵
route = routing.get("bear", {})
check("스케줄러 소비: bear 에서 fvg 숏 신호는 라우팅 불일치로 스킵",
      route.get("fvg", "FLAT") != "short")
check("스케줄러 소비: bear 에서 fvg 롱도 나가지 않음(FLAT)",
      route.get("fvg", "FLAT") != "long")
check("스케줄러 소비: bear engulfing 롱은 그대로", route.get("engulfing", "FLAT") == "long")

# 5. 저장소의 실제 direction_switch.json 도 정합
try:
    real = json.load(open(os.path.join(cwd, "direction_switch.json"), encoding="utf-8"))
    check("저장소 direction_switch.json: bear/fvg FLAT", real["routing"]["bear"]["fvg"] == "FLAT")
except FileNotFoundError:
    check("저장소 direction_switch.json 존재", False, "파일 없음")

print("\n" + ("ALL PASS (%d)" % 0 if not fails else "FAILS: %s" % fails))
sys.exit(1 if fails else 0)
