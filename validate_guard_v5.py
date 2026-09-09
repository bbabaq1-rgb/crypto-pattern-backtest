"""
validate_guard_v5.py — 확인 프레임 v5 (2026-09-09, 사용자 결정 "1,2는 진행").

가드 감사(audit_guards, run 34321686702)가 드러낸 것: v4 의 B 벤치가 실거래 12셀 전부를
기각했고(12/12, 단독 기각 2, OOS 양수 셀 기각 5), 누적 통과가 정확히 그 층에서 3→0 으로
떨어졌다. 레짐 조건부 셀의 게이트 boot_p 는 n=111 에서 OOS 최강 셀(engulfing|bull_btc,
OOS +6.56%)을 떨어뜨렸다 — 표본 부족을 엣지 부재로 오독하는 자리.

v4 파일은 사전 등록본이라 건드리지 않는다. v5 는 v4 의 **기계를 전부 재사용**하고
**판정만** 바꾼다:

  규칙 1  B 벤치(같은 코인·같은 달·같은 레짐)는 계산·출력하되 **판정에서 뺀다**(진단).
          근거: 신호 이후 봉까지 풀에 넣어 '그 달이 좋은 달'이라는 사후 정보를 쓴다
          (2026-09-06 기록). 재는 것은 월 안 타이밍이지 수익성이 아니다.
  규칙 2  레짐≠ALL 셀에서 train n < SMALL_N(200) 이고 train 게이트 탈락 사유가 **boot_p 뿐**
          이면 REJECTED/SHADOW 가 아니라 **INCONCLUSIVE**. '판정 불가·계속 관찰'이지 통과가
          아니다. 근거: 레짐 매칭 k=n 베이스라인은 '같은 국면 무작위'라 높고, 소표본에선
          검정력이 없다(2026-09-05 '표본 부족 ≠ 엣지 없음').

바꾸지 않은 것: A 게이트 v2 문턱(n≥20·평균>0·승률≥35%·boot_p<.05·OOS 4분위), OOS A
재현(mean>0·승률≥35%·boot_p<.05), 왕복 0.4% 스트레스, OOS n<10 → INCONCLUSIVE, SPLIT
2025-01-01. v4 가 A 의 OOS boot_p 에 Holm 을 걸지 않았으므로 v5 도 걸지 않는다(Holm 은
B 의 p 에만 걸려 있었고 B 가 빠지면서 가족이 비었다 — 진단으로 A 의 Holm 을 병기한다).

셀 = v4 11셀 + 4h adopted 3셀(감사와 같은 14셀). 사용자 결정 3(달력→국면 홀드아웃)은
별도 — 이 판은 v4 와 같은 달력 SPLIT 을 쓴다.

**DEPLOY_ON_PASS=False** — 관찰 기간(~2026-10-06). CONFIRMED 가 나와도 실거래 반영 없음.
이 판의 목적은 'v4 의 CONFIRMED 0 이 B 아티팩트였는가' 확인이다.

── 사전 확률 (실행 전 기록 — 감사 행렬을 이미 봤으므로 '눈 감은' 예측이 아니다) ─────
· 4h triple_bottom / equal_lows → CONFIRMED 유력(감사 L1~L7 통과, OOS 양수).
  vol_awakening 은 OOS +0.19% 가 boot_p 를 넘을지 불확실.
· engulfing|bull_btc → INCONCLUSIVE(train bp .368, n=111, OOS +7.0% bp .004).
· 1d 라우팅 나머지(fvg|bull_btc OOS −0.33%, three_soldiers|bull −0.06%, fvg|altseason,
  engulfing|bear, engulfing_short) → SHADOW 또는 REJECTED 그대로. B 를 빼도 OOS A 가 음수.
· 그림자 2(double_bottom/inverse_hs) → 변화 없을 것.
· 즉 **B 제거는 4h 셀을 살리고 1d 셀은 못 살린다** 가 예상. 이게 틀리면 그대로 기록.

실행: python validate_guard_v5.py [--no-fetch] [--tf 1d,4h]
출력 _guard_v5.json + RESULT_JSON. 실거래·DB 무관.
"""
import json
import statistics as st
import sys
import time

import regime_switch as rs
import validate_guard_v4 as g4
import validate_regime_split_all as va
import validate_revival as vr
from validate_regime_split import turnover_rank

SMALL_N = 200                       # 규칙 2 문턱 — 감사에서 engulfing|bull_btc n=111 을 보고 잡은 값(사용자 미조정)
JUDGE_B = False                     # 규칙 1 — B 는 진단
DEPLOY_ON_PASS = False
SPLIT = g4.SPLIT_DATE

