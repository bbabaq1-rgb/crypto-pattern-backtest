"""업비트 일봉 +50% 슈팅 선행 신호 — 사전 등록 시험 (2026-09-21, 사용자 지시 "사전 등록해서 여러 창으로 돌려봐").

탐색적 스터디(study_upbit_shooting.py, 2026-09-21)가 최근 30일 11건에서 'D-1 에 거래대금·변동성·
고저폭이 크다'를 관찰했다. 그 창은 이미 봤으므로 **판정에서 제외**하고, 같은 가설을 여러 해·
여러 달 창에서 사전 등록 기준으로 다시 잰다.

── 탐색 판과 무엇이 다른가 (결과 전 고정) ─────────────────────────────────────────────
· 관측 단위를 사건이 아니라 **코인-일**로 바꿨다. 탐색 판의 '베이스라인 중앙값 위 비율'은
  사건이 11건이라 표본 오차가 컸고, 다중검정·창 분할이 없었다.
· 규칙을 **그날 실행 가능한 형태**로 바꿨다 — 매일 종가에 전 종목을 한 특성으로 줄 세워
  상위 10%(top decile)를 사고 다음 날 종가에 판다. 특성은 그 봉까지만 쓴다(인과).
  lift = P(슈팅 | 상위 10%) / P(슈팅 | 전체). 1.0 이면 정보 없음.
· 귀무분포는 **같은 날 같은 개수를 무작위로 고르는 순열**(날짜별 초기하). 슈팅이 특정 달에
  몰려 있어도 그 편중이 귀무에 똑같이 들어가므로 '장이 좋았다'를 엣지로 오인하지 않는다.
  귀무 통계량이 (n_d, k_d, e_d) 에만 의존하므로 **한 번 만든 귀무를 12 특성이 공유**한다.
· **음성 대조 3종**(탐색 판에서 구분이 없던 특성)을 같은 잣대로 돌린다. 2개 이상이 C1 을
  통과하면 프레임이 무언가를 잘못 세고 있다는 뜻이므로 **판 전체를 INVALID** 로 기록한다.

── 동결 파라미터 ────────────────────────────────────────────────────────────────────
· 사건 = 닫힌 일봉 종가 기준 (종가/전일종가 − 1) ≥ +50%. 형성 중인 마지막 봉 제외.
· 유니버스 = 업비트 KRW 전 종목 중 **이력 180봉 이상**(MA180 정의 + 신규 상장 펌프 분리).
  판정 12 특성이 모두 계산되는 코인-일만 넣는다 — 그래야 날짜별 n_d 가 특성마다 같아
  공유 귀무가 성립한다.
· 하루 유니버스 20종목 미만인 날은 제외(횡단면이 성립 안 함).
· 창 = 달력 월. **2026-08·2026-09 는 판정에서 제외**(탐색 판이 본 창) — 따로 병기.
· train = 앞 70% 달, holdout = 뒤 30% 달.
· 판정: C1 train lift ≥ 1.50 AND Holm(m=12) p < .05 AND 월 일관성 ≥ 0.60
        C2 holdout lift ≥ 1.30 AND p < .05
        C3 실용성 — 상위10% 평균 익일수익 − 전체 평균 > 0 (두 분할 모두)
                     AND holdout 상위10% 평균 − 왕복 0.1% > 0
  CONFIRMED = C1 ∧ C2 ∧ C3. **DEPLOY_ON_PASS=False — 통과해도 실거래 반영 없음.**

사전 확률(결과 전 기록): lift ≥ 1.5 는 그럴듯하다(변동성은 자기상관이 강하므로 어제 변동성이
큰 코인이 오늘도 크게 움직인다). **그러나 C3 에서 죽을 것으로 본다** — 고변동 상위 10% 는 슈팅도
더 자주 나지만 폭락도 더 자주 난다. xsec_chars(2026-09-07)의 rvol20 이 정확히 그 구조였다
('순위 예측이지 평균수익이 아니다'). bb_width_pctile120 은 탐색 판에서 A형(확장)·B형(수축)
두 유형이 섞여 방향 자체가 모호하므로 가장 먼저 탈락할 것으로 본다.

한계(결과 전 기록): 생존 편향(현재 업비트에 남아 있는 종목만) · 단일 거래소 KRW 시장
(김치 프리미엄·상장 이벤트) · 스프레드·슬리피지 미반영 · 종가 체결 가정.

실행: python validate_upbit_shoot.py [--bars 1200] [--no-fetch]
출력: _upbit_shoot.json + 표.
"""
import json
import math
import os
import random
import statistics as st
import sys
import time
import urllib.parse

