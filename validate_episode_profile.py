"""
validate_episode_profile.py — 상승 국면(에피소드) 안에서 '많이 오른 코인 vs 안 오른 코인'의 시작 시점 프로필
(2026-09-07 사전 등록, 사용자 지시).

## 질문 (사용자 표현 그대로)
"2021년 불장 때 모든 종목이 다 오른 게 아니라 많이 오른 것들이 있었는데, 이 많이 상승한 종목들은 미상승 종목과
여러 인자들에 이런이런 차이를 보인다 — 모든 해에 다 오르는 건 아니지만(오르는 구간인지는 레짐이 판별) 올랐을 때
이런 특징의 공통점이 있었다를 도출할 수 있는가." 유니버스 80종이 아니라 이력 있는 전 코인(data_long, OKX 무기한 전 종목).

## 프레임 (동결)
  · **에피소드** = 레짐 라벨이 bull_btc 또는 bull_altseason 인 날의 연속 구간(30일 이하 끊김 병합, frame_v3.episodes),
    길이 >= EP_MIN_DAYS(60). 시작 t0 = 구간 첫날, 끝 t1 = 구간 마지막 날. 라벨은 장기 이력으로 만든 레짐 맵
    (regime_switch.build_regime_map(rows_by=)). 라벨이 바닥보다 약 50일 늦게 켜지는 것은 알고 시작한다 — 실거래가
    아는 시점이 그때이므로 그 시점의 상태가 물음이다.
  · **코인·에피소드 행**: t0 에 봉이 있고 t0 이전 이력 >= MIN_HIST(120)봉인 코인. 결과 ret_ep = close(t1)/close(t0) − 1,
    mfe_ep = (t0, t1] 최고 종가/close(t0) − 1(진단). 피처는 t0 봉까지의 정보만(xsec_features.all_at, 35 변수).
    이력이 모자란 변수는 그 코인에서 None(변수별로 표본이 다르다).
  · **집단**: 에피소드 안에서 ret_ep 상위 1/3 = 많이 오른(winners), 하위 1/3 = 안 오른/적게 오른(laggards).
    에피소드당 코인 >= MIN_COINS(15) 인 경우만 통계.
  · **에피소드별 표**: 변수마다 winners 중앙값 / laggards 중앙값 / 순위이연상관(rank-biserial, Mann-Whitney) /
    에피소드 내 스피어만(피처, ret_ep).
  · **풀링 판정**: 에피소드 내 백분위(피처·수익)로 정규화해 전 코인-에피소드 풀 스피어만. p 는 **에피소드 안에서만
    수익 순위를 섞는 순열검정** PERM_N(2000, 시드 42) — 에피소드 구조를 보존한다. Holm 은 35 변수 가족 전체.
    부호 지정 변수(xsec_features FAMILY 의 +/−)는 단측, '?' 는 양측.
  · **일관성**: 에피소드 내 스피어만 부호가 (지정 부호 또는 풀 부호와) 같은 에피소드 비율 >= CONSIST_SHARE(0.75),
    적격 에피소드 >= CONSIST_MIN_EP(3).
  · **판정**: PROFILE(Holm p<.05 AND 일관성) / EPISODE_DEPENDENT(Holm p<.05 이나 일관성 미달 — 특정 에피소드가 끌었다) /
    NONE. 지정 부호 변수가 반대 부호로 Holm p<.05 면 REVERSED 표기.
  · **OOS 없음 — 명시**: 2025-01 이후 상승 에피소드가 없어 시간 OOS 를 만들 수 없다. 이 연구는 프로필(서술) 연구이고,
    PROFILE 판정 변수는 **다음 상승 에피소드(사전 등록된 전향 시험)** 에서 에피소드 내 스피어만 부호 재현을 요구한다.
    그 전에는 규칙으로 승격하지 않는다. DEPLOY_ON_PASS=False.

## 진단 (판정 아님)
  D1 에피소드별 상승 비율(ret_ep>0)·중앙값·winners/laggards 평균·BTC 수익 / D2 '오르지 않은'(ret_ep<=0) vs 나머지의 rank-biserial /
  D3 mfe_ep 결과 풀 스피어만 / D4 지배 라벨(bull_btc vs bull_altseason)별 풀 스피어만 / D5 2021 에피소드 전체 표(사용자 예시).

한계(실행 전 기록): **생존 편향** — 지금 OKX 에 상장돼 있는 코인만 있다(2021 에 크게 오르고 사라진 코인은 표본에 없고,
2021 의 '안 오른' 쪽은 살아남은 코인만 남아 실제보다 좋게 보인다) · 2017~2019 에피소드는 코인 수가 적어 통계 제외될 수
있음 · 상장 전 코인은 그 에피소드에 없음 · 에피소드 4~6개뿐이라 일관성 기준의 검정력이 낮다.

실행: python validate_episode_profile.py [--no-fetch] [--data-long-only]       출력: _episode_profile.json + RESULT_JSON
"""
import json
import math
import random
import statistics as st
import sys

