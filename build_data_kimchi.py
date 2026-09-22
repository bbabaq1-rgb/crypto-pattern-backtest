"""
build_data_kimchi.py — 업비트 KRW 일별(UTC 정렬) 종가·거래대금 수집.

## 왜 240m 인가 — **봉 경계 정렬이 이 데이터의 전부다**
업비트 일봉은 KST 기준(00:00 KST = 15:00 UTC)이라 data_long 의 UTC 일봉 종가와 **9시간 어긋난다**.
알트 하루 변동을 5% 라 하면 9시간 표류는 약 3% 이고, 재려는 상대 김프 스프레드(약 1~3%)보다 크다.
= 일봉을 그냥 쓰면 신호보다 큰 잡음을 얹는 것.

업비트 240m 캔들은 UTC epoch 정렬(00/04/08/12/16/20)이라 **`D 20:00` 봉의 종가 = D+1 00:00 UTC 가격**
이고, data_long 의 date=D 행(00:00 UTC 개장 → D+1 00:00 UTC 종가)과 **정확히 같은 시각**이다.
그래서 240m 을 받아 20:00 봉만 남긴다.

수집 뒤 파일은 하루 한 행뿐이라 작다(코인당 약 3천 행). 러너는 네트워크 없이 이 파일만 읽는다.

출력: data_kimchi/<sym>_krw.csv.gz (date,close,value_krw) + usdkrw.csv + manifest.json
실행: python build_data_kimchi.py [--since 2017-01-01] [--only BTC,ETH]
"""
import gzip
import json
import os
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

UA = {"User-Agent": "curl/8", "Accept": "application/json"}
OUT = "data_kimchi"
SINCE = "2017-01-01"
UNIT = 240              # 4h — UTC 정렬 봉
KEEP_HOUR = 20          # 종가가 D+1 00:00 UTC 인 봉
COUNT = 200             # API 상한
WORKERS = 4             # 종목 병렬 — 합산 요청률을 업비트 10 req/s 아래로 유지
SLEEP = 0.14            # 업비트 시세 API 10 req/s → 여유


def _get(url, tries=5):
    for a in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=25) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(1.0 + a)
                continue
            if a == tries - 1:
                raise
            time.sleep(0.5 * (a + 1))
        except Exception:
            if a == tries - 1:
                raise
            time.sleep(0.5 * (a + 1))
    return []


def krw_markets():
    d = _get("https://api.upbit.com/v1/market/all?isDetails=false")
    return {m["market"].split("-")[1].upper() for m in d if m["market"].startswith("KRW-")}


def fetch_symbol(sym, since=SINCE):
    """[(date, close, value_krw)] 오름차순 — 20:00 UTC 봉만."""
    rows, to = {}, None
    while True:
        url = f"https://api.upbit.com/v1/candles/minutes/{UNIT}?market=KRW-{sym}&count={COUNT}"
        if to:
            url += f"&to={to}"
        d = _get(url)
        if not d:
            break
        for c in d:
            t = c["candle_date_time_utc"]           # 'YYYY-MM-DDTHH:MM:SS'
            if t[11:13] == f"{KEEP_HOUR:02d}":
                rows[t[:10]] = (float(c["trade_price"]), float(c.get("candle_acc_trade_price") or 0.0))
        oldest = d[-1]["candle_date_time_utc"]
        if oldest[:10] < since:
            break
        to = oldest + "Z"
        time.sleep(SLEEP * WORKERS)
        if len(d) < COUNT:
            break
    return [(k, *rows[k]) for k in sorted(rows) if k >= since]


def write(sym, rows):
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, f"{sym.lower()}_krw.csv.gz")
    with gzip.open(p, "wt", newline="") as f:
        f.write("date,close,value_krw\n")
        for d, c, v in rows:
            f.write(f"{d},{c},{v}\n")
    return p


def fetch_fx(since=SINCE):
    """ECB 기준환율 USD→KRW (평일만). **진단 전용** — 주 판정은 환율을 쓰지 않는다."""
    end = datetime.now(timezone.utc).date().isoformat()
    d = _get(f"https://api.frankfurter.app/{since}..{end}?from=USD&to=KRW")
    return sorted((k, v["KRW"]) for k, v in d.get("rates", {}).items() if "KRW" in v)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    since = argv[argv.index("--since") + 1] if "--since" in argv else SINCE
    only = argv[argv.index("--only") + 1].upper().split(",") if "--only" in argv else None

    long_syms = sorted({f.split("_")[0].upper() for f in os.listdir("data_long") if f.endswith("_1d.csv.gz")})
    krw = krw_markets()
    syms = [s for s in long_syms if s in krw]
    if only:
        syms = [s for s in syms if s in only]
    print(f"data_long {len(long_syms)} ∩ 업비트 KRW {len(krw)} → 수집 {len(syms)}", flush=True)

    man = {"since": since, "unit_min": UNIT, "keep_hour_utc": KEEP_HOUR, "workers": WORKERS,
           "built_at": datetime.now(timezone.utc).isoformat(), "symbols": {}}
    def one(sym):
        try:
            return sym, fetch_symbol(sym, since), None
        except Exception as e:
            return sym, [], f"{type(e).__name__}: {e}"

    done = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for sym, rows, err in ex.map(one, syms):
            done += 1
            if err:
                print(f"  [{done}/{len(syms)}] {sym} 실패 {err}", flush=True)
                continue
            if not rows:
                print(f"  [{done}/{len(syms)}] {sym} 0행", flush=True)
                continue
            write(sym, rows)
            man["symbols"][sym] = {"first": rows[0][0], "last": rows[-1][0], "n": len(rows)}
            print(f"  [{done}/{len(syms)}] {sym} {len(rows)}행 {rows[0][0]}~{rows[-1][0]}", flush=True)

    try:
        fx = fetch_fx(since)
        os.makedirs(OUT, exist_ok=True)
        with open(os.path.join(OUT, "usdkrw.csv"), "w") as f:
            f.write("date,usdkrw\n")
            for d, r in fx:
                f.write(f"{d},{r}\n")
        man["fx"] = {"source": "frankfurter/ECB", "n": len(fx),
                     "first": fx[0][0] if fx else None, "last": fx[-1][0] if fx else None,
                     "note": "평일만. 진단 전용 — 주 판정(횡단면)은 환율을 쓰지 않는다."}
        print(f"  FX {len(fx)}행", flush=True)
    except Exception as e:
        print(f"  FX 실패 {type(e).__name__}: {e}", flush=True)

    with open(os.path.join(OUT, "manifest.json"), "w") as f:
        json.dump(man, f, ensure_ascii=False, indent=1)
    print(f"완료 — {len(man['symbols'])} 종목", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
