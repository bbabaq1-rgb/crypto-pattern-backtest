"""
validate_pit_cohort.py — point-in-time(당시 알 수 있던) 코호트로 v4 결과 재검증 (2026-09-06 사전 등록, 사용자 지시)

## 왜

검증 코호트(top20/top30)는 **데이터 마지막 시점의 30일 거래대금 순위**를 과거 전체에 소급한 정적 집합이었다 —
미래 정보 사용 + 살아남은 코인 선택. 실거래는 매 실행 순위를 다시 계산하므로 rolling 인데 검증만 정적이었다.
사용자 제시 의견("시총 우선 → 유동성 우선 rolling universe, survivorship·룩어헤드 회피, 코인별 엣지 분산")을
'검증 코호트의 룩어헤드' 하나로 좁혀 시험한다. registry `pit_cohort_prereg_2026_09_06` 과 같은 내용.

## 코호트 구성 (동결)

  · 매월 말 M 에 코인별 최근 RANK_WINDOW(30) 일봉 평균 거래대금(close×volume)으로 순위 → **다음 달 M+1 의 모든 봉에 적용**
  · 적격: 월말 기준 일봉 이력 >= MIN_HISTORY(60). 미달 코인은 그 달 어떤 코호트에도 없음
  · core20 = 1~20 / top30 = 1~30 (실거래 engulfing·fvg 복제) / liquid = 적격 전부 / mid = 21~ (진단) / majors = 고정 7종
  · 신호와 A 풀 봉 모두 '그 봉의 달에 그 코인이 코호트에 있었는가'로 판정. B 벤치(같은 코인·같은 달)는 코호트 무관 — 불변

## 지표 (동결)

  · v4 11셀을 정적 코호트와 PIT 코호트로 각각 계산(v4 규칙 전부, Holm 은 각 가족 안에서) → 판정 두 벌
  · STABLE = PIT 판정 == 정적 판정 AND 전체 A 엣지 부호 동일, 아니면 SHIFTED
  · 코인별 분산: 코인 평균수익(n>=3) 중앙값 / 양수 코인 비율 / 기여 상위 3 코인 제외 후 평균·A 엣지 / 왕복 0.4% 후 평균
  · 진단: engulfing·fvg 라우팅 셀의 core20 / mid 판 · 무조건부(ALL) 코호트 스캔 static vs PIT · OKX 구간(2022-01~)만의 A 엣지

**배포 판정 아님** — PIT 에서 CONFIRMED 가 새로 나와도 자율 반영 없음(관찰 기간 + 사용자 결정). DEPLOY_ON_PASS=False.
한계(실행 전 기록): 상장폐지 코인 이력 없음(생존 편향 잔존) · 스프레드 이력 없음 · OKX 상장 전 구간은 타 거래소 거래량.

실행: python validate_pit_cohort.py [--no-fetch] [--tf 1d,4h]      출력: _pit_cohort.json + RESULT_JSON
"""
import bisect
import json
import random
import statistics as st
import sys
import time

import regime_switch as rs
import validate_guard_v4 as g4
import validate_regime_split_all as va
import validate_revival as vr
from validate_regime_split import turnover_rank

# ── 동결 파라미터 (registry pit_cohort_prereg_2026_09_06 와 동일) ─────────────────────────────
RANK_WINDOW = 30
MIN_HISTORY = 60
COHORT_BOUNDS = {"core20": (1, 20), "top30": (1, 30), "liquid": (1, 10**9), "mid": (21, 10**9)}
OKX_FROM = "2022-01-01"            # 진단: OKX 거래량 구간
DEPLOY_ON_PASS = False
SEED, POOL_CAP = g4.SEED, vr.POOL_CAP
MAJORS = g4.MAJORS
DIAG_PATTERNS = ("engulfing", "engulfing_short", "fvg")   # core20 / mid 진단 대상 (라우팅 셀)
SCAN = [("engulfing", "detector_engulfing", "long"), ("fvg", "detector_fvg", "long")]


