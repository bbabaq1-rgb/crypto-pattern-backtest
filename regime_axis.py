"""
regime_axis.py — 레짐 '추가 축' 1단계 진단 (2026-09-04 사전 등록).

두 출처를 합쳐 한 번에 잰다.
  (A) `regime_factor_catalog.md` — 방향 축 하나에 **변동성 축·추세 유무 축**을 더해
      "횡보·저변동" 셀을 걸러내라는 제안.
  (B) 사용자 제안 — 알트의 **BTC 상승/하락 베타 비대칭**(β⁺−β⁻)을 알트 강세/약세 축으로.

**먼저 레포 이력과 대조해 이미 끝난 것을 뺐다.**
  · β⁺−β⁻ 는 `relative_strength.compute_capture` 의 cap_score(up_capture − down_capture)와
    같은 정보다. 2026-07-08 에 이미 시험 — **종목 필터로는 기각**(cap<0 종목이 +11.47% vs
    cap>0 +7.87%. 반전 패턴 눌림목 매수라 약한 종목이 더 과매도되어 반등이 크다),
    **시장 평균 avg_cap 은 채택**되어 지금 실거래 사이징 오버레이로 돌고 있다.
    그래서 avg_cap 은 새 후보가 아니라 **비교 기준**으로 넣는다.
  · '조건부 상대수익(BTC 상승일 초과수익)' 은 up_capture 의 분자와 사실상 같아 제외.
  · 롤링 베타 단독은 RS 와 상관이 높고, RS 는 레짐 통제 후 엣지 소멸(2026-07-08).
  · regime_alt 의 breadth 는 **200일선 상회 비율**이라 아래 alt_breadth(BTC 초과 비율)와
    다른 지표다 — 그쪽은 라벨러 후보로 기각됐지만 이건 미시험.

축 (모두 진입 봉까지만 보고 계산 — 룩어헤드 없음)
  adx        : ADX(14). 방향이 아니라 **추세 유무**. 카탈로그 B+.
  er         : Kaufman 효율비(20) = |순변화| / Σ|봉변화|. 낮으면 횡보. 카탈로그 B.
  volpct     : BTC 20일 실현변동성의 직전 365일 백분위 — 변동성 축. 카탈로그 A-.
  alt_breadth: 최근 90일 수익률이 BTC 를 초과한 유니버스 종목 비율(Altcoin Season Index 정의).
  beta_slope : 횡단면 베타 팩터 수익률 — 매일 (종목 60일 베타, 당일 수익률) 회귀 기울기의
               20일 평균. 양수면 고베타가 이기는 국면 = 리스크 선호. 완전 미시험.
  avg_cap    : 유니버스 평균 cap_score — **현행 채택 규칙, 비교 기준**.

사전 등록 판정 (실행 전 고정) — 이번 실행은 **1단계(축이 실재하는가)까지만** 한다.
  배포 7패턴의 방식D 거래를 진입 시점 축 값의 3분위로 나눠,
   A) 최상 3분위 평균 − 최하 3분위 평균의 부트스트랩 양측 p < 0.05
   B) 3분위 평균이 **단조**(증가 또는 감소) — 노이즈가 아니라 정도의 문제여야 한다
   C) 최하(또는 최상, 부호에 따라) 불리 3분위의 평균 < 0 — 실제로 걸러낼 구간이 있어야 한다
  A∧B∧C 를 만족한 축만 **2단계(진입 필터·조건부 손절폭 arm) 사전등록 대상**으로 기록한다.
  2단계는 이번에 실행하지 않는다.

  **왜 진단부터인가**: 지금까지 진입 필터 arm(F_slow/F_fast/F_bear, method_m·method_q)은
  전부 손해였다 — bear 진입 롱이 가장 수익 좋은 부분집합이라서. 축이 실제로 성과를 가르는지
  먼저 보지 않고 필터부터 만들면 같은 실패를 반복한다. `regime_factor_catalog.md` 7장 1번도
  같은 요구다("레짐이 실제로 성과를 가르는가 — 다르지 않으면 그 레짐 변수는 장식입니다").

실거래 무변경. 출력 regime_axis.json + RESULT_JSON.
실행: python regime_axis.py [--no-fetch] [--universe]
"""
import importlib
import json
import math
import random
import statistics as st
import sys

