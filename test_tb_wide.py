"""
test_tb_wide.py — 삼중바닥 넓은 스윙 판(pivot 5 / eq 0.45) 사전 등록 시험 검증 (2026-09-08).

가장 중요한 것: **기본값을 넘기지 않으면 배포된 triple_bottom 의 신호 집합이 한 건도
바뀌지 않는다**(배포 중인 triple_bottom_4h 가 이 파라미터화의 영향을 받으면 안 된다).

실행: python test_tb_wide.py
"""
import sys

import detector_triple_bottom as tb
import validate_tb_wide as tw

fails = []


def check(n, c, d=""):
    print(("PASS " if c else "FAIL ") + n + ("" if c else f" — {d}"))
    c or fails.append(n)


def mk(spec, first="2024-01-01", vols=None):
    """spec: [(low, high)] → rows. 종가는 고가, 시가는 저가. vols 로 봉별 거래량 지정."""
    from datetime import date, timedelta
    d0 = date.fromisoformat(first)
    return [dict(ts=i * 86400000, date=(d0 + timedelta(days=i)).isoformat(),
                 o=l, h=h, l=l, c=h, v=(vols[i] if vols else 1000.0))
            for i, (l, h) in enumerate(spec)]


# ── 1. 기본값 불변 — 배포 패턴 보호 ──────────────────────────────────────────
import random
random.seed(7)
px = 100.0
rows = []
for i in range(400):
    px *= (1 + random.gauss(0, 0.02))
    rows.append(dict(ts=i * 86400000, date=f"2024-{1+i//28:02d}-{1+i%28:02d}",
                     o=px, h=px * 1.02, l=px * 0.98, c=px, v=1000.0 + i))
base = tb.detect(rows)
check("기본 호출과 명시적 None 이 동일", base == tb.detect(rows, pivot_half=None, eq_frac=None))
check("기본값이 모듈 상수와 동일",
      base == tb.detect(rows, pivot_half=tb.PIVOT_HALF, eq_frac=tb.EQ_DEPTH_FRAC))
check("모듈 상수 자체가 안 바뀌었다 (배포 패턴 보호)",
      tb.PIVOT_HALF == 3 and tb.EQ_DEPTH_FRAC == 0.35 and tb.MIN_SPACING == 5
      and tb.MAX_SPAN == 90 and tb.MAX_WAIT == 30 and tb.DEPTH_ATR_MULT == 2.5
      and tb.VOL_BREAK_MULT == 1.5)
check("detect_detail 도 기본값 불변",
      [d["sig"] for d in tb.detect_detail(rows)] == [d["sig"] for d in tb.detect_detail(rows, pivot_half=None)])

# ── 2. 파라미터가 실제로 동작 ────────────────────────────────────────────────
p3 = set(tb._swing_pivots(rows, "l", True, half=3))
p7 = set(tb._swing_pivots(rows, "l", True, half=7))
check("넓은 스윙은 저점을 덜 잡는다", len(p7) < len(p3) and p7 <= p3, (len(p3), len(p7)))
check("_swing_pivots half 기본값 = PIVOT_HALF",
      tb._swing_pivots(rows, "l", True) == tb._swing_pivots(rows, "l", True, half=tb.PIVOT_HALF))
wide = tb.detect(rows, pivot_half=5, eq_frac=0.55)
tight = tb.detect(rows, pivot_half=5, eq_frac=0.35)
check("eq_frac 를 넓히면 신호가 줄지 않는다", len(wide) >= len(tight), (len(tight), len(wide)))

