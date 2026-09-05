"""
validate_revival + 신규 디텍터 4종 로직 검증 (합성 데이터, 네트워크 없음).

고정하는 성질:
  - 신규 디텍터는 detect(rows)->list[int] 계약을 지키고, 정의대로만 발화한다
  - live_outcome 이 1d/4h 는 방식D(method_s.outcome = eval_D 규칙), 1h 는 ATR 배리어로 분기한다
  - gate_cell 은 동결 5조건 + 베이스라인 k=n
  - confirm 은 C1(두 코호트)·C2(holdout)·C3(자산곡선) 전부 요구
  - 후보 목록이 va.PATTERNS 에 실재하는 cid 만 가리킨다 (오타로 조용히 빠지지 않게)
  - 실거래 코드가 이 모듈·신규 디텍터를 import 하지 않는다
실행: python test_revival.py
"""
import random
import sys

import detector_donchian20 as dch
import detector_down_streak3 as dst
import detector_ibs_low as ibs
import detector_rsi2_low as rsi2
import validate_regime_split_all as va
import validate_revival as vr

fails = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f" — {detail}"))
    cond or fails.append(name)


def bar(i, o, h, l, c, day0=1):
    from datetime import date, timedelta
    return dict(ts=i, date=(date(2024, 1, day0) + timedelta(days=i)).isoformat(), o=o, h=h, l=l, c=c, v=100.0)


# ── 1. 디텍터 정의 ───────────────────────────────────────────────────────────
rows = [bar(0, 100, 101, 99, 100), bar(1, 100, 102, 90, 90.5)]     # 종가가 봉 하단(IBS≈0.04), 하락
check("ibs_low: 하단 마감 하락 봉 발화", ibs.detect(rows) == [1], ibs.detect(rows))
rows2 = [bar(0, 100, 101, 99, 100), bar(1, 100, 102, 90, 101.5)]   # 하단이지만 전일보다 상승 → 아님
check("ibs_low: 상승 봉이면 미발화", ibs.detect(rows2) == [])
rows3 = [bar(0, 100, 100, 100, 100), bar(1, 100, 100, 100, 99)]    # h==l 은 나눗셈 회피
check("ibs_low: h==l 봉은 건너뜀", ibs.detect(rows3) == [])

cs = [100, 99, 98]              # 두 번 연속 하락 → RSI(2)=0
rr = [bar(i, c, c + 1, c - 1, c) for i, c in enumerate(cs)]
check("rsi2_low: 연속 하락이면 RSI(2)<10 발화", rsi2.detect(rr) == [2], rsi2.detect(rr))
cs = [100, 101, 102]
rr = [bar(i, c, c + 1, c - 1, c) for i, c in enumerate(cs)]
check("rsi2_low: 연속 상승이면 미발화", rsi2.detect(rr) == [])
rs_ = rsi2.rsi_series([100, 99, 98, 99, 100, 101])
check("rsi2_low: RSI 는 0~100 범위", all(v is None or 0 <= v <= 100 for v in rs_))

cs = [100] * 10 + [100, 99, 98, 97]       # 3연속 하락 + 10일 최저 종가 밑
rr = [bar(i, c, c + 1, c - 1, c) for i, c in enumerate(cs)]
check("down_streak3: 3연속 하락 + 신저가 발화", dst.detect(rr) == [13], dst.detect(rr))
cs = [100] * 10 + [100, 99, 98, 98.5]     # 마지막 봉 상승 → 아님
rr = [bar(i, c, c + 1, c - 1, c) for i, c in enumerate(cs)]
check("down_streak3: 연속이 끊기면 미발화", dst.detect(rr) == [])
cs = [90] * 10 + [100, 99, 98, 97]        # 3연속 하락이지만 10일 저점(90) 위 → 아님
rr = [bar(i, c, c + 1, c - 1, c) for i, c in enumerate(cs)]
check("down_streak3: 신저가 아니면 미발화", dst.detect(rr) == [])

