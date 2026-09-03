"""
method_r 로직 검증 (데이터 수집 없이 합성 봉 + 합성 레짐맵).

확인 대상:
  - mode="D" 가 method_t.outcome_d(방식D)와 완전히 같은 결과를 내는가 (비교 기준의 정합)
  - 사용자 시나리오: bear 진입 롱 → bull 전환 시 D 는 청산, R 은 유지 → 다시 bear 로
    꺾일 때 R 이 청산
  - sideways 처리: R1 은 중립(유지), R2 는 불리(청산)
  - 불리 방향 전환(bull 진입 롱 → bear)은 세 규칙 모두 같은 봉에 청산
  - 숏은 거울상
  - 레짐 변화 없음 / 레짐 정보 없음 → 세 규칙 동일
  - 손절·반대신호 우선순위 불변
  - 이 파일은 연구용 — paper_executor.eval_D(실거래)는 손대지 않았음을 소스로 고정

실행: python test_method_r.py
"""
import sys
from datetime import date, timedelta

import method_r as mr
import method_t as mt

fails = []


def check(n, c, d=""):
    print(("PASS " if c else "FAIL ") + n + ("" if c else f" — {d}"))
    c or fails.append(n)


def bar(o, h, l, c, d):
    return dict(date=d, o=o, h=h, l=l, c=c, v=1)


def mk(n=40, px=100.0):
    return [bar(px, px + 0.5, px - 0.5, px, (date(2026, 1, 1) + timedelta(days=i)).isoformat())
            for i in range(n)]


def regmap(seq):
    """seq: 봉 인덱스별 레짐 리스트 → {date: regime}. None 은 미등록."""
    d0 = date(2026, 1, 1)
    return {(d0 + timedelta(days=i)).isoformat(): r for i, r in enumerate(seq) if r is not None}


def setreg(rm):
    mr.REGMAP = rm
    mt.REGMAP = rm


N = 40


# ── 1. D 모드 = method_t 방식D ───────────────────────────────────────────────
for name, seq in [
    ("레짐 변화 없음", ["bear"] * N),
    ("bear→bull@5", ["bear"] * 5 + ["bull_btc"] * (N - 5)),
    ("bull→bear@7", ["bull_btc"] * 7 + ["bear"] * (N - 7)),
    ("bear→side@4→bear@9", ["bear"] * 4 + ["sideways"] * 5 + ["bear"] * (N - 9)),
    ("레짐 없음", [None] * N),
]:
    setreg(regmap(seq))
    rows = mk()
    for d in ("long", "short"):
        a = mr.outcome_r(rows, 0, d, set(), "D")
        b = mt.outcome_d(rows, 0, d, set(), None)
        check(f"D 모드 ≡ method_t.outcome_d [{name} {d}]", a == b, (a, b))

# ── 2. 사용자 시나리오: bear 진입 롱 → bull 전환 → 다시 bear ────────────────
setreg(regmap(["bear"] * 5 + ["bull_btc"] * 5 + ["bear"] * (N - 10)))
rows = mk()
rD = mr.outcome_r(rows, 0, "long", set(), "D")
r1 = mr.outcome_r(rows, 0, "long", set(), "R1")
r2 = mr.outcome_r(rows, 0, "long", set(), "R2")
check("D: bull 전환(유리)에 청산 — 현행 결함 재현", rD[1] == 5 and rD[2] == "regime_switch", rD)
check("R1: bull 전환은 유지, 다시 bear 로 꺾일 때 청산", r1[1] == 10 and r1[2] == "regime_switch", r1)
check("R2: 동일(sideways 미개입)", r2[1] == 10 and r2[2] == "regime_switch", r2)

# bear 진입 롱이 bull 로 갔다가 끝까지 bull → R 은 maxhold 까지 보유
setreg(regmap(["bear"] * 5 + ["bull_altseason"] * (N - 5)))
r1 = mr.outcome_r(rows, 0, "long", set(), "R1")
check("R1: bull 유지되면 만기까지 보유(30봉)", r1[1] == 30 and r1[2] == "maxhold", r1)

