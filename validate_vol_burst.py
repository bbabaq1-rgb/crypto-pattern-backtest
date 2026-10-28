"""validate_vol_burst.py — R-072 vol_awakening_4h 체결 선택 편향 (사전 등록 2026-10-28).

진단 전용(DEPLOY_ON_PASS=False). R-063 에서 체결된 vol_awakening 평균 -0.55% vs 전체 +0.86% 였다.
가설: 진입 시점 동시성(그 시각에 열려 있는 다른 거래 수)이 클수록 vol_awakening_4h 거래 수익이 낮다.
거래 집합은 validate_portfolio(방식D+레짐청산) 그대로, 동시성은 **시뮬레이터와 무관한 데이터 값**:
c_open = t_in 에 열려 있는(t_in_j <= t_in < t_out_j) 전체 배포 집합 거래 수(자기 제외).
판정(사전 고정, 전부 충족해야 SELECTION_BIAS_*): S1 전체 Spearman rho(c_open, ret) < 0 이고 월 블록 부트 P(rho>=0) < .10 /
S2 train·holdout(2025-01-01) 둘 다 rho < 0 / S3 두 분할 모두 상위 3분위 평균 < 하위 3분위 평균 /
S4 전체에서 3분위 평균이 하위>=중위>=상위. 통과 시 월 내 demean rho<0 이고 부트 P<.10 이면 SELECTION_BIAS_WITHIN_MONTH
아니면 SELECTION_BIAS_TIME_EFFECT. 하나라도 실패면 NO_SELECTION_BIAS.
진단(판정 아님): 같은 날 버스트 순번, G0 시뮬 체결 시점 오픈 수.
"""
import bisect
import json
import math
import random
import sys
from datetime import date

import validate_gap as g
import validate_portfolio as vp

DEPLOY_ON_PASS = False
TARGET = "vol_awakening_4h"
SEED = 72
BOOT_N = 1000
P_BOOT = 0.10


def mean(xs):
    return sum(xs) / len(xs) if xs else None


def c_open_all(trades):
    """각 거래의 진입 시점 동시 보유 수(자기 제외) — 데이터만 사용, 시뮬레이터 무관."""
    ins = sorted(t["t_in"] for t in trades)
    outs = sorted(t["t_out"] for t in trades)
    res = []
    for t in trades:
        n = bisect.bisect_right(ins, t["t_in"]) - bisect.bisect_right(outs, t["t_in"])
        if t["t_out"] > t["t_in"]:
            n -= 1
        res.append(n)
    return res


def burst_ordinal(trades):
    """target 거래의 같은 날(UTC) 내 진입 순번(0부터). 키: (t_in, sym)."""
    day = {}
    for i, t in enumerate(trades):
        day.setdefault(math.floor(t["t_in"]), []).append(i)
    out = {}
    for ids in day.values():
        ids.sort(key=lambda i: (trades[i]["t_in"], trades[i]["sym"]))
        for k, i in enumerate(ids):
            out[i] = k
    return out


