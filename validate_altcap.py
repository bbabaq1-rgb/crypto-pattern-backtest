"""
validate_altcap.py — 시장 평균 상승·하락 비대칭(avg_cap)으로 알트 상승기·하락기를 가를 수 있나
(2026-09-28, 사용자 지시 "사전 등록 시험으로 설계해서 돌려줘").

■ 물음 (사용자 관찰 그대로)
  "비트·이더가 빠지는 것에 비해 알트가 훨씬 많이 빠진다 — 이 빠지는 비율이나 기울기로 상승기·
  하락기를 구분할 수 없나." 레포에는 이미 이 비율이 있다: relative_strength.compute_capture 의
  cap_score = (상승 포착 − 하락 포착). 상승 포착 = BTC 오른 날 알트가 따라 오른 비율, 하락 포착 =
  BTC 빠진 날 알트가 빠진 비율(1 초과면 더 빠짐). 그 **유니버스 평균 avg_cap** 이 실거래에서
  사이징 오버레이로 돌고 있다(avg_cap > 0 → 신규 롱 x0.6).

■ 무엇이 새로운가
  avg_cap 은 '방향 예측'으로 시험된 적이 없다. 종전 backtest_regime_capture 는 **패턴 거래(방식D)의
  성과**를 avg_cap 분위로 나눴을 뿐이고, 알트 시장 자체가 이후 오르느냐 내리느냐는 안 봤다.
  이 판은 그 물음을 알트 시즌 시험(validate_altseason)과 **같은 도구**로 잰다.

■ 부호 — 사용자 가설 방향으로 실행 전에 선언
  "알트가 BTC 보다 더 빠지고 덜 따라 오르는 국면 = 하락기" → avg_cap 이 높을수록 이후 알트가 오른다(+).
  **기존 실거래 오버레이는 반대를 가정한다**(backtest_regime_capture: 집단 bleed = 반전 롱 최적,
  avg_cap 양수 = complacent → 롱 축소). 그래서 결과가 선언 반대로 크게 나오면 REVERSED 로 기록하고
  '기존 오버레이 방향을 지지'로 읽는다(통과로 치지 않는다). 사후에 부호를 고르지 않는다.

■ 지표 5 x 지평 2 = 주 판정 10 셀 (Holm m=10)
  avg_cap        (+1) 시장 평균 cap_score (실거래 계산식 그대로, 60봉)
  avg_cap_chg20  (+1) avg_cap 20일 변화 — 수준이 아니라 '변화'(지속성이 낮아 검출 한계가 낮다)
  avg_down_cap   (-1) 평균 하락 포착 — 빠질 때 더 빠질수록 이후 약세
  avg_up_cap     (+1) 평균 상승 포착 — 오를 때 잘 따라 오를수록 이후 강세
  neg_share      (-1) cap_score < 0 인 알트 비율 — '약한 알트'가 많을수록 이후 약세
  지평 20일 / 60일. 타깃 = 알트 중앙값의 이후 수익률(절대값 — 사용자 물음이 '상승기·하락기').
  BTC 대비 초과수익 타깃은 진단(D2).

■ 음성 대조 — AR(1) φ=0.99 잡음 · 연 1회 사인파 x 지평 2 = 4 셀. **2개 이상 C1 통과 시 판 INVALID.**

■ 통계·판정 — validate_altseason 을 그대로 import (사과 대 사과)
  회전 검정 귀무(최소 이동 1.5 x 지평) · MDE · Holm · judge() 동일. 분할도 동일
  (train 2018-01-01 ~ 2021-12-31 / holdout 2022-01-01 ~). 문턱 IC1 0.20 / IC2 0.15 불변.
  C3 = 선언 부호가 가리키는 3분위의 이후 알트 수익이 전체보다 높음(두 분할) AND holdout 에서 양수.

■ 진단 (판정 아님, 사후 선택 금지)
  D1 **부호 전환 사건** — avg_cap(5일 평균)이 양수 → 음수로 넘어간 날 이후 20·60일 알트 중앙 수익
     vs 무조건부. 사용자에게 제안한 '변화를 확인 신호로' 형태. 사건 수가 적어 판정에 넣지 않는다.
  D2 BTC 대비 초과수익 타깃의 IC.
  D3 오늘 읽기(데이터 끝 날짜) — 전망이 아니라 현재 상태.

■ 사전 확률 (결과 전 기록)
  CONFIRMED 0 예상. 이유: ① 알트 시즌 시험 30셀에서 알트 강도 지표가 전부 잡음과 구분되지 않았다
  ② 레짐 라벨의 20일 방향 적중이 49% ③ 비대칭은 60봉 창이라 후행. 방향은 **REVERSED 쪽이 더 그럴듯**하다고
  본다 — 기존 연구가 '집단 bleed 뒤 반등'을 봤기 때문. 가장 있을 법한 결과는 '변화(chg20)'의 검출 한계만
  낮고 IC 는 그 아래인 것(차분 판과 같은 그림).

■ DEPLOY_ON_PASS = False — 통과해도 실거래 반영 없음. 관찰 기간(~10/06) 중이고, 예측력 확인과
  매매 규칙은 별개 명제다.

실행: python validate_altcap.py
"""
import json
import math
import statistics as st

