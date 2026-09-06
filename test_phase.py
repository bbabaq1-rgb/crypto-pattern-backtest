"""
국면 위치 진단·필터 시험(validate_phase) 고정 — 2026-09-06.

확인 대상:
  - Features: 에피소드 나이(인과) · 재점등(직전 bull 끝과의 간격 <=180일, 첫 에피소드는 신규) · BTC 낙폭(당일 포함 365봉 최고 대비)
  - 버킷 경계 동결 (90/270일, 180일, -10/-30%)
  - 1단계 규칙: ordered 변수(최악<0 & 최선>0 셀 >=3 & 최악 위치 일치 >=3), binary 변수(재점등<신규 >=4 & 재점등<0 >=3)
  - 2단계 판정 = ①제외분 mean<0 ∧ ②D+F CONFIRMED ∧ ③Calmar 비악화
  - 셀 5개·bull_btc·top30·롱 고정, 실거래 코드 미import, 워크플로·tests.yml 등재

실행: python test_phase.py
"""
import sys
from datetime import date, timedelta

import validate_phase as vp

fails = []


def check(n, c, d=""):
    print(("PASS " if c else "FAIL ") + n + ("" if c else f" — {d}"))
    c or fails.append(n)


def days(start, n):
    d0 = date.fromisoformat(start)
    return [(d0 + timedelta(days=i)).isoformat() for i in range(n)]


# 레짐: bull 300 / bear 400 / bull 100(재점등 아님: 간격 400) / bear 100 / bull 60(재점등: 간격 100) / bear 200
seq = ["bull_btc"] * 300 + ["bear"] * 400 + ["bull_btc"] * 100 + ["bear"] * 100 + ["bull_btc"] * 60 + ["bear"] * 200
dl = days("2020-01-01", len(seq)); regmap = dict(zip(dl, seq))
# BTC: 1000 봉 상승 후 고점, 이후 하락
btc = []
for i, d in enumerate(dl):
    c = 100 + i if i < 700 else 800 - (i - 700) * 1.5
    btc.append(dict(date=d, c=c))
f = vp.Features(regmap, btc)
check("에피소드 3개", len(f.eps) == 3, f.eps)
check("나이: 에피소드 첫날 0, 100일째 100", f.age(dl[0]) == 0 and f.age(dl[100]) == 100)
check("나이: bear 날은 None", f.age(dl[500]) is None)
check("재점등: 첫 에피소드 신규", f.reignition(dl[10]) is False)
check("재점등: 간격 400일 → 신규", f.reignition(dl[750]) is False)
check("재점등: 간격 100일 → 재점등", f.reignition(dl[850]) is True)
check("낙폭: 상승 중 0", abs(f.drawdown(dl[500])) < 1e-9)
dd = f.drawdown(dl[900])   # 고점 800(=i 699 → 799) 대비
check("낙폭: 고점 뒤 음수·인과(당일 포함 365봉 최고)", dd is not None and -0.5 < dd < -0.2, dd)
check("버킷 A", f.bucket("A_age", dl[30]) == "<=90d" and f.bucket("A_age", dl[200]) == "91~270d" and f.bucket("A_age", dl[299]) == ">270d")
check("버킷 B", f.bucket("B_reig", dl[720]) == "신규" and f.bucket("B_reig", dl[820]) == "재점등")
check("버킷 C", f.bucket("C_dd", dl[100]) == ">-10%" and f.bucket("C_dd", dl[900]) in ("-10~-30%", "<-30%"))
check("동결 경계: 90/270, 180, -10/-30, 365", vp.AGE_CUTS == (90, 270) and vp.REIG_GAP == 180 and vp.DD_CUTS == (-0.10, -0.30) and vp.DD_LB == 365)

# ── 1단계 규칙 ──
def tab(**kw):  # 버킷명 → (n, mean)
    return {b: dict(n=n, mean=m, win=None, median=None) for b, (n, m) in kw.items()}
A = vp.BUCKETS["A_age"]
good = {f"c{i}": {A[0]: dict(n=10, mean=0.05), A[1]: dict(n=10, mean=0.02), A[2]: dict(n=10, mean=-0.03)} for i in range(3)}
good["c3"] = {A[0]: dict(n=10, mean=0.01), A[1]: dict(n=10, mean=0.03), A[2]: dict(n=10, mean=0.02)}
good["c4"] = {A[0]: dict(n=3, mean=0.0), A[1]: dict(n=10, mean=0.01), A[2]: dict(n=10, mean=-0.01)}
ok, worst, det = vp.stage1_rule(good, "A_age")
check("ordered: 3셀 최악<0·최선>0·같은 버킷 → 통과, 최악=>270d", ok and worst == ">270d", (ok, worst, det))
mixed = dict(good); mixed["c2"] = {A[0]: dict(n=10, mean=-0.02), A[1]: dict(n=10, mean=0.02), A[2]: dict(n=10, mean=0.03)}
ok2, w2, _ = vp.stage1_rule(mixed, "A_age")
check("ordered: 최악 위치가 2:1 로 갈리면 탈락", not ok2 and w2 is None)
B = {f"c{i}": {"신규": dict(n=10, mean=0.03), "재점등": dict(n=10, mean=-0.02)} for i in range(4)}
B["c4"] = {"신규": dict(n=10, mean=0.01), "재점등": dict(n=10, mean=0.02)}
ok3, w3, _ = vp.stage1_rule(B, "B_reig")
check("binary: 재점등<신규 4셀 & 재점등<0 4셀 → 통과", ok3 and w3 == "재점등")
B2 = dict(B); B2["c3"] = {"신규": dict(n=10, mean=0.03), "재점등": dict(n=10, mean=0.01)}
ok4, _, _ = vp.stage1_rule(B2, "B_reig")
check("binary: 재점등<0 이 2셀뿐이면 탈락", not ok4)
B3 = {f"c{i}": {"신규": dict(n=10, mean=0.03), "재점등": dict(n=3, mean=-0.05)} for i in range(5)}
check("binary: n<5 버킷은 세지 않음 → 탈락", not vp.stage1_rule(B3, "B_reig")[0])

# ── 고정 ──
check("셀 5개 · bull_btc · top30 · 롱", [c for c, _ in vp.CELLS] == ["double_bottom_1d", "ma180_decisive", "triple_bottom_1d", "inverse_hs_1d", "three_soldiers_4h"]
      and vp.G == "bull_btc" and vp.COHORT == "top30" and vp.DIRECTION == "long")
check("변수 3개·버킷 고정", vp.VARS == ("A_age", "B_reig", "C_dd") and len(vp.BUCKETS["A_age"]) == 3 and len(vp.BUCKETS["B_reig"]) == 2)
src = open("validate_phase.py", encoding="utf-8").read()
check("실거래 코드 미import", "import paper_executor" not in src and "import scheduler" not in src)
check("2단계 3조건·사용자 결정 명시", "ADOPT_CANDIDATE" in src and "실거래 반영 없음" in src)
wf = open(".github/workflows/phase.yml", encoding="utf-8").read()
check("워크플로: 테스트 → 시험 → 아티팩트", "python test_phase.py" in wf and "python validate_phase.py" in wf and "_phase.json" in wf)
check("tests.yml 등재", "test_phase.py" in open(".github/workflows/tests.yml", encoding="utf-8").read())

print(f"\n{len(fails)} failed")
sys.exit(1 if fails else 0)
