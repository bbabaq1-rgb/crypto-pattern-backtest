"""
validate_short_exit.py — 숏의 레짐 청산 재검토 (선택 편향 통제, 2026-09-04 사용자 지시).

배경
----
레짐 청산 소거 시험(method_s, 유니버스 80)에서 **홀드아웃 구간에서만** 숏 두 셀이
레짐 청산을 빼는 쪽(D_norg)에 유리하게 나왔다.

  engulfing_short  train −2.02%p (t −5.21, 분기 89건 D_norg 승률 24%)
                 holdout **+0.93%p** (t 2.19, 분기 9건 승률 89%)
  fvg_short        train −0.66%p (t −7.59, 분기 213건 승률 21%)
                 holdout **+0.26%p** (t 3.19, 분기 28건 승률 75%)

부호가 train 과 holdout 에서 정확히 뒤집힌다. 그리고 그 holdout(2025-09~2026-09)은
**2026년이 bear 247일 단일**인 구간이다 — 숏에게 유리한 국면이 계속되면 안 끊고 버티는 쪽이
좋은 게 당연하다. 즉 '숏의 성질'이 아니라 '한 국면의 성질'일 가능성이 크다.

이건 **사후 선택된 셀**이다(7패턴 × 3 arm × 2 분할을 본 뒤 좋은 둘을 골랐다). 그래서 이
스크립트는 "숏이 특별한가"를 **반증하려 시도**한다. 그냥 다시 돌려 같은 답이 나오는 건
증거가 아니다.

시험 arm (숏 패턴에만 적용, 롱은 규칙상 D 와 동일)
--------------------------------------------------
  S_norg : 숏은 레짐 전환으로 청산하지 않는다(손절·반대신호·30봉 만기만). 관찰된 그 규칙.
  S_adv  : 숏은 **불리 국면(bull_btc/bull_altseason)으로 들어가는 전환에만** 청산한다.
           method_r 의 RL 은 롱에만 방향 인지를 넣고 숏은 D 그대로 뒀다 — 그 거울상이며
           한 번도 시험된 적이 없다. '유리 전환에 끊지 말자'의 원칙적 형태다.

네 가지 반증 시험 (사전 등록, 실행 전 고정)
--------------------------------------------
1. **시간 분할** — 전 구간을 전반/후반으로 나눠 양쪽 모두 우위가 재현되는가.
   한쪽에만 있으면 잡음이다. (사전 예상: train 이 강하게 음수였으므로 탈락 가능성 높음)
2. **부트스트랩 CI** — 짝지음 차이를 재표본한 95% 신뢰구간이 0 을 배제하고 양수인가.
3. **대조군(플라시보)** — 같은 규칙을 **롱**에 적용했을 때도 좋아지는가. 롱도 같이 좋아지면
   '숏 특유'가 아니라 기간·레짐 효과다. 숏 우위가 롱 우위보다 커야 통과.
4. **레짐 층화** — 우위가 bear 진입 거래에만 있는가. bear 밖(bull_btc/bull_altseason 진입)
   에서도 양수여야 통과. bear 에만 있으면 단일 레짐 의존이고 홀드아웃 관찰의 재현일 뿐이다.

판정: 4개 중 3개 이상 SURVIVES / 2개 PARTIAL(데이터 누적 후 재시험) / 1개 이하 NOISE(추격 중단).
실거래 코드 무변경. 출력 _short_exit.json + RESULT_JSON.
실행: python validate_short_exit.py [--no-fetch] [--majors]
"""
import json
import random
import statistics as st
import sys
from math import sqrt

import detlib
import method_m as mm
import method_r as mr
import method_s as ms
import method_t as mt
import regime_switch as rs

STOP, MAX_HOLD, FEE = ms.STOP, ms.MAX_HOLD, ms.FEE
FETCH_DAYS = ms.FETCH_DAYS
BOOT_N, SEED = 2000, 42
ARMS = ["S_norg", "S_adv"]
# 불리 국면: 숏은 상승 국면이 불리, 롱은 하락 국면이 불리(method_r.ADVERSE R1 과 동일)
ADVERSE = {"short": frozenset({"bull_btc", "bull_altseason"}), "long": frozenset({"bear"})}
MIN_STRATA_N = 20


def outcome(rows, si, direction, opp_set, lab, mode):
    """
    mode "D"    : 레짐 라벨이 진입 때와 달라지면 청산 (현행 eval_D)
         "norg" : 레짐 청산 없음
         "adv"  : 불리 국면으로 **들어가는** 전환에만 청산 (method_m.outcome rule="RL" 과 동일 의미)
    반환 (ret, hold, reason).
    """
    base = rows[si]["c"]
    entry_reg = lab(si)
    end = min(si + MAX_HOLD, len(rows) - 1)
    is_long = direction == "long"
    stop_px = base * (1 - STOP) if is_long else base * (1 + STOP)
    adv = ADVERSE[direction] if mode == "adv" else None
    prev_adv = (entry_reg in adv) if adv else None
    for j in range(si + 1, end + 1):
        hit = rows[j]["l"] <= stop_px if is_long else rows[j]["h"] >= stop_px
        if hit:
            return -STOP - FEE, j - si, "stop"
        cur = lab(j)
        if mode == "norg":
            regsw = False
        elif adv is None:
            regsw = cur not in (None, entry_reg)
        elif cur is None:
            regsw = False
        else:
            cur_adv = cur in adv
            regsw = cur_adv and not prev_adv
            prev_adv = cur_adv
        if j in opp_set or regsw:
            c = rows[j]["c"]
            r = (c - base) / base if is_long else (base - c) / base
            return r - FEE, j - si, ("opp_signal" if j in opp_set else "regime_switch")
    px = rows[end]["o"]
    r = (px - base) / base if is_long else (base - px) / base
    return r - FEE, end - si, "maxhold"


