"""
validate_short_exit 로직 검증 (합성 데이터, 네트워크 없음).

  - mode "D" 가 **실거래 paper_executor.eval_D** 및 method_s.outcome 과 완전 일치
  - mode "norg" 가 method_s.outcome(use_regime=False) 와 일치
  - mode "adv" 가 롱에서 **method_m.outcome(rule="RL")**(= method_r RL) 과 완전 일치 —
    S_adv 가 그 거울상임을 코드로 고정
  - 숏의 adv 는 유리 전환(→bear)에 청산하지 않고 불리 전환(→bull_*)에만 청산
  - 짝지음·부트CI·전후반 분할·레짐 층화·가중 합산 수학
  - 반증 판정 4조건 분기
실행: python test_short_exit.py
"""
import random
import statistics as st
import sys
from datetime import date, timedelta

import method_m as mm
import method_s as ms
import paper_executor as pe
import validate_short_exit as v

fails = []


def check(n, c, d=""):
    print(("PASS " if c else "FAIL ") + n + ("" if c else f" — {d}"))
    c or fails.append(n)


LABELS = ["bull_btc", "bull_altseason", "bear", "sideways"]


def rows_of(n, seed, drift=0.0, start=date(2021, 1, 1)):
    random.seed(seed)
    px, out = 100.0, []
    for i in range(n):
        o = px * (1 + random.gauss(0, 0.004))
        nx = px * (1 + drift + random.gauss(0, 0.02))
        d = start + timedelta(days=i)
        out.append(dict(ts=int((d - date(1970, 1, 1)).total_seconds() * 1000), date=d.isoformat(),
                        o=o, h=max(o, nx) * 1.006, l=min(o, nx) * 0.994, c=nx, v=1000.0))
        px = nx
    return out


# ── 1. 규칙 정합 (가장 중요) ───────────────────────────────────────────────
mis_live = mis_ms = mis_rl = mis_norg = 0
n_case = 0
for seed in range(50):
    rows = rows_of(160, 700 + seed, drift=random.Random(seed).choice([-0.004, 0.0, 0.004]))
    rng = random.Random(seed)
    regmap, lab = {}, rng.choice(LABELS)
    for r in rows:
        if rng.random() < 0.08:
            lab = rng.choice(LABELS)
        regmap[r["date"]] = lab
    opp = {i for i in range(len(rows)) if rng.random() < 0.03}
    labfn = lambda j, r=rows: regmap.get(r[j]["date"])
    for direction in ("long", "short"):
        for si in (10, 45, 95):
            n_case += 1
            d_ = v.outcome(rows, si, direction, opp, labfn, "D")
            if d_ != ms.outcome(rows, si, direction, opp, labfn):
                mis_ms += 1
            live = pe.eval_D(rows, si, direction, opp, regmap)
            if live is not None:
                j, _px, lret, lreason = live
                if abs(lret - d_[0]) > 1e-12 or lreason != d_[2] or (j - si) != d_[1]:
                    mis_live += 1
            if v.outcome(rows, si, direction, opp, labfn, "norg") != \
               ms.outcome(rows, si, direction, opp, labfn, use_regime=False):
                mis_norg += 1
            adv_ = v.outcome(rows, si, direction, opp, labfn, "adv")
            rl = mm.outcome(rows, si, direction, opp, "RL", labfn)
            if direction == "long" and adv_ != rl:
                mis_rl += 1
check(f'mode "D" == paper_executor.eval_D ({n_case} 시나리오)', mis_live == 0, f"{mis_live}건")
check('mode "D" == method_s.outcome ', mis_ms == 0, f"{mis_ms}건")
check('mode "norg" == method_s.outcome(use_regime=False)', mis_norg == 0, f"{mis_norg}건")
check('mode "adv"(롱) == method_m.outcome(rule="RL") — method_r RL 과 동일', mis_rl == 0, f"{mis_rl}건")

# ── 2. 숏 adv 의 방향성 ────────────────────────────────────────────────────
check("불리 국면: 숏은 bull_*, 롱은 bear",
      v.ADVERSE["short"] == frozenset({"bull_btc", "bull_altseason"}) and v.ADVERSE["long"] == frozenset({"bear"}))
rows = rows_of(60, 3)
# bull_btc 진입 -> bear 전환(숏에 유리): adv 는 청산 안 함, D 는 청산함
fav = {r["date"]: ("bull_btc" if i < 10 else "bear") for i, r in enumerate(rows)}
labf = lambda j: fav.get(rows[j]["date"])
check("숏 adv: 유리 전환(→bear)에는 청산하지 않는다",
      v.outcome(rows, 2, "short", set(), labf, "adv")[2] != "regime_switch")