import validate_altseason as V
from relative_strength import CAPTURE_N, CAP_MIN_DAY, CAP_SCALE

OUT = "_altcap.json"

# ── 동결 상수 (2026-09-28, 결과 보기 전) ──────────────────────────────────
HORIZONS = (20, 60)
CHG_LB = 20                 # avg_cap 변화 창
FLIP_SMOOTH = 5             # D1 사건 판정용 avg_cap 이동평균
MIN_COINS = 10              # 그날 cap 이 계산된 알트가 이보다 적으면 관측 제외
SEED = 20260928
DEPLOY_ON_PASS = False

FEATURES = [
    ("avg_cap",       "시장 평균 상승·하락 비대칭 (cap_score 평균)", +1),
    ("avg_cap_chg20", "시장 평균 비대칭 20일 변화",                  +1),
    ("avg_down_cap",  "평균 하락 포착 (빠질 때 얼마나 더 빠지나)",   -1),
    ("avg_up_cap",    "평균 상승 포착 (오를 때 얼마나 따라 오르나)", +1),
    ("neg_share",     "비대칭 음수 알트 비율",                       -1),
]
CONTROLS = [
    ("ctrl_ar1",    "음성대조 — AR(1) φ=0.99 잡음", +1),
    ("ctrl_season", "음성대조 — 연 1회 사인파",      +1),
]
M_HOLM = len(FEATURES) * len(HORIZONS)


# ── 비대칭 계열 (실거래 compute_capture 와 같은 식을 창 단위로 굴린다) ────────
def rolling_capture(alt, btc, n=CAPTURE_N, min_day=CAP_MIN_DAY, scale=CAP_SCALE):
    """alt·btc = {date: close}. 반환 {date: (cap_score, up_cap, dn_cap)} — 계산 불가 날은 빠진다.

    compute_capture 는 '알트 거래일 ∩ BTC 거래일' 로 정렬한 종가의 마지막 n+1 개(= n 개 수익률)를 쓴다.
    여기서는 같은 정렬 수열 위에서 창을 한 칸씩 민다. 결과가 compute_capture 와 같은지는
    test_altcap 이 합성 데이터로 고정한다.
    """
    ds = [d for d in sorted(alt) if d in btc]
    a = [alt[d] for d in ds]
    b = [btc[d] for d in ds]
    rets = []                                         # (date, ra, rb) — 정렬 수열의 연속 쌍
    for i in range(1, len(ds)):
        if a[i - 1] > 0 and b[i - 1] > 0:
            rets.append((ds[i], a[i] / a[i - 1] - 1, b[i] / b[i - 1] - 1))
    out = {}
    for k in range(n - 1, len(rets)):
        win = rets[k - n + 1:k + 1]
        up_a = sum(ra for _, ra, rb in win if rb > 0)
        up_b = sum(rb for _, ra, rb in win if rb > 0)
        dn_a = sum(ra for _, ra, rb in win if rb < 0)
        dn_b = sum(rb for _, ra, rb in win if rb < 0)
        n_up = sum(1 for _, _, rb in win if rb > 0)
        n_dn = sum(1 for _, _, rb in win if rb < 0)
        if n_up < min_day or n_dn < min_day or up_b == 0 or dn_b == 0:
            continue
        up_cap, dn_cap = up_a / up_b, dn_a / dn_b
        cap = max(-1.0, min(1.0, (up_cap - dn_cap) / scale))
        out[rets[k][0]] = (cap, up_cap, dn_cap)
    return out


