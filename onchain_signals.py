"""
onchain_signals.py — 온체인 보조 신호 3종

1. 펀딩비 (OKX 공개 API — 인증 불필요)
2. ETF 순유입 (SoSoValue 무료 API)
3. 스테이블코인 시총 변화 (CoinGecko 무료)

fetch() -> {
  "funding": {"signal": "bull"|"bear"|"neutral", ...},
  "etf":     {"signal": "bull"|"bear"|"neutral", ...},
  "stable":  {"signal": "bull"|"bear"|"neutral", ...},
  "score":   int (-3 ~ +3),
  "fetched_at": str,
}

API 실패 시 각 신호 독립적으로 neutral 처리 — 레짐 판단은 계속.
"""
import os
import json
from datetime import datetime, timezone

# ── 임계값 ────────────────────────────────────────────────────────────────────
FUNDING_BEAR_THR = +0.0005   # > +0.05%  → 과열(bear 가중)
FUNDING_BULL_THR = -0.0005   # < -0.05%  → 공포(bull 반전 가중)
STABLE_BULL_THR  = +0.03     # 7일 변화율 > +3% → 신규 자금 유입
STABLE_BEAR_THR  = -0.03     # 7일 변화율 < -3% → 자금 이탈

CACHE_FILE  = "onchain_cache.json"
CACHE_TTL_H = 4   # 4시간 캐시


# ── 캐시 유틸 ─────────────────────────────────────────────────────────────────
def _load_cache():
    if not os.path.exists(CACHE_FILE):
        return None
    try:
        c = json.load(open(CACHE_FILE, encoding="utf-8"))
        fetched = c.get("fetched_at", "")
        if fetched:
            age_h = (
                datetime.now(timezone.utc) - datetime.fromisoformat(fetched)
            ).total_seconds() / 3600
            if age_h < CACHE_TTL_H:
                return c.get("result")
    except Exception:
        pass
    return None


