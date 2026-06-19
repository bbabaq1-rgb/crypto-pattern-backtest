"""
detector_engulfing.py — Bullish Engulfing (반전 맥락 한정) 탐지.

정의 (롱 반전 신호):
  (1) 직전 봉 음봉, 당일 봉 양봉이며 당일 몸통이 직전 몸통을 감싼다
      (open[i] <= close[i-1] AND close[i] >= open[i-1]).
  (2) 반전 맥락: 직전/당일 저점이 최근 LOOKBACK봉 최저 부근(LOW_TOL 이내).
  (3) 거래량 동반: 당일 거래량 >= 직전 VOL_LOOKBACK봉 평균의 VOL_MULT배.
  세 조건 AND. 신호 시점 = 엔걸핑 당일(i), 그 종가 기준 라벨링.

라벨(1단계와 동일): 이후 LABEL_WINDOW봉 내 +RISE_THR 선도달=real,
  -FALL_THR 선도달=fake, 그 외 neutral.

orchestrator 표준 인터페이스 evaluate(date_from, date_to) 제공.
"""
import csv
from datetime import datetime, timezone

# ======================================================================
# 파라미터
# ======================================================================
LOOKBACK     = 10       # 반전 맥락(최근 저점) 판정 구간
LOW_TOL      = 0.02     # '최저 부근' 허용 편차 (2%)
VOL_LOOKBACK = 20       # 거래량 기준 평균 봉수
VOL_MULT     = 1.5      # 거래량 동반 배수

LABEL_WINDOW = 20
RISE_THR     = 0.15
FALL_THR     = -0.10

PATTERN = "engulfing"
SYMBOLS = ["BTC", "SOL", "ETH", "BNB", "XRP", "ADA", "AVAX"]
CSV_1D  = lambda s: f"data/{s.lower()}_1d.csv"


def load_ohlcv(sym):
    rows = []
    with open(CSV_1D(sym), newline="") as f:
        for r in csv.DictReader(f):
            ts = int(float(r["timestamp"]))
            d  = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
            rows.append(dict(date=d, o=float(r["open"]), h=float(r["high"]),
                             l=float(r["low"]), c=float(r["close"]),
                             v=float(r["volume"])))
    return rows


def detect(rows):
    """불리시 엔걸핑(반전 맥락) 신호 인덱스 목록."""
    n = len(rows)
    o = [r["o"] for r in rows]; c = [r["c"] for r in rows]
    lo = [r["l"] for r in rows]; v = [r["v"] for r in rows]
    sig = []
    start = max(LOOKBACK, VOL_LOOKBACK) + 1
    for i in range(start, n):
        # (1) 불리시 엔걸핑
        if not (c[i] > o[i] and c[i - 1] < o[i - 1]
                and o[i] <= c[i - 1] and c[i] >= o[i - 1]):
            continue
        # (2) 반전 맥락: 최근 저점 부근
        win_low = min(lo[i - LOOKBACK:i])
        if min(lo[i], lo[i - 1]) > win_low * (1 + LOW_TOL):
            continue
        # (3) 거래량 동반
        base = sum(v[i - VOL_LOOKBACK:i]) / VOL_LOOKBACK
        if base <= 0 or v[i] < VOL_MULT * base:
            continue
        sig.append(i)
    return sig


def label(rows, si):
    base = rows[si]["c"]
    up, dn = base * (1 + RISE_THR), base * (1 + FALL_THR)
    hi = min(si + LABEL_WINDOW, len(rows) - 1)
    for j in range(si + 1, hi + 1):
        if rows[j]["c"] >= up:
            return "real"
        if rows[j]["c"] <= dn:
            return "fake"
    return "neutral"


def evaluate(date_from=None, date_to=None):
    per = {}
    agg = dict(n=0, real=0, fake=0, neutral=0)
    for sym in SYMBOLS:
        try:
            rows = load_ohlcv(sym)
        except FileNotFoundError:
            continue
        cc = dict(n=0, real=0, fake=0, neutral=0)
        for si in detect(rows):
            d = rows[si]["date"]
            if date_from and d < date_from:
                continue
            if date_to and d > date_to:
                continue
            cc["n"] += 1
            cc[label(rows, si)] += 1
        per[sym] = cc
        for k in agg:
            agg[k] += cc[k]
    return dict(agg=agg, per=per)


if __name__ == "__main__":
    r = evaluate()
    print(PATTERN, r["agg"])
