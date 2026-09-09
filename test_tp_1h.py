"""
test_tp_1h.py — 1h 재측정 + 넓은 손절 + 레버리지 사전 등록 고정 (2026-09-09).

지키는 성질:
  · 동결 격자·주 판정 4셀·비용·스캔한도가 결과를 보고 바뀌지 않는다
  · **필요 리프트 = 수수료/(익절+손절)** — 넓힐수록 작아진다(사용자 질문의 산술 근거)
  · 배리어 규칙이 인과적이고, 27셀 동시 해소가 셀별 계산과 **완전히 같다**
  · 동률은 손절 우선(보수), 낙관 arm 은 익절 — 둘이 진실을 가둔다
  · **레버리지는 건당 수익률·승률을 바꾸지 않는다**(판정 무관, P2 에만 나타난다)
  · 무손절 셀의 ②③ N/A 처리가 사전 규정대로 동작한다
  · DEPLOY_ON_PASS=False 이고 실거래 경로 어디에도 등재돼 있지 않다
"""
import inspect
import json

import validate_tp_1h as T

fails = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


# ── 동결 ────────────────────────────────────────────────────────────────────
check("주 판정 TF 는 1h", T.PRIMARY_TF == "1h" and T.TFS == ("1h", "1d"), T.TFS)
check("익절 격자 1/2/3%", T.TP_LEVELS == (0.01, 0.02, 0.03), T.TP_LEVELS)
check("손절 격자에 **3% 와 8% 초과(12/16/20)와 무손절** 이 있다",
      T.SL_LEVELS == (0.01, 0.02, 0.03, 0.04, 0.08, 0.12, 0.16, 0.20, None), T.SL_LEVELS)
check("27셀", len(T.CELLS) == 27, len(T.CELLS))
check("주 판정 4셀 = 사용자 지목 (1%/3%, 1%/8%, 1%/20%, 1%/무손절)",
      T.PRIMARY_ARMS == ["T1S3", "T1S8", "T1S20", "T1SX"], T.PRIMARY_ARMS)
check("Holm 가족 크기 = 주 판정 셀 수", len(T.PRIMARY) == 4)
check("무손절 셀 이름은 T1SX 이고 손절이 None", T.CELL_OF["T1SX"] == (0.01, None))
check("동결 왕복 수수료 0.2%", T.FEE == 0.002, T.FEE)
check("마찰 스트레스 0.4%", T.FRICTION == 0.004, T.FRICTION)
check("스캔한도 1h 2000 / 1d 250", T.MAX_SCAN_BY_TF == {"1h": 2000, "1d": 250})
check("홀드아웃 1h 90 / 1d 365", T.HOLDOUT_BY_TF == {"1h": 90, "1d": 365})
check("P2 레버리지 스윕 1/2/3x", T.POT_LEVS == (1, 2, 3), T.POT_LEVS)
check("DEPLOY_ON_PASS=False", T.DEPLOY_ON_PASS is False)
check("패턴은 TF 무관 캔들 6종, triple_bottom(주봉) 제외",
      len(T.PATS) == 6 and all(lb != "triple_bottom" for lb, _, _ in T.PATS))

# ── 산술: 필요 리프트 ────────────────────────────────────────────────────────
check("필요 리프트 = 손익분기 − 랜덤워크 = FEE/(TP+SL)",
      all(abs(T.need_lift(tp, sl) - (T.breakeven_win(tp, sl) - T.rw_hit(tp, sl))) < 1e-12
          for tp, sl in T.CELLS if sl is not None))
check("1%/3% 는 +5.00%p, 1%/8% 는 +2.22%p, 1%/20% 는 +0.95%p",
      abs(T.need_lift(.01, .03) - 0.05) < 1e-12
      and abs(T.need_lift(.01, .08) - 0.002 / 0.09) < 1e-12
      and abs(T.need_lift(.01, .20) - 0.002 / 0.21) < 1e-12)
check("**손절을 넓히면 필요 리프트가 단조 감소** (사용자 질문의 핵심 산술)",
      all(T.need_lift(.01, a) > T.need_lift(.01, b)
          for a, b in zip((.01, .02, .03, .04, .08, .12, .16), (.02, .03, .04, .08, .12, .16, .20))))
check("랜덤워크 도달률에서 수수료 전 기대값이 정확히 0",
      all(abs(T.rw_hit(tp, sl) * tp - (1 - T.rw_hit(tp, sl)) * sl) < 1e-12
          for tp, sl in T.CELLS if sl is not None))
check("무손절은 기준값이 정의되지 않는다",
      T.rw_hit(.01, None) is None and T.breakeven_win(.01, None) is None
      and T.need_lift(.01, None) is None)


# ── 배리어 규칙 ─────────────────────────────────────────────────────────────
def bar(o, h, l, c, d="2024-01-01", ts=0):
    return dict(date=d, ts=ts, o=o, h=h, l=l, c=c, v=1)


flat = [bar(100, 100, 100, 100, f"2024-01-{i+1:02d}", i) for i in range(3)]
cells = [(0.01, 0.08), (0.01, None), (0.03, 0.20)]

