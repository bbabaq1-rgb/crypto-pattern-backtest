"""
test_engulf_tf.py — engulfing TF 재시험(1h/4h/1w) 사전 등록 고정 (2026-09-09).

지키는 성질:
  · 동결 파라미터(TF·방향·코호트·레짐·홀드아웃·Holm·마찰)가 결과를 보고 바뀌지 않는다
  · **디텍터를 건드리지 않았다** — 배포된 1d engulfing 신호 집합 불변
  · DEPLOY_ON_PASS=False 이고 universe/scheduler 어디에도 등재돼 있지 않다
  · PIT 풀 인덱스가 코호트·레짐 조건을 실제로 지킨다
  · Holm 보정의 수학적 성질
"""
import inspect
import json

import detector_engulfing as eng_long
import detector_engulfing_short as eng_short
import validate_engulf_tf as E
import validate_revival as vr

fails = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


# ── 동결 파라미터 ────────────────────────────────────────────────────────────
check("주 판정 TF 는 1h/4h/1w (사용자 지정)", E.TFS == ("1h", "4h", "1w"), E.TFS)
check("방향 두 갈래", E.DIRECTIONS == ("long", "short"), E.DIRECTIONS)
check("코호트 core20(실거래 engulfing top20 의 PIT 판) · 레짐 ALL",
      (E.COHORT, E.REGIME) == ("core20", "ALL"), (E.COHORT, E.REGIME))
check("홀드아웃 — 1h 90 / 4h 365 / 1w 730일",
      E.HOLDOUT_BY_TF["1h"] == 90 and E.HOLDOUT_BY_TF["4h"] == 365
      and E.HOLDOUT_BY_TF["1w"] == 730, E.HOLDOUT_BY_TF)
check("1d 는 참조 셀이지 판정 가족이 아니다", E.REF_TF == "1d" and "1d" not in E.TFS)
check("Holm 가족 크기 m=6 (TF 3 x 방향 2)", len(E.TFS) * len(E.DIRECTIONS) == 6)
check("D5 마찰은 왕복 0.4% (캐스케이드 내성 한계와 같은 값)", E.FRICTION == 0.004, E.FRICTION)
check("DEPLOY_ON_PASS=False (관찰 기간 — 통과해도 반영 없음)", E.DEPLOY_ON_PASS is False)

# ── 디텍터 불변 (배포 1d 보호) ────────────────────────────────────────────────
check("롱은 detector_engulfing.detect 를 그대로 쓴다", E.DETECT["long"] is eng_long.detect)
check("숏은 detector_engulfing_short.detect 를 그대로 쓴다", E.DETECT["short"] is eng_short.detect)
for nm, mod in (("engulfing", eng_long), ("engulfing_short", eng_short)):
    sig = inspect.signature(mod.detect)
    check(f"{nm}.detect 인자는 rows 하나 — 이 시험이 파라미터를 넣지 않았다",
          list(sig.parameters) == ["rows"], list(sig.parameters))
src = inspect.getsource(E)
check("시험 코드가 detect 에 추가 인자를 넘기지 않는다",
      "DETECT[d](rows" not in src and "detect(rows," not in src)

# 실제 신호 집합이 바뀌지 않았는지 — 합성 봉으로 확인(디텍터 자체를 호출)
rows = []
px = 100.0
for i in range(120):
    up = (i % 7) in (3, 4)
    o = px
    c = px * (1.03 if up else 0.985)
    rows.append(dict(date=f"2024-{1 + i // 28:02d}-{1 + i % 28:02d}", ts=i * 86400000,
                     o=o, h=max(o, c) * 1.005, l=min(o, c) * 0.995, c=c, v=1000 + i))
    px = c
before_l, before_s = eng_long.detect(rows), eng_short.detect(rows)
import validate_engulf_tf as _reimport  # noqa: F401  (모듈 로드가 부작용을 내지 않는지)
check("모듈 로드가 롱 신호 집합을 바꾸지 않는다", eng_long.detect(rows) == before_l)
check("모듈 로드가 숏 신호 집합을 바꾸지 않는다", eng_short.detect(rows) == before_s)

# ── 등재되지 않았다 ─────────────────────────────────────────────────────────
uni = json.load(open("universe.json", encoding="utf-8"))
uni_txt = json.dumps(uni, ensure_ascii=False)
for key in ("engulfing_4h", "engulfing_1w", "engulfing_1h_adopted"):
    check(f"universe 에 {key} 없음", key not in uni_txt)
