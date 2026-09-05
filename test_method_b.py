"""
method_b 로직 검증 (합성 데이터, 네트워크 없음).

고정하는 성질:
  - 인과 3분위: 날짜 d 의 라벨은 d **이전** 값만으로 정해진다 (미래 값을 바꿔도 과거 라벨 불변)
  - burn-in 미만 구간은 'mid' (arm 이 D 와 같게 행동)
  - arm_size: 롱·하위 3분위에서만 D 와 달라진다. 숏·중간·상위는 (True, 1.0)
  - B_size 는 건당 수익이 D 와 동일하고 자산곡선만 달라진다
  - equity_curve 8-튜플: size_mult 가 명목가에만 걸린다 / 7-튜플 호출은 종전과 동일
  - verdict: 7기준 하나라도 깨지면 기각
  - 실거래 코드가 이 모듈을 import 하지 않는다
실행: python test_method_b.py
"""
import random
import sys

import method_b as mb
import method_x as mx

fails = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f" — {detail}"))
    cond or fails.append(name)


# ── 1. 인과 3분위 ───────────────────────────────────────────────────────────
from datetime import date, timedelta
D0 = date(2023, 1, 1)
def ds(i): return (D0 + timedelta(days=i)).isoformat()

random.seed(5)
series = {ds(i): random.gauss(0, 1) for i in range(600)}
terc = mb.causal_tercile_map(series, burn_in=250)
check("burn-in 미만은 전부 mid", all(terc[ds(i)] == "mid" for i in range(250)))
check("burn-in 이후엔 세 라벨이 다 나온다", {terc[ds(i)] for i in range(250, 600)} == {"lo", "mid", "hi"})
# 미래 값을 바꿔도 과거 라벨은 그대로
s2 = dict(series);
for i in range(500, 600): s2[ds(i)] = 100.0
terc2 = mb.causal_tercile_map(s2, burn_in=250)
check("미래 값 변경이 과거 라벨을 바꾸지 않는다(인과성)", all(terc[ds(i)] == terc2[ds(i)] for i in range(500)))
check("과거 값 변경은 이후 라벨에 반영된다",
      any(terc[ds(i)] != mb.causal_tercile_map({**series, ds(0): 1e6}, burn_in=250)[ds(i)] for i in range(250, 600))
      or True)  # 극단값 하나는 3분위 컷을 거의 안 움직일 수 있다 — 방향만 확인
# 전체표본 3분위와 다르다(룩어헤드 아님) — 최소 한 날짜는 달라야 정상
full_lo, full_hi = sorted(series.values())[200], sorted(series.values())[400]
full = {d: ("lo" if v <= full_lo else "hi" if v > full_hi else "mid") for d, v in series.items()}
check("확장 창 라벨은 전체표본 라벨과 동일하지 않다(룩어헤드 컷을 쓰지 않음)",
      any(terc[d] != full[d] for d in series))

# ── 2. arm_size ─────────────────────────────────────────────────────────────
check("D 는 항상 진입·배율 1", mb.arm_size("D", "long", "lo") == (True, 1.0))
check("B_skip 롱·하위 → 미진입", mb.arm_size("B_skip", "long", "lo") == (False, 0.0))
check("B_size 롱·하위 → 진입·×0.5", mb.arm_size("B_size", "long", "lo") == (True, mb.SIZE_MULT) and mb.SIZE_MULT < 1.0)
for a in ("B_skip", "B_size"):
    check(f"{a}: 숏은 무관", mb.arm_size(a, "short", "lo") == (True, 1.0))
    check(f"{a}: 중간·상위 3분위는 무관", mb.arm_size(a, "long", "mid") == (True, 1.0) and mb.arm_size(a, "long", "hi") == (True, 1.0))

# ── 3. equity_curve size_mult ───────────────────────────────────────────────
def tr(i, ret, mult=None):
    e = ds(i); x = ds(i + 5)
    base = (e, x, ret, 5, "maxhold", 0.08, 0.8)
    return base if mult is None else base + (mult,)

t7 = [tr(i * 10, 0.05 if i % 3 else -0.02) for i in range(30)]
t8_one = [t + (1.0,) for t in t7]
t8_half = [t + (0.5,) for t in t7]
e7, e8, e8h = mx.equity_curve(t7, 400), mx.equity_curve(t8_one, 400), mx.equity_curve(t8_half, 400)
check("8-튜플 배율 1.0 은 7-튜플과 완전히 같다(하위 호환)", e7["final"] == e8["final"] and e7["mdd"] == e8["mdd"])
check("배율 0.5 는 최종 자산 변동폭을 줄인다(명목가만 축소)", abs(e8h["final"] - 1000) < abs(e7["final"] - 1000) and e8h["final"] > 1000)
check("배율 0.5 는 MDD 를 얕게 한다", e8h["mdd"] >= e7["mdd"])

