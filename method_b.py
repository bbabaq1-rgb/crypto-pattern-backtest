"""
method_b.py — beta_slope 2단계: 진입 필터 / 사이징 오버레이 짝지음 시험 (2026-09-05, 사전 등록).

## 왜

regime_axis 1단계(2026-09-04)에서 배포 7패턴 방식D 거래를 진입 시점 축 값 3분위로 갈랐을 때
**beta_slope**(횡단면 베타 팩터 수익률 — 고베타 알트가 이기는 날 양수)만 A∧B∧C 를 만족했다:
하위 3분위 −0.81% / 상위 +3.59%, 스프레드 +4.40%p. 그리고 2026-09-05 상관 진단에서 **현행 채택 규칙
avg_cap 과 독립**임을 확인했다 — Pearson 0.139, avg_cap 하위·중간 3분위 **안에서** beta 스프레드
+5.89 / +8.43%p(p .000), 상위(안일 국면)에선 소멸. 즉 avg_cap 오버레이(complacent 에서만 롱 축소)가
**작동하지 않는 국면**에서 beta_slope 가 정보를 갖는다. 상보적이라 얹을 가치가 있다.

## arm (모두 방식D 청산 — 다른 것은 진입 포함 여부 / 크기뿐)

  D        현행.
  B_skip   진입 시점 beta_slope 가 **하위 3분위**면 롱 진입을 건너뛴다. 숏은 무관(avg_cap 오버레이와
           같은 롱 전용 규칙). 짝지음: 건너뛴 거래는 arm 쪽 수익 0 — 짝지음 차이 = −(D 수익).
  B_size   같은 조건에서 진입은 하되 **크기 ×0.5** (축소만, upsize 없음 — REGIME_CAP_MULT 0.6 과 같은
           보수 원칙). 건당 수익은 D 와 동일하므로 자산곡선·부트스트랩으로만 판정한다.

**3분위 컷은 인과적**: 날짜 d 의 컷은 d 이전 값들의 3분위(확장 창, 최소 BURN_IN 일). 전체 표본 3분위를
쓰면 미래 값으로 컷을 정하는 룩어헤드다. 컷이 정의되지 않는 초기 구간은 '중간'으로 두어 arm 이
D 와 같게 행동한다.

## 사전 등록 판정 (결과를 보기 전에 동결) — arm X 가 7개 전부 만족해야 채택

  ① 걸러진 집합의 질 — 스킵/축소된 거래의 D 수익 평균이 나머지 롱 거래 평균보다 낮고, 그 자체가
     음수. 두 집단 부트스트랩 boot_p < 0.05 (regime_axis.boot_diff_p). 걸러진 n >= 30.
  ② train 포트폴리오 CAGR > D
  ③ train Calmar > D
  ④ 시간 분할 — train 전반/후반 각각 CAGR 우위
  ⑤ MDD 가 D 대비 5%p 넘게 악화되지 않음
  ⑥ 짝지음 블록 부트스트랩 Calmar 우위 >= 60%
  ⑦ holdout(마지막 365일) CAGR 우위

통과 → **자율 반영 권한**(CLAUDE.md 2026-09-05)에 따라 실거래 반영: paper_executor 진입 경로에
avg_cap 오버레이와 나란히 beta 오버레이(B_size 가 통과하면 ×0.5, B_skip 이 통과하면 스킵. 둘 다면
B_skip 우선 — 더 단순하고 자본을 더 아낀다). 경계값·부분 통과는 반영하지 않는다.

## 이 프레임이 못 보는 것 (명시)

  · 자산곡선은 avg_cap 오버레이를 모델링하지 않는다 — 여기서 재는 것은 beta 오버레이 **단독** 효과.
    실거래에서는 둘이 겹친다. 상관 진단상 겹치는 구간(cap 상위)에서 beta 효과가 없으니 이중 축소
    위험은 작지만, 채택 시 겹침 규칙을 명시한다(둘 다 걸리면 min 이 아니라 곱? → **min**: 축소만
    하는 두 규칙을 곱하면 과축소. 채택 시 min(0.6, 0.5)=0.5).
  · 표본은 7패턴 무조건부(method_x/r/s 와 같은 프레임) — 실거래 라우팅 복제가 아니다. 라우팅이
    거르는 셀까지 넣고 재므로 절대 수준은 낙관적이나 arm 비교는 상쇄된다.
  · 유니버스 생존 편향 — beta_slope 를 현재 살아있는 종목으로 과거에 계산한다.

실행: python method_b.py [--no-fetch] [--universe]
출력: method_b.json
"""
import importlib
import json
import math
import random
import statistics as st
import sys
from datetime import date

