"""
method_r.py — 방향 인지 레짐 청산 시험: 방식D vs 방식R.

배경
----
방식D(현행 실거래)의 레짐 전환 청산은 **방향을 보지 않는다.**

    regsw = regmap[date] not in (None, entry_reg)      # paper_executor.eval_D

진입 당시와 레짐이 다르기만 하면 롱·숏 가리지 않고 종가 청산한다. 그 결과
bear 에서 바닥을 잡은 롱(engulfing/marubozu/triple_bottom 이 bear 에서 롱으로 라우팅됨)은
레짐이 bull 로 **유리하게** 바뀌는 순간 청산된다 — 상승을 타야 할 때 내리는 셈이다.
같은 규칙이 숏에는 손절 역할을, 롱에는 수익 기회를 끊는 역할을 한다.

사용자 관찰(2026-09-03): "하락 국면에서 바닥을 잡고 상승을 탔는데 상승 전환됐다고
청산되면 안 된다. 상승일 때 다 먹다가 다시 하락으로 바뀔 때 청산해야 고점을 보고
나온다." — 이 규칙이 방식R 이다.

방식R = 방식D 에서 레짐 조건만 교체: **불리한 국면으로 들어가는 전환**에만 청산.
  R1 : 롱 불리 = {bear},           숏 불리 = {bull_btc, bull_altseason}.  sideways 중립(유지)
  R2 : 롱 불리 = {bear, sideways}, 숏 불리 = {bull_*, sideways}.          횡보도 불리로 간주
'전환'은 직전 상태가 불리가 아니었다가 불리가 되는 순간이다. 진입 자체가 불리 국면이면
(bear 롱) 이미 불리 상태에서 시작하므로, 한 번 벗어났다가 **다시 들어올 때** 청산된다.
손절 -8% / 반대패턴 신호 / 최대 30봉은 방식D 와 동일하게 둔다.

방법
----
method_t.py 와 같은 틀 — 같은 신호에 세 규칙을 동시에 적용하는 **짝지음(paired)** 비교.
가격 경로가 동일하므로 종목·시점 교란이 상쇄되어 분리 비교보다 검정력이 훨씬 높다.
두 규칙이 실제로 갈라지는 거래(분기 거래)만 따로 떼어 어느 쪽이 이겼는지도 센다 —
대부분의 거래는 레짐이 안 바뀌어 두 규칙이 같은 결과를 내므로, 평균차이가 작아
보여도 분기 거래 안에서는 큰 차이일 수 있다.
사용자 시나리오(bear 진입 롱 → bull 전환)를 따로 잘라 본다.
자산곡선(가용잔고 20%/12포지션/2x, method_t 와 동일)으로 CAGR/MDD 도 병기한다.

사전 등록 판정 기준 (결과를 보기 전에 정한다)
------------------------------------------
방식R 채택 조건 — 아래 전부:
  1) 7패턴 합산 짝지음 평균차이 > 0 이고 t > 2.0 (또는 부트스트랩 p < 0.05)
  2) CAGR 우위 패턴 수 >= 4/7
  3) 짝지음 t < -2.0 인 패턴이 하나도 없음 (특정 패턴을 크게 망치지 않음)
  4) 분기 거래 안에서 R 승률 > 50%
R1 과 R2 가 같은 방향이면 구조, 한쪽만 튀면 잡음으로 본다.

실행: python method_r.py   (Actions 러너 — 데이터 자동 수집, method_r.yml)
"""
import importlib
import json
import random
import statistics as st

import detlib
import regime_switch as rs
import method_t as mt                       # PATS / ensure_data / summ / paired_stats / equity_curve

STOP_LOSS_PCT = mt.STOP_LOSS_PCT
MAX_HOLD      = mt.MAX_HOLD
FEE           = mt.FEE

MODES = ["D", "R1", "R2"]
ADVERSE = {
    "R1": {"long": {"bear"},
           "short": {"bull_btc", "bull_altseason"}},
    "R2": {"long": {"bear", "sideways"},
           "short": {"bull_btc", "bull_altseason", "sideways"}},
}
BOOT_N = 2000
BOOT_SEED = 7

