"""
exchange.py - 거래소 연결 모듈.

[시뮬레이션] 환경변수 없음 -> 시가 체결 가정, 로컬 기록만.
[데모]       BITGET_DEMO_KEY/SECRET/PASSPHRASE -> 비트겟 샌드박스 (주문 미사용).
[실거래]     OKX_KEY/SECRET/PASSPHRASE -> OKX USDT 무기한 선물(swap) 실주문.

실거래 규칙 (불변):
  - USDT 무기한 선물(swap)만 — 롱/숏 모두 가능
  - 레버리지 2x 고정 (코드 강제 — 외부에서 변경 불가)
  - 격리 마진(isolated) 고정 (교차 마진 절대 불가)
  - 잔고 < 주문금액 시 가용잔고 90%로 자동 조정, $10 미만이면 스킵
  - 동시 최대 5포지션
  - 진입 직후 OKX algo 손절 주문(privatePostTradeOrderAlgo) 제출
  - 손절 주문 실패 시 진입 즉시 시장가 청산 (진입 취소)
"""
import os

OKX_LEVERAGE    = 2            # 레버리지 2x 고정 (절대 변경 금지)
OKX_MARGIN_MODE = "isolated"  # 격리 마진 고정 (교차 절대 불가)


# ---------------------------------------------------------------------------
# 공통 헬퍼
# ---------------------------------------------------------------------------

def is_live():
    """OKX 실거래 환경변수 3종 모두 설정돼 있으면 True."""
    return bool(
        os.environ.get("OKX_KEY") and
        os.environ.get("OKX_SECRET") and
        os.environ.get("OKX_PASSPHRASE")
    )


# ---------------------------------------------------------------------------
# 비트겟 데모 (기존 유지 - 잔고 확인용)
# ---------------------------------------------------------------------------

def connect():
    """비트겟 데모 연결. 키 없거나 실패 시 시뮬레이션 모드 반환."""
    key = os.environ.get("BITGET_DEMO_KEY")
    sec = os.environ.get("BITGET_DEMO_SECRET")
    pw  = os.environ.get("BITGET_DEMO_PASSPHRASE")
    if not (key and sec and pw):
        return {"mode": "simulation", "exchange": None, "balance": None,
                "note": "데모 키 없음 -> 시뮬레이션 모드(시가 체결 가정, 로컬 기록만)"}
    try:
        import ccxt
        ex = ccxt.bitget({"apiKey": key, "secret": sec, "password": pw,
                          "enableRateLimit": True})
        ex.set_sandbox_mode(True)
        bal = ex.fetch_balance()
        usdt = bal.get("USDT", {}).get("total")
        return {"mode": "demo", "exchange": ex, "balance": usdt,
                "note": "비트겟 데모 연결 성공(읽기 전용; 주문 미사용)"}
    except Exception as e:
        return {"mode": "simulation", "exchange": None, "balance": None,
                "note": f"데모 연결 실패 -> 시뮬레이션 폴백: {str(e)[:80]}"}


# ---------------------------------------------------------------------------
# OKX 실거래 (USDT 무기한 선물)
# ---------------------------------------------------------------------------

def connect_live():
    """
    OKX USDT 무기한 선물 실거래 연결. 환경변수 미설정 또는 연결 실패 시 None 반환.
    반환: {"exchange": ccxt.okx 인스턴스, "usdt_free": float} 또는 None
    """
    if not is_live():
        return None
    try:
        import ccxt
        ex = ccxt.okx({
            "apiKey":    os.environ["OKX_KEY"],
            "secret":    os.environ["OKX_SECRET"],
            "password":  os.environ["OKX_PASSPHRASE"],
            "enableRateLimit": True,
        })
        ex.load_markets()
        bal = ex.fetch_balance()
        usdt_free = float(bal.get("USDT", {}).get("free", 0.0))
        return {"exchange": ex, "usdt_free": usdt_free}
    except Exception as e:
        print(f"[OKX] 실거래 연결 실패: {str(e)[:80]}")
        return None