check("숏 D: 같은 상황에서 청산한다",
      v.outcome(rows, 2, "short", set(), labf, "D")[2] == "regime_switch")
# bear 진입 -> bull_btc 전환(숏에 불리): adv 도 청산
unf = {r["date"]: ("bear" if i < 10 else "bull_btc") for i, r in enumerate(rows)}
labu = lambda j: unf.get(rows[j]["date"])
check("숏 adv: 불리 전환(→bull_*)에는 청산한다",
      v.outcome(rows, 2, "short", set(), labu, "adv")[2] == "regime_switch")
check("숏 norg: 어떤 전환에도 청산하지 않는다",
      v.outcome(rows, 2, "short", set(), labu, "norg")[2] != "regime_switch"
      and v.outcome(rows, 2, "short", set(), labf, "norg")[2] != "regime_switch")
# bull_btc 진입(이미 불리) -> 계속 bull: 재청산 없음
al = {r["date"]: "bull_btc" for r in rows}
check("숏 adv: 이미 불리 국면에서 진입하면 그 사실만으로 청산하지 않는다",
      v.outcome(rows, 2, "short", set(), lambda j: al.get(rows[j]["date"]), "adv")[2] != "regime_switch")

# ── 3. 통계 도우미 ─────────────────────────────────────────────────────────
b = [("2024-01-01", 0.10, 5, "x", "bear"), ("2024-06-01", -0.05, 5, "x", "bull_btc"),
     ("2025-01-01", 0.00, 5, "x", "bear"), ("2025-06-01", 0.02, 5, "x", "sideways")]
a = [("2024-01-01", 0.12, 5, "x", "bear"), ("2024-06-01", -0.05, 5, "x", "bull_btc"),
     ("2025-01-01", 0.04, 5, "x", "bear"), ("2025-06-01", 0.01, 5, "x", "sideways")]
p = v.paired(b, a)
check("paired: 평균 차이", abs(p["mean"] - st.mean([0.02, 0.0, 0.04, -0.01])) < 1e-12)
check("paired: 분기 거래는 차이가 0 이 아닌 것만", p["div_n"] == 3)
check("paired: 승/패", (p["arm_wins"], p["arm_losses"]) == (2, 1))
lo, hi = v.boot_ci(b, a, n=500, seed=1)
check("boot_ci: lo <= hi", lo <= hi)
check("boot_ci: 전부 양수면 lo > 0", v.boot_ci(b, [(x[0], x[1] + 0.05) + x[2:] for x in b], n=500)[0] > 0)
h1, h2 = v.split_half(b, a)
check("split_half: 전반/후반 각 2건", h1["n"] == 2 and h2["n"] == 2)
reg = v.by_regime(b, a)
check("by_regime: bear 2건 평균 +3%p", reg["bear"]["n"] == 2 and abs(reg["bear"]["mean"] - 0.03) < 1e-12)
check("pool: 표본 가중", abs(v.pool([(0.02, 100), (-0.01, 300)]) - (-0.0025)) < 1e-12)
check("pool: 빈 입력 0", v.pool([]) == 0.0)


# ── 4. 판정 분기 ───────────────────────────────────────────────────────────
def decide(h1, h2, ci_lo, s, l, non_bear):
    c1, c2, c3 = h1 > 0 and h2 > 0, ci_lo > 0, s > l
    c4 = bool(non_bear) and all(x > 0 for x in non_bear)
    n = sum((c1, c2, c3, c4))
    return "SURVIVES" if n >= 3 else ("PARTIAL" if n == 2 else "NOISE")


check("판정 SURVIVES: 4개 통과", decide(0.01, 0.01, 0.005, 0.02, 0.00, [0.01]) == "SURVIVES")
check("판정 SURVIVES: 3개 통과", decide(0.01, 0.01, 0.005, 0.00, 0.02, [0.01]) == "SURVIVES")
check("판정 PARTIAL: 2개", decide(0.01, -0.01, 0.005, 0.02, 0.00, [-0.01]) == "PARTIAL")
check("판정 NOISE: 부호 뒤집힘 + CI 0 포함 + 롱도 좋아짐 + bear 전용",
      decide(-0.02, 0.03, -0.005, 0.001, 0.004, [-0.01]) == "NOISE")
check("판정 NOISE: bear 밖 표본이 없으면 ④ 탈락", decide(0.01, 0.01, -0.005, 0.00, 0.02, []) == "NOISE")

print("\n" + ("ALL PASS" if not fails else f"FAILS: {fails}"))
sys.exit(1 if fails else 0)
