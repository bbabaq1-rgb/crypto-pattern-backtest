"""
validate_xsec_momentum.py — 횡단면 모멘텀 (2026-09-04 사전 등록, 사용자 지시 1차 묶음 #2).

배경. 횡단면 모멘텀은 학술 증거가 가장 강한 축의 하나다(Jegadeesh & Titman 1993 이후 재현
다수, 크립토는 Liu·Tsyvinski·Wu 2022). 레포에는 상대강도(RS) 모듈이 있었으나 **패턴 진입의
필터로** 시험돼 기각됐고(2026-07-08, 레짐 교란으로 독립 엣지 소멸) 지금은 표시 전용이다.
'필터로 쓸모없다'와 '단독 진입 규칙으로 엣지가 있다'는 다른 물음이므로 여기서 후자를 잰다.

규칙 (사전 등록, 최적화 금지)
  · 매주(7일) 리밸런스. 각 리밸런스 봉 t 에서 유니버스를 **최근 L일 수익률**로 순위,
    상위 TOP_N 종목을 롱 신호로 낸다.
  · **skip-1**: 수익률은 t-1 종가까지로 계산한다(t-L-1 -> t-1). 단기 반전 오염을 피하는 표준 처리.
  · L 후보 5개 사전 등록: 7 / 14 / 28 / 56 / 84 일. (Liu & Tsyvinski: 주 단위가 월 단위보다 강함)
  · 숏은 시험하지 않는다 — 숏 라우팅은 별도 게이트이고 2026-09-04 숏 연구에서 문제가 확인됐다.

프레임 (두 판 병기, 사전 등록)
  · **동결 게이트(주 판정)**: detlib.outcome ±10%/20봉. 레포 전 패턴과 비교 가능한 유일한 잣대.
    게이트 n>=20, mean>0, median>0, boot_p<0.05, OOS 4분위 양구간>=2.
    boot_p 베이스라인은 **같은 레짐·같은 날짜 풀의 무작위 진입**(validate_regime_split 과 동일 원리)
    — '상승장이라 오른 것'을 엣지로 오인하지 않기 위해.
  · **추세 진단(판정 아님)**: 60봉 선행수익(배리어 없음). 추세추종은 오른쪽 꼬리로 버는 구조라
    ±10%/20봉 대칭 배리어가 엣지를 잘라낼 수 있다. 동결 게이트만 기각이고 진단은 양수면
    '프레임 탓 기각'으로 분류해 청산 규칙 과제로 넘긴다. 이 분류 규칙도 실행 전에 정했다.
  · **포트폴리오 진단(판정 아님)**: 주간 리밸런스 동일가중 top-N 자산곡선 vs 유니버스 동일가중
    보유. 신호 단위가 아니라 운용 단위에서 작동하는지 본다.

다중검정 사전 규칙: L 5개를 본다. PASSED 는 위 동결 게이트. **배포 후보(STRICT)** 는 추가로
  (a) boot_p < 0.01 (b) 인접 L 중 최소 하나도 PASSED — 파라미터 칼끝에 선 셀을 배제한다.
실거래 코드 무변경. 출력 _xsec_momentum.json + RESULT_JSON.
실행: python validate_xsec_momentum.py [--no-fetch] [--majors] [--min-bars N]
  --min-bars 는 이력이 긴 종목만 남겨 관측 창을 넓힌다. 유니버스 80 은 최근 상장이 많아
  기본 실행이 2024~2026(2.4년)만 덮는다 — 1차 실행에서 확인된 한계이고, 긴 이력 판을 병기한다.
"""
import json
import gate as gt   # 이 모듈의 로컬 함수 gate() 와 이름 충돌 방지
import random
import statistics as st
import sys
from math import erf, sqrt

import detlib
import method_s as ms
import regime_switch as rs

LOOKBACKS = [7, 14, 28, 56, 84]
TOP_N = 10
REBAL = 7
SKIP = 1
LABEL_W = detlib.LABEL_WINDOW          # 20
TREND_H = 60                           # 추세 진단 지평(봉)
SEED, BOOT_N = 42, 1000
STRICT_BOOT_P = 0.01
REGIMES = ["bull_btc", "bull_altseason", "bear", "sideways"]


