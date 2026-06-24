"""
btc_dominance.py — 실제 BTC 도미넌스 취득 시도(CoinGecko 무료).
  - 현재값: /api/v3/global 의 market_cap_percentage.btc (무료 가능)
  - 히스토리: /global/market_cap_chart 는 유료(401), /coins/bitcoin/dominance 차단.
  => 히스토리 불가 -> regime_switch 는 상대강도 프록시 유지. 본 모듈은 현재값 +
     불가 사유만 btc_dominance.json 에 기록(감사 추적용).
"""
import json
import urllib.request


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return json.loads(urllib.request.urlopen(req, timeout=20).read())


def main():
    res = {"current_btc_d": None, "history_available": False,
           "note": "", "source": "coingecko free"}
    try:
        g = _get("https://api.coingecko.com/api/v3/global")
        res["current_btc_d"] = round(g["data"]["market_cap_percentage"]["btc"], 2)
    except Exception as e:
        res["note"] += f"current fetch 실패: {str(e)[:80]}; "
    # 히스토리 시도
    try:
        _get("https://api.coingecko.com/api/v3/global/market_cap_chart?days=365")
        res["history_available"] = True
    except Exception as e:
        res["note"] += f"history 불가(무료 API 제한): {str(e)[:60]}"

    res["regime_basis"] = ("real_btc_d" if res["history_available"]
                           else "proxy(BTC vs 알트 상대강도) 유지 - 실제 BTC.D 히스토리 API 불가")
    json.dump(res, open("btc_dominance.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(json.dumps(res, ensure_ascii=False))


if __name__ == "__main__":
    main()
