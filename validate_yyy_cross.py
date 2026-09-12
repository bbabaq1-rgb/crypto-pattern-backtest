"""
validate_yyy_cross.py — 양양양 + MA5xMA20 크로스 추격 시험 (2026-09-12).

사전 등록 registry `yyy_cross_prereg_2026_09_12`.
**이것은 사후 선택 셀의 추격이다** — kakao 판(run 34678062587) 진단에서 yyy_cross 가
변형 중 최고였고, 그 수치를 보고 이 셀을 골랐다. 그래서 확인 기준만으로는 부족하고
validate_ih_exit(2026-09-01) 선례대로 **반증 3종**을 붙인다.

주 판정 2셀 = yyy_cross x {1d, 4h} · 롱 · ALL · top30 · Holm m=2
  확인: C1 게이트 v2(+Holm) · C2 국면 홀드아웃(frame_v3) · C2b · C3 자산곡선
  반증: F1 걸러진 거래가 음수 (method_b 교훈) / F2 전후반 부호 유지 /
        F3 대조군 — 같은 크로스 필터를 다른 배포 패턴에 붙여도 비슷하면 '추세 필터' 일 뿐

**PASS = 확인 4 + 반증 3 전부.** DEPLOY_ON_PASS=False.
"""
import json, sys, time, random, statistics as stt
from datetime import date

import validate_revival as vr
import validate_regime_split_all as va
import regime_switch as rs
import frame_v3 as fv
import detector_kakao_base as kb
import detector_yyy as d_yyy
import detector_ma_cross as d_cross

DEPLOY_ON_PASS = False
TFS, COHORT, REGIME, DIRECTION = ("1d", "4h"), "top30", "ALL", "long"
FRICTION, SEED, BOOT_N = 0.004, 42, 1000
HOLDOUT_BY_TF = {"1d": 365, "4h": 365}

# F3 대조군 — 같은 조건(top30·ALL·롱)으로 통일해 붙인다. 실거래 라우팅 복제가 아니라
# '크로스 필터의 효과' 만 비교하는 것(사전 등록 known_limits).
CONTROLS = ["detector_engulfing", "detector_fvg", "detector_inverted_hammer", "detector_marubozu"]


def holm(pv):
    items = sorted((v, k) for k, v in pv.items() if v is not None)
    m, out, run = len(items), {}, 0.0
    for r, (v, k) in enumerate(items):
        run = max(run, min(1.0, (m - r) * v))
        out[k] = run
    return out


def _f(v, w=8):
    return f"{'n/a':>{w}}" if v is None else f"{v*100:>+{w-1}.2f}%"


def mean(xs):
    return (sum(xs) / len(xs)) if xs else None


def boot_ci(xs, seed=SEED, n=BOOT_N):
    """평균의 부트스트랩 95% CI."""
    if len(xs) < 5:
        return (None, None)
    rng = random.Random(seed)
    ms = sorted(stt.fmean(rng.choices(xs, k=len(xs))) for _ in range(n))
    return ms[int(0.025 * n)], ms[int(0.975 * n)]


