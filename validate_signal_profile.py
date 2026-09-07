"""
validate_signal_profile.py — 우리 신호봉에서 잰 상태 변수가 '이미 진입하는 거래'의 승자/패자를 가르는가
(2026-09-07 사전 등록, 사용자 승인 "응 사전등록해서 돌려줘").

## 질문
xsec_chars(월말 순위)·episode_profile(상승 국면 시작 프로필)과 달리, **실거래가 실제로 진입하는 봉**(배포 셀의 패턴 신호봉)에서
35 상태 변수(xsec_features.all_at)를 재고, 그 거래의 방식D 수익률과의 관계를 본다. 통과 변수는 새 진입 규칙이 아니라
**슬롯 우선순위·사이징 층 후보**다(다음 단계: 라우팅 복제 프레임 sizing_vol ROUTING_MODE 에서 짝지음 시험 — 별도 사전 등록).

## 프레임 (동결)
  · **주 판정 가족** = 배포 1d 롱 셀 4개 풀링: engulfing|bull_btc · engulfing|bear · fvg|bull_btc · fvg|bull_altseason
    (validate_guard_v4.CELLS 의 1d·long·deployed, 코호트 top30 정적 — v4 와 같은 신호 집합). 셀별은 진단.
  · 신호·수익: g4.collect_cell — 방식D 청산(손절 8%/반대신호/레짐 전환/30봉), 수수료 차감. 피처는 신호봉 i 까지(인과).
  · 통계: 풀 스피어만(피처, ret). p = **월 클러스터 부트스트랩**(신호가 난 달을 복원추출, 1000회, 시드 42; 통계량 = 스피어만).
    지정 부호 변수는 단측, '?' 는 양측. Holm 은 35 변수.
  · 분할: train < 2025-01-01 <= OOS (v4 동일).
  · train 적격: Holm p<.05 · 방향 정렬 rho > 0 · n >= 60.
    OOS 재현: n >= 20 · 같은 방향 rho > 0 · 부트 단측 p < .05(비보정) · 피처 상위 1/3 평균수익 − 하위 1/3 > 0.
  · 판정: CANDIDATE(train+OOS) / TRAIN_ONLY / NONE. 지정 부호 반대로 train 양측 p<.05 → REVERSED 표기.
  · DEPLOY_ON_PASS=False. 실거래 무변경(관찰 기간).

## 진단 (판정 아님)
  D1 셀별 train/OOS rho / D2 승자(ret>0) vs 패자 rank-biserial / D3 피처 3분위별 손절 비율 / D4 월 demean 판(같은 달 안 비교) /
  D5 engulfing_short|bull_altseason(숏) 별도.

한계: 신호 n 이 수백이라 검정력 낮음 · 레짐 조건부 셀 안에서도 국면 잔차가 피처·수익에 같이 실릴 수 있음(D4 로 보조) ·
정적 코호트(v4 와 동일, PIT 아님 — 신호 집합 비교 가능성을 위해).

실행: python validate_signal_profile.py [--no-fetch]        출력: _signal_profile.json + RESULT_JSON
"""
import json
import random
import statistics as st
import sys

import regime_switch as rs
import validate_guard_v4 as g4
import validate_regime_split_all as va
import validate_xsec_chars as vx
import xsec_features as xf
from validate_regime_split import turnover_rank

SPLIT_DATE = g4.SPLIT_DATE            # 2025-01-01
BOOT_N, SEED = 1000, 42
ALPHA = 0.05
MIN_TRAIN_N, MIN_OOS_N = 60, 20
DEPLOY_ON_PASS = False
PRIMARY_CIDS = ("engulfing|bull_btc", "engulfing|bear", "fvg|bull_btc", "fvg|bull_altseason")
SHORT_CID = "engulfing_short|bull_altseason"
KEYS, SIGN = xf.ALL_KEYS, xf.ALL_SIGN


def attach_features(sigs, rows_by, btc_rows):
    fs_cache = {}
    for s in sigs:
        if s["sym"] not in fs_cache:
            fs_cache[s["sym"]] = xf.FeatureSeries(rows_by[s["sym"]], btc_rows)
        s["f"] = xf.all_at(fs_cache[s["sym"]], s["i"])
    return sigs


