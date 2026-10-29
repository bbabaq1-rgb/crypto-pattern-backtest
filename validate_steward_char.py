"""validate_steward_char.py — R-062 운용 규칙(S1·S2) 작동 특성 (사전 등록 2026-10-29, registry steward_char_prereg_2026_10_29).

진단 전용(DEPLOY_ON_PASS=False). steward.judge 를 그대로 import 해 규칙 상수를 바꾸지 않고
파트 A(백테스트 거래열 순차 적용)와 파트 B(합성 몬테카를로)로 오정지율·탐지 속도를 잰다.
"""
import json
import random
import statistics as stt
import sys
from datetime import date

import numpy as np

import steward as sw

DEPLOY_ON_PASS = False
SEED = 62
HORIZON_WEEKS = 52
SIMS = 400
BOOT_A = 2000
BOOT_B = 300
MUS = [-2.0, -1.0, -0.5, 0.0, 0.5, 1.0, 2.0]
LAMS = [1, 3]
V_UNITS = ("triple_bottom_4h", "vol_awakening_4h")  # steward.CONFIRMED 의 4h 두 패턴
SPLIT = date(2025, 1, 1)
Q2_MAX, Q3_MIN, Q3_MED, Q4_MAX = 0.25, 0.80, 40, 0.05


def day_of(t):
    return date.fromordinal(int(t))


def tier_for(unit):
    return "V" if unit in V_UNITS else "U"


def s2_pre(n, mean, span):
    return n >= sw.S2_MIN_N and mean < 0 and span >= sw.S2_MIN_SPAN_DAYS


def run_unit(trades, tier, boot_n=BOOT_A):
    """한 단위의 거래(t_in,t_out,ret)를 t_out 순으로 순차 적용. 주 1회 평가. 첫 정지 반환."""
    seq = sorted(trades, key=lambda t: t["t_out"])
    n, s = 0, 0.0
    first = None
    rows = []
    last_wk = None
    stop = None
    for i, t in enumerate(seq):
        d_in, d_out = day_of(t["t_in"]), day_of(t["t_out"])
        r = t["ret"] * 100
        n += 1; s += r
        first = d_in if first is None or d_in < first else first
        rows.append({"entry_date": d_in.isoformat(), "return_pct": r})
        wk = d_out.isocalendar()[:2]
        if wk == last_wk:
            continue
        last_wk = wk
        mean = s / n
        span = (d_out - first).days
        st = dict(n=n, mean=mean, span=span, p=None)
        if s2_pre(n, mean, span):
            st["p"] = sw.cluster_boot_p(rows, B=boot_n)
        hits = sw.judge(tier, st)
        if hits:
            stop = dict(rule="+".join(hits), at=i + 1, date=d_out.isoformat(), mean=mean)
            break
    rest = seq[stop["at"]:] if stop else []
    return stop, dict(n_rest=len(rest), mean_rest=(sum(t["ret"] for t in rest) / len(rest) * 100) if rest else None)


def part_a(base):
    by = {}
    for t in base:
        by.setdefault(t["pattern"], []).append(t)
    out = {}
    cut = (SPLIT.toordinal())
    for u, tr in sorted(by.items()):
        tier = tier_for(u)
        stop, rest = run_unit(tr, tier)
        ho = [t["ret"] * 100 for t in tr if t["t_in"] >= cut]
        full = sum(t["ret"] for t in tr) / len(tr) * 100
        cls = "NEVER_STOPPED"
        if stop:
            if tier == "V":
                cls = "V_STOPPED"
            elif rest["mean_rest"] is None:
                cls = "STOPPED_NO_REST"
            else:
                cls = "CORRECT_STOP" if rest["mean_rest"] < 0 else "FALSE_STOP"
        out[u] = dict(tier=tier, n=len(tr), mean=full, holdout_n=len(ho),
                      holdout_mean=(sum(ho) / len(ho)) if ho else None, stop=stop, rest=rest, cls=cls)
    return out


def sim_once(rng, pool, mu, lam):
    """합성 한 경로. 반환: (S1 정지 주 또는 None, S2 정지 주 또는 None, 각 정지 시점 거래 수)."""
    nprng = np.random.default_rng(rng.randrange(1 << 31))
    sums, cnts = [], []
    n, s = 0, 0.0
    s1 = s2 = None
    for w in range(HORIZON_WEEKS):
        k = int(nprng.poisson(lam))
        if k:
            x = pool[nprng.integers(0, len(pool), k)] + mu
            sums.append(float(x.sum())); cnts.append(k)
            n += k; s += float(x.sum())
        else:
            sums.append(0.0); cnts.append(0)
        if n == 0:
            continue
        mean = s / n
        if s1 is None and n >= sw.S1_MIN_N and mean < 0:
            s1 = (w, n)
        span = w * 7
        if s2 is None and s2_pre(n, mean, span):
            a = np.array(sums); c = np.array(cnts)
            m = c > 0
            a, c = a[m], c[m]
            idx = nprng.integers(0, len(a), (BOOT_B, len(a)))
            bm = a[idx].sum(1) / c[idx].sum(1)
            if (bm >= 0).mean() < sw.S2_ALPHA:
                s2 = (w, n)
        if s1 and s2:
            break
    return s1, s2


