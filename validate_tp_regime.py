"""
validate_tp_regime.py — 작은 고정 익절 배리어 격자의 **레짐 분해** 사전 등록 (2026-09-09, 사용자 지적
"1%/8% 레짐이나 상승국면에서 테스트한거 맞아? 일반적인 전체기간으로 놓고만 테스트한거 아니지?" → 맞다,
전 기간 풀링뿐이었다. "전부 진행해봐").

── 무엇을 빠뜨렸나 ─────────────────────────────────────────────────────────
1d 판(tp_small)·1h 판(tp_1h) 모두 배리어 셀을 **레짐으로 나누지 않았다**. tp_small 은 레짐맵을
만들었으나 방식D 기준선 arm 에만 썼고, tp_1h 는 레짐 참조가 0건이다. 이 레포는 레짐을 나누면 같은
패턴이 13%p 까지 갈리는 것을 이미 확인했으면서(engulfing 롱 bull_btc +1.78% vs altseason −6.97%)
그걸 안 걸었다.

── 왜 결과가 뒤집힐 수 있나 (산술) ─────────────────────────────────────────
배리어 쌍의 기대값은 **보유 기간 동안 쌓인 드리프트**다 — 무드리프트에서 정확히 0 인 것은 그 특수해.
(정지시간 정리: E[손익] = μ·E[τ]). 1%/8% 의 평균 보유가 1h 에서 17봉이므로 수수료 0.2% 를 넘으려면
  필요 드리프트 ≈ 0.2% / 17h ≈ **0.28%/일**
레포에 기록된 bull_btc 국면 top30 무작위 롱은 20일 +5.24% ≈ **0.26%/일** — 문턱과 사실상 같다.
즉 경계선이고, 전 기간 풀링(−0.28%)은 bull 과 bear 를 평균 내 이걸 지웠을 수 있다.

**이 규칙은 패턴 엣지가 없어도 된다** — 드리프트만 있으면 된다. 앞선 두 판에서 '패턴 엣지 ≈ 0'
을 결론처럼 적었으나 사용자 규칙에 필요한 것은 기준 ①(건당>0)이고, 그건 상승 국면에서 드리프트
만으로 양수가 될 수 있다. 프레임을 잘못 잡았던 것이다.

── 동결 (실행 전 고정) ─────────────────────────────────────────────────────
· 격자·규칙·비용·스캔한도·패턴 6종은 tp_1h 와 동일(import 해서 쓴다 — 재정의하지 않는다).
· 레짐 = **진입 봉 날짜의 레짐 라벨**(regime_switch.build_regime_map, 닫힌 봉 인과 라벨). 이것은
  스케줄러가 진입 시점에 보는 것과 같은 지연 라벨이므로 **실행 가능한 조건**이다.
· 레짐 4: bull_btc / bull_altseason / bear / ALL (sideways 는 라벨러가 사실상 안 낸다).
· TF: **1h 주 판정**(해상도) + 1d 진단(커버리지 — 1h 는 365일뿐이라 bull_btc 일수가 적을 수 있다).
· **주 판정 8셀 = {T1S3, T1S8, T1S20, T1SX} × {bull_btc, bull_altseason}**, TF 1h. Holm m=8.
  bear·ALL·1d·나머지 격자는 진단. 사후 선택 금지.
· 무작위 베이스라인은 **레짐 매칭** — 같은 레짐으로 라벨된 봉에서만 뽑는다(패턴 vs 같은 국면 무작위).
  이것이 '드리프트 수확'과 '패턴 엣지'를 가른다: 패턴 건당>0 인데 엣지≈0 이면 드리프트 수확.
· 홀드아웃: g≠ALL 은 frame_v3.holdout_dates(그 레짐으로 라벨된 날 중 가장 최근 N일, 비연속),
  ALL 은 달력 마지막 N일. N = 1h 90 / 1d 365.
· 커버리지: train n < COV_MIN(1h 100 / 1d 20) 또는 holdout n < 10 → 성능 기준을 통과했더라도
  **INCONCLUSIVE**(기각 아님). 판정 우선순위는 frame_v3 와 같다 — 성능 실패 → REJECTED,
  성능 통과·커버리지 실패 → INCONCLUSIVE, 전부 → PASS.

── 판정 (tp_1h 와 동일 7개, 베이스라인만 레짐 매칭) ────────────────────────
  ① train 건당>0 ② 승률>손익분기 ③ 리프트>0 ④ 패턴 엣지>0 & Holm p<.05 (레짐 매칭 무작위 대비)
  ⑤ 마찰 0.4%>0 ⑥ 전후반 양수 ⑦ holdout 건당>0. 무손절은 ②③ N/A(tp_1h 규정 그대로).
**드리프트 수확 판정(추가, 판정 아님·서술)**: ①⑤⑦ 통과인데 ④ 실패면 'DRIFT_HARVEST' 로 표기 —
'이 국면에서 롱은 번다'는 뜻이지 패턴이 뭘 하는 건 아니다. 그래도 사용자 규칙엔 그것으로 충분할 수
있으므로 숨기지 않고 따로 센다.
**DEPLOY_ON_PASS=False** — 통과해도 실거래 반영 없음(관찰 기간, 청산 변경은 실주문 경로).

── 실행 가능성 유보 (결과 전 기록) ─────────────────────────────────────────
레짐 라벨의 20일 지평 방향 예측력은 ≈0 으로 측정돼 있다(적중 49%, 2026-09-04). 다만 배리어 보유는
17시간이지 20일이 아니다 — 지연 라벨이 17시간 안의 드리프트를 담는지는 별개 질문이고 이 시험이
그것을 직접 잰다(진입 시점 라벨 조건부 건당). 통과해도 '국면을 미리 안다'가 아니라 '라벨이 이렇게
찍힌 동안 이 규칙이 번다'로 읽는다.

── 사전 확률 (결과 보기 전 기록, 크기 없음) ────────────────────────────────
· bull_btc: 경계. 산술상 ±. 통과한다면 ④(엣지)는 여전히 ≈0 일 것 → DRIFT_HARVEST 가능성.
· bull_altseason: 음수 예상 — 라벨이 후행이라 국면 끝자락에 몰리고, 그 국면 무작위 롱이 20봉
  −3.04% 였다(2026-09-04).
· bear: 음수 예상.
· 1h bull_btc 는 커버리지 미달(INCONCLUSIVE) 가능성이 높다 — 최근 365일이 bear 지배.
  1d 가 그 빈칸을 메운다(단 동률 오염이 남는다 — T1S8 13.3%, T1S20 1.6%. 낙관 상한을 병기).

실행: python validate_tp_regime.py [--no-fetch] [--tf 1h,1d]
출력 _tp_regime.json + RESULT_JSON. 실거래·DB 무관.
"""
import json
import random
import statistics as st
import sys

