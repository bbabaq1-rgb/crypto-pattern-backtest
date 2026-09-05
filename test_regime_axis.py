"""
regime_axis(레짐 추가 축 진단) 로직 검증 (합성 데이터, 네트워크 없음).

  - adx/er/volpct/alt_breadth/beta_slope 가 전부 **인과적** (진입 이후를 바꿔도 불변)
  - 각 축이 아는 신호에 대해 기대 방향으로 반응한다(추세 vs 횡보, 알트 강세 vs 약세)
  - 3분위 진단의 사전 기준 A/B/C 분기
  - avg_cap 은 새 후보가 아니라 **비교 기준**으로 분류돼 있다
실행: python test_regime_axis.py
"""
import random
import statistics as st
import sys

import regime_axis as ra

fails = []


def check(n, c, d=""):
    print(("PASS " if c else "FAIL ") + n + ("" if c else f" — {d}"))
    c or fails.append(n)


def bars(closes, day0=1):
    out = []
    for i, c in enumerate(closes):
        o = closes[i - 1] if i else c
        out.append(dict(date=f"2024-{1 + i // 28:02d}-{1 + i % 28:02d}",
                        o=o, h=max(o, c) * 1.005, l=min(o, c) * 0.995, c=c, v=1000.0))
    return out


# ── 1. 축이 기대 방향으로 반응 ─────────────────────────────────────────────
# 합성 픽스처는 **현실적이어야** 한다. 완전 매끈한 톱니는 고가·저가가 매 봉 동일해
# 방향운동(DM)이 0 이 되고, 초기 한 봉의 비대칭이 ADX 를 100 으로 끌고 간다(1차 작성 시
# 실제로 그렇게 나왔다). 잡음 있는 추세 vs 잡음 있는 횡보로 비교한다.
random.seed(41)
_p, _tr = 100.0, []
for _ in range(200):                                   # 강한 추세 + 잡음
    _p *= 1 + 0.012 + random.gauss(0, 0.004); _tr.append(_p)
trend = bars(_tr)
_lvl, _ch = 100.0, []
for _ in range(200):                                   # 수준 회귀형 횡보
    _lvl += (100.0 - _lvl) * 0.35 + random.gauss(0, 2.0); _ch.append(_lvl)
chop = bars(_ch)
check("ADX: 추세 > 횡보", ra.adx_series(trend)[150] > ra.adx_series(chop)[150],
      f"{ra.adx_series(trend)[150]:.1f} vs {ra.adx_series(chop)[150]:.1f}")
check("효율비: 추세는 1 에 가깝고 횡보는 0 에 가깝다",
      ra.er_series(trend)[150] > 0.9 and ra.er_series(chop)[150] < 0.2,
      f"{ra.er_series(trend)[150]:.2f} vs {ra.er_series(chop)[150]:.2f}")
check("효율비 범위 0~1", all(0 <= x <= 1 for x in ra.er_series(trend) if x is not None))
check("ADX 범위 0~100", all(0 <= x <= 100 for x in ra.adx_series(trend) if x is not None))

# ── 2. 인과성 ──────────────────────────────────────────────────────────────
random.seed(1)
base = bars([100 * (1 + random.gauss(0, 0.02)) ** 1 for _ in range(1)] and
            [100 * __import__("math").exp(sum(random.gauss(0, 0.02) for _ in range(i + 1)))
             for i in range(250)])
fut = [dict(x) for x in base]
for j in range(151, 250):
    fut[j]["c"] *= 4; fut[j]["h"] *= 4; fut[j]["l"] *= 4; fut[j]["o"] *= 4
check("ADX 인과적", ra.adx_series(base)[150] == ra.adx_series(fut)[150])
check("효율비 인과적", ra.er_series(base)[150] == ra.er_series(fut)[150])
vb, vf = ra.btc_vol_pct(base), ra.btc_vol_pct(fut)
d150 = base[150]["date"]
check("변동성 백분위 인과적", vb.get(d150) == vf.get(d150))

btc = base
# 종목마다 베타를 다르게 준다 — 전부 같은 경로면 횡단면 분산이 0 이라 beta_slope 가
# 계산되지 않는다(1차 작성 시 0건이 나왔다). 여기서는 개별 잡음으로 이질성을 만든다.
def _alts(drift, seed0):
    out = {}
    for k in range(12):
        random.seed(seed0 + k)
        px, rows = 100.0, []
        for i, c in enumerate(base):
            br = 0.0 if i == 0 else (base[i]["c"] - base[i - 1]["c"]) / base[i - 1]["c"]
            beta = 0.5 + 0.15 * k                      # 종목별 베타 0.5~2.15
            px *= 1 + drift + beta * br + random.gauss(0, 0.005)
            rows.append(px)
        out[f"A{k}"] = bars(rows)
    return out


