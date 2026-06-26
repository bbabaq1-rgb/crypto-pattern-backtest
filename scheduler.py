"""
scheduler.py — 매일 UTC 00:00 자동 파이프라인 (페이퍼테스트 준비, 실주문 없음).

순서:
  (1) 7종목 일봉 최신 fetch (fetch_data.py)
  (2) regime_switch 로 현재 레짐 판정
  (3) direction_switch.json 갱신(레짐->방향 라우팅)
  (4) engulfing/fvg detector로 '오늘(최신봉)' 신호 탐지 (레짐이 켠 방향만)
  (5) 신호를 signals_today.json 에 저장
      (패턴/방향/종목/강도/레짐/권장진입가/손절가/익절조건)

사용:
  python scheduler.py once     # 1회 실행(fetch 생략, 데이터 최신 가정)
  python scheduler.py oncefull # 1회 실행(fetch 포함)
  python scheduler.py          # 데몬: 매 UTC 00:00 자동 실행(while+sleep)
실주문은 넣지 않는다 — 신호만 기록.
"""
import sys
import os
import json
import time
import subprocess
from datetime import datetime, timezone, timedelta

import detlib
import regime_switch as rs
import direction_switch as ds

def _universe():
    if os.path.exists("universe.json"):
        u = json.load(open("universe.json", encoding="utf-8")).get("trading_universe")
        if u:
            return u
    return list(detlib.SYMBOLS)


SYMBOLS = _universe()
FOCUS = ["engulfing", "fvg"]
STOP = 0.08
MAX_HOLD = 30
DETMOD = {("engulfing", "long"): "detector_engulfing",
          ("engulfing", "short"): "detector_engulfing_short",
          ("fvg", "long"): "detector_fvg",
          ("fvg", "short"): "detector_fvg_short"}


EXCHANGES = ["binance", "bybit", "okx"]   # 451 지역차단 시 순서대로 폴백


def _fetch_one(sym, exchange):
    """단일 종목 fetch, 성공 시 True / 실패 시 False."""
    import os
    out = f"data/{sym.lower()}_1d.csv"
    r = subprocess.run(
        [sys.executable, "fetch_data.py", "--exchange", exchange,
         "--symbol", f"{sym}/USDT", "--timeframe", "1d",
         "--since", "2021-01-01", "--out", out],
        capture_output=True, text=True)
    geo_blocked = "451" in r.stdout or "451" in r.stderr or \
                  "restricted location" in r.stderr or "restricted location" in r.stdout
    return r.returncode == 0, geo_blocked


def fetch_all():
    """유니버스 전체 1d CSV를 순차 fetch. 거래소 451 차단 시 다음 거래소로 폴백."""
    import os
    os.makedirs("data", exist_ok=True)
    ok = err = 0
    # 첫 종목으로 어느 거래소가 살아있는지 탐색
    active_ex = EXCHANGES[0]
    for ex in EXCHANGES:
        success, geo = _fetch_one(SYMBOLS[0], ex)
        if success:
            active_ex = ex
            ok += 1
            print(f"  [fetch] 거래소={ex} 사용 (첫 종목 {SYMBOLS[0]} OK)")
            break
        if geo:
            print(f"  [fetch] {ex} 지역차단(451) -> 다음 거래소 시도")
        else:
            print(f"  [fetch] {ex} 실패(비차단) -> 다음 거래소 시도")
    else:
        print(f"  [fetch] 모든 거래소 실패 — 기존 CSV로 진행")
        return

    for s in SYMBOLS[1:]:   # 나머지 종목은 확정된 거래소로
        success, _ = _fetch_one(s, active_ex)
        if success:
            ok += 1
        else:
            print(f"  [fetch] {s} 실패({active_ex})")
            err += 1
    print(f"  [fetch] 완료 {ok}종목 / 실패 {err}종목 (거래소={active_ex})")


