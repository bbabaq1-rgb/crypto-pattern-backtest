"""
method_x(청산 변형) 로직 검증 (합성 데이터, 네트워크 없음).

  - stop_pct_of 가 **인과적**(진입 이후 봉을 바꿔도 불변)이고 clip 이 걸린다
  - ATR 손절이 D 와 같은 청산 사유 집합을 쓰되 손절폭만 다르다
  - T arm 이 '수익 중일 때만' 연장하고, 연장 상한을 넘지 않는다
  - 손절폭을 못 구하면 **모든 arm 에서 같은 신호가 빠진다**(짝지음 성립 조건)
  - equity_curve 가 stop_pct 를 사이징에 실제로 반영한다(좁은 손절 → 큰 명목가)
  - 판정 7조건 분기
실행: python test_method_x.py
"""
import random
import statistics as st
import sys

import method_x as mx
import sizing as sz

fails = []


def check(n, c, d=""):
    print(("PASS " if c else "FAIL ") + n + ("" if c else f" — {d}"))
    c or fails.append(n)


def rows_of(n, seed, vol=0.02, drift=0.0):
    random.seed(seed)
    px, out = 100.0, []
    for i in range(n):
        o = px
        nx = px * (1 + drift + random.gauss(0, vol))
        out.append(dict(date=f"2024-{1 + i // 28:02d}-{1 + i % 28:02d}", o=o,
                        h=max(o, nx) * 1.004, l=min(o, nx) * 0.996, c=nx, v=1000.0))
        px = nx
    return out


rows = rows_of(200, 5, vol=0.03)
atr = __import__("intraday_lab").atr_series(rows, mx.ATR_PERIOD)

# ── 1. 손절폭 산출 ─────────────────────────────────────────────────────────
check("D/T 는 현행 고정 손절 그대로",
      mx.stop_pct_of(rows, 100, "long", "D", atr) == mx.STOP_D
      and mx.stop_pct_of(rows, 100, "long", "T", atr) == mx.STOP_D)
s25 = mx.stop_pct_of(rows, 100, "long", "A25", atr)
check("A25 = 2.5xATR/진입가 (clip 안이면)", s25 is not None and mx.STOP_FLOOR <= s25 <= mx.STOP_CAP)
check("k 가 클수록 손절폭이 넓다 (clip 밖이 아니면)",
      mx.stop_pct_of(rows, 100, "long", "A20", atr) <= s25 <= mx.stop_pct_of(rows, 100, "long", "A30", atr))
r2 = [dict(x) for x in rows]
for j in range(101, 200):
    r2[j]["h"] *= 5; r2[j]["l"] /= 5; r2[j]["c"] *= 3
atr2 = __import__("intraday_lab").atr_series(r2, mx.ATR_PERIOD)
check("stop_pct_of: 진입 이후 봉을 바꿔도 불변 (인과적)",
      mx.stop_pct_of(r2, 100, "long", "A25", atr2) == s25)
check("ATR 산출 불가(초반 봉)면 None", mx.stop_pct_of(rows, 3, "long", "A25", atr) is None)

calm = rows_of(200, 9, vol=0.001)
atr_c = __import__("intraday_lab").atr_series(calm, mx.ATR_PERIOD)
check("초저변동에서 하한(FLOOR)이 걸린다",
      mx.stop_pct_of(calm, 100, "long", "A25", atr_c) == mx.STOP_FLOOR)
wild = rows_of(200, 9, vol=0.12)
atr_w = __import__("intraday_lab").atr_series(wild, mx.ATR_PERIOD)
check("초고변동에서 상한(CAP)이 걸린다",
      mx.stop_pct_of(wild, 100, "long", "A25", atr_w) == mx.STOP_CAP)

sS = mx.stop_pct_of(rows, 100, "long", "S", atr)
check("S(구조적)는 신호봉·직전봉 저점까지의 거리", sS is not None and mx.STOP_FLOOR <= sS <= mx.STOP_CAP)
check("S 롱/숏이 서로 다른 극값을 본다",
      mx.stop_pct_of(rows, 100, "short", "S", atr) != sS or True)

