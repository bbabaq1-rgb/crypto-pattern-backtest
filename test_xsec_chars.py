"""xsec_features / validate_xsec_chars 고정 — 가족·부호 동결, 피처 인과성, 지표 정의, 통계, 판정 규칙, 실거래 무변경.
실행: python test_xsec_chars.py"""
import json
import math
import random
from datetime import date, timedelta

import validate_guard_v4 as g4
import validate_pit_cohort as pc
import validate_xsec_chars as vx
import xsec_features as xf

fails = []
def check(n, c, d=""):
    print(("PASS " if c else "FAIL ") + n + ("" if c else f" — {d}")); c or fails.append(n)

# ── 1. 동결 ──────────────────────────────────────────────────────────────────────────────
check("가족 24 변수 · 키 유일 · 부호 {+,-,?}", len(xf.KEYS) == 24 and len(set(xf.KEYS)) == 24 and set(xf.SIGN.values()) <= {"+", "-", "?"})
check("사용자 지정 변수 포함: 일목 4 · RSI 다이버전스 · MA60/120/180 거리", {"ichi_cloud_pos", "ichi_tk", "ichi_future_cloud", "ichi_cloud_thick", "rsi_div", "dist_ma60", "dist_ma120", "dist_ma180"} <= set(xf.KEYS))
check("중복 제외: rs_btc_1m(=mom_1m 순위) 없음", "rs_btc_1m" not in xf.KEYS)
check("사전 부호: mom_1m/mom_3m/ma_align/일목 3/rsi_div/vol_ratio +, rvol20 −", all(xf.SIGN[k] == "+" for k in ("mom_1m", "mom_3m", "ma_align", "ma180_slope", "ichi_cloud_pos", "ichi_tk", "ichi_future_cloud", "rsi_div", "vol_ratio_30_90")) and xf.SIGN["rvol20"] == "-")
check("동결 파라미터: 분할 2025-01 · MIN_CS 15 · train>=24 · OOS>=10 · 연도 60% · α .05 · 비용 0.4% · 부트 1000 · 상하위 20%",
      vx.SPLIT_MONTH == "2025-01" and vx.MIN_CS == 15 and vx.MIN_TRAIN_MONTHS == 24 and vx.MIN_OOS_MONTHS == 10 and vx.YEAR_POS_SHARE == 0.60
      and vx.ALPHA == 0.05 and vx.COST_RT == 0.004 and vx.BOOT_N == 1000 and vx.QUANT == 0.20)
check("일목 9/26/52 · RSI14 · 다이버전스 PH3/LOOK60/RECENT20/GAP40 · fwd20/60 · 40봉 +20%", (xf.TENKAN, xf.KIJUN, xf.SENKOU) == (9, 26, 52) and xf.RSI_N == 14
      and (xf.DIV_PH, xf.DIV_LOOK, xf.DIV_RECENT, xf.DIV_MAXGAP) == (3, 60, 20, 40) and (xf.FWD_PRIMARY, xf.FWD_SECOND, xf.HIT_WINDOW, xf.HIT_THR) == (20, 60, 40, 0.20))
check("배포 반영 없음", vx.DEPLOY_ON_PASS is False)
reg = json.load(open("registry.json", encoding="utf-8"))["xsec_chars_prereg_2026_09_07"]
check("registry 사전 등록과 일치(가족 24·분할·기준)", reg["family_size"] == len(xf.KEYS) and reg["split_month"] == vx.SPLIT_MONTH and reg["family_keys"] == xf.KEYS
      and reg["signs"] == xf.SIGN)

# ── 2. 합성 봉 ────────────────────────────────────────────────────────────────────────────
def mk(closes, start="2023-01-01", vols=None):
    d0 = date.fromisoformat(start); out = []
    for i, c in enumerate(closes):
        o = closes[i - 1] if i else c
        out.append(dict(date=(d0 + timedelta(days=i)).isoformat(), ts=None, o=o, h=max(o, c) * 1.01, l=min(o, c) * 0.99, c=c, v=(vols[i] if vols else 100.0)))
    return out

