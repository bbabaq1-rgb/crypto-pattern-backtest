"""validate_steward_common.py — R-100: 전/후 prior 부호 반전이 국면인가 단위 구성인가 (사전 등록 2026-11-08,
registry steward_common_prereg_2026_11_08).

R-099 는 전(5단위, mu 전부 양수)·후(3단위, 전부 음수)로 갈렸지만 두 arm 의 단위 집합이 달랐다. 여기서는 **양쪽 arm 모두 n>=MIN_UNIT_N 인
공통 단위만** 남겨 같은 단위가 전→후에 부호가 바뀌는지 본다. 분할(SPLIT)·단위 정의·잡음 풀·규칙은 R-099/R-082 그대로.
주 판정은 거래 단위 층화 부트스트랩(단위 안에서 재표집)이고, J 비교(현행-NEVER)는 진단이다.
DEPLOY_ON_PASS=False — 어떤 결과든 steward 상수·실거래 무변경.
"""
import json
import os
import sys

import numpy as np

import steward as sw
import validate_steward_loss as L
import validate_steward_phase as P

DEPLOY_ON_PASS = False
SPLIT = P.SPLIT          # 2026-10-10, R-099 와 동일
MIN_UNIT_N = 10          # 단위가 각 arm 에서 가져야 하는 최소 거래 수
MIN_COMMON = 2           # 공통 단위 최소 개수
MIN_ARM_N = 40           # arm 당 공통 단위 거래 수
B = 2000
SEED = 20261108


def unit_rets(rows):
    """steward.live_d 행 → {unit: [return %]} (단위 = pattern|direction)."""
    by = {}
    for t in rows:
        by.setdefault(f"{t.get('pattern')}|{t.get('direction')}", []).append(float(t["return_pct"]))
    return by


def common_units(pre_by, post_by, k=MIN_UNIT_N):
    return sorted(u for u in pre_by if u in post_by and len(pre_by[u]) >= k and len(post_by[u]) >= k)


def strat_boot(pre_by, post_by, units, b=B, seed=SEED):
    """공통 단위 안에서 거래를 재표집. 반환: arm 평균(거래 가중)과 post-pre 의 점추정·CI."""
    rng = np.random.default_rng(seed)
    pa = {u: np.asarray(pre_by[u], float) for u in units}
    qa = {u: np.asarray(post_by[u], float) for u in units}

    def mean_of(d, idx=None):
        s = n = 0.0
        for u in units:
            x = d[u] if idx is None else d[u][idx[u]]
            s += x.sum(); n += len(x)
        return s / n

    pm, qm = mean_of(pa), mean_of(qa)
    pb, qb = np.empty(b), np.empty(b)
    for i in range(b):
        pi = {u: rng.integers(0, len(pa[u]), len(pa[u])) for u in units}
        qi = {u: rng.integers(0, len(qa[u]), len(qa[u])) for u in units}
        pb[i], qb[i] = mean_of(pa, pi), mean_of(qa, qi)
    ci = lambda a: (float(np.percentile(a, 2.5)), float(np.percentile(a, 97.5)))
    return dict(pre=pm, post=qm, diff=qm - pm, pre_ci=ci(pb), post_ci=ci(qb), diff_ci=ci(qb - pb))


def judge(res, n_common, n_pre, n_post):
    """코드가 낸다. 사전 등록 기준."""
    if n_common < MIN_COMMON or n_pre < MIN_ARM_N or n_post < MIN_ARM_N:
        return "INCONCLUSIVE"
    pos_pre = res["pre_ci"][0] > 0
    neg_post = res["post_ci"][1] < 0
    drop = res["diff_ci"][1] < 0
    if pos_pre and neg_post and drop:
        return "PHASE_EFFECT"
    if not drop:
        return "UNIT_COMPOSITION"        # 같은 단위에서 전→후 하락이 CI 로 확인되지 않음
    return "PARTIAL_DROP"                # 하락은 있으나 부호 반전(전 양·후 음) 미확인


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    trades = json.load(open(argv[argv.index("--trades-json") + 1], encoding="utf-8")) \
        if "--trades-json" in argv else sw.fetch_trades()
    rows = sw.live_d(trades)
    pre_r = [t for t in rows if sw._d(t.get("entry_date")) < SPLIT]
    post_r = [t for t in rows if sw._d(t.get("entry_date")) >= SPLIT]
    pre_by, post_by = unit_rets(pre_r), unit_rets(post_r)
    units = common_units(pre_by, post_by)
    print(f"R-100 분할 {SPLIT} — 방식D {len(rows)}행 (전 {len(pre_r)} / 후 {len(post_r)}), 공통 단위 {len(units)}: {units}")
    per = {u: dict(n_pre=len(pre_by[u]), n_post=len(post_by[u]), mu_pre=float(np.mean(pre_by[u])),
                   mu_post=float(np.mean(post_by[u]))) for u in units}
    for u, d in per.items():
        print(f"  {u}: 전 n{d['n_pre']} {d['mu_pre']:+.2f}% / 후 n{d['n_post']} {d['mu_post']:+.2f}%")
    n_pre = sum(len(pre_by[u]) for u in units); n_post = sum(len(post_by[u]) for u in units)
    out = dict(prereg="steward_common_prereg_2026_11_08", units=units, per_unit=per, n_pre=n_pre, n_post=n_post)
    if len(units) < MIN_COMMON:
        v = "INCONCLUSIVE"; res = None
    else:
        res = strat_boot(pre_by, post_by, units)
        v = judge(res, len(units), n_pre, n_post)
        print(f"  공통 전 {res['pre']:+.2f}% CI {tuple(round(x,2) for x in res['pre_ci'])} / 후 {res['post']:+.2f}% "
              f"CI {tuple(round(x,2) for x in res['post_ci'])} / 후-전 {res['diff']:+.2f} CI {tuple(round(x,2) for x in res['diff_ci'])}")
        # 진단: 공통 단위 prior 로 현행-NEVER (R-099 와 같은 잡음 풀)
        pool = [float(t["return_pct"]) for t in rows]
        pay, _ = L.simulate(pool)
        diag = {}
        for name, by in (("pre", pre_by), ("post", post_by)):
            base = [dict(pattern=u, ret=r / 100.0) for u in units for r in by[u]]
            old = L.MIN_UNIT_N; L.MIN_UNIT_N = MIN_UNIT_N
            try:
                w, info = L.prior_weights(base)
            finally:
                L.MIN_UNIT_N = old
            diag[name] = dict(mu=info["mu"], cur_vs_never=L.diff_ci(pay, "C0_current", "NEVER", w))
            print(f"  [{name}] 공통 prior mu {info['mu']} 현행-NEVER {diag[name]['cur_vs_never']}")
        out["diag"] = diag
    out["res"] = res; out["verdict"] = v
    print(f"\n판정: {v}")
    if os.environ.get("GITHUB_ACTIONS") == "true":
        rr = "" if res is None else f" pre={res['pre']:+.2f} post={res['post']:+.2f} diff_ci={tuple(round(x,2) for x in res['diff_ci'])}"
        print(f"::notice title=R-100 steward 공통 단위::{v} units={len(units)} n_pre={n_pre} n_post={n_post}{rr}")
    json.dump(out, open("_steward_common.json", "w"), indent=1, ensure_ascii=False, default=str)
    return 0


if __name__ == "__main__":
    sys.exit(main())
