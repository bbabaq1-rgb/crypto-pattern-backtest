"""
backtest_regime_capture.py — 시장 전체 비대칭(집계 cap)을 '레짐 지표'로 검증.

개별 종목 필터로는 역효과였지만(backtest_capture.py), 시장 전체 집계는 다른 질문:
  '알트가 집단적으로 bleed하는 국면(avg_cap 매우 음수) vs 집단적으로 버티는 국면'이
  전략 성과(방식D)를 가르는가?

방법(전부 causal, look-ahead 없음):
  1. 각 종목 일자별 cap_score 롤링 시리즈 → 날짜별 유니버스 평균 = market_cap_breadth.
  2. 20봉 MA와 그 기울기(상승/하락)도 산출.
  3. 각 1d 신호에 '진입일'의 breadth/MA/기울기를 붙여, 시장상태 분위로 D수익 비교.
비교지표: 5분위 mean/Calmar/승률 단조성 + OOS 4구간 안정성.
채택은 하지 않고 '관측/레짐지표 유효성' 판단만(레짐 정의 변경은 REGMAP 재검증 필요).
"""
import sys
import json
import statistics as st

import detlib
from method_d import outcome_d, summ, _calmar
from method_e import PATS_ALL
from relative_strength import CAPTURE_N, CAP_MIN_DAY

import importlib

OOS = [("2021-01-01", "2022-05-31"), ("2022-06-01", "2023-10-31"),
       ("2023-11-01", "2025-03-31"), ("2025-04-01", "2026-12-31")]


def _returns_by_date(rows, btc_by_date):
    """(date, alt_ret, btc_ret) causal 시리즈."""
    out = []
    prev_a = prev_b = None
    for r in rows:
        b = btc_by_date.get(r["date"])
        if b is None:
            continue
        if prev_a and prev_b and prev_a > 0 and prev_b > 0:
            out.append((r["date"], r["c"] / prev_a - 1, b / prev_b - 1))
        prev_a, prev_b = r["c"], b
    return out


def cap_series(rows, btc_by_date):
    """종목의 날짜별 cap_score(롤링 CAPTURE_N). {date: cap}."""
    rets = _returns_by_date(rows, btc_by_date)
    res = {}
    for i in range(len(rets)):
        if i + 1 < CAPTURE_N:
            continue
        win = rets[i + 1 - CAPTURE_N: i + 1]
        up_a = sum(x[1] for x in win if x[2] > 0); up_b = sum(x[2] for x in win if x[2] > 0)
        dn_a = sum(x[1] for x in win if x[2] < 0); dn_b = sum(x[2] for x in win if x[2] < 0)
        n_up = sum(1 for x in win if x[2] > 0); n_dn = sum(1 for x in win if x[2] < 0)
        if n_up < CAP_MIN_DAY or n_dn < CAP_MIN_DAY or up_b == 0 or dn_b == 0:
            continue
        res[win[-1][0]] = max(-1.0, min(1.0, up_a / up_b - dn_a / dn_b))
    return res


def build_breadth():
    """날짜별 유니버스 평균 cap_score + 20MA + 기울기(부호)."""
    btc = detlib.load_ohlcv("BTC", "1d")
    btc_by_date = {r["date"]: r["c"] for r in btc}
    from scheduler import SYMBOLS
    per_date = {}
    for sym in SYMBOLS:
        if sym == "BTC":
            continue
        try:
            rows = detlib.load_ohlcv(sym, "1d")
        except Exception:
            continue
        for d, v in cap_series(rows, btc_by_date).items():
            per_date.setdefault(d, []).append(v)
    dates = sorted(per_date)
    avg = {d: st.mean(per_date[d]) for d in dates if len(per_date[d]) >= 5}
    dates = sorted(avg)
    # 20MA + 기울기
    ma, slope = {}, {}
    seq = [avg[d] for d in dates]
    for i, d in enumerate(dates):
        if i >= 19:
            ma[d] = st.mean(seq[i - 19:i + 1])
            if i >= 24:
                slope[d] = ma[d] - st.mean(seq[i - 24:i - 4])   # 5봉 전 MA 대비
    return avg, ma, slope