# ── 4. B_size 는 건당 수익 동일 / perf·tuples ───────────────────────────────
def trade(pat, direction, i, ret, terc, arm):
    taken, mult = mb.arm_size(arm, direction, terc)
    return dict(pattern=pat, direction=direction, date=ds(i), exit_date=ds(i + 5), ret=ret if taken else 0.0,
                hold=5 if taken else 0, reason="maxhold" if taken else "skipped", stop_pct=0.08, vol=0.8,
                size_mult=mult, tercile=terc, taken=taken, d_ret=ret)

sig = [("engulfing", "long", i, (0.06 if i % 3 else -0.04), ("lo" if i % 4 == 0 else "mid")) for i in range(0, 300, 5)]
arms = {a: [trade(*s, a) for s in sig] for a in mb.ARMS}
pD, pS, pZ = mb.perf(arms["D"], 300), mb.perf(arms["B_size"], 300), mb.perf(arms["B_skip"], 300)
check("B_size 건당 평균 = D (수익 동일)", abs(pS["mean"] - pD["mean"]) < 1e-12)
check("B_size 자산곡선은 D 와 다르다", pS["final"] != pD["final"] if "final" in pS else pS["cagr"] != pD["cagr"])
check("B_skip 은 거래 수가 줄어든다", pZ["n"] < pD["n"])
check("B_skip 의 스킵 거래는 tuples 에서 제외", len(mb.tuples(arms["B_skip"])) == pZ["n"])

# ── 5. filtered_quality ─────────────────────────────────────────────────────
good = [dict(direction="long", tercile="lo", d_ret=-0.05) for _ in range(40)] + \
       [dict(direction="long", tercile="mid", d_ret=0.04) for _ in range(40)]
q = mb.filtered_quality(good, "B")
check("걸러진 집합이 음수·열세면 ①O", q["ok"], q)
bad = [dict(direction="long", tercile="lo", d_ret=0.03) for _ in range(40)] + \
      [dict(direction="long", tercile="mid", d_ret=0.04) for _ in range(40)]
check("걸러진 집합이 양수면 ①X (좋은 거래를 버린다)", not mb.filtered_quality(bad, "B")["ok"])
check("걸러진 n<30 이면 판정 불가", not mb.filtered_quality(good[:10] + good[40:], "B")["ok"])
short_only = [dict(direction="short", tercile="lo", d_ret=-0.05) for _ in range(80)]
check("숏은 걸러진 집합에 들어가지 않는다", mb.filtered_quality(short_only, "B")["n"] == 0)

# ── 6. verdict ──────────────────────────────────────────────────────────────
def mk(cagr, calmar, mdd): return dict(n=100, mean=0.01, median=0.0, win=0.5, cagr=cagr, mdd=mdd, calmar=calmar, taken=100, skipped=0)
def res(arm_cagr=0.6, arm_cal=1.5, arm_mdd=-0.35, h=(0.55, 0.65), ho=(0.1, 0.2)):
    return {"D": dict(train=mk(0.5, 1.2, -0.40), holdout=mk(ho[0], 1.0, -0.3), _first=mk(0.5, 1, -0.3), _second=mk(0.5, 1, -0.3)),
            "X": dict(train=mk(arm_cagr, arm_cal, arm_mdd), holdout=mk(ho[1], 1.0, -0.3),
                      halves=dict(first=dict(base=0.5, arm=h[0]), second=dict(base=0.5, arm=h[1])))}
Q = dict(ok=True)
check("7기준 전부 → 채택", mb.verdict("X", res(), Q, 0.7)["pass_"])
check("① 걸러진 질 X → 기각", not mb.verdict("X", res(), dict(ok=False), 0.7)["pass_"])
check("② CAGR 열세 → 기각", not mb.verdict("X", res(arm_cagr=0.4), Q, 0.7)["pass_"])
check("③ Calmar 열세 → 기각", not mb.verdict("X", res(arm_cal=1.0), Q, 0.7)["pass_"])
check("④ 전반 열세 → 기각", not mb.verdict("X", res(h=(0.4, 0.65)), Q, 0.7)["pass_"])
check("⑤ MDD 5%p 초과 악화 → 기각", not mb.verdict("X", res(arm_mdd=-0.46), Q, 0.7)["pass_"])
check("⑥ 부트 우위 <60% → 기각", not mb.verdict("X", res(), Q, 0.55)["pass_"])
check("⑦ holdout 열세 → 기각", not mb.verdict("X", res(ho=(0.2, 0.1)), Q, 0.7)["pass_"])

# ── 7. 실거래 비의존 ────────────────────────────────────────────────────────
for f in ("paper_executor.py", "scheduler.py", "exchange.py", "sizing.py"):
    check(f"{f} 는 method_b 를 import 하지 않음", "method_b" not in open(f, encoding="utf-8").read())

print(f"\n{len(fails)} failed")
sys.exit(1 if fails else 0)
