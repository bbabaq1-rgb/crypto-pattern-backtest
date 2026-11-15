"""validate_halt_shadow.py — R-114: 정지(2026-11-09) 이후 신호를 주문 없이 방식D 로 재평가해,
같은 단위(pattern|direction)의 정지 전 실거래 방식D 분포와 비교 (registry halt_shadow_prereg_2026_11_15).
진단 전용 — 재개 권고 아님(재개는 사용자 결정). DEPLOY_ON_PASS=False.

그림자 = validate_portfolio 의 배포 집합 재생(1d 라우팅 복제 + 4h adopted 4종, 방식D). 기준 풀 = trades 의
실거래 방식D 중 entry_date < SHADOW_FROM. 해소된 거래만(데이터 끝에서 잘린 미해소 거래 제외).
판정(사전 고정): 그림자 합산 n < MIN_POST → INCONCLUSIVE / 합산 백분위 < ALPHA → REGIME_CHANGE_CANDIDATE / 그 외 WITHIN_DISTRIBUTION.
"""
import json
import os
import sys
from collections import defaultdict
from datetime import date

import numpy as np

import validate_ledger_recent as lr

DEPLOY_ON_PASS = False
SHADOW_FROM = "2026-11-09"
MIN_REF_N = 10
MIN_POST = 30
ALPHA = 0.05
BOOT = 10000
SEED = 20261115
PCT = 100.0   # 재생 수익률은 분수, 장부 return_pct 는 %


def unit_of(label):
    return (label[:-6], "short") if label.endswith("_short") else (label, "long")


def ymd(t_in):
    return date.fromordinal(int(t_in)).isoformat()


def shadow_units(recs, shadow_from=SHADOW_FROM):
    """재생 레코드 → {unit: [ret%]} (진입일 >= shadow_from, 해소된 것만)."""
    if not recs:
        return {}
    end = max(r["t_out"] for r in recs)
    out = defaultdict(list)
    for r in recs:
        if ymd(r["t_in"]) < shadow_from:
            continue
        if r["t_out"] >= end - 0.99:      # 데이터 끝에서 잘린(미해소) 거래 제외 — 보수적
            continue
        p, d = unit_of(r["pattern"])
        out[f"{p}|{d}"].append(float(r["ret"]) * PCT)
    return dict(out)


def ref_units(trades, shadow_from=SHADOW_FROM):
    ref = defaultdict(list)
    for t in lr.sw.live_d(trades):
        if lr.sw._d(t["entry_date"]) < shadow_from:
            ref[f"{t.get('pattern')}|{t.get('direction')}"].append(float(t["return_pct"]))
    return ref


def judge(ref, post, seed=SEED, boot=BOOT):
    rng = np.random.default_rng(seed)
    units, tot_obs, tot_n, sims = [], 0.0, 0, np.zeros(boot)
    elig = [u for u in post if len(ref.get(u, [])) >= MIN_REF_N]
    for u in sorted(elig):
        p, pool = post[u], np.asarray(ref[u], float)
        units.append(dict(unit=u, n_ref=len(pool), mu_ref=float(pool.mean()), n_post=len(p),
                          mu_post=float(np.mean(p)), pct=lr.pct_below(pool, len(p), float(np.sum(p)), rng, boot)))
        tot_obs += float(np.sum(p)); tot_n += len(p)
        sims += rng.choice(pool, size=(boot, len(p)), replace=True).sum(axis=1)
    skipped = {u: len(v) for u, v in post.items() if u not in elig}
    if tot_n < MIN_POST:
        verdict, pooled = "INCONCLUSIVE", None
    else:
        pooled = float((sims <= tot_obs + 1e-12).mean())
        verdict = "REGIME_CHANGE_CANDIDATE" if pooled < ALPHA else "WITHIN_DISTRIBUTION"
    return dict(verdict=verdict, pooled_pct=pooled, n_post=tot_n, mu_post=(tot_obs / tot_n if tot_n else None),
                units=units, skipped_post_units=skipped,
                n_post_all_units=sum(len(v) for v in post.values()))


def replay():
    import detlib, regime_switch as rs, method_t as mt
    import validate_portfolio as vp
    syms = json.load(open("universe.json", encoding="utf-8"))["trading_universe"]
    vp.fetch(syms)
    rows_4h = {}
    for s in syms:
        try:
            rows_4h[s] = detlib.load_ohlcv(s, "4h")
        except (FileNotFoundError, RuntimeError):
            continue
    ranked = vp.turnover_rank(rows_4h)
    regmap = rs.build_regime_map()
    mt.REGMAP = regmap          # 방식D 레짐 전환 청산 켜기 (2026-09-21 결함 교훈)
    return vp.collect_1d(syms) + vp.collect_4h(rows_4h, ranked, regmap)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    trades = json.load(open(argv[argv.index("--trades-json") + 1], encoding="utf-8")) \
        if "--trades-json" in argv else lr.sw.fetch_trades()
    ref = ref_units(trades)
    post = shadow_units(replay())
    res = judge(ref, post)
    print(f"R-114 기준 {sum(map(len, ref.values()))}행 / 그림자({SHADOW_FROM}~) 해소 {res['n_post_all_units']}행")
    for u in res["units"]:
        print(f"  {u['unit']:32} ref n={u['n_ref']:3} {u['mu_ref']:+6.2f}% | shadow n={u['n_post']:3} {u['mu_post']:+6.2f}% pct={u['pct']:.3f}")
    print(f"  기준 미달 단위(제외): {res['skipped_post_units']}")
    print(f"합산 n={res['n_post']} 평균 {res['mu_post']} 백분위 {res['pooled_pct']}\n판정: {res['verdict']}")
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::notice title=R-114 halt shadow::{res['verdict']} pooled_pct={res['pooled_pct']} n_post={res['n_post']} "
              f"mu_post={res['mu_post']} n_all={res['n_post_all_units']} "
              f"units={[(u['unit'], u['n_post'], round(u['mu_post'],2), round(u['pct'],3)) for u in res['units']]}")
    json.dump(dict(prereg="halt_shadow_prereg_2026_11_15", **res), open("_halt_shadow.json", "w"),
              indent=1, ensure_ascii=False, default=str)
    return 0


if __name__ == "__main__":
    sys.exit(main())