REGMAP = {}


# ── 청산 규칙 ───────────────────────────────────────────────────────────────
def outcome_r(rows, si, direction, opp_set, mode):
    """
    mode="D"  : 방식D 그대로 (method_t.outcome_d 와 동일 결과 — 테스트로 고정)
    mode="R1"/"R2": 레짐 조건만 '불리 국면 진입 시'로 교체.
    반환: (ret, hold_bars, reason)
    """
    base = rows[si]["c"]
    entry_reg = REGMAP.get(rows[si]["date"])
    end = min(si + MAX_HOLD, len(rows) - 1)
    adv = ADVERSE.get(mode, {}).get(direction, set())
    prev_adv = entry_reg in adv

    for j in range(si + 1, end + 1):
        # 1) 손절 (봉 내) — 항상 먼저
        if direction == "long":
            if rows[j]["l"] <= base * (1 - STOP_LOSS_PCT):
                return -STOP_LOSS_PCT - FEE, j - si, "stop"
        else:
            if rows[j]["h"] >= base * (1 + STOP_LOSS_PCT):
                return -STOP_LOSS_PCT - FEE, j - si, "stop"

        # 2) 레짐 조건
        cur = REGMAP.get(rows[j]["date"])
        if mode == "D":
            regsw = cur not in (None, entry_reg)
        else:
            if cur is None:
                regsw = False                       # 레짐 정보 없는 봉은 판단 보류
            else:
                cur_adv = cur in adv
                regsw = cur_adv and not prev_adv    # 불리 국면으로 '들어가는' 순간만
                prev_adv = cur_adv

        # 3) 반대 신호 / 레짐 (종가)
        if j in opp_set or regsw:
            c = rows[j]["c"]
            r = (c - base) / base if direction == "long" else (base - c) / base
            return r - FEE, j - si, ("opp_signal" if j in opp_set else "regime_switch")

    px = rows[end]["o"]
    r = (px - base) / base if direction == "long" else (base - px) / base
    return r - FEE, end - si, "maxhold"


# ── 통계 보조 ───────────────────────────────────────────────────────────────
def boot_p(diffs, n=BOOT_N, seed=BOOT_SEED):
    """짝지음 차이의 부트스트랩: 평균차이 <= 0 인 재표본 비율 (단측)."""
    if len(diffs) < 2:
        return 1.0
    rng = random.Random(seed)
    k = len(diffs)
    le = 0
    for _ in range(n):
        s = sum(diffs[rng.randrange(k)] for _ in range(k)) / k
        if s <= 0:
            le += 1
    return le / n


def divergence(base, arm):
    """
    두 규칙이 실제로 갈라진 거래만 비교.
    base/arm: [(entry_date, exit_date, ret, hold, reason)] 같은 순서.
    """
    idx = [i for i, (b, a) in enumerate(zip(base, arm))
           if b[3] != a[3] or b[4] != a[4] or abs(b[2] - a[2]) > 1e-12]
    if not idx:
        return dict(n=0)
    bd = [base[i][2] for i in idx]
    ad = [arm[i][2] for i in idx]
    d = [a - b for a, b in zip(ad, bd)]
    return dict(n=len(idx),
                share=len(idx) / len(base),
                base_mean=st.mean(bd), arm_mean=st.mean(ad),
                base_median=st.median(bd), arm_median=st.median(ad),
                mean_diff=st.mean(d),
                arm_wins=sum(1 for x in d if x > 1e-12),
                arm_losses=sum(1 for x in d if x < -1e-12),
                base_reasons=_count(base[i][4] for i in idx),
                arm_reasons=_count(arm[i][4] for i in idx),
                base_hold=st.mean(base[i][3] for i in idx),
                arm_hold=st.mean(arm[i][3] for i in idx))


