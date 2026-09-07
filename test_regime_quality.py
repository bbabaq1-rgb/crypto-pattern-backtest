"""
regime_alt / regime_quality / method_q 로직 검증 (합성 데이터, 네트워크 없음).

  - 추가 신호: breadth 비율·임계, vol 백분위(저/고), funding 백분위(hot/cold) — 룩어헤드 없음
  - 라벨러: current 는 rs.build_regime_map 과 동일, funding_cap 은 hot 에서만 bull→sideways,
    vol_side 는 low&side 에서만 sideways, breadth_only 는 히스테리시스 없음, vote4 는 4표 중 3표
  - 벤치마크: 선행수익·진실 전환·지연·분리폭·적중률·flips, beats_current 4조건
  - method_q: D arm 이 method_m.outcome 과 동일, F arm 은 막힌 거래 ret 0, 1단계 미통과는 adopt=False
  - e2e: 합성 CSV 위에서 regime_quality.main / method_q.main 이 끝까지 돌고 JSON 을 쓴다
실행: python test_regime_quality.py
"""
import csv
import json
import os
import random
import sys
import tempfile
from datetime import date, timedelta

import detlib
import regime_switch as rs
import regime_alt as ra
import regime_quality as rq
import method_q as mq
import method_m as mm

fails = []


def check(n, c, d=""):
    print(("PASS " if c else "FAIL ") + n + ("" if c else f" — {d}"))
    c or fails.append(n)


def rows_of(n, seed, drift=0.0, start=date(2021, 1, 1), vol=0.02, gaps=False):
    random.seed(seed)
    px, out = 100.0, []
    for i in range(n):
        o = px * (1 + random.gauss(0, 0.004)) if gaps else px
        nx = px * (1 + drift + random.gauss(0, vol))
        d = start + timedelta(days=i)
        out.append(dict(ts=int((d - date(1970, 1, 1)).total_seconds() * 1000), date=d.isoformat(),
                        o=o, h=max(o, nx) * (1 + abs(random.gauss(0, 0.006))), l=min(o, nx) * (1 - abs(random.gauss(0, 0.006))),
                        c=nx, v=1000.0 * (1 + abs(random.gauss(0, 0.8)) if gaps else 1)))
        px = nx
    return out


# BTC.D 네트워크 차단
rs._load_btcd_cache = lambda allow_stale=False: {}
rs._fetch_btcd_from_cg = lambda: None
ra.BREADTH_MIN_N = 3

# 1. breadth
up = rows_of(300, 1, drift=0.01)          # 강한 상승 → 200MA 위
dn = rows_of(300, 2, drift=-0.01)
br = ra.breadth_series({"A": up, "B": up, "C": up, "D": dn})
last = up[-1]["date"]
check("breadth: 4종목 중 3 상승 → 0.75", abs(br[last][0] - 0.75) < 1e-9 and br[last][1] == 4, str(br.get(last)))
check("breadth: 200봉 미만 날짜는 분모 없음", up[100]["date"] not in br)
sig = ra.breadth_signal(br)
check("breadth_signal: 0.75 → up", sig[last] == "up")
check("breadth_signal: min_n 미만 제외", ra.breadth_signal(br, min_n=5) == {})

# 2. vol / funding 백분위
calm = rows_of(500, 3, vol=0.005) + []
wild = rows_of(500, 3, vol=0.005)
# 뒤 60일만 변동성 4배
random.seed(9)
px = wild[-61]["c"]
for i in range(len(wild) - 60, len(wild)):
    nx = px * (1 + random.gauss(0, 0.04)); wild[i]["c"] = nx; wild[i]["o"] = px; px = nx
vs = ra.vol_state(wild)
check("vol_state: 변동성 급등 구간 끝 → high", vs[wild[-1]["date"]] == "high", vs.get(wild[-1]["date"]))
check("vol_state: 초반 365일 미만은 없음", wild[100]["date"] not in vs)
dates = [r["date"] for r in wild]
fund = {d: 0.0001 for d in dates}
for d in dates[-40:]:
    fund[d] = 0.002                                 # 마지막 40일 과열
