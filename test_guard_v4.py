"""validate_guard_v4 고정 — 동결 파라미터(사용자 확정 2026-09-06)·B 풀 매칭 규칙·클러스터 부트·Holm·판정 규칙·실거래 무변경.
실행: python test_guard_v4.py"""
import random
import statistics as st
from datetime import date, timedelta

import validate_guard_v4 as g

fails = []
def check(n, c, d=""):
    print(("PASS " if c else "FAIL ") + n + ("" if c else f" — {d}")); c or fails.append(n)


# ── 1. 동결 파라미터 ──────────────────────────────────────────────────────────────────────
check("분할일 2025-01-01 고정", g.SPLIT_DATE == "2025-01-01")
check("비용 스트레스 0.4/0.6, 필수 0.4, 기본 0.2 왕복", g.STRESS_FEES == (0.004, 0.006) and g.STRESS_REQUIRED == 0.004 and abs(g.FEE_BASE - 0.002) < 1e-12)
check("엣지 여유 +0.20%p · 부트 1000 · α .05 · OOS n>=10 · B 풀>=5 · B 월>=3 · 창 ±10", g.EDGE_MARGIN == 0.002 and g.BOOT_N == 1000 and g.ALPHA == 0.05
      and g.OOS_MIN_N == 10 and g.B_MIN_POOL == 5 and g.B_MIN_MONTHS == 3 and g.WINDOW_BARS == 10)
check("통과해도 실거래 반영 없음", g.DEPLOY_ON_PASS is False)
check("주 판정 가족 11셀 — 배포 7 / 관찰 2 / 그림자 2", len(g.CELLS) == 11 and sum(c["status"] == "deployed" for c in g.CELLS) == 7
      and sum(c["status"] == "observation" for c in g.CELLS) == 2 and sum(c["status"] == "shadow" for c in g.CELLS) == 2)
check("그림자 셀 = double_bottom_1d·inverse_hs_1d bull_btc", {c["cid"] for c in g.CELLS if c["status"] == "shadow"} == {"double_bottom_1d|bull_btc", "inverse_hs_1d|bull_btc"})
check("실거래 코호트 복제: engulfing/fvg top30, three_soldiers all, ih/marubozu majors", all(c["cohort"] == "top30" for c in g.CELLS if c["pattern"] in ("engulfing", "engulfing_short", "fvg"))
      and all(c["cohort"] == "all" for c in g.CELLS if c["pattern"] == "three_soldiers_4h") and all(c["cohort"] == "majors" for c in g.CELLS if c["pattern"] in ("inverted_hammer", "marubozu")))
check("라우팅 복제: bull_altseason engulfing 은 숏, bear fvg 없음(FLAT), sideways 없음",
      any(c["cid"] == "engulfing_short|bull_altseason" and c["direction"] == "short" for c in g.CELLS)
      and not any(c["pattern"] == "fvg" and c["regime"] == "bear" for c in g.CELLS) and not any(c["regime"] == "sideways" for c in g.CELLS))
check("청산은 방식D 30봉 (validate_revival.live_outcome 공유)", g.MAX_HOLD == 30)

# ── 2. 합성 데이터: B 풀 매칭 ────────────────────────────────────────────────────────────
def mkrows(n, start="2024-10-01", seed=1, drift=0.0):
    rng = random.Random(seed); d0 = date.fromisoformat(start); rows = []; px = 100.0
    for i in range(n):
        o = px; c = o * (1 + drift + rng.uniform(-0.02, 0.02)); h = max(o, c) * 1.01; l = min(o, c) * 0.99
        rows.append(dict(date=(d0 + timedelta(days=i)).isoformat(), ts=int((d0 + timedelta(days=i)).strftime("%s")) * 1000 if False else None, o=o, h=h, l=l, c=c, v=1000.0)); px = c
    return rows

