"""
validate_routing.py — 진입 **방향** 라우팅 규칙 시험 (2026-09-05, 사용자 지시).

## 왜

레포의 제1원칙은 '게이트 동결'인데, 라우팅 계층에서만 그게 적용되지 않는다.

  · registry.json 무조건부 판정: engulfing **validated**(롱), fvg **passed**(롱),
    engulfing_short **rejected**, fvg_short **rejected**.
  · 그런데 direction_switch.decide() 는 regime_switch.json 의 레짐별 **n>=20 이고 mean>0**
    두 조건만 본다. median / boot_p / OOS 를 보지 않는다.
  · 그 결과 **동결 게이트에서 기각된 숏이, 게이트를 거치지 않은 표를 근거로 켜진다.**
    현재(bull_altseason) engulfing 이 숏으로 나가는 이유가 정확히 이것이다.

거기에 report_regime_quality.md 가 별도로 확인한 사실이 겹친다 — 현행 레짐 라벨의 20일 지평
**방향 예측력은 적중 49%** 로 사실상 없다. 그런데 라우팅은 라벨을 예측기로 써서 방향을 정한다.
반면 method_s 가 확인한 '레짐 정보 실재'는 **청산 시점**에 대한 것이지 진입 방향이 아니다.

이 시험은 그 둘을 분리한다: **청산은 세 arm 모두 방식D 로 동일하고, 다른 것은 진입 방향뿐이다.**

## arm (진입 방향 결정 규칙)

  route   현행 실거래 규칙. direction_switch.decide() + ROUTING_OVERRIDES 를 그대로 호출해
          복제한다(테스트가 direction_switch.json 과의 일치를 고정).
  uncond  레짐을 방향에 쓰지 않는다. 동결 게이트가 검증한 방향으로 고정 —
          engulfing 롱, fvg 롱. (숏 디텍터는 무조건부 표본에서 rejected 이므로 쓰지 않는다.)
  gated   레짐 라우팅이되 **레짐 분리 게이트를 통과한 셀만** 켠다. 통과 셀이 없으면 FLAT.
          _regime_split.json 을 읽는다(없으면 이 arm 은 건너뛴다). 3단계 제안의 미리보기.
  route_bfl  (2026-09-05 추가, 사용자 지시) route 와 **(bear, fvg) 한 셀만** FLAT→long 으로 다르다.
          1차 시험의 uncond 분기에서 bear fvg 롱이 n=538 +1.63% 로 나왔으나, 4셀을 한꺼번에 바꾸는
          uncond 로는 이 셀만의 기여를 분리할 수 없었다. 분기 셀이 정확히 하나라 기준 3) 이 깨끗하다.

## 기준 3) 의 셀별 부호 규칙 (1차 시험 후 추가 — 새 arm 에만 적용)

1차 시험에서 uncond 의 분기 우위(+1.54% vs +0.32%)가 전부 bear fvg 538건에서 나오고 정작 문제의
altseason engulfing 셀에서는 크게 진 것을 봤다. 분기 표본을 셀 구분 없이 합친 설계 한계다.
**이미 판정한 uncond·gated 에 사후 적용하면 사전등록 위반**이므로 그 둘은 종전 규칙(합산)을 유지하고,
그 뒤에 추가된 arm(PER_CELL_ARMS)에는 '분기 셀 **각각**이 n>=30, 평균 양수, route 보다 높다'를 요구한다.

## 편향을 어느 쪽으로 뒀는지 — 중요

route 의 라우팅 표(regime_switch.json)는 **전 기간 데이터로 적합된 표**다. 2023 년의 거래가
2025 년 데이터로 만든 표를 근거로 방향을 고르는 셈이라 route 에게 룩어헤드 이점이 있다.
이건 실거래 규칙 자체의 성질이라 그대로 둔다 — 대신 **판정은 route 쪽으로 보수적**이 된다.
route 가 이 이점을 갖고도 지면 그 결과는 강하고, 이기면 그만큼 할인해서 읽어야 한다.

ROUTING_OVERRIDES 의 (bear, fvg)=FLAT 은 2026-09-04 사용자 결정이다. 과거 전 구간에
소급 적용되므로 그 시점 이전에는 실제로 일어나지 않은 규칙이지만, **지금의 실거래 규칙을
재는 것이 목적**이므로 복제한다.

## 사전 등록 판정 기준 (결과를 보기 전에 동결한다)

기준선은 route(현행). arm X 가 아래 7개를 **전부** 만족해야 '채택 권고'.

  1) train 포트폴리오 CAGR > route
  2) train Calmar > route
  3) **분기 셀** — 두 arm 이 서로 다른 방향을 고른 (레짐, 패턴) 셀에서 X 의 건당 평균이
     route 보다 높고, 그 자체가 양수. (분기 n < 30 이면 판정 불가로 표시하고 실패 처리)
  4) 시간 분할 — train 전반/후반 각각에서 CAGR 우위가 유지
  5) MDD 가 route 대비 5%p 넘게 악화되지 않음
  6) 짝지음 블록 부트스트랩에서 Calmar 우위 비율 >= 60%
  7) holdout(마지막 365일) 에서 CAGR 우위 유지

6개 이하면 **현행 유지**. 실거래 규칙은 이 파일이 바꾸지 않는다 — 판정만 낸다.

## 블록 부트스트랩이 짝지음인 이유

arm 마다 거래 집합이 다르므로(롱 디텍터와 숏 디텍터는 애초에 다른 신호다) method_r/method_s
식의 '같은 신호에 두 규칙' 짝지음이 성립하지 않는다. 대신 **같은 시간 블록**을 재표집하고
각 arm 이 그 블록에서 실제로 한 거래를 가져온다 — 시장 국면 교란이 arm 간에 상쇄된다.

실행: python validate_routing.py [--no-fetch] [--majors]
출력: _routing.json
"""
import importlib
import json
import random
import statistics as st
import sys
from datetime import date