import detlib
import method_s as ms
import method_t as mt
import regime_switch as rs
import relative_strength as rsx

AXES = ["adx", "er", "volpct", "alt_breadth", "beta_slope", "avg_cap"]
NEW_AXES = ["adx", "er", "volpct", "alt_breadth", "beta_slope"]   # avg_cap 은 기준
ADX_P, ER_P = 14, 20
VOL_LB, VOL_PCT_WIN = 20, 365
BREADTH_LB = 90            # Altcoin Season Index 관례
BETA_LB, BETA_SMOOTH = 60, 20
BOOT_N, BOOT_SEED = 2000, 11
REGMAP = {}


# ── 축 계산 (전부 인과적) ──────────────────────────────────────────────────
def adx_series(rows, period=ADX_P):
    """Wilder ADX. 값이 확정되는 인덱스에만 채우고 그 이전은 None (인과적)."""
    n = len(rows)
    out = [None] * n
    if n < period * 2 + 2:
        return out
    tr, pdm, ndm = [], [], []
    for i in range(1, n):
        h, l = rows[i]["h"], rows[i]["l"]
        ph, pl, pc = rows[i-1]["h"], rows[i-1]["l"], rows[i-1]["c"]
        tr.append(max(h - l, abs(h - pc), abs(l - pc)))
        up, dn = h - ph, pl - l
        pdm.append(up if (up > dn and up > 0) else 0.0)
        ndm.append(dn if (dn > up and dn > 0) else 0.0)
    atr, ap, an = sum(tr[:period]), sum(pdm[:period]), sum(ndm[:period])
    dx_list, adx_val = [], None
    for k in range(period, len(tr)):
        atr = atr - atr / period + tr[k]
        ap = ap - ap / period + pdm[k]
        an = an - an / period + ndm[k]
        if atr <= 0:
            dx = 0.0
        else:
            pdi, ndi = 100 * ap / atr, 100 * an / atr
            tot = pdi + ndi
            dx = 100 * abs(pdi - ndi) / tot if tot > 0 else 0.0
        dx_list.append(dx)
        if len(dx_list) == period:
            adx_val = st.mean(dx_list)
        elif len(dx_list) > period:
            adx_val = (adx_val * (period - 1) + dx) / period
        if adx_val is not None:
            out[k + 1] = adx_val          # tr[k] 는 rows[k+1] 의 봉
    return out


def er_series(rows, period=ER_P):
    """Kaufman 효율비: |c_i - c_{i-p}| / Σ|c_j - c_{j-1}|. 0~1, 낮으면 횡보."""
    c = [r["c"] for r in rows]
    out = [None] * len(rows)
    for i in range(period, len(rows)):
        path = sum(abs(c[j] - c[j - 1]) for j in range(i - period + 1, i + 1))
        out[i] = abs(c[i] - c[i - period]) / path if path > 0 else None
    return out


def _rets(cs):
    return [(cs[i] - cs[i - 1]) / cs[i - 1] if cs[i - 1] else 0.0 for i in range(1, len(cs))]


def btc_vol_pct(btc_rows):
    """date -> BTC 20일 실현변동성의 직전 365일 백분위 (0~1). 인과적."""
    c = [r["c"] for r in btc_rows]
    rt = _rets(c)
    vols = [None] * len(btc_rows)
    for i in range(VOL_LB, len(btc_rows)):
        w = rt[i - VOL_LB:i]
        vols[i] = st.pstdev(w) if len(w) >= 2 else None
    out = {}
    for i, r in enumerate(btc_rows):
        v = vols[i]
        if v is None:
            continue
        hist = [x for x in vols[max(0, i - VOL_PCT_WIN):i] if x is not None]
        if len(hist) < 60:
            continue
        less = sum(1 for x in hist if x < v)
        eq = sum(1 for x in hist if x == v)
        out[r["date"]] = (less + 0.5 * eq) / len(hist)
    return out


