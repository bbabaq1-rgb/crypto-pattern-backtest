"""
audit_okx.py — OKX 실계좌 상태 덤프 (정합성 감사용).

GitHub Actions(OKX 키 보유)에서 실행해 okx_state.json 아티팩트로 저장.
잔고 + 오픈 포지션 + 대기 중 손절(algo) 주문을 한 파일에 기록한다.
읽기 전용 — 주문/청산 등 상태 변경 없음.
"""
import json
from datetime import datetime, timezone

import exchange as ex_mod


def main():
    out = {"ts": datetime.now(timezone.utc).isoformat(), "is_live": ex_mod.is_live()}
    if not ex_mod.is_live():
        out["error"] = "OKX 키 미설정"
    else:
        conn = ex_mod.connect_live()
        if not conn:
            out["error"] = "connect_live 실패"
        else:
            out["balance"]   = ex_mod.get_balance(conn)
            out["positions"] = ex_mod.get_okx_positions(conn)
            # 대기 중 손절(algo) 주문 — 포지션별 손절 존재 여부 검증용
            try:
                ex = conn["exchange"]
                resp = ex.privateGetTradeOrdersAlgoPending({"ordType": "conditional"})
                out["algo_orders"] = [
                    {"instId": o.get("instId"), "side": o.get("side"),
                     "slTriggerPx": o.get("slTriggerPx"), "sz": o.get("sz"),
                     "state": o.get("state"), "algoId": o.get("algoId")}
                    for o in resp.get("data", [])]
            except Exception as e:
                out["algo_orders_error"] = str(e)[:120]

    json.dump(out, open("okx_state.json", "w"), indent=2, default=str)
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
