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


# ── 러너/스케줄러용 수집 윈도우 (봉 단위 아님, '일' 단위) ─────────────────
# GitHub Actions 러너는 매번 빈 파일시스템에서 시작하므로 2021년부터 전체
# 재수집하면 실행이 100분+ 걸린다. 신호 탐지·레짐 판정에 필요한 만큼만 수집.
#   1d: 900일  (BTC 200MA + slope 220봉 + 레짐 히스토리 여유)
#   4h: 130일  (~780봉 — 하모닉 피벗 탐지 충분)
#   1h: 40일   (~960봉 — OKX 1h 과거 한계 회피: since 2021 요청 시 빈 응답)
WINDOW_DAYS = {"1d": 900, "4h": 130, "1h": 40}

# 거래소 폴백 순서 — GitHub Actions IP에서 binance/bybit는 차단(빈 응답)되고
# okx만 동작하므로 okx 우선. (로컬에서는 어느 쪽이든 동작)
EXCHANGE_ORDER = ("okx", "bybit", "binance")

_ex_cache = {}


def _get_exchange(exchange_id):
    """ccxt 인스턴스 캐시 — 심볼마다 재생성하지 않는다(임포트/마켓로드 비용 절감)."""
    if exchange_id not in _ex_cache:
        import ccxt
        _ex_cache[exchange_id] = getattr(ccxt, exchange_id)({"enableRateLimit": True})
    return _ex_cache[exchange_id]


def _csv_last_ts(path):
    """기존 CSV의 마지막 timestamp(ms). 없거나 못 읽으면 None."""
    try:
        with open(path, newline="") as f:
            last = None
            for r in csv.DictReader(f):
                last = r
            return int(float(last["timestamp"])) if last else None
    except Exception:
        return None


def update_csv(symbol, timeframe, out_path, window_days=None, quiet=True):
    """
    증분 수집: 기존 CSV가 있으면 마지막 봉 이후만 받아 append,
    없으면 WINDOW_DAYS 기준 최근 구간만 수집해 새로 쓴다.
    okx→bybit→binance 순서 폴백. 성공 시 (신규봉수, 총봉수), 실패 시 (0, 기존봉수 또는 0).
    in-process 호출용 — subprocess/ccxt 재임포트 비용 없음.
    """
    days = window_days or WINDOW_DAYS.get(timeframe, 900)
    now_ms = int(time.time() * 1000)
    default_since = now_ms - days * 86400 * 1000

    last_ts = _csv_last_ts(out_path)
    # 기존 rows 로드 (증분 병합용)
    old_rows = []
    if last_ts is not None:
        with open(out_path, newline="") as f:
            old_rows = [[int(float(r["timestamp"])), float(r["open"]), float(r["high"]),
                         float(r["low"]), float(r["close"]), float(r["volume"])]
                        for r in csv.DictReader(f)]

    for ex_id in EXCHANGE_ORDER:
        try:
            ex = _get_exchange(ex_id)
            tf_ms = ex.parse_timeframe(timeframe) * 1000
            since = (last_ts + tf_ms) if last_ts is not None else default_since
            if since >= now_ms and last_ts is not None:
                return 0, len(old_rows)          # 이미 최신
            new_rows, ex_used = fetch_ohlcv_all(ex_id, symbol, timeframe, since,
                                                limit=300, max_retries=1, exchange=ex,
                                                quiet=quiet)
            if not new_rows and last_ts is None:
                continue                          # 신규 수집인데 0봉 → 다음 거래소
            merged = old_rows + [r for r in new_rows if not old_rows or r[0] > old_rows[-1][0]]
            if not merged:
                continue
            save_csv(merged, ex_used, out_path, quiet=quiet)
            return len(merged) - len(old_rows), len(merged)
        except Exception as e:
            if not quiet:
                print(f"  [update_csv] {ex_id} {symbol} {timeframe} 실패: {str(e)[:60]}")
            continue
    return 0, len(old_rows)


def fetch_ohlcv_all(exchange_id, symbol, timeframe, since_ms,
                    until_ms=None, limit=1000, max_retries=3, exchange=None,
                    quiet=False):
    """
    since_ms 부터 (until_ms 또는 현재까지) 모든 캔들을 페이지네이션으로 수집.
    거래소 한 번 호출당 캔들 수 한도(예: 바이낸스 1000개)를 since 이동으로 넘는다.
    exchange 인스턴스를 넘기면 재사용(임포트/생성 비용 절감).
    """
    import ccxt
    if exchange is not None:
        pass
    else:
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
                if not quiet:
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
        if not quiet:
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


def save_csv(rows, exchange, out_path, quiet=False):
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "datetime", "open", "high", "low", "close", "volume"])
        for ts, o, h, l, c, v in rows:
            w.writerow([ts, exchange.iso8601(ts), o, h, l, c, v])
    if not quiet:
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
