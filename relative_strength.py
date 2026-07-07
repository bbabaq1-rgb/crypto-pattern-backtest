"""
relative_strength.py — BTC 대비 상대강도(RS) 모듈.

계산 (모두 결정론적, 종가 기준):
  1. 롤링 베타: 최근 BETA_N(90)봉 일별수익률 회귀 — beta = Cov(alt,btc)/Var(btc).
     표본 < 90봉이면 beta=1.0 + unstable=True.
  2. 기간별 RS: N∈{7,14,30}봉 각각 RS_N = alt누적수익률 − beta×BTC누적수익률.
     RS>0 = BTC 대비 초과성과.
  3. rs_score: 가중평균(단기 0.5 / 중기 0.3 / 장기 0.2) 후 [-1,+1] 정규화.
     정규화: clip(가중RS / SCALE, -1, +1), SCALE=0.20 — 가중 초과수익 ±20%에서
     포화. (판단 근거: 1d 알트의 한 달 BTC 대비 ±20% 초과면 극단적 강/약 —
     tanh 대신 clip을 써서 해석이 직관적이고 역산 가능하게 유지)

BTC 자신은 RS=0 기준점(rs_score=0.0, beta=1.0).
정렬: 날짜 문자열 기준 교집합만 사용(상장 시차·결측 안전).
"""
from __future__ import annotations

BETA_N   = 90
RS_SPANS = ((7, 0.5), (14, 0.3), (30, 0.2))
SCALE    = 0.20


def _aligned_closes(alt_rows, btc_rows, idx=None):
    """idx(알트 기준 봉 인덱스, None=최신)까지 날짜 정렬된 (alt, btc) 종가 리스트."""
    if idx is None:
        idx = len(alt_rows) - 1
    btc_by_date = {r["date"]: r["c"] for r in btc_rows}
    a, b = [], []
    for r in alt_rows[: idx + 1]:
        c = btc_by_date.get(r["date"])
        if c is not None:
            a.append(r["c"]); b.append(c)
    return a, b


def _returns(closes):
    return [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes))
            if closes[i - 1] > 0]


def compute_rs(alt_rows, btc_rows, idx=None, symbol=None):
    """
    반환: {"beta", "unstable", "rs": {7:…,14:…,30:…}, "rs_score"}
    idx: 알트 rows 기준 '해당 봉 시점'까지만 사용(백테스트 look-ahead 방지).
    """
    if symbol == "BTC":
        return {"beta": 1.0, "unstable": False,
                "rs": {n: 0.0 for n, _ in RS_SPANS}, "rs_score": 0.0}

    a, b = _aligned_closes(alt_rows, btc_rows, idx)
    if len(a) < 8:                     # 최소한 7봉 RS도 못 구하면 중립
        return {"beta": 1.0, "unstable": True,
                "rs": {n: 0.0 for n, _ in RS_SPANS}, "rs_score": 0.0}

    # 1) 롤링 베타 (최근 BETA_N봉 일별수익률)
    ra, rb = _returns(a[-(BETA_N + 1):]), _returns(b[-(BETA_N + 1):])
    m = min(len(ra), len(rb))
    ra, rb = ra[-m:], rb[-m:]
    unstable = m < BETA_N
    beta = 1.0
    if m >= 20:                        # 최소 표본에서만 회귀(그 미만은 기본 1.0)
        mb = sum(rb) / m
        var = sum((x - mb) ** 2 for x in rb) / m
        if var > 0:
            ma_ = sum(ra) / m
            cov = sum((ra[i] - ma_) * (rb[i] - mb) for i in range(m)) / m
            beta = cov / var
    if m < BETA_N:
        beta = 1.0                     # 스펙: 90봉 미만이면 기본값 + unstable

    # 2) 기간별 RS
    rs = {}
    for n, _w in RS_SPANS:
        if len(a) > n and a[-n - 1] > 0 and b[-n - 1] > 0:
            alt_ret = a[-1] / a[-n - 1] - 1
            btc_ret = b[-1] / b[-n - 1] - 1
            rs[n] = alt_ret - beta * btc_ret
        else:
            rs[n] = 0.0

    # 3) 가중 평균 → [-1,+1] 정규화
    weighted = sum(rs[n] * w for n, w in RS_SPANS)
    score = max(-1.0, min(1.0, weighted / SCALE))
    return {"beta": round(beta, 4), "unstable": unstable,
            "rs": {n: round(v, 5) for n, v in rs.items()},
            "rs_score": round(score, 4)}


def rs_emoji(score):
    """대시보드 표시: 💪 강함(>0.2) / 😐 중립 / 🥱 약함(<-0.2)."""
    if score is None:
        return "—"
    if score > 0.2:
        return "💪"
    if score < -0.2:
        return "🥱"
    return "😐"


if __name__ == "__main__":
    import sys, detlib
    sys.stdout.reconfigure(encoding="utf-8")
    btc = detlib.load_ohlcv("BTC", "1d")
    for s in ("ETH", "SOL", "ADA", "COMP", "GLM"):
        try:
            alt = detlib.load_ohlcv(s, "1d")
        except Exception:
            continue
        r = compute_rs(alt, btc, symbol=s)
        print(f"{s:5} beta={r['beta']:+.2f} rs7={r['rs'][7]*100:+.1f}% "
              f"rs14={r['rs'][14]*100:+.1f}% rs30={r['rs'][30]*100:+.1f}% "
              f"score={r['rs_score']:+.2f} {rs_emoji(r['rs_score'])}"
              + (" [unstable]" if r["unstable"] else ""))
