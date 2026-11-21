"""
detector_turtle_soup_4h.py — Turtle Soup (Connors/Raschke) 4h 롱 (R-009, 2026-11-21 사전 등록).

정의(동결, 닫힌 봉 i 에서 판정 — 미래 봉 미사용):
  (1) 직전 LOOKBACK(20)봉 최저가 L = min(low[i-20..i-1]) 이고 그 저점이 MIN_AGE(4)봉 이상 전에 형성
      (가장 최근 최저 위치 j 가 i - j >= MIN_AGE — Raschke 의 '신저점이 4일 이상 전'),
  (2) 현재 봉 저가가 L 아래로 이탈(low[i] < L),
  (3) 같은 봉 종가가 L 위로 복귀(close[i] > L).
  → 롱 신호(가짜 돌파 반전). 진입은 봉 i 종가(닫힌 봉).

liquidity_sweep(기각)과의 차이: sweep 은 Equal Lows 풀(저점 2개 이상 0.5% 이내) + 침투 깊이 0.5% 이상 +
복귀를 RECOVER_BARS(3)봉 안에 + 거래량 2배 를 요구한다. Turtle Soup 은 풀·깊이·거래량 조건이 없고
단일 20봉 저점의 같은 봉 복귀만 본다 — 신호 집합이 훨씬 넓다(겹침은 검증 러너에서 진단으로 측정).
"""
import detlib

LOOKBACK = 20
MIN_AGE = 4


def detect(rows):
    sig = []
    for i in range(LOOKBACK, len(rows)):
        win = [rows[k]["l"] for k in range(i - LOOKBACK, i)]
        lo = min(win)
        # 가장 최근에 그 최저가가 찍힌 위치
        j = max(k for k in range(i - LOOKBACK, i) if rows[k]["l"] == lo)
        if i - j < MIN_AGE:
            continue
        if rows[i]["l"] < lo and rows[i]["c"] > lo:
            sig.append(i)
    return sig


def load_ohlcv(sym, tf="4h"):
    return detlib.load_ohlcv(sym, tf)


evaluate = detlib.make_evaluate(detect, direction="long")
