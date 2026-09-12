"""
detector_ma3_breakout.py — 3이평 돌파 (2026-09-12 사전 등록, 주 판정).

원문(김명규): "이평돌파는 양봉 바디가 5 10 20을 덮어야 됨. 그러면 그 직전 언덕
넘을 때 매수 타점." / "바디니까 시가 종가가 덮어야지."

  셋업: 양봉이고 바디(시가~종가)가 MA5·MA10·MA20 을 전부 감싼다
  진입: 그 뒤 **직전 스윙 고점**('직전 언덕') 을 돌파하는 봉 — 10봉 이내

레포에 없던 축이다 — ma180_breakout 은 종가가 장기선을 교차하는 것이고,
donchian20·breakout_retest 는 가격 돌파다. '바디가 여러 단기선을 동시에 감싼다'는
추세 전환의 **강도**를 재는 다른 정보일 수 있다(사전 등록의 실행 근거).
"""
import detector_kakao_base as kb

load_ohlcv = kb.load_ohlcv


def setups(rows):
    f, m, s = kb.sma(rows, kb.MA_FAST), kb.sma(rows, kb.MA_MID), kb.sma(rows, kb.MA_SLOW)
    out = []
    for i, r in enumerate(rows):
        if f[i] is None or m[i] is None or s[i] is None or not kb.is_bull(r):
            continue
        if kb.body_lo(r) <= min(f[i], m[i], s[i]) and kb.body_hi(r) >= max(f[i], m[i], s[i]):
            out.append(i)
    return out


def detect(rows):
    return kb.breakout_entries(rows, setups(rows), lambda i: kb.prior_swing_high(rows, i))
