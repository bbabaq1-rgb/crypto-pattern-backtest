"""
study_ma_breakout.py — 일봉 장기 이평선(180/200/250일) 상향 돌파 뒤 '슈팅' 이벤트 스터디 (2026-09-06, 사용자 지시
"일봉 기준 이평선 180일 이상을 돌파했을 때 슈팅이 나오는 케이스 수익률 분석해줘").

성격
  탐색적 분석. 배포 판정 시험이 아니다 — 동결 게이트·방식D 수치는 참고로 같이 찍지만, 진입 후보로 올리려면
  별도 사전 등록(디텍터 모듈 + revival 확인 프레임)이 필요하다. 이 스크립트는 실거래 코드를 import 하지 않는다.

이벤트 정의(사전 등록)
  MA_N = 단순이동평균 N일(N ∈ {180, 200, 250}), 종가 기준.
  돌파 = close[i] > MA[i] 이고 close[i-1] <= MA[i-1] 이며, 직전 BELOW_MIN(20)봉 이상 연속으로 close <= MA 였던 경우
        (이평선 근처에서 톱질하는 재돌파는 제외 — 그런 것도 '재돌파' 셀로 따로 센다).
  진입 = 돌파봉 종가(인과: 그 봉이 닫힌 뒤 알 수 있는 정보만 사용).
  필터 변형(각각 따로 셀): raw / decisive(종가 >= MA×1.02) / volume(돌파봉 거래량 >= 20봉 평균×1.5) / slope(MA[i] > MA[i-20]) /
        deep(직전 60봉 최저 종가가 MA 대비 −20% 이하 — 깊은 곳에서 올라온 돌파).

측정(셀마다)
  · 전방 수익률 close→close  +5/+10/+20/+40/+60봉: 평균·중앙·승률
  · 슈팅률 = MFE(진입 후 k봉 내 최고가/진입가 −1) 가 +20% / +30% / +50% 이상인 비율, k=20/40/60
  · MAE(최저가 기준 최대 역행) 중앙값, 이평선 재하향 비율(20봉 내 종가 < MA)
  · 무작위 진입 베이스라인(같은 종목 풀, k=n, 시드 42)의 같은 지표 — '슈팅률이 원래 얼마인가'를 같이 본다
  · 동결 라벨(±10%/20봉) 게이트 v2 판정과 방식D(−8%/레짐/30봉) 건당 수익 — 참고
  · 분해: 진입 레짐 / 연도 / 코호트(top30 vs 나머지) / 메이저 7 vs 알트
출력: _ma_breakout.json + RESULT_JSON.  실행: python study_ma_breakout.py [--no-fetch]
"""
import json
import random
import statistics as st
import sys
import time

import detlib
import method_s as ms
import regime_switch as rs
import validate_regime_split_all as va
from validate_regime_split import turnover_rank
from validate_late_entry import gate_v2, _f

SEED, BOOT_N = 42, 1000
MA_WINDOWS = (180, 200, 250)
BELOW_MIN = 20
HORIZONS = (5, 10, 20, 40, 60)
MFE_K = (20, 40, 60)
SHOOT_THR = (0.20, 0.30, 0.50)
DECISIVE, VOL_MULT, SLOPE_LB, DEEP_LB, DEEP_THR = 1.02, 1.5, 20, 60, -0.20
FILTERS = ("raw", "decisive", "volume", "slope", "deep", "rebreak")
POOL_CAP = 20000
MAJORS = list(detlib.SYMBOLS)
FEE = detlib.FEE


