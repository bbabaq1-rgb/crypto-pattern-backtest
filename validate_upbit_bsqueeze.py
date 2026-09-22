"""업비트 B형(무거래 수축 뒤 급등) 전용 — 사전 등록 시험 (2026-09-22, 사용자 지시 "B형만 공통점 더 찾아봐, A는 애초에 대상이 아니야").

**왜 별도 판인가 — 앞선 판(validate_upbit_shoot)은 B형을 찾을 수 없는 구조였다.**
12 특성을 전부 **내림차순**으로만 줄 세웠다. `bb_width_pctile120` 내림차순은 '볼밴이 넓은 쪽'
= A형(이미 달리던 중)이다. B형은 그 반대쪽이고 규칙으로 시험된 적이 없다.

── 앞선 판과 무엇이 다른가 (결과 전 고정) ─────────────────────────────────────────
1. **풀에서 A형을 뺀다** — 그날 직전 20일 수익 > +15% 인 코인 제외. 문턱 A_TYPE_RET20 는
   앞선 판에서 이미 동결된 값이고(진단용으로 썼다) 그대로 쓴다. 인과적이라 그날 계산 가능.
2. **방향이 반대** — 수축 특성은 **오름차순**(값이 작을수록 상위)으로 줄 세운다.
3. **라벨 지평이 20봉** — B형은 '수축이 몇 주에 걸쳐 풀리는' 셋업이라 익일 라벨로는 원래
   물음에 답할 수 없다. E20 = 이후 20 거래일 안에 하루 종가 +50% 사건이 한 번이라도 발생.
   **절단 편향을 피하려고 창이 온전한 코인-일만 넣는다**(i+20 이 존재해야 한다).
4. **실용성도 20봉 수익으로 잰다** — 상위 10% 의 fwd20 평균이 유니버스 평균과 비용을 넘는가.

나머지(데이터·유니버스 180봉·하루 20종목·달력 월 창·2026-08·09 제외·train 70%·
날짜별 순열 귀무 1000회·시드)는 앞선 판과 **완전히 동일**하다.

── 주 판정 셀 하나 ────────────────────────────────────────────────────────────
`squeeze_score` = 그날 풀 안에서 **볼밴 폭 120일 백분위**와 **거래량/20일평균**의
오름차순 순위를 평균한 점수. 상위 10% = **가장 조용하고 가장 수축된 코인들**.
사용자 표현 '무거래 수축' 을 두 축 그대로 옮긴 것이고, 탐색 판 B형 관찰에서 나온
'250일 고점 −72%' 는 **일부러 주 판정에 넣지 않았다**(사건 11건을 보고 얻은 값이라
주 판정에 넣으면 사후 선택이다). 진단으로만 본다.

판정: C1 train lift>=1.50 & Holm p<.05 & 월 일관성>=0.60 / C2 holdout lift>=1.30 & p<.05 /
C3 상위10% fwd20 평균 − 유니버스 평균 > 0 (두 분할) AND holdout 상위10% − 왕복 0.1% > 0.
CONFIRMED = C1 ∧ C2 ∧ C3. **DEPLOY_ON_PASS=False.**

사전 확률(결과 전 기록): **주 판정은 C1 에서 lift < 1 로 떨어질 것으로 본다.** 앞선 판에서
높은 쪽이 2~3.4배 enriched 였으므로 낮은 쪽은 반대로 depleted 일 가능성이 크고, 탐색 판의
B형 4/11 은 '기저율만큼 나온다'(lift≈1)와 구분되지 않는다. **그러나 C3 는 처음으로 양수가
나올 수 있다** — 조용한 코인은 고변동 바구니처럼 매일 피를 흘리지 않는다. 즉 이 판의
흥미로운 결과는 '잡지는 못하는데 잃지도 않는다' 이고, 그건 진입 규칙이 아니라 **A형이
왜 손실인지**에 대한 대조 증거다. 크기·순위는 예측하지 않는다.

한계: 앞선 판의 한계 전부(생존 편향·단일 거래소 KRW·스프레드 미반영·이력 180봉) +
**E20 라벨은 코인-일이 시간축으로 겹친다**(같은 슈팅이 최대 20 코인-일을 양성으로 만든다) —
날짜별 순열 귀무는 같은 날 안에서만 섞으므로 이 겹침에 영향받지 않지만, 월 일관성과
부트 없는 p 는 실질 독립 표본이 사건 수만큼뿐임을 감안해 읽어야 한다.

실행: python validate_upbit_bsqueeze.py [--bars 1200] [--no-fetch]
출력: _upbit_bsqueeze.json + 표.
"""
import json
import math
import random
import statistics as st
import sys

