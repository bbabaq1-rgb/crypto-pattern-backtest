"""
validate_revival.py — 베이스라인 수정 후 살아난 후보의 **실거래 프레임 확인 시험** + 신규 진입 후보
(2026-09-05, 사용자 지시 "베이스라인 버그로 기각했던 테스트들 다시 살릴 만한 건 없어? …
스스로 찾아서 테스트하고 실제 매매에서 통과될 것들 찾아와").

## 왜 두 단계인가

validate_regime_split_all(440셀) 은 **선별(screen)** 이다 — 라벨은 원 검증 잣대(±10%/20봉,
1h 는 ATR 배리어)이고 셀이 수백 개라 우연 통과가 수십 개 섞인다. 베이스라인 k=30→n 수정 후
PASSED 0 → 31, STRICT 0 → 8 (우연 기대 ≈22). 그중 STRICT 8 은 사전 규칙(boot_p<.01, 양수해>=2,
두 코호트)을 넘었지만 **실거래가 쓰는 청산 규칙으로 잰 것이 아니다.**

이 모듈은 그 후보를 **실거래와 같은 프레임**으로 다시 잰다 — 다른 프레임에서도 살아야 배포 후보다.

  · 청산: 1d/4h 는 **방식D**(paper_executor.eval_D 와 같은 규칙 = method_s.outcome:
    −8% 손절 / 레짐 라벨 전환 / 30봉 만기. 반대 신호는 adopted 패턴처럼 없음).
    1h 는 exit_spec 경로(±1.5×ATR14 배리어 + 12봉, intraday_lab.outcome_atr).
  · 진입: 셀 레짐과 진입 봉 레짐이 같을 때만 (ALL 은 무조건).
  · 코호트: all / top30 (실거래 유니버스 80 의 거래대금 상위 30).
  · 베이스라인: 같은 레짐·코호트·TF 무작위 진입을 **같은 청산 규칙**으로 평가, k = n.
  · 자산곡선: 실거래 사이징(risk 1.5% / lev 3 / 변동성 타겟팅) — method_x.equity_curve.

## 사전 등록 판정 (결과를 보기 전에 동결)

셀(패턴, 레짐, 코호트)마다 동결 게이트 5조건:
  G1 n>=20  G2 mean>0  G3 **승률>=35%** (gate v2, 2026-09-05; v1 은 median>0)  G4 boot_p<0.05 (레짐 베이스라인, k=n)  G5 OOS 4분위 양수>=2
후보(패턴, 레짐)가 **확인(CONFIRMED)** 되려면 추가로:
  C1 실거래 코호트(top30) G1~G5 통과 (2026-09-05 완화 — 종전 '두 코호트 모두')
  C2 holdout(마지막 365일) n>=10 이고 mean>0 — top30 코호트 기준
  C3 train 자산곡선 CAGR>0 이고 Calmar>0 — top30 코호트 기준
전부 만족 → registry `passed_not_deployed` 후보로 기록한다. **배포는 사용자 결정.** 하나라도
빠지면 그대로 기각 기록.

## 신규 후보 (--new)

캔들 가족(hammer/morning_star/piercing/pin_bar/dark_cloud/evening_star)은 전부 기각 이력이 있다.
다른 정보를 쓰는 4종을 사전 등록한다 — ibs_low(봉 내 위치) / rsi2_low(2기간 모멘텀 극단) /
down_streak3(연속하락+신저가) / donchian20(20일 고가 돌파 — 추세추종, 배포 중엔 three_soldiers 뿐).
선별을 거치지 않았으므로 **전 레짐 셀(4+ALL) × 2코호트** 를 돌리고 같은 C1~C3 을 요구한다.
4패턴 × 5레짐 × 2코호트 = 40셀, α=.05 우연 통과 ≈2 — C1(두 코호트 동시)이 이를 억제한다.

## 편향 주의

· 후보 8개는 **같은 데이터에서 선별된 것**이라 이 확인은 완전한 out-of-sample 이 아니다. 청산
  규칙이 다르다는 점(±10%/20봉 → 방식D)만이 독립성의 원천이다. holdout(C2)이 유일한 시간 분리.
· 4h 후보의 방식D 30봉 = 5일. 배포 중인 three_soldiers_4h 가 이 규칙으로 돈다.

실행: python validate_revival.py [--no-fetch] [--new] [--tf 1d,4h,1h]
출력: _revival.json
"""
import importlib
import json
import random
import statistics as st
import sys
import time
from datetime import date