cs = [100] * 22 + [105, 106]
rr = [bar(i, c, c + 0.5, c - 0.5, c) for i, c in enumerate(cs)]
check("donchian20: 첫 돌파 봉만 발화(연속 돌파 2번째는 제외)", dch.detect(rr) == [22], dch.detect(rr))
cs = [100] * 22 + [100.4]                 # 직전 20봉 고가 100.5 미만 → 아님
rr = [bar(i, c, c + 0.5, c - 0.5, c) for i, c in enumerate(cs)]
check("donchian20: 고가 미돌파면 미발화", dch.detect(rr) == [])

for m in (ibs, rsi2, dst, dch):
    check(f"{m.PATTERN}: evaluate 가 존재(orchestrator 계약)", callable(getattr(m, "evaluate", None)))


# ── 2. live_outcome 분기 ────────────────────────────────────────────────────
random.seed(3)
px, walk = 100.0, []
for i in range(120):
    nxt = px * (1 + random.gauss(0, 0.02))
    walk.append(bar(i, px, max(px, nxt) * 1.01, min(px, nxt) * 0.99, nxt)); px = nxt
reg = {r["date"]: "bull_btc" for r in walk}
lab = lambda j: reg.get(walk[j]["date"])
r1d = vr.live_outcome("1d", walk, 10, "long", lab)
check("1d: 방식D 결과 4-튜플(ret, hold, reason, stop)", r1d is not None and len(r1d) == 4 and r1d[3] == vr.STOP, r1d)
check("1d: 청산 사유는 D 의 것", r1d[2] in ("stop", "regime_switch", "maxhold", "opp_signal"), r1d[2])
check("1d: 보유 <= 30봉", r1d[1] <= vr.MAX_HOLD)
import method_s as ms
same = ms.outcome(walk, 10, "long", set(), lab, use_regime=True, max_hold=vr.MAX_HOLD)
check("1d: method_s.outcome(=eval_D 규칙)과 동일", (r1d[0], r1d[1], r1d[2]) == same, (r1d, same))

import intraday_lab as il
atr = il.atr_series(walk)
r1h = vr.live_outcome("1h", walk, 30, "long", lab, atr)
check("1h: ATR 배리어 결과, 보유 = HORIZON", r1h is not None and r1h[1] == il.HORIZON["1h"], r1h)
check("1h: 손절폭이 k x ATR / 진입가", abs(r1h[3] - il.K_ATR * atr[30] / walk[30]["c"]) < 1e-12)
check("1h: ATR 없으면 None", vr.live_outcome("1h", walk, 30, "long", lab, None) is None)

# 레짐 전환이 있으면 D 는 그 봉에서 청산한다 (method_s 와 같은 규칙임을 재확인)
reg2 = dict(reg); reg2[walk[13]["date"]] = "bear"
lab2 = lambda j: reg2.get(walk[j]["date"])
r_sw = vr.live_outcome("1d", walk, 10, "long", lab2)
check("1d: 레짐 전환 봉에서 청산(또는 그 전 손절)", r_sw[2] in ("regime_switch", "stop") and r_sw[1] <= 3, r_sw)


# ── 3. gate_cell ────────────────────────────────────────────────────────────
def sig(d, ret, reason="maxhold"):
    return dict(date=d, ret=ret, hold=10, reason=reason)


