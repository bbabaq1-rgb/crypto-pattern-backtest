"""
notify.py — 텔레그램 알림 (베스트에포트).

TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 환경변수(.env 또는 GitHub Secrets)가
설정된 경우에만 발송. 미설정·실패 시 조용히 스킵 — 알림 실패가 매매 파이프라인을
절대 막지 않는다(print로 로그만).

설정 방법(1회):
  1. 텔레그램에서 @BotFather → /newbot → 토큰 발급
  2. 봇과 대화 시작(아무 메시지) 후 https://api.telegram.org/bot<토큰>/getUpdates
     에서 chat.id 확인
  3. GitHub repo Settings → Secrets → TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID 등록
     (워크플로 env는 이미 연결됨)
"""
import os


def available() -> bool:
    return bool(os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"))


def send(text: str) -> bool:
    """텔레그램 메시지 발송. 성공 True. 미설정/실패 시 False(예외 없음)."""
    if not available():
        return False
    try:
        import requests
        token = os.environ["TELEGRAM_BOT_TOKEN"]
        chat  = os.environ["TELEGRAM_CHAT_ID"]
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
        ok = r.status_code == 200
        if not ok:
            print(f"[notify] 텔레그램 실패 {r.status_code}: {r.text[:80]}")
        return ok
    except Exception as e:
        print(f"[notify] 텔레그램 오류(무시): {str(e)[:80]}")
        return False


if __name__ == "__main__":
    print("available:", available())
    if available():
        print("sent:", send("🔔 crypto-pattern-backtest 알림 테스트"))
