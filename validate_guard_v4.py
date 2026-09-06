"""
validate_guard_v4.py — 확인 프레임 v4 = **3중 대조 동시 통과** (2026-09-06 사전 등록, 사용자 확정)

## 왜

bull_btc 국면 진단(diag_bull_phase, 2026-09-06)에서 1d 반전 패턴이 '같은 레짐·코호트 무작위' 대조로는 강하지만
'같은 달 무작위' 대조로는 엣지 ≈0 이었다. 사용자 정정 4건 — 매칭 단위 불충분 / 실질 표본은 월 클러스터 /
라벨 품질은 1차 가설 / 사후 승격 금지 — 를 반영해, **결과를 보기 전에** 매칭 규칙·클러스터 추론·OOS 분할·
통과/보류 기준을 여기 고정한다. registry `guard_v4_prereg_draft_2026_09_06` 과 같은 내용.

## 대조 3종 (전부 같은 실행 조건: 방향·TF·코호트·청산 방식D·수수료 왕복 0.2%·펀딩/슬리피지 미반영·중복 제한 없음)

  A  기존 레짐·코호트 무작위 — 같은 레짐 라벨·코호트·TF 의 무작위 진입(상한 20000)을 같은 청산으로 평가, k=n 부트.
  B  같은 코인·같은 달 무작위 — 신호 (코인 c, 봉 i) 마다 벤치 = 같은 코인 c · 같은 달 · **신호 봉과 같은 레짐 라벨** ·
     같은 방향 · 실제 진입 가능 봉(신호봉 제외, 청산 평가 가능 범위 안)의 방식D 수익 평균. edge_i = r_i − bench.
     풀이 5봉 미만이면 그 신호는 B 에서 제외(개수 보고). 진단 병기: ±10봉 창(같은 코인, 월·레짐 무관) 벤치.
  C  시간 순서 OOS — **train < 2025-01-01 <= OOS** (고정). train = 후보 적격성, OOS = A/B 재현 최종 확인.

## 클러스터 추론 (B)

거래 n 이 아니라 **월** 이 실질 표본. 월 클러스터 블록 부트스트랩 1000회(코인-월 클러스터 병기)로
n 가중 / 동등 월 가중 / 코인-월 동등 가중 세 평균의 p(<=0). 통과 = 세 점추정 모두 > 0 이고 월 클러스터 p(n가중) < 0.05.
OOS 의 B p 는 주 판정 가족(OOS 검정이 계산된 주 셀 전체) 안에서 **Holm 보정**.

## 판정 (사전 등록, 결과 본 뒤 불변)

  REJECTED           전체 표본 A 성능이 명확히 음수 — mean<=0 또는 승률<35%
  INCONCLUSIVE       OOS n<10 또는 OOS B 월 수<3 (표본 부족 — 기각 아님)
  UNCONFIRMED_SHADOW train 적격성(A 게이트 v2 + B 월클러스터 p<.05·세 가중>0) 실패, 또는 OOS 재현 중 하나라도 실패
  CONFIRMED          train 적격 AND OOS A(mean>0·승률>=35%·boot_p<.05) AND OOS B(세 가중>0·Holm p<.05·엣지>=+0.20%p)
                     AND OOS 비용 스트레스(왕복 0.4% 에서 mean>0; 0.6% 는 보고)

배포 셀(engulfing/fvg/three_soldiers_4h)·관찰 셀(ih/marubozu)은 판정과 무관하게 **주문 무변경, 보고만**.
그림자 셀(double_bottom_1d/inverse_hs_1d)은 CONFIRMED 여도 자율 반영 없음 — 사용자 결정. DEPLOY_ON_PASS = False.

## 진단 블록 (판정과 분리, 같은 실행)

  D1 bull_btc 같은 달 무작위 기대값의 장기 부호(월 클러스터 p) · bull vs 비-bull 무작위 비교 · train/OOS 각각
  D2 BTC 3개월 forward return 을 레짐 라벨별로 — 라벨이 bear/sideways 와 분리되는가 (train/OOS)
  D3 셀별 ±10봉 창 B 변형
  D4 배포 후 실거래 행(Supabase trades, live) — 패턴별 n/평균/손절 비율 (읽기 전용, 없으면 생략)

실행: python validate_guard_v4.py [--no-fetch] [--tf 1d,4h]      출력: _guard_v4.json + RESULT_JSON
"""
import importlib
import json
import random
import statistics as st
import sys
import time
from datetime import date

import detlib
import diag_bull_phase as dg
import gate
import regime_switch as rs
import sizing as sz
import validate_regime_split_all as va
import validate_revival as vr
from validate_regime_split import turnover_rank

