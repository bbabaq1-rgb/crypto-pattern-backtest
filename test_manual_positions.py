"""
test_manual_positions.py — 대표님 수동 포지션 종목을 프로그램이 건드리지 않는다 (2026-11-04).

계기: "지금 okx에 ont 15배 롱 내가 수동 매매했어 이건 너가 건드리지 마 내가 수동으로 처리하게".
손절 자동점검(exchange.ensure_stop_orders)은 거래소의 **모든** 포지션을 돌며 손절 algo 가 없으면
진입가 ±8% 손절을 걸고, 포지션이 없어진 종목의 algo 는 고아로 취소한다. universe.json
["manual_positions"] 에 적힌 종목은 그 두 가지를 하지 않는다. 같은 목록으로 장부 행의 실거래
승격(reconcile_live_flag)과 신규 진입(메인·AI)도 막는다 — 승격되면 방식D 청산이, 진입하면 OKX net
모드 합산이 그 포지션에 닿기 때문이다.

  1. ensure_stop_orders(skip=) — 수동 종목: 재등록 없음 · 재정렬 취소 없음 · 고아 취소 없음 / 나머지 종목 동작 불변
  2. skip 없음·빈 집합이면 종전과 호출이 바이트 단위로 같다
  3. manual_symbols — 키 없음·빈 목록·파일 없음·깨진 JSON → 빈 집합, 대소문자·공백 정규화
  4. reconcile_live_flag — 수동 종목 장부 행은 승격하지 않는다(기본은 manual_symbols 를 읽는다)
  5. 배선(소스) — 손절 점검 두 호출부가 skip 을 넘긴다 · 진입 루프 판정이 봉 조회·중복 방어·AI 판단·사이징보다 앞
  6. 현재 universe.json — ONT·BAT 가 manual_positions 에 있고 program_exclude 와는 별개
  7. 오프라인 e2e — 같은 실행에 ONT·ETH 신호가 오면 ETH 만 진입, 목록을 비우면 둘 다 진입(종전 동작)

실행: python test_manual_positions.py   (실패 시 exit 1)
"""
import csv
import io
import json
import os
import random
import shutil
import sys
import tempfile

import exchange as ex_mod
import paper_executor as pe

fails = []


def check(n, c, d=""):
    print(("PASS " if c else "FAIL ") + n + ("" if c else f" — {d}"))
    if not c:
        fails.append(n)


class StubEx:
    """ensure_stop_orders 가 쓰는 OKX 엔드포인트만 흉내낸다(test_exchange_stops 와 같은 모양)."""

    def __init__(self, positions, pending):
        self._positions = positions
        self._pending = pending
        self.algo_calls = []
        self.cancel_calls = []

    def fetch_positions(self):
        return self._positions

    def privateGetTradeOrdersAlgoPending(self, params):
        # conditional·oco 두 번 조회된다 — 같은 주문을 두 번 줘도 algoId 로 1건 처리되는지까지 본다
        return {"code": "0", "data": list(self._pending)}

    def privatePostTradeOrderAlgo(self, params):
        self.algo_calls.append(dict(params))
        return {"code": "0", "data": [{"algoId": "NEW1"}]}

    def privatePostTradeCancelAlgos(self, arr):
        self.cancel_calls.append(arr)
        return {"code": "0"}

    def price_to_precision(self, sym, px):
        return round(float(px), 6)

    def market_id(self, sym):
        return sym.split("/")[0] + "-USDT-SWAP"


def pos(sym, contracts=10.0, entry=0.25, side="long", lev=15):
    return {"symbol": f"{sym}/USDT:USDT", "contracts": contracts, "side": side,
            "entryPrice": entry, "notional": contracts * entry, "leverage": lev,
            "contractSize": 1, "unrealizedPnl": 0,
            "info": {"instId": f"{sym}-USDT-SWAP", "margin": "10"}}


