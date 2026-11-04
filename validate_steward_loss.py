"""validate_steward_loss.py — R-082 steward 정지 규칙을 손실함수로 재설계 (사전 등록 2026-11-04, registry steward_loss_prereg_2026_11_04).

DEPLOY_ON_PASS=True(backlog). R-080 이 확률 제약(오정지<=15%)으로는 후보가 없다고 했다. 여기서는 제약을 버리고
**기대 손익** 으로 규칙을 비교한다: 정지된 뒤 남은 거래 수 x (-mu) 가 규칙의 손익(정지 안 하면 0).
mu 사전분포는 실거래 이전 백테스트 단위(패턴) 평균(수축 후)만 쓴다 — 실거래 장부 사용 금지.
경로 생성·부트·정지 판정은 validate_steward_v2.sim 과 같은 구조(주 1회 평가, 표본 평균<0 일 때만 발동).
"""
import json
import random
import sys

import numpy as np

import validate_steward_v2 as v2

DEPLOY_ON_PASS = True
SEED = 82
HORIZON_WEEKS = 52
SIMS = 400
BOOT_ITERS = 500
LAMS = [1, 3]
GRID = [-4.0, -3.0, -2.0, -1.0, -0.5, 0.0, 0.5, 1.0, 2.0, 3.0, 4.0, 6.0, 8.0]
MIN_UNIT_N = 40
TAU_FLOOR2 = 0.25          # %^2 — 단위 간 참 분산 하한
DECAY = -1.0               # %p — 백테스트 → 실거래 감쇠 진단(기준 c3 에 사용)
MIN_DETECT = 0.70          # mu=-2%, lam=3 에서 정지 확률 하한(안전 가드)
# 규칙: s1=(최소 n, α 또는 None=부호검사)  s2=(최소 n, α, 최소 기간 일). 결과 전 고정.
RULES = {
    "NEVER": dict(s1=(10 ** 9, None), s2=(10 ** 9, 0.0, 10 ** 9)),
    "C0_current": v2.CANDS["C0_current"],
    "C1": v2.CANDS["C1"], "C2": v2.CANDS["C2"], "C3": v2.CANDS["C3"],
    "L1": dict(s1=(30, 0.20), s2=(30, 0.02, 28)),
    "L2": dict(s1=(15, 0.30), s2=(20, 0.02, 28)),
    "L3": dict(s1=(60, 0.30), s2=(60, 0.05, 56)),
}
CANDIDATES = [k for k in RULES if k not in ("NEVER", "C0_current")]


def snap(x):
    x = min(max(x, GRID[0]), GRID[-1])
    return min(range(len(GRID)), key=lambda i: abs(GRID[i] - x))


def prior_weights(base, shrink=True, shift=0.0):
    """백테스트 거래(dict: pattern, ret) → GRID 위 가중치(합 1). 단위 = 패턴, n>=MIN_UNIT_N."""
    by = {}
    for t in base:
        by.setdefault(t["pattern"], []).append(t["ret"] * 100)
    units = {u: np.asarray(r, float) for u, r in by.items() if len(r) >= MIN_UNIT_N}
    if not units:
        raise ValueError("no units")
    m = np.array([r.mean() for r in units.values()])
    n = np.array([len(r) for r in units.values()], float)
    se2 = np.array([r.var(ddof=1) / len(r) for r in units.values()])
    g = float((m * n).sum() / n.sum())
    tau2 = max(float(m.var(ddof=1) - se2.mean()) if len(m) > 1 else 0.0, TAU_FLOOR2)
    mu = g + (tau2 / (tau2 + se2)) * (m - g) if shrink else m
    w = np.zeros(len(GRID))
    for x in mu + shift:
        w[snap(float(x))] += 1.0
    return w / w.sum(), dict(units=len(units), grand=g, tau2=tau2, mu=sorted(round(float(x), 2) for x in mu))


