"""
배포 패턴 청산 일치 점검(validate_exit_consistency) 고정 — 2026-09-06.

확인 대상:
  - 셀 목록이 실거래 배포 범위와 일치: universe.json adopted_patterns(1d ih/marubozu) · adopted_4h_patterns(4종),
    코호트(ih/marubozu → majors = scheduler.PATTERN_UNIVERSE, three_soldiers → all, 4h 신규 3종 → top30),
    레짐(three_soldiers → scheduler.ADOPTED4H_REGIME 키, 나머지 전부)
  - 판정 대상 3종(ih/marubozu/three_soldiers_4h) = 방식D 실거래 프레임 확인을 거치지 않은 패턴. 참고 3종은 판정 아님
  - arm D == method_s.outcome / A_label == validate_exit_1w.outcome_close_rule / A_nocat == detlib.outcome
  - judge 진리표 (KEEP_D / SWITCH_CANDIDATE_A_label / OBSERVE / PATTERN_REJUDGE_CANDIDATE)
  - 풀·수집이 레짐 조건을 지킴, 짝지음 공통 키
  - 워크플로·tests.yml 등재, 실거래 코드(paper_executor/scheduler) 무변경(이 시험은 import 만)

실행: python test_exit_consistency.py
"""
import json
import random
import sys

import detlib
import method_s as ms
import scheduler as sch
import validate_exit_consistency as vc
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
                         v=100 * (1 + abs(random.gauss(0, 0.5))), date=f"2024-{1 + i // 28:02d}-{1 + i % 28:02d}", ts=i * 86_400_000))
        px = nxt
    return rows


# ── 1. 셀 = 실거래 범위 ───────────────────────────────────────────────────────
u = json.load(open("universe.json", encoding="utf-8"))
ad1 = {a["pattern"]: a for a in u.get("adopted_patterns", [])}
ad4 = {a["pattern"]: a for a in u.get("adopted_4h_patterns", [])}
cells = {c[0]: c for c in vc.CELLS}
check("1d 배포(adopted_patterns) 전부 셀에 있음", set(ad1) <= set(cells), (set(ad1), set(cells)))
check("4h 배포(adopted_4h_patterns) 전부 셀에 있음", set(ad4) <= set(cells), (set(ad4), set(cells)))
check("셀은 배포 패턴만", set(cells) == set(ad1) | set(ad4))
for pid in ad1:
    check(f"{pid}: 모듈·코호트(majors)·레짐 전부 = 실거래", cells[pid][2] == ad1[pid]["module"] and cells[pid][3] == "majors"
          and sch.PATTERN_UNIVERSE.get(pid) == "majors" and cells[pid][4] is None)
for pid, ap in ad4.items():
    coh = ap.get("cohort") or "all"
    rg = ap.get("regimes")
    want_rg = None if rg == "all" else (tuple(sch.ADOPTED4H_REGIME) if rg is None else tuple(rg))
    check(f"{pid}: 모듈·코호트({coh})·레짐 = 실거래", cells[pid][2] == ap["module"] and cells[pid][3] == coh
          and (cells[pid][4] is None if want_rg is None else set(cells[pid][4]) == set(want_rg)), (cells[pid][3:5], coh, want_rg))
judged = {c[0] for c in vc.CELLS if c[5]}
check("판정 대상 = D 실거래 프레임 미확인 3종", judged == {"inverted_hammer", "marubozu", "three_soldiers_4h"}, judged)
check("참고 3종 = revival 에서 D 로 확인된 4h 신규", {c[0] for c in vc.CELLS if not c[5]} == {"triple_bottom_4h", "equal_lows_4h", "vol_awakening_4h"})
check("arm 3종·홀드아웃 365·풀 상한", vc.ARMS == ("D", "A_label", "A_nocat") and vc.HOLDOUT_DAYS == 365 and vc.POOL_CAP == 20000)
check("MAJORS = 검증 7종목", vc.MAJORS == list(detlib.SYMBOLS) == sch.MAJORS)

