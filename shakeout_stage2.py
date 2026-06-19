"""
shakeout_stage2.py — S 후보에 '거래량 터지는 셰이크아웃' 필터 적용 (통계만)

입력 : data/shakeout_stage1_signals.csv  (symbol, metric, date, s_close, label)
       label 은 1단계가 매긴 진짜/페이크/중립을 그대로 재사용(재라벨링 X).

셰이크아웃 필터 (각 S 이후 SCAN_WINDOW봉 안에서 검사, 세 조건 AND):
  1) 신저점 침투 : S 이후 형성된 직전 최저점(running min low)을
                   DIP_PCT 이상 하향 돌파하는 봉 k 가 있다.
  2) 빠른 회복   : k 이후 RECOVER_BARS봉 이내에 종가가 그 직전 최저점 위로 회복.
  3) 거래량 폭발 : 회복 구간(k~회복봉)의 최대 거래량이
                   직전 VOL_LOOKBACK봉 평균 거래량의 VOL_MULT배 이상.

분석: 필터 전(전체) vs 필터 후(셰이크아웃 확인) 의 진짜/페이크/중립 비율을
      전체·종목별로 비교. 끝에 게이트 verdict 자동 판정.
"""
import csv
from collections import defaultdict

# ======================================================================
# 파라미터 (여기만 바꾸면 됨)
# ======================================================================
DIP_PCT       = 0.01    # 신저점 침투 깊이 (직전 최저점 대비 1%)
RECOVER_BARS  = 4       # 신저점 후 회복 허용 봉수
VOL_LOOKBACK  = 20      # 거래량 기준 평균 산출 봉수
VOL_MULT      = 2.0     # 거래량 폭발 배수 (기준평균 대비)
SCAN_WINDOW   = 20      # S 이후 셰이크아웃 탐지 구간(=1단계 label_window)

MIN_N         = 20      # verdict: 최소 표본 수
MIN_TRUE_RATE = 0.55    # verdict: 최소 진짜 비율

IN_CSV  = "data/shakeout_stage1_signals.csv"
CSV_1D  = lambda s: f"data/{s.lower()}_1d.csv"


# ======================================================================
def load_ohlcv(sym):
    """일봉 CSV -> (date->idx 맵, rows[{date,o,h,l,c,v}])"""
    rows, idx = [], {}
    from datetime import datetime, timezone
    with open(CSV_1D(sym), newline="") as f:
        for r in csv.DictReader(f):
            ts = int(float(r["timestamp"]))
            d  = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
            idx[d] = len(rows)
            rows.append(dict(date=d, o=float(r["open"]), h=float(r["high"]),
                             l=float(r["low"]), c=float(r["close"]),
                             v=float(r["volume"])))
    return idx, rows


def shakeout_confirmed(rows, si):
    """S 인덱스 si 에 대해 세 조건 AND 충족 여부."""
    n = len(rows)
    end = min(si + SCAN_WINDOW, n - 1)
    running_min = rows[si]["l"]                      # 직전 최저점(점진 갱신)
    for k in range(si + 1, end + 1):
        # 1) 신저점 침투
        if rows[k]["l"] <= running_min * (1 - DIP_PCT):
            broke_level = running_min                # 돌파당한 직전 최저점
            # 2) RECOVER_BARS 이내 종가 회복
            rec_end = min(k + RECOVER_BARS, n - 1)
            rec_bar = None
            for j in range(k, rec_end + 1):
                if rows[j]["c"] > broke_level:
                    rec_bar = j
                    break
            if rec_bar is not None:
                # 3) 거래량 폭발 (회복 구간 최대 vol vs 직전 VOL_LOOKBACK 평균)
                lo = k - VOL_LOOKBACK
                if lo >= 0:
                    base = sum(rows[m]["v"] for m in range(lo, k)) / VOL_LOOKBACK
                    peak = max(rows[m]["v"] for m in range(k, rec_bar + 1))
                    if base > 0 and peak >= VOL_MULT * base:
                        return True
        running_min = min(running_min, rows[k]["l"])
    return False