def month_boot_rho(sigs, key, n_boot=BOOT_N, seed=SEED):
    """dict(n, rho, p_pos, p_neg, p_two, months) — 월 복원추출 부트."""
    pts = [(s["month"], s["f"][key], s["ret"]) for s in sigs if s["f"].get(key) is not None]
    if len(pts) < 5:
        return dict(n=len(pts), rho=None, p_pos=None, p_neg=None, p_two=None, months=0)
    rho = vx.spearman([f for _, f, _ in pts], [r for _, _, r in pts])
    by = {}
    for m, f, r in pts:
        by.setdefault(m, []).append((f, r))
    months = sorted(by)
    if rho is None or len(months) < 3:
        return dict(n=len(pts), rho=rho, p_pos=None, p_neg=None, p_two=None, months=len(months))
    rng = random.Random(seed)
    draws = []
    for _ in range(n_boot):
        pick = []
        for _ in months:
            pick += by[months[rng.randrange(len(months))]]
        r2 = vx.spearman([f for f, _ in pick], [r for _, r in pick])
        if r2 is not None:
            draws.append(r2)
    if not draws:
        return dict(n=len(pts), rho=rho, p_pos=None, p_neg=None, p_two=None, months=len(months))
    p_pos = sum(1 for d in draws if d <= 0) / len(draws)      # 양의 상관 검정: 부트 분포가 0 이하일 확률
    p_neg = sum(1 for d in draws if d >= 0) / len(draws)
    return dict(n=len(pts), rho=rho, p_pos=p_pos, p_neg=p_neg, p_two=min(1.0, 2 * min(p_pos, p_neg)), months=len(months))