import upbit_feat as UF
import validate_upbit_shoot as V

OUT = "_upbit_bsqueeze.json"

# ── 동결 상수 (V 에서 그대로 가져오는 것은 재선언하지 않는다) ────────────────────
HORIZON = 20                 # 라벨·수익 지평(거래일)
A_TYPE_MAX_RET20 = V.A_TYPE_RET20   # 0.15 — 앞선 판에서 동결된 A형 구분선
C1_LIFT, C2_LIFT = V.C1_LIFT, V.C2_LIFT
DEPLOY_ON_PASS = False

# 주 판정 = squeeze_score(복합) / B 특성 4 / 음성 대조 3 → Holm m=8
SQUEEZE_PARTS = ["bb_width_pctile120", "vol_ratio20"]      # 둘 다 오름차순
BFEAT = [
    ("bb_width_pctile120", "볼밴 폭 120일 백분위", True),
    ("vol_ratio20", "거래량/20일평균", True),
    ("range20_pct", "20일 고저폭/종가", True),
    ("atr14_pct", "ATR14/종가", True),
]
CONTROL = [
    ("dist_ma180", "종가 vs MA180", False),
    ("dd_250h", "250일 고점 대비", False),
    ("n_ma_above", "이평선 위 개수", False),
]
MAIN = ("squeeze_score", "수축 복합점수(볼폭+거래량)", True)
FEATURES = [MAIN] + BFEAT + CONTROL           # (key, label, ascending)
KEYS = [k for k, _, _ in FEATURES]
NEED = sorted({k for k, _, _ in BFEAT + CONTROL} | set(SQUEEZE_PARTS) | {"ret20"})
M_HOLM = len(FEATURES)                         # 8


def build_records(data):
    """코인-일: A형 제외 풀 + E20 라벨 + fwd20. 창이 온전한 봉만(절단 편향 방지)."""
    latest = max((r[-1]["date"] for r in data.values() if r), default=None)
    recs = []
    for m, rows0 in data.items():
        rows = [r for r in rows0 if r["date"] < latest]
        if len(rows) <= V.MIN_BARS + HORIZON + 1:
            continue
        feats = UF.compute(rows)
        cl = [r["c"] for r in rows]
        shoot = [0] * len(rows)
        for j in range(1, len(rows)):
            shoot[j] = 1 if cl[j] / cl[j - 1] - 1 >= V.THR else 0
        for i in range(V.MIN_BARS, len(rows) - HORIZON):
            f = feats[i]
            if f is None:
                continue
            vals = {k: f.get(k) for k in NEED}
            if any(v is None for v in vals.values()):
                continue
            if vals["ret20"] > A_TYPE_MAX_RET20:      # A형(이미 달리던 중) 제외
                continue
            recs.append(dict(
                date=rows[i]["date"], market=m,
                v=[vals[k] for k, _, _ in BFEAT + CONTROL],
                parts=[vals[k] for k in SQUEEZE_PARTS],
                dd250=vals["dd_250h"],
                shoot=int(any(shoot[i + 1:i + 1 + HORIZON])),
                fwd=cl[i + HORIZON] / cl[i] - 1,
                fwd60=(cl[min(i + 60, len(rows) - 1)] / cl[i] - 1)))
    return recs, latest


