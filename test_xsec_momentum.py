"""
validate_xsec_momentum 로직 검증 (합성 데이터, 네트워크 없음).

  - signals(): **룩어헤드 없음** — 진입 봉 이후를 바꿔도 선정이 불변
  - skip-1 이 실제로 적용된다(직전 봉까지로 순위를 매긴다)
  - 리밸런스 주기 7일, 상위 TOP_N, 수익률 내림차순
  - 후보가 얕은 날짜는 건너뛴다
  - fwd(): 지평 선행수익 + 수수료 차감
  - gate(): 베이스라인이 신호의 **레짐 구성**을 따라간다(상승장 편중을 상쇄)
  - STRICT 규칙(인접 L 동반 통과 + boot_p<0.01) 분기
  - e2e: 합성 CSV 로 main() 이 끝까지 돌고 _xsec_momentum.json 을 쓴다
실행: python test_xsec_momentum.py
"""
import csv
import json
import os
import random
import statistics as st
import sys
import tempfile
from datetime import date, timedelta

import detlib
import regime_switch as rs
import validate_xsec_momentum as x

fails = []


def check(n, c, d=""):
    print(("PASS " if c else "FAIL ") + n + ("" if c else f" — {d}"))
    c or fails.append(n)


def rows_of(n, seed, drift=0.0, vol=0.02, start=date(2021, 1, 1)):
    random.seed(seed)
    px, out = 100.0, []
    for i in range(n):
        o = px * (1 + random.gauss(0, 0.004))
        nx = px * (1 + drift + random.gauss(0, vol))
        d = start + timedelta(days=i)
        out.append(dict(ts=int((d - date(1970, 1, 1)).total_seconds() * 1000), date=d.isoformat(),
                        o=o, h=max(o, nx) * 1.006, l=min(o, nx) * 0.994, c=nx,
                        v=1000.0 * (1 + abs(random.gauss(0, 0.8)))))
        px = nx
    return out


# ── 1. 선정 규칙 ───────────────────────────────────────────────────────────
N = 400
rows_by = {f"S{k}": rows_of(N, 600 + k, drift=0.0) for k in range(30)}
rows_by["WINNER"] = rows_of(N, 999, drift=0.010)          # 강한 상승 추세
rows_by["LOSER"] = rows_of(N, 998, drift=-0.010)
didx = x.date_index(rows_by)
sig = x.signals(rows_by, didx, 28)
check("signals: 신호가 나온다", len(sig) > 0)
picked = {}
for d, s, i, r in sig:
    picked.setdefault(d, []).append(s)
check("signals: 리밸런스마다 상위 TOP_N", all(len(v) == x.TOP_N for v in picked.values()))
dates_sorted = sorted(didx)
sig_dates = sorted(picked)
gaps = {dates_sorted.index(b) - dates_sorted.index(a) for a, b in zip(sig_dates, sig_dates[1:])}
check("signals: 리밸런스 간격 7일", gaps <= {x.REBAL}, str(sorted(gaps)[:5]))
late = [d for d in sig_dates if d > dates_sorted[100]]
check("signals: 추세 상위 종목이 대체로 선정된다",
      sum(1 for d in late if "WINNER" in picked[d]) > len(late) * 0.8)
check("signals: 하락 종목은 거의 선정되지 않는다",
      sum(1 for d in late if "LOSER" in picked[d]) < len(late) * 0.2)

# 룩어헤드: 진입 봉 이후를 조작해도 선정 불변
cut = dates_sorted[200]
mut = {s: [dict(r) for r in rws] for s, rws in rows_by.items()}
for s, rws in mut.items():
    for r in rws:
        if r["date"] > cut:
            r["c"] *= (5.0 if s == "LOSER" else 0.2)      # 미래를 완전히 뒤집는다
