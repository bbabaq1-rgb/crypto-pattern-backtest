"""
paper_executor.py — 로컬 모의 체결 엔진 (실주문 없음).

signals_today.json -> 진입 기록(paper_positions.json).
매 실행마다 오픈 포지션 청산 모니터링:
  방식D: 손절 -8% / 반대패턴 신호 / 레짐 전환 / 최대30봉 시가청산.
  방식A: +10%/-10% / 최대20봉 종가청산 (병행 비교).
청산 시 paper_trades.json 에 기록(방식별 1행).

자본 $2,000, 포지션당 10%($200), 레버리지 1x. 체결가=시가/종가 가정(슬리피지 없음).
"""
import sys
import json
import os
import importlib
from datetime import datetime, timezone

import detlib
import regime_switch as rs

CAPITAL = 2000.0
POS_PCT = 0.10
POS_USD = CAPITAL * POS_PCT
STOP = 0.08
MAX_HOLD_D = 30
MAX_HOLD_A = 20
FEE = detlib.FEE

POS_FILE = "paper_positions.json"
TRD_FILE = "paper_trades.json"
OPP = {("engulfing", "long"): "detector_engulfing_short",
       ("engulfing", "short"): "detector_engulfing",
       ("fvg", "long"): "detector_fvg_short",
       ("fvg", "short"): "detector_fvg"}
DETMOD = {("engulfing", "long"): "detector_engulfing",
          ("engulfing", "short"): "detector_engulfing_short",
          ("fvg", "long"): "detector_fvg",
          ("fvg", "short"): "detector_fvg"}


def _load(fn, default):
    return json.load(open(fn, encoding="utf-8")) if os.path.exists(fn) else default


