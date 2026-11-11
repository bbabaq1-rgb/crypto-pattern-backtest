"""validate_minorder.py — R-107: equity 대역별 최소주문 통과 비율 (계산 전용, 2026-11-11).

실거래 라우팅 복제 거래열(sizing_vol.collect_all)의 진입 시점 σ 로 vol_scale 을 구해
equity 별로 '증거금 >= MIN_MARGIN' 을 통과하는 신호 비율을 계산한다. 사전 등록: registry minorder_prereg_2026_11_11.
"""
import json
import statistics as st
import sys

import sizing as sz

DEPLOY_ON_PASS = False
EQ_GRID = (90, 100, 160, 240, 355)
STOP = 0.08
RECENT_DAYS = 90
FLOOR = 100.0          # paper_executor.EQUITY_FLOOR 와 같아야 한다 (test 가 대조)


def vscale(vol):
    """진입 시점 σ -> 실거래 vol_scale. σ 없으면 1.0(실거래 폴백과 동일)."""
    if not (sz.VOL_TARGETING and sz.VOL_S_NORM) or not vol or vol <= 0:
        return 1.0      # sizing.vol_scale 의 폴백과 동일
    return sz.vol_scale_raw(vol) / sz.VOL_S_NORM


def need_equity(vs):
    return sz.min_equity_for(vs, STOP)


def pass_rate(scales, eq):
    """equity eq 에서 주문이 나가는 비율. eq<FLOOR 는 킬스위치라 0."""
    if not scales or eq < FLOOR:
        return 0.0 if scales else None
    ok = sum(1 for v in scales if need_equity(v) <= eq)
    return ok / len(scales)


def verdict(all_scales, recent_scales):
    ra = pass_rate(all_scales, FLOOR)
    rr = pass_rate(recent_scales, FLOOR) if recent_scales else None
    if ra is not None and ra >= 0.9 and (rr is None or rr >= 0.9):
        return "NO_PROBLEM"
    return "PROBLEM"


def main(argv=None):
    import importlib
    import sizing_vol as sv
    import method_s as ms
    import method_t as mt
    import regime_switch as rs
    argv = argv if argv is not None else sys.argv[1:]
    sv.ROUTING_MODE = True
    ms.UNIVERSE_MODE = True
    syms = ms.symbols()
    if "--no-fetch" not in argv:
        ms.ensure_data(ms.FETCH_DAYS, syms)
    mt.REGMAP = rs.build_regime_map()
    trades = sv.collect_all(syms)
    if not trades:
        print("거래 없음"); return
    from datetime import date, timedelta
    last = max(t[0] for t in trades)
    try:
        cut = (date.fromisoformat(str(last)[:10]) - timedelta(days=RECENT_DAYS)).isoformat()
    except ValueError:
        cut = None
    sc = [(t[0], t[4], vscale(t[6])) for t in trades]
    all_s = [s for _, _, s in sc]
    rec_s = [s for d, _, s in sc if cut and str(d)[:10] >= cut]
    print(f"[표본] 거래 {len(all_s)} | 최근 {RECENT_DAYS}일({cut}~) {len(rec_s)} | 변동성 없음(스케일1) {sum(1 for t in trades if not t[6])}")
    need = sorted(need_equity(v) for v in all_s)
    q = {f"p{p}": round(need[min(len(need)-1, int(len(need)*p/100))], 1) for p in (10, 25, 50, 75, 90, 100)}
    print("필요 최소 equity 분위:", q)
    print(f"{'equity':>8}{'전체':>9}{'최근90일':>10}")
    table = {}
    for eq in EQ_GRID:
        a = pass_rate(all_s, eq); r = pass_rate(rec_s, eq)
        table[eq] = dict(all=a, recent=r)
        print(f"{eq:>8}{a*100:>8.1f}%{(r*100 if r is not None else float('nan')):>9.1f}%"
              + ("   ← 킬스위치(equity<$100) 전면 스킵" if eq < FLOOR else ""))
    by = {}
    for _, p, s in sc:
        by.setdefault(p, []).append(s)
    pat = {p: {eq: round(pass_rate(v, eq), 3) for eq in (160, 240, 355)} | {"n": len(v)} for p, v in by.items()}
    for p, d in sorted(pat.items()):
        print(f"  {p:<22} n={d['n']:>4} @160 {d[160]*100:5.1f}% @240 {d[240]*100:5.1f}% @355 {d[355]*100:5.1f}%")
    v = verdict(all_s, rec_s)
    print(f"[판정] {v}")
    json.dump(dict(verdict=v, table=table, need_quantiles=q, patterns=pat, n=len(all_s), n_recent=len(rec_s),
                   consts=dict(risk=sz.RISK_FRAC, lev=sz.LEV_CAP, stop=STOP, vol_s_norm=sz.VOL_S_NORM)),
              open("_minorder.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print("RESULT_JSON: " + json.dumps(dict(verdict=v, r100=table[100]["all"], r160=table[160]["all"],
          r240=table[240]["all"], r355=table[355]["all"], rec240=table[240]["recent"]), separators=(",", ":")))


if __name__ == "__main__":
    main()
