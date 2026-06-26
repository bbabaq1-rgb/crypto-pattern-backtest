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


def _auto_fetch(sym, tf):
    """CSV가 없을 때 fetch_data.py로 자동 다운로드. 451 차단 시 거래소 폴백."""
    import sys, os, subprocess
    os.makedirs("data", exist_ok=True)
    print(f"  [auto-fetch] {sym} {tf} 데이터 없음 -> 다운로드 중...", flush=True)
    for ex in ("binance", "bybit", "okx"):
        r = subprocess.run(
            [sys.executable, "fetch_data.py", "--exchange", ex,
             "--symbol", f"{sym}/USDT", "--timeframe", tf,
             "--since", "2021-01-01", "--out", CSV(sym, tf)],
            capture_output=True, text=True)
        if r.returncode == 0:
            return
        geo = "451" in r.stdout + r.stderr or "restricted location" in r.stdout + r.stderr
        print(f"  [auto-fetch] {ex} {'지역차단(451)' if geo else '실패'} -> {'다음 거래소' if geo else '중단'}")
        if not geo:
            break
    raise RuntimeError(f"fetch_data.py 실패: {sym} {tf} (모든 거래소 시도)")


def load_ohlcv(sym, tf="1d"):
    path = CSV(sym, tf)
    if not __import__("os").path.exists(path):
        _auto_fetch(sym, tf)
    rows = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            ts = int(float(r["timestamp"]))
            d = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
            rows.append(dict(date=d, o=float(r["open"]), h=float(r["high"]),
                             l=float(r["low"]), c=float(r["close"]),
                             v=float(r["volume"])))
    return rows


def outcome(rows, si, direction="long"):
    """트리플배리어. direction='short'이면 라벨/수익 반전(하락 선도달=real)."""
    base = rows[si]["c"]
    up, dn = base * (1 + RISE_THR), base * (1 + FALL_THR)
    hi = min(si + LABEL_WINDOW, len(rows) - 1)
    for j in range(si + 1, hi + 1):
        c = rows[j]["c"]
        if direction == "long":
            if c >= up:
                return "real", c / base - 1 - FEE
            if c <= dn:
                return "fake", c / base - 1 - FEE
        else:                                   # short: 하락=수익
            if c <= dn:
                return "real", (base - c) / base - FEE
            if c >= up:
                return "fake", (base - c) / base - FEE
    r = rows[hi]["c"] / base - 1
    return "neutral", (r - FEE) if direction == "long" else (-r - FEE)


def make_evaluate(detect, direction="long"):
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
                lab, ret = outcome(rows, si, direction)
                cc["n"] += 1; cc[lab] += 1; rets.append(ret)
            per[sym] = cc
            for k in agg:
                agg[k] += cc[k]
        return dict(agg=agg, per=per, rets=rets)
    return evaluate
