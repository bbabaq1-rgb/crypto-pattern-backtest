"""
validate_late_entry.py — triple_bottom 1w **지각 진입(L3+3봉)** 사전 등록 시험 (2026-09-05, 사용자 지시).

배경
  2026-09-03 룩어헤드 점검에서 triple_bottom_1w 의 등재 수치(n=142 +7.7%)는 L3(세 번째 바닥)가
  확정되기 전(L3+1·L3+2)에 난 돌파 38건(평균 약 +20%)이 만든 것으로 판명됐다. 그 돌파봉은 실거래가
  마지막 봉으로는 절대 잡을 수 없다(L3 확정에 이후 3봉의 저가가 필요). 실거래가 잡을 수 있는
  확정 후 돌파 104건은 게이트 미달(+3.07%, boot_p .164 / v2 재실행 +3.65% bp .133) → 등재 정지.

가설(사전 등록)
  미확정 돌파 셋업은 '바닥 직후 강하게 튄' 셋업이라 엣지가 있고, L3 가 확정되는 첫 봉(L3+3)에
  뒤늦게 들어가도 그 엣지의 상당 부분이 남는다. 즉 신호봉을 돌파봉 → L3+3 으로 옮긴 **인과적**
  규칙이 게이트를 넘는다.  (주봉이므로 1~2봉 지각 = 1~2주 지각 — 감쇠가 클 수 있다. 그걸 잰다.)

arm (신호 집합, detector_triple_bottom.detect(mode=))
  late          [주 판정]  미확정 돌파 셋업만. 신호 = L3+3, 그 봉 종가 > 넥라인(돌파 유지). 인과.
  late_nohold   [진단]     종가 조건 없이 L3+3.
  causal        [참고]     확정 후 돌파(현 정지 판정의 집합, 9/3 REJECT 재현용).
  early_ceiling [참고]     같은 미확정 셋업을 돌파봉에서 진입(실거래 불가 — 상한선).
  union_live    [진단]     late ∪ causal (두 모드를 함께 켰을 때의 실거래 집합).

판정 기준(사전 등록 — 사후 변경 금지)
  1단계 동결 라벨(±10%/20봉, 수수료 0.2%) 게이트 v2: n>=20, mean>0, 승률>=35%(gate.dist_ok),
        boot_p<0.05(같은 1w 무작위 진입 k=n 베이스라인, 1000회, 시드 42), OOS 4분위 양구간>=2.
  2단계 실거래 프레임(validate_revival 과 같은 정의):
        C1 실거래 코호트(1w 는 유니버스 전체 = 'all')에서 방식D 청산·k=n 베이스라인 게이트 PASSED
        C2 holdout(마지막 365일) n>=10 이고 mean>0  — n<10 이면 INCONCLUSIVE(배포 불가, 기각도 아님)
        C3 train 자산곡선(실거래 사이징) CAGR>0 이고 Calmar>0
  최종: 1단계 PASSED ∧ C1 ∧ C2 ∧ C3 → PASSED(자율 반영 대상: adopted 1w 항목에 mode=late 등재)
        1단계 PASSED 이나 C2 표본 부족 → INCONCLUSIVE.  그 외 → REJECTED.
  판정은 **late 한 arm** 으로만 한다. 나머지는 참고·진단이며 통과해도 반영하지 않는다.

진단(판정 무관)
  · 감쇠 곡선: 미확정 셋업을 돌파봉+d(d=0..3) 에서 진입했을 때 평균 — 지각의 비용
  · brk−L3 분포(1 vs 2), 종가 조건으로 탈락한 셋업 수, 레짐별·연도별 분해
출력: _late_entry.json + RESULT_JSON.  실행: python validate_late_entry.py [--no-fetch]
"""
import json
import random
import statistics as st
import sys
import time
from datetime import date
from math import sqrt

import detlib
import fetch_data
import gate
import method_s as ms
import method_x as mx
import regime_switch as rs
import sizing as sz
import detector_triple_bottom as tb
from validate_regime_split import _pval, turnover_rank
from validate_revival import _tnum, equity as _equity

