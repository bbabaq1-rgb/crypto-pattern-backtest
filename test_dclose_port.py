"""test_dclose_port.py — validate_dclose_port 고정: D_close 청산 논리 · 훅 동작 불변 · 짝지음 정렬 · 판정 규칙."""
import random
import sys

import method_t as mt
import validate_dclose as vd
import validate_dclose_port as dp
import validate_portfolio as vp
import validate_regime_split_all as va

fails = []


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f" — {extra}"))
    if not cond:
        fails.append(name)


def mk(n=120, price=100.0, ts0=1_700_000_000_000):
    rows = []
    for i in range(n):
        rows.append(dict(date=f"2024-{1 + i // 28:02d}-{1 + i % 28:02d}", ts=ts0 + i * 14_400_000,
                         o=price, h=price * 1.003, l=price * 0.997, c=price, v=1000.0))
    return rows


mt.REGMAP = {}
check("DEPLOY_ON_PASS=False", dp.DEPLOY_ON_PASS is False)
check("동결 상수", dp.CAT == 0.15 and dp.STOP == 0.08 and dp.SPLIT == "2025-01-01" and dp.J3_WIN == 0.60)

# ── 청산 논리 ────────────────────────────────────────────────────────────
r = mk(); r[10].update(l=90.0, c=95.0)       # 저가는 −10% 지만 종가는 −5%: D 는 손절, D_close 는 버틴다
d = mt.outcome_d(r, 5, "long", set())
c = dp.outcome_d_close(r, 5, "long", set())
check("D 는 저가 손절", d[2] == "stop" and d[1] == 5, d)
check("D_close 는 종가 −5% 에서 버틴다(만기까지)", c[2] == "maxhold", c)

r = mk(); r[10].update(l=90.0, c=91.0)       # 종가 −9% → 종가 손절
c = dp.outcome_d_close(r, 5, "long", set())
check("종가 ≤ −8% 면 그 종가에 청산", c[2] == "sl_close" and abs(c[0] - (0.91 - 1 - mt.FEE)) < 1e-9, c)

r = mk(); r[10].update(l=80.0, c=91.0)       # 저가 −20% → 재해 손절 −15% 가 먼저
c = dp.outcome_d_close(r, 5, "long", set())
check("재해 손절 −15%(저가)", c[2] == "cat_stop" and abs(c[0] - (-0.15 - mt.FEE)) < 1e-9, c)

r = mk(); r[10].update(h=110.0, c=109.0)     # 숏: 종가 +9% → 종가 손절, 손실 부호
c = dp.outcome_d_close(r, 5, "short", set())
check("숏 종가 손절 대칭", c[2] == "sl_close" and abs(c[0] - (1 - 1.09 - mt.FEE)) < 1e-9, c)
r = mk(); r[10].update(h=130.0, c=109.0)
check("숏 재해 손절 +15%", dp.outcome_d_close(r, 5, "short", set())[2] == "cat_stop")

r = mk(); r[8]["c"] = 102.0
check("opp 신호 청산은 D 와 동일", dp.outcome_d_close(r, 5, "long", {8}) == mt.outcome_d(r, 5, "long", {8}))
mt.REGMAP = {rr["date"]: ("a" if i < 7 else "b") for i, rr in enumerate(mk())}
r = mk(); r[8]["c"] = 103.0
check("레짐 전환 청산은 D 와 동일", dp.outcome_d_close(r, 5, "long", set()) == mt.outcome_d(r, 5, "long", set()))
mt.REGMAP = {}
r = mk()
check("아무 일 없으면 만기도 D 와 동일", dp.outcome_d_close(r, 5, "long", set()) == mt.outcome_d(r, 5, "long", set()))

# 저가·종가 모두 −8% 미만으로 안 가면 모든 경로에서 D 와 일치 (난수 경로)
rng = random.Random(7)
same = 0
for _ in range(200):
    rows = mk()
    p = 100.0
    for i in range(1, len(rows)):
        p *= 1 + rng.uniform(-0.012, 0.012)
        rows[i].update(o=p, c=p, h=p * 1.004, l=p * 0.996)
    a, b = mt.outcome_d(rows, 3, "long", set()), dp.outcome_d_close(rows, 3, "long", set())
    if min(x["l"] for x in rows[4:34]) > 100.0 * 0.92 or a[2] != "stop":
        same += (a == b)
check("저가 손절이 없는 난수 경로는 D 와 완전히 동일", same > 150, same)

# R-002 모듈과 롱 한정 일치 (같은 규칙의 두 구현)
agree = 0
for _ in range(100):
    rows = mk()
    p = 100.0
    for i in range(1, len(rows)):
        p *= 1 + rng.uniform(-0.03, 0.03)
        rows[i].update(o=p, c=p, h=p * 1.01, l=p * 0.99)
    lab = lambda j, rows=rows: mt.REGMAP.get(rows[j]["date"])
    x, y = vd.outcome_d_close(rows, 3, lab, cat=0.15), dp.outcome_d_close(rows, 3, "long", set())
    agree += (abs(x[0] - y[0]) < 1e-12 and x[1:] == y[1:])