# ── 동결 파라미터 (registry guard_v4_prereg_draft_2026_09_06.frozen_params 와 동일) ──────────────
SPLIT_DATE = "2025-01-01"          # train < SPLIT <= OOS
FEE_BASE = detlib.FEE              # 0.002 왕복 — 양측 동일
STRESS_FEES = (0.004, 0.006)
STRESS_REQUIRED = 0.004
EDGE_MARGIN = 0.002                # OOS B 엣지 >= +0.20%p (비용 여유)
BOOT_N, SEED, ALPHA = 1000, 42, 0.05
OOS_MIN_N, B_MIN_POOL, B_MIN_MONTHS = 10, 5, 3
WINDOW_BARS = 10                   # 진단 전용 ±10봉 창
WIN_MIN = gate.WIN_RATE_MIN            # 0.35 (게이트 v2)
DEPLOY_ON_PASS = False             # 통과해도 실거래 반영 없음 — 사용자 결정
MAX_HOLD = vr.MAX_HOLD             # 30 (방식D)
MAJORS = list(detlib.SYMBOLS)


def _det(mod):
    return lambda rows, m=mod: importlib.import_module(m).detect(rows)


# 주 판정 가족 — 실거래 라우팅 그대로 복제 (코호트는 scheduler.PATTERN_UNIVERSE 현행: engulfing 은 사용자 강제 top30)
CELLS = [
    dict(cid="engulfing|bull_btc",              pattern="engulfing",         det="detector_engulfing",         tf="1d", cohort="top30",  regime="bull_btc",       direction="long",  status="deployed"),
    dict(cid="engulfing|bear",                  pattern="engulfing",         det="detector_engulfing",         tf="1d", cohort="top30",  regime="bear",           direction="long",  status="deployed"),
    dict(cid="engulfing_short|bull_altseason",  pattern="engulfing_short",   det="detector_engulfing_short",   tf="1d", cohort="top30",  regime="bull_altseason", direction="short", status="deployed"),
    dict(cid="fvg|bull_btc",                    pattern="fvg",               det="detector_fvg",               tf="1d", cohort="top30",  regime="bull_btc",       direction="long",  status="deployed"),
    dict(cid="fvg|bull_altseason",              pattern="fvg",               det="detector_fvg",               tf="1d", cohort="top30",  regime="bull_altseason", direction="long",  status="deployed"),
    dict(cid="three_soldiers_4h|bull_btc",      pattern="three_soldiers_4h", det="detector_three_soldiers_4h", tf="4h", cohort="all",    regime="bull_btc",       direction="long",  status="deployed"),
    dict(cid="three_soldiers_4h|bull_altseason",pattern="three_soldiers_4h", det="detector_three_soldiers_4h", tf="4h", cohort="all",    regime="bull_altseason", direction="long",  status="deployed"),
    dict(cid="inverted_hammer|ALL",             pattern="inverted_hammer",   det="detector_inverted_hammer",   tf="1d", cohort="majors", regime="ALL",            direction="long",  status="observation"),
    dict(cid="marubozu|ALL",                    pattern="marubozu",          det="detector_marubozu",          tf="1d", cohort="majors", regime="ALL",            direction="long",  status="observation"),
    dict(cid="double_bottom_1d|bull_btc",       pattern="double_bottom_1d",  det="detector_double_bottom",     tf="1d", cohort="top30",  regime="bull_btc",       direction="long",  status="shadow"),
    dict(cid="inverse_hs_1d|bull_btc",          pattern="inverse_hs_1d",     det="detector_inverse_hs",        tf="1d", cohort="top30",  regime="bull_btc",       direction="long",  status="shadow"),
]
REGIMES = ["bull_btc", "bull_altseason", "bear", "sideways"]


# ── 청산 평가 캐시 (양측 동일 규칙) ───────────────────────────────────────────────────────────
class Outcomes:
    """(sym, i) → 방식D 수익률. 신호와 벤치가 **같은 함수·같은 캐시**를 쓴다."""

    def __init__(self, tf, rows_by, regmap, direction):
        self.tf, self.rows_by, self.regmap, self.direction = tf, rows_by, regmap, direction
        self.cache = {}

    def eligible(self, sym, i):
        rows = self.rows_by[sym]
        return 30 <= i < len(rows) - MAX_HOLD - 1

    def full(self, sym, i):
        key = (sym, i)
        if key not in self.cache:
            rows = self.rows_by[sym]
            lab = lambda j, rows=rows: self.regmap.get(rows[j]["date"])
            self.cache[key] = vr.live_outcome(self.tf, rows, i, self.direction, lab, None)
        return self.cache[key]

    def ret(self, sym, i):
        r = self.full(sym, i)
        return None if r is None else r[0]


