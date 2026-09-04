"""
regime_alt.py — 레짐 라벨러 후보 (연구용, 2026-09-04, 사용자 지시 "레짐 정확도를 올릴 변수 추가").

현행(regime_switch.build_regime_map)은 일봉 3신호 다수결이다: BTC 200일선 20일 기울기(price),
ETH/BTC 20일 기울기(eb), BTC.D 20일 기울기(dom), 2/3 지지 히스테리시스. 약점(실측):
  · bull_altseason 구간 무작위 롱 20봉 −3.04% — 라벨이 국면 끝자락에 붙는다(후행).
  · sideways 가 5년간 0일 — p=='side' 후보가 eb/dom 'side' 와 동시에 맞는 날이 없다.
이 모듈은 현행 3신호를 **그대로 두고** 추가 신호(시장 폭·변동성·펀딩)를 얹거나 바꾼
라벨러 후보를 만든다. 실거래 코드는 이 모듈을 쓰지 않는다 — regime_quality / method_q 전용.

추가 신호 (전부 닫힌 일봉·과거 데이터만, 룩어헤드 없음):
  breadth : 유니버스 중 종가 > 200일선 비율(200봉 이상 종목만). up>=0.60 / down<=0.40 / side.
  vol     : BTC 20일 실현변동성의 직전 365일 백분위. low<0.30 / high>0.70 / mid.
  funding : BTC 무기한 펀딩비 30일 평균의 직전 365일 백분위. hot>0.80 / cold<0.20 / mid.

라벨러 후보 (사전 등록):
  current       : 현행 그대로 (비교 기준).
  fast_slope    : 현행에서 가격 기울기 lookback 20→10 (지연만 줄이는 가장 단순한 손잡이).
  breadth_price : 신호1(BTC 기울기)을 breadth 로 교체. 나머지 동일.
  vote4         : 현행 후보에 breadth 를 4번째 표로 — 전환에 4표 중 3표 필요(합의 강화).
  vol_side      : 현행 + (vol low AND breadth side) 이면 sideways — 횡보 복원.
  funding_cap   : 현행 + funding hot 이면 bull_* → sideways (과열 구간 롱 금지).
  breadth_only  : breadth 가 price 역할(up/down/side)이고 eb/dom 은 현행. = breadth_price 와
                  같은 구조지만 히스테리시스 없이 매일 후보 그대로(전환 지연 0 의 상한).
"""
import json
import math
import os
import statistics as st
import time

import detlib
import regime_switch as rs

BREADTH_UP, BREADTH_DN = 0.60, 0.40
VOL_LB, VOL_PCT_WIN = 20, 365
VOL_LOW, VOL_HIGH = 0.30, 0.70
FUND_LB, FUND_PCT_WIN = 30, 365
FUND_HOT, FUND_COLD = 0.80, 0.20
FUNDING_CACHE = "funding_history_btc.json"
BREADTH_MIN_N = 10
LABELERS = ["current", "fast_slope", "breadth_price", "vote4", "vol_side", "funding_cap", "breadth_only"]


# ── 추가 신호 ────────────────────────────────────────────────────────────────
def breadth_series(rows_by_sym, ma_p=200):
    """date -> (above_frac, n). 200봉 이상 가진 종목만 분모에 넣는다."""
    above, total = {}, {}
    for rows in rows_by_sym.values():
        ma = rs.sma([r["c"] for r in rows], ma_p)
        for i, r in enumerate(rows):
            if ma[i] is None:
                continue
            d = r["date"]
            total[d] = total.get(d, 0) + 1
            above[d] = above.get(d, 0) + (r["c"] > ma[i])
    return {d: (above.get(d, 0) / total[d], total[d]) for d in total}


def breadth_signal(breadth, min_n=None):
    min_n = BREADTH_MIN_N if min_n is None else min_n
    out = {}
    for d, (f, n) in breadth.items():
        if n < min_n:
            continue
        out[d] = "up" if f >= BREADTH_UP else "down" if f <= BREADTH_DN else "side"
    return out


def _pct_rank(vals, i, win):
    lo = max(0, i - win)
    hist = [v for v in vals[lo:i] if v is not None]
    if len(hist) < win // 2:
        return None
    # 동률은 절반만 세어 평탄한 구간이 100% 로 읽히지 않게 한다(전부 같으면 0.5)
    less = sum(1 for v in hist if v < vals[i]); eq = sum(1 for v in hist if v == vals[i])
    return (less + 0.5 * eq) / len(hist)