r = T.outcomes_all(flat + [bar(100, 101.5, 99.5, 101, "2024-01-04", 3)], 2, "long",
                   cells, 50)
check("롱 +1% 고가 도달 → 익절, 수익 = tp − 수수료",
      r[0][2] == "target" and abs(r[0][0] - (0.01 - T.FEE)) < 1e-12 and r[0][1] == 1, r[0])
r = T.outcomes_all(flat + [bar(100, 100.5, 91.0, 92, "2024-01-04", 3)], 2, "long", cells, 50)
check("롱 −8% 저가 도달 → 손절", r[0][2] == "stop" and abs(r[0][0] - (-0.08 - T.FEE)) < 1e-12)
check("같은 봉에서 무손절 셀은 손절이 없어 계속 간다", r[1][2] == "open")
r = T.outcomes_all(flat + [bar(100, 105, 91.0, 95, "2024-01-04", 3)], 2, "long", cells, 50)
check("동률이면 **손절 우선**(보수적)", r[0][2] == "stop" and r[0][3] is True, r[0])
ro = T.outcomes_all(flat + [bar(100, 105, 91.0, 95, "2024-01-04", 3)], 2, "long", cells, 50,
                    optimistic=True)
check("낙관 arm 은 같은 동률을 익절로 돌린다", ro[0][2] == "target" and ro[0][3] is True, ro[0])
check("동률이 아니면 낙관·보수가 같다",
      T.outcomes_all(flat + [bar(100, 101.5, 99.5, 101, "2024-01-04", 3)], 2, "long",
                     cells, 50, optimistic=True)[0][2] == "target")
long_flat = flat + [bar(100, 100.2, 99.8, 100, f"2024-02-{i+1:02d}", 10 + i) for i in range(5)]
r = T.outcomes_all(long_flat, 2, "long", cells, 50)
check("어느 배리어에도 안 닿으면 마지막 봉 시가로 'open'",
      r[0][2] == "open" and r[0][1] == len(long_flat) - 1 - 2, r[0])
r = T.outcomes_all(flat + [bar(100, 100.5, 98.5, 99, "2024-01-04", 3)], 2, "short", cells, 50)
check("숏 −1% 저가 도달 → 익절", r[0][2] == "target")
r = T.outcomes_all(flat + [bar(100, 109, 100, 108, "2024-01-04", 3)], 2, "short", cells, 50)
check("숏 +8% 고가 도달 → 손절", r[0][2] == "stop")

spike = flat[:2] + [bar(100, 130, 70, 100, "2024-01-03", 2), bar(100, 100, 100, 100, "2024-01-04", 3)]
check("진입 봉의 고가·저가는 판정에 쓰지 않는다(룩어헤드 없음)",
      T.outcomes_all(spike, 2, "long", cells, 50)[0][2] == "open")
src = inspect.getsource(T.crossings) + inspect.getsource(T._resolve)
check("스캔은 si+1 부터(진입 봉 제외)", "range(si + 1" in src)
check("배리어 기준가는 신호봉 **종가**", 'base = rows[si]["c"]' in src)
check("레짐·반대신호·시간 청산이 규칙에 없다",
      "REGMAP" not in src and "opp_set" not in src)

# 문턱 교차표 최적화 == **독립 구현**(셀마다 봉을 처음부터 다시 훑는 소박한 판)
# 같은 코드 경로끼리 비교하면 최적화 검증이 안 되므로 여기서 따로 짠다.
def naive(rows, si, direction, tp, sl, max_scan, optimistic=False):
    base = rows[si]["c"]
    is_long = direction == "long"
    end = min(si + max_scan, len(rows) - 1)
    for j in range(si + 1, end + 1):
        r = rows[j]
        if is_long:
            up, dn = (r["h"] - base) / base, (base - r["l"]) / base
        else:
            up, dn = (base - r["l"]) / base, (r["h"] - base) / base
        hit_t = up >= tp
        hit_s = sl is not None and dn >= sl
        if not (hit_t or hit_s):
            continue
        tie = hit_t and hit_s
        win = hit_t if not tie else bool(optimistic)
        return ((tp - T.FEE) if win else (-sl - T.FEE), j - si,
                "target" if win else "stop", tie)
    px = rows[end]["o"]
    rr = (px - base) / base if is_long else (base - px) / base
    return rr - T.FEE, end - si, "open", False


import random as _r
_rng = _r.Random(3)
px, rows = 100.0, []
for i in range(400):
    o = px
    c = px * (1 + _rng.uniform(-0.06, 0.06))
    rows.append(bar(o, max(o, c) * (1 + _rng.uniform(0, .05)),
                    min(o, c) * (1 - _rng.uniform(0, .05)), c,
                    f"2024-{1+i//28:02d}-{1+i%28:02d}", i))
    px = c
mismatch, n_cmp, n_tie = None, 0, 0
for direction in ("long", "short"):
    for si in (30, 60, 90, 120, 200, 310):
        for opt in (False, True):
            got = T.outcomes_all(rows, si, direction, T.CELLS, 200, optimistic=opt)
            for ci, (tp, sl) in enumerate(T.CELLS):
                want = naive(rows, si, direction, tp, sl, 200, optimistic=opt)
                n_cmp += 1
                n_tie += 1 if want[3] else 0
                if got[ci] != want and mismatch is None:
                    mismatch = (direction, si, opt, tp, sl, got[ci], want)
