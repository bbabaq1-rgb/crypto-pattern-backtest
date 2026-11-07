"""validate_steward_phase.py — R-099: steward 정지 규칙의 가치가 prior 국면에 의존하는가 (사전 등록 2026-11-07,
registry steward_phase_prereg_2026_11_07).

R-096 은 장부 227행의 8단위 수축 mu 가 전부 음수라 현행 규칙이 NEVER 보다 낫다고 했는데, 그 장부는 10/10 이후 bull_btc 국면 거래가
지배한다. 장부를 entry_date 기준 SPLIT 전/후로 나눠 prior 를 따로 만들고 같은 규칙 8개를 같은 잡음 풀·격자·시드로 평가한다.
규칙·격자·경로 생성·판정 통계는 validate_steward_loss / validate_steward_ledger 를 그대로 쓴다(새 규칙 금지).
DEPLOY_ON_PASS=False — 어떤 결과든 steward 상수·실거래 무변경.
"""
import json
import os
import sys

import steward as sw
import validate_steward_ledger as S
import validate_steward_loss as L

DEPLOY_ON_PASS = False
SPLIT = "2026-10-10"      # 사전 고정 — entry_date < SPLIT 이 '국면 전'
MIN_UNIT_N = 10           # 분할 때문에 R-092(20) 대신 R-096 값 사용
MIN_UNITS = 3             # arm 당
MIN_ARM_N = 60            # arm 당 장부 행


def split_base(base_rows):
    """steward.live_d 행 → (pre, post) ledger_base 입력."""
    pre = [t for t in base_rows if sw._d(t.get("entry_date")) < SPLIT]
    post = [t for t in base_rows if sw._d(t.get("entry_date")) >= SPLIT]
    return S.ledger_base(pre), S.ledger_base(post)


def arm_prior(base):
    """arm 장부 → (w, info) 또는 None(부족). S.MIN_UNIT_N 을 잠시 바꾼다."""
    if len(base) < MIN_ARM_N:
        return None
    old = S.MIN_UNIT_N
    S.MIN_UNIT_N = MIN_UNIT_N
    try:
        w, info = S.prior(base)
    except ValueError:
        return None
    finally:
        S.MIN_UNIT_N = old
    return None if info["units"] < MIN_UNITS else (w, info)


def judge(pay, pre, post):
    """코드가 낸다. pre/post = arm_prior 결과 또는 None."""
    out = dict(arms={})
    for name, a in (("pre", pre), ("post", post)):
        if a is None:
            out["arms"][name] = None
            continue
        w, info = a
        d = L.diff_ci(pay, "C0_current", "NEVER", w)
        best = max(L.CANDIDATES, key=lambda r: L.J(pay, r, w))
        out["arms"][name] = dict(J={r: L.J(pay, r, w) for r in L.RULES}, cur_vs_never=d, best=best,
                                 best_vs_cur=L.diff_ci(pay, best, "C0_current", w), prior=info,
                                 sep=d[1] > 0)
    P, Q = out["arms"]["pre"], out["arms"]["post"]
    if P is None:
        v = "INCONCLUSIVE"
    elif P["sep"]:
        v = "UNIT_ROBUST"
    elif Q is not None and Q["sep"]:
        v = "PHASE_DEPENDENT"
    else:
        v = "NOT_SEPARABLE"
    out["verdict"] = v
    return out


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    trades = json.load(open(argv[argv.index("--trades-json") + 1], encoding="utf-8")) \
        if "--trades-json" in argv else sw.fetch_trades()
    rows = sw.live_d(trades)
    pre_b, post_b = split_base(rows)
    print(f"R-099 분할 {SPLIT} — 실거래 방식D {len(rows)}행 (전 {len(pre_b)} / 후 {len(post_b)})")
    allb = pre_b + post_b
    if len(allb) < 2:
        print("판정: INCONCLUSIVE (장부 없음)"); return 0
    pre, post = arm_prior(pre_b), arm_prior(post_b)
    for n, a in (("pre", pre), ("post", post)):
        print(f"  {n}: {'부족' if a is None else a[1]}")
    pool = [b["ret"] * 100 for b in allb]
    pay, stp = L.simulate(pool)
    res = judge(pay, pre, post)
    for n, a in res["arms"].items():
        if a:
            print(f"  [{n}] J " + " ".join(f"{r}={a['J'][r]:+.1f}" for r in L.RULES)
                  + f" | 현행-NEVER {a['cur_vs_never']} 최선 {a['best']}")
    print(f"\n판정: {res['verdict']}")
    if os.environ.get("GITHUB_ACTIONS") == "true":
        parts = []
        for n, a in res["arms"].items():
            parts.append(f"{n}=None" if a is None else
                         f"{n}[units={a['prior']['units']} mu={a['prior']['mu']} cur-never={tuple(round(x,1) for x in a['cur_vs_never'])} "
                         f"best={a['best']} J={' '.join(f'{r}={a['J'][r]:+.1f}' for r in L.RULES)}]")
        print(f"::notice title=R-099 steward 국면 prior::{res['verdict']} n_pre={len(pre_b)} n_post={len(post_b)} " + " ".join(parts))
    json.dump(dict(prereg="steward_phase_prereg_2026_11_07", verdict=res["verdict"], arms=res["arms"],
                   n_pre=len(pre_b), n_post=len(post_b)),
              open("_steward_phase.json", "w"), indent=1, ensure_ascii=False, default=str)
    return 0


if __name__ == "__main__":
    sys.exit(main())