def _save_cache(result):
    data = {"fetched_at": datetime.now(timezone.utc).isoformat(), "result": result}
    json.dump(data, open(CACHE_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


# ── Signal 1: 펀딩비 (OKX 공개 API) ─────────────────────────────────────────
def _fetch_funding() -> dict:
    """
    OKX 무기한 선물 주요 종목 펀딩비 평균.
    인증 없이 공개 API 사용. 실패 시 neutral.
    """
    SWAP_SYMS = [
        "BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP",
        "XRP-USDT-SWAP", "ADA-USDT-SWAP", "AVAX-USDT-SWAP",
        "DOGE-USDT-SWAP", "LINK-USDT-SWAP", "DOT-USDT-SWAP",
        "ATOM-USDT-SWAP", "APT-USDT-SWAP", "ARB-USDT-SWAP",
        "OP-USDT-SWAP",   "NEAR-USDT-SWAP", "TRX-USDT-SWAP",
        "INJ-USDT-SWAP",  "SUI-USDT-SWAP",  "TON-USDT-SWAP",
    ]
    try:
        import requests
        rates = []
        for inst_id in SWAP_SYMS:
            try:
                r = requests.get(
                    "https://www.okx.com/api/v5/public/funding-rate",
                    params={"instId": inst_id},
                    headers={"Accept": "application/json"},
                    timeout=10,
                )
                if r.ok:
                    data = r.json().get("data", [])
                    if data:
                        fr = float(data[0].get("fundingRate", 0))
                        rates.append(fr)
            except Exception:
                continue

        if not rates:
            return {"signal": "neutral", "avg_rate": None, "n": 0, "error": "no data"}

        avg = sum(rates) / len(rates)
        if avg > FUNDING_BEAR_THR:
            sig = "bear"
        elif avg < FUNDING_BULL_THR:
            sig = "bull"
        else:
            sig = "neutral"

        return {"signal": sig, "avg_rate": round(avg * 100, 6), "n": len(rates),
                "note": "avg_rate in % (×100)"}

    except Exception as e:
        return {"signal": "neutral", "avg_rate": None, "n": 0, "error": str(e)[:80]}


# ── Signal 2: ETF 순유입 (SoSoValue) ─────────────────────────────────────────
def _fetch_etf_flow() -> dict:
    """
    BTC 현물 ETF 일일 순유입 최근 3일. SoSoValue 무료 API.
    응답 형식 불일치 또는 접속 실패 시 neutral.
    """
    ENDPOINTS = [
        "https://sosovalue.com/api/etf/us-bitcoin-spot-etf-fund-flow-history",
        "https://sosovalue.xyz/api/etf/us-bitcoin-spot-etf-fund-flow-history",
    ]
    try:
        import requests
        data = None
        for url in ENDPOINTS:
            try:
                r = requests.get(
                    url, timeout=15,
                    headers={
                        "Accept": "application/json",
                        "User-Agent": "Mozilla/5.0 (compatible; crypto-bot/1.0)",
                    },
                )
                if r.ok:
                    data = r.json()
                    break
            except Exception:
                continue

        if data is None:
            return {"signal": "neutral", "flows_3d": [], "error": "API 실패"}

        # 다양한 응답 구조 대응
        flows_raw = []
        if isinstance(data, list):
            flows_raw = data
        elif isinstance(data, dict):
            for key in ("data", "result", "items", "history", "flows", "list"):
                val = data.get(key)
                if isinstance(val, list):
                    flows_raw = val
                    break

        # netFlow 필드 추출
        flows = []
        for item in flows_raw:
            if not isinstance(item, dict):
                continue
            for fk in ("netFlow", "net_flow", "flow", "netInflow", "net_inflow",
                       "totalFlow", "total_flow", "value", "amount"):
                v = item.get(fk)
                if v is not None:
                    try:
                        flows.append(float(v))
                        break
                    except (ValueError, TypeError):
                        pass

        flows3 = flows[-3:] if len(flows) >= 3 else flows
        if len(flows3) < 3:
            return {"signal": "neutral", "flows_3d": flows3,
                    "error": f"데이터 부족 ({len(flows3)}개)"}

        if all(f > 0 for f in flows3):
            sig = "bull"
        elif all(f < 0 for f in flows3):
            sig = "bear"
        else:
            sig = "neutral"

        return {"signal": sig, "flows_3d": [round(f, 2) for f in flows3]}

    except Exception as e:
        return {"signal": "neutral", "flows_3d": [], "error": str(e)[:80]}


# ── Signal 3: 스테이블코인 시총 변화 (CoinGecko) ─────────────────────────────
def _fetch_stablecoin() -> dict:
    """
    USDT + USDC 7일 시총 변화율 평균.
    CoinGecko 무료 API. 실패 시 neutral.
    """
    import time as _time
    try:
        import requests
        total_change = 0.0
        n_ok = 0
        by_coin = {}

        for coin_id in ["tether", "usd-coin"]:
            try:
                r = requests.get(
                    f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart",
                    params={"vs_currency": "usd", "days": 8, "interval": "daily"},
                    headers={"Accept": "application/json"},
                    timeout=20,
                )
                if not r.ok:
                    _time.sleep(2)
                    continue
                mc = r.json().get("market_caps", [])
                if len(mc) < 2:
                    continue
                first = float(mc[0][1])
                last_val = float(mc[-1][1])
                if first > 0:
                    chg = (last_val - first) / first
                    total_change += chg
                    n_ok += 1
                    by_coin[coin_id] = round(chg * 100, 3)
                _time.sleep(2)
            except Exception:
                _time.sleep(2)
                continue

        if n_ok == 0:
            return {"signal": "neutral", "avg_7d_pct": None, "by_coin": {}, "error": "API 실패"}

        avg = total_change / n_ok
        if avg > STABLE_BULL_THR:
            sig = "bull"
        elif avg < STABLE_BEAR_THR:
            sig = "bear"
        else:
            sig = "neutral"

        return {"signal": sig, "avg_7d_pct": round(avg * 100, 3), "by_coin": by_coin,
                "note": "avg_7d_pct in %"}

    except Exception as e:
        return {"signal": "neutral", "avg_7d_pct": None, "by_coin": {}, "error": str(e)[:80]}


# ── 점수 변환 유틸 ─────────────────────────────────────────────────────────────
def _sig_to_score(sig: str) -> int:
    return 1 if sig == "bull" else -1 if sig == "bear" else 0


# ── 공개 함수: fetch ──────────────────────────────────────────────────────────
def fetch(use_cache: bool = True) -> dict:
    """
    온체인 보조 신호 3종 수집. 캐시 TTL=4h.

    반환:
        {
          "funding": {"signal": "bull"|"bear"|"neutral", "avg_rate": float, ...},
          "etf":     {"signal": ..., "flows_3d": [...], ...},
          "stable":  {"signal": ..., "avg_7d_pct": float, ...},
          "score":   int (-3 ~ +3),
          "fetched_at": str,
        }
    """
    if use_cache:
        cached = _load_cache()
        if cached is not None:
            print("  [온체인] 캐시 사용 (4h TTL)", flush=True)
            return cached

    print("  [온체인] 신호 수집 시작...", flush=True)

    funding = _fetch_funding()
    print(f"  [온체인] 펀딩비:       {funding['signal']:8s} "
          f"(avg={funding.get('avg_rate')}%)", flush=True)

    etf = _fetch_etf_flow()
    print(f"  [온체인] ETF 순유입:   {etf['signal']:8s} "
          f"(3d={etf.get('flows_3d', [])})", flush=True)

    stable = _fetch_stablecoin()
    print(f"  [온체인] 스테이블코인: {stable['signal']:8s} "
          f"(7d={stable.get('avg_7d_pct')}%)", flush=True)

    score = (_sig_to_score(funding["signal"])
             + _sig_to_score(etf["signal"])
             + _sig_to_score(stable["signal"]))

    result = {
        "funding":    funding,
        "etf":        etf,
        "stable":     stable,
        "score":      score,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    _save_cache(result)
    print(f"  [온체인] 종합 점수: {score:+d}", flush=True)
    return result


# ── 공개 함수: adjust_regime ─────────────────────────────────────────────────
def adjust_regime(primary_regime: str, onchain: dict) -> str:
    """
    온체인 보조 점수로 primary 레짐 완화 (조정).

    규칙:
    - primary=bear  + score >= +2 → sideways  (과매도 · 반전 가능성)
    - primary=bull_btc + score <= -2 → sideways (과열 · 조정 가능성)
    - 나머지 → primary 그대로
    """
    score = onchain.get("score", 0)
    if primary_regime == "bear" and score >= 2:
        print(f"  [온체인] {primary_regime} → sideways 완화 "
              f"(score=+{score}; 공포/반전 신호)", flush=True)
        return "sideways"
    if primary_regime == "bull_btc" and score <= -2:
        print(f"  [온체인] {primary_regime} → sideways 완화 "
              f"(score={score}; 과열 신호)", flush=True)
        return "sideways"
    return primary_regime


# ── 대시보드 표시용 텍스트 ────────────────────────────────────────────────────
def format_display(onchain: dict) -> dict:
    """
    대시보드용 온체인 요약 반환.
    {
      "funding_icon": str, "etf_icon": str, "stable_icon": str,
      "score_text": str, "score_color": str,
    }
    """
    ICONS = {"bull": "🟢", "bear": "🔴", "neutral": "🟡"}

    fund_sig   = onchain.get("funding", {}).get("signal", "neutral")
    etf_sig    = onchain.get("etf",     {}).get("signal", "neutral")
    stable_sig = onchain.get("stable",  {}).get("signal", "neutral")
    score      = onchain.get("score", 0)

    fund_rate  = onchain.get("funding", {}).get("avg_rate")
    etf_flows  = onchain.get("etf",     {}).get("flows_3d", [])
    stable_chg = onchain.get("stable",  {}).get("avg_7d_pct")

    fund_detail   = f"{fund_rate:+.4f}%" if fund_rate is not None else "—"
    etf_detail    = "3일 유입" if etf_sig == "bull" else ("3일 유출" if etf_sig == "bear" else "혼합")
    stable_detail = f"{stable_chg:+.2f}%" if stable_chg is not None else "—"

    score_color = "#26a641" if score > 0 else ("#f85149" if score < 0 else "#888")
    bull_bear   = "bull 우세" if score > 0 else ("bear 우세" if score < 0 else "중립")

    return {
        "funding_icon":   ICONS.get(fund_sig, "🟡"),
        "etf_icon":       ICONS.get(etf_sig, "🟡"),
        "stable_icon":    ICONS.get(stable_sig, "🟡"),
        "fund_sig":       fund_sig,
        "etf_sig":        etf_sig,
        "stable_sig":     stable_sig,
        "fund_detail":    fund_detail,
        "etf_detail":     etf_detail,
        "stable_detail":  stable_detail,
        "score":          score,
        "score_text":     f"{score:+d} ({bull_bear})",
        "score_color":    score_color,
    }


if __name__ == "__main__":
    result = fetch(use_cache=False)
    print("\n── 온체인 보조 신호 결과 ──")
    print(f"  펀딩비:      {result['funding']['signal']:8s}  "
          f"avg={result['funding'].get('avg_rate')}%  n={result['funding'].get('n', 0)}")
    print(f"  ETF 순유입:  {result['etf']['signal']:8s}  "
          f"3d={result['etf'].get('flows_3d', [])}")
    print(f"  스테이블코인: {result['stable']['signal']:8s}  "
          f"7d={result['stable'].get('avg_7d_pct')}%")
    print(f"  종합 점수:   {result['score']:+d}  "
          f"({'bull 우세' if result['score']>0 else 'bear 우세' if result['score']<0 else '중립'})")
