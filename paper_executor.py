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
MAX_LIVE_POS   = 12    # 동시 최대 실거래 포지션 (2026-07-06 사용자 승인으로 5→12 상향)
LIVE_MIN_USD   = 10.0  # 최소 주문 금액 (이하 스킵)
LIVE_FIRST_USD = 20.0  # 첫 주문 고정 금액
LIVE_BAL_PCT   = 0.20  # 두 번째부터 가용잔고 × 20%

# 계좌 킬스위치: equity가 고점(HWM) 대비 KILL_DD 이상 하락하면 신규 실거래 진입 중지.
# (개별 손절과 별개의 계좌 차원 브레이크. 기존 포지션 청산 모니터링은 계속 동작)
# HWM은 수동 갱신: equity가 이 값을 넘으면 로그로 상향 제안이 출력된다.
EQUITY_HWM = 287.57    # 2026-07-06 실측 고점
KILL_DD    = 0.20      # -20%

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
    # 실거래 판정: 방식D만 실제 OKX 청산과 연결됨(af7b3c4 결정). 방식A(±10%)는
    # 페이퍼 비교 전용이므로 live 포지션이라도 A청산은 '페이퍼'로 기록해야 한다.
    # (과거엔 A청산도 live_mode를 상속 → '실거래' 마커가 붙어 매도로 오인, 포지션은
    #  D가 홀딩 중이라 오픈으로 남아 매매내역↔오픈포지션 불일치 발생: UNI 사례)
    is_live_trade = bool(pos.get("live_mode", False)) and method == "D"
    trades.append(dict(method=method, symbol=pos["symbol"], direction=pos["direction"],
                       pattern=pos["pattern"], regime=pos.get("regime"),
                       entry_date=pos["entry_date"], entry_price=pos["entry_price"],
                       exit_date=exit_date, exit_price=round(exit_px, 4), ret=round(ret, 5),
                       pnl_usd=round(ret * POS_USD, 2), hold_bars=j - pos["entry_idx"],
                       reason=reason, method_label=method,
                       live_mode=is_live_trade))


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
    # '실거래' 마커: DB에 live_mode 컬럼이 없어도(DDL 미적용) 대시보드가
    # exit_reason으로 실거래/페이퍼를 구분할 수 있게 실거래 청산에 마커 부여.
    def _reason(t):
        r = t["reason"]
        return f"{r} ·실거래" if t.get("live_mode") and "실거래" not in str(r) else r
    rows = [{"symbol": t["symbol"], "pattern": t["pattern"], "direction": t["direction"],
             "entry_date": t["entry_date"], "entry_price": t["entry_price"],
             "exit_date": t.get("exit_date"), "exit_price": t["exit_price"],
             "return_pct": round(t["ret"] * 100, 4), "hold_bars": t["hold_bars"],
             "exit_reason": _reason(t), "method": t["method"],
             "pnl_usd": t.get("pnl_usd"),
             "live_mode": bool(t.get("live_mode", False))} for t in new_trades]
    try:
        import supabase_client as sc
        # 재실행 중복 방어: 동일 키(method 포함) 기존 행 제거 후 삽입
        for r in rows:
            (cli.table("trades").delete()
             .eq("symbol", r["symbol"]).eq("pattern", r["pattern"])
             .eq("direction", r["direction"]).eq("entry_date", r["entry_date"])
             .eq("method", r["method"]).execute())
        _, dropped = sc.insert_tolerant(cli, "trades", rows)
        if dropped:
            print("  [DB] trades 스키마 미존재 컬럼 제외:", dropped)
        return len(rows)
    except Exception as e:
        print("  [DB] trades insert 실패(로컬 JSON 유지):", str(e)[:60])
        return 0


def push_positions_db(new_positions):
    cli = _db()
    if not cli or not new_positions:
        return 0
    # method에 LIVE 인코딩: positions 테이블에 live_mode 컬럼이 없어도(DDL 미적용)
    # 러너 복원·대시보드가 실거래 여부를 알 수 있게 한다.
    rows = [{"symbol": p["symbol"], "pattern": p["pattern"], "direction": p["direction"],
             "entry_date": p["entry_date"], "entry_price": p["entry_price"],
             "stop_loss": p.get("stop"), "size_usd": p.get("size_usd"),
             "live_mode": bool(p.get("live_mode", False)),
             "status": "open",
             "method": "AD-LIVE" if p.get("live_mode") else "AD"} for p in new_positions]
    try:
        import supabase_client as sc
        # 재실행 중복 방어: 동일 키 기존 행 제거 후 삽입 (ZIL×5 오염 재발 방지)
        for r in rows:
            (cli.table("positions").delete()
             .eq("symbol", r["symbol"]).eq("pattern", r["pattern"])
             .eq("direction", r["direction"]).eq("entry_date", r["entry_date"]).execute())
        _, dropped = sc.insert_tolerant(cli, "positions", rows)
        if dropped:
            print("  [DB] positions 스키마 미존재 컬럼 제외:", dropped)
        return len(rows)
    except Exception as e:
        print("  [DB] positions insert 실패(로컬 JSON 유지):", str(e)[:60])
        return 0


