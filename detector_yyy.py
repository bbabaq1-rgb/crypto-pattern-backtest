"""
detector_yyy.py — 양양양 (2026-09-12 사전 등록).

원문(김명규): "양양양이 완성되고 그 마지막 양의 고점 돌파 시" 매수.
**모양·크기 조건 없음** — 김승준 "캔들 말하는 거지 모양이나 크기 없고" → 김명규 "응".
그래서 기본(plain)은 배포된 three_soldiers_4h(바디>=60%·위꼬리<=20%·종가 계단상승)와
**조건이 다르다**. 배포 디텍터는 건드리지 않는다.

mode:
  plain  (주 판정) 3연속 양봉 + 3봉 고점 돌파 진입
  strict (진단)    배포 three_soldiers 조건 + 고점 돌파 진입
  bottom (진단)    plain + 바닥 필터(직전 250봉 최저가가 최근 20봉 안)
  cross  (진단)    plain + MA5 x MA20 상향 교차(직전 20봉 내)
  close  (진단)    plain 인데 진입이 3봉 **종가** — 배포판과 같은 진입, 프레임 정합성 확인
"""
import detector_kakao_base as kb

load_ohlcv = kb.load_ohlcv

BODY_RATIO, UPPER_RATIO = 0.60, 0.20   # 배포 three_soldiers_4h 와 같은 값(strict 전용)


def _white_strict(r):
    body, rng = r["c"] - r["o"], (r["h"] - r["l"]) or 1e-9
    return body > 0 and body / rng >= BODY_RATIO and (r["h"] - r["c"]) / rng <= UPPER_RATIO


def setups(rows, mode="plain"):
    out = []
    for i in range(2, len(rows)):
        r0, r1, r2 = rows[i - 2], rows[i - 1], rows[i]
        if mode == "strict":
            ok = (_white_strict(r0) and _white_strict(r1) and _white_strict(r2)
                  and r1["c"] > r0["c"] and r2["c"] > r1["c"])
        else:
            ok = kb.is_bull(r0) and kb.is_bull(r1) and kb.is_bull(r2)
        if not ok:
            continue
        if mode == "bottom" and not kb.at_bottom(rows, i):
            continue
        if mode == "cross" and not kb.cross_up(rows, i):
            continue
        out.append(i)
    return out


def detect(rows, mode="plain"):
    st = setups(rows, mode)
    if mode == "close":
        return st                      # 배포판과 같은 진입(3봉 종가)
    return kb.breakout_entries(rows, st, lambda i: rows[i]["h"])
