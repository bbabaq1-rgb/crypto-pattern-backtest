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

CAPTURE_N   = 60     # 상승/하락 포착 계산 윈도우(각 방향 표본 충분해야 함)
CAP_MIN_DAY = 8      # 상승일·하락일 각각 최소 표본(미달 시 중립)
CAP_SCALE   = 1.0    # cap_score 정규화 스케일(up_cap - down_cap 를 ±1로)


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


def compute_capture(alt_rows, btc_rows, idx=None, symbol=None):
    """
    상승/하락 비대칭 포착 지표 — '비트 오를 때 알트가 얼마나 따라 오르고,
    비트 빠질 때 얼마나 더 빠지는가'를 방향별로 분리(사용자 지적 반영).

    최근 CAPTURE_N봉을 BTC 상승일/하락일로 나눠:
      up_capture   = Σ(alt수익 | BTC>0) / Σ(BTC수익 | BTC>0)   # 랠리 참여도
      down_capture = Σ(alt수익 | BTC<0) / Σ(BTC수익 | BTC<0)   # 하락 동조도(>1=더 빠짐)
      cap_score    = clip((up_capture − down_capture)/CAP_SCALE, -1, +1)
        cap_score>0 : 오를 때 잘 따라오르고 빠질 때 덜 빠짐(강한 알트)
        cap_score<0 : 오를 땐 찔끔, 빠질 땐 왕창(약한 알트 — 사용자가 말한 그 경우)
    반환: {"up_capture","down_capture","cap_score","unstable"}
    BTC 자신은 up=down=1, cap_score=0 기준점.
    """
    if symbol == "BTC":
        return {"up_capture": 1.0, "down_capture": 1.0, "cap_score": 0.0,
                "unstable": False}
    a, b = _aligned_closes(alt_rows, btc_rows, idx)
    ra, rb = _returns(a[-(CAPTURE_N + 1):]), _returns(b[-(CAPTURE_N + 1):])
    m = min(len(ra), len(rb))
    ra, rb = ra[-m:], rb[-m:]
    up_a = sum(ra[i] for i in range(m) if rb[i] > 0)
    up_b = sum(rb[i] for i in range(m) if rb[i] > 0)
    dn_a = sum(ra[i] for i in range(m) if rb[i] < 0)
    dn_b = sum(rb[i] for i in range(m) if rb[i] < 0)
    n_up = sum(1 for x in rb if x > 0)
    n_dn = sum(1 for x in rb if x < 0)
    if n_up < CAP_MIN_DAY or n_dn < CAP_MIN_DAY or up_b == 0 or dn_b == 0:
        return {"up_capture": None, "down_capture": None, "cap_score": 0.0,
                "unstable": True}
    up_cap = up_a / up_b            # 둘 다 양수 → 알트 랠리 참여
    dn_cap = dn_a / dn_b            # 둘 다 음수 → 비율 양수, >1이면 더 빠짐
    cap_score = max(-1.0, min(1.0, (up_cap - dn_cap) / CAP_SCALE))
    return {"up_capture": round(up_cap, 3), "down_capture": round(dn_cap, 3),
            "cap_score": round(cap_score, 4), "unstable": m < CAPTURE_N}


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