def mark_closed_db(closed_positions):
    """완전 청산(A·D 모두)된 포지션의 DB status를 'closed'로 갱신."""
    cli = _db()
    if not cli or not closed_positions:
        return 0
    n = 0
    for p in closed_positions:
        try:
            (cli.table("positions").update({"status": "closed"})
             .eq("symbol", p["symbol"]).eq("pattern", p["pattern"])
             .eq("direction", p["direction"]).eq("entry_date", p["entry_date"]).execute())
            n += 1
        except Exception as e:
            print("  [DB] positions close 갱신 실패(무시):", str(e)[:60])
    return n


def _derive_tf(pattern):
    """패턴명 접미사에서 timeframe 복원 (DB에 tf 컬럼이 없어서 사용)."""
    if pattern.endswith("_4h"):
        return "4h"
    if pattern.endswith("_1h"):
        return "1h"
    return "1d"


def restore_state_db(positions, trades):
    """
    러너(빈 파일시스템)에서 Supabase로 상태 복원.

    GitHub Actions는 매 실행 파일시스템이 초기화되므로 paper_positions/trades
    JSON이 비어 있다. 복원 없이는 openkeys/closedkeys가 비어 같은 신호로
    매 실행 재진입(실거래 중복 매수!)하고 청산 거래가 매번 재기록된다.
    로컬 JSON이 있으면 그것을 원천으로 쓰고 DB 복원은 건너뛴다.
    """
    cli = _db()
    if not cli:
        return positions, trades
    try:
        if not trades:
            tr = cli.table("trades").select("*").limit(1000).execute().data or []
            for t in tr:
                ret = (t.get("return_pct") or 0) / 100.0
                # pnl_usd: DB 값 우선. 컬럼 없으면 과거 트레이드 기준 size $200으로
                # 재구성 (현재 POS_USD로 재계산하면 daily_summary 누적%가 왜곡됨)
                pnl = t.get("pnl_usd")
                if pnl is None:
                    pnl = round(ret * 200.0, 2)
                trades.append(dict(
                    method=t.get("method"), symbol=t.get("symbol"),
                    direction=t.get("direction"), pattern=t.get("pattern"),
                    regime=t.get("regime"), entry_date=t.get("entry_date"),
                    entry_price=t.get("entry_price"), exit_date=t.get("exit_date"),
                    exit_price=t.get("exit_price"), ret=ret,
                    pnl_usd=pnl, hold_bars=t.get("hold_bars"),
                    reason=t.get("exit_reason"), method_label=t.get("method"),
                    live_mode=bool(t.get("live_mode") or False)))
            if tr:
                print(f"  [restore] Supabase trades {len(tr)}건 복원")
        if not positions:
            pr = (cli.table("positions").select("*").eq("status", "open")
                  .limit(500).execute().data) or []
            closed_am = {(t["symbol"], t["pattern"], t["direction"],
                          t["entry_date"], t["method"]) for t in trades}
            seen = set()
            for p in pr:
                key = (p["symbol"], p["pattern"], p["direction"], p["entry_date"])
                if key in seen:          # 과거 중복 오염 방어 — 첫 행만 채택
                    continue
                seen.add(key)
                # live 판정: live_mode 컬럼(있으면) OR method의 LIVE 인코딩
                is_live = bool(p.get("live_mode")) or \
                    str(p.get("method", "")).upper().endswith("LIVE")
                positions.append(dict(
                    symbol=p["symbol"], direction=p["direction"], pattern=p["pattern"],
                    regime=p.get("regime"), tf=_derive_tf(p["pattern"]),
                    entry_date=p["entry_date"],
                    entry_price=p.get("entry_price"), stop=p.get("stop_loss"),
                    size_usd=p.get("size_usd") or POS_USD,
                    live_mode=is_live,
                    d_closed=key + ("D",) in closed_am,
                    a_closed=key + ("A",) in closed_am))
            if pr:
                print(f"  [restore] Supabase 오픈 포지션 {len(positions)}건 복원"
                      f" (원본 {len(pr)}행, 중복 {len(pr)-len(positions)}행 무시)")
    except Exception as e:
        print("  [restore] DB 상태 복원 실패(무시):", str(e)[:60])
    return positions, trades


