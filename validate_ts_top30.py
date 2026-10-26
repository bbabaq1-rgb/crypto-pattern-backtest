"""
validate_ts_top30.py — three_soldiers_4h 코호트 all → top30 축소 (자율 연구 R-003, 사전 등록 registry ts_top30_prereg_2026_10_26)

실거래 three_soldiers_4h 는 universe.json 에 cohort 필드가 없어 4h 전 종목에서 돈다(bull 레짐 게이트만).
revival 프레임(2026-09-05)에서 top30 bull_btc PASSED / all REJECTED(med -0.49%) 였다.
이 시험은 '코호트를 top30 으로 좁히면 포트폴리오가 나아지는가' 하나만 묻는다 — 신호 집합이 줄어드는 방향의 변경.

arm: current(전 종목, validate_portfolio.ADOPTED_4H 와 동일) vs top30(three_soldiers_4h 거래 중 turnover 순위 30 밖 제거).
나머지 배포 셀·사이징·슬롯(MAX_POS)·청산(방식D)은 validate_portfolio 프레임 그대로.

판정(전부 충족 PASSED):
  F1 걸러진 거래(순위>=30) 평균 < 0, 월 블록 부트 P(평균<0) >= 0.90 (method_b 교훈)
  F1b 걸러진 거래 평균이 train·holdout 각각 < 0 (둘 다 n>=10)
  F2 포트폴리오 holdout J1~J5 (validate_portfolio 와 같은 정의: CAGR>, Calmar>, 부트 우위>=0.60, MDD 악화<=5%p, train 도 CAGR·Calmar >=)
  F3 남는 거래(top30) 평균이 train·holdout 각각 > 0 (holdout n>=10)
표본 n<10 만이 유일한 실패 사유면 INCONCLUSIVE, 그 외 REJECTED. 분할 vp.SPLIT(2025-01-01).
DEPLOY_ON_PASS = True (backlog R-003) — PASSED 일 때만 universe.json 에 cohort 한 줄.
"""
import json
import random
import sys
from datetime import date

import detlib
import method_t as mt
import method_x as mx
import validate_portfolio as vp
from validate_regime_split import turnover_rank

DEPLOY_ON_PASS = True
PAT = "three_soldiers_4h"
TOP_N = 30
MIN_N = 10
F1_P = 0.90
BOOT = 2000
SEED = 42


def is_removed(t):
    """top30 arm 이 제거하는 거래 — three_soldiers_4h 이고 순위가 TOP_N 밖(순위 없음 포함)."""
    return t["pattern"] == PAT and (t.get("rank") is None or t["rank"] >= TOP_N)


def make_arms(base):
    return {"current": list(base), "top30": [t for t in base if not is_removed(t)]}


def _month(t):
    return date.fromordinal(int(t)).strftime("%Y-%m")


def month_boot_p_neg(trades, rng, n=BOOT):
    """월 블록 부트스트랩: 월 단위 재표집 평균 < 0 인 비율."""
    by = {}
    for t in trades:
        by.setdefault(_month(t["t_in"]), []).append(t["ret"])
    keys = list(by)
    if not keys:
        return None
    neg = 0
    for _ in range(n):
        tot = cnt = 0
        for _k in keys:
            r = by[keys[rng.randrange(len(keys))]]
            tot += sum(r)
            cnt += len(r)
        neg += (tot / cnt) < 0
    return neg / n


def mean(xs):
    return sum(xs) / len(xs) if xs else None


