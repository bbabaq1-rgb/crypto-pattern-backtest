"""
expand_universe.py — 업비트 KRW ∩ OKX 선물 교집합으로 유니버스 확대.

A. 업비트 KRW + OKX USDT-swap 교집합, 기존 제외
B. OKX 1d + 4h 데이터 fetch (500봉 미만 스킵)
C. engulfing/fvg/inverted_hammer/marubozu(1d) + gartley/bat/butterfly(4h) 검증
D. universe.json 갱신
"""
import os, sys, json, subprocess, statistics as st, importlib, time

import detlib

SINCE = "2021-01-01"
MIN_BARS = 500          # 이 미만이면 데이터 부족으로 스킵
SYM_MIN_N = 5           # 심볼 채택 최소 신호 수
STABLECOINS = {"USDT", "USDC", "DAI", "BUSD", "TUSD", "FDUSD", "PYUSD"}


# ────────────────────────────────────────────────
# A. 교집합 수집
# ────────────────────────────────────────────────

def get_upbit_krw():
    import urllib.request
    url = "https://api.upbit.com/v1/market/all"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        markets = json.loads(r.read())
    return {m["market"].replace("KRW-", "") for m in markets if m["market"].startswith("KRW-")}


def get_okx_swap():
    import ccxt
    okx = ccxt.okx({"enableRateLimit": True})
    mkts = okx.load_markets()
    return {
        m["base"] for m in mkts.values()
        if m.get("settle") == "USDT" and m.get("type") == "swap" and m.get("active")
    }


def load_universe():
    return json.load(open("universe.json", encoding="utf-8"))


def known_symbols(uni):
    s = set(uni.get("trading_universe", []))
    s |= set(uni.get("okx_unavailable", []))
    s |= set(uni.get("rejected", {}).keys())
    s |= set(uni.get("data_short", []))
    return s


# ────────────────────────────────────────────────
# B. 데이터 fetch
# ────────────────────────────────────────────────

def fetch_sym(sym, tf, exchange="okx"):
    out = f"data/{sym.lower()}_{tf.replace('h','h')}.csv"
    r = subprocess.run(
        [sys.executable, "fetch_data.py",
         "--exchange", exchange,
         "--symbol", f"{sym}/USDT",
         "--timeframe", tf,
         "--since", SINCE,
         "--out", out],
        capture_output=True, text=True
    )
    return r.returncode == 0, out


def bar_count(path):
    if not os.path.exists(path):
        return 0
    with open(path) as f:
        return sum(1 for _ in f) - 1  # 헤더 제외


# ────────────────────────────────────────────────
# C. 패턴 검증 (심볼 단위)
# ────────────────────────────────────────────────

PATTERNS_1D = [
    ("engulfing",        "detector_engulfing",        "long"),
    ("fvg",              "detector_fvg",              "long"),
    ("inverted_hammer",  "detector_inverted_hammer",  "long"),
    ("marubozu",         "detector_marubozu",         "long"),
]
PATTERNS_4H = [
    ("gartley",   "detector_gartley",   "long"),
    ("bat",       "detector_bat",       "long"),
    ("butterfly", "detector_butterfly", "long"),
]


def validate_sym(sym, patterns, tf):
    """심볼 하나에 대해 여러 패턴 실행 → {pat: {n, mean, median}}."""
    res = {}
    for pat, modname, direction in patterns:
        mod = importlib.import_module(modname)
        try:
            rows = detlib.load_ohlcv(sym, tf)
        except (FileNotFoundError, RuntimeError):
            res[pat] = None
            continue
        sigs = mod.detect(rows)
        rets = [detlib.outcome(rows, si, direction=direction)[1] for si in sigs]
        if not rets:
            res[pat] = {"n": 0, "mean": None, "median": None}
        else:
            res[pat] = {
                "n": len(rets),
                "mean": round(st.mean(rets), 5),
                "median": round(st.median(rets), 5),
            }
    return res


def sym_verdict(res_1d, res_4h):
    """심볼 채택 여부 판정. pass 패턴 목록과 사유 반환."""
    passed_pats = []
    for pat, r in {**res_1d, **res_4h}.items():
        if r and r["n"] >= SYM_MIN_N and r["mean"] is not None and r["mean"] > 0:
            passed_pats.append(pat)
    if passed_pats:
        return True, f"통과 패턴: {', '.join(passed_pats)}"
    # 기각 사유 구성
    best = max(
        ((r["mean"] if r and r["mean"] is not None else -999), pat)
        for pat, r in {**res_1d, **res_4h}.items()
    )
    return False, f"모든 패턴 기대값<=0 (최고: {best[0]*100:+.2f}% {best[1]})"


