"""
method_m / regime_multi 로직 검증 (합성 데이터, 네트워크 없음).

  - RegimeMap.at: 닫힌 봉 라벨만(룩어헤드 없음), 첫 봉 전 None
  - build_from_rows: 상승 추세 → bull_*, 하락 → bear, 히스테리시스로 단일 신호 전환 억제
  - 임계값 스케일 규칙
  - outcome(rule D, daily lab) ≡ method_r.outcome_r("D"), outcome(rule RL) ≡ outcome_r("RL")
  - 필터 arm: 막힌 거래 ret 0 / "filtered", 아니면 D 와 동일
  - 실거래 코드는 regime_multi/method_m 을 import 하지 않음
실행: python test_method_m.py
"""
import random, sys
from datetime import date, timedelta

import method_m as mm
import method_r as mr
import regime_multi as rm

fails = []


def check(n, c, d=""):
    print(("PASS " if c else "FAIL ") + n + ("" if c else f" — {d}"))
    c or fails.append(n)


DAY = 86_400_000
T0 = 1_700_000_000_000


def rows_of(n, seed, drift=0.0, vol=0.02, tf_ms=DAY):
    random.seed(seed); px, out = 100.0, []
    for i in range(n):
        nxt = px * (1 + drift + random.gauss(0, vol))
        d = (date(2024, 1, 1) + timedelta(days=i * tf_ms // DAY)).isoformat()
        out.append(dict(ts=T0 + i * tf_ms, date=d, o=px, h=max(px, nxt) * 1.005, l=min(px, nxt) * 0.995, c=nxt, v=1))
        px = nxt
    return out


# ── 1. RegimeMap ────────────────────────────────────────────────────────────
m = rm.RegimeMap([(100, "bear"), (200, "bull_btc"), (300, "bear")])
check("첫 유효 시각 전 None", m.at(99) is None)
check("유효 시각 정확히 포함", m.at(100) == "bear" and m.at(200) == "bull_btc")
check("구간 내 마지막 라벨", m.at(250) == "bull_btc" and m.at(10_000) == "bear")
check("임계값 스케일: 일봉 20일=0.1%, 주봉 4주=0.14%, 4h 20봉=0.0167%",
      abs(rm.thr_for(20, 1.0) - 0.001) < 1e-12 and abs(rm.thr_for(4, 7.0) - 0.0014) < 1e-12
      and abs(rm.thr_for(20, 1 / 6) - 0.001 / 6) < 1e-12)

# ── 2. build_from_rows ──────────────────────────────────────────────────────
btc_up = rows_of(400, 1, drift=0.004, vol=0.005)
eth_up = rows_of(400, 2, drift=0.005, vol=0.005)
alts = {a: rows_of(400, 10 + i, drift=0.003, vol=0.005) for i, a in enumerate(rm.ALTS[:3])}
mp = rm.build_from_rows(btc_up, eth_up, alts, 50, 10, 10, 15, DAY, 0.001, 0.001)
check("상승 추세 → 라벨 존재·bull 계열", len(mp) > 0 and set(mp.lab) <= {"bull_btc", "bull_altseason"}, set(mp.lab))
check("라벨 유효 시각 = 봉 닫힘(ts+봉길이)", mp.first_ts() % DAY == T0 % DAY and mp.first_ts() > btc_up[60]["ts"])
btc_dn = rows_of(400, 3, drift=-0.004, vol=0.005)
mp2 = rm.build_from_rows(btc_dn, eth_up, alts, 50, 10, 10, 15, DAY, 0.001, 0.001)
check("하락 추세 → bear", len(mp2) > 0 and mp2.lab[-1] == "bear" and mp2.lab.count("bear") > len(mp2) * 0.8, mr._count(mp2.lab))
# 룩어헤드: 마지막 봉을 바꿔도 그 전 라벨 불변
mp3 = rm.build_from_rows(btc_up[:-1] + [dict(btc_up[-1], c=1.0, l=1.0)], eth_up, alts, 50, 10, 10, 15, DAY, 0.001, 0.001)
check("마지막 봉 변경은 이전 봉 라벨에 영향 없음", mp3.lab[:-1] == mp.lab[:-1])

# ── 3. outcome ≡ method_r ───────────────────────────────────────────────────
REGS = ["bull_btc", "bull_altseason", "bear", "sideways", None]
n_eq = 0; mism = []
for trial in range(300):
    rng = random.Random(trial)
    rows = rows_of(80, trial, vol=rng.choice([0.005, 0.02, 0.04]))
    seq, g = [], rng.choice(REGS)
    for _ in rows:
        if rng.random() < 0.15: g = rng.choice(REGS)
        seq.append(g)
    regmap = {r["date"]: g for r, g in zip(rows, seq) if g is not None}
    mr.REGMAP = regmap; mm.REGMAP = regmap
    opp = set(rng.sample(range(80), rng.choice([0, 1, 3]))) if rng.random() < 0.5 else set()
    si = rng.randint(0, 40); direction = "long" if trial % 3 else "short"
    lab = mm.label_fn("daily", rows, "1d")
    ok = True
    for rule in ("D", "RL"):
        a = mm.outcome(rows, si, direction, opp, rule, lab)
        b = mr.outcome_r(rows, si, direction, opp, rule)
        if not (abs(a[0] - b[0]) < 1e-12 and a[1] == b[1] and a[2] == b[2]):
            ok = False; mism.append((trial, rule, a, b))
    n_eq += ok
check("outcome(D/RL, daily) ≡ method_r.outcome_r — 300 무작위 시나리오", n_eq == 300 and not mism, mism[:2])

# ts 기반 라벨: RegimeMap 을 통해 같은 라벨을 주면 결과 동일
rows = rows_of(60, 7, vol=0.01)
seq = ["bear"] * 10 + ["bull_btc"] * 20 + ["bear"] * 30
regmap = {r["date"]: g for r, g in zip(rows, seq)}
mr.REGMAP = regmap; mm.REGMAP = regmap
tsmap = rm.RegimeMap([(r["ts"] + DAY, g) for r, g in zip(rows, seq)])
mm.MAPS = {"slow": tsmap, "fast": tsmap}
lab_ts = mm.label_fn("slow", rows, "1d")
check("ts 조회 라벨 = date 조회 라벨(닫힌 봉 기준)", all(lab_ts(j) == regmap[rows[j]["date"]] for j in range(60)))
check("D_slow 가 daily 와 같은 맵이면 D 와 동일",
      mm.outcome(rows, 5, "long", set(), "D", lab_ts) == mm.outcome(rows, 5, "long", set(), "D", mm.label_fn("daily", rows, "1d")))
# 스케일이 다른 맵: 주봉 라벨(7일마다)로 조회하면 전환 시점이 달라진다
wk = rm.RegimeMap([(rows[0]["ts"] + 7 * DAY * k, ("bear" if k % 2 else "bull_btc")) for k in range(9)])
mm.MAPS["slow"] = wk
lab_w = mm.label_fn("slow", rows, "1d")
check("주봉 맵은 7일 단위로만 바뀜", len({lab_w(j) for j in range(0, 6)}) == 1 and lab_w(0) != lab_w(7))

# ── 4. 필터 ─────────────────────────────────────────────────────────────────
check("롱은 bear 에서 차단, bull/sideways 허용", mm.blocked("long", "bear") and not mm.blocked("long", "bull_btc") and not mm.blocked("long", "sideways"))
check("숏은 bull_* 에서 차단, bear/sideways 허용", mm.blocked("short", "bull_altseason") and not mm.blocked("short", "bear") and not mm.blocked("short", "sideways"))

# ── 5. 실거래 코드 비의존 ────────────────────────────────────────────────────
for f in ("paper_executor.py", "scheduler.py", "exchange.py", "regime_switch.py"):
    src = open(f, encoding="utf-8").read()
    check(f"{f} 는 regime_multi/method_m 을 import 하지 않음", "import regime_multi" not in src and "import method_m" not in src
          and "from regime_multi" not in src)

print(f"\n{len(fails)} failed")
sys.exit(1 if fails else 0)
