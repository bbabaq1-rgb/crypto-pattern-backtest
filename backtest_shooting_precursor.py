"""
backtest_shooting_precursor.py — '슈팅(일봉 급등)' 전조의 4h/1h 캔들 구조 연구.

질문(사용자): 최근 1년 일봉 마감 기준 급등일들을 뽑아, 그 '직전' 4h/1h 캔들에서
슈팅을 예고하는 공통 특징이 있는가?

설계(전부 causal):
  이벤트 = 일봉 종가수익률 ≥ +15% (최근 1년, 유니버스 전체)
  대조군 = 같은 종목들의 비이벤트 일(수익률<+10%) 무작위 5배수(seed 고정)
  특징   = 이벤트 '전일까지'의 4h(직전 6~30봉)·1h 캔들만 사용 — look-ahead 없음
  판별력 = rank-AUC (Mann-Whitney): 0.5=무정보, ≥0.60 후보 / ≤0.40 역방향 후보

주의(정직): 이건 연관성 연구다. 분리력 있는 특징이 나와도 '수익 나는 진입규칙'이
되려면 별도 디텍터로 만들어 동결 게이트(다년 OOS)를 통과해야 한다(2단계).
"""
import sys
import glob
import os
import json
import random
import statistics as st
from bisect import bisect_left
from datetime import date, timedelta

import detlib

SEED       = 42
EVENT_THR  = 0.15      # 일봉 종가 +15% 이상 = 슈팅
CTRL_MAX   = 0.10      # 대조군은 +10% 미만(경계 완충)
CTRL_MULT  = 5         # 대조군 표본 배수
LOOKBACK_D = 372       # 최근 1년(+버퍼)


def _universe():
    uni = json.load(open("universe.json", encoding="utf-8")).get("trading_universe", [])
    have = {os.path.basename(f)[:-7].upper() for f in glob.glob("data/*_1d.csv")}
    return [s for s in uni if s in have]


def _load(sym, tf):
    try:
        return detlib.load_ohlcv(sym, tf)
    except Exception:
        return None


def _idx_before(dates, d):
    """dates(오름차순, 중복 허용)에서 date < d 인 마지막 인덱스."""
    return bisect_left(dates, d) - 1


# ── 4h/1h 전조 특징 (마지막 봉 인덱스 i 기준, i까지 봉만 사용) ─────────────────
def feats_4h(rows, i):
    if i < 42:
        return None
    w6  = rows[i - 5:i + 1]
    w12 = rows[i - 11:i + 1]
    w30 = rows[i - 41:i - 11]           # 비교 기준(직전 12봉 제외한 이전 30봉)
    qv  = lambda r: r["c"] * r["v"]
    base_v = st.mean([qv(r) for r in w30]) or 1e-9
    hi12, lo12 = max(r["h"] for r in w12), min(r["l"] for r in w12)
    hi30, lo30 = max(r["h"] for r in w30), min(r["l"] for r in w30)
    rng30 = (hi30 - lo30) or 1e-9
    rets12 = [w12[k]["c"] / w12[k - 1]["c"] - 1 for k in range(1, len(w12)) if w12[k - 1]["c"] > 0]
    rets30 = [w30[k]["c"] / w30[k - 1]["c"] - 1 for k in range(1, len(w30)) if w30[k - 1]["c"] > 0]
    streak = 0
    for r in reversed(rows[max(0, i - 11):i + 1]):
        if r["c"] > r["o"]:
            streak += 1
        else:
            break
    hl = sum(1 for k in range(1, 6) if w6[k]["l"] > w6[k - 1]["l"]) / 5
    lw = st.mean([(min(r["o"], r["c"]) - r["l"]) / ((r["h"] - r["l"]) or 1e-9) for r in w6])
    sv = sum((1 if r["c"] > r["o"] else -1) * qv(r) for r in w12)
    tv = sum(qv(r) for r in w12) or 1e-9
    hi3d = max(r["h"] for r in rows[i - 17:i + 1][:-1]) if i >= 18 else hi12
    return {
        "v_build6":   st.mean([qv(r) for r in w6]) / base_v,          # 거래대금 빌드업(6봉=24h)
        "v_build12":  st.mean([qv(r) for r in w12]) / base_v,
        "compress":   (hi12 - lo12) / rng30,                          # 가격 압축(<1 = 수렴)
        "rvol_ratio": (st.pstdev(rets12) / (st.pstdev(rets30) or 1e-9)) if len(rets12) > 1 and len(rets30) > 1 else 1.0,
        "green_streak": streak,                                       # 마지막 연속 양봉(4h)
        "higher_lows": hl,                                            # 저가 단조상승 비율
        "lower_wick":  lw,                                            # 아래꼬리 비중(매수흡수)
        "signed_vol":  sv / tv,                                       # 부호거래량(-1~+1)
        "near_break":  rows[i]["c"] / hi3d - 1,                       # 3일 고점 대비 위치
    }