good = [sig(f"2024-{1 + i // 28:02d}-{1 + i % 28:02d}", 0.05 if i % 3 else -0.02) for i in range(60)]
pool = [random.gauss(0.0, 0.03) for _ in range(500)]
g = vr.gate_cell(good, pool)
check("gate: n·mean·median·boot_p·OOS 계산", g["n"] == 60 and g["mean"] > 0 and g["median"] > 0 and g["oos_pos"] >= 2, g)
check("gate: 베이스라인 k = n", g["base_k"] == 60)
check("gate: 엣지 큰 셀은 PASSED", g["verdict"] == "PASSED", g["reason"])
bad = [sig(f"2024-{1 + i // 28:02d}-{1 + i % 28:02d}", random.gauss(0, 0.03)) for i in range(60)]
b = vr.gate_cell(bad, pool)
check("gate: 무작위와 구분 안 되면 REJECTED", b["verdict"] == "REJECTED", b)
few = vr.gate_cell(good[:10], pool)
check("gate: n<20 이면 사유에 표기", "n<20" in few["reason"])
check("gate: 풀 없으면 boot_p=1", vr.gate_cell(good, [])["boot_p"] == 1.0)
check("gate: 청산 사유 분포 기록", g["reasons"].get("maxhold") == 60)


# ── 4. confirm ──────────────────────────────────────────────────────────────
def full_sig(d, ret):
    from datetime import date, timedelta
    x = date.fromisoformat(d) + timedelta(days=5)
    return dict(date=d, ret=ret, hold=5, reason="maxhold", stop_pct=0.08, vol=0.8, exit_date=x.isoformat())


train_sigs = [full_sig(f"2023-{1 + i // 28:02d}-{1 + i % 28:02d}", 0.06 if i % 3 else -0.02) for i in range(90)]
hold_sigs = [full_sig(f"2025-{1 + i // 28:02d}-{1 + i % 28:02d}", 0.04) for i in range(15)]
passed = dict(verdict="PASSED")
cells_ok = {"all": dict(gate=passed, sigs=train_sigs + hold_sigs),
            "top30": dict(gate=passed, sigs=train_sigs + hold_sigs)}
cf = vr.confirm(cells_ok, "2025-01-01", 700)
check("confirm: 두 코호트 통과 + holdout 양수 + 자산곡선 양수 → CONFIRMED", cf["confirmed"], cf)
cells_one = {"all": dict(gate=dict(verdict="REJECTED"), sigs=[]), "top30": cells_ok["top30"]}
check("confirm: top30 통과·all 기각이면 C1 통과(실거래 코호트 기준)", vr.confirm(cells_one, "2025-01-01", 700)["c1_live_cohort"])
cells_rev = {"all": cells_ok["all"], "top30": dict(gate=dict(verdict="REJECTED"), sigs=cells_ok["top30"]["sigs"])}
check("confirm: all 통과·top30 기각이면 탈락(C1)", not vr.confirm(cells_rev, "2025-01-01", 700)["confirmed"])
cells_ho = {k: dict(gate=passed, sigs=train_sigs + [full_sig(f"2025-01-{1 + i:02d}", -0.03) for i in range(15)])
            for k in ("all", "top30")}
check("confirm: holdout 음수면 탈락(C2)", not vr.confirm(cells_ho, "2025-01-01", 700)["confirmed"])
cells_few = {k: dict(gate=passed, sigs=train_sigs + hold_sigs[:5]) for k in ("all", "top30")}
check("confirm: holdout n<10 이면 탈락(C2 판정 불가)", not vr.confirm(cells_few, "2025-01-01", 700)["confirmed"])
losing = [full_sig(f"2023-{1 + i // 28:02d}-{1 + i % 28:02d}", -0.03) for i in range(90)]
cells_eq = {k: dict(gate=passed, sigs=losing + hold_sigs) for k in ("all", "top30")}
check("confirm: 자산곡선 음수면 탈락(C3)", not vr.confirm(cells_eq, "2025-01-01", 700)["confirmed"])


# ── 5. 후보 목록 정합 ───────────────────────────────────────────────────────
tab = vr._pattern_table()
missing = [cid for cid, _ in vr.CANDIDATES if cid not in tab]
check("CANDIDATES 의 cid 가 전부 va.PATTERNS 에 실재", not missing, missing)
check("신규 4종이 표에 등록", all(cid in tab for cid, *_ in vr.NEW_PATTERNS))
check("three_soldiers_4h 재판정이 후보에 포함", ("three_soldiers_4h", "bull_btc") in vr.CANDIDATES)
check("확인 코호트는 실거래 상위 코호트(top30)", vr.CONFIRM_COHORT == "top30")


