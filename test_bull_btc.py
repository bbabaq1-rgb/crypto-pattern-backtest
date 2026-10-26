"""test_bull_btc.py — validate_bull_btc 로직 고정 (네트워크 없음)"""
import math
import random
from datetime import date

import validate_bull_btc as v
import validate_portfolio as vp

ok = fail = 0
def chk(n, c, x=""):
    global ok, fail
    if c: ok += 1
    else: fail += 1; print("  FAIL", n, x)

def D(s): return float(date.fromisoformat(s).toordinal())
def T(pat, d, ret, hold=2, vol=0.8, rank=0, sym="X"):
    return dict(pattern=pat, t_in=D(d), t_out=D(d) + hold, ret=ret, sym=sym, vol=vol, tf="1d", rank=rank)

print("§1 태그·제거 규칙")
reg = {"2025-01-01": "bull_btc", "2025-01-02": "bear"}
b = v.tag([T("engulfing", "2025-01-01", .1), T("engulfing_short", "2025-01-01", .1),
           T("fvg", "2025-01-02", .1), T("vol_awakening_4h", "2025-01-01", .1)], reg)
chk("진입 레짐 부착", [t["reg"] for t in b] == ["bull_btc", "bull_btc", "bear", "bull_btc"])
chk("방향: *_short 만 숏", [t["dir"] for t in b] == ["long", "short", "long", "long"])
chk("제거 = bull_btc 이고 롱", [v.is_removed(t) for t in b] == [True, False, False, True])
a = v.make_arms(b)
chk("current 불변", a["current"] == b)
chk("arm 은 bull_btc 롱만 제거", len(a["no_bull_btc_long"]) == 2)
chk("레짐 미판정(None) 은 제거 안 함", not v.is_removed(dict(reg=None, dir="long")))

print("§2 path 훅은 종전 결과를 바꾸지 않는다 (동작 불변)")
rng = random.Random(7)
trs = [T("engulfing", date.fromordinal(739000 + rng.randrange(400)).isoformat(), rng.uniform(-.1, .15), hold=rng.randrange(1, 9),
         vol=rng.uniform(.4, 1.5), rank=rng.randrange(30), sym="S%d" % i) for i in range(120)]
trs.sort(key=lambda t: t["t_in"])
r0 = vp.simulate(trs, "current")
p = []
r1 = vp.simulate(trs, "current", path=p)
chk("path 유무와 무관하게 동일", all(r0[k] == r1[k] for k in ("final", "cagr", "mdd", "calmar", "taken", "skip_slot", "skip_margin")))
chk("path 기록 시각 단조", all(p[i][0] <= p[i + 1][0] for i in range(len(p) - 1)) and len(p) > 0)
chk("마지막 path equity = final", abs(p[-1][1] - r0["final"]) < 1e-6)

print("§3 구간 로그수익")
path = [(D("2025-01-03") + .5, 1000.0), (D("2025-01-05") + .5, 1100.0)]
eod = v.day_curve(path)
chk("첫 기록 전은 시작자본", eod(D("2025-01-02")) == vp.START_EQ)
chk("기록 시각이 속한 날의 종가에 반영", eod(D("2025-01-03")) == 1000.0 and eod(D("2025-01-05")) == 1100.0)
tot, mdd = v.restricted(path, {"2025-01-05"})
chk("1000→1100 일의 로그수익", abs(tot - math.log(1.1)) < 1e-12 and mdd == 0.0)
tot2, _ = v.restricted(path, {"2025-01-04"})
chk("변화 없는 날 0", tot2 == 0.0)
tot3, mdd3 = v.restricted([(D("2025-01-03") + .5, 1100.0), (D("2025-01-04") + .5, 990.0)], {"2025-01-04"})
chk("하락일 MDD 음수", tot3 < 0 and mdd3 < 0)
chk("자본 소진 -inf", v.restricted([(D("2025-01-03") + .5, 0.0)], {"2025-01-03"})[0] == float("-inf"))

print("§4 판정 함수")
good = dict(k1=(40, -.02, .95), k2=(.1, .0, 40), k3=(.1, -.1), k4=(.5, .3, 2., 1.), k5=.8, k6=.95, k7=(3, 3))
chk("전부 통과 PASSED", v.judge(good)[0] == "PASSED")
chk("K2 실패(train 이 더 나쁨) REJECTED", v.judge(dict(good, k2=(-.2, .0, 40)))[0] == "REJECTED" and "K2" in v.judge(dict(good, k2=(-.2, .0, 40)))[1])
chk("K1 n<30 만이면 INCONCLUSIVE", v.judge(dict(good, k1=(10, -.02, .95)))[0] == "INCONCLUSIVE")
chk("K1 n<30 이어도 다른 실패면 REJECTED", v.judge(dict(good, k1=(10, -.02, .95), k5=.3))[0] == "REJECTED")
chk("K7 적격<2 만이면 INCONCLUSIVE", v.judge(dict(good, k7=(1, 1)))[0] == "INCONCLUSIVE")
chk("K7 음수 에피소드 과반 미만 실패", "K7" in v.judge(dict(good, k7=(4, 1)))[1])
chk("K6 백분위 문턱", "K6" in v.judge(dict(good, k6=.85))[1])
chk("K5 문턱", "K5" in v.judge(dict(good, k5=.55))[1])
chk("K1 평균 양수면 실패", "K1" in v.judge(dict(good, k1=(40, .01, .95)))[1])
chk("반영 대상: PASSED 이고 K5>=0.70", v.deployable("PASSED", .75) and not v.deployable("PASSED", .65)
    and not v.deployable("REJECTED", .9) and not v.deployable("INCONCLUSIVE", .9))

print("§5 동결 상수")
chk("동결 상수", (v.REG, v.MIN_N, v.K1_P, v.K5_WIN, v.K5_DEPLOY, v.K6_RANK, v.RAND_N) == ("bull_btc", 30, .90, .60, .70, .90, 200))
chk("분할·부트는 포트폴리오 프레임 값 사용", v.vp.BOOT_N == vp.BOOT_N)

print("§6 BTC 낙폭 버킷(진단)")
rows = [dict(date="2025-01-%02d" % (i + 1), close=100.0) for i in range(5)] + [dict(date="2025-01-06", close=85.0), dict(date="2025-01-07", close=70.0)]
bk = v.btc_dd_bucket(rows)
chk("고점 -15% -> dd10_20", bk["2025-01-06"] == "dd10_20")
chk("고점 -30% -> dd20p", bk["2025-01-07"] == "dd20p")
chk("고점 부근 dd0_10", bk["2025-01-03"] == "dd0_10")

print(f"\n{ok} 통과 / {fail} 실패")
raise SystemExit(1 if fail else 0)
