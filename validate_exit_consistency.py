"""
validate_exit_consistency.py — 배포 패턴의 **진입 검증 프레임 vs 실거래 청산(방식D)** 일치 점검 (2026-09-06, 사용자 질문
"1h 빼고 전부 청산이 D 인데 이것도 전부 진입 규칙에 맞게 검증해야 하지 않나").

현황
  exit_spec(ATR 배리어) 가 없는 배포 패턴은 전부 방식D(−8% 저가 손절 / 레짐 전환 / 30봉 시가)로 실거래 청산한다.
  그 중 방식D 로 실거래 프레임 확인을 거친 것은
    · engulfing / fvg (1d)                          — method_d (A vs D Calmar 게이트, 2026-07)
    · triple_bottom_4h / equal_lows_4h / vol_awakening_4h — validate_revival C1~C3 가 방식D 청산 (2026-09-05)
  거치지 않은 것(±10%/20봉 동결 라벨로만 통과, D 로 실거래 중):
    · inverted_hammer (1d, 메이저 7) · marubozu (1d, 메이저 7) · three_soldiers_4h (4h, 전체, bull 레짐만)
  triple_bottom 1w 에서 같은 불일치가 승률 67%→20% 를 만들었다(validate_late_entry / validate_exit_1w).

시험(사전 등록)
  셀 = 배포 패턴 × 실거래 범위(코호트·레짐 게이팅 그대로) × 청산 arm
    D        현행 실거래(method_s.outcome = paper_executor.eval_D, 반대신호 없음)
    A_label  진입 검증 라벨과 같은 청산: 종가 ≥+10% 익절 / 종가 ≤−10% 손절 / 20봉 만기 종가 + 거래소 재해용 손절 −20%(저가)
    A_nocat  [진단] 재해 손절 없는 순수 라벨(= detlib.outcome) — 재해 손절의 비용을 분리
  각 (셀, arm) 을 실거래 프레임으로 판정: C1 같은 청산 규칙·같은 코호트·같은 레짐 조건 무작위 진입 k=n 베이스라인(1000회,
  시드 42) 게이트 v2 / C2 holdout 마지막 365일 n>=10 & mean>0 / C3 train 자산곡선(실거래 사이징) CAGR>0 & Calmar>0.
  OK = C1 ∧ C2 ∧ C3.  짝지음(A_label − D, 같은 신호)도 함께.

판정 규칙(사전 등록 — 사후 변경 금지). 패턴별로:
  D_OK                         → 현행 유지(A 가 더 좋아도 바꾸지 않는다 — 검증된 규칙을 더 검증된 규칙으로만 바꾼다는 뜻이 아니라,
                                  실거래 규칙 변경은 불일치가 확인된 곳에만 한다)
  ¬D_OK ∧ A_OK ∧ 짝지음 A−D>0, t>2 → **청산 전환 후보(A_label)** — 사용자 결정(실거래 청산 변경은 자율 반영 예외)
  ¬D_OK ∧ ¬A_OK                → **패턴 재판정 후보** — 청산을 바꿔도 못 살리므로 정지 검토, 사용자 결정
  D_OK 가 아닌데 A_OK 이지만 짝지음 열세  → 관찰(보고만)
  참고 3종(revival D 확인분)은 표만 출력, 판정 대상 아님. **실거래 변경 없음.**

출력: _exit_consistency.json + RESULT_JSON.  실행: python validate_exit_consistency.py [--no-fetch]
"""
import importlib
import json
import random
import statistics as st
import sys
import time
from datetime import date

import detlib
import method_s as ms
import regime_switch as rs
import sizing as sz
import validate_regime_split_all as va
from validate_regime_split import turnover_rank
from validate_revival import _tnum, equity as _equity, HOLDOUT_MIN_N
from validate_late_entry import gate_v2, _f
from validate_exit_1w import outcome_close_rule, HOLD_A, CAT_STOP, STOP_CLOSE

SEED, BOOT_N, POOL_CAP = 42, 1000, 20000
HOLD_D, STOP_D = ms.MAX_HOLD, ms.STOP
HOLDOUT_DAYS = 365
FETCH_TFS = ("1d", "4h")
BULL = ("bull_btc", "bull_altseason")
# (cid, tf, module, cohort, regimes(None=전부), judged)
CELLS = [
    ("inverted_hammer",  "1d", "detector_inverted_hammer",  "majors", None, True),
    ("marubozu",         "1d", "detector_marubozu",         "majors", None, True),
    ("three_soldiers_4h", "4h", "detector_three_soldiers_4h", "all",   BULL, True),
    ("triple_bottom_4h", "4h", "detector_triple_bottom",    "top30",  None, False),
    ("equal_lows_4h",    "4h", "detector_equal_lows_4h",    "top30",  None, False),
    ("vol_awakening_4h", "4h", "detector_vol_awakening_4h", "top30",  None, False),
]
ARMS = ("D", "A_label", "A_nocat")
MAJORS = list(detlib.SYMBOLS)


