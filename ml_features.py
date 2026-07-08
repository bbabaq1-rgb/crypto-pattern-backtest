"""
ml_features.py — 기존 1d 패턴 신호의 '메타-필터' 학습용 특징/라벨 추출.

철학: 디텍터(결정론)를 대체하지 않는다. 기존 신호(engulfing·fvg·inverted_hammer·
marubozu 롱/숏)를 '후보'로 두고, 각 신호가 방식D에서 수익 낼지를 예측하는 메타모델.
모든 특징은 '진입 봉 시점'까지의 정보만 사용(look-ahead 없음). 이미지 아님 — 숫자만.

라벨: 방식D 수익률(회귀) + 이진(수익>0).
특징(진입 봉 기준, causal):
  - 패턴/방향 원핫
  - 모멘텀: 5/10/20봉 수익률
  - 이동평균 이격: c/SMA20, c/SMA50
  - 변동성: 20봉 수익률 표준편차, ATR14/price
  - 거래량비: v / 20봉 평균
  - 위치: 20봉 고저 범위 내 위치(0~1)
  - RSI14
  - BTC 대비: rs_score, cap_score
  - 시장 레짐: 진입일 유니버스 avg_cap(브레드스)
  - BTC 자체 모멘텀: BTC 10봉 수익률
"""
import statistics as st

import detlib
from method_d import outcome_d
from method_e import PATS_ALL
from relative_strength import compute_rs, compute_capture

import importlib

PATTERNS = ["engulfing", "fvg", "engulfing_short", "fvg_short",
            "inverted_hammer", "marubozu"]

FEATURE_NAMES = (
    [f"pat_{p}" for p in PATTERNS] + ["is_long"] +
    ["mom5", "mom10", "mom20", "ma20_gap", "ma50_gap",
     "vol20", "atr_pct", "vol_ratio", "range_pos", "rsi14",
     "rs_score", "cap_score", "mkt_avg_cap", "btc_mom10"]
)


def _sma(vals, n, i):
    if i + 1 < n:
        return None
    return sum(vals[i - n + 1:i + 1]) / n


def _rsi(closes, i, n=14):
    if i < n:
        return 50.0
    g = l = 0.0
    for k in range(i - n + 1, i + 1):
        d = closes[k] - closes[k - 1]
        g += max(d, 0); l += max(-d, 0)
    ag, al = g / n, l / n
    return 100.0 if al == 0 else 100 - 100 / (1 + ag / al)


def _atr(rows, i, n=14):
    if i < n:
        return None
    s = 0.0
    for k in range(i - n + 1, i + 1):
        pc = rows[k - 1]["c"]
        s += max(rows[k]["h"] - rows[k]["l"], abs(rows[k]["h"] - pc), abs(rows[k]["l"] - pc))
    return s / n


def build_dataset(mkt_avg_cap=None):
    """
    반환: (X[list[list]], y_ret[list], y_bin[list], meta[list[dict]])
    meta: {"date","symbol","pattern","direction"} — 워크포워드 분할·평가용.
    mkt_avg_cap: {date: 유니버스 avg_cap} (없으면 backtest_regime_capture.build_breadth).
    """
    if mkt_avg_cap is None:
        from backtest_regime_capture import build_breadth
        mkt_avg_cap, _, _ = build_breadth()

    btc = detlib.load_ohlcv("BTC", "1d")
    btc_close = [r["c"] for r in btc]
    btc_ret10 = {}
    for i in range(len(btc)):
        if i >= 10 and btc_close[i - 10] > 0:
            btc_ret10[btc[i]["date"]] = btc_close[i] / btc_close[i - 10] - 1

    X, y_ret, y_bin, meta = [], [], [], []
    pat_index = {p: k for k, p in enumerate(PATTERNS)}

    for label, direction, detmod, oppmod in PATS_ALL:
        mod = importlib.import_module(detmod)
        opp = importlib.import_module(oppmod) if oppmod else None
        for sym in detlib.SYMBOLS:
            if sym == "BTC":
                continue
            try:
                rows = mod.load_ohlcv(sym, "1d")
            except FileNotFoundError:
                continue
            closes = [r["c"] for r in rows]
            vols = [r["v"] for r in rows]
            opp_set = set(opp.detect(rows)) if opp else set()
            for si in mod.detect(rows):
                d = rows[si]["date"]
                if d not in mkt_avg_cap or si < 55:
                    continue
                ret, _hold = outcome_d(rows, si, direction, opp_set)

                # 특징(진입 봉 si 기준, causal)
                def mom(n):
                    return closes[si] / closes[si - n] - 1 if closes[si - n] > 0 else 0.0
                sma20 = _sma(closes, 20, si); sma50 = _sma(closes, 50, si)
                rr = [closes[k] / closes[k - 1] - 1 for k in range(si - 19, si + 1) if closes[k - 1] > 0]
                vol20 = st.pstdev(rr) if len(rr) > 1 else 0.0
                atr = _atr(rows, si)
                vavg = sum(vols[si - 19:si + 1]) / 20 if si >= 19 else vols[si]
                hi20 = max(r["h"] for r in rows[si - 19:si + 1])
                lo20 = min(r["l"] for r in rows[si - 19:si + 1])
                rng = (hi20 - lo20) or 1e-9
                rs = compute_rs(rows, btc, idx=si, symbol=sym)["rs_score"]
                cap = compute_capture(rows, btc, idx=si, symbol=sym)["cap_score"]

                onehot = [0] * len(PATTERNS)
                onehot[pat_index[label]] = 1
                feat = onehot + [
                    1 if direction == "long" else 0,
                    mom(5), mom(10), mom(20),
                    (closes[si] / sma20 - 1) if sma20 else 0.0,
                    (closes[si] / sma50 - 1) if sma50 else 0.0,
                    vol20,
                    (atr / closes[si]) if atr and closes[si] else 0.0,
                    (vols[si] / vavg) if vavg else 1.0,
                    (closes[si] - lo20) / rng,
                    _rsi(closes, si) / 100.0,
                    rs if rs is not None else 0.0,
                    cap if cap is not None else 0.0,
                    mkt_avg_cap[d],
                    btc_ret10.get(d, 0.0),
                ]
                X.append(feat); y_ret.append(ret); y_bin.append(1 if ret > 0 else 0)
                meta.append({"date": d, "symbol": sym, "pattern": label, "direction": direction})
    return X, y_ret, y_bin, meta


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    X, yr, yb, meta = build_dataset()
    print(f"샘플 {len(X)}건, 특징 {len(X[0])}개")
    print(f"수익 라벨 평균 {st.mean(yr)*100:+.2f}%, 이진 승률 {st.mean(yb)*100:.1f}%")
    print(f"기간 {min(m['date'] for m in meta)} ~ {max(m['date'] for m in meta)}")
    print("특징명:", FEATURE_NAMES)
