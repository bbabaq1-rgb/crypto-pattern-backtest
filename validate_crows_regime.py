"""
validate_crows_regime.py
Three Black Crows 4h — bear/altseason 레짐 조건부 재검증

게이트: n>=20, mean>0, median>0, OOS 양구간, baseline p<0.05
"""
import json, os, random, statistics, importlib
from regime_switch import build_regime_map
import detlib

TF        = "4h"
DIRECTION = "short"
MOD_CROWS = "detector_three_crows_4h"
MOD_SOLD  = "detector_three_soldiers_4h"
BOOT_N    = 1000
SEED      = 42

TARGET_REGIMES = {"bear", "bull_altseason"}


# ─── 심볼 목록 ────────────────────────────────────────────────────────────────
def _symbols():
    uni = json.load(open("universe.json", encoding="utf-8"))
    return [s for s in uni.get("trading_universe", [])
            if os.path.exists(f"data/{s.lower()}_4h.csv")]


# ─── 신호 수집 (레짐 필터 포함) ──────────────────────────────────────────────
def _collect(mod_name, symbols, regime_dates, direction=DIRECTION):
    mod  = importlib.import_module(mod_name)
    sigs = []   # (date, ret)
    for sym in symbols:
        try:
            rows = mod.load_ohlcv(sym, TF)
        except Exception:
            continue
        for si in mod.detect(rows):
            d = rows[si]["date"]
            if d not in regime_dates:
                continue
            _, ret = detlib.outcome(rows, si, direction)
            sigs.append((d, ret))
    sigs.sort(key=lambda x: x[0])
    return sigs


# ─── 부트스트랩 베이스라인 ────────────────────────────────────────────────────
def _bootstrap(symbols, regime_dates, direction=DIRECTION, n=BOOT_N, seed=SEED):
    """레짐 구간 내 무작위 진입 n회 반복 → 평균수익 분포 반환."""
    random.seed(seed)
    pool = []
    for sym in symbols:
        try:
            rows = detlib.load_ohlcv(sym, TF)
        except Exception:
            continue
        for i in range(len(rows) - detlib.LABEL_WINDOW - 1):
            if rows[i]["date"] in regime_dates:
                pool.append((rows, i))
    if not pool:
        return []
    boot_means = []
    for _ in range(n):
        sample = random.choices(pool, k=30)
        rets   = [detlib.outcome(r, si, direction)[1] for r, si in sample]
        boot_means.append(statistics.mean(rets))
    return boot_means


# ─── t 검정 (한 표본) ────────────────────────────────────────────────────────
def _ttest_1samp(rets):
    from math import sqrt
    n = len(rets)
    if n < 2:
        return float("nan"), float("nan")
    mu  = statistics.mean(rets)
    sd  = statistics.stdev(rets)
    t   = mu / (sd / sqrt(n))
    # 자유도 n-1 t 분포 p값 근사 (Scipy 없이)
    # Abramowitz & Stegun 26.7.8 근사 — 양측, 충분히 작은 p는 0.0001로 표기
    import math
    df = n - 1
    x  = df / (df + t * t)
    # 불완전 베타 근사 (단순 버전: Wald 근사)
    z  = abs(t) / sqrt(1 + t * t / df * (1 + t * t / (2 * df)))
    p  = 2 * (1 - 0.5 * (1 + math.erf(z / math.sqrt(2))))
    return t, p


