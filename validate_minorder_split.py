"""validate_minorder_split.py — R-124: 최소주문 스킵만 분리 (진단 전용, 2026-11-20).

R-122 의 스킵 비율(70~78%)은 슬롯·증거금·최소주문 합산이라 '재개 equity 240 이 최소주문 때문에 막히는가'에 답하지 못했다.
R-122 프레임 그대로(T7 창 52개 1년 부트 500회, 시드 124, 킬스위치 $100) vg.simulate(skips=) 훅으로 스킵 원인을 분리한다.
주 지표 = 최소주문 스킵 / 사이징 단계 도달 신호(킬스위치·슬롯 스킵 제외). 사전 등록: registry minorder_split_prereg_2026_11_20.
DEPLOY_ON_PASS=False — 위험 수준·충전은 사용자 결정.
"""
import json
import random
import statistics as st
import sys

import validate_gap as vg
import validate_killswitch as ks
import validate_portfolio as vp

DEPLOY_ON_PASS = False
RISKS = (0.010, 0.015)
EQS = (240.0, 355.0, 500.0, 750.0)
SEED = 124
BOOT_N = 500
HI = 0.20        # risk 1.0% eq240 최소주문 비율 하한(가설: 이상)
LO = 0.10        # risk 1.0% eq355 최소주문 비율 상한(가설: 미만)
CAUSES = ("kill", "slot", "minorder", "total_cap", "free")


def run_cell(path, eq0, risk, floor=ks.FLOOR):
    old = vp.START_EQ
    vp.START_EQ = eq0
    sk = {}
    try:
        r = vg.simulate(path, floor=floor, risk=risk, skips=sk)
    finally:
        vp.START_EQ = old
    c = {k: sk.get(k, 0) for k in CAUSES}
    reach = r["taken"] + c["minorder"] + c["total_cap"] + c["free"]      # 사이징 단계 도달
    total = r["taken"] + r["skipped"]
    return dict(taken=r["taken"], total=total, reach=reach, **c,
                mo_reach=(c["minorder"] / reach if reach else 0.0),
                mo_all=(c["minorder"] / total if total else 0.0))


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
        out[k] = {m: st.median(x[m] for x in rows) for m in ("mo_reach", "mo_all", "taken", "reach", "total") + CAUSES}
    return out


def verdict(s):
    """CONFIRMED: risk 1.0% 에서 eq240 mo_reach 중앙 >= HI AND eq355 mo_reach 중앙 < LO.
    MINORDER_NOT_BINDING: eq240 mo_reach < HI (재개 equity 240 이 최소주문에 막히지 않는다).
    THRESHOLD_HIGHER: eq240 >= HI 이나 eq355 >= LO (최소주문 영향이 355 까지 이어진다)."""
    a = s[(0.010, 240.0)]["mo_reach"]
    b = s[(0.010, 355.0)]["mo_reach"]
    if a < HI:
        return "MINORDER_NOT_BINDING"
    return "CONFIRMED" if b < LO else "THRESHOLD_HIGHER"


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

    def show(tag, d):
        for r in RISKS:
            for e in EQS:
                c = d[(r, e)]
                print(f"[{tag}] risk {r*100:.1f}% eq{e:.0f} 신호 {c['total']:.0f} 체결 {c['taken']:.0f} 킬 {c['kill']:.0f} 슬롯 {c['slot']:.0f} "
                      f"최소주문 {c['minorder']:.0f} 노출상한 {c['total_cap']:.0f} 증거금 {c['free']:.0f} | "
                      f"최소주문/도달 {c['mo_reach']*100:5.1f}% 최소주문/전체 {c['mo_all']*100:5.1f}%", flush=True)
    show("전체 풀", s)
    sh = None
    if len(ks.windows_of(ho)) >= 8:
        sh = summarize(boot(ho, seed=SEED + 1))
        show("holdout 풀 진단", sh)
    v = verdict(s)
    print(f"[판정] {v} (DEPLOY_ON_PASS={DEPLOY_ON_PASS})")
    ser = lambda d: {f"{r}|{e}": x for (r, e), x in d.items()}
    json.dump(dict(verdict=v, main=ser(s), holdout=ser(sh) if sh else None), open("_minorder_split.json", "w"), indent=1)
    print("RESULT_JSON: " + json.dumps(dict(verdict=v, main=ser(s)), separators=(",", ":")))


if __name__ == "__main__":
    main()
