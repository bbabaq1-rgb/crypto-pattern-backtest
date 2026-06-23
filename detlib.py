"""
detlib.py — detector 공용 부품 (로더/트리플배리어/evaluate 래퍼).
신규 detector는 detect(rows)만 구현하고 evaluate = make_evaluate(detect)로 노출.
라벨/수익 기준 동결: ±10% 트리플배리어, 20봉, 왕복 수수료 0.2%.
"""
import csv
from datetime import datetime, timezone

RISE_THR, FALL_THR, FEE, LABEL_WINDOW = 0.10, -0.10, 0.002, 20
SYMBOLS = ["BTC", "SOL", "ETH", "BNB", "XRP", "ADA", "AVAX"]
CSV = lambda s, tf: f"data/{s.lower()}_{tf}.csv"


def load_ohlcv(sym, tf="1d"):
    rows = []
    with open(CSV(sym, tf), newline="") as f:
        for r in csv.DictReader(f):
            ts = int(float(r["timestamp"]))
            d = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
            rows.append(dict(date=d, o=float(r["open"]), h=float(r["high"]),
                             l=float(r["low"]), c=float(r["close"]),
                             v=float(r["volume"])))
    return rows


def outcome(rows, si):
    base = rows[si]["c"]
    up, dn = base * (1 + RISE_THR), base * (1 + FALL_THR)
    hi = min(si + LABEL_WINDOW, len(rows) - 1)
    for j in range(si + 1, hi + 1):
        if rows[j]["c"] >= up:
            return "real", rows[j]["c"] / base - 1 - FEE
        if rows[j]["c"] <= dn:
            return "fake", rows[j]["c"] / base - 1 - FEE
    return "neutral", rows[hi]["c"] / base - 1 - FEE


def make_evaluate(detect):
    def evaluate(date_from=None, date_to=None, tf="1d"):
        per = {}
        agg = dict(n=0, real=0, fake=0, neutral=0)
        rets = []
        for sym in SYMBOLS:
            try:
                rows = load_ohlcv(sym, tf)
            except FileNotFoundError:
                continue
            cc = dict(n=0, real=0, fake=0, neutral=0)
            for si in detect(rows):
                d = rows[si]["date"]
                if date_from and d < date_from:
                    continue
                if date_to and d > date_to:
                    continue
                lab, ret = outcome(rows, si)
                cc["n"] += 1; cc[lab] += 1; rets.append(ret)
            per[sym] = cc
            for k in agg:
                agg[k] += cc[k]
        return dict(agg=agg, per=per, rets=rets)
    return evaluate