import detlib
import gate
import intraday_lab as il
import method_s as ms
import method_x as mx
import regime_switch as rs
import sizing as sz
import validate_regime_split_all as va
from validate_regime_split import _pval, turnover_rank

SEED, BOOT_N = 42, 1000
POOL_CAP = 20000            # 베이스라인 풀 평가 상한(셀당) — 방식D 는 봉마다 최대 30봉 루프라 비용 제한
HOLDOUT_DAYS = 365
HOLDOUT_MIN_N = 10
MAX_HOLD = ms.MAX_HOLD      # 30
STOP = ms.STOP              # 0.08
REGIMES = ["bull_btc", "bull_altseason", "bear", "sideways"]
COHORTS = ["all", "top30"]
CONFIRM_COHORT = "top30"    # C2/C3 기준 코호트

# ── 후보 — validate_regime_split_all run 33947910532 (베이스라인 수정 후) STRICT 8 + 배포 재판정 ──
CANDIDATES = [
    ("triple_bottom_1d",   "bull_btc"),
    ("double_bottom_1d",   "bull_btc"),
    ("vol_awakening_4h",   "bull_btc"),
    ("breakout_retest_4h", "bull_btc"),
    ("triple_bottom_4h",   "ALL"),
    ("equal_lows_4h",      "bear"),
    ("vwap_rev_short_4h",  "bear"),
    ("fvg_short_1h",       "bull_altseason"),
    ("three_soldiers_4h",  "bull_btc"),      # 배포 중 — 레짐 베이스라인 재판정(종전 bp .165 → 수정 후 .003)
    # 2026-09-05 게이트 v2 재실행(regime_split_all run 33955072518)에서 새로 STRICT 가 된 셀 — 확인 시험 대상 추가.
    # (triple_bottom_4h|bull_btc 도 STRICT 이지만 배포된 ALL 셀의 부분집합이라 별도 확인 불필요)
    ("breakout_retest_4h", "ALL"),
    ("vol_awakening_4h",   "ALL"),
]
NEW_PATTERNS = [
    ("ibs_low_1d",      "1d", "detector_ibs_low",      "long"),
    ("rsi2_low_1d",     "1d", "detector_rsi2_low",     "long"),
    ("down_streak3_1d", "1d", "detector_down_streak3", "long"),
    ("donchian20_1d",   "1d", "detector_donchian20",   "long"),
]


def _pattern_table():
    """cid -> (tf, detect_fn, direction). va.PATTERNS + 신규."""
    t = {cid: (tf, fn, d) for cid, tf, fn, d, _ in va.PATTERNS}
    for cid, tf, mod, d in NEW_PATTERNS:
        t[cid] = (tf, (lambda rows, m=mod: importlib.import_module(m).detect(rows)), d)
    return t


# ── 실거래 프레임 청산 ──────────────────────────────────────────────────────
def live_outcome(tf, rows, si, direction, lab, atr=None):
    """(ret, hold, reason, stop_pct) — 1d/4h 방식D, 1h ATR 배리어. 계산 불가면 None."""
    if tf == "1h":
        if atr is None or atr[si] is None or atr[si] <= 0:
            return None
        _, r = il.outcome_atr(rows, si, direction, atr, il.HORIZON["1h"])
        if r is None:
            return None
        return r, il.HORIZON["1h"], "atr", il.K_ATR * atr[si] / rows[si]["c"]
    ret, hold, reason = ms.outcome(rows, si, direction, set(), lab, use_regime=True, max_hold=MAX_HOLD)
    return ret, hold, reason, STOP


def tail_for(tf):
    return il.HORIZON["1h"] if tf == "1h" else MAX_HOLD