def main():
    # 입력 로드
    sig = []
    with open(IN_CSV, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            sig.append(r)

    # 종목별 OHLCV 캐시
    cache = {}
    # before/after 카운터: [n, real, fake, neutral]
    def newc():
        return dict(n=0, real=0, fake=0, neutral=0)
    before_all, after_all = newc(), newc()
    before_sym = defaultdict(newc)
    after_sym  = defaultdict(newc)

    LK = {"진짜": "real", "페이크": "fake", "중립": "neutral"}
    missing = 0

    for r in sig:
        sym, date, label = r["symbol"], r["date"], r["label"]
        key = LK.get(label, "neutral")
        if sym not in cache:
            cache[sym] = load_ohlcv(sym)
        idx, rows = cache[sym]
        if date not in idx:
            missing += 1
            continue
        si = idx[date]

        # 필터 전
        before_all["n"] += 1; before_all[key] += 1
        before_sym[sym]["n"] += 1; before_sym[sym][key] += 1

        # 필터 적용
        if shakeout_confirmed(rows, si):
            after_all["n"] += 1; after_all[key] += 1
            after_sym[sym]["n"] += 1; after_sym[sym][key] += 1

    # ---- 출력 ----
    def rate(c, k):
        return c[k] / c["n"] if c["n"] else 0.0

    def pct(c, k):
        return f"{rate(c,k)*100:5.1f}%" if c["n"] else "  -  "

    def line(name, c):
        return (f"  {name:>6}  n={c['n']:>4}  "
                f"진짜 {c['real']:>3} ({pct(c,'real')})  "
                f"페이크 {c['fake']:>3} ({pct(c,'fake')})  "
                f"중립 {c['neutral']:>3} ({pct(c,'neutral')})")

    print("=" * 74)
    print("shakeout_stage2 - 셰이크아웃 필터 전/후 비교")
    print(f"params: dip_pct={DIP_PCT}, recover_bars={RECOVER_BARS}, "
          f"vol_lookback={VOL_LOOKBACK}, vol_mult={VOL_MULT}, scan_window={SCAN_WINDOW}")
    print("=" * 74)
    if missing:
        print(f"[주의] 날짜 매칭 실패 {missing}건(스킵)")

    print("\n### 전체 ###")
    print("  [필터 전]")
    print(line("ALL", before_all))
    print("  [필터 후]")
    print(line("ALL", after_all))
    keep = after_all["n"] / before_all["n"] * 100 if before_all["n"] else 0
    impr = (rate(after_all, "real") - rate(before_all, "real")) * 100
    print(f"\n  => 진짜비율 {rate(before_all,'real')*100:.1f}% -> {rate(after_all,'real')*100:.1f}% "
          f"({impr:+.1f}%p),  신호 {before_all['n']} -> {after_all['n']} (잔존 {keep:.1f}%)")

    print("\n### 종목별 ###")
    syms = sorted(before_sym.keys())
    for sym in syms:
        print(f"\n[{sym}]")
        print("  전 " + line("", before_sym[sym]).strip())
        print("  후 " + line("", after_sym[sym]).strip())

    # ---- 게이트 verdict ----
    n  = after_all["n"]
    tr = rate(after_all, "real")
    if n < MIN_N:
        verdict = f"보류 (표본부족: n={n} < {MIN_N})"
    elif tr >= MIN_TRUE_RATE:
        verdict = f"통과 (6종목 확대검증 대상: n={n}, 진짜율 {tr*100:.1f}% >= {MIN_TRUE_RATE*100:.0f}%)"
    else:
        verdict = f"기각 (엣지없음: n={n}, 진짜율 {tr*100:.1f}% < {MIN_TRUE_RATE*100:.0f}%)"

    print("\n" + "=" * 74)
    print(f"VERDICT: {verdict}")
    print(f"  (기준: min_n={MIN_N}, min_true_rate={MIN_TRUE_RATE})")
    print("=" * 74)


if __name__ == "__main__":
    main()
