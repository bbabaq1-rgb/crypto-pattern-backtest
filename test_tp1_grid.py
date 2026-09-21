"""
test_tp1_grid.py — 익절×손절 격자(validate_tp1_grid) 로직 오프라인 검증. 네트워크 불필요.

가장 중요한 것: **전방 스캔 1회 최적화(first_hits/resolve_hits)가 어제 판의
validate_tp1_stop.resolve 와 전 셀에서 바이트 단위로 같은 답을 내는가.**
격자가 12 → 60셀이 되면서 넣은 최적화라 여기서 어긋나면 수치 전부가 무의미하다.

실행: python test_tp1_grid.py
"""
import random
import sys

import paper_executor as pe
import validate_tp1_grid as vg
import validate_tp1_stop as vs

fails = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f" — {detail}"))
    cond or fails.append(name)


def bar(o, h, l, c, i, date="2026-01-01"):
    return dict(o=o, h=h, l=l, c=c, v=1.0, date=date, ts=1_700_000_000_000 + i * 3_600_000)


def rand_rows(rng, n=60, start=100.0):
    rows = [bar(start, start, start, start, 0)]
    px = start
    for i in range(1, n):
        o = px
        c = o * (1 + rng.gauss(0, 0.012))
        h = max(o, c) * (1 + abs(rng.gauss(0, 0.010)))
        l = min(o, c) * (1 - abs(rng.gauss(0, 0.010)))
        rows.append(bar(o, h, l, c, i))
        px = c
    return rows


# ── 1. 최적화 동등성 — 이 테스트가 이 판의 근간 ────────────────────────────────
rng = random.Random(7)
mismatch = None
cells = 0
for trial in range(120):
    rows = rand_rows(rng, n=rng.choice([25, 60, 140]))
    si = rng.randrange(0, len(rows) - 2)
    hits = vg.first_hits(rows, si)
    if hits is None:
        continue
    for ti, tp in enumerate(vg.TP_GRID):
        for li, sl in enumerate(vg.SL_GRID):
            ref = vs.resolve(rows, si, tp, sl)
            got = vg.resolve_hits(rows, si, hits, ti, li, tp, sl)
            cells += 1
            if ref is None or got is None:
                if (ref is None) != (got is None):
                    mismatch = (trial, si, tp, sl, ref, got)
                continue
            if not (abs(ref[0] - got[0]) < 1e-12 and ref[1] == got[1] and ref[2] == got[2]):
                mismatch = (trial, si, tp, sl, ref, got)
check(f"resolve_hits ≡ validate_tp1_stop.resolve (합성 {cells}셀)", mismatch is None, mismatch)

# 극단 경로도 — 즉시 손절 / 즉시 익절 / 동률 / 미해소
base = [bar(100, 100, 100, 100, 0)]
for name, tail in (
    ("즉시 익절", [bar(100, 104, 99.8, 103, 1)]),
    ("즉시 손절", [bar(100, 100.2, 75, 80, 1)]),
    ("같은 봉 동률", [bar(100, 104, 75, 95, 1)]),
    ("미해소", [bar(100, 100.2, 99.8, 100, i) for i in range(1, 8)]),
    ("먼저 익절 뒤 손절", [bar(100, 104, 99.9, 103, 1), bar(103, 103, 70, 75, 2)]),
    ("먼저 손절 뒤 익절", [bar(100, 100.1, 90, 92, 1), bar(92, 130, 92, 128, 2)]),
):
    rows = base + tail
    hits = vg.first_hits(rows, 0, max_scan=6)
    bad = []
    for ti, tp in enumerate(vg.TP_GRID):
        for li, sl in enumerate(vg.SL_GRID):
            ref = vs.resolve(rows, 0, tp, sl, max_scan=6)
            got = vg.resolve_hits(rows, 0, hits, ti, li, tp, sl)
            if (ref is None) != (got is None):
                bad.append((tp, sl, ref, got))
            elif ref is not None and not (abs(ref[0] - got[0]) < 1e-12
                                          and ref[1] == got[1] and ref[2] == got[2]):
                bad.append((tp, sl, ref, got))
    check(f"극단 경로 동등: {name}", not bad, bad[:3])

check("무효 신호(마지막 봉)는 None", vg.first_hits([bar(100, 100, 100, 100, 0)], 0) is None)
check("가격 0 이면 None", vg.first_hits([bar(0, 0, 0, 0, 0), bar(1, 1, 1, 1, 1)], 0) is None)

