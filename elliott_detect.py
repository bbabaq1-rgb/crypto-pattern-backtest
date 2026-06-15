"""
결정론적 엘리엇 파동 라벨링 — detect() 구현 예시

설계 원칙
  1) ZigZag 로 스윙 피벗(고점/저점)을 추출한다  → 파동의 골격
  2) 엘리엇 '절대 규칙' 3가지로 5파 임펄스 구조를 검증한다 (위반 시 무효)
  3) 피보나치 '가이드라인' 충족도로 confidence(0~1)를 계산한다
  4) 마지막 피벗 위치로 '현재 몇 파 / 상승·하락 구간'을 추정한다

중요(지난 대화의 연장선):
  여기서 나오는 confidence 는 '규칙 충족 점수'이지 보정된 확률이 아니다.
  이 값을 매매 임계값으로 쓰려면 반드시 과거 데이터 백테스트로 보정해야 한다.
  이 코드는 재현 가능 + 백테스트 가능하다는 점이 LLM hot-path 대비 핵심 장점이다.
"""

from dataclasses import dataclass, field
from typing import Optional


# ----------------------------------------------------------------------
# 데이터 구조
# ----------------------------------------------------------------------
@dataclass
class Pivot:
    index: int      # 캔들 인덱스
    price: float    # 피벗 가격
    kind: str       # "H"(고점) | "L"(저점)


@dataclass
class Signal:
    pattern: str                 # 예: "elliott_impulse_up"
    direction: str               # "up" | "down" | "none"
    confidence: float            # 0.0~1.0 (규칙 충족 점수 — 보정 필요)
    current_wave: Optional[str] = None   # 예: "wave_3", "wave_4"
    detail: dict = field(default_factory=dict)


# ----------------------------------------------------------------------
# 1) ZigZag 피벗 추출 (퍼센트 반전 기준 — 완전 결정론적)
# ----------------------------------------------------------------------
def zigzag(prices, threshold=0.05):
    """
    종가 시퀀스에서 threshold(예: 5%) 이상 반전할 때마다 스윙 피벗을 확정.
    '드래그형' 상태기계: 추세가 이어지면 마지막 피벗을 극값으로 끌고 가고,
    threshold 이상 반전하면 새 피벗을 확정한다. 같은 입력이면 항상 같은 결과.
    """
    n = len(prices)
    if n < 2:
        return []

    idx = [0]              # 확정/잠정 피벗의 인덱스
    val = [prices[0]]      # 확정/잠정 피벗의 가격
    direction = 0          # +1 상승 / -1 하락 / 0 미정

    for i in range(1, n):
        p = prices[i]
        cur_idx, cur_price = idx[-1], val[-1]

        if direction == 1:                       # 상승 진행
            if p > cur_price:
                idx[-1], val[-1] = i, p          # 고점을 위로 드래그
            elif (cur_price - p) / cur_price >= threshold:
                idx.append(i); val.append(p); direction = -1   # 하락 반전
        elif direction == -1:                    # 하락 진행
            if p < cur_price:
                idx[-1], val[-1] = i, p          # 저점을 아래로 드래그
            elif (p - cur_price) / cur_price >= threshold:
                idx.append(i); val.append(p); direction = 1    # 상승 반전
        else:                                    # 방향 미정 → 첫 임계 돌파로 결정
            if (p - cur_price) / cur_price >= threshold:
                idx.append(i); val.append(p); direction = 1
            elif (cur_price - p) / cur_price >= threshold:
                idx.append(i); val.append(p); direction = -1

    if len(val) < 2:
        return []

    # 가격 비교로 H/L 라벨 부여 (첫 피벗은 두 번째 피벗 기준 역방향)
    pivots = []
    for k in range(len(val)):
        if k == 0:
            kind = "L" if val[1] > val[0] else "H"
        else:
            kind = "H" if val[k] > val[k - 1] else "L"
        pivots.append(Pivot(idx[k], val[k], kind))

    return pivots


# ----------------------------------------------------------------------
# 2)+3) 엘리엇 5파 임펄스 검증 + confidence 계산
# ----------------------------------------------------------------------
def _abs(a, b):
    return abs(b - a)


def label_impulse_up(p):
    """
    상승 임펄스 후보: 6개 피벗(저-고-저-고-저-고) = 0~5파.
    p = [P0(L), P1(H), P2(L), P3(H), P4(L), P5(H)]
    """
    P0, P1, P2, P3, P4, P5 = (x.price for x in p)

    w1 = _abs(P0, P1)   # 1파 길이
    w3 = _abs(P2, P3)   # 3파 길이
    w5 = _abs(P4, P5)   # 5파 길이

    # --- 절대 규칙 (하나라도 위반하면 임펄스 아님) ---
    rule2 = P2 > P0                       # 2파는 1파 시작점 아래로 안 감
    rule3 = not (w3 < w1 and w3 < w5)     # 3파는 1·3·5 중 최단이 아님
    rule4 = P4 > P1                       # 4파는 1파 영역 침범 안 함(임펄스)
    valid = rule2 and rule3 and rule4

    if not valid:
        return dict(valid=False,
                    rules=dict(rule2=rule2, rule3=rule3, rule4=rule4))

    # --- 가이드라인 (충족도로 confidence 가산) ---
    retr2 = _abs(P1, P2) / w1 if w1 else 0     # 2파 되돌림 비율
    retr4 = _abs(P3, P4) / w3 if w3 else 0     # 4파 되돌림 비율
    ext3  = w3 / w1 if w1 else 0               # 3파/1파 확장 배수

    score = 0.40                               # 절대 규칙 통과 기본점
    # 3파가 가장 김 (전형적 강세)
    if w3 >= w1 and w3 >= w5:        score += 0.15
    # 2파 되돌림이 전형 구간(0.5~0.786)
    if 0.45 <= retr2 <= 0.80:        score += 0.12
    # 4파 되돌림이 전형 구간(0.236~0.5)
    if 0.20 <= retr4 <= 0.55:        score += 0.12
    # 3파 확장이 1.618 부근
    if 1.5 <= ext3 <= 2.8:           score += 0.11
    # 교대 원칙: 2파와 4파 되돌림 깊이가 충분히 다름
    if abs(retr2 - retr4) >= 0.15:   score += 0.10

    confidence = round(min(score, 1.0), 3)
    return dict(valid=True,
                confidence=confidence,
                rules=dict(rule2=rule2, rule3=rule3, rule4=rule4),
                fib=dict(retr2=round(retr2, 3), retr4=round(retr4, 3),
                         ext3=round(ext3, 3)),
                waves=dict(w1=round(w1, 4), w3=round(w3, 4), w5=round(w5, 4)))


