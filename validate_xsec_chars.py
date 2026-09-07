"""
validate_xsec_chars.py — 횡단면 특성 연구 (2026-09-07 사전 등록, 사용자 지시 "패턴 말고 다른 방향으로 엣지 … 어떤 조건에
있었던 것들이 더 많이 빠르게 올랐는가" + "일목균형표·다이버전스 상태·60/120/180선 대비 위치 등 싹 다").

## 질문
매월 말, 유동성 적격 코인들을 **같은 시점의 상태 변수**(xsec_features.FAMILY 25종)로 줄 세웠을 때 그 순서가 이후
20봉 수익률(주 결과)·60봉 수익률·'40봉 내 고가 +20% 도달'(빠르기, 진단) 순서를 예측하는가. 패턴 진입이 아니라
**코인 선택**의 물음이다 — 통과 변수는 그대로 매매 규칙이 아니고, 다음 단계(슬롯 우선순위 오버레이 또는 단독
진입 규칙)를 별도 사전 등록해야 한다. DEPLOY_ON_PASS=False, 실거래 무변경(관찰 기간 ~2026-10-06).

## 프레임 (동결)
  · 유니버스: PIT liquid — 월말 30일 거래대금 순위, 적격 60봉(validate_pit_cohort.pit_membership 그대로). 월 M 말
    형성 시점의 적격 집합 = pm[M+1](M 말 기준 순위가 다음 달 적용분이므로 형성 시점에 알 수 있는 정보와 같다).
    2017~ 장기 이력(data_long) + OKX. top30 판은 진단.
  · 형성 시점: 각 달 마지막 봉(코인별). 피처는 그 봉까지의 정보만(xsec_features 가 인과, 테스트 고정).
  · 결과: fwd20 = 20봉 뒤 종가/형성 종가 − 1 (주 판정). fwd60·hit20_40 은 진단.
  · 월별 통계: 스피어만 순위상관 IC(피처, fwd20), 상·하위 20% 평균(TOP/BOT, 동률은 심볼명으로 결정론적 절단), 유니버스 평균.
    횡단면 코인 수 MIN_CS(15) 미만인 달은 그 변수에서 제외.
  · 방향: '+'/'-' 변수는 사전 부호로 정렬, '?' 변수는 **train 평균 IC 부호**를 방향으로 정하고 OOS 에 그 부호를 요구
    (train 검정은 양측 p).
  · 분할: train 월 < 2025-01 / OOS 월 >= 2025-01 (v4 와 동일 날짜).
  · train 적격(전부): Holm(가족 25) p < .05 · 연도별(월 >= 6) 정렬 IC 양수 비율 >= 60% · 최고 연도 제외 평균 IC > 0 ·
    train 월 >= 24.
  · OOS 재현(전부): 월 >= 10 · 정렬 평균 IC > 0 · 월 부트 단측 p < .05(비보정) · TOP 평균 − 유니버스 평균 > 0 ·
    TOP 평균 − 왕복 비용 0.4% > 0.
  · 판정: CONFIRMED(train+OOS) / TRAIN_ONLY(train 만) / REJECTED. 부호 지정 변수가 train 에서 반대 부호로 양측 p<.05 면
    REVERSED 표기(진단 — 새 규칙으로 승격하지 않고, 추격하려면 별도 사전 등록).
  · p 는 월 블록 부트스트랩 1000회(시드 고정), 통계량 = 월 IC 평균.

## 진단 (판정 아님)
  D1 fwd60·hit20_40 IC 부호 일치 / D2 레짐별(형성일 라벨) IC / D3 top30 코호트 IC / D4 변수 간 순위상관(중복 확인) /
  D5 사용자 원 질문 그대로: 최근 365일 수익 4분위별 시작 시점 피처 중앙값 + 단일 횡단면 스피어만 / D6 CONFIRMED 변수
  순위평균 합성 IC(사후 합성 — 참고만).

실행: python validate_xsec_chars.py [--no-fetch]        출력: _xsec_chars.json + RESULT_JSON
"""
import json
import math
import random
import statistics as st
import sys
from datetime import date, timedelta

import regime_switch as rs
import validate_guard_v4 as g4
import validate_pit_cohort as pc
import validate_regime_split_all as va
import xsec_features as xf