def build_cap_series(S):
    """V.build_series 의 격자 위에 시장 평균 비대칭 계열을 얹는다. 적격(이력 180봉) 알트만."""
    by, dates, el = S["by"], S["dates"], S["eligible"]
    btc = by["btc"]
    per = {s: rolling_capture(by[s], btc) for s in by if s != "btc"}
    avg_cap, avg_up, avg_dn, neg, n_used = [], [], [], [], []
    for d in dates:
        vals = [per[s][d] for s in per if d in per[s] and el(s, d)]
        n_used.append(len(vals))
        if len(vals) < MIN_COINS:
            avg_cap.append(None); avg_up.append(None); avg_dn.append(None); neg.append(None)
            continue
        avg_cap.append(st.mean(v[0] for v in vals))
        avg_up.append(st.median(v[1] for v in vals))
        avg_dn.append(st.median(v[2] for v in vals))
        neg.append(sum(1 for v in vals if v[0] < 0) / len(vals))
    return dict(avg_cap=avg_cap, avg_up=avg_up, avg_dn=avg_dn, neg=neg, n_used=n_used)


def features_at(S, C):
    n = len(S["dates"])
    base = V.features_at(S)                          # 대조 계열(ar1·season)을 같은 시드로 재사용
    out = []
    for i in range(n):
        ac = C["avg_cap"][i]
        chg = (None if (i < CHG_LB or ac is None or C["avg_cap"][i - CHG_LB] is None)
               else ac - C["avg_cap"][i - CHG_LB])
        out.append({"avg_cap": ac, "avg_cap_chg20": chg,
                    "avg_down_cap": C["avg_dn"][i], "avg_up_cap": C["avg_up"][i],
                    "neg_share": C["neg"][i],
                    "ctrl_ar1": base[i]["ctrl_ar1"], "ctrl_season": base[i]["ctrl_season"]})
    return out


def target_abs(S, horizon):
    """i -> 이후 horizon 일 알트 중앙값 수익률(절대). 라벨 창이 온전한 날만. 적격 알트만."""
    dates, by, el = S["dates"], S["by"], S["eligible"]
    out = [None] * len(dates)
    for i in range(len(dates) - horizon):
        d0, d1 = dates[i], dates[i + horizon]
        rs_ = [by[s][d1] / by[s][d0] - 1 for s in S["alts"]
               if d0 in by[s] and d1 in by[s] and el(s, d0)]
        if len(rs_) >= V.MIN_UNIVERSE:
            out[i] = st.median(rs_)
    return out


def flip_events(avg_cap, dates, smooth=FLIP_SMOOTH):
    """avg_cap 의 smooth 일 이동평균이 양수 → 0 이하로 넘어간 날 인덱스 (D1 진단)."""
    ma = [None] * len(avg_cap)
    for i in range(len(avg_cap)):
        w = avg_cap[max(0, i - smooth + 1):i + 1]
        if len(w) == smooth and all(v is not None for v in w):
            ma[i] = sum(w) / smooth
    return [i for i in range(1, len(ma))
            if ma[i] is not None and ma[i - 1] is not None and ma[i - 1] > 0 >= ma[i]]