def get_balance(live_conn):
    """
    OKX 선물 계좌 총 자산 조회.

    반환: {
        "equity": float,   # 총 자산 (마진+미실현P&L 포함) — OKX totalEq
        "free":   float,   # 가용 잔고 (새 주문에 쓸 수 있는 USDT)
        "total":  float,   # 총 USDT (free + 포지션 마진, 미실현P&L 미포함)
    }
    실패 시 None 반환.
    """
    try:
        ex  = live_conn["exchange"]
        bal = ex.fetch_balance()

        # 1순위: OKX totalEq (미실현P&L 포함 총 자산)
        equity = None
        try:
            raw = bal.get("info", {}).get("data", [])
            if raw:
                eq = raw[0].get("totalEq")
                if eq is not None:
                    equity = float(eq)
        except Exception:
            pass

        usdt     = bal.get("USDT", {})
        free_bal = float(usdt.get("free", 0.0))
        total_bal = float(usdt.get("total", 0.0))

        return {
            "equity": equity if equity is not None else total_bal,
            "free":   free_bal,
            "total":  total_bal,
        }
    except Exception as e:
        print(f"[OKX] 잔고 조회 실패: {str(e)[:60]}")
        return None


def get_okx_positions(live_conn):
    """
    OKX 실제 오픈 포지션 목록 조회.
    반환: [{"symbol", "direction", "qty"(계약수), "coin_qty"(코인수량),
             "entry_price", "unrealized_pnl", "notional"(명목=코인수량×가격),
             "margin"(실제 투입증거금), "leverage"(실제 레버리지)}]
    실패 시 빈 리스트 반환.

    주의:
      - qty 는 OKX 계약수(contracts). 코인 수량은 contracts × contractSize.
      - margin 은 OKX 가 보고한 실제 초기증거금(initialMargin/collateral).
        assume-2x 로 나누지 않고 거래소 값을 그대로 쓴다.
    """
    try:
        ex = live_conn["exchange"]
        positions = ex.fetch_positions()
        result = []
        for p in positions:
            contracts = abs(float(p.get("contracts") or 0))
            if contracts <= 0:
                continue
            sym  = str(p.get("symbol", "")).split("/")[0].split(":")[0]
            side = str(p.get("side", "")).lower()
            direction = "long" if side == "long" else "short"

            entry     = float(p.get("entryPrice") or p.get("averagePrice") or 0)
            notional  = abs(float(p.get("notional") or 0))
            leverage  = float(p.get("leverage") or 0) or None

            # 계약당 코인 수량(contractSize) — notional/entry 로 역산 폴백
            csize = p.get("contractSize")
            try:
                csize = float(csize) if csize else None
            except (TypeError, ValueError):
                csize = None
            coin_qty = contracts * csize if csize else (
                notional / entry if entry else contracts)

            # 실제 증거금 우선순위: OKX raw margin(격리 실증거금) → imr → ccxt
            # initialMargin → 명목/레버리지. collateral 은 미실현손익이 섞여
            # '투입금'과 어긋나므로 쓰지 않는다.
            info = p.get("info", {}) if isinstance(p.get("info"), dict) else {}
            margin = None
            for cand in (info.get("margin"), info.get("imr"),
                         p.get("initialMargin")):
                try:
                    if cand is not None and float(cand) > 0:
                        margin = float(cand); break
                except (TypeError, ValueError):
                    continue
            if margin is None and notional and leverage:
                margin = notional / leverage

            # 청산가(liquidation) — OKX liqPx 우선, 없으면 격리 2x 근사
            liq = None
            for cand in (p.get("liquidationPrice"), info.get("liqPx")):
                try:
                    if cand is not None and float(cand) > 0:
                        liq = float(cand); break
                except (TypeError, ValueError):
                    continue
            if liq is None and entry and leverage:
                # 격리마진 대략적 청산가(수수료·유지증거금 무시): 롱 entry*(1-1/lev)
                liq = entry * (1 - 1 / leverage) if direction == "long" \
                    else entry * (1 + 1 / leverage)

            # ROE(증거금 대비 수익률) = 미실현손익 / 증거금
            upnl = float(p.get("unrealizedPnl") or 0)
            roe  = (upnl / margin * 100) if margin else None

            # 현재가(mark) — 포지션 응답에 이미 포함되어 별도 시세조회 불필요(첫 로딩 가속)
            mark = None
            for cand in (p.get("markPrice"), info.get("markPx"), info.get("last")):
                try:
                    if cand is not None and float(cand) > 0:
                        mark = float(cand); break
                except (TypeError, ValueError):
                    continue

            result.append({
                "symbol":          sym,
                "direction":       direction,
                "qty":             contracts,
                "coin_qty":        coin_qty,
                "entry_price":     entry,
                "unrealized_pnl":  upnl,
                "notional":        notional,
                "margin":          margin,
                "leverage":        leverage,
                "liq_price":       liq,
                "roe":             roe,
                "mark_price":      mark,
            })
        return result
    except Exception as e:
        print(f"[OKX] 포지션 조회 실패: {str(e)[:60]}")
        return []


