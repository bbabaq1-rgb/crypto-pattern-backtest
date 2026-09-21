"""업비트 KRW 일봉 '슈팅'(하루 +50% 이상) 사례의 차트 공통점 — 탐색적 스터디 (2026-09-21, 사용자 지시).

질문: "최근 한 달 안에 일봉 50% 이상 슈팅이 나온 코인들은 슈팅 난 날 이평선 안 캔들 위치·거래량·패턴에
어떤 공통점이 있나".

**배포 판정이 아니다.** 사전 등록도 아니고 게이트도 없다. 관찰 결과를 진입 후보로 쓰려면 별도 사전 등록.

설계 요점(결과 전 고정):
· 사건 = 닫힌 일봉에서 (종가/전일종가 − 1) ≥ +50%. 형성 중인 오늘 봉은 제외. 창은 마지막 닫힌 봉 기준 30일.
  고가 기준(고가/전일종가 ≥ 1.5)은 별도 집계만.
· **공통점은 '전날(D−1)'에서 찾는다.** 슈팅 당일(D)의 거래량 폭증·장대 양봉은 정의상 따라오는 것이라
  공통점이 아니라 동어반복이다. D 의 모양은 참고로만 병기한다.
· **베이스라인 없이는 공통점이 아니다.** 하락장에선 모든 코인이 이평선 아래 있으므로 '이평선 아래'는
  슈팅의 특징이 아니다. 같은 창의 모든 코인-일(사건일 제외)을 베이스라인으로 두고, 사건 D−1 의 특성
  분포가 베이스라인과 어디서 갈리는지를 본다(중앙값 비교 + 사건이 베이스라인 중앙값 위에 있는 비율).
· 신규 상장(D 이전 이력 60봉 미만)은 이평선 자체가 없으므로 **따로 센다**(상장 펌프는 다른 현상).
· 후행(D+1~D+5)은 짧게 병기 — 공통점을 찾아도 그 뒤가 어떤지 모르면 쓸모가 없다.

실행: python study_upbit_shooting.py [--days 30] [--thr 0.5] [--no-fetch]
출력: _upbit_shooting.json + 표.
"""
import json
import os
import statistics as st
import sys
import time
import urllib.parse
import urllib.request

OUT = "_upbit_shooting.json"
CACHE = "data_upbit_krw_1d.json"
WINDOW_DAYS = 30
THR = 0.50
BARS = 400              # MA180 + 창 30일 + 여유
MIN_HIST = 60           # 이력 60봉 미만 = 신규 상장 취급
MAS = (5, 20, 60, 120, 180)


# ─────────────────────────────────────────── 수집 ───────────────────────────────────────────
def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def krw_markets():
    d = _get("https://api.upbit.com/v1/market/all?isDetails=false")
    return sorted(m["market"] for m in d if m["market"].startswith("KRW-"))


