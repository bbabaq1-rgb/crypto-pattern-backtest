"""
validate_vol_awakening.py — 거래량 각성(슈팅 초동) 4h 디텍터 동결 게이트 검증.

게이트 동결: n>=20, mean>0, median>0, boot_p<0.05, OOS 양구간>=2 (기존과 동일).
라벨: detlib.outcome 트리플배리어 ±10%/20봉/수수료 0.2% (동결).
데이터: 로컬 4h 전체(98종목, 2021~). 발견 표본(최근 1년)과 달리 다년 검증이므로
발견-검증 중첩은 부분적(마지막 OOS 구간만) — 리포트에 명시.
"""
import sys
import os
import glob
import json
import random
import statistics
from math import sqrt, erf

import detlib
import detector_vol_awakening_4h as dva

TF = "4h"
SEED = 42
BOOT_N = 1000
LABEL_W = detlib.LABEL_WINDOW

OOS_SPLITS = [
    ("2021-01-01", "2022-05-31"),
    ("2022-06-01", "2023-10-31"),
    ("2023-11-01", "2025-03-31"),
    ("2025-04-01", "2026-12-31"),
]


def _syms():
    return sorted({os.path.basename(f)[:-7].upper() for f in glob.glob("data/*_4h.csv")})


def _pval(t, df):
    z = abs(t) / sqrt(1 + t * t / df)
    return 2 * (1 - 0.5 * (1 + erf(z / sqrt(2))))


_CACHE = {}


def _rows(sym):
    if sym not in _CACHE:
        try:
            _CACHE[sym] = detlib.load_ohlcv(sym, TF)
        except Exception:
            _CACHE[sym] = None
    return _CACHE[sym]


def _collect(syms, date_from=None, date_to=None):
    rets = []
    for sym in syms:
        rows = _rows(sym)
        if not rows:
            continue
        for si in dva.detect(rows):
            d = rows[si]["date"]
            if date_from and d < date_from:
                continue
            if date_to and d > date_to:
                continue
            _, ret = detlib.outcome(rows, si, "long")
            rets.append((d, ret))
    return rets


def _bootstrap(syms, k, n=BOOT_N):
    random.seed(SEED)
    pool = []
    for sym in syms:
        rows = _rows(sym)
        if not rows:
            continue
        for i in range(len(rows) - LABEL_W - 1):
            pool.append((rows, i))
    means = []
    for _ in range(n):
        sample = random.choices(pool, k=k)
        means.append(statistics.mean(detlib.outcome(r, si, "long")[1] for r, si in sample))
    return means


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    syms = _syms()
    print(f"vol_awakening_4h 동결 게이트 검증 — {len(syms)}종목 4h")

    sigs = _collect(syms)
    rets = [r for _, r in sigs]
    n = len(rets)
    mean = statistics.mean(rets) if rets else 0
    med = statistics.median(rets) if rets else 0
    sd = statistics.stdev(rets) if n > 1 else 0
    t = mean / (sd / sqrt(n)) if sd > 0 else 0
    p = _pval(t, n - 1) if n > 1 else 1.0
    print(f"\n전체: n={n} mean={mean*100:+.2f}% median={med*100:+.2f}% t={t:.2f} p={p:.4f}")

    boot = _bootstrap(syms, k=max(10, min(30, n)))
    boot_p = sum(1 for b in boot if b >= mean) / len(boot)
    print(f"bootstrap({BOOT_N}회) baseline 초과확률 boot_p={boot_p:.4f}")

    print("\nOOS 4구간:")
    oos_pos = 0
    for i, (d0, d1) in enumerate(OOS_SPLITS, 1):
        rr = [r for d, r in sigs if d0 <= d <= d1]
        m = statistics.mean(rr) if rr else 0
        ok = m > 0 and len(rr) >= 5
        oos_pos += ok
        print(f"  Q{i} ({d0[:7]}~{d1[:7]}): n={len(rr)} mean={m*100:+.2f}% {'O' if ok else 'X'}")

    ok_all = n >= 20 and mean > 0 and med > 0 and boot_p < 0.05 and oos_pos >= 2
    fails = []
    if n < 20: fails.append("n<20")
    if mean <= 0: fails.append("mean<=0")
    if med <= 0: fails.append("median<=0")
    if boot_p >= 0.05: fails.append(f"boot_p={boot_p:.3f}")
    if oos_pos < 2: fails.append(f"OOS {oos_pos}/4")
    verdict = "PASSED" if ok_all else "REJECTED"
    print(f"\n>>> 판정: {verdict}" + (f" ({', '.join(fails)})" if fails else ""))
    json.dump(dict(n=n, mean=mean, median=med, p=p, boot_p=boot_p,
                   oos_pos=oos_pos, verdict=verdict, fails=fails),
              open("_vol_awakening_result.json", "w"), ensure_ascii=False, indent=2,
              default=lambda x: round(float(x), 6))
    return verdict


if __name__ == "__main__":
    main()
