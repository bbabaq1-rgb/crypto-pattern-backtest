"""
test_exchange_stops.py — 손절(algo) 주문 안전망 오프라인 검증.

실거래 주문 경로(exchange.place_stop_algo / ensure_stop_orders)는 러너에서만
실행되므로, OKX API를 스텁으로 갈아끼워 로직만 검증한다. 네트워크·키 불필요.
실행: python test_exchange_stops.py   (실패 시 exit 1)

검증 대상 (2026-08-29 실계좌 사고 대응):
  - 손절 주문에 reduceOnly 포함 (포지션 없을 때 트리거돼도 신규 진입 안 됨)
  - 포지션 없는 고아 손절 주문 취소
  - 포지션 조회 실패 시 취소 전면 스킵 (살아있는 손절 보호)
"""
import sys

import exchange as ex_mod


class StubEx:
    """필요한 OKX 엔드포인트만 흉내내는 스텁."""

    def __init__(self, positions, pending, reject_reduce_only=False,
                 positions_raise=False):
        self._positions = positions
        self._pending = pending
        self.reject_reduce_only = reject_reduce_only
        self.positions_raise = positions_raise
        self.algo_calls = []      # 등록 시도한 파라미터
        self.cancel_calls = []    # 취소 시도한 인자

    def fetch_positions(self):
        if self.positions_raise:
            raise RuntimeError("network down")
        return self._positions

    def privateGetTradeOrdersAlgoPending(self, params):
        return {"code": "0", "data": self._pending}

    def privatePostTradeOrderAlgo(self, params):
        self.algo_calls.append(dict(params))
        if self.reject_reduce_only and "reduceOnly" in params:
            return {"code": "51000", "msg": "reduceOnly not supported"}
        return {"code": "0", "data": [{"algoId": "NEW1"}]}

    def privatePostTradeCancelAlgos(self, arr):
        self.cancel_calls.append(arr)
        return {"code": "0"}

    def price_to_precision(self, sym, px):
        return round(float(px), 4)

    def market_id(self, sym):
        return sym.split("/")[0] + "-USDT-SWAP"


def pos(sym, contracts=4.0, entry=500.0, side="long"):
    return {"symbol": f"{sym}/USDT:USDT", "contracts": contracts, "side": side,
            "entryPrice": entry, "notional": contracts * entry, "leverage": 2,
            "contractSize": 1, "unrealizedPnl": 0,
            "info": {"instId": f"{sym}-USDT-SWAP", "margin": "10"}}


def algo(sym, algo_id, state="live"):
    return {"instId": f"{sym}-USDT-SWAP", "algoId": algo_id, "state": state,
            "side": "sell", "slTriggerPx": "100", "sz": "4"}


fails = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f" — {detail}"))
    if not cond:
        fails.append(name)


