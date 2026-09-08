"""test_cadence.py — validate_cadence 로직 고정 (네트워크 없음)."""
import json
import math

import validate_cadence as vc

FAIL = []


def chk(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        FAIL.append(msg)


def mk(closes, first="2019-01-01", high=None, low=None):
    """종가 목록 → rows. 고가/저가 기본은 종가와 동일(띠 이벤트 없음)."""
    from datetime import date, timedelta
    d0 = date.fromisoformat(first)
    rows = []
    for k, c in enumerate(closes):
        h = high[k] if high else c
        l = low[k] if low else c
        rows.append(dict(ts=k, date=(d0 + timedelta(days=k)).isoformat(), o=c, h=h, l=l, c=c, v=1000.0))
    return rows


def idx_of(rows):
    return {x["date"]: k for k, x in enumerate(rows)}


# 1) 고정 유니버스 — 이력·생존 요건
rows = {
    "OLD":  mk([1.0] * 400, first="2018-01-01"),          # 2018-01 ~ 2019-02 → end 미달
    "FULL": mk([1.0] * 900, first="2018-01-01"),          # 2018-01 ~ 2020-06
    "LATE": mk([1.0] * 900, first="2019-01-01"),          # 시작 이력 부족
}
fu = vc.fixed_universe(rows, "2019-06-01", "2020-06-01", "2018-06-01")
chk(fu == ["FULL"], f"고정 유니버스는 이력·생존 둘 다 요구 (got {fu})")

# 2) none 은 세 arm 이 동일해야 한다
closes = [100 * (1.001 ** k) for k in range(400)]
rows2 = {s: mk(closes, first="2018-01-01") for s in ("A", "B", "C")}
syms = list(rows2)
dates = [x["date"] for x in rows2["A"] if x["date"] >= "2018-07-01"]
idx, tv = vc.prep(rows2, syms)
curves = {a: vc.basket(rows2, dates, syms, idx, tv, 2, None, a) for a in vc.ARMS}
chk(all(curves["reselect"] is not None and
        max(abs(x - y) for x, y in zip(curves["reselect"], curves[a])) < 1e-12 for a in vc.ARMS),
    "none 주기에서 reselect/reweight/anchor 곡선이 완전히 동일")

# 3) 앵커 리셋 1회 = 왕복 수수료 2회 (가격 불변이면 가치가 (1-fee)^2 배)
flat = mk([100.0] * 60, first="2018-01-01")
seg = [x["date"] for x in flat]
no_reset = vc.sleeve_vals(flat, idx_of(flat), seg[0], seg[-1], seg)
one_reset = vc.sleeve_vals(flat, idx_of(flat), seg[0], seg[-1], seg, resets=[seg[30]])
chk(abs(no_reset[-1] - (1 - vc.FEE)) < 1e-12, "리셋 없으면 진입 수수료 1회만")
chk(abs(one_reset[-1] - (1 - vc.FEE) ** 3) < 1e-12,
    f"리셋 1회는 왕복 2회 추가 (got {one_reset[-1]:.8f} vs {(1-vc.FEE)**3:.8f})")
chk(abs(one_reset[29] - no_reset[29]) < 1e-12, "리셋 전 구간은 값이 같다")

# 3b) 재구성 슬리피지는 리셋 1회당 왕복 2회로 걸린다 (D5 진단 경로)
one_slip = vc.sleeve_vals(flat, idx_of(flat), seg[0], seg[-1], seg, resets=[seg[30]], reset_slip=0.001)
chk(abs(one_slip[-1] - (1 - vc.FEE) ** 3 * (1 - 0.001) ** 2) < 1e-12, "리셋 슬리피지 왕복 2회")
chk(abs(vc.sleeve_vals(flat, idx_of(flat), seg[0], seg[-1], seg, reset_slip=0.001)[-1]
        - no_reset[-1]) < 1e-12, "리셋이 없으면 재구성 슬리피지는 값에 영향이 없다")

# 4) 띠 규칙 — 손절 후 진입가로 복귀할 때만 재매수
c = [100.0] * 10
lo = [100.0] * 10
hi = [100.0] * 10
lo[3] = 98.0          # 손절 (P*(1-1%) = 99)
hi[6] = 100.0         # 진입가 복귀
c[4] = c[5] = 95.0
lo[4] = lo[5] = 95.0
hi[4] = hi[5] = 95.0
r = mk(c, first="2018-01-01", high=hi, low=lo)
seg = [x["date"] for x in r]
v = vc.sleeve_vals(r, idx_of(r), seg[0], seg[-1], seg)
chk(v[4] == v[5], "손절 뒤에는 현금이라 가치가 가격과 무관하게 고정")
chk(v[3] < v[0], "손절이 손실로 반영")
chk(v[7] != v[5], "진입가 복귀 시 재매수돼 다시 가격을 따라간다")

# 5) anchor 는 비중을 재균등화하지 않는다 (한 종목이 크게 오르면 reweight 와 갈린다)
up = mk([100 * (1.01 ** k) for k in range(400)], first="2018-01-01")
flat2 = mk([100.0] * 400, first="2018-01-01")
rows5 = {"UP": up, "FLAT": flat2}
syms5 = ["UP", "FLAT"]
dates5 = [x["date"] for x in up if x["date"] >= "2018-07-01"]
idx5, tv5 = vc.prep(rows5, syms5)
a5 = vc.basket(rows5, dates5, syms5, idx5, tv5, 2, 30, "anchor")
r5 = vc.basket(rows5, dates5, syms5, idx5, tv5, 2, 30, "reweight")
chk(a5[-1] > r5[-1] * 1.01, f"anchor(비중 흐름) != reweight(재균등화)  {a5[-1]:.2f} vs {r5[-1]:.2f}")

# 6) 거래대금 순위 — 고정 집합 안에서만, 그날 값으로
rows6 = {"BIG": mk([100.0] * 100, first="2018-01-01"), "SMALL": mk([1.0] * 100, first="2018-01-01")}
idx6, tv6 = vc.prep(rows6, ["BIG", "SMALL"])
chk(vc.rank_at(["BIG", "SMALL"], idx6, tv6, rows6["BIG"][50]["date"]) == ["BIG", "SMALL"], "거래대금 내림차순")
chk(vc.rank_at(["SMALL"], idx6, tv6, rows6["BIG"][50]["date"]) == ["SMALL"], "고정 집합 밖 종목은 후보에 없다")
chk(vc.rank_at(["BIG"], idx6, tv6, rows6["BIG"][5]["date"]) == [], "거래대금 창(30봉) 미만이면 후보 아님")

# 7) marks — 주기 일수마다, none 은 1회
chk(vc.marks_of(list(range(100)), None) == [0], "none 은 시작 1회")
chk(vc.marks_of(list(range(100)), 30) == [0, 30, 60, 90], "주기 30일 마크")

# 8) 판정 함수 — 사전 등록한 우선순위 + 퇴화 가드
chk(vc.decide(False, True, True, True) == "CONFOUNDED_BY_UNIVERSE", "J1 실패 → CONFOUNDED_BY_UNIVERSE")
chk(vc.decide(True, True, True, False) == "UNSTABLE", "J4 실패 → UNSTABLE")
chk(vc.decide(True, False, True, True) == "MECHANISM_NOT_SELECTION", "J2 실패 → MECHANISM_NOT_SELECTION")
chk(vc.decide(True, True, False, True) == "MECHANISM_NOT_SELECTION", "J3 실패 → MECHANISM_NOT_SELECTION")
chk(vc.decide(True, True, True, True) == "CADENCE_CONFIRMED", "전부 통과 → CADENCE_CONFIRMED")
chk(vc.decide(True, True, True, True, degenerate=True) == "INCONCLUSIVE_DEGENERATE",
    "선택 arm 퇴화 시 J2·J3 를 읽지 않는다")
chk(vc.decide(False, True, True, True, degenerate=True) == "CONFOUNDED_BY_UNIVERSE",
    "퇴화라도 J1(주기 효과)은 읽는다 — J1 실패가 우선")

# 8b) Calmar 비교는 부동소수 잡음으로 결정되지 않는다
chk(not vc.gt(1.3296522775120678, 1.3296522775120654), "2e-15 차이는 우위로 세지 않는다")
chk(vc.gt(1.0 + 2 * vc.EPS, 1.0), "EPS 를 넘는 차이는 우위")
chk(not vc.gt(None, 1.0) and not vc.gt(1.0, None), "None 은 우위가 아니다")
chk(vc.MAX_SELECT_RATIO == 0.75 and vc.EPS == 1e-6, "가드 상수 동결")

# 9) stats — Calmar 정의
eq = [1.0, 2.0, 1.0, 4.0]
s = vc.stats(eq, 365.25)
chk(abs(s["mdd"] + 0.5) < 1e-12, "MDD 는 최고점 대비 최대 낙폭")
chk(abs(s["cagr"] - 3.0) < 1e-6 and abs(s["calmar"] - 6.0) < 1e-6, "Calmar = CAGR/|MDD|")

# 10) 동결 파라미터가 band_rule/basket 과 같은 값인지
import validate_band_rule as br
chk(vc.FEE == br.FEE and abs(vc.SLIP - 0.00141) < 1e-12 and vc.STOP == 0.01,
    "손절·슬립·수수료가 band_rule 확정판과 동일")
chk(vc.DEPLOY_ON_PASS is False, "DEPLOY_ON_PASS=False (통과해도 실거래 반영 없음)")
chk(vc.PRIMARY == dict(window="W1", n=20, cadence="monthly"), "주 판정 셀 동결")
chk(tuple(vc.CADENCES) == ("none", "weekly", "biweekly", "monthly", "quarterly", "semiannual"), "주기 격자 동결")

# 11) 실거래 무영향 — 스케줄러·레지스트리에 등재되지 않는다
src = open("scheduler.py", encoding="utf-8").read()
chk("validate_cadence" not in src, "스케줄러가 이 연구 모듈을 import 하지 않는다")
reg = json.load(open("registry.json", encoding="utf-8"))
chk("cadence_prereg_2026_09_07" in reg, "registry 에 사전 등록 기록이 있다")

# 12) 워크플로 등재
y = open("tests.yml", encoding="utf-8").read() if False else open(".github/workflows/tests.yml", encoding="utf-8").read()
chk("test_cadence.py" in y, "tests.yml 등재")

print(f"\n{'ALL PASS' if not FAIL else 'FAILURES: ' + str(len(FAIL))} ({len(FAIL)} fail)")
raise SystemExit(1 if FAIL else 0)
