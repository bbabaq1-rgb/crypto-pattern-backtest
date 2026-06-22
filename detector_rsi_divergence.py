"""
detector_rsi_divergence.py — RSI Bullish Divergence 탐지.

정의 (롱 반전 신호):
  연속된 두 swing low L1, L2 (간격 MAX_GAP 이내)에서
    가격: low[L2] < low[L1]        (가격은 더 낮은 저점)
    RSI : rsi[L2] > rsi[L1]        (RSI는 더 높은 저점) = bullish divergence
  L1의 RSI가 RSI_OVERSOLD 이하(과매도 구간)일 때만 인정.
  신호/진입 시점 = L2 + PIVOT_HALF (스윙로우 확정 시점), 그 종가 기준.

라벨/수익(보정 동결): 이후 LABEL_WINDOW봉 트리플배리어
  +RISE_THR 선도달=real, -FALL_THR 선도달=fake, 그 외 neutral(시간정지).
  ret = 실현수익 - FEE(왕복).

orchestrator 표준 인터페이스 evaluate(date_from, date_to) -> dict(agg, per, rets).
"""
import csv
from datetime import datetime, timezone

# ======================================================================
# 파라미터
# ======================================================================
RSI_PERIOD   = 14
PIVOT_HALF   = 2        # 스윙로우 좌우 폭(확정 지연)
MAX_GAP      = 40       # 두 저점 최대 간격(봉)
RSI_OVERSOLD = 45       # L1 RSI 과매도 상한

LABEL_WINDOW = 20
RISE_THR     = 0.10     # 대칭 (2026-06 보정 동결)
FALL_THR     = -0.10
FEE          = 0.002

PATTERN = "rsi_divergence"
SYMBOLS = ["BTC", "SOL", "ETH", "BNB", "XRP", "ADA", "AVAX"]
CSV = lambda s, tf: f"data/{s.lower()}_{tf}.csv"


def load_ohlcv(sym, tf="1d"):
    rows = []
    with open(CSV(sym, tf), newline="") as f:
        for r in csv.DictReader(f):
            ts = int(float(r["timestamp"]))
            d  = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
            rows.append(dict(date=d, o=float(r["open"]), h=float(r["high"]),
                             l=float(r["low"]), c=float(r["close"]),
                             v=float(r["volume"])))
    return rows


def rsi_series(closes, period=RSI_PERIOD):
    """Wilder RSI. 앞 period개는 None."""
    n = len(closes)
    rsi = [None] * n
    if n <= period:
        return rsi
    gains = losses = 0.0
    for i in range(1, period + 1):
        ch = closes[i] - closes[i - 1]
        gains += max(ch, 0.0); losses += max(-ch, 0.0)
    ag, al = gains / period, losses / period
    rsi[period] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    for i in range(period + 1, n):
        ch = closes[i] - closes[i - 1]
        ag = (ag * (period - 1) + max(ch, 0.0)) / period
        al = (al * (period - 1) + max(-ch, 0.0)) / period
        rsi[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return rsi


def swing_lows(rows):
    """폭 PIVOT_HALF 의 로컬 저점 인덱스 목록."""
    lo = [r["l"] for r in rows]
    n = len(rows)
    out = []
    for i in range(PIVOT_HALF, n - PIVOT_HALF):
        seg = lo[i - PIVOT_HALF:i + PIVOT_HALF + 1]
        if lo[i] == min(seg) and lo[i] <= lo[i - 1] and lo[i] <= lo[i + 1]:
            out.append(i)
    return out


def detect(rows):
    """bullish divergence 신호의 진입 인덱스(=L2+PIVOT_HALF) 목록."""
    closes = [r["c"] for r in rows]
    lo = [r["l"] for r in rows]
    rsi = rsi_series(closes)
    piv = swing_lows(rows)
    sig = []
    for a in range(len(piv) - 1):
        L1 = piv[a]
        if rsi[L1] is None or rsi[L1] > RSI_OVERSOLD:
            continue
        for b in range(a + 1, len(piv)):
            L2 = piv[b]
            if L2 - L1 > MAX_GAP:
                break
            if rsi[L2] is None:
                continue
            # 가격 더 낮은 저점 + RSI 더 높은 저점
            if lo[L2] < lo[L1] and rsi[L2] > rsi[L1]:
                entry = L2 + PIVOT_HALF          # 스윙로우 확정 시점
                if entry < len(rows):
                    sig.append(entry)
                break                            # L1당 첫 divergence만
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
            cc["n"] += 1
            cc[lab] += 1
            rets.append(ret)
        per[sym] = cc
        for k in agg:
            agg[k] += cc[k]
    return dict(agg=agg, per=per, rets=rets)


if __name__ == "__main__":
    import statistics as st
    r = evaluate()
    a = r["agg"]; rr = r["rets"]
    print(PATTERN, a)
    if rr:
        print(f"mean={st.mean(rr)*100:+.2f}% median={st.median(rr)*100:+.2f}% n={len(rr)}")
