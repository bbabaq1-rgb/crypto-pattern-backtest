"""
regime_multi.py — 레짐 라벨을 **여러 시간 스케일**로 만든다 (연구용, 2026-09-03).

현행 레짐(regime_switch.build_regime_map)은 일봉 하나다: BTC 200일선 20일 기울기 +
ETH/BTC 20일 기울기 + BTC.D 20일 기울기, 2/3 지지 히스테리시스. 이 모듈은 같은
3-신호 구조를 임의 봉(1w / 1d / 4h / 1h)에 적용해 '주단위 / 일단위 / 시간단위'
스케일의 라벨을 만든다. 실거래 코드는 이 모듈을 쓰지 않는다 — method_m.py 전용.

스케일 정의(사전등록, 2026-09-03):
  slow  : 1w 봉(1d 리샘플)  MA 30주  기울기 4주   ETH/BTC 8주  BTC.D 프록시 8주
  daily : 1d 봉             MA 200일 기울기 20일  ETH/BTC 20일 BTC.D 30일   (= 현행)
  fast  : 4h 봉             MA 200봉 기울기 20봉  ETH/BTC 20봉 BTC.D 30봉   (≈33일/3.3일)
기울기 임계값은 현행 0.1%(20일)을 lookback 일수에 비례해 스케일한다.
BTC.D 는 모든 스케일에서 프록시(BTC vs 알트바스켓 수익 비교)만 쓴다 — CoinGecko 는
일봉 365일뿐이라 스케일 간 공정 비교를 위해 통일.

라벨 유효 시각: 봉이 **닫힌** 시각(ts + 봉 길이)부터. RegimeMap.at(t) 는 t 이전에
닫힌 마지막 봉의 라벨을 준다 — 룩어헤드 없음.
"""
import statistics as st
from bisect import bisect_right

import detlib
from regime_switch import sma, _signal_support, ALTS, MARKET

TF_MS = {"1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000, "1w": 7 * 86_400_000}
BASE_THR, BASE_LB_DAYS = 0.001, 20.0

SCALES = {
    "slow":  dict(tf="1w", ma_p=30,  slope_lb=4,  ethbtc_lb=8,  dom_lb=8,  bar_days=7.0),
    "daily": dict(tf="1d", ma_p=200, slope_lb=20, ethbtc_lb=20, dom_lb=30, bar_days=1.0),
    "fast":  dict(tf="4h", ma_p=200, slope_lb=20, ethbtc_lb=20, dom_lb=30, bar_days=1 / 6),
}


def thr_for(slope_lb, bar_days):
    """기울기 임계값 — 현행(0.1% / 20일)을 lookback 일수에 비례."""
    return BASE_THR * (slope_lb * bar_days) / BASE_LB_DAYS


def load_rows(sym, tf):
    if tf == "1w":
        return detlib.resample_rows(detlib.load_ohlcv(sym, "1d"), "1w")
    return detlib.load_ohlcv(sym, tf)


class RegimeMap:
    """(valid_from_ts, label) 계단 함수."""
    def __init__(self, items):
        items = sorted(items)
        self.ts = [t for t, _ in items]
        self.lab = [l for _, l in items]

    def at(self, t):
        i = bisect_right(self.ts, t) - 1
        return self.lab[i] if i >= 0 else None

    def __len__(self):
        return len(self.ts)

    def first_ts(self):
        return self.ts[0] if self.ts else None


def _slope_labels(vals, ma_p, lb, thr):
    ma = sma(vals, ma_p)
    out = [None] * len(vals)
    for i in range(len(vals)):
        if i < ma_p + lb or ma[i] is None or ma[i - lb] is None or ma[i - lb] == 0:
            continue
        s = (ma[i] - ma[i - lb]) / ma[i - lb]
        out[i] = "up" if s > thr else "down" if s < -thr else "side"
    return out


def build_from_rows(btc, eth, alts, ma_p, slope_lb, ethbtc_lb, dom_lb, tf_ms, thr_price, thr_eth):
    """
    btc/eth/alts: ts 정렬된 rows. 반환 RegimeMap (라벨 유효 시각 = 봉 닫힌 시각).
    현행 build_regime_map 과 같은 후보 결정·히스테리시스.
    """
    bts = [r["ts"] for r in btc]
    bpx = [r["c"] for r in btc]
    price = dict(zip(bts, _slope_labels(bpx, ma_p, slope_lb, thr_price)))
    emap = {r["ts"]: r["c"] for r in eth}
    common = [t for t in bts if t in emap]
    ratio = [emap[t] / bpx[i] for i, t in enumerate(bts) if t in emap]
    ethbtc = dict(zip(common, _slope_labels(ratio, ethbtc_lb, ethbtc_lb, thr_eth)))
    amaps = {s: {r["ts"]: r["c"] for r in rows} for s, rows in alts.items()}
    dom = {}
    for i, t in enumerate(bts):
        if i < dom_lb or bpx[i - dom_lb] == 0:
            continue
        t0 = bts[i - dom_lb]
        br = bpx[i] / bpx[i - dom_lb] - 1
        ar = [m[t] / m[t0] - 1 for m in amaps.values() if t in m and t0 in m and m[t0] > 0]
        if ar:
            dom[t] = "up" if br > st.median(ar) else "down"
    items, prev = [], None
    for t in bts:
        p, eb, dm = price.get(t), ethbtc.get(t), dom.get(t, "side")
        if p is None or eb is None:
            continue
        if p == "down":
            cand = "bear"
        elif p == "side":
            cand = "sideways"
        else:
            alt_v = int(eb == "up") + int(dm == "down")
            btc_v = int(eb == "down") + int(dm == "up")
            cand = "bull_altseason" if alt_v > btc_v else "bull_btc"
        lab = cand if (prev is None or _signal_support(cand, p, eb, dm) >= 2) else prev
        items.append((t + tf_ms, lab))
        prev = lab
    return RegimeMap(items)


def build_scale_map(scale, loader=load_rows):
    cfg = SCALES[scale]
    tf = cfg["tf"]
    btc = loader(MARKET, tf)
    eth = loader("ETH", tf)
    alts = {}
    for a in ALTS:
        try:
            alts[a] = loader(a, tf)
        except (FileNotFoundError, RuntimeError):
            pass
    thr_p = thr_for(cfg["slope_lb"], cfg["bar_days"])
    thr_e = thr_for(cfg["ethbtc_lb"], cfg["bar_days"])
    return build_from_rows(btc, eth, alts, cfg["ma_p"], cfg["slope_lb"], cfg["ethbtc_lb"],
                           cfg["dom_lb"], TF_MS[tf], thr_p, thr_e)
