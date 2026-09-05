"""
validate_exit_1w.py — triple_bottom 1w **전용 청산 규칙** 사전 등록 시험 (2026-09-06, 사용자 지시 "돌려줘").

배경
  validate_late_entry(run 33966797748): 지각 진입(L3+3) 30건은 동결 라벨(종가 ±10%/20주)에서 +12.42%·승률 67%로
  통과했지만, 방식D(주봉 **저가** −8% 손절/레짐 전환/30봉)에서는 23/30 이 손절돼 승률 20%·중앙값 −8.20%.
  라벨 기준 승자 20건 중 최소 14건이 D 에서 손절로 끝났다 — 오를 거래를 주봉 흔들림에서 털린 것.
  방식D 는 1d engulfing/fvg 에서 검증된 규칙이고 1w 에서는 검증된 적이 없다(CLAUDE.md 보류 항목).
  원칙: **검증 프레임과 실거래 규칙이 다르면 실거래를 검증에 맞춘다.**

가설(사전 등록)
  1w 진입에 검증 라벨과 같은 청산(종가 기준 ±10%, 20주)을 쓰면 실거래 프레임(베이스라인·holdout·자산곡선)에서도
  통과한다. 즉 문제는 진입이 아니라 청산 규칙이다.

진입 집합
  late    [주 판정]  detector_triple_bottom.detect(mode="late")   — 미확정 돌파 셋업, 신호 L3+3, 종가>넥라인
  causal  [부 판정]  detect(causal=True)                          — 확정 후 돌파(9/3 정지 집합). 결과는 보고만.

청산 arm (전부 인과, 봉 종가 판정. 실거래 원칙 '손절 주문 없으면 실거래 없음' 을 위해 종가 규칙 arm 은
거래소 재해용 손절 −20%(봉 저가) 를 항상 동반한다 — 그것이 먼저 걸린 횟수를 진단으로 센다)
  A_label   [주 판정]  종가 ≥ +10% 익절 / 종가 ≤ −10% 손절 / 20주 만기 종가 청산 / 재해 −20%.  = paper_executor.eval_A
                       + 재해 손절. 사이징 stop_pct=0.10.
  A_notarget [진단]    A_label 에서 +10% 익절만 제거(상방 열어둠).
  S_base    [진단]     종가 < 세 바닥 최저가(base_low) 면 청산(패턴 무효화). 익절 없음, 20주, 재해 −20%.
                       stop_pct = min(0.20, (진입−base_low)/진입).
  N_neck    [진단]     종가 < 넥라인이면 청산(돌파 실패). 익절 없음, 20주, 재해 −20%. stop_pct = max(거리, 0.05).
  D_close   [진단]     방식D 의 −8% 손절을 저가 대신 **종가**로 판정. 레짐 전환·30봉 시가 청산은 D 그대로.
  D         [참고]     현행 방식D(method_s.outcome) — 지각 진입 시험의 2단계 수치 재현.

판정 기준(사전 등록 — 사후 변경 금지). 주 판정 셀 = (late, A_label)
  C1  실거래 코호트 all(1w 스케줄러 범위) · 같은 청산 규칙의 무작위 1w 진입 k=n 베이스라인(1000회, 시드 42) · 게이트 v2 PASSED
  C2  holdout = 마지막 **730일**(주봉은 5년에 약 30건이라 365일이면 1건 — 사전에 2년으로 정한다) n>=10 이고 mean>0.
      n<10 → INCONCLUSIVE(반영 불가·기각 아님)
  C3  train 자산곡선(실거래 사이징 risk 1.5%/lev3/vol targeting/MAX_POS 16, method_x.equity_curve) CAGR>0 이고 Calmar>0
  최종: C1 ∧ C2 ∧ C3 → PASSED. C1·C3 통과·C2 표본 부족 → INCONCLUSIVE. 그 외 REJECTED.
  (1단계 동결 라벨 게이트는 late 가 run 33966797748 에서 PASSED — 재확인만 출력)
  **PASSED 여도 자율 반영하지 않는다** — 실거래 청산 규칙(eval_D → 별도 경로) 변경은 사용자 보고 후 적용
  (2026-09-05 자율 반영 권한의 예외로 미리 정해둔 항목). (causal, A_label) 이 통과하면 별도 후보로 보고.

진단(판정 무관)
  · 짝지음: 같은 신호에서 각 arm − D 의 건당 차이·우위 비율(가격 경로가 같아 검정력이 큼)
  · 재해 손절 선행 횟수, 청산 사유 분포, 평균 보유(주), 연간 슬롯·주 점유(20주 보유의 자리값)
  · 레짐별·연도별 분해
출력: _exit_1w.json + RESULT_JSON.  실행: python validate_exit_1w.py [--no-fetch]
"""
import json
import random
import statistics as st
import sys
import time
from datetime import date