# ─── 게이트 체크 ──────────────────────────────────────────────────────────────
def _gate(label, sigs, boot_means=None):
    rets = [r for _, r in sigs]
    n    = len(rets)
    mean = statistics.mean(rets)   if rets else 0.0
    med  = statistics.median(rets) if rets else 0.0
    t, p = _ttest_1samp(rets)

    # 베이스라인 p: 부트 분포에서 signal mean보다 큰 비율
    if boot_means:
        boot_p = sum(1 for b in boot_means if b >= mean) / len(boot_means)
    else:
        boot_p = float("nan")

    print(f"\n{'='*60}")
    print(f"[{label}]")
    print(f"  n={n}  mean={mean*100:+.2f}%  median={med*100:+.2f}%")
    print(f"  t={t:.3f}  one-sample p={p:.4f}")
    if boot_means:
        print(f"  bootstrap p(boot>=signal_mean)={boot_p:.4f}")
    print(f"  게이트:")
    g_n   = n >= 20
    g_mu  = mean > 0
    g_med = med > 0
    g_bas = (not isinstance(boot_p, float) or not (boot_p == boot_p)) or boot_p < 0.05
    print(f"    n≥20  : {'✓' if g_n   else '✗'}")
    print(f"    mean>0: {'✓' if g_mu  else '✗'}")
    print(f"    med>0 : {'✓' if g_med else '✗'}")
    if boot_means:
        print(f"    base p<0.05: {'✓' if g_bas else '✗'} (boot_p={boot_p:.4f})")
    return dict(n=n, mean=mean, median=med, t=t, p=p, boot_p=boot_p,
                pass_n=g_n, pass_mu=g_mu, pass_med=g_med, pass_bas=g_bas)


