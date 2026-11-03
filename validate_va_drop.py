"""validate_va_drop.py — R-089 vol_awakening_4h 배포 제외 반증 3종 (사전 등록 2026-11-03).

R-063 에서 vol_awakening 을 빼면 전기간 CAGR -11% -> +22.4% 가 됐으나 사후 선택된 셀이다(validate_ih_exit 선례).
거래 집합은 validate_portfolio(방식D+레짐청산) 그대로, 시뮬레이터는 validate_gap.simulate(current 와 동일 회계).
arm: current / no_va(vol_awakening_4h 전부 제거). 분할 train(<2025-01-01) / holdout. 분할별 **공통 span**(current 거래의
첫~끝 시각)으로 CAGR 을 연율화해 arm 간 분모를 맞춘다(R-070 계열 결함 재발 방지).
판정(전부 충족해야 PASSED_NOT_DEPLOYED, 하나라도 실패면 REJECTED):
K1 train·holdout 둘 다 Calmar(no_va) > Calmar(current).
K2 무작위 제거 대조: 분할별로 같은 수의 **다른 패턴** 거래를 무작위 제거(200회, 시드 89)한 Calmar 분포의 95백분위를
   no_va 가 두 분할 모두 넘는다.
K3 제거 거래(vol_awakening) 평균: 전체에서 월 블록 부트 P(mean>=0) < .10 이고 holdout 평균 <= 0.
K4 CAGR(no_va) > CAGR(current) 두 분할 모두이고 MDD 가 5%p 넘게 악화되지 않는다.
진단(판정 아님): 분할별 체결 수·MDD·CAGR, 제거 거래 분할별 평균, 대조 분포 중앙.
DEPLOY_ON_PASS=False — V 등급(guard_v5 CONFIRMED) 셀이라 통과해도 사용자 보고. steward S 규칙을 우회하지 않는다.
"""
import json
import random
import statistics as st
import sys

import validate_gap as g
import validate_portfolio as vp
import validate_vol_burst as vb

DEPLOY_ON_PASS = False
TARGET = "vol_awakening_4h"
SEED = 89
RAND_N = 200
P_BOOT = 0.10
MDD_TOL = 0.05


def span_of(trades):
    ts = [t["t_in"] for t in trades] + [t["t_out"] for t in trades]
    return max(1.0, max(ts) - min(ts)) if ts else 1.0


def run(trades, span):
    """g.simulate 결과를 공통 span 으로 재연율화."""
    r = g.simulate(trades) if trades else dict(final=vp.START_EQ, mdd=0.0, taken=0, skipped=0)
    eq = r["final"]
    cagr = (eq / vp.START_EQ) ** (365.25 / span) - 1 if eq > 0 else -1.0
    mdd = r["mdd"]
    return dict(cagr=cagr, mdd=mdd, calmar=(cagr / abs(mdd) if mdd < 0 else float("inf")),
                taken=r["taken"], skipped=r["skipped"], final=eq)


def percentile(xs, q):
    s = sorted(xs)
    if not s:
        return None
    k = (len(s) - 1) * q
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def split_trades(base, cut):
    return [t for t in base if t["t_in"] < cut], [t for t in base if t["t_in"] >= cut]


def analyse_split(tr, rng, n=RAND_N):
    span = span_of(tr)
    cur = run(tr, span)
    keep = [t for t in tr if t["pattern"] != TARGET]
    nov = run(keep, span)
    k = len(tr) - len(keep)
    others = [i for i, t in enumerate(tr) if t["pattern"] != TARGET]
    ctrl = []
    for _ in range(n):
        drop = set(rng.sample(others, min(k, len(others))))
        sub = [t for i, t in enumerate(tr) if i not in drop]
        ctrl.append(run(sub, span)["calmar"])
    return dict(cur=cur, nov=nov, n_removed=k, ctrl_p95=percentile(ctrl, 0.95),
                ctrl_med=st.median(ctrl) if ctrl else None, n_trades=len(tr))