import detlib
import gate
import method_s as ms
import regime_switch as rs
import sizing as sz
import detector_triple_bottom as tb
from validate_regime_split import turnover_rank
from validate_revival import _tnum, equity as _equity
from validate_late_entry import fetch_1d, load_rows, gate_v2, _f, HOLDOUT_MIN_N

SEED, BOOT_N = 42, 1000
TF = "1w"
FEE = detlib.FEE
HOLD_A = 20                 # 검증 라벨·eval_A 와 동일
HOLD_D = ms.MAX_HOLD        # 30
TARGET, STOP_CLOSE, CAT_STOP = 0.10, 0.10, 0.20
STOP_D = ms.STOP            # 0.08
HOLDOUT_DAYS = 730
LIVE_COHORT = "all"
PRIMARY_ENTRY, PRIMARY_EXIT = "late", "A_label"
ENTRIES = ("late", "causal")
EXITS = ("A_label", "A_notarget", "S_base", "N_neck", "D_close", "D")
POOL_OF = {"A_label": "A_label", "A_notarget": "A_notarget", "S_base": "A_notarget", "N_neck": "A_notarget",
           "D_close": "D_close", "D": "D"}       # 패턴 문맥이 필요한 arm 은 가장 가까운 무패턴 규칙의 풀


def _syms():
    return json.load(open("universe.json", encoding="utf-8"))["trading_universe"]


# ── 청산 규칙 ─────────────────────────────────────────────────────────────────
def outcome_close_rule(rows, si, max_hold=HOLD_A, target=TARGET, stop_close=STOP_CLOSE, cat=CAT_STOP,
                       struct_px=None, neck_px=None):
    """
    종가 판정 청산(롱). 반환 (ret, hold, reason, truncated).
    우선순위(같은 봉): 재해 손절(저가) → 익절(종가) → 종가 손절 → 구조/넥라인(종가). 만기는 마지막 봉 종가.
    target/stop_close/struct_px/neck_px 가 None 이면 그 규칙 없음. cat=None 이면 재해 손절 없음(= detlib.outcome 동치).
    """
    base = rows[si]["c"]
    n = len(rows)
    end = min(si + max_hold, n - 1)
    for j in range(si + 1, end + 1):
        if cat is not None and rows[j]["l"] <= base * (1 - cat):
            return -cat - FEE, j - si, "cat_stop", False
        c = rows[j]["c"]
        if target is not None and c >= base * (1 + target):
            return c / base - 1 - FEE, j - si, "tp", False
        if stop_close is not None and c <= base * (1 - stop_close):
            return c / base - 1 - FEE, j - si, "sl_close", False
        if struct_px is not None and c < struct_px:
            return c / base - 1 - FEE, j - si, "struct", False
        if neck_px is not None and c < neck_px:
            return c / base - 1 - FEE, j - si, "neck", False
    c = rows[end]["c"]
    return c / base - 1 - FEE, end - si, "timestop", end < si + max_hold


def outcome_d_close(rows, si, lab, max_hold=HOLD_D, stop=STOP_D):
    """방식D 에서 손절 판정만 저가 → 종가. 레짐 전환 청산·만기 시가 청산은 method_s.outcome 과 동일."""
    base = rows[si]["c"]
    entry_reg = lab(si)
    n = len(rows)
    end = min(si + max_hold, n - 1)
    for j in range(si + 1, end + 1):
        c = rows[j]["c"]
        if c <= base * (1 - stop):
            return c / base - 1 - FEE, j - si, "sl_close", False
        if lab(j) not in (None, entry_reg):
            return c / base - 1 - FEE, j - si, "regime_switch", False
    px = rows[end]["o"]
    return px / base - 1 - FEE, end - si, "maxhold", end < si + max_hold


