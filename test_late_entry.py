"""
triple_bottom '지각 진입(L3+3)' 모드·사전 등록 시험 고정 — 2026-09-05.

확인 대상:
  - detect(mode="breakout") 는 종전 detect 와 동일(기본값). detect == detect_detail 의 sig 열.
  - late 신호 = 미확정 돌파 셋업의 L3+PIVOT_HALF, 종가 > 넥라인. late_nohold ⊇ late.
    late_nohold 신호 집합 == {L3+3 | 종전(룩어헤드) 판의 미확정 돌파 셋업, L3+3 < n}.
  - late 계열은 인과적: 모든 신호가 rows[:i+1] 에서 재현.
  - late 와 causal(breakout) 은 셋업(돌파봉)이 겹치지 않는다.
  - 조작 시나리오: 돌파가 L3+1 에서 난 삼중바닥 → old 는 L3+1, causal 은 없음, late 는 L3+3;
    L3+3 종가가 넥라인 아래로 돌아오면 late 없음·late_nohold 만.
  - validate_late_entry: arm 목록·주 판정 arm·코호트·판정 함수 truth table·게이트 v2 k=n·감쇠 곡선.
  - 워크플로·tests.yml 등재, 스케줄러가 기본 모드(breakout)만 부르는지(정지 패턴 무영향).

실행: python test_late_entry.py
"""
import random
import sys

import detector_triple_bottom as tb
import validate_late_entry as vl

fails = []


def check(n, c, d=""):
    print(("PASS " if c else "FAIL ") + n + ("" if c else f" — {d}"))
    c or fails.append(n)


def mkrows(n, seed, vol=0.03):
    random.seed(seed)
    px, rows = 100.0, []
    for i in range(n):
        nxt = px * (1 + random.gauss(0, vol))
        rows.append(dict(o=px, h=max(px, nxt) * (1 + abs(random.gauss(0, 0.004))),
                         l=min(px, nxt) * (1 - abs(random.gauss(0, 0.004))), c=nxt,
                         v=100 * (1 + abs(random.gauss(0, 0.5))), date=f"{i:04d}", ts=i * 86_400_000 * 7))
        px = nxt
    return rows


def triple_bottom_rows(brk_off=1, hold=True, n=120):
    """L1=40, L2=50, L3=60 저점 85, 그 외 100 근처. 돌파 = L3+brk_off 종가 104(거래량 4배).
    hold=False 면 L3+3 종가가 넥라인 아래(99)."""
    rows = []
    for i in range(n):
        base = 100.0 + 0.01 * i                     # 완만한 단조 상승(잡음 저점 없음)
        o = h = l = c = base
        h, l = base + 0.6, base - 0.6
        v = 100.0
        if i in (40, 50, 60):
            l, c = 85.0, 86.0
        if i in (41, 51, 61):
            o = 86.0
        rows.append(dict(o=o, h=h, l=l, c=c, v=v, date=f"{i:04d}", ts=i * 86_400_000 * 7))
    brk = 60 + brk_off
    rows[brk].update(c=104.0, h=104.5, v=400.0)
    for j in range(brk + 1, 60 + tb.PIVOT_HALF + 1):
        rows[j].update(c=103.0, h=103.5, l=101.5, o=103.0)
    if not hold:
        rows[60 + tb.PIVOT_HALF].update(c=99.0, l=98.5, h=103.0)
    for j in range(60 + tb.PIVOT_HALF + 1, n):
        rows[j].update(c=103.0, h=103.5, l=102.0, o=103.0)
    return rows


# ── 1. 종전 동작 불변 · detail 일치 ─────────────────────────────────────────
same = True
for seed in range(200):
    rows = mkrows(500, seed)
    for causal in (True, False):
        a = tb.detect(rows, causal=causal)
        b = [d["sig"] for d in tb.detect_detail(rows, causal=causal)]
        if a != b or a != tb.detect(rows, causal=causal, mode="breakout"):
            same = False
check("detect(기본) == detect(mode='breakout') == detail 의 sig", same)
check("기본 mode 는 breakout (스케줄러 mod.detect(rows) 무영향)", tb.detect.__defaults__ == (True, "breakout"))

