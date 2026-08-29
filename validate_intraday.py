"""
validate_intraday.py — ≤1h 단타 후보 5종 일괄 검증 (2026-08-29).

배경: 1h 이하에서 기각된 14종은 전부 '단일 종목 OHLCV 모양' 패턴이었고,
총수익 0.1~0.3%를 왕복 수수료 0.2%가 잠식하는 구조였다. 여기서는 축이 다른
5개 가설을 같은 프레임(intraday_lab: ATR 배리어 + TF별 보유한도 +
수수료 마진 게이트)으로 검증한다.

  S1 횡단면 단기 반전  — 최근 k봉 수익률 랭킹 하위 롱 / 상위 숏 (시장중립)
  S2 펀딩비 극단       — 정산시점 횡단면 펀딩 상위 숏 / 하위 롱
  S3 청산 캐스케이드   — 급변+거래량폭증+꼬리회복 봉을 역방향 페이드
  S4 시간대 효과       — 시(UTC)별 전방수익 (Bonferroni 24)
  S5 거래량 쇼크       — 거래량 z>=3 + 봉 방향 추세지속

파라미터는 사전 고정(스윕 없음) — 다중비교 방지. S4만 24개 시를 동시에 보므로
Bonferroni 보정(0.05/24)을 별도 적용한다.

실행: python validate_intraday.py [--no-fetch]
"""
import json
import statistics
import sys
import time
from collections import defaultdict

import intraday_lab as lab

FETCH_WINDOWS = {"1h": 365, "15m": 60}
TFS = ["1h", "15m"]

# ── 사전 고정 파라미터 ───────────────────────────────────────────────────────
S1_LOOKBACK = 6        # 최근 6봉 수익률로 랭킹
S1_FRAC = 0.10         # 상·하위 10%
S2_FRAC = 0.10         # 펀딩 상·하위 10%
S2_SYMS = 30           # 펀딩 이력 수집 종목 수(거래대금 상위)
S2_DAYS = 365
S3_MOVE_ATR = 2.5      # |봉 변동| >= 2.5 x ATR
S3_VOL_MULT = 3.0      # 거래량 >= 20봉 평균 x 3
S3_RECOVER = 0.40      # 종가가 봉 범위의 40% 이상 되돌림(꼬리)
S5_VOL_Z = 3.0         # 거래량 z >= 3


def _universe():
    return json.load(open("universe.json", encoding="utf-8"))["trading_universe"]


def fetch_all(syms):
    import fetch_data
    for tf in TFS:
        t0, ok, new = time.time(), 0, 0
        for s in syms:
            n_new, total = fetch_data.update_csv(
                f"{s}/USDT", tf, lab.CSV(s, tf),
                window_days=FETCH_WINDOWS[tf])
            if total > 0:
                ok += 1
                new += n_new
        print(f"[fetch] {tf}: {ok}/{len(syms)}종목 +{new}봉 "
              f"({time.time()-t0:.0f}s)", flush=True)


def _load_all(tf):
    """{sym: (rows, atr)} — 데이터 없는 종목은 스킵."""
    data = {}
    for s in lab.symbols_with(tf):
        try:
            rows = lab.load_raw(s, tf)
        except Exception:
            continue
        if len(rows) < 100:
            continue
        data[s] = (rows, lab.atr_series(rows))
    return data


