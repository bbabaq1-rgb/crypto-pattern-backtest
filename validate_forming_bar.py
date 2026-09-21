"""
validate_forming_bar.py — 형성 중인 봉 탐지가 검증과 얼마나 다른가 (사전 등록, 2026-09-21)

**왜.** 배포 패턴 일부는 아직 `rows[-1]`(= 거래소가 주는 **형성 중**인 봉)에서 탐지하는데,
검증은 닫힌 봉 종가로 신호를 판정했다. 2026-08-30 에 exit_spec 패턴만 `_closed_idx` 로 고쳤고
2026-09-05 에 4h 신규 3종에 `detect_on_closed_bar` 를 붙였으며, 나머지는 **종전 동작을 바꾸지
않으려고 그대로 뒀다.** 그 불일치의 크기가 한 번도 측정된 적이 없다. 같은 종류의 결함으로
하모닉 5종이 등재 정지됐다(피벗 확정에 3봉이 필요해 마지막 봉에서 절대 발화 못 함, 진입 0건).

────────────────────────────────────────────────────────────────────────────
사전 등록 (결과 보기 전 고정 — registry forming_bar_prereg_2026_09_21)

셀: forming 으로 도는 배포 패턴만 — 1d engulfing 롱·숏 / fvg 롱·숏 / inverted_hammer /
    marubozu · 4h three_soldiers_4h.  **레짐 라우팅은 걸지 않는다(무조건부)** — 신호 집합
    차이는 라우팅과 무관하고 라우팅을 걸면 표본만 줄어 검정력이 떨어진다.
    제외(결과 전 기록): triple_bottom_4h / equal_lows_4h / vol_awakening_4h 는
    detect_on_closed_bar=true, cascade·tp1·adopted_1h 는 `_closed_idx` — 이미 닫힌 봉이다.
합성: 1d 부분봉은 **4h 로**, 4h 부분봉은 **1h 로**. 슬로틱 (0,4,8,12,16,20) UTC.
      부분봉 = 그 봉 시작부터 틱까지 닫힌 하위 TF 봉의 OHLCV 합산(정확, 해상도 손실 없음).
      틱 h=0 은 **빈 봉**(o=h=l=c=시가, v=0) — 실거래 틱이 정각 직후라 이 쪽이 실제에 가깝다.
      4h 는 틱과 봉 경계가 일치하므로 사실상 빈 봉에서만 탐지한다(진단으로 h1 판 병기).
중복 방어: 봉 ts 기준 → 한 봉에 **첫 발화 한 번만**. 진입가 = 그 틱의 부분봉 종가.
판정: MATERIAL / IMMATERIAL — 어느 **배포 셀에서든** 하나라도 걸리면 MATERIAL.
      (i)   only_forming 비율 >= 20%   (ii) forming 건당이 closed 대비 1.0%p 이상 낮음
      (iii) forming 건당 평균이 음수
DEPLOY_ON_PASS = False — 고치는 것(기존 패턴에 detect_on_closed_bar 를 켜는 것)은
실거래 규칙 변경이라 사용자 결정 + 관찰 기간(~2026-10-06) 이후.

실행: python validate_forming_bar.py [--no-fetch]
"""
import importlib
import json
import statistics as st
import sys
import time

import detlib
import method_t as mt
import regime_switch
import validate_regime_split_all as va
from validate_regime_split import turnover_rank

DEPLOY_ON_PASS = False

FETCH_WINDOWS = {"1d": 1800, "4h": 1100, "1h": 365}
SLOW_TICK_HOURS = (0, 4, 8, 12, 16, 20)         # scheduler.SLOW_TICK_HOURS 와 같다
BAR_MS = {"1d": 86400000, "4h": 14400000, "1h": 3600000}
SUB_TF = {"1d": "4h", "4h": "1h"}
WINDOW = 120                                     # 부분봉 탐지용 꼬리 길이(충분성은 런타임 검증)
TOP_N = 30
MIN_N = 20                                       # 셀 판정 최소 표본

# 판정 문턱 (동결)
MAT_ONLY_FORMING = 0.20
MAT_DROP = 0.010                                 # 1.0%p
EPS = 1e-12
OUT = "_forming_bar.json"