def collect_cell(oc, detect_fn, syms, regime):
    """신호 목록(봉 인덱스 포함). vr.collect 와 같은 적격 조건(si>=30, 청산 평가 가능)."""
    out = []
    for s in syms:
        rows = oc.rows_by[s]
        try:
            idxs = detect_fn(rows)
        except Exception as e:
            print(f"  [detect] {s} 오류: {str(e)[:60]}"); idxs = []
        for si in idxs:
            if not oc.eligible(s, si):
                continue
            lab = oc.regmap.get(rows[si]["date"])
            if regime != "ALL" and lab != regime:
                continue
            r = oc.full(s, si)
            if r is None:
                continue
            vol = sz.realized_vol(rows, si, tf=oc.tf)
            if vol is None:
                continue
            ret, hold, reason, stop_pct = r
            xi = min(si + hold, len(rows) - 1)
            out.append(dict(sym=s, i=si, date=rows[si]["date"], month=rows[si]["date"][:7], regime=lab,
                            ret=ret, hold=hold, reason=reason, stop_pct=stop_pct, vol=vol,
                            exit_date=rows[xi]["date"], t_in=vr._tnum(rows[si]), t_out=vr._tnum(rows[xi])))
    return out


# ── B: 같은 코인·같은 달·같은 레짐 벤치 ─────────────────────────────────────────────────────
def bench_pool(oc, sym, i, mode="month"):
    """mode='month': 같은 달·같은 레짐 라벨(신호 봉 기준)·신호봉 제외·진입 가능 봉. mode='window': ±WINDOW_BARS 봉(월·레짐 무관)."""
    rows = oc.rows_by[sym]
    if mode == "window":
        cand = range(max(0, i - WINDOW_BARS), min(len(rows), i + WINDOW_BARS + 1))
        return [j for j in cand if j != i and oc.eligible(sym, j)]
    m, lab = rows[i]["date"][:7], oc.regmap.get(rows[i]["date"])
    lo = i
    while lo - 1 >= 0 and rows[lo - 1]["date"][:7] == m:
        lo -= 1
    hi = i
    while hi + 1 < len(rows) and rows[hi + 1]["date"][:7] == m:
        hi += 1
    return [j for j in range(lo, hi + 1)
            if j != i and oc.eligible(sym, j) and oc.regmap.get(rows[j]["date"]) == lab]


def b_edges(oc, sigs, mode="month", min_pool=B_MIN_POOL):
    """[dict(sym, month, ret, bench, edge, pool_n)] + 제외 건수."""
    out, excluded = [], 0
    for s in sigs:
        pj = bench_pool(oc, s["sym"], s["i"], mode)
        rets = [r for r in (oc.ret(s["sym"], j) for j in pj) if r is not None]
        if len(rets) < min_pool:
            excluded += 1
            continue
        bench = st.mean(rets)
        out.append(dict(sym=s["sym"], date=s["date"], month=s["month"], ret=s["ret"], bench=bench,
                        edge=s["ret"] - bench, pool_n=len(rets)))
    return out, excluded


# ── 클러스터 부트스트랩 ─────────────────────────────────────────────────────────────────────
def _three_means(groups):
    """groups: [[(coin, edge), ...] 월 단위]. (n가중, 동등월, 동등코인-월)."""
    flat = [e for g in groups for _, e in g]
    if not flat:
        return None, None, None
    nw = st.mean(flat)
    eqm = st.mean(st.mean(e for _, e in g) for g in groups if g)
    cm = []
    for g in groups:
        by = {}
        for c, e in g:
            by.setdefault(c, []).append(e)
        cm.extend(st.mean(v) for v in by.values())
    return nw, eqm, (st.mean(cm) if cm else None)


