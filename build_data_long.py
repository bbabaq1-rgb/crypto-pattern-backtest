"""
build_data_long.py — 장기 일봉 이력(2017~) 수집 → data_long/{sym}_1d.csv.gz (2026-09-06, 사용자 지시).

## 왜

검증에 쓰는 1d 데이터는 OKX 1800일(2021-10~)이고, top-80 알트 대부분은 900일(2024-03~)뿐이다.
레짐 조건부 규칙(bull_btc 에서만 진입 등)을 '독립된 상승 국면 여러 개에서 맞는가'로 재려면
사이클이 둘 이상 필요하다 — 2017/2021/2024 상승, 2018/2022/2026 하락. 이 스크립트는
GitHub Actions 러너(미국 IP — binance/bybit 는 빈 응답, okx/coinbase/kraken/kucoin 등은 가능)에서
거래소별로 가장 오래된 이력을 받아 종목마다 **가장 일찍 시작하는 소스 하나**를 고른다.

## 한계 (기록)

· 생존 편향 — 2017년부터 있는 종목은 살아남은 종목이다. 2018 상위 80 은 대부분 사라졌다.
· 소스 혼합 — 오래된 구간은 현물(다른 거래소), 최근 구간은 OKX 무기한. 1d 패턴에서 가격 차는
  작지만 거래량 척도는 다르다(검증은 turnover 순위에 최근 30일만 쓰므로 영향 없음).
· 러너 파일시스템은 매번 비므로 결과를 **브랜치(data-long)에 커밋**한다. 러너는 이 폴더를 읽지
  않는다(스케줄러 무관) — 검증 스크립트가 `--long` 일 때만 읽는다.

출력: data_long/{sym}_1d.csv.gz (fetch_data.save_csv 와 같은 컬럼) + data_long/manifest.json
실행: python build_data_long.py [--symbols BTC,ETH] [--since 2017-01-01]
      [--okx-all] [--shard i/n] [--skip-existing] [--out DIR]
  --okx-all       OKX USDT 무기한 전 종목(스테이블 제외) ∪ 유니버스 — 에피소드 프로필 연구용(2026-09-07)
  --shard i/n     종목을 n 개로 나눠 i 번째만(0 기준). Actions 매트릭스 병렬 수집용
  --skip-existing data_long/ 에 이미 있는 종목은 건너뜀
  --out DIR       산출 폴더(기본 data_long). 샤드는 별도 폴더에 쓰고 collect 단계에서 합친다
"""
import csv
import gzip
import io
import json
import os
import sys
import time
from datetime import datetime, timezone

import ccxt

import fetch_data
import regime_switch as rs

OUT_DIR = "data_long"
SINCE = "2017-01-01"
# 시도 순서 — okx 는 러너에서 검증된 소스라 먼저. 나머지는 미국 IP 허용 거래소.
EXCHANGES = ["okx", "coinbaseexchange", "coinbase", "kucoin", "gate", "htx", "mexc", "bitget", "cryptocom", "kraken"]
# kraken 은 공개 OHLC 가 최근 720봉만 돌려줘 장기 이력에 못 쓴다 — 최후 순위. (1차 실행 2026-09-06 에서
# kraken 만 통과해 전 종목 2024-09 시작이 됐다. 원인: probe 가 since=2017 빈 응답을 '불가'로 봤고
# gate 의 ccxt id 를 'gateio' 로 잘못 썼다.)
QUOTES = {"coinbaseexchange": ["USDT", "USD"], "coinbase": ["USDT", "USD"], "kraken": ["USDT", "USD"]}
DEFAULT_QUOTES = ["USDT"]
EARLY_ENOUGH = "2018-06-30"     # 이 날짜 이전에서 시작하는 소스를 찾으면 다른 거래소는 안 본다
PROBE_SYMBOL = "BTC"
# 거래소 대부분은 상장 전 since 에 빈 응답을 준다 → 시작점을 앞에서부터 더듬어 찾는다.
START_CANDIDATES = ["2017-01-01", "2017-07-01", "2018-01-01", "2018-07-01", "2019-01-01", "2019-07-01",
                    "2020-01-01", "2020-07-01", "2021-01-01", "2021-07-01", "2022-01-01", "2023-01-01",
                    "2024-01-01", "2025-01-01"]