def outcome_arm(arm, rows, si, lab):
    """(ret, hold, reason, stop_pct). 롱 전용(배포 셀 전부 롱)."""
    if arm == "D":
        r, h, why = ms.outcome(rows, si, "long", set(), lab, use_regime=True, max_hold=HOLD_D)
        return r, h, why, STOP_D
    if arm == "A_label":
        r, h, why, _ = outcome_close_rule(rows, si)
        return r, h, why, STOP_CLOSE
    if arm == "A_nocat":
        r, h, why, _ = outcome_close_rule(rows, si, cat=None)
        return r, h, why, STOP_CLOSE
    raise ValueError(arm)


def tail_for(arm):
    return HOLD_D if arm == "D" else HOLD_A


def cohort_syms(rule, rows_by, ranked):
    if rule == "majors":
        return [s for s in MAJORS if s in rows_by]
    if rule == "top30":
        return [s for s in ranked[:30] if s in rows_by]
    return sorted(rows_by)


def collect(detect_fn, arm, syms, rows_by, regmap, regimes, tf="1d"):
    out = []
    tail = tail_for(arm)
    for sym in syms:
        rows = rows_by[sym]
        lab = lambda j, rows=rows: regmap.get(rows[j]["date"])
        try:
            idxs = detect_fn(rows)
        except Exception as e:
            print(f"  [detect] {sym} 오류: {str(e)[:60]}"); idxs = []
        for si in idxs:
            if si + 1 >= len(rows) or si >= len(rows) - tail - 1 or si < 30:
                continue
            reg = regmap.get(rows[si]["date"])
            if regimes is not None and reg not in regimes:
                continue
            vol = sz.realized_vol(rows, si, tf=tf)
            if vol is None:
                continue
            ret, hold, reason, stop_pct = outcome_arm(arm, rows, si, lab)
            xi = min(si + hold, len(rows) - 1)
            out.append(dict(sym=sym, date=rows[si]["date"], regime=reg, ret=ret, hold=hold, reason=reason,
                            stop_pct=stop_pct, vol=vol, exit_date=rows[xi]["date"],
                            t_in=_tnum(rows[si]), t_out=_tnum(rows[xi]), key=(sym, si)))
    return out


def pool(arm, syms, rows_by, regmap, regimes, seed=SEED):
    tail = tail_for(arm)
    idx = [(s, i) for s in syms for rows in [rows_by[s]] for i in range(30, len(rows) - tail - 1)
           if regimes is None or regmap.get(rows[i]["date"]) in regimes]
    rng = random.Random(seed)
    if len(idx) > POOL_CAP:
        idx = rng.sample(idx, POOL_CAP)
    out = []
    for s, i in idx:
        rows = rows_by[s]
        lab = lambda j, rows=rows: regmap.get(rows[j]["date"])
        out.append(outcome_arm(arm, rows, i, lab)[0])
    return out


def confirm(sigs, pool_rets, cutoff, span_train, label):
    g = gate_v2(label, sigs, pool_rets)
    reasons = {}
    for s in sigs:
        reasons[s["reason"]] = reasons.get(s["reason"], 0) + 1
    g["reasons"] = reasons
    g["hold_bars"] = st.mean(s["hold"] for s in sigs) if sigs else 0.0
    train = [s for s in sigs if s["date"] < cutoff]
    hold = [s for s in sigs if s["date"] >= cutoff]
    ho = dict(n=len(hold), mean=st.mean(s["ret"] for s in hold) if hold else None)
    c1 = g["verdict"] == "PASSED"
    c2 = ho["n"] >= HOLDOUT_MIN_N and ho["mean"] is not None and ho["mean"] > 0
    eq = _equity(train, span_train)
    c3 = bool(eq) and eq["cagr"] > 0 and eq["calmar"] > 0
    return dict(gate=g, c1=c1, c2=c2, c3=c3, ok=bool(c1 and c2 and c3), holdout=ho, equity=eq, train_n=len(train))


def paired(a_sigs, d_sigs):
    d = {s["key"]: s["ret"] for s in d_sigs}
    diffs = [s["ret"] - d[s["key"]] for s in a_sigs if s["key"] in d]
    if not diffs:
        return dict(n=0, mean_diff=0.0, t=0.0, win_share=0.0)
    m = st.mean(diffs)
    sd = st.pstdev(diffs) if len(diffs) > 1 else 0.0
    return dict(n=len(diffs), mean_diff=m, t=(m / (sd / len(diffs) ** 0.5) if sd > 0 else 0.0),
                win_share=sum(1 for x in diffs if x > 0) / len(diffs))


