"""validate_iso_skip.py — R-075 vol_awakening_4h 고립 신호 스킵 필터 (사전 등록 2026-11-10).

R-072: 진입 시점 동시 보유 수(c_open) 하위 3분위 vol_awakening_4h 평균 -0.29%(holdout -0.58%) vs 상위 +2.97%.
사후 선택 셀이라 반증 3종을 함께 건다(validate_ih_exit/va_drop 선례). 거래 집합·시뮬레이터는 va_drop 과 동일
(validate_portfolio 방식D+레짐청산, validate_gap.simulate, 분할별 공통 span 연율화).
c_open = t_in 에 열려 있는(t_in_j <= t_in < t_out_j) 다른 배포 거래 수. 인과적: 'j 가 t_in 에 아직 안 닫혔나'는
t_in 시점에 관측 가능하고 t_in_j > t_in 인 미래 진입은 세지 않는다(vb.c_open_all). 단 live 는 슬롯 스킵 거래가 열려
있지 않으므로 값이 다를 수 있다(known_limits).
arm: current / iso_skip(vol_awakening_4h 중 c_open <= LO 인 거래 제거). LO = **train 의 vol_awakening c_open 하위
3분위 경계**, holdout 에 고정 적용.
판정(전부 충족해야 PASSED_NOT_DEPLOYED):
I1 train·holdout 둘 다 Calmar(iso_skip) > Calmar(current).
I2 같은 수의 **다른 vol_awakening 거래**를 무작위 제거(200회, 시드 75)한 Calmar 분포의 95백분위를 두 분할 모두 넘는다.
I3 스킵된 거래 평균: 전체 월 블록 부트 P(mean>=0) < .10 이고 train·holdout 평균 둘 다 < 0 (전후반 부호 역전 금지).
I4 CAGR(iso_skip) > CAGR(current) 두 분할 모두이고 MDD 악화 5%p 이내.
DEPLOY_ON_PASS=False — 첫 시험, V 등급 셀, 통과해도 사용자 보고.
"""
import json
import random
import statistics as st
import sys

import validate_gap as g
import validate_portfolio as vp
import validate_va_drop as vd
import validate_vol_burst as vb

DEPLOY_ON_PASS = False
TARGET = "vol_awakening_4h"
SEED = 75
RAND_N = 200
P_BOOT = 0.10
MDD_TOL = 0.05


def attach_c_open(base):
    """각 거래에 c_open 을 붙인 사본 열(시간순 base 가정)."""
    co = vb.c_open_all(base)
    return [dict(t, c_open=c) for t, c in zip(base, co)]


def train_cut(base_c, cut):
    """train 의 TARGET c_open 하위 3분위 경계(LO). train 표본이 없으면 None."""
    cs = [t["c_open"] for t in base_c if t["pattern"] == TARGET and t["t_in"] < cut]
    if len(cs) < 3:
        return None
    return vb.tercile_cuts(cs)[0]


def is_skipped(t, lo):
    return t["pattern"] == TARGET and lo is not None and t["c_open"] <= lo


def analyse_split(tr, lo, rng, n=RAND_N):
    span = vd.span_of(tr)
    cur = vd.run(tr, span)
    keep = [t for t in tr if not is_skipped(t, lo)]
    iso = vd.run(keep, span)
    k = len(tr) - len(keep)
    targets = [i for i, t in enumerate(tr) if t["pattern"] == TARGET]
    ctrl = []
    for _ in range(n):
        drop = set(rng.sample(targets, min(k, len(targets))))
        ctrl.append(vd.run([t for i, t in enumerate(tr) if i not in drop], span)["calmar"])
    return dict(cur=cur, iso=iso, n_removed=k, ctrl_p95=vd.percentile(ctrl, 0.95),
                ctrl_med=st.median(ctrl) if ctrl else None, n_trades=len(tr))