def sma(vals, n):
    out = [None] * len(vals)
    s = 0.0
    for i, v in enumerate(vals):
        s += v
        if i >= n:
            s -= vals[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def crosses(rows, n):
    """(i, kind) — kind 'fresh'(직전 BELOW_MIN봉 이상 아래) / 'rebreak'(그보다 짧게 아래였다가 재돌파)."""
    cl = [r["c"] for r in rows]
    ma = sma(cl, n)
    out = []
    below = 0
    for i in range(1, len(rows)):
        if ma[i] is None or ma[i - 1] is None:
            continue
        if cl[i] > ma[i] and cl[i - 1] <= ma[i - 1]:
            out.append((i, "fresh" if below >= BELOW_MIN else "rebreak"))
        below = below + 1 if cl[i] <= ma[i] else 0
    return out, ma


def passes(filt, rows, i, ma):
    cl = [r["c"] for r in rows]
    if filt == "raw":
        return True
    if filt == "decisive":
        return cl[i] >= ma[i] * DECISIVE
    if filt == "volume":
        if i < 21:
            return False
        avg = sum(r["v"] for r in rows[i - 20:i]) / 20
        return avg > 0 and rows[i]["v"] >= avg * VOL_MULT
    if filt == "slope":
        return i >= SLOPE_LB and ma[i - SLOPE_LB] is not None and ma[i] > ma[i - SLOPE_LB]
    if filt == "deep":
        if i < DEEP_LB:
            return False
        lo = min(cl[i - DEEP_LB:i])
        return lo / ma[i] - 1 <= DEEP_THR
    raise ValueError(filt)


def forward(rows, i):
    """전방 지표. 데이터가 모자라면 해당 항목 None."""
    base = rows[i]["c"]
    n = len(rows)
    out = {}
    for h in HORIZONS:
        out[f"r{h}"] = (rows[i + h]["c"] / base - 1) if i + h < n else None
    for k in MFE_K:
        seg = rows[i + 1:min(i + k, n - 1) + 1]
        if len(seg) < k:
            out[f"mfe{k}"] = None; out[f"mae{k}"] = None
        else:
            out[f"mfe{k}"] = max(r["h"] for r in seg) / base - 1
            out[f"mae{k}"] = min(r["l"] for r in seg) / base - 1
    return out


def summarize(events):
    """events: [dict(fwd=..., label=..., d=..., retest=...)]"""
    n = len(events)
    if n == 0:
        return dict(n=0)
    res = dict(n=n)
    for h in HORIZONS:
        v = [e["fwd"][f"r{h}"] for e in events if e["fwd"][f"r{h}"] is not None]
        res[f"r{h}"] = dict(n=len(v), mean=st.mean(v), median=st.median(v), win=sum(1 for x in v if x > 0) / len(v)) if v else None
    for k in MFE_K:
        v = [e["fwd"][f"mfe{k}"] for e in events if e["fwd"][f"mfe{k}"] is not None]
        a = [e["fwd"][f"mae{k}"] for e in events if e["fwd"][f"mae{k}"] is not None]
        res[f"mfe{k}"] = dict(n=len(v), median=st.median(v), **{f"shoot{int(t*100)}": sum(1 for x in v if x >= t) / len(v) for t in SHOOT_THR}) if v else None
        res[f"mae{k}_median"] = st.median(a) if a else None
    rt = [e["retest"] for e in events if e["retest"] is not None]
    res["retest20"] = sum(rt) / len(rt) if rt else None
    lab = [e["label"] for e in events if e["label"] is not None]
    res["label_mean"] = st.mean(lab) if lab else None
    dd = [e["d"] for e in events if e["d"] is not None]
    res["d_mean"] = st.mean(dd) if dd else None
    res["d_win"] = (sum(1 for x in dd if x > 0) / len(dd)) if dd else None
    return res


def build_events(rows_by, regmap, n_ma, filt, syms):
    evs = []
    for sym in syms:
        rows = rows_by[sym]
        cr, ma = crosses(rows, n_ma)
        cl = [r["c"] for r in rows]
        lab = lambda j, rows=rows: regmap.get(rows[j]["date"])
        for i, kind in cr:
            if filt == "rebreak":
                if kind != "rebreak":
                    continue
            else:
                if kind != "fresh" or not passes(filt, rows, i, ma):
                    continue
            if i + 1 >= len(rows):
                continue
            fwd = forward(rows, i)
            retest = None
            if i + 20 < len(rows):
                retest = int(any(cl[j] < ma[j] for j in range(i + 1, i + 21) if ma[j] is not None))
            label = detlib.outcome(rows, i, "long")[1] if i + 1 < len(rows) else None
            d = ms.outcome(rows, i, "long", set(), lab, use_regime=True, max_hold=ms.MAX_HOLD)[0] if i + 2 < len(rows) else None
            evs.append(dict(sym=sym, date=rows[i]["date"], regime=regmap.get(rows[i]["date"]), fwd=fwd, retest=retest,
                            label=label, d=d, ret=label, major=sym in MAJORS))
    return evs


def baseline(rows_by, syms, seed=SEED):
    idx = [(s, i) for s in syms for i in range(260, len(rows_by[s]) - 61)]
    rng = random.Random(seed)
    if len(idx) > POOL_CAP:
        idx = rng.sample(idx, POOL_CAP)
    evs = []
    for s, i in idx:
        rows = rows_by[s]
        evs.append(dict(fwd=forward(rows, i), retest=None, label=detlib.outcome(rows, i, "long")[1], d=None))
    return evs


def _line(name, r):
    if r.get("n", 0) == 0:
        return f"  {name:<22} n=0"
    def fr(h):
        x = r.get(f"r{h}")
        return f"{x['mean']*100:+5.1f}%/{x['win']*100:3.0f}%" if x else "   n/a   "
    m40 = r.get("mfe40") or {}
    return (f"  {name:<22} n={r['n']:>5} | +5 {fr(5)} +20 {fr(20)} +60 {fr(60)} | 슈팅40봉 ≥20% {m40.get('shoot20', 0)*100:4.0f}% "
            f"≥30% {m40.get('shoot30', 0)*100:4.0f}% ≥50% {m40.get('shoot50', 0)*100:4.0f}% | MFE40 중앙 {m40.get('median', 0)*100:+5.1f}% "
            f"MAE40 중앙 {(r.get('mae40_median') or 0)*100:+5.1f}% | 재하향20 {(r.get('retest20') or 0)*100:3.0f}% "
            f"| 라벨 {_f(r.get('label_mean'), 7)} D {_f(r.get('d_mean'), 7)}")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    syms = va._syms()
    print(f"장기 이평 돌파 슈팅 스터디 | 유니버스 {len(syms)} | MA {MA_WINDOWS} | BELOW_MIN {BELOW_MIN} | 시드 {SEED}")
    if "--no-fetch" not in argv:
        va.fetch(syms, ["1d"])
    regmap = rs.build_regime_map()
    rows_by = va.load_tf(syms, "1d")
    syms = sorted(rows_by)
    ranked = turnover_rank(rows_by)
    top30 = set(ranked[:30])
    dates = sorted({r["date"] for rows in rows_by.values() for r in rows})
    print(f"[데이터] 1d 종목 {len(rows_by)} | {dates[0]}~{dates[-1]}")

    t0 = time.time()
    base_evs = baseline(rows_by, syms)
    base = summarize(base_evs)
    base_pool = [e["label"] for e in base_evs]
    print(f"\n[베이스라인] 무작위 진입 {len(base_evs)}건 ({time.time()-t0:.0f}s)")
    print(_line("random", base))

    out = dict(baseline=base, cells={})
    for n_ma in MA_WINDOWS:
        print(f"\n[MA {n_ma}]")
        for filt in FILTERS:
            evs = build_events(rows_by, regmap, n_ma, filt, syms)
            s = summarize(evs)
            g = gate_v2(f"MA{n_ma}/{filt} 라벨게이트", [dict(sym=e["sym"], date=e["date"], ret=e["label"]) for e in evs if e["label"] is not None], base_pool) if evs else None
            print(_line(f"{filt}", s))
            splits = {}
            if evs:
                for key, fn in (("regime", lambda e: e["regime"] or "none"), ("year", lambda e: e["date"][:4]),
                                ("cohort", lambda e: "top30" if e["sym"] in top30 else "rest"), ("major", lambda e: "majors" if e["major"] else "alts")):
                    grp = {}
                    for e in evs:
                        grp.setdefault(fn(e), []).append(e)
                    splits[key] = {k: summarize(v) for k, v in sorted(grp.items())}
                if filt == "raw":
                    for k, v in splits["regime"].items():
                        print(_line(f"  ↳ 레짐 {k}", v))
                    for k, v in splits["year"].items():
                        print(_line(f"  ↳ {k}", v))
                    for k, v in splits["cohort"].items():
                        print(_line(f"  ↳ {k}", v))
                    for k, v in splits["major"].items():
                        print(_line(f"  ↳ {k}", v))
            out["cells"][f"MA{n_ma}/{filt}"] = dict(summary=s, gate=g, splits=splits)
    json.dump(out, open("_ma_breakout.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print("\n[저장] _ma_breakout.json")
    brief = {k: dict(n=v["summary"].get("n", 0),
                     r20=round((v["summary"].get("r20") or {}).get("mean", 0) * 100, 2),
                     shoot20_40=round(((v["summary"].get("mfe40") or {}).get("shoot20", 0)) * 100, 1),
                     shoot30_40=round(((v["summary"].get("mfe40") or {}).get("shoot30", 0)) * 100, 1),
                     label=round((v["summary"].get("label_mean") or 0) * 100, 2),
                     gate=(v["gate"] or {}).get("verdict"), bp=(v["gate"] or {}).get("boot_p"))
             for k, v in out["cells"].items()}
    brief["random"] = dict(n=base["n"], r20=round((base.get("r20") or {}).get("mean", 0) * 100, 2),
                           shoot20_40=round(((base.get("mfe40") or {}).get("shoot20", 0)) * 100, 1),
                           shoot30_40=round(((base.get("mfe40") or {}).get("shoot30", 0)) * 100, 1),
                           label=round((base.get("label_mean") or 0) * 100, 2))
    print("RESULT_JSON: " + json.dumps(brief, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
