"""
실행 엔진 안전장치 검증 (2026-09-03 전체 점검 후속).

  - 저가 코인: 진입가·손절가 8자리 보존, 진입가 0 이어도 청산 경로가 죽지 않음
  - DB 복원 tf 는 universe 기준(_pattern_tf) — triple_bottom → 1w
  - reconcile_closed_positions 는 엔진이 이미 D 청산한 포지션을 다시 기록하지 않음
  - 킬스위치 fail-closed: 잔고 조회 실패 → 신규 진입 보류
  - 같은 종목·방향 실포지션 중복 진입 방어(거래소 실측 + 장부)
  - ensure_stop_orders(replace=): 살아있는 algo 를 취소하고 새 배리어로 재등록
  - place_swap_entry: 주문 재조회로 실제 평균 체결가 사용
  - 실거래 손익(pnl_live_usd) 기록 경로

실행: python test_executor_safety.py
"""
import json
import random
import sys
import zlib

import paper_executor as pe
import exchange as ex_mod

fails = []


def check(n, c, d=""):
    print(("PASS " if c else "FAIL ") + n + ("" if c else f" — {d}"))
    c or fails.append(n)


src_pe = open("paper_executor.py", encoding="utf-8").read()
src_ex = open("exchange.py", encoding="utf-8").read()


# ── 1. reconcile: d_closed 포지션 재기록 금지 + 진입가 0 방어 + 실손익 동봉 ────
orig_pos, orig_hist = ex_mod.get_okx_positions, ex_mod.get_okx_closed_positions
ex_mod.get_okx_positions = lambda c: []
ex_mod.get_okx_closed_positions = lambda c, limit=50: {("SOL", "long"): {"close_px": 95.0, "pnl": -1.23, "type": "2"},
                                                        ("ADA", "long"): {"close_px": 0.5, "pnl": 0.4, "type": "4"}}
pe._db = lambda: None
positions = [dict(symbol="SOL", direction="long", pattern="marubozu", entry_date="2026-09-01",
                  entry_price=100.0, live_mode=True, d_closed=True, a_closed=False, entry_idx=0),
             dict(symbol="ADA", direction="long", pattern="fvg", entry_date="2026-09-01",
                  entry_price=0.0, live_mode=True, d_closed=False, a_closed=False, entry_idx=0)]
trades = []
kept, closed = pe.reconcile_closed_positions(positions, trades, {"exchange": None})
check("d_closed 포지션은 reconcile 이 다시 기록하지 않고 유지(A 다리)",
      [p["symbol"] for p in kept] == ["SOL"] and all(t["symbol"] != "SOL" for t in trades), (kept, trades))
check("진입가 0 인 포지션도 예외 없이 기록(수익률 0)", closed == ["ADA"] and trades and trades[-1]["ret"] == round(-pe.FEE, 5), trades)
check("reconcile 기록에 거래소 실손익 동봉", trades and trades[-1].get("pnl_live_usd") == 0.4, trades)
ex_mod.get_okx_positions, ex_mod.get_okx_closed_positions = orig_pos, orig_hist

# ── 2. 복원 tf ────────────────────────────────────────────────────────────────
check("복원 시 tf 는 DB 컬럼 우선, 없으면 _pattern_tf(universe 기준)",
      'tf=p.get("tf") or _pattern_tf(p["pattern"])' in src_pe and 'tf=_derive_tf(p["pattern"])' not in src_pe)
check("triple_bottom 복원 tf = 1w", pe._pattern_tf("triple_bottom") == "1w")

# ── 3. 킬스위치 / 중복 진입 (소스 고정) ──────────────────────────────────────
check("잔고 조회 실패 → 킬스위치(fail-closed)", "if bal is None:" in src_pe and "fail-closed" in src_pe)
check("같은 종목·방향 실포지션 중복 진입 스킵", 'if (s["symbol"], s["direction"]) in live_dir_keys:' in src_pe)
check("중복 키는 거래소 실측 + 장부 live 포지션 합집합", "ex_mod.get_okx_positions(live_conn)}" in src_pe
      and 'for p in still_open if p.get("live_mode")}' in src_pe)
check("진입가·손절가·청산가 8자리", "entry_price=round(entry, 8)" in src_pe and "stop=round(stop_px, 8)" in src_pe
      and "exit_price=round(exit_px, 8)" in src_pe and "round(entry, 4)" not in src_pe)
check("실거래 D 청산 진입가 0 방어", 'if fill and pos["entry_price"]:' in src_pe)
check("재정렬은 replace= 로 기존 algo 를 교체", "replace={s[\"symbol\"]}" in src_pe)