def judge(f):
    """f: dict(removed_mean, removed_pneg, rm_tr(mean,n), rm_ho(mean,n), kept_tr, kept_ho, J(dict J1..J5))."""
    fails, thin = [], []
    f1 = f["removed_mean"] is not None and f["removed_mean"] < 0 and (f["removed_pneg"] or 0) >= F1_P
    if not f1:
        fails.append("F1")
    for key, name in (("rm_tr", "F1b_train"), ("rm_ho", "F1b_holdout")):
        m, n = f[key]
        if n < MIN_N:
            thin.append(name)
        elif not m < 0:
            fails.append(name)
    for key, name in (("kept_tr", "F3_train"), ("kept_ho", "F3_holdout")):
        m, n = f[key]
        if n < MIN_N:
            thin.append(name)
        elif not m > 0:
            fails.append(name)
    for k, v in f["J"].items():
        if not v:
            fails.append("F2_" + k)
    if fails:
        return "REJECTED", fails, thin
    return ("INCONCLUSIVE" if thin else "PASSED"), fails, thin


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    print("=" * 90)
    print("R-003 three_soldiers_4h 코호트 all -> top30 (사전 등록 2026-10-26)")
    print("=" * 90)
    import regime_switch as rs
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
    mt.REGMAP = regmap          # 레짐 전환 청산 켜기 (2026-09-21 결함 교훈)
    t1d = vp.collect_1d(syms)
    t4h = vp.collect_4h(rows_4h, ranked, regmap)
    base = sorted(t1d + t4h, key=lambda t: t["t_in"])
    arms = make_arms(base)
    cut = mx._tnum(vp.SPLIT)
    removed = [t for t in base if is_removed(t)]
    kept = [t for t in base if t["pattern"] == PAT and not is_removed(t)]
    split = lambda ts: ([t for t in ts if t["t_in"] < cut], [t for t in ts if t["t_in"] >= cut])
    rm_tr, rm_ho = split(removed)
    kp_tr, kp_ho = split(kept)
    st = lambda ts: (mean([t["ret"] for t in ts]), len(ts))
    print(f"three_soldiers_4h: 걸러진 {len(removed)} (train {len(rm_tr)} / ho {len(rm_ho)}) · 남는 {len(kept)} (train {len(kp_tr)} / ho {len(kp_ho)})")
    for nm, ts in (("걸러진", removed), ("걸러진 train", rm_tr), ("걸러진 holdout", rm_ho),
                   ("남는", kept), ("남는 train", kp_tr), ("남는 holdout", kp_ho)):
        m, n = st(ts)
        print(f"  {nm:14} n={n:5} 평균 {('%+.2f%%' % (m*100)) if m is not None else 'NA'}")
    pneg = month_boot_p_neg(removed, random.Random(SEED))

    tr = {a: vp.simulate([t for t in arms[a] if t["t_in"] < cut], "current") for a in arms}
    ho_tr = {a: [t for t in arms[a] if t["t_in"] >= cut] for a in arms}
    ho = {a: vp.simulate(ho_tr[a], "current") for a in arms}
    for a in arms:
        print(f"  [train]   {a:8} CAGR {tr[a]['cagr']*100:+7.1f}% MDD {tr[a]['mdd']*100:6.1f}% Calmar {tr[a]['calmar']:5.2f} 체결 {tr[a]['taken']}")
        print(f"  [holdout] {a:8} CAGR {ho[a]['cagr']*100:+7.1f}% MDD {ho[a]['mdd']*100:6.1f}% Calmar {ho[a]['calmar']:5.2f} 체결 {ho[a]['taken']}")
    rng = random.Random(vp.SEED)
    wins = 0
    for _ in range(vp.BOOT_N):
        bs = vp.block_bootstrap(ho_tr["current"], rng)
        wins += vp.simulate([t for t in bs if not is_removed(t)], "current")["calmar"] > vp.simulate(bs, "current")["calmar"]
    pw = wins / vp.BOOT_N
    c, a = ho["current"], ho["top30"]
    J = dict(J1=a["cagr"] > c["cagr"], J2=a["calmar"] > c["calmar"], J3=pw >= vp.J3_WIN,
             J4=a["mdd"] >= c["mdd"] - vp.J4_MDD_TOL,
             J5=tr["top30"]["cagr"] >= tr["current"]["cagr"] and tr["top30"]["calmar"] >= tr["current"]["calmar"])
    f = dict(removed_mean=mean([t["ret"] for t in removed]), removed_pneg=pneg,
             rm_tr=st(rm_tr), rm_ho=st(rm_ho), kept_tr=st(kp_tr), kept_ho=st(kp_ho), J=J)
    verdict, fails, thin = judge(f)
    print(f"\n걸러진 거래 월 블록 부트 P(평균<0) = {pneg}")
    print(f"부트 우위 P(top30 Calmar > current) = {pw:.0%}   J = {J}")
    print(f"\n판정: {verdict}  실패={fails} 표본부족={thin}  (DEPLOY_ON_PASS={DEPLOY_ON_PASS})")
    json.dump(dict(prereg="ts_top30_prereg_2026_10_26", verdict=verdict, fails=fails, thin=thin,
                   removed=dict(n=len(removed), mean=f["removed_mean"], p_neg=pneg, train=rm_tr and st(rm_tr), holdout=st(rm_ho)),
                   kept=dict(train=st(kp_tr), holdout=st(kp_ho)),
                   train={k: {x: y for x, y in v.items() if x != "blocked_by"} for k, v in tr.items()},
                   holdout={k: {x: y for x, y in v.items() if x != "blocked_by"} for k, v in ho.items()},
                   boot_win=pw, J=J), open("_ts_top30.json", "w"), indent=1, ensure_ascii=False, default=str)


if __name__ == "__main__":
    main()