def outcome_arm(arm, rows, si, lab, det=None):
    """(ret, hold, reason, stop_pct, truncated). det: detect_detail 항목(S_base/N_neck 에 필요)."""
    base = rows[si]["c"]
    if arm == "A_label":
        r, h, why, tr = outcome_close_rule(rows, si)
        return r, h, why, STOP_CLOSE, tr
    if arm == "A_notarget":
        r, h, why, tr = outcome_close_rule(rows, si, target=None)
        return r, h, why, STOP_CLOSE, tr
    if arm == "S_base":
        lo = min(rw["l"] for rw in rows[det["L1"]:det["L3"] + 1])
        r, h, why, tr = outcome_close_rule(rows, si, target=None, stop_close=None, struct_px=lo)
        return r, h, why, min(CAT_STOP, max(0.0, (base - lo) / base)), tr
    if arm == "N_neck":
        r, h, why, tr = outcome_close_rule(rows, si, target=None, stop_close=None, neck_px=det["neck"])
        return r, h, why, max((base - det["neck"]) / base, 0.05), tr
    if arm == "D_close":
        r, h, why, tr = outcome_d_close(rows, si, lab)
        return r, h, why, STOP_D, tr
    if arm == "D":
        r, h, why = ms.outcome(rows, si, "long", set(), lab, use_regime=True, max_hold=HOLD_D)
        return r, h, why, STOP_D, (why == "maxhold" and si + HOLD_D > len(rows) - 1)
    raise ValueError(arm)


def entry_details(entry, rows):
    if entry == "late":
        return tb.detect_detail(rows, mode="late")
    if entry == "causal":
        return tb.detect_detail(rows, causal=True)
    raise ValueError(entry)


# ── 수집 ──────────────────────────────────────────────────────────────────────
def collect(entry, arm, rows_by, regmap):
    out = []
    for sym, rows in rows_by.items():
        lab = lambda j, rows=rows: regmap.get(rows[j]["date"])
        for det in entry_details(entry, rows):
            si = det["sig"]
            if si + 2 > len(rows) - 1 or si < 30:
                continue
            vol = sz.realized_vol(rows, si, tf=TF)
            if vol is None:
                continue
            ret, hold, reason, stop_pct, tr = outcome_arm(arm, rows, si, lab, det)
            xi = min(si + hold, len(rows) - 1)
            out.append(dict(sym=sym, date=rows[si]["date"], regime=regmap.get(rows[si]["date"]), ret=ret, hold=hold,
                            reason=reason, stop_pct=stop_pct, vol=vol, truncated=tr, exit_date=rows[xi]["date"],
                            t_in=_tnum(rows[si]), t_out=_tnum(rows[xi]), key=(sym, si)))
    return out


def pool(arm, rows_by, regmap, syms):
    out = []
    for sym in syms:
        rows = rows_by[sym]
        lab = lambda j, rows=rows: regmap.get(rows[j]["date"])
        for i in range(30, len(rows) - 2):
            out.append(outcome_arm(arm, rows, i, lab)[0])
    return out


def confirm(sigs, pool_rets, cutoff, span_train, label):
    g = gate_v2(f"{label}", sigs, pool_rets)
    reasons = {}
    for s in sigs:
        reasons[s["reason"]] = reasons.get(s["reason"], 0) + 1
    g["reasons"] = reasons
    g["hold_bars"] = st.mean(s["hold"] for s in sigs) if sigs else 0.0
    g["truncated"] = sum(1 for s in sigs if s["truncated"])
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
    slot_weeks_per_year = (sum(s["hold"] for s in train) / max(1, span_train) * 365) if train else 0.0
    return dict(gate=g, c1=c1, c2=c2, c2_possible=c2_possible, c3=c3, holdout=ho, equity=eq, train_n=len(train),
                slot_weeks_per_year=slot_weeks_per_year,
                by_regime={k: dict(n=len(v), mean=st.mean(v)) for k, v in sorted(by_reg.items())})