import detlib
import direction_switch as ds
import method_s as ms
import method_x as mx
import regime_switch as rs
import sizing as sz
import sizing_study as ss
from validate_regime_split import turnover_rank

WINDOW = 1800
HOLDOUT_DAYS = 365
BOOT_N, SEED = 300, 11
BLOCK_DAYS = 30
MIN_DIVERGENCE_N = 30          # 기준 3) 판정 가능 최소 분기 표본
MDD_TOLERANCE = 0.05           # 기준 5) 허용 악화폭

ARMS = ["route", "uncond", "gated", "route_bfl"]
BASELINE = "route"
PER_CELL_ARMS = {"route_bfl"}   # 기준 3) 을 셀별 부호로 판정하는 arm (1차 이후 추가분)
# (기본패턴, 롱 디텍터, 숏 디텍터, 실거래 코호트) — 코호트는 scheduler.PATTERN_UNIVERSE 복제
BASE_PATTERNS = [("engulfing", "detector_engulfing", "detector_engulfing_short", "top20"),
                 ("fvg", "detector_fvg", "detector_fvg_short", "top30")]
SPLIT_FILE = "_regime_split.json"
MAJORS_ONLY = False


# ── arm 별 방향 결정 ────────────────────────────────────────────────────────
def route_table():
    """현행 실거래 라우팅 표. direction_switch 의 함수를 그대로 호출해 복제한다."""
    bp = json.load(open("regime_switch.json", encoding="utf-8"))["by_pattern"]
    tbl = {}
    for rg in ds.REGIMES:
        for pat in ds.FOCUS:
            lo, sh = bp[pat][rg], bp[pat + "_short"][rg]
            d, _ = ds.decide(lo["mean"], lo["n"], sh["mean"], sh["n"])
            ov = ds.ROUTING_OVERRIDES.get((rg, pat))
            tbl[(rg, pat)] = ov if ov is not None else d
    return tbl


