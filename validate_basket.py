"""
validate_basket.py — 띠 규칙을 실제로 운용할 **바스켓 구성 규칙** (2026-09-07 사전 등록, 사용자 지시
"바스켓 구성 규칙(몇 종목, 어떤 기준, 재구성 주기)을 사전 등록해서 돌려줘").

## 배경
band_rule 시험(VIABLE 3/3)이 남긴 미해결 문제: **어느 코인에 이 규칙을 걸 것인가.** 그 시험은 거래대금 상위 20종목을
한 번 고정해 썼고 재구성도 없었다. 여기서 몇 종목 · 어떤 기준 · 어떤 주기가 나은지를 잰다.

## 사전 확률 — 결과를 보기 전에 기록한다
레포의 기존 연구는 **종목 선택이 잘 안 된다**고 반복해서 말했다: xsec_chars 24변수 중 rvol20 하나만 순위를 예측했고
그마저 평균수익은 음수 스프레드 · episode_profile 은 프로필 부호가 국면 세기에 따라 뒤집힘 · breadth_state 는 20셀 전부
방어 프로필 우위. 따라서 **가장 그럴듯한 결과는 '단순 거래대금 상위 N 을 쓰라'**이다. 그렇게 나와도 실패가 아니라 답이다.

## 동결 파라미터
  · 규칙: band_rule 확정판 — 진입가 P 고정, 손절 저가 <= P×(1−STOP 1%), 재매수 고가 >= P, 시장가 슬리피지 SLIP(0.141%,
    band_rule 에서 측정한 1시간 지연 δ), 수수료 편도 0.1%.
  · **풀**: 형성일 기준 직전 30봉 평균 거래대금 상위 POOL_N(60) — point-in-time(그날 알 수 있는 정보만).
  · **선택 기준 5**: liquidity(풀 상위 N, 베이스라인) / lowvol(rvol20 최저 N) / defensive(방어 프로필 점수 상위 N) /
    broad(넓은불장 프로필 점수 상위 N) / random(풀에서 무작위 N, RANDOM_DRAWS 200회, 시드 고정 — **귀무분포**).
    프로필 점수 정의·부호는 validate_breadth_state 의 BROAD/DEFENSIVE 를 그대로 가져온다(이미 고정된 값).
  · **N 격자**: 5 / 10 / 20 / 40.   · **재구성 주기**: none / quarterly(91일) / monthly(30일).
  · 재구성 시 전량 청산 후 그날 종가로 균등 재배분(수수료 양측). none 은 시작일 1회 형성.
  · 전 구간 2019-06-01 ~ 2026-09-06 연속 자산곡선. 주 지표 **Calmar = CAGR / |MDD|**.
  · **주 판정 셀: N=20, quarterly.** (band_rule 과의 비교용으로 N=20, none 도 병기 — 판정 아님)

## 판정 (사전 등록)
  J1 선택 정보: lowvol / defensive / broad 각각의 Calmar 가 **random 200회 분포의 95백분위를 초과**하는가 (Holm 보정 3)
  J2 유동성 대비: 같은 셀에서 liquidity 베이스라인의 Calmar 를 초과하는가
  판정: J1·J2 를 모두 통과한 기준이 있으면 **SELECTION_CONFIRMED**(그 기준 이름), 없으면 **NO_SELECTION_EDGE**
        (= 거래대금 상위 N 을 쓰라). liquidity 자체가 random 95백분위를 넘는지도 병기(유동성 자체의 정보).
  N·재구성은 **판정이 아니라 민감도 서술** — liquidity 기준으로 Calmar 표를 내고 단조성·회전비용을 적는다.
        (다중검정 부담을 선택 기준에만 걸고, 규모·주기는 고르는 게 아니라 보고한다)

**DEPLOY_ON_PASS=False.** 통과해도 실거래 반영 없음 — 이건 기존 패턴 시스템과 별개 시스템이고 채택은 사용자 결정.

한계(실행 전 기록): **생존 편향이 이 시험에서 가장 크다** — data_long 은 현재 OKX 상장 코인만이라 2019 년 바스켓은
'그때 있었고 지금도 살아남은' 코인이다. 그리고 **생존은 저변동·방어 성격과 상관**이 있으므로 defensive/lowvol арм 이
구조적으로 유리하다. 따라서 **방어 계열이 이겨도 강한 증거가 아니다**(이 문장을 결과 전에 적는다).
그 외: 재구성 없음 arm 은 2019 년에 존재한 코인만 쓸 수 있어 풀이 작다(주기 비교에 교란) · 스프레드 미반영.

실행: python validate_basket.py [--no-fetch]      출력: _basket.json + RESULT_JSON
"""
import json
import random
import statistics as st
import sys

