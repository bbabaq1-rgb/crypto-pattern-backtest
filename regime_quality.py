"""
regime_quality.py — 레짐 라벨 품질 벤치마크 (1단계, 2026-09-04 사전 등록).

패턴 신호와 무관하게 **라벨 자체**를 평가한다. 거래 표본에 맞추지 않으므로 과적합 위험이
낮고, 라벨러가 고정 규칙이라 적합 단계가 없다(연도별 분해로 일관성만 본다).

지표 (라벨러마다):
  ① 분리폭 separation : 유니버스 동일가중 **20일 선행수익**의 [bull(btc∪altseason) 평균 − bear 평균].
                        라벨이 방향을 안다면 양수이고 클수록 좋다. 연도별로도 낸다.
  ② 적중률 hit_rate   : bull 라벨 날 선행20일 유니버스 수익>0, bear 는 <0, sideways 는 |수익|<5%.
  ③ 전환 지연 lag     : 사후 진실(BTC 40일 선행수익 ±5% 부호)의 국면 전환일부터 라벨이 같은
                        방향으로 바뀌기까지 일수(상한 90). 평균·중앙.
  ④ 뒤집힘 flips/yr   : 라벨 변경 횟수 / 연수. 많으면 청산(D 레짐 전환)이 잦아진다.
  ⑤ 구성 coverage     : 라벨별 일수 비율(sideways 가 살아 있는지).

판정 규칙 (실행 전 고정):
  후보가 current 를 이기려면 (a) 분리폭이 current 보다 크고 (b) 연도별 분리폭이 n>=30 인 해에서
  3/4 이상 양수이며 (c) 지연이 current 보다 짧거나 같고 (d) flips/yr 이 current 의 1.5배 이하.
  이 넷을 모두 만족한 후보만 2단계(method_q, 짝지음 거래 시험)의 채택 후보가 된다.
  실거래 코드 무변경. 출력 _regime_quality.json + RESULT_JSON.
실행: python regime_quality.py [--no-fetch]
"""
import json
import statistics as st
import sys
import time

import detlib
import fetch_data
import regime_alt as ra

FWD, TRUTH_FWD, TRUTH_THR = 20, 40, 0.05
HORIZONS = [20, 40, 60, 90]      # 진단용 — 판정은 FWD=20 하나로 고정(사전 등록), 나머지는 '느린 라벨이 긴 지평에서는 분리하는가' 확인
LAG_CAP, MIN_RUN = 90, 10
FETCH_DAYS = 1800
BULL = {"bull_btc", "bull_altseason"}


def fetch(syms):
    t0, ok = time.time(), 0
    for s in syms:
        try:
            _, total = fetch_data.update_csv(f"{s}/USDT", "1d", detlib.CSV(s, "1d"), window_days=FETCH_DAYS)
            ok += total > 0
        except Exception as e:
            print(f"  [fetch] {s} 실패: {str(e)[:60]}")
    print(f"[fetch] 1d {FETCH_DAYS}일 {ok}/{len(syms)} ({time.time()-t0:.0f}s)", flush=True)


def forward_returns(rows_by, fwd=FWD):
    """date -> 유니버스 동일가중 fwd 일 선행수익 (그날 데이터 있는 종목 평균)."""
    acc = {}
    for rows in rows_by.values():
        for i in range(len(rows) - fwd):
            acc.setdefault(rows[i]["date"], []).append(rows[i + fwd]["c"] / rows[i]["c"] - 1)
    return {d: st.mean(v) for d, v in acc.items()}


def truth_series(btc, fwd=TRUTH_FWD, thr=TRUTH_THR):
    """사후 진실: date -> 'bull'/'bear'/None (BTC fwd 일 선행수익 ±thr)."""
    out = {}
    for i in range(len(btc) - fwd):
        r = btc[i + fwd]["c"] / btc[i]["c"] - 1
        out[btc[i]["date"]] = "bull" if r > thr else "bear" if r < -thr else None
    return out


def transitions(truth, min_run=MIN_RUN):
    """진실 국면이 min_run 일 이상 이어진 뒤 반대 국면으로 바뀐 날 [(date, new_state)]."""
    dates = sorted(truth)
    out, cur, run = [], None, 0
    for d in dates:
        t = truth[d]
        if t is None:
            continue
        if t == cur:
            run += 1
        else:
            if cur is not None and run >= min_run:
                out.append((d, t))
            cur, run = t, 1
    return out


def _dir(label):
    return "bull" if label in BULL else "bear" if label == "bear" else None