CELLS = list(g4.CELLS) + [
    dict(cid="triple_bottom_4h|ALL",  pattern="triple_bottom_4h",  det="detector_triple_bottom",     tf="4h", cohort="top30", regime="ALL", direction="long", status="deployed"),
    dict(cid="equal_lows_4h|ALL",     pattern="equal_lows_4h",     det="detector_equal_lows_4h",     tf="4h", cohort="top30", regime="ALL", direction="long", status="deployed"),
    dict(cid="vol_awakening_4h|ALL",  pattern="vol_awakening_4h",  det="detector_vol_awakening_4h",  tf="4h", cohort="top30", regime="ALL", direction="long", status="deployed"),
]


def _only_boot_p(reason):
    """train 게이트 탈락 사유가 boot_p 하나뿐인가."""
    if not reason:
        return False
    parts = [r.strip() for r in reason.split(",") if r.strip()]
    return bool(parts) and all(p.startswith("boot_p") for p in parts)


def verdict_v5(cell, full_a, train_gate, oos_a, oos_mean):
    """
    v4.verdict 에서 B 를 뺀 것 + 규칙 2. 반환 (verdict, fails, rule2_applied).
    """
    fails = []
    if full_a["n"] == 0 or full_a["mean"] is None or full_a["mean"] <= 0 or (full_a["win"] or 0) < g4.WIN_MIN:
        return "REJECTED", ["A_full mean<=0 or win<35%"], False
    tg_pass = train_gate["verdict"] == "PASSED"
    regime_cell = cell["regime"] != "ALL"
    if not tg_pass:
        if regime_cell and full_a["n"] < SMALL_N and _only_boot_p(train_gate.get("reason", "")):
            return "INCONCLUSIVE", [f"train A boot_p only, regime cell n={full_a['n']}<{SMALL_N}"], True
        fails.append("train A gate")
    if oos_a["n"] < g4.OOS_MIN_N:
        return "INCONCLUSIVE", fails + [f"OOS n={oos_a['n']}"], False
    if not (oos_a["mean"] > 0 and (oos_a["win"] or 0) >= g4.WIN_MIN
            and oos_a["boot_p"] is not None and oos_a["boot_p"] < g4.ALPHA):
        fails.append("OOS A")
    if not (g4.mean_at_fee(oos_mean, g4.STRESS_REQUIRED) or 0) > 0:
        fails.append("OOS cost@0.4%")
    return ("CONFIRMED" if not fails else "UNCONFIRMED_SHADOW"), fails, False


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    tfs = argv[argv.index("--tf") + 1].split(",") if "--tf" in argv else ["1d", "4h"]
    syms = va._syms()
    print(f"확인 프레임 v5 — 규칙 1: B 벤치 판정 제외(JUDGE_B={JUDGE_B}) | 규칙 2: 레짐 셀 n<{SMALL_N} & boot_p 단독 탈락 → INCONCLUSIVE "
          f"| 나머지 v4 동일(split {SPLIT}, OOS A, 비용 0.4%) | DEPLOY_ON_PASS={DEPLOY_ON_PASS}")
    if "--no-fetch" not in argv:
        va.fetch(syms, tfs)
    rows_1d = va.load_tf(syms, "1d", long=True)
    regmap = rs.build_regime_map(rows_by=rows_1d)
    ranked = turnover_rank(rows_1d)
    cohort_syms = {"top30": ranked[:30], "all": list(rows_1d), "majors": [s for s in g4.MAJORS if s in rows_1d]}
    first_1d = min(r["date"] for rows in rows_1d.values() for r in rows)
    last_1d = max(r["date"] for rows in rows_1d.values() for r in rows)
    rows_tf = {"1d": rows_1d}
    if "4h" in tfs:
        rows_tf["4h"] = va.load_tf(syms, "4h")
    print(f"[data] 1d {len(rows_1d)}종목 {first_1d}~{last_1d} | 레짐 {min(regmap)}~{max(regmap)}")

    oc_cache, pool_cache = {}, {}

    def oc_for(tf, d):
        k = (tf, d)
        if k not in oc_cache:
            oc_cache[k] = g4.Outcomes(tf, rows_tf[tf], regmap, d)
        return oc_cache[k]

    def pool_for(tf, cohort, g, d):
        k = (tf, cohort, g, d)
        if k not in pool_cache:
            oc = oc_for(tf, d)
            cs = set(s for s in cohort_syms[cohort] if s in rows_tf[tf])
            idx, _ = vr.build_context(tf, {s: rows_tf[tf][s] for s in cs}, {cohort: cs}, regmap)
            t0 = time.time()
            pool_cache[k] = g4.pool_with_dates(oc, idx[(cohort, g)])
            print(f"  [pool A] {tf}/{cohort}/{g}/{d} {len(pool_cache[k])}건 ({time.time()-t0:.0f}s)", flush=True)
        return pool_cache[k]

    results = {}
    for cell in CELLS:
        if cell["tf"] not in tfs:
            continue
        tf, coh, g, d = cell["tf"], cell["cohort"], cell["regime"], cell["direction"]
        oc = oc_for(tf, d)
        cs = [s for s in cohort_syms[coh] if s in rows_tf[tf]]
        pool = pool_for(tf, coh, g, d)
        first_tf = first_1d if tf == "1d" else min(r["date"] for rows in rows_tf[tf].values() for r in rows)
        t0 = time.time()
        rec = g4.run_cell(cell, oc, cs, pool, first_tf, last_1d)
        results[cell["cid"]] = rec
        print(f"  [{cell['cid']}] n={rec['n']} train {rec['n_train']} OOS {rec['n_oos']} "
              f"train게이트 {rec['train_gate']['verdict']} {rec['train_gate']['reason'] or ''} ({time.time()-t0:.0f}s)", flush=True)

    # A 의 OOS boot_p Holm — **진단**(v4 도 A 에는 안 걸었다)
    fam_a = {k: v["oos_a"]["boot_p"] for k, v in results.items() if v["oos_a"]["n"] >= g4.OOS_MIN_N and v["oos_a"]["boot_p"] is not None}
    holm_a = g4.holm(fam_a)

    print("\n" + "=" * 140)
    print(f"[v5 판정] B 제외 · 레짐 셀 n<{SMALL_N} boot_p 단독 → INCONCLUSIVE · 나머지 v4 동일")
    print("=" * 140)
    print(f"  {'셀':<36}{'상태':<12}{'v4':<20}{'v5':<20}{'사유':<38}{'n':>6}{'OOS n':>6}{'OOS mean':>10}{'OOS bp':>8}{'B(진단)':>10}")
    print("  " + "-" * 138)
    summary, changed = {}, []
    for k, v in results.items():
        cell = v["cell"]
        # v4 판정(같은 데이터로 재계산 — 대조용)
        fam_b = {kk: vv["oos_b"]["p_nw"] for kk, vv in results.items()
                 if vv["oos_a"]["n"] >= g4.OOS_MIN_N and vv["oos_b"]["months"] >= g4.B_MIN_MONTHS and vv["oos_b"]["p_nw"] is not None}
        v4_vd, v4_fails = g4.verdict(v["full_a"], v["train_gate"]["verdict"] == "PASSED", v["train_b"], v["oos_a"], v["oos_b"],
                                     g4.holm(fam_b).get(k), v["oos_a"]["mean"])
        v5_vd, v5_fails, rule2 = verdict_v5(cell, v["full_a"], v["train_gate"], v["oos_a"], v["oos_a"]["mean"])
        summary[k] = dict(status=cell["status"], v4=v4_vd, v5=v5_vd, fails=v5_fails, rule2=rule2, n=v["n"],
                          oos_n=v["oos_a"]["n"], oos_mean=v["oos_a"]["mean"], oos_bp=v["oos_a"]["boot_p"],
                          oos_bp_holm=holm_a.get(k), b_oos_nw=v["oos_b"]["nw"], b_oos_p=v["oos_b"]["p_nw"],
                          train_gate=v["train_gate"]["verdict"], train_reason=v["train_gate"]["reason"])
        if v4_vd != v5_vd:
            changed.append((k, v4_vd, v5_vd))
        om = v["oos_a"]["mean"]
        print(f"  {k:<36}{cell['status']:<12}{v4_vd:<20}{'**' + v5_vd + '**':<20}{('/'.join(v5_fails) or 'ok')[:37]:<38}"
              f"{v['n']:>6}{v['oos_a']['n']:>6}{('-' if om is None else f'{om*100:+.2f}%'):>10}"
              f"{g4._p(v['oos_a']['boot_p']):>8}{g4._f(v['oos_b']['nw']):>10}")

    print("\n  [v4 → v5 변경]")
    for k, a, b in changed:
        print(f"     {k:<36} {a} → {b}" + ("  (규칙 2)" if summary[k]["rule2"] else "  (규칙 1: B 제외)"))
    if not changed:
        print("     없음")
    counts = {}
    for k, s in summary.items():
        counts[s["v5"]] = counts.get(s["v5"], 0) + 1
    print(f"\n  v5 집계: {counts}  |  DEPLOY_ON_PASS={DEPLOY_ON_PASS} — CONFIRMED 도 실거래 반영 없음(관찰 기간)")
    print(f"  A OOS boot_p Holm(진단, m={len(fam_a)}): " + ", ".join(f"{k.split('|')[0]}:{g4._p(p)}" for k, p in holm_a.items()))

    json.dump(dict(config=dict(small_n=SMALL_N, judge_b=JUDGE_B, split=SPLIT, deploy_on_pass=DEPLOY_ON_PASS),
                   summary=summary, changed=changed, counts=counts, holm_a=holm_a),
              open("_guard_v5.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print("\n[저장] _guard_v5.json")
    print("RESULT_JSON: " + json.dumps(dict(counts=counts, changed=[(k, a, b) for k, a, b in changed],
                                            deployed=False), separators=(",", ":"), ensure_ascii=False))


if __name__ == "__main__":
    main()