def sim_path(seed, pool, mu, lam, rules):
    """한 경로 → {규칙: 남은 거래 수(정지 후) 또는 None=정지 없음}, 그리고 첫 정지 시 누적 n."""
    nprng = np.random.default_rng(seed)
    sums, cnts = [], []
    n, s = 0, 0.0
    cum = []
    stop = {k: None for k in rules}
    stop_n = {k: None for k in rules}
    for w in range(HORIZON_WEEKS):
        k = int(nprng.poisson(lam))
        x = float((pool[nprng.integers(0, len(pool), k)] + mu).sum()) if k else 0.0
        sums.append(x); cnts.append(k); n += k; s += x
        cum.append(n)
        if n == 0 or s / n >= 0:
            continue
        cache = {}
        def p():
            if "p" not in cache:
                cache["p"] = v2.boot_p(sums, cnts, nprng, B=BOOT_ITERS)
            return cache["p"]
        for name, r in rules.items():
            if stop[name] is not None:
                continue
            n1, a1 = r["s1"]
            if n >= n1 and (a1 is None or p() < a1):
                stop[name] = w; stop_n[name] = n; continue
            n2, a2, span2 = r["s2"]
            if n >= n2 and w * 7 >= span2 and p() < a2:
                stop[name] = w; stop_n[name] = n
    total = n
    rest = {k: (None if stop[k] is None else total - cum[stop[k]]) for k in rules}
    return rest, stop_n


def simulate(pool, sims=SIMS, seed=SEED, rules=None):
    """반환 pay[rule][lam][mu_idx] = ndarray(sims) 손익(-mu*남은거래), stopped[rule][lam][mu_idx]=정지율."""
    rules = rules or RULES
    pool = np.asarray(pool, float)
    pool = pool - pool.mean()
    rng = random.Random(seed)
    pay = {r: {lam: [] for lam in LAMS} for r in rules}
    stp = {r: {lam: [] for lam in LAMS} for r in rules}
    for lam in LAMS:
        for mu in GRID:
            pp = {r: np.zeros(sims) for r in rules}
            ss = {r: 0 for r in rules}
            for i in range(sims):
                rest, _ = sim_path(rng.randrange(1 << 31), pool, mu, lam, rules)
                for r, x in rest.items():
                    if x is not None:
                        pp[r][i] = -mu * x
                        ss[r] += 1
            for r in rules:
                pay[r][lam].append(pp[r]); stp[r][lam].append(ss[r] / sims)
    return pay, stp


def J(pay, rule, w, lams=LAMS):
    return float(np.mean([sum(w[j] * pay[rule][lam][j].mean() for j in range(len(GRID))) for lam in lams]))


def diff_ci(pay, a, b, w, B=1000, seed=SEED):
    """J(a)-J(b) 의 점추정과 2.5%/97.5% — 셀 안에서 경로 인덱스를 규칙 간 공유 재표집(짝지음)."""
    rng = np.random.default_rng(seed)
    sims = len(pay[a][LAMS[0]][0])
    d = {lam: [pay[a][lam][j] - pay[b][lam][j] for j in range(len(GRID))] for lam in LAMS}
    pt = float(np.mean([sum(w[j] * d[lam][j].mean() for j in range(len(GRID))) for lam in LAMS]))
    out = np.empty(B)
    for bi in range(B):
        tot = 0.0
        for lam in LAMS:
            for j in range(len(GRID)):
                if w[j] > 0:
                    idx = rng.integers(0, sims, sims)
                    tot += w[j] * d[lam][j][idx].mean()
        out[bi] = tot / len(LAMS)
    return pt, float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5))