def lag_stats(labels, trans, dates_sorted, cap=LAG_CAP):
    """전환일 이후 라벨이 같은 방향이 될 때까지 일수(cap 상한). 이미 같은 방향이면 0."""
    idx = {d: i for i, d in enumerate(dates_sorted)}
    lags = []
    for d, want in trans:
        if d not in idx:
            continue
        i0 = idx[d]
        lag = cap
        for k in range(0, cap + 1):
            j = i0 + k
            if j >= len(dates_sorted):
                break
            if _dir(labels.get(dates_sorted[j])) == want:
                lag = k
                break
        lags.append(lag)
    if not lags:
        return dict(n=0, mean=None, median=None, capped=0)
    return dict(n=len(lags), mean=st.mean(lags), median=st.median(lags),
                capped=sum(1 for x in lags if x >= cap))


def separation_at(labels, fwd):
    """지평별 진단: (분리폭, 적중률, n) — bull∪altseason 평균 − bear 평균 / 방향 적중."""
    ds = [d for d in labels if d in fwd]
    if not ds:
        return None
    bull = [fwd[d] for d in ds if labels[d] in BULL]
    bear = [fwd[d] for d in ds if labels[d] == "bear"]
    sep = (st.mean(bull) if bull else 0.0) - (st.mean(bear) if bear else 0.0)
    hit = sum((fwd[d] > 0) if labels[d] in BULL else (fwd[d] < 0) if labels[d] == "bear" else (abs(fwd[d]) < 0.05) for d in ds)
    return dict(separation=sep, hit_rate=hit / len(ds), n=len(ds))


def evaluate_labeler(name, labels, fwd_uni, fwd_btc, trans, fwd_by_h=None):
    dates = sorted(d for d in labels if d in fwd_uni)
    if not dates:
        return None
    by = {}
    for d in dates:
        by.setdefault(labels[d], []).append(d)
    per = {}
    for lab, ds in by.items():
        u = [fwd_uni[d] for d in ds]
        b = [fwd_btc[d] for d in ds if d in fwd_btc]
        per[lab] = dict(n=len(ds), share=len(ds) / len(dates), uni_mean=st.mean(u), uni_median=st.median(u),
                        btc_mean=st.mean(b) if b else None)
    bull = [fwd_uni[d] for d in dates if labels[d] in BULL]
    bear = [fwd_uni[d] for d in dates if labels[d] == "bear"]
    sep = (st.mean(bull) if bull else 0.0) - (st.mean(bear) if bear else 0.0)
    hit = 0
    for d in dates:
        r, lab = fwd_uni[d], labels[d]
        hit += (r > 0) if lab in BULL else (r < 0) if lab == "bear" else (abs(r) < 0.05)
    by_year = {}
    for d in dates:
        y = d[:4]
        by_year.setdefault(y, {"bull": [], "bear": []})
        if labels[d] in BULL:
            by_year[y]["bull"].append(fwd_uni[d])
        elif labels[d] == "bear":
            by_year[y]["bear"].append(fwd_uni[d])
    years = {}
    for y, v in sorted(by_year.items()):
        n = len(v["bull"]) + len(v["bear"])
        s = (st.mean(v["bull"]) if v["bull"] else 0.0) - (st.mean(v["bear"]) if v["bear"] else 0.0)
        years[y] = dict(n=n, separation=s, n_bull=len(v["bull"]), n_bear=len(v["bear"]))
    all_dates = sorted(labels)
    flips = sum(1 for a, b in zip(all_dates, all_dates[1:]) if labels[a] != labels[b])
    yrs = max(1e-9, len(all_dates) / 365.25)
    by_h = {str(h): separation_at(labels, f) for h, f in (fwd_by_h or {}).items()}
    return dict(name=name, n_days=len(dates), separation=sep, hit_rate=hit / len(dates),
                lag=lag_stats(labels, trans, all_dates), flips_per_year=flips / yrs,
                per_label=per, by_year=years, by_horizon=by_h)