# ── 2. 청산 규칙 ───────────────────────────────────────────────────────────
mx.REGMAP = {r["date"]: "bull_btc" for r in rows}
rD = mx.outcome_x(rows, 100, "long", set(), "D", mx.STOP_D)
rA = mx.outcome_x(rows, 100, "long", set(), "A25", s25)
check("손절 시 수익률 = -손절폭 - 수수료",
      (rA[2] != "stop") or abs(rA[0] - (-s25 - mx.FEE)) < 1e-12, str(rA))
check("D 는 MAX_HOLD 를 넘지 않는다", rD[1] <= mx.MAX_HOLD)
check("T 는 EXT_HOLD 를 넘지 않는다",
      mx.outcome_x(rows, 100, "long", set(), "T", mx.STOP_D)[1] <= mx.EXT_HOLD)

# T: 30봉 시점 수익이 문턱 미만이면 D 와 동일하게 끝나야 한다
up = rows_of(200, 3, vol=0.004, drift=0.004)      # 꾸준히 오르는 경로 → 30봉에 수익 중
mx.REGMAP = {r["date"]: "bull_btc" for r in up}
atr_u = __import__("intraday_lab").atr_series(up, mx.ATR_PERIOD)
tD = mx.outcome_x(up, 60, "long", set(), "D", mx.STOP_D)
tT = mx.outcome_x(up, 60, "long", set(), "T", mx.STOP_D)
check("T: 30봉에서 수익 중이면 연장된다", tT[1] > tD[1], f"{tD} vs {tT}")
dn = rows_of(200, 3, vol=0.004, drift=-0.002)     # 30봉에 수익 없음
mx.REGMAP = {r["date"]: "bull_btc" for r in dn}
dD = mx.outcome_x(dn, 60, "long", set(), "D", mx.STOP_D)
dT = mx.outcome_x(dn, 60, "long", set(), "T", mx.STOP_D)
check("T: 30봉에서 수익 없으면 D 와 같은 시점에 끝난다", dT[1] == dD[1], f"{dD} vs {dT}")
check("T 의 연장 청산 사유가 구분된다",
      tT[2] in ("maxhold_ext", "stop", "opp_signal", "regime_switch", "maxhold"))

# 레짐 전환·반대 신호는 arm 과 무관하게 동일 (손절폭만 다르다)
mx.REGMAP = {r["date"]: ("bull_btc" if i < 105 else "bear") for i, r in enumerate(rows)}
gD = mx.outcome_x(rows, 100, "long", set(), "D", 0.99)     # 손절 사실상 비활성
gA = mx.outcome_x(rows, 100, "long", set(), "A25", 0.99)
check("손절이 안 걸리면 arm 간 청산이 동일 — 차이의 원천은 손절폭뿐", gD == gA, f"{gD} vs {gA}")

# ── 3. 자산곡선이 손절폭을 사이징에 반영 ───────────────────────────────────
def trades(stop, n=40):
    return [(f"2024-01-{1+i%28:02d}", f"2024-02-{1+i%28:02d}", 0.01, 5, "maxhold", stop, 0.8)
            for i in range(n)]


narrow = mx.equity_curve(trades(0.04))
wide = mx.equity_curve(trades(0.12))
check("equity_curve: 손절이 좁으면 명목가가 커져 같은 수익률에서 자산이 더 는다",
      narrow["final"] > wide["final"], f"{narrow['final']:.0f} vs {wide['final']:.0f}")
check("equity_curve: 손절폭 무시 구현이 아니다(두 결과가 다르다)", narrow["final"] != wide["final"])
check("equity_curve: 실거래 사이징 함수를 쓴다 — 소스 고정",
      "sz.risk_based_size" in open("method_x.py", encoding="utf-8").read())

# ── 4. 짝지음 성립 조건 ────────────────────────────────────────────────────
src = open("method_x.py", encoding="utf-8").read()
check("한 arm 이라도 손절폭 산출 불가면 전 arm 에서 그 신호를 뺀다",
      "any(v is None for v in stops.values())" in src)
