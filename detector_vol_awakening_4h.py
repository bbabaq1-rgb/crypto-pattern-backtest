"""
detector_vol_awakening_4h.py — '거래량 각성(슈팅 초동)' 디텍터 (4h, LONG).

근거: 슈팅 전조 이벤트 스터디(backtest_shooting_precursor.py, 최근 1년 162건) —
급등 24~48h 전에 거래대금 빌드업(AUC 0.66)·변동성 각성(0.60)·매수 부호거래량(0.58)이
관측됨. 이를 단순 결정론 규칙으로 고정(반올림 임계값, 파라미터 최소화):

  신호(4h 봉 i, 롱):
    1) 직전 6봉 평균 거래대금 ≥ 기준(이전 30봉 평균) × 1.5      # 빌드업
    2) 직전 12봉 부호거래량 합 > 0                               # 매수 우위
    3) 직전 12봉 변동성 ≥ 이전 30봉 변동성                        # 각성
    4) 종가가 직전 3일(18봉) 고점 미만                            # 본격 돌파 전(초동)
    5) 당봉 양봉                                                  # 방향 확인

검증: 동결 게이트(n≥20, mean>0, median>0, boot_p<0.05, OOS≥2) — validate 스크립트로.
"""
import statistics as st

import detlib

V_BUILD_MIN = 1.5
BASE_N      = 30       # 기준 구간(직전 12봉 제외 이전 30봉)
REC_N       = 12


def detect(rows):
    sig = []
    n = len(rows)
    qv = [r["c"] * r["v"] for r in rows]
    for i in range(REC_N + BASE_N, n):
        w6  = rows[i - 5:i + 1]
        w12 = rows[i - REC_N + 1:i + 1]
        b0, b1 = i - REC_N - BASE_N + 1, i - REC_N + 1
        base_v = st.mean(qv[b0:b1]) or 0
        if base_v <= 0:
            continue
        # 1) 빌드업
        if st.mean(qv[i - 5:i + 1]) < V_BUILD_MIN * base_v:
            continue
        # 2) 매수 부호거래량
        sv = sum((1 if r["c"] > r["o"] else -1) * r["c"] * r["v"] for r in w12)
        if sv <= 0:
            continue
        # 3) 변동성 각성
        r12 = [w12[k]["c"] / w12[k - 1]["c"] - 1 for k in range(1, len(w12)) if w12[k - 1]["c"] > 0]
        base_rows = rows[b0:b1]
        r30 = [base_rows[k]["c"] / base_rows[k - 1]["c"] - 1
               for k in range(1, len(base_rows)) if base_rows[k - 1]["c"] > 0]
        if len(r12) < 2 or len(r30) < 2 or st.pstdev(r12) < st.pstdev(r30):
            continue
        # 4) 아직 3일(18봉) 고점 미만 — 초동 국면
        hi3d = max(r["h"] for r in rows[i - 17:i])
        if rows[i]["c"] >= hi3d:
            continue
        # 5) 당봉 양봉
        if rows[i]["c"] <= rows[i]["o"]:
            continue
        sig.append(i)
    return sig


def load_ohlcv(sym, tf="4h"):
    return detlib.load_ohlcv(sym, tf)


evaluate = detlib.make_evaluate(detect, direction="long")