def beats_current(c, cur):
    yrs = [v for v in c["by_year"].values() if v["n"] >= 30]
    pos = sum(1 for v in yrs if v["separation"] > 0)
    a = c["separation"] > cur["separation"]
    b = len(yrs) > 0 and pos / len(yrs) >= 0.75
    lc, lr = c["lag"]["mean"], cur["lag"]["mean"]
    cc = (lc is not None and lr is not None and lc <= lr) or (lc is None and lr is None)
    d = c["flips_per_year"] <= cur["flips_per_year"] * 1.5
    return dict(pass_=bool(a and b and cc and d), a_sep=a, b_years=b, c_lag=cc, d_flips=d, pos_years=pos, n_years=len(yrs))


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    syms = json.load(open("universe.json", encoding="utf-8"))["trading_universe"]
    if "--no-fetch" not in argv:
        fetch(sorted(set(syms) | {"BTC", "ETH"} | set(ra.rs.ALTS)))
    ctx = ra.load_context(syms, fetch_funding="--no-fetch" not in argv)
    rows_by, btc = ctx["rows_by"], ctx["btc"]
    fwd_uni = forward_returns(rows_by)
    fwd_btc = forward_returns({"BTC": btc})
    fwd_by_h = {h: (fwd_uni if h == FWD else forward_returns(rows_by, fwd=h)) for h in HORIZONS}
    truth = truth_series(btc)
    trans = transitions(truth)
    print(f"[data] 종목 {len(rows_by)} | 선행수익 {len(fwd_uni)}일 | 진실 전환 {len(trans)}회 | 펀딩 {ctx['funding_days']}일")
    print(f"[signals] breadth {len(ctx['signals']['breadth'])}일 | vol {len(ctx['signals']['vol'])}일")
    res = {}
    for name, labels in ctx["labels"].items():
        r = evaluate_labeler(name, labels, fwd_uni, fwd_btc, trans, fwd_by_h)
        if r:
            res[name] = r
    cur = res["current"]
    print("\n" + "=" * 120)
    print(f"{'labeler':<14}{'days':>6}{'분리폭':>8}{'적중':>7}{'지연평균':>9}{'지연중앙':>9}{'cap':>5}{'flips/yr':>9}  구성(bull_btc/alt/bear/side)  연도별 분리폭")
    print("=" * 120)
    verdicts = {}
    for name, r in res.items():
        pl = r["per_label"]
        comp = "/".join(f"{pl.get(k, {}).get('share', 0)*100:.0f}" for k in ("bull_btc", "bull_altseason", "bear", "sideways"))
        yr = " ".join(f"{y}:{v['separation']*100:+.1f}" for y, v in r["by_year"].items())
        lg = r["lag"]
        v = beats_current(r, cur) if name != "current" else None
        verdicts[name] = v
        tag = "" if v is None else ("  ← 후보" if v["pass_"] else f"  ✗{''.join(k[0] for k, ok in v.items() if k != 'pass_' and k[0] in 'abcd' and not ok)}")
        print(f"{name:<14}{r['n_days']:>6}{r['separation']*100:>+8.2f}{r['hit_rate']*100:>6.0f}%"
              f"{(lg['mean'] if lg['mean'] is not None else float('nan')):>9.1f}{(lg['median'] if lg['median'] is not None else float('nan')):>9.1f}{lg['capped']:>5}"
              f"{r['flips_per_year']:>9.1f}  {comp:<28}  {yr}{tag}")
    print("\n[라벨별 선행 20일 유니버스 평균] (라벨이 방향을 아는지 직접 본다)")
    for name, r in res.items():
        print(f"  {name:<14}" + "  ".join(f"{k}:{v['uni_mean']*100:+.2f}%(n{v['n']})" for k, v in r["per_label"].items()))
    print("\n[지평별 분리폭 / 적중률] (진단 — 판정은 20일 고정. 느린 라벨이 긴 지평에서는 방향을 아는가)")
    print(f"  {'labeler':<14}" + "".join(f"{'sep'+str(h)+'d':>9}{'hit':>6}" for h in HORIZONS))
    for name, r in res.items():
        cells = []
        for h in HORIZONS:
            x = r["by_horizon"].get(str(h))
            cells.append(f"{x['separation']*100:>+8.2f}%{x['hit_rate']*100:>5.0f}%" if x else f"{'n/a':>9}{'':>6}")
        print(f"  {name:<14}" + "".join(cells))
    cands = [n for n, v in verdicts.items() if v and v["pass_"]]
    json.dump(dict(rule=dict(fwd=FWD, truth_fwd=TRUTH_FWD, truth_thr=TRUTH_THR, lag_cap=LAG_CAP,
                             beats="sep>current & years>=3/4 pos & lag<=current & flips<=1.5x"),
                   horizons=HORIZONS, results=res, verdicts=verdicts, candidates=cands, funding_days=ctx["funding_days"]),
              open("_regime_quality.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n[후보] current 를 이긴 라벨러: {cands or '없음'}")
    print("RESULT_JSON: " + json.dumps(dict(candidates=cands,
                                            separation={n: round(r["separation"], 5) for n, r in res.items()},
                                            lag={n: r["lag"]["mean"] for n, r in res.items()}),
                                       separators=(",", ":")))


if __name__ == "__main__":
    main()