# ── 3. sideways 처리 — R1 중립 / R2 불리 ─────────────────────────────────────
setreg(regmap(["bear"] * 5 + ["sideways"] * 5 + ["bear"] * (N - 10)))
rD = mr.outcome_r(rows, 0, "long", set(), "D")
r1 = mr.outcome_r(rows, 0, "long", set(), "R1")
r2 = mr.outcome_r(rows, 0, "long", set(), "R2")
check("D: sideways 전환에 청산", rD[1] == 5, rD)
check("R1: sideways 는 중립 → 다시 bear 진입 시 청산", r1[1] == 10, r1)
# R2 는 bear·sideways 둘 다 불리 → bear 진입 롱은 처음부터 불리 상태. sideways 로
# 가도 '불리로 들어가는 전환'이 아니고, 다시 bear 로 와도 마찬가지 → 만기 보유.
# (규칙 정의상 일관된 결과. sideways 가 '불리로의 전환'이 되는 건 bull 진입일 때 — 아래)
check("R2: bear 진입 롱은 sideways/bear 모두 불리 집합 → 전환 없음 → 만기", r2[2] == "maxhold", r2)

# bull 진입 롱 → sideways: D/R2 청산, R1 유지
setreg(regmap(["bull_btc"] * 5 + ["sideways"] * (N - 5)))
check("bull 롱 → sideways: R1 유지(만기)", mr.outcome_r(rows, 0, "long", set(), "R1")[2] == "maxhold")
check("bull 롱 → sideways: R2 청산", mr.outcome_r(rows, 0, "long", set(), "R2")[1] == 5)

# ── 4. 불리 방향 전환 — 세 규칙 동일 ─────────────────────────────────────────
setreg(regmap(["bull_btc"] * 7 + ["bear"] * (N - 7)))
outs = [mr.outcome_r(rows, 0, "long", set(), m) for m in mr.MODES + ["R2"]]
check("bull 롱 → bear: 모든 arm 이 7봉에 청산", all(o[1] == 7 and o[2] == "regime_switch" for o in outs), outs)

# bull_btc → bull_altseason (같은 bull 계열) : D 는 청산, R 은 유지
setreg(regmap(["bull_btc"] * 6 + ["bull_altseason"] * (N - 6)))
check("bull_btc→bull_altseason: D 청산(레짐 라벨 변화)", mr.outcome_r(rows, 0, "long", set(), "D")[1] == 6)
check("bull_btc→bull_altseason: R1 유지(둘 다 유리)", mr.outcome_r(rows, 0, "long", set(), "R1")[2] == "maxhold")

# ── 5. 숏 거울상 ─────────────────────────────────────────────────────────────
setreg(regmap(["bull_btc"] * 5 + ["bear"] * 5 + ["bull_btc"] * (N - 10)))
sD = mr.outcome_r(rows, 0, "short", set(), "D")
s1 = mr.outcome_r(rows, 0, "short", set(), "R1")
check("숏 D: bear 전환(유리)에 청산", sD[1] == 5, sD)
check("숏 R1: bear 유지, 다시 bull 로 꺾일 때 청산", s1[1] == 10, s1)
setreg(regmap(["bear"] * 5 + ["bull_altseason"] * (N - 5)))
check("bear 숏 → bull_altseason: R1 청산(불리)", mr.outcome_r(rows, 0, "short", set(), "R1")[1] == 5)

# ── 6. 변화 없음 / 정보 없음 → 동일 ──────────────────────────────────────────
for name, seq in [("변화 없음", ["bear"] * N), ("정보 없음", [None] * N)]:
    setreg(regmap(seq))
    outs = [mr.outcome_r(rows, 0, "long", set(), m) for m in mr.MODES + ["R2"]]
    check(f"{name}: 모든 arm 동일(maxhold)", len(set(outs)) == 1 and outs[0][2] == "maxhold", outs)

# 중간에 레짐 정보가 빠진 봉 — R 은 그 봉을 건너뛰고 상태 유지
setreg(regmap(["bear"] * 5 + [None] * 3 + ["bull_btc"] * 4 + ["bear"] * (N - 12)))
r1 = mr.outcome_r(rows, 0, "long", set(), "R1")
check("레짐 결측 봉은 판단 보류 — 이후 bear 재진입(12)에 청산", r1[1] == 12, r1)

# ── 7. 손절·반대신호 우선순위 불변 ─────────────────────────────────────────
setreg(regmap(["bear"] * 3 + ["bull_btc"] * (N - 3)))
rows2 = mk(); rows2[2] = dict(rows2[2], l=90.0)          # 2봉째 -10% 저가
for m in mr.MODES + ["R2"]:
    o = mr.outcome_r(rows2, 0, "long", set(), m)
    check(f"{m}: 손절이 레짐보다 먼저(2봉 stop)", o[1] == 2 and o[2] == "stop", o)
setreg(regmap(["bear"] * N))
for m in mr.MODES + ["R2"]:
    o = mr.outcome_r(rows, 0, "long", {4}, m)
    check(f"{m}: 반대신호 청산 유지(4봉 opp_signal)", o[1] == 4 and o[2] == "opp_signal", o)

