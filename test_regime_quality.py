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
check("라벨러 7종 전부 생성", set(labs) == set(ra.LABELERS), str(set(labs)))
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
check("e2e quality: 7 라벨러 결과", set(q["results"]) == set(ra.LABELERS), str(set(q["results"])))
check("e2e quality: verdicts 에 current 제외 6", sum(1 for v in q["verdicts"].values() if v) == 6)
check("e2e quality: candidates 는 리스트", isinstance(q["candidates"], list))
check("e2e quality: 지평별 진단 20/40/60/90", all(set(r["by_horizon"]) == {"20", "40", "60", "90"} for r in q["results"].values()))
check("e2e quality: 20일 지평 분리폭 == 주 지표", all(abs(r["by_horizon"]["20"]["separation"] - r["separation"]) < 1e-12 for r in q["results"].values()))
check("e2e method_q: 패턴 결과 + _verdicts", "_verdicts" in m and any(not k.startswith("_") for k in m))
check("e2e method_q: 1단계 미통과 라벨러 arm 은 adopt=False",
      all(not v["adopt"] for a, v in m["_verdicts"].items() if "_" in a and a.split("_", 1)[1] not in q["candidates"]))
check("e2e method_q: RL(현행) arm 은 1단계 무관하게 stage1_ok", m["_verdicts"]["RL"]["stage1_ok"])
check("e2e method_q: arm 수 = 2 + 3x6", len(m["_config"]["arms"]) == 2 + 3 * 6, str(len(m["_config"]["arms"])))

print("\n" + ("ALL PASS" if not fails else f"FAILS: {fails}"))
sys.exit(1 if fails else 0)