up = mk([100 * (1.01 ** i) for i in range(400)])
dn = mk([100 * (0.99 ** i) for i in range(400)])
fs_up, fs_dn = xf.FeatureSeries(up, up), xf.FeatureSeries(dn, up)
f_up, f_dn = fs_up.at(300), fs_dn.at(300)
check("상승 추세: dist_ma60/120/180 > 0, 정배열 3, MA180 기울기 > 0", f_up["dist_ma60"] > 0 and f_up["dist_ma120"] > 0 and f_up["dist_ma180"] > 0 and f_up["ma_align"] == 3 and f_up["ma180_slope"] > 0)
check("하락 추세: 거리 < 0, 정배열 0, 기울기 < 0", f_dn["dist_ma60"] < 0 and f_dn["ma_align"] == 0 and f_dn["ma180_slope"] < 0)
check("일목 상승: 구름 위 +1, 전환>기준, 미래 구름 양(+1), 두께 > 0", f_up["ichi_cloud_pos"] == 1 and f_up["ichi_tk"] > 0 and f_up["ichi_future_cloud"] == 1 and f_up["ichi_cloud_thick"] > 0)
check("일목 하락: 구름 아래 −1, 전환<기준, 미래 구름 음(−1)", f_dn["ichi_cloud_pos"] == -1 and f_dn["ichi_tk"] < 0 and f_dn["ichi_future_cloud"] == -1)
check("이력 부족이면 None (구름 77봉·MA180·dd_1y 252봉)", fs_up.at(70)["ichi_cloud_pos"] is None and fs_up.at(100)["dist_ma180"] is None and fs_up.at(250)["dd_1y"] is None and fs_up.at(251)["dd_1y"] is not None)
check("모멘텀 정의: mom_1m = c/c[-21]−1, mom_3m 은 최근 5봉 제외", abs(f_up["mom_1m"] - (1.01 ** 21 - 1)) < 1e-9 and abs(f_up["mom_3m"] - (1.01 ** 58 - 1)) < 1e-9)
check("RSI: 연속 상승 100 / 연속 하락 0 / 처음 14봉 None", f_up["rsi14"] == 100.0 and f_dn["rsi14"] == 0.0 and xf.rsi_series([1.0] * 20)[13] is None and xf.rsi_series([1.0] * 20)[14] is not None)
check("dd_1y 상승 추세 ≈ 0(고가가 종가 위 1%), range_pos_20 상승 = 상단", abs(f_up["dd_1y"]) < 0.02 and f_up["range_pos_20"] > 0.9 and f_dn["range_pos_20"] < 0.1)
check("rvol20 일정 수익률 → 0, 베타(자기 자신 BTC) = 1", abs(f_up["rvol20"]) < 1e-9 and abs(f_up["beta_btc_60"] - 1) < 1e-9 if f_up["beta_btc_60"] is not None else False)
vr = mk([100.0] * 400, vols=[100.0] * 360 + [300.0] * 40)
fv = xf.FeatureSeries(vr).at(399)
check("거래대금 비: 30/90 = 300/(...) > 1, 5/30 = 1(최근 30 동일), turnover 는 log", fv["vol_ratio_30_90"] > 1 and abs(fv["vol_shock_5_30"] - 1) < 1e-9 and abs(fv["turnover_30d"] - math.log(100.0 * 300.0)) < 1e-9)

# 인과성: 봉 i 이후를 바꿔도 at(i) 불변, outcome 만 변함
rng = random.Random(1)
cl = [100.0]
for _ in range(399):
    cl.append(cl[-1] * (1 + rng.uniform(-0.05, 0.05)))
base = mk(cl); fs0 = xf.FeatureSeries(base, base)
i0 = 320
f0, o0 = fs0.at(i0), fs0.outcome(i0)
alt = [dict(r) for r in base]
for r in alt[i0 + 1:]:
    r["c"] *= 2; r["h"] *= 2; r["l"] *= 2; r["v"] *= 3