def main():
    # 1) 고아 취소 + 손절 누락 재등록 동시 케이스
    #    BNB: 포지션 있으나 손절 없음 → 재등록
    #    ETH: 손절만 있고 포지션 없음   → 고아 취소
    #    LTC: 포지션 + 손절 정상        → 무동작
    stub = StubEx(positions=[pos("BNB"), pos("LTC", entry=40.0)],
                  pending=[algo("ETH", "A_ETH"), algo("LTC", "A_LTC")])
    fixed, cancelled = ex_mod.ensure_stop_orders({"exchange": stub})
    check("BNB 손절 재등록", fixed == [("BNB", 460.0)], f"fixed={fixed}")
    check("ETH 고아 취소", [c[0] for c in cancelled] == ["ETH-USDT-SWAP"],
          f"cancelled={cancelled}")
    check("LTC 정상건 취소 안 함",
          all("LTC" not in str(c) for c in stub.cancel_calls), stub.cancel_calls)
    check("재등록에 reduceOnly 포함",
          bool(stub.algo_calls) and stub.algo_calls[0].get("reduceOnly") is True,
          stub.algo_calls)

    # 2) 포지션 조회 실패 → 고아 취소 전면 스킵(살아있는 손절 보호)
    stub2 = StubEx(positions=[], pending=[algo("ETH", "A_ETH")],
                   positions_raise=True)
    _, cancelled2 = ex_mod.ensure_stop_orders({"exchange": stub2})
    check("조회 실패 시 취소 스킵", cancelled2 == [] and stub2.cancel_calls == [],
          f"cancelled={cancelled2} calls={stub2.cancel_calls}")

    # 3) 포지션 0 + 고아만 존재 → 취소 (구버전 early-return 회귀 방지)
    stub3 = StubEx(positions=[],
                   pending=[algo("ETH", "A_ETH"), algo("UNI", "A_UNI")])
    _, cancelled3 = ex_mod.ensure_stop_orders({"exchange": stub3})
    check("포지션 0이어도 고아 취소",
          sorted(c[0] for c in cancelled3) == ["ETH-USDT-SWAP", "UNI-USDT-SWAP"],
          f"cancelled={cancelled3}")

    # 4) reduceOnly 거부 → 1회 폴백 후 성공
    stub4 = StubEx(positions=[], pending=[], reject_reduce_only=True)
    resp = ex_mod.place_stop_algo(stub4, "BNB-USDT-SWAP", "sell", 4, 460.0)
    check("reduceOnly 거부 시 폴백 성공", str(resp.get("code")) == "0", resp)
    check("폴백은 정확히 1회(2번째 호출엔 reduceOnly 없음)",
          len(stub4.algo_calls) == 2 and "reduceOnly" not in stub4.algo_calls[1],
          stub4.algo_calls)

    # 5-저가코인) 지수 표기 금지 — 2026-09-17 SHIB 회귀
    #    파이썬 str(9e-06) == '9e-06' 이고 OKX 는 이를 51000 Parameter slTriggerPx
    #    error 로 거부한다. 가격이 $0.0001 밑인 종목(SHIB/PEPE/BONK)이 전부 여기에 걸렸다.
    check("num_str: 저가 십진 표기", ex_mod.num_str(9.4e-06) == "0.0000094",
          ex_mod.num_str(9.4e-06))
    check("num_str: 지수 표기 없음",
          all("e" not in ex_mod.num_str(v).lower()
              for v in (9e-06, 1.02e-05, 1.234e-07, 0.0, 65000.5, 1e12)),
          [ex_mod.num_str(v) for v in (9e-06, 1.02e-05, 1.234e-07, 0.0, 65000.5, 1e12)])
    check("num_str: 정상 가격은 종전 표기 유지",
          (ex_mod.num_str(460.0), ex_mod.num_str(0.5), ex_mod.num_str(0.01),
           ex_mod.num_str(0.0)) == ("460", "0.5", "0.01", "0"),
          [ex_mod.num_str(v) for v in (460.0, 0.5, 0.01, 0.0)])

    stub_shib = StubEx(positions=[], pending=[])
    ex_mod.place_stop_algo(stub_shib, "SHIB-USDT-SWAP", "sell", 1200,
                           9.4e-06, tp_px=1.06e-05)
    prm = stub_shib.algo_calls[0]
    check("SHIB 손절 트리거가 십진 문자열",
          prm["slTriggerPx"] == "0.0000094" and prm["tpTriggerPx"] == "0.0000106",
          prm)
    check("sz 도 지수 표기 아님", "e" not in prm["sz"].lower(), prm["sz"])

    # 5) state != live 인 대기 주문은 대상 아님
    stub5 = StubEx(positions=[], pending=[algo("ETH", "A_ETH", state="canceled")])
    _, cancelled5 = ex_mod.ensure_stop_orders({"exchange": stub5})
    check("비활성 주문은 취소 대상 아님", cancelled5 == [], cancelled5)

    algo_state_checks()

    print()
    print(f"실패 {len(fails)}건" if fails else "전체 통과")
    return 1 if fails else 0


class AlgoStateEx:
    """
    exchange.algo_state 가 부르는 OKX 엔드포인트 스텁 — 2026-10-29 진단 실행(읽기 전용)에서 받은 응답 모양 그대로:
      · 대기 조회(orders-algo-pending)는 대기 목록에 없으면 51603 'Order does not exist' 예외
      · 이력 조회(orders-algo-history)는 ordType 이 맞아야 1건, 아니면 51603 예외
      · 시장가 OCO 의 이력은 state=effective · actualPx="" · actualSide=tp/sl · ordIdList=[시장가 주문 id]
      · 체결가는 그 주문(trade/order)의 avgPx · accFillSz
    """

    def __init__(self, pending=None, history=None, orders=None, order_raises=False):
        self.pending, self.history = pending or {}, history or {}
        self.orders, self.order_raises = orders or {}, order_raises
        self.order_calls = []

    @staticmethod
    def _not_found():
        return Exception('okx {"code":"51603","data":[],"msg":"Order does not exist"}')

    def _lookup(self, table, p):
        o = table.get(p["algoId"])
        if o is None or o["ordType"] != p["ordType"]:
            raise self._not_found()
        return {"code": "0", "data": [o]}

    def privateGetTradeOrdersAlgoPending(self, p):
        return self._lookup(self.pending, p)

    def privateGetTradeOrdersAlgoHistory(self, p):
        return self._lookup(self.history, p)

    def privateGetTradeOrder(self, p):
        self.order_calls.append(p)
        if self.order_raises:
            raise Exception("network")
        return {"code": "0", "data": [self.orders[p["ordId"]]]}


def _oco_hist(aid, side, oids, actual_px=""):
    """실측 응답(2026-10-29 algoId 4051395198249181184)과 같은 필드 모양."""
    return {"algoId": aid, "instId": "BTC-USDT-SWAP", "ordType": "oco", "state": "effective",
            "actualPx": actual_px, "actualSide": side, "actualSz": "0.37", "tpTriggerPx": "80743",
            "tpOrdPx": "-1", "slTriggerPx": "79590", "slOrdPx": "-1",
            "ordId": oids[0] if oids else "", "ordIdList": oids, "sz": "0.37", "failCode": "0"}


