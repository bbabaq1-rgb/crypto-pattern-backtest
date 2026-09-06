"""
validate_ma180.py — 장기 이평 돌파 진입 후보의 **실거래 프레임 사전 등록 시험** (2026-09-06,
사용자 지시 "MA180 사전 등록은 기록용 진행해줘").

## 성격 — 기록용

사전 등록 기준을 전부 통과해도 **실거래에 반영하지 않는다.** 사용자가 이번 건을 명시적으로
'기록용'으로 지정했다(자율 반영 조항의 예외). 통과하면 registry 에 `passed_not_deployed` 로
남기고 배포 여부는 사용자 결정으로 넘긴다. registry/universe/scheduler 어디에도 넣지 않는다.

## 배경

study_ma_breakout.py(2026-09-06)는 탐색적 스터디였다 — MA180 첫 돌파(20일 이상 아래였다가)의
40봉 내 +20% 도달률이 57%(무작위 44.5%), decisive(종가>=MA×1.02) 셀은 동결 라벨 +4.19%
중앙 +10% 승률 56% OOS 4/4. 다만 **레짐 편중이 컸다**(bull_btc +20d +18.1% / bear·altseason 음수)
**연도 편중도 컸다**(2023·2024 가 전부, 2025·2026 음수). 그래서 이 시험의 주 판정 셀은
bull_btc 하나이고, holdout(마지막 365일 = 2025-09~2026-09, bear 지배)이 실질 관문이다.

## 사전 등록 (결과를 보기 전에 동결)

신호   detector_ma180_breakout.detect — MA180, fresh(직전 20봉 이상 아래), decisive(>=MA×1.02),
       진입 = 돌파봉 종가(인과).
주 판정 셀  (ma180_decisive, bull_btc, top30) 롱 — **이 셀 하나만 판정한다.**
청산   방식D (method_s.outcome = paper_executor.eval_D: −8% 저가 손절 / 레짐 라벨 전환 / 30봉 만기)
베이스라인  같은 레짐·코호트·TF 무작위 진입을 **같은 청산 규칙**으로 평가, k=n

  C1  동결 게이트 v2 5조건 — n>=20, mean>0, 승률>=35%, boot_p<0.05, OOS 양분위>=2 (top30 코호트)
  C2  holdout(마지막 365일) n>=10 이고 mean>0
  C2b train 자체가 게이트 통과 **이고** train n >= holdout n / 2
      (2026-09-05 기록한 설계 결함 보완 — vwap_rev_short_4h 가 표본 92% 를 holdout 에 두고
       train 이 비다시피 한 채 통과했다. '다음 설계부터 적용' 항목의 첫 적용.)
  C3  train 자산곡선 CAGR>0 이고 Calmar>0 (실거래 사이징 risk 1.5%/lev 3/변동성 타겟팅)

전부 만족 → CONFIRMED(기록만). 하나라도 빠지면 REJECTED 로 기록하고 끝낸다.

## 진단 셀 (판정 아님, 참고 출력)

ma180_decisive|ALL · ma180_raw|bull_btc · ma180_raw|ALL · ma200_decisive|bull_btc,
그리고 all 코호트 수치. 사후에 이 중에서 골라 '살았다'고 말하지 않는다 —
사후 선택 셀 추격 금지(validate_ih_exit 교훈).

실행: python validate_ma180.py [--no-fetch]
출력: _ma180.json
"""
import json
import statistics as st
import sys
import time
from datetime import date

import regime_switch as rs
import validate_regime_split_all as va
import validate_revival as vr
from validate_regime_split import turnover_rank
import detector_ma180_breakout as det

TF = "1d"
DIRECTION = "long"
COHORTS = vr.COHORTS                 # ["all", "top30"]
CONFIRM_COHORT = vr.CONFIRM_COHORT   # "top30"
HOLDOUT_DAYS = vr.HOLDOUT_DAYS       # 365
HOLDOUT_MIN_N = vr.HOLDOUT_MIN_N     # 10
TRAIN_MIN_RATIO = 0.5                # C2b: train n >= holdout n x 이 비율

