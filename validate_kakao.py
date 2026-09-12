"""
validate_kakao.py — 지인 카톡 규칙 3종 사전 등록 시험 (2026-09-12).

사전 등록: registry `kakao_patterns_prereg_2026_09_12` (원문·동결 파라미터·사전 확률).
**DEPLOY_ON_PASS=False** — 통과해도 실거래 반영 없음, 배포는 사용자 결정.

주 판정 6셀 = {ma3_breakout, yyb, yyy_plain} x {1d, 4h} · 롱 · 레짐 ALL · 코호트 top30.
  C1  게이트 v2 + **Holm m=6** 보정 boot_p
  C2  국면 홀드아웃 (frame_v3; ALL 셀이라 달력 365일)
  C2b train 자체 게이트 통과 AND train n >= holdout n/2
  C3  자산곡선 CAGR>0 & Calmar>0
판정 우선순위는 frame_v3 와 같게: 성능 실패 → REJECTED / 성능 통과·커버리지 실패 →
INCONCLUSIVE / 전부 → CONFIRMED.

진단(판정 아님, 사후 선택 금지): yyy strict/bottom/cross/close · 코호트 all ·
레짐 분해 · 왕복 마찰 0.4%.
"""
import json, sys, time
from datetime import date

import validate_revival as vr
import validate_regime_split_all as va
import regime_switch as rs
import frame_v3 as fv
import detector_ma3_breakout as d_ma3
import detector_yyb as d_yyb
import detector_yyy as d_yyy

DEPLOY_ON_PASS = False
TFS        = ("1d", "4h")
COHORT     = "top30"
REGIME     = "ALL"
DIRECTION  = "long"
FRICTION   = 0.004          # D5 왕복 마찰 스트레스
HOLDOUT_BY_TF = {"1d": 365, "4h": 365}

PRIMARY = [("ma3_breakout", lambda r: d_ma3.detect(r)),
           ("yyb",          lambda r: d_yyb.detect(r)),
           ("yyy_plain",    lambda r: d_yyy.detect(r, "plain"))]
DIAG_YYY = ["strict", "bottom", "cross", "close"]


def holm(pvals):
    """{key: p} → {key: 보정 p} (step-down). validate_tb_wide 와 같은 구현."""
    items = sorted((v, k) for k, v in pvals.items() if v is not None)
    m, out, run = len(items), {}, 0.0
    for r, (v, k) in enumerate(items):
        run = max(run, min(1.0, (m - r) * v))
        out[k] = run
    return out


def _f(v, w=8):
    return f"{'n/a':>{w}}" if v is None else f"{v*100:>+{w-1}.2f}%"