# ────────────────────────────────────────────────
# 메인
# ────────────────────────────────────────────────

def main():
    os.makedirs("data", exist_ok=True)
    uni = load_universe()
    known = known_symbols(uni)

    print("=" * 70)
    print("A. 업비트 KRW ∩ OKX USDT-swap 교집합 수집")
    print("=" * 70)
    upbit = get_upbit_krw()
    okx   = get_okx_swap()
    inter = (upbit & okx) - STABLECOINS
    new_cands = sorted(inter - known)
    print(f"  Upbit KRW: {len(upbit)}종목 | OKX swap: {len(okx)}종목")
    print(f"  교집합: {len(inter)}종목 | 기존 제외 후 신규 후보: {len(new_cands)}종목")
    print(f"  신규 후보: {new_cands}")

    print("\n" + "=" * 70)
    print("B. 데이터 fetch (OKX, 1d + 4h, 500봉 미만 스킵)")
    print("=" * 70)
    data_short = []
    fetch_ok   = []
    for sym in new_cands:
        ok1d, path1d = fetch_sym(sym, "1d")
        n1d = bar_count(path1d)
        if not ok1d or n1d < MIN_BARS:
            print(f"  [{sym}] 1d {n1d}봉 → DATA_SHORT (스킵)")
            data_short.append(sym)
            continue
        # 4h fetch (실패해도 DATA_SHORT 처리 안 함 — 1d만으로도 검증 가능)
        ok4h, path4h = fetch_sym(sym, "4h")
        n4h = bar_count(path4h)
        print(f"  [{sym}] 1d={n1d}봉 / 4h={n4h}봉 ({'OK' if ok4h else 'fetch실패'})")
        fetch_ok.append((sym, n1d, n4h if ok4h else 0))

    print(f"\n  fetch 완료: {len(fetch_ok)}종목 | DATA_SHORT: {len(data_short)}종목")

    print("\n" + "=" * 70)
    print("C. 패턴 검증 (심볼 단위, n≥5 & mean>0 → 채택)")
    print("=" * 70)
    adopted = []
    rejected = {}

    for sym, n1d, n4h in fetch_ok:
        res_1d = validate_sym(sym, PATTERNS_1D, "1d")
        res_4h = validate_sym(sym, PATTERNS_4H, "4h") if n4h >= MIN_BARS else {}

        ok, reason = sym_verdict(res_1d, res_4h)

        summary_parts = []
        for pat, r in {**res_1d, **res_4h}.items():
            if r and r["n"] > 0:
                summary_parts.append(f"{pat}(n={r['n']},μ={r['mean']*100:+.1f}%)")
        summary = " | ".join(summary_parts) if summary_parts else "신호 없음"

        verdict_str = "ADOPT" if ok else "REJECT"
        print(f"  [{sym}] {verdict_str} - {reason}")
        print(f"         {summary}")

        if ok:
            adopted.append(sym)
        else:
            rejected[sym] = reason

    print(f"\n  채택: {len(adopted)}종목 {adopted}")
    print(f"  기각: {len(rejected)}종목")
    print(f"  데이터부족: {len(data_short)}종목")

    print("\n" + "=" * 70)
    print("D. universe.json 갱신")
    print("=" * 70)
    # 기존 universe 갱신
    uni["trading_universe"] = sorted(set(uni["trading_universe"]) | set(adopted))
    uni["data_short"]       = sorted(set(uni.get("data_short", [])) | set(data_short))
    uni.setdefault("rejected", {})
    uni["rejected"].update(rejected)
    uni["tried"] = uni.get("tried", 0) + len(fetch_ok) + len(data_short)

    # 신규 채택 정보
    uni.setdefault("expansion_runs", [])
    from datetime import datetime, timezone
    run_info = {
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "source": "upbit_krw_x_okx_swap",
        "candidates": len(new_cands),
        "adopted": adopted,
        "rejected_count": len(rejected),
        "data_short_count": len(data_short),
    }
    uni["expansion_runs"].append(run_info)

    json.dump(uni, open("universe.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"  universe.json 저장 완료")
    print(f"  trading_universe: {len(uni['trading_universe'])}종목")

    return {
        "intersection": len(inter),
        "new_candidates": len(new_cands),
        "fetch_ok": len(fetch_ok),
        "data_short": len(data_short),
        "adopted": adopted,
        "rejected": rejected,
    }


if __name__ == "__main__":
    result = main()