def add_squeeze(days):
    """그날 풀 안에서 두 축의 오름차순 순위를 평균 → squeeze_score(작을수록 수축)."""
    for rs in days.values():
        n = len(rs)
        ranks = []
        for j in range(len(SQUEEZE_PARTS)):
            order = sorted(range(n), key=lambda t: (rs[t]["parts"][j], rs[t]["market"]))
            rk = [0.0] * n
            for pos, t in enumerate(order):
                rk[t] = pos / max(1, n - 1)
            ranks.append(rk)
        for t, r in enumerate(rs):
            r["score"] = sum(rk[t] for rk in ranks) / len(ranks)


def value_of(r, ki):
    return r["score"] if ki == 0 else r["v"][ki - 1]


def capture(days, ki, asc):
    """특성 ki 의 상위 10%(asc 면 작은 쪽)가 잡은 사건 수 + 그 바구니 수익."""
    cap, tf, tf60 = {}, {}, {}
    for d, rs in days.items():
        k = V.top_k(len(rs))
        sgn = 1 if asc else -1
        srt = sorted(rs, key=lambda r: (sgn * value_of(r, ki), r["market"]))[:k]
        cap[d] = sum(r["shoot"] for r in srt)
        tf[d] = [r["fwd"] for r in srt]
        tf60[d] = [r["fwd60"] for r in srt]
    return cap, tf, tf60


def analyze(days, months, rnd):
    sub = {d: rs for d, rs in days.items() if d[:7] in months}
    ds = V.day_stats(sub)
    nulls = V.null_lifts(ds, rnd)
    uni = [r["fwd"] for rs in sub.values() for r in rs]
    uni60 = [r["fwd60"] for rs in sub.values() for r in rs]
    res = {}
    for ki, (k, name, asc) in enumerate(FEATURES):
        cap, tf, tf60 = capture(sub, ki, asc)
        lf, (sc, sk, se, sn) = V.lift_of(cap, ds)
        p = V.pval(lf, nulls)
        mons = ok = 0
        for mo in sorted(months):
            l2, (_, _, e2, _) = V.lift_of(cap, ds, months={mo})
            if e2 >= V.MIN_EVENTS_MONTH and l2 is not None:
                mons += 1
                ok += int(l2 > 1.0)
        flat = [x for v in tf.values() for x in v]
        flat60 = [x for v in tf60.values() for x in v]
        res[k] = dict(name=name, asc=asc, lift=lf, p=p, captured=sc, sum_k=sk, events=se, n=sn,
                      months_scored=mons, months_ok=ok,
                      consistency=(ok / mons if mons else None),
                      top_fwd=st.fmean(flat) if flat else None,
                      uni_fwd=st.fmean(uni) if uni else None,
                      top_fwd60=st.fmean(flat60) if flat60 else None,
                      uni_fwd60=st.fmean(uni60) if uni60 else None)
    adj = V.holm({k: res[k]["p"] for k in res})
    # V.holm 은 V.M_HOLM(12) 을 쓰므로 이 판의 m=8 로 다시 계산한다
    order = sorted(res, key=lambda k: res[k]["p"])
    run = 0.0
    for j, k in enumerate(order):
        run = max(run, min(1.0, (M_HOLM - j) * res[k]["p"]))
        res[k]["p_holm"] = run
    return dict(months=sorted(months), days=len(sub), records=sum(len(v) for v in sub.values()),
                events=sum(e for _, e, _ in ds.values()),
                base_rate=(sum(e for _, e, _ in ds.values()) / max(1, sum(n for n, _, _ in ds.values()))),
                uni_fwd=st.fmean(uni) if uni else None, by_feat=res)


