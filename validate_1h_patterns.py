"""
validate_1h_patterns.py
1h 전용 패턴 발굴 — 풀 파이프라인 (게이트 + OOS 4구간 + 베이스라인)

패턴 목록:
  three_soldiers_1h, three_crows_1h
  engulfing_1h, inverted_hammer_1h, fvg_1h
  gartley_1h, bat_1h, butterfly_1h
  vwap_rev_long_1h, vwap_rev_short_1h
  breakout_retest_1h

게이트 동결: n>=20, mean>0, median>0, OOS 양구간>=2, baseline_p<0.05
"""
import os, glob, csv, json, random, statistics, importlib
from datetime import datetime, timezone
from math import sqrt, erf

import detlib
from detector_harmonic_base import detect_harmonic, find_pivots

TF   = "1h"
SEED = 42
BOOT_N = 1000
LABEL_W = detlib.LABEL_WINDOW  # 20봉

# OOS 4구간 경계 (1h 데이터는 날짜로 분할)
OOS_SPLITS = [
    ("2021-01-01", "2022-08-10"),
    ("2022-08-11", "2024-01-11"),
    ("2024-01-12", "2025-05-10"),
    ("2025-05-11", "2026-12-31"),
]

HARMONIC_CFG = {
    "gartley":   {"ab_xa":(0.568,0.668),"bc_ab":(0.382,0.886),"cd_bc":(1.272,1.618),"ad_xa":(0.736,0.836)},
    "bat":       {"ab_xa":(0.382,0.500),"bc_ab":(0.382,0.886),"cd_bc":(1.618,2.618),"ad_xa":(0.836,0.936)},
    "butterfly": {"ab_xa":(0.736,0.836),"bc_ab":(0.382,0.886),"cd_bc":(1.618,2.618),"ad_xa":(1.222,1.322)},
}

# ── 심볼 목록 ────────────────────────────────────────────────────────────────
def _syms():
    return sorted({
        os.path.basename(f)[:-7].upper()
        for f in glob.glob("data/*_1h.csv")
    })

# ── p값 근사 (scipy 없이) ───────────────────────────────────────────────────
def _pval(t, df):
    z = abs(t) / sqrt(1 + t*t/df)
    return 2*(1 - 0.5*(1 + erf(z/sqrt(2))))

# ── 신호 수집 (모든 심볼) ─────────────────────────────────────────────────────
def _collect(detect_fn, direction, syms=None, date_from=None, date_to=None):
    if syms is None:
        syms = _syms()
    rets = []
    for sym in syms:
        try:
            rows = detlib.load_ohlcv(sym, TF)
        except Exception:
            continue
        for si in detect_fn(rows):
            d = rows[si]["date"]
            if date_from and d < date_from:
                continue
            if date_to and d > date_to:
                continue
            _, ret = detlib.outcome(rows, si, direction)
            rets.append((d, ret))
    return rets   # [(date, ret)]

# ── 부트스트랩 베이스라인 ────────────────────────────────────────────────────
def _bootstrap(direction, syms, k=30, n=BOOT_N, seed=SEED):
    random.seed(seed)
    pool = []
    for sym in syms:
        try:
            rows = detlib.load_ohlcv(sym, TF)
        except Exception:
            continue
        for i in range(len(rows) - LABEL_W - 1):
            pool.append((rows, i))
    if not pool:
        return 0.5
    actual_k = min(k, len(pool))
    boot_means = []
    for _ in range(n):
        sample = random.choices(pool, k=actual_k)
        rets   = [detlib.outcome(r, si, direction)[1] for r, si in sample]
        boot_means.append(statistics.mean(rets))
    return boot_means