def vol_state(btc_rows):
    """date -> 'low'/'mid'/'high' (20일 실현변동성의 직전 365일 백분위)."""
    c = [r["c"] for r in btc_rows]
    lr = [None] + [math.log(c[i] / c[i - 1]) for i in range(1, len(c))]
    vol = [None] * len(c)
    for i in range(VOL_LB, len(c)):
        w = lr[i - VOL_LB + 1:i + 1]
        if all(x is not None for x in w):
            vol[i] = st.pstdev(w)
    out = {}
    for i, r in enumerate(btc_rows):
        if vol[i] is None:
            continue
        p = _pct_rank(vol, i, VOL_PCT_WIN)
        if p is None:
            continue
        out[r["date"]] = "low" if p < VOL_LOW else "high" if p > VOL_HIGH else "mid"
    return out


def funding_state(fund_daily, dates):
    """fund_daily: date -> 일평균 펀딩비. date -> 'hot'/'mid'/'cold'."""
    vals = [fund_daily.get(d) for d in dates]
    ma = [None] * len(vals)
    for i in range(len(vals)):
        w = [v for v in vals[max(0, i - FUND_LB + 1):i + 1] if v is not None]
        if len(w) >= FUND_LB // 2:
            ma[i] = st.mean(w)
    out = {}
    for i, d in enumerate(dates):
        if ma[i] is None:
            continue
        p = _pct_rank(ma, i, FUND_PCT_WIN)
        if p is None:
            continue
        out[d] = "hot" if p > FUND_HOT else "cold" if p < FUND_COLD else "mid"
    return out