import upbit_feat as UF
from study_upbit_shooting import _get, krw_markets

CACHE = "data_upbit_krw_1d.json"
OUT = "_upbit_shoot.json"

# ── 동결 상수 ──────────────────────────────────────────────────────────────────────
BARS = 1200                 # 종목당 일봉 수집 상한(약 3.3년)
THR = 0.50                  # 사건 문턱
MIN_BARS = 180              # 이력 요건(MA180)
TOP_FRAC = 0.10             # 상위 분위
MIN_UNIVERSE = 20           # 하루 최소 종목 수
BOOT = 1000
SEED = 20260921
EXCLUDE_MONTHS = ("2026-08", "2026-09")
TRAIN_FRAC = 0.70
C1_LIFT, C2_LIFT = 1.50, 1.30
ALPHA = 0.05
CONSISTENCY = 0.60
MIN_EVENTS_MONTH = 3        # 월 일관성 집계에 넣을 최소 사건 수
FEE = 0.001                 # 업비트 왕복 수수료(0.05% × 2)
A_TYPE_RET20 = 0.15         # 진단: A형(이미 달리던 중) 구분선
DEPLOY_ON_PASS = False

HYPO = [
    ("turnover20_krw", "20일 평균 거래대금"),
    ("atr14_pct", "ATR14/종가"),
    ("range20_pct", "20일 고저폭/종가"),
    ("vol_ratio20", "거래량/20일평균"),
    ("vol_ratio20_prev5", "최근5일 거래량/20일평균"),
    ("from_60lo", "60일 저점 대비"),
    ("ma20_slope20", "MA20 20일 기울기"),
    ("bb_width_pctile120", "볼밴 폭 120일 백분위"),
    ("rsi14", "RSI14"),
]
CONTROL = [
    ("dist_ma180", "종가 vs MA180"),
    ("dd_250h", "250일 고점 대비"),
    ("n_ma_above", "이평선 위 개수"),
]
FEATURES = HYPO + CONTROL
KEYS = [k for k, _ in FEATURES]
M_HOLM = len(FEATURES)       # 12


# ─────────────────────────────────────────── 수집 ───────────────────────────────────────────
def _page(market, to=None):
    u = f"https://api.upbit.com/v1/candles/days?market={market}&count=200"
    if to:
        u += "&to=" + urllib.parse.quote(to)
    return _get(u)


def _rowify(c):
    return dict(date=c["candle_date_time_kst"][:10], o=c["opening_price"], h=c["high_price"],
                l=c["low_price"], c=c["trade_price"], v=c["candle_acc_trade_volume"],
                krw=c["candle_acc_trade_price"])


def ensure_cache(bars=BARS, no_fetch=False):
    """캐시를 bars 봉까지 **뒤로** 확장한다. 기존 캐시(400봉)를 버리지 않는다."""
    data = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}
    if no_fetch:
        return data
    mk = krw_markets()
    print(f"[수집] 업비트 KRW {len(mk)} 종목 → {bars}봉", flush=True)
    for i, m in enumerate(mk):
        rows = data.get(m) or []
        try:
            if not rows:                                  # 신규 종목 — 최신부터
                d = _page(m)
                rows = sorted((_rowify(c) for c in d), key=lambda r: r["date"])
                time.sleep(0.12)
            guard = 0
            while len(rows) < bars and guard < 20:
                guard += 1
                d = _page(m, f"{rows[0]['date']} 00:00:00")
                if not d:
                    break
                add = {r["date"]: r for r in (_rowify(c) for c in d)}
                add.update({r["date"]: r for r in rows})
                rows = [add[k] for k in sorted(add)]
                time.sleep(0.12)
            data[m] = rows
        except Exception as e:
            print(f"  {m} 실패: {str(e)[:60]}")
        if (i + 1) % 50 == 0:
            print(f"  {i+1}/{len(mk)}", flush=True)
    json.dump(data, open(CACHE, "w", encoding="utf-8"))
    return data


