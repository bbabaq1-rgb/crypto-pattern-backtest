"""test_killswitch.py — validate_killswitch 로직 고정 (네트워크 없음)"""
import random
import validate_gap as vg
import validate_killswitch as d
import validate_portfolio as vp

ok = fail = 0
def chk(n, c, x=""):
    global ok, fail
    if c: ok += 1
    else: fail += 1; print("  FAIL", n, x)

chk("DEPLOY False", d.DEPLOY_ON_PASS is False)
chk("동결", d.EQ_LADDER == (160.0, 240.0, 355.0, 500.0) and d.FLOOR == 100.0 and d.WINDOWS == 52 and d.SEED == 118)
rng = random.Random(3)
def mk(n):
    ts = []
    for i in range(n):
        t_in = 740000.0 + i * 0.5
        ts.append(dict(t_in=t_in, t_out=t_in + 3 + rng.random() * 5, ret=rng.uniform(-0.09, 0.12), pattern="p%d" % (i % 3),
                       sym="S%d" % i, rank=i % 30, vol=rng.choice([None, 0.5, 0.9, 1.6])))
    return ts
T = mk(300)
# floor=None 은 종전과 같다
a = vg.simulate(T)
b = vg.simulate(T, floor=None)
chk("floor None 불변", a == b)
# floor 가 매우 높으면 진입 0, 낮으면 불변
c = vg.simulate(T, floor=1e9)
chk("floor 높으면 체결 0", c["taken"] == 0)
e = vg.simulate(T, floor=0.0)
chk("floor 0 은 불변", e["taken"] == a["taken"] and abs(e["final"] - a["final"]) < 1e-9)
# 킬스위치 이후 체결은 floor 없을 때 이하
f = vg.simulate(T, floor=vp.START_EQ * 0.95)
chk("floor 는 체결을 줄이기만", f["taken"] <= a["taken"])
# 창·경로
w = d.windows_of(T)
chk("창 분할 비어있지 않음", len(w) > 3 and sum(len(x) for x in w) == len(T))
p = d.one_year_path(w, random.Random(1), n_windows=10)
chk("경로 정렬·수 보존 규칙", all(p[i]["t_in"] <= p[i + 1]["t_in"] for i in range(len(p) - 1)))
chk("경로 길이 상한 10주", max(t["t_in"] for t in p) < 10 * 7.0 + 1e-9)
chk("보유 유지", all(t["t_out"] >= t["t_in"] for t in p))
# 결정성
p2 = d.one_year_path(w, random.Random(1), n_windows=10)
chk("시드 결정성", [x["t_in"] for x in p] == [x["t_in"] for x in p2])
# START_EQ 복원
e0 = vp.START_EQ
d.run_path(p, 160.0)
chk("START_EQ 복원", vp.START_EQ == e0)
# 모든 거래가 큰 손실이면 낮은 equity 에서 도달
L = [dict(t, ret=-0.2) for t in T]
r = d.run_path(L, 160.0)
chk("대손실 경로는 도달", r["reached"] and r["t_reach"] is not None)
W = [dict(t, ret=0.2) for t in T]
chk("대이익 경로는 미도달", not d.run_path(W, 160.0)["reached"])
# 판정 함수
chk("INSENS 높음", d.verdict({160: .5, 240: .4, 355: .3, 500: .2}) == "EQUITY_INSENSITIVE")
chk("INSENS 낮음", d.verdict({160: .005, 240: .004, 355: .002, 500: .0}) == "EQUITY_INSENSITIVE")
chk("THRESHOLD", d.verdict({160: .30, 240: .12, 355: .04, 500: .02}) == "THRESHOLD_EXISTS")
chk("NO_SAFE", d.verdict({160: .6, 240: .4, 355: .2, 500: .08}) == "NO_SAFE_LEVEL")
chk("비단조는 NO_SAFE", d.verdict({160: .1, 240: .2, 355: .03, 500: .02}) == "NO_SAFE_LEVEL")
print(f"test_killswitch: {ok} ok, {fail} fail")
raise SystemExit(1 if fail else 0)
