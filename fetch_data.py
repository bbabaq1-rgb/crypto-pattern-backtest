"""
fetch_data.py — ccxt OHLCV 수집기 (대표님 PC / Claude Code 에서 실행)

이 스크립트는 거래소에 직접 접속하므로 인터넷이 열린 환경(대표님 PC,
Claude Code, GitHub Actions 등)에서 실행해야 한다. Claude 채팅 샌드박스에서는
외부 접속이 막혀 동작하지 않는다.

사용 예:
  pip install ccxt
  python fetch_data.py --exchange binance --symbol BTC/USDT --timeframe 1d \
                       --since 2021-01-01 --out data/btc_1d.csv
  python fetch_data.py --exchange upbit   --symbol BTC/KRW  --timeframe 4h \
                       --since 2023-01-01 --out data/btc_krw_4h.csv

출력 CSV 컬럼: timestamp(ms), datetime(UTC), open, high, low, close, volume
이 형식은 backtest.py 가 그대로 읽는다.
"""

import argparse
import csv
import os
import sys
import time


def fetch_ohlcv_all(exchange_id, symbol, timeframe, since_ms,
                    until_ms=None, limit=1000, max_retries=3):
    """
    since_ms 부터 (until_ms 또는 현재까지) 모든 캔들을 페이지네이션으로 수집.
    거래소 한 번 호출당 캔들 수 한도(예: 바이낸스 1000개)를 since 이동으로 넘는다.
    """
    import ccxt
    try:
        exchange = getattr(ccxt, exchange_id)({"enableRateLimit": True})
    except AttributeError:
        sys.exit(f"[오류] ccxt에 '{exchange_id}' 거래소가 없습니다.")

    if not exchange.has.get("fetchOHLCV"):
        sys.exit(f"[오류] {exchange_id}는 OHLCV 조회를 지원하지 않습니다.")

    all_rows = []
    since = since_ms
    tf_ms = exchange.parse_timeframe(timeframe) * 1000

    while True:
        batch = None
        for attempt in range(max_retries):
            try:
                batch = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=limit)
                break
            except Exception as e:                      # 네트워크/레이트리밋 재시도
                wait = (attempt + 1) * 2
                print(f"  재시도 {attempt+1}/{max_retries} ({e}) — {wait}s 대기")
                time.sleep(wait)
        if not batch:
            break

        # 중복 방지: 직전 마지막 이후만 채택
        batch = [r for r in batch if r[0] >= since]
        if not batch:
            break
        all_rows += batch
        last_ts = batch[-1][0]
        print(f"  {exchange.iso8601(batch[0][0])} ~ {exchange.iso8601(last_ts)}  (누적 {len(all_rows)})")

        since = last_ts + tf_ms
        if until_ms and since > until_ms:
            break
        # len(batch) < limit 으로 종료하지 않음:
        # OKX 등 per-call 캡이 300인 거래소에서 limit=1000 을 넘기면
        # 항상 300 < 1000 → 첫 페이지에서 멈추는 버그 방지.
        # 빈 배치(위의 두 개 if not batch) 가 실제 종료 신호.
        time.sleep(exchange.rateLimit / 1000)

    # 타임스탬프 기준 정렬·중복 제거
    seen, dedup = set(), []
    for r in sorted(all_rows, key=lambda x: x[0]):
        if r[0] in seen:
            continue
        seen.add(r[0]); dedup.append(r)
    return dedup, exchange


def save_csv(rows, exchange, out_path):
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "datetime", "open", "high", "low", "close", "volume"])
        for ts, o, h, l, c, v in rows:
            w.writerow([ts, exchange.iso8601(ts), o, h, l, c, v])
    print(f"[완료] {len(rows)}개 캔들 → {out_path}")


def main():
    p = argparse.ArgumentParser(description="ccxt OHLCV 수집기")
    p.add_argument("--exchange", default="binance", help="거래소 id (binance, upbit, ...)")
    p.add_argument("--symbol", default="BTC/USDT", help="종목 (예: BTC/USDT, BTC/KRW)")
    p.add_argument("--timeframe", default="1d", help="시간단위 (1m,5m,15m,1h,4h,1d,1w)")
    p.add_argument("--since", default="2021-01-01", help="시작일 YYYY-MM-DD")
    p.add_argument("--until", default=None, help="종료일 YYYY-MM-DD (생략 시 현재까지)")
    p.add_argument("--limit", type=int, default=1000, help="호출당 캔들 수")
    p.add_argument("--out", default="data/ohlcv.csv", help="출력 CSV 경로")
    args = p.parse_args()

    import ccxt
    since_ms = ccxt.Exchange.parse8601(f"{args.since}T00:00:00Z")
    until_ms = ccxt.Exchange.parse8601(f"{args.until}T00:00:00Z") if args.until else None

    print(f"[수집] {args.exchange} {args.symbol} {args.timeframe} since {args.since}")
    rows, exchange = fetch_ohlcv_all(args.exchange, args.symbol, args.timeframe,
                                     since_ms, until_ms, args.limit)
    if not rows:
        sys.exit("[오류] 수집된 데이터가 없습니다. 종목/기간/거래소를 확인하세요.")
    save_csv(rows, exchange, args.out)


if __name__ == "__main__":
    main()