def algo_state_checks():
    # 6) 시장가 OCO 익절 — actualPx "" 여도 체결가를 시장가 주문의 avgPx 에서 읽는다(실측 80,752.2)
    st = AlgoStateEx(history={"A1": _oco_hist("A1", "tp", ["O1"])},
                     orders={"O1": {"ordId": "O1", "state": "filled", "avgPx": "80752.2", "accFillSz": "0.37"}})
    r = ex_mod.algo_state({"exchange": st}, "A1")
    check("시장가 OCO 익절: state effective · actual_px = 주문 avgPx · side tp · 출처 order",
          r == {"state": "effective", "actual_px": 80752.2, "actual_side": "tp", "px_source": "order"}, r)
    check("주문 조회는 instId·ordId 로 한 번", st.order_calls == [{"instId": "BTC-USDT-SWAP", "ordId": "O1"}],
          st.order_calls)

    # 7) 시장가 OCO 손절 — 같은 경로(실측 80,940)
    st = AlgoStateEx(history={"A2": _oco_hist("A2", "sl", ["O2"])},
                     orders={"O2": {"ordId": "O2", "state": "filled", "avgPx": "80940", "accFillSz": "0.36"}})
    r = ex_mod.algo_state({"exchange": st}, "A2")
    check("시장가 OCO 손절: actual_px 80940 · side sl", r and r["actual_px"] == 80940.0 and r["actual_side"] == "sl", r)

    # 8) 부분 체결로 주문이 여러 건 — 체결 수량 가중 평균
    st = AlgoStateEx(history={"A3": _oco_hist("A3", "sl", ["O3", "O4"])},
                     orders={"O3": {"avgPx": "100", "accFillSz": "1"}, "O4": {"avgPx": "103", "accFillSz": "2"}})
    r = ex_mod.algo_state({"exchange": st}, "A3")
    check("주문 여러 건 → 수량 가중 평균(100×1 + 103×2)/3 = 102", r and abs(r["actual_px"] - 102.0) < 1e-9, r)

    # 9) 주문 조회 실패 — 체결가를 모르면 None(트리거 가격으로 대신 적지 않는다), 상태는 그대로
    st = AlgoStateEx(history={"A1": _oco_hist("A1", "tp", ["O1"])}, order_raises=True)
    r = ex_mod.algo_state({"exchange": st}, "A1")
    check("주문 조회 실패 → state effective · actual_px None · 출처 None",
          r == {"state": "effective", "actual_px": None, "actual_side": "tp", "px_source": None}, r)

    # 10) ordIdList 가 비면 ordId 한 건으로
    h = _oco_hist("A5", "tp", [])
    h["ordId"] = "O5"
    st = AlgoStateEx(history={"A5": h}, orders={"O5": {"avgPx": "50", "accFillSz": "1"}})
    r = ex_mod.algo_state({"exchange": st}, "A5")
    check("ordIdList 없으면 ordId 로", r and r["actual_px"] == 50.0, r)

    # 11) actualPx 가 실제 값이면 그대로(주문 조회 안 함) — 지정가 OCO 대비
    st = AlgoStateEx(history={"A6": _oco_hist("A6", "tp", ["O6"], actual_px="101.5")})
    r = ex_mod.algo_state({"exchange": st}, "A6")
    check("actualPx 있으면 그 값 · 출처 actual · 주문 조회 0", r and r["actual_px"] == 101.5
          and r["px_source"] == "actual" and st.order_calls == [], r)

    # 12) actualPx "-1"(시장가 표시) 은 체결가가 아니다 → 주문에서 읽는다
    st = AlgoStateEx(history={"A7": _oco_hist("A7", "tp", ["O7"], actual_px="-1")},
                     orders={"O7": {"avgPx": "99", "accFillSz": "1"}})
    r = ex_mod.algo_state({"exchange": st}, "A7")
    check("actualPx -1 은 무시하고 주문 avgPx", r and r["actual_px"] == 99.0 and r["px_source"] == "order", r)

    # 13) 아직 대기 중(live) — 주문 조회 없이 상태만
    live = dict(_oco_hist("A8", "", []), state="live", actualSide="")
    st = AlgoStateEx(pending={"A8": live})
    r = ex_mod.algo_state({"exchange": st}, "A8")
    check("대기(live) → actual_px None · 주문 조회 0", r and r["state"] == "live" and r["actual_px"] is None
          and st.order_calls == [], r)

    # 14) 어디에도 없으면 None(알 수 없음 — 호출부가 보류)
    r = ex_mod.algo_state({"exchange": AlgoStateEx()}, "ZZ")
    check("대기·이력 어디에도 없음 → None", r is None, r)

    # 15) 취소된 algo 는 체결가를 찾지 않는다
    st = AlgoStateEx(history={"A9": dict(_oco_hist("A9", "", ["O9"]), state="canceled")})
    r = ex_mod.algo_state({"exchange": st}, "A9")
    check("canceled → actual_px None · 주문 조회 0", r and r["state"] == "canceled" and r["actual_px"] is None
          and st.order_calls == [], r)


if __name__ == "__main__":
    sys.exit(main())
