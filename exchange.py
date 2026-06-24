"""
exchange.py — 비트겟 데모(샌드박스) 연결. 실주문 절대 없음(읽기 전용).

키: 환경변수 BITGET_DEMO_KEY / BITGET_DEMO_SECRET / BITGET_DEMO_PASSPHRASE.
연결되면 데모 잔고 조회까지. 키 없거나 실패 시 '시뮬레이션 모드'로 폴백
(체결은 로컬에서 시가 가정으로만 기록).

※ 주문 생성 함수는 의도적으로 미구현 — 페이퍼테스트는 로컬 모의 체결만 한다.
"""
import os


def connect():
    key = os.environ.get("BITGET_DEMO_KEY")
    sec = os.environ.get("BITGET_DEMO_SECRET")
    pw = os.environ.get("BITGET_DEMO_PASSPHRASE")
    if not (key and sec and pw):
        return {"mode": "simulation", "exchange": None, "balance": None,
                "note": "데모 키 없음 -> 시뮬레이션 모드(시가 체결 가정, 로컬 기록만)"}
    try:
        import ccxt
        ex = ccxt.bitget({"apiKey": key, "secret": sec, "password": pw,
                          "enableRateLimit": True})
        ex.set_sandbox_mode(True)                 # 데모/샌드박스
        bal = ex.fetch_balance()
        usdt = bal.get("USDT", {}).get("total")
        return {"mode": "demo", "exchange": ex, "balance": usdt,
                "note": "비트겟 데모 연결 성공(읽기 전용; 주문 미사용)"}
    except Exception as e:
        return {"mode": "simulation", "exchange": None, "balance": None,
                "note": f"데모 연결 실패 -> 시뮬레이션 폴백: {str(e)[:80]}"}


if __name__ == "__main__":
    c = connect()
    print(f"mode={c['mode']} | balance={c['balance']} | {c['note']}")