# (셀, 방향, 디텍터, 반대 디텍터, TF, 코호트)
CELLS = [
    ("engulfing",        "long",  "detector_engulfing",         "detector_engulfing_short", "1d", "top30"),
    ("engulfing_short",  "short", "detector_engulfing_short",   "detector_engulfing",       "1d", "top30"),
    ("fvg",              "long",  "detector_fvg",               "detector_fvg_short",       "1d", "top30"),
    ("fvg_short",        "short", "detector_fvg_short",         "detector_fvg",             "1d", "top30"),
    ("inverted_hammer",  "long",  "detector_inverted_hammer",   None,                       "1d", "majors"),
    ("marubozu",         "long",  "detector_marubozu",          None,                       "1d", "majors"),
    ("three_soldiers_4h", "long", "detector_three_soldiers_4h", None,                       "4h", "all"),
]


# ── 부분봉 ────────────────────────────────────────────────────────────────────
def bucket(child_rows, bar_ms):
    """하위 TF 봉을 상위 봉 시작 ts 로 묶는다. UTC 정렬이라 나눗셈으로 정확히 갈린다."""
    out = {}
    for r in child_rows:
        ts = r.get("ts")
        if not ts:
            continue
        out.setdefault(int(ts) // bar_ms * bar_ms, []).append(r)
    for v in out.values():
        v.sort(key=lambda r: r["ts"])
    return out


def partial(children, k, parent):
    """완료된 하위 봉 k 개로 만든 부분봉. k=0 은 **빈 봉**(막 열린 상태).

    하위 TF OHLCV 합산은 그 구간의 OHLC 와 정확히 같으므로 해상도 손실이 없다.
    """
    if k <= 0:
        o = children[0]["o"] if children else parent["o"]
        return dict(parent, o=o, h=o, l=o, c=o, v=0.0)
    cs = children[:k]
    return dict(parent, o=cs[0]["o"], h=max(c["h"] for c in cs),
                l=min(c["l"] for c in cs), c=cs[-1]["c"],
                v=sum(c.get("v", 0.0) for c in cs))


def fires(detect, rows, i, last_row):
    """rows[:i] 뒤에 last_row 를 붙였을 때 그 마지막 봉이 신호인가 (꼬리 WINDOW 만 본다)."""
    s = max(0, i - WINDOW)
    win = rows[s:i] + [last_row]
    return (len(win) - 1) in set(detect(win))


def window_ok(detect, rows):
    """꼬리 WINDOW 로 자른 탐지가 전체 탐지와 같은가 — 다르면 그 셀은 측정 불가."""
    full = set(detect(rows))
    for i in range(1, len(rows)):
        if fires(detect, rows, i, rows[i]) != (i in full):
            return False
    return True


# ── 신호 수집 ─────────────────────────────────────────────────────────────────
def forming_signals(detect, rows, kids, tf, ticks):
    """{bar_idx: (발화 틱 k, 그 틱의 부분봉 종가)} — 한 봉에 첫 발화 한 번만."""
    out = {}
    for i in range(1, len(rows)):
        ts = rows[i].get("ts")
        if not ts:
            continue
        cs = kids.get(int(ts) // BAR_MS[tf] * BAR_MS[tf], [])
        if not cs:
            continue
        for k in ticks:
            if k > len(cs) - 1 and k > 0:
                break                       # 그 틱까지의 하위 봉이 없다(데이터 공백)
            pb = partial(cs, k, rows[i])
            if fires(detect, rows, i, pb):
                out[i] = (k, pb["c"])
                break
    return out


def outcome_at(rows, si, direction, opp_set, base):
    """방식D 를 **진입가만 갈아 끼워** 돌린다. outcome_d 는 rows[si]['c'] 를 기준가로 쓰므로
    그 한 칸만 바꾸면 청산 로직을 한 줄도 복제하지 않고 그대로 재사용할 수 있다."""
    if base == rows[si]["c"]:
        return mt.outcome_d(rows, si, direction, opp_set)
    r2 = list(rows)
    r2[si] = dict(rows[si], c=base)
    return mt.outcome_d(r2, si, direction, opp_set)


def _stats(rets):
    if not rets:
        return dict(n=0)
    return dict(n=len(rets), mean=st.fmean(rets), med=st.median(rets),
                win=sum(1 for r in rets if r > 0) / len(rets))


def run_cell(cell, rows_by, kids_by, ticks, tag):
    name, direction, detmod, oppmod, tf, cohort = cell
    detect = importlib.import_module(detmod).detect
    opp = importlib.import_module(oppmod).detect if oppmod else None
    n_only_f = n_only_c = n_both = 0
    rets_c, rets_f, dpx, bad_window = [], [], [], 0
    per_sym = 0
    for sym, rows in rows_by.items():
        if len(rows) < 40:
            continue
        kids = kids_by.get(sym)
        if not kids:
            continue
        if per_sym < 3:                      # 종목 3개까지 창 충분성 검증(전수는 느리다)
            if not window_ok(detect, rows[-400:]):
                bad_window += 1
            per_sym += 1
        closed = {i for i in detect(rows) if 0 < i < len(rows) - 1}
        forming = {i: v for i, v in forming_signals(detect, rows, kids, tf, ticks).items()
                   if 0 < i < len(rows) - 1}
        opp_set = set(opp(rows)) if opp else set()
        n_only_f += len(set(forming) - closed)
        n_only_c += len(closed - set(forming))
        n_both += len(closed & set(forming))
        for i in closed:
            rets_c.append(outcome_at(rows, i, direction, opp_set, rows[i]["c"])[0])
        for i, (_, px) in forming.items():
            rets_f.append(outcome_at(rows, i, direction, opp_set, px)[0])
            if i in closed and rows[i]["c"]:
                dpx.append(px / rows[i]["c"] - 1.0)
    c, f = _stats(rets_c), _stats(rets_f)
    nf = f["n"]
    return dict(cell=name, tf=tf, tag=tag, cohort=cohort,
                only_forming=n_only_f, only_closed=n_only_c, both=n_both,
                only_forming_ratio=(n_only_f / nf if nf else None),
                closed=c, forming=f, bad_window=bad_window,
                dpx_med=(st.median(dpx) if dpx else None),
                dpx_absmed=(st.median([abs(x) for x in dpx]) if dpx else None))


def judge(r):
    """MATERIAL 조건 세 개 중 걸린 것. 표본 < MIN_N 이면 판정하지 않는다."""
    hits = []
    if r["forming"]["n"] < MIN_N:
        return hits
    if r["only_forming_ratio"] is not None and r["only_forming_ratio"] >= MAT_ONLY_FORMING - EPS:
        hits.append(f"(i) only_forming {r['only_forming_ratio']*100:.0f}%")
    if r["closed"]["n"] >= MIN_N and r["closed"]["mean"] - r["forming"]["mean"] >= MAT_DROP - EPS:
        hits.append(f"(ii) 건당 {r['closed']['mean']*100:+.2f}% → {r['forming']['mean']*100:+.2f}%")
    if r["forming"]["mean"] < 0:
        hits.append(f"(iii) forming 건당 음수 {r['forming']['mean']*100:+.2f}%")
    return hits


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    print("=" * 108)
    print("형성 중인 봉 탐지 — 사전 등록 (registry forming_bar_prereg_2026_09_21)")
    print(f"  판정 MATERIAL 조건: (i) only_forming >= {MAT_ONLY_FORMING*100:.0f}% "
          f"(ii) 건당 {MAT_DROP*100:.1f}%p 이상 하락 (iii) forming 건당 음수 | "
          f"DEPLOY_ON_PASS={DEPLOY_ON_PASS}")
    print("=" * 108, flush=True)

    syms = va._syms()
    if "--no-fetch" not in argv:
        import fetch_data
        for tf, win in FETCH_WINDOWS.items():
            t0, okn = time.time(), 0
            for s in syms:
                try:
                    _, tot = fetch_data.update_csv(f"{s}/USDT", tf, detlib.CSV(s, tf), window_days=win)
                    okn += tot > 0
                except Exception as e:
                    print(f"  [fetch] {s} {tf} 실패: {str(e)[:50]}")
            print(f"[fetch] {tf} {win}일 {okn}/{len(syms)} ({time.time()-t0:.0f}s)", flush=True)

    rows = {tf: va.load_tf(syms, tf) for tf in ("1d", "4h", "1h")}
    # 비워 두면 outcome_d 의 레짐 전환 청산이 조용히 꺼진다(2026-09-21 발견).
    mt.REGMAP = regime_switch.build_regime_map()
    ranked = turnover_rank(rows["1d"])
    pools = {"top30": ranked[:TOP_N], "majors": list(detlib.SYMBOLS),
             "all": sorted(rows["4h"])}
    kids = {tf: {s: bucket(rows[SUB_TF[tf]].get(s, []), BAR_MS[tf]) for s in syms}
            for tf in ("1d", "4h")}
    print(f"[데이터] 1d {len(rows['1d'])} / 4h {len(rows['4h'])} / 1h {len(rows['1h'])} 종목",
          flush=True)

    out = []
    for cell in CELLS:
        name, _, _, _, tf, cohort = cell
        pool = {s: rows[tf][s] for s in pools[cohort] if s in rows[tf]}
        ticks = [h // 4 for h in SLOW_TICK_HOURS] if tf == "1d" else [0]
        t0 = time.time()
        r = run_cell(cell, pool, kids[tf], ticks, "main")
        r["hits"] = judge(r)
        out.append(r)
        print(f"  [{name}] {time.time()-t0:.0f}s  closed {r['closed']['n']} / "
              f"forming {r['forming']['n']}", flush=True)
        if tf == "4h":                       # 진단 — 첫 하위 봉까지 담은 판
            d = run_cell(cell, pool, kids[tf], [1], "h1")
            d["hits"] = []
            out.append(d)

    print("\n" + "-" * 108)
    print(f"{'셀':<20}{'판':<6}{'closed n':>9}{'forming n':>10}{'only_f':>8}{'only_c':>8}"
          f"{'only_f%':>9}{'closed 건당':>12}{'forming 건당':>13}{'진입가차':>10}")
    print("-" * 108)
    for r in out:
        c, f = r["closed"], r["forming"]
        ofr = "—" if r["only_forming_ratio"] is None else f"{r['only_forming_ratio']*100:.0f}%"
        dp = "—" if r["dpx_med"] is None else f"{r['dpx_med']*100:+.2f}%"
        print(f"{r['cell']:<20}{r['tag']:<6}{c['n']:>9}{f['n']:>10}{r['only_forming']:>8}"
              f"{r['only_closed']:>8}{ofr:>9}"
              f"{(c['mean']*100 if c['n'] else 0):>11.2f}%"
              f"{(f['mean']*100 if f['n'] else 0):>12.2f}%{dp:>10}")
    print("-" * 108)

    bad = [r["cell"] for r in out if r["bad_window"]]
    if bad:
        print(f"[경고] 꼬리 {WINDOW}봉 탐지가 전체 탐지와 불일치한 셀: {sorted(set(bad))} "
              f"— 그 셀의 forming 수치는 신뢰할 수 없다")

    main_rows = [r for r in out if r["tag"] == "main"]
    hits = {r["cell"]: r["hits"] for r in main_rows if r["hits"]}
    thin = [r["cell"] for r in main_rows if r["forming"]["n"] < MIN_N]
    v = "MATERIAL" if hits else "IMMATERIAL"
    print("\n" + "=" * 108)
    print(f"판정: {v}")
    for cell, hs in sorted(hits.items()):
        print(f"  - {cell}: " + " / ".join(hs))
    if not hits:
        print("  - 배포 셀 어디에서도 세 조건이 걸리지 않음")
    if thin:
        print(f"  * 표본 부족({MIN_N} 미만)으로 판정 제외: {thin} "
              f"— **발화 자체가 거의 없다는 사실 자체가 결과다**")
    print(f"실거래 무변경 (DEPLOY_ON_PASS={DEPLOY_ON_PASS})")
    print("=" * 108)

    json.dump(dict(verdict=v, hits=hits, thin=thin, cells=out,
                   thresholds=dict(only_forming=MAT_ONLY_FORMING, drop=MAT_DROP, min_n=MIN_N),
                   windows=FETCH_WINDOWS, ticks=list(SLOW_TICK_HOURS),
                   deploy_on_pass=DEPLOY_ON_PASS),
              open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print(f"[저장] {OUT}")


if __name__ == "__main__":
    main()