def part_b(pool, sims=SIMS, seed=SEED):
    pool = np.asarray(pool, float)
    pool = pool - pool.mean()
    res = {}
    rng = random.Random(seed)
    for lam in LAMS:
        for mu in MUS:
            p1 = p2 = pany = 0
            ns = []
            for _ in range(sims):
                s1, s2 = sim_once(rng, pool, mu, lam)
                p1 += s1 is not None; p2 += s2 is not None
                first = [x for x in (s1, s2) if x]
                if first:
                    pany += 1
                    ns.append(min(first)[1])
            res[(lam, mu)] = dict(p_s1=p1 / sims, p_s2=p2 / sims, p_any=pany / sims,
                                  med_n=(stt.median(ns) if ns else None))
    return res


def verdict(a, b):
    fails = []
    if any(v["cls"] == "V_STOPPED" for v in a.values()):
        fails.append("V_FALSE_STOP")
    if b[(3, 1.0)]["p_s1"] > Q2_MAX:
        fails.append("S1_OVERTRIGGER")
    d = b[(3, -2.0)]
    if d["p_any"] < Q3_MIN or d["med_n"] is None or d["med_n"] > Q3_MED:
        fails.append("SLOW_DETECTION")
    if b[(3, 1.0)]["p_s2"] > Q4_MAX:
        fails.append("S2_MISCALIBRATED")
    return ("|".join(fails) if fails else "RULES_OK"), fails


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    import detlib
    import method_t as mt
    import regime_switch as rs
    import validate_portfolio as vp
    from validate_regime_split import turnover_rank
    print("=" * 90)
    print("R-062 운용 규칙(S1·S2) 작동 특성 (사전 등록 2026-10-29)")
    print("=" * 90)
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
    base = sorted(vp.collect_1d(syms) + vp.collect_4h(rows_4h, ranked, regmap), key=lambda t: t["t_in"])
    print(f"거래 {len(base)}")
    # 순서: t_in 은 ordinal 기반 실수라 day_of 가 그대로 동작해야 한다(validate_portfolio._tnum 계약)
    a = part_a(base)
    print("\n[파트 A] 단위 | 등급 | n | 전체평균 | 홀드아웃 | 첫 정지 | 잔여평균 | 분류")
    for u, v in a.items():
        stp = f"{v['stop']['rule']}@n={v['stop']['at']} {v['stop']['date']}" if v["stop"] else "-"
        rm = f"{v['rest']['mean_rest']:+.2f}%(n={v['rest']['n_rest']})" if v["rest"]["mean_rest"] is not None else "-"
        ho = f"{v['holdout_mean']:+.2f}%" if v["holdout_mean"] is not None else "-"
        print(f"  {u:22} {v['tier']} n={v['n']:5} {v['mean']:+6.2f}% {ho:>8} {stp:28} {rm:>16} {v['cls']}")
    pool = [t["ret"] * 100 for t in base]
    print(f"\n[파트 B] 풀 sd {np.std(pool):.2f}% 몬테카를로 {SIMS}회 x {HORIZON_WEEKS}주")
    b = part_b(pool)
    print("  lam  mu     P(S1)  P(S2)  P(any)  정지시 거래수 중앙")
    for (lam, mu), v in b.items():
        med = f"{v['med_n']:.0f}" if v["med_n"] is not None else "-"
        print(f"  {lam:3} {mu:+5.1f}%  {v['p_s1']:.3f}  {v['p_s2']:.3f}  {v['p_any']:.3f}   {med}")
    ver, fails = verdict(a, b)
    print(f"\n판정: {ver}")
    json.dump(dict(prereg="steward_char_prereg_2026_10_29", verdict=ver, fails=fails, part_a=a,
                   part_b={f"{k[0]}|{k[1]}": v for k, v in b.items()}, pool_sd=float(np.std(pool))),
              open("_steward_char.json", "w"), indent=1, ensure_ascii=False, default=str)


if __name__ == "__main__":
    main()
