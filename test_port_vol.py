"""
test_port_vol.py — validate_port_vol 로직 고정 (네트워크 없음)

고정하는 것 셋:
  1) **프레임 무변경** — size_mult=None 이면 validate_portfolio 의 종전 동작과 완전히 같다.
  2) **수식** — 평균 쌍상관 역산이 쌍을 전부 도는 정의와 정확히 일치하고,
     포트폴리오 σ 가 ρ=0/1 의 극단에서 손계산과 맞는다.
  3) **레짐 전환 청산이 켜져 있는가** — 2026-09-21 에 sizing_vol / validate_portfolio 가
     mt.REGMAP 을 안 채운 채 돌고 있던 것이 발견됐다. 그 재발을 막는다.
"""
import inspect
import io
import contextlib
import math
import random
import statistics as st
from datetime import date, timedelta

import method_t as mt
import sizing as sz
import sizing_vol as sv
import validate_port_vol as vpv
import validate_portfolio as vp

ok = fail = 0


def chk(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
    else:
        fail += 1
        print(f"  FAIL {name} {extra}")


def pair_corr_bruteforce(series):
    """정의 그대로 — 모든 쌍의 피어슨 상관 평균. 역산 공식의 정답지."""
    T = min(len(x) for x in series)
    xs = [x[:T] for x in series]
    zs = []
    for x in xs:
        m = st.fmean(x)
        sd = math.sqrt(sum((v - m) ** 2 for v in x) / (T - 1))
        zs.append([(v - m) / sd for v in x])
    tot = cnt = 0.0
    for i in range(len(zs)):
        for j in range(i + 1, len(zs)):
            tot += sum(a * b for a, b in zip(zs[i], zs[j])) / (T - 1)
            cnt += 1
    return tot / cnt


print("§1 프레임 무변경 — size_mult=None 이 종전 동작")
rng = random.Random(11)
base_day = date(2024, 1, 1).toordinal()


def mk_trades(n, seed):
    r = random.Random(seed)
    out = []
    for i in range(n):
        t_in = base_day + r.randrange(0, 600) + r.random()
        out.append(dict(t_in=t_in, t_out=t_in + r.uniform(0.5, 25),
                        ret=r.gauss(0.01, 0.09), pattern=r.choice(["engulfing", "fvg", "vol_awakening_4h"]),
                        sym=f"S{r.randrange(0, 20)}", vol=r.uniform(0.3, 2.0),
                        tf=r.choice(["1d", "4h"]), rank=r.randrange(0, 30)))
    return sorted(out, key=lambda t: t["t_in"])


for seed in range(6):
    tr = mk_trades(120, seed)
    a = vp.simulate(tr, "current")
    b = vp.simulate(tr, "current", size_mult=None)
    c = vp.simulate(tr, "current", size_mult=lambda ctx: 1.0)
    keys = ("final", "cagr", "mdd", "calmar", "taken", "skip_slot", "skip_margin")
    chk(f"None 은 인자 없는 호출과 동일(seed {seed})", all(a[k] == b[k] for k in keys))
    chk(f"배율 1.0 도 동일(seed {seed})", all(abs(a[k] - c[k]) < 1e-9 for k in keys),
        f"{[(k, a[k], c[k]) for k in keys if abs(a[k]-c[k])>=1e-9]}")

tr = mk_trades(200, 99)
half = vp.simulate(tr, "current", size_mult=lambda ctx: 0.5)
full = vp.simulate(tr, "current")
chk("배율 0.5 는 노출을 낮춘다", half["exposure"] < full["exposure"])
chk("exposure 가 진입당 명목가/equity 평균", full["exposure"] > 0)
chk("cap arm 과 size_mult 는 독립",
    vp.simulate(tr, "current", cap=4)["skip_cap"] > 0)

print("§2 평균 쌍상관 — 역산이 정의와 일치")
for seed in (1, 2, 3):
    r = random.Random(seed)
    common = [r.gauss(0, 1) for _ in range(80)]
    series = [[0.6 * common[t] + 0.8 * r.gauss(0, 1) for t in range(80)] for _ in range(8)]
    a = vpv.avg_pair_corr(series)
    b = pair_corr_bruteforce(series)
    chk(f"역산 == 전수(seed {seed})", abs(a - b) < 1e-9, f"{a} vs {b}")
ident = [[1.0, 2.0, 3.0, 4.0, 5.0]] * 4
chk("완전 동일 계열은 ρ̄=1", abs(vpv.avg_pair_corr(ident) - 1.0) < 1e-9)
chk("계열 1개면 None", vpv.avg_pair_corr([[1.0, 2.0, 3.0]]) is None)
chk("상수 계열은 제외돼 None", vpv.avg_pair_corr([[1.0] * 5, [2.0] * 5]) is None)
anti = [[1.0, 2.0, 3.0, 4.0], [4.0, 3.0, 2.0, 1.0]]
chk("반대 계열은 ρ̄=-1", abs(vpv.avg_pair_corr(anti) + 1.0) < 1e-9)

print("§3 port_sigma — 극단에서 손계산과 맞는가")
wv = [(0.5, 0.8), (0.5, 0.8)]
chk("ρ=1 이면 σ_p = Σwσ", abs(vpv.port_sigma(wv, 1.0) - 0.8) < 1e-12)
chk("ρ=0 이면 σ_p = sqrt(Σ(wσ)²)", abs(vpv.port_sigma(wv, 0.0) - math.sqrt(2 * 0.4 ** 2)) < 1e-12)
chk("ρ=0 이 ρ=1 보다 작다(분산 효과)", vpv.port_sigma(wv, 0.0) < vpv.port_sigma(wv, 1.0))
chk("단일 포지션은 ρ 와 무관",
    abs(vpv.port_sigma([(1.0, 0.9)], 0.0) - vpv.port_sigma([(1.0, 0.9)], 1.0)) < 1e-12)
chk("빈 오픈북은 None", vpv.port_sigma([], 0.7) is None)
chk("포지션이 늘면 σ_p 가 커진다(같은 w)",
    vpv.port_sigma([(0.2, 0.8)] * 4, 0.7) > vpv.port_sigma([(0.2, 0.8)] * 2, 0.7))

print("§4 배율 arm")
rho_of = {"2024-04-24": 0.7}
mkt_of = {"2024-04-24": 0.80}
t = dict(t_in=float(date(2024, 4, 24).toordinal()), vol=0.80, pattern="fvg", sym="X", tf="1d")
ctx = dict(equity=1000.0, free=1000.0, peak=1000.0, open_pos={}, trades=[t], idx=0, t=t["t_in"])
chk("current 는 훅 없음", vpv.make_mult("current", rho_of, mkt_of, 0.8, vpv.date_of) is None)
f_mkt = vpv.make_mult("port_mkt", rho_of, mkt_of, 0.80, vpv.date_of)
chk("port_mkt: σ=TARGET 이면 배율 1", abs(f_mkt(ctx) - 1.0) < 1e-12)
f_mkt2 = vpv.make_mult("port_mkt", rho_of, {"2024-04-24": 1.60}, 0.80, vpv.date_of)
chk("port_mkt: σ 두 배면 배율 0.5", abs(f_mkt2(ctx) - 0.5) < 1e-12)
f_mkt3 = vpv.make_mult("port_mkt", rho_of, {"2024-04-24": 0.05}, 0.80, vpv.date_of)
chk("port_mkt: 상한 2.0 클립", abs(f_mkt3(ctx) - 2.0) < 1e-12)
chk("port_mkt: σ 없으면 중립", vpv.make_mult("port_mkt", rho_of, {}, 0.8, vpv.date_of)(ctx) == 1.0)
f_dd = vpv.make_mult("port_dd", rho_of, mkt_of, None, vpv.date_of)
chk("port_dd: 고점 근처면 1.0", f_dd(ctx) == 1.0)
chk("port_dd: −20% 에서 0.5", f_dd(dict(ctx, equity=800.0)) == 0.5)
chk("port_dd: −19% 는 1.0", f_dd(dict(ctx, equity=810.0)) == 1.0)
f_corr = vpv.make_mult("port_corr", {"2024-04-24": vpv.CORR_REF_RHO}, mkt_of, None, vpv.date_of)
chk("port_corr: ρ̄=기준치면 배율 1.0", abs(f_corr(ctx) - 1.0) < 1e-12)
m_hi = vpv.make_mult("port_corr", {"2024-04-24": 0.95}, mkt_of, None, vpv.date_of)(ctx)
m_lo = vpv.make_mult("port_corr", {"2024-04-24": 0.30}, mkt_of, None, vpv.date_of)(ctx)
chk("port_corr: 상관이 높으면 노출을 줄인다", m_hi < 1.0, f"{m_hi}")
chk("port_corr: 상관이 낮으면 노출을 늘린다", m_lo > 1.0, f"{m_lo}")
chk("port_corr: 포지션 수와 무관(상관 축 전용)",
    f_corr(dict(ctx, open_pos={i: (10.0, 100.0) for i in range(10)}, trades=[t] * 11, idx=0))
    == f_corr(ctx))
chk("port_corr: 배율 상·하한 안", all(vpv.M_LO <= m <= vpv.M_HI for m in (m_hi, m_lo)))
f_pv = vpv.make_mult("port_vol", rho_of, mkt_of, 0.80, vpv.date_of)
mv_empty = f_pv(ctx)
mv_full = f_pv(dict(ctx, open_pos={i: (10.0, 120.0) for i in range(12)}, trades=[t] * 13, idx=0))
chk("port_vol: 오픈북이 찼을수록 배율이 작다", mv_full < mv_empty, f"{mv_full} vs {mv_empty}")
chk("port_vol: 배율 상·하한 안", vpv.M_LO <= mv_full <= vpv.M_HI)
hi_vol = f_pv(dict(ctx, trades=[dict(t, vol=3.0)], idx=0))
chk("port_vol: 고변동 신호면 배율이 더 작다", hi_vol <= mv_empty)

print("§5 판정 J1~J6")
def R(cagr, mdd, calmar, exp):
    return dict(cagr=cagr, mdd=mdd, calmar=calmar, exposure=exp)
good_tr = {"current": R(0.10, -0.30, 0.33, 1.00), "port_vol": R(0.12, -0.28, 0.43, 1.00)}
good_ho = {"current": R(0.05, -0.40, 0.13, 1.00), "port_vol": R(0.08, -0.38, 0.21, 1.00)}
j, ex = vpv.judge(good_tr, good_ho, 0.70)
chk("전부 충족", all(j.values()) and abs(ex - 1.0) < 1e-12)
j, _ = vpv.judge(good_tr, good_ho, 0.59)
chk("J3 부트 0.59 는 탈락", not j["J3 부트 우위>=0.60"])
j, _ = vpv.judge(good_tr, good_ho, 0.60)
chk("J3 부트 0.60 은 통과", j["J3 부트 우위>=0.60"])
bad_ex = {"current": R(0.05, -0.40, 0.13, 1.00), "port_vol": R(0.08, -0.38, 0.21, 0.70)}
j, ex = vpv.judge(good_tr, bad_ex, 0.70)
chk("J6 노출 0.70x 는 탈락(작게 걸어 얻은 개선)", not j["J6 노출 0.90~1.10x"])
chk("J6 외 나머지는 통과", sum(1 for k, v in j.items() if not v) == 1)
j, _ = vpv.judge(good_tr, {"current": R(0.05, -0.40, 0.13, 1.0),
                           "port_vol": R(0.08, -0.46, 0.21, 1.0)}, 0.70)
chk("J4 MDD 6%p 악화는 탈락", not j["J4 MDD 악화<=5%p"])
j, _ = vpv.judge(good_tr, {"current": R(0.05, -0.40, 0.13, 1.0),
                           "port_vol": R(0.08, -0.45, 0.21, 1.0)}, 0.70)
chk("J4 MDD 5%p 정확히는 통과", j["J4 MDD 악화<=5%p"])
j, _ = vpv.judge({"current": R(0.10, -0.30, 0.33, 1.0), "port_vol": R(0.09, -0.30, 0.30, 1.0)},
                 good_ho, 0.70)
chk("J5 train 열세는 탈락", not j["J5 train 도 우위"])

print("§6 레짐 전환 청산이 켜져 있는가 (2026-09-21 결함 재발 방지)")
d0 = date(2025, 1, 1)
rows = [dict(date=(d0 + timedelta(days=i)).isoformat(), ts=0,
             o=100.0, h=101.0, l=99.0, c=100.0 + i * 0.1, v=1.0) for i in range(40)]
saved = mt.REGMAP
mt.REGMAP = {}
mt._REGMAP_WARNED = False
err = io.StringIO()
with contextlib.redirect_stderr(err):
    empty = mt.outcome_d(rows, 5, "long", set())
chk("빈 REGMAP 이면 경고를 낸다", "REGMAP 이 비어" in err.getvalue())
chk("경고는 한 번만", err.getvalue().count("[경고]") == 1)
chk("빈 REGMAP 이면 레짐 청산이 사라진다(결함의 실체)", empty[2] == "maxhold")
mt.REGMAP = {r["date"]: ("bull_btc" if i < 8 else "bear") for i, r in enumerate(rows)}
filled = mt.outcome_d(rows, 5, "long", set())
chk("REGMAP 이 있으면 레짐 전환 청산이 작동", filled[2] == "regime_switch")
chk("결과가 실제로 달라진다", filled[1] != empty[1])
chk("regmap_ready 가 상태를 알려준다", mt.regmap_ready() and not (lambda: (
    setattr(mt, "REGMAP", {}) or mt.regmap_ready()))())
mt.REGMAP = saved
for mod in (vp, sv, vpv):
    chk(f"{mod.__name__}.main 이 REGMAP 을 세운다", "REGMAP" in inspect.getsource(mod.main))

print("§7 동결 상수 / 배포 금지")
chk("DEPLOY_ON_PASS False", vpv.DEPLOY_ON_PASS is False)
chk("주 판정 arm 은 port_vol", vpv.MAIN_ARM == "port_vol")
chk("arm 5개", vpv.ARMS == ["current", "port_vol", "port_mkt", "port_corr", "port_dd"])
chk("배율 상·하한이 건당 타겟팅과 같다", (vpv.M_LO, vpv.M_HI) == (sz.VOL_LO, sz.VOL_HI) == (0.5, 2.0))
chk("ρ̄ 창 60 / 최소 30 / 기본 0.70",
    (vpv.RHO_WIN, vpv.RHO_MIN, vpv.RHO_DEFAULT) == (60, 30, 0.70))
chk("J6 대역 0.90~1.10", (vpv.J6_LO, vpv.J6_HI) == (0.90, 1.10))
chk("J3/J4 는 validate_portfolio 와 공유", vpv.J3_WIN == vp.J3_WIN and vpv.J4_MDD_TOL == vp.J4_MDD_TOL)
chk("분할·사이징 상수는 실거래 고정",
    vpv.SPLIT == "2025-01-01" and vpv.MAX_POS == 13 and vpv.STOP == 0.08)
chk("port_dd 문턱 −20% / 0.5배", (vpv.DD_TRIP, vpv.DD_MULT) == (0.20, 0.5))

print(f"\n{'='*60}\n통과 {ok} / 실패 {fail}\n{'='*60}")
raise SystemExit(1 if fail else 0)
