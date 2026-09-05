"""
validate_regime_split_all.py — 기각·정지 패턴 전수 레짐별 재시험 (2026-09-04, 사용자 질문
"지금까지 레짐 구분 없이 백테스트했으면 기각했던 것들도 전부 다시 봐야 하지 않나").

validate_regime_split(배포 1d 6종) 과 같은 프레임을 **기각(rejected)·정지(suspended)·보류(holding)
패턴 전부**로 넓힌다. 셀 = 패턴 x 진입 레짐(bull_btc / bull_altseason / bear / sideways / ALL)
x 코호트(all / top30). 레짐은 진입 봉 날짜의 일봉 레짐(regime_switch.build_regime_map, 닫힌 봉)
— 4h/1h 봉도 그날의 일봉 레짐을 쓴다(실거래 라우팅이 그렇게 돈다).

라벨 프레임 (TF 별, 원 검증과 같은 잣대 — 단 1h 는 교정된 잣대):
  1d / 1w / 4h : 동결 ±10%/20봉 (detlib.outcome). 원 검증이 이 라벨이었다.
  1h           : ±1.5xATR14 배리어 + 12봉 보유 + 왕복 0.2% (intraday_lab.outcome_atr).
                 2026-08-29 발견 — ±10%/20봉은 1h 에서 배리어 도달률 0% 라 측정 오류.
                 즉 1h 셀은 '레짐' 과 '라벨' 두 가지가 동시에 바뀐 재시험이다.
하모닉·triple_bottom 은 룩어헤드 제거 판(confirm=True / causal=True) 만 본다 — 원 등재 수치는
미래 봉을 봤으므로 비교 대상이 아니다.

boot_p 베이스라인 = **같은 레짐·같은 코호트·같은 TF 의 무작위 진입** (validate_regime_split 과 동일).
게이트(동결): n>=20, mean>0, median>0, boot_p<0.05, OOS 4분위 양구간>=2.

**다중검정 사전 규칙** (실행 전 고정): 셀이 수백 개라 boot_p<0.05 만으로는 우연 통과가 수십 개
나온다. 그래서 '배포 후보' 는 PASSED 에 더해 (a) boot_p < 0.01 (b) 연도별 양수 해 >= 2
(c) all/top30 두 코호트 모두 PASSED — 셋 다 만족해야 한다(STRICT). PASSED 만 된 셀은
'재시험 후보' 로만 기록한다. 이 규칙은 결과를 보기 전에 정했다.

실거래 코드 무변경. 출력 _regime_split_all.json + RESULT_JSON.
실행: python validate_regime_split_all.py [--no-fetch] [--tf 1d,4h,1h,1w] [--quick]
"""
import importlib
import json
import random
import statistics as st
import sys
import time
from math import sqrt

import detlib
import fetch_data
import intraday_lab as il
import regime_switch as rs
from validate_regime_split import _pval, turnover_rank

SEED, BOOT_N = 42, 1000
LABEL_W = detlib.LABEL_WINDOW
REGIMES = ["bull_btc", "bull_altseason", "bear", "sideways"]
COHORTS = ["all", "top30"]
FETCH_WINDOWS = {"1d": 1800, "4h": 1100, "1h": 365}
STRICT_BOOT_P = 0.01
STRICT_MIN_POS_YEARS = 2


# ── 패턴 목록 (사전 등록) ────────────────────────────────────────────────────
# (cell_id, tf, module, attr_or_callable_name, direction, 원 판정 메모)
def _harm(name, cfg_src):
    import detector_harmonic_base as hb
    if cfg_src == "4h":
        cfg = importlib.import_module(f"detector_{name}").CFG
    else:
        from validate_1h_patterns import HARMONIC_CFG
        cfg = HARMONIC_CFG[name]
    return lambda rows, c=cfg: hb.detect_harmonic(rows, c, confirm=True)


def _tb_causal(rows):
    import detector_triple_bottom as tb
    return tb.detect(rows, causal=True)


def _attr(mod, fn):
    return lambda rows: getattr(importlib.import_module(mod), fn)(rows)


