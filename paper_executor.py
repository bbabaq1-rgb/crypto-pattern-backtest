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
import exchange as ex_mod

CAPITAL = 200.0    # 시뮬레이션 가상자본 $200
POS_PCT = 0.20
POS_USD = CAPITAL * POS_PCT   # $40 (시뮬레이션 포지션당 고정)
STOP = 0.08
MAX_HOLD_D = 30
MAX_HOLD_A = 20
# TF별 방식D 최대보유(향후 하위TF 통과 대비 준비값). 현재 검증 통과 TF는 1d뿐.
MAX_HOLD_BY_TF = {"1d": 30, "4h": 20, "1h": 48, "15m": 120}
FEE = detlib.FEE

# 실거래 포지션 사이징 규칙
MAX_LIVE_POS   = 5     # 동시 최대 실거래 포지션
LIVE_MIN_USD   = 10.0  # 최소 주문 금액 (이하 스킵)
LIVE_FIRST_USD = 20.0  # 첫 주문 고정 금액
LIVE_BAL_PCT   = 0.20  # 두 번째부터 가용잔고 × 20%

# 앙상블 Grade 기반 포지션 사이징 배수
GRADE_SIZE_MULT = {"A": 1.5, "B": 1.0, "C": 0.7, "D": 0.5}

POS_FILE = "paper_positions.json"
TRD_FILE = "paper_trades.json"
OPP = {("engulfing", "long"): "detector_engulfing_short",
       ("engulfing", "short"): "detector_engulfing",
       ("fvg", "long"): "detector_fvg_short",
       ("fvg", "short"): "detector_fvg",
       # 하모닉: 반대 패턴 없음 → None (opp_set = 빈 집합)
       ("gartley",   "long"): None,
       ("bat",       "long"): None,
       ("butterfly", "long"): None,
}
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


def _record_trade(trades, pos, method, ex, exit_date=None):
    j, exit_px, ret, reason = ex
    trades.append(dict(method=method, symbol=pos["symbol"], direction=pos["direction"],
                       pattern=pos["pattern"], regime=pos["regime"],
                       entry_date=pos["entry_date"], entry_price=pos["entry_price"],
                       exit_date=exit_date, exit_price=round(exit_px, 4), ret=round(ret, 5),
                       pnl_usd=round(ret * POS_USD, 2), hold_bars=j - pos["entry_idx"],
                       reason=reason, method_label=method))


# ---- Supabase 동기화 (베스트에포트; 실패/미설정 시 JSON 폴백) ----
def _db():
    try:
        import supabase_client as sc
        return sc.get_client("service") if sc.available() else None
    except Exception:
        return None


def push_trades_db(new_trades):
    cli = _db()
    if not cli or not new_trades:
        return 0
    rows = [{"symbol": t["symbol"], "pattern": t["pattern"], "direction": t["direction"],
             "entry_date": t["entry_date"], "entry_price": t["entry_price"],
             "exit_date": t.get("exit_date"), "exit_price": t["exit_price"],
             "return_pct": round(t["ret"] * 100, 4), "hold_bars": t["hold_bars"],
             "exit_reason": t["reason"], "method": t["method"]} for t in new_trades]
    try:
        cli.table("trades").insert(rows).execute()
        return len(rows)
    except Exception as e:
        print("  [DB] trades insert 실패(로컬 JSON 유지):", str(e)[:60])
        return 0


def push_positions_db(new_positions):
    cli = _db()
    if not cli or not new_positions:
        return 0
    rows = [{"symbol": p["symbol"], "pattern": p["pattern"], "direction": p["direction"],
             "entry_date": p["entry_date"], "entry_price": p["entry_price"],
             "stop_loss": p.get("stop"), "size_usd": p.get("size_usd"),
             "live_mode": bool(p.get("live_mode", False)),
             "status": "open", "method": "AD"} for p in new_positions]
    try:
        cli.table("positions").insert(rows).execute()
        return len(rows)
    except Exception as e:
        print("  [DB] positions insert 실패(로컬 JSON 유지):", str(e)[:60])
        return 0


