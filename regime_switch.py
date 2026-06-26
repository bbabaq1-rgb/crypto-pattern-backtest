"""
regime_switch.py — 가격 레짐 + 도미넌스(프록시)로 4국면 자동 판정 + 패턴별 레짐 기대값.

레짐 지표 2종(BTC 1d 기준 시장 레짐):
  가격   : 200봉 MA 기울기(최근 20봉). >+0.1% 상승 / <-0.1% 하락 / 그사이 횡보.
  도미넌스: BTC 도미넌스 방향 프록시 = BTC 30봉수익 vs 알트(6종) 중앙 30봉수익.
           BTC가 더 강하면 BTC.D 상승(알트약세), 약하면 하락(알트시즌).
  ※ 무료 BTC.D 히스토리 신뢰 확보가 어려워, 동일 데이터 기반 상대강도 프록시 사용.

4국면:
  가격상승 + 도미넌스하락 -> bull_altseason
  가격상승 + 도미넌스상승 -> bull_btc
  가격하락               -> bear
  횡보                   -> sideways

출력: 날짜별 레짐 + 패턴(롱/숏)별 레짐 기대값 표. regime_switch.json 저장.
"""
import json
import importlib
import statistics as st

import detlib

MA_P, SLOPE_LB, SLOPE_THR, DOM_LB = 200, 20, 0.001, 30
MARKET = "BTC"
ALTS = ["SOL", "ETH", "XRP", "ADA", "AVAX", "TRX"]  # BNB -> TRX (OKX 수집 가능)
REGIMES = ["bull_altseason", "bull_btc", "bear", "sideways"]
PATTERNS = ["engulfing", "engulfing_short", "fvg", "fvg_short",
            "inverse_hs", "inverse_hs_short", "order_block", "order_block_short"]
TF = "1d"


def sma(x, p):
    out = [None] * len(x); s = 0.0
    for i, c in enumerate(x):
        s += c
        if i >= p: s -= x[i - p]
        if i >= p - 1: out[i] = s / p
    return out


def build_regime_map():
    """date -> regime (BTC 시장 기준)."""
    btc = detlib.load_ohlcv(MARKET, TF)
    bdate = [r["date"] for r in btc]; bcl = [r["c"] for r in btc]
    ma = sma(bcl, MA_P)
    # 알트 date->close
    altmap = {}
    for a in ALTS:
        try:
            rows = detlib.load_ohlcv(a, TF)
        except FileNotFoundError:
            continue
        altmap[a] = {r["date"]: r["c"] for r in rows}
    bidx = {d: i for i, d in enumerate(bdate)}
    reg = {}
    for i, d in enumerate(bdate):
        if ma[i] is None or i - SLOPE_LB < 0 or ma[i - SLOPE_LB] is None or i - DOM_LB < 0:
            continue
        slope = (ma[i] - ma[i - SLOPE_LB]) / ma[i - SLOPE_LB]
        price = "up" if slope > SLOPE_THR else "down" if slope < -SLOPE_THR else "side"
        btc_ret = bcl[i] / bcl[i - DOM_LB] - 1
        d0 = bdate[i - DOM_LB]
        alt_rets = []
        for a, m in altmap.items():
            if d in m and d0 in m and m[d0] > 0:
                alt_rets.append(m[d] / m[d0] - 1)
        alt_med = st.median(alt_rets) if alt_rets else 0.0
        dom_rising = btc_ret > alt_med
        if price == "down":
            reg[d] = "bear"
        elif price == "side":
            reg[d] = "sideways"
        else:
            reg[d] = "bull_btc" if dom_rising else "bull_altseason"
    return reg


def pattern_by_regime(pid, regmap):
    mod = importlib.import_module(f"detector_{pid}")
    det = getattr(mod, "detect", None) or getattr(mod, "detect_sweeps")
    buckets = {rg: [] for rg in REGIMES}
    for sym in mod.SYMBOLS:
        try:
            rows = mod.load_ohlcv(sym, TF)
        except FileNotFoundError:
            continue
        for si in det(rows):
            rg = regmap.get(rows[si]["date"])
            if rg:
                buckets[rg].append(mod.outcome(rows, si)[1])
    return {rg: (dict(n=len(v), mean=round(st.mean(v), 5)) if v else dict(n=0, mean=None))
            for rg, v in buckets.items()}


def main():
    regmap = build_regime_map()
    from collections import Counter
    cnt = Counter(regmap.values())
    print("=" * 78)
    print("레짐 분포(일수):", dict(cnt))
    print("=" * 78)
    table = {}
    print(f"\n  {'패턴':<20} " + " ".join(f"{rg:>16}" for rg in REGIMES))
    print("  " + "-" * 92)
    for pid in PATTERNS:
        pr = pattern_by_regime(pid, regmap)
        table[pid] = pr
        cells = []
        for rg in REGIMES:
            x = pr[rg]
            cells.append(f"{x['mean']*100:+.2f}%(n{x['n']})" if x["mean"] is not None else "  -  ")
        print(f"  {pid:<20} " + " ".join(f"{c:>16}" for c in cells))

    json.dump({"regime_days": dict(cnt), "by_pattern": table},
              open("regime_switch.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("\n[저장] regime_switch.json")


if __name__ == "__main__":
    main()