def decide(cf):
    if cf["c1"] and cf["c2"] and cf["c3"]:
        v = "PASSED"
    elif cf["c1"] and cf["c3"] and not cf["c2_possible"]:
        v = "INCONCLUSIVE"
    else:
        v = "REJECTED"
    why = []
    if not cf["c1"]: why.append(f"C1 {cf['gate']['reason']}")
    if not cf["c2_possible"]: why.append(f"C2 holdout n={cf['holdout']['n']}<{HOLDOUT_MIN_N}")
    elif not cf["c2"]: why.append(f"C2 holdout mean={_f(cf['holdout']['mean']).strip()}")
    if not cf["c3"]: why.append("C3 자산곡선")
    return v, why


def paired(a_sigs, d_sigs):
    """같은 (sym, si) 신호에서 arm − D."""
    d = {s["key"]: s["ret"] for s in d_sigs}
    diffs = [s["ret"] - d[s["key"]] for s in a_sigs if s["key"] in d]
    if not diffs:
        return dict(n=0)
    m = st.mean(diffs)
    sd = st.pstdev(diffs) if len(diffs) > 1 else 0.0
    t = m / (sd / len(diffs) ** 0.5) if sd > 0 else 0.0
    return dict(n=len(diffs), mean_diff=m, t=t, win_share=sum(1 for x in diffs if x > 0) / len(diffs),
                tie_share=sum(1 for x in diffs if abs(x) < 1e-12) / len(diffs))


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    syms = _syms()
    print(f"1w 전용 청산 사전 등록 시험 | triple_bottom @{TF} | 유니버스 {len(syms)} | 주 판정 ({PRIMARY_ENTRY}, {PRIMARY_EXIT}) | 시드 {SEED}")
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
    print(f"[데이터] 1w 종목 {len(rows_by)} | {first}~{last} | holdout >= {cutoff} ({HOLDOUT_DAYS}일) | train {span_train}일")

    # 1단계 재확인(동결 라벨 = A_label 에서 재해 손절 없음)
    print("\n[1단계 재확인] 동결 라벨 ±10%/20봉 (validate_late_entry 와 동일 정의)")
    lab_pool = [detlib.outcome(rows, i, "long")[1] for rows in rows_by.values() for i in range(len(rows) - detlib.LABEL_WINDOW - 1)]
    stage1 = {}
    for e in ENTRIES:
        sigs = [dict(sym=s, date=rows_by[s][d["sig"]]["date"], ret=detlib.outcome(rows_by[s], d["sig"], "long")[1])
                for s in rows_by for d in entry_details(e, rows_by[s]) if d["sig"] + 1 < len(rows_by[s])]
        stage1[e] = gate_v2(f"label:{e}", sigs, lab_pool)

    # 베이스라인 풀(청산 arm 별)
    print("\n[풀] 같은 청산 규칙의 무작위 1w 진입 (코호트 all)")
    pools = {}
    for arm in sorted(set(POOL_OF.values())):
        t0 = time.time()
        pools[arm] = pool(arm, rows_by, regmap, cohorts[LIVE_COHORT])
        print(f"  {arm:<11} n={len(pools[arm])} mean={_f(st.mean(pools[arm]))} ({time.time()-t0:.0f}s)", flush=True)

    # 2단계
    results = {}
    for e in ENTRIES:
        print(f"\n[2단계] 진입 {e} · 코호트 {LIVE_COHORT} · 청산 arm 6종")
        sig_by_arm = {arm: collect(e, arm, rows_by, regmap) for arm in EXITS}
        results[e] = {}
        for arm in EXITS:
            cf = confirm(sig_by_arm[arm], pools[POOL_OF[arm]], cutoff, span_train, f"{e}/{arm}")
            cf["paired_vs_D"] = paired(sig_by_arm[arm], sig_by_arm["D"]) if arm != "D" else None
            eq = cf["equity"] or {}
            pv = cf["paired_vs_D"]
            print(f"    -> C1 {cf['c1']} | C2 holdout n={cf['holdout']['n']} mean={_f(cf['holdout']['mean'])} "
                  f"{'판정불가' if not cf['c2_possible'] else cf['c2']} | C3 CAGR {_f(eq.get('cagr'))} MDD {_f(eq.get('mdd'))} "
                  f"Calmar {eq.get('calmar', 0) or 0:.2f} {cf['c3']} | 보유 {cf['gate']['hold_bars']:.1f}주 슬롯 {cf['slot_weeks_per_year']:.0f}주/년 "
                  f"| 청산 {cf['gate']['reasons']} truncated {cf['gate']['truncated']}"
                  + (f" | vs D {pv['mean_diff']*100:+.2f}%p t={pv['t']:.2f} 우위 {pv['win_share']*100:.0f}%" if pv and pv.get("n") else ""))
            g = cf["gate"]
            yr = " ".join(f"{y}:{v['mean']*100:+.1f}%(n{v['n']})" for y, v in g["by_year"].items())
            oo = " ".join(f"Q{o['q']}:{o['mean']*100:+.1f}%(n{o['n']})" for o in g["oos"])
            rg = " ".join(f"{k}:{v['mean']*100:+.1f}%(n{v['n']})" for k, v in cf["by_regime"].items())
            print(f"       연도별 {yr} | OOS {oo} | 레짐 {rg}")
            results[e][arm] = cf
    # top30 참고(주 셀만)
    top = set(cohorts["top30"])
    prim_sigs = [s for s in collect(PRIMARY_ENTRY, PRIMARY_EXIT, rows_by, regmap) if s["sym"] in top]
    print(f"\n[참고] ({PRIMARY_ENTRY}, {PRIMARY_EXIT}) top30 코호트")
    top_cf = confirm(prim_sigs, pools[POOL_OF[PRIMARY_EXIT]], cutoff, span_train, f"{PRIMARY_ENTRY}/{PRIMARY_EXIT}:top30")

    prim = results[PRIMARY_ENTRY][PRIMARY_EXIT]
    verdict, why = decide(prim)
    sec = results["causal"][PRIMARY_EXIT]
    sec_v, sec_why = decide(sec)
    print("\n" + "=" * 100)
    print(f"[판정] triple_bottom_1w ({PRIMARY_ENTRY}, {PRIMARY_EXIT}) → {verdict} {'; '.join(why)}")
    print(f"[부 판정] (causal, {PRIMARY_EXIT}) → {sec_v} {'; '.join(sec_why)}  (보고용 — 별도 후보)")
    print("[주의] PASSED 여도 실거래 청산 변경은 자율 반영 대상이 아니다 — 사용자 보고 후 적용.")
    out = dict(test="exit_1w_triple_bottom", primary=[PRIMARY_ENTRY, PRIMARY_EXIT], verdict=verdict, reasons=why,
               secondary=dict(cell=["causal", PRIMARY_EXIT], verdict=sec_v, reasons=sec_why),
               data=dict(first=first, last=last, cutoff=cutoff, span_train=span_train, n_syms=len(rows_by), holdout_days=HOLDOUT_DAYS),
               stage1=stage1, pools={k: dict(n=len(v), mean=st.mean(v)) for k, v in pools.items()},
               results=results, primary_top30=top_cf)
    json.dump(out, open("_exit_1w.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print("[저장] _exit_1w.json")
    summary = {e: {a: (results[e][a]["gate"]["verdict"], results[e][a]["gate"]["n"], round(results[e][a]["gate"]["mean"] * 100, 2),
                      round(results[e][a]["gate"]["win_rate"] or 0, 2), round(results[e][a]["gate"]["boot_p"], 3),
                      round(min((results[e][a]["equity"] or {}).get("calmar", 0) or 0, 999), 2)) for a in EXITS} for e in ENTRIES}
    print("RESULT_JSON: " + json.dumps(dict(verdict=verdict, reasons=why, secondary=sec_v, holdout=prim["holdout"], arms=summary),
                                       ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
