"""
validate_universe_1d.py — 검증-실거래 유니버스 불일치 해소용 재검증.

배경: 기존 1d 패턴 검증(n=1,290)은 7종목(detlib.SYMBOLS 메이저) 기준인데
실거래는 71종목 유니버스에서 돈다. 알트에서도 엣지가 유효한지 전체 유니버스로
재검증한다(게이트 동결: n>=20, mean>0, median>0, boot_p<0.05, OOS 양구간>=2).

데이터 주의: 로컬 1d CSV 중 54종목은 2021년부터 풀 히스토리, 나머지는 900일
윈도우(2024~). OOS Q1~Q2엔 풀 히스토리 종목만 신호가 잡힌다(자연 필터링).

대상: 실거래 라우팅에 실제 쓰이는 1d 패턴×방향 6종
  engulfing(L/S), fvg(L/S), inverted_hammer(L), marubozu(L)
"""
import os
import glob
import json
import random
import statistics
import importlib
import sys
from math import sqrt, erf

import detlib

TF     = "1d"
SEED   = 42
BOOT_N = 1000
LABEL_W = detlib.LABEL_WINDOW

OOS_SPLITS = [
    ("2021-01-01", "2022-05-31"),
    ("2022-06-01", "2023-10-31"),
    ("2023-11-01", "2025-03-31"),
    ("2025-04-01", "2026-12-31"),
]

CANDS = [
    ("engulfing",        "detector_engulfing",        "long"),
    ("engulfing_short",  "detector_engulfing_short",  "short"),
    ("fvg",              "detector_fvg",              "long"),
    ("fvg_short",        "detector_fvg_short",        "short"),
    ("inverted_hammer",  "detector_inverted_hammer",  "long"),
    ("marubozu",         "detector_marubozu",         "long"),
]


def _universe_syms():
    """trading_universe ∩ 로컬 1d CSV 보유 종목."""
    uni = json.load(open("universe.json", encoding="utf-8")).get("trading_universe", [])
    have = {os.path.basename(f)[:-7].upper() for f in glob.glob("data/*_1d.csv")}
    return sorted([s for s in uni if s in have])


def _pval(t, df):
    z = abs(t) / sqrt(1 + t * t / df)
    return 2 * (1 - 0.5 * (1 + erf(z / sqrt(2))))


_ROWS_CACHE = {}


def _rows(sym):
    if sym not in _ROWS_CACHE:
        try:
            _ROWS_CACHE[sym] = detlib.load_ohlcv(sym, TF)
        except Exception:
            _ROWS_CACHE[sym] = None
    return _ROWS_CACHE[sym]


def _collect(detect_fn, direction, syms, date_from=None, date_to=None):
    rets = []
    for sym in syms:
        rows = _rows(sym)
        if not rows:
            continue
        for si in detect_fn(rows):
            d = rows[si]["date"]
            if date_from and d < date_from:
                continue
            if date_to and d > date_to:
                continue
            _, ret = detlib.outcome(rows, si, direction)
            rets.append((d, ret))
    return rets


def _bootstrap(direction, syms, k=30, n=BOOT_N, seed=SEED):
    random.seed(seed)
    pool = []
    for sym in syms:
        rows = _rows(sym)
        if not rows:
            continue
        for i in range(len(rows) - LABEL_W - 1):
            pool.append((rows, i))
    if not pool:
        return [0.0]
    actual_k = min(k, len(pool))
    means = []
    for _ in range(n):
        sample = random.choices(pool, k=actual_k)
        means.append(statistics.mean(detlib.outcome(r, si, direction)[1] for r, si in sample))
    return means


def run_pattern(label, detect_fn, direction, syms):
    print(f"\n{'='*64}\n패턴: {label}  방향={direction}  (유니버스 {len(syms)}종목)")
    sigs = _collect(detect_fn, direction, syms)
    rets = [r for _, r in sigs]
    n = len(rets)
    mean = statistics.mean(rets) if rets else 0.0
    med  = statistics.median(rets) if rets else 0.0
    if n >= 2:
        sd = statistics.stdev(rets)
        t  = mean / (sd / sqrt(n)) if sd > 0 else 0.0
        p  = _pval(t, n - 1)
    else:
        t, p = 0.0, 1.0
    boot   = _bootstrap(direction, syms, k=max(10, min(30, n)))
    boot_p = sum(1 for b in boot if b >= mean) / len(boot)
    print(f"  n={n} mean={mean*100:+.2f}% median={med*100:+.2f}% "
          f"p={p:.4f} boot_p={boot_p:.4f}")

    oos_pos, oos = 0, []
    for i, (d0, d1) in enumerate(OOS_SPLITS, 1):
        rr = [r for _, r in _collect(detect_fn, direction, syms, d0, d1)]
        m  = statistics.mean(rr) if rr else 0.0
        ok = m > 0 and len(rr) >= 5
        oos_pos += ok
        oos.append(dict(q=i, n=len(rr), mean=m, ok=ok))
        print(f"  OOS Q{i} ({d0[:7]}~{d1[:7]}): n={len(rr)} mean={m*100:+.2f}% {'O' if ok else 'X'}")

    ok_all = n >= 20 and mean > 0 and med > 0 and boot_p < 0.05 and oos_pos >= 2
    verdict = "PASSED" if ok_all else "REJECTED"
    fails = []
    if n < 20: fails.append("n<20")
    if mean <= 0: fails.append("mean<=0")
    if med <= 0: fails.append("median<=0")
    if boot_p >= 0.05: fails.append(f"boot_p={boot_p:.3f}")
    if oos_pos < 2: fails.append(f"OOS {oos_pos}/4")
    print(f"  판정: {verdict}" + (f" ({', '.join(fails)})" if fails else ""))
    return dict(pattern=label, direction=direction, n=n, mean=mean, median=med,
                p=p, boot_p=boot_p, oos_pos=oos_pos, oos=oos,
                verdict=verdict, reason=", ".join(fails))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    syms = _universe_syms()
    print(f"71종목 유니버스 1d 재검증 — 로컬 데이터 보유 {len(syms)}종목")
    results = []
    for label, mod_name, direction in CANDS:
        mod = importlib.import_module(mod_name)
        results.append(run_pattern(label, mod.detect, direction, syms))

    print(f"\n{'='*64}\n요약  (기존 7종목 검증과 비교)")
    print(f"{'패턴':<18} {'n':>6} {'mean':>8} {'median':>8} {'OOS':>5} {'boot_p':>8} {'판정':>9}")
    for r in results:
        print(f"{r['pattern']:<18} {r['n']:>6} {r['mean']*100:>+7.2f}% "
              f"{r['median']*100:>+7.2f}% {r['oos_pos']:>3}/4 {r['boot_p']:>8.4f} "
              f"{r['verdict']:>9}" + (f"  [{r['reason']}]" if r['reason'] else ""))
    json.dump(results, open("_universe_1d_results.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2, default=lambda x: round(float(x), 6))
    print("\n결과 -> _universe_1d_results.json")
    return results


if __name__ == "__main__":
    main()
