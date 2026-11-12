"""validate_minorder4h.py — R-108: 4h 배포 패턴의 최소주문 통과 비율 (계산 전용, 2026-11-12).

R-107(validate_minorder)과 같은 함수·상수로, 표본만 validate_portfolio.collect_4h 로 바꾼다.
사전 등록: registry minorder4h_prereg_2026_11_12. 주 판정: equity $240 에서 전체 통과 >= 90% 면 NO_PROBLEM.
"""
import json
import sys

import validate_minorder as vm

DEPLOY_ON_PASS = False
PRIMARY_EQ = 240
THRESH = 0.90


def verdict(scales):
    r = vm.pass_rate(scales, PRIMARY_EQ)
    if r is None:
        return "NO_DATA"
    return "NO_PROBLEM" if r >= THRESH else "PROBLEM"


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    import validate_portfolio as vp
    import method_t as mt
    import regime_switch as rs
    syms = json.load(open("universe.json", encoding="utf-8"))["trading_universe"]
    if "--no-fetch" not in argv:
        vp.fetch(syms)
    import detlib
    rows_4h = {}
    for s in syms:
        try:
            rows_4h[s] = detlib.load_ohlcv(s, "4h")
        except (FileNotFoundError, RuntimeError):
            continue
    ranked = vp.turnover_rank(rows_4h)
    regmap = rs.build_regime_map()
    mt.REGMAP = regmap
    trades = vp.collect_4h(rows_4h, ranked, regmap)
    if not trades:
        print("거래 없음"); return
    last = max(t["t_in"] for t in trades)
    cut = last - vm.RECENT_DAYS
    sc = [(t["t_in"], t["pattern"], vm.vscale(t["vol"])) for t in trades]
    all_s = [s for _, _, s in sc]
    rec_s = [s for d, _, s in sc if d >= cut]
    print(f"[표본] 4h 거래 {len(all_s)} | 최근 {vm.RECENT_DAYS}일 {len(rec_s)} | σ 없음 {sum(1 for t in trades if not t['vol'])}")
    need = sorted(vm.need_equity(v) for v in all_s)
    q = {f"p{p}": round(need[min(len(need) - 1, int(len(need) * p / 100))], 1) for p in (10, 25, 50, 75, 90, 100)}
    print("필요 최소 equity 분위:", q)
    table = {}
    print(f"{'equity':>8}{'전체':>9}{'최근90일':>10}")
    for eq in vm.EQ_GRID:
        a = vm.pass_rate(all_s, eq); r = vm.pass_rate(rec_s, eq)
        table[eq] = dict(all=a, recent=r)
        print(f"{eq:>8}{a*100:>8.1f}%{(r*100 if r is not None else float('nan')):>9.1f}%")
    by = {}
    for _, p, s in sc:
        by.setdefault(p, []).append(s)
    pat = {p: {eq: round(vm.pass_rate(v, eq), 3) for eq in (160, 240, 355)} | {"n": len(v)} for p, v in by.items()}
    for p, d in sorted(pat.items()):
        print(f"  {p:<22} n={d['n']:>5} @160 {d[160]*100:5.1f}% @240 {d[240]*100:5.1f}% @355 {d[355]*100:5.1f}%")
    v = verdict(all_s)
    print(f"[판정] {v} (equity ${PRIMARY_EQ} 전체 {table[PRIMARY_EQ]['all']*100:.1f}% vs 문턱 {THRESH*100:.0f}%)")
    json.dump(dict(verdict=v, table=table, need_quantiles=q, patterns=pat, n=len(all_s), n_recent=len(rec_s)),
              open("_minorder4h.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print("RESULT_JSON: " + json.dumps(dict(verdict=v, r100=table[100]["all"], r160=table[160]["all"],
          r240=table[240]["all"], r355=table[355]["all"], rec240=table[240]["recent"]), separators=(",", ":")))


if __name__ == "__main__":
    main()
