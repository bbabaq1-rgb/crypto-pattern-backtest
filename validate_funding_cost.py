"""
validate_funding_cost.py — 펀딩비를 손익에 부과했을 때의 변화 (사전 등록, 2026-09-21)

**왜.** 이 레포의 어떤 손익 계산에도 펀딩비가 들어간 적이 없다(2026-09-21 확인:
method_x / method_t / validate_revival / paper_executor / intraday_lab / exit_barriers /
sizing / detlib 전부 0건). 비용은 `intraday_lab.FEE = 0.002`(왕복 0.2%) 하나뿐이다.
그런데 배포 집합은 **전부 알트 무기한 롱**이고 방식D 는 최대 30봉(1d 30일 / 4h 5일)을 든다.
롱이 펀딩을 내는 쪽이 기본값이므로 실거래는 백테스트가 떼지 않는 비용을 매 8시간 낸다.

**새 엣지를 찾는 시험이 아니다** — 이미 측정된 엣지의 진짜 크기를 아는 시험이다.

────────────────────────────────────────────────────────────────────────────
사전 등록 (결과 보기 전 고정 — registry funding_cost_prereg_2026_09_21)

소스: OKX `funding-rate-history` 1순위(실제 거래 대상). Bybit 는 **확장 창에만**,
      겹치는 구간에서 ρ >= 0.80 AND 평균 절대차 <= 0.005%/8h 를 둘 다 만족할 때만.
부과: (t_in, t_out] 사이 **정산된** 요율만 합산. funding_pct = Σ rate × 부호(롱 +1 / 숏 −1).
      ret_net = ret − funding_pct. 명목가는 거래 내내 고정으로 본다.
거래: validate_portfolio 의 배포 집합 정의 그대로(1d 라우팅 4셀 + ih/marubozu + 4h 4종).
판정: PASS/FAIL 이 아니라 **MATERIAL / IMMATERIAL**.
      (i)  전체 평균 펀딩 비용 >= 전체 평균 총수익의 20%
      (ii) 배포 셀 중 하나 이상에서 건당 평균이 펀딩 부과로 음수로 뒤집힘
      (iii) 포트폴리오 곡선 Calmar 가 10% 이상 하락
      하나라도 걸리면 MATERIAL.
DEPLOY_ON_PASS = False — 어떤 결과든 실거래 무변경. 바뀌는 것은 **기존 수치의 해석**이다.

한계(결과 전 기록): OKX 이력이 약 3개월이라 커버리지가 최근 창에 한정되고, 그 창은
bear 지배라 펀딩이 낮다 → **이 측정은 하한일 가능성이 높다.** IMMATERIAL 이 나와도
'불장에서도 작다'는 뜻이 아니다. 커버 안 되는 과거 거래는 추정치로 채우지 않고 제외한다.

실행: python validate_funding_cost.py [--no-fetch] [--no-bybit]
"""
import json
import math
import statistics as st
import sys
import time
import urllib.request
from bisect import bisect_left, bisect_right
from datetime import date, datetime, timezone

import detlib
import method_t as mt
import validate_portfolio as vp
import validate_regime_split_all as va
import validate_regime_split as vrs
import regime_switch

DEPLOY_ON_PASS = False

EPOCH_ORD = date(1970, 1, 1).toordinal()
BAR_MS = {"1d": 86400000, "4h": 14400000, "1h": 3600000, "1w": 604800000}

OKX_BASE = "https://www.okx.com"
BYBIT_BASE = "https://api.bybit.com"
UA = {"User-Agent": "Mozilla/5.0"}
TIMEOUT = 20
OKX_LIMIT, OKX_PAGES = 100, 40          # 100건/페이지 ≈ 33일 — API 가 먼저 끊는다
BYBIT_LIMIT, BYBIT_PAGES = 200, 60      # 200건/페이지 ≈ 66일

# 합치 게이트 (동결)
AGREE_RHO = 0.80
AGREE_DIFF = 0.00005                    # 0.005%/8h
AGREE_MIN_N = 100                       # 겹치는 정산 수 하한