# ── 분석 ──────────────────────────────────────────────────────────────────
def one(idxs, feats, tgt, key, sign, seed, min_shift):
    sub = [i for i in idxs if feats[i].get(key) is not None and tgt[i] is not None]
    if len(sub) < 2 * min_shift + 3:
        return None
    fv = [feats[i][key] for i in sub]
    tv = [tgt[i] for i in sub]
    ic = V.spearman(fv, tv)
    nulls = V.rotation_null(fv, tv, min_shift=min_shift, seed=seed)
    return dict(n=len(sub), ic=ic, p=V.pval(ic, nulls, sign), p_two=V.pval_two(ic, nulls),
                mde=V.mde(nulls, sign), terc=V.tercile_stats(fv, tv, sign))


def analyze(S, C, feats, targets):
    dates = S["dates"]
    rows = []
    for h in HORIZONS:
        tgt = targets[h]
        keep = [i for i in range(len(dates))
                if tgt[i] is not None and dates[i] >= V.START and C["n_used"][i] >= MIN_COINS]
        tr_i = [i for i in keep if dates[i] < V.SPLIT]
        ho_i = [i for i in keep if dates[i] >= V.SPLIT]
        ms = int(round(1.5 * h))
        for k, (key, label, sign) in enumerate([*FEATURES, *CONTROLS]):
            rows.append(dict(key=f"{key}@{h}", base=key, horizon=h, label=label, sign=sign,
                             train=one(tr_i, feats, tgt, key, sign, SEED + 10 * h + k, ms),
                             holdout=one(ho_i, feats, tgt, key, sign, SEED + 10 * h + 500 + k, ms),
                             is_control=key.startswith("ctrl_")))
    hp = V.holm([(r["key"], r["train"]["p"]) for r in rows
                 if not r["is_control"] and r["train"]], m=M_HOLM)
    for r in rows:
        if r["train"]:
            r["train"]["p_holm"] = hp.get(r["key"], r["train"]["p"])
    for r in rows:
        r["verdict"], r["why"] = V.judge(r)
    return rows


def c1_raw(r):
    """대조 INVALID 판정용 — Holm 없이 부호·크기·raw p."""
    tr = r["train"]
    return bool(tr and (tr["ic"] * r["sign"]) > 0 and abs(tr["ic"]) >= V.IC1 and tr["p"] < V.ALPHA)


