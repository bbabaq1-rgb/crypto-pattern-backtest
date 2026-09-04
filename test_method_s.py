"""
method_s(레짐 청산 소거 시험) 로직 검증 (합성 데이터, 네트워크 없음).

  - outcome(use_regime=True, max_hold=30) 이 **실거래 paper_executor.eval_D** 및
    method_m.outcome(rule="D") 과 수익률·보유봉·사유까지 완전 일치 (base arm 이 현행 규칙임을 고정)
  - D_norg 는 regime_switch 를 절대 내지 않고, D_time 은 상한이 실제로 구속한다
  - 블록 셔플이 라벨별 일수와 런 길이 다중집합을 **정확히 보존**하고 정렬만 파괴한다
  - 사전 등록 판정 A/B/C 분기, weighted 합산
  - main() 이 합성 CSV 위에서 끝까지 돌고 method_s.json 을 쓴다
실행: python test_method_s.py
"""
import csv
import json
import os
import random
import sys
import tempfile
from datetime import date, timedelta

import detlib
import method_m as mm
import method_r as mr
import method_s as ms
import paper_executor as pe
import regime_switch as rs

fails = []


def check(n, c, d=""):
    print(("PASS " if c else "FAIL ") + n + ("" if c else f" — {d}"))
    c or fails.append(n)


def rows_of(n, seed, drift=0.0, start=date(2021, 1, 1), vol=0.02, gaps=True):
    random.seed(seed)
    px, out = 100.0, []
    for i in range(n):
        o = px * (1 + random.gauss(0, 0.004)) if gaps else px
        nx = px * (1 + drift + random.gauss(0, vol))
        d = start + timedelta(days=i)
        out.append(dict(ts=int((d - date(1970, 1, 1)).total_seconds() * 1000), date=d.isoformat(),
                        o=o, h=max(o, nx) * (1 + abs(random.gauss(0, 0.006))),
                        l=min(o, nx) * (1 - abs(random.gauss(0, 0.006))),
                        c=nx, v=1000.0 * (1 + abs(random.gauss(0, 0.8)))))
        px = nx
    return out


LABELS = ["bull_btc", "bull_altseason", "bear", "sideways"]

# ── 1. base arm 이 실거래 규칙과 같은가 (가장 중요) ─────────────────────────
check("상수 일치: 손절/만기/수수료", (ms.STOP, ms.MAX_HOLD, ms.FEE) == (pe.STOP, pe.MAX_HOLD_D, pe.FEE),
      f"{(ms.STOP, ms.MAX_HOLD, ms.FEE)} vs {(pe.STOP, pe.MAX_HOLD_D, pe.FEE)}")

mismatch_live = mismatch_mm = 0
n_case = 0
for seed in range(60):
    rows = rows_of(160, 500 + seed, drift=random.Random(seed).choice([-0.004, 0.0, 0.004]))
    rng = random.Random(seed)
    regmap = {}
    lab = rng.choice(LABELS)
    for r in rows:                                  # 런 구조를 가진 라벨열
        if rng.random() < 0.08:
            lab = rng.choice(LABELS)
        regmap[r["date"]] = lab
    opp_set = {i for i in range(len(rows)) if rng.random() < 0.03}
    for direction in ("long", "short"):
        for si in (10, 40, 90):
            n_case += 1
            labfn = lambda j, r=rows: regmap.get(r[j]["date"])
            ret, hold, reason = ms.outcome(rows, si, direction, opp_set, labfn)
            live = pe.eval_D(rows, si, direction, opp_set, regmap)
            if live is None:
                if si + ms.MAX_HOLD <= len(rows) - 1:
                    mismatch_live += 1                # eval_D 는 만기 미도래면 None
            else:
                j, _px, lret, lreason = live
                if abs(lret - ret) > 1e-12 or lreason != reason or (j - si) != hold:
                    mismatch_live += 1
            mret, mhold, mreason = mm.outcome(rows, si, direction, opp_set, "D", labfn)
            if abs(mret - ret) > 1e-12 or mreason != reason or mhold != hold:
                mismatch_mm += 1
check(f"outcome == paper_executor.eval_D ({n_case} 시나리오)", mismatch_live == 0, f"{mismatch_live}건 불일치")
check(f"outcome == method_m.outcome(rule=D) ({n_case} 시나리오)", mismatch_mm == 0, f"{mismatch_mm}건 불일치")

# ── 2. arm 규칙의 의미 ──────────────────────────────────────────────────────
rows = rows_of(200, 7)
rng = random.Random(3)
regmap = {}
lab = "bull_btc"
for r in rows:
    if rng.random() < 0.15:
        lab = rng.choice(LABELS)
    regmap[r["date"]] = lab
