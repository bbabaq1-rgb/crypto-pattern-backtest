"""
alt_fetch.py — 바이낸스 USDT 상위 알트 50종 조회 + 일봉 fetch.
ccxt엔 시총이 없어 24h 거래대금(quoteVolume) 상위로 대체(유동성 프록시).
스테이블/기존 12종 제외. <500봉이면 '데이터부족'으로 기록·스킵.
"""
import json
import ccxt

from fetch_data import fetch_ohlcv_all, save_csv

EXIST = {"BTC", "SOL", "ETH", "BNB", "XRP", "ADA", "AVAX",
         "LINK", "DOT", "LTC", "ATOM", "UNI"}
STABLE = {"USDC", "FDUSD", "TUSD", "DAI", "USDP", "BUSD", "USDD", "PYUSD",
          "AEUR", "EUR", "EURI", "XUSD", "USD1", "USDE"}
MIN_BARS = 500
TOP_N = 50


def ranked_alts():
    ex = ccxt.binance({"enableRateLimit": True})
    mk = ex.load_markets()
    tk = ex.fetch_tickers()
    rows = []
    for sym, t in tk.items():
        if not sym.endswith("/USDT"):
            continue
        m = mk.get(sym)
        if not m or not m.get("spot") or not m.get("active"):
            continue
        base = m["base"]
        if base in EXIST or base in STABLE:
            continue
        qv = t.get("quoteVolume") or 0
        rows.append((base, sym, qv))
    rows.sort(key=lambda x: -x[2])
    return rows[:TOP_N]


def main():
    top = ranked_alts()
    print(f"상위 {len(top)} 알트(거래대금순):", ", ".join(b for b, _, _ in top))
    result = {}
    since = ccxt.Exchange.parse8601("2021-01-01T00:00:00Z")
    for base, sym, qv in top:
        out = f"data/{base.lower()}_1d.csv"
        try:
            rows, exchange = fetch_ohlcv_all("binance", sym, "1d", since)
            if len(rows) < MIN_BARS:
                result[base] = dict(bars=len(rows), status="데이터부족", qv=round(qv))
                print(f"  {base}: {len(rows)}봉 -> 데이터부족(스킵)")
                continue
            save_csv(rows, exchange, out)
            result[base] = dict(bars=len(rows), status="ok", qv=round(qv))
        except Exception as e:
            result[base] = dict(bars=0, status=f"오류:{str(e)[:40]}", qv=round(qv))
            print(f"  {base}: 오류 {str(e)[:60]}")
    json.dump(result, open("alt_fetch.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    ok = [b for b, v in result.items() if v["status"] == "ok"]
    short = [b for b, v in result.items() if v["status"] == "데이터부족"]
    print(f"\n시도 {len(top)} | ok {len(ok)} | 데이터부족 {len(short)}")
    print("ok:", ok)
    print("데이터부족:", short)


if __name__ == "__main__":
    main()