# 판정 문턱 (동결)
MAT_SHARE = 0.20                        # (i)  평균 비용 / 평균 총수익
MAT_CALMAR_DROP = 0.10                  # (iii) Calmar 하락률
EPS = 1e-12                             # 문턱 '이상' 이 부동소수로 뒤집히지 않게
OUT = "_funding_cost.json"


# ── 시각 ──────────────────────────────────────────────────────────────────────
def close_ms(tnum, tf):
    """거래 레코드의 t_in/t_out(일수 ordinal) → 그 **봉의 종가 시각**(ms).

    1d 는 ordinal 정수(= 그 날짜 00:00 UTC)라 +1일이 종가 시각이고,
    4h 는 vr._tnum 이 봉 **시작** ts 를 분수 일수로 준 것이라 +4h 가 종가 시각이다.
    """
    return int(round((float(tnum) - EPOCH_ORD) * 86400000.0)) + BAR_MS.get(tf, 86400000)


def _ms_day(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


# ── 펀딩 이력 ─────────────────────────────────────────────────────────────────
def _get(url, params=None):
    if params:
        url += "?" + "&".join(f"{k}={v}" for k, v in params.items() if v not in (None, ""))
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=TIMEOUT) as r:
        return json.loads(r.read().decode())


def okx_funding(symbol, pages=OKX_PAGES):
    """{fundingTime(ms): rate} — `after` 로 과거 방향 페이지네이션."""
    out, after = {}, None
    for _ in range(pages):
        try:
            data = _get(OKX_BASE + "/api/v5/public/funding-rate-history",
                        {"instId": f"{symbol}-USDT-SWAP", "limit": OKX_LIMIT,
                         "after": after}).get("data", [])
        except Exception:
            break
        if not data:
            break
        oldest = None
        for x in data:
            rate = x.get("realizedRate") or x.get("fundingRate")
            t = x.get("fundingTime")
            if rate in (None, "") or not t:
                continue
            t = int(t)
            out[t] = float(rate)
            oldest = t if oldest is None else min(oldest, t)
        if oldest is None or len(data) < OKX_LIMIT:
            break
        after = oldest          # OKX: 요청한 fundingTime 보다 **이전** 것을 돌려준다
    return out


def bybit_funding(symbol, pages=BYBIT_PAGES):
    """{fundingRateTimestamp(ms): rate} — `endTime` 으로 과거 방향 페이지네이션."""
    out, end = {}, None
    for _ in range(pages):
        try:
            js = _get(BYBIT_BASE + "/v5/market/funding/history",
                      {"category": "linear", "symbol": f"{symbol}USDT",
                       "limit": BYBIT_LIMIT, "endTime": end})
        except Exception:
            break
        rows = (js.get("result") or {}).get("list") or []
        if not rows:
            break
        oldest = None
        for x in rows:
            t, rate = x.get("fundingRateTimestamp"), x.get("fundingRate")
            if not t or rate in (None, ""):
                continue
            t = int(t)
            out[t] = float(rate)
            oldest = t if oldest is None else min(oldest, t)
        if oldest is None or len(rows) < BYBIT_LIMIT:
            break
        end = oldest - 1
    return out


def agreement(a, b):
    """(rho, 평균 절대차, 겹치는 수). 정산 시각이 같은 점들만 본다."""
    keys = sorted(set(a) & set(b))
    if len(keys) < 3:
        return None, None, len(keys)
    xs = [a[k] for k in keys]
    ys = [b[k] for k in keys]
    mad = sum(abs(x - y) for x, y in zip(xs, ys)) / len(keys)
    mx, my = st.fmean(xs), st.fmean(ys)
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    # 상수 계열 방어는 **상대** 문턱이어야 한다 — fmean 의 반올림 때문에 분산이 정확히 0 이
    # 아니라 1e-17 급으로 남고, 그대로 나누면 ρ=1.0000000000000002 같은 허수가 나온다.
    scale = max(abs(mx), abs(my), 1e-12)
    if sx <= 1e-9 * scale or sy <= 1e-9 * scale:
        return None, mad, len(keys)
    rho = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)
    return rho, mad, len(keys)