# ── 6. 실거래 코드 비의존 ───────────────────────────────────────────────────
for f in ("paper_executor.py", "scheduler.py", "exchange.py"):
    src = open(f, encoding="utf-8").read()
    check(f"{f} 는 validate_revival 을 import 하지 않음", "validate_revival" not in src)
    check(f"{f} 는 신규 디텍터를 import 하지 않음",
          not any(m in src for m in ("detector_ibs_low", "detector_rsi2_low", "detector_down_streak3", "detector_donchian20")))
import json
u = json.load(open("universe.json", encoding="utf-8"))
adopted = json.dumps(u.get("adopted_patterns", [])) + json.dumps(u.get("adopted_4h_patterns", []))
check("신규 디텍터는 universe.json adopted 에 없음(미등재)",
      not any(m in adopted for m in ("ibs_low", "rsi2_low", "down_streak3", "donchian20")))


# ── 1h 채점표 (2026-09-05): 봉 ts 시각 자산곡선 + TF 별 holdout ─────────────
import method_x as mx
check("HOLDOUT_DAYS_BY_TF: 1h 는 90일, 1d/4h 는 종전 365일",
      vr.HOLDOUT_DAYS_BY_TF["1h"] == 90 and vr.HOLDOUT_DAYS_BY_TF["1d"] == vr.HOLDOUT_DAYS == 365 == vr.HOLDOUT_DAYS_BY_TF["4h"])
t0 = vr._tnum(dict(date="2026-09-05"))
t1 = vr._tnum(dict(date="2026-09-05", ts=1788566400000))          # 2026-09-05 00:00 UTC
t2 = vr._tnum(dict(date="2026-09-05", ts=1788566400000 + 3600000 * 5))
check("_tnum: ts 없으면 date ordinal", t0 == float(__import__("datetime").date(2026, 9, 5).toordinal()))
check("_tnum: ts 는 같은 날 자정과 일치, 5시간 뒤는 +5/24 일", abs(t1 - t0) < 1e-6 and abs((t2 - t1) - 5 / 24) < 1e-6)
check("method_x._tnum: 숫자는 그대로, 문자열은 ordinal", mx._tnum(12.5) == 12.5 and mx._tnum("2026-09-05") == t0)
# 같은 날 진입·청산되는 1h 거래 3건 — 날짜 문자열로 넘기면 빠지고, 분수 일수로 넘기면 전부 잡힌다
base_ts = 1788566400000
sig1h = [dict(date="2026-09-05", exit_date="2026-09-05", ret=0.02, hold=6, reason="atr", stop_pct=0.01, vol=0.8,
              t_in=vr._tnum(dict(ts=base_ts + 3600000 * k)), t_out=vr._tnum(dict(ts=base_ts + 3600000 * (k + 6))))
         for k in (0, 1, 2)]
eq_ts = vr.equity(sig1h, 300)
legacy = [{k: v for k, v in s.items() if k not in ("t_in", "t_out")} for s in sig1h]
eq_dt = vr.equity(legacy, 300)
check("1h 자산곡선: 분수 일수로 넘기면 같은 날 3거래가 전부 반영돼 자산이 늘어난다", eq_ts is not None and eq_ts["final"] > mx.START_EQ)
check("1h 자산곡선: 날짜 문자열 폴백은 같은 날 거래를 놓친다(종전 'C3 계산 불가' 재현)",
      eq_dt is not None and eq_dt["final"] == mx.START_EQ)
check("CANDIDATES 에 1h 셀이 들어갔다", any(cid.endswith("_1h") for cid, _ in vr.CANDIDATES))

print(f"\n{len(fails)} failed")
sys.exit(1 if fails else 0)