def _iso(ts):
    return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def _ms(day):
    return int(datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp() * 1000)


STABLE = {"USDT", "USDC", "DAI", "BUSD", "TUSD", "FDUSD", "PYUSD", "USDE", "USD1", "USDD", "USDP", "GUSD", "FRAX"}


def okx_all_symbols():
    """OKX USDT 무기한(활성) 기초자산 전부 — 스테이블 제외. 유니버스·레짐 종목과 합집합."""
    ex = ccxt.okx({"enableRateLimit": True})
    mk = ex.load_markets()
    bases = {m["base"] for m in mk.values() if m.get("swap") and m.get("quote") == "USDT"
             and m.get("active") and m.get("settle") == "USDT"}
    bases = {b for b in bases if b and b.upper() not in STABLE}
    return sorted(bases | set(universe_symbols()))


def shard(syms, spec):
    i, n = (int(x) for x in spec.split("/"))
    return [s for k, s in enumerate(sorted(syms)) if k % n == i]


def universe_symbols():
    u = json.load(open("universe.json", encoding="utf-8"))
    syms = list(u["trading_universe"])
    for s in [rs.MARKET, "ETH"] + list(rs.ALTS):
        if s not in syms:
            syms.append(s)
    return syms


def make_exchange(exid):
    ex = getattr(ccxt, exid)({"enableRateLimit": True})
    ex.load_markets()
    return ex


def market_symbol(ex, exid, base):
    for q in QUOTES.get(exid, DEFAULT_QUOTES):
        s = f"{base}/{q}"
        if s in ex.markets and ex.markets[s].get("spot", True):
            return s
    return None


def _first_bar(ex, sym, ms):
    try:
        rows = ex.fetch_ohlcv(sym, "1d", since=ms, limit=10)
    except Exception:
        rows = None
    time.sleep(ex.rateLimit / 1000)
    return rows[0][0] if rows else None