# ─────────────────────────────────────────── 표본 ───────────────────────────────────────────
def build_records(data):
    """코인-일 관측: 특성(닫힌 봉 i) + 라벨(i+1 의 슈팅 여부) + 익일 수익."""
    latest = max((r[-1]["date"] for r in data.values() if r), default=None)
    recs = []
    for m, rows0 in data.items():
        rows = [r for r in rows0 if r["date"] < latest]      # 형성 중인 마지막 봉 제외
        if len(rows) <= MIN_BARS + 1:
            continue
        feats = UF.compute(rows)
        cl = [r["c"] for r in rows]
        for i in range(MIN_BARS, len(rows) - 1):
            f = feats[i]
            if f is None:
                continue
            vals = [f.get(k) for k in KEYS]
            if any(v is None for v in vals):
                continue
            fwd1 = cl[i + 1] / cl[i] - 1
            fwd5 = cl[min(i + 5, len(rows) - 1)] / cl[i] - 1
            recs.append(dict(date=rows[i]["date"], market=m, v=vals, ret20=f["ret20"],
                             fwd1=fwd1, fwd5=fwd5, shoot=int(fwd1 >= THR),
                             shoot_hi=int(rows[i + 1]["h"] / cl[i] - 1 >= THR)))
    return recs, latest


def group_days(recs):
    by = {}
    for r in recs:
        by.setdefault(r["date"], []).append(r)
    return {d: v for d, v in by.items() if len(v) >= MIN_UNIVERSE}


def top_k(n):
    return max(1, int(math.ceil(TOP_FRAC * n)))


# ─────────────────────────────────────────── 계산 ───────────────────────────────────────────
def day_stats(days, label="shoot"):
    """날짜별 (n_d, e_d, k_d) — 특성과 무관하므로 귀무가 이걸 공유한다."""
    out = {}
    for d, rs in days.items():
        n = len(rs)
        out[d] = (n, sum(r[label] for r in rs), top_k(n))
    return out


def feature_capture(days, ki, label="shoot"):
    """특성 ki 상위 10% 가 잡은 사건 수 — 날짜별. 동점은 종목명 오름차순(결정론)."""
    cap, top_fwd1, top_fwd5 = {}, {}, {}
    for d, rs in days.items():
        k = top_k(len(rs))
        srt = sorted(rs, key=lambda r: (-r["v"][ki], r["market"]))[:k]
        cap[d] = sum(r[label] for r in srt)
        top_fwd1[d] = [r["fwd1"] for r in srt]
        top_fwd5[d] = [r["fwd5"] for r in srt]
    return cap, top_fwd1, top_fwd5


def lift_of(cap, ds, months=None):
    sc = sk = se = sn = 0
    for d, (n, e, k) in ds.items():
        if months is not None and d[:7] not in months:
            continue
        sc += cap[d]; sk += k; se += e; sn += n
    if not sk or not se or not sn:
        return None, (sc, sk, se, sn)
    base = se / sn
    return (sc / sk) / base, (sc, sk, se, sn)


def null_lifts(ds, rnd):
    """날짜별 초기하 추출 — 특성 비의존. 반환은 BOOT 개의 lift."""
    ev_days = [(n, e, k) for (n, e, k) in ds.values() if e > 0 and k > 0]
    sk = sum(k for _, _, k in ds.values())
    se = sum(e for _, e, _ in ds.values())
    sn = sum(n for n, _, _ in ds.values())
    if not sk or not se or not sn:
        return []
    base = se / sn
    out = []
    for _ in range(BOOT):
        c = 0
        for n, e, k in ev_days:
            if k >= n:
                c += e
            else:
                c += sum(1 for x in rnd.sample(range(n), k) if x < e)
        out.append((c / sk) / base)
    return out


