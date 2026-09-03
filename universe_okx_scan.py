"""
universe_okx_scan.py — 유니버스 확대 1~2단계 (2026-09-04, 사용자 지시).

질문: 업비트 교집합(67종목) 대신 'OKX 무기한 거래대금 상위 N' 으로 바꾸면 무엇이 달라지나.
1) 스캔: OKX USDT 무기한 활성 종목을 24h 거래대금으로 정렬 → 상위 TOP_SCAN 중 현 유니버스
   밖 후보를 골라 1d 900일을 받는다(현 유니버스 67 도 같이 받아 같은 잣대로 순위).
   500봉 미만은 데이터 부족으로 표시만.
2) 코호트 검증: 전체(현 유니버스 ∪ 후보)를 30일 평균 거래대금(scheduler._volume_ranked 와
   같은 식)으로 정렬해 순위 구간별(1-20 / 21-30 / 31-50 / 51-80 / 81+)로 배포 1d 패턴의
   동결 라벨(±10%/20봉) 성적과 게이트(n>=20/mean/median/boot_p/OOS 4분위)를 잰다.
   추가로 '현 유니버스 vs 신규 후보' 와 '확대 후 top20/top30 이 현 top20/top30 과 어떻게
   달라지는가'를 낸다 — engulfing 은 top20, fvg 는 top30 만 쓰므로 그 경계가 핵심.
실거래 코드 무변경. 출력 _okx_scan.json + RESULT_JSON.
"""
import json
import statistics as st
import sys
import time
import importlib

import ccxt
import detlib
import fetch_data
from validate_confirm_bar import gate

TOP_SCAN = 150            # 24h 거래대금 상위 몇 종목까지 후보로 볼지
MIN_BARS = 500
WINDOW_1D = 900
STABLE = {"USDT", "USDC", "DAI", "BUSD", "TUSD", "FDUSD", "PYUSD", "USDE", "USD1", "USDD"}
PATTERNS = [("engulfing", "detector_engulfing", "long"),
            ("engulfing_short", "detector_engulfing_short", "short"),
            ("fvg", "detector_fvg", "long"),
            ("fvg_short", "detector_fvg_short", "short"),
            ("inverted_hammer", "detector_inverted_hammer", "long"),
            ("marubozu", "detector_marubozu", "long")]
COHORTS = [(1, 20), (21, 30), (31, 50), (51, 80), (81, 10_000)]


def okx_perps_by_volume():
    ex = ccxt.okx({"enableRateLimit": True})
    mk = ex.load_markets()
    syms = [m["symbol"] for m in mk.values() if m.get("swap") and m.get("quote") == "USDT"
            and m.get("active") and m.get("settle") == "USDT"]
    t = ex.fetch_tickers(syms)
    rows = []
    for s, tk in t.items():
        base = s.split("/")[0]
        if base in STABLE:
            continue
        # OKX 무기한 티커는 ccxt quoteVolume 이 비어 있을 수 있다(1차 실행에서 전부 0 →
        # 알파벳 역순 정렬). volCcy24h(기초자산 수량) x 현재가 → USD 거래대금으로 폴백.
        last = float(tk.get("last") or 0)
        qv = float(tk.get("quoteVolume") or 0)
        if not qv:
            info = tk.get("info") or {}
            base_vol = float(tk.get("baseVolume") or info.get("volCcy24h") or 0)
            qv = base_vol * last
        rows.append((qv, base))
    rows.sort(reverse=True)
    return rows


def fetch_1d(sym):
    """
    **무기한 캔들 우선**(없으면 현물). 2차 실행에서 현 유니버스는 현물, 후보는 무기한으로
    받아 '현물 거래대금 vs 선물 거래대금'을 비교하는 꼴이 됐다(후보 과대평가). 실제 매매가
    무기한이므로 전 종목을 무기한으로 통일한다. ccxt 는 둘 다 기초자산 수량으로 거래량을
    주므로(okx.parse_ohlcv: spot idx5 / swap idx6 = base volume) close x volume = USD 거래대금.
    반환 총 봉수.
    """
    path = detlib.CSV(sym, "1d")
    for symbol in (f"{sym}/USDT:USDT", f"{sym}/USDT"):
        try:
            _, total = fetch_data.update_csv(symbol, "1d", path, window_days=WINDOW_1D)
        except Exception as e:
            print(f"  [fetch] {symbol} 실패: {str(e)[:60]}"); total = 0
        if total:
            return total
    return 0


def turnover_30d(rows):
    if len(rows) < 35:
        return None
    return sum(r["c"] * r["v"] for r in rows[-30:]) / 30


def collect(sym, pat_mod, direction, rows):
    mod = importlib.import_module(pat_mod)
    out = []
    for si in mod.detect(rows):
        if si + 1 >= len(rows):
            continue
        _, ret = detlib.outcome(rows, si, direction)
        out.append((rows[si]["date"], ret))
    return out