# ── 2. late 정의 (합성 랜덤 + 조작 시나리오) ────────────────────────────────
def_ok = sub_ok = disj_ok = causal_ok = True
n_late = n_nohold = n_early = 0
for seed in range(400):
    rows = mkrows(500, seed)
    n = len(rows)
    early = vl.early_setups(rows)
    n_early += len(early)
    want_nohold = {d["L3"] + tb.PIVOT_HALF for d in early if d["L3"] + tb.PIVOT_HALF < n}
    nohold = tb.detect(rows, mode="late_nohold")
    late = tb.detect(rows, mode="late")
    n_late += len(late); n_nohold += len(nohold)
    if set(nohold) != want_nohold:
        def_ok = False
    if not set(late) <= set(nohold):
        sub_ok = False
    for d in tb.detect_detail(rows, mode="late"):
        if not (d["sig"] == d["L3"] + tb.PIVOT_HALF and d["L3"] < d["brk"] < d["L3"] + tb.PIVOT_HALF
                and rows[d["sig"]]["c"] > d["neck"]):
            def_ok = False
    if {d["brk"] for d in tb.detect_detail(rows, mode="late")} & {d["brk"] for d in tb.detect_detail(rows, causal=True)}:
        disj_ok = False
    for i in late + nohold:
        mode = "late" if i in late else "late_nohold"
        if i not in set(tb.detect(rows[:i + 1], mode=mode)):
            causal_ok = False
check(f"late_nohold == 미확정 셋업의 L3+3 (합성 {n_early}건 중 {n_nohold}건 산출)", def_ok and n_early > 0, (n_early, n_nohold))
check(f"late ⊆ late_nohold, late 는 종가>넥라인 ({n_late}건)", sub_ok)
check("late 와 causal(breakout) 셋업(돌파봉) 불교차", disj_ok)
check("late 계열 신호 전부 인과(rows[:i+1] 재현)", causal_ok)

rows = triple_bottom_rows(brk_off=1, hold=True)
old = tb.detect(rows, causal=False); cau = tb.detect(rows, causal=True)
late = tb.detect(rows, mode="late"); nohold = tb.detect(rows, mode="late_nohold")
check("시나리오: 종전 판은 L3+1 돌파봉 신호", old == [61], old)
check("시나리오: causal 판은 신호 없음(미확정 돌파)", cau == [], cau)
check("시나리오: late 신호 = L3+3 = 63", late == [63] and nohold == [63], (late, nohold))
d = tb.detect_detail(rows, mode="late")[0]
check("시나리오: detail L1/L2/L3/brk", (d["L1"], d["L2"], d["L3"], d["brk"]) == (40, 50, 60, 61), d)
check("시나리오: L3+3 이전 데이터로는 신호 없음(L3 미확정)", tb.detect(rows[:63], mode="late") == [])
check("시나리오: L3+3 까지의 데이터로 마지막 봉이 신호(스케줄러 조건 충족 가능)", tb.detect(rows[:64], mode="late") == [63])
rows2 = triple_bottom_rows(brk_off=1, hold=False)
check("시나리오: L3+3 종가가 넥라인 아래면 late 없음, late_nohold 만",
      tb.detect(rows2, mode="late") == [] and tb.detect(rows2, mode="late_nohold") == [63])
rows3 = triple_bottom_rows(brk_off=2, hold=True)
check("시나리오: L3+2 돌파도 late = L3+3", tb.detect(rows3, mode="late") == [63] and tb.detect(rows3, causal=True) == [])
rows4 = triple_bottom_rows(brk_off=3, hold=True)
check("시나리오: L3+3 돌파는 확정 후 돌파 → causal 신호, late 아님",
      tb.detect(rows4, causal=True) == [63] and tb.detect(rows4, mode="late") == [])
try:
    tb.detect(rows, mode="nope"); bad = False
except ValueError:
    bad = True
check("잘못된 mode 는 ValueError", bad)

# ── 3. validate_late_entry 고정 ─────────────────────────────────────────────
check("arm 5종", set(vl.ARMS) == {"late", "late_nohold", "causal", "early_ceiling", "union_live"})
check("주 판정 arm = late, 실거래 코호트 = all(1w 는 유니버스 전체), holdout 365일/n>=10",
      vl.PRIMARY == "late" and vl.LIVE_COHORT == "all" and vl.HOLDOUT_DAYS == 365 and vl.HOLDOUT_MIN_N == 10)
check("TF 1w, 1d 1800일(종전 등재·재검증과 같은 창), 시드 42/부트 1000", vl.TF == "1w" and vl.FETCH_1D_DAYS == 1800 and (vl.SEED, vl.BOOT_N) == (42, 1000))
rb = {f"S{i}": mkrows(500, i) for i in range(60)}
ec = {s: vl.ARMS["early_ceiling"](r) for s, r in rb.items()}
check("early_ceiling 신호 = 미확정 셋업 돌파봉", all(set(v) == {d["brk"] for d in vl.early_setups(rb[s])} for s, v in ec.items()))
un = {s: vl.ARMS["union_live"](r) for s, r in rb.items()}
check("union_live = late ∪ causal", all(set(v) == set(tb.detect(rb[s], mode="late")) | set(tb.detect(rb[s])) for s, v in un.items()))