def cluster_boot(edges, n_boot=BOOT_N, seed=SEED):
    """월 클러스터 부트(주) + 코인-월 클러스터 부트(병기). p = P(통계량 <= 0)."""
    by_m = {}
    for e in edges:
        by_m.setdefault(e["month"], []).append((e["sym"], e["edge"]))
    months = sorted(by_m)
    groups = [by_m[m] for m in months]
    nw, eqm, eqcm = _three_means(groups)
    res = dict(n=len(edges), months=len(months), coin_months=len({(e["sym"], e["month"]) for e in edges}),
               nw=nw, eq_month=eqm, eq_coin_month=eqcm, p_nw=None, p_eq_month=None, p_eq_coin_month=None,
               p_nw_coinmonth=None, ci_nw=None)
    if not months:
        return res
    rng = random.Random(seed)
    draws = []
    for _ in range(n_boot):
        pick = [groups[rng.randrange(len(groups))] for _ in range(len(groups))]
        draws.append(_three_means(pick))
    def p_of(k):
        vals = [d[k] for d in draws if d[k] is not None]
        return sum(1 for v in vals if v <= 0) / len(vals) if vals else None
    res["p_nw"], res["p_eq_month"], res["p_eq_coin_month"] = p_of(0), p_of(1), p_of(2)
    v0 = sorted(d[0] for d in draws if d[0] is not None)
    if v0:
        res["ci_nw"] = (v0[int(0.025 * (len(v0) - 1))], v0[int(0.975 * (len(v0) - 1))])
    # 코인-월 클러스터 (병기)
    by_cm = {}
    for e in edges:
        by_cm.setdefault((e["sym"], e["month"]), []).append(e["edge"])
    cms = list(by_cm.values())
    rng2 = random.Random(seed + 1)
    cnt = 0
    for _ in range(n_boot):
        pick = [cms[rng2.randrange(len(cms))] for _ in range(len(cms))]
        flat = [e for g in pick for e in g]
        cnt += st.mean(flat) <= 0
    res["p_nw_coinmonth"] = cnt / n_boot
    return res


def b_ok(cb, alpha=ALPHA, p_key="p_nw"):
    """세 가중 점추정 모두 > 0 이고 월 클러스터 p < alpha."""
    if cb["nw"] is None or cb[p_key] is None:
        return False
    return cb["nw"] > 0 and cb["eq_month"] > 0 and cb["eq_coin_month"] > 0 and cb[p_key] < alpha


def holm(pvals):
    """{key: p} → {key: p_adj} (Holm step-down)."""
    items = sorted((p, k) for k, p in pvals.items() if p is not None)
    m, out, run = len(items), {}, 0.0
    for r, (p, k) in enumerate(items):
        run = max(run, min(1.0, (m - r) * p))
        out[k] = run
    return out


# ── A: 레짐·코호트 무작위 ────────────────────────────────────────────────────────────────
def a_stats(sigs, pool_rets, seed=SEED):
    rets = [s["ret"] for s in sigs]
    n = len(rets)
    mean = st.mean(rets) if rets else None
    win = gate.win_rate(rets) if rets else None
    boot_p, base = None, None
    if pool_rets and n:
        rng = random.Random(seed)
        means = [st.mean(rng.choices(pool_rets, k=n)) for _ in range(BOOT_N)]
        boot_p = sum(1 for m in means if m >= mean) / BOOT_N
        base = st.mean(means)
    return dict(n=n, mean=mean, win=win, boot_p=boot_p, base_mean=base,
                edge=(mean - base) if (mean is not None and base is not None) else None, pool_n=len(pool_rets))


def mean_at_fee(mean, fee):
    """수익률에 이미 FEE_BASE 가 빠져 있다 → 스트레스 수수료로 재계산."""
    return None if mean is None else mean - (fee - FEE_BASE)


# ── 판정 ─────────────────────────────────────────────────────────────────────────────────
def verdict(full_a, train_gate_passed, train_b, oos_a, oos_b, p_holm, oos_mean):
    """
    full_a: 전체 표본 a_stats / train_gate_passed: vr.gate_cell verdict == PASSED / train_b, oos_b: cluster_boot
    oos_a: a_stats / p_holm: OOS B Holm 보정 p / oos_mean: OOS 평균(FEE_BASE 포함 수익)
    반환 (verdict, fails)
    """
    fails = []
    if full_a["n"] == 0 or full_a["mean"] is None or full_a["mean"] <= 0 or (full_a["win"] or 0) < WIN_MIN:
        return "REJECTED", ["A_full mean<=0 or win<35%"]
    if not train_gate_passed:
        fails.append("train A gate")
    if not b_ok(train_b):
        fails.append("train B")
    if oos_a["n"] < OOS_MIN_N or oos_b["months"] < B_MIN_MONTHS:
        return "INCONCLUSIVE", fails + [f"OOS n={oos_a['n']} months={oos_b['months']}"]
    if not (oos_a["mean"] > 0 and (oos_a["win"] or 0) >= WIN_MIN and oos_a["boot_p"] is not None and oos_a["boot_p"] < ALPHA):
        fails.append("OOS A")
    if not (oos_b["nw"] is not None and oos_b["nw"] > 0 and oos_b["eq_month"] > 0 and oos_b["eq_coin_month"] > 0
            and p_holm is not None and p_holm < ALPHA and oos_b["nw"] >= EDGE_MARGIN):
        fails.append("OOS B")
    if not (mean_at_fee(oos_mean, STRESS_REQUIRED) or 0) > 0:
        fails.append("OOS cost@0.4%")
    return ("CONFIRMED" if not fails else "UNCONFIRMED_SHADOW"), fails