def _count(it):
    out = {}
    for x in it:
        out[x] = out.get(x, 0) + 1
    return out


def _jsonable(x):
    """json.dump default — set 을 정렬 리스트로 (1차 실행이 ADVERSE 의 set 에서 죽었다)."""
    if isinstance(x, (set, frozenset)):
        return sorted(x)
    raise TypeError(f"not serializable: {type(x).__name__}")


# ── 실행 ────────────────────────────────────────────────────────────────────
def run_pattern(label, direction, detmod, oppmod, tf):
    mod = importlib.import_module(detmod)
    opp = importlib.import_module(oppmod) if oppmod else None

    arms = {m: [] for m in MODES}
    entry_regs = []                             # 신호별 진입 레짐 (시나리오 분해용)

    for sym in detlib.SYMBOLS:
        try:
            rows = detlib.load_ohlcv(sym, tf)
        except (FileNotFoundError, RuntimeError):
            continue
        if len(rows) < 40:
            continue
        opp_set = set(opp.detect(rows)) if opp else set()
        for si in mod.detect(rows):
            if si + 1 >= len(rows):
                continue
            entry_regs.append(REGMAP.get(rows[si]["date"]))
            for m in MODES:
                ret, hold, reason = outcome_r(rows, si, direction, opp_set, m)
                xi = min(si + hold, len(rows) - 1)
                arms[m].append((rows[si]["date"], rows[xi]["date"], ret, hold, reason))

    if not arms["D"]:
        return None

    base = arms["D"]
    base_rets = [t[2] for t in base]
    out = {}
    for m in MODES:
        trades = arms[m]
        rec = dict(per_trade=mt.summ(trades),
                   equity=mt.equity_curve(sorted(trades, key=lambda t: t[0])),
                   reasons=_count(t[4] for t in trades))
        if m != "D":
            rets = [t[2] for t in trades]
            p = mt.paired_stats(base_rets, rets)
            p["boot_p"] = boot_p([a - b for a, b in zip(rets, base_rets)])
            rec["paired_vs_D"] = p
            rec["divergence"] = divergence(base, trades)
            # 사용자 시나리오: 불리 국면에서 진입한 거래(bear 롱 / bull 숏)만
            adv = ADVERSE[m][direction]
            sub = [i for i, r in enumerate(entry_regs) if r in adv]
            if len(sub) >= 2:
                sb = [base_rets[i] for i in sub]
                sa = [rets[i] for i in sub]
                ps = mt.paired_stats(sb, sa)
                ps["boot_p"] = boot_p([a - b for a, b in zip(sa, sb)])
                ps["base_mean"] = st.mean(sb)
                ps["arm_mean"] = st.mean(sa)
                rec["adverse_entry_subset"] = ps
        out[m] = rec
    out["_entry_regime_counts"] = _count(entry_regs)
    return out


def verdict(results, arm):
    """사전 등록 기준 4개를 전부 만족하는가."""
    if not results:
        return dict(pass_=False, reason="no results")
    pooled = results["_pooled"][arm]
    c1 = pooled["mean_diff"] > 0 and (pooled["t"] > 2.0 or pooled["boot_p"] < 0.05)
    pats = [lb for lb in results if not lb.startswith("_")]
    cw = sum(1 for lb in pats
             if results[lb][arm]["equity"]["cagr"] > results[lb]["D"]["equity"]["cagr"])
    c2 = cw >= 4
    c3 = all(results[lb][arm]["paired_vs_D"]["t"] >= -2.0 for lb in pats)
    dv = results["_pooled"][arm]["divergence"]
    c4 = dv["n"] > 0 and dv["arm_wins"] > dv["arm_losses"]
    return dict(pass_=bool(c1 and c2 and c3 and c4),
                c1_pooled_sig=c1, c2_cagr_wins=cw, c3_no_pattern_hurt=c3,
                c4_divergence_winrate=c4)