fs = ra.funding_state(fund, dates)
check("funding_state: 과열 구간 → hot", fs[dates[-1]] == "hot", fs.get(dates[-1]))
check("funding_state: 평상 구간 → mid", fs[dates[-100]] == "mid", fs.get(dates[-100]))

# 3. 라벨러 (현행과의 관계)
btc = rows_of(900, 11, drift=0.001); eth = rows_of(900, 12, drift=0.0005)
alts = {a: rows_of(900, 20 + k, drift=0.0005) for k, a in enumerate(rs.ALTS)}
uni = {**alts, "BTC": btc, "ETH": eth}
cur_direct = ra._vote(*ra.base_signals(btc, eth, alts))
labs, sigs = ra.build_all(btc, eth, alts, uni, fund_daily=fund, current=cur_direct)
check("라벨러 전종 생성", set(labs) == set(ra.LABELERS), str(set(labs)))
check("current 는 넘긴 맵 그대로", labs["current"] == cur_direct)
check("모든 라벨이 4레짐 안", all(v in rs.REGIMES for m in labs.values() for v in m.values()))
diff_fc = {d for d in labs["current"] if labs["funding_cap"][d] != labs["current"][d]}
fst = ra.funding_state(fund, sorted(labs["current"]))
check("funding_cap: 바뀐 날은 전부 hot 이고 bull→sideways",
      all(fst.get(d) == "hot" and labs["current"][d] in ra.BULL if hasattr(ra, "BULL") else True for d in diff_fc)
      and all(labs["funding_cap"][d] == "sideways" for d in diff_fc))
diff_vs = {d for d in labs["current"] if labs["vol_side"][d] != labs["current"][d]}
check("vol_side: 바뀐 날은 전부 vol low & breadth side",
      all(sigs["vol"].get(d) == "low" and sigs["breadth"].get(d) == "side" for d in diff_vs))
check("breadth_price/breadth_only 는 breadth 있는 날만", set(labs["breadth_only"]) <= set(sigs["breadth"]))
# vote4: 전환에 3표 필요 → 뒤집힘이 current 이하
def flips(m):
    ds = sorted(m); return sum(1 for a, b in zip(ds, ds[1:]) if m[a] != m[b])
check("vote4: 뒤집힘 <= current (합의 강화)", flips(labs["vote4"]) <= flips(labs["current"]),
      f"{flips(labs['vote4'])} vs {flips(labs['current'])}")
check("breadth_only: 뒤집힘 >= breadth_price (히스테리시스 없음)",
      flips(labs["breadth_only"]) >= flips(labs["breadth_price"]))
# fast_slope 는 rs.SLOPE_LB 를 복원한다
check("fast_slope: rs.SLOPE_LB 복원", rs.SLOPE_LB == 20)

# 3b. alt_side / wide_side (2026-09-07 사용자 정의, 사전 등록 regime_altside_prereg_2026_09_07)
check("동결: SIDE_THR 0.01 · 후보 2종 등재", ra.SIDE_THR == 0.01
      and {"wide_side", "alt_side"} <= set(ra.LABELERS))
_reg = json.load(open("registry.json", encoding="utf-8"))["regime_altside_prereg_2026_09_07"]
check("registry 사전 등록과 일치(띠 0.01·주 판정 alt_side)",
      "0.01" in _reg["frozen_params"]["SIDE_THR"] and "alt_side" in _reg["judgement_frozen"]["primary_cell"])
check("base_signals(slope_thr=): rs.SLOPE_THR 복원", rs.SLOPE_THR == 0.001)
_pn, _, _ = ra.base_signals(btc, eth, alts)
_pw, _, _ = ra.base_signals(btc, eth, alts, slope_thr=ra.SIDE_THR)
check("넓힌 띠: side 날이 늘고 up/down 은 줄어든다",
      sum(1 for v in _pw.values() if v == "side") > sum(1 for v in _pn.values() if v == "side")
      and set(_pw) == set(_pn))
check("넓힌 띠: 좁은 띠의 side 는 전부 넓은 띠에서도 side",
      all(_pw[d] == "side" for d, v in _pn.items() if v == "side"))
