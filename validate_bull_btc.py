"""
validate_bull_btc.py — bull_btc 레짐 롱 신규 진입 정지 (자율 연구 R-060, 사전 등록 registry bull_btc_prereg_2026_10_26)

계기: 2026-10-10 bull_btc 전환 뒤 실거래 알트 롱 40건 평균 약 -5.4%(vol_awakening_4h 1/14 승, fvg 0/5 ...).
guard_v4 D1: bull_btc 월 top30 무작위 롱 train +5.24% -> OOS(2025~) -1.70% — 라벨은 BTC 방향은 가르지만 알트 롱
수익은 못 가른다. 패턴별 정지 규칙(S1·S2)은 한 국면(2주)에서 안 걸리므로 '레짐 단위' 정지를 포트폴리오 프레임으로 판정한다.

arm: current(validate_portfolio 배포 집합 그대로) vs no_bull_btc_long(진입 레짐이 bull_btc 인 롱 전부 제거).
사이징·청산(방식D)·슬롯(MAX_POS)은 validate_portfolio 프레임 고정. 진입 레짐 = 진입 날짜의 regime_switch 라벨(라우팅과 같은 맵).

홀드아웃(frame_v3 국면 홀드아웃): bull_btc 로 라벨된 날 중 가장 최근 365일(frame_v3.holdout_dates). train = 그 외 bull_btc 날.
레짐 구간 성과 = 전 기간 시뮬레이션 자산곡선(vp.simulate path)에서 해당 날짜들의 일별 로그수익만 이어붙인 값.

판정(전부 충족해야 PASSED):
  K1 홀드아웃 구간 진입 제거 거래: n>=30, 평균<0, 월 블록 부트 P(평균<0) >= 0.90
  K2 train bull_btc 구간에서도 arm 구간 로그수익 >= current (단일 구간 의존 방지, 2023~24 강세를 이길 것)
  K3 홀드아웃 구간 arm 로그수익 > current
  K4 전 기간 arm CAGR > current AND Calmar > current
  K5 전 기간 짝지음 블록 부트 P(arm Calmar > current Calmar) >= 0.60
  K6 노출 정합 대조: 같은 개수를 롱 거래에서 무작위로 뺀 200회 중 arm 전 기간 Calmar 의 백분위 >= 0.90
  K7 bull_btc 에피소드(frame_v3.episodes): 적격(n>=5) >=2 이고 제거 거래 평균<0 인 에피소드가 과반
표본 부족(K1 n<30 / K7 적격 에피소드<2 / K2 train n<30)이 유일한 실패 사유면 INCONCLUSIVE, 그 외 REJECTED.
경계 규칙(사전): PASSED 여도 K5 < 0.70 이면 경계값 — 자율 반영 안 함. DEPLOY_ON_PASS=True(backlog R-060).
"""
import json
import math
import random
import statistics as st
import sys
from bisect import bisect_left
from datetime import date

import detlib
import frame_v3 as f3
import method_t as mt
import method_x as mx
import validate_portfolio as vp
from validate_regime_split import turnover_rank
from validate_ts_top30 import month_boot_p_neg, mean

DEPLOY_ON_PASS = True
REG = "bull_btc"
MIN_N = 30
K1_P = 0.90
K5_WIN = 0.60
K5_DEPLOY = 0.70
K6_RANK = 0.90
RAND_N = 200
SEED = 42


def _iso(t_in):
    return date.fromordinal(int(t_in)).isoformat()


def tag(trades, regmap):
    """거래에 진입 날짜·진입 레짐·방향을 붙인다. 1d 라벨은 *_short 가 숏, 나머지는 롱(4h 는 전부 롱)."""
    out = []
    for t in trades:
        d = _iso(t["t_in"])
        out.append(dict(t, date=d, reg=regmap.get(d),
                        dir="short" if str(t["pattern"]).endswith("_short") else "long"))
    return out


def is_removed(t):
    return t.get("reg") == REG and t.get("dir") == "long"


def make_arms(base):
    return {"current": list(base), "no_bull_btc_long": [t for t in base if not is_removed(t)]}


def day_curve(path, start_eq=None):
    """path [(t, equity)] -> end_of_day(day_ordinal) 함수. 첫 기록 전은 start_eq."""
    start_eq = vp.START_EQ if start_eq is None else start_eq
    ts = [p[0] for p in path]
    eq = [p[1] for p in path]

    def end_of_day(d):
        k = bisect_left(ts, d + 1.0)            # t < d+1 인 마지막 기록
        return start_eq if k == 0 else eq[k - 1]
    return end_of_day


