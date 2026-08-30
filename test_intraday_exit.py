"""
하위 TF ATR 배리어 청산 경로 검증 (실주문 없음, 스텁 거래소).

두 가지를 동시에 증명한다:
  1) 새 경로(eval_I / OCO 브래킷 / 기록 손절가 재등록)가 검증 프레임과 같게 동작
  2) 기존 1d/4h/1w 패턴의 청산 동작이 이 변경으로 바뀌지 않음(회귀 방지)

실행: python test_intraday_exit.py
"""
import random
import sys

import detlib
import intraday_lab as ilab
import paper_executor as pe
import exchange as ex_mod

fails = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f" — {detail}"))
    if not cond:
        fails.append(name)


def mkrows(n=300, seed=1, start_ts=1600000000000, step_ms=3600000):
    """랜덤워크 OHLC (ts 포함 — detlib.load_ohlcv 와 같은 스키마)."""
    random.seed(seed)
    rows, px, ts = [], 100.0, start_ts
    from datetime import datetime, timezone
    for _ in range(n):
        nxt = px * (1 + random.gauss(0, 0.006))
        hi = max(px, nxt) * (1 + abs(random.gauss(0, 0.002)))
        lo = min(px, nxt) * (1 - abs(random.gauss(0, 0.002)))
        d = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        rows.append(dict(ts=ts, date=d, o=px, h=hi, l=lo, c=nxt, v=100.0))
        px, ts = nxt, ts + step_ms
    return rows


# ── 1. eval_I ≡ intraday_lab.outcome_atr (검증 프레임과 동일 규칙인가) ─────────
rows = mkrows(400, seed=7)
atr = ilab.atr_series(rows, 14)
H = ilab.HORIZON["1h"]
mismatch, compared, reached = 0, 0, 0
for direction in ("long", "short"):
    for i in range(20, 380):
        a = atr[i]
        if not a:
            continue
        base = rows[i]["c"]
        dist = ilab.K_ATR * a
        if direction == "long":
            sl, tp = base - dist, base + dist
        else:
            sl, tp = base + dist, base - dist
        want_label, want_ret = ilab.outcome_atr(rows, i, direction, atr, H)
        got = pe.eval_I(rows, i, direction, sl, tp, H)
        if want_ret is None or got is None:
            continue
        compared += 1
        if want_label in ("real", "fake"):
            reached += 1
        if abs(got[2] - want_ret) > 1e-12:
            mismatch += 1
check("eval_I 수익률이 검증 라벨(outcome_atr)과 완전 일치",
      compared > 500 and mismatch == 0, f"비교 {compared}건 중 불일치 {mismatch}건")
check("표본에서 배리어가 실제로 도달됨(시간초과 편중 아님)",
      reached / max(1, compared) > 0.5, f"도달률 {reached/max(1,compared):.0%}")

# ── 2. eval_I 세부 규칙: 손절 우선 / 익절 / 시간청산 ─────────────────────────
flat = [dict(ts=i, date="2026-01-01", o=100, h=100.5, l=99.5, c=100, v=1)
        for i in range(30)]
both = list(flat)
both[3] = dict(both[3], h=120.0, l=80.0)      # 같은 봉에서 익절·손절 동시 터치
r = pe.eval_I(both, 0, "long", 90.0, 110.0, 12)
check("같은 봉 양방향 터치 시 손절 우선(보수적)", r and r[3] == "atr_stop", r)

tponly = list(flat)
tponly[5] = dict(tponly[5], h=120.0)
r = pe.eval_I(tponly, 0, "long", 90.0, 110.0, 12)
check("익절 배리어 도달 시 atr_target", r and r[3] == "atr_target" and r[0] == 5, r)
check("익절 수익률 = 배리어 기준 - 수수료",
      r and abs(r[2] - ((110.0 / 100.0 - 1) - pe.FEE)) < 1e-12, r)

