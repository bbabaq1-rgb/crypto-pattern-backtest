"""
regime_switch.py v2 — 3-signal 가중 다수결 레짐 판정

시그널 3종:
  1. BTC 200MA 기울기 (기존) — 가격 방향
  2. ETH/BTC 비율 20MA 기울기 (신규) — 알트 vs BTC 상대강도. ETH·BTC 일봉 CSV에서 직접 계산.
  3. BTC.D 방향 (신규 하이브리드)
     - 최근 365일: CoinGecko 무료 /coins/{id}/market_chart 에서 BTC+ETH+SOL+XRP+ADA 시총 합산
                  BTC.D_proxy = btc_mc / (btc_mc + eth_mc + sol_mc + xrp_mc + ada_mc)
     - 이전 기간: BTC vs 알트바스켓 30봉 수익률 비교 (기존 프록시 유지)
  ※ TOTAL3(BTC·ETH 제외): 무료 API에서 전체 시총 히스토리 불가 → 5종 시총 프록시로 대체.
     CoinGecko PRO 구독 시 /global/market_cap_chart 로 정확한 TOTAL2/TOTAL3 가능.

레짐 확정 규칙 (노이즈 감소):
  bear   : price_sig = 'down' → 즉시 bear (가격 하락이 가장 강한 시그널)
  sideways : price_sig = 'side'
  bull_btc / bull_altseason : price_sig = 'up' + eth/btc·btc.d 방향 다수결
  전환 조건 : 3개 시그널 중 2개 이상이 후보 레짐을 지지할 때만 전환 (hysteresis)

출력: 날짜별 레짐 + 패턴(롱/숏)별 레짐 기대값. regime_switch.json 저장.
"""
import json
import os
import time
import importlib
import statistics as st
from datetime import datetime, timezone
from collections import Counter

import detlib

# ── 파라미터 ──────────────────────────────────────────────────────────────
MA_P       = 200    # BTC 200MA 기간
SLOPE_LB   = 20     # 가격 MA 기울기 lookback
SLOPE_THR  = 0.001  # 가격 MA 기울기 임계값 (0.1%)
ETHBTC_LB  = 20     # ETH/BTC 비율 MA + 기울기 lookback
ETHBTC_THR = 0.001  # ETH/BTC 기울기 임계값
DOM_LB     = 30     # 구형 알트-바스켓 수익 비교 기간(봉)
DOM_MA_LB  = 20     # BTC.D MA 기울기 lookback
DOM_THR    = 0.0002 # BTC.D 기울기 임계값 (BTC.D는 완만하게 움직임)
BTCD_CACHE = "btc_dominance.json"
BTCD_TTL_H = 23     # BTC.D 캐시 유효기간(시간)

MARKET  = "BTC"
ALTS    = ["SOL", "ETH", "XRP", "ADA", "AVAX", "TRX"]
REGIMES = ["bull_altseason", "bull_btc", "bear", "sideways"]
PATTERNS = ["engulfing", "engulfing_short", "fvg", "fvg_short",
            "inverse_hs", "inverse_hs_short", "order_block", "order_block_short"]
TF = "1d"

# CoinGecko ID → 심볼 (BTC.D 근사치 계산용)
CG_IDS = [
    ("bitcoin",  "BTC"),
    ("ethereum", "ETH"),
    ("solana",   "SOL"),
    ("ripple",   "XRP"),
    ("cardano",  "ADA"),
]


# ── 유틸리티 ──────────────────────────────────────────────────────────────
def sma(x, p):
    out = [None] * len(x); s = 0.0
    for i, c in enumerate(x):
        s += c
        if i >= p: s -= x[i - p]
        if i >= p - 1: out[i] = s / p
    return out


# ── Signal 1: BTC 200MA 기울기 ────────────────────────────────────────────
def _price_signal(btc_rows):
    """date -> 'up'/'down'/'side'"""
    dates  = [r["date"] for r in btc_rows]
    prices = [r["c"]    for r in btc_rows]
    ma = sma(prices, MA_P)
    out = {}
    for i, d in enumerate(dates):
        if i < MA_P + SLOPE_LB or ma[i] is None or ma[i - SLOPE_LB] is None:
            continue
        ref = ma[i - SLOPE_LB]
        if ref == 0:
            continue
        slope = (ma[i] - ref) / ref
        out[d] = "up" if slope > SLOPE_THR else "down" if slope < -SLOPE_THR else "side"
    return out