# ── 2. arm 동치 ──────────────────────────────────────────────────────────────
none_lab = lambda j: None
ok_d = ok_a = ok_n = True
for seed in range(80):
    rows = mkrows(300, seed)
    for si in range(30, 260, 11):
        d = vc.outcome_arm("D", rows, si, none_lab)
        if (d[0], d[1], d[2]) != ms.outcome(rows, si, "long", set(), none_lab, use_regime=True, max_hold=vc.HOLD_D) or d[3] != 0.08:
            ok_d = False
        a = vc.outcome_arm("A_label", rows, si, none_lab)
        if (a[0], a[1], a[2]) != ve.outcome_close_rule(rows, si)[:3] or a[3] != 0.10:
            ok_a = False
        nc = vc.outcome_arm("A_nocat", rows, si, none_lab)
        if abs(nc[0] - detlib.outcome(rows, si, "long")[1]) > 1e-12:
            ok_n = False
check("arm D == method_s.outcome(방식D), stop 8%", ok_d)
check("arm A_label == validate_exit_1w.outcome_close_rule(라벨+재해), stop 10%", ok_a)
check("arm A_nocat == detlib.outcome(동결 라벨)", ok_n)
check("tail: D 30봉 / A 20봉", vc.tail_for("D") == 30 and vc.tail_for("A_label") == 20 == vc.tail_for("A_nocat"))

# ── 3. 레짐 조건·짝지음 ─────────────────────────────────────────────────────
rb = {f"S{i}": mkrows(200, i) for i in range(3)}
regmap = {r["date"]: ("bull_btc" if (int(r["date"][5:7]) % 2) else "bear") for rows in rb.values() for r in rows}
det = lambda rows: list(range(35, 150, 10))
allc = vc.collect(det, "D", list(rb), rb, regmap, None, tf="1d")
bull = vc.collect(det, "D", list(rb), rb, regmap, vc.BULL, tf="1d")
check("레짐 조건 수집: bull 셀 ⊂ 전체, 전부 bull 라벨", 0 < len(bull) < len(allc) and all(s["regime"] in vc.BULL for s in bull))
pr_all = vc.pool("A_label", list(rb), rb, regmap, None); pr_bull = vc.pool("A_label", list(rb), rb, regmap, vc.BULL)
check("풀도 레짐 조건 적용(bull 풀이 더 작음)", 0 < len(pr_bull) < len(pr_all))
a_s = vc.collect(det, "A_label", list(rb), rb, regmap, None, tf="1d")
pv = vc.paired(a_s, allc)
check("짝지음: 같은 신호 수, 키 공통", pv["n"] == len(allc) == len(a_s))
check("코호트 majors → 7종목 ∩ 데이터", vc.cohort_syms("majors", {"BTC": [], "ETH": [], "X": []}, ["X", "BTC"]) == ["BTC", "ETH"])
check("코호트 top30 → 순위 상위 30 ∩ 데이터", vc.cohort_syms("top30", {"A": [], "B": []}, ["B", "Z", "A"]) == ["B", "A"])

# ── 4. 판정 규칙 ────────────────────────────────────────────────────────────
good = dict(mean_diff=0.02, t=3.0); bad = dict(mean_diff=0.02, t=1.0); neg = dict(mean_diff=-0.01, t=-3.0)
check("judge: D_OK → KEEP_D (A 가 더 좋아도)", vc.judge(True, True, good) == "KEEP_D")
check("judge: ¬D ∧ A ∧ 짝지음 유의 우위 → SWITCH_CANDIDATE", vc.judge(False, True, good) == "SWITCH_CANDIDATE_A_label")
check("judge: ¬D ∧ A ∧ 짝지음 비유의 → OBSERVE", vc.judge(False, True, bad) == "OBSERVE" and vc.judge(False, True, neg) == "OBSERVE")
check("judge: ¬D ∧ ¬A → PATTERN_REJUDGE_CANDIDATE", vc.judge(False, False, good) == "PATTERN_REJUDGE_CANDIDATE")

# ── 5. 등재·무변경 ──────────────────────────────────────────────────────────
wf = open(".github/workflows/exit_consistency.yml", encoding="utf-8").read()
check("워크플로: 테스트 → 시험 → 아티팩트", "python test_exit_consistency.py" in wf and "python validate_exit_consistency.py" in wf and "_exit_consistency.json" in wf)
check("tests.yml 등재", "test_exit_consistency.py" in open(".github/workflows/tests.yml", encoding="utf-8").read())
src = open("validate_exit_consistency.py", encoding="utf-8").read()
check("시험 모듈은 paper_executor 를 import 하지 않음(실거래 무관)", "import paper_executor" not in src)
check("실거래 변경 없음 명시", "실거래 변경 없음" in src)

print(f"\n{len(fails)} failed")
sys.exit(1 if fails else 0)