def ensure_stop_orders(live_conn, stop_pct=0.08):
    """
    안전망: 모든 오픈 포지션에 손절(algo) 주문이 걸려 있는지 점검, 없으면 재등록.

    '손절 주문 없으면 실거래 절대 안 됨' 원칙의 상시 자동 점검(과거엔 수동 감사 의존).
    - 기존 주문은 절대 취소/수정하지 않음 — 누락된 포지션에만 추가.
    - 손절가 = 진입가 ±stop_pct (방식D 정책과 동일, 가격 기준).
    반환: [(symbol, stop_px), ...] 재등록 목록. 실패는 출력만(파이프라인 비차단).
    """
    fixed = []
    try:
        ex = live_conn["exchange"]
        poss = get_okx_positions(live_conn)
        if not poss:
            return fixed
        resp = ex.privateGetTradeOrdersAlgoPending({"ordType": "conditional"})
        covered = {o.get("instId") for o in resp.get("data", [])
                   if o.get("state") == "live" and o.get("slTriggerPx")}
        for p in poss:
            inst = f"{p['symbol']}-USDT-SWAP"
            if inst in covered:
                continue
            entry, d = p["entry_price"], p["direction"]
            sl_px = entry * (1 - stop_pct) if d == "long" else entry * (1 + stop_pct)
            ccxt_sym = f"{p['symbol']}/USDT:USDT"
            sl_px = float(ex.price_to_precision(ccxt_sym, sl_px))
            close_side = "sell" if d == "long" else "buy"
            try:
                r = ex.privatePostTradeOrderAlgo({
                    "instId": inst, "tdMode": OKX_MARGIN_MODE, "side": close_side,
                    "ordType": "conditional", "sz": str(p["qty"]),
                    "slTriggerPx": str(sl_px), "slOrdPx": "-1",
                    "slTriggerPxType": "last",
                })
                if r.get("code") == "0":
                    fixed.append((p["symbol"], sl_px))
                    print(f"  [SL점검] {p['symbol']} 손절 누락 → 재등록 @ {sl_px}")
                else:
                    print(f"  [SL점검] {p['symbol']} 재등록 실패: {str(r)[:80]}")
            except Exception as e:
                print(f"  [SL점검] {p['symbol']} 재등록 오류: {str(e)[:60]}")
    except Exception as e:
        print(f"  [SL점검] 점검 실패(무시): {str(e)[:60]}")
    return fixed


