import sys
sys.path.insert(0, ".")
from triple_bottom_volume import detect_triple_bottom_descending
from backtest import load_csv, run_backtest

CONFS  = [0.0, 0.5, 0.6, 0.7]
FILES  = {"BTC": "data/btc_1h.csv", "SOL": "data/sol_1h.csv"}
HOLD   = 10
FEE    = 0.001
WARMUP = 60

detector = lambda c: detect_triple_bottom_descending(c)

results = {}
for sym, path in FILES.items():
    ohlcv = load_csv(path)
    n_total = len(ohlcv)
    results[sym] = {"n_total": n_total, "rows": []}
    for mc in CONFS:
        res = run_backtest(ohlcv, detector, "triple_bottom_desc",
                           hold=HOLD, min_conf=mc, fee=FEE, warmup=WARMUP)
        n    = res["n_trades"]
        per1k = round(n / n_total * 1000, 2) if n_total else 0
        wr   = f"{res['win_rate']*100:.1f}%" if res["win_rate"] is not None else "—"
        avg  = f"{res['avg_ret']*100:+.2f}%" if res["avg_ret"] is not None else "—"
        med  = f"{res['median_ret']*100:+.2f}%" if res["median_ret"] is not None else "—"
        rets = [t["ret"] for t in res["trades"]]
        results[sym]["rows"].append(
            {"mc": mc, "n": n, "per1k": per1k,
             "wr": wr, "avg": avg, "med": med, "rets": rets}
        )

# ── 표 출력 ──────────────────────────────────────────────────────────
for sym, data in results.items():
    n_total = data["n_total"]
    print(f"\n{'='*64}")
    print(f"  {sym}/USDT 1h  ({n_total:,}캔들, hold={HOLD}, fee={FEE})")
    print(f"{'='*64}")
    print(f"{'min-conf':>9} {'신호수':>6} {'per 1k':>7} {'승률':>8} {'평균':>8} {'중앙값':>8}")
    print("-"*64)
    for r in data["rows"]:
        print(f"{r['mc']:>9.1f} {r['n']:>6} {r['per1k']:>7.2f} "
              f"{r['wr']:>8} {r['avg']:>8} {r['med']:>8}")

# ── conf=0.0 per-trade 원시값 ─────────────────────────────────────────
print(f"\n{'='*64}")
print("  conf=0.0 per-trade 수익 원시값 (수수료 차감 후)")
print(f"{'='*64}")
for sym, data in results.items():
    row0 = data["rows"][0]
    rets = row0["rets"]
    print(f"\n[{sym}]  총 {row0['n']}건")
    if rets:
        for i, r in enumerate(rets, 1):
            print(f"  #{i:02d}  {r*100:+.4f}%")
    else:
        print("  (신호 없음)")