# ── Signal 2: ETH/BTC 비율 기울기 ─────────────────────────────────────────
def _ethbtc_signal(btc_rows, eth_rows):
    """
    ETH/BTC = eth_close / btc_close.
    20MA 기울기 양수 → 알트 강세('up'), 음수 → BTC 강세('down').
    date -> 'up'/'down'/'side'
    """
    btc_map = {r["date"]: r["c"] for r in btc_rows}
    eth_map = {r["date"]: r["c"] for r in eth_rows}
    dates = sorted(set(btc_map) & set(eth_map))
    ratio = [eth_map[d] / btc_map[d] for d in dates]
    ma = sma(ratio, ETHBTC_LB)
    out = {}
    for i, d in enumerate(dates):
        if i < ETHBTC_LB or ma[i] is None or ma[i - ETHBTC_LB] is None:
            continue
        ref = ma[i - ETHBTC_LB]
        if ref == 0:
            continue
        slope = (ma[i] - ref) / ref
        out[d] = "up" if slope > ETHBTC_THR else "down" if slope < -ETHBTC_THR else "side"
    return out


# ── Signal 3: BTC.D 방향 (CoinGecko 365d + 구형 proxy 하이브리드) ─────────
def _fetch_btcd_from_cg():
    """
    CoinGecko 무료 /coins/{id}/market_chart (days=365)에서
    BTC+ETH+SOL+XRP+ADA 시총 합산 → BTC.D_proxy 계산.
    성공 여부와 관계없이 dict 반환.
    """
    try:
        import requests
    except ImportError:
        return {}

    mc = {}
    for cg_id, sym in CG_IDS:
        for attempt in range(2):
            try:
                r = requests.get(
                    f"https://api.coingecko.com/api/v3/coins/{cg_id}/market_chart",
                    params={"vs_currency": "usd", "days": 365, "interval": "daily"},
                    headers={"Accept": "application/json"},
                    timeout=20,
                )
                if r.ok:
                    mc[sym] = {}
                    for ts, val in r.json().get("market_caps", []):
                        d = datetime.utcfromtimestamp(ts / 1000).strftime("%Y-%m-%d")
                        mc[sym][d] = val
                    break
                elif r.status_code == 429:
                    time.sleep(5)
            except Exception:
                time.sleep(2)
        time.sleep(1.5)

    if "BTC" not in mc:
        return {}

    btcd = {}
    for d, btc_mc in mc["BTC"].items():
        total = btc_mc
        for sym, m in mc.items():
            if sym != "BTC" and d in m:
                total += m[d]
        if total > 0:
            btcd[d] = btc_mc / total

    # 오늘 실시간 BTC.D 덮어쓰기
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/global",
            headers={"Accept": "application/json"},
            timeout=15,
        )
        if r.ok:
            pct = r.json()["data"]["market_cap_percentage"]
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            if "btc" in pct:
                btcd[today] = pct["btc"] / 100.0
    except Exception:
        pass

    return btcd


def _load_btcd_cache():
    """캐시 로드. TTL 이내면 history dict 반환, 만료시 None."""
    if not os.path.exists(BTCD_CACHE):
        return None
    try:
        c = json.load(open(BTCD_CACHE, encoding="utf-8"))
        fetched_at = c.get("fetched_at", "")
        if fetched_at:
            age_h = (
                datetime.now(timezone.utc)
                - datetime.fromisoformat(fetched_at)
            ).total_seconds() / 3600
            if age_h < BTCD_TTL_H:
                return c.get("history", {})
    except Exception:
        pass
    return None


