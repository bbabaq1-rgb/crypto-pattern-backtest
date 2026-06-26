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

_fetch_failed: set = set()  # 이번 실행에서 이미 실패한 (sym, tf) 캐시


def _auto_fetch(sym, tf):
    """CSV가 없을 때 fetch_data.py로 자동 다운로드. 실패 시 거래소 순서대로 폴백."""
    import sys, os, subprocess
    key = (sym, tf)
    if key in _fetch_failed:
        return  # 이미 실패 확인 -> 즉시 스킵 (같은 프로세스 내 재시도 방지)
    os.makedirs("data", exist_ok=True)
    print(f"  [auto-fetch] {sym} {tf} 없음 -> 다운로드 시도...", flush=True)
    for ex in ("binance", "bybit", "okx"):
        print(f"  [auto-fetch] {ex} 시도...", flush=True)
        r = subprocess.run(
            [sys.executable, "fetch_data.py", "--exchange", ex,
             "--symbol", f"{sym}/USDT", "--timeframe", tf,
             "--since", "2021-01-01", "--out", CSV(sym, tf)])
        if r.returncode == 0:
            print(f"  [auto-fetch] {ex} OK", flush=True)
            return
    print(f"  [auto-fetch] 실패: {sym} {tf} 모든 거래소 불가 - 스킵", flush=True)
    _fetch_failed.add(key)  # 실패 캐시 -> 이후 같은 심볼 즉시 스킵
    # 파일이 없으면 load_ohlcv 에서 FileNotFoundError 발생 -> 호출부 except 로 처리


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