# 후보 규칙
check("_candidate_altside: down→bear, up 은 현행과 동일",
      ra._candidate_altside("down", "up", "down") == "bear"
      and all(ra._candidate_altside("up", e, m) == ra._candidate("up", e, m)
              for e in ("up", "down", "side") for m in ("up", "down", "side")))
check("_candidate_altside: 횡보+도미넌스 하락 → bull_altseason (사용자 정의)",
      ra._candidate_altside("side", "side", "down") == "bull_altseason"
      and ra._candidate_altside("side", "up", "down") == "bull_altseason")
check("_candidate_altside: 횡보+도미넌스 상승/중립 → sideways",
      ra._candidate_altside("side", "side", "up") == "sideways"
      and ra._candidate_altside("side", "side", "side") == "sideways"
      and ra._candidate_altside("side", "down", "down") == "sideways")
# 지지 규칙
check("_support_altside: 횡보 알트불장은 가격을 +1 로 (2표 가능)",
      ra._support_altside("bull_altseason", "side", "side", "down") == 2
      and ra._support_altside("bull_altseason", "side", "up", "down") == 3)
check("_support_altside: 그 외는 현행과 동일",
      all(ra._support_altside(c, p, e, m) == rs._signal_support(c, p, e, m)
          for c in ("bear", "sideways", "bull_btc") for p in ("up", "down", "side")
          for e in ("up", "down", "side") for m in ("up", "down", "side")))
# _vote 기본 동작 불변
check("_vote: cand_fn/sup_fn 미지정 시 종전과 동일", ra._vote(_pn, sigs["ethbtc"], sigs["dom"]) == labs["current"])
# 라벨 관계
_alt, _wide = labs["alt_side"], labs["wide_side"]
# 주의: 넓힌 띠만으로 sideways 가 발화하지는 않는다 — 히스테리시스가 'sideways' 후보에 2표를 요구하고
# eb/dom 이 'side' 인 날이 드물기 때문(현행 sideways 0일과 같은 구조적 이유). 규칙이 보장하는 것만 고정한다.
check("alt_side: 넓은 띠 횡보날을 bull_btc 로 부르지 않는다(사용자 정의의 핵심)",
      all(_alt[d] != "bull_btc" for d in _alt if _pw.get(d) == "side"
          and ra._candidate_altside(_pw[d], sigs["ethbtc"].get(d, "side"), sigs["dom"].get(d, "side")) != "bull_btc"
          and ra._support_altside(ra._candidate_altside(_pw[d], sigs["ethbtc"].get(d, "side"), sigs["dom"].get(d, "side")),
                                  _pw[d], sigs["ethbtc"].get(d, "side"), sigs["dom"].get(d, "side")) >= 2))
check("alt_side: 횡보+도미넌스 하락(eb 하락 아님) 날은 반드시 bull_altseason — 히스테리시스 통과",
      all(_alt[d] == "bull_altseason" for d in _alt
          if _pw.get(d) == "side" and sigs["dom"].get(d, "side") == "down"
          and sigs["ethbtc"].get(d, "side") != "down"))
check("alt_side: 현행과 다른 날은 전부 넓은 띠 기준으로 up 이 아니다",
      all(_pw.get(d) != "up" for d in _alt if d in labs["current"] and _alt[d] != labs["current"][d]))
check("alt_side: bear 는 넓은 띠 down 에서만(히스테리시스 유지분 제외 규칙 확인용 후보)",
      all(ra._candidate_altside(_pw[d], sigs["ethbtc"].get(d, "side"), sigs["dom"].get(d, "side")) != "bear"
          for d in _pw if _pw[d] != "down"))
check("wide_side: 후보 규칙은 현행과 같다(띠만 다름)",
      _wide == ra._vote(_pw, sigs["ethbtc"], sigs["dom"]))
check("signals 에 진단용 원신호 병기", {"price", "price_wide", "dom", "ethbtc"} <= set(sigs))

# 3c. 진단 함수 (판정 아님)
_rel = rq.alt_rel_forward({"BTC": up[:100], "ETH": dn[:100]}, fwd=20)
check("alt_rel_forward: 알트 − BTC 선행수익",
      abs(_rel[up[0]["date"]] - ((dn[20]["c"] / dn[0]["c"] - 1) - (up[20]["c"] / up[0]["c"] - 1))) < 1e-12)