# 동률 플래그
rows = base + [bar(100, 104, 75, 95, 1)]
hits = vg.first_hits(rows, 0)
ti = vg.TP_GRID.index(0.02)
li = vg.SL_GRID.index(0.08)
r = vg.resolve_hits(rows, 0, hits, ti, li, 0.02, 0.08)
check("동률이면 손절 우선 + tie=True", r[2] == "stop" and r[3] is True, r)
rows2 = base + [bar(100, 104, 99.9, 103, 1)]
h2 = vg.first_hits(rows2, 0)
check("익절만이면 tie=False", vg.resolve_hits(rows2, 0, h2, ti, li, 0.02, 0.08)[3] is False)

# first_hits 자체 — 최초 도달 봉이 임계값에 대해 비감소
rows3 = base + [bar(100, 101.2, 99, 101, 1), bar(101, 103.5, 97.5, 103, 2), bar(103, 106, 94, 95, 3)]
h3 = vg.first_hits(rows3, 0)
tb = [x for x in h3["tp_bar"] if x is not None]
sb = [x for x in h3["sl_bar"] if x is not None]
check("tp 최초도달 봉이 비감소", tb == sorted(tb), h3["tp_bar"])
check("sl 최초도달 봉이 비감소", sb == sorted(sb), h3["sl_bar"])
check("격자는 오름차순(포인터 스캔 전제)",
      list(vg.TP_GRID) == sorted(vg.TP_GRID) and list(vg.SL_GRID) == sorted(vg.SL_GRID))

# ── 2. 어제 판과 공유하는 정의 ─────────────────────────────────────────────────
check("FEE/LEV/START/MAX_SCAN/TOPN/디텍터를 어제 판에서 그대로 가져온다",
      (vg.FEE, vg.LEV, vg.START, vg.MAX_SCAN, vg.TOPN, vg.DETMOD)
      == (vs.FEE, vs.LEV, vs.START, vs.MAX_SCAN, vs.TOPN, vs.DETMOD))
check("pot_next·tnum·turnover_rank·signals 는 같은 함수 객체",
      vg.pot_next is vs.pot_next and vg.tnum is vs.tnum
      and vg.turnover_rank is vs.turnover_rank and vg.signals is vs.signals)
check("손절 격자도 어제와 동일", vg.SL_GRID is vs.SL_GRID)

# 포트 규칙이 실거래 cap_margin 과 일치
cap = pe.LIVE_CAPS["tp1_engulfing_1h"]
seq = [0.008, -0.082, 0.018, 0.018, -0.01, 0.028, -0.082, 0.008]
pot = vg.START
for x in seq:
    pot = vg.pot_next(pot, x)
ref = pe.cap_margin(cap, "tp1_engulfing_1h",
                    [dict(pattern="tp1_engulfing_1h", method="D", ret=x) for x in seq])
check("포트 스텝이 실거래 cap_margin 과 8스텝 일치", abs(round(pot, 2) - ref) < 1e-9, (round(pot, 2), ref))

# ── 3. 손익분기·랜덤워크 공식 ──────────────────────────────────────────────────
recs = vg.prepare([("A", base + [bar(100, 104, 99.9, 103, 1)], 0)])
g = vg.grid(recs)
c = next(x for x in g if abs(x["tp"] - 0.01) < 1e-12 and abs(x["sl"] - 0.08) < 1e-12)
check("손익분기 = (SL+FEE)/(TP+SL) — 현행 셀 91.11%", abs(c["breakeven"] - 0.082 / 0.09) < 1e-12, c["breakeven"])
check("랜덤워크 도달률 = SL/(TP+SL) — 현행 셀 88.89%", abs(c["martingale"] - 0.08 / 0.09) < 1e-12)
c2 = next(x for x in g if abs(x["tp"] - 0.02) < 1e-12 and abs(x["sl"] - 0.08) < 1e-12)
check("익절 2%/손절 8% 손익분기 82.00%", abs(c2["breakeven"] - 0.82) < 1e-12, c2["breakeven"])
check("익절 2%/손절 8% 랜덤워크 80.00%", abs(c2["martingale"] - 0.80) < 1e-12)
check("격자 크기 = 익절 5 × 손절 12 = 60셀", len(g) == 60, len(g))

# ── 4. 순차 시뮬 ───────────────────────────────────────────────────────────────
def mk(sym, i0, path):
    rows = [bar(100, 100, 100, 100, i0)] + [bar(100, h, l, 100, i0 + 1 + k)
                                            for k, (h, l) in enumerate(path)]
    return sym, rows, 0


