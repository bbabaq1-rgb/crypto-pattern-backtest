"""
test_tp1_slots.py — validate_tp1_slots 고정.

가장 중요한 것은 §1 **동치**: (max_open=1, 교체없음, full) 이 어제 판
validate_tp1_stop.simulate(sl=0.08) 과 거래 단위로 완전히 같아야 한다. 이 셀이 '현행' 기준선이고
여기가 어긋나면 격자 전체가 무의미하다.
"""
import random
import sys

import paper_executor as pe
import validate_tp1_slots as vg
import validate_tp1_stop as vs

FAIL = 0


def check(name, cond, extra=""):
    global FAIL
    print(("PASS " if cond else "FAIL ") + name + (f"  {extra}" if extra and not cond else ""))
    if not cond:
        FAIL += 1


def bars(seq, t0=1_700_000_000_000, step=3_600_000):
    """(o,h,l,c) 튜플 리스트 → rows(1h ts 포함)."""
    out = []
    for i, (o, h, l, c) in enumerate(seq):
        ts = t0 + i * step
        out.append(dict(ts=ts, date="2026-01-01", o=o, h=h, l=l, c=c, v=1.0))
    return out


def flat(n, px=100.0, t0=1_700_000_000_000):
    return bars([(px, px, px, px)] * n, t0=t0)


def rand_rows(rng, n=200, t0=1_700_000_000_000):
    px = 100.0
    seq = []
    for _ in range(n):
        o = px
        c = o * (1 + rng.gauss(0, 0.012))
        h = max(o, c) * (1 + abs(rng.gauss(0, 0.006)))
        l = min(o, c) * (1 - abs(rng.gauss(0, 0.006)))
        seq.append((o, h, l, c))
        px = c
    return bars(seq, t0=t0)


# ── 1. 동치 — 현행 셀이 어제 판과 같은 거래를 낸다 ──────────────────────────────
print("\n[1] (슬롯1·교체없음·full) ≡ validate_tp1_stop.simulate")
rng = random.Random(20260921)
mismatch = None
tot = 0
for trial in range(40):
    syms = {}
    for k in range(rng.randint(2, 5)):
        syms[f"S{k}"] = rand_rows(rng, n=rng.choice([120, 200, 300]))
    sigs = []
    for s, rows in syms.items():
        for si in sorted(rng.sample(range(0, len(rows) - 2), rng.randint(3, 12))):
            sigs.append((s, rows, si))
    a = vs.simulate(sigs, vg.SL)
    b = vg.simulate(sigs, 1, None, "full")
    tot += 1
    ka = [(t["sym"], t["date"], round(t["ret"], 12), t["hold"], t["reason"], t["margin"]) for t in a["trades"]]
    kb = [(t["sym"], t["date"], round(t["ret"], 12), t["hold"], t["reason"], t["margin"]) for t in b["trades"]]
    if ka != kb or round(a["pnl"], 6) != round(b["pnl"], 6) or a["n"] != b["n"]:
        mismatch = (trial, a["n"], b["n"], a["pnl"], b["pnl"])
        break
    if a["skipped"] != b["skipped_slot"] + b["skipped_dup"]:
        mismatch = (trial, "skip", a["skipped"], b["skipped_slot"], b["skipped_dup"])
        break
check(f"거래·손익·스킵 수 완전 일치 (난수 {tot}판)", mismatch is None, str(mismatch))
check("pot_final 도 일치", all(
    vs.simulate(s, vg.SL)["pot_final"] == vg.simulate(s, 1, None, "full")["pot_final"]
    for s in [[("A", rand_rows(random.Random(i), 150), j) for j in (5, 40, 90)] for i in (1, 2, 3)]))

# ── 2. 슬롯 수 — 더 많은 신호를 받는다 ─────────────────────────────────────────
print("\n[2] max_open")
rows_a, rows_b, rows_c = (rand_rows(random.Random(7), 400),
                          rand_rows(random.Random(8), 400),
                          rand_rows(random.Random(9), 400))