def main():
    print("=" * 110)
    print("시장 평균 상승·하락 비대칭(avg_cap) → 이후 알트 방향 — 사전 등록 시험 (2026-09-28)")
    print("=" * 110)
    by = V.load_all()
    S = V.build_series(by)
    C = build_cap_series(S)
    feats = features_at(S, C)
    targets = {h: target_abs(S, h) for h in HORIZONS}
    rows = analyze(S, C, feats, targets)
    dates = S["dates"]

    print(f"데이터 {dates[0]} ~ {dates[-1]} · 종목 {len(by)} · train < {V.SPLIT} ≤ holdout")
    print(f"{'셀':<22}{'부호':>4}{'n_tr':>6}{'IC_tr':>8}{'MDE_tr':>8}{'Holm':>7}"
          f"{'n_ho':>6}{'IC_ho':>8}{'p_ho':>7}{'선호3분위 tr/ho':>20}  판정")
    for r in rows:
        tr, ho = r["train"] or {}, r["holdout"] or {}
        t1, t2 = (tr.get("terc") or {}), (ho.get("terc") or {})
        terc = (f"{t1.get('top_mean', float('nan'))*100:+.1f}/{t2.get('top_mean', float('nan'))*100:+.1f}%"
                if t1 and t2 else "—")
        print(f"{r['key']:<22}{r['sign']:>+4d}{tr.get('n', 0):>6}{V.fmt(tr.get('ic'))}"
              f"{V.fmt(tr.get('mde'))}{tr.get('p_holm', float('nan')):>7.3f}"
              f"{ho.get('n', 0):>6}{V.fmt(ho.get('ic'))}{ho.get('p', float('nan')):>7.3f}"
              f"{terc:>20}  {r['verdict']} {'; '.join(r['why'])}")

    ctrl_pass = [r["key"] for r in rows if r["is_control"] and c1_raw(r)]
    invalid = len(ctrl_pass) >= 2
    main_rows = [r for r in rows if not r["is_control"]]
    tally = {v: sum(1 for r in main_rows if r["verdict"] == v)
             for v in ("CONFIRMED", "INCONCLUSIVE", "REVERSED", "REJECTED")}
    print(f"\n판 {'INVALID' if invalid else 'VALID'} (대조 C1 통과 {len(ctrl_pass)}/4: {ctrl_pass}) | {tally}")

    # D1 부호 전환 사건
    ev = flip_events(C["avg_cap"], dates)
    d1 = {}
    for h in HORIZONS:
        tgt = targets[h]
        for part, lo, hi in (("train", V.START, V.SPLIT), ("holdout", V.SPLIT, "9999")):
            evv = [tgt[i] for i in ev if tgt[i] is not None and lo <= dates[i] < hi]
            allv = [tgt[i] for i in range(len(dates)) if tgt[i] is not None and lo <= dates[i] < hi
                    and C["n_used"][i] >= MIN_COINS]
            d1[f"{part}@{h}"] = dict(n_events=len(evv),
                                     ev_mean=st.mean(evv) if evv else None,
                                     ev_pos=(sum(1 for v in evv if v > 0) / len(evv)) if evv else None,
                                     all_mean=st.mean(allv) if allv else None,
                                     all_pos=(sum(1 for v in allv if v > 0) / len(allv)) if allv else None)
    print("\nD1 avg_cap(5일 평균) 양수→음수 전환 뒤 알트 중앙 수익 (진단):")
    for k, v in d1.items():
        if v["n_events"]:
            print(f"  {k:<14} 사건 {v['n_events']:>3} | 사건 뒤 평균 {v['ev_mean']*100:+6.2f}% (양수 {v['ev_pos']:.0%}) "
                  f"vs 무조건부 {v['all_mean']*100:+6.2f}% (양수 {v['all_pos']:.0%})")
        else:
            print(f"  {k:<14} 사건 0")

    # D2 BTC 대비 초과수익 타깃
    print("\nD2 BTC 대비 초과수익 타깃 IC (진단):")
    d2 = {}
    for h in HORIZONS:
        ex, _ = V.target_at(S, horizon=h)
        for key, _l, sign in FEATURES:
            pts = {}
            for part, lo, hi in (("train", V.START, V.SPLIT), ("holdout", V.SPLIT, "9999")):
                sub = [i for i in range(len(dates)) if ex[i] is not None and feats[i][key] is not None
                       and lo <= dates[i] < hi and C["n_used"][i] >= MIN_COINS]
                pts[part] = V.spearman([feats[i][key] for i in sub], [ex[i] for i in sub]) if len(sub) > 30 else None
            d2[f"{key}@{h}"] = pts
            print(f"  {key}@{h:<4} train {V.fmt(pts['train'])} / holdout {V.fmt(pts['holdout'])}")

    # D3 오늘 읽기
    last = max(i for i in range(len(dates)) if C["avg_cap"][i] is not None)
    today = {k: feats[last][k] for k, _l, _s in FEATURES}
    print(f"\nD3 데이터 끝({dates[last]}) 읽기: " +
          " / ".join(f"{k} {v:+.3f}" for k, v in today.items() if v is not None))

    json.dump(dict(rows=rows, invalid=invalid, ctrl_pass=ctrl_pass, tally=tally, d1=d1, d2=d2,
                   d3=dict(date=dates[last], **today), deploy_on_pass=DEPLOY_ON_PASS),
              open(OUT, "w"), ensure_ascii=False, indent=1, default=str)
    print(f"→ {OUT}")
    return rows


if __name__ == "__main__":
    main()