SEED, BOOT_N = 42, 1000
TF = "1w"
FETCH_1D_DAYS = 1800
LABEL_W = detlib.LABEL_WINDOW
MAX_HOLD, STOP = ms.MAX_HOLD, ms.STOP
HOLDOUT_DAYS, HOLDOUT_MIN_N = 365, 10
LIVE_COHORT = "all"          # 스케줄러 1w 블록은 유니버스 전체(SYMBOLS)를 돈다
PRIMARY = "late"
DECAY_D = (0, 1, 2, 3)


def _syms():
    return json.load(open("universe.json", encoding="utf-8"))["trading_universe"]


def fetch_1d(syms):
    t0, ok = time.time(), 0
    for s in syms:
        try:
            _, total = fetch_data.update_csv(f"{s}/USDT", "1d", detlib.CSV(s, "1d"), window_days=FETCH_1D_DAYS)
            ok += total > 0
        except Exception as e:
            print(f"  [fetch] {s} 1d 실패: {str(e)[:60]}")
    print(f"[fetch] 1d {FETCH_1D_DAYS}일 {ok}/{len(syms)} ({time.time()-t0:.0f}s)", flush=True)


def load_rows(syms, tf):
    out = {}
    for s in syms:
        try:
            rows = detlib.load_ohlcv(s, tf)
            if rows:
                out[s] = rows
        except Exception:
            pass
    return out


# ── arm 정의 ─────────────────────────────────────────────────────────────────
def early_setups(rows):
    """종전(룩어헤드) 판의 셋업 중 L3 미확정 돌파(brk < L3+PIVOT_HALF) — 실거래 불가 집합."""
    return [d for d in tb.detect_detail(rows, causal=False) if d["brk"] < d["L3"] + tb.PIVOT_HALF]


ARMS = {
    "late":          lambda rows: tb.detect(rows, mode="late"),
    "late_nohold":   lambda rows: tb.detect(rows, mode="late_nohold"),
    "causal":        lambda rows: tb.detect(rows, causal=True),
    "early_ceiling": lambda rows: sorted({d["brk"] for d in early_setups(rows)}),
    "union_live":    lambda rows: sorted(set(tb.detect(rows, mode="late")) | set(tb.detect(rows, causal=True))),
}


# ── 1단계: 동결 라벨 게이트 ──────────────────────────────────────────────────
def frozen_sigs(detect_fn, rows_by):
    out = []
    for sym, rows in rows_by.items():
        for si in detect_fn(rows):
            if si + 1 >= len(rows):
                continue
            _, ret = detlib.outcome(rows, si, "long")
            out.append(dict(sym=sym, date=rows[si]["date"], ret=ret))
    return out


def frozen_pool(rows_by):
    return [detlib.outcome(rows, i, "long")[1] for rows in rows_by.values() for i in range(len(rows) - LABEL_W - 1)]


