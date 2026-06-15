"""
터미널(Terminal) / 엔딩 다이애고널 detector — detect_terminal()

elliott_detect.py 와 같은 폴더에 두고 사용한다 (zigzag/Signal 재사용).

개념(닐리 NEoWave / 엘리엇 다이애고널):
  - 5분절(피벗 6개)의 쐐기(wedge)형 패턴, 1~5로 라벨링.
  - 핵심 특징: 4파가 1파의 가격영역을 '겹친다(overlap)'  ← 일반 임펄스의 정반대.
  - 각 다리는 3파(조정) 구조. 보통 수렴형(contracting): 파동 크기가 점점 작아짐.
  - 위치: 큰 5파 임펄스의 5파, 또는 ABC 조정의 C파 끝 → 추세 소진/반전 신호.

코드화 분류:
  ✅ 1·4파 겹침, 쐐기 수렴, 고점·저점 진행, 파동 축소  → 좌표로 정확히 판정
  ⚙️ '각 다리가 3파' (하위 타임프레임 분석 필요 → 여기선 생략/근사)
  ⚠️ '정말 터미널 위치인가'(상위 구조의 5파/C파인지)는 상위 컨텍스트 필요
"""

from elliott_detect import zigzag, Signal, Pivot


def _slope(p_start: Pivot, p_end: Pivot):
    di = p_end.index - p_start.index
    return (p_end.price - p_start.price) / di if di else 0.0


def label_terminal_up(p):
    """
    상승 터미널 후보: P0(L) P1(H) P2(L) P3(H) P4(L) P5(H)
    (하락 반전을 예고하는 라이징 웨지)
    """
    P0, P1, P2, P3, P4, P5 = (x.price for x in p)
    w1, w3, w5 = abs(P1 - P0), abs(P3 - P2), abs(P5 - P4)

    # --- 터미널 핵심 조건 ---
    higher_highs = P1 < P3 < P5            # 고점 상승 (전진은 계속)
    higher_lows  = P0 < P2 < P4            # 저점 상승
    overlap      = P4 < P1                 # ★ 4파가 1파 고점 아래로 = 겹침(터미널의 정의)

    # 쐐기 수렴: 상단선(P1→P5) 기울기 < 하단선(P0→P4) 기울기
    slope_up  = _slope(p[1], p[5])
    slope_low = _slope(p[0], p[4])
    converging = slope_up < slope_low

    valid = higher_highs and higher_lows and overlap
    if not valid:
        return dict(valid=False,
                    checks=dict(higher_highs=higher_highs,
                                higher_lows=higher_lows, overlap=overlap))

    # --- confidence (규칙 충족 점수) ---
    score = 0.45                                   # 핵심 3조건 통과 기본점
    if converging:                  score += 0.20  # 수렴형 쐐기
    if w1 > w3 > w5:                score += 0.20  # 파동이 점점 작아짐(소진)
    elif w1 > w5:                   score += 0.08  # 약하게라도 축소
    # 5파가 상단선을 살짝 돌파(throw-over) 후 되돌릴 때 신뢰도↑ (간이판정)
    if P5 > P3 and (P5 - P3) < (P3 - P1):  score += 0.10
    if not converging and slope_up > slope_low:    # 확산형이면 감점
        score -= 0.15

    confidence = round(max(0.0, min(score, 1.0)), 3)
    return dict(valid=True, confidence=confidence,
                checks=dict(higher_highs=True, higher_lows=True,
                            overlap=True, converging=converging),
                geom=dict(slope_upper=round(slope_up, 4),
                          slope_lower=round(slope_low, 4),
                          w1=round(w1, 3), w3=round(w3, 3), w5=round(w5, 3)))


def detect_terminal(candles, zigzag_threshold=0.03) -> Signal:
    """
    상승 터미널(라이징 웨지) 탐지. 발견 시 direction='down'(반전 예고).
    하락 터미널(폴링 웨지)은 가격 부호를 뒤집어 동일 로직으로 확장 가능.
    """
    if candles and isinstance(candles[0], (list, tuple)):
        prices = [c[4] for c in candles]
    else:
        prices = list(candles)

    pivots = zigzag(prices, zigzag_threshold)
    if len(pivots) < 6:
        return Signal("none", "none", 0.0, "forming",
                      {"reason": "피벗 부족", "pivots": len(pivots)})

    # 최근의 6피벗 쐐기 후보를 뒤에서부터 탐색
    for start in range(len(pivots) - 6, -1, -1):
        window = pivots[start:start + 6]
        if [w.kind for w in window] != ["L", "H", "L", "H", "L", "H"]:
            continue
        res = label_terminal_up(window)
        if res["valid"]:
            # 5파 완성 후 하단선 이탈 여부로 '완료/반전 확정' 판단
            lower_now = window[4].price  # 마지막 저점(간이 하단선 근사)
            broke_down = prices[-1] < lower_now
            return Signal(
                pattern="terminal_rising_wedge",
                direction="down",                 # 상승 터미널 → 하락 반전 예고
                confidence=res["confidence"],
                current_wave="post_terminal" if broke_down else "wave_5_or_forming",
                detail={
                    "checks": res["checks"],
                    "geom": res["geom"],
                    "broke_lower_line": broke_down,
                    "wedge_pivots": [(p.index, round(p.price, 2), p.kind)
                                     for p in window],
                },
            )

    return Signal("no_terminal", "none", 0.0, "forming",
                  {"pivots": len(pivots)})


# ----------------------------------------------------------------------
if __name__ == "__main__":
    import math
    def leg(a, b, n):
        return [a + (b - a) * (i / (n - 1)) for i in range(n)]

    # 라이징 웨지: 고점·저점 모두 상승하되 4파가 1파 고점 아래(겹침), 수렴·축소
    seq = (leg(100, 120, 20) + leg(120, 110, 13) + leg(110, 126, 25)
           + leg(126, 117, 14) + leg(117, 130, 20) + leg(130, 108, 16))  # 마지막=하단 이탈
    prices = [round(p + 0.3 * math.sin(i / 2), 4) for i, p in enumerate(seq)]

    sig = detect_terminal(prices, zigzag_threshold=0.03)
    print("=== detect_terminal() ===")
    print(f"pattern      : {sig.pattern}")
    print(f"direction    : {sig.direction}")
    print(f"current_wave : {sig.current_wave}")
    print(f"confidence   : {sig.confidence}")
    for k, v in sig.detail.items():
        print(f"{k:16}: {v}")