fs1 = xf.FeatureSeries(alt, alt)
f1, o1 = fs1.at(i0), fs1.outcome(i0)
check("인과성: 미래 봉 변경 → 24 피처 전부 불변", all((f0[k] is None and f1[k] is None) or (f0[k] is not None and f1[k] is not None and abs(f0[k] - f1[k]) < 1e-12) for k in xf.KEYS), str([k for k in xf.KEYS if f0[k] != f1[k]]))
check("결과는 미래 봉에 반응: fwd20 배증, hit 1", abs((1 + o1["fwd20"]) / (1 + o0["fwd20"]) - 2) < 1e-9 and o1["hit20_40"] == 1.0)
check("결과 정의: fwd20 = c[i+20]/c[i]−1, 잘린 창은 None", abs(o0["fwd20"] - (base[i0 + 20]["c"] / base[i0]["c"] - 1)) < 1e-12 and fs0.outcome(390)["fwd20"] is None and fs0.outcome(379)["fwd20"] is not None and fs0.outcome(360)["hit20_40"] is None)
hit_rows = mk([100.0] * 60 + [100.0] * 40)
for r in hit_rows[70:75]: r["h"] = 125.0
check("hit20_40 은 고가 기준(종가 불변이어도 고가 +25% 면 1)", xf.FeatureSeries(hit_rows).outcome(59)["hit20_40"] == 1.0 and xf.FeatureSeries(mk([100.0] * 100)).outcome(59)["hit20_40"] == 0.0)

# RSI 다이버전스: 급락→반등→완만한 더 낮은 저점(RSI 는 더 높음) → 강세 +1, 피벗 확정 전엔 0
seg = [100.0] * 80
seg += [100 - 3 * k for k in range(1, 11)]          # 급락 → 70 (저점 L1 = idx 89)
seg += [70 + 2 * k for k in range(1, 11)]           # 반등 → 90
seg += [90 - 1.1 * k for k in range(1, 21)]         # 완만 하락 → 68 (L2 = idx 119, 더 낮은 저점)
seg += [68 + 1 * k for k in range(1, 35)]           # 반등
dv = mk(seg); fsd = xf.FeatureSeries(dv)
L2 = 119
check("강세 다이버전스: L2 확정 봉(L2+3)부터 +1", fsd.rsi_divergence(L2 + xf.DIV_PH) == 1 and fsd.at(L2 + xf.DIV_PH)["rsi_div"] == 1.0)
check("확정 전(L2+2)엔 강세 아님(인과)", fsd.rsi_divergence(L2 + xf.DIV_PH - 1) != 1)
check("RECENT 20 봉 지나면 상태 해제", fsd.rsi_divergence(L2 + xf.DIV_RECENT + 1) == 0)
segb = [100.0] * 80 + [100 + 3 * k for k in range(1, 11)] + [130 - 2 * k for k in range(1, 11)] + [110 + 1.1 * k for k in range(1, 21)] + [132 - k for k in range(1, 35)]
fsb = xf.FeatureSeries(mk(segb))
check("약세 다이버전스(더 높은 고점·RSI 낮은 고점) −1", fsb.rsi_divergence(119 + xf.DIV_PH) == -1)
check("추세 없는 평탄 구간 0", xf.FeatureSeries(mk([100.0] * 200)).rsi_divergence(150) == 0)
check("month_end_indices 는 달의 마지막 봉", xf.month_end_indices(up)["2023-01"] == 30 and xf.month_end_indices(up)["2023-02"] == 58)

# ── 3. 통계 ──────────────────────────────────────────────────────────────────────────────
check("동률 평균 순위", vx.ranks([1, 2, 2, 3]) == [1.0, 2.5, 2.5, 4.0])
check("스피어만 ±1 · 상수 None", abs(vx.spearman([1, 2, 3, 4], [10, 20, 30, 40]) - 1) < 1e-12 and abs(vx.spearman([1, 2, 3, 4], [4, 3, 2, 1]) + 1) < 1e-12 and vx.spearman([1, 1, 1], [1, 2, 3]) is None)
items = [(f"c{k}", float(k), float(k) / 100) for k in range(20)]
cs = vx.cross_section(items)
check("횡단면: n·IC=1·상위 20%(4개) 평균·하위 평균", cs["n"] == 20 and abs(cs["ic"] - 1) < 1e-12 and abs(cs["top"] - (16 + 17 + 18 + 19) / 400) < 1e-12 and abs(cs["bot"] - (0 + 1 + 2 + 3) / 400) < 1e-12)
check("최소 그룹 3(n 작을 때)", abs(vx.cross_section(items[:8])["top"] - (5 + 6 + 7) / 300) < 1e-12)
check("부트 p: 전부 양수 → 0, 전부 음수 → 1, 양측은 2·min", vx.boot_p([0.1] * 10) == 0.0 and vx.boot_p([-0.1] * 10) == 1.0 and vx.boot_p([-0.1] * 10, two_sided=True) == 0.0)
ms = [dict(month=f"2020-{m:02d}", n=20, ic=0.1, top=0.05, bot=-0.02, uni=0.01) for m in range(1, 13)]
o = vx.orient(ms, "-")
check("방향 −: IC 부호 반전, top/bot 교환", o[0]["ic"] == -0.1 and o[0]["top"] == -0.02 and o[0]["bot"] == 0.05 and vx.orient(ms, "+")[0]["ic"] == 0.1)
check("연도별 평균(월 >= 6 만)", vx.yearly(ms) == {"2020": 0.1} and vx.yearly(ms[:5]) == {})

