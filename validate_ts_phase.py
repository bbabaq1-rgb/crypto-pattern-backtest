"""
validate_ts_phase.py — three_soldiers_4h holdout 약세의 원인: 순위가 아니라 국면인가 (자율 연구 R-030,
사전 등록 registry ts_phase_prereg_2026_11_22). 연구 전용 — 실거래 무변경, DEPLOY_ON_PASS=False.

R-003 에서 순위>=30 걸러진 거래가 train +4.58% / holdout -0.79% 로 부호가 뒤집혔다. 코호트가 아니라 시장 국면
(2025 가짜 bull)이 원인이면 bull 라벨 에피소드로 층화했을 때 train 양수가 에피소드 2개 이상에서 재현되고
holdout 손실은 특정 에피소드에 몰린다. 반대로 최근 에피소드들이 전부 음수면 패턴 자체의 감쇠다.

표본: validate_portfolio.collect_4h 의 three_soldiers_4h 거래(bull_btc∪bull_altseason 게이트, 전 종목 = 실거래 복제).
에피소드: frame_v3.episodes — bull 두 라벨을 'bull' 로 합친 레짐맵에서 연속 구간(30일 이하 끊김 병합).
분할: 진입일 < 2025-01-01 train / 이후 holdout (vp.SPLIT).
판정(상호 배타, 위에서부터):
  NO_WEAKNESS   holdout n>=10 인데 평균 >= 0 (약세 자체가 재현 안 됨)
  INCONCLUSIVE  train n<30 또는 holdout n<10 또는 적격 에피소드(n>=5) 부족
  EPISODE_PHASE train 평균>0 이고 train 적격 에피소드 중 양수 >=2, holdout 평균<0 이며
                holdout 적격 에피소드 중 평균<0 인 것을 제외한 나머지 holdout(n>=10)이 평균>0 (손실이 일부 에피소드에 몰림)
  PATTERN_DECAY train 평균>0 이고 holdout 적격 에피소드가 >=2개 전부 평균<0 (국면을 바꿔도 같은 부호)
  MIXED         그 외
진단(판정 아님): 레짐별(bull_btc/bull_altseason) 평균, 순위 상/하 반분, 월 블록 부트 P(holdout 평균<0).
"""
import json
import random
import sys
from datetime import date

import detlib
import frame_v3 as f3
import method_t as mt
import method_x as mx
import validate_portfolio as vp
from validate_regime_split import turnover_rank
from validate_ts_top30 import month_boot_p_neg

DEPLOY_ON_PASS = False
PAT = "three_soldiers_4h"
BULL = {"bull_btc", "bull_altseason"}
MIN_TRAIN, MIN_HO, EP_N = 30, 10, 5
SEED = 42


def day_of(t):
    return date.fromordinal(int(t)).isoformat()


def bull_regmap(regmap):
    return {d: ("bull" if g in BULL else g) for d, g in regmap.items()}


def mean(xs):
    return sum(xs) / len(xs) if xs else None


def tag(trades, eps):
    for t in trades:
        t["date"] = day_of(t["t_in"])
        t["ep"] = f3.episode_of(t["date"], eps)
    return trades


def ep_stats(trades, eps):
    out = []
    for i, (a, b) in enumerate(eps):
        rs = [t["ret"] for t in trades if t["ep"] == i]
        out.append(dict(i=i, start=a, end=b, n=len(rs), mean=mean(rs), q=len(rs) >= EP_N))
    return out


def judge(train, ho, tr_eps, ho_eps, ho_rest):
    """train/ho: (mean, n). *_eps: ep_stats 결과. ho_rest: 손실 에피소드를 뺀 holdout (mean, n)."""
    if ho[1] >= MIN_HO and ho[0] >= 0:
        return "NO_WEAKNESS"
    q_tr = [e for e in tr_eps if e["q"]]
    q_ho = [e for e in ho_eps if e["q"]]
    if train[1] < MIN_TRAIN or ho[1] < MIN_HO or not q_tr or not q_ho:
        return "INCONCLUSIVE"
    pos_tr = sum(1 for e in q_tr if e["mean"] > 0)
    if train[0] > 0 and pos_tr >= 2:
        bad = [e for e in q_ho if e["mean"] < 0]
        if len(q_ho) >= 2 and len(bad) == len(q_ho):
            return "PATTERN_DECAY"
        if bad and ho_rest[1] >= MIN_HO and ho_rest[0] > 0:
            return "EPISODE_PHASE"
    return "MIXED"


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
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
    mt.REGMAP = regmap
    trades = [t for t in vp.collect_4h(rows_4h, ranked, regmap) if t["pattern"] == PAT]
    eps = f3.episodes(bull_regmap(regmap), "bull")
    tag(trades, eps)
    cut = mx._tnum(vp.SPLIT)
    tr = [t for t in trades if t["t_in"] < cut]
    ho = [t for t in trades if t["t_in"] >= cut]
    st = lambda ts: (mean([t["ret"] for t in ts]), len(ts))
    tr_e, ho_e = ep_stats(tr, eps), ep_stats(ho, eps)
    bad_idx = {e["i"] for e in ho_e if e["q"] and e["mean"] < 0}
    rest = [t for t in ho if t["ep"] not in bad_idx]
    verdict = judge(st(tr), st(ho), tr_e, ho_e, st(rest))
    print(f"R-030 {PAT}: train {st(tr)} / holdout {st(ho)} / 손실 에피소드 제외 holdout {st(rest)}")
    for nm, es in (("train", tr_e), ("holdout", ho_e)):
        for e in es:
            if e["n"]:
                print(f"  [{nm}] ep{e['i']} {e['start']}~{e['end']} n={e['n']:4} 평균 {e['mean']*100:+.2f}%{'' if e['q'] else ' (부적격)'}")
    diag = {}
    for g in sorted(BULL):
        sub = [t for t in trades if regmap.get(t["date"]) == g]
        diag[g] = st(sub)
        print(f"  진단 레짐 {g}: n={len(sub)} 평균 {diag[g][0]*100 if diag[g][0] is not None else float('nan'):+.2f}%")
    med = sorted(t["rank"] for t in trades)[len(trades) // 2] if trades else None
    for nm, sub in (("상위순위", [t for t in ho if med is not None and t["rank"] < med]),
                    ("하위순위", [t for t in ho if med is not None and t["rank"] >= med])):
        print(f"  진단 holdout {nm}: n={len(sub)} 평균 {st(sub)[0]}")
    pneg = month_boot_p_neg(ho, random.Random(SEED))
    print(f"  holdout 월 블록 부트 P(평균<0) = {pneg}")
    print(f"\n판정: {verdict}  (DEPLOY_ON_PASS={DEPLOY_ON_PASS})")
    json.dump(dict(prereg="ts_phase_prereg_2026_11_22", verdict=verdict, train=st(tr), holdout=st(ho), rest=st(rest),
                   train_eps=tr_e, holdout_eps=ho_e, diag=diag, p_neg=pneg),
              open("_ts_phase.json", "w"), indent=1, ensure_ascii=False, default=str)


if __name__ == "__main__":
    main()