def _pval(t, df):
    z = abs(t) / sqrt(1 + t * t / df)
    return 2 * (1 - 0.5 * (1 + erf(z / sqrt(2))))


MIN_BARS_DEFAULT = LABEL_W + 120


def load_all(syms, min_bars=MIN_BARS_DEFAULT):
    """
    min_bars 로 이력이 긴 종목만 남길 수 있다. 유니버스 80 은 최근 상장이 많아 대부분 900봉
    이라, 리밸런스마다 '20종목 이상이 lb+1 이력을 가진 날짜'가 2024 이후에만 성립한다
    (1차 실행이 실제로 2024~2026 2.4년만 덮었다). --min-bars 로 긴 이력 부분집합을 돌려
    관측 창을 넓힌 판을 함께 본다.
    """
    out = {}
    for s in syms:
        try:
            r = detlib.load_ohlcv(s, "1d")
            if len(r) >= min_bars:
                out[s] = r
        except (FileNotFoundError, RuntimeError):
            pass
    return out


def date_index(rows_by):
    """날짜 -> {sym: idx}. 종목마다 상장일이 달라 날짜 축으로 정렬한다."""
    idx = {}
    for s, rows in rows_by.items():
        for i, r in enumerate(rows):
            idx.setdefault(r["date"], {})[s] = i
    return idx


def signals(rows_by, didx, lb):
    """
    주간 리밸런스마다 최근 lb 일 수익률(skip-1) 상위 TOP_N. [(date, sym, idx, rank)].
    수익률은 t-1 종가 기준이므로 t 봉 종가 진입에 룩어헤드가 없다.
    """
    dates = sorted(didx)
    out = []
    for k in range(0, len(dates), REBAL):
        d = dates[k]
        scored = []
        for s, i in didx[d].items():
            rows = rows_by[s]
            j = i - SKIP                      # 기준 봉 = t-1
            j0 = j - lb
            if j0 < 0 or i + 1 >= len(rows):
                continue
            p0, p1 = rows[j0]["c"], rows[j]["c"]
            if p0 <= 0:
                continue
            scored.append((p1 / p0 - 1, s, i))
        if len(scored) < TOP_N * 2:           # 후보가 얕으면 순위가 무의미
            continue
        scored.sort(reverse=True)
        for rank, (_, s, i) in enumerate(scored[:TOP_N]):
            out.append((d, s, i, rank))
    return out


def fwd(rows, i, h):
    j = min(i + h, len(rows) - 1)
    if j <= i or rows[i]["c"] <= 0:
        return None
    return rows[j]["c"] / rows[i]["c"] - 1 - detlib.FEE