def restricted(path, days, start_eq=None):
    """days(iso 문자열 집합) 날짜들의 일별 로그수익만 합친다 -> (합 로그수익, 이어붙인 곡선 MDD)."""
    eod = day_curve(path, start_eq)
    tot, cum, peak, mdd = 0.0, 0.0, 0.0, 0.0
    for d in sorted(days):
        o = date.fromisoformat(d).toordinal()
        e1, e0 = eod(o), eod(o - 1)
        if e1 <= 0 or e0 <= 0:
            return float("-inf"), -1.0
        r = math.log(e1 / e0)
        tot += r
        cum += r
        peak = max(peak, cum)
        mdd = min(mdd, math.exp(cum - peak) - 1)
    return tot, mdd


def judge(f):
    """f: dict(k1=(n, mean, pneg), k2=(arm_L_T, cur_L_T, n_train_removed), k3=(arm_L_H, cur_L_H),
    k4=(arm_cagr, cur_cagr, arm_calmar, cur_calmar), k5=win, k6=rank, k7=(qualifying, negative))."""
    fails, thin = [], []
    n, m, pneg = f["k1"]
    if n < MIN_N:
        thin.append("K1_n")
    elif not (m is not None and m < 0 and (pneg or 0) >= K1_P):
        fails.append("K1")
    aT, cT, nT = f["k2"]
    if nT < MIN_N:
        thin.append("K2_n")
    elif not aT >= cT:
        fails.append("K2")
    aH, cH = f["k3"]
    if not aH > cH:
        fails.append("K3")
    ac, cc, aq, cq = f["k4"]
    if not (ac > cc and aq > cq):
        fails.append("K4")
    if not f["k5"] >= K5_WIN:
        fails.append("K5")
    if not f["k6"] >= K6_RANK:
        fails.append("K6")
    q, neg = f["k7"]
    if q < 2:
        thin.append("K7_eps")
    elif not neg * 2 >= q:
        fails.append("K7")
    if fails:
        return "REJECTED", fails, thin
    return ("INCONCLUSIVE" if thin else "PASSED"), fails, thin


def deployable(verdict, k5):
    """자율 반영 대상: PASSED 이고 경계값(K5<0.70)이 아닐 때만."""
    return DEPLOY_ON_PASS and verdict == "PASSED" and k5 >= K5_DEPLOY