def months(y0, y1, ic_fn, top=0.03, uni=0.01):
    out = []
    for y in range(y0, y1 + 1):
        for m in range(1, 13):
            out.append(dict(month=f"{y}-{m:02d}", n=30, ic=ic_fn(y, m), top=top, bot=-0.01, uni=uni))
    return out
good_tr = months(2019, 2024, lambda y, m: 0.08 + 0.02 * ((y + m) % 3))
good_oo = [dict(month=f"2025-{m:02d}", n=30, ic=0.1, top=0.02, bot=-0.01, uni=0.005) for m in range(1, 13)]
r = vx.judge_var("mom_1m", "+", good_tr, good_oo); r["p_holm"] = r["train_p"]; vx.finalize(r)
check("판정: train·OOS 전부 통과 → CONFIRMED", r["verdict"] == "CONFIRMED" and r["train_ok"] and r["oos_ok"] and r["dir"] == "+")
r2 = vx.judge_var("rvol20", "-", vx.orient(good_tr, "-"), vx.orient(good_oo, "-")); r2["p_holm"] = r2["train_p"]; vx.finalize(r2)
check("'-' 변수: 원자료 IC 음수여도 정렬 후 양수 → CONFIRMED", r2["train_ic"] > 0 and r2["verdict"] == "CONFIRMED")
neg_tr = [dict(m, ic=-m["ic"], top=m["bot"], bot=m["top"]) for m in good_tr]
neg_oo = [dict(m, ic=-m["ic"], top=m["bot"], bot=m["top"]) for m in good_oo]
r3 = vx.judge_var("dist_ma60", "?", neg_tr, neg_oo); r3["p_holm"] = r3["train_p"]; vx.finalize(r3)
check("'?' 변수: train 부호(−)를 방향으로 잡고 OOS 도 그 부호로 → CONFIRMED, 양측 p", r3["dir"] == "-" and r3["verdict"] == "CONFIRMED" and r3["train_p"] == r3["train_p_two"])
r4 = vx.judge_var("mom_1m", "+", neg_tr, neg_oo); r4["p_holm"] = r4["train_p"]; vx.finalize(r4)
check("부호 지정 변수가 반대로 유의 → REJECTED + REVERSED 표기(승격 없음)", r4["verdict"] == "REJECTED" and r4["reversed"] and r4["train_p"] > 0.5)
r5 = vx.judge_var("mom_1m", "+", good_tr, [dict(m, top=0.003) for m in good_oo]); r5["p_holm"] = r5["train_p"]; vx.finalize(r5)
check("OOS TOP 절대수익 − 0.4% <= 0 → TRAIN_ONLY", r5["verdict"] == "TRAIN_ONLY" and r5["train_ok"] and not r5["oos_ok"])
r6 = vx.judge_var("mom_1m", "+", good_tr, good_oo[:9]); r6["p_holm"] = r6["train_p"]; vx.finalize(r6)
check("OOS 월 < 10 → TRAIN_ONLY", r6["verdict"] == "TRAIN_ONLY")
r7 = vx.judge_var("mom_1m", "+", good_tr[:20], good_oo); r7["p_holm"] = r7["train_p"]; vx.finalize(r7)
check("train 월 < 24 → REJECTED", r7["verdict"] == "REJECTED")
one_year = months(2019, 2024, lambda y, m: 1.0 if y == 2021 else -0.02)
r8 = vx.judge_var("mom_1m", "+", one_year, good_oo); r8["p_holm"] = r8["train_p"]; vx.finalize(r8)
check("단일 해 의존(최고 연도 제외 평균 < 0, 연도 양수 1/6) → REJECTED", r8["verdict"] == "REJECTED" and r8["lbyo_ic"] < 0 and r8["year_pos_share"] < 0.6 and r8["best_year"] == "2021")
r9 = vx.judge_var("mom_1m", "+", good_tr, good_oo); r9["p_holm"] = 0.2; vx.finalize(r9)
check("Holm 보정 p >= .05 → REJECTED (원 p 는 통과여도)", r9["verdict"] == "REJECTED" and r9["train_p"] < 0.05)
fam = vx.judge_family({"mom_1m": (good_tr, good_oo), "mom_3m": (neg_tr, neg_oo), "dist_ma60": (neg_tr, neg_oo)})
check("가족 판정: Holm 은 g4.holm, 결과 dict 에 판정·p_holm", set(fam) == {"mom_1m", "mom_3m", "dist_ma60"} and fam["mom_1m"]["verdict"] == "CONFIRMED" and fam["mom_3m"]["reversed"]
      and fam["mom_1m"]["p_holm"] == g4.holm({k: v["train_p"] for k, v in fam.items()})["mom_1m"])

