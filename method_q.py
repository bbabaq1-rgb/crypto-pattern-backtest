"""
method_q.py — 레짐 라벨러 후보의 짝지음 거래 시험 (2단계, 2026-09-04 사전 등록).

method_m(레짐 스케일 연구)과 같은 틀: 같은 신호에 arm 별 청산·필터를 적용해 짝지음 비교,
자산곡선 CAGR, 분기 거래 승률, 전후반, 마지막 365일 홀드아웃, 판정 ①~⑦(method_r.verdict).
레짐 소스만 regime_alt 의 후보 라벨러로 바꾼다.

arm (base = D, 현행 일봉 레짐 방식D):
  D_<L>  : 방식D 규칙, 레짐 소스만 후보 L (진입·청산 둘 다 L 라벨).
  RL_<L> : 롱 한정 방향 인지 청산(method_r RL), 레짐 소스 L.
  F_<L>  : 진입 필터 — 롱은 L 이 bear 면, 숏은 L 이 bull_* 면 진입 안 함(무거래 = ret 0), 청산은 현행 D.
채택 후보는 **1단계(regime_quality)를 통과한 라벨러의 arm 만**. 나머지는 진단으로만 기록한다 —
이 규칙은 실행 전에 정했다. 실거래 코드 무변경. 출력 method_q.json + RESULT_JSON.
"""
import importlib
import json
import statistics as st
import sys
from datetime import date, timedelta

import detlib
import method_m as mm
import method_r as mr
import method_t as mt
import regime_alt as ra
import regime_switch as rs

HOLDOUT_DAYS = mm.HOLDOUT_DAYS
REGMAPS = {}          # name -> date->label
ARMS, ARM_RULE, ARM_SCALE = [], {}, {}


def setup_arms(names):
    global ARMS, ARM_RULE, ARM_SCALE
    ARMS, ARM_RULE, ARM_SCALE = ["D", "RL"], {"D": "D", "RL": "RL"}, {"D": "current", "RL": "current"}
    for L in names:
        if L == "current":
            continue
        for rule in ("D", "RL", "F"):
            a = f"{rule}_{L}"
            ARMS.append(a); ARM_RULE[a] = rule; ARM_SCALE[a] = L
    mm.ARMS, mm.ARM_RULE, mm.ARM_SCALE = ARMS, ARM_RULE, ARM_SCALE


def label_fn(name, rows):
    m = REGMAPS[name]
    return lambda j: m.get(rows[j]["date"])


def run_pattern(label, direction, detmod, oppmod, tf, cutoff):
    mod = importlib.import_module(detmod)
    opp = importlib.import_module(oppmod) if oppmod else None
    arms = {m: [] for m in ARMS}
    n_skipped = 0
    entry_daily = []
    names = list(REGMAPS)
    for sym in detlib.SYMBOLS:
        try:
            rows = detlib.load_ohlcv(sym, tf)
        except (FileNotFoundError, RuntimeError):
            continue
        if len(rows) < 40:
            continue
        opp_set = set(opp.detect(rows)) if opp else set()
        labs = {n: label_fn(n, rows) for n in names}
        for si in mod.detect(rows):
            if si + 1 >= len(rows):
                continue
            ent = {n: labs[n](si) for n in names}
            if any(v is None for v in ent.values()):
                n_skipped += 1
                continue
            entry_daily.append(ent["current"])
            for m in ARMS:
                rule, src = ARM_RULE[m], ARM_SCALE[m]
                if rule == "F":
                    if mm.blocked(direction, ent[src]):
                        arms[m].append((rows[si]["date"], rows[si]["date"], 0.0, 0, "filtered"))
                        continue
                    ret, hold, reason = mm.outcome(rows, si, direction, opp_set, "D", labs["current"])
                else:
                    ret, hold, reason = mm.outcome(rows, si, direction, opp_set, rule, labs[src])
                xi = min(si + hold, len(rows) - 1)
                arms[m].append((rows[si]["date"], rows[xi]["date"], ret, hold, reason))
    if not arms["D"]:
        return None
    base = arms["D"]
    tr, ho = mr.split_idx(base, cutoff)
    out = {}
    for m in ARMS:
        out[m] = dict(train=mm._arm_stats(base, arms[m], tr, m, True),
                      holdout=mm._arm_stats(base, arms[m], ho, m, False))
    out["_strata"] = {}
    for m in ARMS:
        if m == "D":
            continue
        d = [arms[m][i][2] - base[i][2] for i in range(len(base))]
        by_reg, by_year = {}, {}
        for i, x in enumerate(d):
            by_reg.setdefault(entry_daily[i], []).append(x)
            by_year.setdefault(base[i][0][:4], []).append(x)
        out["_strata"][m] = dict(
            by_regime={k: dict(n=len(v), diff=st.mean(v)) for k, v in by_reg.items()},
            by_year={k: dict(n=len(v), diff=st.mean(v)) for k, v in sorted(by_year.items())})
    out["_n_train"], out["_n_holdout"], out["_n_skipped_no_support"] = len(tr), len(ho), n_skipped
    return out