def pval(obs, nulls):
    if obs is None or not nulls:
        return 1.0
    return (1 + sum(1 for x in nulls if x >= obs)) / (len(nulls) + 1)


def holm(pvals):
    """pvals: {key: p} → {key: adjusted p}. m 은 등록된 특성 수로 고정."""
    order = sorted(pvals, key=lambda k: pvals[k])
    adj, run = {}, 0.0
    for j, k in enumerate(order):
        run = max(run, min(1.0, (M_HOLM - j) * pvals[k]))
        adj[k] = run
    return adj


def analyze(days, months, rnd):
    """한 분할(달 집합)의 전 특성 결과."""
    sub = {d: rs for d, rs in days.items() if d[:7] in months}
    ds = day_stats(sub)
    nulls = null_lifts(ds, rnd)
    uni = [r["fwd1"] for rs in sub.values() for r in rs]
    uni5 = [r["fwd5"] for rs in sub.values() for r in rs]
    res = {}
    for ki, (k, name) in enumerate(FEATURES):
        cap, tf1, tf5 = feature_capture(sub, ki)
        lf, (sc, sk, se, sn) = lift_of(cap, ds)
        p = pval(lf, nulls)
        # 월 일관성
        mons, ok = 0, 0
        for mo in sorted(months):
            l2, (_, _, e2, _) = lift_of(cap, ds, months={mo})
            if e2 >= MIN_EVENTS_MONTH and l2 is not None:
                mons += 1
                ok += int(l2 > 1.0)
        flat1 = [x for v in tf1.values() for x in v]
        flat5 = [x for v in tf5.values() for x in v]
        # 고가 라벨(진단)
        ds_hi = day_stats(sub, "shoot_hi")
        cap_hi, _, _ = feature_capture(sub, ki, "shoot_hi")
        lf_hi, _ = lift_of(cap_hi, ds_hi)
        res[k] = dict(name=name, lift=lf, p=p, captured=sc, sum_k=sk, events=se, n=sn,
                      months_scored=mons, months_ok=ok,
                      consistency=(ok / mons if mons else None),
                      top_fwd1=st.fmean(flat1) if flat1 else None,
                      uni_fwd1=st.fmean(uni) if uni else None,
                      top_fwd5=st.fmean(flat5) if flat5 else None,
                      uni_fwd5=st.fmean(uni5) if uni5 else None,
                      lift_high=lf_hi)
    adj = holm({k: res[k]["p"] for k in res})
    for k in res:
        res[k]["p_holm"] = adj[k]
    return dict(months=sorted(months), days=len(sub), records=sum(len(v) for v in sub.values()),
                events=sum(e for _, e, _ in ds.values()),
                base_rate=(sum(e for _, e, _ in ds.values()) / max(1, sum(n for n, _, _ in ds.values()))),
                uni_fwd1=st.fmean(uni) if uni else None, by_feat=res)


def judge(tr, ho):
    """사전 등록 판정."""
    out = {}
    for k, _ in FEATURES:
        a, b = tr["by_feat"][k], ho["by_feat"][k]
        c1 = bool(a["lift"] is not None and a["lift"] >= C1_LIFT and a["p_holm"] < ALPHA
                  and a["consistency"] is not None and a["consistency"] >= CONSISTENCY)
        c2 = bool(b["lift"] is not None and b["lift"] >= C2_LIFT and b["p"] < ALPHA)
        edge_tr = (a["top_fwd1"] - a["uni_fwd1"]) if (a["top_fwd1"] is not None and a["uni_fwd1"] is not None) else None
        edge_ho = (b["top_fwd1"] - b["uni_fwd1"]) if (b["top_fwd1"] is not None and b["uni_fwd1"] is not None) else None
        c3 = bool(edge_tr is not None and edge_tr > 0 and edge_ho is not None and edge_ho > 0
                  and b["top_fwd1"] is not None and b["top_fwd1"] - FEE > 0)
        out[k] = dict(c1=c1, c2=c2, c3=c3, edge_tr=edge_tr, edge_ho=edge_ho,
                      verdict=("CONFIRMED" if (c1 and c2 and c3) else "REJECTED"))
    ctrl_c1 = sum(1 for k, _ in CONTROL if out[k]["c1"])
    return out, ctrl_c1