# ── PIT 코호트 ───────────────────────────────────────────────────────────────────────────────
def pit_membership(rows_1d, window=RANK_WINDOW, min_hist=MIN_HISTORY):
    """{적용월 'YYYY-MM': {sym: rank}} — 월 M 말 순위를 M 의 다음 달에 적용. 첫 달은 없음."""
    months = sorted({r["date"][:7] for rows in rows_1d.values() for r in rows})
    dates_by = {s: [r["date"] for r in rows] for s, rows in rows_1d.items()}
    out = {}
    for k in range(len(months) - 1):
        m, nxt = months[k], months[k + 1]
        scores = []
        for s, rows in rows_1d.items():
            ds = dates_by[s]
            i = bisect.bisect_right(ds, m + "-31") - 1          # m 의 마지막 봉
            if i < 0 or ds[i][:7] != m or i + 1 < min_hist:
                continue
            seg = rows[max(0, i - window + 1):i + 1]
            tv = sum(r["c"] * r["v"] for r in seg) / len(seg)
            if tv > 0:
                scores.append((tv, s))
        scores.sort(reverse=True)
        out[nxt] = {s: rank + 1 for rank, (_, s) in enumerate(scores)}
    return out


def in_cohort(pm, cname, sym, date_):
    if cname == "majors":
        return sym in MAJORS
    r = pm.get(date_[:7], {}).get(sym)
    if r is None:
        return False
    lo, hi = COHORT_BOUNDS[cname]
    return lo <= r <= hi


def cohort_turnover(pm, cname):
    """월별 코호트 구성 변화 — (평균 진입+이탈 코인 수, 월 수)."""
    ms = sorted(pm)
    prev, changes = None, []
    for m in ms:
        cur = {s for s in pm[m] if in_cohort(pm, cname, s, m + "-01")}
        if prev is not None:
            changes.append(len(cur ^ prev))
        prev = cur
    return (st.mean(changes) if changes else None), len(ms)


def pit_pool(oc, syms, pm, cname, regime, seed=SEED):
    """PIT 코호트·레짐 조건의 A 풀 (상한 POOL_CAP) → [(date, ret)]."""
    idx = []
    for s in syms:
        rows = oc.rows_by[s]
        for i in range(30, len(rows) - g4.MAX_HOLD - 1):
            d = rows[i]["date"]
            if regime != "ALL" and oc.regmap.get(d) != regime:
                continue
            if in_cohort(pm, cname, s, d):
                idx.append((s, i))
    if len(idx) > POOL_CAP:
        idx = random.Random(seed).sample(idx, POOL_CAP)
    return g4.pool_with_dates(oc, idx)


def pit_filter(sigs, pm, cname):
    return [s for s in sigs if in_cohort(pm, cname, s["sym"], s["date"])]


# ── 코인별 분산 ───────────────────────────────────────────────────────────────────────────────
def per_coin(sigs, pool_rets, min_n=3, drop_top=3):
    by = {}
    for s in sigs:
        by.setdefault(s["sym"], []).append(s["ret"])
    means = {c: st.mean(v) for c, v in by.items() if len(v) >= min_n}
    contrib = sorted(((sum(v), c) for c, v in by.items()), reverse=True)
    dropped = {c for _, c in contrib[:drop_top]}
    rem = [s for s in sigs if s["sym"] not in dropped]
    a_rem = g4.a_stats(rem, pool_rets) if rem else dict(mean=None, edge=None, n=0)
    mean_all = st.mean(s["ret"] for s in sigs) if sigs else None
    return dict(coins=len(by), coins_n3=len(means),
                coin_median=(st.median(means.values()) if means else None),
                coin_pos_share=(sum(1 for v in means.values() if v > 0) / len(means) if means else None),
                dropped=sorted(dropped), n_after_drop=len(rem), mean_after_drop=a_rem["mean"], edge_after_drop=a_rem["edge"],
                mean_cost04=g4.mean_at_fee(mean_all, 0.004))


def stability(static_v, pit_v, static_edge, pit_edge):
    if static_edge is None or pit_edge is None:
        return "SHIFTED"
    same_sign = (static_edge > 0) == (pit_edge > 0)
    return "STABLE" if (static_v == pit_v and same_sign) else "SHIFTED"


def _f(v, w=8):
    return f"{'n/a':>{w}}" if v is None else f"{v*100:>+{w-1}.2f}%"


def _p(v):
    return "  n/a" if v is None else f"{v:.3f}"


def judge_family(results):
    """Holm 을 가족 안에서 적용해 판정. results: {cid: rec}."""
    fam = {k: v["oos_b"]["p_nw"] for k, v in results.items()
           if v["oos_a"]["n"] >= g4.OOS_MIN_N and v["oos_b"]["months"] >= g4.B_MIN_MONTHS and v["oos_b"]["p_nw"] is not None}
    adj = g4.holm(fam)
    for k, v in results.items():
        vd, fails = g4.verdict(v["full_a"], v["train_gate"]["verdict"] == "PASSED", v["train_b"], v["oos_a"], v["oos_b"], adj.get(k), v["oos_a"]["mean"])
        v["p_holm"], v["verdict"], v["fails"] = adj.get(k), vd, fails
    return len(fam)