PATTERNS = [
    # ── 1d 기각 (registry patterns rejected + candle_results 기각) ──
    ("pin_bar_1d",          "1d", _attr("detector_pin_bar", "detect"),          "long",  "rejected"),
    ("nr7_1d",              "1d", _attr("detector_nr7", "detect"),              "long",  "rejected"),
    ("bb_squeeze_1d",       "1d", _attr("detector_bb_squeeze", "detect"),       "long",  "rejected"),
    ("double_bottom_1d",    "1d", _attr("detector_double_bottom", "detect"),    "long",  "rejected"),
    ("liquidity_sweep_1d",  "1d", _attr("detector_liquidity_sweep", "detect_sweeps"), "long", "rejected"),
    ("inverse_hs_1d",       "1d", _attr("detector_inverse_hs", "detect"),       "long",  "rejected"),
    ("rsi_divergence_1d",   "1d", _attr("detector_rsi_divergence", "detect"),   "long",  "rejected"),
    ("macd_divergence_1d",  "1d", _attr("detector_macd_divergence", "detect"),  "long",  "rejected"),
    ("order_block_1d",      "1d", _attr("detector_order_block", "detect"),      "long",  "rejected"),
    ("bos_choch_1d",        "1d", _attr("detector_bos_choch", "detect"),        "long",  "rejected"),
    ("spring_wyckoff_1d",   "1d", _attr("detector_spring_wyckoff", "detect"),   "long",  "rejected"),
    ("inverse_hs_short_1d", "1d", _attr("detector_inverse_hs_short", "detect"), "short", "rejected"),
    ("order_block_short_1d","1d", _attr("detector_order_block_short", "detect"),"short", "rejected"),
    ("triple_bottom_1d",    "1d", _tb_causal,                                   "long",  "rejected(causal)"),
    ("triple_top_1d",       "1d", _attr("detector_triple_top", "detect"),       "short", "rejected"),
    ("hammer_1d",           "1d", _attr("detector_hammer", "detect"),           "long",  "rejected"),
    ("piercing_line_1d",    "1d", _attr("detector_piercing_line", "detect"),    "long",  "rejected"),
    ("morning_star_1d",     "1d", _attr("detector_morning_star", "detect"),     "long",  "rejected"),
    ("dark_cloud_cover_1d", "1d", _attr("detector_dark_cloud_cover", "detect"), "short", "rejected"),
    ("evening_star_1d",     "1d", _attr("detector_evening_star", "detect"),     "short", "rejected"),
    ("marubozu_short_1d",   "1d", _attr("detector_marubozu_short", "detect"),   "short", "rejected"),
    # ── 1w (1d 리샘플) ──
    ("triple_bottom_1w",    "1w", _tb_causal,                                   "long",  "suspended_lookahead(causal REJECT)"),
    ("triple_top_1w",       "1w", _attr("detector_triple_top", "detect"),       "short", "rejected"),
    # ── 4h 기각 + 정지 하모닉(인과 판) + 보류 + 배포(three_soldiers, 레짐 확인용) ──
    ("three_crows_4h",      "4h", _attr("detector_three_crows_4h", "detect"),   "short", "rejected"),
    ("breakout_retest_4h",  "4h", _attr("detector_breakout_retest_4h", "detect"),"long", "rejected"),
    ("equal_highs_4h",      "4h", _attr("detector_equal_highs_4h", "detect"),   "short", "rejected"),
    ("equal_lows_4h",       "4h", _attr("detector_equal_lows_4h", "detect"),    "long",  "rejected"),
    ("vwap_rev_long_4h",    "4h", _attr("detector_vwap_rev_long_4h", "detect"), "long",  "rejected"),
    ("vwap_rev_short_4h",   "4h", _attr("detector_vwap_rev_short_4h", "detect"),"short", "rejected"),
    ("vol_awakening_4h",    "4h", _attr("detector_vol_awakening_4h", "detect"), "long",  "rejected"),
    ("gartley_4h",          "4h", _harm("gartley", "4h"),                       "long",  "suspended_lookahead(causal REJECT)"),
    ("bat_4h",              "4h", _harm("bat", "4h"),                           "long",  "suspended_lookahead(causal REJECT)"),
    ("butterfly_4h",        "4h", _harm("butterfly", "4h"),                     "long",  "suspended_lookahead(causal REJECT)"),
    ("crab_4h",             "4h", _harm("crab", "4h"),                          "long",  "holding"),
    ("shark_4h",            "4h", _harm("shark", "4h"),                         "long",  "holding"),
    ("cypher_4h",           "4h", _harm("cypher", "4h"),                        "long",  "holding"),
    ("triple_bottom_4h",    "4h", _tb_causal,                                   "long",  "rejected(causal)"),
    ("three_soldiers_4h",   "4h", _attr("detector_three_soldiers_4h", "detect"),"long",  "deployed(bull only) — 레짐 확인"),
    # ── 1h 기각 + 정지 하모닉 1h (ATR 프레임) ──
    ("three_soldiers_1h",   "1h", _attr("detector_three_soldiers_1h", "detect"),"long",  "rejected"),
    ("three_crows_1h",      "1h", _attr("detector_three_crows_1h", "detect"),   "short", "rejected"),
    ("engulfing_1h",        "1h", _attr("detector_engulfing", "detect"),        "long",  "rejected"),
    ("engulfing_short_1h",  "1h", _attr("detector_engulfing_short", "detect"),  "short", "rejected"),
    ("inverted_hammer_1h",  "1h", _attr("detector_inverted_hammer", "detect"),  "long",  "rejected"),
    ("fvg_long_1h",         "1h", _attr("detector_fvg", "detect"),              "long",  "rejected"),
    ("fvg_short_1h",        "1h", _attr("detector_fvg_short", "detect"),        "short", "rejected"),
    ("gartley_1h",          "1h", _harm("gartley", "1h"),                       "long",  "rejected(boot_p .092)/causal REJECT"),
    ("bat_1h",              "1h", _harm("bat", "1h"),                           "long",  "suspended_lookahead(causal REJECT)"),
    ("butterfly_1h",        "1h", _harm("butterfly", "1h"),                     "long",  "suspended_lookahead(causal REJECT)"),
    ("vwap_rev_long_1h",    "1h", _attr("detector_vwap_rev_long_1h", "detect"), "long",  "rejected"),
    ("vwap_rev_short_1h",   "1h", _attr("detector_vwap_rev_short_1h", "detect"),"short", "rejected"),
    ("breakout_retest_1h",  "1h", _attr("detector_breakout_retest_1h", "detect"),"long", "rejected"),
    ("bb_zscore_1h",        "1h", _attr("detector_bb_zscore_1h", "detect_long"),"long",  "rejected"),
    ("bb_zscore_short_1h",  "1h", _attr("detector_bb_zscore_1h", "detect_short"),"short","rejected"),
    ("rsi_extreme_1h",      "1h", _attr("detector_rsi_extreme_1h", "detect_long"),"long","rejected"),
    ("rsi_extreme_short_1h","1h", _attr("detector_rsi_extreme_1h", "detect_short"),"short","rejected"),
]