def judge(pay, stp, w_main, w_raw, w_decay):
    """판정 — 코드가 낸다. ADOPT:<규칙> | CURRENT_RETAINED."""
    j = {r: J(pay, r, w_main) for r in RULES}
    best = max(CANDIDATES, key=lambda r: j[r])
    pt, lo, hi = diff_ci(pay, best, "C0_current", w_main)
    c = {}
    c["c1_ci_positive"] = lo > 0
    c["c2_both_lam"] = all(J(pay, best, w_main, [lam]) > J(pay, "C0_current", w_main, [lam]) for lam in LAMS)
    c["c3_raw_and_decay"] = (J(pay, best, w_raw) > J(pay, "C0_current", w_raw)
                             and J(pay, best, w_decay) > J(pay, "C0_current", w_decay))
    c["c4_detect"] = stp[best][3][GRID.index(-2.0)] >= MIN_DETECT
    c["c5_beats_never"] = j[best] > 0
    ok = all(c.values())
    return dict(verdict=(f"ADOPT:{best}" if ok else "CURRENT_RETAINED"), best=best, J=j, diff=(pt, lo, hi),
                criteria=c, never_best=max(j[r] for r in CANDIDATES + ["C0_current"]) <= 0)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    import detlib
    import method_t as mt
    import regime_switch as rs
    import validate_portfolio as vp
    from validate_regime_split import turnover_rank
    print("R-082 steward 정지 규칙 손실함수 재설계 (사전 등록 2026-11-04)")
    syms = json.load(open("universe.json", encoding="utf-8"))["trading_universe"]
    if "--no-fetch" not in argv:
        vp.fetch(syms)
    rows_4h = {}
    for s in syms:
        try:
            rows_4h[s] = detlib.load_ohlcv(s, "4h")
        except (FileNotFoundError, RuntimeError):
            continue
    ranked = turnover_rank(rows_4h)
    mt.REGMAP = rs.build_regime_map()
    base = vp.collect_1d(syms) + vp.collect_4h(rows_4h, ranked, mt.REGMAP)
    pool = [t["ret"] * 100 for t in base]
    w_main, info = prior_weights(base)
    w_raw, _ = prior_weights(base, shrink=False)
    w_decay, _ = prior_weights(base, shift=DECAY)
    print(f"거래 {len(base)} 풀 sd {np.std(pool):.2f}% 사전 {info}")
    pay, stp = simulate(pool)
    res = judge(pay, stp, w_main, w_raw, w_decay)
    print("규칙별 J(주 사전) / raw / decay / lam1 / lam3 / mu=-2 정지율(lam3) / mu=+1 정지율(lam3)")
    for r in RULES:
        print(f"  {r:11} {res['J'][r]:+9.2f} {J(pay, r, w_raw):+9.2f} {J(pay, r, w_decay):+9.2f} "
              f"{J(pay, r, w_main, [1]):+9.2f} {J(pay, r, w_main, [3]):+9.2f} "
              f"{stp[r][3][GRID.index(-2.0)]:.2f} {stp[r][3][GRID.index(1.0)]:.2f}")
    print(f"최선 후보 {res['best']} - 현행: {res['diff'][0]:+.2f} CI [{res['diff'][1]:+.2f},{res['diff'][2]:+.2f}] 기준 {res['criteria']}")
    print(f"NEVER 가 모든 규칙 이상: {res['never_best']}")
    print(f"\n판정: {res['verdict']}")
    json.dump(dict(prereg="steward_loss_prereg_2026_11_04", verdict=res["verdict"], best=res["best"], J=res["J"],
                   diff=res["diff"], criteria=res["criteria"], never_best=res["never_best"], prior=info,
                   weights=dict(main=list(w_main), raw=list(w_raw), decay=list(w_decay)),
                   J_raw={r: J(pay, r, w_raw) for r in RULES}, J_decay={r: J(pay, r, w_decay) for r in RULES},
                   stop={r: {str(l): stp[r][l] for l in LAMS} for r in RULES}, grid=GRID),
              open("_steward_loss.json", "w"), indent=1, ensure_ascii=False, default=str)


if __name__ == "__main__":
    main()