def place_swap_entry(live_conn, symbol, direction, stop_px, size_usd=20.0):
    """
    OKX USDT 무기한 선물 시장가 진입 + OKX algo 손절 주문 동시 제출.

    direction : 'long' 또는 'short'
    stop_px   : 손절 트리거 가격
    size_usd  : 마진 금액 (잔고 부족 시 가용잔고 90%로 자동 조정, $10 미만 스킵)

    성공 → (result_dict, "ok")
    실패 → (None, reason_str)
    result_dict 키: entry_order_id, sl_order_id, entry_price, qty,
                    stop_price, direction, leverage, size_usd
    """
    if direction not in ("long", "short"):
        return None, f"invalid_direction:{direction}"

    ex         = live_conn["exchange"]
    ccxt_sym   = f"{symbol}/USDT:USDT"
    side       = "buy"  if direction == "long" else "sell"
    close_side = "sell" if direction == "long" else "buy"
    eff_size   = size_usd   # 실제 주문금액 (잔고 조정 후 갱신)

    # ---- 레버리지·마진 모드 강제 설정 ----------------------------------------
    try:
        ex.set_margin_mode(OKX_MARGIN_MODE, ccxt_sym)
    except Exception:
        pass
    try:
        ex.set_leverage(OKX_LEVERAGE, ccxt_sym,
                        params={"mgnMode": OKX_MARGIN_MODE})
    except Exception:
        pass

    # ---- 사전 확인: 가격·잔고·lot size ----------------------------------------
    try:
        ticker    = ex.fetch_ticker(ccxt_sym)
        price     = float(ticker["last"])
        if price <= 0:
            return None, "ticker_invalid"

        # 잔고 확인 → 부족하면 가용잔고 90%로 자동 조정
        bal       = ex.fetch_balance()
        usdt_free = float(bal.get("USDT", {}).get("free", 0))
        if usdt_free < eff_size:
            eff_size = round(usdt_free * 0.9, 2)
            print(f"  [live] 잔고 부족({usdt_free:.2f} USDT) → ${size_usd} → ${eff_size:.2f} 조정")
        if eff_size < 10.0:
            return None, f"balance_too_low({usdt_free:.2f} USDT free → skip)"

        # 수량 계산 (레버리지 반영) — OKX swap 주문 수량은 '계약 수' 단위.
        # contractSize≠1 종목(AXS/COMP=0.1 등)에서 코인 수로 보내면 의도의
        # 1/10 크기로 체결되는 버그가 있었다 → 계약 수로 환산.
        mkt       = ex.market(ccxt_sym)
        csize     = float(mkt.get("contractSize") or 1) or 1.0
        notional  = eff_size * OKX_LEVERAGE
        raw_qty   = notional / price / csize
        qty       = float(ex.amount_to_precision(ccxt_sym, raw_qty))

        # 최소 lot size 확인
        min_qty  = float((mkt.get("limits") or {}).get("amount", {}).get("min") or 0)
        if min_qty > 0 and qty < min_qty:
            return None, f"qty_below_lot_min({qty:.6f} < {min_qty})"
        if qty <= 0:
            return None, "qty_zero"

    except Exception as e:
        return None, f"pre_check: {str(e)[:60]}"

    # ---- 1단계: 시장가 진입 ---------------------------------------------------
    try:
        entry_order  = ex.create_market_order(
            ccxt_sym, side, qty,
            params={"tdMode": OKX_MARGIN_MODE},
        )
        filled_qty   = float(entry_order.get("filled") or qty)
        filled_price = float(entry_order.get("average") or price)
        entry_id     = entry_order.get("id", "")
    except Exception as e:
        return None, f"entry_failed: {str(e)[:60]}"

    # ---- 2단계: OKX Algo 손절 주문 (privatePostTradeOrderAlgo) ----------------
    # OKX code 50015 원인: create_order의 stopLoss dict 형식이 algo endpoint와 불일치
    # → POST /api/v5/trade/order-algo 직접 호출로 교체
    sl_price = float(ex.price_to_precision(ccxt_sym, stop_px))
    try:
        inst_id = ex.market_id(ccxt_sym)   # "SOL-USDT-SWAP" 형식
        resp    = ex.privatePostTradeOrderAlgo({
            "instId":          inst_id,
            "tdMode":          OKX_MARGIN_MODE,
            "side":            close_side,
            "ordType":         "conditional",
            "sz":              str(filled_qty),
            "slTriggerPx":     str(sl_price),
            "slOrdPx":         "-1",         # -1 = 시장가 체결
            "slTriggerPxType": "last",
        })
        if resp.get("code") != "0":
            raise Exception(str(resp))
        sl_id = resp["data"][0]["algoId"]
    except Exception as sl_err:
        # 손절 실패 → 진입 즉시 시장가 청산 (진입 취소)
        try:
            ex.create_market_order(
                ccxt_sym, close_side, filled_qty,
                params={"tdMode": OKX_MARGIN_MODE, "reduceOnly": True},
            )
            cancel_note = "entry_reversed_ok"
        except Exception as rev_err:
            cancel_note = f"reverse_failed:{str(rev_err)[:40]}"
        return None, f"sl_failed({str(sl_err)[:60]})_{cancel_note}"

    return {
        "entry_order_id": entry_id,
        "sl_order_id":    sl_id,
        "entry_price":    filled_price,
        "qty":            filled_qty,
        "stop_price":     sl_price,
        "direction":      direction,
        "leverage":       OKX_LEVERAGE,
        "size_usd":       eff_size,
    }, "ok"