# ----------------------------------------------------------------------
# 현재 진행 파동 추정
# ----------------------------------------------------------------------
def _current_wave(pivots_used, total_pivots, last_kind):
    """
    완성된 5파(피벗6) 뒤 마지막 잠정 피벗이 어느 파동 진행 중인지 추정.
    """
    n = total_pivots
    if n <= 6:
        # 아직 5파가 다 안 나옴 → 피벗 개수로 진행 파동 매핑
        mapping = {2: "wave_1", 3: "wave_2", 4: "wave_3",
                   5: "wave_4", 6: "wave_5"}
        return mapping.get(n, "forming")
    # 5파 완성 이후 추가 피벗 → 조정(ABC) 진입으로 본다
    return "correction_ABC"


# ----------------------------------------------------------------------
# 공개 함수: detect()
# ----------------------------------------------------------------------
def detect(candles, zigzag_threshold=0.05) -> Signal:
    """
    candles: 종가 리스트 또는 ccxt OHLCV 리스트([ts,o,h,l,c,v]).
    반환: Signal(pattern, direction, confidence, current_wave, detail)
    """
    # 종가 추출 (둘 다 지원)
    if candles and isinstance(candles[0], (list, tuple)):
        prices = [c[4] for c in candles]      # OHLCV의 close
    else:
        prices = list(candles)

    pivots = zigzag(prices, zigzag_threshold)
    if len(pivots) < 2:
        return Signal("none", "none", 0.0, "forming",
                      {"reason": "피벗 부족"})

    # 현재 진행 방향: 마지막 두 피벗으로 판정
    last = pivots[-1]
    direction = "up" if last.kind == "H" else "down"

    # 가장 최근의 상승 임펄스 후보(저점에서 시작하는 6피벗)를 찾는다
    best = None
    for start in range(len(pivots) - 6, -1, -1):
        window = pivots[start:start + 6]
        if len(window) < 6:
            continue
        if [w.kind for w in window] == ["L", "H", "L", "H", "L", "H"]:
            res = label_impulse_up(window)
            if res["valid"]:
                best = (start, window, res)
                break

    if best is None:
        # 임펄스 구조 미검출 → 패턴 없음(또는 조정 진행)
        return Signal("no_clear_impulse", direction, 0.0,
                      _current_wave(None, len(pivots), last.kind),
                      {"pivots": len(pivots)})

    start, window, res = best
    current = _current_wave(window, len(pivots), last.kind)

    return Signal(
        pattern="elliott_impulse_up",
        direction=direction,
        confidence=res["confidence"],
        current_wave=current,
        detail={
            "rules": res["rules"],
            "fib": res["fib"],
            "waves": res["waves"],
            "pivot_count": len(pivots),
            "impulse_pivots": [(p.index, round(p.price, 2), p.kind)
                               for p in window],
        },
    )


# ----------------------------------------------------------------------
# 데모: 합성 엘리엇 5파 데이터로 동작 확인
# ----------------------------------------------------------------------
def _synthetic_elliott():
    """0→1파↑ 2파↓ 3파↑(확장) 4파↓ 5파↑ 형태의 종가 시퀀스 생성."""
    import math
    def leg(start, end, n):
        return [start + (end - start) * (i / (n - 1)) for i in range(n)]
    seq = []
    seq += leg(100, 120, 20)    # 1파 ↑
    seq += leg(120, 110, 12)    # 2파 ↓ (0.5 되돌림)
    seq += leg(110, 150, 30)    # 3파 ↑ (확장)
    seq += leg(150, 138, 14)    # 4파 ↓ (0.3 되돌림)
    seq += leg(138, 160, 22)    # 5파 ↑
    # 미세 노이즈(결정론적: sin 기반)
    return [round(p + 0.4 * math.sin(i / 2), 4) for i, p in enumerate(seq)]


if __name__ == "__main__":
    prices = _synthetic_elliott()
    sig = detect(prices, zigzag_threshold=0.05)

    print("=== detect() 결과 ===")
    print(f"pattern      : {sig.pattern}")
    print(f"direction    : {sig.direction}")
    print(f"current_wave : {sig.current_wave}")
    print(f"confidence   : {sig.confidence}")
    print("--- detail ---")
    for k, v in sig.detail.items():
        print(f"{k:14}: {v}")