r = pe.eval_I(flat, 0, "long", 90.0, 110.0, 12)
check("미도달 시 horizon 봉에서 시간청산", r and r[3] == "atr_timestop" and r[0] == 12, r)

sh = list(flat)
sh[4] = dict(sh[4], l=80.0)
r = pe.eval_I(sh, 0, "short", 110.0, 90.0, 12)
check("숏 익절(하락 배리어) 판정", r and r[3] == "atr_target" and r[2] > 0, r)

short_end = flat[:6]                            # horizon 이전에 데이터 끝
check("데이터가 horizon 에 못 미치면 청산 없음(None)",
      pe.eval_I(short_end, 0, "long", 90.0, 110.0, 12) is None)
check("배리어 미기록(stop/target None)이면 청산 안 함",
      pe.eval_I(flat, 0, "long", None, None, 12) is None)

# ── 3. 기존 경로 회귀 방지: eval_D / eval_A 골든값 불변 ──────────────────────
d_rows = mkrows(200, seed=3, step_ms=86400000)
regmap = {r["date"]: "bull_btc" for r in d_rows}
gold_D = pe.eval_D(d_rows, 10, "long", set(), regmap)
gold_A = pe.eval_A(d_rows, 10, "long")
check("eval_D 하드코딩 상수 불변 (±8% / 30봉)",
      pe.STOP == 0.08 and pe.MAX_HOLD_D == 30 and pe.MAX_HOLD_A == 20,
      f"STOP={pe.STOP} D={pe.MAX_HOLD_D} A={pe.MAX_HOLD_A}")
check("eval_D 가 여전히 결과를 반환(경로 유지)", gold_D is not None)
check("eval_A 가 여전히 결과를 반환(경로 유지)", gold_A is not None)
check("eval_D 청산 사유가 기존 어휘만 사용",
      gold_D[3] in ("stop", "opp_signal", "regime_switch", "maxhold"), gold_D)

# 기존 등재 패턴에는 exit_spec 이 없어야 한다 = 청산 경로가 바뀌지 않는다
legacy = ["engulfing", "fvg", "inverted_hammer", "marubozu", "gartley", "bat",
          "butterfly", "three_soldiers_4h", "bat_1h", "butterfly_1h",
          "triple_bottom", "engulfing_short", "fvg_short"]
leaked = [p for p in legacy if p in pe.EXIT_SPECS]
check("기존 등재 패턴은 ATR 경로로 라우팅되지 않음", not leaked, leaked)
check("cascade_fade_long_1h 만 exit_spec 보유",
      set(pe.EXIT_SPECS) == {"cascade_fade_long_1h"}, set(pe.EXIT_SPECS))

spec = pe.EXIT_SPECS["cascade_fade_long_1h"]
check("exit_spec 이 검증치와 일치 (k=1.5 / 12봉 / ATR14)",
      spec["k_atr"] == ilab.K_ATR and spec["horizon_bars"] == ilab.HORIZON["1h"]
      and spec["atr_period"] == 14, spec)

# ── 4. 진입봉 식별: 1h 에서 date 는 봉을 특정 못 하고 ts 는 특정한다 ─────────
h_rows = mkrows(48, seed=5)                     # 1h × 48봉 = 2일
target_i = 30
same_day = [i for i, r in enumerate(h_rows) if r["date"] == h_rows[target_i]["date"]]
first_of_day = same_day[0]
check("1h 은 같은 date 에 여러 봉이 존재(= date 로 봉 특정 불가)",
      len(same_day) > 1 and first_of_day != target_i,
      f"{len(same_day)}봉, 첫봉 {first_of_day}")
check("date 폴백은 그날 첫 봉을 가리킴(구 동작 재현)",
      pe._bar_idx(h_rows, None, h_rows[target_i]["date"]) == first_of_day)
check("ts 로는 진입봉을 정확히 특정",
      pe._bar_idx(h_rows, h_rows[target_i]["ts"], h_rows[target_i]["date"]) == target_i)