import frame_v3 as f3
import regime_switch as rs
import validate_regime_split_all as va
import validate_tp_1h as T

# ── 동결 ─────────────────────────────────────────────────────────────────────
TFS = ("1h", "1d")
PRIMARY_TF = "1h"
REGIMES = ("bull_btc", "bull_altseason", "bear", "ALL")
PRIMARY_REGIMES = ("bull_btc", "bull_altseason")
PRIMARY_CELLS = T.PRIMARY_ARMS                      # T1S3 / T1S8 / T1S20 / T1SX
PRIMARY = [(m, g) for m in PRIMARY_CELLS for g in PRIMARY_REGIMES]   # 8, Holm m=8
COV_MIN = {"1h": 100, "1d": 20}
HOLDOUT_MIN_N = 10
RAND_N = 6000
DEPLOY_ON_PASS = False


def key(m, g):
    return f"{m}|{g}"


# ── 수집 (tp_1h 의 교차표를 그대로 쓰고 레짐으로 버킷만 나눈다) ────────────
def collect(rows_by, regmap, direction, max_scan, detect_fn):
    """{cell: {regime: [(date, ret, hold, reason, tie)]}} + 낙관 판(주 판정 셀만) + P2 입력."""
    sigs = []
    for rows in rows_by.values():
        if len(rows) < 40:
            continue
        for si in detect_fn(rows):
            if si + 1 < len(rows):
                sigs.append((rows, si))
    n_all = len(sigs)
    if n_all > T.SIG_CAP:
        sigs = random.Random(T.SIG_SEED).sample(sigs, T.SIG_CAP)
    buckets = {T.cell_name(tp, sl): {g: [] for g in REGIMES} for tp, sl in T.CELLS}
    opt = {m: {g: [] for g in REGIMES} for m in PRIMARY_CELLS}
    for rows, si in sigs:
        cross = T.crossings(rows, si, direction, max_scan)
        if cross is None:
            continue
        d0 = rows[si]["date"]
        g = regmap.get(d0)
        for tp, sl in T.CELLS:
            m = T.cell_name(tp, sl)
            o = T._resolve(cross, rows, si, direction, tp, sl)
            rec = (d0, o[0], o[1], o[2], o[3])
            buckets[m]["ALL"].append(rec)
            if g in buckets[m]:
                buckets[m][g].append(rec)
            if m in opt:
                oo = T._resolve(cross, rows, si, direction, tp, sl, optimistic=True)
                orec = (d0, oo[0], oo[1], oo[2], oo[3])
                opt[m]["ALL"].append(orec)
                if g in opt[m]:
                    opt[m][g].append(orec)
    return buckets, opt, n_all, len(sigs)


