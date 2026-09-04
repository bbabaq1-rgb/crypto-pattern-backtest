"""
validate_regime_split.py — 레짐별 분리 게이트 (2026-09-04, 사용자 제안).

"같은 패턴이라도 하락국면과 상승국면 수익이 다르다. 최근 구간으로만 재지 말고 레짐으로 나눠서
그 레짐에 맞는 패턴을 골라야 한다." → 배포 1d 패턴 6종(engulfing L/S, fvg L/S, inverted_hammer,
marubozu)을 **진입 시점 레짐(bull_btc / bull_altseason / bear / sideways)** 로 나눠 셀마다 동결
게이트를 적용한다. 코호트(전체 / 거래대금 top20 / top30, 무기한 캔들 기준)도 교차한다.

- 데이터: universe.json trading_universe, 1d WINDOW 일(거래소가 주는 만큼). 레짐맵은 현행
  regime_switch.build_regime_map()(닫힌 봉).
- 라벨: 동결 ±10%/20봉 (detlib.outcome). 게이트: n>=20, mean>0, median>0, boot_p<0.05,
  OOS 4분위 양구간>=2. **boot_p 는 같은 레짐·같은 코호트의 무작위 진입**을 베이스라인으로
  쓴다 — 상승장 롱이 "상승장이라서" 좋은 것을 엣지로 오인하지 않기 위해.
- 현재 라우팅(direction_switch.json)과 셀 판정을 나란히 놓아 어느 (레짐, 패턴, 방향) 셀이
  게이트를 넘는지 보여 준다. 실거래 코드 무변경. 출력 _regime_split.json + RESULT_JSON.
"""
import importlib
import json
import random
import statistics as st
import sys
import time
from math import erf, sqrt

import detlib
import fetch_data
import regime_switch as rs

WINDOW = 1800
SEED, BOOT_N = 42, 1000
LABEL_W = detlib.LABEL_WINDOW
REGIMES = ["bull_btc", "bull_altseason", "bear", "sideways"]
PATTERNS = [("engulfing", "detector_engulfing", "long"),
            ("engulfing_short", "detector_engulfing_short", "short"),
            ("fvg", "detector_fvg", "long"),
            ("fvg_short", "detector_fvg_short", "short"),
            ("inverted_hammer", "detector_inverted_hammer", "long"),
            ("marubozu", "detector_marubozu", "long")]


def _syms():
    return json.load(open("universe.json", encoding="utf-8"))["trading_universe"]


def fetch(syms):
    t0, ok = time.time(), 0
    for s in syms:
        try:
            _, total = fetch_data.update_csv(f"{s}/USDT", "1d", detlib.CSV(s, "1d"), window_days=WINDOW)
            ok += total > 0
        except Exception as e:
            print(f"  [fetch] {s} 실패: {str(e)[:60]}")
    print(f"[fetch] 1d {WINDOW}일 {ok}/{len(syms)} ({time.time()-t0:.0f}s)", flush=True)


def turnover_rank(rows_by_sym):
    sc = []
    for s, rows in rows_by_sym.items():
        if len(rows) >= 35:
            sc.append((sum(r["c"] * r["v"] for r in rows[-30:]) / 30, s))
    sc.sort(reverse=True)
    return [s for _, s in sc]


def _pval(t, df):
    z = abs(t) / sqrt(1 + t * t / df)
    return 2 * (1 - 0.5 * (1 + erf(z / sqrt(2))))