def _ranks(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def spearman(x, y):
    if len(x) < 3:
        return None
    rx, ry = _ranks(x), _ranks(y)
    mx_, my_ = mean(rx), mean(ry)
    sxy = sum((a - mx_) * (b - my_) for a, b in zip(rx, ry))
    sxx = sum((a - mx_) ** 2 for a in rx)
    syy = sum((b - my_) ** 2 for b in ry)
    if sxx <= 0 or syy <= 0:
        return None
    return sxy / math.sqrt(sxx * syy)


def month_key(t_in):
    d = date.fromordinal(int(t_in))
    return d.year * 12 + d.month


def demean_by_month(recs):
    """recs: [(month, c, ret)] → 월 평균을 뺀 (c, ret) 열."""
    by = {}
    for m, c, r in recs:
        by.setdefault(m, []).append((c, r))
    xs, ys = [], []
    for v in by.values():
        mc, mr = mean([a for a, _ in v]), mean([b for _, b in v])
        for a, b in v:
            xs.append(a - mc)
            ys.append(b - mr)
    return xs, ys


def month_boot_p(recs, stat, rng, n=BOOT_N):
    """월 블록 재표집 → P(stat >= 0). recs: [(month, c, ret)]."""
    by = {}
    for r in recs:
        by.setdefault(r[0], []).append(r)
    months = sorted(by)
    ge = tot = 0
    for _ in range(n):
        bs = []
        for _ in months:
            bs.extend(by[rng.choice(months)])
        v = stat(bs)
        if v is None:
            continue
        tot += 1
        ge += int(v >= 0)
    return ge / tot if tot else None


def stat_rho(recs):
    return spearman([c for _, c, _ in recs], [r for _, _, r in recs])


def stat_rho_dm(recs):
    xs, ys = demean_by_month(recs)
    return spearman(xs, ys)


def tercile_cuts(cs):
    s = sorted(cs)
    n = len(s)
    return s[n // 3], s[(2 * n) // 3]


def tercile_means(recs, cuts):
    lo, hi = cuts
    a = [r for _, c, r in recs if c <= lo]
    b = [r for _, c, r in recs if lo < c <= hi]
    c_ = [r for _, c, r in recs if c > hi]
    return mean(a), mean(b), mean(c_), (len(a), len(b), len(c_))


def judge(res):
    """res: dict(rho, p_boot, rho_tr, rho_ho, ter_tr, ter_ho, ter_full, rho_dm, p_dm). 사전 고정 규칙."""
    f = {}
    f["S1"] = res["rho"] is not None and res["rho"] < 0 and res["p_boot"] is not None and res["p_boot"] < P_BOOT
    f["S2"] = all(x is not None and x < 0 for x in (res["rho_tr"], res["rho_ho"]))
    f["S3"] = all(t[0] is not None and t[2] is not None and t[2] < t[0] for t in (res["ter_tr"], res["ter_ho"]))
    tf = res["ter_full"]
    f["S4"] = all(x is not None for x in tf[:3]) and tf[0] >= tf[1] >= tf[2]
    if not all(f.values()):
        return "NO_SELECTION_BIAS", f
    if res["rho_dm"] is not None and res["rho_dm"] < 0 and res["p_dm"] is not None and res["p_dm"] < P_BOOT:
        return "SELECTION_BIAS_WITHIN_MONTH", f
    return "SELECTION_BIAS_TIME_EFFECT", f


def analyse(base, cut):
    """base: 시간순 전체 거래. target 거래에 대한 판정 입력을 만든다."""
    co = c_open_all(base)
    recs, idxs = [], []
    for i, t in enumerate(base):
        if t["pattern"] == TARGET:
            recs.append((month_key(t["t_in"]), co[i], t["ret"]))
            idxs.append(i)
    tr = [r for r, i in zip(recs, idxs) if base[i]["t_in"] < cut]
    ho = [r for r, i in zip(recs, idxs) if base[i]["t_in"] >= cut]
    rng = random.Random(SEED)
    cuts = tercile_cuts([c for _, c, _ in recs]) if recs else (0, 0)
    res = dict(n=len(recs), n_tr=len(tr), n_ho=len(ho),
               rho=stat_rho(recs), p_boot=month_boot_p(recs, stat_rho, rng) if recs else None,
               rho_tr=stat_rho(tr), rho_ho=stat_rho(ho),
               ter_tr=tercile_means(tr, cuts), ter_ho=tercile_means(ho, cuts), ter_full=tercile_means(recs, cuts),
               rho_dm=stat_rho_dm(recs), p_dm=month_boot_p(recs, stat_rho_dm, rng) if recs else None,
               cuts=cuts)
    return res, recs, idxs


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    import detlib
    import method_t as mt
    import regime_switch as rs
    from validate_regime_split import turnover_rank
    print("=" * 90)
    print("R-072 vol_awakening_4h 체결 선택 편향 — 동시성별 수익 (사전 등록 2026-10-28)")
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
    cut = vp.mx._tnum(vp.SPLIT)
    res, recs, idxs = analyse(base, cut)
    print(f"전체 거래 {len(base)} / {TARGET} {res['n']} (train {res['n_tr']} / holdout {res['n_ho']})")
    print(f"  Spearman rho(c_open, ret) 전체 {res['rho']:+.3f}  월블록 부트 P(rho>=0)={res['p_boot']:.3f}")
    print(f"    train {res['rho_tr']:+.3f} / holdout {res['rho_ho']:+.3f}")
    print(f"  월 내 demean rho {res['rho_dm']:+.3f}  P(rho>=0)={res['p_dm']:.3f}")
    lo, hi = res["cuts"]
    print(f"  3분위 경계 c_open <= {lo} / <= {hi}")
    for nm in ("ter_full", "ter_tr", "ter_ho"):
        a, b, c, ns = res[nm]
        f = lambda x: "  n/a " if x is None else f"{x*100:+6.2f}%"
        print(f"   {nm:9} 하위 {f(a)} 중위 {f(b)} 상위 {f(c)}  (n={ns})")
    verdict, flags = judge(res)
    print(f"\n판정: {verdict}  {flags}")
    # 진단 1: 같은 날 버스트 순번
    tgt = [base[i] for i in idxs]
    bo = burst_ordinal(tgt)
    byo = {}
    for k, t in enumerate(tgt):
        byo.setdefault(min(bo[k], 4), []).append(t["ret"])
    print("[진단] 같은 날 vol_awakening 진입 순번별 평균:")
    for k in sorted(byo):
        print(f"   순번 {k}{'+' if k == 4 else ' '} n={len(byo[k]):5} {mean(byo[k])*100:+6.2f}%")
    # 진단 2: G0 시뮬 체결 시점 오픈 수
    open_at = {}
    sim = g.simulate(base, open_at=open_at)
    took = set(sim["took"])
    bins = {}
    for i in idxs:
        if i in took:
            bins.setdefault(min(open_at[i] // 3, 4), []).append(base[i]["ret"])
    print("[진단] G0 체결분 — 체결 직전 오픈 포지션 수(3 단위 구간)별 평균:")
    for k in sorted(bins):
        print(f"   {k*3}~{k*3+2}{'+' if k == 4 else ' '} n={len(bins[k]):5} {mean(bins[k])*100:+6.2f}%")
    json.dump(dict(prereg="vol_burst_prereg_2026_10_28", verdict=verdict, flags=flags,
                   res={k: v for k, v in res.items()}, burst={str(k): [len(v), mean(v)] for k, v in byo.items()},
                   sim_open={str(k): [len(v), mean(v)] for k, v in bins.items()}),
              open("_vol_burst.json", "w"), indent=1, ensure_ascii=False, default=str)


if __name__ == "__main__":
    main()