import frame_v3 as f3
import regime_switch as rs
import validate_guard_v4 as g4
import validate_regime_split_all as va
import validate_xsec_chars as vx
import xsec_features as xf

# ── 동결 파라미터 ─────────────────────────────────────────────────────────────────────────────
EPISODE_LABELS = ("bull_btc", "bull_altseason")
EP_MIN_DAYS = 60
MIN_HIST = 120
MIN_COINS = 15
PERM_N, SEED = 2000, 42
ALPHA = 0.05
CONSIST_SHARE = 0.75
CONSIST_MIN_EP = 3
DEPLOY_ON_PASS = False
KEYS = xf.ALL_KEYS
SIGN = xf.ALL_SIGN


# ── 에피소드 ─────────────────────────────────────────────────────────────────────────────────
def bull_episodes(regmap, labels=EPISODE_LABELS, min_days=EP_MIN_DAYS):
    """[(start, end, dominant_label, days)] — 두 상승 라벨 합집합의 연속 구간."""
    merged = {d: ("bull" if g in labels else g) for d, g in regmap.items()}
    out = []
    for s, e in f3.episodes(merged, "bull"):
        days = f3._ord(e) - f3._ord(s) + 1
        if days < min_days:
            continue
        cnt = {}
        for d, g in regmap.items():
            if s <= d <= e and g in labels:
                cnt[g] = cnt.get(g, 0) + 1
        dom = max(cnt, key=cnt.get) if cnt else "bull"
        out.append((s, e, dom, days))
    return out


def build_rows(rows_1d, eps, btc_sym="BTC", min_hist=MIN_HIST):
    """[(ep_id, sym, ret_ep, mfe_ep, feats)]"""
    btc = rows_1d.get(btc_sym)
    out = []
    for s, rows in rows_1d.items():
        idx = {r["date"]: k for k, r in enumerate(rows)}
        dates = [r["date"] for r in rows]
        fs = None
        for ep_id, (t0, t1, _, _) in enumerate(eps):
            i0 = idx.get(t0)
            if i0 is None or i0 < min_hist:
                continue
            # t1 이하 마지막 봉
            import bisect
            i1 = bisect.bisect_right(dates, t1) - 1
            if i1 <= i0:
                continue
            c0 = rows[i0]["c"]
            if c0 <= 0:
                continue
            if fs is None:
                fs = xf.FeatureSeries(rows, btc)
            seg = [r["c"] for r in rows[i0 + 1:i1 + 1]]
            out.append(dict(ep=ep_id, sym=s, ret=rows[i1]["c"] / c0 - 1, mfe=max(seg) / c0 - 1, f=xf.all_at(fs, i0)))
    return out


# ── 통계 ──────────────────────────────────────────────────────────────────────────────────────
def rank_biserial(a, b):
    """Mann-Whitney 기반: P(a > b) − P(a < b). a=winners 피처, b=laggards 피처."""
    if not a or not b:
        return None
    gt = lt = 0
    for x in a:
        for y in b:
            gt += x > y; lt += x < y
    return (gt - lt) / (len(a) * len(b))