# (cid, ma_n, filt, [셀 레짐...])
CELLS = [
    ("ma180_decisive", 180, "decisive", ["bull_btc", "ALL"]),
    ("ma180_raw",      180, "raw",      ["bull_btc", "ALL"]),
    ("ma200_decisive", 200, "decisive", ["bull_btc"]),
]
PRIMARY = ("ma180_decisive", "bull_btc")   # 판정하는 유일한 셀
DEPLOY_ON_PASS = False                     # 기록용 — 통과해도 자동 반영 없음(사용자 지시 2026-09-06)


def detect_fn_for(ma_n, filt):
    return lambda rows: det.detect(rows, ma_n=ma_n, filt=filt)


def confirm_ma180(cells, cutoff, span_train, pool_rets):
    """vr.confirm(C1/C2/C3) + C2b(train 자체 게이트 통과 & train n >= holdout n x TRAIN_MIN_RATIO)."""
    base = vr.confirm(cells, cutoff, span_train)
    ref = cells.get(CONFIRM_COHORT, {}).get("sigs", [])
    train = [s for s in ref if s["date"] < cutoff]
    hold = [s for s in ref if s["date"] >= cutoff]
    tg = vr.gate_cell(train, pool_rets) if train else dict(verdict="REJECTED", reason="train 없음", n=0)
    enough = len(train) >= len(hold) * TRAIN_MIN_RATIO
    c2b = tg["verdict"] == "PASSED" and enough
    base["c2b_train"] = c2b
    base["train_gate"] = tg
    base["train_n"] = len(train)
    base["confirmed"] = bool(base["c1_live_cohort"] and base["c2_holdout"] and c2b and base["c3_equity"])
    return base


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    syms = va._syms()
    print(f"MA 장기 이평 돌파 사전 등록 시험 | 유니버스 {len(syms)} | TF {TF} | 주 판정 셀 {PRIMARY} @{CONFIRM_COHORT}")
    print(f"[성격] 기록용 — 통과해도 실거래 반영 없음(DEPLOY_ON_PASS={DEPLOY_ON_PASS}). 배포는 사용자 결정.")
    if "--no-fetch" not in argv:
        va.fetch(syms, [TF])
    regmap = rs.build_regime_map()
    rows_by = va.load_tf(syms, TF)
    ranked = turnover_rank(rows_by)
    cohorts = {"all": set(rows_by), "top30": set(s for s in ranked[:30] if s in rows_by)}
    pools, atrs = vr.build_context(TF, rows_by, cohorts, regmap)

    first = min(r["date"] for rows in rows_by.values() for r in rows)
    last = max(r["date"] for rows in rows_by.values() for r in rows)
    cutoff = date.fromordinal(date.fromisoformat(last).toordinal() - HOLDOUT_DAYS).isoformat()
    span_train = max(1, date.fromisoformat(cutoff).toordinal() - date.fromisoformat(first).toordinal())
    print(f"[분할] train {first} ~ {cutoff} ({span_train}일) | holdout {HOLDOUT_DAYS}일 ({cutoff} ~ {last})")
    print(f"[코호트] all {len(cohorts['all'])} / top30 {len(cohorts['top30'])}")

    pool_rets = {}
    for cname in COHORTS:
        for g in ["bull_btc", "ALL"]:
            t0 = time.time()
            pool_rets[(cname, g)] = vr.eval_pool(TF, pools[(cname, g)], rows_by, atrs, regmap, DIRECTION)
            print(f"  [pool] {cname}:{g} {len(pool_rets[(cname, g)])}건 ({time.time()-t0:.0f}s)", flush=True)

    results = {}
    for cid, ma_n, filt, regimes in CELLS:
        t0 = time.time()
        by_sym = vr.collect(TF, detect_fn_for(ma_n, filt), DIRECTION, rows_by, atrs, regmap)
        tot = sum(len(v) for v in by_sym.values())
        print(f"\n[{cid}] MA{ma_n} {filt} — 신호 {tot}건 ({time.time()-t0:.0f}s)", flush=True)
        for g in regimes:
            cells = {}
            judged = (cid, g) == PRIMARY
            print(f"  [셀 레짐 {g}] {'** 주 판정 **' if judged else '(진단)'}")
            for cname in COHORTS:
                cs = cohorts[cname]
                sigs = [x for s in cs for x in by_sym.get(s, []) if g == "ALL" or x["regime"] == g]
                rec = vr.gate_cell(sigs, pool_rets[(cname, g)])
                cells[cname] = dict(gate=rec, sigs=sigs)
                yr = " ".join(f"{y}:{v['mean']*100:+.1f}%(n{v['n']})" for y, v in rec["by_year"].items())
                print(f"    {cname:<6} n={rec['n']:>5} mean={vr._f(rec['mean'])} med={vr._f(rec['median'])} "
                      f"승률 {rec['win_rate']*100:>3.0f}% 절사 {vr._f(rec['trimmed_mean'])} top5 {(rec['top5_share'] or 0)*100:>3.0f}% "
                      f"| 레짐평균 {vr._f(rec['base_mean'])} 엣지 {vr._f(rec['edge'])} | boot_p={rec['boot_p']:.3f} "
                      f"OOS={rec['oos_pos']}/4 보유 {rec['hold']:.1f} -> {rec['verdict']} {rec['reason']}")
                print(f"           연도별 {yr} | 청산 {rec['reasons']}")
            cf = confirm_ma180(cells, cutoff, span_train, pool_rets[(CONFIRM_COHORT, g)])
            eq = cf["equity"] or {}
            tg = cf["train_gate"]
            print(f"    => {'CONFIRMED' if cf['confirmed'] else 'not confirmed'}{' (판정)' if judged else ' (진단, 판정 아님)'} "
                  f"| C1 {cf['c1_live_cohort']} | C2 holdout n={cf['holdout']['n']} mean={vr._f(cf['holdout']['mean'])} {cf['c2_holdout']} "
                  f"| C2b train n={cf['train_n']} {tg['verdict']} {c2b_note(tg)} {cf['c2b_train']} "
                  f"| C3 CAGR {vr._f(eq.get('cagr'))} MDD {vr._f(eq.get('mdd'))} Calmar {eq.get('calmar', 0):.2f} {cf['c3_equity']}")
            results[f"{cid}|{g}"] = dict(cid=cid, ma_n=ma_n, filt=filt, regime=g, tf=TF, direction=DIRECTION,
                                         judged=judged, cells={c: cells[c]["gate"] for c in cells}, confirm=cf)

    pk = f"{PRIMARY[0]}|{PRIMARY[1]}"
    prim = results[pk]
    verdict = "CONFIRMED_RECORD_ONLY" if prim["confirm"]["confirmed"] else "REJECTED"
    print("\n" + "=" * 100)
    print(f"[판정] 주 셀 {pk} @{CONFIRM_COHORT} -> {verdict}")
    print("  기록용 시험 — 통과여도 실거래 반영 없음. 배포는 사용자 결정.")
    diag = [k for k, v in results.items() if not v["judged"] and v["confirm"]["confirmed"]]
    print(f"  진단 셀 중 기준 충족: {diag if diag else '없음'} (사후 선택 금지 — 추격하지 않는다)")
    json.dump(dict(primary=pk, verdict=verdict, deploy_on_pass=DEPLOY_ON_PASS, cutoff=cutoff, results=results),
              open("_ma180.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print("[저장] _ma180.json")
    print("RESULT_JSON: " + json.dumps(dict(primary=pk, verdict=verdict, diagnostic_pass=diag), ensure_ascii=False))


def c2b_note(tg):
    return f"({tg.get('reason') or 'ok'})"


if __name__ == "__main__":
    main()