sig2 = x.signals(mut, x.date_index(mut), 28)
p1 = {(d, s) for d, s, _, _ in sig if d <= cut}
p2 = {(d, s) for d, s, _, _ in sig2 if d <= cut}
check("signals: 진입 이후 봉을 뒤집어도 그 이전 선정은 불변 (룩어헤드 없음)", p1 == p2,
      f"{len(p1 ^ p2)}건 차이")

# skip-1: 마지막 봉만 조작하면 그 날짜의 선정은 안 바뀌고, 다음 리밸런스는 바뀔 수 있다
mut2 = {s: [dict(r) for r in rws] for s, rws in rows_by.items()}
tgt = sig_dates[len(sig_dates) // 2]
for s, rws in mut2.items():
    for r in rws:
        if r["date"] == tgt and s == "LOSER":
            r["c"] *= 50.0                                # 당일 종가만 폭등
sig3 = x.signals(mut2, x.date_index(mut2), 28)
p3 = {s for d, s, _, _ in sig3 if d == tgt}
check("skip-1: 당일 종가를 조작해도 그 날 선정은 불변",
      p3 == set(picked[tgt]), f"{p3 ^ set(picked[tgt])}")

# ── 2. fwd ─────────────────────────────────────────────────────────────────
r0 = rows_by["S0"]
check("fwd: 지평 선행수익 - 수수료",
      abs(x.fwd(r0, 10, 20) - (r0[30]["c"] / r0[10]["c"] - 1 - detlib.FEE)) < 1e-12)
check("fwd: 끝을 넘으면 마지막 봉으로 클립", x.fwd(r0, len(r0) - 3, 100) is not None)
check("fwd: 여지 없으면 None", x.fwd(r0, len(r0) - 1, 20) is None)

# ── 3. gate 베이스라인이 레짐 구성을 따라가는가 ────────────────────────────
up = rows_of(300, 11, drift=0.01)
dn = rows_of(300, 12, drift=-0.01)
regmap = {}
for i, r in enumerate(up):
    regmap[r["date"]] = "bull_btc" if i < 150 else "bear"
pool = {"bull_btc": [(up, i) for i in range(0, 140)],
        "bear": [(dn, i) for i in range(160, 270)],
        "bull_altseason": [], "sideways": []}
sig_bull = [(up[i]["date"], detlib.outcome(up, i, "long")[1]) for i in range(20, 120)]
sig_bear = [(up[i]["date"], detlib.outcome(up, i, "long")[1]) for i in range(160, 260)]
g_bull = x.gate("bull", sig_bull, pool, regmap, verbose=False)
g_bear = x.gate("bear", sig_bear, pool, regmap, verbose=False)
check("gate: bull 신호의 베이스라인은 bull 풀(상승)에서 뽑혀 평균이 높다",
      g_bull["base_mean"] > g_bear["base_mean"],
      f"{g_bull['base_mean']} vs {g_bear['base_mean']}")
check("gate: 엣지 = 평균 - 레짐 베이스라인",
      abs(g_bull["edge"] - (g_bull["mean"] - g_bull["base_mean"])) < 1e-12)
check("gate: 게이트 5조건", g_bull["verdict"] in ("PASSED", "REJECTED"))
g_small = x.gate("small", sig_bull[:5], pool, regmap, verbose=False)
check("gate: n<20 이면 REJECTED", g_small["verdict"] == "REJECTED" and "n<20" in g_small["reason"])


# ── 4. STRICT 규칙 ─────────────────────────────────────────────────────────
def strict_of(results, passed):
    out = []
    for lb in passed:
        adj = [a for a in x.LOOKBACKS if a != lb
               and abs(x.LOOKBACKS.index(a) - x.LOOKBACKS.index(lb)) == 1]
        if results[lb]["boot_p"] < x.STRICT_BOOT_P and any(a in passed for a in adj):
            out.append(lb)
    return out


res = {7: dict(boot_p=0.005), 14: dict(boot_p=0.02), 28: dict(boot_p=0.001), 56: dict(boot_p=0.30), 84: dict(boot_p=0.40)}
check("STRICT: 인접 L 이 함께 통과하고 boot_p<0.01 이면 후보", strict_of(res, [7, 14]) == [7])
check("STRICT: 혼자만 통과하면 제외", strict_of(res, [28]) == [])
check("STRICT: boot_p 0.02 는 PASSED 여도 STRICT 아님", 14 not in strict_of(res, [7, 14]))

# ── 4b. min_bars 필터 ──────────────────────────────────────────────────────
short_rows = {"A": rows_of(50, 1), "B": rows_of(500, 2), "C": rows_of(900, 3)}
import unittest.mock as _m
with _m.patch.object(detlib, "load_ohlcv", side_effect=lambda s, tf="1d": short_rows[s]):
    check("load_all: 기본 min_bars 는 짧은 종목을 뺀다", set(x.load_all(list(short_rows))) == {"B", "C"})
    check("load_all: min_bars=800 이면 긴 종목만", set(x.load_all(list(short_rows), 800)) == {"C"})
    check("load_all: min_bars 가 크면 빈 결과", x.load_all(list(short_rows), 5000) == {})

# ── 5. e2e ─────────────────────────────────────────────────────────────────
def write_csv(path, rws):
    with open(path, "w", newline="") as f:
        w = csv.writer(f); w.writerow(["timestamp", "open", "high", "low", "close", "volume"])
        for r in rws:
            w.writerow([r["ts"], r["o"], r["h"], r["l"], r["c"], r["v"]])


cwd = os.getcwd()
with tempfile.TemporaryDirectory() as td:
    os.chdir(td)
    try:
        os.makedirs("data")
        syms = [f"C{k}" for k in range(24)]
        for k, s in enumerate(syms):
            write_csv(f"data/{s.lower()}_1d.csv",
                      rows_of(700, 700 + k, drift=0.0008 if k % 3 == 0 else -0.0003))
        json.dump({"trading_universe": syms}, open("universe.json", "w"))
        base = rows_of(700, 700)
        rgm, lb2, rr = {}, "bull_btc", random.Random(31)
        for i, r in enumerate(base):
            if i < 60:
                continue
            if rr.random() < 0.02:
                lb2 = rr.choice(["bull_btc", "bull_altseason", "bear"])
            rgm[r["date"]] = lb2
        rs.build_regime_map = lambda *a, **k: rgm
        x.BOOT_N = 60
        x.main(["--no-fetch"])
        out = json.load(open("_xsec_momentum.json", encoding="utf-8"))
    finally:
        os.chdir(cwd)
check("e2e: L 5개 전부 결과", set(out["results"]) == {str(l) for l in x.LOOKBACKS}, str(set(out["results"])))
check("e2e: 신호가 실제로 잡혔다", all(v["n"] >= 20 for v in out["results"].values()),
      str({k: v["n"] for k, v in out["results"].items()}))
check("e2e: 판정 문자열", all(v["verdict"] in ("PASSED", "REJECTED") for v in out["results"].values()))
check("e2e: 추세 진단·포트폴리오 기록",
      all("trend" in v and "portfolio" in v for v in out["results"].values()))
check("e2e: STRICT ⊆ PASSED", set(out["strict"]) <= set(out["passed"]))
check("e2e: 프레임 탓 기각은 동결 기각 + 추세 양수",
      all(out["results"][str(l)]["verdict"] == "REJECTED" and out["results"][str(l)]["trend"]["mean"] > 0
          for l in out["frame_blocked"]))
check("e2e: 베이스라인이 산출됐다",
      all(v["base_mean"] is not None for v in out["results"].values()))
check("e2e: config 에 관측 창 기록",
      all(k in out["config"] for k in ("min_bars", "date_from", "date_to")))

print("\n" + ("ALL PASS" if not fails else f"FAILS: {fails}"))
sys.exit(1 if fails else 0)
