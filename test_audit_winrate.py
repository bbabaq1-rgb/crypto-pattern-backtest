"""
test_audit_winrate.py — 승률 문턱 교정 감사 고정 (2026-09-12 사전 등록).

이 감사의 값은 **문턱을 안 바꾸고 측정만 한다**는 것과 **판정식이 사전 등록대로**라는 데 있다.
둘 다 동작으로 고정한다.
"""
import sys
import gate
import audit_winrate as aw

fails = []


def check(name, cond, extra=""):
    (print(f"PASS {name}") if cond else (fails.append(name), print(f"FAIL {name} {extra}")))


# ── 동결 파라미터 ──────────────────────────────────────────────────────
check("승률 버킷 4구간 동결", aw.WR_BUCKETS == ((0.00, 0.30), (0.30, 0.35), (0.35, 0.40), (0.40, 1.01)))
check("문턱 격자 25/30/35/40% 동결", aw.WR_GRID == (0.25, 0.30, 0.35, 0.40))
check("A1 중복 문턱 0.50 · A2 하한 10셀/3버킷", (aw.RHO_THR, aw.MIN_CELLS_A2, aw.MIN_PER_BUCKET) == (0.50, 10, 3))
check("판정 코호트 top30", aw.COHORT == "top30")

# ── **문턱을 안 바꾼다** — 이 감사의 절대 조항 ──────────────────────────
check("gate.WIN_RATE_MIN 은 여전히 0.35", abs(gate.WIN_RATE_MIN - 0.35) < 1e-12)
check("gate v2 유지 (중앙값은 판정에서 빠져 있다)", gate.GATE_VERSION == 2)
# 문자열이 아니라 **동작**으로 — 감사 함수를 실제로 써 본 뒤 게이트가 그대로인지 확인한다
_before = (gate.WIN_RATE_MIN, gate.GATE_VERSION, gate.MIN_N, gate.dist_ok([-0.082] * 65 + [0.30] * 35))
aw.spearman([1, 2, 3, 4, 5], [2, 1, 4, 3, 5])
aw.other_fails(dict(n=50, mean=0.01, boot_p=0.01, oos_pos=3),
               dict(c2_holdout=True, c2b_train=True, c3_equity=True, E=dict(ok=True)))
aw.population()
check("감사를 써도 게이트 상수·판정 동작이 그대로",
      (gate.WIN_RATE_MIN, gate.GATE_VERSION, gate.MIN_N,
       gate.dist_ok([-0.082] * 65 + [0.30] * 35)) == _before)
check("감사 모듈이 gate 함수를 덮어쓰지 않는다",
      aw.gate.dist_ok is gate.dist_ok and aw.gate.win_rate is gate.win_rate)

# 중앙값이 실제로 판정에 안 쓰이는지 — 동작으로 확인(문자열 아님)
lose, win = -0.082, 0.30
rets = [lose] * 65 + [win] * 35          # 중앙값 음수, 승률 35%, 평균 양수
check("게이트 v2: 중앙값 음수여도 승률 35% 면 분포조건 통과", gate.dist_ok(rets) is True)
check("게이트 v2: 승률 34% 면 분포조건 탈락", gate.dist_ok([lose] * 66 + [win] * 34) is False)

# ── other_fails — '승률 하나로만 떨어졌다' 판별이 정확한가 ────────────────
ok_j = dict(c2_holdout=True, c2b_train=True, c3_equity=True, E=dict(ok=True))
rec_wr_only = dict(n=100, mean=0.05, boot_p=0.01, oos_pos=3)      # 승률 외 전부 통과
check("승률 외 층 전부 통과 → other_fails 비어 있음", aw.other_fails(rec_wr_only, ok_j) == [])
check("홀드아웃 탈락은 승률 외 사유로 잡힌다",
      "holdout" in aw.other_fails(rec_wr_only, dict(ok_j, c2_holdout=False)))
check("boot_p 탈락도 승률 외 사유", "bp=0.300" in aw.other_fails(dict(rec_wr_only, boot_p=0.30), ok_j))
check("other_fails 는 승률을 아예 안 본다 (rec 에 win_rate 없어도 동작)",
      aw.other_fails(rec_wr_only, ok_j) == [])

# ── 스피어만 ───────────────────────────────────────────────────────────
check("spearman 완전 단조 = +1", abs(aw.spearman([1, 2, 3, 4, 5], [10, 20, 30, 40, 50]) - 1.0) < 1e-9)
check("spearman 역단조 = −1", abs(aw.spearman([1, 2, 3, 4, 5], [50, 40, 30, 20, 10]) + 1.0) < 1e-9)
check("spearman 동률 처리(상수열) → None 또는 0", aw.spearman([1, 1, 1, 1, 1], [1, 2, 3, 4, 5]) in (None, 0.0))
check("spearman 표본 5 미만 → None", aw.spearman([1, 2, 3], [1, 2, 3]) is None)
check("spearman None 섞여도 동작", aw.spearman([1, 2, 3, 4, 5, None], [1, 2, 3, 4, 5, 9]) is not None)

# ── 셀 모집단 — 사후 선택이 아니라 기존 목록에서만 온다 ────────────────
import validate_revival as vr
import audit_guards as ag
pop = aw.population()
ids = {(c["cid"], c["regime"]) for c in pop}
check("모집단 비어있지 않음", len(pop) > 10, str(len(pop)))
check("모집단은 1d/4h 만", all(c["tf"] in ("1d", "4h") for c in pop))
cand = {(cid, g) for cid, g in vr.CANDIDATES}
live = {(c["pattern"], c["regime"]) for c in ag.CELLS if c["tf"] in ("1d", "4h")}
check("모집단 ⊆ (revival 후보 ∪ 실거래 셀) — 새로 고른 셀이 없다", ids <= (cand | live),
      str(sorted(ids - (cand | live))[:4]))
check("실거래 셀이 포함돼 있다", any(c["src"].startswith("live") for c in pop))
check("revival 후보가 포함돼 있다", any(c["src"] == "revival" for c in pop))
check("중복 셀 없음", len(ids) == len(pop))

# ── 사전 등록 기록 ─────────────────────────────────────────────────────
import json
reg = json.load(open("registry.json"))
check("사전 등록 존재", "winrate_guard_audit_prereg_2026_09_12" in reg)
p = reg["winrate_guard_audit_prereg_2026_09_12"]
check("사전 등록: 문턱 변경 금지 명시", "문턱을 바꾸지 않는다" in p.get("절대_조항", ""))
check("사전 등록: 판정 3종 고정", set(p.get("판정_규칙(사전_고정)", {})) == {"REDUNDANT", "INDEPENDENT", "INCONCLUSIVE"})
check("사전 등록: 측정 4종 고정", len(p.get("측정(사전_고정)", {})) == 4)
check("사전 등록: 사전 확률 기록", "사전_확률(결과_전_기록)" in p)

# ── 실거래 무변경 ──────────────────────────────────────────────────────
uni = json.dumps(json.load(open("universe.json")), ensure_ascii=False)
check("universe 미등재 (감사는 매매 경로와 무관)", "winrate_audit" not in uni)

print(f"\n{len(fails)} 실패" if fails else "\n전부 통과")
sys.exit(1 if fails else 0)