def alt_breadth_series(rows_by_sym, btc_rows, lb=BREADTH_LB):
    """date -> 최근 lb봉 수익률이 BTC 를 초과한 종목 비율. Altcoin Season Index 정의."""
    bc = {r["date"]: r["c"] for r in btc_rows}
    bdates = [r["date"] for r in btc_rows]
    bidx = {d: i for i, d in enumerate(bdates)}
    num, den = {}, {}
    for sym, rows in rows_by_sym.items():
        if sym == "BTC":
            continue
        for i in range(lb, len(rows)):
            d = rows[i]["date"]
            j = bidx.get(d)
            if j is None or j < lb:
                continue
            p0, p1 = rows[i - lb]["c"], rows[i]["c"]
            b0, b1 = btc_rows[j - lb]["c"], btc_rows[j]["c"]
            if p0 <= 0 or b0 <= 0:
                continue
            den[d] = den.get(d, 0) + 1
            num[d] = num.get(d, 0) + ((p1 / p0 - 1) > (b1 / b0 - 1))
    return {d: num.get(d, 0) / den[d] for d in den if den[d] >= 10}


def beta_slope_series(rows_by_sym, btc_rows, lb=BETA_LB, smooth=BETA_SMOOTH):
    """
    date -> 횡단면 베타 팩터 수익률의 smooth일 평균.
    매일 (종목 lb일 베타, 당일 수익률) 단순회귀 기울기 → 고베타가 이긴 날은 양수.
    베타는 **전일까지의 데이터**로만 추정(당일 수익률과 겹치지 않게).
    """
    bdates = [r["date"] for r in btc_rows]
    bidx = {d: i for i, d in enumerate(bdates)}
    brets = [None] + _rets([r["c"] for r in btc_rows])
    daily = {}
    for sym, rows in rows_by_sym.items():
        if sym == "BTC":
            continue
        cs = [r["c"] for r in rows]
        rt = [None] + _rets(cs)
        for i in range(lb + 1, len(rows)):
            d = rows[i]["date"]
            j = bidx.get(d)
            if j is None or j < lb + 1 or brets[j] is None or rt[i] is None:
                continue
            ar = [x for x in rt[i - lb:i] if x is not None]
            br = [x for x in brets[max(0, j - lb):j] if x is not None]
            m = min(len(ar), len(br))
            if m < lb // 2:
                continue
            ar, br = ar[-m:], br[-m:]
            vb = st.pvariance(br)
            if vb <= 0:
                continue
            mb, ma_ = st.mean(br), st.mean(ar)
            beta = sum((br[k] - mb) * (ar[k] - ma_) for k in range(m)) / m / vb
            daily.setdefault(d, []).append((beta, rt[i]))
    raw = {}
    for d, pairs in daily.items():
        if len(pairs) < 10:
            continue
        xs = [p[0] for p in pairs]; ys = [p[1] for p in pairs]
        vx = st.pvariance(xs)
        if vx <= 0:
            continue
        mx, my = st.mean(xs), st.mean(ys)
        raw[d] = sum((xs[k] - mx) * (ys[k] - my) for k in range(len(xs))) / len(xs) / vx
    ds = sorted(raw)
    out = {}
    for i, d in enumerate(ds):
        w = [raw[x] for x in ds[max(0, i - smooth + 1):i + 1]]
        out[d] = st.mean(w)
    return out


def avg_cap_series(rows_by_sym, btc_rows):
    """date -> 유니버스 평균 cap_score (현행 채택 규칙, 비교 기준). 인과적."""
    bidx = {r["date"]: i for i, r in enumerate(btc_rows)}
    acc = {}
    step = 5      # cap_score 는 무거워서 5봉 간격 계산 후 앞으로 채움(진단용 근사)
    for sym, rows in rows_by_sym.items():
        if sym == "BTC":
            continue
        for i in range(rsx.CAPTURE_N + 1, len(rows), step):
            d = rows[i]["date"]
            if d not in bidx:
                continue
            try:
                c = rsx.compute_capture(rows, btc_rows, idx=i, symbol=sym)
            except Exception:
                continue
            if c.get("unstable"):
                continue
            acc.setdefault(d, []).append(c["cap_score"])
    raw = {d: st.mean(v) for d, v in acc.items() if len(v) >= 5}
    ds = sorted(raw)
    out, cur = {}, None
    alld = sorted({r["date"] for rows in rows_by_sym.values() for r in rows})
    k = 0
    for d in alld:
        while k < len(ds) and ds[k] <= d:
            cur = raw[ds[k]]; k += 1
        if cur is not None:
            out[d] = cur
    return out