def run_cell(cell, oc, cs, pool, first_date, last_date):
    """셀 하나의 A/B/C 통계 (판정 제외 — Holm 은 가족 전체가 있어야 한다). 반환 dict + (train, oos)."""
    tf = cell["tf"]
    sigs = collect_cell(oc, _det(cell["det"]), cs, cell["regime"])
    train = [s for s in sigs if s["date"] < SPLIT_DATE]
    oos = [s for s in sigs if s["date"] >= SPLIT_DATE]
    pool_tr = [r for dt, r in pool if dt < SPLIT_DATE]
    pool_oos = [r for dt, r in pool if dt >= SPLIT_DATE]
    full_a = a_stats(sigs, [r for _, r in pool])
    tr_gate = vr.gate_cell(train, pool_tr)
    tr_a = a_stats(train, pool_tr)
    oos_a = a_stats(oos, pool_oos)
    eb_tr, ex_tr = b_edges(oc, train)
    eb_oos, ex_oos = b_edges(oc, oos)
    tr_b, oos_b = cluster_boot(eb_tr), cluster_boot(eb_oos)
    ew_tr, _ = b_edges(oc, train, mode="window", min_pool=WINDOW_BARS)
    ew_oos, _ = b_edges(oc, oos, mode="window", min_pool=WINDOW_BARS)
    win_tr, win_oos = cluster_boot(ew_tr), cluster_boot(ew_oos)
    oos_mean = oos_a["mean"]
    span_tr = max(1, date.fromisoformat(SPLIT_DATE).toordinal() - date.fromisoformat(first_date).toordinal())
    span_oos = max(1, date.fromisoformat(last_date).toordinal() - date.fromisoformat(SPLIT_DATE).toordinal())
    eq_tr, eq_oos = vr.equity(train, span_tr), vr.equity(oos, span_oos)
    by_year = {}
    for s in sigs:
        by_year.setdefault(s["date"][:4], []).append(s["ret"])
    reasons = {}
    for s in oos:
        reasons[s["reason"]] = reasons.get(s["reason"], 0) + 1
    rec = dict(cell=cell, n=len(sigs), n_train=len(train), n_oos=len(oos), full_a=full_a, train_gate=tr_gate, train_a=tr_a, oos_a=oos_a,
               train_b=tr_b, oos_b=oos_b, b_excluded=dict(train=ex_tr, oos=ex_oos),
               window_b=dict(train=win_tr, oos=win_oos),
               stress={f"{f:.3f}": mean_at_fee(oos_mean, f) for f in STRESS_FEES},
               equity=dict(train=eq_tr, oos=eq_oos),
               by_year={y: dict(n=len(v), mean=st.mean(v)) for y, v in sorted(by_year.items())},
               oos_reasons=reasons, sigs_oos=[dict(sym=s["sym"], date=s["date"], ret=s["ret"], reason=s["reason"]) for s in oos])
    return rec


# ── 풀 ───────────────────────────────────────────────────────────────────────────────────
def pool_with_dates(oc, idx):
    out = []
    for s, i in idx:
        r = oc.ret(s, i)
        if r is not None:
            out.append((oc.rows_by[s][i]["date"], r))
    return out


def _f(v, w=8):
    return f"{'n/a':>{w}}" if v is None else f"{v*100:>+{w-1}.2f}%"


def _p(v):
    return "  n/a" if v is None else f"{v:.3f}"


# ── D4: 실거래 행 (읽기 전용) ─────────────────────────────────────────────────────────────
def live_rows():
    try:
        import supabase_client as sc
        if not sc.available():
            return None
        cli = sc.get_client("service") if __import__("os").environ.get("SUPABASE_SERVICE_KEY") else sc.get_client("anon")
        tr = cli.table("trades").select("*").limit(2000).execute().data or []
    except Exception as e:
        print(f"  [D4] Supabase 조회 생략: {str(e)[:80]}")
        return None
    out = {}
    for t in tr:
        live = bool(t.get("live_mode")) or str(t.get("method", "")).upper().endswith("LIVE")
        if not live:
            continue
        k = f"{t.get('pattern')}|{t.get('direction')}"
        ret = (t.get("return_pct") or 0) / 100.0
        d = out.setdefault(k, dict(n=0, rets=[], stops=0, first=None, last=None))
        d["n"] += 1; d["rets"].append(ret); d["stops"] += (t.get("exit_reason") == "stop")
        ed = t.get("entry_date")
        if ed:
            d["first"] = min(d["first"] or ed, ed); d["last"] = max(d["last"] or ed, ed)
    for k, d in out.items():
        d["mean"] = st.mean(d["rets"]) if d["rets"] else None
        d["stop_share"] = d["stops"] / d["n"] if d["n"] else None
        d.pop("rets")
    return out


