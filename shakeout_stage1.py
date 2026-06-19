"""
shakeout_stage1.py — 급락 후 변동성 수축점(S) 탐지 + 진짜/페이크 라벨링 (통계만, 매매 X)

로직
  1) 급락 구간: 직전 LOOKBACK_FAST봉 동안 고점(window 내 최고 종가) 대비
     종가가 DROP_MIN 이상 하락한 봉 t 를 '급락 종료봉'으로 본다.
  2) 변동성 수축: t 직후 FLAT_BARS봉의 변동성 지표가 모두 급락구간 평균의
     CONTRACT_RATIO 이하이면, 그 시작점(t+1)을 S로 기록.
  3) 변동성 지표 3종을 각각 따로 계산해 S 목록을 3개 만든다:
       (a) body  = |close-open|     캔들 몸통
       (b) range = high-low         고저 변동폭
       (c) atr14 = ATR(14)          평균 진폭
  4) 라벨링(S 종가 기준, 이후 LABEL_WINDOW봉 안에서 먼저 닿는 쪽):
       종가 >= S*(1+RISE_THR)  먼저 -> '진짜'
       종가 <= S*(1+FALL_THR)  먼저 -> '페이크'  (FALL_THR은 음수)
       둘 다 아니면                  -> '중립'

출력: (종목 x 지표3종) S개수·진짜/페이크/중립 개수+비율 표, 7종목 합산,
      각 S의 (종목,지표,날짜,S종가,라벨) CSV 저장(2단계 재사용).
"""
import csv
from datetime import datetime, timezone

# ======================================================================
# 파라미터 (여기만 바꾸면 됨)
# ======================================================================
LOOKBACK_FAST  = 10      # 급락 측정 구간(봉)
DROP_MIN       = 0.15    # 급락 최소 낙폭 (고점 대비, 15%)
CONTRACT_RATIO = 0.5     # 변동성 수축 기준 (급락구간 평균 대비 비율)
FLAT_BARS      = 5       # 수축 상태 최소 유지 봉수
CONTRACT_SEARCH = 15     # 급락 종료 후 수축 '시작점'을 찾는 탐색 봉수
LABEL_WINDOW   = 20      # 라벨 판정 관찰 봉수
RISE_THR       = 0.15    # '진짜' 상승 임계 (+15%)
FALL_THR       = -0.10   # '페이크' 하락 임계 (-10%)

ATR_PERIOD     = 14
SYMBOLS = ["BTC", "SOL", "ETH", "BNB", "XRP", "ADA", "AVAX"]
CSV_PATH = lambda s: f"data/{s.lower()}_1d.csv"
OUT_CSV  = "data/shakeout_stage1_signals.csv"
METRICS  = ["body", "range", "atr14"]


# ======================================================================
def load(sym):
    """CSV -> dict 리스트 [{date, o,h,l,c,v}]"""
    rows = []
    with open(CSV_PATH(sym), newline="") as f:
        for r in csv.DictReader(f):
            ts = int(float(r["timestamp"]))
            d  = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
            rows.append(dict(date=d,
                             o=float(r["open"]), h=float(r["high"]),
                             l=float(r["low"]),  c=float(r["close"])))
    return rows


def compute_metrics(rows):
    """3종 변동성 지표 시계열 계산. atr14는 앞 ATR_PERIOD봉 None."""
    n = len(rows)
    body  = [abs(rows[i]["c"] - rows[i]["o"]) for i in range(n)]
    rng   = [rows[i]["h"] - rows[i]["l"]      for i in range(n)]

    tr = [None] * n
    for i in range(n):
        if i == 0:
            tr[i] = rows[i]["h"] - rows[i]["l"]
        else:
            pc = rows[i - 1]["c"]
            tr[i] = max(rows[i]["h"] - rows[i]["l"],
                        abs(rows[i]["h"] - pc), abs(rows[i]["l"] - pc))
    atr = [None] * n
    for i in range(n):
        if i >= ATR_PERIOD:
            atr[i] = sum(tr[i - ATR_PERIOD + 1:i + 1]) / ATR_PERIOD
    return {"body": body, "range": rng, "atr14": atr}