import validate_band_rule as br
import validate_breadth_state as bs
import validate_regime_split_all as va
import xsec_features as xf

# ── 동결 ─────────────────────────────────────────────────────────────────────────────────────
STOP = 0.01
FEE = br.FEE
SLIP = 0.00141                      # band_rule 에서 측정한 1시간 지연 δ
POOL_N = 60
CRITERIA = ("liquidity", "lowvol", "defensive", "broad", "random")
N_GRID = (5, 10, 20, 40)
REBAL = {"none": None, "quarterly": 91, "monthly": 30}
N_PRIMARY, REBAL_PRIMARY = 20, "quarterly"
RANDOM_DRAWS, SEED = 200, 42
START, END = "2019-06-01", "2026-09-06"
PCTL = 95
DEPLOY_ON_PASS = False


def turnover_at(rows, i, win=30):
    if i + 1 < win:
        return None
    seg = rows[i - win + 1:i + 1]
    return sum(x["c"] * x["v"] for x in seg) / win


def pool_at(rows_1d, date_, pool_n=POOL_N, min_hist=252):
    """형성일 기준 PIT 풀: 이력 >= min_hist 이고 거래대금 상위 pool_n. 반환 [(sym, idx)]."""
    cand = []
    for s, r in rows_1d.items():
        idx = {x["date"]: k for k, x in enumerate(r)}
        i = idx.get(date_)
        if i is None or i < min_hist:
            continue
        tv = turnover_at(r, i)
        if tv:
            cand.append((tv, s, i))
    cand.sort(reverse=True)
    return [(s, i) for _, s, i in cand[:pool_n]]


def select(rows_1d, pool, crit, n, ff, seed=None):
    """기준에 따라 풀에서 n 종목. 반환 [(sym, idx)]."""
    if crit == "liquidity":
        return pool[:n]
    if crit == "random":
        rng = random.Random(seed)
        return rng.sample(pool, min(n, len(pool)))
    feats = [(s, ff(s, rows_1d[s]).at(i)) for s, i in pool]
    if crit == "lowvol":
        ok = [(s, f["rvol20"]) for s, f in feats if f.get("rvol20") is not None]
        ok.sort(key=lambda t: (t[1], t[0]))
        pick = {s for s, _ in ok[:n]}
    else:
        spec = bs.BROAD if crit == "broad" else bs.DEFENSIVE
        sc = bs.profile_score(feats, spec)
        if not sc:
            return pool[:n]
        pick = {s for s, _ in sorted(sc.items(), key=lambda t: (-t[1], t[0]))[:n]}
    return [(s, i) for s, i in pool if s in pick][:n]


def sleeve_curve(rows, i0, i1, dates):
    """한 종목에 띠 규칙을 걸었을 때의 일별 가치(시작 1.0). dates 는 마스터 날짜 목록."""
    idx = {x["date"]: k for k, x in enumerate(rows)}
    P = rows[i0]["c"]
    if P <= 0:
        return None
    S = P * (1 - STOP)
    E = 1.0 * (1 - FEE); units = E / P; inpos = True
    out = {}; last = E
    for j in range(i0, i1 + 1):
        x = rows[j]
        if j > i0:
            if inpos:
                if x["l"] <= S:
                    fill = min(S, x["o"]) if x["o"] < S else S * (1 - SLIP)
                    E = units * fill * (1 - FEE); units = 0.0; inpos = False
            elif x["h"] >= P:
                px = P * (1 + SLIP); E *= (1 - FEE); units = E / px; inpos = True
        last = units * x["c"] if units > 0 else E
        out[x["date"]] = last
    vals = []; cur = 1.0
    for d in dates:
        if d in out:
            cur = out[d]
        vals.append(cur)
    return vals


def hold_curve(rows, i0, i1, dates):
    idx0 = rows[i0]["c"]
    if idx0 <= 0:
        return None
    out = {rows[j]["date"]: rows[j]["c"] / idx0 for j in range(i0, i1 + 1)}
    vals = []; cur = 1.0
    for d in dates:
        if d in out:
            cur = out[d]
        vals.append(cur)
    return vals


