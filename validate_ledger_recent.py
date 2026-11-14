"""validate_ledger_recent.py — R-105: 최근 실거래 방식D 결과가 같은 단위의 그 이전 실거래 분포 안인가 밖인가
(registry ledger_recent_prereg_2026_11_14). 진단 전용, 재개 권고 아님. DEPLOY_ON_PASS=False.

단위 = pattern|direction. 기준 풀 = entry_date < POST_FROM 의 실거래 방식D, 최근 = entry_date >= POST_FROM.
단위별·합산 백분위 = 기준 풀에서 최근 n 건을 복원추출한 평균(합)이 관측값 이하일 확률(부트스트랩).
판정(사전 고정): 최근 거래 < MIN_POST → INCONCLUSIVE / 합산 백분위 < 0.05 → REGIME_CHANGE_CANDIDATE / 그 외 WITHIN_DISTRIBUTION.
"""
import json
import os
import sys
from collections import defaultdict

import numpy as np

import steward as sw

DEPLOY_ON_PASS = False
POST_FROM = "2026-11-04"
MIN_REF_N = 10
MIN_POST = 10
ALPHA = 0.05
BOOT = 10000
SEED = 20261114


def split(trades, post_from=POST_FROM):
    ref, post = defaultdict(list), defaultdict(list)
    for t in sw.live_d(trades):
        u = f"{t.get('pattern')}|{t.get('direction')}"
        r = float(t["return_pct"])
        (post if sw._d(t["entry_date"]) >= post_from else ref)[u].append(r)
    return ref, post


def pct_below(pool, n, obs_sum, rng, boot=BOOT):
    """P(n 건 복원추출 합 <= obs_sum)."""
    pool = np.asarray(pool, float)
    draws = rng.choice(pool, size=(boot, n), replace=True).sum(axis=1)
    return float((draws <= obs_sum + 1e-12).mean())


def judge(ref, post, seed=SEED, boot=BOOT):
    rng = np.random.default_rng(seed)
    units, tot_obs, tot_n = [], 0.0, 0
    sims = np.zeros(boot)
    elig = [u for u in post if len(ref.get(u, [])) >= MIN_REF_N]
    for u in sorted(elig):
        p, pool = post[u], np.asarray(ref[u], float)
        units.append(dict(unit=u, n_ref=len(pool), mu_ref=float(pool.mean()), n_post=len(p),
                          mu_post=float(np.mean(p)),
                          pct=pct_below(pool, len(p), float(np.sum(p)), rng, boot)))
        tot_obs += float(np.sum(p)); tot_n += len(p)
        sims += rng.choice(pool, size=(boot, len(p)), replace=True).sum(axis=1)
    skipped = {u: len(v) for u, v in post.items() if u not in elig}
    if tot_n < MIN_POST:
        verdict, pooled = "INCONCLUSIVE", None
    else:
        pooled = float((sims <= tot_obs + 1e-12).mean())
        verdict = "REGIME_CHANGE_CANDIDATE" if pooled < ALPHA else "WITHIN_DISTRIBUTION"
    return dict(verdict=verdict, pooled_pct=pooled, n_post=tot_n, mu_post=(tot_obs / tot_n if tot_n else None),
                units=units, skipped_post_units=skipped)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    trades = json.load(open(argv[argv.index("--trades-json") + 1], encoding="utf-8")) \
        if "--trades-json" in argv else sw.fetch_trades()
    ref, post = split(trades)
    res = judge(ref, post)
    print(f"R-105 기준 {sum(map(len, ref.values()))}행 / 최근({POST_FROM}~) {sum(map(len, post.values()))}행")
    for u in res["units"]:
        print(f"  {u['unit']:32} ref n={u['n_ref']:3} {u['mu_ref']:+6.2f}% | post n={u['n_post']:3} {u['mu_post']:+6.2f}% pct={u['pct']:.3f}")
    print(f"  기준 미달로 제외된 최근 단위: {res['skipped_post_units']}")
    print(f"합산 최근 n={res['n_post']} 평균 {res['mu_post']} 백분위 {res['pooled_pct']}\n판정: {res['verdict']}")
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::notice title=R-105 ledger recent::{res['verdict']} pooled_pct={res['pooled_pct']} n_post={res['n_post']} "
              f"mu_post={res['mu_post']} units={[(u['unit'], u['n_post'], round(u['mu_post'],2), round(u['pct'],3)) for u in res['units']]}")
    json.dump(dict(prereg="ledger_recent_prereg_2026_11_14", **res), open("_ledger_recent.json", "w"),
              indent=1, ensure_ascii=False, default=str)
    return 0


if __name__ == "__main__":
    sys.exit(main())