def run(stamp=None):
    stamp = stamp or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    regmap = rs.build_regime_map()
    positions = _load(POS_FILE, [])
    trades = _load(TRD_FILE, [])
    rows_cache = {}

    def rows_of(sym, tf="1d"):
        key = (sym, tf)
        if key not in rows_cache:
            try:
                rows_cache[key] = detlib.load_ohlcv(sym, tf)
            except (FileNotFoundError, RuntimeError):
                rows_cache[key] = None  # OKX 미상장 등 데이터 없음
        return rows_cache[key]

    t0 = len(trades)                  # 이번 실행에서 새로 체결되는 거래 추적
    new_positions = []
    # 1) 오픈 포지션 청산 모니터링
    still_open = []
    for pos in positions:
        rows = rows_of(pos["symbol"], pos.get("tf", "1d"))
        if rows is None:          # 데이터 미수집 종목(OKX 미상장 등) -> 포지션 유지
            still_open.append(pos); continue
        ei = _date_idx(rows, pos["entry_date"])
        if ei is None:
            still_open.append(pos); continue
        pos["entry_idx"] = ei
        oppname = OPP.get((pos["pattern"], pos["direction"]))
        opp_set = set(importlib.import_module(oppname).detect(rows)) if oppname else set()
        if not pos.get("d_closed"):
            ex = eval_D(rows, ei, pos["direction"], opp_set, regmap)
            if ex:
                _record_trade(trades, pos, "D", ex, rows[ex[0]]["date"]); pos["d_closed"] = True
        if not pos.get("a_closed"):
            ex = eval_A(rows, ei, pos["direction"])
            if ex:
                _record_trade(trades, pos, "A", ex, rows[ex[0]]["date"]); pos["a_closed"] = True
        if not (pos.get("d_closed") and pos.get("a_closed")):
            still_open.append(pos)

    # 2) 신규 진입 (signals_today.json)
    live_conn = ex_mod.connect_live() if ex_mod.is_live() else None
    if live_conn:
        print(f"[live] OKX 선물 실거래 모드 | USDT free={live_conn['usdt_free']:.2f}")

    # 실거래 포지션 현황 — 사이징·max 체크용
    live_open_count   = sum(1 for p in still_open if p.get("live_mode"))
    live_filled_count = live_open_count + sum(1 for t in trades if t.get("live_mode"))

    sig = _load("signals_today.json", {"signals": []})
    openkeys  = {(p["symbol"], p["pattern"], p["direction"], p["entry_date"]) for p in still_open}
    closedkeys = {(t["symbol"], t["pattern"], t["direction"], t["entry_date"]) for t in trades}
    new = 0
    live_orders = 0
    for s in sig.get("signals", []):
        rows = rows_of(s["symbol"], s.get("tf", "1d"))
        if rows is None:
            continue
        ei = _date_idx(rows, s["date"])
        if ei is None:
            continue
        key = (s["symbol"], s["pattern"], s["direction"], s["date"])
        if key in openkeys or key in closedkeys:
            continue

        entry   = rows[ei]["c"]
        stop_px = entry * (1 - STOP) if s["direction"] == "long" else entry * (1 + STOP)

        live_info    = {}
        # 앙상블 Grade 기반 사이징: A×1.5 / B×1.0 / C×0.7 / D×0.5
        grade        = s.get("ensemble_grade", "B")
        grade_mult   = GRADE_SIZE_MULT.get(grade, 1.0)
        size_for_pos = round(POS_USD * grade_mult, 2)
        # tf_confirmed=False → 추가로 ×0.5
        tf_ok        = s.get("tf_confirmed", True)
        if not tf_ok:
            size_for_pos = round(size_for_pos * 0.5, 2)
        if grade != "B" or not tf_ok:
            tf_tag = " [4h비확증×0.5]" if not tf_ok else ""
            print(f"  [사이징] {s['symbol']} {grade}등급×{grade_mult}{tf_tag} → ${size_for_pos:.1f}")

        if live_conn:
            # 동시 최대 포지션 체크
            if live_open_count >= MAX_LIVE_POS:
                print(f"  [live] 최대 포지션({MAX_LIVE_POS}개) 도달 — {s['symbol']} 스킵")
                continue

            # 포지션 사이징 (첫 주문 $20 고정 / 이후 잔고 20%)
            if live_filled_count == 0:
                live_size_usd = LIVE_FIRST_USD
            else:
                bal_info      = ex_mod.get_balance(live_conn)
                usdt_free     = bal_info["free"] if isinstance(bal_info, dict) else float(bal_info or 0)
                live_size_usd = round(usdt_free * LIVE_BAL_PCT, 2)

            # 최소 주문 금액 체크
            if live_size_usd < LIVE_MIN_USD:
                print(f"  [live] 최소주문금액 미만(${live_size_usd:.1f}) — {s['symbol']} 스킵")
                continue

            result, reason = ex_mod.place_swap_entry(
                live_conn, s["symbol"], s["direction"], stop_px,
                size_usd=live_size_usd,
            )
            if result is None:
                print(f"  [live] {s['symbol']} {s['direction']} 주문 실패: {reason}")
                # 주문 실패 시 size_for_pos = POS_USD (페이퍼 기록만 유지)
            else:
                live_info    = {"live_order": result, "live_mode": True}
                size_for_pos = live_size_usd
                live_open_count   += 1
                live_filled_count += 1
                live_orders       += 1
                print(f"  [live] {s['symbol']} {s['direction']} 진입 OK | "
                      f"size=${live_size_usd:.0f} entry={result['entry_price']:.4f} "
                      f"sl={result['stop_price']:.4f}")

        rank      = s.get("priority_rank")
        cnt       = s.get("pattern_count", 1)
        fired     = s.get("patterns_fired", [s.get("pattern")])
        score     = s.get("ensemble_score")
        grade_out = s.get("ensemble_grade", "B")
        GRADE_ICON = {"A": "🔥", "B": "⭐", "C": "🔵", "D": "⚪"}
        rank_str  = f"#{rank}" if rank else ""
        score_str = f" [{score:.1f}]" if score is not None else ""
        multi_str = " [멀티]" if cnt > 1 else ""
        icon_str  = GRADE_ICON.get(grade_out, "")
        print(f"  [paper] 신규: {rank_str} {icon_str}{grade_out}{score_str} "
              f"{s['symbol']} {fired} {s['direction']}{multi_str} ${size_for_pos:.0f}")
        p = dict(symbol=s["symbol"], direction=s["direction"], pattern=s["pattern"],
                 regime=s.get("regime"), tf=s.get("tf", "1d"),
                 entry_date=s["date"], entry_idx=ei,
                 entry_price=round(entry, 4), stop=round(stop_px, 4),
                 size_usd=size_for_pos, d_closed=False, a_closed=False, **live_info)
        still_open.append(p); new_positions.append(p); new += 1

    # JSON은 항상 저장(로컬 폴백/원천)
    _save(POS_FILE, still_open)
    _save(TRD_FILE, trades)
    # Supabase 동기화(가능 시): 이번 실행 신규 체결/신규 포지션만 INSERT
    new_trades = trades[t0:]
    dbt = push_trades_db(new_trades)
    dbp = push_positions_db(new_positions)
    dbmsg = f" | DB동기화 trades+{dbt}/positions+{dbp}" if _db() else " | DB미설정(JSON만)"
    live_msg = f" | 실거래주문 {live_orders}건" if live_conn else ""
    print(f"[paper] 신규진입 {new}건 | 오픈 {len(still_open)}건 | 누적 체결 {len(trades)}건{live_msg}{dbmsg}")
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
    universe = _load("universe.json", {}).get("trading_universe") or list(detlib.SYMBOLS)
    added = 0
    for sym in universe:
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


def migrate():
    """기존 JSON(paper_trades/positions)을 Supabase로 1회 마이그레이션."""
    if not _db():
        print("[migrate] DB 미설정 - 스킵(JSON 유지)")
        return
    n = push_trades_db(_load(TRD_FILE, []))
    p = push_positions_db(_load(POS_FILE, []))
    print(f"[migrate] Supabase 이관: trades {n}건 / positions {p}건")


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "selftest":
        selftest()
    elif arg == "seed":
        seed()
    elif arg == "migrate":
        migrate()
    else:
        run()