def load_days(market, bars=BARS):
    out, to = {}, None
    for _ in range((bars + 199) // 200):
        u = f"https://api.upbit.com/v1/candles/days?market={market}&count=200"
        if to:
            u += "&to=" + urllib.parse.quote(to)
        d = _get(u)
        if not d:
            break
        for c in d:
            out[c["candle_date_time_kst"][:10]] = c
        to = d[-1]["candle_date_time_utc"].replace("T", " ")
        time.sleep(0.12)
    return [dict(date=k, o=v["opening_price"], h=v["high_price"], l=v["low_price"], c=v["trade_price"],
                 v=v["candle_acc_trade_volume"], krw=v["candle_acc_trade_price"])
            for k, v in sorted(out.items())]


def fetch_all(no_fetch=False):
    if no_fetch and os.path.exists(CACHE):
        return json.load(open(CACHE, encoding="utf-8"))
    data, mk = {}, krw_markets()
    print(f"[수집] 업비트 KRW {len(mk)} 종목 × {BARS}봉", flush=True)
    for i, m in enumerate(mk):
        try:
            data[m] = load_days(m)
        except Exception as e:
            print(f"  {m} 실패: {str(e)[:60]}")
        if (i + 1) % 50 == 0:
            print(f"  {i+1}/{len(mk)}", flush=True)
    json.dump(data, open(CACHE, "w", encoding="utf-8"))
    return data


# ─────────────────────────────────────────── 지표 ───────────────────────────────────────────
def sma(xs, n, i):
    return sum(xs[i - n + 1:i + 1]) / n if i + 1 >= n else None


def rsi(cl, i, n=14):
    if i < n:
        return None
    g = l = 0.0
    for j in range(i - n + 1, i + 1):
        d = cl[j] - cl[j - 1]
        g += max(d, 0); l += max(-d, 0)
    return 100.0 if l == 0 else 100 - 100 / (1 + g / l)


def atr(rows, i, n=14):
    if i < n:
        return None
    trs = [max(r["h"] - r["l"], abs(r["h"] - p["c"]), abs(r["l"] - p["c"]))
           for p, r in zip(rows[i - n:i], rows[i - n + 1:i + 1])]
    return sum(trs) / n


def pct_rank(x, pool):
    return sum(1 for p in pool if p < x) / len(pool) if pool else None


def features(rows, i):
    """i 번째 봉(닫힌 봉)의 '그 시점까지' 만 쓰는 특성. 이력이 모자라면 None."""
    if i < MIN_HIST:
        return None
    cl = [r["c"] for r in rows]
    vol = [r["v"] for r in rows]
    c, r = cl[i], rows[i]
    f = {}
    ma = {n: sma(cl, n, i) for n in MAS}
    for n in MAS:
        f[f"dist_ma{n}"] = (c / ma[n] - 1) if ma[n] else None
    avail = [n for n in MAS if ma[n]]
    f["n_ma_above"] = sum(1 for n in avail if c > ma[n])           # 몇 개 이평선 위에 있나
    f["n_ma_avail"] = len(avail)
    f["ma_aligned_bull"] = int(len(avail) >= 3 and all(ma[a] > ma[b] for a, b in zip(avail, avail[1:])))
    f["ma_aligned_bear"] = int(len(avail) >= 3 and all(ma[a] < ma[b] for a, b in zip(avail, avail[1:])))
    m20p = sma(cl, 20, i - 20) if i >= 40 else None
    f["ma20_slope20"] = (ma[20] / m20p - 1) if (ma[20] and m20p) else None
    m60p = sma(cl, 60, i - 20) if i >= 80 else None
    f["ma60_slope20"] = (ma[60] / m60p - 1) if (ma[60] and m60p) else None
    # 거래량·거래대금
    v20 = sum(vol[i - 20:i]) / 20
    f["vol_ratio20"] = vol[i] / v20 if v20 else None
    f["vol_ratio20_prev5"] = (sum(vol[i - 4:i + 1]) / 5) / v20 if v20 else None
    k20 = sum(x["krw"] for x in rows[i - 20:i + 1]) / 21
    f["turnover20_krw"] = k20
    # 수익률·위치
    f["ret5"] = c / cl[i - 5] - 1
    f["ret20"] = c / cl[i - 20] - 1
    f["ret60"] = c / cl[i - 60] - 1
    hi120 = max(x["h"] for x in rows[max(0, i - 120):i + 1]); lo60 = min(x["l"] for x in rows[i - 60:i + 1])
    f["dd_120h"] = c / hi120 - 1
    f["from_60lo"] = c / lo60 - 1
    hi250 = max(x["h"] for x in rows[max(0, i - 250):i + 1])
    f["dd_250h"] = c / hi250 - 1
    # 압축·변동성
    a = atr(rows, i)
    f["atr14_pct"] = a / c if a else None
    rng20 = (max(x["h"] for x in rows[i - 19:i + 1]) - min(x["l"] for x in rows[i - 19:i + 1])) / c
    f["range20_pct"] = rng20
    sd = st.pstdev(cl[i - 19:i + 1]); bbw = 4 * sd / ma[20] if ma[20] else None
    f["bb_width"] = bbw
    hist_bbw = []
    for j in range(max(20, i - 120), i):
        m = sma(cl, 20, j)
        if m:
            hist_bbw.append(4 * st.pstdev(cl[j - 19:j + 1]) / m)
    f["bb_width_pctile120"] = pct_rank(bbw, hist_bbw) if (bbw and hist_bbw) else None
    f["rsi14"] = rsi(cl, i)
    # 연속·캔들
    streak = 0
    for j in range(i, 0, -1):
        d = cl[j] - cl[j - 1]
        if d == 0:
            break
        s = 1 if d > 0 else -1
        if streak == 0 or (streak > 0) == (s > 0):
            streak += s
        else:
            break
    f["streak"] = streak                                   # +n 연속 양봉 / −n 연속 음봉
    rg = r["h"] - r["l"]
    f["body_pct"] = abs(r["c"] - r["o"]) / rg if rg else 0
    f["upper_wick_pct"] = (r["h"] - max(r["o"], r["c"])) / rg if rg else 0
    f["lower_wick_pct"] = (min(r["o"], r["c"]) - r["l"]) / rg if rg else 0
    f["bull_candle"] = int(r["c"] > r["o"])
    f["day_ret"] = c / cl[i - 1] - 1
    p = rows[i - 1]
    f["inside_bar"] = int(r["h"] <= p["h"] and r["l"] >= p["l"])
    f["nr7"] = int(rg <= min(x["h"] - x["l"] for x in rows[i - 6:i + 1]))
    f["engulf_bull"] = int(r["c"] > r["o"] and p["c"] < p["o"] and r["c"] >= p["o"] and r["o"] <= p["c"])
    f["hammer"] = int(rg > 0 and f["lower_wick_pct"] >= 0.6 and f["body_pct"] <= 0.3)
    f["doji"] = int(rg > 0 and f["body_pct"] <= 0.1)
    # 이력·재발
    f["bars_hist"] = i
    f["shoots60"] = sum(1 for j in range(max(1, i - 60), i + 1) if cl[j] / cl[j - 1] - 1 >= THR)
    f["big_days60"] = sum(1 for j in range(max(1, i - 60), i + 1) if cl[j] / cl[j - 1] - 1 >= 0.2)
    return f


# ─────────────────────────────────────────── 분석 ───────────────────────────────────────────
FEAT_ORDER = [
    ("dist_ma5", "종가 vs MA5"), ("dist_ma20", "종가 vs MA20"), ("dist_ma60", "종가 vs MA60"),
    ("dist_ma120", "종가 vs MA120"), ("dist_ma180", "종가 vs MA180"), ("n_ma_above", "이평선 위 개수(5개 중)"),
    ("ma_aligned_bull", "정배열"), ("ma_aligned_bear", "역배열"), ("ma20_slope20", "MA20 20일 기울기"),
    ("ma60_slope20", "MA60 20일 기울기"),
    ("vol_ratio20", "거래량/20일평균"), ("vol_ratio20_prev5", "최근5일 거래량/20일평균"), ("turnover20_krw", "20일 평균 거래대금(KRW)"),
    ("ret5", "직전 5일 수익"), ("ret20", "직전 20일 수익"), ("ret60", "직전 60일 수익"),
    ("dd_120h", "120일 고점 대비"), ("dd_250h", "250일 고점 대비"), ("from_60lo", "60일 저점 대비"),
    ("atr14_pct", "ATR14/종가"), ("range20_pct", "20일 고저폭/종가"), ("bb_width", "볼밴 폭"),
    ("bb_width_pctile120", "볼밴 폭 120일 백분위(0=최대 수축)"), ("rsi14", "RSI14"),
    ("streak", "연속 양(+)/음(−)봉 수"), ("body_pct", "몸통/범위"), ("upper_wick_pct", "위꼬리/범위"),
    ("lower_wick_pct", "아래꼬리/범위"), ("bull_candle", "양봉"), ("day_ret", "당일 수익"),
    ("inside_bar", "인사이드바"), ("nr7", "NR7"), ("engulf_bull", "상승 장악형"), ("hammer", "망치형"), ("doji", "도지"),
    ("bars_hist", "이력 봉 수"), ("shoots60", "60일 내 +50% 일수(당일 포함)"), ("big_days60", "60일 내 +20% 일수"),
]
BINARY_KEYS = {"ma_aligned_bull", "ma_aligned_bear", "bull_candle", "inside_bar", "nr7", "engulf_bull", "hammer", "doji"}
PCT_KEYS = {"dist_ma5", "dist_ma20", "dist_ma60", "dist_ma120", "dist_ma180", "ma20_slope20", "ma60_slope20",
            "ret5", "ret20", "ret60", "dd_120h", "dd_250h", "from_60lo", "atr14_pct", "range20_pct", "bb_width", "day_ret"}


def med(xs):
    xs = [x for x in xs if x is not None]
    return st.median(xs) if xs else None


def fmt(k, v):
    if v is None:
        return "   n/a"
    if k in PCT_KEYS:
        return f"{v*100:+7.1f}%"
    if k == "turnover20_krw":
        return f"{v/1e8:7.1f}억"
    if k == "bb_width_pctile120":
        return f"{v*100:6.0f}%"
    return f"{v:7.2f}"


def summarize(events, base, key):
    """사건 vs 베이스라인: 중앙값 둘 + 사건이 베이스라인 중앙값보다 큰 비율(0.5 = 구분 없음)."""
    ev = [e[key] for e in events if e.get(key) is not None]
    bs = [b[key] for b in base if b.get(key) is not None]
    if not ev or not bs:
        return None
    bm = st.median(bs)
    frac = sum(1 for x in ev if x > bm) / len(ev)
    ties = sum(1 for x in ev if x == bm) / len(ev)
    return dict(ev_med=st.median(ev), ev_mean=st.fmean(ev), base_med=bm, base_mean=st.fmean(bs),
                frac_above=frac, ties=ties, n_ev=len(ev), n_base=len(bs))


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    days = int(argv[argv.index("--days") + 1]) if "--days" in argv else WINDOW_DAYS
    thr = float(argv[argv.index("--thr") + 1]) if "--thr" in argv else THR
    data = fetch_all("--no-fetch" in argv)

    # 마지막 닫힌 봉 = 전 종목 공통 최신 날짜에서 오늘(형성 중) 제외
    latest = max(r[-1]["date"] for r in data.values() if r)
    print(f"[데이터] {len(data)} 종목 · 최신 봉 {latest} (형성 중 → 제외)")
    import datetime as dt
    last_closed = (dt.date.fromisoformat(latest) - dt.timedelta(days=1)).isoformat()
    win_start = (dt.date.fromisoformat(last_closed) - dt.timedelta(days=days - 1)).isoformat()
    print(f"[창] {win_start} ~ {last_closed} ({days}일) · 문턱 종가 +{thr*100:.0f}%")

    events, young, hi_only, base = [], [], [], []
    post = []
    for m, rows in data.items():
        rows = [r for r in rows if r["date"] <= last_closed]
        for i in range(1, len(rows)):
            d = rows[i]["date"]
            if d < win_start:
                continue
            ret = rows[i]["c"] / rows[i - 1]["c"] - 1
            hret = rows[i]["h"] / rows[i - 1]["c"] - 1
            is_ev = ret >= thr
            if hret >= thr and not is_ev:
                hi_only.append(dict(market=m, date=d, close_ret=ret, high_ret=hret))
            if is_ev:
                if i - 1 < MIN_HIST:
                    young.append(dict(market=m, date=d, ret=ret, bars_before=i - 1))
                    continue
                fpre, fday = features(rows, i - 1), features(rows, i)
                nxt = [rows[i + k]["c"] / rows[i]["c"] - 1 if i + k < len(rows) else None for k in (1, 2, 3, 5)]
                gap = rows[i]["o"] / rows[i - 1]["c"] - 1
                close_pos = (rows[i]["c"] - rows[i]["l"]) / (rows[i]["h"] - rows[i]["l"]) if rows[i]["h"] > rows[i]["l"] else None
                events.append(dict(market=m, date=d, ret=ret, high_ret=hret, gap=gap, close_pos=close_pos,
                                   pre=fpre, day=fday, next=nxt))
            elif i - 1 >= MIN_HIST:
                f = features(rows, i - 1)
                if f:
                    base.append(f)
    events.sort(key=lambda e: -e["ret"])
    print(f"[사건] 종가 +{thr*100:.0f}% 이상 {len(events) + len(young)}건 "
          f"(이력 {MIN_HIST}봉 이상 {len(events)} / 신규상장·이력부족 {len(young)}) · 고가만 도달 {len(hi_only)}건 "
          f"· 베이스라인 코인-일 {len(base)}")

    # ── 사건 목록
    print("\n== 사건 목록 (종가 기준, 이력 충분) ==")
    print(f"{'종목':10} {'날짜':10} {'수익':>7} {'고가':>7} {'갭':>6} {'종가위치':>6} | {'D-1 MA20':>8} {'D-1 MA60':>8} {'D-1 MA180':>9} "
          f"{'위/5':>4} {'D-1 볼폭%':>8} {'D-1 거래량x':>9} {'D-1 RSI':>7} {'20일수익':>8} {'250고점':>8} | {'D+1':>6} {'D+5':>6}")
    for e in events:
        p, n = e["pre"], e["next"]
        print(f"{e['market'][4:]:10} {e['date']:10} {e['ret']*100:+6.0f}% {e['high_ret']*100:+6.0f}% {e['gap']*100:+5.1f}% "
              f"{(e['close_pos'] or 0)*100:5.0f}% | {p['dist_ma20']*100:+7.1f}% {p['dist_ma60']*100:+7.1f}% "
              f"{fmt('dist_ma180', p['dist_ma180']):>9} {p['n_ma_above']:>2}/{p['n_ma_avail']} "
              f"{fmt('bb_width_pctile120', p['bb_width_pctile120']):>8} {p['vol_ratio20']:8.2f}x {p['rsi14']:6.0f} "
              f"{p['ret20']*100:+7.1f}% {p['dd_250h']*100:+7.1f}% | "
              + " ".join(f"{x*100:+5.1f}%" if x is not None else "  n/a " for x in (n[0], n[3])))
    if young:
        print("\n== 신규 상장·이력 부족 (이평선 없음, 별도) ==")
        for y in young:
            print(f"  {y['market'][4:]:10} {y['date']} {y['ret']*100:+6.0f}%  이력 {y['bars_before']}봉")
    if hi_only:
        print(f"\n== 고가만 +{thr*100:.0f}% 도달(종가는 미달) {len(hi_only)}건 ==")
        for h in hi_only:
            print(f"  {h['market'][4:]:10} {h['date']} 종가 {h['close_ret']*100:+6.0f}% 고가 {h['high_ret']*100:+6.0f}%")

    # ── D−1 공통점 vs 베이스라인
    print(f"\n== 슈팅 전날(D-1) 특성 — 사건 {len(events)} vs 베이스라인 코인-일 {len(base)} ==")
    print("  '위 비율' = 사건 D-1 값이 베이스라인 중앙값보다 큰 비율. 0.5 면 구분 없음, 0.8+/0.2- 면 뚜렷.")
    print(f"{'특성':28} {'사건 중앙':>9} {'베이스 중앙':>10} {'위 비율':>7}  판독")
    summ = {}
    for k, name in FEAT_ORDER:
        s = summarize([e["pre"] for e in events], base, k)
        if not s:
            continue
        summ[k] = s
        fa = s["frac_above"]
        # 0/1 특성은 '베이스 중앙값(0 또는 1)보다 큰 비율' 이 발생률과 다른 뜻이 되므로 태그를 붙이지 않는다 — 아래 발생률 표로 본다
        binary = k in BINARY_KEYS
        tag = "" if binary else ("▲ 높음" if fa >= 0.75 else "▼ 낮음" if fa <= 0.25 else ("△" if fa >= 0.65 else "▽" if fa <= 0.35 else ""))
        print(f"{name:28} {fmt(k, s['ev_med']):>9} {fmt(k, s['base_med']):>10} {fa:7.2f}  {tag}")

    # ── 이산 특성(패턴) 발생률
    print("\n== D-1 캔들 패턴 발생률 (사건 vs 베이스라인) ==")
    for k, name in [("engulf_bull", "상승 장악형"), ("hammer", "망치형"), ("doji", "도지"), ("inside_bar", "인사이드바"),
                    ("nr7", "NR7"), ("bull_candle", "양봉"), ("ma_aligned_bull", "정배열"), ("ma_aligned_bear", "역배열")]:
        ev = st.fmean(e["pre"][k] for e in events) if events else 0
        bs = st.fmean(b[k] for b in base) if base else 0
        print(f"  {name:12} 사건 {ev*100:5.1f}%  베이스 {bs*100:5.1f}%  비 {ev/bs if bs else float('nan'):.2f}x")

    # ── 당일(D) 모양 (참고)
    print("\n== 슈팅 당일(D) 모양 — 참고(동어반복 주의) ==")
    for k, name in [("vol_ratio20", "거래량/20일평균"), ("body_pct", "몸통/범위"), ("upper_wick_pct", "위꼬리/범위"),
                    ("dist_ma20", "종가 vs MA20"), ("dist_ma60", "종가 vs MA60"), ("rsi14", "RSI14")]:
        print(f"  {name:14} 중앙 {fmt(k, med([e['day'][k] for e in events]))}")
    print(f"  갭업(시가/전일종가) 중앙 {med([e['gap'] for e in events])*100:+.1f}%  · 종가 위치(범위 내) 중앙 "
          f"{med([e['close_pos'] for e in events])*100:.0f}%")

    # ── 후행
    print("\n== 슈팅 뒤 (D+k 종가 / D 종가) ==")
    for idx, lab in enumerate(("D+1", "D+2", "D+3", "D+5")):
        xs = [e["next"][idx] for e in events if e["next"][idx] is not None]
        if xs:
            print(f"  {lab}: 중앙 {st.median(xs)*100:+.1f}%  평균 {st.fmean(xs)*100:+.1f}%  양수 {sum(1 for x in xs if x>0)/len(xs)*100:.0f}%  n={len(xs)}")

    json.dump(dict(window=[win_start, last_closed], thr=thr, n_markets=len(data), events=events, young=young,
                   high_only=hi_only, n_base=len(base), summary=summ),
              open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print(f"\n[저장] {OUT}")


if __name__ == "__main__":
    main()