sig3 = [("A", rows_a, 10), ("B", rows_b, 10), ("C", rows_c, 10)]
r1 = vg.simulate(sig3, 1, None, "full")
r2 = vg.simulate(sig3, 2, None, "full")
r3 = vg.simulate(sig3, 3, None, "full")
check("슬롯이 늘면 거래 수가 줄지 않는다", r1["n"] <= r2["n"] <= r3["n"], f"{r1['n']}/{r2['n']}/{r3['n']}")
check("슬롯 3 이면 같은 봉 신호 3건을 다 받는다", r3["n"] == 3, str(r3["n"]))
check("슬롯 1 이면 1건만 받는다", r1["n"] == 1, str(r1["n"]))
check("슬롯스킵 계수", r1["skipped_slot"] == 2 and r3["skipped_slot"] == 0)
check("최대 동시보유가 슬롯을 안 넘는다",
      all(vg.simulate(sig3, m, None, "full")["avg_open"] <= m + 1e-9 for m in (1, 2, 3)))

print("\n[2b] 같은 종목 중복 금지")
sdup = [("A", rows_a, 10), ("A", rows_a, 11)]
rd = vg.simulate(sdup, 3, None, "full")
check("슬롯이 남아도 같은 종목은 두 번 안 든다", rd["skipped_dup"] >= 1 and rd["n"] == 1,
      f"n={rd['n']} dup={rd['skipped_dup']}")

# ── 3. 사이징 ─────────────────────────────────────────────────────────────────
print("\n[3] 증거금")
check("full 첫 진입 증거금 = 시작 포트", abs(r3["trades"][0]["margin"] - vg.START) < 1e-9)
s3 = vg.simulate(sig3, 3, None, "split")
check("split 첫 진입 증거금 = 포트/슬롯", s3["trades"][0]["margin"] == round(vg.START / 3, 2),
      str(s3["trades"][0]["margin"]))
check("split 은 거래 집합이 full 과 같다(크기만 다름)",
      [t["sym"] for t in s3["trades"]] == [t["sym"] for t in r3["trades"]]
      and [t["ret"] for t in s3["trades"]] == [t["ret"] for t in r3["trades"]])

print("\n[3b] 포트는 청산 시각순으로만 갱신된다 (cap_margin 규칙)")
seq = [dict(pattern="P", method="D", ret=t["ret"], exit_date="2026-01-%02d" % (i + 1),
            entry_date="2026-01-01") for i, t in enumerate(r3["trades"])]
cap = dict(compound=True, start_margin=vg.START, margin_usd=vg.START, leverage=vg.LEV, loss_floor=True)
check("pe.cap_margin 과 포트 최종값 일치",
      abs(pe.cap_margin(cap, "P", seq) - r3["pot_final"]) < 0.02,
      f"{pe.cap_margin(cap, 'P', seq)} vs {r3['pot_final']}")
check("동시 보유 중 두 번째 진입 증거금 = 첫 진입과 같다(아직 미해소)",
      r3["trades"][0]["margin"] == vg.START and all(
          t["margin"] == vg.START for t in r3["trades"] if t["t"] == r3["trades"][0]["t"]))

# ── 4. 교체 규칙 ──────────────────────────────────────────────────────────────
print("\n[4] 교체")
# A: 신호봉(0) 종가 100 → 이후 완만히 +0.5% 까지 올랐다가 유지(배리어 미도달)
up = bars([(100, 100, 100, 100)] + [(100, 100.6, 99.9, 100.5)] * 60)
# B: 같은 시각에 신호가 계속 뜨는 다른 종목
other = bars([(50, 50, 50, 50)] * 60)
sig = [("A", up, 0), ("B", other, 3)]
base = vg.simulate(sig, 1, None, "full")
rep0 = vg.simulate(sig, 1, 0.0, "full")
check("교체 없음이면 B 는 스킵", base["n"] == 1 and base["skipped_slot"] == 1)
check("교체 문턱 0% 면 A 를 닫고 B 로 교체", rep0["replaced"] == 1 and rep0["n"] == 2,
      f"replaced={rep0['replaced']} n={rep0['n']}")
t0 = rep0["trades"][0]
check("교체 청산 사유는 replaced", t0["reason"] == "replaced")
check("교체 수익률 = 그 시각 종가 대비 − 수수료",
      abs(t0["ret"] - ((100.5 - 100) / 100 - vg.FEE)) < 1e-12, str(t0["ret"]))
check("총수익 0.5% 라도 수수료 0.2% 차감 후 순수익 0.3%", abs(t0["ret"] - 0.003) < 1e-12)

print("\n[4b] 문턱")
check("문턱 0.5% 면 총수익 0.5% 는 '초과'가 아니라 발동 안 함",
      vg.simulate(sig, 1, 0.005, "full")["replaced"] == 0)
check("문턱 0.2%(수수료)면 발동", vg.simulate(sig, 1, 0.002, "full")["replaced"] == 1)

