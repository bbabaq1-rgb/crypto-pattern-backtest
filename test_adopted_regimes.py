"""
scheduler.adopted_regime_ok — 채택 패턴 항목별 레짐 게이트 (2026-09-05).

고정하는 성질:
  - `regimes` 필드가 없는 기존 항목은 **종전 동작과 동일**: 1d 는 게이트 없음(ih/marubozu),
    4h 는 전역 bull-only(three_soldiers_4h)
  - "all" 은 전 레짐 허용, 리스트는 그 레짐에서만
  - universe.json 의 현 배포 항목들이 필드 없이도 종전과 같은 셀에서 켜진다
실행: python test_adopted_regimes.py
"""
import json
import sys

import scheduler as sch

fails = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f" — {detail}"))
    cond or fails.append(name)


REG = ["bull_btc", "bull_altseason", "bear", "sideways"]
legacy = {"pattern": "x", "module": "m", "direction": "long"}

check("1d 기존 항목(regimes 없음)은 전 레짐 허용", all(sch.adopted_regime_ok(legacy, r, "1d") for r in REG))
check("4h 기존 항목(regimes 없음)은 bull 둘만 — 종전 ADOPTED4H_REGIME 과 동일",
      [r for r in REG if sch.adopted_regime_ok(legacy, r, "4h")] == ["bull_btc", "bull_altseason"])
check("ADOPTED4H_REGIME 상수는 불변", set(sch.ADOPTED4H_REGIME) == {"bull_btc", "bull_altseason"})

only_btc = dict(legacy, regimes=["bull_btc"])
check("regimes=[bull_btc] 는 bull_btc 에서만 (1d)", [r for r in REG if sch.adopted_regime_ok(only_btc, r, "1d")] == ["bull_btc"])
check("regimes=[bull_btc] 는 bull_btc 에서만 (4h)", [r for r in REG if sch.adopted_regime_ok(only_btc, r, "4h")] == ["bull_btc"])
bear_only = dict(legacy, regimes=["bear"])
check("regimes=[bear] 는 4h 에서도 bear 허용(전역 bull-only 를 덮어쓴다)",
      sch.adopted_regime_ok(bear_only, "bear", "4h") and not sch.adopted_regime_ok(bear_only, "bull_btc", "4h"))
allr = dict(legacy, regimes="all")
check("regimes='all' 은 전 레짐 (4h 포함)", all(sch.adopted_regime_ok(allr, r, "4h") for r in REG))
check("regimes=[] 는 아무 레짐도 허용 안 함", not any(sch.adopted_regime_ok(dict(legacy, regimes=[]), r, "1d") for r in REG))

# 현 universe.json 배포 항목 — 필드 없이 종전 셀 그대로
u = json.load(open("universe.json", encoding="utf-8"))
for ap in u.get("adopted_patterns", []):
    check(f"현 1d 채택 {ap['pattern']} 은 전 레짐에서 켜짐(종전 동작)",
          all(sch.adopted_regime_ok(ap, r, ap.get("tf", "1d")) for r in REG))
for ap in u.get("adopted_4h_patterns", []):
    ok = [r for r in REG if sch.adopted_regime_ok(ap, r, "4h")]
    check(f"현 4h 채택 {ap['pattern']} 은 bull 둘에서만(종전 동작)", ok == ["bull_btc", "bull_altseason"], ok)

src = open("scheduler.py", encoding="utf-8").read()
check("1d adopted 루프가 게이트를 호출", "adopted_regime_ok(ap, regime, ap_tf)" in src)
check("4h 블록이 게이트를 호출", 'adopted_regime_ok(ap, regime, "4h")' in src)
check("4h 숏 항목은 손절가가 진입가 위", "round(entry4 * (1 + STOP), 4)" in src)

print(f"\n{len(fails)} failed")
sys.exit(1 if fails else 0)