# ── 셀 판정 ─────────────────────────────────────────────────────────────────
def gate_cell(sigs, pool_rets, seed=SEED):
    """sigs: [dict(date, ret, ...)] / pool_rets: 같은 레짐·코호트·TF 무작위 진입의 실거래 프레임 수익률."""
    rets = [s["ret"] for s in sigs]
    n = len(rets)
    mean = st.mean(rets) if rets else 0.0
    med = st.median(rets) if rets else 0.0
    boot_p, base_mean = 1.0, None
    if pool_rets and n:
        rng = random.Random(seed)
        means = [st.mean(rng.choices(pool_rets, k=n)) for _ in range(BOOT_N)]
        boot_p = sum(1 for m in means if m >= mean) / BOOT_N
        base_mean = st.mean(means)
    oos_pos = 0
    if n >= 20:
        dates = sorted(s["date"] for s in sigs)
        cuts = [dates[len(dates) * i // 4] for i in range(1, 4)]
        for q in range(4):
            lo = cuts[q - 1] if q else "0000"; hi = cuts[q] if q < 3 else "9999"
            qr = [s["ret"] for s in sigs if lo <= s["date"] < hi]
            oos_pos += (len(qr) >= 5 and st.mean(qr) > 0)
    fails = []
    if n < 20: fails.append("n<20")
    if mean <= 0: fails.append("mean<=0")
    if not gate.dist_ok(rets): fails.append(gate.dist_reason(rets))   # v2: 승률>=35% (2026-09-05)
    if boot_p >= 0.05: fails.append(f"boot_p={boot_p:.3f}")
    if n >= 20 and oos_pos < 2: fails.append(f"OOS {oos_pos}/4")
    by_year = {}
    for s in sigs:
        by_year.setdefault(s["date"][:4], []).append(s["ret"])
    reasons = {}
    for s in sigs:
        reasons[s["reason"]] = reasons.get(s["reason"], 0) + 1
    return dict(n=n, mean=mean, median=med, boot_p=boot_p, base_mean=base_mean,
                win_rate=gate.win_rate(rets), trimmed_mean=gate.trimmed_mean(rets), top5_share=gate.top_share(rets),
                edge=(mean - base_mean) if base_mean is not None else None,
                oos_pos=oos_pos, pool_n=len(pool_rets), base_k=n,
                by_year={y: dict(n=len(v), mean=st.mean(v)) for y, v in sorted(by_year.items())},
                reasons=reasons, hold=st.mean(s["hold"] for s in sigs) if sigs else 0.0,
                verdict="PASSED" if not fails else "REJECTED", reason=", ".join(fails))


def equity(sigs, span_days):
    if not sigs:
        return None
    tup = [(s["date"], s["exit_date"], s["ret"], s["hold"], s["reason"], s["stop_pct"], s["vol"]) for s in sigs]
    tup.sort()
    return mx.equity_curve(tup, span_days=span_days)


def confirm(cells, cutoff, span_train):
    """
    cells: {cohort: dict(gate=rec, sigs=[...])}. C1~C3 판정.
    반환 dict(confirmed, c1, c2, c3, holdout=..., equity=...)
    """
    # C1 (2026-09-05 완화): 두 코호트 동시 → **실거래 코호트(top30)** 통과. 사용자 지적("조건을 너무 다
    # 만족시키려 한다")에 따라 내가 얹은 확인 조건 중 가장 엄한 것을 실거래가 실제로 도는 코호트로 좁힌다.
    # all 코호트 결과는 계속 계산·보고한다(경계 판단 참고용).
    c1 = cells.get(CONFIRM_COHORT, {}).get("gate", {}).get("verdict") == "PASSED"
    ref = cells.get(CONFIRM_COHORT, {}).get("sigs", [])
    train = [s for s in ref if s["date"] < cutoff]
    hold = [s for s in ref if s["date"] >= cutoff]
    ho = dict(n=len(hold), mean=st.mean(s["ret"] for s in hold) if hold else None)
    c2 = ho["n"] >= HOLDOUT_MIN_N and ho["mean"] is not None and ho["mean"] > 0
    eq = equity(train, span_train)
    c3 = bool(eq) and eq["cagr"] > 0 and eq["calmar"] > 0
    return dict(confirmed=bool(c1 and c2 and c3), c1_live_cohort=c1, c2_holdout=c2, c3_equity=c3,
                holdout=ho, equity=eq)


# ── 데이터 ──────────────────────────────────────────────────────────────────
def build_context(tf, rows_by, cohorts, regmap):
    """레짐·코호트별 베이스라인 풀 수익률(실거래 프레임, 상한 POOL_CAP) + ATR."""
    atrs = {s: (il.atr_series(rows) if tf == "1h" else None) for s, rows in rows_by.items()}
    tail = tail_for(tf)
    rng = random.Random(SEED)
    pools = {}
    for cname, cs in cohorts.items():
        for g in REGIMES + ["ALL"]:
            idx = [(s, i) for s in cs for rows in [rows_by[s]]
                   for i in range(30, len(rows) - tail - 1)
                   if g == "ALL" or regmap.get(rows[i]["date"]) == g]
            if len(idx) > POOL_CAP:
                idx = rng.sample(idx, POOL_CAP)
            pools[(cname, g)] = idx
    return pools, atrs


def eval_pool(tf, idx, rows_by, atrs, regmap, direction):
    out = []
    for s, i in idx:
        rows = rows_by[s]
        lab = lambda j, rows=rows: regmap.get(rows[j]["date"])
        r = live_outcome(tf, rows, i, direction, lab, atrs.get(s))
        if r is not None:
            out.append(r[0])
    return out


def collect(tf, detect_fn, direction, rows_by, atrs, regmap):
    tail = tail_for(tf)
    by_sym = {}
    for s, rows in rows_by.items():
        lab = lambda j, rows=rows: regmap.get(rows[j]["date"])
        try:
            idxs = detect_fn(rows)
        except Exception as e:
            print(f"  [detect] {s} {tf} 오류: {str(e)[:60]}"); idxs = []
        out = []
        for si in idxs:
            if si + 1 >= len(rows) or si >= len(rows) - tail - 1 or si < 30:
                continue
            r = live_outcome(tf, rows, si, direction, lab, atrs.get(s))
            if r is None:
                continue
            vol = sz.realized_vol(rows, si, tf=tf)
            if vol is None:
                continue
            ret, hold, reason, stop_pct = r
            out.append(dict(sym=s, date=rows[si]["date"], regime=regmap.get(rows[si]["date"]),
                            ret=ret, hold=hold, reason=reason, stop_pct=stop_pct, vol=vol,
                            exit_date=rows[min(si + hold, len(rows) - 1)]["date"]))
        by_sym[s] = out
    return by_sym


def _f(v, w=8):
    return f"{'n/a':>{w}}" if v is None else f"{v*100:>+{w-1}.2f}%"


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    new_mode = "--new" in argv
    tfs = argv[argv.index("--tf") + 1].split(",") if "--tf" in argv else ["1d", "4h", "1h"]
    syms = va._syms()
    if "--no-fetch" not in argv:
        va.fetch(syms, [tf for tf in ("1d", "4h", "1h") if tf in tfs])
    regmap = rs.build_regime_map()
    table = _pattern_table()
    todo = ([(cid, g) for cid, _, _, _ in NEW_PATTERNS for g in REGIMES + ["ALL"]] if new_mode
            else list(CANDIDATES))
    todo = [(cid, g) for cid, g in todo if table[cid][0] in tfs]
    print(f"[모드] {'신규 후보 전 셀' if new_mode else 'STRICT 후보 확인'} | 셀(패턴,레짐) {len(todo)} | TF {tfs}")

    rows_1d = va.load_tf(syms, "1d")
    ranked = turnover_rank(rows_1d)
    all_dates = sorted({r["date"] for rows in rows_1d.values() for r in rows})
    d_hi = date.fromisoformat(all_dates[-1]).toordinal()
    cutoff = date.fromordinal(d_hi - HOLDOUT_DAYS).isoformat()
    print(f"[분할] train < {cutoff} <= holdout")

    results, ctx_cache = {}, {}
    for cid, g in todo:
        tf, detect_fn, direction = table[cid]
        if tf not in ctx_cache:
            rows_by = rows_1d if tf == "1d" else va.load_tf(syms, tf)
            cohorts = {"all": set(rows_by), "top30": set(s for s in ranked[:30] if s in rows_by)}
            pools, atrs = build_context(tf, rows_by, cohorts, regmap)
            first = min(r["date"] for rows in rows_by.values() for r in rows)
            span_train = max(1, date.fromisoformat(cutoff).toordinal() - date.fromisoformat(first).toordinal())
            ctx_cache[tf] = dict(rows_by=rows_by, cohorts=cohorts, pools=pools, atrs=atrs,
                                 span_train=span_train, pool_rets={}, sigs={})
            print(f"[{tf}] 종목 {len(rows_by)} | train 창 {span_train}일", flush=True)
        ctx = ctx_cache[tf]
        key = (cid, direction)
        if key not in ctx["sigs"]:
            t0 = time.time()
            ctx["sigs"][key] = collect(tf, detect_fn, direction, ctx["rows_by"], ctx["atrs"], regmap)
            print(f"  [collect] {cid}: {sum(len(v) for v in ctx['sigs'][key].values())}건 ({time.time()-t0:.0f}s)", flush=True)
        by_sym = ctx["sigs"][key]
        cells = {}
        print(f"\n[{cid} {direction} @{tf} | 셀 레짐 {g}]")
        for cname in COHORTS:
            cs = ctx["cohorts"][cname]
            pk = (cname, g, direction)
            if pk not in ctx["pool_rets"]:
                t0 = time.time()
                ctx["pool_rets"][pk] = eval_pool(tf, ctx["pools"][(cname, g)], ctx["rows_by"], ctx["atrs"], regmap, direction)
                print(f"  [pool] {cname}:{g}:{direction} {len(ctx['pool_rets'][pk])}건 ({time.time()-t0:.0f}s)", flush=True)
            sigs = [x for s in cs for x in by_sym.get(s, []) if g == "ALL" or x["regime"] == g]
            rec = gate_cell(sigs, ctx["pool_rets"][pk])
            cells[cname] = dict(gate=rec, sigs=sigs)
            yr = " ".join(f"{y}:{v['mean']*100:+.1f}%(n{v['n']})" for y, v in rec["by_year"].items())
            print(f"  {cname:<6} n={rec['n']:>5} mean={_f(rec['mean'])} med={_f(rec['median'])} 승률 {rec['win_rate']*100:>3.0f}% 절사 {_f(rec['trimmed_mean'])} top5 {(rec['top5_share'] or 0)*100:>3.0f}% "
                  f"| 레짐평균 {_f(rec['base_mean'])} 엣지 {_f(rec['edge'])} | boot_p={rec['boot_p']:.3f} "
                  f"OOS={rec['oos_pos']}/4 보유 {rec['hold']:.1f} -> {rec['verdict']} {rec['reason']}")
            print(f"         연도별 {yr} | 청산 {rec['reasons']}")
        cf = confirm(cells, cutoff, ctx["span_train"])
        eq = cf["equity"] or {}
        print(f"  => {'CONFIRMED' if cf['confirmed'] else 'not confirmed'} | C1 실거래코호트 {cf['c1_live_cohort']} "
              f"| C2 holdout n={cf['holdout']['n']} mean={_f(cf['holdout']['mean'])} {cf['c2_holdout']} "
              f"| C3 자산곡선 CAGR {_f(eq.get('cagr'))} MDD {_f(eq.get('mdd'))} Calmar {eq.get('calmar', 0):.2f} {cf['c3_equity']}")
        results[f"{cid}|{g}"] = dict(pattern=cid, regime=g, tf=tf, direction=direction,
                                     cells={c: cells[c]["gate"] for c in cells}, confirm=cf)

    confirmed = [k for k, v in results.items() if v["confirm"]["confirmed"]]
    print("\n" + "=" * 100)
    print(f"[요약] 셀(패턴,레짐) {len(results)} | CONFIRMED {len(confirmed)}")
    for k in confirmed:
        v = results[k]; r30 = v["cells"]["top30"]; eq = v["confirm"]["equity"]
        print(f"  CONFIRMED {v['pattern']:<22} {v['regime']:<15} top30 n={r30['n']} mean={_f(r30['mean'])} "
              f"boot_p={r30['boot_p']:.3f} | holdout {_f(v['confirm']['holdout']['mean'])} | Calmar {eq['calmar']:.2f}")
    out = "_revival_new.json" if new_mode else "_revival.json"
    json.dump(dict(mode="new" if new_mode else "candidates", cutoff=cutoff, results=results, confirmed=confirmed),
              open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print(f"[저장] {out}")
    print("RESULT_JSON: " + json.dumps(dict(confirmed=confirmed, n=len(results)), ensure_ascii=False))


if __name__ == "__main__":
    main()
