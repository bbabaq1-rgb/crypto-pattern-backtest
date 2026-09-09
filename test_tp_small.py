"""
test_tp_small.py — 작은 고정 익절(+1%) 사전 등록 고정 (2026-09-09).

지키는 성질:
  · 동결 격자·주 판정 셀·비용·레버리지가 결과를 보고 바뀌지 않는다
  · 배리어 규칙이 **인과적**이다 — 진입 봉 이후만 본다, 진입가는 신호봉 종가
  · 같은 봉에서 익절·손절이 겹치면 손절 우선 (보수적)
  · 랜덤워크 도달률·손익분기 승률 공식이 실제 기대값과 정합한다
  · 전용 포트(P2)가 **한 번에 한 포지션**이고 복리로 굴러간다
  · DEPLOY_ON_PASS=False 이고 실거래 청산 경로 어디에도 등재돼 있지 않다
"""
import inspect
import json
import statistics as st

import validate_tp_small as T

fails = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


# ── 동결 파라미터 ────────────────────────────────────────────────────────────
check("익절 격자 1/2/3%", T.TP_LEVELS == (0.01, 0.02, 0.03), T.TP_LEVELS)
check("손절 격자 1/2/4/8% (8% = 현행)", T.SL_LEVELS == (0.01, 0.02, 0.04, 0.08), T.SL_LEVELS)
check("12셀 + 기준선 D", len(T.CELLS) == 12 and T.ARMS[0] == "D" and len(T.ARMS) == 13)
check("주 판정 셀은 사용자가 지정한 익절1%/손절8% 하나",
      T.PRIMARY == (0.01, 0.08) and T.PRIMARY_ARM == "T1S8", (T.PRIMARY, T.PRIMARY_ARM))
check("동결 왕복 수수료 0.2% (레포 공통)", T.FEE == 0.002, T.FEE)
check("마찰 스트레스 0.4% (캐스케이드 내성 한계와 같은 값)", T.FRICTION == 0.004, T.FRICTION)
check("P2 레버리지 3x (사용자 지정 '레버리지 3프로')", T.POT_LEV == 3, T.POT_LEV)
check("홀드아웃 365일", T.HOLDOUT_DAYS == 365, T.HOLDOUT_DAYS)
check("미도달 강제청산 한도 250봉", T.MAX_SCAN == 250, T.MAX_SCAN)
check("DEPLOY_ON_PASS=False — 통과해도 실거래 반영 없음", T.DEPLOY_ON_PASS is False)
check("표본은 배포 7패턴 (method_t.PATS 그대로)", len(T.PATS) == 7)

# ── 배리어 산술 ──────────────────────────────────────────────────────────────
check("랜덤워크 도달률 = SL/(TP+SL)", abs(T.rw_hit(0.01, 0.08) - 8 / 9) < 1e-12, T.rw_hit(0.01, 0.08))
check("대칭 배리어는 50%", abs(T.rw_hit(0.02, 0.02) - 0.5) < 1e-12)
for tp, sl in T.CELLS:
    w = T.rw_hit(tp, sl)
    ev = w * tp - (1 - w) * sl
    if abs(ev) > 1e-12:
        check(f"랜덤워크 도달률에서 수수료 전 기대값 0 ({tp},{sl})", False, ev)
check("랜덤워크 도달률에서 수수료 전 기대값이 정확히 0 (12셀 전부)", True)
be = T.breakeven_win(0.01, 0.08)
check("손익분기 승률 1%/8% = 91.11%", abs(be - 0.082 / 0.09) < 1e-12, be)
check("손익분기 승률에서 수수료 후 기대값 0",
      abs(be * (0.01 - T.FEE) - (1 - be) * (0.08 + T.FEE)) < 1e-12)
check("손익분기 승률 > 랜덤워크 도달률 (수수료가 문턱을 올린다)",
      all(T.breakeven_win(tp, sl) > T.rw_hit(tp, sl) for tp, sl in T.CELLS))
