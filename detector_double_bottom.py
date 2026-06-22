"""
detector_double_bottom.py — Double Bottom 탐지 (롱 반전).

정의:
  (1) 두 개의 swing low L1, L2 가 서로 EQ_TOL 이내(동일 지지선), MAX_GAP 이내 간격.
  (2) 사이에 반등 고점(넥라인)이 존재, 그 고점 대비 두 저점이 MIN_DROP 이상 아래.
  (3) L2 이후 종가가 넥라인을 상향 돌파(확정). 신호 = 돌파봉(i) 종가.

라벨/수익(동결): LABEL_WINDOW 트리플배리어 ±10%, ret = 실현 - FEE.
표준 인터페이스 evaluate(date_from, date_to, tf) -> dict(agg, per, rets).
"""
import csv
from datetime import datetime, timezone

PIVOT_HALF = 2
EQ_TOL     = 0.03      # 두 저점 동일수준 허용 (3%)
MAX_GAP    = 60        # 두 저점 최대 간격(봉)
MIN_DROP   = 0.05      # 넥라인 대비 저점 깊이 최소(5%)

LABEL_WINDOW = 20
RISE_THR     = 0.10
FALL_THR     = -0.10
FEE          = 0.002

PATTERN = "double_bottom"
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


def _swing_lows(rows):
    lo = [r["l"] for r in rows]
    out = []
    for i in range(PIVOT_HALF, len(rows) - PIVOT_HALF):
        if lo[i] == min(lo[i - PIVOT_HALF:i + PIVOT_HALF + 1]):
            out.append(i)
    return out


def detect(rows):
    n = len(rows)
    lo = [r["l"] for r in rows]; hi = [r["h"] for r in rows]; cl = [r["c"] for r in rows]
    piv = _swing_lows(rows)
    sig = []
    used = set()
    for a in range(len(piv) - 1):
        L1 = piv[a]
        for b in range(a + 1, len(piv)):
            L2 = piv[b]
            if L2 - L1 > MAX_GAP:
                break
            if L2 - L1 < 3:
                continue
            # 두 저점 동일 수준
            if abs(lo[L2] - lo[L1]) / lo[L1] > EQ_TOL:
                continue
            neck = max(hi[L1 + 1:L2])            # 사이 반등 고점
            if neck <= 0:
                continue
            if (neck - max(lo[L1], lo[L2])) / neck < MIN_DROP:
                continue
            # L2 이후 넥라인 상향 돌파 봉
            brk = None
            for j in range(L2 + 1, min(L2 + MAX_GAP, n)):
                if cl[j] > neck:
                    brk = j
                    break
            if brk is not None and brk not in used:
                used.add(brk)
                sig.append(brk)
            break                                # L1당 첫 쌍만
    return sorted(set(sig))


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