check("ts 가 안 맞으면 date 로 폴백(복원분 호환)",
      pe._bar_idx(h_rows, 999, h_rows[target_i]["date"]) == first_of_day)
check("detlib.load_ohlcv 스키마에 ts 포함", "ts" in detlib.resample_rows(
    [dict(ts=1, date="2026-01-01", o=1, h=2, l=1, c=2, v=1)], "1w")[0])

# ── 5. barriers_of: target 유실 시 손절 거리 대칭 복원 ───────────────────────
b = pe.barriers_of(dict(entry_price=100.0, stop=98.5, target=101.5))
check("기록된 target 우선 사용", b == (98.5, 101.5), b)
b = pe.barriers_of(dict(entry_price=100.0, stop=98.5))          # DB 복원 시나리오
check("target 유실 시 손절 거리 대칭 복원(롱)", abs(b[1] - 101.5) < 1e-9, b)
b = pe.barriers_of(dict(entry_price=100.0, stop=101.5))         # 숏
check("target 유실 시 손절 거리 대칭 복원(숏)", abs(b[1] - 98.5) < 1e-9, b)


# ── 6. 거래소 주문 파라미터: OCO 브래킷 / conditional ────────────────────────
class StubEx:
    def __init__(self, positions=None, pending=None):
        self.sent = []
        self.cancelled = []
        self._positions = positions or []
        self._pending = pending or {}
        self.queried = []

    def privatePostTradeOrderAlgo(self, params):
        self.sent.append(params)
        return {"code": "0", "data": [{"algoId": f"A{len(self.sent)}"}]}

    def privateGetTradeOrdersAlgoPending(self, params):
        self.queried.append(params.get("ordType"))
        return {"code": "0", "data": self._pending.get(params.get("ordType"), [])}

    def privatePostTradeCancelAlgos(self, orders):
        self.cancelled += orders
        return {"code": "0"}

    def price_to_precision(self, sym, px):
        return f"{float(px):.4f}"

    def market_id(self, sym):
        return sym.split("/")[0] + "-USDT-SWAP"

    def fetch_positions(self, symbols=None):
        return self._positions


ex = StubEx()
ex_mod.place_stop_algo(ex, "SOL-USDT-SWAP", "sell", 1.0, 90.0)
p0 = ex.sent[-1]
check("tp 없으면 conditional(손절만)", p0["ordType"] == "conditional"
      and "tpTriggerPx" not in p0, p0)
check("손절 주문은 항상 reduceOnly", p0.get("reduceOnly") is True, p0)

ex_mod.place_stop_algo(ex, "SOL-USDT-SWAP", "sell", 1.0, 98.5, tp_px=101.5)
p1 = ex.sent[-1]
check("tp 주면 OCO 브래킷", p1["ordType"] == "oco", p1)
check("OCO 에 손절·익절 트리거 모두 포함",
      p1["slTriggerPx"] == "98.5" and p1["tpTriggerPx"] == "101.5", p1)
check("OCO 도 시장가 체결(-1) · reduceOnly",
      p1["tpOrdPx"] == "-1" and p1["slOrdPx"] == "-1"
      and p1.get("reduceOnly") is True, p1)


# ── 7. ensure_stop_orders: 기록 손절가 우선 / oco 조회 / 기존 폴백 ───────────
def stub_conn(ex):
    return {"exchange": ex}


okx_pos = [{"symbol": "SOL/USDT:USDT", "side": "long", "contracts": 1.0,
            "entryPrice": 100.0, "notional": 100.0, "contractSize": 1.0,
            "info": {"instId": "SOL-USDT-SWAP", "margin": "50"}, "leverage": 2}]

ex = StubEx(positions=okx_pos)
fixed, cancelled = ex_mod.ensure_stop_orders(
    stub_conn(ex), stop_map={"SOL": {"stop": 98.5, "target": 101.5}})
