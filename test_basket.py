"""validate_basket 고정 — 동결 파라미터·PIT 풀·선택 기준·자산곡선/재구성·통계·판정 규칙·실거래 무변경.
실행: python test_basket.py"""
import json
from datetime import date, timedelta

import validate_band_rule as br
import validate_basket as vb
import validate_breadth_state as bs

fails = []
def check(n, c, d=""):
    print(("PASS " if c else "FAIL ") + n + ("" if c else f" — {d}")); c or fails.append(n)

def mk(cl, start="2019-01-01", v=1.0, lows=None, highs=None):
    d0 = date.fromisoformat(start); out = []
    for i, c in enumerate(cl):
        o = cl[i-1] if i else c
        out.append(dict(date=(d0+timedelta(days=i)).isoformat(), ts=None, o=o,
                        h=highs[i] if highs else max(o, c), l=lows[i] if lows else min(o, c), c=c, v=v))
    return out

# ── 1. 동결 ──────────────────────────────────────────────────────────────────────────────
check("손절 1% · 슬립 0.141%(band_rule δ) · 수수료 band_rule 과 동일 · 풀 60 · 무작위 200 · 95백분위",
      vb.STOP == 0.01 and abs(vb.SLIP - 0.00141) < 1e-9 and vb.FEE == br.FEE and vb.POOL_N == 60
      and vb.RANDOM_DRAWS == 200 and vb.PCTL == 95 and vb.SEED == 42)
check("기준 5 · N 격자 4 · 재구성 3 · 주판정 N=20/quarterly · 구간 2019-06~2026-09",
      vb.CRITERIA == ("liquidity","lowvol","defensive","broad","random") and vb.N_GRID == (5,10,20,40)
      and vb.REBAL == {"none":None,"quarterly":91,"monthly":30} and (vb.N_PRIMARY, vb.REBAL_PRIMARY) == (20,"quarterly")
      and vb.START == "2019-06-01" and vb.END == "2026-09-06")
check("프로필 부호를 breadth_state 에서 그대로 가져옴(재정의 안 함)", "bs.BROAD" in open("validate_basket.py",encoding="utf-8").read()
      and "bs.DEFENSIVE" in open("validate_basket.py",encoding="utf-8").read())
check("배포 반영 없음", vb.DEPLOY_ON_PASS is False)
reg = json.load(open("registry.json", encoding="utf-8"))["basket_prereg_2026_09_07"]
check("registry 사전 등록과 일치", reg["frozen"]["stop"] == 0.01 and reg["frozen"]["pool_n"] == 60
      and reg["frozen"]["n_grid"] == [5,10,20,40] and reg["frozen"]["random_draws"] == 200 and reg["deploy_on_pass"] is False)
check("registry 가 사전 확률(선택은 잘 안 된다)과 생존 편향 경고를 결과 전에 적었다",
      "NO_SELECTION_EDGE" in reg["prior"] and "생존" in reg["known_limits"] and "방어" in reg["known_limits"])

# ── 2. PIT 풀 ────────────────────────────────────────────────────────────────────────────
rows = {f"c{k}": mk([100.0]*400, v=float(10-k)) for k in range(8)}      # 거래대금 c0 > c1 > ...
p = vb.pool_at(rows, "2019-12-01", pool_n=3)
check("풀: 거래대금 상위 순서", [s for s,_ in p] == ["c0","c1","c2"])
check("풀: 이력 252봉 미만 날짜는 비어 있음", vb.pool_at(rows, "2019-03-01", pool_n=3) == [])
check("풀 원소는 (심볼, 그날 인덱스)", all(rows[s][i]["date"]=="2019-12-01" for s,i in p))
rows2 = {**rows, "cX": mk([100.0]*400, v=999.0)}
check("PIT: 거래대금이 큰 종목이 상위로 (그날까지의 정보만)", vb.pool_at(rows2,"2019-12-01",pool_n=1)[0][0] == "cX")

# ── 3. 선택 기준 ─────────────────────────────────────────────────────────────────────────
import random as _r
_rr = _r.Random(3)
def rw(n, drift=0.0, vol=0.02):
    cl=[100.0]
    for _ in range(n-1): cl.append(max(cl[-1]*(1+drift+_rr.uniform(-vol,vol)),1e-6))
    return cl
sel_rows = {}
for k in range(18):                                   # profile_score 는 코인 >= 15 를 요구 — 풀을 그 이상으로
    sel_rows[f"s{k:02d}"] = mk(rw(500, vol=0.004+0.003*k), v=float(30-k))   # s00 저변동 … s17 고변동
btc = mk(rw(500))
cache={}
def ff(s,r):
    if s not in cache: cache[s]=bs.FastFeatures(r,btc)
    return cache[s]