def gated_table(cohort_of):
    """
    레짐 분리 게이트 통과 셀만 켠 표. _regime_split.json 이 없으면 None.
    셀은 실거래와 같은 코호트(engulfing=top20, fvg=top30)에서 읽는다.
    """
    try:
        res = json.load(open(SPLIT_FILE, encoding="utf-8"))["results"]
    except Exception as e:
        print(f"[gated] {SPLIT_FILE} 없음/읽기 실패({str(e)[:40]}) — gated arm 건너뜀")
        return None
    tbl = {}
    for rg in ds.REGIMES:
        for pat in ds.FOCUS:
            key = f"{cohort_of[pat]}:{rg}"
            lo = res.get(pat, {}).get(key)
            sh = res.get(pat + "_short", {}).get(key)
            cands = []
            if lo and lo.get("verdict") == "PASSED":
                cands.append(("long", lo["mean"]))
            if sh and sh.get("verdict") == "PASSED":
                cands.append(("short", sh["mean"]))
            cands.sort(key=lambda x: -x[1])
            tbl[(rg, pat)] = cands[0][0] if cands else "FLAT"
    return tbl


def build_tables():
    cohort_of = {p: c for p, _, _, c in BASE_PATTERNS}
    tabs = {"route": route_table(),
            "uncond": {(rg, pat): "long" for rg in ds.REGIMES for pat in ds.FOCUS}}
    g = gated_table(cohort_of)
    if g is not None:
        tabs["gated"] = g
    # route 와 한 셀만 다르다 — (bear, fvg) 를 long 으로. 다른 7셀은 route 그대로 복사.
    # (2026-09-04~05 사이 route 값은 FLAT, 2026-09-05 오버라이드 제거 후는 short — 어느 쪽이든 arm 정의는 같다)
    bfl = dict(tabs["route"])
    bfl[("bear", "fvg")] = "long"
    tabs["route_bfl"] = bfl
    return tabs


# ── 신호 수집 ───────────────────────────────────────────────────────────────
def symbols():
    if MAJORS_ONLY:
        return list(detlib.SYMBOLS)
    return json.load(open("universe.json", encoding="utf-8"))["trading_universe"]


def collect(rows_by, cohorts, regmap):
    """
    반환: cands[(base_pattern)] = [dict(sym, i, date, regime, direction, ret, hold, reason,
                                        exit_date, stop_pct, vol)]
    한 봉이 롱·숏 신호를 동시에 낼 수 있으므로 (i, direction) 각각을 후보로 둔다.
    수익률은 arm 과 무관하게 방향으로만 정해지므로 여기서 한 번만 계산한다.
    """
    def lab_of(rows):
        return lambda j: regmap.get(rows[j]["date"])

    out = {}
    for base, longmod, shortmod, cohort in BASE_PATTERNS:
        ml, msd = importlib.import_module(longmod), importlib.import_module(shortmod)
        rec = []
        syms = cohorts[cohort]
        for s in syms:
            rows = rows_by.get(s)
            if not rows:
                continue
            lsig, ssig = set(ml.detect(rows)), set(msd.detect(rows))
            lab = lab_of(rows)
            for i, direction in ([(i, "long") for i in sorted(lsig)]
                                 + [(i, "short") for i in sorted(ssig)]):
                if i + 1 >= len(rows):
                    continue
                opp = ssig if direction == "long" else lsig
                ret, hold, reason = ms.outcome(rows, i, direction, opp, lab)
                vol = sz.realized_vol(rows, i, tf="1d")
                if vol is None:
                    continue          # 사이징 불가 → 전 arm 에서 제외(비교 공정성)
                rec.append(dict(sym=s, i=i, date=rows[i]["date"],
                                regime=regmap.get(rows[i]["date"]),
                                direction=direction, ret=ret, hold=hold, reason=reason,
                                exit_date=rows[min(i + hold, len(rows) - 1)]["date"],
                                stop_pct=ms.STOP, vol=vol))
        out[base] = rec
        print(f"  [collect] {base}: 후보 {len(rec)}건 ({len(syms)}종목)", flush=True)
    return out