def main(argv=None):
    global REGMAPS
    argv = argv if argv is not None else sys.argv[1:]
    if "--no-fetch" not in argv:
        mt.ensure_data(mm.DAILY_FETCH_DAYS)
    ctx = ra.load_context(fetch_funding="--no-fetch" not in argv)
    REGMAPS = ctx["labels"]
    mr.REGMAP = REGMAPS["current"]
    stage1 = []
    try:
        stage1 = json.load(open("_regime_quality.json", encoding="utf-8")).get("candidates", [])
    except Exception:
        pass
    setup_arms(list(REGMAPS))
    last = max(REGMAPS["current"])
    cutoff = (date.fromisoformat(last) - timedelta(days=HOLDOUT_DAYS)).isoformat()
    for n, m in REGMAPS.items():
        print(f"[regime:{n}] {len(m)}일 분포 {mr._count(m.values())}")
    print(f"[holdout] cutoff {cutoff} | 1단계 통과 후보: {stage1 or '없음'} | 펀딩 {ctx['funding_days']}일")
    print("=" * 130)
    results = {}
    for label, direction, detmod, oppmod, tf in mt.PATS:
        try:
            res = run_pattern(label, direction, detmod, oppmod, tf, cutoff)
        except Exception as e:
            import traceback; traceback.print_exc()
            print(f"\n[{label}] 실행 오류: {str(e)[:80]}"); continue
        if not res:
            print(f"\n[{label}] 신호 없음 — 스킵"); continue
        results[label] = res
        print(f"\n[{label} @{tf} {direction}] train {res['_n_train']} / holdout {res['_n_holdout']} / 공통지지 밖 {res['_n_skipped_no_support']}")
        mm._print(res, "train"); mm._print(res, "holdout")
    if not results:
        print("결과 없음"); return
    results["_pooled"] = {"train": {}, "holdout": {}}
    print("\n" + "=" * 130)
    print("합산 + 판정 ①합산유의 ②CAGR우위>=4/7 ③t<-2 패턴없음 ④분기승률>50% ⑤전후반양수 ⑥⑦홀드아웃  |  채택 = PASS 이고 1단계 통과 라벨러")
    verdicts = {}
    for m in ARMS:
        if m == "D":
            continue
        for split in ("train", "holdout"):
            results["_pooled"][split][m] = mr._pool(results, split, m)
        v = mr.verdict(results, m)
        v["stage1_ok"] = ARM_SCALE[m] in stage1 or ARM_SCALE[m] == "current"
        v["adopt"] = bool(v["pass_"] and v["stage1_ok"])
        verdicts[m] = v
        tr = results["_pooled"]["train"][m] or {}
        ho = results["_pooled"]["holdout"][m] or {}
        dv = tr.get("divergence", {})
        wr = dv.get("arm_wins", 0) / max(1, dv.get("arm_wins", 0) + dv.get("arm_losses", 0)) * 100
        print(f"  {m:<18} train n={tr.get('n')} diff={tr.get('mean_diff', 0)*100:+.3f}%p t={tr.get('t', 0):.2f} "
              f"boot_p={tr.get('boot_p', 1):.3f} CAGR우위 {v['c2_cagr_wins']}/7 분기 {dv.get('n', 0)}건 승률 {wr:.0f}% "
              f"| holdout diff={ho.get('mean_diff', 0)*100:+.3f}%p → {'PASS' if v['pass_'] else 'REJECT'}"
              f"{' (1단계 통과 → 채택 후보)' if v['adopt'] else (' (1단계 미통과 — 진단만)' if v['pass_'] else '')}")
    results["_verdicts"] = verdicts
    results["_config"] = dict(arms=ARMS, labelers=list(REGMAPS), stage1_candidates=stage1,
                              holdout_days=HOLDOUT_DAYS, cutoff=cutoff)
    json.dump(results, open("method_q.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1,
              default=mr._jsonable)
    print("\nRESULT_JSON: " + json.dumps({m: dict(pass_=v["pass_"], adopt=v["adopt"], c2=v["c2_cagr_wins"])
                                         for m, v in verdicts.items()}))


if __name__ == "__main__":
    main()
