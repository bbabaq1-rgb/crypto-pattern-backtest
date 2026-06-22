"""
detector_pin_bar.py — Bullish Pin Bar(해머) 탐지.

정의 (롱 반전 신호):
  (1) 아래꼬리 >= 몸통 x TAIL_MULT, 위꼬리 <= 몸통(작은 위꼬리), 양봉.
  (2) 반전 맥락: 최근 LOOKBACK봉 최저 부근(LOW_TOL 이내).
  (3) 거래량 동반: 당일 거래량 >= 직전 VOL_LOOKBACK봉 평균의 VOL_MULT배.
  신호 = 핀바 당일(i), 그 종가 기준 라벨/수익.

라벨/수익(동결): LABEL_WINDOW 트리플배리어 ±10%, ret = 실현 - FEE.
표준 인터페이스 evaluate(date_from, date_to, tf) -> dict(agg, per, rets).
"""
import csv
from datetime import datetime, timezone

LOOKBACK     = 10
LOW_TOL      = 0.02
TAIL_MULT    = 2.0      # 아래꼬리/몸통 비율
VOL_LOOKBACK = 20
VOL_MULT     = 1.5

LABEL_WINDOW = 20
RISE_THR     = 0.10
FALL_THR     = -0.10
FEE          = 0.002

PATTERN = "pin_bar"
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


def detect(rows):
    n = len(rows)
    lo = [r["l"] for r in rows]; v = [r["v"] for r in rows]
    sig = []
    start = max(LOOKBACK, VOL_LOOKBACK) + 1
    for i in range(start, n):
        o, h, l, c = rows[i]["o"], rows[i]["h"], rows[i]["l"], rows[i]["c"]
        body = abs(c - o); lower = min(o, c) - l; upper = h - max(o, c)
        if body <= 0 or lower < TAIL_MULT * body or upper > body or c <= o:
            continue
        win_low = min(lo[i - LOOKBACK:i])
        if min(l, lo[i - 1]) > win_low * (1 + LOW_TOL):
            continue
        base = sum(v[i - VOL_LOOKBACK:i]) / VOL_LOOKBACK
        if base <= 0 or v[i] < VOL_MULT * base:
            continue
        sig.append(i)
    return sig


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


if __name__ == "__main__":
    import statistics as st
    r = evaluate(); a = r["agg"]; rr = r["rets"]
    print(PATTERN, a, f"mean={st.mean(rr)*100:+.2f}%" if rr else "")
