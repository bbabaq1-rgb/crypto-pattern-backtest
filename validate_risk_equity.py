"""validate_risk_equity.py — R-120: 위험 수준 x 시작 equity 별 킬스위치($100) 도달 확률 (진단 전용, 2026-11-18).

R-118(risk 1.5%) 프레임 그대로 — 7일 창 52개 복원추출, validate_gap.simulate(floor=100) — 에서 RISK_FRAC 만
{0.5,1.0,1.5}% 로 바꾸고 equity {240,355,500,750} 를 교차한다. 같은 재표집을 12셀 전부에 적용(짝지음).
사전 등록: registry risk_equity_prereg_2026_11_18. DEPLOY_ON_PASS=False — 위험 수준·충전은 사용자 결정.
"""
import json
import random
import sys

import validate_gap as vg
import validate_killswitch as ks
import validate_portfolio as vp

DEPLOY_ON_PASS = False
RISKS = (0.005, 0.010, 0.015)
EQS = (240.0, 355.0, 500.0, 750.0)
SEED = 120
BOOT_N = 500
SAFE_P = 0.05
LOW_RISK_EQ = 355.0     # 가설: risk 0.5% 의 안전 최소 equity 가 이 값 이하


def run_cell(path, eq0, risk, floor=ks.FLOOR):
    old = vp.START_EQ
    vp.START_EQ = eq0
    try:
        p = []
        vg.simulate(path, path=p, floor=floor, risk=risk)
    finally:
        vp.START_EQ = old
    return any(e < floor for _, e in p)


def boot(pool, seed=SEED, n=BOOT_N):
    wins = ks.windows_of(pool)
    rng = random.Random(seed)
    hit = {(r, e): 0 for r in RISKS for e in EQS}
    for _ in range(n):
        path = ks.one_year_path(wins, rng)
        for r in RISKS:
            for e in EQS:
                hit[(r, e)] += run_cell(path, e, r)
    return {k: v / n for k, v in hit.items()}


def min_safe(p, risk):
    s = [e for e in EQS if p[(risk, e)] < SAFE_P]
    return min(s) if s else None


def verdict(p):
    """p: {(risk, eq): P(reach)}.
    NO_SAFE_CELL: 12셀 중 5% 미만 0개 (위험 축소로 안 풀림).
    RISK_SCALES: risk 0.5% 의 최소 안전 equity 가 존재, <= LOW_RISK_EQ, 그리고 risk 가 낮을수록 최소 안전 equity 가
      단조 비증가(None 은 무한대) — 가설 충족.
    SAFE_BUT_LARGE: 안전 셀은 있으나 위 조건 불충족."""
    safe = [k for k, v in p.items() if v < SAFE_P]
    if not safe:
        return "NO_SAFE_CELL"
    inf = float("inf")
    ms = [min_safe(p, r) or inf for r in sorted(RISKS)]   # 0.5, 1.0, 1.5
    mono = all(ms[i] <= ms[i + 1] for i in range(len(ms) - 1))
    if ms[0] <= LOW_RISK_EQ and mono:
        return "RISK_SCALES"
    return "SAFE_BUT_LARGE"


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    import detlib
    import method_t as mt
    import method_x as mx
    import regime_switch as rs
    from validate_regime_split import turnover_rank
    syms = json.load(open("universe.json", encoding="utf-8"))["trading_universe"]
    if "--no-fetch" not in argv:
        vp.fetch(syms)
    rows_4h = {}
    for s in syms:
        try:
            rows_4h[s] = detlib.load_ohlcv(s, "4h")
        except (FileNotFoundError, RuntimeError):
            continue
    ranked = turnover_rank(rows_4h)
    regmap = rs.build_regime_map()
    mt.REGMAP = regmap
    base = sorted(vp.collect_1d(syms) + vp.collect_4h(rows_4h, ranked, regmap), key=lambda t: t["t_in"])
    cut = mx._tnum(vp.SPLIT)
    ho = [t for t in base if t["t_in"] >= cut]
    print(f"총 거래 {len(base)} (holdout {len(ho)}), 7일 창 {len(ks.windows_of(base))}개", flush=True)
    p = boot(base)
    for r in RISKS:
        print(f"[전체 풀] risk {r*100:.1f}%  " + "  ".join(f"eq{e:.0f} {p[(r, e)]*100:5.1f}%" for e in EQS)
              + f"  최소안전 {min_safe(p, r)}", flush=True)
    ph = None
    if len(ks.windows_of(ho)) >= 8:
        ph = boot(ho, seed=SEED + 1)
        for r in RISKS:
            print(f"[holdout 풀 진단] risk {r*100:.1f}%  " + "  ".join(f"eq{e:.0f} {ph[(r, e)]*100:5.1f}%" for e in EQS), flush=True)
    v = verdict(p)
    print(f"[판정] {v} (DEPLOY_ON_PASS={DEPLOY_ON_PASS})")
    ser = lambda d: {f"{r}|{e}": x for (r, e), x in d.items()}
    json.dump(dict(verdict=v, main=ser(p), holdout=ser(ph) if ph else None), open("_risk_equity.json", "w"), indent=1)
    print("RESULT_JSON: " + json.dumps(dict(verdict=v, p=ser(p)), separators=(",", ":")))


if __name__ == "__main__":
    main()