import detlib
import method_s as ms
import method_t as mt
import method_x as mx
import regime_axis as ra
import regime_switch as rs
import sizing as sz
import sizing_study as ss

ARMS = ["D", "B_skip", "B_size"]
SIZE_MULT = 0.5           # B_size: 하위 3분위 롱 축소 배율 (축소만)
BURN_IN = 250             # 인과 3분위 컷 최소 관측 일수
MIN_FILTERED_N = 30       # 기준 ① 판정 가능 최소 걸러진 표본
HOLDOUT_DAYS = 365
BOOT_N, SEED = 300, 13
BLOCK_DAYS = 30
MDD_TOLERANCE = 0.05
PATS = mt.PATS            # 7패턴 (engulfing/fvg ±, ih, marubozu, triple_bottom 1w)


# ── 인과 3분위 ──────────────────────────────────────────────────────────────
def causal_tercile_map(series, burn_in=BURN_IN):
    """
    date -> 'lo'/'mid'/'hi'. 날짜 d 의 컷은 **d 이전** 값들의 3분위(확장 창). burn_in 미만은 'mid'.
    O(n log n) 을 위해 정렬 리스트에 이분 삽입.
    """
    import bisect
    out, sorted_vals = {}, []
    for d in sorted(series):
        v = series[d]
        n = len(sorted_vals)
        if n >= burn_in:
            lo_c, hi_c = sorted_vals[n // 3], sorted_vals[2 * n // 3]
            out[d] = "lo" if v <= lo_c else ("hi" if v > hi_c else "mid")
        else:
            out[d] = "mid"
        bisect.insort(sorted_vals, v)
    return out


def arm_size(arm, direction, tercile):
    """arm 별 (진입 여부, 크기 배율). 롱·하위 3분위에서만 D 와 달라진다."""
    if direction != "long" or tercile != "lo":
        return True, 1.0
    if arm == "B_skip":
        return False, 0.0
    if arm == "B_size":
        return True, SIZE_MULT
    return True, 1.0


# ── 거래 수집 ───────────────────────────────────────────────────────────────
def collect(syms, regmap, terc):
    """
    반환: trades[arm] = [dict(pattern, direction, date, exit_date, ret, hold, reason, stop_pct,
                              vol, size_mult, tercile, taken)]
    D 의 거래마다 arm 별 (taken, size_mult) 를 붙인다. 신호 집합은 세 arm 이 완전히 같다.
    """
    trades = {a: [] for a in ARMS}
    for label, direction, detmod, oppmod, tf in PATS:
        mod = importlib.import_module(detmod)
        opp = importlib.import_module(oppmod) if oppmod else None
        n_lab = 0
        for sym in syms:
            try:
                rows = detlib.load_ohlcv(sym, tf)
            except (FileNotFoundError, RuntimeError):
                continue
            if len(rows) < 40:
                continue
            opp_set = set(opp.detect(rows)) if opp else set()
            lab = lambda j, rows=rows: regmap.get(rows[j]["date"])
            for si in mod.detect(rows):
                if si + 1 >= len(rows) or si < 30:
                    continue
                vol = sz.realized_vol(rows, si, tf=tf)
                if vol is None:
                    continue
                ret, hold, reason = ms.outcome(rows, si, direction, opp_set, lab)
                d = rows[si]["date"]
                t = terc.get(d, "mid")
                xd = rows[min(si + hold, len(rows) - 1)]["date"]
                for a in ARMS:
                    taken, mult = arm_size(a, direction, t)
                    trades[a].append(dict(pattern=label, direction=direction, date=d, exit_date=xd,
                                          ret=ret if taken else 0.0, hold=hold if taken else 0,
                                          reason=reason if taken else "skipped", stop_pct=ms.STOP,
                                          vol=vol, size_mult=mult, tercile=t, taken=taken, d_ret=ret))
                n_lab += 1
        print(f"  [collect] {label}: {n_lab}건", flush=True)
    return trades


def tuples(tr):
    return sorted((t["date"], t["exit_date"], t["ret"], t["hold"], t["reason"], t["stop_pct"], t["vol"], t["size_mult"])
                  for t in tr if t["taken"])


def perf(tr, span_days):
    taken = [t for t in tr if t["taken"]]
    if not taken:
        return None
    eq = mx.equity_curve(tuples(tr), span_days=span_days)
    rets = [t["ret"] for t in taken]
    return dict(n=len(taken), mean=st.mean(rets), median=st.median(rets),
                win=sum(1 for r in rets if r > 0) / len(rets),
                cagr=eq["cagr"], mdd=eq["mdd"], calmar=eq["calmar"], taken=eq["taken"], skipped=eq["skipped"])


def filtered_quality(d_trades, arm):
    """기준 ① — 스킵/축소 대상(롱·하위 3분위)의 D 수익 vs 나머지 롱 거래."""
    flt = [t["d_ret"] for t in d_trades if t["direction"] == "long" and t["tercile"] == "lo"]
    rest = [t["d_ret"] for t in d_trades if t["direction"] == "long" and t["tercile"] != "lo"]
    if len(flt) < MIN_FILTERED_N or len(rest) < MIN_FILTERED_N:
        return dict(n=len(flt), n_rest=len(rest), ok=False, reason="표본 부족")
    p = ra.boot_diff_p(rest, flt)      # rest > flt 인지 (단측)
    ok = st.mean(flt) < st.mean(rest) and st.mean(flt) < 0 and p < 0.05
    return dict(n=len(flt), n_rest=len(rest), flt_mean=st.mean(flt), rest_mean=st.mean(rest),
                flt_median=st.median(flt), rest_median=st.median(rest), boot_p=p, ok=ok)


def _dnum(ds_):
    return ss._dnum(ds_)


def paired_block_boot(arm_trades, rng, n_boot=BOOT_N, block=BLOCK_DAYS):
    """validate_routing.paired_block_boot 와 같은 설계 — 같은 시간 블록을 arm 마다 재표집. 8-튜플."""
    all_days = [_dnum(t["date"]) for tr in arm_trades.values() for t in tr if t["taken"]]
    out = {a: dict(calmar=[], cagr=[], mdd=[]) for a in arm_trades}
    if not all_days:
        return out
    d0, d1 = min(all_days), max(all_days)
    n_blocks = max(1, (d1 - d0) // block + 1)
    by_block = {}
    for a, tr in arm_trades.items():
        m = {}
        for t in tr:
            if t["taken"]:
                m.setdefault((_dnum(t["date"]) - d0) // block, []).append(t)
        by_block[a] = m
    for _ in range(n_boot):
        pick = [rng.randrange(n_blocks) for _ in range(n_blocks)]
        for a, m in by_block.items():
            tup = []
            for pos, b in enumerate(pick):
                shift = (pos - b) * block
                for t in m.get(b, []):
                    e, x = _dnum(t["date"]) + shift, _dnum(t["exit_date"]) + shift
                    tup.append((date.fromordinal(e).isoformat(), date.fromordinal(max(x, e)).isoformat(),
                                t["ret"], t["hold"], t["reason"], t["stop_pct"], t["vol"], t["size_mult"]))
            tup.sort()
            eq = mx.equity_curve(tup, span_days=n_blocks * block)
            out[a]["calmar"].append(min(eq["calmar"], 50.0) if eq else 0.0)
            out[a]["cagr"].append(eq["cagr"] if eq else 0.0)
            out[a]["mdd"].append(eq["mdd"] if eq else 0.0)
    return out


def verdict(arm, res, quality, boot_win):
    b, x = res["D"], res[arm]
    if not b["train"] or not x["train"]:
        return dict(pass_=False, reason="train 없음")
    c1 = bool(quality.get("ok"))
    c2 = x["train"]["cagr"] > b["train"]["cagr"]
    c3 = x["train"]["calmar"] > b["train"]["calmar"]
    h = x.get("halves", {})
    c4 = bool(h) and all(k in h for k in ("first", "second")) and all(h[k]["arm"] > h[k]["base"] for k in ("first", "second"))
    c5 = x["train"]["mdd"] >= b["train"]["mdd"] - MDD_TOLERANCE
    c6 = boot_win >= 0.60
    c7 = bool(b["holdout"]) and bool(x["holdout"]) and x["holdout"]["cagr"] > b["holdout"]["cagr"]
    return dict(pass_=all([c1, c2, c3, c4, c5, c6, c7]), c1_filtered_quality=c1, c2_cagr=c2, c3_calmar=c3,
                c4_halves=c4, c5_mdd=c5, c6_boot_win=c6, c7_holdout=c7, boot_win=boot_win)


def _f(v, w=8):
    return f"{'n/a':>{w}}" if v is None else f"{v*100:>+{w-1}.2f}%"


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    ms.UNIVERSE_MODE = "--universe" in argv
    syms = ms.symbols()
    print(f"[표본] {len(syms)}종목 ({'유니버스 80' if ms.UNIVERSE_MODE else '메이저'})")
    if "--no-fetch" not in argv:
        ms.ensure_data(mt.FETCH_DAYS, syms)
    regmap = rs.build_regime_map()
    rows_by = {}
    for s in syms:
        try:
            rows_by[s] = detlib.load_ohlcv(s, "1d")
        except Exception:
            pass
    btc = rows_by.get("BTC")
    if not btc:
        raise SystemExit("BTC 1d 없음")
    beta = ra.beta_slope_series(rows_by, btc)
    terc = causal_tercile_map(beta)
    dist = {k: sum(1 for v in terc.values() if v == k) for k in ("lo", "mid", "hi")}
    print(f"[beta_slope] {len(beta)}일 | 인과 3분위(burn-in {BURN_IN}) 분포 {dist}")

    print("[신호 수집]")
    trades = collect(syms, regmap, terc)
    all_dates = sorted(t["date"] for t in trades["D"])
    d_lo, d_hi = _dnum(all_dates[0]), _dnum(all_dates[-1])
    cutoff = date.fromordinal(d_hi - HOLDOUT_DAYS).isoformat()
    d_cut = _dnum(cutoff)
    span_train = max(1, d_cut - d_lo)
    mid = date.fromordinal(d_lo + span_train // 2).isoformat()
    print(f"[분할] train < {cutoff} <= holdout | train 창 {span_train}일 | 전후반 경계 {mid}")

    res = {}
    for a in ARMS:
        tr = trades[a]
        train = [t for t in tr if t["date"] < cutoff]; hold = [t for t in tr if t["date"] >= cutoff]
        first = [t for t in train if t["date"] < mid]; second = [t for t in train if t["date"] >= mid]
        res[a] = dict(train=perf(train, span_train), holdout=perf(hold, HOLDOUT_DAYS),
                      _first=perf(first, span_train // 2), _second=perf(second, span_train // 2))
    for a in ARMS[1:]:
        res[a]["halves"] = {k: dict(base=res["D"][f"_{k}"]["cagr"], arm=res[a][f"_{k}"]["cagr"])
                            for k in ("first", "second") if res["D"].get(f"_{k}") and res[a].get(f"_{k}")}

    d_train = [t for t in trades["D"] if t["date"] < cutoff]
    quality = filtered_quality(d_train, "B")
    print("\n[기준 ① — 걸러진 집합(롱·beta 하위 3분위)의 D 수익, train]")
    if quality.get("n") is not None and "flt_mean" in quality:
        print(f"  걸러진 n={quality['n']} mean={_f(quality['flt_mean'])} med={_f(quality['flt_median'])} "
              f"| 나머지 롱 n={quality['n_rest']} mean={_f(quality['rest_mean'])} med={_f(quality['rest_median'])} "
              f"| boot_p={quality['boot_p']:.3f} -> {'O' if quality['ok'] else 'X'}")
    else:
        print(f"  {quality}")

    print("\n[성과]")
    print(f"  {'arm':<8}{'분할':<9}{'n':>6}{'건당평균':>10}{'중앙':>9}{'승률':>7}{'CAGR':>10}{'MDD':>9}{'Calmar':>8}{'진입':>7}{'스킵':>7}")
    print("  " + "-" * 92)
    for a in ARMS:
        for sp in ("train", "holdout"):
            p = res[a][sp]
            if not p:
                print(f"  {a:<8}{sp:<9}     0"); continue
            print(f"  {a:<8}{sp:<9}{p['n']:>6}{_f(p['mean'], 10)}{_f(p['median'], 9)}{p['win']*100:>6.0f}%"
                  f"{_f(p['cagr'], 10)}{_f(p['mdd'], 9)}{p['calmar']:>8.2f}{p['taken']:>7}{p['skipped']:>7}")

    print("\n[짝지음 블록 부트스트랩 (train)]", flush=True)
    rng = random.Random(SEED)
    train_map = {a: [t for t in trades[a] if t["date"] < cutoff] for a in ARMS}
    boot = paired_block_boot(train_map, rng)
    wins = {}
    for a in ARMS[1:]:
        pair = list(zip(boot["D"]["calmar"], boot[a]["calmar"]))
        wins[a] = sum(1 for bb, xx in pair if xx > bb) / len(pair) if pair else 0.0
        print(f"  {a}: Calmar 중앙 D {st.median(boot['D']['calmar']):.2f} vs {a} {st.median(boot[a]['calmar']):.2f} "
              f"| {a} 우위 {wins[a]*100:.0f}%")

    print("\n[판정] 사전 등록 7기준 — 전부 통과해야 채택(자율 반영 대상)")
    verdicts = {}
    for a in ARMS[1:]:
        v = verdict(a, res, quality, wins[a]); verdicts[a] = v
        flags = " ".join(f"{k.split('_')[0]}{'O' if v[k] else 'X'}" for k in
                         ("c1_filtered_quality", "c2_cagr", "c3_calmar", "c4_halves", "c5_mdd", "c6_boot_win", "c7_holdout"))
        print(f"  {a:<8}{'채택' if v['pass_'] else '기각':<6} {flags}")

    # 패턴별 걸러진 비율·수익 (진단)
    print("\n[진단] 패턴별 롱 거래 중 beta 하위 3분위 비율과 D 수익 (train)")
    for label, direction, *_ in PATS:
        if direction != "long":
            continue
        sub = [t for t in d_train if t["pattern"] == label]
        lo = [t["d_ret"] for t in sub if t["tercile"] == "lo"]; rest = [t["d_ret"] for t in sub if t["tercile"] != "lo"]
        if sub:
            print(f"  {label:<16} n={len(sub):>5} 하위 {len(lo):>4}({len(lo)/len(sub)*100:>4.0f}%) "
                  f"mean {_f(st.mean(lo) if lo else None)} | 나머지 mean {_f(st.mean(rest) if rest else None)}")

    json.dump(dict(arms=ARMS, size_mult=SIZE_MULT, burn_in=BURN_IN, cutoff=cutoff, universe=ms.UNIVERSE_MODE,
                   tercile_dist=dist, quality=quality, results=res, boot_win=wins, verdicts=verdicts),
              open("method_b.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print("\n[저장] method_b.json")
    print("RESULT_JSON: " + json.dumps({a: v["pass_"] for a, v in verdicts.items()}))


if __name__ == "__main__":
    main()