def judge(tr, ho):
    out = {}
    for k, _, _ in FEATURES:
        a, b = tr["by_feat"][k], ho["by_feat"][k]
        c1 = bool(a["lift"] is not None and a["lift"] >= C1_LIFT and a["p_holm"] < V.ALPHA
                  and a["consistency"] is not None and a["consistency"] >= V.CONSISTENCY)
        c2 = bool(b["lift"] is not None and b["lift"] >= C2_LIFT and b["p"] < V.ALPHA)
        e_tr = (a["top_fwd"] - a["uni_fwd"]) if (a["top_fwd"] is not None and a["uni_fwd"] is not None) else None
        e_ho = (b["top_fwd"] - b["uni_fwd"]) if (b["top_fwd"] is not None and b["uni_fwd"] is not None) else None
        c3 = bool(e_tr is not None and e_tr > 0 and e_ho is not None and e_ho > 0
                  and b["top_fwd"] is not None and b["top_fwd"] - V.FEE > 0)
        out[k] = dict(c1=c1, c2=c2, c3=c3, edge_tr=e_tr, edge_ho=e_ho,
                      verdict=("CONFIRMED" if (c1 and c2 and c3) else "REJECTED"))
    ctrl = sum(1 for k, _, _ in CONTROL if out[k]["c1"])
    return out, ctrl


