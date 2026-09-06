"""
diag_bull_phase.py — bull_btc 레짐 안에서 패턴 엣지가 시간에 따라 체계적으로 감소하는가? (진단 전용)
(2026-09-06, 사용자 사양 — "코드/판정 변경 없이 진단 실험만")

## 무엇을 재나

  1. 모든 bull_btc 패턴의 2023-01 이후 **월별** 성과 전수 (패턴 / 같은 달 무작위 진입 / 엣지)
  2. bull_btc 시작 후 경과 개월 0–2 / 3–5 / 6–8 / 9–11 / 12+ 별 패턴 vs 무작위 엣지
  3. 직전 bull_btc 종료 후 6개월 이내 재점등 vs 6개월 초과 신규 bull 별 같은 비교
  4. BTC 1년 고점 대비 낙폭 0~−10% / −10~−20% / ≤−20% 별 같은 비교
  5. 각 bull_btc 월의 BTC 3개월/6개월 forward return — 레짐 라벨의 실제 국면 품질
  6. 월별 표에 알트 시장 상태 병기 — ETH/BTC 월 변화, 알트 바스켓(SOL/ETH/XRP/ADA/AVAX/TRX) 30일 상대수익(레짐
     라벨러가 쓰는 BTC.D 프록시와 같은 정의). TOTAL3 는 이 레포에 없음(CoinGecko 유료) — 미제공.

**엣지 = 패턴 − 같은 조건(같은 달 / 같은 버킷 / 같은 코호트 / 같은 청산 방식D)의 무작위 진입.**
BTC 상승 자체를 패턴 능력으로 착각하지 않기 위한 핵심 대조. 무작위 진입 풀은 bull_btc 라벨 날짜의
전 봉에서 표집(상한 20000)하고, 각 버킷·달에는 그 조건에 속한 풀 표본만 쓴다.

## 하지 않는 것

  · 버킷 경계는 이 파일에 고정 — 결과를 본 뒤 바꾸지 않는다.
  · 필터 arm·채택 판정·실거래 반영 없음. 어떤 패턴도 제외·채택하지 않는다.
  · 최종 판정(패턴 문제 / BTC 레짐 문제 / 알트 레짐 문제 / 표본 부족)은 표를 근거로 보고서에서 한다.

실행: python diag_bull_phase.py [--no-fetch]      출력: _diag_bull_phase.json + 로그 표
"""
import importlib
import json
import math
import statistics as st
import sys
import time
from datetime import date

import detector_ma180_breakout as dm
import frame_v3 as fv
import regime_switch as rs
import validate_regime_split_all as va
import validate_revival as vr
from validate_regime_split import turnover_rank

G = "bull_btc"
DIRECTION = "long"
MONTH_FROM = "2023-01"
AGE_BUCKETS = [("0-2m", 0, 2), ("3-5m", 3, 5), ("6-8m", 6, 8), ("9-11m", 9, 11), ("12m+", 12, 10**9)]   # 경과 개월 = 일수//30
REIG_DAYS = 182                                                                                   # 6개월
DD_BUCKETS = [("0~-10%", -0.10, 0.0), ("-10~-20%", -0.20, -0.10), ("<=-20%", -10.0, -0.20)]         # (lo, hi]
DD_LB = 365
FWD = {"3m": 91, "6m": 182}
ALT_LB = 30
PRIORITY = ["double_bottom_1d", "ma180_decisive", "inverse_hs_1d", "three_soldiers_4h"]


def _det(mod, fn="detect"):
    return lambda rows, m=mod, f=fn: getattr(importlib.import_module(m), f)(rows)


# (cid, tf, 코호트 — 실거래와 같은 범위, detect)
PATTERNS = [
    ("double_bottom_1d",  "1d", "top30", _det("detector_double_bottom")),
    ("ma180_decisive",    "1d", "top30", lambda rows: dm.detect(rows, ma_n=180, filt="decisive")),
    ("inverse_hs_1d",     "1d", "top30", _det("detector_inverse_hs")),
    ("three_soldiers_4h", "4h", "all",   _det("detector_three_soldiers_4h")),
    ("triple_bottom_1d",  "1d", "top30", va._tb_causal),
    ("engulfing",         "1d", "top20", _det("detector_engulfing")),
    ("fvg",               "1d", "top30", _det("detector_fvg")),
]


