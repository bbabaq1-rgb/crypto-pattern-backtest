"""validate_steward_ledger.py — R-092 steward 정지 규칙 8개를 **실거래 장부 prior** 로 재평가 (사전 등록 2026-11-05,
registry steward_ledger_prereg_2026_11_05).

DEPLOY_ON_PASS=True(backlog R-092). R-082 는 백테스트 단위 평균을 prior 로 써서 모든 정지 규칙이 NEVER 보다 나빴다(c5 실패).
정지의 가치는 prior 에 음수 mu 질량이 얼마나 있느냐에 달려 있고 그것은 배포 후 실거래 장부가 말한다.
규칙 격자·경로 생성·손익 정의·시드는 validate_steward_loss 를 그대로 import(새 규칙 추가 금지). 바꾸는 것은 prior 와 잡음 풀뿐:
 - 단위 = (pattern, direction) 의 실거래 방식D 행(steward.live_d), n >= MIN_UNIT_N(20)
 - 잡음 풀 = 장부 수익률 전체(%) 평균 0 이동 — 네트워크·OKX 데이터 불필요
"""
import json
import sys

import numpy as np

import steward as sw
import validate_steward_loss as L

DEPLOY_ON_PASS = True
MIN_UNIT_N = 20          # 단위당 실거래 최소 건수(backlog 고정)
MIN_UNITS = 3            # 미만이면 INCONCLUSIVE
MIN_TOTAL_N = 100        # 장부 전체 최소 — 미만이면 INCONCLUSIVE
DECAY = L.DECAY


def ledger_base(trades):
    """steward.live_d 행 → prior_weights 입력(dict pattern, ret). 단위 키 = pattern|direction."""
    return [dict(pattern=f"{t.get('pattern')}|{t.get('direction')}", ret=float(t["return_pct"]) / 100.0)
            for t in sw.live_d(trades)]


def prior(base, shrink=True, shift=0.0):
    old = L.MIN_UNIT_N
    L.MIN_UNIT_N = MIN_UNIT_N
    try:
        return L.prior_weights(base, shrink=shrink, shift=shift)
    finally:
        L.MIN_UNIT_N = old


def judge(pay, stp, w_main, w_raw, w_decay, n_units, n_total):
    """코드가 낸다. INCONCLUSIVE(장부 부족) | ADOPT:<규칙> | NEVER_PREFERRED | CURRENT_RETAINED."""
    j = {r: L.J(pay, r, w_main) for r in L.RULES}
    best = max(L.CANDIDATES, key=lambda r: j[r])
    if n_units < MIN_UNITS or n_total < MIN_TOTAL_N:
        return dict(verdict="INCONCLUSIVE", best=best, J=j, criteria={}, why=f"units={n_units} n={n_total}")
    d_cur = L.diff_ci(pay, best, "C0_current", w_main)
    d_nev = L.diff_ci(pay, best, "NEVER", w_main)
    c = {
        "c1_beats_current_ci": d_cur[1] > 0,
        "c2_both_lam": all(L.J(pay, best, w_main, [lam]) > L.J(pay, "C0_current", w_main, [lam]) for lam in L.LAMS),
        "c3_raw_and_decay": (L.J(pay, best, w_raw) > L.J(pay, "C0_current", w_raw)
                             and L.J(pay, best, w_decay) > L.J(pay, "C0_current", w_decay)),
        "c4_detect": stp[best][3][L.GRID.index(-2.0)] >= L.MIN_DETECT,
        "c5_beats_never_ci": d_nev[1] > 0,
    }
    ok = all(c.values())
    never_best = max(j[r] for r in L.CANDIDATES + ["C0_current"]) <= 0
    verdict = f"ADOPT:{best}" if ok else ("NEVER_PREFERRED" if never_best else "CURRENT_RETAINED")
    return dict(verdict=verdict, best=best, J=j, criteria=c, diff_cur=d_cur, diff_never=d_nev, never_best=never_best)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    trades = json.load(open(argv[argv.index("--trades-json") + 1], encoding="utf-8")) \
        if "--trades-json" in argv else sw.fetch_trades()
    base = ledger_base(trades)
    print(f"R-092 장부 prior — 실거래 방식D {len(base)}행")
    if len(base) < 2:
        print("판정: INCONCLUSIVE (장부 없음)"); return 0
    pool = [b["ret"] * 100 for b in base]
    try:
        w_main, info = prior(base)
    except ValueError:
        print("판정: INCONCLUSIVE (n>=20 단위 없음)")
        return 0
    w_raw, _ = prior(base, shrink=False)
    w_decay, _ = prior(base, shift=DECAY)
    print(f"풀 sd {np.std(pool):.2f}% 사전 {info}")
    pay, stp = L.simulate(pool)
    res = judge(pay, stp, w_main, w_raw, w_decay, info["units"], len(base))
    print("규칙별 J(주) / raw / decay / lam1 / lam3 / mu=-2 정지율(lam3)")
    for r in L.RULES:
        print(f"  {r:11} {res['J'][r]:+9.2f} {L.J(pay, r, w_raw):+9.2f} {L.J(pay, r, w_decay):+9.2f} "
              f"{L.J(pay, r, w_main, [1]):+9.2f} {L.J(pay, r, w_main, [3]):+9.2f} {stp[r][3][L.GRID.index(-2.0)]:.2f}")
    print(f"기준 {res['criteria']} best={res['best']}")
    print(f"\n판정: {res['verdict']}")
    import os
    if os.environ.get("GITHUB_ACTIONS") == "true":   # 세션의 gh 는 잡 로그를 못 받는다 — check-run 주석으로 낸다
        jt = " ".join(f"{r}={res['J'][r]:+.1f}" for r in L.RULES)
        print(f"::notice title=R-092 steward 장부 prior::{res['verdict']} best={res['best']} units={info['units']} n={len(base)} "
              f"mu={info['mu']} J[{jt}] criteria={res['criteria']} diff_cur={res.get('diff_cur')} diff_never={res.get('diff_never')}")
    json.dump(dict(prereg="steward_ledger_prereg_2026_11_05", verdict=res["verdict"], best=res["best"], J=res["J"],
                   criteria=res["criteria"], prior=info, n=len(base),
                   diff_cur=res.get("diff_cur"), diff_never=res.get("diff_never"),
                   J_raw={r: L.J(pay, r, w_raw) for r in L.RULES}, J_decay={r: L.J(pay, r, w_decay) for r in L.RULES},
                   weights=dict(main=list(w_main))),
              open("_steward_ledger.json", "w"), indent=1, ensure_ascii=False, default=str)
    return 0


if __name__ == "__main__":
    sys.exit(main())