# ── 메인 ─────────────────────────────────────────────────────────────────────────────────
def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    tfs = argv[argv.index("--tf") + 1].split(",") if "--tf" in argv else ["1d", "4h"]
    syms = va._syms()
    print(f"확인 프레임 v4 — 3중 대조 | split {SPLIT_DATE} | B 풀 같은 코인·월·레짐·TF·방향·진입가능봉(>= {B_MIN_POOL}) "
          f"| 월 클러스터 부트 {BOOT_N} | Holm | 비용 스트레스 {STRESS_FEES} (필수 {STRESS_REQUIRED}) | 엣지 여유 {EDGE_MARGIN*100:.2f}%p "
          f"| DEPLOY_ON_PASS={DEPLOY_ON_PASS}")
    if "--no-fetch" not in argv:
        va.fetch(syms, tfs)
    rows_1d = va.load_tf(syms, "1d", long=True)
    regmap = rs.build_regime_map(rows_by=rows_1d)
    ranked = turnover_rank(rows_1d)
    cohort_syms = {"top30": [s for s in ranked[:30]], "all": list(rows_1d), "majors": [s for s in MAJORS if s in rows_1d]}
    first_1d = min(r["date"] for rows in rows_1d.values() for r in rows)
    last_1d = max(r["date"] for rows in rows_1d.values() for r in rows)
    print(f"[data] 1d {len(rows_1d)}종목 {first_1d}~{last_1d} | 레짐 {min(regmap)}~{max(regmap)} | top30 {cohort_syms['top30'][:10]}…")

    rows_tf = {"1d": rows_1d}
    if "4h" in tfs:
        rows_tf["4h"] = va.load_tf(syms, "4h")
        f4 = min(r["date"] for rows in rows_tf["4h"].values() for r in rows)
        print(f"[data] 4h {len(rows_tf['4h'])}종목 {f4}~")

    oc_cache, pool_cache = {}, {}

    def oc_for(tf, direction):
        k = (tf, direction)
        if k not in oc_cache:
            oc_cache[k] = Outcomes(tf, rows_tf[tf], regmap, direction)
        return oc_cache[k]

    def pool_for(tf, cohort, regime, direction):
        k = (tf, cohort, regime, direction)
        if k not in pool_cache:
            oc = oc_for(tf, direction)
            cs = set(s for s in cohort_syms[cohort] if s in rows_tf[tf])
            idx, _ = vr.build_context(tf, {s: rows_tf[tf][s] for s in cs}, {cohort: cs}, regmap)
            t0 = time.time()
            pool_cache[k] = pool_with_dates(oc, idx[(cohort, regime)])
            print(f"  [pool A] {tf}/{cohort}/{regime}/{direction} {len(pool_cache[k])}건 ({time.time()-t0:.0f}s)", flush=True)
        return pool_cache[k]

    results = {}
    for cell in CELLS:
        if cell["tf"] not in tfs:
            continue
        tf, coh, g, d = cell["tf"], cell["cohort"], cell["regime"], cell["direction"]
        oc = oc_for(tf, d)
        cs = [s for s in cohort_syms[coh] if s in rows_tf[tf]]
        t0 = time.time()
        pool = pool_for(tf, coh, g, d)
        first_tf = first_1d if tf == "1d" else min(r["date"] for rows in rows_tf[tf].values() for r in rows)
        rec = run_cell(cell, oc, cs, pool, first_tf, last_1d)
        results[cell["cid"]] = rec
        full_a, tr_gate, tr_a, oos_a, tr_b, oos_b = rec["full_a"], rec["train_gate"], rec["train_a"], rec["oos_a"], rec["train_b"], rec["oos_b"]
        ex_tr, ex_oos, win_tr, win_oos = rec["b_excluded"]["train"], rec["b_excluded"]["oos"], rec["window_b"]["train"], rec["window_b"]["oos"]
        eq_tr, eq_oos, reasons, oos_mean = rec["equity"]["train"], rec["equity"]["oos"], rec["oos_reasons"], oos_a["mean"]
        print(f"\n[{cell['cid']}] {tf}/{coh}/{d} ({cell['status']}) n={rec['n']} train {rec['n_train']} / OOS {rec['n_oos']} ({time.time()-t0:.0f}s)")
        print(f"  A full  mean {_f(full_a['mean'])} 승률 {(full_a['win'] or 0)*100:3.0f}% 엣지 {_f(full_a['edge'])} bp {_p(full_a['boot_p'])}")
        print(f"  A train mean {_f(tr_a['mean'])} 승률 {(tr_a['win'] or 0)*100:3.0f}% 엣지 {_f(tr_a['edge'])} bp {_p(tr_a['boot_p'])} | 게이트 v2 {tr_gate['verdict']} {tr_gate['reason']}")
        print(f"  A OOS   mean {_f(oos_a['mean'])} 승률 {(oos_a['win'] or 0)*100:3.0f}% 엣지 {_f(oos_a['edge'])} bp {_p(oos_a['boot_p'])} | 비용 0.4% {_f(mean_at_fee(oos_mean, 0.004))} 0.6% {_f(mean_at_fee(oos_mean, 0.006))} | 청산 {reasons}")
        for nm, cb, ex in (("B train", tr_b, ex_tr), ("B OOS  ", oos_b, ex_oos)):
            print(f"  {nm} n={cb['n']} 월 {cb['months']} 코인월 {cb['coin_months']} 제외 {ex} | n가중 {_f(cb['nw'])} 동등월 {_f(cb['eq_month'])} 동등코인월 {_f(cb['eq_coin_month'])} "
                  f"| p월 {_p(cb['p_nw'])}/{_p(cb['p_eq_month'])}/{_p(cb['p_eq_coin_month'])} p코인월 {_p(cb['p_nw_coinmonth'])} CI {cb['ci_nw']}")
        print(f"  D3 ±{WINDOW_BARS}봉 창: train {_f(win_tr['nw'])} p {_p(win_tr['p_nw'])} | OOS {_f(win_oos['nw'])} p {_p(win_oos['p_nw'])}")
        yr = " ".join(f"{y}:{v['mean']*100:+.1f}%(n{v['n']})" for y, v in results[cell['cid']]["by_year"].items())
        print(f"  연도별 {yr}")
        if eq_tr: print(f"  자산곡선(진단) train CAGR {_f(eq_tr['cagr'])} MDD {_f(eq_tr['mdd'])} Calmar {eq_tr['calmar']:.2f}" + (f" | OOS CAGR {_f(eq_oos['cagr'])} MDD {_f(eq_oos['mdd'])} Calmar {eq_oos['calmar']:.2f}" if eq_oos else ""))

    # Holm — OOS 검정이 계산된 주 셀 전체
    fam = {k: v["oos_b"]["p_nw"] for k, v in results.items()
           if v["oos_a"]["n"] >= OOS_MIN_N and v["oos_b"]["months"] >= B_MIN_MONTHS and v["oos_b"]["p_nw"] is not None}
    adj = holm(fam)
    print("\n" + "=" * 120)
    print(f"[판정] Holm 가족 m={len(fam)} | 규칙: REJECTED(전체 A 음수) / INCONCLUSIVE(OOS n<{OOS_MIN_N} 또는 월<{B_MIN_MONTHS}) / UNCONFIRMED_SHADOW / CONFIRMED")
    summary = {}
    for k, v in results.items():
        vd, fails = verdict(v["full_a"], v["train_gate"]["verdict"] == "PASSED", v["train_b"], v["oos_a"], v["oos_b"], adj.get(k), v["oos_a"]["mean"])
        v["p_holm"] = adj.get(k); v["verdict"] = vd; v["fails"] = fails
        summary[k] = dict(verdict=vd, fails=fails, status=v["cell"]["status"], n=v["n"], oos_n=v["oos_a"]["n"],
                          oos_b_nw=v["oos_b"]["nw"], p_raw=v["oos_b"]["p_nw"], p_holm=adj.get(k))
        act = "주문 무변경(보고만)" if v["cell"]["status"] in ("deployed", "observation") else "그림자 유지(사용자 결정)"
        print(f"  {k:<36} {v['cell']['status']:<11} **{vd:<18}** {'/'.join(fails) or 'ok':<40} OOS n={v['oos_a']['n']:>4} B {_f(v['oos_b']['nw'])} p {_p(v['oos_b']['p_nw'])} Holm {_p(adj.get(k))} → {act}")

    # ── 진단 블록 ────────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 120)
    print("[D1] 같은 달 무작위 기대값 — top30 롱 무작위(A 풀)를 레짐별·기간별로. 월 클러스터 p = P(<=0). '레짐이 조건부 기대값 라우터인가'")
    diag = dict(D1={}, D2={}, D4=None)
    for g in REGIMES:
        pr = pool_for("1d", "top30", g, "long")
        for per, cond in (("train", lambda dt: dt < SPLIT_DATE), ("oos", lambda dt: dt >= SPLIT_DATE)):
            edges = [dict(sym="_", month=dt[:7], edge=r) for dt, r in pr if cond(dt)]
            cb = cluster_boot(edges) if edges else None
            months_pos = None
            if edges:
                bym = {}
                for e in edges:
                    bym.setdefault(e["month"], []).append(e["edge"])
                months_pos = sum(1 for v in bym.values() if st.mean(v) > 0) / len(bym)
            diag["D1"][f"{g}|{per}"] = dict(n=len(edges), nw=(cb["nw"] if cb else None), eq_month=(cb["eq_month"] if cb else None),
                                           p_nw=(cb["p_nw"] if cb else None), months=(cb["months"] if cb else 0), months_pos=months_pos,
                                           ci=(cb["ci_nw"] if cb else None))
            r_ = diag["D1"][f"{g}|{per}"]
            print(f"  {g:<15} {per:<5} n={r_['n']:>6} 월 {r_['months']:>3} | n가중 {_f(r_['nw'])} 동등월 {_f(r_['eq_month'])} p {_p(r_['p_nw'])} 양수월 {(r_['months_pos'] or 0)*100:3.0f}% CI {r_['ci']}")
    for per in ("train", "oos"):
        b = diag["D1"].get(f"bull_btc|{per}", {}); nb = [diag["D1"].get(f"{g}|{per}", {}) for g in ("bull_altseason", "bear", "sideways")]
        if b.get("nw") is not None:
            others = [x["nw"] for x in nb if x.get("nw") is not None]
            print(f"  bull vs 비-bull ({per}): bull {_f(b['nw'])} vs 비-bull 평균 {_f(st.mean(others) if others else None)}")

    print("\n[D2] BTC 3개월 forward return 을 레짐 라벨별로 (일 단위, 겹침 있음) — 라벨이 bear/sideways 와 분리되는가")
    mk = dg.Market(regmap, rows_1d)
    for per, cond in (("train", lambda dt: dt < SPLIT_DATE), ("oos", lambda dt: dt >= SPLIT_DATE)):
        for g in REGIMES:
            f3 = [mk.btc_fwd(dt, 91) for dt in sorted(regmap) if regmap[dt] == g and cond(dt)]
            f3 = [x for x in f3 if x is not None]
            rec = dict(days=len(f3), fwd3m=(st.mean(f3) if f3 else None), pos=(sum(1 for x in f3 if x > 0) / len(f3) if f3 else None))
            diag["D2"][f"{g}|{per}"] = rec
            print(f"  {per:<5} {g:<15} 일 {rec['days']:>5} | fwd3m {_f(rec['fwd3m'])} 양수 {(rec['pos'] or 0)*100:3.0f}%")

    print("\n[D4] 배포 후 실거래 행 (Supabase trades live, 읽기 전용)")
    lr = live_rows()
    diag["D4"] = lr
    if lr:
        for k, d_ in sorted(lr.items()):
            print(f"  {k:<28} n={d_['n']:>3} mean {_f(d_['mean'])} 손절 {(d_['stop_share'] or 0)*100:3.0f}% {d_['first']}~{d_['last']}")
    else:
        print("  (자료 없음 또는 조회 생략)")

    out = dict(frame="v4", split=SPLIT_DATE, frozen=dict(fee_base=FEE_BASE, stress=STRESS_FEES, stress_required=STRESS_REQUIRED, edge_margin=EDGE_MARGIN,
                                                           boot_n=BOOT_N, alpha=ALPHA, oos_min_n=OOS_MIN_N, b_min_pool=B_MIN_POOL, b_min_months=B_MIN_MONTHS, window=WINDOW_BARS),
               deploy_on_pass=DEPLOY_ON_PASS, holm_family=list(fam), results=results, summary=summary, diag=diag)
    json.dump(out, open("_guard_v4.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print("\n[저장] _guard_v4.json — 실거래 반영 없음(DEPLOY_ON_PASS=False)")
    print("RESULT_JSON: " + json.dumps(dict(frame="v4", summary={k: dict(verdict=v["verdict"], fails=v["fails"], oos_n=v["oos_n"], p_holm=v["p_holm"]) for k, v in summary.items()}), ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
