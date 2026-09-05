"""
1w 전용 청산 사전 등록 시험 고정 — 2026-09-06.

확인 대상:
  - outcome_close_rule: 재해 손절(저가) 우선 → 익절(종가) → 종가 손절 → 구조/넥라인, 만기 종가·truncated 플래그
  - 재해 손절 없음(cat=None)·기본 파라미터면 detlib.outcome(동결 라벨)과 수익률 완전 일치 (A_label = 라벨 + 재해 손절)
  - A_label 은 저가가 −10% 를 찍어도 종가가 안 깨지면 안 나간다(방식D 와의 차이의 핵심)
  - outcome_d_close: 종가 −8% 판정, 레짐 전환·만기 시가는 method_s.outcome 과 동일
  - arm D 는 method_s.outcome 그대로
  - decide truth table / 사전 등록 상수(holdout 730, 주 판정 셀, arm 6종, 풀 매핑) / 워크플로·tests.yml
  - 짝지음 함수

실행: python test_exit_1w.py
"""
import random
import sys

import detlib
import method_s as ms
import validate_exit_1w as ve

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
                         v=100.0, date=f"{i:04d}", ts=i * 7 * 86_400_000))
        px = nxt
    return rows


def flat(n=40, px=100.0):
    return [dict(o=px, h=px, l=px, c=px, v=1.0, date=f"{i:04d}", ts=i) for i in range(n)]


FEE = detlib.FEE
none_lab = lambda j: None

# ── 1. 종가 규칙 청산 ─────────────────────────────────────────────────────────
rows = flat(); rows[3].update(c=111.0, h=112.0)
r, h, why, tr = ve.outcome_close_rule(rows, 0)
check("익절: 종가 ≥ +10% 인 봉의 종가로 청산", why == "tp" and h == 3 and abs(r - (0.11 - FEE)) < 1e-12, (r, h, why))
rows = flat(); rows[2].update(c=89.0, l=88.0)
r, h, why, tr = ve.outcome_close_rule(rows, 0)
check("종가 손절: 종가 ≤ −10%", why == "sl_close" and h == 2 and abs(r - (-0.11 - FEE)) < 1e-12)
rows = flat(); rows[2].update(l=88.0, c=99.0)                # 저가만 −12%, 종가 −1%
r, h, why, tr = ve.outcome_close_rule(rows, 0)
check("A_label 핵심: 저가가 −10% 를 찍어도 종가가 버티면 안 나감", why == "timestop" and h == 20, (why, h))
rows = flat(); rows[2].update(l=79.0, c=99.0)                # 저가 −21%
r, h, why, tr = ve.outcome_close_rule(rows, 0)
check("재해 손절: 저가 ≤ −20% 면 −20% 로 청산(우선)", why == "cat_stop" and h == 2 and abs(r - (-0.20 - FEE)) < 1e-12)
rows = flat(); rows[2].update(l=79.0, c=112.0, h=113.0)      # 같은 봉 재해+익절 → 재해 우선(보수)
check("같은 봉 재해 손절·익절 동시 → 재해 우선", ve.outcome_close_rule(rows, 0)[2] == "cat_stop")
rows = flat(); rows[4].update(c=94.0, l=93.0)
r, h, why, tr = ve.outcome_close_rule(rows, 0, target=None, stop_close=None, struct_px=95.0)
check("구조적 손절: 종가 < base_low", why == "struct" and h == 4)
r, h, why, tr = ve.outcome_close_rule(rows, 0, target=None, stop_close=None, neck_px=95.0)
check("넥라인 회귀: 종가 < neck", why == "neck" and h == 4)
rows = flat(40)
r, h, why, tr = ve.outcome_close_rule(rows, 10)
check("만기: 20봉 종가, truncated=False", why == "timestop" and h == 20 and tr is False, (h, tr))
r, h, why, tr = ve.outcome_close_rule(rows, 30)
check("데이터 끝 미결: 마지막 봉 종가 평가 + truncated=True", why == "timestop" and h == 9 and tr is True, (h, tr))

# A_label(cat=None) == 동결 라벨
same = True; n_cmp = 0
for seed in range(150):
    rows = mkrows(300, seed)
    for si in range(30, 260, 7):
        a = ve.outcome_close_rule(rows, si, cat=None)[0]
        b = detlib.outcome(rows, si, "long")[1]
        n_cmp += 1
        if abs(a - b) > 1e-12:
            same = False
check(f"재해 손절 없는 A_label == detlib.outcome (동결 라벨) 수익률 완전 일치 ({n_cmp}건)", same)
# 재해 손절이 있으면 라벨과 다른 경우는 오직 cat_stop 인 경우
only_cat = True
for seed in range(150):
    rows = mkrows(300, seed, vol=0.06)
    for si in range(30, 260, 7):
        r1, _, why1, _ = ve.outcome_close_rule(rows, si)
        r0 = detlib.outcome(rows, si, "long")[1]
        if abs(r1 - r0) > 1e-12 and why1 != "cat_stop":
            only_cat = False
check("A_label 이 라벨과 갈라지는 경우는 재해 손절만", only_cat)