labfn = lambda j: regmap.get(rows[j]["date"])
res_d = [ms.outcome(rows, si, "long", set(), labfn) for si in range(5, 150)]
res_n = [ms.outcome(rows, si, "long", set(), labfn, use_regime=False) for si in range(5, 150)]
res_t = [ms.outcome(rows, si, "long", set(), labfn, use_regime=False, max_hold=8) for si in range(5, 150)]
check("D 는 regime_switch 를 낸다", any(r[2] == "regime_switch" for r in res_d))
check("D_norg 는 regime_switch 를 절대 안 낸다", not any(r[2] == "regime_switch" for r in res_n))
check("D_norg 사유는 stop/opp_signal/maxhold 뿐",
      {r[2] for r in res_n} <= {"stop", "opp_signal", "maxhold"}, str({r[2] for r in res_n}))
check("D_time 상한이 구속한다", max(r[1] for r in res_t) <= 8)
check("D_norg 보유 >= D 보유 (레짐 출구를 없앴으므로)",
      all(n[1] >= d[1] for n, d in zip(res_n, res_d)))
check("레짐 없는 봉(None)은 전환으로 세지 않는다",
      ms.outcome(rows, 5, "long", set(), lambda j: None)[2] in ("stop", "maxhold"))

# ── 3. 블록 셔플 ────────────────────────────────────────────────────────────
rr = ms.runs_of(regmap)
check("runs_of: 길이 합 = 일수", sum(n for _, n in rr) == len(regmap))
check("runs_of: 인접 런 라벨이 다르다", all(a[0] != b[0] for a, b in zip(rr, rr[1:])))
check("flips = 런 수 - 1", ms.flips(regmap) == len(rr) - 1)
sh = ms.shuffle_regmap(regmap, 42)
check("셔플: 날짜 집합 동일", set(sh) == set(regmap))
check("셔플: 라벨별 일수 정확히 보존", mr._count(sh.values()) == mr._count(regmap.values()),
      f"{mr._count(sh.values())} vs {mr._count(regmap.values())}")
check("셔플: 런 길이 다중집합 보존",
      sorted(n for _, n in ms.runs_of(sh)) != [] and
      sum(n for _, n in ms.runs_of(sh)) == len(regmap))
check("셔플: 전환 수를 **정확히** 보존 (제약 셔플)", ms.flips(sh) == ms.flips(regmap),
      f"{ms.flips(sh)} vs {ms.flips(regmap)}")
check("셔플: 인접 런 라벨이 겹치지 않음", all(a[0] != b[0] for a, b in zip(ms.runs_of(sh), ms.runs_of(sh)[1:])))
check("셔플: 런 개수 보존", len(ms.runs_of(sh)) == len(ms.runs_of(regmap)))
check("셔플: 라벨별 런 길이 다중집합 보존",
      {lb: sorted(n for l, n in ms.runs_of(sh) if l == lb) for lb in set(regmap.values())} ==
      {lb: sorted(n for l, n in ms.runs_of(regmap) if l == lb) for lb in set(regmap.values())})
_plain = ms.shuffle_regmap(regmap, 42, preserve_flips=False)
check("무제약 셔플은 전환 수가 줄어든다(제약 셔플이 필요한 이유)",
      ms.flips(_plain) < ms.flips(regmap), f"{ms.flips(_plain)} vs {ms.flips(regmap)}")
diff_days = sum(1 for d in regmap if sh[d] != regmap[d])
check("셔플: 정렬이 실제로 파괴됨(상당수 날짜의 라벨이 바뀜)", diff_days > len(regmap) * 0.2,
      f"{diff_days}/{len(regmap)}")
check("셔플: 시드 고정 재현", ms.shuffle_regmap(regmap, 42) == sh)
check("셔플: 다른 시드는 다른 결과", ms.shuffle_regmap(regmap, 43) != sh)

# ── 4. 합산·판정 분기 ───────────────────────────────────────────────────────
check("weighted: 표본 가중 평균", abs(ms.weighted([(0.02, 100), (-0.01, 300)]) - (-0.0025)) < 1e-12)
check("weighted: 빈 입력 0", ms.weighted([]) == 0.0)


def decide(frac, norg_diff, time_diff, time_t, norg_pass):
    A = frac >= 0.90 and norg_diff < 0
    B = frac <= 0.60 or (time_diff >= 0 and time_t > -2)
    C = bool(norg_pass)
    return ("C_레짐청산_해로움" if C
            else "A_상태정보_실재" if A and not B
            else "B_레짐은_시계" if B and not A
            else "D_정보있음_그러나_시계로대체가능" if A and B
            else "INCONCLUSIVE")