def algo(sym, algo_id, sl="0.2"):
    return {"instId": f"{sym}-USDT-SWAP", "algoId": algo_id, "state": "live",
            "side": "sell", "slTriggerPx": sl, "sz": "10"}


def run_stops(positions, pending, **kw):
    ex = StubEx(positions, pending)
    buf, old = io.StringIO(), sys.stdout
    sys.stdout = buf
    try:
        fixed, cancelled = ex_mod.ensure_stop_orders({"exchange": ex}, **kw)
    finally:
        sys.stdout = old
    return ex, fixed, cancelled, buf.getvalue()


def inst_of_algo_calls(ex):
    return sorted(c.get("instId") for c in ex.algo_calls)


def inst_of_cancels(ex):
    return sorted(a[0]["instId"] for a in ex.cancel_calls)


# ── 1. ensure_stop_orders(skip=) ───────────────────────────────────────────
# ONT: 대표님 수동 포지션(손절 algo 없음) / BNB: 프로그램 포지션 손절 누락 / XRP: 포지션 없는 고아 algo
P = [pos("ONT", 400, 0.25, lev=15), pos("BNB", 4, 500.0, lev=3)]
A = [algo("XRP", "X1")]
ex, fixed, cancelled, log = run_stops(P, A, skip={"ONT"})
check("skip: 수동 종목(ONT)은 손절 누락이어도 재등록하지 않는다",
      "ONT-USDT-SWAP" not in inst_of_algo_calls(ex) and all(s != "ONT" for s, _ in fixed), (ex.algo_calls, fixed))
check("skip: 나머지 종목(BNB) 손절 누락은 종전대로 재등록", inst_of_algo_calls(ex) == ["BNB-USDT-SWAP"]
      and [s for s, _ in fixed] == ["BNB"], ex.algo_calls)
check("skip: 나머지 종목 고아 algo(XRP)는 종전대로 취소", inst_of_cancels(ex) == ["XRP-USDT-SWAP"], ex.cancel_calls)
check("skip: 수동 종목은 로그 한 줄로 남긴다", "ONT 수동 포지션 — 손절 재등록 안 함" in log, log)

# 대표님 algo 가 이미 걸려 있으면 로그도 없이 그대로(덮어쓰지도, 취소하지도 않는다)
ex, fixed, cancelled, log = run_stops([pos("ONT", 400, 0.25)], [algo("ONT", "U1")], skip={"ONT"})
check("skip: 수동 종목 algo 가 있으면 무동작(등록·취소 0, 로그 없음)",
      not ex.algo_calls and not ex.cancel_calls and "ONT" not in log, (ex.algo_calls, ex.cancel_calls, log))

# 대표님이 포지션을 닫은 뒤 남은 algo — 종전이면 고아로 취소되지만 수동 종목은 그대로 둔다
ex0, _, c0, _ = run_stops([], [algo("ONT", "U1")])
ex1, _, c1, _ = run_stops([], [algo("ONT", "U1")], skip={"ONT"})
check("대조: skip 없으면 포지션 없는 ONT algo 는 고아로 취소(종전 동작)", inst_of_cancels(ex0) == ["ONT-USDT-SWAP"], c0)
check("skip: 수동 종목의 남은 algo 는 고아 취소하지 않는다", not ex1.cancel_calls and not c1, ex1.cancel_calls)

# replace(재정렬) 경로 — 수동 종목이 replace 에 들어와도 취소하지 않는다
ex, fixed, cancelled, _ = run_stops([pos("ONT", 400, 0.25)], [algo("ONT", "U1")],
                                    stop_map={"ONT": {"stop": 0.1}}, replace={"ONT"}, skip={"ONT"})
check("skip: replace 에 수동 종목이 있어도 algo 취소·재등록 없음", not ex.cancel_calls and not ex.algo_calls,
      (ex.cancel_calls, ex.algo_calls))
ex, fixed, cancelled, _ = run_stops([pos("ONT", 400, 0.25)], [algo("ONT", "U1")],
                                    stop_map={"ONT": {"stop": 0.1}}, replace={"ONT"})
