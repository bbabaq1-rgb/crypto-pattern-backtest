"""
test_yyy_cross.py — 양양양 + MA5xMA20 크로스 추격 시험 고정 (2026-09-12 사전 등록).

registry `yyy_cross_prereg_2026_09_12`. **사후 선택 셀의 추격**이라 확인 기준보다
반증 기준(F1/F2/F3)의 배선이 더 중요하다 — 그것들이 조용히 느슨해지면 시험 자체가
무의미해진다. 여기서는 판정 배선을 **동작으로** 고정한다.
"""
import sys
import detector_kakao_base as kb
import detector_yyy as d_yyy
import detector_ma_cross as d_cross
import validate_yyy_cross as vx

fails = []


def check(name, cond, extra=""):
    (print(f"PASS {name}") if cond else (fails.append(name), print(f"FAIL {name} {extra}")))


def mk(seq):
    return [dict(date=f"2020-01-{i+1:02d}", ts=i * 86400000, o=o, h=h, l=l, c=c, v=1.0)
            for i, (o, h, l, c) in enumerate(seq)]


# ── 동결 파라미터 — kakao 판에서 하나도 안 바뀌었나 ──────────────────────
check("MA 5/20 · 교차 20봉 내 동결", (kb.MA_FAST, kb.MA_SLOW, kb.CROSS_WITHIN) == (5, 20, 20))
check("피벗 반폭 3 · 돌파대기 10봉 동결", (kb.PIVOT_HALF, kb.BREAK_WAIT) == (3, 10))
check("주 판정 = 2TF · top30 · ALL · 롱", vx.TFS == ("1d", "4h") and vx.COHORT == "top30"
      and vx.REGIME == "ALL" and vx.DIRECTION == "long")
check("DEPLOY_ON_PASS=False (통과해도 실거래 반영 없음)", vx.DEPLOY_ON_PASS is False)
check("마찰 스트레스 왕복 0.4%", abs(vx.FRICTION - 0.004) < 1e-12)
check("F3 대조군 = 배포 패턴 4종",
      set(vx.CONTROLS) == {"detector_engulfing", "detector_fvg",
                           "detector_inverted_hammer", "detector_marubozu"})

# ── cross_up 의미 ──────────────────────────────────────────────────────
# 20봉 평평 뒤 상승 → 어딘가에서 MA5 가 MA20 을 위로 뚫는다
rows = mk([(100, 100, 100, 100)] * 25 + [(100 + i, 100 + i, 100 + i, 100 + i) for i in range(1, 16)])
xs = d_cross.detect(rows)
check("cross_up: 상향 교차가 정확히 한 번", len(xs) == 1, str(xs))
i0 = xs[0]
check("cross_up: 교차 봉에서 참", kb.cross_up(rows, i0))
check("cross_up: 교차 직전 봉에서 거짓", not kb.cross_up(rows, i0 - 1))
check("cross_up: 교차 20봉 뒤에는 거짓 (within 이 실제로 작동)",
      (i0 + 20 >= len(rows)) or not kb.cross_up(rows, i0 + 20))
# 계속 하락하면 교차 없음
down = mk([(100 - i, 100 - i, 100 - i, 100 - i) for i in range(40)])
check("cross_up: 하락 추세에선 교차 없음", d_cross.detect(down) == [] and not kb.cross_up(down, 39))

# ── cross 는 plain 의 부분집합이어야 F1 이 '걸러진 거래' 가 된다 ─────────
seq = []
for i in range(60):
    base = 100 + (i * 0.7 if i > 25 else 0)
    seq.append((base, base + 2.5, base - 1.0, base + 2.0 if i % 4 != 3 else base - 0.5))
rows = mk(seq)
plain = set(d_yyy.detect(rows, "plain"))
cross = set(d_yyy.detect(rows, "cross"))
check("cross ⊆ plain (부분집합)", cross <= plain, f"plain{sorted(plain)} cross{sorted(cross)}")
check("cross 가 실제로 걸러낸다 (전부 통과가 아니다)", len(cross) < len(plain) or len(plain) == 0,
      f"plain{len(plain)} cross{len(cross)}")

# ── F1: 걸러진 거래가 양수면 탈락해야 한다 (method_b 교훈) ───────────────
check("F1 판정식: 걸러진 평균이 양수면 False", not (vx.mean([0.05, 0.03]) < 0))
check("F1 판정식: 걸러진 평균이 음수면 True", vx.mean([-0.05, 0.01]) < 0)

# ── F2: 달력 중점 분할 (arm 별 중앙값이 아니다 — validate_routing 교훈) ──
sig = ([dict(date="2020-01-01", ret=0.1)] * 9 + [dict(date="2020-12-31", ret=-0.1)])
h1, h2 = vx.split_half(sig)
check("F2 분할: 달력 중점 기준 (9:1 이 아니라 날짜로)", len(h1) == 9 and len(h2) == 1,
      f"{len(h1)}/{len(h2)}")
check("F2 분할: 빈 입력 방어", vx.split_half([]) == ([], []))

# ── Holm ───────────────────────────────────────────────────────────────
h = vx.holm({"a": 0.01, "b": 0.04})
check("Holm m=2: 작은 p 는 x2", abs(h["a"] - 0.02) < 1e-12, str(h))
check("Holm m=2: 단조 증가 (step-down)", h["b"] >= h["a"])

# ── 최종 판정식이 확인 4 + 반증 3 전부를 요구하나 ───────────────────────
src = open("validate_yyy_cross.py", encoding="utf-8").read()
check("최종 판정 = conf_ok AND f1 AND f2 AND f3",
      'v["conf_ok"] and v["f1"] and v["f2"] and v["f3"]' in src)
check("F3 는 대조군 중앙값 초과를 요구", 'yg > med' in src)

# ── 배포 패턴 불변 — 이 시험은 실거래를 건드리지 않는다 ─────────────────
import json
uni = json.load(open("universe.json"))
reg = json.load(open("registry.json"))
names = json.dumps(uni, ensure_ascii=False)
check("universe 미등재 (yyy/cross 가 스케줄러에 없다)",
      "yyy" not in names and "ma_cross" not in names)
check("사전 등록 기록 존재", "yyy_cross_prereg_2026_09_12" in reg)
p = reg["yyy_cross_prereg_2026_09_12"]
check("사전 등록: DEPLOY_ON_PASS False", p.get("DEPLOY_ON_PASS") is False)
check("사전 등록: 반증 3종이 기록돼 있다",
      len([k for k in p.get("반증_기준(사후_선택_셀이라_추가)", {})]) == 3)
check("사전 등록: 사후 선택임을 명시", any("사후_선택" in k for k in p))

# 배포 three_soldiers_4h 는 이 판과 무관한 별도 디텍터
import detector_three_soldiers_4h as d_ts
check("배포 three_soldiers_4h 디텍터가 yyy 와 다른 모듈", d_ts.detect is not d_yyy.detect)

print(f"\n{len(fails)} 실패" if fails else "\n전부 통과")
sys.exit(1 if fails else 0)