# ── 3분위 진단 ─────────────────────────────────────────────────────────────
def terciles(vals):
    s = sorted(vals)
    n = len(s)
    return s[n // 3], s[2 * n // 3]


def boot_diff_p(a, b, n=BOOT_N, seed=BOOT_SEED):
    """두 표본 평균차이의 부트스트랩 양측 p (차이의 부호가 뒤집히는 비율 x2)."""
    if len(a) < 2 or len(b) < 2:
        return 1.0
    rng = random.Random(seed)
    obs = st.mean(a) - st.mean(b)
    cnt = 0
    for _ in range(n):
        ra = sum(a[rng.randrange(len(a))] for _ in range(len(a))) / len(a)
        rb = sum(b[rng.randrange(len(b))] for _ in range(len(b))) / len(b)
        if (ra - rb) * (1 if obs >= 0 else -1) <= 0:
            cnt += 1
    return min(1.0, 2 * cnt / n)


def diagnose(axis, trades):
    """trades: [(ret, axis_val)]. 3분위 진단 + 사전 기준 A/B/C."""
    xs = [t for t in trades if t[1] is not None]
    if len(xs) < 60:
        return dict(n=len(xs), skip="표본 부족(<60)")
    lo_c, hi_c = terciles([t[1] for t in xs])
    lo = [t[0] for t in xs if t[1] <= lo_c]
    mid = [t[0] for t in xs if lo_c < t[1] <= hi_c]
    hi = [t[0] for t in xs if t[1] > hi_c]
    if min(len(lo), len(mid), len(hi)) < 15:
        return dict(n=len(xs), skip="분위 표본 부족")
    ms_ = [st.mean(lo), st.mean(mid), st.mean(hi)]
    mono = (ms_[0] <= ms_[1] <= ms_[2]) or (ms_[0] >= ms_[1] >= ms_[2])
    p = boot_diff_p(hi, lo)
    worst = min(ms_)
    a = p < 0.05
    c = worst < 0
    return dict(n=len(xs), cuts=[lo_c, hi_c],
                tercile=[dict(n=len(lo), mean=ms_[0], median=st.median(lo)),
                         dict(n=len(mid), mean=ms_[1], median=st.median(mid)),
                         dict(n=len(hi), mean=ms_[2], median=st.median(hi))],
                spread=ms_[2] - ms_[0], boot_p=p,
                A_sig=a, B_monotone=mono, C_neg_tail=c,
                real=bool(a and mono and c))


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    ms.UNIVERSE_MODE = "--universe" in argv
    syms = ms.symbols()
    print(f"[표본] {len(syms)}종목 ({'유니버스 80' if ms.UNIVERSE_MODE else '메이저'})")
    if "--no-fetch" not in argv:
        ms.ensure_data(mt.FETCH_DAYS, syms)
    global REGMAP
    REGMAP = rs.build_regime_map()
    mt.REGMAP = REGMAP

    rows_by = {}
    for s in syms:
        try:
            rows_by[s] = detlib.load_ohlcv(s, "1d")
        except (FileNotFoundError, RuntimeError):
            continue
    btc = rows_by.get("BTC")
    if not btc:
        print("BTC 데이터 없음"); return
    print(f"[축] 계산 중 — adx/er(종목별), volpct/alt_breadth/beta_slope/avg_cap(시장)", flush=True)
    mkt = dict(volpct=btc_vol_pct(btc),
               alt_breadth=alt_breadth_series(rows_by, btc),
               beta_slope=beta_slope_series(rows_by, btc),
               avg_cap=avg_cap_series(rows_by, btc))
    for k, v in mkt.items():
        print(f"  {k}: {len(v)}일", flush=True)

    per_axis = {a: [] for a in AXES}
    for label, direction, detmod, oppmod, tf in mt.PATS:
        mod = importlib.import_module(detmod)
        opp = importlib.import_module(oppmod) if oppmod else None
        n = 0
        for sym in syms:
            rows = rows_by.get(sym) if tf == "1d" else None
            if rows is None:
                try:
                    rows = detlib.load_ohlcv(sym, tf)
                except (FileNotFoundError, RuntimeError):
                    continue
            if len(rows) < 60:
                continue
            adx = adx_series(rows)
            er = er_series(rows)
            opp_set = set(opp.detect(rows)) if opp else set()
            for si in mod.detect(rows):
                if si + 1 >= len(rows):
                    continue
                ret, hold, reason = mt.outcome_d(rows, si, direction, opp_set)
                d = rows[si]["date"]
                per_axis["adx"].append((ret, adx[si]))
                per_axis["er"].append((ret, er[si]))
                for k in ("volpct", "alt_breadth", "beta_slope", "avg_cap"):
                    per_axis[k].append((ret, mkt[k].get(d)))
                n += 1
        print(f"  [{label}] {n}건", flush=True)

    print("\n" + "=" * 118)
    print("레짐 추가 축 1단계 진단 — 배포 7패턴 방식D 거래를 진입 시점 축 값 3분위로 분할")
    print("=" * 118)
    print(f"  {'축':<12}{'n':>6}{'하위3분위':>11}{'중간':>10}{'상위3분위':>11}{'스프레드':>10}"
          f"{'boot_p':>9}  {'A유의':>6}{'B단조':>6}{'C음수꼬리':>9}  판정")
    print("  " + "-" * 114)
    out = {}
    for a in AXES:
        r = diagnose(a, per_axis[a])
        out[a] = r
        if r.get("skip"):
            print(f"  {a:<12}{r['n']:>6}  {r['skip']}")
            continue
        t = r["tercile"]
        tag = "**축 실재**" if r["real"] else "장식(기각)"
        base = "  <- 현행 채택 규칙" if a == "avg_cap" else ""
        print(f"  {a:<12}{r['n']:>6}{t[0]['mean']*100:>+10.2f}%{t[1]['mean']*100:>+9.2f}%"
              f"{t[2]['mean']*100:>+10.2f}%{r['spread']*100:>+9.2f}%{r['boot_p']:>9.3f}"
              f"  {'O' if r['A_sig'] else 'X':>6}{'O' if r['B_monotone'] else 'X':>6}"
              f"{'O' if r['C_neg_tail'] else 'X':>9}  {tag}{base}")

    real = [a for a in NEW_AXES if out.get(a, {}).get("real")]
    print(f"\n[사전 등록 판정] A(양측 boot_p<0.05) ∧ B(단조) ∧ C(불리 분위 평균<0) 전부 만족")
    if real:
        print(f"  축 실재: {real} → **2단계(진입 필터·조건부 손절폭) 사전등록 대상**. 이번엔 실행 안 함")
    else:
        print(f"  축 실재: 없음 → 2단계 없음. '레짐이 성과를 가르는가'에서 갈리지 않으면 장식이다")
    print(f"  참고: avg_cap(현행 채택) 판정 = {'실재' if out.get('avg_cap', {}).get('real') else '이 프레임에선 미검출'}"
          f" — 새 축은 이것 대비 개선이어야 의미가 있다")
    print("\n[유보] 유니버스 생존 편향 — 현재 살아있는 종목으로 과거를 계산한다(시점별 유니버스 없음).")
    print("       상폐 종목이 빠져 alt_breadth·beta_slope 가 낙관적으로 치우칠 수 있다.")

    json.dump(dict(config=dict(adx_p=ADX_P, er_p=ER_P, breadth_lb=BREADTH_LB,
                               beta_lb=BETA_LB, beta_smooth=BETA_SMOOTH,
                               n_symbols=len(syms), universe=ms.UNIVERSE_MODE),
                   axes=out, real=real),
              open("regime_axis.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("[저장] regime_axis.json")
    print("RESULT_JSON: " + json.dumps(dict(
        real=real,
        spread={a: round(out[a]["spread"], 5) for a in AXES if "spread" in out.get(a, {})},
        boot_p={a: out[a]["boot_p"] for a in AXES if "boot_p" in out.get(a, {})}),
        separators=(",", ":")))


if __name__ == "__main__":
    main()