def _line(tag, rec):
    a, o, b = rec["full_a"], rec["oos_a"], rec["oos_b"]
    return (f"  {tag:<7} n={rec['n']:>5} (tr {rec['n_train']:>4}/oos {rec['n_oos']:>4}) | A full {_f(a['mean'])} 엣지 {_f(a['edge'])} bp {_p(a['boot_p'])} "
            f"| A OOS {_f(o['mean'])} 엣지 {_f(o['edge'])} bp {_p(o['boot_p'])} | B OOS {_f(b['nw'])} p {_p(b['p_nw'])} Holm {_p(rec.get('p_holm'))} "
            f"| train B {_f(rec['train_b']['nw'])} p {_p(rec['train_b']['p_nw'])} → **{rec.get('verdict', '')}** {'/'.join(rec.get('fails', []))}")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    tfs = argv[argv.index("--tf") + 1].split(",") if "--tf" in argv else ["1d", "4h"]
    syms = va._syms()
    print(f"PIT 코호트 재검증 | 리밸런스 월말 · 순위 창 {RANK_WINDOW}일 · 적격 {MIN_HISTORY}봉 · 코호트 {COHORT_BOUNDS} | DEPLOY_ON_PASS={DEPLOY_ON_PASS}")
    if "--no-fetch" not in argv:
        va.fetch(syms, tfs)
    rows_1d = va.load_tf(syms, "1d", long=True)
    regmap = rs.build_regime_map(rows_by=rows_1d)
    ranked = turnover_rank(rows_1d)
    static_syms = {"top30": ranked[:30], "core20": ranked[:20], "all": list(rows_1d), "liquid": list(rows_1d), "mid": ranked[20:], "majors": [s for s in MAJORS if s in rows_1d]}
    pm = pit_membership(rows_1d)
    first_1d = min(r["date"] for rows in rows_1d.values() for r in rows)
    last_1d = max(r["date"] for rows in rows_1d.values() for r in rows)
    print(f"[data] 1d {len(rows_1d)}종목 {first_1d}~{last_1d} | PIT 적용월 {min(pm)}~{max(pm)} ({len(pm)}개월)")
    for cname in ("core20", "top30", "liquid"):
        chg, nm = cohort_turnover(pm, cname)
        sizes = [sum(1 for s in pm[m] if in_cohort(pm, cname, s, m + '-01')) for m in sorted(pm)]
        print(f"  [PIT {cname:<6}] 월평균 구성 변화 {chg:.1f}코인 | 크기 최소/중앙/최대 {min(sizes)}/{int(st.median(sizes))}/{max(sizes)}")
    # 정적 top30 vs 최근 PIT top30 겹침
    last_m = max(pm)
    pit_last = {s for s in pm[last_m] if in_cohort(pm, "top30", s, last_m + "-01")}
    print(f"  [정적 top30 vs PIT {last_m} top30] 겹침 {len(pit_last & set(static_syms['top30']))}/30")

    rows_tf = {"1d": rows_1d}
    if "4h" in tfs:
        rows_tf["4h"] = va.load_tf(syms, "4h")
    oc_cache = {}

    def oc_for(tf, d):
        if (tf, d) not in oc_cache:
            oc_cache[(tf, d)] = g4.Outcomes(tf, rows_tf[tf], regmap, d)
        return oc_cache[(tf, d)]

    def first_of(tf):
        return first_1d if tf == "1d" else min(r["date"] for rows in rows_tf[tf].values() for r in rows)

    static_res, pit_res, diag_cm, sigs_all = {}, {}, {}, {}
    static_pool_cache, pit_pool_cache = {}, {}
    for cell in g4.CELLS:
        tf, coh, g, d = cell["tf"], cell["cohort"], cell["regime"], cell["direction"]
        if tf not in tfs:
            continue
        oc = oc_for(tf, d)
        allsyms = list(rows_tf[tf])
        t0 = time.time()
        # 신호는 전 종목에서 한 번 수집 → 코호트별로 필터
        key = (cell["det"], tf, g, d)
        if key not in sigs_all:
            sigs_all[key] = g4.collect_cell(oc, g4._det(cell["det"]), allsyms, g)
        sigs = sigs_all[key]
        # 정적
        cs_static = [s for s in static_syms[coh] if s in rows_tf[tf]]
        sk = (tf, coh, g, d)
        if sk not in static_pool_cache:
            idx, _ = vr.build_context(tf, {s: rows_tf[tf][s] for s in cs_static}, {coh: set(cs_static)}, regmap)
            static_pool_cache[sk] = g4.pool_with_dates(oc, idx[(coh, g)])
        st_sigs = [s for s in sigs if s["sym"] in set(cs_static)]
        rec_s = g4.run_cell(cell, oc, cs_static, static_pool_cache[sk], first_of(tf), last_1d, sigs=st_sigs)
        # PIT
        pcoh = {"top30": "top30", "all": "liquid", "majors": "majors"}[coh]
        pk = (tf, pcoh, g, d)
        if pk not in pit_pool_cache:
            pit_pool_cache[pk] = pit_pool(oc, allsyms, pm, pcoh, g)
        p_sigs = pit_filter(sigs, pm, pcoh)
        rec_p = g4.run_cell(cell, oc, allsyms, pit_pool_cache[pk], first_of(tf), last_1d, sigs=p_sigs)
        for rec, pool in ((rec_s, static_pool_cache[sk]), (rec_p, pit_pool_cache[pk])):
            pr = [r for _, r in pool]
            rec["per_coin"] = dict(full=per_coin([s for s in (st_sigs if rec is rec_s else p_sigs)], pr),
                                   train=per_coin([s for s in (st_sigs if rec is rec_s else p_sigs) if s["date"] < g4.SPLIT_DATE], [r for dt, r in pool if dt < g4.SPLIT_DATE]),
                                   oos=per_coin([s for s in (st_sigs if rec is rec_s else p_sigs) if s["date"] >= g4.SPLIT_DATE], [r for dt, r in pool if dt >= g4.SPLIT_DATE]))
        # OKX 구간 진단 (2022-01~): A 엣지만
        okx_s = [s for s in st_sigs if s["date"] >= OKX_FROM]; okx_p = [s for s in p_sigs if s["date"] >= OKX_FROM]
        rec_s["okx_a"] = g4.a_stats(okx_s, [r for dt, r in static_pool_cache[sk] if dt >= OKX_FROM])
        rec_p["okx_a"] = g4.a_stats(okx_p, [r for dt, r in pit_pool_cache[pk] if dt >= OKX_FROM])
        for rec in (rec_s, rec_p):
            rec.pop("sigs_oos", None)
        static_res[cell["cid"]], pit_res[cell["cid"]] = rec_s, rec_p
        # 진단: core20 / mid (라우팅 셀만, 1d)
        if cell["pattern"] in DIAG_PATTERNS and tf == "1d":
            diag_cm[cell["cid"]] = {}
            for cn in ("core20", "mid"):
                dk = (tf, cn, g, d)
                if dk not in pit_pool_cache:
                    pit_pool_cache[dk] = pit_pool(oc, allsyms, pm, cn, g)
                ds_ = pit_filter(sigs, pm, cn)
                r_ = g4.run_cell(cell, oc, allsyms, pit_pool_cache[dk], first_of(tf), last_1d, sigs=ds_)
                r_.pop("sigs_oos", None)
                diag_cm[cell["cid"]][cn] = r_
        print(f"[{cell['cid']}] {tf} 정적 {coh} n={rec_s['n']} / PIT {pcoh} n={rec_p['n']} ({time.time()-t0:.0f}s)", flush=True)

    m_s, m_p = judge_family(static_res), judge_family(pit_res)
    for dd in diag_cm.values():
        judge_family(dd)   # 진단 셀은 자체 가족(코호트 2개) — 판정 참고용

    print("\n" + "=" * 130)
    print(f"[판정 두 벌] 정적 Holm m={m_s} / PIT Holm m={m_p}")
    summary = {}
    for cid in static_res:
        s_, p_ = static_res[cid], pit_res[cid]
        stab = stability(s_["verdict"], p_["verdict"], s_["full_a"]["edge"], p_["full_a"]["edge"])
        summary[cid] = dict(static=s_["verdict"], pit=p_["verdict"], stability=stab, n_static=s_["n"], n_pit=p_["n"],
                            edge_static=s_["full_a"]["edge"], edge_pit=p_["full_a"]["edge"],
                            oos_static=s_["oos_a"]["mean"], oos_pit=p_["oos_a"]["mean"],
                            b_oos_static=s_["oos_b"]["nw"], b_oos_pit=p_["oos_b"]["nw"],
                            okx_edge_static=s_["okx_a"]["edge"], okx_edge_pit=p_["okx_a"]["edge"])
        print(f"\n[{cid}] ({static_res[cid]['cell']['status']}) → {stab}")
        print(_line("static", s_)); print(_line("PIT", p_))
        for nm, rec in (("static", s_), ("PIT", p_)):
            pc = rec["per_coin"]["full"]; po = rec["per_coin"]["oos"]
            print(f"    {nm:<6} 코인별(full) n3코인 {pc['coins_n3']:>3} 중앙 {_f(pc['coin_median'])} 양수 {(pc['coin_pos_share'] or 0)*100:3.0f}% | 상위3 제외 평균 {_f(pc['mean_after_drop'])} 엣지 {_f(pc['edge_after_drop'])} ({pc['dropped']}) "
                  f"| OOS 코인 중앙 {_f(po['coin_median'])} 양수 {(po['coin_pos_share'] or 0)*100:3.0f}% 상위3제외 엣지 {_f(po['edge_after_drop'])} | OKX구간 엣지 {_f(rec['okx_a']['edge'])}(n{rec['okx_a']['n']})")
        if cid in diag_cm:
            for cn, r_ in diag_cm[cid].items():
                print(_line(f"·{cn}", r_))

    # ── 무조건부 코호트 스캔 static vs PIT ─────────────────────────────────────────────────────
    print("\n" + "=" * 130)
    print("[진단] 무조건부(ALL 레짐) 코호트 스캔 — 게이트 v2, k=n 같은 코호트 풀. static vs PIT")
    scan = {}
    oc = oc_for("1d", "long")
    allsyms = list(rows_1d)
    for pat, det, d in SCAN:
        key = (det, "1d", "ALL", d)
        if key not in sigs_all:
            sigs_all[key] = g4.collect_cell(oc, g4._det(det), allsyms, "ALL")
        sigs = sigs_all[key]
        scan[pat] = {}
        for cn in ("core20", "top30", "liquid", "mid"):
            cs = [s for s in static_syms[cn] if s in rows_1d]
            idx, _ = vr.build_context("1d", {s: rows_1d[s] for s in cs}, {cn: set(cs)}, regmap)
            sp = [r for _, r in g4.pool_with_dates(oc, idx[(cn, "ALL")])]
            gs = vr.gate_cell([s for s in sigs if s["sym"] in set(cs)], sp)
            dk = ("1d", cn, "ALL", d)
            if dk not in pit_pool_cache:
                pit_pool_cache[dk] = pit_pool(oc, allsyms, pm, cn, "ALL")
            pp = [r for _, r in pit_pool_cache[dk]]
            gp = vr.gate_cell(pit_filter(sigs, pm, cn), pp)
            scan[pat][cn] = dict(static=gs, pit=gp)
            print(f"  {pat:<10} {cn:<7} static n={gs['n']:>5} {_f(gs['mean'])} 엣지 {_f(gs['edge'])} bp {gs['boot_p']:.3f} {gs['verdict']:<8} | PIT n={gp['n']:>5} {_f(gp['mean'])} 엣지 {_f(gp['edge'])} bp {gp['boot_p']:.3f} {gp['verdict']}")

    counts = {}
    for v in summary.values():
        counts[v["stability"]] = counts.get(v["stability"], 0) + 1
    print("\n" + "=" * 130)
    print(f"[요약] STABLE {counts.get('STABLE', 0)} / SHIFTED {counts.get('SHIFTED', 0)} — 실거래 반영 없음(DEPLOY_ON_PASS={DEPLOY_ON_PASS})")
    for cid, v in summary.items():
        print(f"  {cid:<36} static {v['static']:<18} PIT {v['pit']:<18} {v['stability']:<8} n {v['n_static']}->{v['n_pit']} 엣지 {_f(v['edge_static'])}->{_f(v['edge_pit'])} OOS {_f(v['oos_static'])}->{_f(v['oos_pit'])}")
    out = dict(frame="pit_cohort", frozen=dict(rank_window=RANK_WINDOW, min_history=MIN_HISTORY, cohorts=COHORT_BOUNDS, okx_from=OKX_FROM),
               deploy_on_pass=DEPLOY_ON_PASS, months=len(pm), summary=summary, static=static_res, pit=pit_res, diag_core_mid=diag_cm, scan=scan)
    json.dump(out, open("_pit_cohort.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print("[저장] _pit_cohort.json")
    print("RESULT_JSON: " + json.dumps(dict(frame="pit_cohort", counts=counts, summary={k: dict(static=v["static"], pit=v["pit"], stability=v["stability"]) for k, v in summary.items()}), ensure_ascii=False))


if __name__ == "__main__":
    main()