check("대조: skip 없으면 replace 는 종전대로 취소 후 재등록", inst_of_cancels(ex) == ["ONT-USDT-SWAP"]
      and inst_of_algo_calls(ex) == ["ONT-USDT-SWAP"], (ex.cancel_calls, ex.algo_calls))

# 대소문자·공백 정규화
ex, _, _, _ = run_stops([pos("ONT", 400, 0.25)], [], skip={" ont "})
check("skip: 심볼 대소문자·공백 정규화", not ex.algo_calls, ex.algo_calls)

# ── 2. skip 없음·빈 집합 = 종전과 같다 ─────────────────────────────────────
P2 = [pos("ONT", 400, 0.25), pos("BNB", 4, 500.0), pos("LTC", 3, 60.0)]
A2 = [algo("LTC", "L1"), algo("ETH", "E1"), algo("ETH", "E1")]
runs = [run_stops(P2, A2), run_stops(P2, A2, skip=None), run_stops(P2, A2, skip=set()), run_stops(P2, A2, skip=[])]
ref = (runs[0][0].algo_calls, runs[0][0].cancel_calls, runs[0][1], runs[0][2])
check("skip 생략 = None = 빈 집합 = 빈 목록 — 등록·취소 호출과 반환값이 완전히 같다",
      all((r[0].algo_calls, r[0].cancel_calls, r[1], r[2]) == ref for r in runs), [r[1:3] for r in runs])
check("기준 실행: ONT·BNB 재등록, LTC 무동작, ETH 고아 1건 취소(중복 algoId 1건 처리)",
      inst_of_algo_calls(runs[0][0]) == ["BNB-USDT-SWAP", "ONT-USDT-SWAP"]
      and inst_of_cancels(runs[0][0]) == ["ETH-USDT-SWAP"], (runs[0][0].algo_calls, runs[0][0].cancel_calls))


# ── 3. manual_symbols ──────────────────────────────────────────────────────
def ms_with(content):
    d = tempfile.mkdtemp()
    p = os.path.join(d, "universe.json")
    try:
        if content is not None:
            with open(p, "w", encoding="utf-8") as f:
                f.write(content)
        return pe.manual_symbols(p)
    finally:
        shutil.rmtree(d, ignore_errors=True)


check("manual_symbols: 파일 없음 → 빈 집합", ms_with(None) == set())
check("manual_symbols: 키 없음 → 빈 집합", ms_with(json.dumps({"program_exclude": ["BTC"]})) == set())
check("manual_symbols: 빈 목록·null → 빈 집합", ms_with('{"manual_positions": []}') == set()
      and ms_with('{"manual_positions": null}') == set())
check("manual_symbols: 깨진 JSON → 빈 집합", ms_with("{not json") == set())
check("manual_symbols: 대문자·공백 정규화, 빈 문자열 제외",
      ms_with(json.dumps({"manual_positions": ["ont", " Ada ", ""]})) == {"ONT", "ADA"})
check("manual_symbols 는 program_exclude 를 읽지 않는다(별개 목록)",
      ms_with(json.dumps({"program_exclude": ["BTC"], "manual_positions": ["ONT"]})) == {"ONT"})


# ── 4. reconcile_live_flag ─────────────────────────────────────────────────
class _Conn(dict):
    pass


def recon(rows, okx, skip):
    keep = ex_mod.get_okx_positions
    ex_mod.get_okx_positions = lambda conn: okx
    buf, old = io.StringIO(), sys.stdout
    sys.stdout = buf
    try:
        return pe.reconcile_live_flag([dict(r) for r in rows], _Conn(), skip=skip)
    finally:
        sys.stdout = old
        ex_mod.get_okx_positions = keep