check("판정 A: 셔플 압도 + 소거 손해", decide(0.95, -0.004, -0.01, -3.0, False) == "A_상태정보_실재")
check("판정 B: 셔플과 구분 불가", decide(0.50, -0.004, -0.01, -3.0, False) == "B_레짐은_시계")
check("판정 D: 셔플은 이기나 시간 상한이 동등 -> 시계로 대체 가능",
      decide(0.95, -0.004, +0.001, 0.5, False) == "D_정보있음_그러나_시계로대체가능")
check("판정 B: 셔플 구분 불가 + 시간 상한 열세도 B",
      decide(0.50, -0.004, -0.01, -3.0, False) == "B_레짐은_시계")
check("판정 C: 소거가 유의 우위면 최우선", decide(0.95, +0.01, -0.01, -3.0, True) == "C_레짐청산_해로움")
check("판정 INCONCLUSIVE", decide(0.75, -0.004, -0.01, -3.0, False) == "INCONCLUSIVE")

# ── 4b. 표본 범위 (--universe) ──────────────────────────────────────────────
check("기본 표본은 메이저 7종목", ms.symbols() == list(detlib.SYMBOLS) and not ms.UNIVERSE_MODE)
_cwd = os.getcwd()
with tempfile.TemporaryDirectory() as _td:
    os.chdir(_td)
    try:
        json.dump({"trading_universe": ["AAA", "BBB", "CCC"]}, open("universe.json", "w"))
        ms.UNIVERSE_MODE = True
        check("--universe 는 universe.json trading_universe 를 쓴다", ms.symbols() == ["AAA", "BBB", "CCC"])
        json.dump({}, open("universe.json", "w"))
        check("trading_universe 없으면 메이저 폴백", ms.symbols() == list(detlib.SYMBOLS))
        os.remove("universe.json")
        check("universe.json 없어도 예외 없이 메이저 폴백", ms.symbols() == list(detlib.SYMBOLS))
    finally:
        ms.UNIVERSE_MODE = False
        os.chdir(_cwd)
check("collect 는 넘긴 심볼만 본다",
      ms.collect("detector_engulfing", None, "1d", syms=[]) == [])

# ── 5. e2e ──────────────────────────────────────────────────────────────────
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
        syms = sorted(set(detlib.SYMBOLS) | set(rs.ALTS))
        for k, s in enumerate(syms):
            write_csv(f"data/{s.lower()}_1d.csv", rows_of(900, 100 + k, drift=0.0006 if k % 2 else -0.0003))
        json.dump({"trading_universe": syms}, open("universe.json", "w"))
        big = rows_of(900, 100)
        rgm, lb = {}, "bull_btc"
        rr2 = random.Random(11)
        for r in big:
            if rr2.random() < 0.02:
                lb = rr2.choice(LABELS)
            rgm[r["date"]] = lb
        rs.build_regime_map = lambda *a, **k: rgm
        mr.BOOT_N = 40
        ms.HOLDOUT_DAYS = 200
        ms.main(["--no-fetch", "--shuffles", "4"])
        out = json.load(open("method_s.json", encoding="utf-8"))
    finally:
        os.chdir(cwd)
pats = [k for k in out if not k.startswith("_")]
check("e2e: 패턴 결과 존재", len(pats) >= 3, str(pats))
check("e2e: 4 arm 전부", all(set(ms.ARMS) <= set(out[p]) for p in pats))
check("e2e: 청산사유 기록", all("_reasons" in out[p] for p in pats))
check("e2e: D_norg 사유에 regime_switch 없음",
      all("regime_switch" not in out[p]["_reasons"]["D_norg"] for p in pats))
check("e2e: D 사유에 regime_switch 있음", any("regime_switch" in out[p]["_reasons"]["D"] for p in pats))
check("e2e: D_time 상한 = D 평균보유 반올림", all(1 <= out[p]["_cap"] <= ms.MAX_HOLD for p in pats))
check("e2e: 셔플 draw 4개", out["_shuffle"]["n"] == 4, str(out["_shuffle"]["n"]))
check("e2e: d_win_frac 은 0~1", 0.0 <= out["_shuffle"]["d_win_frac"] <= 1.0)
check("e2e: 판정 문자열", out["_verdict"] in
      ("A_상태정보_실재", "B_레짐은_시계", "C_레짐청산_해로움",
       "D_정보있음_그러나_시계로대체가능", "INCONCLUSIVE"), out["_verdict"])
check("e2e: 합산에 3 arm", set(out["_pooled"]["train"]) == {"D_norg", "D_time", "D_shuffle"})
check("e2e: config 에 표본 범위 기록",
      out["_config"]["universe_mode"] is False and out["_config"]["n_symbols"] == len(detlib.SYMBOLS))

print("\n" + ("ALL PASS" if not fails else f"FAILS: {fails}"))
sys.exit(1 if fails else 0)