def judge(a_tr, a_ho, va_p_boot, va_ho_mean):
    flags = {}
    flags["K1"] = a_tr["nov"]["calmar"] > a_tr["cur"]["calmar"] and a_ho["nov"]["calmar"] > a_ho["cur"]["calmar"]
    flags["K2"] = (a_tr["ctrl_p95"] is not None and a_ho["ctrl_p95"] is not None
                   and a_tr["nov"]["calmar"] > a_tr["ctrl_p95"] and a_ho["nov"]["calmar"] > a_ho["ctrl_p95"])
    flags["K3"] = (va_p_boot is not None and va_p_boot < P_BOOT and va_ho_mean is not None and va_ho_mean <= 0)

    def k4(a):
        return a["nov"]["cagr"] > a["cur"]["cagr"] and (a["nov"]["mdd"] - a["cur"]["mdd"]) >= -MDD_TOL
    flags["K4"] = k4(a_tr) and k4(a_ho)
    verdict = "PASSED_NOT_DEPLOYED" if all(flags.values()) else "REJECTED"
    return verdict, flags


def target_stats(base, cut, rng):
    va = [t for t in base if t["pattern"] == TARGET]
    recs = [(vb.month_key(t["t_in"]), 0, t["ret"]) for t in va]
    stat = lambda rs: vb.mean([r for _, _, r in rs])
    p = vb.month_boot_p(recs, stat, rng)
    ho = [t["ret"] for t in va if t["t_in"] >= cut]
    tr = [t["ret"] for t in va if t["t_in"] < cut]
    return dict(n=len(va), mean=vb.mean([t["ret"] for t in va]), p_boot=p,
                mean_tr=vb.mean(tr), mean_ho=vb.mean(ho), n_tr=len(tr), n_ho=len(ho))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    import detlib
    import method_t as mt
    import regime_switch as rs
    from validate_regime_split import turnover_rank
    print("=" * 90)
    print("R-089 vol_awakening_4h 배포 제외 — 반증 3종 (사전 등록 2026-11-03)")
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
    tr, ho = split_trades(base, cut)
    rng = random.Random(SEED)
    a_tr = analyse_split(tr, rng)
    a_ho = analyse_split(ho, rng)
    ts = target_stats(base, cut, rng)
    for nm, a in (("train", a_tr), ("holdout", a_ho)):
        c, n = a["cur"], a["nov"]
        print(f"[{nm}] 거래 {a['n_trades']} 제거 {a['n_removed']} | current CAGR {c['cagr']*100:+.1f}% MDD {c['mdd']*100:.1f}% "
              f"Calmar {c['calmar']:.2f} 체결 {c['taken']} | no_va CAGR {n['cagr']*100:+.1f}% MDD {n['mdd']*100:.1f}% "
              f"Calmar {n['calmar']:.2f} 체결 {n['taken']} | 대조 중앙 {a['ctrl_med']:.2f} p95 {a['ctrl_p95']:.2f}", flush=True)
    print(f"[제거 거래] n={ts['n']} 평균 {ts['mean']*100:+.2f}% P(mean>=0)={ts['p_boot']:.3f} "
          f"train {ts['mean_tr']*100 if ts['mean_tr'] is not None else float('nan'):+.2f}% (n={ts['n_tr']}) "
          f"holdout {ts['mean_ho']*100 if ts['mean_ho'] is not None else float('nan'):+.2f}% (n={ts['n_ho']})")
    verdict, flags = judge(a_tr, a_ho, ts["p_boot"], ts["mean_ho"])
    print(f"\n판정: {verdict}  {flags}")
    json.dump(dict(prereg="va_drop_prereg_2026_11_03", verdict=verdict, flags=flags, train=a_tr, holdout=a_ho, target=ts),
              open("_va_drop.json", "w"), indent=1, ensure_ascii=False, default=str)


if __name__ == "__main__":
    main()