def judge(a_tr, a_ho, sk_p_boot, sk_tr_mean, sk_ho_mean):
    f = {}
    f["I1"] = a_tr["iso"]["calmar"] > a_tr["cur"]["calmar"] and a_ho["iso"]["calmar"] > a_ho["cur"]["calmar"]
    f["I2"] = (a_tr["ctrl_p95"] is not None and a_ho["ctrl_p95"] is not None
               and a_tr["iso"]["calmar"] > a_tr["ctrl_p95"] and a_ho["iso"]["calmar"] > a_ho["ctrl_p95"])
    f["I3"] = (sk_p_boot is not None and sk_p_boot < P_BOOT and sk_tr_mean is not None and sk_ho_mean is not None
               and sk_tr_mean < 0 and sk_ho_mean < 0)

    def i4(a):
        return a["iso"]["cagr"] > a["cur"]["cagr"] and (a["iso"]["mdd"] - a["cur"]["mdd"]) >= -MDD_TOL
    f["I4"] = i4(a_tr) and i4(a_ho)
    return ("PASSED_NOT_DEPLOYED" if all(f.values()) else "REJECTED"), f


def skipped_stats(base_c, cut, lo, rng):
    sk = [t for t in base_c if is_skipped(t, lo)]
    recs = [(vb.month_key(t["t_in"]), 0, t["ret"]) for t in sk]
    p = vb.month_boot_p(recs, lambda rs: vb.mean([r for _, _, r in rs]), rng) if recs else None
    tr = [t["ret"] for t in sk if t["t_in"] < cut]
    ho = [t["ret"] for t in sk if t["t_in"] >= cut]
    kept = [t["ret"] for t in base_c if t["pattern"] == TARGET and not is_skipped(t, lo)]
    return dict(n=len(sk), mean=vb.mean([t["ret"] for t in sk]), p_boot=p, mean_tr=vb.mean(tr), mean_ho=vb.mean(ho),
                n_tr=len(tr), n_ho=len(ho), kept_mean=vb.mean(kept), kept_n=len(kept))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    import detlib
    import method_t as mt
    import regime_switch as rs
    from validate_regime_split import turnover_rank
    print("=" * 90)
    print("R-075 vol_awakening_4h 고립 신호 스킵 (사전 등록 2026-11-10)")
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
    base_c = attach_c_open(base)
    cut = vp.mx._tnum(vp.SPLIT)
    lo = train_cut(base_c, cut)
    print(f"전체 거래 {len(base_c)} / LO(train {TARGET} c_open 하위 3분위 경계) = {lo}")
    tr, ho = vd.split_trades(base_c, cut)
    rng = random.Random(SEED)
    a_tr = analyse_split(tr, lo, rng)
    a_ho = analyse_split(ho, lo, rng)
    ss = skipped_stats(base_c, cut, lo, rng)
    for nm, a in (("train", a_tr), ("holdout", a_ho)):
        c, i = a["cur"], a["iso"]
        print(f"[{nm}] 거래 {a['n_trades']} 스킵 {a['n_removed']} | current CAGR {c['cagr']*100:+.1f}% MDD {c['mdd']*100:.1f}% "
              f"Calmar {c['calmar']:.2f} 체결 {c['taken']} | iso CAGR {i['cagr']*100:+.1f}% MDD {i['mdd']*100:.1f}% "
              f"Calmar {i['calmar']:.2f} 체결 {i['taken']} | 대조 중앙 {a['ctrl_med']:.2f} p95 {a['ctrl_p95']:.2f}", flush=True)
    f = lambda x: float("nan") if x is None else x * 100
    print(f"[스킵 거래] n={ss['n']} 평균 {f(ss['mean']):+.2f}% P(mean>=0)={ss['p_boot']} train {f(ss['mean_tr']):+.2f}% (n={ss['n_tr']}) "
          f"holdout {f(ss['mean_ho']):+.2f}% (n={ss['n_ho']}) | 유지 {ss['kept_n']}건 평균 {f(ss['kept_mean']):+.2f}%")
    verdict, flags = judge(a_tr, a_ho, ss["p_boot"], ss["mean_tr"], ss["mean_ho"])
    print(f"\n판정: {verdict}  {flags}")
    json.dump(dict(prereg="iso_skip_prereg_2026_11_10", verdict=verdict, flags=flags, lo=lo, train=a_tr, holdout=a_ho, skipped=ss),
              open("_iso_skip.json", "w"), indent=1, ensure_ascii=False, default=str)


if __name__ == "__main__":
    main()