def tercile_spread(sigs, key, d):
    """방향 d 기준 피처 '좋은' 1/3 평균수익 − '나쁜' 1/3 평균수익."""
    pts = sorted(((s["f"][key], s["sym"], s["ret"]) for s in sigs if s["f"].get(key) is not None), key=lambda t: (t[0], t[1]))
    if len(pts) < 6:
        return None, None, None
    k = max(2, len(pts) // 3)
    lo, hi = [r for _, _, r in pts[:k]], [r for _, _, r in pts[-k:]]
    good, bad = (hi, lo) if d == "+" else (lo, hi)
    return st.mean(good) - st.mean(bad), st.mean(good), st.mean(bad)


def judge_var(key, sign, train, oos):
    tr = month_boot_rho(train, key)
    oo = month_boot_rho(oos, key)
    rho = tr["rho"]
    if sign == "+":
        d, p = "+", tr["p_pos"]
    elif sign == "-":
        d, p = "-", tr["p_neg"]
    else:
        d = "+" if (rho is None or rho >= 0) else "-"
        p = tr["p_two"]
    want = 1 if d == "+" else -1
    sp_tr = tercile_spread(train, key, d)
    sp_oo = tercile_spread(oos, key, d)
    rec = dict(key=key, group=xf.ALL_GROUP[key], sign=sign, dir=d, n_train=tr["n"], n_oos=oo["n"], months_train=tr["months"], months_oos=oo["months"],
               train_rho=rho, train_rho_dir=(rho * want) if rho is not None else None, train_p=p, train_p_two=tr["p_two"],
               oos_rho=oo["rho"], oos_rho_dir=(oo["rho"] * want) if oo["rho"] is not None else None,
               oos_p=(oo["p_pos"] if d == "+" else oo["p_neg"]),
               train_spread=sp_tr[0], train_good=sp_tr[1], train_bad=sp_tr[2], oos_spread=sp_oo[0], oos_good=sp_oo[1], oos_bad=sp_oo[2],
               reversed=bool(sign in "+-" and rho is not None and rho * want < 0 and tr["p_two"] is not None and tr["p_two"] < ALPHA), p_holm=None)
    return rec


def finalize(rec):
    tr_ok = (rec["n_train"] >= MIN_TRAIN_N and rec["p_holm"] is not None and rec["p_holm"] < ALPHA and rec["train_rho_dir"] is not None and rec["train_rho_dir"] > 0)
    oo_ok = (rec["n_oos"] >= MIN_OOS_N and rec["oos_rho_dir"] is not None and rec["oos_rho_dir"] > 0 and rec["oos_p"] is not None and rec["oos_p"] < ALPHA
             and rec["oos_spread"] is not None and rec["oos_spread"] > 0)
    rec["train_ok"], rec["oos_ok"] = tr_ok, oo_ok
    rec["verdict"] = "CANDIDATE" if (tr_ok and oo_ok) else ("TRAIN_ONLY" if tr_ok else "NONE")
    return rec


def judge_family(train, oos, keys=KEYS):
    recs = {k: judge_var(k, SIGN[k], train, oos) for k in keys}
    ph = g4.holm({k: r["train_p"] for k, r in recs.items() if r["train_p"] is not None})
    for k, r in recs.items():
        r["p_holm"] = ph.get(k)
        finalize(r)
    return recs


# ── 진단 ──
def winner_rb(sigs, key):
    w = [s["f"][key] for s in sigs if s["f"].get(key) is not None and s["ret"] > 0]
    l = [s["f"][key] for s in sigs if s["f"].get(key) is not None and s["ret"] <= 0]
    if not w or not l:
        return None
    gt = lt = 0
    for x in w:
        for y in l:
            gt += x > y; lt += x < y
    return (gt - lt) / (len(w) * len(l))


def stop_share_by_tercile(sigs, key):
    pts = sorted(((s["f"][key], s["sym"], s["reason"]) for s in sigs if s["f"].get(key) is not None), key=lambda t: (t[0], t[1]))
    if len(pts) < 6:
        return None
    k = max(2, len(pts) // 3)
    lo, mid, hi = pts[:k], pts[k:-k], pts[-k:]
    return [sum(1 for _, _, r in g if r == "stop") / len(g) if g else None for g in (lo, mid, hi)]


def demeaned(sigs, key, min_m=3):
    by = {}
    for s in sigs:
        if s["f"].get(key) is not None:
            by.setdefault(s["month"], []).append(s)
    xs, ys = [], []
    for g in by.values():
        if len(g) < min_m:
            continue
        mf = st.mean(s["f"][key] for s in g); mr = st.mean(s["ret"] for s in g)
        xs += [s["f"][key] - mf for s in g]; ys += [s["ret"] - mr for s in g]
    return vx.spearman(xs, ys) if len(xs) >= 10 else None


def _f(v, w=7, pct=False):
    if v is None:
        return " " * (w - 1) + "-"
    return f"{v*100:{w}.2f}" if pct else f"{v:{w}.3f}"


def _p(v):
    return "   -" if v is None else f"{v:.3f}"


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    syms = va._syms()
    print(f"신호봉 프로필 | 주 가족 {PRIMARY_CIDS} 풀링 · 변수 {len(KEYS)} · 월 클러스터 부트 {BOOT_N} · split {SPLIT_DATE} | DEPLOY_ON_PASS={DEPLOY_ON_PASS}")
    if "--no-fetch" not in argv:
        va.fetch(syms, ["1d"])
    rows_1d = va.load_tf(syms, "1d", long=True)
    regmap = rs.build_regime_map(rows_by=rows_1d)
    ranked = turnover_rank(rows_1d)
    top30 = [s for s in ranked[:30]]
    cells = {c["cid"]: c for c in g4.CELLS}
    by_cell = {}
    for cid in PRIMARY_CIDS + (SHORT_CID,):
        c = cells[cid]
        oc = g4.Outcomes("1d", rows_1d, regmap, c["direction"])
        sigs = g4.collect_cell(oc, g4._det(c["det"]), [s for s in top30 if s in rows_1d], c["regime"])
        attach_features(sigs, rows_1d, rows_1d.get("BTC"))
        by_cell[cid] = sigs
        print(f"  [signals] {cid:<32} n={len(sigs)} train {sum(1 for s in sigs if s['date'] < SPLIT_DATE)} / OOS {sum(1 for s in sigs if s['date'] >= SPLIT_DATE)}")
    prim = [s for cid in PRIMARY_CIDS for s in by_cell[cid]]
    train = [s for s in prim if s["date"] < SPLIT_DATE]
    oos = [s for s in prim if s["date"] >= SPLIT_DATE]
    print(f"[primary] 1d 롱 4셀 풀 n={len(prim)} train {len(train)} / OOS {len(oos)} · 평균수익 train {st.mean(s['ret'] for s in train)*100:+.2f}% OOS {st.mean(s['ret'] for s in oos)*100 if oos else float('nan'):+.2f}%")

    recs = judge_family(train, oos)
    print("\n== 주 판정 (풀 스피어만·월 부트 p·Holm / OOS 재현 / 3분위 스프레드) ==")
    print(f"{'변수':<18}{'grp':<10}{'sg':<3}{'dir':<4}{'nTr':>5}{'rhoTr':>8}{'p':>7}{'Holm':>7}{'sprTr':>8}{'nOO':>5}{'rhoOO':>8}{'pOO':>7}{'sprOO':>8}  판정")
    for k in sorted(recs, key=lambda k: (recs[k]["p_holm"] if recs[k]["p_holm"] is not None else 9, -(recs[k]["train_rho_dir"] or 0))):
        r = recs[k]
        print(f"{k:<18}{r['group']:<10}{r['sign']:<3}{r['dir']:<4}{r['n_train']:>5}{_f(r['train_rho_dir'],8)}{_p(r['train_p']):>7}{_p(r['p_holm']):>7}{_f(r['train_spread'],7,True)}%"
              f"{r['n_oos']:>5}{_f(r['oos_rho_dir'],8)}{_p(r['oos_p']):>7}{_f(r['oos_spread'],7,True)}%  {r['verdict']}{' REVERSED' if r['reversed'] else ''}")
    counts = {v: sum(1 for r in recs.values() if r["verdict"] == v) for v in ("CANDIDATE", "TRAIN_ONLY", "NONE")}
    counts["REVERSED"] = sum(1 for r in recs.values() if r["reversed"])
    print(f"\n판정: {counts}")

    diag = {"d1": {}, "d2": {}, "d3": {}, "d4": {}, "d5": {}}
    print("\n== D1 셀별 train/OOS rho (방향 정렬) · D2 승자 vs 패자 rb · D3 3분위 손절비율(low/mid/high) · D4 월 demean rho ==")
    for k in KEYS:
        d = recs[k]["dir"]; w = 1 if d == "+" else -1
        diag["d1"][k] = {}
        cell_txt = []
        for cid in PRIMARY_CIDS:
            cs = by_cell[cid]
            tr = month_boot_rho([s for s in cs if s["date"] < SPLIT_DATE], k, n_boot=0)
            oo = month_boot_rho([s for s in cs if s["date"] >= SPLIT_DATE], k, n_boot=0)
            diag["d1"][k][cid] = dict(train=(tr["rho"] * w) if tr["rho"] is not None else None, oos=(oo["rho"] * w) if oo["rho"] is not None else None, n=tr["n"] + oo["n"])
            cell_txt.append(f"{cid.split('|')[0][:3]}|{cid.split('|')[1][:4]} {_f(diag['d1'][k][cid]['train'],6)}/{_f(diag['d1'][k][cid]['oos'],6)}")
        diag["d2"][k] = winner_rb(prim, k)
        diag["d3"][k] = stop_share_by_tercile(prim, k)
        diag["d4"][k] = demeaned(prim, k)
        d3 = diag["d3"][k]
        d3t = "/".join(f"{v*100:.0f}" for v in d3) + "%" if d3 else "-"
        print(f"  {k:<18} " + " ".join(cell_txt) + f"  D2 rb {_f(diag['d2'][k])}  D3 {d3t:<12} D4 {_f(diag['d4'][k])}")
    sh = by_cell[SHORT_CID]
    sh_tr = [s for s in sh if s["date"] < SPLIT_DATE]; sh_oo = [s for s in sh if s["date"] >= SPLIT_DATE]
    print(f"\n== D5 숏 셀 {SHORT_CID} n={len(sh)} (train {len(sh_tr)} / OOS {len(sh_oo)}) — 풀 rho(원부호) ==")
    for k in KEYS:
        a = month_boot_rho(sh_tr, k, n_boot=0); b = month_boot_rho(sh_oo, k, n_boot=0)
        diag["d5"][k] = dict(train=a["rho"], oos=b["rho"])
        print(f"  {k:<18} train {_f(a['rho'])} (n {a['n']})  oos {_f(b['rho'])} (n {b['n']})")

    out = dict(frame="signal_profile", split=SPLIT_DATE, primary=list(PRIMARY_CIDS), n=dict(all=len(prim), train=len(train), oos=len(oos)),
               cells={cid: len(v) for cid, v in by_cell.items()}, counts=counts, results=recs, diag=diag, deploy_on_pass=DEPLOY_ON_PASS)
    json.dump(out, open("_signal_profile.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print("RESULT_JSON: " + json.dumps(dict(frame="signal_profile", n=out["n"], counts=counts,
                                            verdicts={k: r["verdict"] + ("/REV" if r["reversed"] else "") for k, r in recs.items() if r["verdict"] != "NONE" or r["reversed"]},
                                            top=[(k, recs[k]["dir"], round(recs[k]["train_rho_dir"] or 0, 3), recs[k]["p_holm"], round(recs[k]["oos_rho_dir"] or 0, 3)) for k in sorted(recs, key=lambda k: recs[k]["p_holm"] if recs[k]["p_holm"] is not None else 9)[:8]]),
                                       ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