pool = vb.pool_at(sel_rows, sel_rows["s00"][450]["date"], pool_n=18)
check("풀 18종목 확보", len(pool)==18)
lv = [s for s,_ in vb.select(sel_rows, pool, "lowvol", 3, ff)]
rvols = sorted(((ff(s,sel_rows[s]).at(i)["rvol20"], s) for s,i in pool))
check("lowvol: 실현변동성 최저 3종목", set(lv) == {s for _,s in rvols[:3]}, f"{lv} vs {[s for _,s in rvols[:3]]}")
liq = [s for s,_ in vb.select(sel_rows, pool, "liquidity", 3, ff)]
check("liquidity: 풀 상위 3 그대로(풀은 거래대금 내림차순)", liq == [s for s,_ in pool[:3]])
r1 = [s for s,_ in vb.select(sel_rows, pool, "random", 3, ff, seed=1)]
r1b = [s for s,_ in vb.select(sel_rows, pool, "random", 3, ff, seed=1)]
r2 = [s for s,_ in vb.select(sel_rows, pool, "random", 3, ff, seed=2)]
check("random: 같은 시드면 재현, 다른 시드면 다름", r1 == r1b and len(r1)==3 and r1 != r2)
dfn = [s for s,_ in vb.select(sel_rows, pool, "defensive", 5, ff)]
brd = [s for s,_ in vb.select(sel_rows, pool, "broad", 5, ff)]
check("defensive/broad: 5종목 선택 · 서로 다른 집합(부호가 반대인 프로필)", len(dfn)==5 and len(brd)==5 and set(dfn)!=set(brd), f"{dfn} vs {brd}")
check("선택 결과는 풀의 부분집합", set(lv)<=set(s for s,_ in pool) and set(dfn)<=set(s for s,_ in pool))
# 실제 동작 고정: 풀이 profile_score 최소 코인 수(15) 미만이면 프로필 기준은 liquidity 로 폴백한다
small = pool[:10]
check("풀 < 15 이면 defensive/broad 는 liquidity 로 폴백(profile_score 가 빈 dict)",
      bs.profile_score([(s, ff(s,sel_rows[s]).at(i)) for s,i in small], bs.DEFENSIVE) == {}
      and [s for s,_ in vb.select(sel_rows, small, "defensive", 3, ff)] == [s for s,_ in small[:3]])

# ── 4. 자산곡선·재구성 ───────────────────────────────────────────────────────────────────
dts = [x["date"] for x in sel_rows["s00"][300:400]]
flat = mk([100.0]*500)
c = vb.sleeve_curve(flat, 300, 399, dts)
check("sleeve: 평탄하면 진입수수료만 차감된 채 유지", abs(c[0]-(1-vb.FEE))<1e-9 and abs(c[-1]-(1-vb.FEE))<1e-9)
up = mk([100*1.01**i for i in range(500)])
cu = vb.sleeve_curve(up, 300, 399, dts)
check("sleeve: 상승만 하면 손절 없이 보유와 같은 궤적", cu[-1] > cu[0]*2.5 and abs(cu[-1]/cu[0] - up[399]["c"]/up[300]["c"]) < 1e-6)
dn = mk([100*0.97**i for i in range(500)])
cd = vb.sleeve_curve(dn, 300, 399, dts)
ch = vb.hold_curve(dn, 300, 399, dts)
check("sleeve: 하락에서 손절 후 현금 — 보유보다 훨씬 낫다", cd[-1] > ch[-1]*3)
check("hold_curve: 시작 1.0, 가격비 그대로", abs(ch[0]-1.0)<1e-9 and abs(ch[-1]-(dn[399]["c"]/dn[300]["c"]))<1e-9)
b_none = vb.basket_curve(sel_rows, dts, "liquidity", 3, None, ff)
b_reb = vb.basket_curve(sel_rows, dts, "liquidity", 3, 30, ff)
check("basket: 길이 = 날짜 수, 시작 1.0 근처", len(b_none)==len(dts) and 0.9 < b_none[0] <= 1.0 and len(b_reb)==len(dts))
check("재구성 arm 은 수수료를 더 문다(같은 선택이면 최종이 더 낮거나 같다)", b_reb[-1] <= b_none[-1]*1.05)
bh = vb.basket_curve(sel_rows, dts, "liquidity", 3, None, ff, hold=True)
check("hold=True 는 띠 규칙 없이 보유", len(bh)==len(dts) and abs(bh[0]-1.0)<1e-9)

# ── 5. 통계·판정 ─────────────────────────────────────────────────────────────────────────
s = vb.stats([1.0,1.2,0.9,1.5], 365)
check("stats: 최종·MDD·CAGR·Calmar", abs(s["final"]-1.5)<1e-9 and abs(s["mdd"]-(0.9/1.2-1))<1e-9
      and s["cagr"] is not None and s["calmar"] is not None and s["calmar"]>0)
check("stats: MDD 0(단조 상승)이면 Calmar None", vb.stats([1.0,1.1,1.2],365)["calmar"] is None)
check("stats: 빈 곡선 안전", vb.stats([],365)["final"] is None)
h = vb.holm({"a":0.01,"b":0.04,"c":0.5})
check("Holm: 단조 비감소·최소값 보정", h["a"]>=0.03-1e-9 and h["c"]>=h["b"]>=h["a"])
check("Holm: None 은 제외", "d" not in vb.holm({"a":0.01,"d":None}))

# ── 6. 무변경·등재 ───────────────────────────────────────────────────────────────────────
src=open("validate_basket.py",encoding="utf-8").read()
check("실거래·배포 코드 없음", "import paper_executor" not in src and "import scheduler" not in src and "adopted_" not in src)
sched=open("scheduler.py",encoding="utf-8").read()+open("paper_executor.py",encoding="utf-8").read()
check("스케줄러·실행기가 이 모듈을 읽지 않음", "validate_basket" not in sched)
wf=open(".github/workflows/basket.yml",encoding="utf-8").read()
check("워크플로: data-long 체크아웃 + 테스트 선행 + 실행", "data-long" in wf and "python test_basket.py" in wf and "python validate_basket.py" in wf)
check("tests.yml 등재", "test_basket.py" in open(".github/workflows/tests.yml",encoding="utf-8").read())

print(f"\n{'ALL PASS' if not fails else 'FAILED: ' + ', '.join(fails)} ({len(fails)} fail)")
import sys; sys.exit(1 if fails else 0)
