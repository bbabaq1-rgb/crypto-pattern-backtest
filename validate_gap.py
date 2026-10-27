"""validate_gap.py — R-063 거래 평균 양수 vs 포트폴리오 자산곡선 음수 괴리 분해 (사전 등록 2026-10-27).

진단 전용(DEPLOY_ON_PASS=False). validate_portfolio 의 거래 집합(1d 라우팅 복제 + 4h adopted 4종, 방식D+레짐청산)을
고정하고 시뮬레이터 설정을 **한 번에 하나씩** 풀어 전기간 CAGR 이 양수로 돌아서는 단계를 찾는다.
단계: G0 current / G1 flat(변동성 배율 1) / G2 slots_inf / G3 no_caps(슬롯·총명목가 상한·증거금 제약 해제) /
G4 no_vol_awakening / G5 no_4h / G6 risk 1.0% / G7 risk 0.5% / G8 random_order(우선순위 무작위, 100회 중앙).
판정(사전 고정): G0 CAGR>0 이면 NO_GAP. 아니면 G1~G5 중 CAGR>0 으로 돌아선 단계가 원인 후보 —
G1=(a) 변동성 가중 / G2·G3=(c) 슬롯·증거금 경합 / G4·G5=(b) 4h 버스트 / 이들 없이 G6·G7 만이면 RISK_LEVEL /
아무 단계도 안 돌아서면 PATH_DEPENDENT(프레임·손실 동시성). 복수면 CAGR 개선 최대 단계를 primary 로.
"""
import json
import random
import statistics as st
import sys

import sizing as sz
import validate_portfolio as vp

DEPLOY_ON_PASS = False
RAND_N = 100
SEED = 63
STAGES = ["G0", "G1", "G2", "G3", "G4", "G5", "G6", "G7"]
FACTOR = {"G1": "a_vol_weight", "G2": "c_slot_margin", "G3": "c_slot_margin",
          "G4": "b_4h_burst", "G5": "b_4h_burst"}
INF = 10 ** 9


def simulate(trades, *, max_pos=None, flat=False, no_caps=False, risk=None, rng=None, path=None):
    """vp.simulate(arm=current) 와 같은 회계 + 설정 해제 노브. 기본 인자면 vp.simulate 와 동일(test 고정).
    rng 를 주면 같은 시각 진입 후보의 우선순위를 무작위로(G8)."""
    max_pos = vp.MAX_POS if max_pos is None else max_pos
    evs = []
    for i, t in enumerate(trades):
        evs.append((t["t_out"], -1, i))
        evs.append((t["t_in"], 0, i))
    evs.sort(key=lambda e: (e[0], e[1]))
    equity = free = vp.START_EQ
    open_pos, peak, mdd = {}, vp.START_EQ, 0.0
    taken, skipped, took = 0, 0, []
    i = 0
    while i < len(evs):
        t0 = evs[i][0]
        batch = []
        while i < len(evs) and evs[i][0] == t0:
            _, kind, idx = evs[i]
            if kind == -1:
                rec = open_pos.pop(idx, None)
                if rec is not None:
                    margin, notional = rec
                    pnl = notional * trades[idx]["ret"]
                    equity += pnl
                    free += margin + pnl
                    peak = max(peak, equity)
                    mdd = min(mdd, equity / peak - 1)
            else:
                batch.append(idx)
            i += 1
        if path is not None:
            path.append((t0, equity))
        if equity <= 0:
            equity = 0.0
            break
        if not batch:
            continue
        if rng is not None:
            rng.shuffle(batch)
        else:
            batch.sort(key=lambda idx: (0.0, vp._tf_rank(trades[idx]["pattern"]),
                                        trades[idx]["rank"] if trades[idx]["rank"] is not None else 500,
                                        trades[idx]["sym"]))
        for idx in batch:
            tr = trades[idx]
            if len(open_pos) >= max_pos:
                skipped += 1
                continue
            s = 1.0 if flat else vp._live_scale(tr["vol"])
            kw = {}
            if risk is not None:
                kw["risk_frac"] = risk
            if no_caps:
                kw["max_total_frac"] = 1e9
            r = sz.risk_based_size(equity, 1e18 if no_caps else free, vp.STOP, vol_scale=s,
                                   open_notional=sum(n for _, n in open_pos.values()), **kw)
            if r is None:
                skipped += 1
                continue
            free -= r["margin_usd"]
            open_pos[idx] = (r["margin_usd"], r["notional"])
            taken += 1
            took.append(idx)
    span = max(1.0, evs[-1][0] - evs[0][0]) if evs else 1.0
    cagr = (equity / vp.START_EQ) ** (365.25 / span) - 1 if equity > 0 else -1.0
    return dict(final=equity, cagr=cagr, mdd=mdd, calmar=(cagr / abs(mdd) if mdd < 0 else float("inf")),
                taken=taken, skipped=skipped, took=took)