def judge(d_ok, a_ok, pv):
    """사전 등록 판정 규칙."""
    if d_ok:
        return "KEEP_D"
    if a_ok and pv["mean_diff"] > 0 and pv["t"] > 2:
        return "SWITCH_CANDIDATE_A_label"
    if a_ok:
        return "OBSERVE"
    return "PATTERN_REJUDGE_CANDIDATE"


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    syms = va._syms()
    print(f"청산 일치 점검 | 배포 패턴 {sum(1 for c in CELLS if c[5])} 판정 + 참고 {sum(1 for c in CELLS if not c[5])} | arm {ARMS} | 시드 {SEED}")
    if "--no-fetch" not in argv:
        va.fetch(syms, list(FETCH_TFS))
    regmap = rs.build_regime_map()
    rows_1d = va.load_tf(syms, "1d")
    ranked = turnover_rank(rows_1d)
    rows_tf = {"1d": rows_1d, "4h": va.load_tf(syms, "4h")}
    results = {}
    for cid, tf, mod, cohort, regimes, judged in CELLS:
        rows_by = rows_tf[tf]
        cs = cohort_syms(cohort, rows_by, ranked)
        detect_fn = importlib.import_module(mod).detect
        dates = sorted({r["date"] for s in cs for r in rows_by[s]})
        first, last = dates[0], dates[-1]
        cutoff = date.fromordinal(date.fromisoformat(last).toordinal() - HOLDOUT_DAYS).isoformat()
        span_train = max(1, date.fromisoformat(cutoff).toordinal() - date.fromisoformat(first).toordinal())
        print(f"\n[{cid} @{tf} | 코호트 {cohort}({len(cs)}) | 레짐 {regimes or '전부'} | {first}~{last} | holdout>={cutoff}]"
              + ("" if judged else "  (참고 — 판정 대상 아님)"))
        sig_by = {}
        cf_by = {}
        for arm in ARMS:
            t0 = time.time()
            pr = pool(arm, cs, rows_by, regmap, regimes)
            sig_by[arm] = collect(detect_fn, arm, cs, rows_by, regmap, regimes, tf=tf)
            cf = confirm(sig_by[arm], pr, cutoff, span_train, f"{cid}/{arm}")
            eq = cf["equity"] or {}
            print(f"    -> OK={cf['ok']} C1 {cf['c1']} | C2 holdout n={cf['holdout']['n']} mean={_f(cf['holdout']['mean'])} {cf['c2']} "
                  f"| C3 CAGR {_f(eq.get('cagr'))} MDD {_f(eq.get('mdd'))} Calmar {min(eq.get('calmar', 0) or 0, 999):.2f} {cf['c3']} "
                  f"| 보유 {cf['gate']['hold_bars']:.1f}봉 | 청산 {cf['gate']['reasons']} | 풀 {len(pr)} ({time.time()-t0:.0f}s)", flush=True)
            cf_by[arm] = cf
        pv = paired(sig_by["A_label"], sig_by["D"])
        pv_nc = paired(sig_by["A_nocat"], sig_by["D"])
        verdict = judge(cf_by["D"]["ok"], cf_by["A_label"]["ok"], pv) if judged else "REFERENCE"
        print(f"  짝지음 A_label−D: n={pv['n']} {pv['mean_diff']*100:+.2f}%p t={pv['t']:.2f} 우위 {pv['win_share']*100:.0f}% "
              f"| A_nocat−D {pv_nc['mean_diff']*100:+.2f}%p t={pv_nc['t']:.2f}  => {verdict}")
        results[cid] = dict(tf=tf, cohort=cohort, regimes=regimes, judged=judged, arms=cf_by,
                            paired_A_vs_D=pv, paired_Anocat_vs_D=pv_nc, verdict=verdict)
    print("\n" + "=" * 100)
    for cid, r in results.items():
        d, a = r["arms"]["D"]["gate"], r["arms"]["A_label"]["gate"]
        print(f"  {cid:<18} D: n={d['n']:>4} {_f(d['mean'])} 승률 {(d['win_rate'] or 0)*100:3.0f}% bp {d['boot_p']:.3f} OK={r['arms']['D']['ok']!s:<5} "
              f"| A_label: {_f(a['mean'])} 승률 {(a['win_rate'] or 0)*100:3.0f}% bp {a['boot_p']:.3f} OK={r['arms']['A_label']['ok']!s:<5} "
              f"| A−D {r['paired_A_vs_D']['mean_diff']*100:+.2f}%p t={r['paired_A_vs_D']['t']:.2f} → {r['verdict']}")
    json.dump(dict(results=results, cells=[c[:5] for c in CELLS]), open("_exit_consistency.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1, default=str)
    print("[저장] _exit_consistency.json")
    print("RESULT_JSON: " + json.dumps({cid: dict(verdict=r["verdict"], D_ok=r["arms"]["D"]["ok"], A_ok=r["arms"]["A_label"]["ok"],
                                                 D=(r["arms"]["D"]["gate"]["n"], round(r["arms"]["D"]["gate"]["mean"] * 100, 2), round(r["arms"]["D"]["gate"]["boot_p"], 3)),
                                                 A=(r["arms"]["A_label"]["gate"]["n"], round(r["arms"]["A_label"]["gate"]["mean"] * 100, 2), round(r["arms"]["A_label"]["gate"]["boot_p"], 3)),
                                                 paired=round(r["paired_A_vs_D"]["mean_diff"] * 100, 2), t=round(r["paired_A_vs_D"]["t"], 2))
                                        for cid, r in results.items()}, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
