"""
장기 이평 돌파 슈팅 스터디(study_ma_breakout) 고정 — 2026-09-06.

확인 대상:
  - sma 정확성(수치·초기 None) · 돌파 정의(종가 교차, fresh = 직전 BELOW_MIN봉 이상 아래 / rebreak 구분) · 인과성
  - 필터 5종의 의미(decisive/volume/slope/deep)
  - forward: 전방 수익·MFE/MAE 계산, 데이터 부족 시 None
  - summarize: 슈팅률(≥20/30/50%)·재하향 비율 집계
  - 사전 등록 상수 · 실거래 코드 미import · 워크플로·tests.yml 등재

실행: python test_ma_breakout.py
"""
import sys

import study_ma_breakout as sm

fails = []


def check(n, c, d=""):
    print(("PASS " if c else "FAIL ") + n + ("" if c else f" — {d}"))
    c or fails.append(n)


def rows_from(closes, vol=100.0):
    return [dict(o=c, h=c * 1.01, l=c * 0.99, c=c, v=vol, date=f"{i:04d}", ts=i) for i, c in enumerate(closes)]


# ── 1. sma · 돌파 정의 ────────────────────────────────────────────────────────
check("sma: 초기 None, 값 정확", sm.sma([1, 2, 3, 4, 5], 3) == [None, None, 2.0, 3.0, 4.0])

# 200봉 100 flat 뒤 60봉 90(아래) 뒤 돌파 110
closes = [100.0] * 200 + [90.0] * 60 + [110.0] * 30
rows = rows_from(closes)
cr, ma = sm.crosses(rows, 180)
check("fresh 돌파 1건, 위치 260", cr == [(260, "fresh")], cr)
# 짧게(5봉) 아래였다가 재돌파 → rebreak
closes2 = [100.0] * 200 + [90.0] * 5 + [110.0] * 30
cr2, _ = sm.crosses(rows_from(closes2), 180)
check("BELOW_MIN 미만 아래 → rebreak", cr2 == [(205, "rebreak")], cr2)
# 인과성: 돌파 시점까지의 데이터만으로 같은 신호
cr_trunc, _ = sm.crosses(rows[:261], 180)
check("인과성: rows[:i+1] 로 같은 돌파", cr_trunc == [(260, "fresh")])
check("교차 없으면 신호 없음", sm.crosses(rows_from([100.0] * 300), 180)[0] == [])

# ── 2. 필터 ─────────────────────────────────────────────────────────────────
i = 260
check("raw 항상 통과", sm.passes("raw", rows, i, ma))
check("decisive: 110 >= MA×1.02 통과", sm.passes("decisive", rows, i, ma))
rows_w = rows_from([100.0] * 200 + [90.0] * 60 + [97.5] * 30)      # MA≈96.7 근처 → 1.02 미달
cr_w, ma_w = sm.crosses(rows_w, 180)
check("decisive: 약한 돌파 탈락", cr_w and not sm.passes("decisive", rows_w, cr_w[0][0], ma_w))
rows_v = rows_from(closes); rows_v[260]["v"] = 400.0
check("volume: 돌파봉 거래량 ≥ 20봉 평균×1.5 통과", sm.passes("volume", rows_v, 260, ma))
check("volume: 평균 거래량이면 탈락", not sm.passes("volume", rows, 260, ma))
check("slope: 하락 중인 MA(90 구간 반영) 는 탈락", not sm.passes("slope", rows, 260, ma))
rows_up = rows_from([80.0] * 200 + [100.0] * 40 + [95.0] * 25 + [105.0] * 10)
cr_u, ma_u = sm.crosses(rows_up, 180)
check("slope: 상승 중인 MA 통과", cr_u and sm.passes("slope", rows_up, cr_u[-1][0], ma_u), cr_u)
check("deep: 직전 60봉 최저 종가가 MA 대비 −20% 이하", sm.passes("deep", rows_from([100.0] * 200 + [70.0] * 60 + [110.0] * 30), 260,
                                                              sm.crosses(rows_from([100.0] * 200 + [70.0] * 60 + [110.0] * 30), 180)[1]))
