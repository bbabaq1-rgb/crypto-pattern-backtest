"""
detector_vwap_rev_short_4h.py — VWAP 이탈→복귀 숏 신호 (4h).

정의:
  당일 VWAP + 2σ 위로 이탈 후 밴드 안으로 복귀 → 숏 신호.
"""
import detlib
from collections import defaultdict


def _build_vwap_data(rows):
    date_idx = defaultdict(list)
    for i, r in enumerate(rows):
        date_idx[r["date"][:10]].append(i)
    result = {}
    for indices in date_idx.values():
        cum_v = cum_tpv = cum_tp2v = 0.0
        n = 0
        for idx in sorted(indices):
            r  = rows[idx]
            tp = (r["h"] + r["l"] + r["c"]) / 3
            v  = r["v"]
            cum_v   += v; cum_tpv += tp * v; cum_tp2v += tp * tp * v
            n += 1
            if cum_v > 0:
                vwap = cum_tpv / cum_v
                std  = max(0.0, cum_tp2v / cum_v - vwap * vwap) ** 0.5
                result[idx] = (vwap, std, n)
    return result


def detect(rows):
    vwap_data = _build_vwap_data(rows)
    signals   = []
    for i in range(1, len(rows)):
        prev = vwap_data.get(i - 1)
        curr = vwap_data.get(i)
        if prev is None or curr is None:
            continue
        vp, sp, np = prev
        vc, sc, nc = curr
        if np < 3 or sp < 1e-9:
            continue
        upper = vp + 2 * sp
        # 전봉: 상단 이탈 / 현봉: 밴드 복귀
        if rows[i-1]["c"] > upper and rows[i]["c"] <= upper:
            signals.append(i)
    return signals


def load_ohlcv(sym, tf="4h"):
    return detlib.load_ohlcv(sym, tf)


evaluate = detlib.make_evaluate(detect, direction="short")