def eval_pattern(collected, direction, regmap, mode):
    """[(entry_date, ret, hold, reason, entry_regime)] — arm 간 순서가 같아 짝지음이 성립."""
    out = []
    for rows, opp_set, sigs in collected:
        lab = (lambda j, r=rows: regmap.get(r[j]["date"]))
        for si in sigs:
            ret, hold, reason = outcome(rows, si, direction, opp_set, lab, mode)
            out.append((rows[si]["date"], ret, hold, reason, lab(si)))
    return out


def paired(base, arm):
    d = [a[1] - b[1] for a, b in zip(arm, base)]
    n = len(d)
    if not n:
        return dict(n=0, mean=0.0, t=0.0, div_n=0, arm_wins=0, arm_losses=0, winrate=0.0)
    m = st.mean(d)
    sd = st.stdev(d) if n > 1 else 0.0
    t = m / (sd / sqrt(n)) if sd > 0 else 0.0
    div = [x for x in d if abs(x) > 1e-12]
    w = sum(1 for x in div if x > 0)
    return dict(n=n, mean=m, t=t, div_n=len(div), arm_wins=w, arm_losses=len(div) - w,
                winrate=(w / len(div) if div else 0.0))


def boot_ci(base, arm, n=BOOT_N, seed=SEED):
    d = [a[1] - b[1] for a, b in zip(arm, base)]
    if not d:
        return (0.0, 0.0)
    rng = random.Random(seed)
    means = sorted(st.mean(rng.choices(d, k=len(d))) for _ in range(n))
    return (means[int(n * 0.025)], means[int(n * 0.975)])


