"""
validate_regime_split 로직 검증 (합성 데이터, 네트워크 없음).

  - gate_cell: 3-튜플(date, ret, direction) 언패킹, 게이트 5조건, OOS 4분위
  - 베이스라인이 '같은 레짐·코호트 무작위 진입'이라 레짐 자체의 방향성이 상쇄되는가
    (상승 추세 합성 데이터에서 아무 봉이나 잡아도 평균이 양수 → 그만큼 boot_p 가 커진다)
  - turnover_rank 가 30일 거래대금 내림차순
실행: python test_regime_split.py
"""
import random
import sys

import detlib
import validate_regime_split as v

fails = []


def check(n, c, d=""):
    print(("PASS " if c else "FAIL ") + n + ("" if c else f" — {d}"))
    c or fails.append(n)


def rows_of(n, seed, drift=0.0, px0=100.0):
    random.seed(seed)
    px, out = px0, []
    from datetime import date, timedelta
    for i in range(n):
        nxt = px * (1 + drift + random.gauss(0, 0.01))
        out.append(dict(ts=i, date=(date(2024, 1, 1) + timedelta(days=i)).isoformat(),
                        o=px, h=max(px, nxt) * 1.005, l=min(px, nxt) * 0.995, c=nxt, v=100.0 + i))
        px = nxt
    return out


# ── 1. gate_cell 언패킹·게이트 ────────────────────────────────────────────────
sigs = [("2026-01-%02d" % (i + 1), 0.12 if i % 4 else -0.10, "long") for i in range(40)]
rec = v.gate_cell("t1", sigs, [], verbose=False)
check("3-튜플 sigs 를 받는다(회귀: too many values to unpack)", rec["n"] == 40)
check("평균·중앙값 계산", rec["mean"] > 0 and rec["median"] > 0, rec)
check("풀 없으면 boot_p=1 → REJECT", rec["boot_p"] == 1.0 and rec["verdict"] == "REJECTED", rec)
few = v.gate_cell("t2", sigs[:5], [], verbose=False)
check("n<20 이면 사유에 표기", "n<20" in few["reason"], few)

# ── 2. 베이스라인이 레짐 방향성을 상쇄하는가 ────────────────────────────────
up = rows_of(400, 1, drift=0.004)          # 상승 추세
pool = [(up, i) for i in range(len(up) - detlib.LABEL_WINDOW - 1)]
# '아무 봉이나' 잡은 신호 40개 — 패턴 엣지가 없는데 상승장이라 평균은 양수
rng = random.Random(7)
idx = rng.sample(range(len(pool)), 40)
naive = [(up[i]["date"], detlib.outcome(up, i, "long")[1], "long") for i in idx]
rec_naive = v.gate_cell("naive", naive, pool, verbose=False)
check("상승장 무작위 진입은 평균 양수", rec_naive["mean"] > 0, rec_naive["mean"])
check("같은 레짐 베이스라인이면 엣지 없음으로 판정(boot_p 큼)", rec_naive["boot_p"] > 0.05, rec_naive["boot_p"])
# 진짜 엣지(상위 수익 봉만 고름)는 통과 방향으로 움직인다
best = sorted(range(len(pool)), key=lambda i: -detlib.outcome(up, i, "long")[1])[:40]
edge = [(up[i]["date"], detlib.outcome(up, i, "long")[1], "long") for i in sorted(best)]
rec_edge = v.gate_cell("edge", edge, pool, verbose=False)
check("실제 엣지가 있으면 boot_p 작아짐", rec_edge["boot_p"] < rec_naive["boot_p"], (rec_edge["boot_p"], rec_naive["boot_p"]))
# 레짐 자체 수익(베이스라인 평균)과 패턴 엣지(차이)를 분리해 보고하는가
check("베이스라인 평균 보고", rec_naive["base_mean"] is not None and rec_naive["base_mean"] > 0, rec_naive["base_mean"])
check("무작위 진입의 엣지는 0 근처", abs(rec_naive["edge_vs_regime"]) < abs(rec_naive["mean"]), 
      (rec_naive["edge_vs_regime"], rec_naive["mean"]))
check("실제 엣지 셀은 엣지가 크게 양수", rec_edge["edge_vs_regime"] > rec_naive["edge_vs_regime"],
      (rec_edge["edge_vs_regime"], rec_naive["edge_vs_regime"]))
check("연도별 분해 존재", isinstance(rec_naive.get("by_year"), dict) and rec_naive["by_year"], rec_naive.get("by_year"))

# ── 3. turnover_rank ────────────────────────────────────────────────────────
r = v.turnover_rank({"A": rows_of(60, 2, px0=10.0), "B": rows_of(60, 3, px0=1000.0), "C": rows_of(20, 4)})
check("거래대금 내림차순, 35봉 미만 제외", r == ["B", "A"], r)

# ── 4. 실거래 코드 비의존 ────────────────────────────────────────────────────
for f in ("paper_executor.py", "scheduler.py", "exchange.py"):
    src = open(f, encoding="utf-8").read()
    check(f"{f} 는 validate_regime_split 를 import 하지 않음", "validate_regime_split" not in src)

print(f"\n{len(fails)} failed")
sys.exit(1 if fails else 0)