def _ord(d):
    return date.fromisoformat(d).toordinal()


class Market:
    """bull_btc 에피소드·BTC 낙폭/수익·알트 상태 — 전부 날짜 기준 인과(당일 포함) 값. forward return 만 미래를 본다(국면 품질 검증용)."""

    def __init__(self, regmap, rows_1d):
        self.regmap = regmap
        self.eps = fv.episodes(regmap, G)
        self.starts = [_ord(a) for a, _ in self.eps]
        self.ends = [_ord(b) for _, b in self.eps]
        btc = rows_1d[rs.MARKET]
        self.btc_dates = [r["date"] for r in btc]
        self.btc_close = {r["date"]: r["c"] for r in btc}
        cl = [r["c"] for r in btc]
        self.dd = {}
        for i, r in enumerate(btc):
            hi = max(cl[max(0, i - DD_LB + 1):i + 1])
            self.dd[r["date"]] = cl[i] / hi - 1 if hi > 0 else None
        self.eth = {r["date"]: r["c"] for r in rows_1d.get("ETH", [])}
        self.alts = {a: {r["date"]: r["c"] for r in rows_1d.get(a, [])} for a in rs.ALTS}

    def ep_index(self, d):
        o = _ord(d)
        for k, (s, e) in enumerate(zip(self.starts, self.ends)):
            if s <= o <= e:
                return k
        return None

    def age_days(self, d):
        k = self.ep_index(d)
        return None if k is None else _ord(d) - self.starts[k]

    def age_bucket(self, d):
        a = self.age_days(d)
        if a is None:
            return None
        m = a // 30
        for name, lo, hi in AGE_BUCKETS:
            if lo <= m <= hi:
                return name
        return None

    def reignition(self, d):
        k = self.ep_index(d)
        if k is None:
            return None
        return "재점등(<=6m)" if (k > 0 and self.starts[k] - self.ends[k - 1] <= REIG_DAYS) else "신규(>6m)"

    def dd_bucket(self, d):
        x = self.dd.get(d)
        if x is None:
            return None
        for name, lo, hi in DD_BUCKETS:
            if lo < x <= hi:
                return name
        return None

    def _close_on_or_before(self, d):
        for x in reversed(self.btc_dates):
            if x <= d:
                return self.btc_close[x]
        return None

    def _close_on_or_after(self, d):
        for x in self.btc_dates:
            if x >= d:
                return self.btc_close[x], x
        return None, None

    def btc_fwd(self, d, days):
        c0 = self.btc_close.get(d) or self._close_on_or_before(d)
        target = date.fromordinal(_ord(d) + days).isoformat()
        c1, x = self._close_on_or_after(target)
        if c0 is None or c1 is None or x > self.btc_dates[-1]:
            return None
        if _ord(x) - _ord(target) > 5:
            return None
        return c1 / c0 - 1

    def ret_between(self, series, d0, d1):
        a, b = series.get(d0), series.get(d1)
        return (b / a - 1) if a and b else None

    def alt_rel_30d(self, d):
        """알트 바스켓 30일 수익 중앙값 − BTC 30일 수익 (레짐 라벨러의 BTC.D 프록시와 같은 정의, 부호 반대)."""
        d0 = date.fromordinal(_ord(d) - ALT_LB).isoformat()
        b = self.ret_between(self.btc_close, d0, d)
        if b is None:
            return None
        ar = [self.ret_between(m, d0, d) for m in self.alts.values()]
        ar = [x for x in ar if x is not None]
        return (st.median(ar) - b) if ar else None


# ── 통계 ──────────────────────────────────────────────────────────────────────
def welch_t(a, b):
    if len(a) < 2 or len(b) < 2:
        return None
    va_, vb = st.pvariance(a) * len(a) / (len(a) - 1), st.pvariance(b) * len(b) / (len(b) - 1)
    se = math.sqrt(va_ / len(a) + vb / len(b))
    return (st.mean(a) - st.mean(b)) / se if se > 0 else None