def run_once(do_fetch=True):
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    if do_fetch:
        print(f"[1] fetch {len(SYMBOLS)}종목 일봉 (순차, 완료 후 진행)...")
        fetch_all()
        print("[1] fetch 완료 -> 레짐 판정 시작")

    print("[2] 레짐 판정..."); regmap = rs.build_regime_map()
    latest = max(regmap); regime = regmap[latest]
    print(f"    현재 레짐: {regime} ({latest})")

    print("[3] direction_switch 갱신..."); ds.main()
    routing = json.load(open("direction_switch.json", encoding="utf-8"))["routing"]
    route = routing.get(regime, {})

    print("[4] 오늘 신호 탐지...")
    import importlib
    signals = []
    for pat in FOCUS:
        d = route.get(pat, "FLAT")
        if d not in ("long", "short"):
            continue
        mod = importlib.import_module(DETMOD[(pat, d)])
        for sym in SYMBOLS:
            try:
                rows = mod.load_ohlcv(sym, "1d")
            except FileNotFoundError:
                continue
            sigset = set(mod.detect(rows))
            last = len(rows) - 1
            if last in sigset:                 # 최신봉이 신호
                v = [r["v"] for r in rows]
                vr = round(v[last] / (sum(v[last - 20:last]) / 20), 2) if last >= 20 else None
                entry = rows[last]["c"]
                stop_px = round(entry * (1 - STOP), 4) if d == "long" else round(entry * (1 + STOP), 4)
                signals.append(dict(
                    pattern=pat, direction=d, symbol=sym, date=rows[last]["date"],
                    strength_vol_ratio=vr, regime=regime,
                    entry=round(entry, 4), stop=stop_px,
                    take_profit="반대패턴 신호 or 레짐전환 or 최대30봉 시가청산"))
    # 채택된 추가 패턴(캔들 등) — 방향 고정, 레짐 라우팅 없이 최신봉 신호 탐지
    adopted = []
    if os.path.exists("universe.json"):
        adopted = json.load(open("universe.json", encoding="utf-8")).get("adopted_patterns", [])
    for ap in adopted:
        mod = importlib.import_module(ap["module"])
        for sym in SYMBOLS:
            try:
                rows = mod.load_ohlcv(sym, "1d")
            except FileNotFoundError:
                continue
            last = len(rows) - 1
            if last in set(mod.detect(rows)):
                entry = rows[last]["c"]
                dd = ap["direction"]
                stop_px = round(entry * (1 - 0.08), 4) if dd == "long" else round(entry * (1 + 0.08), 4)
                signals.append(dict(pattern=ap["pattern"], direction=dd, symbol=sym,
                                    date=rows[last]["date"], strength_vol_ratio=None,
                                    regime=regime, entry=round(entry, 4), stop=stop_px,
                                    take_profit="반대패턴 신호 or 레짐전환 or 최대30봉 시가청산"))

    out = dict(generated_at=stamp, regime=regime, regime_date=latest,
               routing=route, n_signals=len(signals), signals=signals,
               note="페이퍼테스트용 신호 기록 - 실주문 없음")
    json.dump(out, open("signals_today.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"[5] signals_today.json 저장: 신호 {len(signals)}건")
    for s in signals:
        print(f"    {s['symbol']} {s['pattern']} {s['direction']} @ {s['entry']} 손절 {s['stop']}")

    print("[6] 페이퍼 체결(진입+청산 모니터링)...")
    import exchange, paper_executor
    conn = exchange.connect()
    print(f"    거래소: {conn['mode']} | {conn['note']}")
    pr = paper_executor.run(stamp)
    out["paper"] = pr

    print("[7] daily_summary 기록...")
    try:
        import supabase_client as sc
        if sc.available():
            tr = json.load(open("paper_trades.json", encoding="utf-8")) if os.path.exists("paper_trades.json") else []
            cra = round(sum(t["pnl_usd"] for t in tr if t["method"] == "A") / 2000 * 100, 2)
            crd = round(sum(t["pnl_usd"] for t in tr if t["method"] == "D") / 2000 * 100, 2)
            day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            sc.get_client("service").table("daily_summary").upsert(
                {"date": day, "total_open": pr["open"], "signals_count": len(signals),
                 "cumulative_return_a": cra, "cumulative_return_d": crd},
                on_conflict="date").execute()
            print(f"    daily_summary UPSERT 완료 (open={pr['open']}, sig={len(signals)}, A={cra}%, D={crd}%)")
        else:
            print("    DB 미설정 - daily_summary 스킵(로컬 JSON 유지)")
    except Exception as e:
        print("    daily_summary 실패(무시):", str(e)[:80])
    return out


def daemon():
    print("scheduler 데몬 시작 - 매 UTC 00:00 실행 (Ctrl+C 중단)")
    while True:
        now = datetime.now(timezone.utc)
        nxt = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        wait = (nxt - now).total_seconds()
        print(f"  다음 실행까지 {wait/3600:.1f}시간 대기...")
        time.sleep(wait)
        try:
            run_once(do_fetch=True)
        except Exception as e:
            print("  run_once 오류:", e)


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "once":
        run_once(do_fetch=False)
    elif arg == "oncefull":
        run_once(do_fetch=True)
    else:
        daemon()
