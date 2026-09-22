"""
power_curve.py — 알트 시즌 시험의 **검정력 곡선** (2026-09-22, 사용자 지시 "검정력 곡선 돌려줘").

■ 이것은 판정이 아니라 계산이다
  어떤 지표에 대해서도 새 판정을 내리지 않는다. 가설 검정이 아니라 **검정력 분석**이고,
  검정력 분석이 기존 표본의 분산 구조를 쓰는 것은 표준이다. 출력에 verdict 는 없다.

■ 무엇에 답하나
  유료 데이터(CoinGecko Analyst / CoinMarketCap Startup)를 사면 타깃을 '생존 80종목 중앙값'
  에서 **진짜 TOTAL3/BTC** 로 바꿀 수 있고, 그러면 '적격 코인 10종목' 요건이 사라져 표본
  시작이 2018-05 → 2014 로 내려간다. 비중첩 120일 창이 **24 → 약 38** 이 된다.
  **그만큼 사면 MDE 가 문턱(0.20) 밑으로 내려오는가?** 내려오지 않으면 돈을 쓸 이유가 없다.

■ 방법
  ① 라벨 있는 구간에서 길이 L(일)의 **연속** 부분창을 잘라
  ② validate_altseason 과 **똑같은 회전 검정**으로 귀무를 만들고 MDE(95백분위)를 잰다
  ③ L 를 키우며 MDE(n_win) 곡선을 그리고 log-log 최소제곱으로 MDE = c · n^(-p) 를 적합
  ④ n=21(2014 시작 시 train) · n=38(전체) 로 외삽
  이론값은 p=0.5 (독립 표본의 SE ∝ 1/√n). **p 를 가정하지 않고 측정해서 외삽한다** —
  중첩 창이 완전 독립은 아니지만 정보가 0 도 아니기 때문이다.

■ 자체 검산
  train 구간(n_win 11.1)에서 ethbtc_mom120 의 MDE 가 공식 실행(run 35694986034)의
  **0.299** 를 재현해야 한다. 재현 못 하면 곡선 전체가 무의미하므로 먼저 찍는다.

실행: python power_curve.py [--smoke]
"""
import json
import math
import statistics as st
import sys

import validate_altseason as V

OUT = "_power_curve.json"

# 동결 — validate_altseason 과 같은 회전 검정을 쓴다
BOOT_CURVE = 500      # 곡선용(MDE 는 95백분위라 500 이면 충분)
BOOT_ANCHOR = 1000    # 검산용 — 공식 실행과 같은 값
SEED = 20260922
WIN_GRID = [6, 9, 12, 15, 18, 21, 24]   # 비중첩 120일 창 개수
MAX_PLACE = 3                            # L 마다 시작점 최대 3곳 (평균)
TARGETS = [(21, "2014 시작 시 train"), (38, "2014 시작 시 전체")]
KEYS = [k for k, _, _ in V.FEATURES]
SIGNS = {k: s for k, _, s in V.FEATURES}


def labeled_index(S, tgt):
    """validate_altseason.analyze 와 같은 필터 — 라벨 있고 START 이후이고 유니버스 충족."""
    d = S["dates"]
    return [i for i in range(len(d))
            if tgt[i] is not None and d[i] >= V.START and S["univ_n"][i] >= V.MIN_UNIVERSE]


def placements(total, span, k=MAX_PLACE):
    """길이 span 의 연속 부분창 시작 offset 목록(최대 k개, 균등 배치)."""
    room = total - span
    if room <= 0:
        return [0]
    k = min(k, room + 1)
    return sorted({round(room * j / (k - 1)) for j in range(k)}) if k > 1 else [0]


def mde_for(feats, tgt, idxs, key, boot, seed):
    """부분창 idxs 에서 key 의 MDE. 결측 있으면 None."""
    sub = [i for i in idxs if feats[i].get(key) is not None]
    if len(sub) < 2 * V.MIN_SHIFT + 3:
        return None
    fv = [feats[i][key] for i in sub]
    tv = [tgt[i] for i in sub]
    nulls = V.rotation_null(fv, tv, boot=boot, seed=seed)
    if not nulls:
        return None
    return abs(V.mde(nulls, SIGNS[key]))


