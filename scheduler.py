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


def fetch_all():
    for s in SYMBOLS:
        subprocess.run([sys.executable, "fetch_data.py", "--exchange", "binance",
                        "--symbol", f"{s}/USDT", "--timeframe", "1d",
                        "--since", "2021-01-01", "--out", f"data/{s.lower()}_1d.csv"],
                       capture_output=True)


def run_once(do_fetch=True):
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    if do_fetch:
        print("[1] fetch 7종목 일봉..."); fetch_all()

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
    out = dict(generated_at=stamp, regime=regime, regime_date=latest,
               routing=route, n_signals=len(signals), signals=signals,
               note="페이퍼테스트용 신호 기록 — 실주문 없음")
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
    return out


def daemon():
    print("scheduler 데몬 시작 — 매 UTC 00:00 실행 (Ctrl+C 중단)")
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