check("롱에서 validate_dclose.outcome_d_close 와 일치(100 경로)", agree == 100, agree)

# ── 훅: None 이면 종전 동작과 완전히 같다 ───────────────────────────────────
rows_by = {"AAA": mk(), "BBB": mk(price=50.0)}
for rs_ in rows_by.values():
    for i, x in enumerate(rs_):
        w = 0.01 * ((i % 7) - 3)
        x.update(c=x["o"] * (1 + w), h=x["o"] * 1.02, l=x["o"] * 0.98)
rows_by["AAA"][40].update(l=70.0, c=88.0)
orig = va.PATTERNS
stub = lambda rows: [30, 36]
va.PATTERNS = [(p, "4h", stub, "long", "") for p, _g, _c in vp.ADOPTED_4H]
try:
    base = vp.collect_4h(rows_by, ["AAA", "BBB"], {})
    expl = vp.collect_4h(rows_by, ["AAA", "BBB"], {}, outcome_fn=mt.outcome_d)
    alt = vp.collect_4h(rows_by, ["AAA", "BBB"], {}, outcome_fn=dp.outcome_d_close)
finally:
    va.PATTERNS = orig
check("collect_4h 훅 기본값 = mt.outcome_d (결과 동일)", base == expl and len(base) > 0, len(base))
check("대체 청산을 넘기면 신호는 같고 청산만 달라진다",
      [(a["sym"], a["pattern"], a["t_in"]) for a in base] == [(a["sym"], a["pattern"], a["t_in"]) for a in alt]
      and any(a["ret"] != b["ret"] for a, b in zip(base, alt)))

import inspect
check("훅 인자 기본값 None (collect_1d/collect_4h/collect_all)",
      all(inspect.signature(f).parameters["outcome_fn"].default is None
          for f in (vp.collect_1d, vp.collect_4h, vp.sv.collect_all)))
check("simulate 시그니처 불변", list(inspect.signature(vp.simulate).parameters) == ["trades", "arm", "cap", "size_mult"])

# ── 짝지음 정렬·판정 ─────────────────────────────────────────────────────────
def T(t_in, hold, ret, sym="A", pat="p"):
    return dict(t_in=float(t_in), t_out=float(t_in + hold), ret=ret, pattern=pat, sym=sym, vol=0.8, tf="4h", rank=0)


dl = [T(2, 3, 0.01), T(1, 3, -0.08), T(1, 2, 0.02, "B")]
cl = [T(1, 5, -0.09), T(1, 2, 0.02, "B"), T(2, 6, 0.01)]
a, b = dp.pair_trades(dl, cl)
check("pair_trades 가 같은 신호끼리 인덱스 정렬", all(dp._key(x) == dp._key(y) for x, y in zip(a, b)))
try:
    dp.pair_trades(dl, cl[:2]); ok = False
except AssertionError:
    ok = True
check("신호 집합이 다르면 즉시 실패", ok)

mk_r = lambda cagr, mdd, calmar, exp=1.0: dict(cagr=cagr, mdd=mdd, calmar=calmar, exposure=exp)
J, v = dp.judge(mk_r(.2, -.3, .67), mk_r(.3, -.31, 1.0), mk_r(.1, -.2, .5), mk_r(.1, -.2, .5), .7)
check("전부 충족이면 ADOPT_CANDIDATE", v == "ADOPT_CANDIDATE" and all(J.values()), J)
for name, args in dict(
        J1=(mk_r(.3, -.3, .67), mk_r(.2, -.3, .8), mk_r(.1, -.2, .5), mk_r(.1, -.2, .5), .7),
        J2=(mk_r(.2, -.3, .9), mk_r(.3, -.3, .8), mk_r(.1, -.2, .5), mk_r(.1, -.2, .5), .7),
        J3=(mk_r(.2, -.3, .5), mk_r(.3, -.3, .8), mk_r(.1, -.2, .5), mk_r(.1, -.2, .5), .5),
        J4=(mk_r(.2, -.3, .5), mk_r(.3, -.4, .8), mk_r(.1, -.2, .5), mk_r(.1, -.2, .5), .7),
        J5=(mk_r(.2, -.3, .5), mk_r(.3, -.3, .8), mk_r(.2, -.2, .5), mk_r(.1, -.2, .5), .7),
        J6=(mk_r(.2, -.3, .5, 1.0), mk_r(.3, -.3, .8, 1.5), mk_r(.1, -.2, .5), mk_r(.1, -.2, .5), .7)).items():
    J, v = dp.judge(*args)
    check(f"{name} 하나만 실패해도 REJECTED", v == "REJECTED" and not J[name], J)

# paired_boot: 두 목록이 같으면 우위 0
tl = [T(i, 3, 0.01 if i % 3 else -0.08, sym=f"S{i%5}") for i in range(80)]
check("동일 목록이면 부트 우위 0 (엄격 부등호)", dp.paired_boot(tl, [dict(t) for t in tl], random.Random(1), n_boot=20) == 0.0)

if fails:
    print(f"\n{len(fails)} FAIL"); sys.exit(1)
print("\nALL PASS")