def agree_ok(rho, mad, n):
    """동결 게이트 — 셋 다 만족해야 Bybit 를 확장 창에 쓴다."""
    return (rho is not None and mad is not None and n >= AGREE_MIN_N
            and rho >= AGREE_RHO and mad <= AGREE_DIFF)


def merge_curve(okx, bybit, use_bybit):
    """(정렬된 시각 리스트, 요율 리스트). 겹치는 구간은 **OKX 우선**(실제 거래 대상)."""
    m = dict(bybit) if use_bybit else {}
    m.update(okx)
    ts = sorted(m)
    return ts, [m[t] for t in ts]


def charge(curve, t0, t1, sign):
    """(t0, t1] 안의 정산 요율 합 × 부호. 롱 sign=+1 (rate>0 이면 지불)."""
    ts, rates = curve
    lo, hi = bisect_right(ts, t0), bisect_right(ts, t1)
    return sign * sum(rates[lo:hi])


def covered(curve, t0, t1):
    """이 거래 구간이 이력 창 안에 **온전히** 들어오는가. 밖이면 추정치로 채우지 않는다."""
    ts, _ = curve
    return bool(ts) and ts[0] <= t0 and ts[-1] >= t1


# ── 거래 집합 ─────────────────────────────────────────────────────────────────
DIR_OF = {p[0]: p[1] for p in mt.PATS}          # 1d 라벨 → long/short
for _p, _g, _c in vp.ADOPTED_4H:
    DIR_OF[_p] = "long"


def sign_of(pattern):
    return 1.0 if DIR_OF.get(pattern, "long") == "long" else -1.0


def build_trades(syms, fetch=True):
    if fetch:
        vp.fetch(syms)
    rows_1d = va.load_tf(syms, "1d")
    rows_4h = va.load_tf(syms, "4h")
    # 배포 프레임(validate_portfolio·스케줄러)과 같은 호출. 비워 두면 outcome_d 의
    # 레짐 전환 청산이 조용히 꺼진다(2026-09-21 발견).
    mt.REGMAP = regime_switch.build_regime_map()
    regmap = mt.REGMAP
    ranked = vrs.turnover_rank(rows_4h)
    trades = vp.collect_1d(syms) + vp.collect_4h(rows_4h, ranked, regmap)
    for t in trades:
        t["ms_in"] = close_ms(t["t_in"], t["tf"])
        t["ms_out"] = close_ms(t["t_out"], t["tf"])
        t["regime"] = regmap.get(_ms_day(t["ms_in"]))
    trades.sort(key=lambda t: (t["t_in"], t["pattern"], t["sym"]))
    return trades


# ── 집계 ──────────────────────────────────────────────────────────────────────
def _agg(rows):
    if not rows:
        return dict(n=0)
    g = [t["ret"] for t in rows]
    net = [t["ret_net"] for t in rows]
    f = [t["funding"] for t in rows]
    return dict(n=len(rows),
                gross=st.fmean(g), net=st.fmean(net), fund=st.fmean(f),
                gross_med=st.median(g), net_med=st.median(net),
                win_gross=sum(1 for x in g if x > 0) / len(g),
                win_net=sum(1 for x in net if x > 0) / len(net),
                hold=st.fmean([t["t_out"] - t["t_in"] for t in rows]))


def _pf(trades, key):
    """포트폴리오 곡선 — 슬롯 배분은 current 고정, ret 만 key 로 갈아 끼운다."""
    tr = [dict(t, ret=t[key]) for t in trades]
    return vp.simulate(tr, "current")