# ─────────────────────────────────────────── 진단 ───────────────────────────────────────────
def diagnostics(days, months, rnd):
    sub = {d: rs for d, rs in days.items() if d[:7] in months}
    ds = day_stats(sub)
    # A/B 유형: 사건 코인-일의 직전 20일 수익
    ev = [r for rs in sub.values() for r in rs if r["shoot"]]
    a_type = sum(1 for r in ev if r["ret20"] > A_TYPE_RET20)
    # 조합 규칙: 거래대금·ATR 둘 다 상위 10%
    i_to, i_atr = KEYS.index("turnover20_krw"), KEYS.index("atr14_pct")
    sc = sk = 0
    fwd = []
    for d, rs in sub.items():
        k = top_k(len(rs))
        s1 = {r["market"] for r in sorted(rs, key=lambda r: (-r["v"][i_to], r["market"]))[:k]}
        s2 = {r["market"] for r in sorted(rs, key=lambda r: (-r["v"][i_atr], r["market"]))[:k]}
        both = [r for r in rs if r["market"] in s1 and r["market"] in s2]
        sc += sum(r["shoot"] for r in both); sk += len(both)
        fwd += [r["fwd1"] for r in both]
    se = sum(e for _, e, _ in ds.values()); sn = sum(n for n, _, _ in ds.values())
    comb = dict(n=sk, captured=sc,
                lift=((sc / sk) / (se / sn)) if (sk and se and sn) else None,
                fwd1=st.fmean(fwd) if fwd else None)
    by_month = {}
    for mo in sorted(months):
        e = n = 0
        for d, (nd, ed, _) in ds.items():
            if d[:7] == mo:
                e += ed; n += nd
        by_month[mo] = dict(events=e, coin_days=n, rate=(e / n if n else None))
    return dict(events=len(ev), a_type=a_type, b_type=len(ev) - a_type, combined=comb, by_month=by_month)