def arm_trades(cands, table):
    """arm 의 방향 표에 맞는 후보만 남긴다."""
    out = []
    for base, recs in cands.items():
        for r in recs:
            if r["regime"] is None:
                continue
            if table.get((r["regime"], base)) == r["direction"]:
                out.append(dict(r, base=base))
    out.sort(key=lambda r: r["date"])
    return out


# ── 성과 ────────────────────────────────────────────────────────────────────
def as_tuples(trades):
    """method_x.equity_curve 가 받는 7-튜플."""
    return [(t["date"], t["exit_date"], t["ret"], t["hold"], t["reason"], t["stop_pct"], t["vol"])
            for t in trades]


def perf(trades, span_days=None):
    """
    span_days: 그 분할(train/holdout)의 **공통 기간**. arm 마다 거래 집합이 다르므로 각자의
    첫~마지막 간격으로 연율화하면 분모가 달라져 CAGR 이 비교 불가능해진다 — 거래가 짧은
    구간에 몰린 arm 이 같은 손실로 훨씬 나쁜 CAGR 을 받는다. 분할 창으로 통일한다.
    """
    if not trades:
        return None
    rets = [t["ret"] for t in trades]
    eq = mx.equity_curve(as_tuples(trades), span_days=span_days)
    return dict(n=len(rets), mean=st.mean(rets), median=st.median(rets),
                win=sum(1 for r in rets if r > 0) / len(rets),
                hold=st.mean(t["hold"] for t in trades),
                cagr=eq["cagr"] if eq else 0.0, mdd=eq["mdd"] if eq else 0.0,
                calmar=eq["calmar"] if eq else 0.0,
                taken=eq["taken"] if eq else 0, skipped=eq["skipped"] if eq else 0)


def split_by_date(trades, cutoff):
    return ([t for t in trades if t["date"] < cutoff],
            [t for t in trades if t["date"] >= cutoff])


# ── 분기 셀 ─────────────────────────────────────────────────────────────────
def divergence(cands, tab_a, tab_b):
    """
    두 표가 서로 다른 방향(FLAT 포함)을 고른 (레짐, 패턴) 셀에서, 각 arm 이 실제로 한 거래를
    비교한다. FLAT 쪽은 거래 0건이므로 '건당 평균'이 정의되지 않는다 — 그 셀은 자본을 쓰지
    않으므로 수익률 0 이 아니라 **표본 없음**으로 다루고, n 과 함께 보고한다.
    """
    cells, a_tr, b_tr = [], [], []
    for base, recs in cands.items():
        for rg in ds.REGIMES:
            da, db = tab_a.get((rg, base), "FLAT"), tab_b.get((rg, base), "FLAT")
            if da == db:
                continue
            ra = [r for r in recs if r["regime"] == rg and r["direction"] == da]
            rb = [r for r in recs if r["regime"] == rg and r["direction"] == db]
            if not ra and not rb:
                continue      # 표는 다르지만 그 레짐에 신호가 없는 셀 (예: sideways) — 보고 소음
            a_tr += ra; b_tr += rb
            cells.append(dict(pattern=base, regime=rg, a_dir=da, b_dir=db,
                              a_n=len(ra), b_n=len(rb),
                              a_mean=st.mean([r["ret"] for r in ra]) if ra else None,
                              b_mean=st.mean([r["ret"] for r in rb]) if rb else None))
    return dict(cells=cells, a_n=len(a_tr), b_n=len(b_tr),
                a_mean=st.mean([r["ret"] for r in a_tr]) if a_tr else None,
                b_mean=st.mean([r["ret"] for r in b_tr]) if b_tr else None)


# ── 짝지음 블록 부트스트랩 ──────────────────────────────────────────────────
def _dnum(ds_):
    return ss._dnum(ds_)