# ── 게이트 평가 ───────────────────────────────────────────────────────────────
def _gate(name, sigs, direction, syms, verbose=True):
    rets = [r for _, r in sigs]
    n    = len(rets)
    mean = statistics.mean(rets)   if rets else 0.0
    med  = statistics.median(rets) if rets else 0.0

    # t 검정
    if n >= 2:
        sd = statistics.stdev(rets)
        t  = mean / (sd / sqrt(n)) if sd > 0 else 0.0
        p  = _pval(t, n-1)
    else:
        t, p = 0.0, 1.0

    # 부트스트랩 베이스라인
    boot = _bootstrap(direction, syms, k=max(10, min(30, n)))
    boot_p = sum(1 for b in boot if b >= mean) / len(boot) if boot else 0.5

    if verbose:
        print(f"\n  [{name}]  n={n}  mean={mean*100:+.2f}%  median={med*100:+.2f}%")
        print(f"    t={t:.3f} p={p:.4f} | boot_p={boot_p:.4f}")
        g_n  = "✓" if n>=20     else "✗"
        g_mu = "✓" if mean>0    else "✗"
        g_md = "✓" if med>0     else "✗"
        g_bp = "✓" if boot_p<0.05 else "✗"
        print(f"    게이트: n≥20{g_n} mean{g_mu} med{g_md} boot_p<0.05{g_bp}")

    return dict(n=n, mean=mean, median=med, t=t, p=p, boot_p=boot_p,
                ok=n>=20 and mean>0 and med>0 and boot_p<0.05)

# ── OOS 4구간 ────────────────────────────────────────────────────────────────
def _oos4(detect_fn, direction, syms, verbose=True):
    results = []
    pos_count = 0
    for i, (d0, d1) in enumerate(OOS_SPLITS, 1):
        sigs = _collect(detect_fn, direction, syms, date_from=d0, date_to=d1)
        rets = [r for _, r in sigs]
        n    = len(rets)
        mean = statistics.mean(rets) if rets else 0.0
        ok   = mean > 0 and n >= 5
        if ok:
            pos_count += 1
        results.append(dict(q=i, d0=d0, d1=d1, n=n, mean=mean, ok=ok))
        if verbose:
            mark = "✓" if ok else "✗"
            print(f"    OOS Q{i} ({d0}~{d1[:7]}): n={n} mean={mean*100:+.2f}% {mark}")
    if verbose:
        print(f"    OOS 양구간: {pos_count}/4")
    return pos_count, results

# ── 단일 패턴 풀 파이프라인 ───────────────────────────────────────────────────
def run_pattern(label, detect_fn, direction, syms):
    print(f"\n{'='*64}")
    print(f"패턴: {label}  방향={direction}")
    sigs = _collect(detect_fn, direction, syms)
    g    = _gate(label, sigs, direction, syms)
    if g["n"] < 20:
        print(f"  -> FAIL (n={g['n']}<20 표본 부족, OOS 생략)")
        return dict(pattern=label, direction=direction, **g,
                    oos_pos=0, verdict="REJECTED", reason="표본부족")

    print(f"  OOS 4구간:")
    oos_pos, oos_detail = _oos4(detect_fn, direction, syms)

    all_ok = g["ok"] and oos_pos >= 2
    verdict = "PASSED" if all_ok else "REJECTED"
    reason  = ""
    if not all_ok:
        fails = []
        if g["n"] < 20: fails.append("n<20")
        if g["mean"] <= 0: fails.append("mean<=0")
        if g["median"] <= 0: fails.append("median<=0")
        if g["boot_p"] >= 0.05: fails.append(f"boot_p={g['boot_p']:.3f}")
        if oos_pos < 2: fails.append(f"OOS {oos_pos}/4<2")
        reason = ", ".join(fails)

    print(f"\n  판정: >>> {verdict}" + (f" ({reason})" if reason else ""))
    return dict(pattern=label, direction=direction, **g,
                oos_pos=oos_pos, verdict=verdict, reason=reason)