def fetch_funding_history(inst="BTC-USDT-SWAP", days=1800, cache=FUNDING_CACHE, quiet=False):
    """OKX 펀딩비 이력(8h) → date -> 일평균. 캐시 우선. 실패/부족 시 있는 만큼 반환."""
    if os.path.exists(cache):
        try:
            d = json.load(open(cache, encoding="utf-8"))
            if len(d) >= min(days, 400):
                return d
        except Exception:
            pass
    import requests
    now_ms = int(time.time() * 1000)
    since = now_ms - days * 86400 * 1000
    after, raw, calls = None, [], 0
    while calls < 200:
        params = {"instId": inst, "limit": 100}
        if after:
            params["after"] = after
        try:
            r = requests.get("https://www.okx.com/api/v5/public/funding-rate-history",
                             params=params, timeout=15)
            data = r.json().get("data", []) if r.ok else []
        except Exception as e:
            if not quiet:
                print(f"  [funding] fetch 오류: {str(e)[:60]}")
            break
        calls += 1
        if not data:
            break
        raw.extend(data)
        last_t = min(int(x["fundingTime"]) for x in data)
        if last_t <= since:
            break
        after = str(last_t)
        time.sleep(0.15)
    by_day = {}
    from datetime import datetime, timezone
    for x in raw:
        t = int(x["fundingTime"])
        if t < since:
            continue
        d = datetime.fromtimestamp(t / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        by_day.setdefault(d, []).append(float(x.get("realizedRate") or x.get("fundingRate") or 0))
    out = {d: st.mean(v) for d, v in sorted(by_day.items())}
    if out:
        json.dump(out, open(cache, "w", encoding="utf-8"))
    if not quiet:
        print(f"  [funding] {inst} {len(out)}일 (호출 {calls})")
    return out


# ── 현행 신호 재사용 ────────────────────────────────────────────────────────
def base_signals(btc, eth, alts_rows, slope_lb=None):
    """현행 3신호(date->up/down/side). slope_lb 로 가격 기울기 lookback 만 바꿀 수 있다."""
    if slope_lb is None:
        price = rs._price_signal(btc)
    else:
        old = rs.SLOPE_LB
        rs.SLOPE_LB = slope_lb
        try:
            price = rs._price_signal(btc)
        finally:
            rs.SLOPE_LB = old
    return price, rs._ethbtc_signal(btc, eth), rs._dom_signal_hybrid(btc, alts_rows)


def _candidate(p, eb, dom):
    if p == "down":
        return "bear"
    if p == "side":
        return "sideways"
    alt_v = int(eb == "up") + int(dom == "down")
    btc_v = int(eb == "down") + int(dom == "up")
    return "bull_altseason" if alt_v > btc_v else "bull_btc"


def _vote(price, ethbtc, dom, extra=None, need=2, hysteresis=True):
    """현행 build_regime_map 의 투표 루프. extra(d)->추가 지지(0/1) 를 얹을 수 있다."""
    dates = sorted(set(price) & set(ethbtc))
    reg, prev = {}, None
    for d in dates:
        p, eb, dm = price.get(d, "side"), ethbtc.get(d, "side"), dom.get(d, "side")
        cand = _candidate(p, eb, dm)
        sup = rs._signal_support(cand, p, eb, dm) + (extra(d, cand) if extra else 0)
        if not hysteresis or prev is None or sup >= need:
            reg[d] = cand
        else:
            reg[d] = prev
        prev = reg[d]
    return reg


def _breadth_agree(bsig):
    def f(d, cand):
        b = bsig.get(d, "side")
        if cand == "bear":
            return int(b == "down")
        if cand == "sideways":
            return int(b == "side")
        return int(b == "up")
    return f


# ── 라벨러 ──────────────────────────────────────────────────────────────────
def build_all(btc, eth, alts_rows, rows_by_sym, fund_daily=None, current=None):
    """모든 후보 라벨러 → {name: date->label}. current 는 rs.build_regime_map() 결과를 넘긴다."""
    price, eb, dom = base_signals(btc, eth, alts_rows)
    bsig = breadth_signal(breadth_series(rows_by_sym))
    vst = vol_state(btc)
    out = {}
    out["current"] = dict(current) if current is not None else _vote(price, eb, dom)
    p10, _, _ = base_signals(btc, eth, alts_rows, slope_lb=10)
    out["fast_slope"] = _vote(p10, eb, dom)
    bp = {d: bsig[d] for d in price if d in bsig}
    out["breadth_price"] = _vote(bp, eb, dom)
    out["vote4"] = _vote(price, eb, dom, extra=_breadth_agree(bsig), need=3)
    vs = dict(out["current"])
    for d in vs:
        if vst.get(d) == "low" and bsig.get(d) == "side":
            vs[d] = "sideways"
    out["vol_side"] = vs
    fc = dict(out["current"])
    if fund_daily:
        fst = funding_state(fund_daily, sorted(fc))
        for d in fc:
            if fst.get(d) == "hot" and fc[d] in ("bull_btc", "bull_altseason"):
                fc[d] = "sideways"
        out["funding_cap"] = fc
    out["breadth_only"] = _vote(bp, eb, dom, hysteresis=False)
    return out, dict(breadth=bsig, vol=vst)


# ── 공통 컨텍스트 로더 (regime_quality / method_q 공용) ──────────────────────
def load_context(universe=None, fetch_funding=True):
    """
    닫힌 일봉으로 BTC/ETH/알트·유니버스 rows 를 읽고 현행 맵과 후보 맵을 만든다.
    반환 dict(labels={name: date->label}, signals, rows_by, btc, funding_days).
    """
    if universe is None:
        universe = json.load(open("universe.json", encoding="utf-8"))["trading_universe"]
    btc = rs._closed_rows(detlib.load_ohlcv(rs.MARKET, "1d"))
    eth = rs._closed_rows(detlib.load_ohlcv("ETH", "1d"))
    alts = {}
    for a in rs.ALTS:
        try:
            alts[a] = rs._closed_rows(detlib.load_ohlcv(a, "1d"))
        except (FileNotFoundError, RuntimeError):
            pass
    rows_by = {}
    for s in sorted(set(universe) | {rs.MARKET, "ETH"} | set(rs.ALTS)):
        try:
            r = rs._closed_rows(detlib.load_ohlcv(s, "1d"))
            if r:
                rows_by[s] = r
        except (FileNotFoundError, RuntimeError):
            pass
    if fetch_funding:
        fund = fetch_funding_history()
    else:                                   # 네트워크 없이 캐시만
        try:
            fund = json.load(open(FUNDING_CACHE, encoding="utf-8"))
        except Exception:
            fund = {}
    current = rs.build_regime_map()
    labels, signals = build_all(btc, eth, alts, rows_by, fund_daily=fund or None, current=current)
    return dict(labels=labels, signals=signals, rows_by=rows_by, btc=btc, funding_days=len(fund))