def gate(label, sigs, pool, regmap, verbose=True):
    """sigs: [(date, ret)]. pool: {regime: [(rows, i)]} 같은 레짐 무작위 진입 후보."""
    rets = [r for _, r in sigs]
    n = len(rets)
    mean = st.mean(rets) if rets else 0.0
    med = st.median(rets) if rets else 0.0
    t = p = 0.0
    if n >= 2 and st.stdev(rets) > 0:
        t = mean / (st.stdev(rets) / sqrt(n)); p = _pval(t, n - 1)
    # 베이스라인: 신호의 레짐 구성을 그대로 따라가는 무작위 진입
    boot_p, base_mean = 1.0, None
    regs = [regmap.get(d) for d, _ in sigs]
    usable = [g for g in regs if g and pool.get(g)]
    if usable and n:
        rng = random.Random(SEED)
        k = max(10, min(30, n))
        ge, means = 0, []
        for _ in range(BOOT_N):
            vals = []
            for _ in range(k):
                g = usable[rng.randrange(len(usable))]
                rows, i = pool[g][rng.randrange(len(pool[g]))]
                vals.append(detlib.outcome(rows, i, "long")[1])
            bm = st.mean(vals); means.append(bm); ge += bm >= mean
        boot_p = ge / BOOT_N; base_mean = st.mean(means)
    oos = []
    if n >= 20:
        ds = sorted(d for d, _ in sigs)
        cuts = [ds[len(ds) * i // 4] for i in range(1, 4)]
        for q in range(4):
            lo = cuts[q - 1] if q else "0000"; hi = cuts[q] if q < 3 else "9999"
            qr = [r for d, r in sigs if lo <= d < hi]
            qm = st.mean(qr) if qr else 0.0
            oos.append(dict(q=q + 1, n=len(qr), mean=qm, ok=len(qr) >= 5 and qm > 0))
    oos_pos = sum(1 for o in oos if o["ok"])
    ok = n >= 20 and mean > 0 and gt.dist_ok(rets) and boot_p < 0.05 and oos_pos >= 2
    fails = []
    if n < 20: fails.append("n<20")
    if mean <= 0: fails.append("mean<=0")
    if not gt.dist_ok(rets): fails.append(gt.dist_reason(rets))
    if boot_p >= 0.05: fails.append(f"boot_p={boot_p:.3f}")
    if n >= 20 and oos_pos < 2: fails.append(f"OOS {oos_pos}/4")
    by_year = {}
    for d, r in sigs:
        by_year.setdefault(d[:4], []).append(r)
    years = {y: dict(n=len(v), mean=st.mean(v)) for y, v in sorted(by_year.items())}
    rec = dict(n=n, mean=mean, median=med, t=t, p=p, boot_p=boot_p, oos_pos=oos_pos,
               base_mean=base_mean, edge=(mean - base_mean) if base_mean is not None else None,
               by_year=years, verdict="PASSED" if ok else "REJECTED", reason=", ".join(fails))
    if verbose:
        bm = f"{base_mean*100:+6.2f}%" if base_mean is not None else "   n/a"
        ed = f"{rec['edge']*100:+6.2f}%p" if rec["edge"] is not None else "     n/a"
        print(f"  {label:<22} n={n:>5} mean={mean*100:+6.2f}% med={med*100:+6.2f}% "
              f"| 레짐평균 {bm} 엣지 {ed} | boot_p={boot_p:.3f} OOS={oos_pos}/4 -> {rec['verdict']} {rec['reason']}")
    return rec


def portfolio(rows_by, didx, sig, h=REBAL):
    """주간 동일가중 top-N 보유 vs 유니버스 동일가중. 누적 수익(복리)."""
    by_date = {}
    for d, s, i, _ in sig:
        by_date.setdefault(d, []).append((s, i))
    eq_top = eq_uni = 1.0
    for d in sorted(by_date):
        picks = by_date[d]
        rt = [x for x in (fwd(rows_by[s], i, h) for s, i in picks) if x is not None]
        ru = [x for x in (fwd(rows_by[s], i, h) for s, i in didx[d].items()) if x is not None]
        if rt:
            eq_top *= (1 + st.mean(rt))
        if ru:
            eq_uni *= (1 + st.mean(ru))
    return dict(top=eq_top - 1, universe=eq_uni - 1, weeks=len(by_date))


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    ms.UNIVERSE_MODE = "--majors" not in argv
    syms = ms.symbols()
    print(f"[표본] {len(syms)}종목 ({'유니버스 80' if ms.UNIVERSE_MODE else '메이저'})")
    if "--no-fetch" not in argv:
        ms.ensure_data(ms.FETCH_DAYS, syms)
    min_bars = MIN_BARS_DEFAULT
    if "--min-bars" in argv:
        min_bars = int(argv[argv.index("--min-bars") + 1])
    rows_by = load_all(syms, min_bars)
    didx = date_index(rows_by)
    regmap = rs.build_regime_map()
    pool = {g: [(rows_by[s], i) for s in rows_by
                for i in range(len(rows_by[s]) - LABEL_W - 1)
                if regmap.get(rows_by[s][i]["date"]) == g] for g in REGIMES}
    ad = sorted(didx)
    print(f"[data] 종목 {len(rows_by)} (min_bars={min_bars}) | 날짜 {len(didx)} "
          f"({ad[0]}~{ad[-1]}) | 레짐 {len(regmap)}일 | "
          f"풀 " + " ".join(f"{g}:{len(pool[g])}" for g in REGIMES))
    print(f"[규칙] 리밸런스 {REBAL}일 · 상위 {TOP_N} · skip-{SKIP} · L={LOOKBACKS}")
    print("=" * 126)
    print("횡단면 모멘텀 — 동결 게이트(주 판정) + 추세 60봉 진단 + 포트폴리오 진단")
    print("=" * 126)
    results = {}
    for lb in LOOKBACKS:
        sig = signals(rows_by, didx, lb)
        if not sig:
            print(f"\n[L={lb}] 신호 없음"); continue
        froz, trend = [], []
        for d, s, i, _ in sig:
            rows = rows_by[s]
            froz.append((d, detlib.outcome(rows, i, "long")[1]))
            tv = fwd(rows, i, TREND_H)
            if tv is not None:
                trend.append((d, tv))
        print(f"\n[L={lb}일] 신호 {len(sig)}건")
        rec = gate(f"xsec_mom_L{lb}", froz, pool, regmap)
        tr_mean = st.mean([r for _, r in trend]) if trend else 0.0
        tr_med = st.median([r for _, r in trend]) if trend else 0.0
        pf = portfolio(rows_by, didx, sig)
        print(f"  {'':<22} 추세진단(60봉) mean={tr_mean*100:+.2f}% med={tr_med*100:+.2f}% (n={len(trend)}) "
              f"| 포트 top {pf['top']*100:+.0f}% vs 유니버스 {pf['universe']*100:+.0f}% ({pf['weeks']}주)")
        print(f"  {'':<22} 연도별 " + "  ".join(
            f"{y}:{v['mean']*100:+.1f}%(n{v['n']})" for y, v in rec["by_year"].items()))
        rec.update(trend=dict(n=len(trend), mean=tr_mean, median=tr_med), portfolio=pf, n_signals=len(sig))
        results[lb] = rec
    if not results:
        print("결과 없음"); return
    passed = [lb for lb in results if results[lb]["verdict"] == "PASSED"]
    strict = []
    for lb in passed:
        adj = [x for x in LOOKBACKS if x != lb and abs(LOOKBACKS.index(x) - LOOKBACKS.index(lb)) == 1]
        if results[lb]["boot_p"] < STRICT_BOOT_P and any(a in passed for a in adj):
            strict.append(lb)
    frame_blocked = [lb for lb in results
                     if results[lb]["verdict"] == "REJECTED" and results[lb]["trend"]["mean"] > 0
                     and results[lb]["mean"] <= 0]
    print("\n" + "=" * 126)
    print(f"[요약] 셀 {len(results)} | PASSED {passed or '없음'} | STRICT(배포후보) {strict or '없음'}")
    print(f"       프레임 탓 기각 후보(동결 기각 + 추세진단 양수): {frame_blocked or '없음'}")
    print("       STRICT = PASSED + boot_p<0.01 + 인접 L 중 하나도 PASSED (파라미터 칼끝 배제)")
    json.dump(dict(config=dict(lookbacks=LOOKBACKS, top_n=TOP_N, rebal=REBAL, skip=SKIP,
                               trend_h=TREND_H, boot_n=BOOT_N, strict_boot_p=STRICT_BOOT_P,
                               n_symbols=len(rows_by), min_bars=min_bars,
                               date_from=ad[0], date_to=ad[-1]),
                   results={str(k): v for k, v in results.items()},
                   passed=passed, strict=strict, frame_blocked=frame_blocked),
              open(f"_xsec_momentum{'_long' if min_bars > MIN_BARS_DEFAULT else ''}.json",
                   "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\nRESULT_JSON: " + json.dumps(dict(passed=passed, strict=strict,
                                              frame_blocked=frame_blocked,
                                              mean={str(k): round(v["mean"], 5) for k, v in results.items()}),
                                         separators=(",", ":")))


if __name__ == "__main__":
    main()
