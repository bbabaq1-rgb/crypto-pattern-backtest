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

    # 5) state != live 인 대기 주문은 대상 아님
    stub5 = StubEx(positions=[], pending=[algo("ETH", "A_ETH", state="canceled")])
    _, cancelled5 = ex_mod.ensure_stop_orders({"exchange": stub5})
    check("비활성 주문은 취소 대상 아님", cancelled5 == [], cancelled5)

    print()
    print(f"실패 {len(fails)}건" if fails else "전체 통과")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