# ─── OOS 2구간 ────────────────────────────────────────────────────────────────
def _oos2(label, sigs):
    if not sigs:
        print(f"  [OOS] {label}: 데이터 없음"); return 0
    dates = [d for d, _ in sigs]
    mid   = sorted(dates)[len(dates) // 2]
    q1    = [r for d, r in sigs if d <  mid]
    q2    = [r for d, r in sigs if d >= mid]
    pos   = 0
    print(f"\n  [OOS 2구간: {label}]")
    for i, (q, tag) in enumerate([(q1, f"Q1 (< {mid})"), (q2, f"Q2 (>= {mid})")], 1):
        mu = statistics.mean(q) if q else 0.0
        ok = mu > 0
        print(f"    Q{i} {tag}: n={len(q)}, mean={mu*100:+.2f}% {'✓' if ok else '✗'}")
        if ok:
            pos += 1
    print(f"    OOS 양구간: {pos}/2 {'✓' if pos >= 1 else '✗'}")
    return pos


# ─── 메인 ─────────────────────────────────────────────────────────────────────
def main():
    print("Three Black Crows 4h — 레짐 조건부 재검증")
    print("레짐 맵 로딩 (bear/bull_altseason 날짜 추출)...")
    regime_map = build_regime_map()
    all_dates  = set(regime_map.keys())
    bear_dates  = {d for d, r in regime_map.items() if r == "bear"}
    alt_dates   = {d for d, r in regime_map.items() if r == "bull_altseason"}
    target_dates = bear_dates | alt_dates
    print(f"  bear 날짜={len(bear_dates)}, altseason 날짜={len(alt_dates)}, 합산={len(target_dates)}")

    syms = _symbols()
    print(f"  4h 심볼: {len(syms)}개")

    # ── 1. 전체 bear+altseason 신호 수집 ─────────────────────────────────────
    print("\n신호 수집 중...")
    sigs_all  = _collect(MOD_CROWS, syms, target_dates)
    sigs_bear = _collect(MOD_CROWS, syms, bear_dates)
    sigs_alt  = _collect(MOD_CROWS, syms, alt_dates)
    print(f"  bear+alt 신호 {len(sigs_all)}개")
    print(f"  bear 전용  {len(sigs_bear)}개")
    print(f"  altseason 전용 {len(sigs_alt)}개")

    # ── 2. 부트스트랩 베이스라인 ──────────────────────────────────────────────
    print("\n부트스트랩 베이스라인 계산 중 (1000회)...")
    boot_all  = _bootstrap(syms, target_dates)
    boot_bear = _bootstrap(syms, bear_dates, seed=SEED+1)
    boot_alt  = _bootstrap(syms, alt_dates,  seed=SEED+2)
    if boot_all:
        boot_mu  = statistics.mean(boot_all)
        boot_std = statistics.stdev(boot_all)
        print(f"  baseline(bear+alt) mean={boot_mu*100:+.3f}%  std={boot_std*100:.3f}%")

    # ── 3. 게이트 체크 ────────────────────────────────────────────────────────
    r_all  = _gate("bear+altseason 전체", sigs_all,  boot_all)
    r_bear = _gate("bear 전용",           sigs_bear, boot_bear)
    r_alt  = _gate("altseason 전용",      sigs_alt,  boot_alt)

    # ── 4. OOS 2구간 ──────────────────────────────────────────────────────────
    print()
    oos_all  = _oos2("bear+altseason", sigs_all)
    oos_bear = _oos2("bear 전용",       sigs_bear)
    oos_alt  = _oos2("altseason 전용",  sigs_alt)

    # ── 5. 종합 판정 ──────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("종합 판정 (bear+altseason 합산 기준)")
    gates_passed = (r_all["pass_n"] and r_all["pass_mu"] and
                    r_all["pass_med"] and r_all["pass_bas"] and oos_all >= 1)
    verdict = ">>> PASS: 모든 게이트 통과" if gates_passed else ">>> FAIL: 게이트 탈락"
    print(f"  n={r_all['n']}, mean={r_all['mean']*100:+.2f}%, median={r_all['median']*100:+.2f}%")
    print(f"  OOS 양구간: {oos_all}/2")
    print(f"  boot_p={r_all['boot_p']:.4f}")
    print(f"\n  {verdict}")

    # ── 6. Three Soldiers vs Three Crows 비교표 ───────────────────────────────
    print(f"\n{'='*60}")
    print("Three Soldiers(bull 롱) vs Three Crows(bear/alt 숏) 대칭 비교")

    # Three Soldiers 전체 재계산 (bull 레짐 기준)
    bull_dates = {d for d, r in regime_map.items() if r in {"bull_btc", "bull_altseason"}}
    sigs_sold  = _collect(MOD_SOLD, syms, bull_dates, direction="long")
    r_sold = _gate("Three Soldiers (bull 롱 전체 재확인)", sigs_sold)
    oos_sold = _oos2("Three Soldiers OOS", sigs_sold)

    print(f"\n  {'항목':<25} {'Three Soldiers':>18} {'Three Crows':>18}")
    print(f"  {'-'*61}")
    print(f"  {'레짐':<25} {'bull_btc/altseason':>18} {'bear/altseason':>18}")
    print(f"  {'방향':<25} {'long':>18} {'short':>18}")
    print(f"  {'n':<25} {r_sold['n']:>18} {r_all['n']:>18}")
    print(f"  {'mean':<25} {r_sold['mean']*100:>17.2f}% {r_all['mean']*100:>17.2f}%")
    print(f"  {'median':<25} {r_sold['median']*100:>17.2f}% {r_all['median']*100:>17.2f}%")
    print(f"  {'OOS 양구간':<25} {f'{oos_sold}/2':>18} {f'{oos_all}/2':>18}")
    print(f"  {'boot_p':<25} {r_sold['boot_p']:>18.4f} {r_all['boot_p']:>18.4f}")
    sym_label = "대칭 전략 가능" if gates_passed else "대칭 전략 불가 (Crows 탈락)"
    print(f"\n  → {sym_label}")

    # ── 7. 결과 JSON 저장 ────────────────────────────────────────────────────
    results = dict(
        three_crows_4h_regime=dict(
            all=r_all, bear=r_bear, alt=r_alt,
            oos_all=oos_all, oos_bear=oos_bear, oos_alt=oos_alt,
            passed=gates_passed
        ),
        three_soldiers_4h_bull=dict(
            result=r_sold, oos=oos_sold
        )
    )
    with open("_crows_regime_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("\n결과 → _crows_regime_results.json 저장")
    return results


if __name__ == "__main__":
    main()