# ── 3. 동결 파라미터 ─────────────────────────────────────────────────────────
check("주 판정 파라미터 5 / 0.45 (사용자 지정)", tw.PIVOT_HALF == 5 and tw.EQ_FRAC == 0.45)
check("TF 4종", tuple(tw.TFS) == ("1h", "4h", "1d", "1w"))
check("코호트·레짐·방향 동결", (tw.COHORT, tw.REGIME, tw.DIRECTION) == ("top30", "ALL", "long"))
check("홀드아웃 — 1w 는 730일", tw.HOLDOUT_BY_TF == {"1h": 90, "4h": 365, "1d": 365, "1w": 730})
check("DEPLOY_ON_PASS=False (관찰 기간)", tw.DEPLOY_ON_PASS is False)
check("격자는 진단용으로 5/0.45 를 포함", 5 in tw.GRID_PIVOT and 0.45 in tw.GRID_EQ)
_src = open("validate_tb_wide.py", encoding="utf-8").read()
check("장기 이력이 기본 (1w train 이 비지 않게) — --short 로만 끈다",
      'long_1d = "--short" not in argv' in _src and 'va.load_tf(syms, "1d", long=long_1d)' in _src)
check("장기 이력이면 레짐 라벨도 그 봉으로", "rs.build_regime_map(rows_by=rows_1d)" in _src)

# ── 4. Holm 보정 ─────────────────────────────────────────────────────────────
h = tw.holm({"a": 0.01, "b": 0.02, "c": 0.30, "d": 0.90})
check("Holm: 가장 작은 p 에 m 배", abs(h["a"] - 0.04) < 1e-12, h)
check("Holm: 단조 비감소", h["a"] <= h["b"] <= h["c"] <= h["d"], h)
check("Holm: 1.0 상한", tw.holm({"x": 0.9, "y": 0.9})["y"] == 1.0)
check("Holm: 단일 검정은 그대로", abs(tw.holm({"x": 0.03})["x"] - 0.03) < 1e-12)

# ── 5. 하강형 판정 (D2) ──────────────────────────────────────────────────────
# 저점 3개가 계단식으로 낮아지되 폭이 줄어드는 합성 셋업
# detect_detail 은 n < MAX_SPAN//2 (=45봉)면 즉시 빈 목록이므로 앞을 하락 추세로 채운다.
# 단조 하락 구간은 ±5봉 국소 최저가 생기지 않아 패턴 저점과 섞이지 않는다.
prefix = [(130 - 2 * i, 134 - 2 * i) for i in range(15)]
spec = prefix + [(100, 104)] * 6 + [(90, 95)] + [(100, 104)] * 8 + [(86, 92)] + \
       [(98, 103)] * 8 + [(84, 90)] + [(96, 101)] * 6 + [(110, 112)] * 4
# 돌파봉 거래량은 형성구간 평균 x1.5 를 넘어야 한다(VOL_BREAK_MULT) — 마지막 4봉을 키운다
syn = mk(spec, vols=[1000.0] * (len(spec) - 4) + [5000.0] * 4)
det = tb.detect_detail(syn, pivot_half=5, eq_frac=0.55)
if det:
    d = det[0]
    l1, l2, l3 = syn[d["L1"]]["l"], syn[d["L2"]]["l"], syn[d["L3"]]["l"]
    check("합성 셋업이 하강형으로 판정된다",
          l1 > l2 > l3 and (l1 - l2) > (l2 - l3), (l1, l2, l3))
    check("descending() 이 같은 답", tw.descending(syn, d["sig"], 5, 0.55) is True)
else:
    check("합성 셋업 탐지", False, "신호 0건")
check("descending(): 없는 신호 인덱스는 False", tw.descending(syn, -1, 5, 0.55) is False)

# ── 6. 실거래 무영향 ─────────────────────────────────────────────────────────
src_s = open("scheduler.py", encoding="utf-8").read()
src_u = open("universe.json", encoding="utf-8").read()
check("스케줄러가 pivot_half/eq_frac 를 넘기지 않는다 (배포 패턴은 기본값)",
      "pivot_half" not in src_s and "eq_frac" not in src_s)
check("universe adopted 에 tb_wide 등재 없음", "tb_wide" not in src_u)
import json
reg = json.load(open("registry.json", encoding="utf-8"))
check("registry 에 사전 등록 기록", "tb_wide_prereg_2026_09_08" in reg)
y = open(".github/workflows/tests.yml", encoding="utf-8").read()
check("tests.yml 등재", "test_tb_wide.py" in y)

print(f"\n{len(fails)} failed")
sys.exit(1 if fails else 0)
