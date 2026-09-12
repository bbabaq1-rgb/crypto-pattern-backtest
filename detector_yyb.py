"""
detector_yyb.py — 양양음 (2026-09-12 사전 등록, 주 판정).

원문(김명규): "첫번째 양은 5선 밑, 두번째 양은 5선 돌파, 마지막 음은 두번째 양봉의
고점보다 낮음" / "양양음은 우상향 차트에서 유효하고 두번째 양봉의 고점을 돌파할 때
매매 가능, 매수 타점."

  셋업: r0 양봉 & 종가<MA5 · r1 양봉 & 종가>MA5 · r2 음봉 & 고가 < r1 고가
  진입: 그 뒤 **r1 고점** 을 돌파하는 봉 — 10봉 이내

'우상향 차트에서 유효' 는 원문에 정의가 없어 주 판정에 안 넣었다(레짐 분해가 진단).
"""
import detector_kakao_base as kb

load_ohlcv = kb.load_ohlcv


def setups(rows):
    f = kb.sma(rows, kb.MA_FAST)
    out = []
    for i in range(2, len(rows)):
        r0, r1, r2 = rows[i - 2], rows[i - 1], rows[i]
        if f[i - 2] is None or f[i - 1] is None:
            continue
        if (kb.is_bull(r0) and r0["c"] < f[i - 2]
                and kb.is_bull(r1) and r1["c"] > f[i - 1]
                and kb.is_bear(r2) and r2["h"] < r1["h"]):
            out.append(i)
    return out


def detect(rows):
    return kb.breakout_entries(rows, setups(rows), lambda i: rows[i - 1]["h"])
