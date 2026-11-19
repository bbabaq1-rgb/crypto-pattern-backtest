"""validate_risk_cost.py — R-122: 위험 수준 x 시작 equity 별 '안전의 대가' (진단 전용, 2026-11-19).

R-120 프레임 그대로(7일 창 52개 1년 부트 500회, 시드 122, 킬스위치 $100) — 셀마다 도달 확률이 아니라
최종 equity 중앙·성장배수·MDD 중앙·체결 수·스킵 비율을 잰다. 같은 재표집을 12셀에 적용(짝지음).
사전 등록: registry risk_cost_prereg_2026_11_19. DEPLOY_ON_PASS=False — 위험 수준은 사용자 결정.
"""
import json
import random
import statistics as st
import sys

import validate_gap as vg
import validate_killswitch as ks
import validate_portfolio as vp

DEPLOY_ON_PASS = False
RISKS = (0.005, 0.010, 0.015)
EQS = (240.0, 355.0, 500.0, 750.0)
SEED = 122
BOOT_N = 500
RATIO_MIN = 0.70        # 1.0% 성장배수 중앙 / 1.5% 성장배수 중앙 하한
RATIO_EQS = (355.0, 500.0, 750.0)
SKIP_MAX = 0.20         # risk 1.0%, eq 240 의 스킵 비율 상한(슬롯·증거금·최소주문 합산 = 상한 추정)


def run_cell(path, eq0, risk, floor=ks.FLOOR):
    old = vp.START_EQ
    vp.START_EQ = eq0
    try:
        r = vg.simulate(path, floor=floor, risk=risk)
    finally:
        vp.START_EQ = old
    n = r["taken"] + r["skipped"]
    return dict(final=r["final"], mdd=r["mdd"], taken=r["taken"], skip=(r["skipped"] / n if n else 0.0))


def boot(pool, seed=SEED, n=BOOT_N):
    wins = ks.windows_of(pool)
    rng = random.Random(seed)
    acc = {(r, e): [] for r in RISKS for e in EQS}
    for _ in range(n):
        path = ks.one_year_path(wins, rng)
        for r in RISKS:
            for e in EQS:
                acc[(r, e)].append(run_cell(path, e, r))
    return acc


def summarize(acc):
    out = {}
    for k, rows in acc.items():
        eq0 = k[1]
        fin = st.median(x["final"] for x in rows)
        out[k] = dict(final_med=fin, growth_med=fin / eq0, mdd_med=st.median(x["mdd"] for x in rows),
                      taken_med=st.median(x["taken"] for x in rows), skip_med=st.median(x["skip"] for x in rows),
                      p_loss=sum(x["final"] < k[1] for x in rows) / len(rows))
    return out


def ratio(s, eq):
    """risk 1.0% 성장배수 중앙 / risk 1.5% 성장배수 중앙. 1.5% 가 <=0 이거나 성장 ≤1 이면 None(정의 불가)."""
    g15 = s[(0.015, eq)]["growth_med"]
    if g15 <= 1.0:
        return None
    return (s[(0.010, eq)]["growth_med"] - 1.0) / (g15 - 1.0)   # 수익분(성장-1) 비율


def verdict(s):
    """COST_SMALL: 수익분 비율 >= RATIO_MIN at eq 355/500/750 전부 AND risk 1.0%/eq240 skip 중앙 < SKIP_MAX.
    COST_LARGE: 비율 정의됨이고 355/500/750 중 과반(2개 이상)이 RATIO_MIN 미만.
    INCONCLUSIVE: 어느 eq 에서 1.5% 성장 ≤1(비율 정의 불가)이 있어 위 둘을 못 가름.
    MIXED: 그 외(비율은 통과하나 skip 실패 등)."""
    rs = [ratio(s, e) for e in RATIO_EQS]
    if any(x is None for x in rs):
        return "INCONCLUSIVE"
    low = sum(x < RATIO_MIN for x in rs)
    if low >= 2:
        return "COST_LARGE"
    if low == 0 and s[(0.010, 240.0)]["skip_med"] < SKIP_MAX:
        return "COST_SMALL"
    return "MIXED"


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    import detlib
    import method_t as mt
    import method_x as mx
    import regime_switch as rs_
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
    regmap = rs_.build_regime_map()
    mt.REGMAP = regmap
    base = sorted(vp.collect_1d(syms) + vp.collect_4h(rows_4h, ranked, regmap), key=lambda t: t["t_in"])
    cut = mx._tnum(vp.SPLIT)
    ho = [t for t in base if t["t_in"] >= cut]
    print(f"총 거래 {len(base)} (holdout {len(ho)}), 7일 창 {len(ks.windows_of(base))}개", flush=True)
    s = summarize(boot(base))
    for r in RISKS:
        for e in EQS:
            c = s[(r, e)]
            print(f"[전체 풀] risk {r*100:.1f}% eq{e:.0f} 최종중앙 {c['final_med']:8.1f} 성장 {c['growth_med']:.2f}x "
                  f"MDD중앙 {c['mdd_med']*100:6.1f}% 체결 {c['taken_med']:.0f} 스킵 {c['skip_med']*100:4.1f}% 손실확률 {c['p_loss']*100:4.1f}%", flush=True)
    for e in RATIO_EQS:
        print(f"[수익분 비율 1.0%/1.5%] eq{e:.0f}: {ratio(s, e)}", flush=True)
    sh = None
    if len(ks.windows_of(ho)) >= 8:
        sh = summarize(boot(ho, seed=SEED + 1))
        for r in RISKS:
            print(f"[holdout 풀 진단] risk {r*100:.1f}% " + "  ".join(
                f"eq{e:.0f} 성장 {sh[(r, e)]['growth_med']:.2f}x MDD {sh[(r, e)]['mdd_med']*100:.0f}%" for e in EQS), flush=True)
    v = verdict(s)
    print(f"[판정] {v} (DEPLOY_ON_PASS={DEPLOY_ON_PASS})")
    ser = lambda d: {f"{r}|{e}": x for (r, e), x in d.items()}
    json.dump(dict(verdict=v, main=ser(s), holdout=ser(sh) if sh else None), open("_risk_cost.json", "w"), indent=1)
    print("RESULT_JSON: " + json.dumps(dict(verdict=v, main=ser(s)), separators=(",", ":")))


if __name__ == "__main__":
    main()