ROWS = [dict(symbol="ONT", direction="long", live_mode=False), dict(symbol="BNB", direction="long", live_mode=False)]
OKX = [dict(symbol="ONT", direction="long"), dict(symbol="BNB", direction="long")]
out = recon(ROWS, OKX, {"ONT"})
check("reconcile_live_flag: 수동 종목 장부 행은 실거래로 승격하지 않는다",
      [r["live_mode"] for r in out] == [False, True], out)
out0 = recon(ROWS, OKX, set())
check("reconcile_live_flag: skip 이 비면 종전대로 둘 다 승격", [r["live_mode"] for r in out0] == [True, True], out0)
check("reconcile_live_flag: skip 기본값은 manual_symbols()(호출부 문자열 불변)",
      "skip = manual_symbols() if skip is None else" in io.open("paper_executor.py", encoding="utf-8").read()
      .split("def reconcile_live_flag(", 1)[1].split("\ndef ", 1)[0])

# ── 5. 배선(소스) ───────────────────────────────────────────────────────────
SRC = io.open("paper_executor.py", encoding="utf-8").read()
_run = SRC.split("def run(", 1)[1]
check("손절 점검(매 틱)은 skip=manual_symbols() 를 넘긴다",
      "ensure_stop_orders(live_conn, stop_map=stop_map,\n" in _run
      and "skip=manual_symbols())" in _run.split("ensure_stop_orders(live_conn, stop_map=stop_map,", 1)[1][:200])
_re = _run.split("ok_r = ex_mod.ensure_stop_orders(", 1)[1][:300]
check("체결가 재정렬 호출도 skip=manual 을 넘긴다", "live_conn, skip=manual," in _re, _re)
check("ensure_stop_orders 호출은 두 곳 모두 skip 을 넘긴다", _run.count("ensure_stop_orders(") == 2
      and _run.count("skip=manual") == 2, _run.count("ensure_stop_orders("))
i_loop = _run.find('for s in sig.get("signals", []):')
_loop = _run[i_loop:]
i_guard = _loop.find('if str(s["symbol"]).strip().upper() in manual:')
check("수동 종목 집합은 진입 루프 직전에 실행당 1회 읽는다", 0 < _run.find("manual = manual_symbols()") < i_loop)
_order = [_loop.find(k) for k in ("rows = rows_of(", "_is_dup_entry(", "ai_judge.judge(", "size_for_pos")]
check("진입 판정이 루프 맨 앞 — 봉 조회·중복 방어·AI 판단·사이징보다 앞(페이퍼 행도 안 만든다)",
      0 < i_guard and all(i_guard < k for k in _order) and -1 not in _order, (i_guard, _order))
check("판정 뒤 continue + AI 판단 행에 사유 기록",
      "continue" in _loop[i_guard:_loop.find("rows = rows_of(")]
      and '_ai_action(s.get("_ai_rec"), "manual_position")' in _loop[i_guard:_loop.find("rows = rows_of(")])
check("AI 트레이더 예외 없음 — 수동 종목 판정은 ai_trader_patterns 를 보지 않는다",
      "ai_pats" not in _loop[i_guard:_loop.find("rows = rows_of(")])

# ── 6. 현재 universe.json ──────────────────────────────────────────────────
U = json.load(io.open("universe.json", encoding="utf-8"))
check("universe.json: ONT·BAT 가 manual_positions 에 있다(2026-11-04 ONT · 2026-11-05 BAT 대표님 수동 매매)",
      U.get("manual_positions") == ["ONT", "BAT"] and pe.manual_symbols() == {"ONT", "BAT"}, U.get("manual_positions"))
check("universe.json: 수동 목록은 program_exclude 와 별개(BTC 는 AI 전용, ONT 는 대표님 수동)",
      "ONT" not in (U.get("program_exclude") or []) and "BTC" not in (U.get("manual_positions") or []))
check("universe.json: 설명 노트가 있다", "건드리지 마" in str(U.get("manual_positions_note", "")))