rows = mkrows(200)
regmap = {r["date"]: ("bull_btc" if r["date"] < "2025-01-15" else "bear") for r in rows}
oc = g.Outcomes("1d", {"X": rows}, regmap, "long")
check("진입 가능 봉: i<30 불가, 끝 31봉 불가", not oc.eligible("X", 29) and oc.eligible("X", 30) and oc.eligible("X", 200 - 32) and not oc.eligible("X", 200 - 31))
i_sig = 100                      # 2025-01-09 (bull_btc, 1월)
pj = g.bench_pool(oc, "X", i_sig)
ds = [rows[j]["date"] for j in pj]
check("B 풀: 같은 달·같은 레짐·신호봉 제외", i_sig not in pj and all(d[:7] == "2025-01" for d in ds) and all(regmap[d] == "bull_btc" for d in ds) and len(pj) == 13)
i_sig2 = 110                     # 2025-01-19 (bear, 1월) — 같은 달이지만 레짐이 달라 풀이 다름
pj2 = g.bench_pool(oc, "X", i_sig2)
check("B 풀: 같은 달이라도 레짐 라벨이 다르면 다른 봉 집합", set(pj).isdisjoint(pj2) and all(regmap[rows[j]["date"]] == "bear" for j in pj2) and len(pj2) == 16)
pw = g.bench_pool(oc, "X", i_sig, mode="window")
check("±10봉 창(진단): 신호봉 제외 20봉, 월·레짐 무관", len(pw) == 20 and i_sig not in pw and min(pw) == 90 and max(pw) == 110)
check("풀 캐시: 신호와 벤치가 같은 함수 결과", oc.ret("X", 95) == g.vr.live_outcome("1d", rows, 95, "long", lambda j: regmap.get(rows[j]["date"]), None)[0])
sigs = [dict(sym="X", i=i_sig, date=rows[i_sig]["date"], month="2025-01", ret=oc.ret("X", i_sig)),
        dict(sym="X", i=31, date=rows[31]["date"], month=rows[31]["date"][:7], ret=oc.ret("X", 31))]
eb, ex = g.b_edges(oc, sigs)
check("b_edges: edge = 신호 수익 − 풀 평균, 풀 부족 신호는 제외 집계", len(eb) + ex == 2 and all(abs(e["edge"] - (e["ret"] - e["bench"])) < 1e-12 for e in eb))
# 풀 <5 → 제외: 월 첫날 1봉만 남는 경우 — 2024-11-01 신호(i=31)는 같은 달 29봉이라 포함. 인위적으로 min_pool 을 올려 제외 확인
eb2, ex2 = g.b_edges(oc, sigs, min_pool=100)
check("min_pool 초과 시 전부 제외", not eb2 and ex2 == 2)

# ── 3. 클러스터 부트스트랩·가중 ───────────────────────────────────────────────────────────
edges_pos = [dict(sym=f"C{k%5}", month=f"2024-{1+k%6:02d}", edge=0.01 + 0.001 * (k % 7)) for k in range(60)]
cb = g.cluster_boot(edges_pos, n_boot=200)
check("전부 양수 엣지 → 세 가중 >0, 월/코인월 p = 0", cb["nw"] > 0 and cb["eq_month"] > 0 and cb["eq_coin_month"] > 0 and cb["p_nw"] == 0 and cb["p_nw_coinmonth"] == 0 and cb["months"] == 6 and cb["coin_months"] == 30)
edges_neg = [dict(e, edge=-e["edge"]) for e in edges_pos]
cbn = g.cluster_boot(edges_neg, n_boot=200)
check("전부 음수 → p = 1, b_ok False", cbn["p_nw"] == 1.0 and not g.b_ok(cbn))
# n 가중 vs 동등 월: 큰 달이 음수, 작은 달들이 양수
mixed = [dict(sym="C", month="2024-01", edge=-0.01) for _ in range(50)] + [dict(sym="C", month=f"2024-{m:02d}", edge=0.02) for m in range(2, 7)]
cbm = g.cluster_boot(mixed, n_boot=200)
check("가중 방식이 부호를 가른다: n가중 음수, 동등월 양수 → b_ok False", cbm["nw"] < 0 and cbm["eq_month"] > 0 and not g.b_ok(cbm))
check("동등 코인-월 가중: 코인별 평균 후 평균", abs(g._three_means([[("A", 0.1), ("A", 0.1), ("B", -0.1)]])[2] - 0.0) < 1e-12)
check("빈 입력 안전", g.cluster_boot([])["nw"] is None and g.cluster_boot([])["months"] == 0)

# ── 4. Holm ──────────────────────────────────────────────────────────────────────────────
adj = g.holm({"a": 0.01, "b": 0.04, "c": 0.03})
check("Holm 단계적: .01→.03, .03→.06, .04→.06", abs(adj["a"] - 0.03) < 1e-12 and abs(adj["c"] - 0.06) < 1e-12 and abs(adj["b"] - 0.06) < 1e-12)
check("Holm 단조·상한 1", g.holm({"a": 0.5, "b": 0.9})["b"] == 1.0 and g.holm({}) == {})

# ── 5. 비용 스트레스 산술 ─────────────────────────────────────────────────────────────────
check("mean_at_fee: 0.2%→0.4% 는 −0.2%p, 0.6% 는 −0.4%p", abs(g.mean_at_fee(0.01, 0.004) - 0.008) < 1e-12 and abs(g.mean_at_fee(0.01, 0.006) - 0.006) < 1e-12 and g.mean_at_fee(None, 0.004) is None)

