"""
test_time_prop.py — validate_time_prop(A안, 사전 등록 2026-10-22) 로직 고정. 네트워크 없음.

  1. 형성 봉수 수집기의 신호 집합 = 배포 디텍터의 신호 집합 (triple_bottom 인과 판 / equal_lows)
  2. 보유한도 H = clip(round(k·F), 6, 180)
  3. outcome_h(H=30) = method_t.outcome_d 기본값, MAX_HOLD 는 호출 뒤 원상복구
  4. 기록 전용 — DEPLOY_ON_PASS False, 실거래 모듈을 import 하지 않는다
"""
import random

import detector_equal_lows_4h as el
import detector_triple_bottom as tb
import method_t as mt
import validate_time_prop as vt

fails = []


def check(name, ok, info=""):
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"  — {info}"))
    if not ok:
        fails.append(name)


def walk(n, seed, vol=0.02):
    rnd = random.Random(seed)
    px, rows = 100.0, []
    for i in range(n):
        o = px
        c = max(1.0, o * (1 + rnd.gauss(0, vol)))
        h = max(o, c) * (1 + abs(rnd.gauss(0, vol / 2)))
        l = min(o, c) * (1 - abs(rnd.gauss(0, vol / 2)))
        rows.append(dict(o=o, h=h, l=l, c=c, v=100 * (1 + abs(rnd.gauss(0, 0.8))),
                         date=f"2024-{1 + (i // 6) // 28 % 12:02d}-{1 + (i // 6) % 28:02d}", ts=i * 14_400_000))
        px = c
    return rows


# ── 1. 신호 집합 일치 ─────────────────────────────────────────────────────────
n_el = n_tb = 0
ok_el = ok_tb = True
for seed in range(12):
    rows = walk(600, seed)
    a = [s for s, _ in vt.el_signals(rows)]
    ok_el &= a == el.detect(rows)
    n_el += len(a)
    b = [s for s, _ in vt.tb_signals(rows)]
    ok_tb &= b == tb.detect(rows, causal=True)
    n_tb += len(b)
check("equal_lows 형성 수집기 신호 = detector_equal_lows_4h.detect", ok_el)
check("equal_lows 합성 표본에 신호가 있다(공허한 일치 아님)", n_el > 20, n_el)
check("triple_bottom 형성 수집기 신호 = detect(causal=True)", ok_tb)
check("형성 봉수는 양수", all(F > 0 for seed in range(4) for _, F in vt.el_signals(walk(600, seed))))
check("equal_lows F 는 LOOKBACK 이하", all(F <= el.LOOKBACK for seed in range(4) for _, F in vt.el_signals(walk(600, seed))))

# ── 2. 보유한도 ──────────────────────────────────────────────────────────────
check("H 하한 6", vt.hold_limit(2, 1.0) == 6)
check("H 상한 180", vt.hold_limit(500, 1.0) == 180)
check("H = round(k·F)", vt.hold_limit(41, 1.0) == 41 and vt.hold_limit(41, 0.5) == 20 and vt.hold_limit(41, 2.0) == 82)
check("주 판정 k=1.0, 진단 0.5/2.0", vt.K_MAIN == 1.0 and vt.K_DIAG == (0.5, 2.0))

# ── 3. 청산 = 방식D, 보유한도만 다르다 ────────────────────────────────────────
rows = walk(400, 99)
mt.REGMAP = {r["date"]: "bull_btc" for r in rows}
mh0 = mt.MAX_HOLD
same30 = all(vt.outcome_h(rows, si, 30) == mt.outcome_d(rows, si, "long", set()) for si in range(50, 300, 7))
check("outcome_h(H=30) = outcome_d 기본(30봉)", same30)
check("outcome_h 뒤 MAX_HOLD 원상복구", mt.MAX_HOLD == mh0 == 30)
h_long = [vt.outcome_h(rows, si, 90)[1] for si in range(50, 300, 7)]
check("보유한도는 상한으로만 작동(H=90 보유 <= 90)", all(h <= 90 for h in h_long))

# ── 4. 기록 전용 ─────────────────────────────────────────────────────────────
src = open("validate_time_prop.py", encoding="utf-8").read()
check("DEPLOY_ON_PASS False", vt.DEPLOY_ON_PASS is False)
check("실거래 모듈 import 없음", not any(f"import {m}" in src for m in ("scheduler", "paper_executor", "exchange")))
check("레짐 전환 청산을 켠다(mt.REGMAP 설정)", "mt.REGMAP = regmap" in src)

print(f"\n{len(fails)} failed")
raise SystemExit(1 if fails else 0)