def stage_run(trades, stage):
    if stage == "G0":
        return simulate(trades)
    if stage == "G1":
        return simulate(trades, flat=True)
    if stage == "G2":
        return simulate(trades, max_pos=INF)
    if stage == "G3":
        return simulate(trades, max_pos=INF, no_caps=True)
    if stage == "G4":
        return simulate([t for t in trades if t["pattern"] != "vol_awakening_4h"])
    if stage == "G5":
        return simulate([t for t in trades if t["tf"] != "4h"])
    if stage == "G6":
        return simulate(trades, risk=0.010)
    if stage == "G7":
        return simulate(trades, risk=0.005)
    raise ValueError(stage)


def classify(res):
    """res: stage -> dict(cagr). G0 포함. 사전 고정 규칙."""
    g0 = res["G0"]["cagr"]
    if g0 > 0:
        return "NO_GAP", []
    flips = [s for s in STAGES[1:] if res[s]["cagr"] > 0]
    core = [s for s in flips if s in FACTOR]
    if core:
        best = max(core, key=lambda s: res[s]["cagr"])
        return FACTOR[best], flips
    if flips:
        return "RISK_LEVEL", flips
    return "PATH_DEPENDENT", flips


def mean(xs):
    return sum(xs) / len(xs) if xs else None


def selection_diag(trades, took):
    """G0 에서 체결된 거래 vs 전체/미체결의 평균 수익 — 슬롯 선택 편향."""
    tk = set(took)
    all_r = [t["ret"] for t in trades]
    tk_r = [trades[i]["ret"] for i in tk]
    sk_r = [t["ret"] for i, t in enumerate(trades) if i not in tk]
    by = {}
    for p in sorted({t["pattern"] for t in trades}):
        a = [t["ret"] for t in trades if t["pattern"] == p]
        b = [trades[i]["ret"] for i in tk if trades[i]["pattern"] == p]
        by[p] = dict(n=len(a), mean=mean(a), taken=len(b), taken_mean=mean(b))
    return dict(n=len(all_r), mean_all=mean(all_r), n_taken=len(tk_r), mean_taken=mean(tk_r),
                n_skipped=len(sk_r), mean_skipped=mean(sk_r), by_pattern=by)


def indep_log_growth(trades):
    """진단: 겹침·슬롯을 무시하고 거래마다 명목가 비율 f 로 독립 복리 — sum log(1+f*ret)."""
    tot = 0.0
    for t in trades:
        f = min(sz.RISK_FRAC / vp.STOP * vp._live_scale(t["vol"]), sz.MAX_POS_NOTIONAL_FRAC)
        x = 1 + f * t["ret"]
        tot += __import__("math").log(x) if x > 0 else -50.0
    return tot


