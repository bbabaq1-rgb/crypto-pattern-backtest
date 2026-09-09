"""
audit_guards.py — 확인 프레임 **가드 교정 감사** (2026-09-09, 사용자 지시 "가드 너무 엄한것 같으면
그걸 재점검해야지" / "전부 진행해봐").

── 문제 ────────────────────────────────────────────────────────────────────
확인 프레임이 9/05 이후 한 방향으로만 엄해졌다: 게이트 v2 → C2 홀드아웃 → C2b → C3 자산곡선 → PIT
코호트 → v3 에피소드 → v4 B 벤치·Holm. 각 층은 거짓양성 사례를 보고 추가됐고 **거짓음성 비용은 한 번도
재본 적이 없다**. 그 결과 v4 는 11셀 중 CONFIRMED 0 을 냈고 거기엔 **지금 실거래로 돌고 있는 셀**이
포함된다(engulfing|bear, fvg|bull_altseason, three_soldiers_4h|bull_altseason). engulf_tf 진단에서는
배포된 1d 참조 셀이 boot_p .090 으로 게이트를 못 넘었다.

실제로 돈을 벌고 있는 규칙까지 기각하는 프레임이라면, 전략이 약한 게 아니라 잣대가 어긋난 것이다.

── 이 감사가 하는 것 ─────────────────────────────────────────────────────────
실거래 중인 셀 전부에 **가드 층을 하나씩 독립적으로** 걸어 어느 층이 기각을 만드는지 분해한다.
같은 신호 집합 위에서 층마다 pass/fail 을 따로 계산하므로 귀속이 깨끗하다.

층(역사적 추가 순서):
  L1  게이트 v2 (n≥20·평균>0·승률≥35%·k=n boot_p<.05·OOS 4분위 ≥2)   — 2026-09-05
  L2  달력 홀드아웃 (마지막 365일 / 4h 365 / 1h 90, n≥10 & mean>0)       — revival C2
  L3  C2b (train 자체 게이트 통과 & train n ≥ holdout n/2)              — ma180
  L4  C3 자산곡선 (train CAGR>0 & Calmar>0, 실거래 사이징)              — revival
  L5  PIT 코호트 (정적 top30 → 월말 순위 PIT 로 재필터 후 L1 재판정)     — pit_cohort
  L6  v3 국면 홀드아웃 (그 레짐으로 라벨된 최근 365일, 비연속)            — frame_v3
  L7  E 에피소드 OOS (적격 에피소드 ≥2, 양수 ≥2 이며 과반)                — frame_v3
  L8  B 벤치 (같은 코인·같은 달·같은 레짐 무작위 대비, 월 클러스터 부트 p<.05 & 세 가중>0) — guard_v4
  L9  Holm (L1 의 boot_p 를 가족 크기 m 로 보정)                          — guard_v4 / 이후 전부

기준 참조(ground truth 대용): **OOS(2025-01-01~) 실측 건당** — 프레임이 만들어진 뒤의 구간이라
프레임 설계에 쓰이지 않았다. OOS 건당>0 인데 어떤 층이 기각하면 그 층은 거짓음성 후보다.
(OOS 가 짧고 bear 지배라 이것도 완전한 정답은 아니다 — 방향 참조로만 쓴다.)

── 출력 ────────────────────────────────────────────────────────────────────
① 셀 × 층 행렬(O/X) + OOS 건당
② 층별 기각 수 / **단독 기각 수**(다른 층은 다 통과하는데 이 층만 X) / OOS 양수 셀 중 기각 수(= 거짓음성 후보)
③ **누적 통과 곡선** — 층을 역사 순서로 하나씩 얹었을 때 통과 셀 수가 어떻게 줄었나(래칫 시각화)
④ 의심 층 셋에 대한 직접 답:
   · B 벤치 — "신호 이후 봉까지 포함해 사후 조건화" 라고 기록해놓고 판정 기준으로 쓴 층. 인과 판(신호
     **이전** 봉만) 을 병기해 차이를 잰다.
   · Holm — 셀들이 독립 가설이 아닌데(같은 패턴의 레짐·TF 분해) 가족으로 보정. m=1/4/8/12 에서 판정이
     어떻게 바뀌는지.
   · 소표본 4중 처벌 — L1 boot_p·L2·L3·L7 이 n 하나로 함께 떨어지는 셀이 몇 개인지.

**문턱을 바꾸지 않는다.** 이 스크립트는 측정만 한다. 어느 층을 완화·제거할지는 사용자 결정(CLAUDE.md:
게이트 문턱 변경은 사용자 결정). DEPLOY_ON_PASS 개념 없음 — 실거래·DB 무관.

실행: python audit_guards.py [--no-fetch] [--tf 1d,4h]
출력 _audit_guards.json + RESULT_JSON.
"""
import json
import statistics as st
import sys
import time
from datetime import date