check("기록 손절가로 재등록(±8% 아님)",
      ex.sent and ex.sent[-1]["slTriggerPx"] == "98.5", ex.sent)
check("기록 익절가가 있으면 OCO 로 재등록",
      ex.sent and ex.sent[-1]["ordType"] == "oco", ex.sent)
check("conditional·oco 둘 다 pending 조회", set(ex.queried) == {"conditional", "oco"},
      ex.queried)

ex = StubEx(positions=okx_pos)
ex_mod.ensure_stop_orders(stub_conn(ex))       # stop_map 없음 → 기존 ±8% 폴백
check("stop_map 없으면 기존 ±8% 폴백 유지",
      ex.sent and abs(float(ex.sent[-1]["slTriggerPx"]) - 92.0) < 1e-9, ex.sent)
check("stop_map 없으면 익절 안 붙음(기존 패턴 동작 불변)",
      ex.sent and ex.sent[-1]["ordType"] == "conditional", ex.sent)

# 기존 1d 패턴 포지션은 target=None 으로 넘어가야 한다(익절 주문 금지)
ex = StubEx(positions=okx_pos)
ex_mod.ensure_stop_orders(stub_conn(ex),
                          stop_map={"SOL": {"stop": 92.0, "target": None}})
check("target=None 이면 손절만(기존 패턴 회귀 방지)",
      ex.sent and ex.sent[-1]["ordType"] == "conditional", ex.sent)

# 이미 oco 브래킷이 걸린 포지션에는 중복 등록하지 않는다
live_oco = {"oco": [{"state": "live", "instId": "SOL-USDT-SWAP",
                     "slTriggerPx": "98.5", "algoId": "X1"}]}
ex = StubEx(positions=okx_pos, pending=live_oco)
fixed, cancelled = ex_mod.ensure_stop_orders(
    stub_conn(ex), stop_map={"SOL": {"stop": 98.5, "target": 101.5}})
check("살아있는 OCO 를 손절 있음으로 인식(중복 등록 없음)", not ex.sent, ex.sent)
check("살아있는 OCO 를 고아로 오인해 취소하지 않음", not ex.cancelled, ex.cancelled)

# 포지션 없는 oco 고아는 취소된다
ex = StubEx(positions=[], pending=live_oco)
fixed, cancelled = ex_mod.ensure_stop_orders(stub_conn(ex))
check("포지션 없는 OCO 고아는 취소", cancelled == [("SOL-USDT-SWAP", "X1")], cancelled)


# ── 8. place_swap_entry 가 target 을 OCO 로 전달 ─────────────────────────────
class EntryStub(StubEx):
    def set_margin_mode(self, *a, **k): pass
    def set_leverage(self, *a, **k): pass
    def fetch_ticker(self, sym): return {"last": 100.0}
    def fetch_balance(self): return {"USDT": {"free": 1000.0}}
    def market(self, sym): return {"contractSize": 1.0, "limits": {"amount": {"min": 0}}}
    def amount_to_precision(self, sym, q): return f"{float(q):.4f}"
    def create_market_order(self, sym, side, qty, params=None):
        return {"id": "E1", "filled": qty, "average": 100.0}


ex = EntryStub()
res, why = ex_mod.place_swap_entry(stub_conn(ex), "SOL", "long", 98.5,
                                   size_usd=20.0, target_px=101.5)
check("진입 성공", why == "ok" and res, why)
check("진입 시 OCO 브래킷 등록", ex.sent[-1]["ordType"] == "oco", ex.sent[-1])
check("결과에 target_price 포함", res and res.get("target_price") == 101.5, res)

ex = EntryStub()
res, why = ex_mod.place_swap_entry(stub_conn(ex), "SOL", "long", 92.0, size_usd=20.0)
check("target 없는 기존 진입은 conditional 유지",
      ex.sent[-1]["ordType"] == "conditional", ex.sent[-1])
check("기존 진입 결과의 target_price 는 None", res and res.get("target_price") is None,
      res)