def basket_curve(rows_1d, dates, crit, n, rebal_days, ff, seed=None, hold=False):
    """전 구간 자산곡선. rebal_days=None 이면 시작일 1회 형성."""
    marks = [0]
    if rebal_days:
        k = rebal_days
        while k < len(dates):
            marks.append(k); k += rebal_days
    eq = [1.0] * len(dates)
    cap = 1.0
    for m, start in enumerate(marks):
        end = marks[m + 1] - 1 if m + 1 < len(marks) else len(dates) - 1
        d0, d1 = dates[start], dates[end]
        pool = pool_at(rows_1d, d0)
        if not pool:
            continue
        pick = select(rows_1d, pool, crit, n, ff, seed=(None if seed is None else seed + m))
        sub = []
        for s, i0 in pick:
            r = rows_1d[s]
            idx = {x["date"]: k for k, x in enumerate(r)}
            i1 = idx.get(d1)
            if i1 is None or i1 <= i0:
                continue
            c = (hold_curve if hold else sleeve_curve)(r, i0, i1, dates[start:end + 1])
            if c:
                sub.append(c)
        if not sub:
            continue
        seg = [cap * sum(v[t] for v in sub) / len(sub) for t in range(end - start + 1)]
        if rebal_days:                                        # 재구성 시 양측 수수료
            seg = [v * (1 - FEE) ** 2 for v in seg]
        for t, v in enumerate(seg):
            eq[start + t] = v
        cap = seg[-1]
    return eq


def stats(eq, days):
    if not eq or eq[0] <= 0 or eq[-1] <= 0:
        return dict(final=None, cagr=None, mdd=None, calmar=None)
    peak = eq[0]; mdd = 0.0
    for v in eq:
        peak = max(peak, v); mdd = min(mdd, v / peak - 1)
    yrs = days / 365.25
    cagr = eq[-1] ** (1 / yrs) - 1 if yrs > 0 else None
    return dict(final=eq[-1], cagr=cagr, mdd=mdd, calmar=(cagr / abs(mdd) if (cagr is not None and mdd < 0) else None))


def holm(p):
    items = sorted((v, k) for k, v in p.items() if v is not None)
    m, out, run = len(items), {}, 0.0
    for r, (v, k) in enumerate(items):
        run = max(run, min(1.0, (m - r) * v)); out[k] = run
    return out