import frame_v3 as f3
import regime_switch as rs
import validate_guard_v4 as g4
import validate_pit_cohort as pc
import validate_regime_split_all as va
import validate_revival as vr
from validate_regime_split import turnover_rank

SPLIT = g4.SPLIT_DATE                     # OOS 참조 구간 시작 2025-01-01
HOLDOUT_BY_TF = vr.HOLDOUT_DAYS_BY_TF     # 1d/4h 365, 1h 90
LAYERS = ["L1_gate_v2", "L2_holdout_cal", "L3_c2b", "L4_c3_equity", "L5_pit",
          "L6_holdout_regime", "L7_episode", "L8_bench_B", "L9_holm"]
HOLM_FAMILIES = (1, 4, 8, 12)

# 감사 대상 = 실거래 라우팅 셀(guard_v4 deployed) + 4h adopted 3종 + 관찰 2셀
CELLS = [c for c in g4.CELLS if c["status"] in ("deployed", "observation")] + [
    dict(cid="triple_bottom_4h|ALL",  pattern="triple_bottom_4h",  det="detector_triple_bottom",     tf="4h", cohort="top30", regime="ALL", direction="long", status="deployed"),
    dict(cid="equal_lows_4h|ALL",     pattern="equal_lows_4h",     det="detector_equal_lows_4h",     tf="4h", cohort="top30", regime="ALL", direction="long", status="deployed"),
    dict(cid="vol_awakening_4h|ALL",  pattern="vol_awakening_4h",  det="detector_vol_awakening_4h",  tf="4h", cohort="top30", regime="ALL", direction="long", status="deployed"),
]


def _mean(xs):
    return st.mean(xs) if xs else None


def _pct(x, d=2, suffix="%"):
    return "-" if x is None else f"{x*100:+.{d}f}{suffix}"


def _pv(x):
    return "-" if x is None else f"{x:.3f}"


def cal_holdout_set(regmap, first, last, days):
    cut = date.fromordinal(date.fromisoformat(last).toordinal() - days).isoformat()
    return {d for d in regmap if first <= d <= last and d > cut}