# ─────────────────────────────────────────── 실행 ───────────────────────────────────────────
def fmt_lift(x):
    return "  n/a" if x is None else f"{x:5.2f}"


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    bars = int(argv[argv.index("--bars") + 1]) if "--bars" in argv else BARS
    data = ensure_cache(bars, "--no-fetch" in argv)
    recs, latest = build_records(data)
    days = group_days(recs)
    print(f"[데이터] {len(data)} 종목 · 최신 봉 {latest}(형성 중 → 제외) · 코인-일 {len(recs)} · "
          f"유효 거래일 {len(days)}")

    months = sorted({d[:7] for d in days})
    judged = [m for m in months if m not in EXCLUDE_MONTHS]
    held_out_of_study = [m for m in months if m in EXCLUDE_MONTHS]
    n_tr = max(1, int(round(len(judged) * TRAIN_FRAC)))
    tr_m, ho_m = set(judged[:n_tr]), set(judged[n_tr:])
    print(f"[창] 판정 {len(judged)}개월 {judged[0]}~{judged[-1]} "
          f"(train {n_tr} {judged[0]}~{judged[n_tr-1]} / holdout {len(judged)-n_tr} "
          f"{judged[n_tr] if len(judged)>n_tr else '-'}~{judged[-1]}) · 제외 {held_out_of_study}")

    rnd = random.Random(SEED)
    tr = analyze(days, tr_m, rnd)
    ho = analyze(days, ho_m, rnd)
    ver, ctrl_c1 = judge(tr, ho)
    ex = analyze(days, set(held_out_of_study), rnd) if held_out_of_study else None

    print(f"\n[표본] train 거래일 {tr['days']} 코인-일 {tr['records']} 사건 {tr['events']} "
          f"(기저 {tr['base_rate']*100:.3f}%) / holdout 거래일 {ho['days']} 코인-일 {ho['records']} "
          f"사건 {ho['events']} (기저 {ho['base_rate']*100:.3f}%)")
    print(f"\n{'특성':26} {'train':>6} {'Holm p':>7} {'월일관':>7} | {'hold':>6} {'p':>6} | "
          f"{'엣지(tr)':>9} {'엣지(ho)':>9} | 판정")
    for k, name in FEATURES:
        a, b, v = tr["by_feat"][k], ho["by_feat"][k], ver[k]
        tag = "대조 " if any(k == c for c, _ in CONTROL) else ""
        cons = f"{a['months_ok']}/{a['months_scored']}" if a["months_scored"] else "  -"
        print(f"{tag+name:26} {fmt_lift(a['lift'])} {a['p_holm']:7.3f} {cons:>7} | "
              f"{fmt_lift(b['lift'])} {b['p']:6.3f} | "
              f"{(v['edge_tr'] or 0)*100:+8.2f}% {(v['edge_ho'] or 0)*100:+8.2f}% | "
              f"{v['verdict']}{'' if v['verdict']=='CONFIRMED' else ' (' + ''.join(c for c,f in zip('123',(v['c1'],v['c2'],v['c3'])) if not f) + ')'}")

    conf = [k for k, _ in HYPO if ver[k]["verdict"] == "CONFIRMED"]
    invalid = ctrl_c1 >= 2
    print(f"\n[판정] CONFIRMED {len(conf)} / 가설 {len(HYPO)}"
          f"{' — ' + ', '.join(conf) if conf else ''}")
    print(f"[대조] C1 통과 {ctrl_c1}/{len(CONTROL)}" + ("  ← 2개 이상 → 판 전체 INVALID" if invalid else ""))
    print(f"[반영] DEPLOY_ON_PASS={DEPLOY_ON_PASS} — 실거래 변경 없음")

    dg_tr, dg_ho = diagnostics(days, tr_m, rnd), diagnostics(days, ho_m, rnd)
    print(f"\n== 진단(판정 아님) ==")
    for nm, dg in (("train", dg_tr), ("holdout", dg_ho)):
        c = dg["combined"]
        print(f"  {nm}: 사건 {dg['events']} (A형 이미 달리던 중 {dg['a_type']} / B형 {dg['b_type']}) · "
              f"거래대금∩ATR 상위 {c['n']}일-건 lift {fmt_lift(c['lift'])} 익일 "
              f"{(c['fwd1'] or 0)*100:+.2f}%")
    print("  고가 라벨 lift(train):", ", ".join(
        f"{k} {fmt_lift(tr['by_feat'][k]['lift_high'])}" for k, _ in HYPO[:4]))
    print("  D+5: " + ", ".join(
        f"{k} 상위 {(tr['by_feat'][k]['top_fwd5'] or 0)*100:+.1f}% vs 전체 {(tr['by_feat'][k]['uni_fwd5'] or 0)*100:+.1f}%"
        for k, _ in HYPO[:3]))
    if ex:
        print(f"\n== 제외 창 {held_out_of_study} (탐색 판이 본 창 — 판정 아님) ==")
        for k, name in HYPO[:5]:
            e = ex["by_feat"][k]
            print(f"  {name:26} lift {fmt_lift(e['lift'])} p {e['p']:.3f} "
                  f"엣지 {((e['top_fwd1'] or 0)-(e['uni_fwd1'] or 0))*100:+.2f}%")

    json.dump(dict(latest=latest, months=months, judged=judged, excluded=held_out_of_study,
                   train=tr, holdout=ho, excluded_window=ex, verdicts=ver,
                   control_c1=ctrl_c1, invalid=invalid, confirmed=conf,
                   diag=dict(train=dg_tr, holdout=dg_ho),
                   frozen=dict(thr=THR, min_bars=MIN_BARS, top_frac=TOP_FRAC, boot=BOOT, seed=SEED,
                               c1_lift=C1_LIFT, c2_lift=C2_LIFT, alpha=ALPHA,
                               consistency=CONSISTENCY, fee=FEE, m_holm=M_HOLM,
                               exclude_months=list(EXCLUDE_MONTHS), train_frac=TRAIN_FRAC)),
              open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"\n저장: {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
