"""
validate_regime_split_all 로직 검증 (합성 데이터, 네트워크 없음).

  - 사전 등록 패턴 목록: 55 셀, 모듈·함수가 전부 로드되고 합성 rows 에서 예외 없이 돈다
  - 1d/4h/1w 프레임은 validate_regime_split.gate_cell(배포 6종 프레임)과 같은 판정을 낸다
  - 1h 프레임은 intraday_lab.outcome_atr(±1.5ATR/12봉) 을 쓴다 — ±10% 라벨 아님
  - 베이스라인 풀이 레짐별로 분리되고, 1h 풀은 ATR 없는 봉을 제외한다
  - STRICT 규칙: 두 코호트 PASSED + boot_p<0.01 + 양수 해>=2 셋 다 필요
  - main() 이 합성 CSV 위에서 끝까지 돌고 _regime_split_all.json 을 쓴다
실행: python test_regime_split_all.py
"""
import csv
import json
import os
import random
import sys
import tempfile
from datetime import datetime, timedelta, timezone

import detlib
import intraday_lab as il
import regime_switch as rs
import validate_regime_split as v1
import validate_regime_split_all as v

fails = []


def check(n, c, d=""):
    print(("PASS " if c else "FAIL ") + n + ("" if c else f" — {d}"))
    c or fails.append(n)


def rows_of(n, seed, drift=0.0, tf_ms=86_400_000, px0=100.0, start=datetime(2023, 1, 1, tzinfo=timezone.utc)):
    random.seed(seed)
    px, out = px0, []
    for i in range(n):
        nxt = px * (1 + drift + random.gauss(0, 0.01))
        hi, lo = max(px, nxt) * (1 + abs(random.gauss(0, 0.004))), min(px, nxt) * (1 - abs(random.gauss(0, 0.004)))
        ts = int(start.timestamp() * 1000) + i * tf_ms
        out.append(dict(ts=ts, date=datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d"),
                        o=px, h=hi, l=lo, c=nxt, v=1000 + random.random() * 100))
        px = nxt
    return out


# 1. 패턴 목록
check("사전 등록 55 패턴", len(v.PATTERNS) == 55, str(len(v.PATTERNS)))
check("cell_id 중복 없음", len({p[0] for p in v.PATTERNS}) == len(v.PATTERNS))
check("TF 는 1d/1w/4h/1h 만", all(p[1] in ("1d", "1w", "4h", "1h") for p in v.PATTERNS))
check("방향은 long/short 만", all(p[3] in ("long", "short") for p in v.PATTERNS))
check("cell_id 접미사가 TF 와 일치", all(p[0].endswith("_" + p[1]) for p in v.PATTERNS))
syn = rows_of(400, 1)
errs = []
for cid, tf, fn, d, memo in v.PATTERNS:
    try:
        idx = fn(syn)
        assert all(isinstance(i, int) and 0 <= i < len(syn) for i in idx)
    except Exception as e:
        errs.append((cid, str(e)[:50]))
check("모든 디텍터가 합성 rows 에서 인덱스 리스트 반환", not errs, str(errs))

# 2. 프레임: 1d 는 v1.gate_cell 과 동일 판정
sigs = [(syn[i]["date"], detlib.outcome(syn, i, "long")[1], "long") for i in range(30, 300, 9)]
pool_v1 = [(syn, i) for i in range(len(syn) - detlib.LABEL_WINDOW - 1)]
pool_v = [(syn, i, None) for i in range(len(syn) - detlib.LABEL_WINDOW - 1)]
a = v1.gate_cell("v1", sigs, pool_v1, verbose=False)
b = v.gate_cell("v", sigs, pool_v, v.outcome_fixed, verbose=False)
check("1d 프레임: n/mean/median 동일", (a["n"], a["mean"], a["median"]) == (b["n"], b["mean"], b["median"]))
check("1d 프레임: boot_p·base_mean 동일 (같은 시드·같은 풀)",
      abs(a["boot_p"] - b["boot_p"]) < 1e-12 and abs(a["base_mean"] - b["base_mean"]) < 1e-12,
      f"{a['boot_p']} vs {b['boot_p']}")
check("1d 프레임: verdict 동일", a["verdict"] == b["verdict"])
check("frame_of(1d/4h/1w) 은 동결 ±10%/20봉", all(v.frame_of(tf)[0] is v.outcome_fixed and v.frame_of(tf)[2] == 20 for tf in ("1d", "4h", "1w")))

# 3. 1h 프레임은 ATR 배리어
h1 = rows_of(600, 2, tf_ms=3_600_000)
atr = il.atr_series(h1)
fn, need, tail = v.frame_of("1h")
check("frame_of(1h): ATR 필요 + 12봉 꼬리", need and tail == 12)
i0 = 100
check("1h outcome == intraday_lab.outcome_atr", fn(h1, i0, "long", atr) == il.outcome_atr(h1, i0, "long", atr, 12)[1])
check("1h outcome != ±10% 라벨", fn(h1, i0, "long", atr) != detlib.outcome(h1, i0, "long")[1])
check("ATR 없는 초반 봉은 None", fn(h1, 3, "long", atr) is None)

