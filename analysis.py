"""
analysis.py — 패턴 신호의 레짐별 분해 + 베이스라인 비교 헬퍼.
detector 모듈의 detect/detect_sweeps + outcome + load_ohlcv 를 재사용.
"""
import statistics as st

import regime
import baseline


def _detect_fn(mod):
    return getattr(mod, "detect", None) or getattr(mod, "detect_sweeps")


def per_signal(mod, tf, date_from=None, date_to=None):
    """신호별 (ret, regime) 리스트."""
    det = _detect_fn(mod)
    out = []
    for sym in mod.SYMBOLS:
        try:
            rows = mod.load_ohlcv(sym, tf)
        except FileNotFoundError:
            continue
        reg = regime.classify(rows)
        for si in det(rows):
            d = rows[si]["date"]
            if date_from and d < date_from:
                continue
            if date_to and d > date_to:
                continue
            _, ret = mod.outcome(rows, si)
            out.append((ret, reg[si]))
    return out


def regime_breakdown(signals):
    """레짐별 n/평균/중앙."""
    res = {}
    for rg in ("up", "down", "side", None):
        rr = [r for r, g in signals if g == rg]
        if rr:
            res[rg or "na"] = dict(n=len(rr),
                                   mean=round(st.mean(rr), 5),
                                   median=round(st.median(rr), 5))
    return res


def baseline_compare(mod, tf, obs_mean, obs_median, n):
    """무작위 진입 베이스라인 대비 유의성."""
    pool = baseline.entry_pool(mod, tf)
    return baseline.test(pool, obs_mean, obs_median, n)