# ── 6. 판정 규칙 ─────────────────────────────────────────────────────────────────────────
okA = dict(n=40, mean=0.02, win=0.5, boot_p=0.01, base_mean=0.0, edge=0.02, pool_n=100)
okB = dict(n=40, months=8, coin_months=20, nw=0.01, eq_month=0.01, eq_coin_month=0.01, p_nw=0.01, p_eq_month=0.01, p_eq_coin_month=0.01, p_nw_coinmonth=0.01, ci_nw=(0.0, 0.02))
v, f = g.verdict(okA, True, okB, okA, okB, 0.02, 0.02)
check("전부 통과 → CONFIRMED", v == "CONFIRMED" and not f)
v, f = g.verdict(dict(okA, mean=-0.01), True, okB, okA, okB, 0.02, 0.02)
check("전체 A 평균 음수 → REJECTED", v == "REJECTED")
v, f = g.verdict(dict(okA, win=0.3), True, okB, okA, okB, 0.02, 0.02)
check("전체 A 승률 <35% → REJECTED", v == "REJECTED")
v, f = g.verdict(okA, False, okB, okA, okB, 0.02, 0.02)
check("train 게이트 실패 → UNCONFIRMED_SHADOW (영구 기각 아님)", v == "UNCONFIRMED_SHADOW" and "train A gate" in f)
v, f = g.verdict(okA, True, okB, dict(okA, n=9), okB, 0.02, 0.02)
check("OOS n<10 → INCONCLUSIVE", v == "INCONCLUSIVE")
v, f = g.verdict(okA, True, okB, okA, dict(okB, months=2), 0.02, 0.02)
check("OOS B 월<3 → INCONCLUSIVE", v == "INCONCLUSIVE")
v, f = g.verdict(okA, True, okB, okA, okB, 0.08, 0.02)
check("Holm p >= .05 → OOS B 실패 → SHADOW", v == "UNCONFIRMED_SHADOW" and "OOS B" in f)
v, f = g.verdict(okA, True, okB, okA, dict(okB, nw=0.001), 0.02, 0.02)
check("OOS B 엣지 < +0.20%p → 실패 (비용 여유)", v == "UNCONFIRMED_SHADOW" and "OOS B" in f)
v, f = g.verdict(okA, True, okB, okA, dict(okB, eq_month=-0.001), 0.02, 0.02)
check("세 가중 중 하나라도 음수 → OOS B 실패", v == "UNCONFIRMED_SHADOW" and "OOS B" in f)
v, f = g.verdict(okA, True, okB, okA, okB, 0.02, 0.0015)
check("OOS 평균 +0.15% 는 0.4% 수수료에서 음수 → 비용 스트레스 실패", v == "UNCONFIRMED_SHADOW" and "OOS cost@0.4%" in f)
v, f = g.verdict(okA, True, okB, dict(okA, boot_p=0.2), okB, 0.02, 0.02)
check("OOS A boot_p >= .05 → OOS A 실패", v == "UNCONFIRMED_SHADOW" and "OOS A" in f)

# ── 7. 실거래 무변경·워크플로 ─────────────────────────────────────────────────────────────
src = open("validate_guard_v4.py", encoding="utf-8").read()
check("실거래·배포 코드 없음", "import paper_executor" not in src and "adopted_" not in src and "universe.json" not in src.replace("va._syms()", ""))
check("Supabase 는 읽기(select)만", ".insert(" not in src and ".upsert(" not in src and ".delete(" not in src)
wf = open(".github/workflows/guard_v4.yml", encoding="utf-8").read()
check("워크플로 등재 + 테스트 선행", "python validate_guard_v4.py" in wf and "python test_guard_v4.py" in wf)
check("tests.yml 등재", "test_guard_v4.py" in open(".github/workflows/tests.yml", encoding="utf-8").read())
import json
reg = json.load(open("registry.json", encoding="utf-8"))["guard_v4_prereg_draft_2026_09_06"]
fp = reg["frozen_params"]
check("registry 동결값 = 코드 상수", fp["SPLIT_DATE"] == g.SPLIT_DATE and fp["EDGE_MARGIN"] == g.EDGE_MARGIN and fp["B_MIN_POOL"] == g.B_MIN_POOL
      and fp["B_MIN_MONTHS"] == g.B_MIN_MONTHS and fp["OOS_MIN_N"] == g.OOS_MIN_N and fp["STRESS_REQUIRED"] == g.STRESS_REQUIRED and fp["BOOT_N"] == g.BOOT_N)
check("registry 주 셀 목록 = 코드 CELLS", reg["cells_primary"] == [f"{c['cid']}|{c['direction']}" for c in g.CELLS])

print(f"\n{'ALL PASS' if not fails else 'FAILED: ' + ', '.join(fails)} ({len(fails)} fail)")
import sys; sys.exit(1 if fails else 0)