check("마찰 스트레스는 동결 가정과의 차이만 뺀다",
      abs(T.stressed([0.01, 0.03]) - (0.02 - (T.FRICTION - T.FEE))) < 1e-12)
check("빈 표본은 None", T.stressed([]) is None)


# ── 배리어 규칙 (합성 봉) ────────────────────────────────────────────────────
def bar(o, h, l, c, d="2024-01-01"):
    return dict(date=d, ts=0, o=o, h=h, l=l, c=c, v=1)


base = [bar(100, 100, 100, 100, f"2024-01-{i+1:02d}") for i in range(3)]
rows = base + [bar(100, 101.5, 99.5, 101, "2024-01-04")] + [bar(100, 100, 100, 100, "2024-01-05")]
r = T.outcome_tp(rows, 2, "long", 0.01, 0.08)
check("롱: +1% 고가 도달 → 익절, 수익 = tp - 수수료",
      r and r[2] == "target" and abs(r[0] - (0.01 - T.FEE)) < 1e-12 and r[1] == 1, r)

rows2 = base + [bar(100, 100.5, 91.0, 92, "2024-01-04")]
r = T.outcome_tp(rows2, 2, "long", 0.01, 0.08)
check("롱: -8% 저가 도달 → 손절, 손실 = -sl - 수수료",
      r and r[2] == "stop" and abs(r[0] - (-0.08 - T.FEE)) < 1e-12, r)

rows3 = base + [bar(100, 105, 91.0, 95, "2024-01-04")]
r = T.outcome_tp(rows3, 2, "long", 0.01, 0.08)
check("같은 봉에서 둘 다 닿으면 **손절 우선**(보수적)", r and r[2] == "stop", r)

rows4 = base + [bar(100, 100.2, 99.8, 100, f"2024-02-{i+1:02d}") for i in range(5)]
r = T.outcome_tp(rows4, 2, "long", 0.01, 0.08)
check("어느 배리어에도 안 닿으면 마지막 봉 시가로 'open' 청산",
      r and r[2] == "open" and r[1] == len(rows4) - 1 - 2, r)

rows5 = base + [bar(100, 100.5, 98.5, 99, "2024-01-04")]
r = T.outcome_tp(rows5, 2, "short", 0.01, 0.08)
check("숏: -1% 저가 도달 → 익절", r and r[2] == "target" and abs(r[0] - (0.01 - T.FEE)) < 1e-12, r)
r = T.outcome_tp(base + [bar(100, 109, 100, 108, "2024-01-04")], 2, "short", 0.01, 0.08)
check("숏: +8% 고가 도달 → 손절", r and r[2] == "stop", r)

# 인과성 — 진입 봉 자신의 고가/저가는 쓰지 않는다
spike = base[:2] + [bar(100, 120, 80, 100, "2024-01-03")] + [bar(100, 100, 100, 100, "2024-01-04")]
r = T.outcome_tp(spike, 2, "long", 0.01, 0.08)
check("진입 봉의 고가·저가는 배리어 판정에 쓰지 않는다(룩어헤드 없음)",
      r and r[2] == "open", r)
src = inspect.getsource(T.outcome_tp)
check("스캔은 si+1 부터", "range(si + 1" in src, src[:200])
check("배리어 기준가는 신호봉 **종가**", 'base = rows[si]["c"]' in src)
check("레짐·반대신호·시간 청산이 배리어 규칙에 없다",
      "REGMAP" not in src and "opp_set" not in src and "MAX_HOLD" not in src)

# ── P2 전용 포트 ─────────────────────────────────────────────────────────────
tr = [("2024-01-01", "2024-01-02", 0.01, 1, "target", 0.08, 0.8),
      ("2024-01-03", "2024-01-04", 0.01, 1, "target", 0.08, 0.8)]
p = T.pot_curve(tr, lev=3, start=100.0)
check("P2 복리 — 두 번 연속 +1%(3x) 는 100 x 1.03^2",
      p and abs(p["final"] - 100 * 1.03 ** 2) < 1e-9, p)
