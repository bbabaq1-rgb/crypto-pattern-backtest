"""validate_risk_grid.py — R-073 위험 수준 격자 재측정 (사전 등록 2026-10-31, registry risk_grid_prereg_2026_10_31).

R-063: 같은 거래열에서 risk 1.5% -> 0.5% 만으로 전기간 CAGR -11% -> +21.7%. 이 효과가 단일 경로 아티팩트인지
확인한다. 위험 수준은 사용자 결정 영역이라 **측정·보고까지만**(DEPLOY_ON_PASS=False).

프레임: validate_gap.simulate(= vp.simulate current 와 회계 동치) 에 risk·max_pos 만 바꾼다. 거래열·청산·변동성 배율·
총명목가 상한·LEV_CAP 고정. 격자 risk {0.5,1.0,1.5}% x MAX_POS {8,13} = 6셀, 기준 = (1.5%, 13) 현행.
주 판정 셀 2개: (0.5%,13), (1.0%,13). MAX_POS 8 셀은 진단(판정 아님, 사후 선택 금지).

주 판정 셀이 현행 대비 아래 4기준을 **전부** 통과하면 PASS. 둘 중 하나라도 PASS 면 SUPPORTED, 없으면 REJECTED.
 J1 전기간 Calmar > 현행                    J2 holdout(t_in>=2025-01-01) Calmar > 현행
 J3 train(<2025-01-01) Calmar >= 0.9 x 현행 (현행이 양수일 때; 아니면 > 현행)  — 엣지가 양수인 구간에서 이득을
    포기하지 않는가. holdout 은 bear 지배라 작게 거는 쪽이 기계적으로 유리하므로 J3 이 정보가 있는 기준이다.
 J4 같은 블록 재표집(300회) 전기간 Calmar 우위 >= 0.60 (짝지음: 같은 재표집 거래열을 모든 셀이 공유)
"""
import json
import math
import random
import statistics as st
import sys

import sizing as sz
import validate_gap as vg
import validate_portfolio as vp

DEPLOY_ON_PASS = False
RISKS = (0.005, 0.010, 0.015)
SLOTS = (8, 13)
CURRENT = (0.015, 13)
PRIMARY = ((0.005, 13), (0.010, 13))
BOOT_N = 300
SEED = 73
J4_WIN = 0.60
J3_TOL = 0.90
RUIN_FRAC = 0.25          # 부트 최종 자산 < 시작 x 0.25 를 파산 근사로 센다(진단)


def cells():
    return [(r, m) for m in SLOTS for r in RISKS]


def run_cell(trades, cell):
    r, m = cell
    return vg.simulate(trades, max_pos=m, risk=r)


def _cal(x):
    return x["calmar"] if math.isfinite(x["calmar"]) else 1e9


def judge_cell(cell, res, train, hold, win):
    """res/train/hold: cell -> simulate 결과. win: 부트 Calmar 우위 비율. 반환 (통과 여부, 기준별 dict)."""
    cur_f, cur_t, cur_h = _cal(res[CURRENT]), _cal(train[CURRENT]), _cal(hold[CURRENT]) if hold else None
    f, t = _cal(res[cell]), _cal(train[cell])
    h = _cal(hold[cell]) if hold else None
    j1 = f > cur_f
    j2 = (h is not None and cur_h is not None and h > cur_h)
    j3 = t >= J3_TOL * cur_t if cur_t > 0 else t > cur_t
    j4 = win >= J4_WIN
    return (j1 and j2 and j3 and j4), dict(J1=j1, J2=j2, J3=j3, J4=j4)


def classify(res, train, hold, wins):
    out, ok = {}, False
    for c in PRIMARY:
        passed, js = judge_cell(c, res, train, hold, wins[c])
        out[c] = dict(passed=passed, **js)
        ok = ok or passed
    return ("SUPPORTED" if ok else "REJECTED"), out


def boot(trades, rng):
    """cells 전부가 같은 재표집 거래열을 공유(짝지음) — 셀별 Calmar·MDD·파산 여부."""
    bt = vp.block_bootstrap(trades, rng)
    bt.sort(key=lambda t: t["t_in"])
    return {c: run_cell(bt, c) for c in cells()}