def gate_cell(label, sigs, pool, verbose=True):
    """sigs: [(date, ret)], pool: [(rows, i)] 같은 레짐·코호트의 무작위 진입 후보."""
    rets = [r for _, r in sigs]
    n = len(rets)
    mean = st.mean(rets) if rets else 0.0
    med = st.median(rets) if rets else 0.0
    t = p = 0.0
    if n >= 2 and st.stdev(rets) > 0:
        t = mean / (st.stdev(rets) / sqrt(n)); p = _pval(t, n - 1)
    boot_p = 1.0
    if pool and n:
        rng = random.Random(SEED)
        k = min(max(10, min(30, n)), len(pool))
        direction = sigs[0][2] if len(sigs[0]) > 2 else "long"
        ge = 0
        for _ in range(BOOT_N):
            smp = rng.choices(pool, k=k)
            bm = st.mean(detlib.outcome(r, i, direction)[1] for r, i in smp)
            ge += bm >= mean
        boot_p = ge / BOOT_N
    oos = []
    if n >= 20:
        dates = sorted(d for d, *_ in sigs)
        cuts = [dates[len(dates) * i // 4] for i in range(1, 4)]
        for q in range(4):
            lo = cuts[q - 1] if q else "0000"; hi = cuts[q] if q < 3 else "9999"
            qr = [r for d, r, *_ in sigs if lo <= d < hi]
            qm = st.mean(qr) if qr else 0.0
            oos.append(dict(q=q + 1, n=len(qr), mean=qm, ok=len(qr) >= 5 and qm > 0))
    oos_pos = sum(1 for o in oos if o["ok"])
    ok = n >= 20 and mean > 0 and med > 0 and boot_p < 0.05 and oos_pos >= 2
    fails = []
    if n < 20: fails.append("n<20")
    if mean <= 0: fails.append("mean<=0")
    if med <= 0: fails.append("median<=0")
    if boot_p >= 0.05: fails.append(f"boot_p={boot_p:.3f}")
    if n >= 20 and oos_pos < 2: fails.append(f"OOS {oos_pos}/4")
    rec = dict(n=n, mean=mean, median=med, t=t, p=p, boot_p=boot_p, oos_pos=oos_pos,
               verdict="PASSED" if ok else "REJECTED", reason=", ".join(fails))
    if verbose:
        print(f"  {label:<44} n={n:>5} mean={mean*100:+6.2f}% med={med*100:+6.2f}% "
              f"boot_p={boot_p:.3f} OOS={oos_pos}/4 -> {rec['verdict']} {rec['reason']}")
    return rec


def main():
    syms = _syms()
    if "--no-fetch" not in sys.argv:
        fetch(syms)
    regmap = rs.build_regime_map()
    ymix = {}
    for d, g in regmap.items():
        ymix.setdefault(d[:4], {}).setdefault(g, 0); ymix[d[:4]][g] += 1
    print(f"[regime] {len(regmap)}일 | 연도별: " + "  ".join(f"{y}:{v}" for y, v in sorted(ymix.items())))
    rows_by = {}
    for s in syms:
        try:
            rows_by[s] = detlib.load_ohlcv(s, "1d")
        except Exception:
            pass
    ranked = turnover_rank(rows_by)
    cohorts = {"all": set(rows_by), "top20": set(ranked[:20]), "top30": set(ranked[:30])}
    print(f"[rank] top20: {ranked[:20]}")
    # 레짐·코호트별 무작위 진입 풀
    pools = {}
    for cname, cs in cohorts.items():
        for g in REGIMES:
            pools[(cname, g)] = [(rows, i) for s in cs for rows in [rows_by[s]]
                                for i in range(len(rows) - LABEL_W - 1) if regmap.get(rows[i]["date"]) == g]
        pools[(cname, "ALL")] = [(rows, i) for s in cs for rows in [rows_by[s]] for i in range(len(rows) - LABEL_W - 1)]
    routing = {}
    try:
        routing = json.load(open("direction_switch.json", encoding="utf-8")).get("routing", {})
    except Exception:
        pass
    results = {}
    for pat, modname, direction in PATTERNS:
        mod = importlib.import_module(modname)
        sigs_by_sym = {}
        for s, rows in rows_by.items():
            out = []
            for si in mod.detect(rows):
                if si + 1 >= len(rows):
                    continue
                _, ret = detlib.outcome(rows, si, direction)
                out.append((rows[si]["date"], ret, direction, regmap.get(rows[si]["date"])))
            sigs_by_sym[s] = out
        results[pat] = {}
        print(f"\n[{pat} {direction}]")
        for cname, cs in cohorts.items():
            for g in REGIMES + ["ALL"]:
                sigs = [x for s in cs for x in sigs_by_sym[s] if g == "ALL" or x[3] == g]
                rec = gate_cell(f"{pat}:{cname}:{g}", [(d, r, dr) for d, r, dr, _ in sigs], pools[(cname, g)])
                base_pat = pat.replace("_short", "")
                rec["routing_now"] = routing.get(g, {}).get(base_pat) if g != "ALL" else None
                results[pat][f"{cname}:{g}"] = rec
    json.dump(dict(window=WINDOW, year_mix=ymix, top20=ranked[:20], top30=ranked[:30], results=results),
              open("_regime_split.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    passed = {p: [k for k, r in cells.items() if r["verdict"] == "PASSED"] for p, cells in results.items()}
    print("\n[통과 셀]")
    for p, ks in passed.items():
        print(f"  {p:<18} {ks}")
    print("\nRESULT_JSON: " + json.dumps(passed, separators=(",", ":")))


if __name__ == "__main__":
    main()