# ── 4. ensure_stop_orders(replace=) ─────────────────────────────────────────
class StubEx:
    def __init__(self, positions=None, pending=None):
        self.sent, self.cancelled, self.queried = [], [], []
        self._positions, self._pending = positions or [], pending or {}
    def privatePostTradeOrderAlgo(self, params):
        self.sent.append(params); return {"code": "0", "data": [{"algoId": f"A{len(self.sent)}"}]}
    def privateGetTradeOrdersAlgoPending(self, params):
        self.queried.append(params.get("ordType")); return {"code": "0", "data": self._pending.get(params.get("ordType"), [])}
    def privatePostTradeCancelAlgos(self, orders):
        self.cancelled += orders; return {"code": "0"}
    def price_to_precision(self, sym, px): return f"{float(px):.8f}"
    def market_id(self, sym): return sym.split("/")[0] + "-USDT-SWAP"
    def fetch_positions(self, symbols=None): return self._positions


okx_pos = [{"symbol": "SOL/USDT:USDT", "side": "long", "contracts": 1.0, "entryPrice": 100.0,
            "notional": 100.0, "contractSize": 1.0, "info": {"instId": "SOL-USDT-SWAP", "margin": "50"}, "leverage": 2}]
live_oco = {"oco": [{"state": "live", "instId": "SOL-USDT-SWAP", "slTriggerPx": "98.5", "algoId": "X1"}]}
ex = StubEx(positions=okx_pos, pending=live_oco)
fixed, cancelled = ex_mod.ensure_stop_orders({"exchange": ex}, stop_map={"SOL": {"stop": 98.7, "target": 101.7}})
check("replace 없으면 살아있는 OCO 유지(종전 동작)", not ex.sent and not ex.cancelled)
ex = StubEx(positions=okx_pos, pending=live_oco)
fixed, cancelled = ex_mod.ensure_stop_orders({"exchange": ex}, stop_map={"SOL": {"stop": 98.7, "target": 101.7}},
                                             replace={"SOL"})
check("replace: 기존 algo 취소", ex.cancelled and ex.cancelled[0]["algoId"] == "X1", ex.cancelled)
check("replace: 새 배리어로 OCO 재등록", ex.sent and ex.sent[-1]["ordType"] == "oco"
      and abs(float(ex.sent[-1]["slTriggerPx"]) - 98.7) < 1e-9 and abs(float(ex.sent[-1]["tpTriggerPx"]) - 101.7) < 1e-9, ex.sent)
check("replace 대상이 아닌 심볼은 영향 없음", len(ex.cancelled) == 1 and len(ex.sent) == 1)


# ── 5. place_swap_entry: 실제 체결가 재조회 ──────────────────────────────────
class EntryStub(StubEx):
    def __init__(self, avg=None):
        super().__init__(); self._avg = avg; self.fetched = []
    def set_margin_mode(self, *a, **k): pass
    def set_leverage(self, *a, **k): pass
    def fetch_ticker(self, sym): return {"last": 100.0}
    def fetch_balance(self): return {"USDT": {"free": 1000.0}}
    def market(self, sym): return {"contractSize": 1.0, "limits": {"amount": {"min": 0}}}
    def amount_to_precision(self, sym, q): return f"{float(q):.4f}"
    def create_market_order(self, sym, side, qty, params=None):
        return {"id": "E1", "filled": qty}          # 시장가 응답엔 average 없음(실제 OKX 와 동일)
    def fetch_order(self, oid, sym):
        self.fetched.append(oid); return {"average": self._avg, "filled": 0.4}


ex = EntryStub(avg=100.37)
res, why = ex_mod.place_swap_entry({"exchange": ex}, "SOL", "long", 92.0, size_usd=20.0)
check("주문 재조회로 실제 평균 체결가 사용", why == "ok" and abs(res["entry_price"] - 100.37) < 1e-9 and ex.fetched == ["E1"], (res, why))
ex = EntryStub(avg=None)
res, why = ex_mod.place_swap_entry({"exchange": ex}, "SOL", "long", 92.0, size_usd=20.0)
check("재조회에 average 없으면 종전 폴백(시세)", why == "ok" and abs(res["entry_price"] - 100.0) < 1e-9, res)


# ── 6. 저가 코인 e2e: 진입가 8자리 보존, 청산 경로 정상 ──────────────────────
def mkrows(n, seed, scale, step=86400000, start_ts=1_600_000_000_000):
    random.seed(seed); px, ts, rows = 100.0 * scale, start_ts, []
    from datetime import datetime, timezone
    for _ in range(n):
        nxt = px * (1 + random.gauss(0, 0.004))
        d = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        rows.append(dict(ts=ts, date=d, o=px, h=max(px, nxt) * 1.002, l=min(px, nxt) * 0.998, c=nxt, v=100.0))
        px, ts = nxt, ts + step
    return rows