def layer_flags(cell, sigs, pool_rets, regmap, first, last, oc, pm, pool_pit_rets):
    """한 셀의 층별 pass/fail + 근거. 모든 층은 같은 sigs 위에서 독립 계산."""
    tf, g = cell["tf"], cell["regime"]
    days = HOLDOUT_BY_TF[tf]
    out, why = {}, {}

    # L1 게이트 v2 (전체 신호, 레짐·코호트 k=n 풀)
    gt = vr.gate_cell(sigs, pool_rets)
    out["L1_gate_v2"] = gt["verdict"] == "PASSED"
    why["L1_gate_v2"] = gt["reason"] or "ok"

    # L2 달력 홀드아웃
    hs_cal = cal_holdout_set(regmap, first, last, days)
    tr_c = [s for s in sigs if s["date"] not in hs_cal]
    ho_c = [s for s in sigs if s["date"] in hs_cal]
    m_ho = _mean([s["ret"] for s in ho_c])
    out["L2_holdout_cal"] = len(ho_c) >= f3.HOLDOUT_MIN_N and (m_ho or 0) > 0
    why["L2_holdout_cal"] = f"n={len(ho_c)} mean={_pct(m_ho)}"

    # L3 C2b (달력 분할 기준 — ma180/engulf_tf 가 쓴 정의)
    tr_gate = vr.gate_cell(tr_c, pool_rets) if tr_c else dict(verdict="REJECTED", reason="train 0")
    out["L3_c2b"] = tr_gate["verdict"] == "PASSED" and len(tr_c) >= max(1, len(ho_c) // 2)
    why["L3_c2b"] = f"train {tr_gate['verdict']} {tr_gate['reason'] or ''} n={len(tr_c)}/{len(ho_c)}"

    # L4 C3 자산곡선 (train, 실거래 사이징)
    span = max(1, len({s["date"] for s in tr_c}) if tr_c else 1)
    span = max(span, (date.fromisoformat(last).toordinal() - days) - date.fromisoformat(first).toordinal())
    eq = vr.equity(tr_c, span) if tr_c else None
    out["L4_c3_equity"] = bool(eq) and eq["cagr"] > 0 and eq["calmar"] > 0
    why["L4_c3_equity"] = ("-" if not eq else f"CAGR {eq['cagr']*100:+.1f}% Calmar {eq['calmar']:.2f}")

    # L5 PIT 코호트 — 정적 코호트 신호를 월별 PIT 순위로 재필터 후 L1 재판정
    if cell["cohort"] in pc.COHORT_BOUNDS and pm:
        sp = pc.pit_filter(sigs, pm, cell["cohort"])
        gp = vr.gate_cell(sp, pool_pit_rets or pool_rets)
        out["L5_pit"] = gp["verdict"] == "PASSED"
        why["L5_pit"] = f"n {len(sigs)}→{len(sp)} {gp['reason'] or 'ok'}"
    else:
        out["L5_pit"] = out["L1_gate_v2"]          # majors/all 은 PIT 개념 없음 → L1 과 동일
        why["L5_pit"] = "코호트 아님(L1 승계)"

    # L6 v3 국면 홀드아웃
    sub = {d: lab for d, lab in regmap.items() if first <= d <= last}
    hs_reg = f3.holdout_dates(sub, g, days=days)
    ho_r = [s for s in sigs if s["date"] in hs_reg]
    m_hr = _mean([s["ret"] for s in ho_r])
    out["L6_holdout_regime"] = len(ho_r) >= f3.HOLDOUT_MIN_N and (m_hr or 0) > 0
    why["L6_holdout_regime"] = f"n={len(ho_r)} mean={_pct(m_hr)}"

    # L7 에피소드 OOS
    eps = f3.episodes(sub, g)
    e_ok, e_q, e_pos, _ = f3.episode_oos(sigs, eps)
    out["L7_episode"] = bool(e_ok)
    why["L7_episode"] = f"적격 {e_q} 양수 {e_pos}"

    # L8 B 벤치 (train 구간, guard_v4 정의 그대로) + 인과 판 병기
    tr_b = [s for s in sigs if s["date"] < SPLIT]
    eb, ex = g4.b_edges(oc, tr_b)
    cb = g4.cluster_boot(eb)
    out["L8_bench_B"] = g4.b_ok(cb)
    why["L8_bench_B"] = f"n가중 {_pct(cb['nw'], suffix='%p')} p {_pv(cb['p_nw'])} 월 {cb['months']}"
    # 인과 B: 같은 코인·달 풀을 신호 **이전** 봉으로만 제한 (B 사후 조건화의 크기 측정)
    eb_c = causal_b_edges(oc, tr_b)
    cb_c = g4.cluster_boot(eb_c) if eb_c else dict(nw=None, p_nw=None, months=0)
    why["L8_causal_B"] = f"n가중 {_pct(cb_c['nw'], suffix='%p')} p {_pv(cb_c['p_nw'])}"
    out["L8_causal_B"] = g4.b_ok(cb_c) if eb_c else False

    # L9 Holm 은 가족 전체가 필요 — 여기선 raw p 만 남기고 main 에서 채운다
    out["_raw_p"] = gt["boot_p"]

    # OOS 참조
    oos = [s["ret"] for s in sigs if s["date"] >= SPLIT]
    out["_oos_n"], out["_oos_mean"] = len(oos), _mean(oos)
    out["_n"], out["_mean"], out["_win"] = gt["n"], gt["mean"], gt["win_rate"]
    return out, why


def causal_b_edges(oc, sigs, min_pool=g4.B_MIN_POOL):
    """B 벤치의 인과 변형 — 같은 코인·같은 달·같은 레짐 풀을 **신호 이전 봉**으로만 제한.
    현 B 는 신호 이후 봉까지 풀에 넣어 '그 달이 좋은 달'이라는 정보를 쓴다(사후 조건화, v4 결과에 기록).
    둘의 차이가 그 조건화의 크기다."""
    out = []
    for s in sigs:
        rows = oc.rows_by[s["sym"]]
        month, lab = s["month"], s["regime"]
        pool = []
        for j in range(30, s["i"]):                       # 신호 봉 이전만
            if rows[j]["date"][:7] != month:
                continue
            if oc.regmap.get(rows[j]["date"]) != lab:
                continue
            if not oc.eligible(s["sym"], j):
                continue
            r = oc.ret(s["sym"], j)
            if r is not None:
                pool.append(r)
        if len(pool) < min_pool:
            continue
        out.append(dict(sym=s["sym"], month=month, edge=s["ret"] - st.mean(pool)))
    return out


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    tfs = argv[argv.index("--tf") + 1].split(",") if "--tf" in argv else ["1d", "4h"]
    syms = va._syms()
    print(f"가드 교정 감사 — 실거래 셀 {len(CELLS)} × 층 {len(LAYERS)} | OOS 참조 {SPLIT}~ | 문턱 변경 없음(측정만)")
    if "--no-fetch" not in argv:
        va.fetch(syms, tfs)
    rows_1d = va.load_tf(syms, "1d", long=True)
    regmap = rs.build_regime_map(rows_by=rows_1d)
    ranked = turnover_rank(rows_1d)
    cohort_syms = {"top30": ranked[:30], "all": list(rows_1d), "majors": [s for s in g4.MAJORS if s in rows_1d]}
    pm = pc.pit_membership(rows_1d)
    rows_tf = {"1d": rows_1d}
    if "4h" in tfs:
        rows_tf["4h"] = va.load_tf(syms, "4h")
    print(f"[data] 1d {len(rows_1d)}종목 | 레짐 {min(regmap)}~{max(regmap)} | PIT 월 {len(pm)}")

    oc_cache, pool_cache = {}, {}

    def oc_for(tf, d):
        k = (tf, d)
        if k not in oc_cache:
            oc_cache[k] = g4.Outcomes(tf, rows_tf[tf], regmap, d)
        return oc_cache[k]

    def pool_for(tf, cohort, g, d, pit=False):
        k = (tf, cohort, g, d, pit)
        if k not in pool_cache:
            oc = oc_for(tf, d)
            cs = set(s for s in cohort_syms[cohort] if s in rows_tf[tf])
            idx, _ = vr.build_context(tf, {s: rows_tf[tf][s] for s in cs}, {cohort: cs}, regmap)
            ix = idx[(cohort, g)]
            if pit and cohort in pc.COHORT_BOUNDS:
                ix = [(s, i) for s, i in ix if pc.in_cohort(pm, cohort, s, rows_tf[tf][s][i]["date"])]
            t0 = time.time()
            pool_cache[k] = [r for _, r in g4.pool_with_dates(oc, ix)]
            print(f"  [pool] {tf}/{cohort}/{g}/{d}{'/PIT' if pit else ''} {len(pool_cache[k])}건 ({time.time()-t0:.0f}s)", flush=True)
        return pool_cache[k]

    results, whys = {}, {}
    for cell in CELLS:
        tf, coh, g, d = cell["tf"], cell["cohort"], cell["regime"], cell["direction"]
        if tf not in tfs:
            continue
        oc = oc_for(tf, d)
        cs = [s for s in cohort_syms[coh] if s in rows_tf[tf]]
        t0 = time.time()
        sigs = g4.collect_cell(oc, g4._det(cell["det"]), cs, g)
        first = min(r["date"] for rows in rows_tf[tf].values() for r in rows)
        last = max(r["date"] for rows in rows_tf[tf].values() for r in rows)
        pool = pool_for(tf, coh, g, d)
        pool_pit = pool_for(tf, coh, g, d, pit=True) if coh in pc.COHORT_BOUNDS else None
        flags, why = layer_flags(cell, sigs, pool, regmap, first, last, oc, pm, pool_pit)
        results[cell["cid"]], whys[cell["cid"]] = flags, why
        print(f"  [{cell['cid']}] n={flags['_n']} 건당 {_pct(flags['_mean'])} OOS n={flags['_oos_n']} "
              f"{_pct(flags['_oos_mean'])} ({time.time()-t0:.0f}s)", flush=True)

    # L9 Holm — 가족 크기별
    raw = {k: v["_raw_p"] for k, v in results.items()}
    for k, v in results.items():
        v["L9_holm"] = v["L1_gate_v2"] and g4.holm({kk: raw[kk] for kk in results})[k] < 0.05
        for m in HOLM_FAMILIES:
            v[f"_holm_m{m}"] = min(1.0, raw[k] * m) < 0.05 and v["L1_gate_v2"]

    # ── ① 행렬 ──────────────────────────────────────────────────────────────
    cids = list(results)
    print("\n" + "=" * 150)
    print("① 셀 × 층 (O 통과 / X 기각)   OOS = 2025-01-01~ 실측 건당(프레임 설계에 안 쓰인 구간)")
    print("=" * 150)
    hdr = f"  {'셀':<34}" + "".join(f"{l.split('_')[0]:>5}" for l in LAYERS) + f"{'전층':>6}{'n':>7}{'건당':>8}{'OOS n':>7}{'OOS건당':>9}"
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for k in cids:
        v = results[k]
        row = "".join(f"{'O' if v[l] else 'X':>5}" for l in LAYERS)
        allp = all(v[l] for l in LAYERS)
        om = v["_oos_mean"]
        print(f"  {k:<34}{row}{'O' if allp else 'X':>6}{v['_n']:>7}{_pct(v['_mean']):>8}{v['_oos_n']:>7}{_pct(om):>9}")

    # ── ② 층별 귀속 ─────────────────────────────────────────────────────────
    print("\n" + "=" * 150)
    print("② 층별 귀속 — 기각 수 / 단독 기각(다른 층 전부 통과인데 이 층만 X) / OOS 양수 셀 기각 수(거짓음성 후보)")
    print("=" * 150)
    attribution = {}
    for l in LAYERS:
        rej = [k for k in cids if not results[k][l]]
        solo = [k for k in cids if not results[k][l] and all(results[k][o] for o in LAYERS if o != l)]
        fn = [k for k in rej if (results[k]["_oos_mean"] or 0) > 0 and results[k]["_oos_n"] >= 10]
        attribution[l] = dict(rejects=rej, solo=solo, false_neg_candidates=fn)
        print(f"  {l:<20} 기각 {len(rej):>2}/{len(cids)}  단독 {len(solo):>2}  OOS양수기각 {len(fn):>2}"
              + (f"   ← {', '.join(fn)}" if fn else ""))

    # ── ③ 누적 통과 곡선 ────────────────────────────────────────────────────
    print("\n" + "=" * 150)
    print("③ 누적 통과 — 층을 역사 순서로 하나씩 얹었을 때 통과 셀 수 (래칫)")
    print("=" * 150)
    ratchet = []
    for i in range(1, len(LAYERS) + 1):
        stack = LAYERS[:i]
        n_pass = sum(1 for k in cids if all(results[k][l] for l in stack))
        ratchet.append((LAYERS[i - 1], n_pass))
        print(f"  +{LAYERS[i-1]:<20} → 통과 {n_pass:>2}/{len(cids)}")

    # ── ④ 의심 층 직답 ──────────────────────────────────────────────────────
    print("\n" + "=" * 150)
    print("④ 의심 층 셋")
    print("=" * 150)
    print("  [B 벤치 — 사후 조건화 크기] 현 B(신호 이후 봉 포함) vs 인과 B(신호 이전 봉만)")
    for k in cids:
        print(f"     {k:<34} 현 B {'O' if results[k]['L8_bench_B'] else 'X'} {whys[k]['L8_bench_B']:<40} | 인과 B {'O' if results[k]['L8_causal_B'] else 'X'} {whys[k]['L8_causal_B']}")
    print("\n  [Holm — 가족 크기 민감도] L1 통과 셀이 m=1/4/8/12 보정에서 몇 개 살아남나")
    l1 = [k for k in cids if results[k]["L1_gate_v2"]]
    for m in HOLM_FAMILIES:
        surv = [k for k in l1 if results[k][f"_holm_m{m}"]]
        print(f"     m={m:<3} {len(surv):>2}/{len(l1)}  {surv}")
    print("\n  [소표본 4중 처벌] L1·L2·L3·L7 이 같이 X 인 셀 (n 하나가 네 번 세어지는 자리)")
    quad = [k for k in cids if not any(results[k][l] for l in ("L1_gate_v2", "L2_holdout_cal", "L3_c2b", "L7_episode"))]
    print(f"     {len(quad)}셀: {quad}")

    json.dump(dict(cells=[c["cid"] for c in CELLS], layers=LAYERS, results=results, why=whys,
                   attribution=attribution, ratchet=ratchet, split=SPLIT),
              open("_audit_guards.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print("\n[저장] _audit_guards.json")
    print("RESULT_JSON: " + json.dumps(dict(
        n_cells=len(cids),
        ratchet=[(l, n) for l, n in ratchet],
        solo={l: len(a["solo"]) for l, a in attribution.items()},
        false_neg={l: len(a["false_neg_candidates"]) for l, a in attribution.items()},
        thresholds_changed=False), separators=(",", ":"), ensure_ascii=False))


if __name__ == "__main__":
    main()
