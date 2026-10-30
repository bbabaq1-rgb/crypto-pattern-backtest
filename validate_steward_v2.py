"""validate_steward_v2.py — R-080 steward 규칙 개정 후보의 작동 특성 (사전 등록 2026-10-30, registry steward_v2_prereg_2026_10_30).

DEPLOY_ON_PASS=False. R-062 의 몬테카를로(validate_steward_char.part_b 와 같은 풀·같은 경로 생성)를
후보 규칙 3개 + 현행에 대해 같은 난수열로 돌린다. 후보 문턱은 아래 CANDS 에 결과 전 고정.
"""
import json
import random
import statistics as stt
import sys

import numpy as np

import steward as sw

DEPLOY_ON_PASS = False
SEED = 80
HORIZON_WEEKS = 52
SIMS = 400
BOOT_B = 300
MUS = [-2.0, -1.0, 0.0, 0.5, 1.0, 2.0]
LAMS = [1, 3]
# 규칙: s1=(최소 n, α 또는 None=부호검사)  s2=(최소 n, α, 최소 기간 일)
CANDS = {
    "C0_current": dict(s1=(10, None), s2=(20, 0.05, 28)),
    "C1": dict(s1=(20, 0.20), s2=(20, 0.005, 28)),
    "C2": dict(s1=(30, 0.10), s2=(30, 0.002, 28)),
    "C3": dict(s1=(40, 0.20), s2=(40, 0.01, 56)),
}
ORDER = ("C1", "C2", "C3")  # 통과 시 앞선 것을 택한다(변경이 작은 순)
Q1_MAX, Q2_MIN, Q2_MED, Q3_MAX, Q4_MAX = 0.15, 0.80, 40, 0.05, 0.20


def boot_p(sums, cnts, nprng, B=BOOT_B):
    a = np.array(sums, float); c = np.array(cnts, float)
    m = c > 0
    a, c = a[m], c[m]
    idx = nprng.integers(0, len(a), (B, len(a)))
    bm = a[idx].sum(1) / c[idx].sum(1)
    return float((bm >= 0).mean())


def sim_once(seed, pool, mu, lam, rules):
    """한 경로에 모든 후보를 같은 거래열로 적용. 반환 {cand: (s1 정지 (주,n)|None, s2 정지|None)}."""
    nprng = np.random.default_rng(seed)
    sums, cnts = [], []
    n, s = 0, 0.0
    st = {k: [None, None] for k in rules}
    for w in range(HORIZON_WEEKS):
        k = int(nprng.poisson(lam))
        x = float((pool[nprng.integers(0, len(pool), k)] + mu).sum()) if k else 0.0
        sums.append(x); cnts.append(k); n += k; s += x
        if n == 0:
            continue
        mean = s / n
        if mean >= 0:
            continue  # 단측 검정: 표본 평균이 0 이상이면 어느 규칙도 발동하지 않는다
        cache = {}
        def p():
            if "p" not in cache:
                cache["p"] = boot_p(sums, cnts, nprng)
            return cache["p"]
        for name, r in rules.items():
            n1, a1 = r["s1"]
            if st[name][0] is None and n >= n1 and (a1 is None or p() < a1):
                st[name][0] = (w, n)
            n2, a2, span2 = r["s2"]
            if st[name][1] is None and n >= n2 and w * 7 >= span2 and p() < a2:
                st[name][1] = (w, n)
    return st


def part_b(pool, sims=SIMS, seed=SEED, rules=None):
    rules = rules or CANDS
    pool = np.asarray(pool, float)
    pool = pool - pool.mean()
    rng = random.Random(seed)
    res = {}
    for lam in LAMS:
        for mu in MUS:
            acc = {c: dict(u=0, v=0, ns=[]) for c in rules}
            for _ in range(sims):
                st = sim_once(rng.randrange(1 << 31), pool, mu, lam, rules)
                for c, (s1, s2) in st.items():
                    first = [x for x in (s1, s2) if x]
                    if first:
                        acc[c]["u"] += 1
                        acc[c]["ns"].append(min(first)[1])
                    acc[c]["v"] += s2 is not None
            for c, a in acc.items():
                res[(c, lam, mu)] = dict(p_u=a["u"] / sims, p_v=a["v"] / sims,
                                         med_n=(stt.median(a["ns"]) if a["ns"] else None))
    return res


def judge_cand(b, c):
    """후보 하나의 실패 항목 목록."""
    f = []
    if b[(c, 3, 1.0)]["p_u"] > Q1_MAX:
        f.append("Q1_FALSE_STOP_U")
    d = b[(c, 3, -2.0)]
    if d["p_u"] < Q2_MIN:
        f.append("Q2a_MISS")
    if d["med_n"] is None or d["med_n"] > Q2_MED:
        f.append("Q2b_SLOW")
    if b[(c, 3, 1.0)]["p_v"] > Q3_MAX:
        f.append("Q3_FALSE_STOP_V")
    if b[(c, 1, 1.0)]["p_u"] > Q4_MAX:
        f.append("Q4_FALSE_STOP_LOW_FREQ")
    return f


def verdict(b):
    fails = {c: judge_cand(b, c) for c in CANDS}
    ok = [c for c in ORDER if not fails[c]]
    if ok:
        return f"V2_ADOPTABLE:{ok[0]}", fails
    safe = [c for c in ORDER if not (set(fails[c]) & {"Q1_FALSE_STOP_U", "Q3_FALSE_STOP_V", "Q4_FALSE_STOP_LOW_FREQ"})]
    if safe:
        return "TRADEOFF_FALSE_STOP_FIXED_DETECTION_SLOW:" + ",".join(safe), fails
    return "NO_CANDIDATE", fails


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    import detlib
    import method_t as mt
    import regime_switch as rs
    import validate_portfolio as vp
    from validate_regime_split import turnover_rank
    print("R-080 steward 규칙 개정 후보 작동 특성 (사전 등록 2026-10-30)")
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
    regmap = rs.build_regime_map()
    mt.REGMAP = regmap
    base = vp.collect_1d(syms) + vp.collect_4h(rows_4h, ranked, regmap)
    pool = [t["ret"] * 100 for t in base]
    print(f"거래 {len(base)} 풀 sd {np.std(pool):.2f}%")
    b = part_b(pool)
    print("후보 lam mu  P(U정지) P(V=S2만) 정지시 n 중앙")
    for (c, lam, mu), v in b.items():
        med = f"{v['med_n']:.0f}" if v["med_n"] is not None else "-"
        print(f"  {c:11} {lam} {mu:+4.1f}%  {v['p_u']:.3f}  {v['p_v']:.3f}  {med}")
    ver, fails = verdict(b)
    for c in CANDS:
        print(f"  {c}: {fails[c] or 'PASS'}")
    print(f"\n판정: {ver}")
    json.dump(dict(prereg="steward_v2_prereg_2026_10_30", verdict=ver, fails=fails, pool_sd=float(np.std(pool)),
                   part_b={f"{k[0]}|{k[1]}|{k[2]}": v for k, v in b.items()}),
              open("_steward_v2.json", "w"), indent=1, ensure_ascii=False, default=str)


if __name__ == "__main__":
    main()
