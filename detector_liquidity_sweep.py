"""
detector_liquidity_sweep.py — Liquidity Sweep 탐지 + 라벨링 + 자동 검증 루프 1차.

Liquidity Sweep (네 조건 AND):
  (1) 유동성 풀  : 직전 SWEEP_LOOKBACK봉 안에 서로 EQ_TOL 이내로 모인 저점
                   (swing low)이 2개 이상 = Equal Lows. 풀 레벨 = 그 최저.
  (2) 스윕      : 가격이 풀 최저점을 SWEEP_DEPTH 이상 하향 침투.
  (3) 회복      : RECOVER_BARS 이내 종가가 다시 풀 위로 회복.
  (4) 거래량    : 회복 구간 최대 거래량 >= 직전 VOL_LOOKBACK 평균 x VOL_MULT.

지난 셰이크아웃과의 차이 = (1). 아무 신저점이 아니라 '여러 저점이 모인 의미있는
풀'을 쓸어야 한다 → 데드캣 바운스를 거르는 핵심.

신호 시점: 회복 확정봉(rec_bar). 그 종가 기준으로 라벨링.
라벨(셰이크아웃 1단계와 동일 기준): 이후 LABEL_WINDOW봉 내
  +RISE_THR 선도달 -> 진짜, -FALL_THR 선도달 -> 페이크, 그 외 -> 중립.

실행: 7종목 일봉 -> 종목별+전체 진짜/페이크/중립, gate.py verdict, research_log 기록.
"""
import csv
from datetime import datetime, timezone

import gate
import research_log

# ======================================================================
# 파라미터
# ======================================================================
SWEEP_LOOKBACK = 30      # 유동성 풀 탐색 구간(봉)
EQ_TOL         = 0.005   # Equal Lows 허용 편차 (0.5%)
SWEEP_DEPTH    = 0.005   # 풀 최저점 하향 침투 최소폭 (0.5%)
RECOVER_BARS   = 3       # 스윕 후 회복 허용 봉수
VOL_LOOKBACK   = 20      # 거래량 기준 평균 봉수
VOL_MULT       = 2.0     # 거래량 폭발 배수

LABEL_WINDOW   = 20      # 라벨 관찰 봉수
RISE_THR       = 0.10    # 진짜 상승 임계 (+10%, 대칭 — 2026-06 보정 동결)
FALL_THR       = -0.10   # 페이크 하락 임계 (-10%)
FEE            = 0.002   # 왕복 수수료 (0.2%)

PATTERN = "liquidity_sweep"
SYMBOLS = ["BTC", "SOL", "ETH", "BNB", "XRP", "ADA", "AVAX"]
CSV_1D  = lambda s: f"data/{s.lower()}_1d.csv"


def load_ohlcv(sym):
    rows = []
    with open(CSV_1D(sym), newline="") as f:
        for r in csv.DictReader(f):
            ts = int(float(r["timestamp"]))
            d  = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
            rows.append(dict(date=d, h=float(r["high"]), l=float(r["low"]),
                             c=float(r["close"]), v=float(r["volume"])))
    return rows


def detect_sweeps(rows):
    """확정된 Liquidity Sweep 신호의 (rec_bar 인덱스) 목록."""
    n = len(rows)
    lows   = [r["l"] for r in rows]
    closes = [r["c"] for r in rows]
    vols   = [r["v"] for r in rows]
    signals = []
    k = max(SWEEP_LOOKBACK, VOL_LOOKBACK) + 1
    while k < n:
        lo = k - SWEEP_LOOKBACK
        # (1) 풀: 구간 내 swing low 들 중 EQ_TOL 이내로 모인 게 2개 이상
        swings = [lows[j] for j in range(lo + 1, k - 1)
                  if lows[j] <= lows[j - 1] and lows[j] <= lows[j + 1]]
        if len(swings) >= 2:
            pool_low = min(swings)
            touches = sum(1 for s in swings if s <= pool_low * (1 + EQ_TOL))
            if touches >= 2 and lows[k] <= pool_low * (1 - SWEEP_DEPTH):
                # (2) 스윕 발생. (3) 회복 탐색
                rec_end = min(k + RECOVER_BARS, n - 1)
                rec_bar = None
                for j in range(k, rec_end + 1):
                    if closes[j] > pool_low:
                        rec_bar = j
                        break
                if rec_bar is not None:
                    # (4) 거래량 폭발
                    vlo = k - VOL_LOOKBACK
                    base = sum(vols[vlo:k]) / VOL_LOOKBACK
                    peak = max(vols[k:rec_bar + 1])
                    if base > 0 and peak >= VOL_MULT * base:
                        signals.append(rec_bar)
                        k = rec_bar + 1        # 소비 구간 건너뜀(중복 방지)
                        continue
        k += 1
    return signals