def main():
    global REGMAP
    mt.ensure_data()
    REGMAP = rs.build_regime_map()
    mt.REGMAP = REGMAP
    print(f"[regime] 레짐맵 {len(REGMAP)}일")
    results = {}

    print("=" * 112)
    print("방식D(레짐 바뀌면 무조건 청산) vs 방식R(불리 국면 진입 시에만 청산)")
    print("  R1: 롱 불리={bear} / 숏 불리={bull_*}  sideways 중립   |   R2: sideways 도 불리")
    print(f"  손절 -{int(STOP_LOSS_PCT*100)}% / 반대신호 / 최대 {MAX_HOLD}봉 동일. "
          f"자산곡선 가용잔고x{mt.SIM_POS_PCT:.0%}/{mt.SIM_MAX_POS}포지션/{mt.SIM_LEVERAGE}x")
    print("=" * 112)

    pooled = {m: [] for m in MODES[1:]}

    for label, direction, detmod, oppmod, tf in mt.PATS:
        try:
            res = run_pattern(label, direction, detmod, oppmod, tf)
        except Exception as e:
            print(f"\n[{label}] 실행 오류: {str(e)[:80]}")
            continue
        if not res:
            print(f"\n[{label}] 신호 없음 — 스킵")
            continue
        results[label] = res

        print(f"\n[{label} @{tf} {direction}]  진입레짐 {res['_entry_regime_counts']}")
        print(f"  {'arm':<4}{'n':>5}{'건당평균':>10}{'중앙':>9}{'승률':>7}{'평균보유':>8}"
              f"  |{'짝지음차이':>11}{'t':>7}{'boot_p':>8}{'승/패':>9}"
              f"  |{'분기n':>6}{'분기R승률':>10}  |{'CAGR':>8}{'MDD':>8}{'Calmar':>8}")
        print("  " + "-" * 108)
        for m in MODES:
            r = res[m]
            s, eq = r["per_trade"], r["equity"]
            if m == "D":
                pair = f"{'(기준)':>11}{'':>7}{'':>8}{'':>9}"
                dvs = f"{'-':>6}{'-':>10}"
            else:
                p = r["paired_vs_D"]; dv = r["divergence"]
                pair = (f"{p['mean_diff']*100:>+10.2f}%{p['t']:>7.2f}{p['boot_p']:>8.3f}"
                        f"{p['wins']:>4}/{p['losses']:<4}")
                wr = (dv["arm_wins"] / (dv["arm_wins"] + dv["arm_losses"])
                      if dv["n"] and (dv["arm_wins"] + dv["arm_losses"]) else 0)
                dvs = f"{dv['n']:>6}{wr:>9.0%}"
            print(f"  {m:<4}{s['n']:>5}{s['mean']*100:>+9.2f}%{s['median']*100:>+8.2f}%"
                  f"{s['winrate']:>6.0%}{s['avghold']:>8.1f}  |{pair}  |{dvs}"
                  f"  |{eq['cagr']*100:>+7.1f}%{eq['mdd']*100:>+7.1f}%{eq['calmar']:>8.2f}")
            print(f"       사유 {r['reasons']}")
        for m in MODES[1:]:
            sub = res[m].get("adverse_entry_subset")
            if sub:
                print(f"  [{m} 불리국면 진입 거래만 n={sub['n']}] D {sub['base_mean']*100:+.2f}% "
                      f"→ {m} {sub['arm_mean']*100:+.2f}%  차이 {sub['mean_diff']*100:+.2f}%p "
                      f"t={sub['t']:.2f} boot_p={sub['boot_p']:.3f} 승/패 {sub['wins']}/{sub['losses']}")

        # per-pattern 결과에서 짝지음 차이만 모아 합산
        n = res["D"]["per_trade"]["n"]
        for m in MODES[1:]:
            p = res[m]["paired_vs_D"]
            pooled[m].append((p["mean_diff"], p["sd_diff"] if "sd_diff" in p else 0.0, n,
                              res[m]["divergence"]))

    if not results:
        print("결과 없음")
        return

    # ── 합산 (패턴 가중 평균 + 분기 거래 합) ─────────────────────────────────
    print("\n" + "=" * 112)
    print("종합 — 7패턴 합산")
    print("=" * 112)
    results["_pooled"] = {}
    for m in MODES[1:]:
        tot_n = sum(x[2] for x in pooled[m])
        mean_diff = sum(x[0] * x[2] for x in pooled[m]) / tot_n
        # 합산 t: 패턴별 분산을 표본수 가중으로 합침 (근사)
        var = sum((x[1] ** 2) * x[2] for x in pooled[m]) / tot_n if tot_n else 0.0
        t = mean_diff / ((var ** 0.5) / (tot_n ** 0.5)) if var > 0 else 0.0
        # 부트스트랩은 패턴별 boot_p 의 최소값이 아니라 합산 재표본이 필요 — 근사로
        # 패턴 가중 평균차이의 부호 안정성을 패턴 단위 재표본으로 본다
        rng = random.Random(BOOT_SEED)
        items = [(x[0], x[2]) for x in pooled[m]]
        le = 0
        for _ in range(BOOT_N):
            smp = [items[rng.randrange(len(items))] for _ in items]
            s = sum(a * w for a, w in smp) / sum(w for _, w in smp)
            if s <= 0:
                le += 1
        dv_n = sum(x[3]["n"] for x in pooled[m])
        dv_w = sum(x[3].get("arm_wins", 0) for x in pooled[m])
        dv_l = sum(x[3].get("arm_losses", 0) for x in pooled[m])
        results["_pooled"][m] = dict(n=tot_n, mean_diff=mean_diff, t=t, boot_p=le / BOOT_N,
                                     divergence=dict(n=dv_n, arm_wins=dv_w, arm_losses=dv_l))
        pats = [lb for lb in results if not lb.startswith("_")]
        pw = sum(1 for lb in pats if results[lb][m]["paired_vs_D"]["mean_diff"] > 0)
        cw = sum(1 for lb in pats
                 if results[lb][m]["equity"]["cagr"] > results[lb]["D"]["equity"]["cagr"])
        hurt = [lb for lb in pats if results[lb][m]["paired_vs_D"]["t"] < -2.0]
        print(f"  {m}: 합산 n={tot_n} 짝지음 평균차이 {mean_diff*100:+.3f}%p t={t:.2f} "
              f"boot_p(패턴재표본)={le/BOOT_N:.3f} | 짝지음우위 {pw}/{len(pats)} "
              f"CAGR우위 {cw}/{len(pats)} | 분기 {dv_n}건 R승/패 {dv_w}/{dv_l} | "
              f"t<-2 패턴 {hurt or '없음'}")

    summary = {}
    for m in MODES[1:]:
        v = verdict(results, m)
        summary[m] = v
        print(f"  [{m} 판정] {'PASS' if v['pass_'] else 'REJECT'}  "
              f"합산유의={v['c1_pooled_sig']} CAGR우위={v['c2_cagr_wins']}/7 "
              f"패턴훼손없음={v['c3_no_pattern_hurt']} 분기승률>50%={v['c4_divergence_winrate']}")

    payload = dict(config=dict(stop=STOP_LOSS_PCT, max_hold=MAX_HOLD, fee=FEE,
                               adverse={m: {d: sorted(s) for d, s in v.items()}
                                        for m, v in ADVERSE.items()},
                               boot_n=BOOT_N,
                               sim=dict(pos_pct=mt.SIM_POS_PCT, max_pos=mt.SIM_MAX_POS,
                                        leverage=mt.SIM_LEVERAGE, start=mt.SIM_START_EQ)),
                   patterns={k: v for k, v in results.items() if not k.startswith("_")},
                   pooled=results["_pooled"], summary=summary)
    json.dump(payload, open("method_r.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1, default=_jsonable)
    print("\n[저장] method_r.json")
    print("RESULT_SUMMARY: " + json.dumps(summary, separators=(",", ":")))


if __name__ == "__main__":
    main()
