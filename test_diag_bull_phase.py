"""diag_bull_phase 고정 — 버킷 경계(사용자 사양) 동결, 특성 인과성, 진단 전용(필터·채택 없음). 실행: python test_diag_bull_phase.py"""
import sys
from datetime import date, timedelta
import diag_bull_phase as dg

fails = []
def check(n, c, d=""):
    print(("PASS " if c else "FAIL ") + n + ("" if c else f" — {d}")); c or fails.append(n)
def days(start, n):
    d0 = date.fromisoformat(start); return [(d0 + timedelta(days=i)).isoformat() for i in range(n)]

check("버킷 동결: 경과개월 0-2/3-5/6-8/9-11/12+", [b[0] for b in dg.AGE_BUCKETS] == ["0-2m", "3-5m", "6-8m", "9-11m", "12m+"] and dg.AGE_BUCKETS[0][1:] == (0, 2) and dg.AGE_BUCKETS[4][1] == 12)
check("버킷 동결: 재점등 6개월(182일), 낙폭 0/-10/-20, 1년 고점 365봉, 월별 2023-01~", dg.REIG_DAYS == 182 and [b[0] for b in dg.DD_BUCKETS] == ["0~-10%", "-10~-20%", "<=-20%"] and dg.DD_LB == 365 and dg.MONTH_FROM == "2023-01")
check("우선 4패턴", dg.PRIORITY == ["double_bottom_1d", "ma180_decisive", "inverse_hs_1d", "three_soldiers_4h"])

seq = ["bull_btc"] * 400 + ["bear"] * 400 + ["bull_btc"] * 100 + ["bear"] * 100 + ["bull_btc"] * 60 + ["bear"] * 250
dl = days("2020-01-01", len(seq)); regmap = dict(zip(dl, seq))
rows = {"BTC": [dict(date=d, c=(100 + i if i < 700 else 800 - (i - 700) * 1.2)) for i, d in enumerate(dl)],
        "ETH": [dict(date=d, c=10 + i * 0.02) for i, d in enumerate(dl)]}
for a in ("SOL", "XRP", "ADA", "AVAX", "TRX"):
    rows[a] = [dict(date=d, c=1 + i * 0.001) for i, d in enumerate(dl)]
mk = dg.Market(regmap, rows)
check("에피소드 3개", len(mk.eps) == 3)
check("경과개월 버킷: 0일→0-2m, 100일→3-5m, 200→6-8m, 300→9-11m, 399→12m+", [mk.age_bucket(dl[i]) for i in (0, 100, 200, 300, 399)] == ["0-2m", "3-5m", "6-8m", "9-11m", "12m+"])
check("bear 날은 None", mk.age_bucket(dl[500]) is None and mk.reignition(dl[500]) is None)
check("재점등: 간격 400일 → 신규, 100일 → 재점등, 첫 에피소드 신규", mk.reignition(dl[850]) == "신규(>6m)" and mk.reignition(dl[1020]) == "재점등(<=6m)" and mk.reignition(dl[5]) == "신규(>6m)")
check("낙폭: 상승 중 0~-10%, 고점 뒤 <=-20% (당일 포함 365봉 최고, 인과)", mk.dd_bucket(dl[600]) == "0~-10%" and mk.dd_bucket(dl[1000]) == "<=-20%")
check("forward: 데이터 끝 넘으면 None, 안쪽은 값", mk.btc_fwd(dl[-10], 91) is None and mk.btc_fwd(dl[100], 91) is not None and abs(mk.btc_fwd(dl[100], 91) - (291 / 200 - 1)) < 1e-9)
check("알트 상대 30d: 알트가 BTC 보다 느리면 음수", mk.alt_rel_30d(dl[300]) is not None and mk.alt_rel_30d(dl[300]) < 0)
t = dg.welch_t([0.1, 0.2, 0.15, 0.12], [0.0, 0.01, -0.01, 0.02])
check("Welch t 양수·크기", t is not None and t > 3)
check("Spearman: 단조 증가 1.0, n<4 None", abs(dg.spearman([1, 2, 3, 4], [2, 4, 6, 9]) - 1.0) < 1e-9 and dg.spearman([1, 2], [1, 2]) is None)
c = dg.cell([0.1, -0.05, 0.2], [0.0, 0.01])
check("cell: 엣지 = 패턴평균 − 무작위평균", abs(c["edge"] - (st_ := (0.25 / 3 - 0.005))) < 1e-9 and c["n"] == 3 and c["rnd_n"] == 2)
src = open("diag_bull_phase.py", encoding="utf-8").read()
check("진단 전용: 필터/채택/실거래 코드 없음", "ADOPT" not in src and "import paper_executor" not in src and "adopted_patterns" not in src)
check("무작위 대조 명시", "엣지 = 패턴 −" in src)
wf = open(".github/workflows/diag_bull_phase.yml", encoding="utf-8").read()
check("워크플로 등재", "python diag_bull_phase.py" in wf and "python test_diag_bull_phase.py" in wf)
check("tests.yml 등재", "test_diag_bull_phase.py" in open(".github/workflows/tests.yml", encoding="utf-8").read())
print(f"\n{len(fails)} failed"); sys.exit(1 if fails else 0)
