"""
test_tp1_stop.py — 손절 스윕(validate_tp1_stop) 로직 오프라인 검증. 네트워크 불필요.
실행: python test_tp1_stop.py
"""
import sys

import paper_executor as pe
import validate_tp1_stop as vs

fails = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f" — {detail}"))
    cond or fails.append(name)


def bar(o, h, l, c, i, date="2026-01-01"):
    return dict(o=o, h=h, l=l, c=c, v=1.0, date=date, ts=1_700_000_000_000 + i * 3_600_000)


# ── 1. 배리어 판정 ─────────────────────────────────────────────────────────────
base = [bar(100, 100, 100, 100, 0)]
tp_first = base + [bar(100, 100.5, 99.8, 100.2, 1), bar(100, 101.2, 99.9, 101, 2)]
r = vs.resolve(tp_first, 0, 0.01, 0.08)
check("익절 먼저 → +1% − 수수료, hold 2, target", r == (0.01 - vs.FEE, 2, "target"), r)
sl_first = base + [bar(100, 100.3, 91.5, 92, 1), bar(92, 102, 91, 101, 2)]
r = vs.resolve(sl_first, 0, 0.01, 0.08)
check("손절 먼저 → −8% − 수수료, hold 1, stop", r == (-0.08 - vs.FEE, 1, "stop"), r)
tie = base + [bar(100, 101.5, 91.5, 95, 1)]
r = vs.resolve(tie, 0, 0.01, 0.08)
check("같은 봉 동률 → 손절 우선(보수)", r[2] == "stop" and r[0] == -0.08 - vs.FEE, r)
flat = base + [bar(100, 100.4, 99.7, 100.1, i) for i in range(1, 6)]
r = vs.resolve(flat, 0, 0.01, 0.08, max_scan=3)
check("미해소 → 스캔 끝 봉 시가 청산(open)", r[2] == "open" and r[1] == 3 and abs(r[0] - (0.0 - vs.FEE)) < 1e-12, r)
check("신호봉 자체의 고가는 안 본다(인과)",
      vs.resolve([bar(100, 105, 95, 100, 0), bar(100, 100.1, 99.9, 100, 1)], 0, 0.01, 0.08, max_scan=1)[2] == "open")
r3 = vs.resolve(sl_first, 0, 0.01, 0.03)
check("손절 3% 는 같은 봉에서 먼저 걸린다(저가 91.5 → −8.5%)", r3[2] == "stop" and r3[0] == -0.03 - vs.FEE, r3)

# ── 2. 포트 규칙 = paper_executor.cap_margin(loss_floor) ────────────────────────
cap = pe.LIVE_CAPS["tp1_engulfing_1h"]
check("실거래 cap 이 loss_floor 이고 reset_on_loss 는 꺼져 있다", cap.get("loss_floor") is True and not cap.get("reset_on_loss"))
seq = [0.008, 0.008, -0.082, 0.008, -0.01, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, -0.082]
pot = vs.START
for r_ in seq:
    pot = vs.pot_next(pot, r_)
ref = pe.cap_margin(cap, "tp1_engulfing_1h", [dict(pattern="tp1_engulfing_1h", method="D", ret=x) for x in seq])
check("스윕의 포트 스텝이 실거래 cap_margin 과 12스텝 일치", abs(round(pot, 2) - ref) < 1e-9, (round(pot, 2), ref))
check("바닥: 손절로 70 밑이면 70", vs.pot_next(75.0, -0.082) == 70.0)
check("바닥 위 손실은 유지", abs(vs.pot_next(85.0, -0.01) - 85.0 * 0.97) < 1e-9)
check("익절은 ×(1+0.008×3)", abs(vs.pot_next(70.0, 0.008) - 71.68) < 1e-9)

# ── 3. 순차 시뮬 ───────────────────────────────────────────────────────────────
def mk(sym, start_i, path):
    """path: 신호봉 뒤 봉들의 (h, l)"""
    rows = [bar(100, 100, 100, 100, start_i + k) for k in range(0)]
    rows = [bar(100, 100, 100, 100, start_i)] + [bar(100, h, l, 100, start_i + 1 + k) for k, (h, l) in enumerate(path)]
    return sym, rows, 0

sigA = mk("A", 0, [(101.2, 99.9)])                 # 1봉 뒤 익절
sigB = mk("B", 0, [(100.1, 99.9), (101.2, 99.9)])  # 같은 시각 신호 → A 보유 중이라 버려짐
sigC = mk("C", 5, [(100.1, 91.0)])                 # 나중 신호, 손절
res = vs.simulate([sigA, sigB, sigC], 0.08)
check("보유 중 신호는 버린다(B 스킵)", res["n"] == 2 and res["skipped"] == 1, (res["n"], res["skipped"]))
check("계좌손익 = Σ 증거금×ret×3", abs(res["pnl"] - round(70 * (0.01 - vs.FEE) * 3 + 71.68 * (-0.08 - vs.FEE) * 3, 2)) < 0.02, res["pnl"])
check("손절 뒤 포트 바닥 70", res["pot_final"] == 70.0 and res["pot_pure"] < 70.0, (res["pot_final"], res["pot_pure"]))
check("승률·손절 수 집계", res["wins"] == 1 and res["stops"] == 1)
check("손익분기 승률 = (SL+FEE)/(TP+SL)", abs(res["breakeven"] - (0.08 + vs.FEE) / 0.09) < 1e-12)
# 진입 시각만으로 정렬(청산 시각을 미리 보지 않는다) — 같은 시각이면 입력 순서
resBA = vs.simulate([sigB, sigA, sigC], 0.08)
check("동시각 동률은 입력 순서(B 먼저면 B 가 잡히고 A 스킵)", resBA["trades"][0]["sym"] == "B" and resBA["skipped"] == 1)

rows_sw = vs.sweep([sigA, sigC], grid=(0.03, 0.08))
a = vs.answer([dict(r, sl=r["sl"]) for r in rows_sw]) if any(abs(r["sl"] - 0.08) < 1e-12 for r in rows_sw) else None
check("answer 가 최대 손익 셀과 현행 8% 차이를 낸다", a is not None and a["live_sl"] == 0.08 and "gap" in a, a)
check("3% 손절이 C 에서 덜 잃는다(−3% vs −8%)", rows_sw[0]["pnl"] > rows_sw[1]["pnl"], [r["pnl"] for r in rows_sw])

# ── 4. 동결 상수 ───────────────────────────────────────────────────────────────
check("익절 1% · 3x · 시작 70 · 현행 손절 8% 이 격자에 있다", vs.TP == 0.01 and vs.LEV == 3 and vs.START == 70.0 and 0.08 in vs.SL_GRID)
check("DEPLOY_ON_PASS=False", vs.DEPLOY_ON_PASS is False)
check("디텍터는 실거래와 같은 detector_engulfing, 인자 없음", vs.DETMOD == "detector_engulfing"
      and "mod.detect(rows)" in open("validate_tp1_stop.py", encoding="utf-8").read())
check("스케줄러 top20 정의와 같은 30봉 close×volume 순위", vs.turnover_rank({"X": [bar(1, 1, 1, 2, i) for i in range(40)],
                                                                    "Y": [bar(1, 1, 1, 1, i) for i in range(40)]}) == ["X", "Y"])

print(f"\n{len(fails)} failed")
sys.exit(1 if fails else 0)