ti1 = vg.TP_GRID.index(0.01)
li8 = vg.SL_GRID.index(0.08)
A = mk("A", 0, [(101.5, 99.9)])                  # 1봉 뒤 익절
B = mk("B", 0, [(100.1, 99.9), (101.5, 99.9)])   # 같은 시각 → A 보유 중이라 버려짐
C = mk("C", 9, [(100.1, 91.0)])                  # 나중 신호, 손절
res = vg.simulate(vg.prepare([A, B, C]), ti1, li8, 0.01, 0.08)
check("보유 중 신호는 버린다", res["n"] == 2 and res["skipped"] == 1, (res["n"], res["skipped"]))
exp = round(70 * (0.01 - vg.FEE) * 3 + 71.68 * (-0.08 - vg.FEE) * 3, 2)
check("계좌손익 = Σ 증거금×ret×3", abs(res["pnl"] - exp) < 0.02, (res["pnl"], exp))
check("손절 뒤 포트 바닥 70", res["pot_final"] == 70.0 and res["pot_pure"] < 70.0,
      (res["pot_final"], res["pot_pure"]))
check("승률·손절수 집계", res["wins"] == 1 and res["stops"] == 1)
check("prepare 는 진입 시각순 정렬", [r["sym"] for r in vg.prepare([C, B, A])][0] in ("A", "B"))

# 같은 신호에서 익절만 넓히면 해소가 늦거나 같다(단조)
long_path = [(100.5, 99.5)] * 3 + [(101.4, 99.5)] + [(102.6, 99.5)]
rec = vg.prepare([mk("D", 0, long_path)])
holds = [vg.simulate(rec, i, li8, tp, 0.08)["avg_hold"] for i, tp in enumerate(vg.TP_GRID)]
check("익절이 넓을수록 보유가 길거나 같다", all(holds[i] <= holds[i + 1] for i in range(len(holds) - 1)), holds)

# ── 5. 랜덤 베이스라인·answer ──────────────────────────────────────────────────
rows_by = {"X": rand_rows(random.Random(1), 80), "Y": rand_rows(random.Random(2), 80)}
r1 = vg.random_entries(rows_by, n=50)
r2 = vg.random_entries(rows_by, n=50)
check("랜덤 진입은 시드 고정 — 재현된다",
      [(x["sym"], x["si"]) for x in r1] == [(x["sym"], x["si"]) for x in r2])
b = vg.baseline(r1, ti1, li8, 0.01, 0.08)
check("베이스라인이 도달률·건당을 낸다", b["n"] == len(r1) and 0.0 <= b["win_rate"] <= 1.0, b)

grid_rows = vg.grid(vg.prepare([A, C]), r1)
a = vg.answer(grid_rows)
check("answer 가 질문 셀(2%/8%)과 현행(1%/8%)을 비교한다",
      a["ask_pnl"] is not None and a["live_pnl"] is not None and "ask_beats_live" in a, a)
check("answer 가 δ 를 익절별로 낸다", a["delta_by_tp"] is not None and len(a["delta_by_tp"]) == 5)
check("δ = 이론 − 랜덤실측",
      all(abs(r["delta"] - (r["martingale"] - r["rand_win"])) < 1e-12
          for r in grid_rows if r.get("delta") is not None))

# ── 6. 동결 상수 ───────────────────────────────────────────────────────────────
check("익절 격자 {1,1.5,2,2.5,3}%", vg.TP_GRID == (0.010, 0.015, 0.020, 0.025, 0.030))
check("현행 셀 1%/8% · 질문 셀 2% 가 격자 안에 있다",
      vg.LIVE_TP in vg.TP_GRID and vg.ASK_TP in vg.TP_GRID and vg.LIVE_SL in vg.SL_GRID)
check("DEPLOY_ON_PASS=False", vg.DEPLOY_ON_PASS is False)
src = open("validate_tp1_grid.py", encoding="utf-8").read()
check("디텍터는 인자 없이 호출(실거래 신호 집합 불변)", "mod.detect(rows)" in open(
    "validate_tp1_stop.py", encoding="utf-8").read() and "vs.signals" in src)
check("랜덤 베이스라인 n·시드 동결", (vg.RAND_N, vg.RAND_SEED) == (3000, 20260921))

print(f"\n{len(fails)} failed")
sys.exit(1 if fails else 0)