check("P2 배수 기록", p and abs(p["mult"] - 1.03 ** 2) < 1e-9)
over = [("2024-01-01", "2024-01-10", 0.01, 9, "target", 0.08, 0.8),
        ("2024-01-02", "2024-01-03", 0.50, 1, "target", 0.08, 0.8)]
p2 = T.pot_curve(over, lev=3, start=100.0)
check("P2 는 한 번에 한 포지션 — 열려 있는 동안 온 신호는 버린다",
      p2 and p2["taken"] == 1 and p2["skipped"] == 1, p2)
check("P2 는 버린 신호의 수익을 반영하지 않는다", p2 and abs(p2["final"] - 103.0) < 1e-9, p2)
p3 = T.pot_curve([("2024-01-01", "2024-01-02", -0.40, 1, "stop", 0.08, 0.8)], lev=3, start=100.0)
check("P2 파산 하한 0", p3 and p3["final"] == 0.0, p3)
check("P2 빈 표본 None", T.pot_curve([]) is None)
check("P2 는 시간순으로 정렬한 뒤 잡는다", "sorted(trades, key=" in inspect.getsource(T.pot_curve))

# ── Holm ─────────────────────────────────────────────────────────────────────
h = T.holm({"a": 0.01, "b": 0.02, "c": 0.30})
check("Holm: 가장 작은 p 에 m 배", abs(h["a"] - 0.03) < 1e-9, h)
check("Holm: 단조 비감소", h["a"] <= h["b"] <= h["c"], h)
check("Holm: 1.0 상한", T.holm({"a": 0.6, "b": 0.7})["b"] <= 1.0)
check("Holm: None 은 가족에서 빠진다", "b" not in T.holm({"a": 0.01, "b": None}))

# ── 판정 기준이 9개이고 사후에 늘리거나 줄이지 않는다 ─────────────────────────
msrc = inspect.getsource(T.verdict)
for k in ("c1_paired_sig", "c2_mean_pos", "c3_lift_pos", "c4_friction", "c5_halves",
          "c6_cagr_wins", "c7_holdout_diff", "c8_holdout_mean", "c9_pot_cagr"):
    check(f"판정 기준 {k} 존재", k in msrc)
check("PASS 는 9개 전부 만족일 때만",
      "c1 and c2 and c3 and c4 and c5 and c6 and c7 and c8 and c9" in msrc)
check("무작위 베이스라인은 판정에 안 들어간다(진단 전용)",
      "rand" not in msrc and "edge" not in msrc)

# ── 실거래 무관 ──────────────────────────────────────────────────────────────
mod_src = inspect.getsource(T)
check("실거래 체결 엔진을 import 하지 않는다",
      "import paper_executor" not in mod_src and "import exchange" not in mod_src)
check("주문·DB 를 건드리지 않는다",
      "place_" not in mod_src and "supabase" not in mod_src.lower())
sched = open("scheduler.py", encoding="utf-8").read()
check("스케줄러가 이 모듈을 모른다", "validate_tp_small" not in sched and "tp_small" not in sched)
uni = json.dumps(json.load(open("universe.json", encoding="utf-8")), ensure_ascii=False)
check("universe 에 등재 없음", "tp_small" not in uni and "T1S8" not in uni)
pe = open("paper_executor.py", encoding="utf-8").read()
check("실거래 청산 경로가 이 격자를 모른다", "T1S8" not in pe and "tp_small" not in pe)
reg = json.load(open("registry.json", encoding="utf-8"))
check("registry 에 사전 등록 기록", "tp_small_prereg_2026_09_09" in reg)

# ── 워크플로 ────────────────────────────────────────────────────────────────
wf = open(".github/workflows/tp_small.yml", encoding="utf-8").read()
check("워크플로가 로직 테스트를 먼저 돌린다", "python test_tp_small.py" in wf)
check("tests.yml 등재",
      "test_tp_small.py" in open(".github/workflows/tests.yml", encoding="utf-8").read())

print(f"\n{len(fails)} failed")
raise SystemExit(1 if fails else 0)