sched = open("scheduler.py", encoding="utf-8").read()
check("스케줄러가 engulfing 을 1d 외 TF 로 돌리지 않는다",
      "engulfing_4h" not in sched and "engulfing_1w" not in sched)
reg = json.load(open("registry.json", encoding="utf-8"))
check("registry 에 사전 등록 기록", "engulf_tf_prereg_2026_09_09" in reg)

# ── Holm ────────────────────────────────────────────────────────────────────
h = E.holm({"a": 0.01, "b": 0.02, "c": 0.30})
check("Holm: 가장 작은 p 에 m 배", abs(h["a"] - 0.03) < 1e-9, h)
check("Holm: 단조 비감소", h["a"] <= h["b"] <= h["c"], h)
check("Holm: 1.0 상한", E.holm({"a": 0.6, "b": 0.7})["b"] <= 1.0)
check("Holm: 단일 검정은 그대로", abs(E.holm({"a": 0.04})["a"] - 0.04) < 1e-9)
check("Holm: None 은 가족에서 빠진다", "b" not in E.holm({"a": 0.01, "b": None}))

# ── PIT 풀 인덱스 ───────────────────────────────────────────────────────────
rows_by = {
    "AAA": [dict(date=f"2024-01-{d:02d}", ts=d, o=1, h=1, l=1, c=1, v=1) for d in range(1, 29)] * 4,
    "BBB": [dict(date=f"2024-01-{d:02d}", ts=d, o=1, h=1, l=1, c=1, v=1) for d in range(1, 29)] * 4,
}
pm = {"2024-01": {"AAA": 1, "BBB": 99}}          # AAA 만 core20
regmap = {f"2024-01-{d:02d}": ("bull_btc" if d % 2 else "bear") for d in range(1, 29)}
idx = E.pit_idx(rows_by, regmap, pm, "core20", "ALL", "1d")
check("PIT 풀은 코호트 밖 코인을 넣지 않는다", idx and all(s == "AAA" for s, _ in idx),
      sorted({s for s, _ in idx}))
idx_g = E.pit_idx(rows_by, regmap, pm, "core20", "bear", "1d")
check("PIT 풀은 레짐 조건을 지킨다",
      idx_g and all(regmap[rows_by[s][i]["date"]] == "bear" for s, i in idx_g))
check("레짐 조건이 표본을 줄인다", len(idx_g) < len(idx), (len(idx_g), len(idx)))
check("풀 상한은 vr.POOL_CAP 을 따른다", len(E.pit_idx(rows_by, regmap, pm, "core20", "ALL", "1d",
                                                    seed=1)) <= vr.POOL_CAP)
check("코호트 밖만 있으면 빈 풀", E.pit_idx({"BBB": rows_by["BBB"]}, regmap, pm, "core20", "ALL", "1d") == [])

# ── 마찰 스트레스 ────────────────────────────────────────────────────────────
check("D5 는 건당에서 왕복 마찰을 뺀다",
      abs(E.stressed([dict(ret=0.01), dict(ret=0.03)]) - (0.02 - 0.004)) < 1e-12)
check("D5 빈 표본은 None", E.stressed([]) is None)

# ── confirm 연동 ────────────────────────────────────────────────────────────
check("vr.confirm 이 찾는 키로 셀을 넘긴다(코호트 이름과 무관)",
      "vr.CONFIRM_COHORT: dict(gate=rec, sigs=sigs)" in src)
check("C2b(train 자체 게이트 + train n >= holdout n/2)가 판정에 들어 있다",
      "C2b" in src and "tr_rec" in src and 'ho["n"] // 2' in src)
check("판정 우선순위 — INCONCLUSIVE 는 C1·C2b·C3 통과 + holdout 얇을 때만",
      'c1 and c2b and conf["c3_equity"] and ho["n"] < vr.HOLDOUT_MIN_N' in src)

# ── 워크플로 ────────────────────────────────────────────────────────────────
wf = open(".github/workflows/engulf_tf.yml", encoding="utf-8").read()
check("워크플로가 로직 테스트를 먼저 돌린다", "python test_engulf_tf.py" in wf)
check("워크플로가 장기 이력(data-long)을 받는다", "data-long" in wf)
check("tests.yml 등재", "test_engulf_tf.py" in open(".github/workflows/tests.yml", encoding="utf-8").read())

print(f"\n{len(fails)} failed")
raise SystemExit(1 if fails else 0)