check("deep: 얕은 조정은 탈락", not sm.passes("deep", rows, 260, ma))

# ── 3. forward · summarize ──────────────────────────────────────────────────
r = rows_from([100.0] * 70)
r[10]["c"] = 100.0
for j in range(11, 71):
    r[j].update(c=100.0 + (j - 10) * 0.5, h=100.0 + (j - 10) * 0.5 + 30 * (j == 30), l=99.0)
f = sm.forward(r, 10)
check("forward: +20봉 수익 = 110/100−1", abs(f["r20"] - 0.10) < 1e-9, f["r20"])
check("forward: MFE40 = 봉30 고가 스파이크(140)", abs(f["mfe40"] - 0.40) < 1e-9, f["mfe40"])
check("forward: MFE20 은 스파이크 포함, MAE 저가 99", abs(f["mfe20"] - 0.40) < 1e-9 and abs(f["mae20"] - (-0.01)) < 1e-9)
check("forward: 데이터 부족 시 None(+60)", f["r60"] is None and f["mfe60"] is None)
evs = [dict(fwd=dict(r5=0.01, r10=0.02, r20=0.05, r40=None, r60=None, mfe20=0.25, mae20=-0.05, mfe40=0.35, mae40=-0.05, mfe60=None, mae60=None),
            retest=0, label=0.1, d=0.05),
       dict(fwd=dict(r5=-0.01, r10=-0.02, r20=-0.05, r40=None, r60=None, mfe20=0.05, mae20=-0.10, mfe40=0.10, mae40=-0.12, mfe60=None, mae60=None),
            retest=1, label=-0.1, d=-0.08)]
s = sm.summarize(evs)
check("summarize: 슈팅률 40봉 ≥20% 50%, ≥30% 50%, ≥50% 0%", s["mfe40"]["shoot20"] == 0.5 and s["mfe40"]["shoot30"] == 0.5 and s["mfe40"]["shoot50"] == 0.0)
check("summarize: 재하향 50%, 라벨 평균 0, D 승률 50%", s["retest20"] == 0.5 and abs(s["label_mean"]) < 1e-12 and s["d_win"] == 0.5)
check("summarize: r20 승률 50%, r60 None", s["r20"]["win"] == 0.5 and s["r60"] is None)
check("summarize: 빈 입력", sm.summarize([]) == dict(n=0))

# ── 4. 사전 등록·등재 ───────────────────────────────────────────────────────
check("MA 창 180/200/250, BELOW_MIN 20, 필터 6종(rebreak 포함)", sm.MA_WINDOWS == (180, 200, 250) and sm.BELOW_MIN == 20
      and set(sm.FILTERS) == {"raw", "decisive", "volume", "slope", "deep", "rebreak"})
check("슈팅 임계 20/30/50%, MFE 창 20/40/60", sm.SHOOT_THR == (0.20, 0.30, 0.50) and sm.MFE_K == (20, 40, 60))
src = open("study_ma_breakout.py", encoding="utf-8").read()
check("실거래 코드 미import", "import paper_executor" not in src and "import scheduler" not in src)
check("탐색적 분석 명시(배포 판정 아님)", "배포 판정 시험이 아니다" in src)
wf = open(".github/workflows/ma_breakout.yml", encoding="utf-8").read()
check("워크플로: 테스트 → 스터디 → 아티팩트", "python test_ma_breakout.py" in wf and "python study_ma_breakout.py" in wf and "_ma_breakout.json" in wf)
check("tests.yml 등재", "test_ma_breakout.py" in open(".github/workflows/tests.yml", encoding="utf-8").read())

print(f"\n{len(fails)} failed")
sys.exit(1 if fails else 0)