def oos_quartiles(sigs):
    n = len(sigs)
    if n < 20:
        return [], 0
    dates = sorted(s["date"] for s in sigs)
    cuts = [dates[n * i // 4] for i in range(1, 4)]
    oos = []
    for q in range(4):
        lo = cuts[q - 1] if q else "0000"; hi = cuts[q] if q < 3 else "9999"
        qr = [s["ret"] for s in sigs if lo <= s["date"] < hi]
        qm = st.mean(qr) if qr else 0.0
        oos.append(dict(q=q + 1, n=len(qr), mean=qm, ok=len(qr) >= 5 and qm > 0))
    return oos, sum(1 for o in oos if o["ok"])


def gate_v2(label, sigs, pool, seed=SEED):
    """게이트 v2 (동결 5조건). boot_p 는 k=n 베이스라인(2026-09-05 수정된 정의)."""
    rets = [s["ret"] for s in sigs]
    n = len(rets)
    mean = st.mean(rets) if rets else 0.0
    med = st.median(rets) if rets else 0.0
    if n >= 2 and st.stdev(rets) > 0:
        t = mean / (st.stdev(rets) / sqrt(n)); p = _pval(t, n - 1)
    else:
        t, p = 0.0, 1.0
    boot_p, base_mean = 1.0, None
    if pool and n:
        rng = random.Random(seed)
        means = [st.mean(rng.choices(pool, k=n)) for _ in range(BOOT_N)]
        boot_p = sum(1 for m in means if m >= mean) / BOOT_N
        base_mean = st.mean(means)
    oos, oos_pos = oos_quartiles(sigs)
    fails = []
    if n < 20: fails.append("n<20")
    if mean <= 0: fails.append("mean<=0")
    if not gate.dist_ok(rets): fails.append(gate.dist_reason(rets))
    if boot_p >= 0.05: fails.append(f"boot_p={boot_p:.3f}")
    if n >= 20 and oos_pos < 2: fails.append(f"OOS {oos_pos}/4")
    by_year = {}
    for s in sigs:
        by_year.setdefault(s["date"][:4], []).append(s["ret"])
    rec = dict(label=label, n=n, mean=mean, median=med, win_rate=gate.win_rate(rets),
               trimmed_mean=gate.trimmed_mean(rets), top5_share=gate.top_share(rets),
               t=t, p=p, boot_p=boot_p, base_mean=base_mean,
               edge=(mean - base_mean) if base_mean is not None else None,
               oos=oos, oos_pos=oos_pos,
               by_year={y: dict(n=len(v), mean=st.mean(v)) for y, v in sorted(by_year.items())},
               verdict="PASSED" if not fails else "REJECTED", reason=", ".join(fails))
    print(f"  {label:<22} n={n:>4} mean={mean*100:+6.2f}% med={med*100:+6.2f}% 승률 {(rec['win_rate'] or 0)*100:3.0f}% "
          f"절사 {_f(rec['trimmed_mean'], 7)} | 기준 {_f(base_mean, 7)} boot_p={boot_p:.3f} "
          f"OOS={oos_pos}/4 -> {rec['verdict']} {rec['reason']}")
    return rec


# ── 2단계: 실거래 프레임 ──────────────────────────────────────────────────────
def live_sigs(detect_fn, rows_by, regmap):
    out = []
    for sym, rows in rows_by.items():
        lab = lambda j, rows=rows: regmap.get(rows[j]["date"])
        for si in detect_fn(rows):
            # 1w 는 MAX_HOLD(30봉)=30주라 validate_revival 식 'si < len-MAX_HOLD-1' 제외를 쓰면 holdout 365일의
            # 대부분이 빠진다. 대신 데이터 끝에서 아직 안 끝난 거래는 마지막 봉 시가로 평가(ms.outcome 의
            # end=min(si+max_hold, len-1))하고 truncated 로 표시한다 — 사전 등록 규칙.
            if si + 2 > len(rows) - 1 or si < 30:
                continue
            ret, hold, reason = ms.outcome(rows, si, "long", set(), lab, use_regime=True, max_hold=MAX_HOLD)
            vol = sz.realized_vol(rows, si, tf=TF)
            if vol is None:
                continue
            xi = min(si + hold, len(rows) - 1)
            out.append(dict(sym=sym, date=rows[si]["date"], regime=regmap.get(rows[si]["date"]),
                            ret=ret, hold=hold, reason=reason, stop_pct=STOP, vol=vol,
                            truncated=(reason == "maxhold" and si + MAX_HOLD > len(rows) - 1),
                            exit_date=rows[xi]["date"], t_in=_tnum(rows[si]), t_out=_tnum(rows[xi])))
    return out


def live_pool(rows_by, regmap, cohort_syms):
    out = []
    for sym in cohort_syms:
        rows = rows_by[sym]
        lab = lambda j, rows=rows: regmap.get(rows[j]["date"])
        for i in range(30, len(rows) - MAX_HOLD - 1):
            out.append(ms.outcome(rows, i, "long", set(), lab, use_regime=True, max_hold=MAX_HOLD)[0])
    return out


def confirm(sigs, pool, cutoff, span_train, label):
    g = gate_v2(f"{label} [실거래 D]", sigs, pool)
    reasons = {}
    for s in sigs:
        reasons[s["reason"]] = reasons.get(s["reason"], 0) + 1
    g["reasons"] = reasons
    g["hold"] = st.mean(s["hold"] for s in sigs) if sigs else 0.0
    g["truncated"] = sum(1 for s in sigs if s.get("truncated"))
    train = [s for s in sigs if s["date"] < cutoff]
    hold = [s for s in sigs if s["date"] >= cutoff]
    ho = dict(n=len(hold), mean=st.mean(s["ret"] for s in hold) if hold else None)
    c1 = g["verdict"] == "PASSED"
    c2_possible = ho["n"] >= HOLDOUT_MIN_N
    c2 = c2_possible and ho["mean"] is not None and ho["mean"] > 0
    eq = _equity(train, span_train)
    c3 = bool(eq) and eq["cagr"] > 0 and eq["calmar"] > 0
    by_reg = {}
    for s in sigs:
        by_reg.setdefault(s["regime"] or "none", []).append(s["ret"])
    return dict(gate=g, c1_live_cohort=c1, c2_holdout=c2, c2_possible=c2_possible, c3_equity=c3,
                holdout=ho, equity=eq, train_n=len(train),
                by_regime={k: dict(n=len(v), mean=st.mean(v)) for k, v in sorted(by_reg.items())})


# ── 진단 ─────────────────────────────────────────────────────────────────────
def decay_curve(rows_by):
    """미확정 셋업을 돌파봉+d 에서 진입(동결 라벨). d=0 은 실거래 불가 상한, L3+3 진입은 별도 열."""
    cols = {d: [] for d in DECAY_D}
    at_confirm, at_confirm_hold, gap, dropped_hold = [], [], {1: 0, 2: 0}, 0
    for rows in rows_by.values():
        n = len(rows)
        for d in early_setups(rows):
            brk, L3, neck = d["brk"], d["L3"], d["neck"]
            gap[brk - L3] = gap.get(brk - L3, 0) + 1
            for k in DECAY_D:
                if brk + k + 1 < n:
                    cols[k].append(detlib.outcome(rows, brk + k, "long")[1])
            e = L3 + tb.PIVOT_HALF
            if e + 1 < n:
                r = detlib.outcome(rows, e, "long")[1]
                at_confirm.append(r)
                if rows[e]["c"] > neck:
                    at_confirm_hold.append(r)
                else:
                    dropped_hold += 1
    f = lambda v: dict(n=len(v), mean=st.mean(v) if v else None, median=st.median(v) if v else None,
                       win=gate.win_rate(v) if v else None)
    return dict(by_delay={f"brk+{k}": f(v) for k, v in cols.items()},
                at_L3p3=f(at_confirm), at_L3p3_hold=f(at_confirm_hold),
                dropped_by_hold=dropped_hold, brk_minus_L3=gap)


def _f(v, w=8):
    return f"{'n/a':>{w}}" if v is None else f"{v*100:>+{w-1}.2f}%"


def decide(s1_rec, cf):
    """사전 등록 최종 판정. s1_rec: 1단계 gate_v2 결과(주 arm), cf: 2단계 confirm(주 arm, 실거래 코호트)."""
    s1 = s1_rec["verdict"] == "PASSED"
    if s1 and cf["c1_live_cohort"] and cf["c2_holdout"] and cf["c3_equity"]:
        verdict = "PASSED"
    elif s1 and not cf["c2_possible"]:
        verdict = "INCONCLUSIVE"
    else:
        verdict = "REJECTED"
    why = []
    if not s1: why.append(f"1단계 {s1_rec['reason']}")
    if not cf["c1_live_cohort"]: why.append(f"C1 {cf['gate']['reason']}")
    if not cf["c2_possible"]: why.append(f"C2 holdout n={cf['holdout']['n']}<{HOLDOUT_MIN_N}")
    elif not cf["c2_holdout"]: why.append(f"C2 holdout mean={_f(cf['holdout']['mean']).strip()}")
    if not cf["c3_equity"]: why.append("C3 자산곡선")
    return verdict, why


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    syms = _syms()
    print(f"지각 진입 사전 등록 시험 | triple_bottom @{TF} | 유니버스 {len(syms)} | 주 판정 arm = {PRIMARY} | 시드 {SEED}")
    if "--no-fetch" not in argv:
        fetch_1d(syms)
    rows_1d = load_rows(syms, "1d")
    rows_by = load_rows(syms, TF)
    regmap = rs.build_regime_map()
    ranked = turnover_rank(rows_1d)
    cohorts = {"all": sorted(rows_by), "top30": [s for s in ranked[:30] if s in rows_by]}
    all_dates = sorted({r["date"] for rows in rows_1d.values() for r in rows})
    first, last = all_dates[0], all_dates[-1]
    cutoff = date.fromordinal(date.fromisoformat(last).toordinal() - HOLDOUT_DAYS).isoformat()
    span_train = max(1, date.fromisoformat(cutoff).toordinal() - date.fromisoformat(first).toordinal())
    print(f"[데이터] 1w 종목 {len(rows_by)} | {first}~{last} | holdout >= {cutoff} | train {span_train}일")

    # 1단계
    print("\n[1단계] 동결 라벨 ±10%/20봉 · 게이트 v2 · 베이스라인 k=n (같은 1w 무작위 진입)")
    pool1 = frozen_pool(rows_by)
    stage1 = {}
    for name, fn in ARMS.items():
        stage1[name] = gate_v2(name, frozen_sigs(fn, rows_by), pool1)
    # 진단
    dec = decay_curve(rows_by)
    print("\n[진단] 미확정 셋업의 지각 비용 (동결 라벨)")
    for k, v in dec["by_delay"].items():
        print(f"  {k:<8} n={v['n']:>3} mean={_f(v['mean'])} med={_f(v['median'])} 승률 {(v['win'] or 0)*100:3.0f}%")
    v = dec["at_L3p3"]; print(f"  L3+3     n={v['n']:>3} mean={_f(v['mean'])} med={_f(v['median'])} (종가 조건 없음)")
    v = dec["at_L3p3_hold"]; print(f"  L3+3&유지 n={v['n']:>3} mean={_f(v['mean'])} med={_f(v['median'])} | 종가 조건 탈락 {dec['dropped_by_hold']} | brk−L3 {dec['brk_minus_L3']}")

    # 2단계 (주 arm + 참고 arm 전부 계산, 판정은 주 arm)
    print(f"\n[2단계] 실거래 프레임 — 방식D(−8% 손절/레짐 전환/{MAX_HOLD}봉) · 코호트 {LIVE_COHORT} · 실거래 사이징 자산곡선")
    pools2 = {c: live_pool(rows_by, regmap, cohorts[c]) for c in cohorts}
    stage2 = {}
    for name in ("late", "late_nohold", "causal", "union_live"):
        sigs = live_sigs(ARMS[name], rows_by, regmap)
        per = {}
        for c in cohorts:
            cs = set(cohorts[c])
            per[c] = confirm([s for s in sigs if s["sym"] in cs], pools2[c], cutoff, span_train, f"{name}:{c}")
            cf = per[c]; eq = cf["equity"] or {}
            print(f"    -> C1 {cf['c1_live_cohort']} | C2 holdout n={cf['holdout']['n']} mean={_f(cf['holdout']['mean'])} "
                  f"{'판정불가' if not cf['c2_possible'] else cf['c2_holdout']} | C3 CAGR {_f(eq.get('cagr'))} MDD {_f(eq.get('mdd'))} "
                  f"Calmar {eq.get('calmar', 0) or 0:.2f} {cf['c3_equity']} | 청산 {cf['gate']['reasons']} 레짐 "
                  + " ".join(f"{k}:{v['mean']*100:+.1f}%(n{v['n']})" for k, v in cf["by_regime"].items()))
        stage2[name] = per

    # 최종 판정 (사전 등록 규칙, 주 arm 만)
    cf = stage2[PRIMARY][LIVE_COHORT]
    verdict, why = decide(stage1[PRIMARY], cf)
    print("\n" + "=" * 90)
    print(f"[판정] triple_bottom_1w 지각 진입({PRIMARY}) → {verdict} {'; '.join(why)}")
    out = dict(test="late_entry_triple_bottom_1w", primary=PRIMARY, verdict=verdict, reasons=why,
               data=dict(first=first, last=last, cutoff=cutoff, span_train=span_train, n_syms=len(rows_by)),
               stage1=stage1, decay=dec, stage2=stage2)
    json.dump(out, open("_late_entry.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print("[저장] _late_entry.json")
    print("RESULT_JSON: " + json.dumps(dict(verdict=verdict, reasons=why,
                                            stage1={k: (v["verdict"], v["n"], round(v["mean"] * 100, 2), round(v["boot_p"], 3)) for k, v in stage1.items()},
                                            holdout=cf["holdout"]), ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