def diagnostics(days, months):
    """판정 아님 — 수축∩깊은낙폭 교집합, A형 포함 풀 대비, 사건 분포."""
    sub = {d: rs for d, rs in days.items() if d[:7] in months}
    ds = V.day_stats(sub)
    se = sum(e for _, e, _ in ds.values()); sn = sum(n for n, _, _ in ds.values())
    sc = sk = 0
    fwd = []
    for d, rs in sub.items():
        k = V.top_k(len(rs))
        s1 = {r["market"] for r in sorted(rs, key=lambda r: (r["score"], r["market"]))[:k]}
        s2 = {r["market"] for r in sorted(rs, key=lambda r: (r["dd250"], r["market"]))[:k]}
        both = [r for r in rs if r["market"] in s1 and r["market"] in s2]
        sc += sum(r["shoot"] for r in both); sk += len(both)
        fwd += [r["fwd"] for r in both]
    return dict(squeeze_x_deepdd=dict(n=sk, captured=sc,
                                      lift=((sc / sk) / (se / sn)) if (sk and se and sn) else None,
                                      fwd=st.fmean(fwd) if fwd else None),
                events=se, coin_days=sn)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    bars = int(argv[argv.index("--bars") + 1]) if "--bars" in argv else V.BARS
    data = V.ensure_cache(bars, "--no-fetch" in argv)
    recs, latest = build_records(data)
    days = V.group_days(recs)
    add_squeeze(days)
    print(f"[데이터] {len(data)} 종목 · 최신 봉 {latest}(형성 중 → 제외) · A형 제외 풀 코인-일 "
          f"{sum(len(v) for v in days.values())} · 유효 거래일 {len(days)} · 라벨 지평 {HORIZON}봉")

    months = sorted({d[:7] for d in days})
    judged = [m for m in months if m not in V.EXCLUDE_MONTHS]
    excl = [m for m in months if m in V.EXCLUDE_MONTHS]
    n_tr = max(1, int(round(len(judged) * V.TRAIN_FRAC)))
    tr_m, ho_m = set(judged[:n_tr]), set(judged[n_tr:])
    print(f"[창] 판정 {len(judged)}개월 {judged[0]}~{judged[-1]} (train {n_tr} / holdout {len(judged)-n_tr}) · 제외 {excl}")

    rnd = random.Random(V.SEED)
    tr, ho = analyze(days, tr_m, rnd), analyze(days, ho_m, rnd)
    ver, ctrl = judge(tr, ho)
    ex = analyze(days, set(excl), rnd) if excl else None

    print(f"\n[표본] train 거래일 {tr['days']} 코인-일 {tr['records']} 사건(20봉 내 슈팅) {tr['events']} "
          f"(기저 {tr['base_rate']*100:.2f}%) fwd{HORIZON} 유니버스 {tr['uni_fwd']*100:+.2f}% / "
          f"holdout {ho['days']} {ho['records']} {ho['events']} ({ho['base_rate']*100:.2f}%) {ho['uni_fwd']*100:+.2f}%")
    print(f"\n{'특성':28} {'방향':4} {'train':>6} {'Holm p':>7} {'월일관':>7} | {'hold':>6} {'p':>6} | "
          f"{'엣지(tr)':>9} {'엣지(ho)':>9} | 판정")
    for ki, (k, name, asc) in enumerate(FEATURES):
        a, b, v = tr["by_feat"][k], ho["by_feat"][k], ver[k]
        tag = "대조 " if any(k == c for c, _, _ in CONTROL) else ("**" if ki == 0 else "")
        cons = f"{a['months_ok']}/{a['months_scored']}" if a["months_scored"] else "  -"
        fail = "".join(c for c, f in zip("123", (v["c1"], v["c2"], v["c3"])) if not f)
        print(f"{tag+name:28} {'낮은쪽' if asc else '높은쪽':4} {V.fmt_lift(a['lift'])} {a['p_holm']:7.3f} "
              f"{cons:>7} | {V.fmt_lift(b['lift'])} {b['p']:6.3f} | "
              f"{(v['edge_tr'] or 0)*100:+8.2f}% {(v['edge_ho'] or 0)*100:+8.2f}% | "
              f"{v['verdict']}{'' if not fail else ' (' + fail + ')'}")

    conf = [k for k, _, _ in FEATURES if ver[k]["verdict"] == "CONFIRMED" and not any(k == c for c, _, _ in CONTROL)]
    invalid = ctrl >= 2
    print(f"\n[판정] 주 판정 squeeze_score = {ver['squeeze_score']['verdict']} · CONFIRMED {len(conf)} / 가설 5")
    print(f"[대조] C1 통과 {ctrl}/{len(CONTROL)}" + ("  ← 2개 이상 → 판 전체 INVALID" if invalid else ""))
    print(f"[반영] DEPLOY_ON_PASS={DEPLOY_ON_PASS} — 실거래 변경 없음")

    print("\n== 진단(판정 아님) ==")
    for nm, ms in (("train", tr_m), ("holdout", ho_m)):
        dg = diagnostics(days, ms)
        x = dg["squeeze_x_deepdd"]
        print(f"  {nm}: 수축∩250고점낙폭 상위 교집합 {x['n']}일-건 lift {V.fmt_lift(x['lift'])} "
              f"fwd{HORIZON} {(x['fwd'] or 0)*100:+.2f}%")
    m = tr["by_feat"]["squeeze_score"]
    print(f"  squeeze 상위 fwd60 train {(m['top_fwd60'] or 0)*100:+.2f}% vs 유니버스 {(m['uni_fwd60'] or 0)*100:+.2f}%")
    m = ho["by_feat"]["squeeze_score"]
    print(f"  squeeze 상위 fwd60 holdout {(m['top_fwd60'] or 0)*100:+.2f}% vs 유니버스 {(m['uni_fwd60'] or 0)*100:+.2f}%")
    if ex:
        e = ex["by_feat"]["squeeze_score"]
        print(f"\n== 제외 창 {excl} (판정 아님) == squeeze lift {V.fmt_lift(e['lift'])} p {e['p']:.3f} "
              f"엣지 {((e['top_fwd'] or 0)-(e['uni_fwd'] or 0))*100:+.2f}%")

    json.dump(dict(latest=latest, judged=judged, excluded=excl, train=tr, holdout=ho,
                   excluded_window=ex, verdicts=ver, control_c1=ctrl, invalid=invalid,
                   diag=dict(train=diagnostics(days, tr_m), holdout=diagnostics(days, ho_m)),
                   frozen=dict(horizon=HORIZON, a_type_max_ret20=A_TYPE_MAX_RET20,
                               squeeze_parts=SQUEEZE_PARTS, top_frac=V.TOP_FRAC, boot=V.BOOT,
                               seed=V.SEED, c1_lift=C1_LIFT, c2_lift=C2_LIFT, alpha=V.ALPHA,
                               consistency=V.CONSISTENCY, fee=V.FEE, m_holm=M_HOLM,
                               min_bars=V.MIN_BARS, exclude_months=list(V.EXCLUDE_MONTHS))),
              open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"\n저장: {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