def judge(sigs, pool, regmap, equity_fn, p_adj):
    """frame_v3.judge 에 Holm 보정 p 를 얹는다 — 판정 우선순위는 v3 그대로."""
    cf = fv.judge(sigs, pool, regmap, REGIME, equity_fn=equity_fn)
    fails = [x for x in cf["c1"]["fails"] if not x.startswith("boot_p")]
    if p_adj is not None and p_adj >= 0.05:
        fails.append(f"Holm p={p_adj:.3f}")
    c1 = not fails
    if not (c1 and cf["c2_holdout"] and cf["c2b_train"] and cf["c3_equity"]):
        verdict = "REJECTED"
    elif not cf["coverage"]:
        verdict = "INCONCLUSIVE"
    elif not cf["E"]["ok"]:
        verdict = "REJECTED"
    else:
        verdict = "CONFIRMED"
    cf["holm_p"], cf["c1_fails"], cf["verdict_kakao"] = p_adj, fails, verdict
    return cf


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    tfs = argv[argv.index("--tf") + 1].split(",") if "--tf" in argv else list(TFS)
    long_1d = "--short" not in argv
    print(f"지인 카톡 규칙 3종 | 주 판정 {len(PRIMARY)}패턴 x {len(tfs)}TF = {len(PRIMARY)*len(tfs)}셀 "
          f"| 코호트 {COHORT} 레짐 {REGIME} {DIRECTION} | Holm m={len(PRIMARY)*len(tfs)} "
          f"| DEPLOY_ON_PASS={DEPLOY_ON_PASS}", flush=True)
    syms = va._syms()
    if "--no-fetch" not in argv:
        va.fetch(syms, [t for t in ("1d", "4h") if t in tfs or t == "1d"])
    rows_1d = va.load_tf(syms, "1d", long=long_1d)
    regmap = rs.build_regime_map(rows_by=rows_1d) if long_1d else rs.build_regime_map()
    if long_1d:
        print(f"[long] 1d 장기 이력 — 최초 {min(r[0]['date'] for r in rows_1d.values())} "
              f"· 레짐 라벨 {min(regmap)}~{max(regmap)}")
    ranked = vr.turnover_rank(rows_1d)
    out = dict(frame="kakao", deploy_on_pass=DEPLOY_ON_PASS, cells={}, diag={})

    ctx, raw = {}, {}
    for tf in tfs:
        t0 = time.time()
        rows_by = rows_1d if tf == "1d" else va.load_tf(syms, tf)
        rows_by = {s: r for s, r in rows_by.items() if len(r) > 60}
        cs = set(s for s in ranked[:30] if s in rows_by)
        cohorts = {"all": set(rows_by), "top30": cs}
        pools, atrs = vr.build_context(tf, rows_by, cohorts, regmap)
        first = min(r[0]["date"] for r in rows_by.values())
        last = max(r[-1]["date"] for r in rows_by.values())
        cut = date.fromordinal(date.fromisoformat(last).toordinal() - HOLDOUT_BY_TF[tf]).isoformat()
        span = max(1, date.fromisoformat(cut).toordinal() - date.fromisoformat(first).toordinal())
        pool = {c: vr.eval_pool(tf, pools[(c, REGIME)], rows_by, atrs, regmap, DIRECTION)
                for c in ("top30", "all")}
        ctx[tf] = dict(rows_by=rows_by, cs=cs, atrs=atrs, pool=pool, pools=pools,
                       cohorts=cohorts, cutoff=cut, span=span)
        print(f"[{tf}] 종목 {len(rows_by)} · top30 {len(cs)} · train {first}~{cut} "
              f"· holdout {HOLDOUT_BY_TF[tf]}일 · 풀 {len(pool['top30'])}건 ({time.time()-t0:.0f}s)", flush=True)

        for pid, fn in PRIMARY:
            t1 = time.time()
            by_sym = vr.collect(tf, fn, DIRECTION, rows_by, atrs, regmap)
            sigs = [x for s in cs for x in by_sym.get(s, [])]
            rec = vr.gate_cell(sigs, pool["top30"])
            raw[(pid, tf)] = dict(rec=rec, sigs=sigs, by_sym=by_sym)
            print(f"  [collect] {pid}@{tf}: top30 {len(sigs)}건 / 전체 "
                  f"{sum(len(v) for v in by_sym.values())}건 n={rec['n']} mean={_f(rec['mean'])} "
                  f"승률 {rec['win_rate']*100:.0f}% boot_p={rec['boot_p']:.3f} ({time.time()-t1:.0f}s)", flush=True)

    ph = holm({k: v["rec"]["boot_p"] for k, v in raw.items()})
    print(f"\n{'='*96}\n== 주 판정 (Holm m={len(raw)}) ==")
    for (pid, tf), r in raw.items():
        c = ctx[tf]
        cf = judge(r["sigs"], c["pool"]["top30"], regmap,
                   lambda tr, span: vr.equity(tr, span), ph.get((pid, tf)))
        rec, eq, ho, tr = r["rec"], cf["equity"] or {}, cf["holdout"], cf["train"]
        E = cf["E"]
        fric = [x["ret"] - FRICTION for x in r["sigs"]]
        fm = (sum(fric) / len(fric)) if fric else None
        print(f"\n  [{pid} @{tf}] n={rec['n']} mean={_f(rec['mean'])} med={_f(rec['median'])} "
              f"승률 {rec['win_rate']*100:.0f}% 엣지 {_f(rec['edge'])} top5 {(rec['top5_share'] or 0)*100:.0f}%")
        print(f"    boot_p={rec['boot_p']:.3f}→Holm {cf['holm_p']:.3f} | OOS {rec['oos_pos']}/4 "
              f"| E 적격 {E['qualifying']} 양수 {E['positive']} {E['ok']}")
        print(f"    C2 홀드아웃(국면 {ho['days']}일) n={ho['n']} {_f(ho['mean'])} {cf['c2_holdout']} "
              f"| C2b train n={tr['n']} {cf['c2b_train']} | C3 CAGR {_f(eq.get('cagr'))} "
              f"Calmar {eq.get('calmar', 0):.2f} {cf['c3_equity']} | COV {cf['coverage']}")
        print(f"    D5 마찰 0.4% 후 {_f(fm)} | 연도별 "
              + " ".join(f"{y}:{v['mean']*100:+.1f}%(n{v['n']})" for y, v in rec["by_year"].items()))
        print(f"    => **{cf['verdict_kakao']}**" + (f"  ({', '.join(cf['c1_fails'])})" if cf["c1_fails"] else ""))
        out["cells"][f"{pid}|{tf}"] = dict(
            pattern=pid, tf=tf, n=rec["n"], mean=rec["mean"], median=rec["median"],
            win_rate=rec["win_rate"], edge=rec["edge"], boot_p=rec["boot_p"], holm=cf["holm_p"],
            oos=rec["oos_pos"], holdout=ho, train_n=tr["n"], friction_mean=fm,
            equity=(eq and {k: eq[k] for k in ("cagr", "mdd", "calmar", "final")}),
            verdict=cf["verdict_kakao"], fails=cf["c1_fails"])

    # ── 진단 (판정 아님) ────────────────────────────────────────────────
    print(f"\n{'='*96}\n== 진단 — 사후에 여기서 골라 '살았다' 고 하지 않는다 ==")
    print("\n[D1] 양양양 변형 (strict=배포조건 / bottom=바닥필터 / cross=MA크로스 / close=배포판 진입)")
    for tf in tfs:
        c = ctx[tf]
        for mode in DIAG_YYY:
            by_sym = vr.collect(tf, (lambda r, m=mode: d_yyy.detect(r, m)), DIRECTION,
                                c["rows_by"], c["atrs"], regmap)
            sg = [x for s in c["cs"] for x in by_sym.get(s, [])]
            rc = vr.gate_cell(sg, c["pool"]["top30"])
            print(f"  {tf} yyy_{mode:<6} n={rc['n']:>5} mean={_f(rc['mean'])} 승률 {rc['win_rate']*100:>3.0f}% "
                  f"엣지 {_f(rc['edge'])} boot_p={rc['boot_p']:.3f} OOS {rc['oos_pos']}/4", flush=True)
            out["diag"][f"yyy_{mode}|{tf}"] = dict(n=rc["n"], mean=rc["mean"], win_rate=rc["win_rate"],
                                                   edge=rc["edge"], boot_p=rc["boot_p"], oos=rc["oos_pos"])

    print("\n[D2] 코호트 all 대비 (주 판정은 top30)")
    for (pid, tf), r in raw.items():
        sg = [x for v in r["by_sym"].values() for x in v]
        rc = vr.gate_cell(sg, ctx[tf]["pool"]["all"])
        print(f"  {pid:<13} {tf} all n={rc['n']:>5} mean={_f(rc['mean'])} 엣지 {_f(rc['edge'])} "
              f"boot_p={rc['boot_p']:.3f}")
        out["diag"][f"{pid}|{tf}|all"] = dict(n=rc["n"], mean=rc["mean"], edge=rc["edge"], boot_p=rc["boot_p"])

    print("\n[D3] 레짐 분해 (주 판정은 ALL) — 원문 '양양음은 우상향에서 유효' / '양양양은 바닥에서'")
    for (pid, tf), r in raw.items():
        c = ctx[tf]
        line = []
        for g in ("bull_btc", "bull_altseason", "bear"):
            pk = (COHORT, g)
            if pk not in c.setdefault("gpool", {}):
                c["gpool"][pk] = vr.eval_pool(tf, c["pools"][pk], c["rows_by"], c["atrs"], regmap, DIRECTION)
            sg = [x for x in r["sigs"] if x["regime"] == g]
            rc = vr.gate_cell(sg, c["gpool"][pk])
            line.append(f"{g} n={rc['n']} {_f(rc['mean'],7)} 엣지{_f(rc['edge'],7)}")
            out["diag"][f"{pid}|{tf}|{g}"] = dict(n=rc["n"], mean=rc["mean"], edge=rc["edge"])
        print(f"  {pid:<13} {tf} | " + " | ".join(line), flush=True)

    conf = [k for k, v in out["cells"].items() if v["verdict"] == "CONFIRMED"]
    inc = [k for k, v in out["cells"].items() if v["verdict"] == "INCONCLUSIVE"]
    print(f"\n{'='*96}\n판정: CONFIRMED {len(conf)} {conf} / INCONCLUSIVE {len(inc)} {inc} "
          f"/ REJECTED {len(out['cells'])-len(conf)-len(inc)}")
    print(f"DEPLOY_ON_PASS={DEPLOY_ON_PASS} — 통과해도 실거래 반영 없음(배포는 사용자 결정)")
    json.dump(out, open("kakao_result.json", "w"), ensure_ascii=False, indent=1)
    print("→ kakao_result.json")
    return out


if __name__ == "__main__":
    main()
