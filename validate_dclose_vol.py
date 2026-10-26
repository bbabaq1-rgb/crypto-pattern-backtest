"""
validate_dclose_vol.py — D_close 이득의 출처: vol_awakening_4h 한정 반증 3종 (R-020, 2026-10-26, 자율 연구 루프).

계기: R-002 풀링 이득(+0.373%p, t 4.72)이 한 셀(vol_awakening_4h n=5081 +0.49%p t 6.46)에 지배, 동료 셀 일부 음수, 후반 +0.04%p.
사후 선택 셀이므로 validate_ih_exit 식 반증을 선행한다. registry dclose_vol_prereg_2026_10_26.

판정 (사전 등록 — 사후 변경 금지)
  선결  셀 평균차(D_close−D) > 0 (≤0 이면 NOISE)
  F1    달력 전후반(신호 진입일 중앙값) 평균차 둘 다 > 0
  F2    진입 월 블록 부트스트랩(1000, 시드 42) 평균차의 2.5백분위 > 0
  F3    셀 평균차 > 무작위 진입 대조군 평균차 분포의 95백분위
        (대조군: 종목별 신호 수 동일, 진입 봉 시간 균등, 동일 청산, 30회 반복, 시드 42)
  3/3 REAL_CELL_EFFECT · 2/3 MIXED · ≤1 NOISE.  DEPLOY_ON_PASS=False — 통과해도 실거래 반영 없음.
진단(판정 아님): C_month(같은 종목·같은 달 무작위) 평균차 · 동료 4h 3셀 · 최근 365일 · D 손절 거래 중 D_close 회복 비율.
실행: python validate_dclose_vol.py [--no-fetch]
"""
import importlib
import json
import random
import statistics as st
import sys
from datetime import date

import validate_dclose as vd
import regime_switch as rs
import sizing as sz
import validate_regime_split_all as va
from validate_regime_split import turnover_rank
from validate_revival import _tnum

SEED, BOOT_N, CTRL_REPS, CTRL_Q = vd.SEED, vd.BOOT_N, 30, 0.95
CELL = "vol_awakening_4h"
PEERS = ("equal_lows_4h", "triple_bottom_4h", "three_soldiers_4h")
ARMS2 = ("D", "D_close")


