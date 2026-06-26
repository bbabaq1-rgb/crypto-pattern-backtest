"""
exchange.py - 거래소 연결 모듈.

[시뮬레이션] 환경변수 없음 -> 시가 체결 가정, 로컬 기록만.
[데모]       BITGET_DEMO_KEY/SECRET/PASSPHRASE -> 비트겟 샌드박스 (주문 미사용).
[실거래]     OKX_KEY/SECRET/PASSPHRASE -> OKX USDT 무기한 선물(swap) 실주문.

실거래 규칙 (불변):
  - USDT 무기한 선물(swap)만 — 롱/숏 모두 가능
  - 레버리지 2x 고정 (코드 강제 — 외부에서 변경 불가)
  - 격리 마진(isolated) 고정 (교차 마진 절대 불가)
  - 포지션당 최대 $100 고정 (OKX_LIVE_SIZE_USD)
  - 시장가 진입 직후 손절(-8%) 동시 제출
  - 손절 주문 실패 시 진입 즉시 시장가 청산 (진입 취소)
"""
import os

OKX_LIVE_SIZE_USD = 100.0       # 실거래 포지션당 최대 $100 (불변)
OKX_LEVERAGE      = 2            # 레버리지 2x 고정 (절대 변경 금지)
OKX_MARGIN_MODE   = "isolated"  # 격리 마진 고정 (교차 절대 불가)


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


def place_swap_entry(live_conn, symbol, direction, stop_px,
                     size_usd=OKX_LIVE_SIZE_USD):
    """
    OKX USDT 무기한 선물 시장가 진입 + 손절 주문 동시 제출.

    direction: 'long' 또는 'short' 모두 가능 (선물이므로 숏 가능).
    레버리지 2x, 격리 마진 강제 적용.
    손절 실패   -> 진입 즉시 시장가 청산 후 (None, reason) 반환.
    성공        -> (result_dict, "ok") 반환.

    result_dict 키: entry_order_id, sl_order_id, entry_price, qty,
                    stop_price, direction, leverage
    """
    if direction not in ("long", "short"):
        return None, f"invalid_direction:{direction}"

    ex         = live_conn["exchange"]
    ccxt_sym   = f"{symbol}/USDT:USDT"  # OKX USDT 무기한 선물
    side       = "buy"  if direction == "long"  else "sell"
    close_side = "sell" if direction == "long" else "buy"

    # ---- 레버리지·마진 모드 강제 설정 ----
    # 이미 동일 설정이면 거래소가 에러를 내기도 하므로 예외 무시
    try:
        ex.set_margin_mode(OKX_MARGIN_MODE, ccxt_sym)
    except Exception:
        pass
    try:
        ex.set_leverage(OKX_LEVERAGE, ccxt_sym,
                        params={"mgnMode": OKX_MARGIN_MODE})
    except Exception:
        pass

    # ---- 사전 확인 (ticker / 수량 / 잔고) ----
    try:
        ticker = ex.fetch_ticker(ccxt_sym)
        price  = float(ticker["last"])
        if price <= 0:
            return None, "ticker_invalid"

        # 마진 $100 × 레버리지 2 = 노셔널 $200 → 계약 수량
        notional = size_usd * OKX_LEVERAGE
        raw_qty  = notional / price
        qty      = float(ex.amount_to_precision(ccxt_sym, raw_qty))
        if qty <= 0:
            return None, "qty_zero"

        bal       = ex.fetch_balance()
        usdt_free = float(bal.get("USDT", {}).get("free", 0))
        if usdt_free < size_usd * 0.95:      # 5% 여유
            return None, f"insufficient_balance({usdt_free:.1f} USDT free)"
    except Exception as e:
        return None, f"pre_check: {str(e)[:60]}"

    # ---- 1단계: 시장가 진입 ----
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

    # ---- 2단계: 손절 주문 ----
    sl_price = float(ex.price_to_precision(ccxt_sym, stop_px))
    try:
        # OKX 선물 조건부(algo) 손절 주문
        sl_order = ex.create_order(
            ccxt_sym, "conditional", close_side, filled_qty, None,
            params={
                "stopLoss": {
                    "triggerPrice": str(sl_price),
                    "type": "market",       # 시장가 청산
                },
                "tdMode":     OKX_MARGIN_MODE,
                "reduceOnly": True,
            },
        )
        sl_id = sl_order.get("id", "")
    except Exception as sl_err:
        # 손절 실패 -> 진입 즉시 시장가 청산 (진입 취소)
        try:
            ex.create_market_order(
                ccxt_sym, close_side, filled_qty,
                params={"tdMode": OKX_MARGIN_MODE, "reduceOnly": True},
            )
            cancel_note = "entry_reversed_ok"
        except Exception as rev_err:
            cancel_note = f"reverse_failed:{str(rev_err)[:40]}"
        return None, f"sl_failed({str(sl_err)[:50]})_{cancel_note}"

    return {
        "entry_order_id": entry_id,
        "sl_order_id":    sl_id,
        "entry_price":    filled_price,
        "qty":            filled_qty,
        "stop_price":     sl_price,
        "direction":      direction,
        "leverage":       OKX_LEVERAGE,
    }, "ok"


if __name__ == "__main__":
    c = connect()
    print(f"[demo] mode={c['mode']} | balance={c['balance']} | {c['note']}")
    print(f"[live] is_live={is_live()}")
    if is_live():
        lc = connect_live()
        if lc:
            print(f"[live] OKX 연결 OK | USDT free={lc['usdt_free']:.2f}")