def weekly_loss_concentration(path):
    """G0 자산곡선의 ISO 주(근사: 7일 버킷) 로그수익 — 최악 5주 합 / 전체 합."""
    import math
    wk = {}
    prev = vp.START_EQ
    for t, e in path:
        if e <= 0:
            break
        k = int(t // 7)
        wk[k] = wk.get(k, 0.0) + math.log(e / prev)
        prev = e
    vals = sorted(wk.values())
    return dict(weeks=len(vals), total=sum(vals), worst5=sum(vals[:5]), best5=sum(vals[-5:]))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    import detlib
    import method_t as mt
    import regime_switch as rs
    from validate_regime_split import turnover_rank
    print("=" * 90)
    print("R-063 거래 평균 vs 자산곡선 괴리 분해 (사전 등록 2026-10-27)")
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
    print(f"거래 {len(base)} 평균 {mean([t['ret'] for t in base])*100:+.2f}%")
    cut = vp.mx._tnum(vp.SPLIT)
    ho = [t for t in base if t["t_in"] >= cut]

    res, resh = {}, {}
    for s in STAGES:
        res[s] = stage_run(base, s)
        resh[s] = stage_run(ho, s) if ho else None
        r, h = res[s], resh[s]
        print(f"  [{s}] 전기간 CAGR {r['cagr']*100:+8.1f}% MDD {r['mdd']*100:6.1f}% 최종 {r['final']:12.1f} 체결 {r['taken']:5} 스킵 {r['skipped']:5}"
              + (f" | holdout CAGR {h['cagr']*100:+8.1f}% MDD {h['mdd']*100:6.1f}%" if h else ""), flush=True)
    rr = random.Random(SEED)
    rc = [simulate(base, rng=rr)["cagr"] for _ in range(RAND_N)]
    g8 = dict(median=st.median(rc), pos=sum(c > 0 for c in rc) / RAND_N)
    print(f"  [G8] 우선순위 무작위 {RAND_N}회 CAGR 중앙 {g8['median']*100:+.1f}% 양수 비율 {g8['pos']:.0%}")
    verdict, flips = classify(res)
    print(f"\n판정: {verdict}  돌아선 단계={flips}")
    path = []
    simulate(base, path=path)
    sel = selection_diag(base, res["G0"]["took"])
    print(f"[진단] 거래 평균 전체 {sel['mean_all']*100:+.2f}% / 체결 {sel['mean_taken']*100:+.2f}% (n={sel['n_taken']}) / 미체결 "
          f"{(sel['mean_skipped'] or 0)*100:+.2f}% (n={sel['n_skipped']})")
    for p, v in sel["by_pattern"].items():
        print(f"   {p:20} 전체 n={v['n']:5} {v['mean']*100:+6.2f}% / 체결 n={v['taken']:5} "
              f"{(v['taken_mean'] if v['taken_mean'] is not None else 0)*100:+6.2f}%")
    ig = indep_log_growth(base)
    import math
    act = math.log(max(res["G0"]["final"], 1e-9) / vp.START_EQ)
    print(f"[진단] 독립 베팅 가정 로그성장 {ig:+.2f} vs 실제 G0 로그성장 {act:+.2f}")
    wc = weekly_loss_concentration(path)
    print(f"[진단] G0 주별 로그수익 최악 5주 {wc['worst5']:+.2f} / 최고 5주 {wc['best5']:+.2f} / 합 {wc['total']:+.2f} ({wc['weeks']}주)")
    json.dump(dict(prereg="gap_prereg_2026_10_27", verdict=verdict, flips=flips,
                   stages={s: {k: v for k, v in res[s].items() if k != "took"} for s in STAGES},
                   holdout={s: ({k: v for k, v in resh[s].items() if k != "took"} if resh[s] else None) for s in STAGES},
                   g8=g8, selection=sel, indep_log=ig, actual_log=act, weekly=wc),
              open("_gap.json", "w"), indent=1, ensure_ascii=False, default=str)


if __name__ == "__main__":
    main()