def pctile(xs, q):
    xs = sorted(xs)
    if not xs:
        return None
    k = (len(xs) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def month_boot_means(diffs, seed=SEED, boot_n=BOOT_N):
    """진입 월 블록 재표집 평균차 목록."""
    by = {}
    for d, x in diffs:
        by.setdefault(d[:7], []).append(x)
    months = sorted(by)
    if not months:
        return []
    rng = random.Random(seed)
    out = []
    for _ in range(boot_n):
        tot = cnt = 0
        for _ in months:
            v = by[months[rng.randrange(len(months))]]
            tot += sum(v); cnt += len(v)
        out.append(tot / cnt if cnt else 0.0)
    return out


def judge(pos, f1, f2, f3):
    if not pos:
        return "NOISE"
    n = int(bool(f1)) + int(bool(f2)) + int(bool(f3))
    return "REAL_CELL_EFFECT" if n == 3 else ("MIXED" if n == 2 else "NOISE")


def eligible(rows):
    return list(range(30, len(rows) - vd.HOLD_D - 1))


def draw_control(rows, k, rng, month=None, anchor_dates=None):
    """무작위 진입 봉 k 개. anchor_dates 가 있으면 그 날짜의 달('YYYY-MM') 안에서만, 달마다 신호 수만큼."""
    el = eligible(rows)
    if not el:
        return []
    if anchor_dates is None:
        return sorted(rng.sample(el, min(k, len(el))))
    out = []
    by = {}
    for i in el:
        by.setdefault(rows[i]["date"][:7], []).append(i)
    cnt = {}
    for d in anchor_dates:
        cnt[d[:7]] = cnt.get(d[:7], 0) + 1
    for m, c in cnt.items():
        pool = by.get(m, [])
        if pool:
            out += rng.sample(pool, min(c, len(pool)))
    return sorted(out)


def collect2(idx_by_sym, rows_by, regmap, tf):
    """D / D_close 두 arm 만 (같은 가격 경로)."""
    out = []
    for sym, idxs in idx_by_sym.items():
        rows = rows_by[sym]
        lab = lambda j, rows=rows: regmap.get(rows[j]["date"])
        for si in idxs:
            if si + 1 >= len(rows) or si >= len(rows) - vd.HOLD_D - 1 or si < 30:
                continue
            if sz.realized_vol(rows, si, tf=tf) is None:
                continue
            rec = dict(sym=sym, date=rows[si]["date"], t_in=_tnum(rows[si]))
            for arm in ARMS2:
                ret, hold, why = vd.outcome_arm(arm, rows, si, lab)
                rec[arm] = dict(ret=ret, hold=hold, reason=why)
            out.append(rec)
    return out


def diffs_of(sigs):
    return [(s["date"], s["D_close"]["ret"] - s["D"]["ret"]) for s in sigs]


def mean_of(diffs):
    return st.mean(x for _, x in diffs) if diffs else 0.0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    syms = va._syms()
    cell = [c for c in vd.CELLS if c[0] == CELL][0]
    cid, tf, mod, cohort, regimes = cell
    print(f"R-020 D_close 출처 | 셀 {CELL} | 대조군 {CTRL_REPS}회 | 시드 {SEED}")
    if "--no-fetch" not in argv:
        va.fetch(syms, ["1d", "4h"])
    regmap = rs.build_regime_map()
    rows_1d = va.load_tf(syms, "1d")
    ranked = turnover_rank(rows_1d)
    rows_by = va.load_tf(syms, tf)
    cs = vd.cohort_syms(cohort, rows_by, ranked)
    sigs = vd.collect(importlib.import_module(mod).detect, cs, rows_by, regmap, regimes, tf)
    diffs = [(s["date"], s["D_close"]["ret"] - s["D"]["ret"]) for s in sigs]
    cell_m, cell_t = vd.mean_t(diffs)
    ds = sorted(d for d, _ in diffs)
    mid = ds[len(ds) // 2] if ds else ""
    h1 = mean_of([x for x in diffs if x[0] < mid]); h2 = mean_of([x for x in diffs if x[0] >= mid])
    boots = month_boot_means(diffs)
    lo95 = pctile(boots, 0.025)
    # 대조군: 종목별 신호 수 동일, 시간 균등
    cnt = {}
    for s in sigs:
        cnt[s["sym"]] = cnt.get(s["sym"], 0) + 1
    ctrl_means, ctrl_month_means = [], []
    for rep in range(CTRL_REPS):
        rng = random.Random(SEED * 1000 + rep)
        idx = {sym: draw_control(rows_by[sym], k, rng) for sym, k in cnt.items()}
        ctrl_means.append(mean_of(diffs_of(collect2(idx, rows_by, regmap, tf))))
        if rep < 10:
            rng2 = random.Random(SEED * 2000 + rep)
            by_sym_dates = {}
            for s in sigs:
                by_sym_dates.setdefault(s["sym"], []).append(s["date"])
            idx2 = {sym: draw_control(rows_by[sym], len(ds_), rng2, anchor_dates=ds_) for sym, ds_ in by_sym_dates.items()}
            ctrl_month_means.append(mean_of(diffs_of(collect2(idx2, rows_by, regmap, tf))))
    c95 = pctile(ctrl_means, CTRL_Q)
    pos = cell_m > 0
    F1, F2, F3 = bool(h1 > 0 and h2 > 0), bool(lo95 is not None and lo95 > 0), bool(c95 is not None and cell_m > c95)
    verdict = judge(pos, F1, F2, F3)
    # 진단
    last = max((d for d, _ in diffs), default=None)
    cutoff = date.fromordinal(date.fromisoformat(last).toordinal() - 365).isoformat() if last else ""
    ho = [x for x in diffs if x[0] >= cutoff]
    stopped = [s for s in sigs if s["D"]["reason"] == "stop"]
    recov = sum(1 for s in stopped if s["D_close"]["ret"] > s["D"]["ret"]) / len(stopped) if stopped else None
    peers = {}
    for pid in PEERS:
        pc = [c for c in vd.CELLS if c[0] == pid][0]
        ps = vd.collect(importlib.import_module(pc[2]).detect, vd.cohort_syms(pc[3], rows_by, ranked), rows_by, regmap, pc[4], pc[1])
        peers[pid] = dict(n=len(ps), diff=mean_of([(s["date"], s["D_close"]["ret"] - s["D"]["ret"]) for s in ps]))
    diag = dict(holdout_n=len(ho), holdout_diff=mean_of(ho), D_stop_n=len(stopped), D_stop_recovered_frac=recov,
                ctrl_month_mean=st.mean(ctrl_month_means) if ctrl_month_means else None, peers=peers)
    print("\n" + "=" * 90)
    print(f"{CELL} n={len(sigs)} 평균차 {cell_m*100:+.3f}%p t={cell_t:.2f} | 전반 {h1*100:+.2f} 후반 {h2*100:+.2f}%p | "
          f"월부트 2.5%={lo95*100 if lo95 is not None else float('nan'):+.3f}%p | 대조군 평균 {st.mean(ctrl_means)*100:+.3f}%p 95백분위 {c95*100:+.3f}%p")
    print(f"  진단: {json.dumps(diag, ensure_ascii=False, default=str)}")
    print(f"  선결 {pos} F1 {F1} F2 {F2} F3 {F3} => **{verdict}**")
    out = dict(verdict=verdict, pos=pos, F=dict(F1=F1, F2=F2, F3=F3), n=len(sigs), diff=cell_m, t=cell_t, h1=h1, h2=h2,
               boot_lo=lo95, ctrl_mean=st.mean(ctrl_means), ctrl_p95=c95, diag=diag)
    json.dump(out, open("_dclose_vol.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print("RESULT_JSON: " + json.dumps(dict(verdict=verdict, F=dict(F1=F1, F2=F2, F3=F3), diff_pp=round(cell_m * 100, 3),
                                            ctrl_p95_pp=round((c95 or 0) * 100, 3), n=len(sigs)), ensure_ascii=False))


if __name__ == "__main__":
    main()