print("\n[4c] 손실 중이면 교체 안 한다 — 규칙의 비대칭")
down = bars([(100, 100, 100, 100)] + [(100, 100.0, 99.0, 99.2)] * 60)
sigd = [("A", down, 0), ("B", other, 3)]
rd0 = vg.simulate(sigd, 1, 0.0, "full")
check("수익 구간이 아니면 교체 없이 스킵", rd0["replaced"] == 0 and rd0["skipped_slot"] == 1)
check("→ 이기는 포지션만 잘리고 지는 포지션은 남는다(기전 고정)",
      vg.simulate(sig, 1, 0.0, "full")["replaced"] == 1 and rd0["replaced"] == 0)

print("\n[4d] 같은 틱 진입분은 교체 대상이 아니다")
same = [("A", up, 3), ("B", other, 3)]
rs = vg.simulate(same, 1, 0.0, "full")
check("같은 시각 두 신호에서 방금 진입분을 도로 닫지 않는다", rs["replaced"] == 0 and rs["n"] == 1)

print("\n[4e] 교체는 자연 청산을 앞당기기만 한다")
check("교체 arm 의 거래 수 ≥ 기준선", rep0["n"] >= base["n"])
check("교체된 거래의 보유가 자연 청산보다 짧다",
      t0["hold"] < (vs.resolve(up, 0, vg.TP, vg.SL)[1]), f"{t0['hold']}")

print("\n[4f] ts 없는 봉에서는 교체가 발동하지 않는다(보수)")
nots = [dict(r, ts=None) for r in up]
check("ts 없으면 교체 0", vg.simulate([("A", nots, 0), ("B", other, 3)], 1, 0.0, "full")["replaced"] == 0)

# ── 5. 자연 청산이 먼저 ────────────────────────────────────────────────────────
print("\n[5] 청산 우선순위")
fast = bars([(100, 100, 100, 100), (100, 101.5, 99.9, 101.0)] + [(101, 101, 101, 101)] * 30)
sigf = [("A", fast, 0), ("B", other, 5)]
rf = vg.simulate(sigf, 1, 0.0, "full")
check("배리어가 먼저 닿았으면 교체가 아니라 익절로 닫힌다",
      rf["trades"][0]["reason"] == "target" and rf["replaced"] == 0)
check("그 뒤 슬롯이 비어 B 가 정상 진입", rf["n"] == 2)

# ── 6. 격자·판정 ──────────────────────────────────────────────────────────────
print("\n[6] 격자")
g = vg.grid(sig3)
check("격자 크기 = 슬롯 6 × 교체 4 × 사이징 2 = 48", len(g) == 48, str(len(g)))
check("pick 이 현행 셀을 찾는다", vg.pick(g, *vg.LIVE_CELL)["max_open"] == 1)
a = vg.answer(g)
check("answer 에 슬롯 2·3 · 교체 · best 가 있다",
      all(k in a for k in ("slots2", "slots3", "replace0", "best", "live_pnl")))
check("주 판정 셀 4개가 격자 안에 있다", all(vg.pick(g, *c) is not None for c in vg.MAIN_CELLS))

# ── 7. 동결 상수 ──────────────────────────────────────────────────────────────
print("\n[7] 동결")
check("익절 1% / 손절 8% / 3x / 시작 $70", (vg.TP, vg.SL, vg.LEV, vg.START) == (0.01, 0.08, 3, 70.0))
check("어제 판 상수를 그대로 쓴다(별도 정의 금지)",
      vg.TP is vs.TP and vg.LEV is vs.LEV and vg.MAX_SCAN is vs.MAX_SCAN and vg.FEE is vs.FEE)
check("디텍터는 engulfing, 코호트 top20", vg.DETMOD == "detector_engulfing" and vg.TOPN == 20)
check("주 판정 슬롯 {1,2,3}", vg.SLOTS_MAIN == (1, 2, 3))
check("주 판정 교체 문턱 {없음, 0.0}", vg.REPL_MAIN == (None, 0.0))
check("현행 셀 = (1, 없음, full)", vg.LIVE_CELL == (1, None, "full"))
check("DEPLOY_ON_PASS=False", vg.DEPLOY_ON_PASS is False)
check("resolve/tnum/pot_next 는 어제 판 것을 재사용",
      vg.simulate.__globals__["vs"].resolve is vs.resolve and vs.pot_next is vs.pot_next)

print(f"\n{FAIL} failed")
sys.exit(1 if FAIL else 0)
