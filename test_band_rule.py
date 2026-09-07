"""validate_band_rule 고정 — 동결 파라미터·띠 규칙 기전(고정 P·갭·지연)·지연 벌금 정의·바스켓·판정 규칙·실거래 무변경.
실행: python test_band_rule.py"""
import json
from datetime import date, timedelta

import validate_band_rule as bd

fails = []
def check(n, c, d=""):
    print(("PASS " if c else "FAIL ") + n + ("" if c else f" — {d}")); c or fails.append(n)

def mk(cl, start="2020-01-01", lows=None, highs=None, opens=None):
    d0 = date.fromisoformat(start); out = []
    for i, c in enumerate(cl):
        o = opens[i] if opens else (cl[i-1] if i else c)
        out.append(dict(date=(d0+timedelta(days=i)).isoformat(), ts=None, o=o,
                        h=highs[i] if highs else max(o, c), l=lows[i] if lows else min(o, c), c=c, v=100.0))
    return out

# ── 1. 동결 ──────────────────────────────────────────────────────────────────────────────
check("손절 격자 (1,3,8)% 주 1% · 수수료 0.1% · 지연 (0,1,4)h · 코호트 30 · 1h 365일 · 바스켓 20 · 문턱 0.85",
      bd.STOPS == (0.01, 0.03, 0.08) and bd.STOP_PRIMARY == 0.01 and bd.FEE == 0.001 and bd.DELAYS_H == (0, 1, 4)
      and bd.COHORT_N == 30 and bd.H1_DAYS == 365 and bd.BASKET_N == 20 and bd.PASS_RATIO == 0.85)
check("구간 4개 고정 · 판정 기준 구간 지정", len(bd.PERIODS) == 4 and bd.BULL_KEY == "bull" and bd.BEAR_KEY == "bear2022")
check("배포 반영 없음", bd.DEPLOY_ON_PASS is False)
reg = json.load(open("registry.json", encoding="utf-8"))["band_rule_prereg_2026_09_07"]
check("registry 사전 등록과 일치", reg["frozen"]["stop_primary"] == 0.01 and reg["frozen"]["pass_ratio"] == 0.85
      and reg["frozen"]["delays_h"] == [0, 1, 4] and reg["deploy_on_pass"] is False)
check("registry 가 '규칙이 좋은가'를 묻지 않음을 명시", "in-sample" in reg["what_is_not_asked"] or "아니" in reg["what_is_not_asked"])

# ── 2. 띠 규칙 기전 ──────────────────────────────────────────────────────────────────────
# 진입 100 → 98 로 하락(1% 손절 발동) → 100 회복 → 다시 98 → 100. 순환 2회.
cl=[100]+[98,99,100,101]+[98,99,100,101]+[105]*3
r=mk(cl)
o=bd.run_band(r,0,len(r)-1,0.01)
check("고정 띠: 손절가는 항상 최초 진입가 기준(P 불변) — 순환 2회", o[2]==2)
check("회당 비용 = 손절폭+수수료 → 2회 후 배수가 보유보다 약 2.4% 낮다",
      abs((o[0]/o[1]) - (0.99*(1-bd.FEE)**2)**2/(1-bd.FEE)**0) < 0.02, f"{o[0]/o[1]:.4f}")
flat=bd.run_band(mk([100]*20),0,19,0.01)
check("손절 안 닿으면 순환 0, 결과 = 보유 − 진입수수료", flat[2]==0 and abs(flat[0]-(1-bd.FEE))<1e-9)
up=bd.run_band(mk([100*1.02**i for i in range(30)]),0,29,0.01)
check("상승만 하면 순환 0 (그냥 보유와 동일)", up[2]==0 and abs(up[0]/up[1]-(1-bd.FEE))<1e-9)
dn=bd.run_band(mk([100*0.97**i for i in range(40)]),0,39,0.01)
check("하락만 하면 1회 손절 후 현금 유지 — 보유보다 훨씬 낫다", dn[2]==1 and dn[0]>dn[1]*3)
# 갭: 시가가 손절가보다 아래면 시가에 체결
g=mk([100,90,100],opens=[100,90,100],lows=[100,89,95],highs=[100,91,101])
og=bd.run_band(g,0,2,0.01,gap=True); ong=bd.run_band(g,0,2,0.01,gap=False)
check("갭 하락 시 시가 체결(손절가보다 나쁨)", og[0] < ong[0])
check("재매수 시 슬리피지가 결과를 낮춘다", bd.run_band(r,0,len(r)-1,0.01,slip=0.01)[0] < o[0])