def _e2e():
    import csv as _csv, os, shutil, tempfile, detlib
    import regime_switch as rs
    repo, tmp = os.getcwd(), tempfile.mkdtemp()
    shutil.copy("registry.json", os.path.join(tmp, "registry.json"))
    shutil.copy("universe.json", os.path.join(tmp, "universe.json"))
    orig = rs.build_regime_map
    try:
        os.chdir(tmp); os.makedirs("data", exist_ok=True)
        for sym, scale in (("SHIB", 1e-7), ("BTC", 1.0)):
            rr = mkrows(120, zlib.crc32(sym.encode()) % 1000, scale)
            with open(f"data/{sym.lower()}_1d.csv", "w", newline="") as f:
                w = _csv.writer(f); w.writerow(["timestamp", "open", "high", "low", "close", "volume"])
                for x in rr: w.writerow([x["ts"], x["o"], x["h"], x["l"], x["c"], x["v"]])
        r1d = detlib.load_ohlcv("SHIB", "1d"); si = 10
        rs.build_regime_map = lambda *a, **k: {r["date"]: "bull_btc" for r in r1d}
        json.dump({"signals": [dict(symbol="SHIB", pattern="marubozu", direction="long", tf="1d",
                                    date=r1d[si]["date"], ts=r1d[si]["ts"], regime="bull_btc")]}, open("signals_today.json", "w"))
        pe.run()
        pos = json.load(open("paper_positions.json"))
        json.dump({"signals": []}, open("signals_today.json", "w"))
        pe.run()
        return pos, json.load(open("paper_trades.json")), r1d[si]["c"]
    finally:
        rs.build_regime_map = orig; os.chdir(repo); shutil.rmtree(tmp, ignore_errors=True)


pos, tr, c0 = _e2e()
check("저가 코인 진입가가 0 이 아니고 8자리 보존", pos and pos[0]["entry_price"] > 0 and abs(pos[0]["entry_price"] - round(c0, 8)) < 1e-12, pos)
check("저가 코인 손절가도 0 이 아님", pos and pos[0]["stop"] > 0, pos)
check("저가 코인 청산 경로 정상(D·A 기록, 예외 없음)", {t["method"] for t in tr} == {"D", "A"} and all(t["exit_price"] > 0 for t in tr), tr)


# ── 중복 진입 방어 키 — 봉 ts 기준 (2026-09-05 사용자 결정) ──────────────────
_recs = [dict(symbol="ETH", pattern="triple_bottom_4h", direction="long", entry_date="2026-09-05", entry_ts=1000),
         dict(symbol="SOL", pattern="fvg", direction="long", entry_date="2026-09-05")]          # 구 기록: ts 없음
_ts, _dt, _all = pe._record_keys(_recs)
check("키: 같은 날 다른 봉(ts) 신호는 중복이 아니다",
      not pe._is_dup_entry(dict(symbol="ETH", pattern="triple_bottom_4h", direction="long", date="2026-09-05", ts=2000), _ts, _dt, _all))
check("키: 같은 봉(ts) 신호는 중복",
      pe._is_dup_entry(dict(symbol="ETH", pattern="triple_bottom_4h", direction="long", date="2026-09-05", ts=1000), _ts, _dt, _all))
check("키: ts 없는 구 기록은 date 로 보수 대조 — 그날 신호는 중복",
      pe._is_dup_entry(dict(symbol="SOL", pattern="fvg", direction="long", date="2026-09-05", ts=3000), _ts, _dt, _all))
check("키: ts 없는 신호는 date 로만 대조(ts 기록에도 걸린다)",
      pe._is_dup_entry(dict(symbol="ETH", pattern="triple_bottom_4h", direction="long", date="2026-09-05"), _ts, _dt, _all))
check("키: 다른 날은 중복 아님",
      not pe._is_dup_entry(dict(symbol="SOL", pattern="fvg", direction="long", date="2026-09-06", ts=4000), _ts, _dt, _all))
check("키: 다른 방향은 별개", not pe._is_dup_entry(dict(symbol="ETH", pattern="triple_bottom_4h", direction="short", date="2026-09-05", ts=1000), _ts, _dt, _all))
check("키: ts 문자열/실수도 정규화", pe._norm_ts("1000") == 1000 and pe._norm_ts(1000.0) == 1000 and pe._norm_ts(None) is None)
check("run(): 종전 date 키 코드가 남아 있지 않다",
      'key = (s["symbol"], s["pattern"], s["direction"], s["date"])' not in open("paper_executor.py", encoding="utf-8").read()
      and "_is_dup_entry(s, dup_ts, dup_dt, dup_all)" in open("paper_executor.py", encoding="utf-8").read())

print(f"\n{len(fails)} failed")
sys.exit(1 if fails else 0)
