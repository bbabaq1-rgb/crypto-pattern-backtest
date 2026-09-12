"""
detector_kakao_base.py — 지인 카톡 규칙 3종의 공용 부품 (2026-09-12 사전 등록).

registry `kakao_patterns_prereg_2026_09_12` 가 원문·동결 파라미터의 출처다.
여기 있는 상수는 사전 등록에 적힌 값이며 **결과를 보고 바꾸지 않는다**.
"""
import detlib

MA_FAST, MA_MID, MA_SLOW = 5, 10, 20
PIVOT_HALF   = 3     # '직전 언덕' = 피벗 반폭 3 의 스윙 고점
BREAK_WAIT   = 10    # 신호 성립 후 돌파 대기 상한(봉). 무제한이면 신호가 원인과 무관하게 늘어난다
LOW_LOOKBACK = 250   # '월봉 신저점' 1d/4h 환산 — 직전 250봉 최저
LOW_RECENT   = 20    # 그 최저가 최근 20봉 안에 있어야 '바닥'
CROSS_WITHIN = 20    # MA5 x MA20 상향 교차가 직전 20봉 내


def sma(rows, n):
    """rows[i] 까지의 종가 n 봉 단순이동평균. i < n-1 이면 None."""
    out, run = [None] * len(rows), 0.0
    for i, r in enumerate(rows):
        run += r["c"]
        if i >= n:
            run -= rows[i - n]["c"]
        if i >= n - 1:
            out[i] = run / n
    return out


def is_bull(r):
    return r["c"] > r["o"]


def is_bear(r):
    return r["c"] < r["o"]


def body_lo(r):
    return min(r["o"], r["c"])


def body_hi(r):
    return max(r["o"], r["c"])


def prior_swing_high(rows, i, half=PIVOT_HALF):
    """
    i 봉 **이전**에 확정된 가장 최근 스윙 고점 값. 인과적 — i 이후 봉을 안 본다.

    엄격 부등호(<)를 쓴다 — `<=` 면 고가가 같은 횡보 구간에서 **모든 봉이 피벗**이 되어
    평평한 구간이 '언덕' 으로 잡히고, 돌파 신호가 원인과 무관하게 늘어난다(2026-09-12
    구현 중 테스트로 발견, 실행 전 수정). 실데이터에서 고가 완전 동률은 드물고,
    동률이면 그 봉을 건너뛰고 더 과거에서 언덕을 찾는다.
    """
    j = i - half - 1
    while j >= half:
        h = rows[j]["h"]
        if all(rows[k]["h"] < h for k in range(j - half, j + half + 1) if k != j):
            return h
        j -= 1
    return None


def breakout_entries(rows, setups, level_of, wait=BREAK_WAIT):
    """
    setups = [셋업 성립 봉 i], level_of(i) -> 돌파 기준가.
    i+1 부터 wait 봉 안에 고가가 기준가를 넘으면 **그 봉**을 진입 신호로 낸다.
    같은 봉이 두 셋업에서 겹치면 한 번만.
    """
    out = set()
    for i in setups:
        lv = level_of(i)
        if lv is None:
            continue
        for j in range(i + 1, min(i + 1 + wait, len(rows))):
            if rows[j]["h"] > lv:
                out.add(j)
                break
    return sorted(out)


def at_bottom(rows, i, lookback=LOW_LOOKBACK, recent=LOW_RECENT):
    """직전 lookback 봉 최저가가 최근 recent 봉 안에 있었나 — '바닥' 의 동결 정의."""
    lo = max(0, i - lookback + 1)
    if i - lo < recent:
        return False
    seg = rows[lo:i + 1]
    m = min(r["l"] for r in seg)
    return any(r["l"] <= m for r in rows[i - recent + 1:i + 1])


def cross_up(rows, i, within=CROSS_WITHIN):
    """MA5 > MA20 이고 직전 within 봉 내에 상향 교차가 있었나."""
    f, s = sma(rows, MA_FAST), sma(rows, MA_SLOW)
    if f[i] is None or s[i] is None or f[i] <= s[i]:
        return False
    for j in range(max(1, i - within + 1), i + 1):
        if f[j - 1] is not None and s[j - 1] is not None and f[j - 1] <= s[j - 1] and f[j] > s[j]:
            return True
    return False


def load_ohlcv(sym, tf="1d"):
    return detlib.load_ohlcv(sym, tf)