_dg = rq.disagreement({"d1": "bear", "d2": "bear", "d3": "bull_btc"},
                      {"d1": "bull_altseason", "d2": "bear", "d3": "bull_btc"},
                      {"d1": 0.10, "d2": -0.02, "d3": 0.01}, {"d1": 0.05, "d2": 0.0, "d3": 0.0})
_ch = [r for r in _dg if r["changed"]]
check("disagreement: 바뀐 칸만 changed=True, 일수·선행 평균",
      len(_ch) == 1 and _ch[0]["transition"] == "bear→bull_altseason" and _ch[0]["days"] == 1
      and abs(_ch[0]["uni_fwd"] - 0.10) < 1e-12 and abs(_ch[0]["alt_rel_fwd"] - 0.05) < 1e-12)

# 4. 벤치마크 지표
fwd = rq.forward_returns({"A": up[:100]})
check("forward_returns: 20일 뒤 종가/오늘 종가", abs(fwd[up[0]["date"]] - (up[20]["c"] / up[0]["c"] - 1)) < 1e-12)
truth = rq.truth_series(up[:100], fwd=40, thr=0.05)
check("truth: 강한 상승 → bull", truth[up[0]["date"]] == "bull")
# 합성 진실: 30일 bull → 30일 bear
tdates = [(date(2024, 1, 1) + timedelta(days=i)).isoformat() for i in range(60)]
tr_truth = {d: ("bull" if i < 30 else "bear") for i, d in enumerate(tdates)}
trans = rq.transitions(tr_truth, min_run=10)
check("transitions: 1회, 31일째 bear", trans == [(tdates[30], "bear")], str(trans))
lab_lag5 = {d: ("bull_btc" if i < 35 else "bear") for i, d in enumerate(tdates)}
check("lag: 5일 늦은 라벨 → 5", rq.lag_stats(lab_lag5, trans, tdates)["mean"] == 5)
lab_never = {d: "bull_btc" for d in tdates}
check("lag: 안 바뀌면 cap", rq.lag_stats(lab_never, trans, tdates, cap=20)["mean"] == 20)
fwd_syn = {d: (0.05 if i < 30 else -0.05) for i, d in enumerate(tdates)}
r_good = rq.evaluate_labeler("good", {d: ("bull_btc" if i < 30 else "bear") for i, d in enumerate(tdates)}, fwd_syn, fwd_syn, trans)
r_bad = rq.evaluate_labeler("bad", {d: ("bear" if i < 30 else "bull_btc") for i, d in enumerate(tdates)}, fwd_syn, fwd_syn, trans)
check("separation: 맞는 라벨 +10%p, 반대 라벨 −10%p", abs(r_good["separation"] - 0.10) < 1e-9 and abs(r_bad["separation"] + 0.10) < 1e-9)
check("hit_rate: 맞는 라벨 100%, 반대 0%", r_good["hit_rate"] == 1.0 and r_bad["hit_rate"] == 0.0)
check("flips_per_year 계산", r_good["flips_per_year"] > 0)
cur = dict(separation=0.02, by_year={"2023": dict(n=100, separation=0.01)}, lag=dict(mean=10), flips_per_year=4)
better = dict(separation=0.03, by_year={"2023": dict(n=100, separation=0.02), "2024": dict(n=100, separation=0.01)}, lag=dict(mean=8), flips_per_year=5)
check("beats_current: 4조건 만족 → pass", rq.beats_current(better, cur)["pass_"])
check("beats_current: 지연 더 길면 탈락", not rq.beats_current(dict(better, lag=dict(mean=12)), cur)["pass_"])
check("beats_current: flips 1.5배 초과 탈락", not rq.beats_current(dict(better, flips_per_year=7), cur)["pass_"])
check("beats_current: 연도 3/4 미만 탈락", not rq.beats_current(dict(better, by_year={"2023": dict(n=100, separation=0.02), "2024": dict(n=100, separation=-0.01)}), cur)["pass_"])

