"""validate_episode_profile 고정 — 동결 파라미터·에피소드 정의·추가 변수 인과성·집단 통계·순열 p·판정 규칙·실거래 무변경.
실행: python test_episode_profile.py"""
import json
import random
from datetime import date, timedelta

import validate_episode_profile as ve
import validate_xsec_chars as vx
import xsec_features as xf

fails = []
def check(n, c, d=""):
    print(("PASS " if c else "FAIL ") + n + ("" if c else f" — {d}")); c or fails.append(n)

# ── 1. 동결 ──────────────────────────────────────────────────────────────────────────────
check("상승 라벨 2종 · 최소 60일 · 이력 120 · 코인 15 · 순열 2000 · 일관성 75%/3 에피소드 · α .05", ve.EPISODE_LABELS == ("bull_btc", "bull_altseason") and ve.EP_MIN_DAYS == 60
      and ve.MIN_HIST == 120 and ve.MIN_COINS == 15 and ve.PERM_N == 2000 and ve.CONSIST_SHARE == 0.75 and ve.CONSIST_MIN_EP == 3 and ve.ALPHA == 0.05)
check("변수 가족 35 = FAMILY 24 + EXTRA 11, 키 유일", len(ve.KEYS) == 35 and len(xf.EXTRA_KEYS) == 11 and len(set(ve.KEYS)) == 35 and ve.KEYS[:24] == xf.KEYS)
check("FAMILY(24) 동결 불변 — 추가 변수는 별도 목록", len(xf.KEYS) == 24 and all(k not in xf.KEYS for k in xf.EXTRA_KEYS))
check("배포 반영 없음", ve.DEPLOY_ON_PASS is False)
reg = json.load(open("registry.json", encoding="utf-8"))["episode_profile_prereg_2026_09_07"]
check("registry 사전 등록과 일치(가족 35·에피소드 정의·기준)", reg["family_size"] == 35 and reg["family_keys"] == ve.KEYS and "60" in reg["frame_frozen"]["episode"] and "0.75" in reg["frame_frozen"]["consistency"])

# ── 2. 에피소드 정의 ──────────────────────────────────────────────────────────────────────
def days(start, n):
    d0 = date.fromisoformat(start); return [(d0 + timedelta(days=i)).isoformat() for i in range(n)]
reg_map = {}
for d in days("2020-01-01", 100): reg_map[d] = "bear"
for d in days("2020-04-10", 80): reg_map[d] = "bull_btc"
for d in days("2020-06-29", 10): reg_map[d] = "bear"          # 10일 끊김 → 병합
for d in days("2020-07-09", 50): reg_map[d] = "bull_altseason"
for d in days("2020-08-28", 60): reg_map[d] = "bear"
for d in days("2020-10-27", 30): reg_map[d] = "bull_btc"        # 30일 < 60 → 제외
for d in days("2020-11-26", 100): reg_map[d] = "bear"
eps = ve.bull_episodes(reg_map)
check("두 상승 라벨 합집합 + 30일 이하 끊김 병합 → 하나의 에피소드, 30일짜리는 제외", len(eps) == 1 and eps[0][0] == "2020-04-10" and eps[0][1] == "2020-08-27")
check("지배 라벨 = 일수 많은 쪽(bull_btc 80 > altseason 50), 길이 140일", eps[0][2] == "bull_btc" and eps[0][3] == 140)
check("최소 길이 낮추면 2개", len(ve.bull_episodes(reg_map, min_days=20)) == 2)

# ── 3. 행 구성 — 시작 봉·결과·이력 요건 ────────────────────────────────────────────────────
def mk(closes, start):
    d0 = date.fromisoformat(start); out = []
    for i, c in enumerate(closes):
        o = closes[i - 1] if i else c
        out.append(dict(date=(d0 + timedelta(days=i)).isoformat(), ts=None, o=o, h=max(o, c) * 1.01, l=min(o, c) * 0.99, c=c, v=100.0))
    return out
rng = random.Random(5)
def rw(n, start, drift=0.0):
    cl = [100.0]
    for _ in range(n - 1): cl.append(cl[-1] * (1 + drift + rng.uniform(-0.02, 0.02)))
    return mk(cl, start)