# ── 동결 파라미터 ─────────────────────────────────────────────────────────────────────────────
SPLIT_MONTH = "2025-01"
MIN_CS = 15                 # 횡단면 최소 코인 수
MIN_TRAIN_MONTHS = 24
MIN_OOS_MONTHS = 10
MIN_YEAR_MONTHS = 6
YEAR_POS_SHARE = 0.60
ALPHA = 0.05
COST_RT = 0.004             # 왕복 비용 스트레스(v4 STRESS_REQUIRED 와 동일)
BOOT_N, SEED = 1000, 42
QUANT = 0.20
DEPLOY_ON_PASS = False
REGIMES = ("bull_btc", "bull_altseason", "bear")
CORR_FLAG = 0.70


# ── 통계 ──────────────────────────────────────────────────────────────────────────────────────
def ranks(xs):
    """동률 평균 순위 (1..n)."""
    order = sorted(range(len(xs)), key=lambda k: xs[k])
    r = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            r[order[k]] = avg
        i = j + 1
    return r


def spearman(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    rx, ry = ranks(xs), ranks(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    sxx = sum((a - mx) ** 2 for a in rx)
    syy = sum((b - my) ** 2 for b in ry)
    if sxx <= 0 or syy <= 0:
        return None
    return sxy / math.sqrt(sxx * syy)


def cross_section(items, quant=QUANT):
    """items = [(sym, feat, ret)] → dict(n, ic, top, bot, uni). top/bot 은 피처 상·하위 quant 평균(심볼명으로 동률 절단)."""
    n = len(items)
    ic = spearman([f for _, f, _ in items], [r for _, _, r in items])
    srt = sorted(items, key=lambda t: (t[1], t[0]))
    k = max(3, int(n * quant))
    bot = st.mean(r for _, _, r in srt[:k])
    top = st.mean(r for _, _, r in srt[-k:])
    return dict(n=n, ic=ic, top=top, bot=bot, uni=st.mean(r for _, _, r in items))


def boot_p(vals, n_boot=BOOT_N, seed=SEED, two_sided=False):
    """월 블록 부트: 통계량 = 평균. 단측 p = P(평균 <= 0); 양측 = 2·min(P<=0, P>=0)."""
    if not vals:
        return None
    rng = random.Random(seed)
    n = len(vals)
    le = ge = 0
    for _ in range(n_boot):
        m = sum(vals[rng.randrange(n)] for _ in range(n)) / n
        le += m <= 0; ge += m >= 0
    p_le, p_ge = le / n_boot, ge / n_boot
    return min(1.0, 2 * min(p_le, p_ge)) if two_sided else p_le


def yearly(ms):
    """{year: mean ic} (월 >= MIN_YEAR_MONTHS 만)."""
    by = {}
    for m in ms:
        by.setdefault(m["month"][:4], []).append(m["ic"])
    return {y: st.mean(v) for y, v in by.items() if len(v) >= MIN_YEAR_MONTHS}


def orient(ms, d):
    """월 통계 목록을 방향 d('+'/'-') 로 정렬: ic 부호, top/bot 교환."""
    out = []
    for m in ms:
        if d == "+":
            out.append(dict(m))
        else:
            out.append(dict(m, ic=-m["ic"], top=m["bot"], bot=m["top"]))
    return out


def judge_var(key, sign, train_ms, oos_ms, p_holm=None):
    """한 변수의 판정 재료. p_holm 은 가족 보정 뒤 채워진다(judge_family)."""
    tr_raw = st.mean(m["ic"] for m in train_ms) if train_ms else None
    if sign in "+-":
        d = sign
    else:
        d = "+" if (tr_raw is None or tr_raw >= 0) else "-"
    tr, oo = orient(train_ms, d), orient(oos_ms, d)
    tr_ic = [m["ic"] for m in tr]
    rec = dict(key=key, group=xf.GROUP[key], sign=sign, dir=d, train_months=len(tr), oos_months=len(oo),
               train_ic=st.mean(tr_ic) if tr_ic else None,
               train_p=boot_p(tr_ic, two_sided=(sign == "?")) if tr_ic else None,
               train_p_two=boot_p(tr_ic, two_sided=True) if tr_ic else None,
               train_icir=(st.mean(tr_ic) / st.pstdev(tr_ic) * math.sqrt(len(tr_ic))) if len(tr_ic) > 2 and st.pstdev(tr_ic) > 0 else None,
               train_years=yearly(tr), train_top_edge=st.mean(m["top"] - m["uni"] for m in tr) if tr else None,
               train_spread=st.mean(m["top"] - m["bot"] for m in tr) if tr else None,
               oos_ic=None, oos_p=None, oos_top_edge=None, oos_top_abs=None, oos_spread=None, oos_years=yearly(oo))
    ys = rec["train_years"]
    rec["year_pos_share"] = (sum(1 for v in ys.values() if v > 0) / len(ys)) if ys else None
    if ys and len(ys) >= 2:
        best = max(ys, key=ys.get)
        rest = [m["ic"] for m in tr if m["month"][:4] != best]
        rec["lbyo_ic"] = st.mean(rest) if rest else None
        rec["best_year"] = best
    else:
        rec["lbyo_ic"], rec["best_year"] = None, None
    if oo:
        oo_ic = [m["ic"] for m in oo]
        rec.update(oos_ic=st.mean(oo_ic), oos_p=boot_p(oo_ic), oos_top_edge=st.mean(m["top"] - m["uni"] for m in oo),
                   oos_top_abs=st.mean(m["top"] for m in oo), oos_spread=st.mean(m["top"] - m["bot"] for m in oo))
    rec["reversed"] = bool(sign in "+-" and rec["train_ic"] is not None and rec["train_ic"] < 0 and rec["train_p_two"] is not None and rec["train_p_two"] < ALPHA)
    rec["p_holm"] = p_holm
    return rec


def finalize(rec):
    """Holm 보정 p 가 채워진 뒤 판정."""
    tr_ok = (rec["train_months"] >= MIN_TRAIN_MONTHS and rec["p_holm"] is not None and rec["p_holm"] < ALPHA
             and rec["train_ic"] is not None and rec["train_ic"] > 0
             and rec["year_pos_share"] is not None and rec["year_pos_share"] >= YEAR_POS_SHARE
             and rec["lbyo_ic"] is not None and rec["lbyo_ic"] > 0)
    oo_ok = (rec["oos_months"] >= MIN_OOS_MONTHS and rec["oos_ic"] is not None and rec["oos_ic"] > 0
             and rec["oos_p"] is not None and rec["oos_p"] < ALPHA
             and rec["oos_top_edge"] is not None and rec["oos_top_edge"] > 0
             and rec["oos_top_abs"] is not None and rec["oos_top_abs"] - COST_RT > 0)
    rec["train_ok"], rec["oos_ok"] = tr_ok, oo_ok
    rec["verdict"] = "CONFIRMED" if (tr_ok and oo_ok) else ("TRAIN_ONLY" if tr_ok else "REJECTED")
    return rec


def judge_family(stats_by_var):
    """stats_by_var: {key: (train_ms, oos_ms)} → {key: rec}. Holm 은 가족 전체 train p."""
    recs = {k: judge_var(k, xf.SIGN[k], tr, oo) for k, (tr, oo) in stats_by_var.items()}
    ph = g4.holm({k: r["train_p"] for k, r in recs.items() if r["train_p"] is not None})
    for k, r in recs.items():
        r["p_holm"] = ph.get(k)
        finalize(r)
    return recs


# ── 패널 구성 ────────────────────────────────────────────────────────────────────────────────
def build_panel(rows_1d, pm, regmap, btc_sym="BTC"):
    """[(month, sym, rank, regime, feats, outcome)] — 코인별 월말 봉, PIT 적격(pm[다음 달])만."""
    btc = rows_1d.get(btc_sym)
    panel = []
    for s, rows in rows_1d.items():
        fs = xf.FeatureSeries(rows, btc)
        for m, i in xf.month_end_indices(rows).items():
            y, mo = int(m[:4]), int(m[5:])
            m_next = f"{y + (mo == 12):04d}-{(mo % 12) + 1:02d}"
            rank = pm.get(m_next, {}).get(s)
            if rank is None:
                continue
            panel.append(dict(month=m, date=rows[i]["date"], sym=s, rank=rank, regime=regmap.get(rows[i]["date"]),
                              f=fs.at(i), o=fs.outcome(i)))
    return panel


def month_stats(panel, key, out="fwd20", cohort=None, regime=None, min_cs=MIN_CS):
    by = {}
    for p in panel:
        f, r = p["f"].get(key), p["o"].get(out)
        if f is None or r is None:
            continue
        if cohort == "top30" and p["rank"] > 30:
            continue
        if regime is not None and p["regime"] != regime:
            continue
        by.setdefault(p["month"], []).append((p["sym"], f, r))
    out_ms = []
    for m in sorted(by):
        items = by[m]
        if len(items) < min_cs:
            continue
        cs = cross_section(items)
        if cs["ic"] is None:
            continue
        out_ms.append(dict(month=m, **cs))
    return out_ms


def split(ms):
    return [m for m in ms if m["month"] < SPLIT_MONTH], [m for m in ms if m["month"] >= SPLIT_MONTH]


def feature_corr(panel, keys=xf.KEYS):
    """변수 쌍 월별 스피어만 평균(진단)."""
    by = {}
    for p in panel:
        by.setdefault(p["month"], []).append(p)
    acc = {}
    for m, ps in by.items():
        for a in range(len(keys)):
            for b in range(a + 1, len(keys)):
                ka, kb = keys[a], keys[b]
                pairs = [(p["f"][ka], p["f"][kb]) for p in ps if p["f"].get(ka) is not None and p["f"].get(kb) is not None]
                if len(pairs) >= MIN_CS:
                    c = spearman([x for x, _ in pairs], [y for _, y in pairs])
                    if c is not None:
                        acc.setdefault((ka, kb), []).append(c)
    return {f"{a}|{b}": st.mean(v) for (a, b), v in acc.items()}


def user_1y_table(rows_1d, pm, days=365, btc_sym="BTC"):
    """D5: 마지막 봉 기준 days 일 전 시점 피처 vs 이후 days 일 수익 — 단일 횡단면(진단)."""
    last = max(r["date"] for rows in rows_1d.values() for r in rows)
    d0 = (date.fromisoformat(last) - timedelta(days=days)).isoformat()
    m0 = d0[:7]; y, mo = int(m0[:4]), int(m0[5:])
    m_next = f"{y + (mo == 12):04d}-{(mo % 12) + 1:02d}"
    elig = pm.get(m_next, {})
    btc = rows_1d.get(btc_sym)
    items = []
    for s, rows in rows_1d.items():
        if s not in elig:
            continue
        idx = {r["date"]: k for k, r in enumerate(rows)}
        if d0 not in idx or last not in idx:
            continue
        i = idx[d0]
        fs = xf.FeatureSeries(rows, btc)
        items.append(dict(sym=s, ret=rows[idx[last]]["c"] / rows[i]["c"] - 1, f=fs.at(i)))
    if len(items) < 8:
        return dict(start=d0, end=last, n=len(items), note="표본 부족")
    items.sort(key=lambda t: t["ret"])
    q = max(2, len(items) // 4)
    out = dict(start=d0, end=last, n=len(items), quartile_ret=dict(Q1=st.mean(t["ret"] for t in items[:q]), Q4=st.mean(t["ret"] for t in items[-q:])),
               top_coins=[(t["sym"], round(t["ret"], 3)) for t in items[-5:][::-1]], vars={})
    for k in xf.KEYS:
        pairs = [(t["f"][k], t["ret"]) for t in items if t["f"].get(k) is not None]
        if len(pairs) < 8:
            continue
        lo = [t["f"][k] for t in items[:q] if t["f"].get(k) is not None]
        hi = [t["f"][k] for t in items[-q:] if t["f"].get(k) is not None]
        out["vars"][k] = dict(n=len(pairs), rho=spearman([a for a, _ in pairs], [b for _, b in pairs]),
                              q1_med=st.median(lo) if lo else None, q4_med=st.median(hi) if hi else None)
    return out


def composite_ic(panel, keys_dirs, out="fwd20"):
    """D6: 변수 순위 평균 합성(사후 — 참고만)."""
    if not keys_dirs:
        return None
    by = {}
    for p in panel:
        if p["o"].get(out) is None or any(p["f"].get(k) is None for k, _ in keys_dirs):
            continue
        by.setdefault(p["month"], []).append(p)
    ms = []
    for m in sorted(by):
        ps = by[m]
        if len(ps) < MIN_CS:
            continue
        score = [0.0] * len(ps)
        for k, d in keys_dirs:
            rk = ranks([p["f"][k] * (1 if d == "+" else -1) for p in ps])
            score = [a + b for a, b in zip(score, rk)]
        cs = cross_section([(p["sym"], sc, p["o"][out]) for p, sc in zip(ps, score)])
        if cs["ic"] is not None:
            ms.append(dict(month=m, **cs))
    tr, oo = split(ms)
    return dict(train_ic=st.mean(m["ic"] for m in tr) if tr else None, oos_ic=st.mean(m["ic"] for m in oo) if oo else None,
                oos_top_edge=st.mean(m["top"] - m["uni"] for m in oo) if oo else None, months=len(ms))


# ── 출력 ──────────────────────────────────────────────────────────────────────────────────────
def _f(v, w=7, pct=False):
    if v is None:
        return " " * (w - 1) + "-"
    return f"{v*100:{w}.2f}" if pct else f"{v:{w}.3f}"


def _p(v):
    return "   -" if v is None else f"{v:.3f}"


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    syms = va._syms()
    print(f"횡단면 특성 연구 | 가족 {len(xf.KEYS)} 변수 · 월말 형성 · PIT liquid · fwd{xf.FWD_PRIMARY} 주 판정 · 분할 {SPLIT_MONTH} · MIN_CS {MIN_CS} | DEPLOY_ON_PASS={DEPLOY_ON_PASS}")
    if "--no-fetch" not in argv:
        va.fetch(syms, ["1d"])
    rows_1d = va.load_tf(syms, "1d", long=True)
    regmap = rs.build_regime_map(rows_by=rows_1d)
    pm = pc.pit_membership(rows_1d)
    panel = build_panel(rows_1d, pm, regmap)
    first = min(p["month"] for p in panel); last = max(p["month"] for p in panel)
    n_m = len({p["month"] for p in panel})
    print(f"[panel] 코인 {len(rows_1d)} · 코인-월 {len(panel)} · 월 {first}~{last} ({n_m}) · fwd20 있는 행 {sum(1 for p in panel if p['o']['fwd20'] is not None)}")
    cs_sizes = {}
    for p in panel:
        if p["o"]["fwd20"] is not None:
            cs_sizes[p["month"]] = cs_sizes.get(p["month"], 0) + 1
    yrs = {}
    for m, n in cs_sizes.items():
        yrs.setdefault(m[:4], []).append(n)
    print("[panel] 연도별 월 횡단면 코인 수(중앙): " + " ".join(f"{y}:{int(st.median(v))}" for y, v in sorted(yrs.items())))

    stats = {k: split(month_stats(panel, k)) for k in xf.KEYS}
    recs = judge_family(stats)

    print("\n== 주 판정 (fwd20 IC, 방향 정렬) ==")
    print(f"{'변수':<18}{'grp':<9}{'sg':<3}{'dir':<4}{'trM':>4}{'tr_IC':>8}{'ICIR':>7}{'p':>7}{'Holm':>7}{'yr+':>6}{'lbyo':>8}{'trTOPe':>8}{'ooM':>4}{'oo_IC':>8}{'oo_p':>7}{'ooTOPe':>8}{'ooTOP':>8}  판정")
    for k in sorted(recs, key=lambda k: (recs[k]["p_holm"] if recs[k]["p_holm"] is not None else 9)):
        r = recs[k]
        yp = "-" if r["year_pos_share"] is None else f"{r['year_pos_share']*100:.0f}%"
        print(f"{k:<18}{r['group']:<9}{r['sign']:<3}{r['dir']:<4}{r['train_months']:>4}{_f(r['train_ic'])}{_f(r['train_icir'])}{_p(r['train_p']):>7}{_p(r['p_holm']):>7}{yp:>6}{_f(r['lbyo_ic'])}{_f(r['train_top_edge'], pct=True)}%"
              f"{r['oos_months']:>4}{_f(r['oos_ic'])}{_p(r['oos_p']):>7}{_f(r['oos_top_edge'], pct=True)}%{_f(r['oos_top_abs'], pct=True)}%  {r['verdict']}{' REVERSED' if r['reversed'] else ''}")
    counts = {v: sum(1 for r in recs.values() if r["verdict"] == v) for v in ("CONFIRMED", "TRAIN_ONLY", "REJECTED")}
    counts["REVERSED"] = sum(1 for r in recs.values() if r["reversed"])
    print(f"\n판정: {counts}")

    # ── 진단 ──
    diag = {}
    print("\n== D1 fwd60 / hit20_40 IC (전 기간, 방향 정렬) ==")
    d1 = {}
    for k in xf.KEYS:
        d = recs[k]["dir"]; sgn = 1 if d == "+" else -1
        m60 = month_stats(panel, k, out="fwd60"); mh = month_stats(panel, k, out="hit20_40")
        d1[k] = dict(ic60=sgn * st.mean(m["ic"] for m in m60) if m60 else None, ic_hit=sgn * st.mean(m["ic"] for m in mh) if mh else None,
                     hit_top=st.mean((m["top"] if d == "+" else m["bot"]) for m in mh) if mh else None, hit_uni=st.mean(m["uni"] for m in mh) if mh else None)
        print(f"  {k:<18} IC60 {_f(d1[k]['ic60'])}  IC_hit {_f(d1[k]['ic_hit'])}  TOP 도달률 {_f(d1[k]['hit_top'], pct=True)}% vs 유니버스 {_f(d1[k]['hit_uni'], pct=True)}%")
    diag["d1"] = d1
    print("\n== D2 레짐별 IC (형성일 라벨, 전 기간, 방향 정렬) ==")
    d2 = {}
    for k in xf.KEYS:
        d = recs[k]["dir"]; sgn = 1 if d == "+" else -1
        d2[k] = {}
        for g in REGIMES:
            ms = month_stats(panel, k, regime=g, min_cs=8)
            d2[k][g] = dict(months=len(ms), ic=sgn * st.mean(m["ic"] for m in ms) if ms else None)
        print(f"  {k:<18} " + "  ".join(f"{g} {_f(d2[k][g]['ic'])}({d2[k][g]['months']})" for g in REGIMES))
    diag["d2"] = d2
    print("\n== D3 top30 코호트 IC (train/OOS, 방향 정렬) ==")
    d3 = {}
    for k in xf.KEYS:
        d = recs[k]["dir"]; sgn = 1 if d == "+" else -1
        tr, oo = split(month_stats(panel, k, cohort="top30", min_cs=10))
        d3[k] = dict(train_ic=sgn * st.mean(m["ic"] for m in tr) if tr else None, oos_ic=sgn * st.mean(m["ic"] for m in oo) if oo else None, train_months=len(tr), oos_months=len(oo))
        print(f"  {k:<18} train {_f(d3[k]['train_ic'])}({len(tr)})  oos {_f(d3[k]['oos_ic'])}({len(oo)})")
    diag["d3"] = d3
    corr = feature_corr(panel)
    high = sorted(((v, k) for k, v in corr.items() if abs(v) >= CORR_FLAG), reverse=True)
    print(f"\n== D4 변수 간 순위상관 |ρ|>={CORR_FLAG} ==")
    for v, k in high:
        print(f"  {k:<36} {v:+.2f}")
    diag["d4_high_corr"] = [(k, v) for v, k in high]
    d5 = user_1y_table(rows_1d, pm)
    diag["d5_user_1y"] = d5
    print(f"\n== D5 사용자 원 질문: {d5.get('start')}→{d5.get('end')} 수익 4분위 (n={d5.get('n')}) ==")
    if "vars" in d5:
        print(f"  Q1 평균 {d5['quartile_ret']['Q1']*100:+.1f}% / Q4 평균 {d5['quartile_ret']['Q4']*100:+.1f}% · 상위 {d5['top_coins']}")
        for k, v in sorted(d5["vars"].items(), key=lambda kv: -abs(kv[1]["rho"] or 0)):
            print(f"  {k:<18} ρ {_f(v['rho'])}  Q1중앙 {_f(v['q1_med'])}  Q4중앙 {_f(v['q4_med'])}")
    conf = [(k, recs[k]["dir"]) for k in xf.KEYS if recs[k]["verdict"] == "CONFIRMED"]
    diag["d6_composite"] = composite_ic(panel, conf)
    print(f"\n== D6 CONFIRMED 합성(사후 참고) == {diag['d6_composite']}")

    out = dict(frame="xsec_chars", split=SPLIT_MONTH, family=len(xf.KEYS), panel=dict(coins=len(rows_1d), coin_months=len(panel), months=n_m, first=first, last=last),
               counts=counts, results=recs, diag=diag, corr=corr, deploy_on_pass=DEPLOY_ON_PASS)
    json.dump(out, open("_xsec_chars.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print("RESULT_JSON: " + json.dumps(dict(frame="xsec_chars", counts=counts,
                                            verdicts={k: r["verdict"] + ("/REV" if r["reversed"] else "") for k, r in recs.items()},
                                            top=[(k, recs[k]["dir"], round(recs[k]["train_ic"] or 0, 3), recs[k]["p_holm"], round(recs[k]["oos_ic"] or 0, 3)) for k in sorted(recs, key=lambda k: recs[k]["p_holm"] if recs[k]["p_holm"] is not None else 9)[:8]]),
                                       ensure_ascii=False))


if __name__ == "__main__":
    main()