# ── 3. 지연 기전 ─────────────────────────────────────────────────────────────────────────
# 손절 후 1봉 뒤에 이미 P 위 → 추격 매수(벌금). late 카운트 1.
v=mk([100,98,105,106],lows=[100,98,99,105],highs=[100,99,106,107])
d0=bd.run_band(v,0,3,0.01,delay=0); d1=bd.run_band(v,0,3,0.01,delay=1)
check("지연 0: 트리거가 P 에 정확히 체결 (벌금 0건)", d0[3]==0 and d0[2]==1)
check("지연 1: 알아챈 시점에 이미 P 위 → 추격 매수 1건, 결과가 더 나쁘다", d1[3]==1 and d1[0]<d0[0])
# 손절 후 계속 P 아래면 지연이 있어도 벌금 없음
w=mk([100,98,97,96,100,101],lows=[100,98,97,96,97,100],highs=[100,99,98,97,101,102])
e0=bd.run_band(w,0,5,0.01,delay=0); e1=bd.run_band(w,0,5,0.01,delay=1)
check("손절 후 P 아래에 머물면 지연이 무해(벌금 0, 결과 동일)", e1[3]==0 and abs(e0[0]-e1[0])<1e-12)
# delay_cost 는 실데이터용 200봉 하한이 있어 사건 뒤를 평탄하게 채운다(P 위 유지 → 추가 손절 없음)
vL=mk([100,98,105,106]+[106]*200,lows=[100,98,99,105]+[105]*200,highs=[100,99,106,107]+[107]*200)
wL=mk([100,98,97,96,100,101]+[101]*200,lows=[100,98,97,96,97,100]+[100]*200,highs=[100,99,98,97,101,102]+[102]*200)
a=bd.delay_cost({"X":vL},0.01,1)
check("delay_cost: 손절 1건 중 1건이 추격 → 비율 1.0, 초과 = 그 봉 종가/P−1", a["events"]==1 and a["late"]==1
      and abs(a["share"]-1.0)<1e-12 and abs(a["median_excess"]-(105/100-1))<1e-9)
check("delay_cost: P 아래 머물면 추격 0건·초과 0", bd.delay_cost({"X":wL},0.01,1)["late"]==0
      and bd.delay_cost({"X":wL},0.01,1)["events"]==1)
check("delay_cost: 200봉 미만 종목은 건너뛴다(실데이터 하한)", bd.delay_cost({"X":v},0.01,1)["events"]==0)

# ── 4. 바스켓·구간 ───────────────────────────────────────────────────────────────────────
rows={f"c{k}": mk([100]+[98,99,100,101]*3+[100*1.5]*5, "2020-04-29") for k in range(5)}
sp=bd.span(rows["c0"],"2020-04-29","2020-06-30")
check("span: 60봉 미만이면 None", bd.span(mk([100]*30),"2020-01-01","2020-01-30") is None)
rows2={f"c{k}": mk([100.0]*200,"2020-04-29") for k in range(5)}
b=bd.basket(rows2,list(rows2),"2020-04-29","2020-11-01",0.01)
check("바스켓: 동일가중 평균, 종목수 반환", b is not None and b[2]==5 and abs(b[1]-1.0)<1e-9)
check("바스켓: 없는 종목·짧은 구간은 건너뜀", bd.basket(rows2,["zzz"],"2020-04-29","2020-11-01",0.01) is None)

# ── 5. 무변경·등재 ───────────────────────────────────────────────────────────────────────
src=open("validate_band_rule.py",encoding="utf-8").read()
check("실거래·배포 코드 없음", "import paper_executor" not in src and "import scheduler" not in src and "adopted_" not in src)
sched=open("scheduler.py",encoding="utf-8").read()+open("paper_executor.py",encoding="utf-8").read()
check("스케줄러·실행기가 이 모듈을 읽지 않음", "validate_band_rule" not in sched)
wf=open(".github/workflows/band_rule.yml",encoding="utf-8").read()
check("워크플로: 테스트 선행 + 실행", "python test_band_rule.py" in wf and "python validate_band_rule.py" in wf)
check("tests.yml 등재", "test_band_rule.py" in open(".github/workflows/tests.yml",encoding="utf-8").read())

print(f"\n{'ALL PASS' if not fails else 'FAILED: ' + ', '.join(fails)} ({len(fails)} fail)")
import sys; sys.exit(1 if fails else 0)