alts_strong = _alts(+0.002, 100)
alts_weak = _alts(-0.002, 200)
# breadth 는 정의(90일 수익률이 BTC 초과)를 직접 검사한다 — 베타 1 에 상수 초과수익만
# 얹은 픽스처가 맞다. 이질 베타 픽스처(alts_strong)는 국면에 따라 승패가 섞여 정의 검사에
# 부적합하다(1차 작성 시 양쪽 다 0.33 이 나왔다).
def _alts_rel(daily_edge):
    out = {}
    for k in range(12):
        px, rows = 100.0, []
        for i, c in enumerate(base):
            br = 0.0 if i == 0 else (base[i]["c"] - base[i - 1]["c"]) / base[i - 1]["c"]
            px *= 1 + br + daily_edge
            rows.append(px)
        out[f"A{k}"] = bars(rows)
    return out


bs = ra.alt_breadth_series(dict(BTC=btc, **_alts_rel(+0.003)), btc)
bw = ra.alt_breadth_series(dict(BTC=btc, **_alts_rel(-0.003)), btc)
check("alt_breadth: 알트가 BTC 를 이기면 1 에 가깝다", bs.get(d150, 0) > 0.9, str(bs.get(d150)))
check("alt_breadth: 알트가 지면 0 에 가깝다", bw.get(d150, 1) < 0.1, str(bw.get(d150)))
check("alt_breadth: 90일 룩백 이전에는 값이 없다 (인과적)",
      all(d >= base[ra.BREADTH_LB]["date"] for d in bs))
check("alt_breadth 범위 0~1", all(0 <= v <= 1 for v in bs.values()))

sl = ra.beta_slope_series(dict(BTC=btc, **alts_strong), btc)
check("beta_slope: 값이 산출된다", len(sl) > 50, str(len(sl)))
check("beta_slope 유한", all(isinstance(v, float) and v == v for v in sl.values()))

# ── 3. 3분위 진단 기준 ─────────────────────────────────────────────────────
random.seed(7)
# 축이 성과를 실제로 가르는 인공 데이터: 축 값이 높을수록 수익이 높다(단조)
good = [(0.02 * (x / 100) - 0.01 + random.gauss(0, 0.002), x) for x in range(300)]
r = ra.diagnose("t", good)
check("진단: 축이 실제로 가르면 real=True", r["real"], str(r))
check("진단: 단조성 검출", r["B_monotone"])
check("진단: 불리 분위 음수 검출", r["C_neg_tail"])
# 축이 무관한 데이터
noise = [(random.gauss(0.005, 0.02), random.random()) for _ in range(300)]
rn = ra.diagnose("t", noise)
check("진단: 무관한 축은 real=False", not rn["real"], str(rn.get("boot_p")))
# 단조가 아닌 데이터(가운데만 높음) — 유의해도 B 에서 탈락해야 한다
hump = [(0.03 if 100 <= x < 200 else -0.01, x) for x in range(300)]
rh = ra.diagnose("t", hump)
check("진단: 비단조면 real=False (유의해도 탈락)", not rh["real"] and not rh["B_monotone"])
# 불리 분위가 양수면 걸러낼 구간이 없다 → C 탈락
allpos = [(0.01 + 0.02 * (x / 300), x) for x in range(300)]
rp = ra.diagnose("t", allpos)
check("진단: 전 분위가 양수면 real=False (걸러낼 구간 없음)", not rp["real"] and not rp["C_neg_tail"])
check("진단: 표본 부족이면 skip", "skip" in ra.diagnose("t", [(0.0, 1)] * 10))

# ── 4. 설계 고정 ───────────────────────────────────────────────────────────
check("avg_cap 은 새 후보가 아니라 비교 기준",
      "avg_cap" in ra.AXES and "avg_cap" not in ra.NEW_AXES)
check("신규 축 5종", ra.NEW_AXES == ["adx", "er", "volpct", "alt_breadth", "beta_slope"])
src = open("regime_axis.py", encoding="utf-8").read()
check("문서에 cap_score 기시험 사실이 남아 있다 (β⁺−β⁻ 중복 방지)",
      "cap_score" in src and "2026-07-08" in src)
check("1단계만 실행하고 2단계는 별도 등록임을 명시", "2단계는 이번에 실행하지 않는다" in src)
check("생존 편향 유보가 출력에 남는다", "생존 편향" in src)
check("동결: breadth 90일 / beta 60일·20일 평활",
      (ra.BREADTH_LB, ra.BETA_LB, ra.BETA_SMOOTH) == (90, 60, 20))

print("\n" + ("ALL PASS" if not fails else f"FAILS: {fails}"))
sys.exit(1 if fails else 0)