rows_1d = {"BTC": rw(400, "2019-12-01"), "A": rw(400, "2019-12-01", 0.01), "B": rw(400, "2019-12-01", -0.005), "C": rw(60, "2020-03-01")}
eps1 = [("2020-04-10", "2020-08-27", "bull_btc", 140)]
rows = ve.build_rows(rows_1d, eps1)
syms = {r["sym"] for r in rows}
check("이력 120봉 미달 C 제외, 나머지 포함", "C" not in syms and {"BTC", "A", "B"} <= syms)
ra = next(r for r in rows if r["sym"] == "A")
i0 = next(k for k, r in enumerate(rows_1d["A"]) if r["date"] == "2020-04-10"); i1 = next(k for k, r in enumerate(rows_1d["A"]) if r["date"] == "2020-08-27")
c = [r["c"] for r in rows_1d["A"]]
check("ret_ep = close(t1)/close(t0) − 1, mfe = 구간 최고 종가", abs(ra["ret"] - (c[i1] / c[i0] - 1)) < 1e-12 and abs(ra["mfe"] - (max(c[i0 + 1:i1 + 1]) / c[i0] - 1)) < 1e-12)
check("피처 35 종 전부 키 존재, 상승 코인 A 의 dist_ma60 > 0", set(ra["f"]) == set(ve.KEYS) and ra["f"]["dist_ma60"] > 0)

# 추가 변수 인과성 + 정의
base = rw(400, "2023-01-01"); fs0 = xf.FeatureSeries(base, base); i = 320
f0 = xf.extra_at(fs0, i)
alt = [dict(r) for r in base]
for r in alt[i + 1:]: r["c"] *= 3; r["h"] *= 3; r["l"] *= 3
f1 = xf.extra_at(xf.FeatureSeries(alt, alt), i)
check("추가 변수 11 종 인과성: 미래 봉 변경에 불변", all((f0[k] is None and f1[k] is None) or (f0[k] is not None and f1[k] is not None and abs(f0[k] - f1[k]) < 1e-12) for k in xf.EXTRA_KEYS), str([k for k in xf.EXTRA_KEYS if f0[k] != f1[k]]))
up = mk([100 * 1.01 ** k for k in range(400)], "2023-01-01"); fsu = xf.FeatureSeries(up, up); fu = xf.extra_at(fsu, 399)
check("상승 추세: %B 상단 근처(>0.8), ATH 낙폭 0, ATH 경과 0, up_days 1.0, MA180 위 연속 120 상한", fu["bb_pctb"] > 0.8 and abs(fu["ath_dd"]) < 1e-12 and fu["days_since_ath"] == 0 and fu["up_days_20"] == 1.0 and fu["days_above_ma180"] == 120)
dn = mk([100 * 0.99 ** k for k in range(400)], "2023-01-01"); fd = xf.extra_at(xf.FeatureSeries(dn, up), 399)
check("하락 추세: %B 하단(<0.2), ATH 낙폭 < 0, 경과 399, MA180 아래 −120, max_dd_1y < 0", fd["bb_pctb"] < 0.2 and fd["ath_dd"] < 0 and fd["days_since_ath"] == 399 and fd["days_above_ma180"] == -120 and fd["max_dd_1y"] < 0)
check("age_bars = i+1, 자기 자신 BTC 상관 = 1, ADX 는 추세에서 높음(>25)", fu["age_bars"] == 400 and abs(fu["corr_btc_60"] - 1) < 1e-9 and fu["adx14"] > 25)
flat = mk([100 + (k % 2) * 0.5 for k in range(300)] + [100 + (k % 2) * 30 for k in range(100)], "2023-01-01"); ff = xf.extra_at(xf.FeatureSeries(flat), 399)
check("볼밴 폭이 최근 120봉 최소 대비 커지면 squeeze > 1", ff["bb_squeeze"] is not None and ff["bb_squeeze"] > 1)
check("이력 부족 None: squeeze(139봉 미만)·max_dd(252 미만)", xf.extra_at(fsu, 100)["bb_squeeze"] is None and xf.extra_at(fsu, 200)["max_dd_1y"] is None)

# ── 4. 통계 ──────────────────────────────────────────────────────────────────────────────
check("rank-biserial: 전부 큼 +1 / 전부 작음 −1 / 동일 0", ve.rank_biserial([3, 4], [1, 2]) == 1 and ve.rank_biserial([1, 2], [3, 4]) == -1 and ve.rank_biserial([1, 1], [1, 1]) == 0)
def synth_rows(n_ep, n_coin, slope, seed=0):
    r = random.Random(seed); out = []
    for ep in range(n_ep):
        for k in range(n_coin):
            f = r.uniform(0, 1)
            out.append(dict(ep=ep, sym=f"c{k}", ret=slope * f + r.uniform(-0.05, 0.05), mfe=0.0, f={"dist_ma60": f}))
    return out