def verdict(overall, cells, pf_gross, pf_net):
    """MATERIAL / IMMATERIAL — 사전 등록 세 조건."""
    hits = []
    if overall["n"] and overall["gross"] > 0 and overall["fund"] >= MAT_SHARE * overall["gross"] - EPS:
        hits.append(f"(i) 평균 비용 {overall['fund']*100:.3f}%p = 평균 총수익의 "
                    f"{overall['fund']/overall['gross']*100:.0f}% >= {MAT_SHARE*100:.0f}%")
    flipped = [c for c, a in cells.items() if a["n"] and a["gross"] > 0 >= a["net"]]
    if flipped:
        hits.append("(ii) 부호 역전 셀: " + ", ".join(sorted(flipped)))
    cg, cn = pf_gross["calmar"], pf_net["calmar"]
    if math.isfinite(cg) and math.isfinite(cn) and cg > 0 and (cg - cn) / cg >= MAT_CALMAR_DROP - EPS:
        hits.append(f"(iii) 포트폴리오 Calmar {cg:.2f} → {cn:.2f} ({(cn/cg-1)*100:+.0f}%)")
    return ("MATERIAL" if hits else "IMMATERIAL"), hits


# ── 실행 ──────────────────────────────────────────────────────────────────────
def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    print("=" * 100)
    print("펀딩비 손익 반영 — 사전 등록 (registry funding_cost_prereg_2026_09_21)")
    print(f"  판정: MATERIAL / IMMATERIAL (i) 비용>=총수익 {MAT_SHARE*100:.0f}% "
          f"(ii) 셀 부호 역전 (iii) Calmar {MAT_CALMAR_DROP*100:.0f}% 하락 | "
          f"DEPLOY_ON_PASS={DEPLOY_ON_PASS}")
    print("=" * 100, flush=True)

    syms = va._syms()
    trades = build_trades(syms, fetch="--no-fetch" not in argv)
    print(f"[거래] {len(trades)}건 (1d {sum(1 for t in trades if t['tf']=='1d')} / "
          f"4h {sum(1 for t in trades if t['tf']=='4h')})", flush=True)

    # ── 펀딩 수집 ──
    used = sorted({t["sym"] for t in trades})
    t0 = time.time()
    okx = {s: okx_funding(s) for s in used}
    n_okx = sum(len(v) for v in okx.values())
    print(f"[펀딩] OKX {n_okx}건 / {len(used)}종목 ({time.time()-t0:.0f}s)", flush=True)

    bybit, agree = {}, {}
    use_bybit = False
    if "--no-bybit" not in argv:
        t0 = time.time()
        bybit = {s: bybit_funding(s) for s in used}
        n_by = sum(len(v) for v in bybit.values())
        pooled_a, pooled_b = {}, {}
        for s in used:
            for k, v in okx.get(s, {}).items():
                if k in bybit.get(s, {}):
                    pooled_a[(s, k)] = v
                    pooled_b[(s, k)] = bybit[s][k]
        rho, mad, n = agreement(pooled_a, pooled_b)
        use_bybit = agree_ok(rho, mad, n)
        agree = dict(rho=rho, mad=mad, n=n, used=use_bybit)
        print(f"[펀딩] Bybit {n_by}건 — 겹침 {n}건 ρ={rho if rho is None else round(rho,3)} "
              f"평균차={mad if mad is None else round(mad,7)} → "
              f"{'확장 사용' if use_bybit else '**게이트 미달, 미사용**'} ({time.time()-t0:.0f}s)",
              flush=True)

    curves = {s: merge_curve(okx.get(s, {}), bybit.get(s, {}), use_bybit) for s in used}
    spans = [(c[0][0], c[0][-1]) for c in curves.values() if c[0]]
    if spans:
        print(f"[펀딩] 창 {_ms_day(min(a for a, _ in spans))} ~ {_ms_day(max(b for _, b in spans))}",
              flush=True)

    # ── 부과 ──
    for t in trades:
        c = curves.get(t["sym"], ([], []))
        if covered(c, t["ms_in"], t["ms_out"]):
            t["funding"] = charge(c, t["ms_in"], t["ms_out"], sign_of(t["pattern"]))
            t["covered"] = True
        else:
            t["funding"], t["covered"] = 0.0, False
        t["ret_net"] = t["ret"] - t["funding"]

    cov = [t for t in trades if t["covered"]]
    print(f"[커버] {len(cov)}/{len(trades)}건 ({len(cov)/max(1,len(trades))*100:.1f}%)", flush=True)
    if not cov:
        print("\n커버된 거래 0건 — 판정 불가(INCONCLUSIVE). 펀딩 이력 수집 실패.")
        json.dump(dict(verdict="INCONCLUSIVE", covered=0, agree=agree),
                  open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        return

    overall = _agg(cov)
    cells = {}
    for t in cov:
        cells.setdefault(t["pattern"], []).append(t)
    cells = {k: _agg(v) for k, v in sorted(cells.items())}

    print("\n" + "-" * 100)
    print(f"{'셀':<20}{'n':>6}{'총수익':>10}{'펀딩':>10}{'순수익':>10}"
          f"{'승률총':>8}{'승률순':>8}{'보유일':>8}")
    print("-" * 100)
    for name, a in cells.items():
        print(f"{name:<20}{a['n']:>6}{a['gross']*100:>9.2f}%{a['fund']*100:>9.3f}%"
              f"{a['net']*100:>9.2f}%{a['win_gross']*100:>7.0f}%{a['win_net']*100:>7.0f}%"
              f"{a['hold']:>8.1f}")
    print("-" * 100)
    print(f"{'전체':<20}{overall['n']:>6}{overall['gross']*100:>9.2f}%"
          f"{overall['fund']*100:>9.3f}%{overall['net']*100:>9.2f}%"
          f"{overall['win_gross']*100:>7.0f}%{overall['win_net']*100:>7.0f}%{overall['hold']:>8.1f}")

    # 진단 — 레짐별 / TF별
    print("\n[진단] 레짐별 펀딩 비용 (판정 아님)")
    byreg = {}
    for t in cov:
        byreg.setdefault(t["regime"] or "unknown", []).append(t)
    for g, v in sorted(byreg.items()):
        a = _agg(v)
        print(f"  {g:<16} n={a['n']:>5}  펀딩 {a['fund']*100:>7.3f}%p  "
              f"총 {a['gross']*100:>6.2f}% → 순 {a['net']*100:>6.2f}%")
    print("[진단] TF별")
    for tf in ("1d", "4h"):
        v = [t for t in cov if t["tf"] == tf]
        if v:
            a = _agg(v)
            print(f"  {tf:<16} n={a['n']:>5}  펀딩 {a['fund']*100:>7.3f}%p  "
                  f"보유 {a['hold']:.1f}일  일당 {a['fund']/max(a['hold'],1e-9)*100:>6.4f}%p")

    # 포트폴리오 곡선 (커버된 거래만, 같은 집합에서 ret vs ret_net)
    pf_g, pf_n = _pf(cov, "ret"), _pf(cov, "ret_net")
    print("\n[포트폴리오] 커버 구간, 슬롯 배분 current 고정")
    for tag, r in (("펀딩 미부과", pf_g), ("펀딩 부과", pf_n)):
        print(f"  {tag:<12} CAGR {r['cagr']*100:+7.1f}%  MDD {r['mdd']*100:6.1f}%  "
              f"Calmar {r['calmar']:5.2f}  체결 {r['taken']}")

    v, hits = verdict(overall, cells, pf_g, pf_n)
    print("\n" + "=" * 100)
    print(f"판정: {v}")
    for h in hits:
        print("  - " + h)
    if not hits:
        print("  - 세 조건 모두 미달")
    print(f"실거래 무변경 (DEPLOY_ON_PASS={DEPLOY_ON_PASS})")
    print("=" * 100)

    json.dump(dict(verdict=v, hits=hits, overall=overall, cells=cells,
                   agree=agree, use_bybit=use_bybit,
                   covered=len(cov), total=len(trades),
                   window=[_ms_day(min(a for a, _ in spans)), _ms_day(max(b for _, b in spans))] if spans else None,
                   portfolio=dict(gross={k: pf_g[k] for k in ("cagr", "mdd", "calmar", "taken")},
                                  net={k: pf_n[k] for k in ("cagr", "mdd", "calmar", "taken")}),
                   thresholds=dict(share=MAT_SHARE, calmar_drop=MAT_CALMAR_DROP,
                                   agree_rho=AGREE_RHO, agree_diff=AGREE_DIFF),
                   deploy_on_pass=DEPLOY_ON_PASS),
              open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print(f"[저장] {OUT}")


if __name__ == "__main__":
    main()