def _save(fn, obj):
    json.dump(obj, open(fn, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def eval_D(rows, ei, direction, opp_set, regmap):
    base = rows[ei]["c"]; entry_reg = regmap.get(rows[ei]["date"]); last = len(rows) - 1
    end = min(ei + MAX_HOLD_D, last)
    for j in range(ei + 1, end + 1):
        if direction == "long" and rows[j]["l"] <= base * (1 - STOP):
            return j, base * (1 - STOP), -STOP - FEE, "stop"
        if direction == "short" and rows[j]["h"] >= base * (1 + STOP):
            return j, base * (1 + STOP), -STOP - FEE, "stop"
        regsw = regmap.get(rows[j]["date"]) not in (None, entry_reg)
        if j in opp_set or regsw:
            c = rows[j]["c"]; r = (c - base) / base if direction == "long" else (base - c) / base
            return j, c, r - FEE, ("opp_signal" if j in opp_set else "regime_switch")
    if last >= ei + MAX_HOLD_D:
        px = rows[end]["o"]; r = (px - base) / base if direction == "long" else (base - px) / base
        return end, px, r - FEE, "maxhold"
    return None


def eval_A(rows, ei, direction):
    base = rows[ei]["c"]; up = base * 1.10; dn = base * 0.90; last = len(rows) - 1
    end = min(ei + MAX_HOLD_A, last)
    for j in range(ei + 1, end + 1):
        c = rows[j]["c"]
        if direction == "long":
            if c >= up: return j, c, c / base - 1 - FEE, "tp"
            if c <= dn: return j, c, c / base - 1 - FEE, "sl"
        else:
            if c <= dn: return j, c, (base - c) / base - FEE, "tp"
            if c >= up: return j, c, (base - c) / base - FEE, "sl"
    if last >= ei + MAX_HOLD_A:
        c = rows[end]["c"]; r = c / base - 1
        return end, c, (r - FEE if direction == "long" else -r - FEE), "timestop"
    return None


def _date_idx(rows, date):
    for i, r in enumerate(rows):
        if r["date"] == date:
            return i
    return None


def _record_trade(trades, pos, method, ex):
    j, exit_px, ret, reason = ex
    trades.append(dict(method=method, symbol=pos["symbol"], direction=pos["direction"],
                       pattern=pos["pattern"], regime=pos["regime"],
                       entry_date=pos["entry_date"], entry_price=pos["entry_price"],
                       exit_price=round(exit_px, 4), ret=round(ret, 5),
                       pnl_usd=round(ret * POS_USD, 2), hold_bars=j - pos["entry_idx"],
                       reason=reason, method_label=method))


def run(stamp=None):
    stamp = stamp or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    regmap = rs.build_regime_map()
    positions = _load(POS_FILE, [])
    trades = _load(TRD_FILE, [])
    rows_cache = {}

    def rows_of(sym):
        if sym not in rows_cache:
            rows_cache[sym] = detlib.load_ohlcv(sym, "1d")
        return rows_cache[sym]

    # 1) 오픈 포지션 청산 모니터링
    still_open = []
    for pos in positions:
        rows = rows_of(pos["symbol"])
        ei = _date_idx(rows, pos["entry_date"])
        if ei is None:
            still_open.append(pos); continue
        pos["entry_idx"] = ei
        oppmod = importlib.import_module(OPP[(pos["pattern"], pos["direction"])])
        opp_set = set(oppmod.detect(rows))
        if not pos.get("d_closed"):
            ex = eval_D(rows, ei, pos["direction"], opp_set, regmap)
            if ex:
                _record_trade(trades, pos, "D", ex); pos["d_closed"] = True
        if not pos.get("a_closed"):
            ex = eval_A(rows, ei, pos["direction"])
            if ex:
                _record_trade(trades, pos, "A", ex); pos["a_closed"] = True
        if not (pos.get("d_closed") and pos.get("a_closed")):
            still_open.append(pos)

    # 2) 신규 진입 (signals_today.json)
    sig = _load("signals_today.json", {"signals": []})
    openkeys = {(p["symbol"], p["pattern"], p["direction"], p["entry_date"]) for p in still_open}
    closedkeys = {(t["symbol"], t["pattern"], t["direction"], t["entry_date"]) for t in trades}
    new = 0
    for s in sig.get("signals", []):
        rows = rows_of(s["symbol"])
        ei = _date_idx(rows, s["date"])
        if ei is None:
            continue
        key = (s["symbol"], s["pattern"], s["direction"], s["date"])
        if key in openkeys or key in closedkeys:
            continue
        entry = rows[ei]["c"]
        stop_px = entry * (1 - STOP) if s["direction"] == "long" else entry * (1 + STOP)
        still_open.append(dict(symbol=s["symbol"], direction=s["direction"], pattern=s["pattern"],
                               regime=s.get("regime"), entry_date=s["date"], entry_idx=ei,
                               entry_price=round(entry, 4), stop=round(stop_px, 4),
                               size_usd=POS_USD, d_closed=False, a_closed=False))
        new += 1

    _save(POS_FILE, still_open)
    _save(TRD_FILE, trades)
    print(f"[paper] 신규진입 {new}건 | 오픈 {len(still_open)}건 | 누적 체결 {len(trades)}건")
    return dict(new=new, open=len(still_open), trades=len(trades))


def selftest():
    """과거 engulfing 롱 신호 1건을 끝까지(진입->청산) 돌려 엔진 검증(파일 미기록)."""
    regmap = rs.build_regime_map()
    eng = importlib.import_module("detector_engulfing")
    opp = importlib.import_module("detector_engulfing_short")
    rows = eng.load_ohlcv("BTC", "1d")
    opp_set = set(opp.detect(rows))
    for ei in eng.detect(rows):
        if rows[ei]["date"] < "2023-06-01":           # 청산될 만큼 과거
            d = eval_D(rows, ei, "long", opp_set, regmap)
            a = eval_A(rows, ei, "long")
            print(f"[selftest] BTC engulfing long 진입 {rows[ei]['date']} @ {rows[ei]['c']:.1f}")
            print(f"  방식D 청산: bar+{d[0]-ei}, px {d[1]:.1f}, ret {d[2]*100:+.2f}%, 사유 {d[3]}")
            print(f"  방식A 청산: bar+{a[0]-ei}, px {a[1]:.1f}, ret {a[2]*100:+.2f}%, 사유 {a[3]}")
            return


def seed(days=60):
    """최근 days봉의 라우팅-방향 engulfing/fvg 신호로 페이퍼 포트폴리오 부트스트랩.
    (오늘 신호가 없을 때 실데이터로 전체 사이클을 시연하기 위한 1회 킥스타트.)"""
    regmap = rs.build_regime_map()
    routing = _load("direction_switch.json", {"routing": {}})["routing"]
    positions = _load(POS_FILE, [])
    keys = {(p["symbol"], p["pattern"], p["direction"], p["entry_date"]) for p in positions}
    added = 0
    for sym in detlib.SYMBOLS:
        rows = detlib.load_ohlcv(sym, "1d")
        last = len(rows) - 1
        for pat in ("engulfing", "fvg"):
            for d in ("long", "short"):
                mod = importlib.import_module(DETMOD[(pat, d)])
                for ei in mod.detect(rows):
                    if ei < last - days:
                        continue
                    rg = regmap.get(rows[ei]["date"])
                    if not rg or routing.get(rg, {}).get(pat) != d:
                        continue
                    key = (sym, pat, d, rows[ei]["date"])
                    if key in keys:
                        continue
                    entry = rows[ei]["c"]
                    stop_px = entry * (1 - STOP) if d == "long" else entry * (1 + STOP)
                    positions.append(dict(symbol=sym, direction=d, pattern=pat, regime=rg,
                                          entry_date=rows[ei]["date"], entry_idx=ei,
                                          entry_price=round(entry, 4), stop=round(stop_px, 4),
                                          size_usd=POS_USD, d_closed=False, a_closed=False))
                    keys.add(key); added += 1
    _save(POS_FILE, positions)
    print(f"[seed] 최근 {days}봉에서 {added}건 진입 시드 -> 모니터링 실행")
    run()


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "selftest":
        selftest()
    elif arg == "seed":
        seed()
    else:
        run()