def collect_with_breadth(avg, ma, slope):
    recs = []
    for label, direction, detmod, oppmod in PATS_ALL:
        mod = importlib.import_module(detmod)
        opp = importlib.import_module(oppmod) if oppmod else None
        for sym in detlib.SYMBOLS:
            try:
                rows = mod.load_ohlcv(sym, "1d")
            except FileNotFoundError:
                continue
            opp_set = set(opp.detect(rows)) if opp else set()
            for si in mod.detect(rows):
                d = rows[si]["date"]
                if d not in avg:
                    continue
                ret, hold = outcome_d(rows, si, direction, opp_set)
                recs.append(dict(direction=direction, date=d, ret=ret, hold=hold,
                                 mkt=avg[d], ma=ma.get(d), slope=slope.get(d)))
    return recs


def _s(g):
    if not g:
        return None
    rets = [r["ret"] for r in g]
    s = summ(rets, [r["hold"] for r in g])
    s["winrate"] = sum(1 for x in rets if x > 0) / len(rets)
    s["calmar"] = _calmar(s)
    return s


def _quintiles(recs, key):
    vals = sorted(r[key] for r in recs if r.get(key) is not None)
    n = len(vals)
    if n < 50:
        return
    qs = [vals[int(n * q)] for q in (0.2, 0.4, 0.6, 0.8)]
    buckets = [[] for _ in range(5)]
    for r in recs:
        v = r.get(key)
        if v is None:
            continue
        b = sum(1 for q in qs if v > q)
        buckets[b].append(r)
    print(f"  [{key}] 5분위 (낮음→높음)")
    for i, bk in enumerate(buckets):
        s = _s(bk)
        if s:
            print(f"    Q{i+1} {key}[{min(r[key] for r in bk):+.2f}~{max(r[key] for r in bk):+.2f}] "
                  f"n={s['n']:>4} mean={s['mean']*100:+.2f}% wr={s['winrate']*100:.0f}% "
                  f"Calmar={s['calmar']:.2f}")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    print("시장 집계 cap(레짐 지표) 백테스트 — 방식D, causal\n")
    avg, ma, slope = build_breadth()
    print(f"breadth 시리즈: {len(avg)}일 (avg_cap 범위 {min(avg.values()):+.2f}~{max(avg.values()):+.2f}, "
          f"현재 {avg[max(avg)]:+.2f})\n")
    recs = collect_with_breadth(avg, ma, slope)
    longs = [r for r in recs if r["direction"] == "long"]
    print(f"신호 {len(recs)}건 (롱 {len(longs)})\n")

    print("=== 전체 신호: 진입일 시장 avg_cap 분위별 방식D 성과 ===")
    _quintiles(recs, "mkt")
    print("\n=== 롱만: 시장 avg_cap 분위 ===")
    _quintiles(longs, "mkt")
    print("\n=== 롱: 시장 avg_cap의 20MA 기울기(로테이션 방향) 분위 ===")
    _quintiles([r for r in longs if r.get("slope") is not None], "slope")

    # 이분: 시장 bleed 국면(avg_cap<중앙) vs 회복 국면
    med = sorted(r["mkt"] for r in longs)[len(longs) // 2]
    lowg = [r for r in longs if r["mkt"] <= med]
    hig = [r for r in longs if r["mkt"] > med]
    print(f"\n=== 롱 이분 (시장 avg_cap 중앙 {med:+.2f}) ===")
    for tag, g in (("bleed국면(avg_cap 낮음)", lowg), ("회복국면(avg_cap 높음)", hig)):
        s = _s(g)
        if s:
            print(f"  {tag:<26} n={s['n']:>4} mean={s['mean']*100:+.2f}% "
                  f"wr={s['winrate']*100:.0f}% Calmar={s['calmar']:.2f}")
    # OOS 안정성 (낮음 국면 우위가 구간마다 유지되는지)
    print("\n=== OOS 4구간 (롱, bleed국면 vs 회복국면 mean) ===")
    for i, (d0, d1) in enumerate(OOS, 1):
        lo = [r for r in lowg if d0 <= r["date"] <= d1]
        hi = [r for r in hig if d0 <= r["date"] <= d1]
        if lo and hi:
            print(f"  Q{i}: bleed n={len(lo)} {st.mean([r['ret'] for r in lo])*100:+.2f}% | "
                  f"회복 n={len(hi)} {st.mean([r['ret'] for r in hi])*100:+.2f}%")

    json.dump({"cur_avg_cap": round(avg[max(avg)], 4)},
              open("backtest_regime_capture.json", "w"), ensure_ascii=False)


if __name__ == "__main__":
    main()