# 5. method_q arm 의미
mq.REGMAPS = {"current": labs["current"], "vol_side": labs["vol_side"]}
mq.setup_arms(list(mq.REGMAPS))
check("setup_arms: D, RL + 후보당 D_/RL_/F_", mq.ARMS == ["D", "RL", "D_vol_side", "RL_vol_side", "F_vol_side"], str(mq.ARMS))
check("setup_arms: method_m 전역도 교체", mm.ARMS == mq.ARMS)
lab_c = mq.label_fn("current", btc)
si = 400
check("label_fn: 날짜 조회", lab_c(si) == labs["current"].get(btc[si]["date"]))
r1 = mm.outcome(btc, si, "long", set(), "D", lab_c)
r2 = mm.outcome(btc, si, "long", set(), "D", mq.label_fn("current", btc))
check("D arm == method_m.outcome(D, current)", r1 == r2)
check("blocked: 롱은 bear 에서, 숏은 bull_* 에서", mm.blocked("long", "bear") and mm.blocked("short", "bull_btc") and not mm.blocked("long", "bull_btc"))

# 6. e2e (합성 CSV)
def write_csv(path, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f); w.writerow(["timestamp", "open", "high", "low", "close", "volume"])
        for r in rows:
            w.writerow([r["ts"], r["o"], r["h"], r["l"], r["c"], r["v"]])

cwd = os.getcwd()
with tempfile.TemporaryDirectory() as td:
    os.chdir(td)
    try:
        os.makedirs("data")
        syms = sorted(set(detlib.SYMBOLS) | set(rs.ALTS) | {"LINK", "DOT", "UNI"})
        for k, s in enumerate(syms):
            write_csv(f"data/{s.lower()}_1d.csv", rows_of(1500, 100 + k, drift=0.0005 if k % 2 else -0.0002, gaps=True))
        json.dump({"trading_universe": syms}, open("universe.json", "w"))
        json.dump({d: 0.0001 for d in [(date(2021, 1, 1) + timedelta(days=i)).isoformat() for i in range(1500)]},
                  open(ra.FUNDING_CACHE, "w"))
        rq.main(["--no-fetch"])
        q = json.load(open("_regime_quality.json", encoding="utf-8"))
        mm.HOLDOUT_DAYS = 200
        mq.HOLDOUT_DAYS = 200
        import method_r as mr
        mr.BOOT_N = 50
        mq.main(["--no-fetch"])
        m = json.load(open("method_q.json", encoding="utf-8"))
    finally:
        os.chdir(cwd)
check("e2e quality: 전 라벨러 결과", set(q["results"]) == set(ra.LABELERS), str(set(q["results"])))
check("e2e quality: verdicts 는 current 제외 전부", sum(1 for v in q["verdicts"].values() if v) == len(ra.LABELERS) - 1,
      f'{sum(1 for v in q["verdicts"].values() if v)} vs {len(ra.LABELERS) - 1}')
check("e2e quality: candidates 는 리스트", isinstance(q["candidates"], list))
check("e2e quality: 지평별 진단 20/40/60/90", all(set(r["by_horizon"]) == {"20", "40", "60", "90"} for r in q["results"].values()))
check("e2e quality: 20일 지평 분리폭 == 주 지표", all(abs(r["by_horizon"]["20"]["separation"] - r["separation"]) < 1e-12 for r in q["results"].values()))
check("e2e method_q: 패턴 결과 + _verdicts", "_verdicts" in m and any(not k.startswith("_") for k in m))
check("e2e method_q: 1단계 미통과 라벨러 arm 은 adopt=False",
      all(not v["adopt"] for a, v in m["_verdicts"].items() if "_" in a and a.split("_", 1)[1] not in q["candidates"]))
check("e2e method_q: RL(현행) arm 은 1단계 무관하게 stage1_ok", m["_verdicts"]["RL"]["stage1_ok"])
check("e2e method_q: arm 수 = 2 + 3x(라벨러-1)", len(m["_config"]["arms"]) == 2 + 3 * (len(ra.LABELERS) - 1),
      str(len(m["_config"]["arms"])))

print("\n" + ("ALL PASS" if not fails else f"FAILS: {fails}"))
sys.exit(1 if fails else 0)