# 4. 풀 분리
regmap = {r["date"]: ("bear" if k % 2 else "bull_btc") for k, r in enumerate(syn)}
pools, atrs = v.build_pools({"A": syn}, {"all": {"A"}}, regmap, "1d")
check("1d 풀: bear 풀은 bear 날짜만", all(regmap[rw[i]["date"]] == "bear" for rw, i, _ in pools[("all", "bear")]))
check("1d 풀: bull+bear = ALL", len(pools[("all", "bear")]) + len(pools[("all", "bull_btc")]) == len(pools[("all", "ALL")]))
check("1d 풀: 마지막 20봉 제외", max(i for _, i, _ in pools[("all", "ALL")]) == len(syn) - 22)
regmap_h = {r["date"]: "bear" for r in h1}
pools_h, atrs_h = v.build_pools({"A": h1}, {"all": {"A"}}, regmap_h, "1h")
check("1h 풀: ATR 있는 봉만", all(a[i] is not None and a[i] > 0 for _, i, a in pools_h[("all", "bear")]))
check("1h 풀: sideways 풀 비어 있음(스킵 대상)", pools_h[("all", "sideways")] == [])

# 5. STRICT 규칙
good = dict(verdict="PASSED", boot_p=0.004, pos_years=3)
check("strict: 둘 다 좋은 셀 → True", v.strict_ok([good, dict(good)]))
check("strict: 한 코호트 REJECTED → False", not v.strict_ok([good, dict(good, verdict="REJECTED")]))
check("strict: boot_p .03 (PASSED 이지만) → False", not v.strict_ok([good, dict(good, boot_p=0.03)]))
check("strict: 양수 해 1 → False", not v.strict_ok([good, dict(good, pos_years=1)]))
check("strict: 셀 없음(None) → False", not v.strict_ok([good, None]))

# 6. collect 가 꼬리·None 을 거른다
sb = v.collect(lambda rows: list(range(0, len(rows), 7)), {"A": syn}, {"A": None}, regmap, "1d", "long")
check("collect: 신호가 (date, ret, dir, regime) 4-튜플", all(len(x) == 4 and x[2] == "long" for x in sb["A"]))
check("collect: 마지막 20봉 신호 제외", all(x[0] <= syn[len(syn) - 22]["date"] for x in sb["A"]))
sb_h = v.collect(lambda rows: [3, 200, 300], {"A": h1}, {"A": atr}, regmap_h, "1h", "short")
check("collect(1h): ATR 없는 신호(idx 3) 제외", len(sb_h["A"]) == 2)

# 7. main() 합성 CSV e2e
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
        syms = ["AAA", "BBB", "CCC"]
        json.dump({"trading_universe": syms}, open("universe.json", "w"))
        d1 = {}
        for k, s in enumerate(syms):
            d1[s] = rows_of(500, 10 + k, drift=0.001)
            write_csv(f"data/{s.lower()}_1d.csv", d1[s])
            write_csv(f"data/{s.lower()}_1h.csv", rows_of(800, 20 + k, tf_ms=3_600_000))
        rm = {r["date"]: ("bull_btc" if i < 250 else "bear") for i, r in enumerate(d1["AAA"])}
        for r in rows_of(800, 20, tf_ms=3_600_000):
            rm.setdefault(r["date"], "bear")
        rs.build_regime_map = lambda *a, **k: rm
        v.BOOT_N = 50
        v.PATTERNS = [p for p in v.PATTERNS if p[0] in ("hammer_1d", "engulfing_1h", "triple_top_1w")]
        v.main(["--no-fetch", "--tf", "1d,1w,1h"])
        out = json.load(open("_regime_split_all.json", encoding="utf-8"))
    finally:
        os.chdir(cwd)
res = out["results"]
check("e2e: 세 패턴 결과 존재", set(res) == {"hammer_1d", "engulfing_1h", "triple_top_1w"}, str(set(res)))
check("e2e: 1d 셀에 레짐·코호트 키", any(k.startswith("all:") for k in res["hammer_1d"]["cells"])
      and any(k.startswith("top30:") for k in res["hammer_1d"]["cells"]))
check("e2e: 1h 결과 tf=1h", res["engulfing_1h"]["tf"] == "1h")
check("e2e: 1w 결과 tf=1w (1d 리샘플)", res["triple_top_1w"]["tf"] == "1w")
check("e2e: 셀 레코드에 verdict/base_mean/pos_years", all(
    {"verdict", "base_mean", "pos_years", "by_year"} <= set(c) for p in res.values() for c in p["cells"].values()))
check("e2e: strict_rule 기록", out["strict_rule"] == dict(boot_p=0.01, pos_years=2, both_cohorts=True))
check("e2e: summary 의 strict 는 bool", all(isinstance(s["strict"], bool) for s in out["summary"]))

print("\n" + ("ALL PASS" if not fails else f"FAILS: {fails}"))
sys.exit(1 if fails else 0)