def find_S(rows, metric_series):
    """변동성 지표 한 종에 대해 S 인덱스 목록(중복 제거)을 반환."""
    n = len(rows)
    closes = [r["c"] for r in rows]
    S = set()
    start = max(LOOKBACK_FAST, ATR_PERIOD)
    for t in range(start, n - FLAT_BARS - 1):
        # 1) 급락: 직전 LOOKBACK_FAST봉 고점(종가) 대비 close[t] 낙폭
        win_hi = max(closes[t - LOOKBACK_FAST + 1:t + 1])
        if win_hi <= 0:
            continue
        drop = (win_hi - closes[t]) / win_hi
        if drop < DROP_MIN:
            continue
        # 급락구간 평균 변동성 (지표값 None이면 스킵)
        seg = metric_series[t - LOOKBACK_FAST + 1:t + 1]
        if any(v is None for v in seg):
            continue
        crash_avg = sum(seg) / len(seg)
        if crash_avg <= 0:
            continue
        thr = CONTRACT_RATIO * crash_avg
        # 2) 급락 종료 후 CONTRACT_SEARCH봉 안에서, 변동성이 thr 이하로
        #    FLAT_BARS봉 연속 유지되는 '첫 시작점' j 를 S로 기록.
        j_max = min(t + CONTRACT_SEARCH, n - FLAT_BARS)
        for j in range(t + 1, j_max + 1):
            run = metric_series[j:j + FLAT_BARS]
            if any(v is None for v in run):
                continue
            if all(v <= thr for v in run):
                S.add(j)            # 수축 시작점
                break               # 첫 onset만
    return sorted(S)


def label_S(rows, s_idx):
    """S 종가 기준 이후 LABEL_WINDOW봉에서 먼저 닿는 쪽으로 라벨."""
    closes = [r["c"] for r in rows]
    base = closes[s_idx]
    up   = base * (1 + RISE_THR)
    dn   = base * (1 + FALL_THR)
    hi = min(s_idx + LABEL_WINDOW, len(rows) - 1)
    for j in range(s_idx + 1, hi + 1):
        if closes[j] >= up:
            return "진짜"
        if closes[j] <= dn:
            return "페이크"
    return "중립"


def main():
    # results[metric][sym] = dict(n, real, fake, neutral)
    results = {m: {} for m in METRICS}
    signals = []   # (sym, metric, date, s_close, label)

    for sym in SYMBOLS:
        try:
            rows = load(sym)
        except FileNotFoundError:
            print(f"[경고] {sym} 일봉 CSV 없음 — 스킵")
            continue
        mser = compute_metrics(rows)
        for m in METRICS:
            S = find_S(rows, mser[m])
            cnt = dict(n=0, real=0, fake=0, neutral=0)
            for s_idx in S:
                lab = label_S(rows, s_idx)
                cnt["n"] += 1
                cnt["real" if lab == "진짜" else "fake" if lab == "페이크" else "neutral"] += 1
                signals.append((sym, m, rows[s_idx]["date"],
                                round(rows[s_idx]["c"], 4), lab))
            results[m][sym] = cnt

    # ---- 표 출력 ----
    def pct(a, b):
        return f"{a/b*100:4.1f}%" if b else "  -  "

    print("=" * 70)
    print("shakeout_stage1 - 급락 후 변동성 수축점(S) 통계")
    print(f"params: lookback_fast={LOOKBACK_FAST}, drop_min={DROP_MIN}, "
          f"contract_ratio={CONTRACT_RATIO}, flat_bars={FLAT_BARS}")
    print(f"        contract_search={CONTRACT_SEARCH}, label_window={LABEL_WINDOW}, "
          f"rise_thr={RISE_THR}, fall_thr={FALL_THR}")
    print("=" * 70)

    for m in METRICS:
        print(f"\n###### 변동성 지표: {m} ######")
        print(f"  {'종목':>5}  {'S수':>4}  {'진짜':>10}  {'페이크':>10}  {'중립':>10}")
        print("  " + "-" * 56)
        agg = dict(n=0, real=0, fake=0, neutral=0)
        for sym in SYMBOLS:
            c = results[m].get(sym)
            if c is None:
                continue
            for k in agg:
                agg[k] += c[k]
            print(f"  {sym:>5}  {c['n']:>4}  "
                  f"{c['real']:>3} ({pct(c['real'], c['n'])})  "
                  f"{c['fake']:>3} ({pct(c['fake'], c['n'])})  "
                  f"{c['neutral']:>3} ({pct(c['neutral'], c['n'])})")
        print("  " + "-" * 56)
        print(f"  {'합산':>5}  {agg['n']:>4}  "
              f"{agg['real']:>3} ({pct(agg['real'], agg['n'])})  "
              f"{agg['fake']:>3} ({pct(agg['fake'], agg['n'])})  "
              f"{agg['neutral']:>3} ({pct(agg['neutral'], agg['n'])})")

    # ---- CSV 저장 ----
    with open(OUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["symbol", "metric", "date", "s_close", "label"])
        w.writerows(signals)
    print(f"\n[저장] S 신호 {len(signals)}건 -> {OUT_CSV}")


if __name__ == "__main__":
    main()