def fit_loglog(pts):
    """[(n, mde)] -> (c, p) with mde = c * n**(-p). 최소제곱."""
    xs = [math.log(n) for n, _ in pts]
    ys = [math.log(m) for _, m in pts]
    mx, my = st.mean(xs), st.mean(ys)
    den = sum((x - mx) ** 2 for x in xs)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den
    return math.exp(my - slope * mx), -slope


def r2(pts, c, p):
    ys = [math.log(m) for _, m in pts]
    pred = [math.log(c) - p * math.log(n) for n, _ in pts]
    my = st.mean(ys)
    ss_res = sum((y - q) ** 2 for y, q in zip(ys, pred))
    ss_tot = sum((y - my) ** 2 for y in ys)
    return 1 - ss_res / ss_tot if ss_tot else float("nan")


def main():
    smoke = "--smoke" in sys.argv
    grid = WIN_GRID[:3] if smoke else WIN_GRID
    keys = KEYS[:3] if smoke else KEYS
    boot = 120 if smoke else BOOT_CURVE

    print("=" * 96)
    print("알트 시즌 시험 검정력 곡선 — **판정 아님, 계산만** (registry altseason_prereg_2026_09_22 후속)")
    print(f"회전 검정 이동 >= {V.MIN_SHIFT}일 · boot {boot} · seed {SEED} · 지표 {len(keys)}종")
    print("=" * 96)

    S = V.build_series(V.load_all())
    feats = V.features_at(S)
    tgt, _ = V.target_at(S)
    idxs = labeled_index(S, tgt)
    d = S["dates"]
    total_win = len(idxs) / V.HORIZON
    print(f"[표본] 라벨 있는 날 {len(idxs)} ({d[idxs[0]]} ~ {d[idxs[-1]]}) "
          f"= 비중첩 120일 창 {total_win:.1f}개")

    # ── 자체 검산: train 구간에서 공식 실행의 MDE 0.299 를 재현하는가 ──
    tr = [i for i in idxs if d[i] < V.SPLIT]
    anchor = mde_for(feats, tgt, tr, "ethbtc_mom120", BOOT_ANCHOR, SEED + 0)
    ok = anchor is not None and abs(anchor - 0.299) < 0.02
    print(f"[검산] train(n_win {len(tr)/V.HORIZON:.1f}) ethbtc_mom120 MDE = {anchor:.3f} "
          f"— 공식 실행 0.299 {'재현 ✓' if ok else '**불일치 ✗**'}")
    if not ok and not smoke:
        print("       ※ 불일치하면 아래 곡선은 신뢰할 수 없다.")

    # ── 곡선 ──
    print("\n" + "-" * 96)
    print(f"{'창 수':>6}{'일수':>7}{'배치':>5}{'MDE 중앙':>10}{'MDE 최소':>10}{'MDE 최대':>10}   구간")
    print("-" * 96)
    pts, rows = [], []
    for nwin in grid:
        span = nwin * V.HORIZON
        if span > len(idxs):
            continue
        vals, spans = [], []
        for off in placements(len(idxs), span):
            sub = idxs[off:off + span]
            spans.append(f"{d[sub[0]][:7]}~{d[sub[-1]][:7]}")
            for k, key in enumerate(keys):
                m = mde_for(feats, tgt, sub, key, boot, SEED + 31 * nwin + k)
                if m is not None:
                    vals.append(m)
        if not vals:
            continue
        med = st.median(vals)
        pts.append((nwin, med))
        rows.append(dict(n_win=nwin, days=span, n_place=len(spans), mde_median=med,
                         mde_min=min(vals), mde_max=max(vals), spans=spans))
        print(f"{nwin:>6}{span:>7}{len(spans):>5}{med:>10.3f}{min(vals):>10.3f}{max(vals):>10.3f}   "
              f"{', '.join(spans)}")
    print("-" * 96)

    if len(pts) < 3:
        print("점이 모자라 적합 불가(--smoke?)")
        return

    c, p = fit_loglog(pts)
    print(f"\n[적합] MDE = {c:.3f} · n^(-{p:.3f})   R² {r2(pts, c, p):.3f}")
    # p 의 뜻: 0.5 = 120일 창 하나가 곧 독립 관측 하나. p<0.5 면 국면이 뭉쳐 있어
    # 비중첩 창끼리도 상관이 남는다 = **정보가 독립 표본보다 느리게 쌓인다**(= 데이터를
    # 더 사도 1/√n 계산보다 덜 얻는다). p>0.5 는 드물다.
    tag = ("독립 표본과 같은 속도" if p >= 0.48 else
           "독립 표본보다 느리게 쌓인다 — 데이터를 더 사도 1/√n 계산보다 덜 얻는다" if p >= 0.25 else
           "거의 안 쌓인다 — 표본을 늘려도 검정력이 잘 안 는다")
    print(f"       이론값 p=0.500(완전 독립) 대비 **{p:.3f}** — {tag}")
    print(f"       MDE 를 절반으로 줄이려면 창이 **{2 ** (1 / p):.1f}배** 필요하다.")

    print(f"\n[외삽] 문턱 |IC| = {V.IC1}")
    ext = []
    for n, label in TARGETS:
        m = c * n ** (-p)
        ext.append(dict(n_win=n, label=label, mde=m, clears=m < V.IC1))
        print(f"   n_win {n:>3} ({label:<18}) → MDE **{m:.3f}**  "
              f"{'✓ 문턱 아래' if m < V.IC1 else '✗ 문턱 위'}")
    now_tr = c * (len(tr) / V.HORIZON) ** (-p)
    print(f"   (참고) 현재 train n_win {len(tr)/V.HORIZON:.1f} → 적합값 {now_tr:.3f}, 실측 {anchor:.3f}")

    # 문턱을 실제로 넘기려면 창이 몇 개여야 하나
    need = (c / V.IC1) ** (1 / p)
    print(f"\n[필요량] MDE 를 {V.IC1} 아래로 내리려면 **창 {need:.0f}개**"
          f" = 약 {need*V.HORIZON/365:.1f}년 (현재 {total_win:.1f}개 / {total_win*V.HORIZON/365:.1f}년)")

    # ── 진단: 지표별 편차 — 지속성이 낮은(차분) 지표일수록 MDE 가 낮다 ──
    print("\n[진단] 전체 표본에서 지표별 MDE — 지속성이 낮을수록 검정력이 좋다")
    per = []
    for k, key in enumerate(keys):
        m = mde_for(feats, tgt, idxs, key, boot, SEED + 555 + k)
        if m is not None:
            per.append((m, key))
    for m, key in sorted(per):
        print(f"   {key:<18}{m:.3f}")
    if len(per) >= 2:
        lo, hi = min(per)[0], max(per)[0]
        print(f"   최저/최고 = {lo:.3f} / {hi:.3f} — 이 차이는 데이터 **{(hi/lo) ** (1/p):.1f}배**에 해당한다")

    # ── 진단: 전반/후반 구조가 다른가 (외삽의 전제) ──
    half = len(idxs) // 2
    print("\n[진단] 전·후반 MDE 비교 — 외삽은 '추가되는 해도 비슷한 구조'를 전제한다")
    for name, sub in (("전반", idxs[:half]), ("후반", idxs[half:])):
        vals = [m for k, key in enumerate(keys)
                if (m := mde_for(feats, tgt, sub, key, boot, SEED + 777 + k)) is not None]
        if vals:
            print(f"   {name} {d[sub[0]][:7]}~{d[sub[-1]][:7]} (창 {len(sub)/V.HORIZON:.1f}) "
                  f"MDE 중앙 {st.median(vals):.3f}")

    res = dict(note="검정력 계산 — 판정 아님", horizon=V.HORIZON, boot=boot, seed=SEED,
               anchor_mde=anchor, anchor_ok=ok, total_windows=round(total_win, 1),
               fit_c=c, fit_p=p, fit_r2=r2(pts, c, p), curve=rows,
               extrapolation=ext, windows_needed=round(need, 1), threshold=V.IC1,
               per_feature_mde={k: round(m, 4) for m, k in sorted(per)} if per else {},
               halve_factor=round(2 ** (1 / p), 2))
    with open(OUT, "w") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print(f"\n[출력] {OUT}")
    print("[반영] 없음 — 계산 전용. 실거래·판정 무관.")
    return res


if __name__ == "__main__":
    main()