def episode_stats(rows, key, out="ret", min_coins=MIN_COINS):
    """{ep: dict(n, rho, win_med, lag_med, rb, win_mean_ret, lag_mean_ret)}"""
    by = {}
    for r in rows:
        f = r["f"].get(key)
        if f is None or r.get(out) is None:
            continue
        by.setdefault(r["ep"], []).append((r["sym"], f, r[out]))
    res = {}
    for ep, items in by.items():
        if len(items) < min_coins:
            continue
        rho = vx.spearman([f for _, f, _ in items], [y for _, _, y in items])
        if rho is None:
            continue
        srt = sorted(items, key=lambda t: (t[2], t[0]))
        k = max(3, len(items) // 3)
        lag, win = srt[:k], srt[-k:]
        res[ep] = dict(n=len(items), rho=rho, win_med=st.median(f for _, f, _ in win), lag_med=st.median(f for _, f, _ in lag),
                       rb=rank_biserial([f for _, f, _ in win], [f for _, f, _ in lag]),
                       win_ret=st.mean(y for _, _, y in win), lag_ret=st.mean(y for _, _, y in lag))
    return res


def pooled(rows, key, out="ret", min_coins=MIN_COINS):
    """에피소드 내 백분위 정규화 후 풀 스피어만 + 에피소드 내 순열 p. 반환 dict(n, eps, rho, p_two, p_pos, p_neg)."""
    by = {}
    for r in rows:
        f = r["f"].get(key)
        if f is None or r.get(out) is None:
            continue
        by.setdefault(r["ep"], []).append((f, r[out]))
    groups = [v for v in by.values() if len(v) >= min_coins]
    if not groups:
        return dict(n=0, eps=0, rho=None, p_two=None, p_pos=None, p_neg=None)
    xs, ys, gi = [], [], []
    for g in groups:
        rf = vx.ranks([f for f, _ in g]); ry = vx.ranks([y for _, y in g])
        n = len(g)
        xs += [r / n for r in rf]; ys += [r / n for r in ry]; gi.append(n)
    rho = vx.spearman(xs, ys)
    if rho is None:
        return dict(n=len(xs), eps=len(groups), rho=None, p_two=None, p_pos=None, p_neg=None)
    rng = random.Random(SEED)
    ge = le = 0
    for _ in range(PERM_N):
        yp, pos = [], 0
        for n in gi:
            seg = ys[pos:pos + n]; rng.shuffle(seg); yp += seg; pos += n
        r2 = vx.spearman(xs, yp)
        ge += r2 >= rho; le += r2 <= rho
    p_pos, p_neg = ge / PERM_N, le / PERM_N          # p_pos: 관측 이상 클 확률(양의 상관 검정), p_neg: 음의 상관 검정
    return dict(n=len(xs), eps=len(groups), rho=rho, p_two=min(1.0, 2 * min(p_pos, p_neg)), p_pos=p_pos, p_neg=p_neg)


def judge_var(key, sign, ep_stats, pool):
    rho = pool["rho"]
    if sign == "+":
        d, p = "+", pool["p_pos"]
    elif sign == "-":
        d, p = "-", pool["p_neg"]
    else:
        d = "+" if (rho is None or rho >= 0) else "-"
        p = pool["p_two"]
    signs = [(1 if v["rho"] > 0 else -1) for v in ep_stats.values() if v["rho"] != 0]
    want = 1 if d == "+" else -1
    share = (sum(1 for s in signs if s == want) / len(signs)) if signs else None
    return dict(key=key, group=xf.ALL_GROUP[key], sign=sign, dir=d, n=pool["n"], eps=pool["eps"], rho=rho, rho_dir=(rho * want) if rho is not None else None,
                p=p, p_two=pool["p_two"], ep_share=share, ep_n=len(signs),
                ep_rhos={ep: round(v["rho"], 3) for ep, v in ep_stats.items()},
                reversed=bool(sign in "+-" and rho is not None and rho * want < 0 and pool["p_two"] is not None and pool["p_two"] < ALPHA))


def finalize(rec):
    sig = rec["p_holm"] is not None and rec["p_holm"] < ALPHA and rec["rho_dir"] is not None and rec["rho_dir"] > 0
    cons = rec["ep_share"] is not None and rec["ep_n"] >= CONSIST_MIN_EP and rec["ep_share"] >= CONSIST_SHARE
    rec["consistent"] = cons
    rec["verdict"] = "PROFILE" if (sig and cons) else ("EPISODE_DEPENDENT" if sig else "NONE")
    return rec


def judge_family(rows, keys=KEYS):
    recs, eps_all = {}, {}
    for k in keys:
        es = episode_stats(rows, k)
        po = pooled(rows, k)
        eps_all[k] = es
        recs[k] = judge_var(k, SIGN[k], es, po)
    ph = g4.holm({k: r["p"] for k, r in recs.items() if r["p"] is not None})
    for k, r in recs.items():
        r["p_holm"] = ph.get(k)
        finalize(r)
    return recs, eps_all


# ── 진단 ──────────────────────────────────────────────────────────────────────────────────────
def episode_summary(rows, eps, btc_rows):
    out = {}
    bidx = {r["date"]: r["c"] for r in btc_rows}
    for ep_id, (t0, t1, dom, days) in enumerate(eps):
        rs_ = [r["ret"] for r in rows if r["ep"] == ep_id]
        if not rs_:
            out[ep_id] = dict(start=t0, end=t1, dom=dom, days=days, n=0)
            continue
        srt = sorted(rs_)
        k = max(1, len(srt) // 3)
        btc_ret = None
        if t0 in bidx:
            last = max((d for d in bidx if d <= t1), default=None)
            btc_ret = bidx[last] / bidx[t0] - 1 if last else None
        out[ep_id] = dict(start=t0, end=t1, dom=dom, days=days, n=len(rs_), rise_share=sum(1 for r in rs_ if r > 0) / len(rs_),
                          median=st.median(rs_), win_mean=st.mean(srt[-k:]), lag_mean=st.mean(srt[:k]), btc=btc_ret)
    return out


def norise_rb(rows, key):
    """D2: ret<=0 집단 vs ret>0 집단의 피처 rank-biserial (풀, 에피소드 내 백분위)."""
    a, b = [], []
    by = {}
    for r in rows:
        f = r["f"].get(key)
        if f is not None:
            by.setdefault(r["ep"], []).append((f, r["ret"]))
    for g in by.values():
        if len(g) < MIN_COINS:
            continue
        rf = vx.ranks([f for f, _ in g]); n = len(g)
        for (f, y), rk in zip(g, rf):
            (b if y > 0 else a).append(rk / n)
    return dict(n_norise=len(a), n_rise=len(b), rb=rank_biserial(b, a))


def _f(v, w=7, pct=False):
    if v is None:
        return " " * (w - 1) + "-"
    return f"{v*100:{w}.1f}" if pct else f"{v:{w}.3f}"


def _p(v):
    return "   -" if v is None else f"{v:.3f}"


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    print(f"에피소드 프로필 | 상승 라벨 {EPISODE_LABELS} · 최소 {EP_MIN_DAYS}일 · 이력 {MIN_HIST}봉 · 코인 >= {MIN_COINS} · 변수 {len(KEYS)} · 순열 {PERM_N} | DEPLOY_ON_PASS={DEPLOY_ON_PASS}")
    syms = va._syms()
    if "--no-fetch" not in argv and "--data-long-only" not in argv:
        va.fetch(syms, ["1d"])
    import glob, os
    long_syms = sorted({os.path.basename(p).split("_1d")[0].upper() for p in glob.glob(f"{__import__('detlib').LONG_DIR}/*_1d.csv.gz")})
    all_syms = sorted(set(syms) | set(long_syms))
    rows_1d = va.load_tf(all_syms, "1d", long=True)
    regmap = rs.build_regime_map(rows_by=rows_1d)
    eps = bull_episodes(regmap)
    print(f"[data] 코인 {len(rows_1d)} (유니버스 {len(syms)} + 장기 {len(long_syms)}) · 레짐 일수 {len(regmap)} {min(regmap)}~{max(regmap)}")
    print("[episodes] " + " | ".join(f"#{i} {s}~{e} {dom} {d}d" for i, (s, e, dom, d) in enumerate(eps)))
    rows = build_rows(rows_1d, eps)
    summ = episode_summary(rows, eps, rows_1d["BTC"])
    print("\n== D1 에피소드별 상승 분포 ==")
    print(f"{'#':<3}{'start':<12}{'end':<12}{'dom':<15}{'days':>5}{'n':>5}{'rise%':>7}{'median':>8}{'win':>8}{'lag':>8}{'BTC':>8}")
    for ep, v in summ.items():
        if v["n"]:
            print(f"{ep:<3}{v['start']:<12}{v['end']:<12}{v['dom']:<15}{v['days']:>5}{v['n']:>5}{v['rise_share']*100:>6.0f}%{_f(v['median'],8,True)}%{_f(v['win_mean'],7,True)}%{_f(v['lag_mean'],7,True)}%{_f(v['btc'],7,True)}%")
        else:
            print(f"{ep:<3}{v['start']:<12}{v['end']:<12}{v['dom']:<15}{v['days']:>5}    0  (코인 없음)")

    recs, eps_all = judge_family(rows)
    ep_ids = sorted({r["ep"] for r in rows if summ[r["ep"]]["n"] >= MIN_COINS})
    print("\n== 주 판정 (풀 스피어만·순열 p·Holm·에피소드 일관성) ==")
    hdr = f"{'변수':<18}{'grp':<10}{'sg':<3}{'dir':<4}{'n':>5}{'eps':>4}{'rho':>7}{'p':>7}{'Holm':>7}{'ep+':>6}  " + " ".join(f"ep{e:<5}" for e in ep_ids) + "  판정"
    print(hdr)
    for k in sorted(recs, key=lambda k: (recs[k]["p_holm"] if recs[k]["p_holm"] is not None else 9, -(recs[k]["rho_dir"] or 0))):
        r = recs[k]
        sh = "-" if r["ep_share"] is None else f"{r['ep_share']*100:.0f}%"
        eprs = " ".join(f"{r['ep_rhos'].get(e, float('nan')):+.2f} " if e in r["ep_rhos"] else "   -  " for e in ep_ids)
        print(f"{k:<18}{r['group']:<10}{r['sign']:<3}{r['dir']:<4}{r['n']:>5}{r['eps']:>4}{_f(r['rho_dir'])}{_p(r['p']):>7}{_p(r['p_holm']):>7}{sh:>6}  {eprs}  {r['verdict']}{' REVERSED' if r['reversed'] else ''}")
    counts = {v: sum(1 for r in recs.values() if r["verdict"] == v) for v in ("PROFILE", "EPISODE_DEPENDENT", "NONE")}
    counts["REVERSED"] = sum(1 for r in recs.values() if r["reversed"])
    print(f"\n판정: {counts}")

    # 에피소드별 winners/laggards 중앙값 표 — PROFILE·EPISODE_DEPENDENT 변수 + 2021 에피소드 전체(D5)
    print("\n== 에피소드별 winners 중앙값 / laggards 중앙값 / rank-biserial ==")
    for k in [k for k in KEYS if recs[k]["verdict"] != "NONE"]:
        line = f"  {k:<18}"
        for e in ep_ids:
            v = eps_all[k].get(e)
            line += f" | ep{e} {_f(v['win_med'],7)}/{_f(v['lag_med'],7)} rb{v['rb']:+.2f}" if v else f" | ep{e}   -"
        print(line)
    ep2021 = [e for e, v in summ.items() if v["n"] and v["start"] <= "2021-06-01" <= v["end"]]   # 2021 을 품은 에피소드(사용자 예시)
    d5 = {}
    if ep2021:
        e = ep2021[-1]
        print(f"\n== D5 2021 에피소드 #{e} ({summ[e]['start']}~{summ[e]['end']}, n={summ[e]['n']}) 전 변수 ==")
        for k in KEYS:
            v = eps_all[k].get(e)
            if v:
                d5[k] = dict(win_med=v["win_med"], lag_med=v["lag_med"], rb=v["rb"], rho=v["rho"], n=v["n"])
                print(f"  {k:<18} win {_f(v['win_med'],8)}  lag {_f(v['lag_med'],8)}  rb {v['rb']:+.2f}  rho {v['rho']:+.3f}  (n {v['n']})")
    # D2 / D3 / D4
    d2 = {k: norise_rb(rows, k) for k in KEYS}
    d3 = {k: pooled(rows, k, out="mfe")["rho"] for k in KEYS}
    d4 = {}
    for dom in EPISODE_LABELS:
        sub = [r for r in rows if eps[r["ep"]][2] == dom]
        d4[dom] = {k: pooled(sub, k)["rho"] for k in KEYS} if sub else {}
    print("\n== D2 미상승(ret<=0) vs 상승 rank-biserial · D3 mfe 풀 rho · D4 지배 라벨별 풀 rho ==")
    for k in KEYS:
        print(f"  {k:<18} D2 rb {_f(d2[k]['rb'])} (n {d2[k]['n_norise']}/{d2[k]['n_rise']})  D3 {_f(d3[k])}  D4 " + "  ".join(f"{dom} {_f(d4[dom].get(k))}" for dom in EPISODE_LABELS))

    out = dict(frame="episode_profile", episodes=[dict(id=i, start=s, end=e, dom=dom, days=d) for i, (s, e, dom, d) in enumerate(eps)], summary=summ,
               coins=len(rows_1d), rows=len(rows), counts=counts, results=recs, episode_stats={k: {str(e): v for e, v in es.items()} for k, es in eps_all.items()},
               d2=d2, d3=d3, d4=d4, d5_2021=d5, deploy_on_pass=DEPLOY_ON_PASS)
    json.dump(out, open("_episode_profile.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print("RESULT_JSON: " + json.dumps(dict(frame="episode_profile", coins=len(rows_1d), rows=len(rows), episodes=[(s, e, dom, d) for s, e, dom, d in eps], counts=counts,
                                            verdicts={k: r["verdict"] + ("/REV" if r["reversed"] else "") for k, r in recs.items() if r["verdict"] != "NONE" or r["reversed"]},
                                            top=[(k, recs[k]["dir"], round(recs[k]["rho_dir"] or 0, 3), recs[k]["p_holm"], recs[k]["ep_share"]) for k in sorted(recs, key=lambda k: recs[k]["p_holm"] if recs[k]["p_holm"] is not None else 9)[:10]]),
                                       ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
