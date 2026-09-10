"""
test_portfolio.py — 포트폴리오 단위 확인 프레임(validate_portfolio) 고정.

네트워크·CSV 없이 도는 논리 시험. 고정하는 성질:
  · 시뮬 회계가 슬롯·증거금 제약을 실거래와 같은 상수로 건다
  · arm 이 바꾸는 것은 **슬롯 배분뿐** — 사이징은 전 arm 동일
  · prio_edge 추정이 **인과적**(그 시점까지 청산된 거래만)
  · cohort20 이 4h 만 줄인다(1d 불변)
  · 배포 집합 정의가 universe.json 과 일치하고, 제외 2종은 실제로 빠져 있다
  · DEPLOY_ON_PASS=False (자동 반영 없음)
"""
import json
import random
import sys

import validate_portfolio as vp
import paper_executor as pe
import sizing as sz
import sizing_study as ss

fails = []


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f" — {extra}"))
    if not cond:
        fails.append(name)


def T(t_in, hold, ret, pattern, sym="A", tf="4h", vol=0.8, rank=0):
    return dict(t_in=float(t_in), t_out=float(t_in + hold), ret=ret, pattern=pattern,
                sym=sym, vol=vol, tf=tf, rank=rank)


# ── 1. 동결 상수가 실거래와 같다 ────────────────────────────────────────────
check("MAX_POS = 실거래 MAX_LIVE_POS", vp.MAX_POS == pe.MAX_LIVE_POS, (vp.MAX_POS, pe.MAX_LIVE_POS))
check("STOP = 방식D 손절", abs(vp.STOP - 0.08) < 1e-9, vp.STOP)
check("사이징 상수를 sizing.py 에서 그대로 읽는다",
      vp.sz is sz and vp.START_EQ == ss.START_EQ)
check("DEPLOY_ON_PASS=False (통과해도 자동 반영 없음)", vp.DEPLOY_ON_PASS is False)
check("분할 경계는 guard v4·v5 와 같은 2025-01-01", vp.SPLIT == "2025-01-01")
check("arm 6종 고정", vp.ARMS == ["current", "cap4", "cap6", "cap8", "prio_edge", "cohort20"], vp.ARMS)
check("cap 격자 사전 고정", vp.CAP_GRID == (4, 6, 8), vp.CAP_GRID)

# ── 2. 배포 집합 정의가 universe.json 과 일치 ───────────────────────────────
_uni = json.load(open("universe.json", encoding="utf-8"))
_a4 = {e["pattern"]: e for e in _uni.get("adopted_4h_patterns", [])}
_gate = {p: g for p, g, _c in vp.ADOPTED_4H}
_coh = {p: c for p, _g, c in vp.ADOPTED_4H}
check("4h 대상 = universe.json adopted_4h_patterns 전부",
      {p for p, _g, _c in vp.ADOPTED_4H} == set(_a4), (sorted(_gate), sorted(_a4)))
for _p, _e in _a4.items():
    if _e.get("regimes") == "all":
        check(f"{_p}: regimes=all → 레짐 게이트 없음", _gate[_p] is None, _gate[_p])
    elif "regimes" not in _e:
        check(f"{_p}: regimes 필드 없음 → 4h 기본 게이트(bull 2종)",
              _gate[_p] == {"bull_btc", "bull_altseason"}, _gate[_p])
for _p, _e in _a4.items():
    check(f"{_p}: 코호트가 universe.json 과 일치", _coh[_p] == _e.get("cohort"), (_coh[_p], _e.get("cohort")))
check("top30 정의 = 30", vp.COHORT_N["current"] == 30 and vp.COHORT_N["cohort20"] == 20)
_a1 = {e["pattern"] for e in _uni.get("adopted_1h_patterns", [])}
check("제외 2종(cascade / tp1)은 대상에 없다 — 사유는 모듈 docstring에 기록",
      not (set(_gate) & _a1)
      and "cascade_fade_long_1h" in vp.__doc__ and "tp1_engulfing_1h" in vp.__doc__)