def main():
    u = json.load(open("universe.json", encoding="utf-8"))
    cur = list(u["trading_universe"])
    known_bad = set(u.get("okx_unavailable", []))
    t0 = time.time()
    vol = okx_perps_by_volume()
    print(f"[okx] USDT 무기한 활성 {len(vol)}종목 (스테이블 제외), 조회 {time.time()-t0:.0f}s")
    rank24 = {b: i + 1 for i, (_, b) in enumerate(vol)}
    cands = [b for _, b in vol[:TOP_SCAN] if b not in cur and b not in known_bad]
    print(f"[okx] 24h 상위 {TOP_SCAN} 중 유니버스 밖 후보 {len(cands)}종목")
    print("[okx] 24h 상위 40:", "  ".join(f"{i+1}{'★' if b in cur else ''}{b}({v/1e6:.0f}M)" for i, (v, b) in enumerate(vol[:40])))
    if vol and vol[0][0] <= 0:
        raise SystemExit("[okx] 거래대금이 전부 0 — 티커 필드 확인 필요(정렬 무의미)")

    # ── fetch 1d (현 유니버스 + 후보), 시간 측정 ─────────────────────────────
    info = {}
    tf0 = time.time(); per_sym = []
    for s in cur + cands:
        t1 = time.time()
        total = fetch_1d(s)
        per_sym.append(time.time() - t1)
        rows = []
        if total:
            try:
                rows = detlib.load_ohlcv(s, "1d")
            except Exception:
                rows = []
        info[s] = dict(bars=len(rows), turnover=turnover_30d(rows) if rows else None,
                       rank24=rank24.get(s), in_universe=s in cur)
    print(f"[fetch] 1d {WINDOW_1D}일 x {len(cur)+len(cands)}종목: {time.time()-tf0:.0f}s "
          f"(종목당 중앙 {st.median(per_sym):.1f}s / 최대 {max(per_sym):.1f}s)")

    ok = {s: v for s, v in info.items() if v["bars"] >= MIN_BARS and v["turnover"]}
    short = sorted(s for s, v in info.items() if 0 < v["bars"] < MIN_BARS)
    fail = sorted(s for s, v in info.items() if v["bars"] == 0)
    print(f"[data] 500봉 이상 {len(ok)} / 부족 {len(short)} / 실패 {len(fail)}")
    print(f"[data] 데이터 부족 후보: {short}")

    # ── 30일 거래대금 순위(현+후보) ───────────────────────────────────────────
    ranked = sorted(ok, key=lambda s: -ok[s]["turnover"])
    rank30 = {s: i + 1 for i, s in enumerate(ranked)}
    cur_ranked = sorted([s for s in ranked if s in cur], key=lambda s: rank30[s])
    new_top20 = ranked[:20]; new_top30 = ranked[:30]
    cur_top20 = cur_ranked[:20]; cur_top30 = cur_ranked[:30]
    print(f"[rank] 확대 후 top20 중 신규: {[s for s in new_top20 if s not in cur]}")
    print(f"[rank] 확대 후 top30 중 신규: {[s for s in new_top30 if s not in cur]}")
    print(f"[rank] 현 top20 에서 밀려나는 종목: {[s for s in cur_top20 if s not in new_top20]}")
    print(f"[rank] 현 top30 에서 밀려나는 종목: {[s for s in cur_top30 if s not in new_top30]}")
    print("[rank] 확대 후 상위 40(30일 평균 거래대금 M$):", "  ".join(f"{rank30[s]}{'★' if s in cur else ''}{s}({ok[s]['turnover']/1e6:.0f})" for s in ranked[:40]))

    # ── 코호트별 패턴 성적 ───────────────────────────────────────────────────
    rows_cache = {s: detlib.load_ohlcv(s, "1d") for s in ok}
    results = {}
    for pat, modname, direction in PATTERNS:
        per_sym_sigs = {s: collect(s, modname, direction, rows_cache[s]) for s in ok}
        results[pat] = {}
        print(f"\n[{pat} {direction}]")
        groups = {f"rank{lo}-{min(hi, len(ranked))}": [s for s in ranked if lo <= rank30[s] <= hi] for lo, hi in COHORTS}
        groups["current_universe"] = [s for s in ranked if s in cur]
        groups["new_candidates"] = [s for s in ranked if s not in cur]
        groups["cur_top20"] = cur_top20; groups["new_top20"] = new_top20
        groups["cur_top30"] = cur_top30; groups["new_top30"] = new_top30
        for g, syms in groups.items():
            sigs = [x for s in syms for x in per_sym_sigs[s]]
            if not syms:
                continue
            rec = gate(f"{pat}:{g}", sigs, syms, "1d")
            rec["symbols"] = len(syms)
            results[pat][g] = rec
    out = dict(scan=dict(okx_active=len(vol), top_scan=TOP_SCAN, candidates=cands, data_short=short, data_fail=fail,
                         fetch_sec_per_symbol_median=round(st.median(per_sym), 2)),
               info=info, rank30=rank30, new_top20=new_top20, new_top30=new_top30,
               cur_top20=cur_top20, cur_top30=cur_top30, results=results)
    json.dump(out, open("_okx_scan.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    summary = {p: {g: dict(v=r["verdict"], n=r["n"], mean=round(r["mean"] * 100, 2), med=round(r["median"] * 100, 2))
                   for g, r in gs.items()} for p, gs in results.items()}
    print("\nRESULT_JSON: " + json.dumps(dict(new_top20=[s for s in new_top20 if s not in cur],
                                              new_top30=[s for s in new_top30 if s not in cur],
                                              candidates=len(cands), ok=len(ok), short=len(short),
                                              summary=summary), ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