def feats_1h(rows, i):
    if i < 60:
        return None
    w24 = rows[i - 23:i + 1]
    w48 = rows[i - 59:i - 23]
    qv = lambda r: r["c"] * r["v"]
    base_v = st.mean([qv(r) for r in w48]) or 1e-9
    hi24, lo24 = max(r["h"] for r in w24), min(r["l"] for r in w24)
    hi48, lo48 = max(r["h"] for r in w48), min(r["l"] for r in w48)
    streak = 0
    for r in reversed(w24):
        if r["c"] > r["o"]:
            streak += 1
        else:
            break
    return {
        "h1_v_build24": st.mean([qv(r) for r in w24]) / base_v,
        "h1_compress":  (hi24 - lo24) / ((hi48 - lo48) or 1e-9),
        "h1_green_streak": streak,
    }


def _auc(ev, ct):
    """rank-AUC: 이벤트값이 대조군보다 클 확률(0.5=무정보)."""
    allv = sorted([(v, 0) for v in ct] + [(v, 1) for v in ev])
    # 평균 순위(동점 처리)
    ranks = {}
    i = 0
    while i < len(allv):
        j = i
        while j + 1 < len(allv) and allv[j + 1][0] == allv[i][0]:
            j += 1
        for k in range(i, j + 1):
            ranks[k] = (i + j) / 2 + 1
        i = j + 1
    r_ev = sum(ranks[k] for k, (_, g) in enumerate(allv) if g == 1)
    n1, n0 = len(ev), len(ct)
    return (r_ev - n1 * (n1 + 1) / 2) / (n1 * n0)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    random.seed(SEED)
    syms = _universe()
    cutoff = (date.today() - timedelta(days=LOOKBACK_D)).isoformat()

    # 1) 이벤트 추출 (최근 1년 일봉 +15%↑)
    events, pool_ctrl = [], []
    top_gainers = []
    for sym in syms:
        d1 = _load(sym, "1d")
        if not d1:
            continue
        for i in range(1, len(d1)):
            dte = d1[i]["date"]
            if dte < cutoff or d1[i - 1]["c"] <= 0:
                continue
            ret = d1[i]["c"] / d1[i - 1]["c"] - 1
            rec = (sym, dte, ret)
            if ret >= EVENT_THR:
                events.append(rec)
            elif ret < CTRL_MAX:
                pool_ctrl.append(rec)
        best = max(((d1[i]["c"] / d1[i - 1]["c"] - 1, d1[i]["date"]) for i in range(1, len(d1))
                    if d1[i]["date"] >= cutoff and d1[i - 1]["c"] > 0), default=None)
        if best:
            top_gainers.append((sym, best[0], best[1]))
    top_gainers.sort(key=lambda x: -x[1])
    print(f"최근 1년 슈팅 이벤트(일봉 +{EVENT_THR*100:.0f}%↑): {len(events)}건 / {len(syms)}종목")
    print("최대 상승 상위 15종목:")
    for s, r, d in top_gainers[:15]:
        print(f"  {s:6} {r*100:+6.1f}%  ({d})")

    ctrl = random.sample(pool_ctrl, min(len(pool_ctrl), len(events) * CTRL_MULT))

    # 2) 전조 특징 수집 (4h + 1h, 이벤트 '이전' 봉만)
    cache4, cache1 = {}, {}
    def collect(recs):
        out = []
        for sym, dte, ret in recs:
            if sym not in cache4:
                r4 = _load(sym, "4h")
                cache4[sym] = (r4, [r["date"] for r in r4] if r4 else None)
                r1 = _load(sym, "1h")
                cache1[sym] = (r1, [r["date"] for r in r1] if r1 else None)
            r4, d4 = cache4[sym]
            if not r4:
                continue
            i4 = _idx_before(d4, dte)
            f = feats_4h(r4, i4)
            if f is None:
                continue
            r1, d1_ = cache1[sym]
            if r1:
                i1 = _idx_before(d1_, dte)
                f1 = feats_1h(r1, i1)
                if f1:
                    f.update(f1)
            out.append(f)
        return out

    fe, fc = collect(events), collect(ctrl)
    print(f"\n특징 수집: 이벤트 {len(fe)}건 / 대조군 {len(fc)}건 (4h 기준, 1h는 가용 시 병합)")

    # 3) 특징별 분리력(AUC) 랭킹
    keys = sorted({k for f in fe for k in f})
    print(f"\n{'특징':<16}{'AUC':>7}{'이벤트중앙값':>12}{'대조중앙값':>12}  해석")
    results = {}
    for k in keys:
        ev = [f[k] for f in fe if k in f]
        ct = [f[k] for f in fc if k in f]
        if len(ev) < 30 or len(ct) < 30:
            continue
        auc = _auc(ev, ct)
        results[k] = dict(auc=round(auc, 3), ev_med=st.median(ev), ct_med=st.median(ct),
                          n_ev=len(ev), n_ct=len(ct))
        mark = "★★" if abs(auc - 0.5) >= 0.10 else ("★" if abs(auc - 0.5) >= 0.05 else "")
        print(f"{k:<16}{auc:>7.3f}{st.median(ev):>12.3f}{st.median(ct):>12.3f}  {mark}")

    json.dump(dict(n_events=len(fe), n_ctrl=len(fc), features=results,
                   top_gainers=[(s, round(r, 4), d) for s, r, d in top_gainers[:20]]),
              open("shooting_precursor.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print("\n[저장] shooting_precursor.json")
    print("판독: AUC 0.5=무정보, ≥0.60/≤0.40 = 유의미 후보(★★). "
          "후보는 2단계(디텍터화→동결게이트 다년 OOS)로만 채택 가능.")


if __name__ == "__main__":
    main()