def _random_pool(data, horizon, cap=4000):
    """부트스트랩용 무작위 진입 후보."""
    pool = []
    for rows, atr in data.values():
        step = max(1, len(rows) // 60)
        for i in range(20, len(rows) - horizon - 1, step):
            if atr[i]:
                pool.append((rows, atr, i))
    return pool[:cap]


# ── S1 횡단면 단기 반전 ─────────────────────────────────────────────────────
def study_cross_sectional(data, tf, results):
    H = lab.HORIZON[tf]
    # 타임스탬프별 종목 인덱스 정렬
    idx_by_ts = defaultdict(dict)
    for sym, (rows, atr) in data.items():
        for i, r in enumerate(rows):
            idx_by_ts[r["ts"]][sym] = i

    long_sigs, short_sigs = [], []
    for ts in sorted(idx_by_ts):
        members = idx_by_ts[ts]
        if len(members) < 20:            # 횡단면 최소 폭
            continue
        scored = []
        for sym, i in members.items():
            rows, atr = data[sym]
            if i < S1_LOOKBACK or i + H >= len(rows) or not atr[i]:
                continue
            past = rows[i - S1_LOOKBACK]["c"]
            if past <= 0:
                continue
            scored.append((rows[i]["c"] / past - 1, sym, i))
        if len(scored) < 20:
            continue
        scored.sort()
        k = max(1, int(len(scored) * S1_FRAC))
        for _, sym, i in scored[:k]:      # 최근 최약세 -> 롱
            rows, atr = data[sym]
            lb, r = lab.outcome_atr(rows, i, "long", atr, H)
            if r is not None:
                long_sigs.append((rows[i]["date"], r))
        for _, sym, i in scored[-k:]:     # 최근 최강세 -> 숏
            rows, atr = data[sym]
            lb, r = lab.outcome_atr(rows, i, "short", atr, H)
            if r is not None:
                short_sigs.append((rows[i]["date"], r))

    pool = _random_pool(data, H)
    for name, sigs, d in (("S1 횡단면반전 롱(최약세)", long_sigs, "long"),
                          ("S1 횡단면반전 숏(최강세)", short_sigs, "short")):
        boot = lab.bootstrap_baseline(pool, lambda si, dd=d: dd, H)
        results.append(lab.evaluate(f"{name} @{tf}", sigs, boot,
                                    extra=dict(tf=tf, study_id="S1",
                                               direction=d)))


# ── S2 펀딩비 극단 ──────────────────────────────────────────────────────────
def fetch_funding(syms, days=S2_DAYS):
    """OKX 펀딩 이력 (8h 간격). {sym: [(ts, rate)]}"""
    import ccxt
    ex = ccxt.okx({"enableRateLimit": True})
    since0 = int((time.time() - days * 86400) * 1000)
    out = {}
    t0 = time.time()
    for s in syms:
        recs, since = [], since0
        try:
            for _ in range(20):                  # 100개씩 최대 2000건
                batch = ex.fetch_funding_rate_history(f"{s}/USDT:USDT",
                                                      since=since, limit=100)
                if not batch:
                    break
                recs += [(b["timestamp"], float(b["fundingRate"]))
                         for b in batch]
                nxt = batch[-1]["timestamp"] + 1
                if nxt <= since:
                    break
                since = nxt
                if since > time.time() * 1000:
                    break
        except Exception as e:
            print(f"  [funding] {s} 실패: {str(e)[:60]}")
        if recs:
            out[s] = sorted(set(recs))
    print(f"[fetch] funding: {len(out)}/{len(syms)}종목 "
          f"({time.time()-t0:.0f}s)", flush=True)
    return out


def study_funding(data, funding, results):
    """정산시점마다 횡단면 펀딩 상위 10% 숏 / 하위 10% 롱. 진입은 1h 봉 기준."""
    tf, H = "1h", lab.HORIZON["1h"]
    ts_map = defaultdict(dict)
    for sym, recs in funding.items():
        if sym not in data:
            continue
        for ts, rate in recs:
            ts_map[ts - ts % 3600000][sym] = rate   # 시각을 1h 격자에 정렬

    # 심볼별 ts -> index
    pos = {sym: {r["ts"]: i for i, r in enumerate(rows)}
           for sym, (rows, _) in data.items()}

    long_sigs, short_sigs = [], []
    for ts in sorted(ts_map):
        members = {s: v for s, v in ts_map[ts].items() if ts in pos.get(s, {})}
        if len(members) < 15:
            continue
        ranked = sorted(members.items(), key=lambda kv: kv[1])
        k = max(1, int(len(ranked) * S2_FRAC))
        for sym, rate in ranked[:k]:        # 펀딩 최저(숏 과밀) -> 롱
            rows, atr = data[sym]
            i = pos[sym][ts]
            if i + H >= len(rows):
                continue
            _, r = lab.outcome_atr(rows, i, "long", atr, H)
            if r is not None:
                long_sigs.append((rows[i]["date"], r))
        for sym, rate in ranked[-k:]:       # 펀딩 최고(롱 과밀) -> 숏
            rows, atr = data[sym]
            i = pos[sym][ts]
            if i + H >= len(rows):
                continue
            _, r = lab.outcome_atr(rows, i, "short", atr, H)
            if r is not None:
                short_sigs.append((rows[i]["date"], r))

    pool = _random_pool(data, H)
    for name, sigs, d in (("S2 펀딩최저->롱", long_sigs, "long"),
                          ("S2 펀딩최고->숏", short_sigs, "short")):
        boot = lab.bootstrap_baseline(pool, lambda si, dd=d: dd, H)
        results.append(lab.evaluate(f"{name} @1h", sigs, boot,
                                    extra=dict(tf="1h", study_id="S2",
                                               direction=d)))


# ── S3 청산 캐스케이드 페이드 ───────────────────────────────────────────────
def study_cascade(data, tf, results):
    H = lab.HORIZON[tf]
    long_sigs, short_sigs = [], []
    for sym, (rows, atr) in data.items():
        for i in range(25, len(rows) - H - 1):
            a = atr[i]
            if not a:
                continue
            r0, rng = rows[i], rows[i]["h"] - rows[i]["l"]
            if rng <= 0:
                continue
            move = r0["c"] - r0["o"]
            if abs(move) < S3_MOVE_ATR * a:
                continue
            vavg = sum(x["v"] for x in rows[i - 20:i]) / 20
            if vavg <= 0 or r0["v"] < vavg * S3_VOL_MULT:
                continue
            if move < 0:      # 급락 + 아래꼬리 회복 -> 롱 페이드
                if (r0["c"] - r0["l"]) / rng >= S3_RECOVER:
                    _, r = lab.outcome_atr(rows, i, "long", atr, H)
                    if r is not None:
                        long_sigs.append((r0["date"], r))
            else:             # 급등 + 위꼬리 회복 -> 숏 페이드
                if (r0["h"] - r0["c"]) / rng >= S3_RECOVER:
                    _, r = lab.outcome_atr(rows, i, "short", atr, H)
                    if r is not None:
                        short_sigs.append((r0["date"], r))

    pool = _random_pool(data, H)
    for name, sigs, d in (("S3 캐스케이드 급락페이드->롱", long_sigs, "long"),
                          ("S3 캐스케이드 급등페이드->숏", short_sigs, "short")):
        boot = lab.bootstrap_baseline(pool, lambda si, dd=d: dd, H)
        results.append(lab.evaluate(f"{name} @{tf}", sigs, boot,
                                    extra=dict(tf=tf, study_id="S3",
                                               direction=d)))


# ── S4 시간대 효과 ──────────────────────────────────────────────────────────
def study_time_of_day(data, results):
    """시(UTC)별 롱 전방수익. 24개 동시검정 -> Bonferroni 0.05/24."""
    tf, H = "1h", lab.HORIZON["1h"]
    by_hour = defaultdict(list)
    for sym, (rows, atr) in data.items():
        for i in range(20, len(rows) - H - 1):
            if not atr[i]:
                continue
            _, r = lab.outcome_atr(rows, i, "long", atr, H)
            if r is not None:
                by_hour[rows[i]["hour"]].append((rows[i]["date"], r))

    pool = _random_pool(data, H)
    boot = lab.bootstrap_baseline(pool, lambda si: "long", H)
    rows_out = []
    for h in sorted(by_hour):
        rets = [r for _, r in by_hour[h]]
        rows_out.append((h, len(rets), statistics.mean(rets)))
    rows_out.sort(key=lambda x: -x[2])
    print("\n[S4] 시(UTC)별 롱 전방수익 상위 5 / 하위 3")
    for h, n, m in rows_out[:5] + rows_out[-3:]:
        print(f"    {h:02d}시 UTC ({(h+9)%24:02d}시 KST): n={n} mean={m*100:+.3f}%")

    best_h = rows_out[0][0]
    res = lab.evaluate(f"S4 최적시간대 {best_h:02d}UTC 롱 @1h",
                       by_hour[best_h], boot,
                       extra=dict(tf="1h", study_id="S4", direction="long",
                                  best_hour_utc=best_h,
                                  bonferroni_alpha=round(0.05 / 24, 5),
                                  all_hours=[dict(h=h, n=n, mean=round(m, 5))
                                             for h, n, m in rows_out]))
    bp = res.get("boot_p")
    res["bonferroni_ok"] = bool(bp is not None and bp < 0.05 / 24)
    if not res["bonferroni_ok"] and res["verdict"] == "PASSED":
        res["verdict"] = "REJECTED"
        res["reason"] = "Bonferroni(24) 미달"
        print(f"  -> Bonferroni 보정(α={0.05/24:.5f}) 미달로 기각")
    results.append(res)


# ── S5 거래량 쇼크 추세지속 ─────────────────────────────────────────────────
def study_volume_shock(data, tf, results):
    H = lab.HORIZON[tf]
    long_sigs, short_sigs = [], []
    for sym, (rows, atr) in data.items():
        for i in range(25, len(rows) - H - 1):
            if not atr[i]:
                continue
            win = [x["v"] for x in rows[i - 20:i]]
            mu = sum(win) / 20
            sd = statistics.pstdev(win)
            if sd <= 0 or (rows[i]["v"] - mu) / sd < S5_VOL_Z:
                continue
            up = rows[i]["c"] > rows[i]["o"]
            d = "long" if up else "short"
            _, r = lab.outcome_atr(rows, i, d, atr, H)
            if r is not None:
                (long_sigs if up else short_sigs).append((rows[i]["date"], r))

    pool = _random_pool(data, H)
    for name, sigs, d in (("S5 거래량쇼크 양봉->롱", long_sigs, "long"),
                          ("S5 거래량쇼크 음봉->숏", short_sigs, "short")):
        boot = lab.bootstrap_baseline(pool, lambda si, dd=d: dd, H)
        results.append(lab.evaluate(f"{name} @{tf}", sigs, boot,
                                    extra=dict(tf=tf, study_id="S5",
                                               direction=d)))


def main():
    syms = _universe()
    print(f"유니버스 {len(syms)}종목 | 프레임: ±{lab.K_ATR}xATR 배리어, "
          f"보유한도 {lab.HORIZON}, 수수료 {lab.FEE*100:.2f}%")
    if "--no-fetch" not in sys.argv:
        fetch_all(syms)

    results = []
    for tf in TFS:
        data = _load_all(tf)
        print(f"\n{'='*64}\n{tf} 데이터: {len(data)}종목 "
              f"(봉수 중앙값 {statistics.median([len(r) for r, _ in data.values()]) if data else 0:.0f})")
        if not data:
            continue
        study_cross_sectional(data, tf, results)
        study_cascade(data, tf, results)
        study_volume_shock(data, tf, results)
        if tf == "1h":
            study_time_of_day(data, results)
            try:
                fnd = fetch_funding(syms[:S2_SYMS])
                study_funding(data, fnd, results)
            except Exception as e:
                print(f"[S2] 펀딩 검증 실패: {str(e)[:120]}")
                results.append(dict(study="S2 펀딩", verdict="ERROR",
                                    error=str(e)[:120]))

    print(f"\n{'='*64}\n요약")
    for r in results:
        print(f"  {r.get('study','?'):<34} {r.get('verdict'):<9} "
              f"n={r.get('n')} mean={r.get('mean')}")
    lab.dump(results, "_intraday_results.json")


if __name__ == "__main__":
    main()