def earliest_start(ex, sym, since_ms):
    """since 이후 첫 봉 ts. 후보 시작일을 앞에서부터 시도해 처음 비어 있지 않은 응답을 찾고,
    직전 빈 후보와 그 사이를 **일 단위 이분 탐색**으로 좁힌다(격자 반년~1년에 상장일이 끼면
    최대 1년을 잃던 것을 막는다 — 3차 실행에서 OP/APT/ARB 가 격자 날짜에 붙어 있었다)."""
    prev_empty = None
    for cand in START_CANDIDATES:
        ms = _ms(cand)
        if ms < since_ms:
            continue
        ts = _first_bar(ex, sym, ms)
        if ts is None:
            prev_empty = ms
            continue
        # 거래소가 since 보다 이른 봉을 돌려줬다면(상장 이후 since) 그 자체가 첫 봉
        if prev_empty is None or ts < ms:
            return ts
        lo, hi = prev_empty, ms                      # lo: 빈 응답, hi: 데이터 있음
        day = 86_400_000
        while hi - lo > day:
            mid = lo + ((hi - lo) // (2 * day)) * day
            if mid <= lo:
                break
            t2 = _first_bar(ex, sym, mid)
            if t2 is None:
                lo = mid
            else:
                hi = mid; ts = t2
        return ts
    return None


def probe(exid, since_ms):
    """거래소 도달 가능 여부(최근 봉 조회) + BTC 최초 봉. 실패 시 None."""
    try:
        ex = make_exchange(exid)
        sym = market_symbol(ex, exid, PROBE_SYMBOL)
        if not sym:
            print(f"  [probe] {exid} BTC 마켓 없음", flush=True)
            return None
        recent = ex.fetch_ohlcv(sym, "1d", limit=5)
        if not recent:
            print(f"  [probe] {exid} 최근 봉 없음", flush=True)
            return None
        first_ts = earliest_start(ex, sym, since_ms)
        return dict(exchange=ex, symbol=sym, first=_iso(first_ts) if first_ts else None)
    except Exception as e:
        print(f"  [probe] {exid} 불가: {str(e)[:80]}", flush=True)
        return None


def fetch_full(ex, exid, sym, start_ms):
    rows, _ = fetch_data.fetch_ohlcv_all(exid, sym, "1d", start_ms, limit=1000, max_retries=2,
                                         exchange=ex, quiet=True)
    return rows


def save_gz(rows, path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["timestamp", "datetime", "open", "high", "low", "close", "volume"])
    for ts, o, h, l, c, v in rows:
        w.writerow([int(ts), datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat(), o, h, l, c, v])
    with gzip.open(path, "wt", encoding="utf-8", newline="") as f:
        f.write(buf.getvalue())


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    since = argv[argv.index("--since") + 1] if "--since" in argv else SINCE
    since_ms = int(datetime.fromisoformat(since).replace(tzinfo=timezone.utc).timestamp() * 1000)
    out_dir = argv[argv.index("--out") + 1] if "--out" in argv else OUT_DIR
    if "--symbols" in argv:
        syms = argv[argv.index("--symbols") + 1].split(",")
    elif "--okx-all" in argv:
        syms = okx_all_symbols()
    else:
        syms = universe_symbols()
    if "--shard" in argv:
        syms = shard(syms, argv[argv.index("--shard") + 1])
    if "--skip-existing" in argv:
        syms = [s for s in syms if not os.path.exists(f"{OUT_DIR}/{s.lower()}_1d.csv.gz")]
    print(f"장기 1d 수집 | 종목 {len(syms)} | since {since} | out {out_dir} | 거래소 후보 {EXCHANGES}", flush=True)

    reachable = []
    for exid in EXCHANGES:
        p = probe(exid, since_ms)
        if p:
            reachable.append((exid, p["exchange"], p["first"] or "9999"))
            print(f"  [probe] {exid:<16} OK  BTC 최초 봉 {p['first']} ({p['symbol']})", flush=True)
    if not reachable:
        sys.exit("[오류] 도달 가능한 거래소 없음")
    reachable.sort(key=lambda t: t[2])          # BTC 이력이 긴 거래소부터
    print(f"  [probe] 시도 순서: {[e for e, _, _ in reachable]}", flush=True)

    manifest = dict(since=since, built_at=datetime.now(timezone.utc).isoformat(),
                    exchanges=[e for e, _, _ in reachable], symbols={})
    t_all = time.time()
    for i, s in enumerate(syms, 1):
        best = None
        for exid, ex, _ in reachable:
            sym = market_symbol(ex, exid, s)
            if not sym:
                continue
            try:
                start_ts = earliest_start(ex, sym, since_ms)
                if start_ts is None:
                    continue
                if best is not None and _iso(start_ts) >= best["first"]:
                    continue                    # 이미 더 이른 소스가 있으면 받지 않는다
                rows = fetch_full(ex, exid, sym, start_ts)
            except Exception as e:
                print(f"    {s} @{exid} 실패: {str(e)[:60]}", flush=True)
                continue
            if not rows:
                continue
            first = _iso(rows[0][0])
            if best is None or first < best["first"] or (first == best["first"] and len(rows) > best["n"]):
                best = dict(exchange=exid, symbol=sym, first=first, last=_iso(rows[-1][0]), n=len(rows), rows=rows)
            if first <= EARLY_ENOUGH:
                break
        if best is None:
            print(f"  [{i:>2}/{len(syms)}] {s:<9} 소스 없음", flush=True)
            manifest["symbols"][s] = None
            continue
        save_gz(best["rows"], f"{out_dir}/{s.lower()}_1d.csv.gz")
        manifest["symbols"][s] = {k: best[k] for k in ("exchange", "symbol", "first", "last", "n")}
        print(f"  [{i:>2}/{len(syms)}] {s:<9} {best['exchange']:<9} {best['first']} ~ {best['last']}  {best['n']}봉", flush=True)
    os.makedirs(out_dir, exist_ok=True)
    json.dump(manifest, open(f"{out_dir}/manifest.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    ok = sum(1 for v in manifest["symbols"].values() if v)
    pre2019 = sum(1 for v in manifest["symbols"].values() if v and v["first"] < "2019-01-01")
    pre2021 = sum(1 for v in manifest["symbols"].values() if v and v["first"] < "2021-01-01")
    print(f"\n[완료] {ok}/{len(syms)} 종목 | 2019 이전 시작 {pre2019} | 2021 이전 시작 {pre2021} | {time.time()-t_all:.0f}s")
    print("RESULT_JSON: " + json.dumps(dict(ok=ok, pre2019=pre2019, pre2021=pre2021)))


if __name__ == "__main__":
    main()