# ── 7b. 2차 arm — RL / RB / RLB ─────────────────────────────────────────────
# RL: 롱만 R1, 숏은 D
setreg(regmap(["bull_btc"] * 5 + ["bear"] * 5 + ["bull_btc"] * (N - 10)))
check("RL 숏: D 규칙 → 유리(bear) 전환에도 5봉 청산", mr.outcome_r(rows, 0, "short", set(), "RL")[1] == 5)
setreg(regmap(["bear"] * 5 + ["bull_btc"] * 5 + ["bear"] * (N - 10)))
check("RL 롱: R1 규칙 → bull 버티고 bear 재진입(10)에 청산", mr.outcome_r(rows, 0, "long", set(), "RL")[1] == 10)

# RB: 유리 전환 시 수익 중이면 손절을 본전으로. 진입 100, bar5 에 bull 전환(종가 110 > 100) → stop=100
# 주의: 본전 손절은 진입가에 닿는 어떤 꼬리에도 걸린다(가장 타이트한 변형). 그래서
# 전환 이후 봉은 진입가 위(110 수준)에 두고, 의도한 봉에서만 저가를 100 아래로 찍는다.
def lift(rows, start, px):
    """start 봉부터 끝까지 px 수준의 평탄 봉으로 (l = px-0.5 > 100)."""
    for i in range(start, len(rows)):
        rows[i] = dict(rows[i], o=px, h=px + 0.5, l=px - 0.5, c=px)
    return rows

setreg(regmap(["bear"] * 5 + ["bull_btc"] * (N - 5)))
rb = lift(mk(), 5, 110.0); rb[8] = dict(rb[8], l=99.0)          # 8봉 저가 99 < 100(본전)
o_r1 = mr.outcome_r(rb, 0, "long", set(), "R1")
o_rb = mr.outcome_r(rb, 0, "long", set(), "RB")
check("R1: 저가 99 는 -8% 손절선(92) 위 → 유지", o_r1[2] != "stop", o_r1)
check("RB: 본전 이동 후 저가 99 ≤ 100 → 8봉 stop_be, 수익률 = -수수료",
      o_rb == (-mr.FEE, 8, "stop_be"), o_rb)
# 손실 중에 유리 전환 → 본전으로 안 옮김 (다음 봉 본전 체결 방지)
rb2 = mk(); rb2[5] = dict(rb2[5], c=95.0, l=94.5); rb2[8] = dict(rb2[8], l=99.0)
o = mr.outcome_r(rb2, 0, "long", set(), "RB")
check("RB: 전환 시 손실 중(95<100)이면 본전 이동 없음 → 저가 99 에 안 걸림", o[2] != "stop_be" and o[1] > 8, o)
# 본전 이동 뒤에도 -8% 가 아니라 본전에서 잡힌다(더 얕은 손절)
rb3 = lift(mk(), 5, 110.0); rb3[9] = dict(rb3[9], l=91.0)
o = mr.outcome_r(rb3, 0, "long", set(), "RB")
check("RB: 본전 이동 후 91 까지 빠지면 stop_be(본전)로 기록(−8% 아님)", o == (-mr.FEE, 9, "stop_be"), o)
# 진입이 이미 유리(bull 롱)면 전환이 아니므로 본전 이동 없음
setreg(regmap(["bull_btc"] * N))
rb4 = mk(); rb4[3] = dict(rb4[3], c=110.0, h=110.5); rb4[6] = dict(rb4[6], l=99.0)
o = mr.outcome_r(rb4, 0, "long", set(), "RB")
check("RB: bull 진입 롱은 '유리로의 전환'이 없어 본전 이동 없음", o[2] == "maxhold", o)
# bear→sideways→bull : bull 진입(6)이 유리로의 전환 → 본전 이동
setreg(regmap(["bear"] * 3 + ["sideways"] * 3 + ["bull_btc"] * (N - 6)))
rb5 = lift(mk(), 6, 112.0); rb5[9] = dict(rb5[9], l=99.5)
o = mr.outcome_r(rb5, 0, "long", set(), "RB")
check("RB: bear→sideways→bull 에서 bull 진입(6)이 전환 → 본전 이동 → 9봉 stop_be", o == (-mr.FEE, 9, "stop_be"), o)
# 숏 거울상: 진입 100, bear 전환 시 종가 90 → stop=100, 이후 고가 101 → stop_be
setreg(regmap(["bull_btc"] * 5 + ["bear"] * (N - 5)))
rbs = lift(mk(), 5, 90.0); rbs[8] = dict(rbs[8], h=101.0)
o = mr.outcome_r(rbs, 0, "short", set(), "RB")
check("RB 숏: bear 전환 시 수익 중 → 본전 이동 → 고가 101 ≥ 100 → stop_be", o == (-mr.FEE, 8, "stop_be"), o)
# RLB: 롱은 RB 와 같고, 숏은 D
o_rlb_l = mr.outcome_r(rb, 0, "long", set(), "RLB")
setreg(regmap(["bear"] * 5 + ["bull_btc"] * (N - 5)))
o_rlb_l = mr.outcome_r(rb, 0, "long", set(), "RLB")
check("RLB 롱 ≡ RB 롱", o_rlb_l == mr.outcome_r(rb, 0, "long", set(), "RB"), o_rlb_l)
setreg(regmap(["bull_btc"] * 5 + ["bear"] * (N - 5)))
o_rlb_s = mr.outcome_r(rbs, 0, "short", set(), "RLB")
check("RLB 숏 ≡ D 숏 (본전 이동 없이 5봉 regime_switch)", o_rlb_s == mr.outcome_r(rbs, 0, "short", set(), "D") and o_rlb_s[1] == 5, o_rlb_s)
# 본전 이동 arm 도 레짐 변화 없으면 D 와 동일
setreg(regmap(["bear"] * N))
check("RB/RLB: 레짐 변화 없으면 D 와 동일",
      mr.outcome_r(rb, 0, "long", set(), "RB") == mr.outcome_r(rb, 0, "long", set(), "D")
      and mr.outcome_r(rb, 0, "long", set(), "RLB") == mr.outcome_r(rb, 0, "long", set(), "D"))