check(f"문턱 교차표가 독립 구현과 완전히 일치 ({n_cmp}셀 비교, 동률 {n_tie}건)",
      mismatch is None, mismatch)
check("비교 표본에 동률이 실제로 들어 있다(빈 검사가 아님)", n_tie > 0, n_tie)

# ── 레버리지 무관성 ─────────────────────────────────────────────────────────
vsrc = inspect.getsource(T.verdict)
check("판정 함수가 레버리지를 전혀 보지 않는다",
      "lev" not in vsrc and "POT" not in vsrc)
osrc = inspect.getsource(T.crossings) + inspect.getsource(T._resolve)
check("배리어 규칙도 레버리지를 보지 않는다 — 건당 수익률은 가격 수익률",
      "lev" not in osrc)
tr = [(1.0, 2.0, 0.01), (3.0, 4.0, 0.01)]
p1, p3 = T.pot_curve(tr, 1, 100.0), T.pot_curve(tr, 3, 100.0)
check("P2 에서만 레버리지가 나타난다 — 1x 는 1.01^2, 3x 는 1.03^2",
      abs(p1["mult"] - 1.01 ** 2) < 1e-9 and abs(p3["mult"] - 1.03 ** 2) < 1e-9, (p1, p3))
check("P2 는 한 번에 한 포지션 — 열려 있는 동안 온 신호는 버린다",
      T.pot_curve([(1.0, 9.0, 0.01), (2.0, 3.0, 0.5)], 1)["taken"] == 1)
check("P2 파산 하한 0", T.pot_curve([(1.0, 2.0, -0.5)], 3, 100.0)["final"] == 0.0)
check("레버리지 1x 도 건당이 음수면 우하향",
      T.pot_curve([(1.0, 2.0, -0.01), (3.0, 4.0, -0.01)], 1, 100.0)["mult"] < 1.0)

# ── 무손절 N/A 처리 ─────────────────────────────────────────────────────────
tr_s = dict(mean=0.01, winrate=0.5, mean_stressed=0.008)
hv = dict(m1=0.01, m2=0.01)
v = T.verdict("T1SX", tr_s, dict(mean=0.01), 0.4, hv, 0.01)
check("무손절 셀은 ②③ 이 N/A 로 통과 처리되고 플래그가 선다",
      v["na_barrier_ref"] and v["c2_breakeven"] and v["c3_lift"] and v["pass_"], v)
v8 = T.verdict("T1S8", dict(mean=0.01, winrate=0.5, mean_stressed=0.008),
               dict(mean=0.01), 0.4, hv, 0.01)
check("손절 있는 셀은 ②③ 이 실제로 평가된다 — 승률 50% 는 손익분기 91.11% 미달",
      not v8["c2_breakeven"] and not v8["c3_lift"] and not v8["pass_"], v8)
check("④는 엣지와 Holm p 를 둘 다 요구한다",
      not T.verdict("T1S8", dict(mean=0.01, winrate=0.95, mean_stressed=0.008),
                    dict(mean=0.01), 0.90, hv, 0.20)["c4_edge"])
check("PASS 는 7개 전부 만족일 때만",
      "c1 and c2 and c3 and c4 and c5 and c6 and c7" in vsrc)

# ── Holm ────────────────────────────────────────────────────────────────────
h = T.holm({"a": 0.01, "b": 0.02, "c": 0.30})
check("Holm: 가장 작은 p 에 m 배", abs(h["a"] - 0.03) < 1e-9, h)
check("Holm: 단조 비감소", h["a"] <= h["b"] <= h["c"])
check("Holm: 1.0 상한", T.holm({"a": 0.6, "b": 0.7})["b"] <= 1.0)

# ── 실거래 무관 ─────────────────────────────────────────────────────────────
msrc = inspect.getsource(T)
check("실거래 체결 엔진을 import 하지 않는다",
      "import paper_executor" not in msrc and "import exchange" not in msrc)
check("주문·DB 를 건드리지 않는다", "place_" not in msrc and "supabase" not in msrc.lower())
check("스케줄러가 이 모듈을 모른다",
      "tp_1h" not in open("scheduler.py", encoding="utf-8").read())
check("universe 에 등재 없음",
      "T1SX" not in json.dumps(json.load(open("universe.json", encoding="utf-8"))))
check("registry 에 사전 등록 기록",
      "tp_1h_prereg_2026_09_09" in json.load(open("registry.json", encoding="utf-8")))
wf = open(".github/workflows/tp_1h.yml", encoding="utf-8").read()
check("워크플로가 로직 테스트를 먼저 돌린다", "python test_tp_1h.py" in wf)
check("tests.yml 등재",
      "test_tp_1h.py" in open(".github/workflows/tests.yml", encoding="utf-8").read())

print(f"\n{len(fails)} failed")
raise SystemExit(1 if fails else 0)