# ── 라벨 프레임 ─────────────────────────────────────────────────────────────
def outcome_fixed(rows, i, direction, _atr=None):
    return detlib.outcome(rows, i, direction)[1]


def outcome_atr1h(rows, i, direction, atr):
    _, r = il.outcome_atr(rows, i, direction, atr, il.HORIZON["1h"])
    return r


def frame_of(tf):
    """(outcome_fn, need_atr, min_tail) — 마지막 min_tail 봉은 라벨이 잘리므로 신호에서 제외."""
    if tf == "1h":
        return outcome_atr1h, True, il.HORIZON["1h"]
    return outcome_fixed, False, LABEL_W


# ── 게이트 ──────────────────────────────────────────────────────────────────
def gate_cell(label, sigs, pool, outcome_fn, verbose=True):
    """sigs: [(date, ret, direction)], pool: [(rows, i, atr)] 같은 레짐·코호트·TF 무작위 진입 후보."""
    rets = [r for _, r, *_ in sigs]
    n = len(rets)
    mean = st.mean(rets) if rets else 0.0
    med = st.median(rets) if rets else 0.0
    t = p = 0.0
    if n >= 2 and st.stdev(rets) > 0:
        t = mean / (st.stdev(rets) / sqrt(n)); p = _pval(t, n - 1)
    boot_p, base_mean = 1.0, None
    pool_n, base_k = len(pool), 0
    if pool and n:
        rng = random.Random(SEED)
        direction = sigs[0][2]
        # 베이스라인 표본 수 = 셀 표본 수(k = n). 종전 k=min(30, n) 은 베이스라인 평균의
        # 표준오차를 sqrt(30) 에 묶어 분포를 넓히고 boot_p 를 부풀렸다 — 게이트 문턱이 아니라
        # 추정량의 버그다. 풀은 한 번만 평가한다(outcome_fn 은 결정론적).
        pool_rets = [v for v in (outcome_fn(r, i, direction, a) for r, i, a in pool) if v is not None]
        base_k = n
        ge, means = 0, []
        if pool_rets:
            for _ in range(BOOT_N):
                bm = st.mean(rng.choices(pool_rets, k=base_k))
                means.append(bm); ge += bm >= mean
        if means:
            boot_p = ge / len(means); base_mean = st.mean(means)
    oos = []
    if n >= 20:
        dates = sorted(d for d, *_ in sigs)
        cuts = [dates[len(dates) * i // 4] for i in range(1, 4)]
        for q in range(4):
            lo = cuts[q - 1] if q else "0000"; hi = cuts[q] if q < 3 else "9999"
            qr = [r for d, r, *_ in sigs if lo <= d < hi]
            qm = st.mean(qr) if qr else 0.0
            oos.append(dict(q=q + 1, n=len(qr), mean=qm, ok=len(qr) >= 5 and qm > 0))
    oos_pos = sum(1 for o in oos if o["ok"])
    ok = n >= 20 and mean > 0 and med > 0 and boot_p < 0.05 and oos_pos >= 2
    fails = []
    if n < 20: fails.append("n<20")
    if mean <= 0: fails.append("mean<=0")
    if med <= 0: fails.append("median<=0")
    if boot_p >= 0.05: fails.append(f"boot_p={boot_p:.3f}")
    if n >= 20 and oos_pos < 2: fails.append(f"OOS {oos_pos}/4")
    by_year = {}
    for d, r, *_ in sigs:
        by_year.setdefault(d[:4], []).append(r)
    years = {y: dict(n=len(v), mean=st.mean(v)) for y, v in sorted(by_year.items())}
    pos_years = sum(1 for v in years.values() if v["mean"] > 0 and v["n"] >= 5)
    rec = dict(n=n, mean=mean, median=med, t=t, p=p, boot_p=boot_p, oos_pos=oos_pos,
               base_mean=base_mean, pool_n=pool_n, base_k=base_k,
               edge_vs_regime=(mean - base_mean) if base_mean is not None else None,
               by_year=years, pos_years=pos_years,
               verdict="PASSED" if ok else "REJECTED", reason=", ".join(fails))
    if verbose:
        bm = f"{base_mean*100:+6.2f}%" if base_mean is not None else "   n/a"
        ed = f"{(mean-base_mean)*100:+6.2f}%p" if base_mean is not None else "     n/a"
        yr = " ".join(f"{y}:{v['mean']*100:+.1f}%(n{v['n']})" for y, v in years.items())
        print(f"  {label:<40} n={n:>5} mean={mean*100:+6.2f}% med={med*100:+6.2f}% "
              f"| 레짐평균 {bm} 엣지 {ed} | boot_p={boot_p:.3f} OOS={oos_pos}/4 -> {rec['verdict']} {rec['reason']}")
        if years:
            print(f"  {'':<40} 연도별 {yr}")
    return rec


def strict_ok(cells):
    """all/top30 두 코호트 모두 PASSED + boot_p<0.01 + 양수 해>=2 (사전 규칙)."""
    return all(c is not None and c["verdict"] == "PASSED" and c["boot_p"] < STRICT_BOOT_P
               and c["pos_years"] >= STRICT_MIN_POS_YEARS for c in cells)


# ── 데이터 ──────────────────────────────────────────────────────────────────
def _syms():
    return json.load(open("universe.json", encoding="utf-8"))["trading_universe"]


def fetch(syms, tfs):
    for tf in tfs:
        win = FETCH_WINDOWS[tf]
        t0, ok = time.time(), 0
        for s in syms:
            try:
                _, total = fetch_data.update_csv(f"{s}/USDT", tf, detlib.CSV(s, tf), window_days=win)
                ok += total > 0
            except Exception as e:
                print(f"  [fetch] {s} {tf} 실패: {str(e)[:60]}")
        print(f"[fetch] {tf} {win}일 {ok}/{len(syms)} ({time.time()-t0:.0f}s)", flush=True)


def load_tf(syms, tf):
    out = {}
    for s in syms:
        try:
            rows = detlib.load_ohlcv(s, tf)
            if rows:
                out[s] = rows
        except Exception:
            pass
    return out


def build_pools(rows_by, cohorts, regmap, tf):
    _, need_atr, tail = frame_of(tf)
    atrs = {s: (il.atr_series(rows) if need_atr else None) for s, rows in rows_by.items()}
    pools = {}
    for cname, cs in cohorts.items():
        for g in REGIMES + ["ALL"]:
            pools[(cname, g)] = [(rows, i, atrs[s]) for s in cs for rows in [rows_by[s]]
                                for i in range(len(rows) - tail - 1)
                                if (g == "ALL" or regmap.get(rows[i]["date"]) == g)
                                and (not need_atr or (atrs[s][i] is not None and atrs[s][i] > 0))]
    return pools, atrs


def collect(detect_fn, rows_by, atrs, regmap, tf, direction):
    outcome_fn, need_atr, tail = frame_of(tf)
    sigs_by_sym = {}
    for s, rows in rows_by.items():
        out = []
        try:
            idxs = detect_fn(rows)
        except Exception as e:
            print(f"  [detect] {s} {tf} 오류: {str(e)[:60]}"); idxs = []
        for si in idxs:
            if si + 1 >= len(rows) or si >= len(rows) - tail - 1:
                continue
            ret = outcome_fn(rows, si, direction, atrs[s] if need_atr else None)
            if ret is None:
                continue
            out.append((rows[si]["date"], ret, direction, regmap.get(rows[si]["date"])))
        sigs_by_sym[s] = out
    return sigs_by_sym


def _labeler_arg(argv=None):
    """--labeler <name> (regime_alt.LABELERS). 없으면 None = 현행 레짐."""
    argv = sys.argv[1:] if argv is None else argv
    if "--labeler" in argv:
        i = argv.index("--labeler")
        return argv[i + 1] if i + 1 < len(argv) else None
    return None


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    tfs = ["1d", "1w", "4h", "1h"]
    if "--tf" in argv:
        tfs = argv[argv.index("--tf") + 1].split(",")
    quick = "--quick" in argv
    syms = _syms()
    if "--no-fetch" not in argv:
        fetch(syms, [tf for tf in ("1d", "4h", "1h") if tf in tfs or (tf == "1d" and "1w" in tfs)])
    regmap = rs.build_regime_map()
    # --labeler <name>: regime_alt 후보 라벨러로 셀을 다시 정의해 재시험 (라벨러 채택 시 필수 재검증 경로).
    # 기본은 현행 라벨. 후보 맵은 현행 3신호 + 추가 신호로 같은 데이터에서 만든다.
    labeler = _labeler_arg()
    if labeler and labeler != "current":
        import regime_alt as ra
        ctx = ra.load_context(fetch_funding=False)
        if labeler not in ctx["labels"]:
            raise SystemExit(f"[labeler] 알 수 없는 라벨러 {labeler} — {list(ctx['labels'])}")
        regmap = ctx["labels"][labeler]
        print(f"[labeler] 셀 정의 라벨러 = {labeler} ({len(regmap)}일)")
    ymix = {}
    for d, g in regmap.items():
        ymix.setdefault(d[:4], {}).setdefault(g, 0); ymix[d[:4]][g] += 1
    print(f"[regime] {len(regmap)}일 | 연도별: " + "  ".join(f"{y}:{v}" for y, v in sorted(ymix.items())))
    rows_1d = load_tf(syms, "1d")
    ranked = turnover_rank(rows_1d)
    print(f"[rank] top30: {ranked[:30]}")
    results, summary = {}, []
    for tf in tfs:
        rows_by = rows_1d if tf == "1d" else load_tf(syms, tf)
        if not rows_by:
            print(f"[{tf}] 데이터 없음 — 스킵"); continue
        cohorts = {"all": set(rows_by), "top30": set(s for s in ranked[:30] if s in rows_by)}
        pools, atrs = build_pools(rows_by, cohorts, regmap, tf)
        print(f"\n[{tf}] 종목 {len(rows_by)} | 풀 크기 " +
              " ".join(f"{g}:{len(pools[('all', g)])}" for g in REGIMES + ["ALL"]))
        for cid, ptf, detect_fn, direction, memo in PATTERNS:
            if ptf != tf:
                continue
            t0 = time.time()
            sigs_by_sym = collect(detect_fn, rows_by, atrs, regmap, tf, direction)
            results[cid] = {"tf": tf, "direction": direction, "prior": memo, "cells": {}}
            print(f"\n[{cid} {direction} @{tf}] 원판정: {memo}")
            for cname, cs in cohorts.items():
                for g in REGIMES + ["ALL"]:
                    if not pools[(cname, g)]:
                        continue
                    sigs = [x for s in cs for x in sigs_by_sym.get(s, []) if g == "ALL" or x[3] == g]
                    if quick and len(sigs) < 20:
                        continue
                    rec = gate_cell(f"{cid}:{cname}:{g}", [(d, r, dr) for d, r, dr, _ in sigs],
                                    pools[(cname, g)], frame_of(tf)[0])
                    results[cid]["cells"][f"{cname}:{g}"] = rec
            cells = results[cid]["cells"]
            for g in REGIMES + ["ALL"]:
                pair = [cells.get(f"all:{g}"), cells.get(f"top30:{g}")]
                passed = [c for c in pair if c and c["verdict"] == "PASSED"]
                if passed:
                    summary.append(dict(pattern=cid, tf=tf, direction=direction, regime=g,
                                        passed_cohorts=[k for k, c in zip(COHORTS, pair) if c and c["verdict"] == "PASSED"],
                                        strict=strict_ok(pair),
                                        best=max(passed, key=lambda c: c["n"])))
            print(f"  ({time.time()-t0:.0f}s)")
    json.dump(dict(windows=FETCH_WINDOWS, year_mix=ymix, top30=ranked[:30], cohorts=COHORTS,
                   strict_rule=dict(boot_p=STRICT_BOOT_P, pos_years=STRICT_MIN_POS_YEARS, both_cohorts=True),
                   results=results, summary=summary),
              open("_regime_split_all.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    n_cells = sum(len(v["cells"]) for v in results.values())
    print(f"\n[요약] 패턴 {len(results)} 셀 {n_cells} | PASSED (패턴,레짐) {len(summary)} | "
          f"STRICT {sum(1 for s in summary if s['strict'])} | 기대 우연통과(α=.05) ≈ {n_cells*0.05:.0f}")
    for s in summary:
        b = s["best"]
        print(f"  {'STRICT ' if s['strict'] else '       '}{s['pattern']:<22} {s['regime']:<15} {s['passed_cohorts']} "
              f"n={b['n']} mean={b['mean']*100:+.2f}% med={b['median']*100:+.2f}% boot_p={b['boot_p']:.3f} "
              f"엣지 {(b['edge_vs_regime'] or 0)*100:+.2f}%p 양수해 {b['pos_years']}")
    print("\nRESULT_JSON: " + json.dumps(
        dict(passed=[(s["pattern"], s["regime"], s["passed_cohorts"]) for s in summary],
             strict=[(s["pattern"], s["regime"]) for s in summary if s["strict"]],
             n_cells=n_cells), separators=(",", ":")))


if __name__ == "__main__":
    main()