def btc_dd_bucket(rows_btc):
    """진단: 진입일 BTC 가 1년 고점 대비 낙폭(0~-10 / -10~-20 / <-20) — diag_bull_phase 와 같은 고정 버킷."""
    out, hist = {}, []
    for r in rows_btc:
        hist.append(r["close"])
        win = hist[-365:]
        dd = r["close"] / max(win) - 1
        out[r["date"]] = "dd0_10" if dd > -0.10 else ("dd10_20" if dd > -0.20 else "dd20p")
    return out


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    print("=" * 90)
    print("R-060 bull_btc 레짐 롱 신규 진입 정지 (사전 등록 2026-10-26)")
    print("=" * 90)
    import json as _j
    import regime_switch as rs
    syms = _j.load(open("universe.json", encoding="utf-8"))["trading_universe"]
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
    base = sorted(tag(vp.collect_1d(syms) + vp.collect_4h(rows_4h, ranked, regmap), regmap), key=lambda t: t["t_in"])
    arms = make_arms(base)
    removed = [t for t in base if is_removed(t)]
    H = f3.holdout_dates(regmap, REG)
    allb = {d for d, g in regmap.items() if g == REG}
    T = allb - H
    rm_H = [t for t in removed if t["date"] in H]
    rm_T = [t for t in removed if t["date"] in T]
    print(f"거래 {len(base)} · 제거 대상 {len(removed)} (holdout 구간 {len(rm_H)} / train 구간 {len(rm_T)})")
    print(f"bull_btc 일수 {len(allb)} (holdout {len(H)} {min(H) if H else '-'}~{max(H) if H else '-'} / train {len(T)})")
    for nm, ts in (("제거(전체)", removed), ("제거 holdout", rm_H), ("제거 train", rm_T)):
        m = mean([t["ret"] for t in ts])
        print(f"  {nm:12} n={len(ts):5} 평균 {('%+.2f%%' % (m*100)) if m is not None else 'NA'}")

    paths = {a: [] for a in arms}
    full = {a: vp.simulate(arms[a], "current", path=paths[a]) for a in arms}
    for a, r in full.items():
        print(f"  [전기간] {a:18} CAGR {r['cagr']*100:+7.1f}% MDD {r['mdd']*100:6.1f}% Calmar {r['calmar']:5.2f} 체결 {r['taken']}")
    LH = {a: restricted(paths[a], H) for a in arms}
    LT = {a: restricted(paths[a], T) for a in arms}
    for a in arms:
        print(f"  [구간 로그수익] {a:18} holdout {LH[a][0]*100:+7.1f}% (MDD {LH[a][1]*100:6.1f}%) / train {LT[a][0]*100:+7.1f}% (MDD {LT[a][1]*100:6.1f}%)")

    rng = random.Random(vp.SEED)
    wins = 0
    for _ in range(vp.BOOT_N):
        bs = vp.block_bootstrap(base, rng)
        wins += vp.simulate([t for t in bs if not is_removed(t)], "current")["calmar"] > vp.simulate(bs, "current")["calmar"]
    k5 = wins / vp.BOOT_N
    pool = [i for i, t in enumerate(base) if t["dir"] == "long"]
    arm_cal = full["no_bull_btc_long"]["calmar"]
    rr = random.Random(SEED)
    rand_cal = []
    for _ in range(RAND_N):
        drop = set(rr.sample(pool, len(removed)))
        rand_cal.append(vp.simulate([t for i, t in enumerate(base) if i not in drop], "current")["calmar"])
    k6 = sum(1 for c in rand_cal if c < arm_cal) / RAND_N
    eps = f3.episodes(regmap, REG)
    tab = f3.episode_table(removed, eps)
    q = [r for r in tab if r["qualifying"]]
    neg = [r for r in q if r["mean"] < 0]
    print("\n에피소드별 제거 거래:")
    for r in tab:
        print(f"  {r['start']}~{r['end']} n={r['n']:4} 평균 {('%+.2f%%' % (r['mean']*100)) if r['mean'] is not None else 'NA'} 적격 {r['qualifying']}")

    pn = month_boot_p_neg(rm_H, random.Random(SEED)) if rm_H else None
    cur, arm = full["current"], full["no_bull_btc_long"]
    f = dict(k1=(len(rm_H), mean([t["ret"] for t in rm_H]), pn),
             k2=(LT["no_bull_btc_long"][0], LT["current"][0], len(rm_T)),
             k3=(LH["no_bull_btc_long"][0], LH["current"][0]),
             k4=(arm["cagr"], cur["cagr"], arm["calmar"], cur["calmar"]),
             k5=k5, k6=k6, k7=(len(q), len(neg)))
    verdict, fails, thin = judge(f)
    print(f"\nK1 {f['k1']}  K5 부트 우위 {k5:.0%}  K6 무작위 제거 백분위 {k6:.0%} (arm {arm_cal:.2f} vs 무작위 중앙 {st.median(rand_cal):.2f})  K7 {f['k7']}")
    print(f"판정: {verdict}  실패={fails} 표본부족={thin}  반영대상={deployable(verdict, k5)} (DEPLOY_ON_PASS={DEPLOY_ON_PASS})")

    # 진단(판정 아님) — 패턴별 분해 + 진입일 BTC 1년 고점 낙폭 버킷
    print("\n[진단] 패턴별 제거 거래 (holdout / train 평균, 전 기간 Calmar leave-one-pattern-out)")
    diag_pat = {}
    for p in sorted({t["pattern"] for t in removed}):
        h = [t["ret"] for t in rm_H if t["pattern"] == p]
        tr = [t["ret"] for t in rm_T if t["pattern"] == p]
        loo = vp.simulate([t for t in base if not (is_removed(t) and t["pattern"] == p)], "current")["calmar"]
        diag_pat[p] = dict(n_h=len(h), mean_h=mean(h), n_t=len(tr), mean_t=mean(tr), loo_calmar=loo)
        fm = lambda x: ('%+.2f%%' % (x * 100)) if x is not None else 'NA'
        print(f"  {p:20} holdout n={len(h):4} {fm(mean(h)):>8} / train n={len(tr):4} {fm(mean(tr)):>8} / LOO Calmar {loo:5.2f}")
    diag_dd = {}
    try:
        bk = btc_dd_bucket(detlib.load_ohlcv("BTC", "1d"))
        for b in ("dd0_10", "dd10_20", "dd20p"):
            rs_ = [t["ret"] for t in removed if bk.get(t["date"]) == b]
            diag_dd[b] = dict(n=len(rs_), mean=mean(rs_))
            print(f"  BTC 낙폭 {b:8} n={len(rs_):5} 평균 {('%+.2f%%' % (mean(rs_)*100)) if rs_ else 'NA'}")
    except Exception as e:                      # 진단 전용 — 판정에 영향 없음
        print(f"  BTC 낙폭 버킷 생략: {e}")

    json.dump(dict(prereg="bull_btc_prereg_2026_10_26", verdict=verdict, fails=fails, thin=thin, deploy=deployable(verdict, k5),
                   k1=f["k1"], k2=f["k2"], k3=f["k3"], k4=f["k4"], k5=k5, k6=k6, k7=f["k7"],
                   full={a: {x: y for x, y in v.items() if x != "blocked_by"} for a, v in full.items()},
                   holdout_days=len(H), train_days=len(T), episodes=tab, diag_pat=diag_pat, diag_dd=diag_dd,
                   rand_calmar_median=st.median(rand_cal)),
              open("_bull_btc.json", "w"), indent=1, ensure_ascii=False, default=str)


if __name__ == "__main__":
    main()
