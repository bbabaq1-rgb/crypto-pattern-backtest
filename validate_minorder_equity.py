"""validate_minorder_equity.py — R-109: 시작 equity 별 최소주문 스킵을 넣은 포트폴리오 프레임 (진단 전용, 2026-11-16).

validate_portfolio 의 시작 equity 는 1000 이라 최소주문($10 증거금)이 사실상 걸리지 않는다. 같은 거래열·같은 사이징·슬롯으로
시작 equity 만 {160,240,355} 로 낮춰(기준 1000) 최소주문 스킵을 **자산곡선 경로 의존**으로 넣고(risk_based_size 가 None 을
돌려주는 skip_margin) holdout Calmar·체결 거래 평균이 달라지는지 본다. 사전 등록: registry minorder_equity_prereg_2026_11_16.
DEPLOY_ON_PASS=False — 재개·충전·위험 수준은 사용자 결정.
"""
import json
import random
import sys

import validate_portfolio as vp

DEPLOY_ON_PASS = False
REF_EQ = 1000.0
EQ_LADDER = (160.0, 240.0, 355.0)
PRIMARY_EQ = 240.0
SEED = 109
BOOT_N = 300
P_BOOT = 0.10


def run_at(trades, eq0):
    """시작 equity eq0 로 current arm 시뮬. 반환 (결과 dict, 체결 거래 평균 수익, 체결 수)."""
    old = vp.START_EQ
    vp.START_EQ = eq0
    try:
        taken = []
        r = vp.simulate(trades, "current", None, taken_out=taken)
    finally:
        vp.START_EQ = old
    rets = [trades[i]["ret"] for i in taken]
    return r, (sum(rets) / len(rets) if rets else None), len(rets)


def paired_calmar_diff(trades, eq0, seed=SEED, n=BOOT_N):
    """같은 블록 재표집에 eq0 / REF 둘 다 적용. 반환 (P(d<=0), P(d>=0), 유효 반복 수)."""
    rng = random.Random(seed)
    le = ge = tot = 0
    for _ in range(n):
        bs = vp.block_bootstrap(trades, rng)
        a = run_at(bs, eq0)[0]
        b = run_at(bs, REF_EQ)[0]
        ca, cb = a["calmar"], b["calmar"]
        if ca == float("inf") or cb == float("inf"):
            continue
        d = ca - cb
        tot += 1; le += d <= 0; ge += d >= 0
    return (le / tot, ge / tot, tot) if tot else (None, None, 0)


def verdict(p_le0, p_ge0, tr_diff, ho_diff, n_taken_lost):
    """SKIP_HURTS: 기준보다 나쁘다(P(d>=0)<.10, 전후반 둘 다 d<0). SKIP_HELPS: 거울상. 체결 수 급감이면 INSUFFICIENT."""
    if p_le0 is None or n_taken_lost is None:
        return "INSUFFICIENT"
    if p_ge0 < P_BOOT and tr_diff < 0 and ho_diff < 0:
        return "SKIP_HURTS"
    if p_le0 < P_BOOT and tr_diff > 0 and ho_diff > 0:
        return "SKIP_HELPS"
    return "NO_EFFECT"


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    import detlib
    import method_t as mt
    import method_x as mx
    import regime_switch as rs
    from validate_regime_split import turnover_rank
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
    mt.REGMAP = regmap          # 레짐 전환 청산 켬 (2026-09-21 결함 교훈)
    base = sorted(vp.collect_1d(syms) + vp.collect_4h(rows_4h, ranked, regmap), key=lambda t: t["t_in"])
    cut = mx._tnum(vp.SPLIT)
    tr = [t for t in base if t["t_in"] < cut]
    ho = [t for t in base if t["t_in"] >= cut]
    print(f"총 거래 {len(base)} (train {len(tr)} / holdout {len(ho)})", flush=True)
    out = {}
    for tag, ts in (("train", tr), ("holdout", ho)):
        for eq in (REF_EQ,) + EQ_LADDER:
            r, m, n = run_at(ts, eq)
            out[(tag, eq)] = dict(calmar=r["calmar"], cagr=r["cagr"], mdd=r["mdd"], taken=n, mean_taken=m,
                                  skip_margin=r["skip_margin"], skip_slot=r["skip_slot"])
            print(f"[{tag}] eq {eq:6.0f}  Calmar {r['calmar']:6.2f} CAGR {r['cagr']*100:+7.1f}% MDD {r['mdd']*100:6.1f}% "
                  f"체결 {n:5} 체결평균 {(m or 0)*100:+.2f}% 스킵 증거금 {r['skip_margin']:5} 슬롯 {r['skip_slot']:5}", flush=True)
    res = {}
    for eq in EQ_LADDER:
        le, ge, tot = paired_calmar_diff(ho, eq)
        td = out[("train", eq)]["calmar"] - out[("train", REF_EQ)]["calmar"]
        hd = out[("holdout", eq)]["calmar"] - out[("holdout", REF_EQ)]["calmar"]
        res[eq] = dict(p_le0=le, p_ge0=ge, boots=tot, train_diff=td, holdout_diff=hd,
                       taken_ref=out[("holdout", REF_EQ)]["taken"], taken_eq=out[("holdout", eq)]["taken"])
        print(f"[holdout 짝지음 eq {eq:.0f}] Calmar차 train {td:+.2f} holdout {hd:+.2f}  P(d<=0)={le} P(d>=0)={ge} (반복 {tot})")
    p = res[PRIMARY_EQ]
    v = verdict(p["p_le0"], p["p_ge0"], p["train_diff"], p["holdout_diff"], p["taken_eq"])
    print(f"[판정] {v} (주 판정 eq {PRIMARY_EQ:.0f}, DEPLOY_ON_PASS={DEPLOY_ON_PASS})")
    json.dump(dict(verdict=v, res={str(k): v2 for k, v2 in res.items()},
                   table={f"{a}|{b}": v2 for (a, b), v2 in out.items()}),
              open("_minorder_equity.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print("RESULT_JSON: " + json.dumps(dict(verdict=v, p=p), separators=(",", ":"), default=str))


if __name__ == "__main__":
    main()
