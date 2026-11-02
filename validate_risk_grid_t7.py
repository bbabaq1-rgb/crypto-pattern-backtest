"""validate_risk_grid_t7.py — R-086 위험 수준 격자 J4 를 T7(진입 7일 창) 블록 부트로 재판정
(사전 등록 2026-11-02, registry risk_grid_t7_prereg_2026_11_02).

R-073(validate_risk_grid) 프레임·셀·J1~J3 그대로, 짝지음 재표집 블록만 거래 20개 연속(B20) -> 진입 7일 창(T7).
R-084 가 B20 부트가 실현 경로 대비 낙관이라고 밝혔다. 계산 전용: 위험 수준은 사용자 결정. DEPLOY_ON_PASS=False.
"""
import json
import random
import sys

import validate_gap as vg  # noqa: F401
import validate_path_tail as pt
import validate_portfolio as vp
import validate_risk_grid as rg

DEPLOY_ON_PASS = False
SEED = 86
BOOT_N = rg.BOOT_N
BLOCK = "T7"


def boot_t7(trades, rng):
    """모든 셀이 같은 T7 재표집 거래열을 공유(짝지음)."""
    bt = pt._reassign(trades, pt.boot_index(trades, BLOCK, rng))
    bt.sort(key=lambda t: t["t_in"])
    return {c: rg.run_cell(bt, c) for c in rg.cells()}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    import detlib
    import method_t as mt
    import regime_switch as rs
    from validate_regime_split import turnover_rank
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
    print(f"거래 {len(base)} (train {len(tr)} / holdout {len(ho)})")
    res = {c: rg.run_cell(base, c) for c in rg.cells()}
    train = {c: rg.run_cell(tr, c) for c in rg.cells()}
    hold = {c: rg.run_cell(ho, c) for c in rg.cells()} if ho else None
    for c in rg.cells():
        r = res[c]
        print(f"  [{rg._fmt(c)}] 전기간 CAGR {r['cagr']*100:+.1f}% MDD {r['mdd']*100:.1f}% Calmar {rg._cal(r):.2f}", flush=True)
    rng = random.Random(SEED)
    rows = [boot_t7(base, rng) for _ in range(BOOT_N)]
    bs = rg.boot_summary(rows)
    for c in rg.cells():
        b = bs[c]
        print(f"  [T7 {rg._fmt(c)}] Calmar 우위 {b['win']:.0%} · Calmar 중앙 {b['calmar_med']:.2f} · MDD 중앙 {b['mdd_med']*100:.1f}% · "
              f"CAGR 중앙 {b['cagr_med']*100:+.1f}% · 파산근사 {b['ruin']:.1%}", flush=True)
    # 진단: R-073 B20 우위 재현
    rr = random.Random(rg.SEED)
    b20 = rg.boot_summary([rg.boot(base, rr) for _ in range(BOOT_N)])
    for c in rg.PRIMARY:
        print(f"  [진단 B20 {rg._fmt(c)}] 우위 {b20[c]['win']:.0%} (R-073 기록: 0.5% 16% / 1.0% 35%)")
    wins = {c: bs[c]["win"] for c in rg.cells()}
    verdict, detail = rg.classify(res, train, hold, wins)
    print(f"\n판정: {verdict}")
    for c, d in detail.items():
        print(f"  {rg._fmt(c)}: " + " ".join(f"{k}={'O' if d[k] else 'X'}" for k in ("J1", "J2", "J3", "J4"))
              + f" -> {'PASS' if d['passed'] else 'FAIL'}")
    key = lambda c: f"{c[0]}_{c[1]}"
    json.dump(dict(prereg="risk_grid_t7_prereg_2026_11_02", verdict=verdict,
                   detail={key(c): d for c, d in detail.items()},
                   boot_t7={key(c): bs[c] for c in rg.cells()},
                   boot_b20={key(c): b20[c] for c in rg.cells()}),
              open("_risk_grid_t7.json", "w"), indent=1, ensure_ascii=False, default=str)


if __name__ == "__main__":
    main()