def spearman(x, y):
    n = len(x)
    if n < 4:
        return None
    def rk(v):
        order = sorted(range(n), key=lambda i: v[i]); r = [0] * n
        for i, idx in enumerate(order): r[idx] = i
        return r
    rx, ry = rk(x), rk(y)
    mx, my = st.mean(rx), st.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den > 0 else None


def cell(sig_rets, rnd_rets):
    n, rn = len(sig_rets), len(rnd_rets)
    m = st.mean(sig_rets) if sig_rets else None
    rm = st.mean(rnd_rets) if rnd_rets else None
    return dict(n=n, mean=m, win=(sum(1 for r in sig_rets if r > 0) / n if n else None), rnd_n=rn, rnd_mean=rm,
                edge=(m - rm) if (m is not None and rm is not None) else None, t=welch_t(sig_rets, rnd_rets))


def fmt(v, w=7, pct=True):
    if v is None:
        return f"{'n/a':>{w}}"
    return f"{v*100:>+{w-1}.2f}%" if pct else f"{v:>{w}.2f}"


# ── 데이터 ────────────────────────────────────────────────────────────────────
def pool_with_dates(tf, idx, rows_by, atrs, regmap):
    out = []
    for s, i in idx:
        rows = rows_by[s]
        lab = lambda j, rows=rows: regmap.get(rows[j]["date"])
        r = vr.live_outcome(tf, rows, i, DIRECTION, lab, atrs.get(s))
        if r is not None:
            out.append((rows[i]["date"], r[0]))
    return out


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    syms = va._syms()
    tfs = sorted({tf for _, tf, _, _ in PATTERNS})
    print(f"bull_btc 국면 위치 진단 | 패턴 {[p for p, _, _, _ in PATTERNS]} | 월별 {MONTH_FROM}~ | 경과개월 {[b[0] for b in AGE_BUCKETS]} "
          f"| 재점등 {REIG_DAYS}일 | 낙폭 {[b[0] for b in DD_BUCKETS]} | **진단 전용 — 필터·채택 없음**")
    if "--no-fetch" not in argv:
        va.fetch(syms, tfs)
    rows_1d = va.load_tf(syms, "1d", long=True)
    regmap = rs.build_regime_map(rows_by=rows_1d)
    mk = Market(regmap, rows_1d)
    print(f"[에피소드 {G}] {len(mk.eps)}개: " + ", ".join(f"{a}~{b}" for a, b in mk.eps))
    ranked = turnover_rank(rows_1d)
    cohort_syms = {"top20": ranked[:20], "top30": ranked[:30], "all": list(rows_1d)}

    ctx, res = {}, {}
    for cid, tf, coh, det in PATTERNS:
        key = (tf, coh)
        if key not in ctx:
            rows_by = rows_1d if tf == "1d" else va.load_tf(syms, tf)
            cs = set(s for s in cohort_syms[coh] if s in rows_by)
            pools, atrs = vr.build_context(tf, rows_by, {coh: cs}, regmap)
            t0 = time.time()
            pr = pool_with_dates(tf, pools[(coh, G)], rows_by, atrs, regmap)
            print(f"  [pool] {tf}/{coh} {G} {len(pr)}건 ({time.time()-t0:.0f}s)", flush=True)
            ctx[key] = dict(rows_by=rows_by, cs=cs, atrs=atrs, pool=pr)
        c = ctx[key]
        by_sym = vr.collect(tf, det, DIRECTION, {s: c["rows_by"][s] for s in c["cs"]}, c["atrs"], regmap)
        sigs = [x for v in by_sym.values() for x in v if x["regime"] == G]
        res[cid] = dict(tf=tf, cohort=coh, sigs=sigs, pool=c["pool"])
        print(f"  [collect] {cid:<18} {tf}/{coh} bull_btc 신호 {len(sigs)}건", flush=True)

    # ── 1·5·6. 월별 표 ────────────────────────────────────────────────────────
    months = sorted({d[:7] for d in regmap if regmap[d] == G and d[:7] >= MONTH_FROM})
    mrows = []
    print("\n" + "=" * 130)
    print(f"[1·5·6] bull_btc 월별 ({MONTH_FROM}~) — 시장 상태. 경과개월/재점등/낙폭은 그 달 첫 bull 일 기준, BTC 월수익은 월말 종가, fwd 는 월말→+91/+182일")
    print(f"{'월':<8}{'bull일':>6}{'경과':>7}{'재점등':>11}{'낙폭':>9}{'BTC월':>9}{'fwd3m':>9}{'fwd6m':>9}{'ETH/BTC월':>10}{'알트상대30d':>11}")
    for m in months:
        days = sorted(d for d in regmap if d[:7] == m and regmap[d] == G)
        d0 = days[0]
        mend = max(d for d in mk.btc_dates if d[:7] == m) if any(d[:7] == m for d in mk.btc_dates) else None
        prev = [d for d in mk.btc_dates if d < f"{m}-01"]
        pend = prev[-1] if prev else None
        btc_m = mk.ret_between(mk.btc_close, pend, mend) if pend and mend else None
        ethbtc_m = None
        if pend and mend and mk.eth.get(pend) and mk.eth.get(mend):
            ethbtc_m = (mk.eth[mend] / mk.btc_close[mend]) / (mk.eth[pend] / mk.btc_close[pend]) - 1
        row = dict(month=m, bull_days=len(days), age_m=(mk.age_days(d0) // 30 if mk.age_days(d0) is not None else None),
                   age_bucket=mk.age_bucket(d0), reig=mk.reignition(d0), dd=mk.dd.get(d0), dd_bucket=mk.dd_bucket(d0),
                   btc_m=btc_m, fwd3m=(mk.btc_fwd(mend, FWD["3m"]) if mend else None), fwd6m=(mk.btc_fwd(mend, FWD["6m"]) if mend else None),
                   ethbtc_m=ethbtc_m, alt_rel=(mk.alt_rel_30d(mend) if mend else None), patterns={})
        for cid, r in res.items():
            sr = [s["ret"] for s in r["sigs"] if s["date"][:7] == m]
            rr = [ret for d, ret in r["pool"] if d[:7] == m]
            row["patterns"][cid] = cell(sr, rr)
        mrows.append(row)
        print(f"{m:<8}{row['bull_days']:>6}{str(row['age_m']):>7}{row['reig'] or '-':>11}{fmt(row['dd'],9)}{fmt(btc_m,9)}{fmt(row['fwd3m'],9)}{fmt(row['fwd6m'],9)}{fmt(ethbtc_m,10)}{fmt(row['alt_rel'],11)}")

    for group, title in ((PRIORITY, "우선 4패턴"), ([p for p, _, _, _ in PATTERNS if p not in PRIORITY], "나머지")):
        print("\n" + "=" * 130)
        print(f"[1] 월별 패턴 성과 — {title}. 칸 = n / 패턴평균 / 엣지(패턴−같은달 무작위)")
        print(f"{'월':<8}" + "".join(f"{cid[:17]:>27}" for cid in group))
        for row in mrows:
            line = f"{row['month']:<8}"
            for cid in group:
                c = row["patterns"][cid]
                line += f"{c['n']:>5} {fmt(c['mean'],9)} {fmt(c['edge'],10)}  "
            print(line)

    # ── 2·3·4. 버킷 비교 (전 기간 2017~) ─────────────────────────────────────────
    buckets = {}
    specs = [("2_age", "경과개월", mk.age_bucket, [b[0] for b in AGE_BUCKETS]),
             ("3_reig", "재점등", mk.reignition, ["신규(>6m)", "재점등(<=6m)"]),
             ("4_dd", "BTC낙폭", mk.dd_bucket, [b[0] for b in DD_BUCKETS])]
    for key, title, fn, names in specs:
        buckets[key] = {}
        print("\n" + "=" * 130)
        print(f"[{key[0]}] {title} 버킷 — 전 기간(2017~). 칸 = n / 패턴평균 / 무작위평균 / 엣지 / t(Welch)")
        print(f"{'패턴':<18}" + "".join(f"{b:>22}" for b in names))
        for cid, r in res.items():
            buckets[key][cid] = {}
            line = f"{cid:<18}"
            for b in names:
                sr = [s["ret"] for s in r["sigs"] if fn(s["date"]) == b]
                rr = [ret for d, ret in r["pool"] if fn(d) == b]
                c = cell(sr, rr); buckets[key][cid][b] = c
                line += f"{c['n']:>4}{fmt(c['mean'],7)}{fmt(c['rnd_mean'],7)}{fmt(c['edge'],7)}{('t' + format(c['t'], '+.1f')) if c['t'] is not None else '':>7}"
            print(line)
        # 무작위 자체(레짐 품질)
        line = f"{'(무작위 n)':<18}"
        for b in names:
            rr = [ret for d, ret in res[PRIORITY[0]]["pool"] if fn(d) == b]
            line += f"{len(rr):>22}"
        print(line)

    # ── 5. 레짐 품질 요약 ─────────────────────────────────────────────────────────
    print("\n" + "=" * 130)
    print("[5] bull_btc 월의 BTC forward return — 라벨이 실제로 '상승 국면'을 가리키는가 (전 기간 bull 월, 버킷별)")
    allm = sorted({d[:7] for d in regmap if regmap[d] == G})
    qual = {}
    for key, title, fn, names in specs:
        qual[key] = {}
        print(f"  {title}:")
        for b in names:
            f3, f6 = [], []
            for m in allm:
                days = sorted(d for d in regmap if d[:7] == m and regmap[d] == G)
                if fn(days[0]) != b:
                    continue
                mend = max((d for d in mk.btc_dates if d[:7] == m), default=None)
                if not mend:
                    continue
                a, bb = mk.btc_fwd(mend, FWD["3m"]), mk.btc_fwd(mend, FWD["6m"])
                if a is not None: f3.append(a)
                if bb is not None: f6.append(bb)
            q = dict(months=len(f3), fwd3m=(st.mean(f3) if f3 else None), fwd3m_pos=(sum(1 for x in f3 if x > 0) / len(f3) if f3 else None),
                     fwd6m=(st.mean(f6) if f6 else None), fwd6m_pos=(sum(1 for x in f6 if x > 0) / len(f6) if f6 else None))
            qual[key][b] = q
            print(f"    {b:<14} 월 {q['months']:>3} | fwd3m {fmt(q['fwd3m'])} 양수 {(q['fwd3m_pos'] or 0)*100:3.0f}% | fwd6m {fmt(q['fwd6m'])} 양수 {(q['fwd6m_pos'] or 0)*100:3.0f}%")

    # ── 상관: 월별 엣지 vs BTC 월수익 ─────────────────────────────────────────────
    print("\n" + "=" * 130)
    print("[상관] 2023~ 월별 (n>=3 인 달): Spearman(패턴평균, BTC월수익) vs Spearman(엣지, BTC월수익) — 후자가 0 근처면 'BTC 강한 달 = 패턴 강한 달'일 뿐")
    corr = {}
    for cid in res:
        xs, ys, es = [], [], []
        for row in mrows:
            c = row["patterns"][cid]
            if c["n"] >= 3 and row["btc_m"] is not None and c["edge"] is not None:
                xs.append(row["btc_m"]); ys.append(c["mean"]); es.append(c["edge"])
        corr[cid] = dict(months=len(xs), rho_mean=spearman(xs, ys), rho_edge=spearman(xs, es))
        r_ = corr[cid]
        print(f"  {cid:<18} 달 {r_['months']:>2} | ρ(패턴평균,BTC) {fmt(r_['rho_mean'],6,False)} | ρ(엣지,BTC) {fmt(r_['rho_edge'],6,False)}")

    out = dict(regime=G, month_from=MONTH_FROM, episodes=mk.eps, buckets_frozen=dict(age=AGE_BUCKETS, reig_days=REIG_DAYS, dd=DD_BUCKETS),
               patterns={cid: dict(tf=r["tf"], cohort=r["cohort"], n=len(r["sigs"]), pool_n=len(r["pool"])) for cid, r in res.items()},
               monthly=mrows, buckets=buckets, regime_quality=qual, corr=corr)
    json.dump(out, open("_diag_bull_phase.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print("\n[저장] _diag_bull_phase.json  — 진단 전용, 필터·채택·실거래 반영 없음")


if __name__ == "__main__":
    main()