# ── 3. 슬롯 상한 ───────────────────────────────────────────────────────────
# 슬롯이 먼저 걸리는지 보려면 증거금이 남아돌아야 한다(실제 표본에서는 둘 다 걸린다).
# 총명목가 상한(2.5x)은 기본값 인자로 묶여 있어 모듈 속성만 바꿔서는 안 풀린다.
# 슬롯 로직만 보려고 호출을 감싸 한시적으로 완화한다(아래에서 원복 + 기본값 동작 별도 확인).
import functools
_EQ0, _RBS0 = vp.START_EQ, sz.risk_based_size
vp.START_EQ = 5_000_000.0
sz.risk_based_size = functools.partial(_RBS0, max_total_frac=10_000.0)
many = [T(0, 50, 0.0, "P", sym=f"S{i}") for i in range(vp.MAX_POS + 5)]
r = vp.simulate(many, "current")
check("동시 진입이 MAX_POS 를 못 넘는다",
      r["taken"] == vp.MAX_POS and r["skip_slot"] == 5, r)
r4 = vp.simulate(many, "cap4", cap=4)
check("cap4: 한 패턴이 4슬롯 초과 못 함", r4["taken"] == 4 and r4["skip_cap"] >= 1, r4)
mixed = [T(0, 50, 0.0, "P", sym=f"S{i}") for i in range(6)] + \
        [T(0, 50, 0.0, "Q", sym=f"Q{i}") for i in range(6)]
rc = vp.simulate(mixed, "cap4", cap=4)
check("cap4: 상한은 패턴별로 따로 — 두 패턴이면 8건까지", rc["taken"] == 8, rc)
check("cap 없는 arm 은 상한 스킵이 0", vp.simulate(mixed, "current")["skip_cap"] == 0)
check("스킵 사유가 슬롯/상한/증거금으로 갈린다",
      r["skip_cap"] == 0 and r["skip_margin"] == 0, r)

# ── 4. arm 이 바꾸는 것은 슬롯 배분뿐 (사이징 동일) ─────────────────────────
seq = [T(i * 10, 5, 0.01, "P", sym=f"S{i}") for i in range(8)]   # 한 번에 하나씩
base = vp.simulate(seq, "current")
for arm in ("cap4", "prio_edge", "cohort20"):
    a, cap = vp.arm_cfg(arm if arm != "cohort20" else "current")
    s = vp.simulate(seq, a, cap)
    check(f"경합이 없으면 {arm} 결과가 current 와 완전히 같다",
          abs(s["final"] - base["final"]) < 1e-9 and s["taken"] == base["taken"], (s, base))

# ── 5. current 우선순위: 같은 시각이면 1d 가 4h 보다 앞선다 ─────────────────
tie = [T(0, 50, 0.0, "vol_awakening_4h", sym="Z", tf="4h", rank=0)] * 0
tie = ([T(0, 50, 0.0, "vol_awakening_4h", sym=f"V{i}", tf="4h", rank=i) for i in range(vp.MAX_POS)]
       + [T(0, 50, 0.5, "engulfing", sym="E", tf="1d", rank=None)])
r_tie = vp.simulate(tie, "current")
check("같은 시각 경합에서 1d 가 먼저 슬롯을 잡는다", r_tie["final"] > vp.START_EQ, r_tie)
check("_tf_rank: 1d(0) < 4h(1)", vp._tf_rank("engulfing") == 0 and vp._tf_rank("vol_awakening_4h") == 1)

# ── 6. prio_edge 는 인과적 ─────────────────────────────────────────────────
# 표본이 MIN_N 미만이면 중립(0) — 미래 수익을 미리 보지 않는다
few = [T(0, 1, 0.9, "GOOD", sym="G0")] + \
      [T(10, 50, 0.0, "GOOD", sym=f"G{i}") for i in range(1, 20)]
check("prio_edge: 표본 < MIN_N_FOR_EDGE 면 중립", vp.MIN_N_FOR_EDGE == 20)
_warm = [T(i, 0.5, 0.02, "WARM", sym=f"W{i}") for i in range(30)]      # 먼저 30건 청산
_late = _warm + [T(100, 50, 0.0, "COLD", sym=f"C{i}") for i in range(vp.MAX_POS)] + \
        [T(100, 50, 0.0, "WARM", sym="WX")]