def outcome(rows, si):
    """(label, ret) — 트리플배리어. ret은 수수료 차감 후 실현수익."""
    base = rows[si]["c"]
    up, dn = base * (1 + RISE_THR), base * (1 + FALL_THR)
    hi = min(si + LABEL_WINDOW, len(rows) - 1)
    for j in range(si + 1, hi + 1):
        if rows[j]["c"] >= up:
            return "real", rows[j]["c"] / base - 1 - FEE
        if rows[j]["c"] <= dn:
            return "fake", rows[j]["c"] / base - 1 - FEE
    return "neutral", rows[hi]["c"] / base - 1 - FEE      # 시간정지(window end)


def evaluate(date_from=None, date_to=None):
    """
    오케스트레이터 표준 인터페이스.
    date_from/date_to(YYYY-MM-DD)로 신호 발생일을 필터(OOS 시간분할용).
    반환: dict(agg={n,real,fake,neutral}, per={sym:{...}}, rets=[수수료차감 수익,...])
    """
    per = {}
    agg = dict(n=0, real=0, fake=0, neutral=0)
    rets = []
    for sym in SYMBOLS:
        try:
            rows = load_ohlcv(sym)
        except FileNotFoundError:
            continue
        c = dict(n=0, real=0, fake=0, neutral=0)
        for si in detect_sweeps(rows):
            d = rows[si]["date"]
            if date_from and d < date_from:
                continue
            if date_to and d > date_to:
                continue
            lab, ret = outcome(rows, si)
            c["n"] += 1
            c[lab] += 1
            rets.append(ret)
        per[sym] = c
        for kk in agg:
            agg[kk] += c[kk]
    return dict(agg=agg, per=per, rets=rets)


def main():
    res = evaluate()
    per, agg = res["per"], res["agg"]

    def pct(c, k):
        return f"{c[k]/c['n']*100:5.1f}%" if c["n"] else "  -  "

    print("=" * 70)
    print("detector_liquidity_sweep - 자동 패턴 연구 루프 (첫 손님)")
    print(f"params: sweep_lookback={SWEEP_LOOKBACK}, eq_tol={EQ_TOL}, "
          f"sweep_depth={SWEEP_DEPTH}, recover_bars={RECOVER_BARS}")
    print(f"        vol_lookback={VOL_LOOKBACK}, vol_mult={VOL_MULT}, "
          f"label_window={LABEL_WINDOW}, rise_thr={RISE_THR}, fall_thr={FALL_THR}")
    print("=" * 70)
    print(f"  {'종목':>6}  {'n':>4}  {'진짜':>11}  {'페이크':>11}  {'중립':>11}")
    print("  " + "-" * 52)
    for sym in SYMBOLS:
        c = per.get(sym)
        if not c:
            continue
        print(f"  {sym:>6}  {c['n']:>4}  "
              f"{c['real']:>3} ({pct(c,'real')})  "
              f"{c['fake']:>3} ({pct(c,'fake')})  "
              f"{c['neutral']:>3} ({pct(c,'neutral')})")
    print("  " + "-" * 52)
    print(f"  {'전체':>6}  {agg['n']:>4}  "
          f"{agg['real']:>3} ({pct(agg,'real')})  "
          f"{agg['fake']:>3} ({pct(agg,'fake')})  "
          f"{agg['neutral']:>3} ({pct(agg,'neutral')})")

    # ---- 기대값 미리보기 (정식 판정/로그는 orchestrator 담당) ----
    import statistics as st
    rets = res["rets"]
    n = agg["n"]
    if rets:
        print(f"\n  기대값: 평균={st.mean(rets)*100:+.2f}%, "
              f"중앙값={st.median(rets)*100:+.2f}% (수수료 차감, n={n})")
    print("  (정식 verdict/로그는 orchestrator.py 실행 시)")


if __name__ == "__main__":
    main()