def _f(v, w=8, pct=False):
    if v is None:
        return " " * (w - 1) + "-"
    return f"{v*100:{w}.1f}" if pct else f"{v:{w}.2f}"


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    print(f"바스켓 구성 시험 | 손절 {STOP*100:.0f}% 슬립 {SLIP*100:.3f}% · 풀 상위 {POOL_N} · 기준 {CRITERIA} · N {N_GRID} "
          f"· 재구성 {list(REBAL)} · 주판정 N={N_PRIMARY}/{REBAL_PRIMARY} · 무작위 {RANDOM_DRAWS}회 | DEPLOY_ON_PASS={DEPLOY_ON_PASS}")
    rows_1d = va.load_tf(va._syms(), "1d", long=True)
    btc = rows_1d.get("BTC")
    dates = sorted({x["date"] for r in rows_1d.values() for x in r if START <= x["date"] <= END})
    print(f"[data] 코인 {len(rows_1d)} · 날짜 {dates[0]}~{dates[-1]} ({len(dates)}일)")
    cache = {}
    def ff(s, r):
        if s not in cache:
            cache[s] = bs.FastFeatures(r, btc)
        return cache[s]
    days = (len(dates))

    out = dict(frame="basket", deploy_on_pass=DEPLOY_ON_PASS, primary=dict(n=N_PRIMARY, rebal=REBAL_PRIMARY), grid={}, primary_result={})

    # ── 주 판정 셀 ──────────────────────────────────────────────────────────
    rb = REBAL[REBAL_PRIMARY]
    print(f"\n== 주 판정: N={N_PRIMARY} · 재구성 {REBAL_PRIMARY} ==")
    rnd = []
    for k in range(RANDOM_DRAWS):
        eq = basket_curve(rows_1d, dates, "random", N_PRIMARY, rb, ff, seed=SEED + k * 1000)
        s = stats(eq, days)
        if s["calmar"] is not None:
            rnd.append(s["calmar"])
    rnd.sort()
    thr = rnd[int(PCTL / 100 * (len(rnd) - 1))] if rnd else None
    print(f"  무작위 {len(rnd)}회 Calmar: 중앙 {st.median(rnd):.2f} · {PCTL}백분위 **{thr:.2f}** · 범위 {rnd[0]:.2f}~{rnd[-1]:.2f}")
    res = {}
    print(f"  {'기준':<12}{'최종':>9}{'CAGR':>9}{'MDD':>9}{'Calmar':>9}{'무작위 초과':>12}{'백분위':>8}")
    for crit in ("liquidity", "lowvol", "defensive", "broad"):
        eq = basket_curve(rows_1d, dates, crit, N_PRIMARY, rb, ff)
        s = stats(eq, days); res[crit] = s
        pc = (sum(1 for v in rnd if v < s["calmar"]) / len(rnd) * 100) if (rnd and s["calmar"] is not None) else None
        s["pctile"] = pc
        print(f"  {crit:<12}{_f(s['final'],8)}x{_f(s['cagr'],8,True)}%{_f(s['mdd'],8,True)}%{_f(s['calmar'],9)}"
              f"{('통과' if (thr and s['calmar'] and s['calmar']>thr) else '미달'):>12}{(pc if pc is not None else 0):>7.0f}%")
    pvals = {c: (1 - (res[c].get("pctile") or 0) / 100) for c in ("lowvol", "defensive", "broad")}
    ph = holm(pvals)
    liq = res["liquidity"]["calmar"]
    winners = [c for c in ("lowvol", "defensive", "broad")
               if res[c]["calmar"] is not None and thr and res[c]["calmar"] > thr and ph.get(c, 1) < 0.05
               and liq is not None and res[c]["calmar"] > liq]
    verdict = "SELECTION_CONFIRMED" if winners else "NO_SELECTION_EDGE"
    print(f"  Holm 보정 p: " + " · ".join(f"{c} {ph.get(c,1):.3f}" for c in ("lowvol", "defensive", "broad")))
    print(f"  liquidity 자체의 무작위 백분위: {res['liquidity'].get('pctile',0):.0f}%")
    print(f"\n  ** 판정: {verdict} ** {('(' + ', '.join(winners) + ')') if winners else '(= 거래대금 상위 N 을 쓰라)'}")
    out["primary_result"] = dict(random_median=st.median(rnd) if rnd else None, random_p95=thr,
                                 criteria=res, holm=ph, winners=winners, verdict=verdict)

    # ── 민감도 (판정 아님) ──────────────────────────────────────────────────
    print(f"\n== 민감도 (판정 아님) — liquidity 기준 Calmar ==")
    print(f"  {'재구성':<12}" + "".join(f"{'N='+str(n):>10}" for n in N_GRID))
    for rname, rd in REBAL.items():
        line = f"  {rname:<12}"
        for n in N_GRID:
            s = stats(basket_curve(rows_1d, dates, "liquidity", n, rd, ff), days)
            out["grid"][f"liquidity|{n}|{rname}"] = s
            line += f"{_f(s['calmar'],10)}"
        print(line)
    print(f"\n  {'재구성':<12}" + "".join(f"{'N='+str(n):>10}" for n in N_GRID) + "   (최종 배수)")
    for rname, rd in REBAL.items():
        line = f"  {rname:<12}"
        for n in N_GRID:
            s = out["grid"][f"liquidity|{n}|{rname}"]
            line += f"{_f(s['final'],9)}x"
        print(line)
    # band_rule 비교용 + 보유 대조
    s_none = stats(basket_curve(rows_1d, dates, "liquidity", 20, None, ff), days)
    s_hold = stats(basket_curve(rows_1d, dates, "liquidity", 20, REBAL[REBAL_PRIMARY], ff, hold=True), days)
    out["compare"] = dict(n20_none=s_none, hold_n20_quarterly=s_hold)
    print(f"\n  [비교] N=20 재구성없음(band_rule 과 같은 형태): 최종 {_f(s_none['final'],7)}x Calmar {_f(s_none['calmar'],6)}")
    print(f"  [비교] N=20 분기재구성 **그냥 보유**(띠 규칙 없음): 최종 {_f(s_hold['final'],7)}x CAGR {_f(s_hold['cagr'],6,True)}% MDD {_f(s_hold['mdd'],6,True)}% Calmar {_f(s_hold['calmar'],6)}")

    out["verdict"] = verdict
    json.dump(out, open("_basket.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print("\nRESULT_JSON: " + json.dumps(dict(frame="basket", verdict=verdict, winners=winners,
                                             primary={k: dict(final=v.get("final"), cagr=v.get("cagr"), mdd=v.get("mdd"),
                                                              calmar=v.get("calmar"), pctile=v.get("pctile"))
                                                      for k, v in res.items()},
                                             random_p95=thr, grid={k: v.get("calmar") for k, v in out["grid"].items()},
                                             hold=out["compare"]["hold_n20_quarterly"]), ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