pos = synth_rows(4, 30, 1.0)
es = ve.episode_stats(pos, "dist_ma60")
check("에피소드별 통계: 4개, 강한 양의 rho, winners 중앙값 > laggards, rb > 0", len(es) == 4 and all(v["rho"] > 0.9 and v["win_med"] > v["lag_med"] and v["rb"] > 0.8 for v in es.values()))
check("코인 < 15 인 에피소드 제외", ve.episode_stats(synth_rows(2, 10, 1.0), "dist_ma60") == {})
po = ve.pooled(pos, "dist_ma60")
check("풀 스피어만 > 0.9, 순열 p_pos 0, p_neg 1", po["rho"] > 0.9 and po["p_pos"] == 0.0 and po["p_neg"] == 1.0 and po["n"] == 120 and po["eps"] == 4)
null = synth_rows(4, 30, 0.0, seed=3)
pn = ve.pooled(null, "dist_ma60")
check("무관 자료: 양측 p 큼(>.05)", pn["p_two"] > 0.05)
rec = ve.judge_var("dist_ma60", "?", es, po); rec["p_holm"] = rec["p"]; ve.finalize(rec)
check("'?' 변수: 방향 = 풀 부호(+), 양측 p, 4/4 일관 → PROFILE", rec["dir"] == "+" and rec["p"] == po["p_two"] and rec["ep_share"] == 1.0 and rec["verdict"] == "PROFILE")
neg = [dict(r, ret=-r["ret"]) for r in pos]
es2 = ve.episode_stats(neg, "dist_ma60"); po2 = ve.pooled(neg, "dist_ma60")
rec2 = ve.judge_var("dist_ma60", "+", es2, po2); rec2["p_holm"] = rec2["p"]; ve.finalize(rec2)
check("지정 부호 + 인데 반대로 유의 → NONE + REVERSED", rec2["verdict"] == "NONE" and rec2["reversed"] and rec2["p"] == po2["p_pos"])
mixed = synth_rows(3, 30, 1.0) + [dict(r, ep=3) for r in synth_rows(1, 60, -0.3, seed=9)]
es3 = ve.episode_stats(mixed, "dist_ma60"); po3 = ve.pooled(mixed, "dist_ma60")
rec3 = ve.judge_var("dist_ma60", "?", es3, po3); rec3["p_holm"] = rec3["p"]; ve.finalize(rec3)
check("3/4 에피소드 양수 → 일관 75% 통과(PROFILE)", rec3["ep_share"] == 0.75 and rec3["verdict"] == "PROFILE")
mixed2 = synth_rows(2, 30, 1.0) + [dict(r, ep=2 + r["ep"]) for r in synth_rows(2, 30, -0.4, seed=11)]
es4 = ve.episode_stats(mixed2, "dist_ma60"); po4 = ve.pooled(mixed2, "dist_ma60")
rec4 = ve.judge_var("dist_ma60", "?", es4, po4); rec4["p_holm"] = rec4["p"]; ve.finalize(rec4)
check("2/4 만 같은 부호 → 유의해도 EPISODE_DEPENDENT 또는 NONE(일관성 미달)", rec4["ep_share"] == 0.5 and rec4["verdict"] in ("EPISODE_DEPENDENT", "NONE") and not rec4["consistent"])
rec5 = ve.judge_var("dist_ma60", "?", es, po); rec5["p_holm"] = 0.2; ve.finalize(rec5)
check("Holm p >= .05 → NONE", rec5["verdict"] == "NONE")
recs, _ = ve.judge_family(pos, keys=["dist_ma60"])
check("가족 판정 함수: Holm 채움 + 판정", recs["dist_ma60"]["p_holm"] is not None and recs["dist_ma60"]["verdict"] == "PROFILE")
d2 = ve.norise_rb(pos, "dist_ma60")
check("D2 미상승 vs 상승 rank-biserial > 0 (양의 기울기 자료)", d2["rb"] > 0.5 and d2["n_norise"] + d2["n_rise"] == 120)

# ── 5. 무변경·등재 ────────────────────────────────────────────────────────────────────────
src = open("validate_episode_profile.py", encoding="utf-8").read()
check("실거래·배포 코드 없음", "import paper_executor" not in src and "import scheduler" not in src and "adopted_" not in src)
sched = open("scheduler.py", encoding="utf-8").read() + open("paper_executor.py", encoding="utf-8").read()
check("스케줄러·실행기가 episode 모듈을 읽지 않음", "validate_episode_profile" not in sched and "xsec_features" not in sched)
wf = open(".github/workflows/episode_profile.yml", encoding="utf-8").read()
check("워크플로: data-long 브랜치 체크아웃 + 테스트 선행 + 실행", "data-long" in wf and "python test_episode_profile.py" in wf and "python validate_episode_profile.py" in wf)
check("tests.yml 등재", "test_episode_profile.py" in open(".github/workflows/tests.yml", encoding="utf-8").read())

print(f"\n{'ALL PASS' if not fails else 'FAILED: ' + ', '.join(fails)} ({len(fails)} fail)")
import sys; sys.exit(1 if fails else 0)
