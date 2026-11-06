"""validate_steward_ledger10.py — R-096: R-092 와 같은 시험, 단위 최소 n 만 10 으로 낮춘 사전 고정 판
(registry steward_ledger10_prereg_2026_11_06). 규칙·격자·시드·판정식은 validate_steward_ledger 를 그대로 쓴다.
바꾸는 것: MIN_UNIT_N 20→10, MIN_UNITS 3→4. DEPLOY_ON_PASS=False (소표본 prior, R-095 확인 전 승격 금지).
"""
import json
import os
import sys

import steward as sw
import validate_steward_ledger as S
import validate_steward_loss as L

DEPLOY_ON_PASS = False
MIN_UNIT_N = 10
MIN_UNITS = 4


def configure():
    S.MIN_UNIT_N = MIN_UNIT_N
    S.MIN_UNITS = MIN_UNITS


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    configure()
    trades = json.load(open(argv[argv.index("--trades-json") + 1], encoding="utf-8")) \
        if "--trades-json" in argv else sw.fetch_trades()
    base = S.ledger_base(trades)
    print(f"R-096 장부 prior(단위 n>={MIN_UNIT_N}, 단위>={MIN_UNITS}) — 실거래 방식D {len(base)}행")
    if len(base) < 2:
        print("판정: INCONCLUSIVE (장부 없음)"); return 0
    pool = [b["ret"] * 100 for b in base]
    try:
        w_main, info = S.prior(base)
    except ValueError:
        print("판정: INCONCLUSIVE (단위 없음)"); return 0
    w_raw, _ = S.prior(base, shrink=False)
    w_decay, _ = S.prior(base, shift=S.DECAY)
    pay, stp = L.simulate(pool)
    res = S.judge(pay, stp, w_main, w_raw, w_decay, info["units"], len(base))
    print(f"사전 {info}")
    for r in L.RULES:
        print(f"  {r:11} {res['J'][r]:+9.2f} {L.J(pay, r, w_raw):+9.2f} {L.J(pay, r, w_decay):+9.2f}")
    print(f"기준 {res['criteria']} best={res['best']}\n판정: {res['verdict']}")
    if os.environ.get("GITHUB_ACTIONS") == "true":
        jt = " ".join(f"{r}={res['J'][r]:+.1f}" for r in L.RULES)
        print(f"::notice title=R-096 steward 장부 prior n10::{res['verdict']} best={res['best']} units={info['units']} "
              f"n={len(base)} mu={info['mu']} J[{jt}] criteria={res['criteria']} diff_cur={res.get('diff_cur')} diff_never={res.get('diff_never')}")
    json.dump(dict(prereg="steward_ledger10_prereg_2026_11_06", verdict=res["verdict"], best=res["best"], J=res["J"],
                   criteria=res["criteria"], prior=info, n=len(base)),
              open("_steward_ledger10.json", "w"), indent=1, ensure_ascii=False, default=str)
    return 0


if __name__ == "__main__":
    sys.exit(main())