def get_okx_closed_positions(live_conn, limit=50):
    """
    OKX 최근 종료 포지션 이력 — (symbol, direction) → 최신 청산 정보.

    OKX algo 손절이 장중에 터지거나 사용자가 앱에서 직접 닫으면 엔진(일봉 eval_D)이
    모를 수 있다. 이 이력으로 '엔진 몰래 청산된' 포지션을 잡아 기록/정리한다.
    반환: {(sym,dir): {"close_px","pnl","utime","type"}}  (같은 키는 최신 1건)
    """
    out = {}
    try:
        ex = live_conn["exchange"]
        resp = ex.privateGetAccountPositionsHistory({"limit": str(limit)})
        for h in resp.get("data", []):
            sym = str(h.get("instId", "")).split("-")[0]
            pos_side = str(h.get("posSide", "")).lower()
            direction = ("long" if pos_side == "long" else
                         "short" if pos_side == "short" else
                         ("long" if str(h.get("direction", "")).lower() == "long" else "short"))
            try:
                utime = int(h.get("uTime") or 0)
            except (TypeError, ValueError):
                utime = 0
            key = (sym, direction)
            prev = out.get(key)
            if prev and prev["utime"] >= utime:
                continue          # 더 최신 것만 유지
            out[key] = {
                "close_px": float(h.get("closeAvgPx") or 0) or None,
                "pnl":      float(h.get("realizedPnl") or h.get("pnl") or 0),
                "utime":    utime,
                "type":     str(h.get("type", "")),   # 2=전량,3=강제,5=ADL 등
            }
    except Exception as e:
        print(f"[OKX] 청산이력 조회 실패: {str(e)[:60]}")
    return out


def close_swap_position(live_conn, symbol, direction, sl_algo_id=None):
    """
    OKX 포지션 전량 시장가 청산(reduceOnly) + 잔여 손절 algo 취소.

    반환: (fill_price | None, "ok")  성공
          (None, reason)             실패 — 호출부는 포지션 유지 후 재시도
    """
    try:
        ex = live_conn["exchange"]
        ccxt_sym = f"{symbol}/USDT:USDT"
        qty = 0.0
        for p in ex.fetch_positions([ccxt_sym]):
            side = str(p.get("side", "")).lower()
            if side == direction:
                qty = abs(float(p.get("contracts") or 0))
                break
        if qty <= 0:
            return None, "no_position"      # 이미 닫힘(손절 체결 등)
        close_side = "sell" if direction == "long" else "buy"
        order = ex.create_market_order(
            ccxt_sym, close_side, qty,
            params={"tdMode": OKX_MARGIN_MODE, "reduceOnly": True})
        fill = float(order.get("average") or order.get("price") or 0) or None
        # 잔여 손절 algo 취소(실패해도 무시 — 포지션 없으면 자동 무효)
        if sl_algo_id:
            try:
                ex.privatePostTradeCancelAlgos([
                    {"algoId": str(sl_algo_id), "instId": ex.market_id(ccxt_sym)}])
            except Exception:
                pass
        return fill, "ok"
    except Exception as e:
        return None, str(e)[:80]


if __name__ == "__main__":
    c = connect()
    print(f"[demo] mode={c['mode']} | balance={c['balance']} | {c['note']}")
    print(f"[live] is_live={is_live()}")
    if is_live():
        lc = connect_live()
        if lc:
            bal = get_balance(lc)
            if bal:
                print(f"[live] OKX 연결 OK | equity={bal['equity']:.2f}"
                      f" | free={bal['free']:.2f} | total={bal['total']:.2f}")
            poss = get_okx_positions(lc)
            print(f"[live] 오픈 포지션 {len(poss)}개: {poss}")