# gate_v2: k=n 베이스라인, v2 조건
_rng = random.Random(1)
pool = [_rng.gauss(0, 0.05) for _ in range(5000)]
good = [dict(sym="A", date=f"{2000 + i // 12:04d}-{i % 12 + 1:02d}-01", ret=0.12 if i % 3 else -0.05) for i in range(60)]
bad_ = [dict(sym="A", date=f"{2000 + i // 12:04d}-{i % 12 + 1:02d}-01", ret=0.20 if i % 4 == 0 else -0.05) for i in range(60)]
g1 = vl.gate_v2("good", good, pool); g2 = vl.gate_v2("lottery", bad_, pool)
check("gate_v2: 승률 67% 양수 셀 PASSED", g1["verdict"] == "PASSED", g1["reason"])
check("gate_v2: 승률 25% 복권형은 승률 조건으로 REJECTED(v2)", g2["verdict"] == "REJECTED" and "win" in g2["reason"], g2["reason"])
check("gate_v2: 베이스라인 평균 ≈ 풀 평균(k=n)", abs(g1["base_mean"] - sum(pool) / len(pool)) < 0.01)
oos, pos = vl.oos_quartiles(good)
check("OOS 4분위 결정론", len(oos) == 4 and pos == 4 and sum(o["n"] for o in oos) == 60)
check("n<20 이면 OOS 미평가", vl.oos_quartiles(good[:10]) == ([], 0))

# decide truth table
def cf(c1=True, c2p=True, c2=True, c3=True):
    return dict(c1_live_cohort=c1, c2_possible=c2p, c2_holdout=c2, c3_equity=c3,
                gate=dict(reason="x"), holdout=dict(n=3 if not c2p else 20, mean=0.01 if c2 else -0.01))
P = dict(verdict="PASSED", reason=""); R = dict(verdict="REJECTED", reason="boot_p=0.3")
check("decide: 1단계+C1+C2+C3 → PASSED", vl.decide(P, cf())[0] == "PASSED")
check("decide: 1단계 통과·holdout 표본 부족 → INCONCLUSIVE", vl.decide(P, cf(c2p=False, c2=False))[0] == "INCONCLUSIVE")
check("decide: 1단계 탈락이면 holdout 부족이라도 REJECTED", vl.decide(R, cf(c2p=False, c2=False))[0] == "REJECTED")
check("decide: C1 탈락 → REJECTED", vl.decide(P, cf(c1=False))[0] == "REJECTED")
check("decide: holdout 음수 → REJECTED", vl.decide(P, cf(c2=False))[0] == "REJECTED")
check("decide: 자산곡선 탈락 → REJECTED", vl.decide(P, cf(c3=False))[0] == "REJECTED")
check("decide: 사유 문자열 채움", "C3" in " ".join(vl.decide(P, cf(c3=False))[1]))

dec = vl.decay_curve(rb)
check("감쇠 곡선 키 brk+0..3 / L3+3 / L3+3&유지 / brk−L3", set(dec["by_delay"]) == {"brk+0", "brk+1", "brk+2", "brk+3"}
      and "at_L3p3" in dec and "at_L3p3_hold" in dec and set(dec["brk_minus_L3"]) <= {1, 2})
check("감쇠 곡선 n: brk+0 ≥ L3+3 ≥ L3+3&유지", dec["by_delay"]["brk+0"]["n"] >= dec["at_L3p3"]["n"] >= dec["at_L3p3_hold"]["n"])

# live_sigs on synthetic (regmap 없음 → 레짐 None, 방식D 손절/만기만)
ls = vl.live_sigs(vl.ARMS["late_nohold"], rb, {})
check("live_sigs: 방식D 필드·truncated 플래그", all({"ret", "hold", "reason", "stop_pct", "vol", "truncated", "t_in", "t_out"} <= set(x) for x in ls)
      and all(x["stop_pct"] == vl.STOP for x in ls))

# ── 4. 등재·워크플로 ─────────────────────────────────────────────────────────
wf = open(".github/workflows/late_entry.yml", encoding="utf-8").read()
check("워크플로: 테스트 → 시험 → 아티팩트", "python test_late_entry.py" in wf and "python validate_late_entry.py" in wf and "_late_entry.json" in wf)
check("tests.yml 에 test_late_entry 등재", "test_late_entry.py" in open(".github/workflows/tests.yml", encoding="utf-8").read())
sch = open("scheduler.py", encoding="utf-8").read()
check("스케줄러는 mode 를 넘기지 않음(정지된 triple_bottom 1w 동작 불변)", "mode=" not in sch.split("adopted_patterns")[1][:3000])

print(f"\n{len(fails)} failed")
sys.exit(1 if fails else 0)