def _save_btcd_cache(btcd_history):
    """BTC.D 데이터 캐시 저장."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    realtime = btcd_history.get(today)
    data = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "current_btc_d": round(realtime * 100, 2) if realtime else None,
        "history_available": bool(btcd_history),
        "history_days": len(btcd_history),
        "source": "coingecko_free_top5_proxy (bitcoin+ethereum+solana+ripple+cardano)",
        "note": (
            "TOTAL3(BTC·ETH 제외) — 무료 API 한계로 스킵. "
            "5종 시총 합산 BTC.D 근사치 사용. "
            "CoinGecko PRO 시 /global/market_cap_chart 로 정확한 TOTAL2/TOTAL3 가능."
        ),
        "history": btcd_history,
    }
    json.dump(data, open(BTCD_CACHE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def _dom_signal_hybrid(btc_rows, alts_rows):
    """
    BTC.D 방향 시그널 하이브리드:
    - 최근 365일: CoinGecko 5종 시총 합산 BTC.D 20MA 기울기
    - 이전 기간 : BTC vs 알트바스켓 30봉 수익률 비교 프록시
    date -> 'up'/'down'/'side'
    """
    btcd_hist = _load_btcd_cache()
    if btcd_hist is None:
        print("  [BTC.D] CoinGecko fetch 시작...", flush=True)
        btcd_hist = _fetch_btcd_from_cg()
        _save_btcd_cache(btcd_hist)
        if btcd_hist:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            pct = btcd_hist.get(today)
            if pct:
                print(f"  [BTC.D] 현재 BTC.D = {pct*100:.1f}%  "
                      f"({len(btcd_hist)}일치 캐시 저장)", flush=True)

    # CoinGecko 기반 BTC.D slope (최근 365일)
    cg_dates = sorted(d for d, v in btcd_hist.items() if v is not None)
    cg_vals  = [btcd_hist[d] for d in cg_dates]
    cg_sig   = {}
    if len(cg_dates) >= DOM_MA_LB + 1:
        ma = sma(cg_vals, DOM_MA_LB)
        for i, d in enumerate(cg_dates):
            if i < DOM_MA_LB or ma[i] is None or ma[i - DOM_MA_LB] is None:
                continue
            ref = ma[i - DOM_MA_LB]
            if ref == 0:
                continue
            slope = (ma[i] - ref) / ref
            cg_sig[d] = "up" if slope > DOM_THR else "down" if slope < -DOM_THR else "side"

    # 구형 프록시 (BTC vs 알트바스켓 30봉 수익 비교)
    btc_dates = [r["date"] for r in btc_rows]
    btc_close = {r["date"]: r["c"] for r in btc_rows}
    alt_map   = {sym: {r["date"]: r["c"] for r in rows} for sym, rows in alts_rows.items()}

    proxy_sig = {}
    for i, d in enumerate(btc_dates):
        if i < DOM_LB:
            continue
        d0 = btc_dates[i - DOM_LB]
        if btc_close[d0] == 0:
            continue
        btc_ret = btc_close[d] / btc_close[d0] - 1
        alt_rets = [
            m[d] / m[d0] - 1
            for m in alt_map.values()
            if d in m and d0 in m and m[d0] > 0
        ]
        if not alt_rets:
            continue
        alt_med = st.median(alt_rets)
        # BTC > alt → BTC.D 상승(up) / BTC < alt → BTC.D 하락(down)
        proxy_sig[d] = "up" if btc_ret > alt_med else "down"

    # 병합: CoinGecko가 있으면 우선 (더 정확)
    merged = {**proxy_sig, **cg_sig}
    return merged


# ── 3-signal 지지 점수 ─────────────────────────────────────────────────────
def _signal_support(desired, p, eb, dom):
    """
    desired 레짐에 대한 3개 시그널 지지 점수 합산 (0~3).
    각 시그널이 desired와 일치하면 +1.
    """
    s = 0
    # Signal 1: 가격 방향
    if   desired == "bear":
        s += int(p == "down")
    elif desired == "sideways":
        s += int(p == "side")
    else:  # bull_btc / bull_altseason
        s += int(p == "up")

    # Signal 2: ETH/BTC
    if   desired == "bull_altseason":
        s += int(eb == "up")             # ETH/BTC 상승 = 알트 강세
    elif desired == "bull_btc":
        s += int(eb == "down")           # ETH/BTC 하락 = BTC 강세
    elif desired == "bear":
        s += int(eb in ("down", "side")) # ETH/BTC 약세 = 리스크오프
    else:  # sideways
        s += int(eb == "side")

    # Signal 3: BTC.D
    if   desired == "bull_altseason":
        s += int(dom == "down")          # BTC.D 하락 = 알트시즌
    elif desired == "bull_btc":
        s += int(dom == "up")            # BTC.D 상승 = BTC 강세
    elif desired == "bear":
        s += int(dom in ("up", "side"))  # BTC.D 보합·상승 = 리스크오프
    else:  # sideways
        s += int(dom == "side")

    return s


# ── V1 레짐 맵 (비교용, 기존 로직) ──────────────────────────────────────────
def _build_regime_map_v1():
    """기존 2-signal 레짐 (BTC 200MA slope + alt-basket proxy). 비교 전용."""
    btc = detlib.load_ohlcv(MARKET, TF)
    bdate = [r["date"] for r in btc]
    bcl   = [r["c"]    for r in btc]
    ma    = sma(bcl, MA_P)
    altmap = {}
    for a in ALTS:
        try:
            altmap[a] = {r["date"]: r["c"] for r in detlib.load_ohlcv(a, TF)}
        except FileNotFoundError:
            pass
    reg = {}
    for i, d in enumerate(bdate):
        if ma[i] is None or i - SLOPE_LB < 0 or ma[i - SLOPE_LB] is None or i - DOM_LB < 0:
            continue
        slope = (ma[i] - ma[i - SLOPE_LB]) / ma[i - SLOPE_LB]
        price = "up" if slope > SLOPE_THR else "down" if slope < -SLOPE_THR else "side"
        d0 = bdate[i - DOM_LB]
        btc_ret = bcl[i] / bcl[i - DOM_LB] - 1
        alt_rets = [m[d] / m[d0] - 1 for m in altmap.values() if d in m and d0 in m and m[d0] > 0]
        alt_med  = st.median(alt_rets) if alt_rets else 0.0
        dom_rising = btc_ret > alt_med
        if price == "down":
            reg[d] = "bear"
        elif price == "side":
            reg[d] = "sideways"
        else:
            reg[d] = "bull_btc" if dom_rising else "bull_altseason"
    return reg


# ── V2 레짐 맵 (공개 API) ──────────────────────────────────────────────────
def build_regime_map():
    """
    date -> regime  (3-signal majority vote with hysteresis)
    스케줄러가 호출하는 공개 함수. 기존 인터페이스 유지.
    """
    btc = detlib.load_ohlcv(MARKET, TF)
    eth = detlib.load_ohlcv("ETH", TF)
    alts_rows = {}
    for a in ALTS:
        try:
            alts_rows[a] = detlib.load_ohlcv(a, TF)
        except FileNotFoundError:
            pass

    price_sig  = _price_signal(btc)
    ethbtc_sig = _ethbtc_signal(btc, eth)
    dom_sig    = _dom_signal_hybrid(btc, alts_rows)

    all_dates = sorted(set(price_sig) & set(ethbtc_sig))
    reg = {}
    prev = None
    for d in all_dates:
        p   = price_sig.get(d, "side")
        eb  = ethbtc_sig.get(d, "side")
        dom = dom_sig.get(d, "side")

        # 후보 레짐 결정
        if p == "down":
            candidate = "bear"
        elif p == "side":
            candidate = "sideways"
        else:  # up → alt vs btc 다수결
            alt_v = int(eb == "up")  + int(dom == "down")
            btc_v = int(eb == "down") + int(dom == "up")
            candidate = "bull_altseason" if alt_v > btc_v else "bull_btc"

        # hysteresis: 2+ 시그널 지지 시에만 전환
        if prev is None or _signal_support(candidate, p, eb, dom) >= 2:
            reg[d] = candidate
        else:
            reg[d] = prev
        prev = reg[d]

    return reg


# ── 패턴별 레짐 기대값 ─────────────────────────────────────────────────────
def pattern_by_regime(pid, regmap):
    try:
        mod = importlib.import_module(f"detector_{pid}")
    except ModuleNotFoundError:
        return {rg: dict(n=0, mean=None) for rg in REGIMES}
    det = getattr(mod, "detect", None) or getattr(mod, "detect_sweeps", None)
    if det is None:
        return {rg: dict(n=0, mean=None) for rg in REGIMES}
    buckets = {rg: [] for rg in REGIMES}
    for sym in mod.SYMBOLS:
        try:
            rows = mod.load_ohlcv(sym, TF)
        except (FileNotFoundError, AttributeError):
            continue
        for si in det(rows):
            rg = regmap.get(rows[si]["date"])
            if rg:
                buckets[rg].append(mod.outcome(rows, si)[1])
    return {rg: (dict(n=len(v), mean=round(st.mean(v), 5)) if v else dict(n=0, mean=None))
            for rg, v in buckets.items()}


# ── 개선 판정 ──────────────────────────────────────────────────────────────
def _separation_score(table, long_pats=("engulfing", "fvg"),
                      short_pats=("engulfing_short", "fvg_short")):
    """
    레짐 분리 점수:
      - bull_btc에서 long 패턴 기대값 높을수록 +
      - bull_altseason에서 short 패턴 기대값 높을수록 +
      - bear에서 long 패턴 기대값 낮을수록 +
    단순 합산. 높을수록 레짐 라벨링이 잘 된 것.
    """
    score = 0.0
    for pid in long_pats:
        pr = table.get(pid, {})
        bull_btc_mean = (pr.get("bull_btc") or {}).get("mean") or 0
        bear_mean     = (pr.get("bear")     or {}).get("mean") or 0
        score += bull_btc_mean - bear_mean   # bull_btc가 bear보다 높으면 +

    for pid in short_pats:
        pr = table.get(pid, {})
        alt_mean  = (pr.get("bull_altseason") or {}).get("mean") or 0
        bear_mean = (pr.get("bear")           or {}).get("mean") or 0
        score += alt_mean + bear_mean          # short 기대값이 alt+bear 둘 다 높으면 +

    return round(score, 5)


# ── main ───────────────────────────────────────────────────────────────────
def main():
    print("=" * 78)
    print("레짐 스위치 v2 - 3-signal (BTC 가격 + ETH/BTC + BTC.D hybrid)")
    print("=" * 78)

    print("\n[V1] 기존 2-signal 레짐 계산...")
    reg_v1 = _build_regime_map_v1()
    cnt_v1 = Counter(reg_v1.values())

    print("[V2] 신규 3-signal 레짐 계산...")
    reg_v2 = build_regime_map()
    cnt_v2 = Counter(reg_v2.values())

    print(f"\n레짐 분포 비교 (일수):")
    print(f"  {'':20} {'V1(기존)':>12} {'V2(신규)':>12}")
    print("  " + "-" * 46)
    for rg in REGIMES:
        print(f"  {rg:<20} {cnt_v1.get(rg, 0):>12} {cnt_v2.get(rg, 0):>12}")

    # 레짐 변화 날짜 비교
    common = sorted(set(reg_v1) & set(reg_v2))
    changed = sum(1 for d in common if reg_v1[d] != reg_v2[d])
    print(f"\n  V1↔V2 레짐 불일치 일수: {changed}/{len(common)} "
          f"({changed/len(common)*100:.1f}%)")

    # 패턴별 기대값 비교
    EVAL_PATS = ["engulfing", "engulfing_short", "fvg", "fvg_short"]
    print(f"\n패턴 기대값 비교 (롱 패턴은 bull_btc↑ 목표, 숏 패턴은 bull_altseason↑):")
    hdr = f"  {'패턴':<20} {'레짐':<16} {'V1 mean':>10} {'V2 mean':>10} {'개선':>6}"
    print(hdr)
    print("  " + "-" * 65)

    tbl_v1, tbl_v2 = {}, {}
    for pid in EVAL_PATS:
        pr1 = pattern_by_regime(pid, reg_v1)
        pr2 = pattern_by_regime(pid, reg_v2)
        tbl_v1[pid] = pr1
        tbl_v2[pid] = pr2
        for rg in ("bull_btc", "bull_altseason", "bear"):
            m1 = (pr1[rg]["mean"] or 0) * 100
            m2 = (pr2[rg]["mean"] or 0) * 100
            n1 = pr1[rg]["n"]
            n2 = pr2[rg]["n"]
            delta = m2 - m1
            arrow = "↑" if delta > 0.01 else ("↓" if delta < -0.01 else "=")
            print(f"  {pid:<20} {rg:<16} "
                  f"{m1:>+8.2f}%(n{n1}) {m2:>+8.2f}%(n{n2}) {arrow}{delta:>+5.2f}%")

    # 분리 점수 비교
    score_v1 = _separation_score(tbl_v1)
    score_v2 = _separation_score(tbl_v2)
    adopted  = score_v2 > score_v1

    print(f"\n분리 점수: V1={score_v1:+.4f}  V2={score_v2:+.4f}  "
          f"→ {'V2 채택 (개선)' if adopted else 'V1 유지 (개선 없음)'}")

    # 저장할 레짐 결정
    reg_final = reg_v2  # 3-signal 신규 레짐 항상 사용 (ETH/BTC + BTC.D 추가로 더 많은 정보 활용)
    if not adopted:
        print("  ※ 분리 점수는 개선 없으나 신호 다양성 확보를 위해 V2 유지")

    cnt_final = Counter(reg_final.values())
    latest = max(reg_final)
    current_regime = reg_final[latest]

    # 현재 시그널 상세 출력
    btc = detlib.load_ohlcv(MARKET, TF)
    eth = detlib.load_ohlcv("ETH", TF)
    alts_rows = {a: detlib.load_ohlcv(a, TF) for a in ALTS
                 if os.path.exists(f"data/{a.lower()}_1d.csv")}
    p_sig = _price_signal(btc)
    e_sig = _ethbtc_signal(btc, eth)
    d_sig = _dom_signal_hybrid(btc, alts_rows)
    print(f"\n현재({latest}) 시그널:")
    print(f"  BTC 200MA 기울기 : {p_sig.get(latest, 'N/A')}")
    print(f"  ETH/BTC 기울기   : {e_sig.get(latest, 'N/A')}")
    print(f"  BTC.D 방향       : {d_sig.get(latest, 'N/A')}")
    print(f"  최종 레짐        : {current_regime}")

    # regime_switch.json 저장 (전체 패턴 포함)
    all_pats = ["engulfing", "engulfing_short", "fvg", "fvg_short",
                "inverse_hs", "inverse_hs_short", "order_block", "order_block_short"]
    table_all = {}
    for pid in all_pats:
        table_all[pid] = pattern_by_regime(pid, reg_final)

    # ── V3: 온체인 보조 신호 적용 ──────────────────────────────────────────────
    onchain_data = {}
    regime_v3    = current_regime
    try:
        import onchain_signals as oc
        print("\n[온체인] 보조 신호 수집 중...")
        onchain_data = oc.fetch(use_cache=True)
        regime_v3    = oc.adjust_regime(current_regime, onchain_data)

        oc_score = onchain_data.get("score", 0)
        fund_sig = onchain_data.get("funding", {}).get("signal", "—")
        etf_sig  = onchain_data.get("etf",     {}).get("signal", "—")
        stab_sig = onchain_data.get("stable",  {}).get("signal", "—")
        print(f"\n[온체인] 보조 신호 결과:")
        print(f"  펀딩비       : {fund_sig}")
        print(f"  ETF 순유입   : {etf_sig}")
        print(f"  스테이블코인 : {stab_sig}")
        print(f"  종합 점수    : {oc_score:+d}")
        if regime_v3 != current_regime:
            print(f"  레짐 조정    : {current_regime} → {regime_v3} (온체인 완화)")
        else:
            print(f"  레짐 변화 없음: {current_regime} 유지")
    except Exception as e:
        print(f"\n[온체인] 수집 실패(무시): {str(e)[:80]}")

    json.dump(
        {
            "version": "v3",
            "regime_days": dict(cnt_final),
            "separation_score": {"v1": score_v1, "v2": score_v2, "adopted": adopted},
            "by_pattern": table_all,
            "signal_details": {
                latest: {
                    "price_sig":  p_sig.get(latest),
                    "ethbtc_sig": e_sig.get(latest),
                    "dom_sig":    d_sig.get(latest),
                    "primary_regime": current_regime,
                    "final_regime":   regime_v3,
                }
            },
            "onchain": {
                "score":   onchain_data.get("score", 0),
                "funding": onchain_data.get("funding", {}),
                "etf":     onchain_data.get("etf",     {}),
                "stable":  onchain_data.get("stable",  {}),
                "fetched_at": onchain_data.get("fetched_at", ""),
            },
        },
        open("regime_switch.json", "w", encoding="utf-8"),
        ensure_ascii=False,
        indent=2,
    )
    print("\n[저장] regime_switch.json (v3: primary + onchain)")
    return reg_final


if __name__ == "__main__":
    main()
