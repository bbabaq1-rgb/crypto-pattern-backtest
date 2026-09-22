"""
test_power_curve.py — 검정력 곡선 계산기의 성질 고정.

이 스크립트는 **판정을 내리지 않는다**(검정력 계산 전용). 테스트도 그 성질을 포함해 고정한다.
실행: python test_power_curve.py
"""
import math
import sys

import power_curve as P
import validate_altseason as V

FAIL = []


def chk(name, cond, extra=""):
    if cond:
        print(f"  ✓ {name}")
    else:
        FAIL.append(name)
        print(f"  ✗ {name} {extra}")


print("\n§1 부분창 배치")
chk("창이 표본 전체면 배치 1곳", P.placements(100, 100) == [0])
chk("창이 더 길면 배치 1곳", P.placements(100, 150) == [0])
pl = P.placements(1000, 400, k=3)
chk("여유가 있으면 균등 배치 3곳", pl == [0, 300, 600], str(pl))
chk("배치는 정렬·중복 없음", pl == sorted(set(pl)))
chk("모든 배치가 표본 안에 들어간다", all(0 <= o and o + 400 <= 1000 for o in pl))
chk("여유가 배치 수보다 적으면 줄어든다", len(P.placements(100, 99, k=3)) <= 2)

print("\n§2 log-log 적합 — 알려진 지수를 되찾는가")
for true_p in (0.5, 0.35, 0.25):
    pts = [(n, 2.0 * n ** (-true_p)) for n in (6, 9, 12, 15, 18, 21, 24)]
    c, p = P.fit_loglog(pts)
    chk(f"p={true_p} 복원 (적합 {p:.4f}, c {c:.4f})",
        abs(p - true_p) < 1e-9 and abs(c - 2.0) < 1e-9)
    chk(f"  완전 적합이면 R²=1 (p={true_p})", abs(P.r2(pts, c, p) - 1.0) < 1e-9)
noisy = [(6, 0.80), (12, 0.60), (24, 0.45)]
c, p = P.fit_loglog(noisy)
chk("단조 감소 자료에서 p>0", p > 0, f"p={p}")
chk("R² 는 1 이하", P.r2(noisy, c, p) <= 1 + 1e-12)

print("\n§3 회전 검정을 validate_altseason 에서 그대로 쓴다")
chk("rotation_null 이 같은 함수", P.V.rotation_null is V.rotation_null)
chk("mde 가 같은 함수", P.V.mde is V.mde)
chk("MIN_SHIFT 를 재정의하지 않는다", not hasattr(P, "MIN_SHIFT"))
chk("HORIZON 을 재정의하지 않는다", not hasattr(P, "HORIZON"))
chk("문턱은 validate_altseason.IC1 을 읽는다", V.IC1 == 0.20)

print("\n§4 MDE 계산 — 부호와 표본 요건")
fv = [math.sin(i / 40.0) for i in range(900)]
tv = [math.cos(i / 55.0) for i in range(900)]
feats = [{"ethbtc_mom120": fv[i], "disp60": fv[i]} for i in range(900)]
m_pos = P.mde_for(feats, tv, list(range(900)), "ethbtc_mom120", 60, 1)
m_neg = P.mde_for(feats, tv, list(range(900)), "disp60", 60, 1)
chk("MDE 는 절대값으로 돌아온다(부호 무관 비교 가능)",
    m_pos is not None and m_neg is not None and m_pos > 0 and m_neg > 0)
chk("양·음 부호 지표가 같은 계열이면 MDE 크기가 비슷", abs(m_pos - m_neg) < 0.35,
    f"{m_pos:.3f} / {m_neg:.3f}")
chk("표본이 2*MIN_SHIFT 이하면 None",
    P.mde_for(feats, tv, list(range(300)), "ethbtc_mom120", 60, 1) is None)
chk("결측만 있는 지표는 None",
    P.mde_for([{"x": None} for _ in range(900)], tv, list(range(900)), "x", 60, 1) is None
    if "x" in ("x",) else True)

print("\n§5 판정을 내리지 않는다")
src = open("power_curve.py").read()
chk("verdict/CONFIRMED/REJECTED 를 만들지 않는다",
    not any(w in src for w in ("CONFIRMED", "REJECTED", "INCONCLUSIVE")))
chk("judge 를 호출하지 않는다", "judge(" not in src)
chk("DEPLOY 개념이 없다 — 반영 경로 자체가 없다", "DEPLOY" not in src)
chk("헤더가 '판정이 아니라 계산'임을 명시", "판정이 아니라 계산" in src)

print("\n§6 동결 상수")
chk("창 격자 6~24", P.WIN_GRID == [6, 9, 12, 15, 18, 21, 24])
chk("외삽 목표 21(train)·38(전체)", [n for n, _ in P.TARGETS] == [21, 38])
chk("검산용 boot 는 공식 실행과 같은 1000", P.BOOT_ANCHOR == 1000)
chk("곡선용 boot 500", P.BOOT_CURVE == 500)
chk("지표는 가설 10종만 (대조 제외)",
    P.KEYS == [k for k, _, _ in V.FEATURES] and len(P.KEYS) == 10
    and not any(k.startswith("ctrl_") for k in P.KEYS))
chk("부호표가 FEATURES 와 일치", P.SIGNS == {k: s for k, _, s in V.FEATURES})

print("\n§7 labeled_index 가 analyze 와 같은 필터")
va = open("validate_altseason.py").read()
chk("analyze 의 keep 조건 세 가지를 그대로 쓴다",
    all(t in open("power_curve.py").read()
        for t in ["tgt[i] is not None", 'd[i] >= V.START', 'S["univ_n"][i] >= V.MIN_UNIVERSE']))
chk("analyze 도 같은 조건을 쓴다(원본 확인)",
    'tgt[i] is not None and dates[i] >= START' in va)

print("\n" + "=" * 60)
print(f"실패 {len(FAIL)}건" + ("" if not FAIL else ": " + ", ".join(FAIL)))
sys.exit(1 if FAIL else 0)
