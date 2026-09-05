"""
gate.py v2 (2026-09-05 사용자 결정) 고정.

  - v2 분포 조건은 승률 >= 35%. 승률 40% · 평균 양수 셀이 **통과**한다 (v1 median>0 에서는 기각이었다)
  - 승률 30% 는 기각. 평균 음수는 승률과 무관하게 기각
  - rets 를 안 주는 구형 호출은 v1(median>0) 로 판정하고 gate_version=1 을 돌려준다 — 조용히 섞이지 않게
  - 진단: 절사평균·상위5기여도가 계산되고 판정에는 쓰이지 않는다
  - 배포 검증 모듈들이 gate.dist_ok 를 쓴다(자체 median 판정이 남아 있지 않다)
실행: python test_gate.py
"""
import sys

import gate

fails = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f" — {detail}"))
    cond or fails.append(name)


check("GATE_VERSION == 2", gate.GATE_VERSION == 2)
check("WIN_RATE_MIN == 0.35", gate.WIN_RATE_MIN == 0.35)

# 승률 40%, 평균 양수 (승 +0.10 x 40, 패 -0.03 x 60 → mean +0.022, median -0.03)
rets40 = [0.10] * 40 + [-0.03] * 60
import statistics as st
check("표본 성질: 승률 40%, 평균 양수, 중앙값 음수",
      abs(gate.win_rate(rets40) - 0.40) < 1e-9 and st.mean(rets40) > 0 and st.median(rets40) < 0)
v, eff, ver = gate.decide_v(len(rets40), st.mean(rets40), st.median(rets40), T=100, rets=rets40)
check("v2: 승률 40% 평균 양수 → 통과", v == "통과" and ver == 2, (v, ver))
v1, _ = gate.decide(len(rets40), st.mean(rets40), st.median(rets40), T=100)
check("v1(구형 호출, rets 없음): 같은 표본은 기각 — 중앙값 음수", v1 == "기각")
_, _, ver1 = gate.decide_v(len(rets40), st.mean(rets40), st.median(rets40), T=100)
check("구형 호출은 gate_version=1 을 돌려준다", ver1 == 1)

rets30 = [0.10] * 30 + [-0.03] * 70
check("승률 30% 는 기각 (평균 양수여도)", gate.decide(100, st.mean(rets30), st.median(rets30), 100, rets=rets30)[0] == "기각")
rets_neg = [0.01] * 45 + [-0.05] * 55
check("평균 음수는 승률 45% 여도 기각", gate.decide(100, st.mean(rets_neg), st.median(rets_neg), 100, rets=rets_neg)[0] == "기각")
check("승률 정확히 35% 는 통과(경계 포함)", gate.dist_ok([0.1] * 35 + [-0.01] * 65))
check("n<20 은 보류", gate.decide(10, 0.05, 0.01, 100, rets=[0.05] * 10)[0].startswith("보류"))
check("빈 rets 는 dist_ok False", not gate.dist_ok([]))

# 진단
lotto = [1.0] * 5 + [-0.05] * 95           # 5건 대박이 전부
check("복권형: 절사평균 음수", gate.trimmed_mean(lotto) < 0)
check("복권형: 상위5 기여 100%", abs(gate.top_share(lotto) - 1.0) < 1e-9)
even = [0.05] * 50 + [-0.03] * 50
check("고른 분포: 절사평균 양수, 상위5 기여 낮음", gate.trimmed_mean(even) > 0 and gate.top_share(even) < 0.3)
check("총이익 0 이하면 top_share None", gate.top_share([-0.01] * 10) is None)
check("복권형도 v2 판정 자체는 승률로만 (5%→기각)", not gate.dist_ok(lotto))
check("dist_reason 문자열", "win_rate=" in gate.dist_reason(rets30))

# 배포 검증 모듈이 v2 를 쓴다
for f in ("validate_regime_split.py", "validate_regime_split_all.py", "validate_revival.py",
          "validate_confirm_bar.py", "validate_universe_1d.py", "validate_vol_awakening.py",
          "validate_xsec_momentum.py", "validate_triple_pattern.py"):
    src = open(f, encoding="utf-8").read()
    check(f"{f}: gate.dist_ok 사용", "gate.dist_ok(rets)" in src or "gt.dist_ok(rets)" in src)
    check(f"{f}: 자체 median 판정 없음", "and med > 0 and" not in src and 'fails.append("median<=0")' not in src)

for f in ("orchestrator.py", "tf_verify.py", "alt_verify.py", "candle_verify.py"):
    src = open(f, encoding="utf-8").read()
    check(f"{f}: gate.decide 에 rets 를 넘긴다(v2)", "rets=rets" in src and "gate.decide(" in src)
    check(f"{f}: rets 없는 v1 호출 없음", not __import__("re").search(r"gate\.decide\([^)]*count_trials\(\)\)", src) or "rets=rets" in src)
check("validate_crows_regime.py: 승률 조건", "gate.dist_ok(rets)" in open("validate_crows_regime.py", encoding="utf-8").read())

print(f"\n{len(fails)} failed")
sys.exit(1 if fails else 0)