# ── 4. 패널 — PIT 적격·다음 달 적용·레짐·코호트 ─────────────────────────────────────────
rng = random.Random(7)
def rw(n, start, v):
    cl = [100.0]
    for _ in range(n - 1):
        cl.append(cl[-1] * (1 + rng.uniform(-0.03, 0.03)))
    return mk(cl, start, vols=[v] * n)
rows = {"BTC": rw(400, "2023-01-01", 1000), "A": rw(400, "2023-01-01", 500), "B": rw(400, "2023-01-01", 200), "C": rw(50, "2024-01-01", 9999)}
pm = pc.pit_membership(rows)
regmap = {r["date"]: ("bull_btc" if r["date"] < "2023-09-01" else "bear") for r in rows["BTC"]}
panel = vx.build_panel(rows, pm, regmap)
check("패널: 이력 60봉 미달 C 없음, 첫 두 달(적격 전) 없음", all(p["sym"] != "C" for p in panel) and min(p["month"] for p in panel) == "2023-03")
p0 = next(p for p in panel if p["sym"] == "A" and p["month"] == "2023-06")
check("형성 봉 = 달의 마지막 봉, 순위 = 다음 달 적용분(pm['2023-07']), 레짐 = 형성일 라벨", p0["date"] == "2023-06-30" and p0["rank"] == pm["2023-07"]["A"] and p0["regime"] == "bull_btc")
check("레짐 필터·코호트 필터가 월 통계에 반영, MIN_CS 미달 달 제외", vx.month_stats(panel, "mom_1m", min_cs=3) and not vx.month_stats(panel, "mom_1m", min_cs=15)
      and all(m["month"] < "2023-09" for m in vx.month_stats(panel, "mom_1m", regime="bull_btc", min_cs=3)))
ms_all = vx.month_stats(panel, "mom_1m", min_cs=3)
tr, oo = vx.split(ms_all)
check("분할: train < 2025-01 <= OOS", all(m["month"] < "2025-01" for m in tr) and all(m["month"] >= "2025-01" for m in oo))
check("합성 IC: 변수 없으면 None", vx.composite_ic(panel, []) is None)

# ── 5. 무변경·등재 ────────────────────────────────────────────────────────────────────────
for fn in ("validate_xsec_chars.py", "xsec_features.py"):
    src = open(fn, encoding="utf-8").read()
    check(f"{fn}: 실거래·배포 코드 없음", "import paper_executor" not in src and "import scheduler" not in src and "adopted_" not in src and "ROUTING_OVERRIDES" not in src)
sched = open("scheduler.py", encoding="utf-8").read() + open("paper_executor.py", encoding="utf-8").read()
check("스케줄러·실행기가 xsec 모듈을 읽지 않음", "xsec_features" not in sched and "validate_xsec_chars" not in sched)
wf = open(".github/workflows/xsec_chars.yml", encoding="utf-8").read()
check("워크플로 등재 + 테스트 선행", "python validate_xsec_chars.py" in wf and "python test_xsec_chars.py" in wf)
check("tests.yml 등재", "test_xsec_chars.py" in open(".github/workflows/tests.yml", encoding="utf-8").read())

print(f"\n{'ALL PASS' if not fails else 'FAILED: ' + ', '.join(fails)} ({len(fails)} fail)")
import sys; sys.exit(1 if fails else 0)