def boot_summary(rows):
    cur = [_cal(r[CURRENT]) for r in rows]
    out = {}
    for c in cells():
        cal = [_cal(r[c]) for r in rows]
        out[c] = dict(win=sum(a > b for a, b in zip(cal, cur)) / len(rows),
                      calmar_med=st.median(cal),
                      mdd_med=st.median([r[c]["mdd"] for r in rows]),
                      cagr_med=st.median([r[c]["cagr"] for r in rows]),
                      ruin=sum(r[c]["final"] < vp.START_EQ * RUIN_FRAC for r in rows) / len(rows))
    return out


def _fmt(c):
    return f"risk {c[0]*100:.1f}% / MAX_POS {c[1]}"


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    import detlib
    import method_t as mt
    import regime_switch as rs
    from validate_regime_split import turnover_rank
    print("=" * 90)
    print("R-073 위험 수준 격자 재측정 (사전 등록 2026-10-31)")
    print("=" * 90)
    syms = json.load(open("universe.json", encoding="utf-8"))["trading_universe"]
    if "--no-fetch" not in argv:
        vp.fetch(syms)
    rows_4h = {}
    for s in syms:
        try:
            rows_4h[s] = detlib.load_ohlcv(s, "4h")
        except (FileNotFoundError, RuntimeError):
            continue
    ranked = turnover_rank(rows_4h)
    regmap = rs.build_regime_map()
    mt.REGMAP = regmap
    base = sorted(vp.collect_1d(syms) + vp.collect_4h(rows_4h, ranked, regmap), key=lambda t: t["t_in"])
    cut = vp.mx._tnum(vp.SPLIT)
    tr = [t for t in base if t["t_in"] < cut]
    ho = [t for t in base if t["t_in"] >= cut]
    print(f"거래 {len(base)} (train {len(tr)} / holdout {len(ho)}) · 현행 RISK {sz.RISK_FRAC*100:.1f}% LEV {sz.LEV_CAP}")
    res = {c: run_cell(base, c) for c in cells()}
    train = {c: run_cell(tr, c) for c in cells()}
    hold = {c: run_cell(ho, c) for c in cells()} if ho else None
    for c in cells():
        r, a, h = res[c], train[c], (hold[c] if hold else None)
        print(f"  [{_fmt(c)}] 전기간 CAGR {r['cagr']*100:+7.1f}% MDD {r['mdd']*100:6.1f}% Calmar {_cal(r):6.2f} 체결 {r['taken']:5} 스킵 {r['skipped']:5}"
              f" | train Calmar {_cal(a):6.2f} CAGR {a['cagr']*100:+7.1f}%"
              + (f" | holdout Calmar {_cal(h):6.2f} CAGR {h['cagr']*100:+7.1f}% MDD {h['mdd']*100:6.1f}%" if h else ""), flush=True)
    rr = random.Random(SEED)
    rows = [boot(base, rr) for _ in range(BOOT_N)]
    bs = boot_summary(rows)
    for c in cells():
        b = bs[c]
        print(f"  [boot {_fmt(c)}] Calmar 우위 {b['win']:.0%} · Calmar 중앙 {b['calmar_med']:.2f} · MDD 중앙 {b['mdd_med']*100:.1f}% · "
              f"CAGR 중앙 {b['cagr_med']*100:+.1f}% · 파산근사 {b['ruin']:.1%}", flush=True)
    wins = {c: bs[c]["win"] for c in cells()}
    verdict, detail = classify(res, train, hold, wins)
    print(f"\n판정: {verdict}")
    for c, d in detail.items():
        print(f"  {_fmt(c)}: " + " ".join(f"{k}={'O' if d[k] else 'X'}" for k in ("J1", "J2", "J3", "J4"))
              + f" -> {'PASS' if d['passed'] else 'FAIL'}")
    key = lambda c: f"{c[0]}_{c[1]}"
    strip = lambda x: {k: v for k, v in x.items() if k != "took"}
    json.dump(dict(prereg="risk_grid_prereg_2026_10_31", verdict=verdict,
                   detail={key(c): d for c, d in detail.items()},
                   full={key(c): strip(res[c]) for c in cells()},
                   train={key(c): strip(train[c]) for c in cells()},
                   holdout={key(c): strip(hold[c]) for c in cells()} if hold else None,
                   boot={key(c): bs[c] for c in cells()}),
              open("_risk_grid.json", "w"), indent=1, ensure_ascii=False, default=str)


if __name__ == "__main__":
    main()
