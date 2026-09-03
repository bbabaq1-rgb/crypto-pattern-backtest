"""
디텍터 인과성(룩어헤드 제거) 검증 — 2026-09-03.

확인 대상:
  - 하모닉: detect(rows) 의 모든 신호 i 는 detect(rows[:i+1]) 에도 있어야 한다(마지막 봉에서
    재현 가능 = 실거래에서 발화 가능). 종전(confirm=False)은 이 성질이 0/N 으로 깨진다.
  - 하모닉 신호 = 종전 D 인덱스 + PIVOT_WINDOW (확정 봉)
  - triple_bottom: 같은 인과성. causal=False 는 L3+1·L3+2 돌파를 세지만 causal=True 는 안 센다.
    causal=True 신호 ⊆ causal=False 신호 (실거래 신호 집합 불변의 근거)
  - 스케줄러 하모닉 4h 블록 정지, universe 의 bat_1h/butterfly_1h 정지, registry 상태

실행: python test_confirm_bar.py
"""
import random
import sys
import json

import detector_harmonic_base as hb
import detector_bat, detector_gartley, detector_butterfly
import detector_triple_bottom as tb

fails = []


def check(n, c, d=""):
    print(("PASS " if c else "FAIL ") + n + ("" if c else f" — {d}"))
    c or fails.append(n)


def mkrows(n, seed, vol=0.02):
    random.seed(seed)
    px, rows = 100.0, []
    for i in range(n):
        nxt = px * (1 + random.gauss(0, vol))
        rows.append(dict(o=px, h=max(px, nxt) * (1 + abs(random.gauss(0, 0.004))),
                         l=min(px, nxt) * (1 - abs(random.gauss(0, 0.004))), c=nxt,
                         v=100 * (1 + abs(random.gauss(0, 0.5))), date=str(i), ts=i))
        px = nxt
    return rows


def causal_ok(detect, rows):
    """모든 신호가 그 봉까지의 데이터만으로 재현되는가. (총 신호 수, 재현 수)"""
    sigs = detect(rows)
    rep = sum(1 for i in sigs if i in set(detect(rows[:i + 1])))
    return len(sigs), rep


# ── 1. 하모닉 ────────────────────────────────────────────────────────────────
tot = rep = 0
tot_old = rep_old = 0
shift_ok = True
for seed in range(120):
    rows = mkrows(400, seed)
    for mod in (detector_bat, detector_gartley, detector_butterfly):
        n1, r1 = causal_ok(mod.detect, rows); tot += n1; rep += r1
        old = hb.detect_harmonic(rows, mod.CFG, confirm=False)
        n0, r0 = causal_ok(lambda rr: hb.detect_harmonic(rr, mod.CFG, confirm=False), rows)
        tot_old += n0; rep_old += r0
        new = mod.detect(rows)
        if sorted(new) != sorted(d + hb.PIVOT_WINDOW for d in old if d + hb.PIVOT_WINDOW < len(rows)):
            shift_ok = False
check(f"하모닉(확정 봉): 신호 {tot}건 전부 마지막 봉에서 재현(인과)", tot > 0 and rep == tot, (tot, rep))
check(f"하모닉(종전 D 봉): 신호 {tot_old}건 중 재현 0 — 룩어헤드 확인", tot_old > 0 and rep_old == 0, (tot_old, rep_old))
check("하모닉 신호 = 종전 D 인덱스 + PIVOT_WINDOW", shift_ok)
# 마지막 봉 발화 가능성: 확정 봉이 마지막 봉인 경우를 만들어 본다
hit = 0
for seed in range(120):
    rows = mkrows(400, seed)
    for mod in (detector_bat, detector_gartley, detector_butterfly):
        for i in mod.detect(rows):
            if i == len(rows[:i + 1]) - 1 and (len(rows[:i + 1]) - 1) in set(mod.detect(rows[:i + 1])):
                hit += 1
check("하모닉: 마지막 봉이 신호가 되는 경우가 존재(스케줄러 조건 충족 가능)", hit > 0, hit)

# ── 2. triple_bottom ─────────────────────────────────────────────────────────
tot = rep = 0; tot_old = rep_old = 0; subset_ok = True; early_old = 0
for seed in range(150):
    rows = mkrows(500, seed, vol=0.03)
    n1, r1 = causal_ok(tb.detect, rows); tot += n1; rep += r1
    old_fn = lambda rr: tb.detect(rr, causal=False)
    n0, r0 = causal_ok(old_fn, rows); tot_old += n0; rep_old += r0
    new, old = set(tb.detect(rows)), set(old_fn(rows))
    if not new <= old:
        subset_ok = False
    early_old += len(old - new)
check(f"triple_bottom(causal): 신호 {tot}건 전부 인과", tot > 0 and rep == tot, (tot, rep))
check(f"triple_bottom(종전): 신호 {tot_old}건 중 {tot_old - rep_old}건 비인과(L3 미확정 돌파)",
      tot_old > rep_old, (tot_old, rep_old))
check("causal 신호 ⊆ 종전 신호 (실거래 신호 집합 불변)", subset_ok)
check("종전에만 있던 신호 = 비인과 신호 수와 일치", early_old == tot_old - rep_old, (early_old, tot_old - rep_old))

# ── 3. 배포 정지 상태 ────────────────────────────────────────────────────────
import scheduler as sch
check("스케줄러 하모닉 4h 블록 정지(HARMONIC_FOCUS 비어 있음)", sch.HARMONIC_FOCUS == [])
check("정지 목록에 gartley/bat/butterfly", {p for p, _ in sch.HARMONIC_SUSPENDED} == {"gartley", "bat", "butterfly"})
u = json.load(open("universe.json", encoding="utf-8"))
ad = {a["pattern"] for a in u.get("adopted_1h_patterns", [])}
su = {a["pattern"] for a in u.get("suspended_1h_patterns", [])}
check("bat_1h/butterfly_1h 는 adopted 에서 빠지고 suspended 에 있음",
      not ({"bat_1h", "butterfly_1h"} & ad) and su == {"bat_1h", "butterfly_1h"}, (ad, su))
check("cascade 는 계속 adopted", "cascade_fade_long_1h" in ad)
r = json.load(open("registry.json", encoding="utf-8"))
st = {p["id"]: p["status"] for p in r["patterns"]}
check("registry: 하모닉 5종 suspended_lookahead",
      all(st.get(k) == "suspended_lookahead" for k in ("gartley", "bat", "butterfly", "bat_1h", "butterfly_1h")), st)
check("registry: triple_bottom_1w 는 passed 유지(실거래 신호 집합 불변)", st.get("triple_bottom_1w") == "passed")

print(f"\n{len(fails)} failed")
sys.exit(1 if fails else 0)