check("2차 실행 목록은 D/R1/RL/RB/RLB", mr.MODES == ["D", "R1", "RL", "RB", "RLB"], mr.MODES)

# 시간 분할 헬퍼
base_h = [(f"2026-01-{i+1:02d}", "x", 0.0, 1, "maxhold") for i in range(8)]
arm_h  = [(f"2026-01-{i+1:02d}", "x", (0.01 if i < 4 else -0.01), 1, "maxhold") for i in range(8)]
hv = mr.halves(base_h, arm_h)
check("halves: 전반 +1%, 후반 -1% 로 부호 분리", abs(hv["d1"] - 0.01) < 1e-12 and abs(hv["d2"] + 0.01) < 1e-12, hv)

# ── 8. 분기 거래 집계 ────────────────────────────────────────────────────────
base = [("a", "b", 0.05, 5, "regime_switch"), ("a", "b", 0.02, 3, "stop"), ("a", "b", 0.01, 30, "maxhold")]
arm  = [("a", "b", 0.12, 10, "regime_switch"), ("a", "b", 0.02, 3, "stop"), ("a", "b", 0.01, 30, "maxhold")]
dv = mr.divergence(base, arm)
check("분기 거래는 결과가 다른 것만 센다", dv["n"] == 1 and dv["arm_wins"] == 1 and dv["arm_losses"] == 0, dv)
check("분기 비율", abs(dv["share"] - 1 / 3) < 1e-9, dv)
check("boot_p: 전부 양수면 0", mr.boot_p([0.01] * 20) == 0.0)
check("boot_p: 전부 음수면 1", mr.boot_p([-0.01] * 20) == 1.0)

# ── 8b. 결과 저장 직렬화 (1차 실행이 여기서 죽었다 — set 이 JSON 불가) ────────
import json as _json
blob = _json.dumps(dict(adverse={m: {d: sorted(s) for d, s in v.items()} for m, v in mr.ADVERSE.items()},
                        x=mr.ADVERSE["R1"]["long"], z={None: 3, "bear": 1}),
                   default=mr._jsonable)
check("payload 직렬화: set→정렬리스트, None 키(진입레짐 미상) 허용", '["bear"]' in blob and '"null": 3' in blob)

# ── 9. 실거래 코드 무변경 (연구 파일이 eval_D 를 건드리지 않았는가) ──────────
src = open("paper_executor.py", encoding="utf-8").read()
check("paper_executor.eval_D 의 레짐 조건은 현행 그대로(방향 무관)",
      'regsw = regmap.get(rows[j]["date"]) not in (None, entry_reg)' in src)
check("paper_executor 는 method_r 를 import 하지 않음", "method_r" not in src)

print()
print(f"실패 {len(fails)} 건" if fails else "실패 0 — 전체 통과")
sys.exit(1 if fails else 0)