# ── 2. D_close · D ───────────────────────────────────────────────────────────
rows = flat(); rows[2].update(l=90.0, c=99.0)
r, h, why, tr = ve.outcome_d_close(rows, 0, none_lab)
check("D_close: 저가 −10% 는 무시, 종가 판정", why == "maxhold" and h == 30)
rows = flat(); rows[2].update(c=91.0, l=90.0)
r, h, why, tr = ve.outcome_d_close(rows, 0, none_lab)
check("D_close: 종가 ≤ −8% 면 종가로 청산", why == "sl_close" and h == 2 and abs(r - (-0.09 - FEE)) < 1e-12)
regs = {f"{i:04d}": ("bull_btc" if i < 5 else "bear") for i in range(40)}
lab = lambda j: regs[f"{j:04d}"]
rows = flat()
r, h, why, tr = ve.outcome_d_close(rows, 0, lab)
check("D_close: 레짐 전환 청산은 D 와 동일(봉 5)", why == "regime_switch" and h == 5)
same = True
for seed in range(100):
    rows = mkrows(200, seed)
    for si in range(30, 160, 9):
        a = ve.outcome_arm("D", rows, si, none_lab)
        b = ms.outcome(rows, si, "long", set(), none_lab, use_regime=True, max_hold=ve.HOLD_D)
        if (a[0], a[1], a[2]) != b:
            same = False
check("arm D == method_s.outcome(방식D)", same)
# D 와 D_close 의 차이는 손절 판정만: 종가로 −8% 깨진 경우는 둘 다 손절이나 가격이 다름(저가 −8% vs 종가)
rows = flat(); rows[3].update(c=90.0, l=89.0)
d = ve.outcome_arm("D", rows, 0, none_lab); dc = ve.outcome_arm("D_close", rows, 0, none_lab)
check("D 는 −8% 고정가, D_close 는 실제 종가(−10%) 로 기록", abs(d[0] - (-0.08 - FEE)) < 1e-12 and abs(dc[0] - (-0.10 - FEE)) < 1e-12)

# stop_pct
det = dict(sig=10, L1=2, L2=5, L3=8, neck=99.5, brk=9)
rows = flat(); rows[2]["l"] = rows[5]["l"] = rows[8]["l"] = 85.0
a = ve.outcome_arm("S_base", rows, 10, none_lab, det)
check("S_base stop_pct = (진입−base_low)/진입, 상한 20%", abs(a[3] - 0.15) < 1e-12)
a = ve.outcome_arm("N_neck", rows, 10, none_lab, det)
check("N_neck stop_pct 하한 5%", abs(a[3] - 0.05) < 1e-12)
check("A_label/A_notarget stop_pct 10%, D 계열 8%",
      ve.outcome_arm("A_label", rows, 10, none_lab)[3] == 0.10 and ve.outcome_arm("A_notarget", rows, 10, none_lab)[3] == 0.10
      and ve.outcome_arm("D", rows, 10, none_lab)[3] == 0.08 and ve.outcome_arm("D_close", rows, 10, none_lab)[3] == 0.08)

# ── 3. 사전 등록 상수·판정 ───────────────────────────────────────────────────
check("주 판정 셀 (late, A_label), holdout 730일, n>=10", (ve.PRIMARY_ENTRY, ve.PRIMARY_EXIT) == ("late", "A_label")
      and ve.HOLDOUT_DAYS == 730 and ve.HOLDOUT_MIN_N == 10)
check("arm 6종 · 진입 2종 · 풀 매핑 전 arm", set(ve.EXITS) == {"A_label", "A_notarget", "S_base", "N_neck", "D_close", "D"}
      and ve.ENTRIES == ("late", "causal") and set(ve.POOL_OF) == set(ve.EXITS))
check("A_label 파라미터 = 라벨(±10%/20봉) + 재해 20%", (ve.HOLD_A, ve.TARGET, ve.STOP_CLOSE, ve.CAT_STOP) == (20, 0.10, 0.10, 0.20))
check("실거래 코호트 all", ve.LIVE_COHORT == "all")


def cf(c1=True, c2p=True, c2=True, c3=True):
    return dict(c1=c1, c2_possible=c2p, c2=c2, c3=c3, gate=dict(reason="x"), holdout=dict(n=3 if not c2p else 20, mean=0.01 if c2 else -0.01))


check("decide: 전부 통과 → PASSED", ve.decide(cf())[0] == "PASSED")
check("decide: C1·C3 통과·holdout 부족 → INCONCLUSIVE", ve.decide(cf(c2p=False, c2=False))[0] == "INCONCLUSIVE")
check("decide: C1 탈락이면 holdout 부족이라도 REJECTED", ve.decide(cf(c1=False, c2p=False, c2=False))[0] == "REJECTED")
check("decide: C3 탈락 + holdout 부족 → REJECTED", ve.decide(cf(c2p=False, c2=False, c3=False))[0] == "REJECTED")
check("decide: holdout 음수 → REJECTED", ve.decide(cf(c2=False))[0] == "REJECTED")

a = [dict(key=("A", 1), ret=0.10), dict(key=("A", 2), ret=0.05), dict(key=("B", 1), ret=-0.02)]
d = [dict(key=("A", 1), ret=-0.08), dict(key=("A", 2), ret=0.05), dict(key=("C", 9), ret=0.3)]
p = ve.paired(a, d)
check("짝지음: 공통 키만, 평균차·우위·동률", p["n"] == 2 and abs(p["mean_diff"] - 0.09) < 1e-12 and p["win_share"] == 0.5 and p["tie_share"] == 0.5)

# ── 4. 등재 ──────────────────────────────────────────────────────────────────
wf = open(".github/workflows/exit_1w.yml", encoding="utf-8").read()
check("워크플로: 테스트 → 시험 → 아티팩트", "python test_exit_1w.py" in wf and "python validate_exit_1w.py" in wf and "_exit_1w.json" in wf)
check("tests.yml 등재", "test_exit_1w.py" in open(".github/workflows/tests.yml", encoding="utf-8").read())
src = open("validate_exit_1w.py", encoding="utf-8").read()
check("스크립트가 자율 반영 예외를 명시", "자율 반영하지 않는다" in src)

print(f"\n{len(fails)} failed")
sys.exit(1 if fails else 0)