def split_half(base, arm):
    """진입 날짜 중앙값으로 전반/후반 분할."""
    dates = sorted(b[0] for b in base)
    if not dates:
        return None, None
    cut = dates[len(dates) // 2]
    i1 = [i for i, b in enumerate(base) if b[0] < cut]
    i2 = [i for i, b in enumerate(base) if b[0] >= cut]
    return (paired([base[i] for i in i1], [arm[i] for i in i1]),
            paired([base[i] for i in i2], [arm[i] for i in i2]))


def by_regime(base, arm):
    """
    진입 레짐별 짝지음 차이. 레짐 맵 워밍업(200일선+기울기) 이전 진입은 라벨이 None 이라
    층화 대상에서 제외한다 — 짝지음 합산에는 그대로 들어간다(실제 거래이므로).
    """
    out = {}
    for b, a in zip(base, arm):
        if b[4] is None:
            continue
        out.setdefault(b[4], []).append(a[1] - b[1])
    return {k: dict(n=len(v), mean=st.mean(v)) for k, v in sorted(out.items())}


def pool(items):
    """[(mean, n)] -> 표본 가중 평균."""
    tot = sum(n for _, n in items)
    return (sum(m * n for m, n in items) / tot) if tot else 0.0


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    ms.UNIVERSE_MODE = "--majors" not in argv
    syms = ms.symbols()
    print(f"[표본] {len(syms)}종목 ({'유니버스 80' if ms.UNIVERSE_MODE else '메이저'})")
    if "--no-fetch" not in argv:
        ms.ensure_data(FETCH_DAYS, syms)
    regmap = rs.build_regime_map()
    print(f"[regime] {len(regmap)}일 | 전환 {ms.flips(regmap)}회")
    shorts = [p for p in mt.PATS if p[1] == "short"]
    longs = [p for p in mt.PATS if p[1] == "long"]
    print(f"[패턴] 숏 {[p[0] for p in shorts]} | 대조군 롱 {[p[0] for p in longs]}")
    print("=" * 120)
    print("숏 레짐 청산 재검토 — 사후 선택 셀 반증 4종 (시간분할 / 부트스트랩CI / 대조군 / 레짐층화)")
    print("=" * 120)

    results = {"short": {}, "long": {}}
    for side, pats in (("short", shorts), ("long", longs)):
        for label, direction, detmod, oppmod, tf in pats:
            collected = ms.collect(detmod, oppmod, tf, syms)
            if not collected:
                continue
            base = eval_pattern(collected, direction, regmap, "D")
            if not base:
                continue
            rec = {"n": len(base), "tf": tf, "direction": direction,
                   "D_mean": st.mean(b[1] for b in base)}
            for arm in ARMS:
                a = eval_pattern(collected, direction, regmap, "norg" if arm == "S_norg" else "adv")
                p = paired(base, a)
                h1, h2 = split_half(base, a)
                rec[arm] = dict(paired=p, ci=boot_ci(base, a), half1=h1, half2=h2,
                                by_regime=by_regime(base, a),
                                reasons=mr._count(x[3] for x in a))
            results[side][label] = rec
            print(f"\n[{label} @{tf} {direction}] n={len(base)} D 건당 {rec['D_mean']*100:+.2f}%")
            for arm in ARMS:
                r = rec[arm]; p = r["paired"]
                print(f"  {arm:<8} 짝지음 {p['mean']*100:+.3f}%p t={p['t']:+.2f} "
                      f"분기 {p['div_n']}건 승률 {p['winrate']*100:.0f}% | "
                      f"CI[{r['ci'][0]*100:+.2f}, {r['ci'][1]*100:+.2f}] | "
                      f"전반 {(r['half1'] or {}).get('mean', 0)*100:+.3f} 후반 {(r['half2'] or {}).get('mean', 0)*100:+.3f}")
                print(f"  {'':<8} 레짐별 " + "  ".join(
                    f"{k}:{v['mean']*100:+.2f}%p(n{v['n']})" for k, v in r["by_regime"].items()))

    print("\n" + "=" * 120)
    print("합산 + 반증 판정")
    verdicts = {}
    for arm in ARMS:
        sp = [(results["short"][l][arm]["paired"]["mean"], results["short"][l]["n"]) for l in results["short"]]
        lp = [(results["long"][l][arm]["paired"]["mean"], results["long"][l]["n"]) for l in results["long"]]
        s_mean, l_mean = pool(sp), pool(lp)
        h1 = pool([((results["short"][l][arm]["half1"] or {}).get("mean", 0.0),
                    (results["short"][l][arm]["half1"] or {}).get("n", 0)) for l in results["short"]])
        h2 = pool([((results["short"][l][arm]["half2"] or {}).get("mean", 0.0),
                    (results["short"][l][arm]["half2"] or {}).get("n", 0)) for l in results["short"]])
        ci_lo = pool([(results["short"][l][arm]["ci"][0], results["short"][l]["n"]) for l in results["short"]])
        ci_hi = pool([(results["short"][l][arm]["ci"][1], results["short"][l]["n"]) for l in results["short"]])
        reg = {}
        for l in results["short"]:
            for k, v in results["short"][l][arm]["by_regime"].items():
                a = reg.setdefault(k, [0, 0.0]); a[0] += v["n"]; a[1] += v["mean"] * v["n"]
        reg = {k: dict(n=n, mean=(sd / n if n else 0.0)) for k, (n, sd) in reg.items()}
        non_bear = [v["mean"] for k, v in reg.items() if k != "bear" and v["n"] >= MIN_STRATA_N]
        c1 = h1 > 0 and h2 > 0
        c2 = ci_lo > 0
        c3 = s_mean > l_mean
        c4 = bool(non_bear) and all(x > 0 for x in non_bear)
        passed = sum((c1, c2, c3, c4))
        v = "SURVIVES" if passed >= 3 else ("PARTIAL" if passed == 2 else "NOISE")
        verdicts[arm] = dict(short_mean=s_mean, long_mean=l_mean, half1=h1, half2=h2,
                             ci=[ci_lo, ci_hi], by_regime=reg, c1_split=c1, c2_ci=c2,
                             c3_placebo=c3, c4_regime=c4, n_passed=passed, verdict=v)
        print(f"\n  {arm}: 숏 합산 {s_mean*100:+.3f}%p | 롱(대조군) {l_mean*100:+.3f}%p")
        print(f"    ① 시간분할  전반 {h1*100:+.3f} / 후반 {h2*100:+.3f}  -> {'통과' if c1 else '탈락'}")
        print(f"    ② 부트CI    [{ci_lo*100:+.3f}, {ci_hi*100:+.3f}]              -> {'통과' if c2 else '탈락'}")
        print(f"    ③ 대조군    숏 {s_mean*100:+.3f} vs 롱 {l_mean*100:+.3f}      -> {'통과' if c3 else '탈락'}")
        print(f"    ④ 레짐층화  " + "  ".join(f"{k}:{v['mean']*100:+.2f}%p(n{v['n']})" for k, v in reg.items())
              + f"  -> {'통과' if c4 else '탈락'}")
        print(f"    => {passed}/4  **{v}**")
    print("\n  3개 이상 SURVIVES(배포 검토) / 2개 PARTIAL(데이터 누적 후 재시험) / 1개 이하 NOISE(추격 중단)")
    json.dump(dict(arms=ARMS, n_symbols=len(syms), adverse={k: sorted(v) for k, v in ADVERSE.items()},
                   results=results, verdicts=verdicts),
              open("_short_exit.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1,
              default=mr._jsonable)
    print("\nRESULT_JSON: " + json.dumps({a: dict(verdict=v["verdict"], passed=v["n_passed"],
                                                  short=round(v["short_mean"], 5),
                                                  long=round(v["long_mean"], 5))
                                          for a, v in verdicts.items()}, separators=(",", ":")))


if __name__ == "__main__":
    main()