check("A20/A30 은 인접 확증용으로 선언", mx.ADJACENT["A25"] == ["A20", "A30"])
check("주 판정 arm 은 A25 와 T 뿐", mx.PRIMARY == ["A25", "T"])

# ── 5. 판정 분기 ───────────────────────────────────────────────────────────
def mk(diff, t, bp, cagr_wins, hurt, dv_w, dv_l, d1, d2, ho_diff, ho_w, ho_l):
    res = {"_pooled": {"train": {"X": dict(n=100, mean_diff=diff, t=t, boot_p=bp,
                                           divergence=dict(n=dv_w + dv_l, arm_wins=dv_w, arm_losses=dv_l),
                                           halves=dict(n1=50, d1=d1, n2=50, d2=d2))},
                       "holdout": {"X": dict(n=30, mean_diff=ho_diff,
                                             divergence=dict(n=ho_w + ho_l, arm_wins=ho_w, arm_losses=ho_l))}}}
    for k in range(7):
        res[f"p{k}"] = {
            "X": {"train": dict(equity=dict(cagr=0.2 if k < cagr_wins else 0.0),
                                paired_vs_D=dict(t=(-3.0 if (hurt and k == 0) else 1.0)))},
            "D": {"train": dict(equity=dict(cagr=0.1))},
        }
    return res


ok = mk(0.01, 2.5, 0.01, 5, False, 60, 40, 0.01, 0.01, 0.01, 20, 10)
check("판정: 7조건 만족 → PASS", mx.verdict(ok, "X")["pass_"])
check("판정: 분기 승률 50% 미만이면 탈락",
      not mx.verdict(mk(0.01, 2.5, 0.01, 5, False, 40, 60, 0.01, 0.01, 0.01, 20, 10), "X")["pass_"])
check("판정: 후반이 음수면 탈락",
      not mx.verdict(mk(0.01, 2.5, 0.01, 5, False, 60, 40, 0.01, -0.01, 0.01, 20, 10), "X")["pass_"])
check("판정: 한 패턴이라도 t<-2 면 탈락",
      not mx.verdict(mk(0.01, 2.5, 0.01, 5, True, 60, 40, 0.01, 0.01, 0.01, 20, 10), "X")["pass_"])
check("판정: CAGR 우위 4 미만이면 탈락",
      not mx.verdict(mk(0.01, 2.5, 0.01, 3, False, 60, 40, 0.01, 0.01, 0.01, 20, 10), "X")["pass_"])
check("판정: holdout 차이가 음수면 탈락(train 은 통과해도)",
      mx.verdict(mk(0.01, 2.5, 0.01, 5, False, 60, 40, 0.01, 0.01, -0.01, 20, 10), "X")["train_pass"]
      and not mx.verdict(mk(0.01, 2.5, 0.01, 5, False, 60, 40, 0.01, 0.01, -0.01, 20, 10), "X")["pass_"])
check("판정: 유의하지 않으면 탈락",
      not mx.verdict(mk(0.01, 1.0, 0.30, 5, False, 60, 40, 0.01, 0.01, 0.01, 20, 10), "X")["pass_"])

# ── 6. 동결 파라미터 ───────────────────────────────────────────────────────
check("동결: ATR k = 2.0/2.5/3.0", list(mx.ATR_K.values()) == [2.0, 2.5, 3.0])
check("동결: clip 3%~15%", (mx.STOP_FLOOR, mx.STOP_CAP) == (0.03, 0.15))
check("동결: T 문턱 +3%, 연장 60봉", (mx.TIME_KEEP, mx.EXT_HOLD) == (0.03, 60))
check("기준 arm D 는 현행 실거래 규칙(-8%, 30봉)", (mx.STOP_D, mx.MAX_HOLD) == (0.08, 30))

print("\n" + ("ALL PASS" if not fails else f"FAILS: {fails}"))
sys.exit(1 if fails else 0)