# ── 9. run() 전체 경로 e2e: 두 패턴이 각자 규칙으로 청산되는가 ───────────────
# 임시 디렉터리에서 합성 CSV + signals_today.json 으로 엔진을 2회 돌린다
# (1회차 진입 → 2회차 청산 모니터링). 실주문 없음(OKX 환경변수 미설정).
def _e2e():
    import csv as _csv, json as _json, os, shutil, tempfile
    import regime_switch as rs
    repo = os.getcwd()
    tmp = tempfile.mkdtemp()
    shutil.copy("registry.json", os.path.join(tmp, "registry.json"))
    orig_regime = rs.build_regime_map
    try:
        os.chdir(tmp)
        os.makedirs("data", exist_ok=True)
        for sym, tf, step in (("SOL", "1h", 3600000), ("SOL", "1d", 86400000),
                              ("BTC", "1d", 86400000)):
            rr = mkrows(300, seed=hash((sym, tf)) % 1000, step_ms=step)
            with open(f"data/{sym.lower()}_{tf}.csv", "w", newline="") as f:
                w = _csv.writer(f)
                w.writerow(["timestamp", "open", "high", "low", "close", "volume"])
                for x in rr:
                    w.writerow([x["ts"], x["o"], x["h"], x["l"], x["c"], x["v"]])
        r1h = detlib.load_ohlcv("SOL", "1h")
        r1d = detlib.load_ohlcv("SOL", "1d")
        si = 100
        rs.build_regime_map = lambda *a, **k: {r["date"]: "bull_btc" for r in r1d}
        _json.dump({"signals": [
            dict(symbol="SOL", pattern="cascade_fade_long_1h", direction="long",
                 tf="1h", date=r1h[si]["date"], ts=r1h[si]["ts"], regime="bear"),
            dict(symbol="SOL", pattern="marubozu", direction="long", tf="1d",
                 date=r1d[si]["date"], ts=r1d[si]["ts"], regime="bull_btc"),
        ]}, open("signals_today.json", "w"))
        pe.run()                                   # 진입
        _json.dump({"signals": []}, open("signals_today.json", "w"))
        pe.run()                                   # 청산 모니터링
        return (_json.load(open("paper_trades.json")), r1h[si], si)
    finally:
        rs.build_regime_map = orig_regime
        os.chdir(repo)
        shutil.rmtree(tmp, ignore_errors=True)


trades, entry_bar, si = _e2e()
casc = [t for t in trades if t["pattern"] == "cascade_fade_long_1h"]
maru = [t for t in trades if t["pattern"] == "marubozu"]
check("e2e: ATR 패턴이 atr_* 사유로 청산",
      casc and all(t["reason"].startswith("atr_") for t in casc), casc)
check("e2e: ATR 패턴은 방식D 1행만(방식A 병행 기록 없음)", len(casc) == 1, casc)
check("e2e: ATR 패턴 보유봉 <= horizon(12)",
      casc and casc[0]["hold_bars"] <= 12, casc)
check("e2e: ATR 청산 손익이 ±1.5ATR 규모(±8%/±10% 아님)",
      casc and abs(casc[0]["ret"]) < 0.06, casc)
check("e2e: ATR 진입가는 ts 로 특정한 봉의 종가(그날 첫 봉 아님)",
      casc and abs(casc[0]["entry_price"] - round(entry_bar["c"], 4)) < 1e-9,
      (casc[0]["entry_price"] if casc else None, round(entry_bar["c"], 4)))
check("e2e: 레거시 패턴은 방식A·D 병행 기록 유지", len(maru) == 2, maru)
check("e2e: 레거시 청산 사유·보유봉이 기존 규칙 그대로",
      {t["method"]: (t["reason"], t["hold_bars"]) for t in maru}
      == {"D": ("maxhold", 30), "A": ("timestop", 20)}, maru)

print("\n실패", len(fails), "건" if fails else "— 전체 통과")
sys.exit(1 if fails else 0)