def split_half(sigs):
    """달력 중점으로 전·후반 (validate_routing 교훈 — arm 별 중앙값이 아니라 달력 중점)."""
    if not sigs:
        return [], []
    ds = sorted(x["date"] for x in sigs)
    lo, hi = date.fromisoformat(ds[0]).toordinal(), date.fromisoformat(ds[-1]).toordinal()
    mid = date.fromordinal((lo + hi) // 2).isoformat()
    return [x for x in sigs if x["date"] < mid], [x for x in sigs if x["date"] >= mid]


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    tfs = argv[argv.index("--tf") + 1].split(",") if "--tf" in argv else list(TFS)
    long_1d = "--short" not in argv
    print(f"양양양 + MA5xMA20 크로스 — **사후 선택 셀 추격** | 주 판정 {len(tfs)}셀 "
          f"| {COHORT}·{REGIME}·{DIRECTION} | Holm m={len(tfs)} | DEPLOY_ON_PASS={DEPLOY_ON_PASS}")
    print("확인 C1/C2/C2b/C3 + 반증 F1(걸러진 거래 음수)/F2(전후반 부호)/F3(대조군) — **전부 통과해야 PASS**", flush=True)
    syms = va._syms()
    if "--no-fetch" not in argv:
        va.fetch(syms, [t for t in ("1d", "4h") if t in tfs or t == "1d"])
    rows_1d = va.load_tf(syms, "1d", long=long_1d)
    regmap = rs.build_regime_map(rows_by=rows_1d) if long_1d else rs.build_regime_map()
    ranked = vr.turnover_rank(rows_1d)
    out = dict(frame="yyy_cross", deploy_on_pass=DEPLOY_ON_PASS, cells={}, diag={})

    ctx, raw = {}, {}
    for tf in tfs:
        t0 = time.time()
        rows_by = rows_1d if tf == "1d" else va.load_tf(syms, tf)
        rows_by = {s: r for s, r in rows_by.items() if len(r) > 60}
        cs = set(s for s in ranked[:30] if s in rows_by)
        pools, atrs = vr.build_context(tf, rows_by, {"all": set(rows_by), "top30": cs}, regmap)
        first = min(r[0]["date"] for r in rows_by.values())
        last = max(r[-1]["date"] for r in rows_by.values())
        cut = date.fromordinal(date.fromisoformat(last).toordinal() - HOLDOUT_BY_TF[tf]).isoformat()
        span = max(1, date.fromisoformat(cut).toordinal() - date.fromisoformat(first).toordinal())
        pool = vr.eval_pool(tf, pools[(COHORT, REGIME)], rows_by, atrs, regmap, DIRECTION)
        # cross 는 plain 의 부분집합 — 같은 collect 에서 갈라야 F1 이 정확히 '걸러진 거래' 가 된다
        by_plain = vr.collect(tf, lambda r: d_yyy.detect(r, "plain"), DIRECTION, rows_by, atrs, regmap)
        by_cross = vr.collect(tf, lambda r: d_yyy.detect(r, "cross"), DIRECTION, rows_by, atrs, regmap)
        plain = [x for s in cs for x in by_plain.get(s, [])]
        cross = [x for s in cs for x in by_cross.get(s, [])]
        ck = {(x["sym"], x["date"]) for x in cross}
        dropped = [x for x in plain if (x["sym"], x["date"]) not in ck]
        ctx[tf] = dict(rows_by=rows_by, cs=cs, atrs=atrs, pool=pool, pools=pools,
                       cutoff=cut, span=span)
        raw[tf] = dict(cross=cross, plain=plain, dropped=dropped,
                       rec=vr.gate_cell(cross, pool), rec_plain=vr.gate_cell(plain, pool))
        print(f"[{tf}] 종목 {len(rows_by)} · top30 {len(cs)} · train {first}~{cut} "
              f"| plain {len(plain)} → cross {len(cross)} (걸러짐 {len(dropped)}) ({time.time()-t0:.0f}s)", flush=True)

    ph = holm({tf: raw[tf]["rec"]["boot_p"] for tf in tfs})
    print(f"\n{'='*96}\n== 주 판정 (Holm m={len(tfs)}) ==")
    for tf in tfs:
        r, c = raw[tf], ctx[tf]
        rec, rp = r["rec"], r["rec_plain"]
        cf = fv.judge(r["cross"], c["pool"], regmap, REGIME, equity_fn=lambda t, s: vr.equity(t, s))
        p_adj = ph.get(tf, 1.0)
        c1_fails = [x for x in cf["c1"]["fails"] if not x.startswith("boot_p")]
        if p_adj >= 0.05:
            c1_fails.append(f"Holm p={p_adj:.3f}")
        eq, ho, tr = cf["equity"] or {}, cf["holdout"], cf["train"]
        conf_ok = (not c1_fails) and cf["c2_holdout"] and cf["c2b_train"] and cf["c3_equity"]

        # ── 반증 ─────────────────────────────────────────────────────
        dm = mean([x["ret"] for x in r["dropped"]])
        f1 = dm is not None and dm < 0
        h1, h2 = split_half(r["cross"])
        m1, m2 = mean([x["ret"] for x in h1]), mean([x["ret"] for x in h2])
        f2 = m1 is not None and m2 is not None and m1 > 0 and m2 > 0
        lo, hi = boot_ci([x["ret"] for x in r["cross"]])
        gain = (rec["edge"] - rp["edge"]) if (rec["edge"] is not None and rp["edge"] is not None) else None

        print(f"\n  [{tf}] cross n={rec['n']} mean={_f(rec['mean'])} 승률 {rec['win_rate']*100:.0f}% "
              f"엣지 {_f(rec['edge'])} (plain 엣지 {_f(rp['edge'])}, 개선 {_f(gain)})")
        print(f"    C1 boot_p={rec['boot_p']:.3f}→Holm {p_adj:.3f} OOS {rec['oos_pos']}/4 "
              f"{'ok' if not c1_fails else '/'.join(c1_fails)}")
        print(f"    C2 홀드아웃 n={ho['n']} {_f(ho['mean'])} {cf['c2_holdout']} | C2b train n={tr['n']} "
              f"{cf['c2b_train']} | C3 CAGR {_f(eq.get('cagr'))} Calmar {eq.get('calmar',0):.2f} {cf['c3_equity']}")
        print(f"    **F1** 걸러진 거래 n={len(r['dropped'])} 평균 {_f(dm)} → {'통과(음수)' if f1 else '**탈락(양수 — 필터가 아니다)**'}")
        print(f"    **F2** 전반 {_f(m1)}(n{len(h1)}) / 후반 {_f(m2)}(n{len(h2)}) → {'통과' if f2 else '**탈락**'}")
        print(f"    부트 CI 95% [{_f(lo)}, {_f(hi)}] | D5 마찰 0.4% 후 {_f(mean([x['ret']-FRICTION for x in r['cross']]))}")
        out["cells"][tf] = dict(n=rec["n"], mean=rec["mean"], win_rate=rec["win_rate"],
                                edge=rec["edge"], plain_edge=rp["edge"], gain=gain,
                                boot_p=rec["boot_p"], holm=p_adj, oos=rec["oos_pos"],
                                holdout=ho, train_n=tr["n"], equity=(eq and {k: eq[k] for k in ("cagr","mdd","calmar")}),
                                conf_ok=conf_ok, c1_fails=c1_fails,
                                f1=f1, dropped_n=len(r["dropped"]), dropped_mean=dm,
                                f2=f2, first_half=m1, second_half=m2, ci=[lo, hi])

    # ── F3 대조군 ────────────────────────────────────────────────────
    print(f"\n{'='*96}\n== F3 대조군 — 같은 크로스 필터를 다른 배포 패턴에 붙인다 ==")
    print("   같은 폭으로 좋아지면 '양양양 + 크로스' 가 아니라 **그냥 상승 추세 필터**다.")
    import importlib
    for tf in tfs:
        c, gains = ctx[tf], {}
        for modname in CONTROLS:
            try:
                mod = importlib.import_module(modname)
            except Exception as e:
                print(f"  {tf} {modname} import 실패 {str(e)[:40]}"); continue
            by = vr.collect(tf, mod.detect, DIRECTION, c["rows_by"], c["atrs"], regmap)
            base = [x for s in c["cs"] for x in by.get(s, [])]
            # 같은 크로스 조건을 신호에 건다 — 신호 봉에서 cross_up 이 참인 것만
            keep = set()
            for s in c["cs"]:
                rws = c["rows_by"][s]
                di = {rws[i]["date"]: i for i in range(len(rws))}
                for x in by.get(s, []):
                    i = di.get(x["date"])
                    if i is not None and kb.cross_up(rws, i):
                        keep.add((s, x["date"]))
            filt = [x for x in base if (x["sym"], x["date"]) in keep]
            rb, rf = vr.gate_cell(base, c["pool"]), vr.gate_cell(filt, c["pool"])
            g = (rf["edge"] - rb["edge"]) if (rf["edge"] is not None and rb["edge"] is not None) else None
            gains[modname] = g
            nm = modname.replace("detector_", "")
            print(f"  {tf} {nm:<16} n {rb['n']:>5}→{rf['n']:>5} | 엣지 {_f(rb['edge'])}→{_f(rf['edge'])} "
                  f"개선 {_f(g)}", flush=True)
        gs = [v for v in gains.values() if v is not None]
        med = stt.median(gs) if gs else None
        yg = out["cells"][tf]["gain"]
        f3 = (yg is not None and med is not None and yg > med)
        print(f"  → {tf} 대조군 개선 중앙값 {_f(med)} vs yyy {_f(yg)} → F3 "
              f"{'통과 (양양양이 더 크다)' if f3 else '**탈락 (크로스는 아무 패턴에나 먹힌다)**'}")
        out["cells"][tf]["f3"] = f3
        out["cells"][tf]["control_median_gain"] = med
        out["diag"][f"controls|{tf}"] = gains

    # ── 진단: cross_only ─────────────────────────────────────────────
    print(f"\n== 진단 cross_only — 캔들 조건 없이 교차 봉 단독 진입 (판정 아님) ==")
    for tf in tfs:
        c = ctx[tf]
        by = vr.collect(tf, d_cross.detect, DIRECTION, c["rows_by"], c["atrs"], regmap)
        sg = [x for s in c["cs"] for x in by.get(s, [])]
        rc = vr.gate_cell(sg, c["pool"])
        print(f"  {tf} cross_only n={rc['n']:>5} mean={_f(rc['mean'])} 승률 {rc['win_rate']*100:>3.0f}% "
              f"엣지 {_f(rc['edge'])} bp={rc['boot_p']:.3f} | yyy_cross 엣지 {_f(out['cells'][tf]['edge'])}")
        out["diag"][f"cross_only|{tf}"] = dict(n=rc["n"], mean=rc["mean"], edge=rc["edge"],
                                               win_rate=rc["win_rate"], boot_p=rc["boot_p"])

    print(f"\n{'='*96}\n== 최종 ==")
    npass = 0
    for tf in tfs:
        v = out["cells"][tf]
        ok = v["conf_ok"] and v["f1"] and v["f2"] and v["f3"]
        v["verdict"] = "PASSED" if ok else "REJECTED"
        npass += ok
        fl = [k for k, t in (("확인", v["conf_ok"]), ("F1", v["f1"]), ("F2", v["f2"]), ("F3", v["f3"])) if not t]
        print(f"  {tf}: **{v['verdict']}**" + (f"  (탈락 {', '.join(fl)})" if fl else ""))
    print(f"\nPASSED {npass}/{len(tfs)} | DEPLOY_ON_PASS={DEPLOY_ON_PASS} — 통과해도 실거래 반영 없음")
    print("사후 선택 셀 추격이므로 **통과해도 '기각을 면했다' 이지 '발견했다' 가 아니다**(사전 등록 known_limits).")
    json.dump(out, open("yyy_cross_result.json", "w"), ensure_ascii=False, indent=1)
    print("→ yyy_cross_result.json")
    return out


if __name__ == "__main__":
    main()