def paired_block_boot(arm_trades_map, rng, n_boot=BOOT_N, block=BLOCK_DAYS):
    """
    같은 시간 블록을 재표집하고 **각 arm 이 그 블록에서 실제로 한 거래**를 가져온다.
    블록은 날짜를 순서대로 다시 이어 붙여(offset 이동) 보유 기간과 중첩 구조를 보존한다.
    반환: arm -> dict(calmar=[...], cagr=[...], mdd=[...])
    """
    all_days = [_dnum(t["date"]) for tr in arm_trades_map.values() for t in tr]
    if not all_days:
        return {a: dict(calmar=[], cagr=[], mdd=[]) for a in arm_trades_map}
    d0, d1 = min(all_days), max(all_days)
    n_blocks = max(1, (d1 - d0) // block + 1)
    # arm 별 블록 인덱스 -> 거래
    by_block = {}
    for a, tr in arm_trades_map.items():
        m = {}
        for t in tr:
            m.setdefault((_dnum(t["date"]) - d0) // block, []).append(t)
        by_block[a] = m
    out = {a: dict(calmar=[], cagr=[], mdd=[]) for a in arm_trades_map}
    for _ in range(n_boot):
        pick = [rng.randrange(n_blocks) for _ in range(n_blocks)]
        for a, m in by_block.items():
            tup = []
            for pos, b in enumerate(pick):
                shift = (pos - b) * block
                for t in m.get(b, []):
                    e, x = _dnum(t["date"]) + shift, _dnum(t["exit_date"]) + shift
                    tup.append((date.fromordinal(e).isoformat(), date.fromordinal(max(x, e)).isoformat(),
                                t["ret"], t["hold"], t["reason"], t["stop_pct"], t["vol"]))
            tup.sort()
            eq = mx.equity_curve(tup, span_days=n_blocks * block)
            # **draw 마다 arm 별로 정확히 한 값을 넣는다.** 판정 기준 6) 은 arm 간 draw 를
            # zip 으로 짝지으므로, 거래가 없는 draw 를 건너뛰면 i 번째 값이 서로 다른 draw 가
            # 되어 짝지음이 조용히 어긋난다. 거래 0건인 draw 는 '아무것도 안 한 것' —
            # 자본 불변이므로 CAGR·MDD 0, Calmar 0(수익 내는 상대에겐 지고, 잃는 상대는 이긴다).
            out[a]["calmar"].append(min(eq["calmar"], 50.0) if eq else 0.0)
            out[a]["cagr"].append(eq["cagr"] if eq else 0.0)
            out[a]["mdd"].append(eq["mdd"] if eq else 0.0)
    return out


# ── 판정 ────────────────────────────────────────────────────────────────────
def verdict(arm, res, boot_win):
    """사전 등록 기준 7개. 전부 True 여야 채택 권고."""
    b, x = res[BASELINE], res[arm]
    tr_b, tr_x = b["train"], x["train"]
    if not tr_b or not tr_x:
        return dict(pass_=False, reason="train 표본 없음")
    c1 = tr_x["cagr"] > tr_b["cagr"]
    c2 = tr_x["calmar"] > tr_b["calmar"]
    dv = x["divergence"]
    if arm in PER_CELL_ARMS:
        # 셀별 부호: 분기 셀 각각이 n>=30 · 평균 양수 · route 보다 높아야 한다. 셀이 없으면 실패.
        cells = dv.get("cells", [])
        c3 = bool(cells) and all(
            c["b_n"] >= MIN_DIVERGENCE_N and c["b_mean"] is not None and c["b_mean"] > 0
            and (c["a_mean"] is None or c["b_mean"] > c["a_mean"]) for c in cells)
    else:
        c3 = (dv["b_n"] >= MIN_DIVERGENCE_N and dv["b_mean"] is not None
              and (dv["a_mean"] is None or dv["b_mean"] > dv["a_mean"]) and dv["b_mean"] > 0)
    h = x["halves"]
    c4 = bool(h) and all(h[k]["arm"] > h[k]["base"] for k in ("first", "second") if h.get(k))
    c4 = c4 and all(h.get(k) for k in ("first", "second"))
    c5 = tr_x["mdd"] >= tr_b["mdd"] - MDD_TOLERANCE
    c6 = boot_win >= 0.60
    ho_b, ho_x = b["holdout"], x["holdout"]
    c7 = bool(ho_b) and bool(ho_x) and ho_x["cagr"] > ho_b["cagr"]
    ok = all([c1, c2, c3, c4, c5, c6, c7])
    return dict(pass_=ok, c1_cagr=c1, c2_calmar=c2, c3_divergence=c3, c4_halves=c4,
                c5_mdd=c5, c6_boot_calmar_win=c6, c7_holdout=c7,
                divergence_n=dv["b_n"], boot_win=boot_win)


def _f(v, pct=True, w=8):
    if v is None:
        return f"{'n/a':>{w}}"
    return f"{v*100:>+{w-1}.2f}%" if pct else f"{v:>{w}.2f}"


def main(argv=None):
    global MAJORS_ONLY
    argv = list(sys.argv[1:] if argv is None else argv)
    MAJORS_ONLY = "--majors" in argv
    syms = symbols()
    if "--no-fetch" not in argv:
        ms.ensure_data(WINDOW, syms)
    regmap = rs.build_regime_map()
    rows_by = {}
    for s in syms:
        try:
            rows_by[s] = detlib.load_ohlcv(s, "1d")
        except Exception:
            pass
    ranked = turnover_rank(rows_by)
    cohorts = {"all": list(rows_by), "top20": ranked[:20], "top30": ranked[:30]}
    print(f"[universe] {len(rows_by)}종목 | top20 {ranked[:20]}")

    tabs = build_tables()
    print("\n[arm 별 방향 표]")
    print(f"  {'레짐':<16}{'패턴':<11}" + "".join(f"{a:>10}" for a in ARMS if a in tabs))
    for rg in ds.REGIMES:
        for pat in ds.FOCUS:
            print(f"  {rg:<16}{pat:<11}" + "".join(f"{tabs[a].get((rg, pat), 'FLAT'):>10}"
                                                   for a in ARMS if a in tabs))

    print("\n[신호 수집]")
    cands = collect(rows_by, cohorts, regmap)

    all_dates = sorted(r["date"] for recs in cands.values() for r in recs)
    if not all_dates:
        raise SystemExit("신호 0건 — 데이터 확인 필요")
    cutoff = date.fromordinal(_dnum(all_dates[-1]) - HOLDOUT_DAYS).isoformat()
    print(f"[분할] train < {cutoff} <= holdout (마지막 {HOLDOUT_DAYS}일)")

    # 분할별 공통 창(일). arm 이 아니라 **분할**이 분모를 정한다.
    d_lo, d_hi = _dnum(all_dates[0]), _dnum(all_dates[-1])
    d_cut = _dnum(cutoff)
    span_all = max(1, d_hi - d_lo)
    span_train = max(1, d_cut - d_lo)
    mid = date.fromordinal(d_lo + span_train // 2).isoformat()
    span_h1 = span_h2 = max(1, span_train // 2)

    res, tr_map = {}, {}
    for a in ARMS:
        if a not in tabs:
            continue
        tr = arm_trades(cands, tabs[a])
        tr_map[a] = tr
        train, hold = split_by_date(tr, cutoff)
        first, second = split_by_date(train, mid)
        res[a] = dict(all=perf(tr, span_all), train=perf(train, span_train),
                      holdout=perf(hold, HOLDOUT_DAYS),
                      _first=perf(first, span_h1), _second=perf(second, span_h2))

    for a in res:
        if a == BASELINE:
            res[a]["divergence"] = dict(cells=[], a_n=0, b_n=0, a_mean=None, b_mean=None)
            res[a]["halves"] = {}
            continue
        res[a]["divergence"] = divergence(cands, tabs[BASELINE], tabs[a])
        hb, ha = res[BASELINE], res[a]
        res[a]["halves"] = {
            k: dict(base=hb[f"_{k}"]["cagr"], arm=ha[f"_{k}"]["cagr"])
            for k in ("first", "second") if hb.get(f"_{k}") and ha.get(f"_{k}")}

    print("\n[성과]")
    print(f"  {'arm':<8}{'분할':<9}{'n':>6}{'건당평균':>10}{'중앙':>9}{'승률':>7}{'보유':>7}"
          f"{'CAGR':>10}{'MDD':>9}{'Calmar':>8}{'진입':>7}{'스킵':>7}")
    print("  " + "-" * 105)
    for a in res:
        for sp in ("train", "holdout"):
            p = res[a][sp]
            if not p:
                print(f"  {a:<8}{sp:<9}     0  (거래 없음)")
                continue
            print(f"  {a:<8}{sp:<9}{p['n']:>6}{_f(p['mean'])}{_f(p['median'], w=9)}"
                  f"{p['win']*100:>6.0f}%{p['hold']:>7.1f}{_f(p['cagr'], w=10)}{_f(p['mdd'], w=9)}"
                  f"{p['calmar']:>8.2f}{p['taken']:>7}{p['skipped']:>7}")

    print("\n[분기 셀 — route 대비]")
    for a in res:
        if a == BASELINE:
            continue
        dv = res[a]["divergence"]
        print(f"  {a}: route {dv['a_n']}건 {_f(dv['a_mean'])} vs {a} {dv['b_n']}건 {_f(dv['b_mean'])}")
        for c in dv["cells"]:
            print(f"    {c['regime']:<16}{c['pattern']:<11}"
                  f"route={c['a_dir']:<6}n={c['a_n']:<5}{_f(c['a_mean'])}  |  "
                  f"{a}={c['b_dir']:<6}n={c['b_n']:<5}{_f(c['b_mean'])}")

    print("\n[짝지음 블록 부트스트랩]", flush=True)
    rng = random.Random(SEED)
    train_map = {a: split_by_date(tr_map[a], cutoff)[0] for a in tr_map}
    boot = paired_block_boot(train_map, rng)
    wins = {}
    for a in res:
        if a == BASELINE:
            continue
        pair = list(zip(boot[BASELINE]["calmar"], boot[a]["calmar"]))
        wins[a] = (sum(1 for bb, xx in pair if xx > bb) / len(pair)) if pair else 0.0
        bm = st.median(boot[BASELINE]["calmar"]) if boot[BASELINE]["calmar"] else 0.0
        am = st.median(boot[a]["calmar"]) if boot[a]["calmar"] else 0.0
        print(f"  {a}: Calmar 중앙 route {bm:.2f} vs {a} {am:.2f} | {a} 우위 {wins[a]*100:.0f}%")

    print("\n[판정] (사전 등록 7기준 — 전부 통과해야 채택 권고)")
    verdicts = {}
    for a in res:
        if a == BASELINE:
            continue
        v = verdict(a, res, wins.get(a, 0.0))
        verdicts[a] = v
        flags = " ".join(f"{k.split('_')[0]}{'O' if v.get(k) else 'X'}"
                         for k in ("c1_cagr", "c2_calmar", "c3_divergence", "c4_halves",
                                   "c5_mdd", "c6_boot_calmar_win", "c7_holdout"))
        print(f"  {a:<8}{'채택 권고' if v['pass_'] else '현행 유지':<10} {flags}"
              f" | 분기 n={v.get('divergence_n')} boot우위={v.get('boot_win', 0)*100:.0f}%")

    json.dump(dict(window=WINDOW, cutoff=cutoff, majors=MAJORS_ONLY,
                   tables={a: {f"{rg}|{pat}": tabs[a].get((rg, pat), "FLAT")
                               for rg in ds.REGIMES for pat in ds.FOCUS} for a in tabs},
                   results=res, boot_win=wins, verdicts=verdicts),
              open("_routing.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print("\n[저장] _routing.json")
    print("RESULT_JSON: " + json.dumps(
        {a: dict(pass_=v["pass_"], divergence_n=v.get("divergence_n")) for a, v in verdicts.items()},
        ensure_ascii=False))


if __name__ == "__main__":
    main()