def random_baseline(rows_by, regmap, direction, max_scan):
    """레짐 매칭 무작위 진입 — {cell: {regime: summarize}}. 레짐별로 따로 뽑는다."""
    rng = random.Random(T.RAND_SEED)
    pools = {g: [] for g in REGIMES}
    for rows in rows_by.values():
        for i in range(30, len(rows) - 2):
            g = regmap.get(rows[i]["date"])
            pools["ALL"].append((rows, i))
            if g in pools:
                pools[g].append((rows, i))
    out = {T.cell_name(tp, sl): {} for tp, sl in T.CELLS}
    for g, pool in pools.items():
        if not pool:
            continue
        pick = pool if len(pool) <= RAND_N else rng.sample(pool, RAND_N)
        b = {T.cell_name(tp, sl): [] for tp, sl in T.CELLS}
        for rows, i in pick:
            cross = T.crossings(rows, i, direction, max_scan)
            if cross is None:
                continue
            for tp, sl in T.CELLS:
                o = T._resolve(cross, rows, i, direction, tp, sl)
                b[T.cell_name(tp, sl)].append((rows[i]["date"], o[0], o[1], o[2], o[3]))
        for m, v in b.items():
            out[m][g] = T.summarize(v)
    return out


# ── 판정 ────────────────────────────────────────────────────────────────────
def judge(m, g, recs, rand_win, hold_set, cov_min, holm_p):
    tp, sl = T.CELL_OF[m]
    train = [r for r in recs if r[0] not in hold_set]
    hold = [r for r in recs if r[0] in hold_set]
    tr, ho = T.summarize(train), T.summarize(hold)
    if not tr:
        return dict(verdict="INCONCLUSIVE", reason="train 0", train=None, holdout=None)
    hv = T.halves(train)
    v = T.verdict(m, tr, ho, rand_win, hv, holm_p)
    perf_ok = v["pass_"]
    cov = tr["n"] >= cov_min and bool(ho) and ho["n"] >= HOLDOUT_MIN_N
    # 드리프트 수확: 수익 기준(①⑤⑦)은 넘는데 엣지(④)만 못 넘는 경우 — 판정 아님, 서술
    drift = v["c1_mean"] and v["c5_friction"] and v["c7_holdout"] and not v["c4_edge"]
    if perf_ok and cov:
        verdict = "PASS"
    elif perf_ok:
        verdict = "INCONCLUSIVE"
    else:
        # 성능 실패인데 원인이 홀드아웃 부재뿐이면(⑦ 만 X, holdout n<10) 커버리지 문제
        only_holdout = (not v["c7_holdout"]) and all(v[k] for k in ("c1_mean", "c2_breakeven", "c3_lift", "c4_edge", "c5_friction", "c6_halves")) \
            and (not ho or ho["n"] < HOLDOUT_MIN_N)
        verdict = "INCONCLUSIVE" if only_holdout else "REJECTED"
    return dict(verdict=verdict, crit=v, train=tr, holdout=ho, halves=hv, coverage=cov,
                drift_harvest=bool(drift and verdict != "PASS"))


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    tfs = TFS
    for i, a in enumerate(argv):
        if a == "--tf" and i + 1 < len(argv):
            tfs = tuple(x.strip() for x in argv[i + 1].split(","))
    syms = va._syms()
    print(f"[표본] {len(syms)}종목 · 패턴 {len(T.PATS)}종 · TF {tfs} (주 판정 {PRIMARY_TF})")
    print(f"[주 판정] {[key(m, g) for m, g in PRIMARY]} (Holm m={len(PRIMARY)})")
    print("[산술] 필요 드리프트 ≈ 수수료/평균보유 — 1%/8% 1h 보유 17봉이면 약 0.28%/일. "
          "bull_btc 무작위 롱 실측 ≈0.26%/일(2026-09-04) → 경계")
    print(f"[반영] DEPLOY_ON_PASS={DEPLOY_ON_PASS} — 통과해도 실거래 변경 없음\n")
    if "--no-fetch" not in argv:
        va.fetch(syms, list(tfs))
    rows_1d = va.load_tf(syms, "1d")
    regmap = rs.build_regime_map(rows_by=rows_1d)
    days = {g: sum(1 for d in regmap.values() if d == g) for g in REGIMES if g != "ALL"}
    print(f"[레짐] {min(regmap)}~{max(regmap)} 일수 {days}")

    out, verdicts, raw_p = {}, {}, {}
    for tf in tfs:
        rows_by = rows_1d if tf == "1d" else va.load_tf(syms, tf)
        if not rows_by:
            print(f"[{tf}] 데이터 없음"); continue
        ms = T.MAX_SCAN_BY_TF[tf]
        first = min(r["date"] for rows in rows_by.values() for r in rows)
        last = max(r["date"] for rows in rows_by.values() for r in rows)
        win_days = {g: sum(1 for d, lab in regmap.items() if first <= d <= last and lab == g)
                    for g in REGIMES if g != "ALL"}
        print(f"\n[{tf}] {len(rows_by)}종목 {first}~{last} | 창 안 레짐 일수 {win_days}", flush=True)
        sub = {d: lab for d, lab in regmap.items() if first <= d <= last}
        hold_sets = {g: f3.holdout_dates(sub, g, days=T.HOLDOUT_BY_TF[tf]) for g in REGIMES}

        rnd = {}
        for d in ("long", "short"):
            rnd[d] = random_baseline(rows_by, regmap, d, ms)
            print(f"  [무작위·레짐매칭] {tf} {d} 준비", flush=True)

        pooled = {T.cell_name(tp, sl): {g: [] for g in REGIMES} for tp, sl in T.CELLS}
        rw = {T.cell_name(tp, sl): {g: [0.0, 0] for g in REGIMES} for tp, sl in T.CELLS}
        opt_all = {m: {g: [] for g in REGIMES} for m in PRIMARY_CELLS}
        import importlib
        for lb, direction, detmod in T.PATS:
            det = importlib.import_module(detmod).detect
            b, opt, n_all, n_used = collect(rows_by, regmap, direction, ms, det)
            for m in pooled:
                for g in REGIMES:
                    v = b[m][g]
                    if not v:
                        continue
                    pooled[m][g] += v
                    rb = rnd[direction].get(m, {}).get(g)
                    if rb:
                        rw[m][g][0] += len(v) * rb["winrate"]; rw[m][g][1] += len(v)
            for m in PRIMARY_CELLS:
                for g in REGIMES:
                    opt_all[m][g] += opt[m][g]
            print(f"  [{lb}] 신호 {n_all:,}" + (f" → {n_used:,}" if n_used < n_all else ""), flush=True)

        res = {}
        for m in pooled:
            for g in REGIMES:
                recs = pooled[m][g]
                rwin = rw[m][g][0] / rw[m][g][1] if rw[m][g][1] else None
                res[key(m, g)] = dict(recs=recs, rand_win=rwin,
                                      rand_mean=(sum(rnd[d][m][g]["mean"] * rnd[d][m][g]["n"]
                                                     for d in rnd if rnd[d].get(m, {}).get(g))
                                                 / max(1, sum(rnd[d][m][g]["n"] for d in rnd if rnd[d].get(m, {}).get(g))))
                                      if any(rnd[d].get(m, {}).get(g) for d in rnd) else None)
        out[tf] = dict(first=first, last=last, win_days=win_days, res=res, opt=opt_all,
                       hold_sets={g: len(s) for g, s in hold_sets.items()})

        # ── 표: 레짐 × 주 판정 셀 (+ 전 격자 요약) ──────────────────────────
        print("\n" + "=" * 150)
        print(f"[{tf}] 레짐별 배리어 — 무작위는 **같은 레짐** 진입. 엣지 = 패턴 승률 − 같은 레짐 무작위 승률")
        print("=" * 150)
        print(f"  {'셀':<7}{'레짐':<15}{'n':>7}{'건당':>8}{'마찰0.4%':>10}{'승률':>8}{'랜덤워크':>9}"
              f"{'리프트':>8}{'무작위승률':>11}{'엣지':>8}{'무작위건당':>11}{'보유':>7}{'holdout n':>10}{'holdout':>9}")
        print("  " + "-" * 148)
        for tp, sl in T.CELLS:
            m = T.cell_name(tp, sl)
            if m not in PRIMARY_CELLS and tf == PRIMARY_TF:
                pass
            for g in REGIMES:
                r = res[key(m, g)]
                s = T.summarize(r["recs"])
                if not s:
                    continue
                hs = hold_sets[g]
                ho = T.summarize([x for x in r["recs"] if x[0] in hs])
                rwv = T.rw_hit(tp, sl)
                star = "*" if (m, g) in PRIMARY and tf == PRIMARY_TF else " "
                if m not in PRIMARY_CELLS:
                    continue      # 표는 주 판정 셀만 (전 격자는 json 에)
                print(f"  {m:<6}{star}{g:<15}{s['n']:>7}{s['mean']*100:>+7.2f}%{s['mean_stressed']*100:>+9.2f}%"
                      f"{s['winrate']:>8.1%}{T._fmt_pct(rwv, 9)}"
                      + (f"{'-':>8}" if rwv is None else f"{(s['winrate']-rwv)*100:>+7.1f}p")
                      + T._fmt_pct(r['rand_win'], 11)
                      + (f"{'-':>8}" if r['rand_win'] is None else f"{(s['winrate']-r['rand_win'])*100:>+7.1f}p")
                      + (f"{'-':>11}" if r['rand_mean'] is None else f"{r['rand_mean']*100:>+10.2f}%")
                      + f"{s['avghold']:>7.1f}{(ho['n'] if ho else 0):>10}"
                      + (f"{ho['mean']*100:>+8.2f}%" if ho else f"{'-':>9}"))

    # ── 판정 ────────────────────────────────────────────────────────────────
    print("\n" + "=" * 150)
    print(f"사전 등록 판정 — TF {PRIMARY_TF} · {len(PRIMARY)}셀 · Holm m={len(PRIMARY)} · 무작위는 레짐 매칭")
    print("=" * 150)
    P = out.get(PRIMARY_TF)
    if P:
        for m, g in PRIMARY:
            r = P["res"][key(m, g)]
            hs = set(d for d, lab in regmap.items() if P["first"] <= d <= P["last"])
            hs = f3.holdout_dates({d: regmap[d] for d in hs}, g, days=T.HOLDOUT_BY_TF[PRIMARY_TF])
            train = [x for x in r["recs"] if x[0] not in hs]
            wins = [1 if x[1] > 0 else 0 for x in train]
            raw_p[key(m, g)] = T.boot_edge_p(wins, r["rand_win"])
        hp = T.holm(raw_p)
        for m, g in PRIMARY:
            k = key(m, g)
            r = P["res"][k]
            sub = {d: lab for d, lab in regmap.items() if P["first"] <= d <= P["last"]}
            hs = f3.holdout_dates(sub, g, days=T.HOLDOUT_BY_TF[PRIMARY_TF])
            j = judge(m, g, r["recs"], r["rand_win"], hs, COV_MIN[PRIMARY_TF], hp.get(k, 1.0))
            verdicts[k] = dict(verdict=j["verdict"], drift_harvest=j.get("drift_harvest", False),
                               n=(j["train"]["n"] if j["train"] else 0),
                               holdout_n=(j["holdout"]["n"] if j.get("holdout") else 0))
            tp, sl = T.CELL_OF[m]
            tr, ho = j.get("train"), j.get("holdout")
            print(f"\n  [{k}] 익절 {tp:.0%} / 손절 {'무손절' if sl is None else f'{sl:.0%}'}"
                  + (f"   train n={tr['n']:,} holdout n={ho['n'] if ho else 0}" if tr else "   train 0"))
            if not tr:
                print(f"      => INCONCLUSIVE (표본 없음)"); continue
            v = j["crit"]
            for nm, kk in (("①건당>0", "c1_mean"), ("②승률>손익분기", "c2_breakeven"), ("③리프트>0", "c3_lift"),
                           ("④패턴엣지>0 & Holm p<.05 (레짐매칭)", "c4_edge"), ("⑤마찰0.4%>0", "c5_friction"),
                           ("⑥전후반양수", "c6_halves"), ("⑦holdout건당>0", "c7_holdout")):
                na = v["na_barrier_ref"] and kk in ("c2_breakeven", "c3_lift")
                print(f"      {'-' if na else ('O' if v[kk] else 'X')} {nm}")
            rwv = T.rw_hit(tp, sl)
            print(f"      승률 {tr['winrate']:.2%}" + (f" | 랜덤워크 {rwv:.2%} | 손익분기 {T.breakeven_win(tp, sl):.2%}" if rwv else "")
                  + f" | 같은 레짐 무작위 {T._fmt_pct(r['rand_win'], 6, 2).strip()} → 엣지 "
                  f"{((tr['winrate']-r['rand_win'])*100 if r['rand_win'] is not None else 0):+.2f}p "
                  f"(boot_p {raw_p.get(k, 1.0):.3f} → Holm {hp.get(k, 1.0):.3f})")
            print(f"      건당 {tr['mean']*100:+.2f}% / 마찰0.4% {tr['mean_stressed']*100:+.2f}% "
                  f"| 같은 레짐 무작위 건당 {(r['rand_mean'] or 0)*100:+.2f}%"
                  + (f" | holdout n={ho['n']} {ho['mean']*100:+.2f}%" if ho else " | holdout 없음"))
            print(f"      동률 {tr['tie_rate']:.1%} · 보유 {tr['avghold']:.1f}봉 · 최대손실 {tr['maxloss']*100:+.1f}% "
                  f"· 커버리지 {'O' if j['coverage'] else 'X'}(train≥{COV_MIN[PRIMARY_TF]}, holdout≥{HOLDOUT_MIN_N})")
            ob = T.summarize([x for x in P["opt"][m][g] if x[0] not in hs])
            if ob and tr["tie_rate"] > 0:
                print(f"      [진단 상한] 동률→익절이면 승률 {ob['winrate']:.2%} 건당 {ob['mean']*100:+.2f}%")
            tag = j["verdict"] + ("  ← DRIFT_HARVEST(수익 기준 통과·엣지 없음: 이 국면 롱이 번다는 뜻)" if j.get("drift_harvest") else "")
            print(f"      => {tag}")

    # 1d 진단: 같은 8셀을 1d 에서 (커버리지 대비, 낙관 상한 병기)
    if "1d" in out and PRIMARY_TF != "1d":
        D = out["1d"]
        print("\n  [1d 진단 — 커버리지는 넓고 동률 오염은 남는다. 보수/낙관 둘 다]")
        sub = {d: lab for d, lab in regmap.items() if D["first"] <= d <= D["last"]}
        for m, g in PRIMARY:
            r = D["res"][key(m, g)]
            hs = f3.holdout_dates(sub, g, days=T.HOLDOUT_BY_TF["1d"])
            j = judge(m, g, r["recs"], r["rand_win"], hs, COV_MIN["1d"], 1.0)
            tr, ho = j.get("train"), j.get("holdout")
            if not tr:
                print(f"      {key(m, g):<22} train 0"); continue
            ob = T.summarize([x for x in D["opt"][m][g] if x[0] not in hs])
            print(f"      {key(m, g):<22} n={tr['n']:>5} 건당 {tr['mean']*100:+.2f}%(낙관 {ob['mean']*100:+.2f}%) "
                  f"승률 {tr['winrate']:.1%} 무작위 {T._fmt_pct(r['rand_win'], 6).strip()} "
                  f"엣지 {((tr['winrate']-r['rand_win'])*100 if r['rand_win'] is not None else 0):+.1f}p "
                  f"동률 {tr['tie_rate']:.1%} holdout n={ho['n'] if ho else 0} "
                  + (f"{ho['mean']*100:+.2f}%" if ho else "-") + f"  → {j['verdict']}"
                  + (" DRIFT_HARVEST" if j.get("drift_harvest") else ""))

    # 저장
    slim = {tf: dict(first=o["first"], last=o["last"], win_days=o["win_days"], hold_sets=o["hold_sets"],
                     cells={k: dict(summary=T.summarize(v["recs"]), rand_win=v["rand_win"], rand_mean=v["rand_mean"])
                            for k, v in o["res"].items()})
            for tf, o in out.items()}
    json.dump(dict(config=dict(tfs=list(tfs), primary_tf=PRIMARY_TF, primary=[key(m, g) for m, g in PRIMARY],
                               regimes=list(REGIMES), cov_min=COV_MIN, holdout=T.HOLDOUT_BY_TF,
                               deploy_on_pass=DEPLOY_ON_PASS),
                   regime_days=days, by_tf=slim, verdicts=verdicts, boot_p=raw_p),
              open("_tp_regime.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print("\n[저장] _tp_regime.json")
    print("RESULT_JSON: " + json.dumps(dict(tf=PRIMARY_TF, deployed=False, verdicts=verdicts),
                                       separators=(",", ":"), ensure_ascii=False))


if __name__ == "__main__":
    main()