# ── 7. 오프라인 e2e — 체결 엔진 진입 루프 ────────────────────────────────────
def mkrows(n, seed, scale, step=86400000, start_ts=1_600_000_000_000):
    from datetime import datetime, timezone
    random.seed(seed)
    px, ts, rows = 100.0 * scale, start_ts, []
    for _ in range(n):
        nxt = px * (1 + random.gauss(0, 0.004))
        d = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        rows.append(dict(ts=ts, date=d, o=px, h=max(px, nxt) * 1.002, l=min(px, nxt) * 0.998, c=nxt, v=100.0))
        px, ts = nxt, ts + step
    return rows


def _e2e(manual):
    import detlib
    import regime_switch as rs
    repo, tmp = os.getcwd(), tempfile.mkdtemp()
    env_keep = {k: os.environ.pop(k) for k in ("OKX_KEY", "OKX_SECRET", "OKX_PASSPHRASE", "SUPABASE_URL",
                                               "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_KEY", "ANTHROPIC_API_KEY")
                if k in os.environ}
    keep = dict(rg=rs.build_regime_map, af=detlib._auto_fetch)

    def no_fetch(sym, tf):
        raise FileNotFoundError(f"{sym} {tf}")

    try:
        shutil.copy("registry.json", os.path.join(tmp, "registry.json"))
        u = json.load(io.open("universe.json", encoding="utf-8"))
        if manual is None:
            u.pop("manual_positions", None)
        else:
            u["manual_positions"] = manual
        os.chdir(tmp)
        os.makedirs("data", exist_ok=True)
        json.dump(u, open("universe.json", "w", encoding="utf-8"), ensure_ascii=False)
        rr = {}
        for sym, seed, scale in (("ONT", 33, 0.0025), ("ETH", 22, 27.0)):
            rr[sym] = mkrows(120, seed, scale)
            with open(f"data/{sym.lower()}_1d.csv", "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["timestamp", "open", "high", "low", "close", "volume"])
                for x in rr[sym]:
                    w.writerow([x["ts"], x["o"], x["h"], x["l"], x["c"], x["v"]])
        si = 110
        rs.build_regime_map = lambda *a, **k: {r["date"]: "bull_btc" for r in rr["ETH"]}
        detlib._auto_fetch = no_fetch
        json.dump({"signals": [dict(symbol=s, pattern="engulfing", direction="long", tf="1d",
                                    date=rr[s][si]["date"], ts=rr[s][si]["ts"], regime="bull_btc")
                               for s in ("ONT", "ETH")]}, open("signals_today.json", "w"))
        buf, old = io.StringIO(), sys.stdout
        sys.stdout = buf
        try:
            pe.run()
        finally:
            sys.stdout = old
        return json.load(open("paper_positions.json")), buf.getvalue()
    finally:
        rs.build_regime_map, detlib._auto_fetch = keep["rg"], keep["af"]
        os.environ.update(env_keep)
        os.chdir(repo)
        shutil.rmtree(tmp, ignore_errors=True)


pos_, log_ = _e2e(["ONT"])
check("e2e: ONT·ETH engulfing 신호 중 ETH 만 진입(페이퍼 행도 ONT 없음)",
      sorted(p["symbol"] for p in pos_) == ["ETH"], pos_)
check("e2e: ONT 는 '대표님 수동 포지션 종목' 사유로 스킵 로그", "ONT engulfing long — 대표님 수동 포지션 종목" in log_,
      log_[-600:])
check("e2e: 실행 시작에 수동 목록 한 줄", "[수동 포지션] ['ONT']" in log_)
pos0, log0 = _e2e(None)
check("e2e: manual_positions 키가 없으면 둘 다 진입(종전 동작)", sorted(p["symbol"] for p in pos0) == ["ETH", "ONT"], pos0)
check("e2e: 키가 없으면 수동 로그도 없다", "[수동 포지션]" not in log0 and "대표님 수동 포지션 종목" not in log0)

print(f"\n{len(fails)} failed")
sys.exit(1 if fails else 0)
