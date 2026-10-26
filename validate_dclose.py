"""
validate_dclose.py — 방식D 손절 판정 저가 → **종가** (D_close), 1d·4h 배포 셀 짝지음 사전 등록 (R-002, 2026-10-26, 자율 연구 루프).

계기
  validate_exit_1w(2026-09-06) 진단: 주봉에서 D_close 가 D 대비 +4.3%p (t 2.3) — 저가 판정이 흔들림에 과도하게 털어낸다는 독립 증거.
  1d/4h 에서는 한 번도 재지 않았다. 실거래 손실의 대부분이 −8% 손절(관찰 보고)이라 손절 판정 방식은 레버가 크다.

가설
  손절을 봉 저가 대신 종가로 판정하면(레짐 전환·30봉 시가 청산은 D 그대로) 꼬리 스파이크에 털리는 거래가 줄어 건당 수익이 오른다.
  거래소 재해 손절 −15%(저가)는 항상 동반 — 불변 '손절 주문 없으면 실거래 없음' 을 지킨다.

셀 (실거래 배포 범위, 롱 전용, 레짐 게이팅은 universe.json 그대로)
  engulfing 1d top30(실거래 PATTERN_UNIVERSE, 사용자 강제 2026-09-04) · fvg 1d top30 · inverted_hammer 1d majors · three_soldiers_4h all(BULL) ·
  triple_bottom_4h top30 · equal_lows_4h top30 · vol_awakening_4h top30   (marubozu 는 2026-10-22 정지라 제외, 숏은 제외)
arm
  D            현행 (method_s.outcome = eval_D)
  D_close      [주 판정] 종가 ≤ 진입가×0.92 면 그 종가에 청산 / 재해 손절 저가 ≤ ×0.85 (−15%) / 레짐 전환·만기는 D 와 동일
  D_close_nocat [진단] 재해 손절 없음 — 재해 손절의 비용 분리 (실거래 후보 아님)
  사이징 stop_pct 는 두 arm 모두 0.08 (사이징 규칙은 바꾸지 않는다 — 청산만 다르다).

판정 기준 (사전 등록 — 사후 변경 금지). 같은 신호에 두 규칙을 동시에 적용(짝지음), 풀링 7셀:
  P1 풀링 짝지음 평균차 (D_close − D) > 0 이고 t > 2
  P2 진입 월 블록 부트스트랩(1000회, 시드 42) 평균차 ≤ 0 비율 < 0.10      (같은 달 신호 상관 보정)
  P3 평균차 > 0 인 셀 ≥ 5 / 7
  P4 달력 전후반(신호 진입일 중앙값 기준) 평균차 둘 다 > 0
  P5 풀링 자산곡선(method_x.equity_curve, 실거래 사이징): D_close 의 CAGR 과 Calmar 가 모두 D 보다 큼
  P6 최근 365일(달력) 평균차 > 0 (n ≥ 30)
  전부 통과 → PASSED. P1·P2 통과이고 P3~P6 중 일부 실패 → MIXED(보고만). 그 외 REJECTED.
  **PASSED 여도 자율 반영 없음 (DEPLOY_ON_PASS=False)** — 집행 경로(엔진 종가 손절 + 거래소 재해 손절)가 신규 코드다.

진단(판정 아님): 셀별 평균차·t, 손절 거래 수(D / D_close / 재해), D 가 손절한 거래의 D_close 결과(회복·추가 하락),
  D_close 의 종가 손절 평균 실현 손실(−8% 보다 얼마나 깊은가), D_close_nocat 평균차.
출력: _dclose.json + RESULT_JSON.  실행: python validate_dclose.py [--no-fetch]
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
from validate_revival import _tnum, equity as _equity

SEED, BOOT_N = 42, 1000
FEE = detlib.FEE
STOP_D, HOLD_D = ms.STOP, ms.MAX_HOLD
CAT = 0.15
HOLDOUT_DAYS = 365
HOLDOUT_MIN_N = 30
BULL = ("bull_btc", "bull_altseason")
MAJORS = list(detlib.SYMBOLS)
# (cid, tf, module, cohort, regimes)
CELLS = [
    ("engulfing",         "1d", "detector_engulfing",         "top30",  None),
    ("fvg",               "1d", "detector_fvg",               "top30",  None),
    ("inverted_hammer",   "1d", "detector_inverted_hammer",   "majors", None),
    ("three_soldiers_4h", "4h", "detector_three_soldiers_4h", "all",    BULL),
    ("triple_bottom_4h",  "4h", "detector_triple_bottom",     "top30",  None),
    ("equal_lows_4h",     "4h", "detector_equal_lows_4h",     "top30",  None),
    ("vol_awakening_4h",  "4h", "detector_vol_awakening_4h",  "top30",  None),
]
ARMS = ("D", "D_close", "D_close_nocat")
FETCH_TFS = ("1d", "4h")


def outcome_d_close(rows, si, lab, max_hold=HOLD_D, stop=STOP_D, cat=CAT):
    """방식D 에서 손절 판정만 저가 → 종가. cat=None 이면 재해 손절 없음. (ret, hold, reason)."""
    base = rows[si]["c"]
    entry_reg = lab(si)
    end = min(si + max_hold, len(rows) - 1)
    for j in range(si + 1, end + 1):
        if cat is not None and rows[j]["l"] <= base * (1 - cat):
            return -cat - FEE, j - si, "cat_stop"
        c = rows[j]["c"]
        if c <= base * (1 - stop):
            return c / base - 1 - FEE, j - si, "sl_close"
        if lab(j) not in (None, entry_reg):
            return c / base - 1 - FEE, j - si, "regime_switch"
    px = rows[end]["o"]
    return px / base - 1 - FEE, end - si, "maxhold"


def outcome_arm(arm, rows, si, lab):
    if arm == "D":
        r, h, why = ms.outcome(rows, si, "long", set(), lab, use_regime=True, max_hold=HOLD_D)
        return r, h, why
    if arm == "D_close":
        return outcome_d_close(rows, si, lab, cat=CAT)
    if arm == "D_close_nocat":
        return outcome_d_close(rows, si, lab, cat=None)
    raise ValueError(arm)


def cohort_syms(rule, rows_by, ranked):
    if rule == "majors":
        return [s for s in MAJORS if s in rows_by]
    if rule in ("top20", "top30"):
        return [s for s in ranked[:int(rule[3:])] if s in rows_by]
    return sorted(rows_by)


def collect(detect_fn, syms, rows_by, regmap, regimes, tf):
    """셀의 신호마다 세 arm 결과를 한 번에 계산(같은 신호·같은 가격 경로)."""
    out = []
    for sym in syms:
        rows = rows_by[sym]
        lab = lambda j, rows=rows: regmap.get(rows[j]["date"])
        try:
            idxs = detect_fn(rows)
        except Exception as e:
            print(f"  [detect] {sym} 오류: {str(e)[:60]}"); idxs = []
        for si in idxs:
            if si + 1 >= len(rows) or si >= len(rows) - HOLD_D - 1 or si < 30:
                continue
            reg = regmap.get(rows[si]["date"])
            if regimes is not None and reg not in regimes:
                continue
            vol = sz.realized_vol(rows, si, tf=tf)
            if vol is None:
                continue
            rec = dict(sym=sym, date=rows[si]["date"], regime=reg, vol=vol, t_in=_tnum(rows[si]), key=(sym, si))
            for arm in ARMS:
                ret, hold, why = outcome_arm(arm, rows, si, lab)
                xi = min(si + hold, len(rows) - 1)
                rec[arm] = dict(ret=ret, hold=hold, reason=why, exit_date=rows[xi]["date"], t_out=_tnum(rows[xi]))
            out.append(rec)
    return out


def arm_sigs(sigs, arm):
    """equity()/gate 가 받는 평평한 dict 목록."""
    return [dict(date=s["date"], ret=s[arm]["ret"], hold=s[arm]["hold"], reason=s[arm]["reason"],
                 exit_date=s[arm]["exit_date"], t_in=s["t_in"], t_out=s[arm]["t_out"], stop_pct=STOP_D, vol=s["vol"])
            for s in sigs]


# ── 통계 ──────────────────────────────────────────────────────────────────────
def paired_diffs(sigs, a="D_close", b="D"):
    return [(s["date"], s[a]["ret"] - s[b]["ret"]) for s in sigs]


def mean_t(diffs):
    d = [x for _, x in diffs]
    if len(d) < 2:
        return (st.mean(d) if d else 0.0), 0.0
    m = st.mean(d)
    sd = st.stdev(d)
    return m, (m / (sd / len(d) ** 0.5) if sd > 0 else 0.0)


def month_boot_nonpos(diffs, seed=SEED, boot_n=BOOT_N):
    """진입 월 블록 재표집 평균차 ≤ 0 비율 (낮을수록 양수 증거)."""
    by = {}
    for d, x in diffs:
        by.setdefault(d[:7], []).append(x)
    months = sorted(by)
    if not months:
        return 1.0
    rng = random.Random(seed)
    bad = 0
    for _ in range(boot_n):
        tot = cnt = 0
        for _ in months:
            v = by[months[rng.randrange(len(months))]]
            tot += sum(v); cnt += len(v)
        if cnt == 0 or tot / cnt <= 0:
            bad += 1
    return bad / boot_n


def judge(p):
    """p: dict(P1..P6 bool). 사전 등록 판정."""
    if all(p[k] for k in ("P1", "P2", "P3", "P4", "P5", "P6")):
        return "PASSED"
    if p["P1"] and p["P2"]:
        return "MIXED"
    return "REJECTED"


def _f(x):
    return "n/a" if x is None else f"{x*100:+.2f}%"


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    syms = va._syms()
    print(f"D_close 사전 등록 | 셀 {len(CELLS)} | arm {ARMS} | 재해 손절 −{CAT*100:.0f}% | 시드 {SEED}")
    if "--no-fetch" not in argv:
        va.fetch(syms, list(FETCH_TFS))
    regmap = rs.build_regime_map()
    rows_1d = va.load_tf(syms, "1d")
    ranked = turnover_rank(rows_1d)
    rows_tf = {"1d": rows_1d, "4h": va.load_tf(syms, "4h")}
    cell_sigs, per_cell = {}, {}
    for cid, tf, mod, cohort, regimes in CELLS:
        rows_by = rows_tf[tf]
        cs = cohort_syms(cohort, rows_by, ranked)
        t0 = time.time()
        sigs = collect(importlib.import_module(mod).detect, cs, rows_by, regmap, regimes, tf)
        cell_sigs[cid] = sigs
        m, t = mean_t(paired_diffs(sigs))
        mn, tn = mean_t(paired_diffs(sigs, "D_close_nocat"))
        rc = {}
        for s in sigs:
            rc[s["D"]["reason"]] = rc.get(s["D"]["reason"], 0) + 1
        rcc = {}
        for s in sigs:
            rcc[s["D_close"]["reason"]] = rcc.get(s["D_close"]["reason"], 0) + 1
        per_cell[cid] = dict(n=len(sigs), D=st.mean(s["D"]["ret"] for s in sigs) if sigs else None,
                             D_close=st.mean(s["D_close"]["ret"] for s in sigs) if sigs else None,
                             diff=m, t=t, diff_nocat=mn, reasons_D=rc, reasons_Dclose=rcc)
        print(f"[{cid} @{tf} | {cohort}({len(cs)}) | {regimes or '전부'}] n={len(sigs)} D {_f(per_cell[cid]['D'])} "
              f"D_close {_f(per_cell[cid]['D_close'])} 차 {m*100:+.2f}%p t={t:.2f} | nocat 차 {mn*100:+.2f}%p | "
              f"D {rc} | D_close {rcc} ({time.time()-t0:.0f}s)", flush=True)
    allsigs = [s for v in cell_sigs.values() for s in v]
    diffs = paired_diffs(allsigs)
    m, t = mean_t(diffs)
    boot = month_boot_nonpos(diffs)
    ds = sorted(d for d, _ in diffs)
    mid = ds[len(ds) // 2] if ds else ""
    h1, h2 = mean_t([x for x in diffs if x[0] < mid])[0], mean_t([x for x in diffs if x[0] >= mid])[0]
    last = max((d for d, _ in diffs), default=None)
    cutoff = (date.fromordinal(date.fromisoformat(last).toordinal() - HOLDOUT_DAYS).isoformat() if last else "")
    ho = [x for x in diffs if x[0] >= cutoff]
    hm = mean_t(ho)[0] if ho else None
    first = ds[0] if ds else last
    span = max(1, date.fromisoformat(last).toordinal() - date.fromisoformat(first).toordinal()) if last else 1
    eq = {a: _equity(arm_sigs(allsigs, a), span) for a in ("D", "D_close")}
    p5 = bool(eq["D"] and eq["D_close"] and eq["D_close"]["cagr"] > eq["D"]["cagr"] and eq["D_close"]["calmar"] > eq["D"]["calmar"])
    pos_cells = sum(1 for c in per_cell.values() if c["n"] and c["diff"] > 0)
    P = dict(P1=bool(m > 0 and t > 2), P2=boot < 0.10, P3=pos_cells >= 5, P4=bool(h1 > 0 and h2 > 0),
             P5=p5, P6=bool(hm is not None and len(ho) >= HOLDOUT_MIN_N and hm > 0))
    verdict = judge(P)
    # 진단
    stopped = [s for s in allsigs if s["D"]["reason"] == "stop"]
    dstop_close = [s["D_close"]["ret"] for s in stopped]
    sl_close = [s["D_close"]["ret"] for s in allsigs if s["D_close"]["reason"] == "sl_close"]
    diag = dict(n=len(allsigs), n_D_stop=len(stopped),
                n_Dclose_slclose=sum(1 for s in allsigs if s["D_close"]["reason"] == "sl_close"),
                n_Dclose_cat=sum(1 for s in allsigs if s["D_close"]["reason"] == "cat_stop"),
                mean_D_on_Dstopped=st.mean(s["D"]["ret"] for s in stopped) if stopped else None,
                mean_Dclose_on_Dstopped=st.mean(dstop_close) if dstop_close else None,
                mean_slclose_ret=st.mean(sl_close) if sl_close else None,
                nocat_diff=mean_t(paired_diffs(allsigs, "D_close_nocat"))[0])
    print("\n" + "=" * 100)
    print(f"풀링 n={len(allsigs)} 평균차 {m*100:+.3f}%p t={t:.2f} | 월블록 부트 ≤0 비율 {boot:.3f} | 셀 양수 {pos_cells}/7 | "
          f"전반 {h1*100:+.2f} 후반 {h2*100:+.2f}%p | 최근365일 n={len(ho)} {_f(hm)}")
    for a in ("D", "D_close"):
        e = eq[a] or {}
        print(f"  자산곡선 {a:<8} CAGR {_f(e.get('cagr'))} MDD {_f(e.get('mdd'))} Calmar {e.get('calmar', 0) or 0:.2f}")
    print(f"  진단: {json.dumps(diag, ensure_ascii=False, default=str)}")
    print(f"  기준 {P} => **{verdict}**")
    json.dump(dict(verdict=verdict, P=P, pooled=dict(n=len(allsigs), diff=m, t=t, boot=boot, h1=h1, h2=h2, holdout_n=len(ho), holdout=hm),
                   per_cell=per_cell, equity=eq, diag=diag), open("_dclose.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1, default=str)
    print("RESULT_JSON: " + json.dumps(dict(verdict=verdict, P=P, diff_pp=round(m * 100, 3), t=round(t, 2), boot=boot,
                                            cells_pos=pos_cells, n=len(allsigs)), ensure_ascii=False))


if __name__ == "__main__":
    main()