def reconcile_live_flag(positions, live_conn):
    """
    OKX 실측을 기준으로 DB 복원 포지션의 live_mode를 보정.

    OKX에 (symbol, direction)이 실재하면 해당 DB 포지션을 live_mode=True로 승격한다.
    이렇게 해야 방식D 청산 모니터가 그 포지션을 '실거래'로 보고 조건 충족 시
    실제 OKX reduceOnly 주문을 낸다(자동 매도 사각지대 제거). entry_date가 캔들에
    매핑 안 되면 D-eval이 안전하게 스킵되므로 잘못된 청산 위험은 없다.
    """
    try:
        okx = ex_mod.get_okx_positions(live_conn)
    except Exception as e:
        print("  [reconcile] OKX 포지션 조회 실패(무시):", str(e)[:60])
        return positions
    okx_keys = {(p["symbol"], p["direction"]) for p in okx}
    promoted = []
    for pos in positions:
        if (pos["symbol"], pos["direction"]) in okx_keys and not pos.get("live_mode"):
            pos["live_mode"] = True
            promoted.append(pos["symbol"])
    if promoted:
        print(f"  [reconcile] OKX 실재 → 실거래 승격 {len(promoted)}건: {sorted(set(promoted))}")
    return positions


def run(stamp=None):
    stamp = stamp or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    regmap = rs.build_regime_map()
    positions = _load(POS_FILE, [])
    trades = _load(TRD_FILE, [])
    # 러너 파일시스템은 매 실행 초기화 → Supabase에서 상태 복원
    # (복원 없이는 openkeys가 비어 실거래 중복 진입 발생)
    positions, trades = restore_state_db(positions, trades)
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

    # 실거래 연결 — 청산 모니터링(방식D 실주문)에서도 쓰므로 루프 앞에서 생성
    live_conn = ex_mod.connect_live() if ex_mod.is_live() else None
    kill_switch = False       # True면 신규 실거래 진입 중지(청산 모니터링은 계속)
    if live_conn:
        print(f"[live] OKX 선물 실거래 모드 | USDT free={live_conn['usdt_free']:.2f}")
        # 실거래 정합성 보정: OKX에 실재하는 포지션인데 DB엔 페이퍼(live_mode=False)로
        # 남은 것들을 실거래로 승격 → 방식D 청산 모니터가 실제 OKX 주문을 내도록.
        # (과거 진입경로/복원에서 live 표기가 유실돼 실거래인데 자동청산 사각지대이던 문제)
        positions = reconcile_live_flag(positions, live_conn)

        # 안전망 1: 손절(algo) 주문 상시 점검 — 누락 포지션에 재등록
        fixed_sl = ex_mod.ensure_stop_orders(live_conn)
        if fixed_sl:
            import notify
            notify.send("⚠️ <b>손절 주문 누락 감지 → 재등록</b>\n" +
                        "\n".join(f"  {s}: SL @ {px}" for s, px in fixed_sl))

        # 안전망 2: 계좌 킬스위치 — equity가 HWM 대비 -KILL_DD 초과 하락 시 신규 중지
        bal = ex_mod.get_balance(live_conn)
        equity = (bal or {}).get("equity") or 0.0
        floor = EQUITY_HWM * (1 - KILL_DD)
        if equity and equity < floor:
            kill_switch = True
            msg = (f"🛑 킬스위치 발동: equity ${equity:.2f} < 한도 ${floor:.2f} "
                   f"(HWM ${EQUITY_HWM:.2f} -{KILL_DD*100:.0f}%) — 신규 실거래 진입 중지")
            print(f"  [kill] {msg}")
            import notify
            notify.send(msg)
        elif equity > EQUITY_HWM:
            print(f"  [kill] equity ${equity:.2f} > HWM ${EQUITY_HWM:.2f} — "
                  f"paper_executor.EQUITY_HWM 상향 갱신 권장")

    # 1) 오픈 포지션 청산 모니터링
    #    방식D 청산 조건 충족 + live_mode 포지션 → 실제 OKX reduceOnly 청산 주문.
    #    (과거엔 페이퍼 기록만 하고 실주문이 없어 실거래 익절이 영영 실행 안 되던 버그)
    still_open = []
    closed_now = []                   # 이번 실행에서 A·D 모두 청산 완료된 포지션
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
                do_record = True
                if pos.get("live_mode"):
                    if live_conn is None:
                        do_record = False    # 연결 없으면 유지 → 다음 실행 재시도
                        print(f"  [live] {pos['symbol']} D청산 조건 충족했으나 OKX 미연결 — 유지")
                    else:
                        sl_id = (pos.get("live_order") or {}).get("sl_order_id")
                        fill, why = ex_mod.close_swap_position(
                            live_conn, pos["symbol"], pos["direction"], sl_algo_id=sl_id)
                        if why == "ok":
                            if fill:         # 실체결가로 D 기록 교체
                                base = pos["entry_price"]
                                r = ((fill - base) / base if pos["direction"] == "long"
                                     else (base - fill) / base)
                                ex = (ex[0], fill, r - FEE, ex[3])
                            print(f"  [live] {pos['symbol']} {pos['direction']} D청산 실행 "
                                  f"({ex[3]}) fill={fill}")
                            import notify
                            d_ko = "롱" if pos["direction"] == "long" else "숏"
                            notify.send(f"🔵 <b>실거래 청산(방식D)</b> {pos['symbol']} {d_ko}\n"
                                        f"사유: {ex[3]} | 수익률 {ex[2]*100:+.2f}%\n"
                                        f"진입 {pos['entry_price']} → 청산 {fill}")
                        elif why == "no_position":
                            print(f"  [live] {pos['symbol']} 이미 닫힘(손절 체결 추정) — 기록만")
                        else:
                            do_record = False
                            print(f"  [live] {pos['symbol']} D청산 주문 실패({why}) — 유지, 재시도")
                if do_record:
                    _record_trade(trades, pos, "D", ex, rows[ex[0]]["date"]); pos["d_closed"] = True
        if not pos.get("a_closed"):
            ex = eval_A(rows, ei, pos["direction"])
            if ex:
                _record_trade(trades, pos, "A", ex, rows[ex[0]]["date"]); pos["a_closed"] = True
        if not (pos.get("d_closed") and pos.get("a_closed")):
            still_open.append(pos)
        else:
            closed_now.append(pos)

    # 2) 신규 진입 (signals_today.json)

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
        # RS 필터(롱 전용, 백테스트 근거 backtest_rs.py): weak_rs → 추가 ×0.5
        weak_rs = bool(s.get("weak_rs", False))
        if weak_rs:
            size_for_pos = round(size_for_pos * 0.5, 2)
        if grade != "B" or not tf_ok or weak_rs:
            tf_tag = " [4h비확증×0.5]" if not tf_ok else ""
            rs_tag = " [RS약함×0.5]" if weak_rs else ""
            print(f"  [사이징] {s['symbol']} {grade}등급×{grade_mult}{tf_tag}{rs_tag} → ${size_for_pos:.1f}")

        # 킬스위치 발동 시 실주문 블록 전체 스킵(페이퍼 기록은 아래에서 계속)
        if live_conn and kill_switch:
            print(f"  [live] 킬스위치 발동 중 — {s['symbol']} 실거래 진입 스킵(페이퍼만)")

        if live_conn and not kill_switch:
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
            if weak_rs:                     # RS 약한 롱 → 실거래도 절반
                live_size_usd = round(live_size_usd * 0.5, 2)

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
                # 실체결 기준으로 기록 (신호가와 체결가 불일치 방지)
                entry        = result["entry_price"]
                stop_px      = result["stop_price"]
                size_for_pos = result.get("size_usd", live_size_usd)
                live_open_count   += 1
                live_filled_count += 1
                live_orders       += 1
                print(f"  [live] {s['symbol']} {s['direction']} 진입 OK | "
                      f"size=${size_for_pos:.2f} entry={result['entry_price']:.4f} "
                      f"sl={result['stop_price']:.4f}")
                import notify
                d_ko = "롱" if s["direction"] == "long" else "숏"
                notify.send(f"🟢 <b>실거래 진입</b> {s['symbol']} {d_ko}\n"
                            f"패턴: {s['pattern']} | ${size_for_pos:.2f}\n"
                            f"진입 {result['entry_price']:.4f} / 손절 {result['stop_price']:.4f}")

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
    mark_closed_db(closed_now)
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