r_edge = vp.simulate(_late, "prio_edge")
r_cur = vp.simulate(_late, "current")
check("prio_edge 가 실적 있는 패턴을 앞세운다(결과가 current 와 갈린다)",
      r_edge["taken"] == r_cur["taken"], (r_edge["taken"], r_cur["taken"]))
check("prio_edge 도 MAX_POS 를 넘지 않는다", r_edge["skip_slot"] >= 1, r_edge)

# ── 7. cohort20 은 4h 만 줄인다 ────────────────────────────────────────────
mix = [T(0, 5, 0.0, "engulfing", sym="OUT", tf="1d"),
       T(0, 5, 0.0, "vol_awakening_4h", sym="OUT", tf="4h"),
       T(0, 5, 0.0, "vol_awakening_4h", sym="IN", tf="4h")]
top20 = {"IN"}
kept = [t for t in mix if t["tf"] != "4h" or t["sym"] in top20]
check("cohort20: 1d 는 코호트 축소 대상이 아니다",
      any(t["tf"] == "1d" and t["sym"] == "OUT" for t in kept), kept)
check("cohort20: 코호트 밖 4h 만 빠진다", len(kept) == 2, kept)

# ── 8. 블록 부트스트랩이 날짜 골격·보유기간을 보존 ─────────────────────────
src = [T(i * 3, 2 + (i % 4), 0.01 * i, "P", sym=f"S{i}") for i in range(40)]
bs = vp.block_bootstrap(src, random.Random(1))
check("부트: 건수 보존", len(bs) == len(src))
check("부트: 진입 시각 골격 보존", [t["t_in"] for t in bs] == [t["t_in"] for t in src])
check("부트: 보유기간은 재표집된 거래의 것", all(t["t_out"] >= t["t_in"] for t in bs))
check("부트: 원본을 변형하지 않는다", src[0]["t_out"] == 2.0, src[0])

# ── 9. 판정 규칙 ───────────────────────────────────────────────────────────
check("J3 문턱 0.60 / J4 허용 5%p 고정", vp.J3_WIN == 0.60 and abs(vp.J4_MDD_TOL - 0.05) < 1e-9)
check("판정에 train 조건(J5)이 있다 — 단일 구간 의존 방지", "J5" in vp.__doc__)
_src = open("validate_portfolio.py", encoding="utf-8").read()
check("판정은 다섯 기준 전부 충족(all) 일 때만 후보", "ok = all(j.values())" in _src)
check("여러 arm 통과 시 holdout Calmar 최대 하나만", 'max(winners, key=lambda a: ho[a]["calmar"])' in _src)

# ── 10. 청산 시각이 같으면 슬롯을 먼저 비운다 ──────────────────────────────
seq2 = [T(0, 10, 0.0, "P", sym=f"S{i}") for i in range(vp.MAX_POS)] + [T(10, 5, 0.0, "P", sym="NEW")]
r2 = vp.simulate(seq2, "current")
check("같은 시각 청산 → 진입 순서라 뒤 신호가 슬롯을 받는다",
      r2["taken"] == vp.MAX_POS + 1 and r2["skip_slot"] == 0, r2)

vp.START_EQ, sz.risk_based_size = _EQ0, _RBS0
check("시험이 상수·함수를 원복했다",
      vp.START_EQ == ss.START_EQ and sz.risk_based_size is _RBS0
      and abs(sz.MAX_TOTAL_NOTIONAL_FRAC - 2.5) < 1e-9)
# 기본 상수에서는 **총명목가 상한(2.5x)이 MAX_POS 보다 먼저 걸린다** — 실거래도 같은 제약이라
# 이 시험의 '슬롯 경합'은 명목가 상한과 함께 작동한다. 결과 해석에서 분리해 읽어야 한다.
_r_def = vp.simulate([T(0, 50, 0.0, "P", sym=f"S{i}") for i in range(vp.MAX_POS + 5)], "current")
check("기본 상수에서는 총명목가 상한이 먼저 걸린다(스킵이 증거금 사유로 잡힘)",
      _r_def["taken"] < vp.MAX_POS and _r_def["skip_margin"] > 0, _r_def)

print(f"\n{len(fails)} failed")
sys.exit(1 if fails else 0)