# ── 메인 ─────────────────────────────────────────────────────────────────────
def main():
    syms = _syms()
    print(f"1h 패턴 풀 파이프라인 검증")
    print(f"심볼: {len(syms)}개, OOS 4구간, 부트스트랩 {BOOT_N}회")
    print(f"게이트: n>=20, mean>0, median>0, boot_p<0.05, OOS>=2")

    results = []

    # ── Three Soldiers 1h ─────────────────────────────────────────────────
    import detector_three_soldiers_1h as ts1
    results.append(run_pattern("three_soldiers_1h", ts1.detect, "long", syms))

    # ── Three Crows 1h ────────────────────────────────────────────────────
    import detector_three_crows_1h as tc1
    results.append(run_pattern("three_crows_1h", tc1.detect, "short", syms))

    # ── Engulfing 1h ──────────────────────────────────────────────────────
    import detector_engulfing as eng
    results.append(run_pattern("engulfing_1h", eng.detect, "long", syms))

    # ── Inverted Hammer 1h ────────────────────────────────────────────────
    import detector_inverted_hammer as ih
    results.append(run_pattern("inverted_hammer_1h", ih.detect, "long", syms))

    # ── FVG 1h (롱/숏 각각) ──────────────────────────────────────────────
    import detector_fvg as fvg_mod
    fvg_long_sigs_all  = _collect(fvg_mod.detect, "long",  syms)
    fvg_short_sigs_all = _collect(fvg_mod.detect, "short", syms)
    # fvg.detect는 방향 구분 없이 same detect() 사용 — direction으로 라벨 반전
    results.append(run_pattern("fvg_long_1h",  fvg_mod.detect, "long",  syms))
    results.append(run_pattern("fvg_short_1h", fvg_mod.detect, "short", syms))

    # ── Harmonic 1h (Gartley / Bat / Butterfly) ──────────────────────────
    for pat_name, cfg in HARMONIC_CFG.items():
        def _make_detect(c):
            def detect_fn(rows):
                return detect_harmonic(rows, c)
            return detect_fn
        results.append(run_pattern(f"{pat_name}_1h",
                                   _make_detect(cfg), "long", syms))

    # ── VWAP 이탈복귀 1h ──────────────────────────────────────────────────
    import detector_vwap_rev_long_1h  as vl1
    import detector_vwap_rev_short_1h as vs1
    results.append(run_pattern("vwap_rev_long_1h",  vl1.detect,  "long",  syms))
    results.append(run_pattern("vwap_rev_short_1h", vs1.detect,  "short", syms))

    # ── Breakout+Retest 1h ────────────────────────────────────────────────
    import detector_breakout_retest_1h as br1
    results.append(run_pattern("breakout_retest_1h", br1.detect, "long", syms))

    # ── 종합 요약 ─────────────────────────────────────────────────────────
    print(f"\n{'='*64}")
    print("종합 요약")
    print(f"{'패턴':<25} {'n':>6} {'mean':>8} {'median':>8} {'OOS':>6} {'boot_p':>8} {'판정':>10}")
    print(f"{'-'*73}")
    passed = []
    for r in results:
        verdict = r.get("verdict", "REJECTED")
        mark    = "PASS" if verdict == "PASSED" else "FAIL"
        print(f"{r['pattern']:<25} {r.get('n',0):>6} "
              f"{r.get('mean',0)*100:>+7.2f}% "
              f"{r.get('median',0)*100:>+7.2f}% "
              f"{r.get('oos_pos',0):>3}/4"
              f"  {r.get('boot_p',1.0):>7.4f}"
              f"  {mark:>10}"
              + (f"  [{r.get('reason','')}]" if r.get("reason") else ""))
        if verdict == "PASSED":
            passed.append(r)

    print(f"\n통과: {len(passed)}개 / {len(results)}개")
    if passed:
        for r in passed:
            print(f"  -> {r['pattern']} ({r['direction']}) "
                  f"n={r['n']} mean={r['mean']*100:+.2f}% OOS={r['oos_pos']}/4")

    with open("_1h_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("\n결과 -> _1h_results.json 저장")
    return results


if __name__ == "__main__":
    main()
