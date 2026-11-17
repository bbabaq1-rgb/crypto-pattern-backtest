"""validate_killswitch.py — R-118: 재개 equity 별 킬스위치($100) 도달 확률 (진단 전용, 2026-11-17).

배포 거래열을 진입 7일 창(T7) 52개(=1년)로 복원추출해 이어 붙이고, 시작 equity {160,240,355,500} 에서
validate_gap.simulate(floor=100) 으로 굴려 자산곡선이 $100 아래로 내려가 신규 진입이 멈추는 확률을 잰다.
사전 등록: registry killswitch_prereg_2026_11_17. DEPLOY_ON_PASS=False — 재개·충전·위험 수준은 사용자 결정.
"""
import json
import random
import statistics as st
import sys

import validate_gap as vg
import validate_portfolio as vp

DEPLOY_ON_PASS = False
EQ_LADDER = (160.0, 240.0, 355.0, 500.0)
FLOOR = 100.0
WINDOWS = 52
T7_DAYS = 7.0
SEED = 118
BOOT_N = 500
SAFE_P = 0.05
HI_P = 0.10
LO_P = 0.01
MONO_TOL = 0.02


def windows_of(trades):
    wins = {}
    for t in trades:
        wins.setdefault(int(t["t_in"] // T7_DAYS), []).append(t)
    return [wins[k] for k in sorted(wins)]


def one_year_path(wins, rng, n_windows=WINDOWS):
    """창 n_windows 개를 복원추출해 k*7일 간격으로 배치(창 안 상대 시각·보유 유지). t_in 오름차순."""
    out = []
    for k in range(n_windows):
        w = wins[rng.randrange(0, len(wins))]
        base = int(w[0]["t_in"] // T7_DAYS) * T7_DAYS
        off = k * T7_DAYS
        for t in w:
            d_in = t["t_in"] - base
            hold = max(t["t_out"] - t["t_in"], 0.0)
            out.append(dict(t, t_in=off + d_in, t_out=off + d_in + hold))
    out.sort(key=lambda t: t["t_in"])
    return out


def run_path(trades, eq0, floor=FLOOR):
    """시작 equity eq0 로 1년 경로 시뮬. 반환 dict(reached, t_reach, ruin, final, taken)."""
    old = vp.START_EQ
    vp.START_EQ = eq0
    try:
        path = []
        r = vg.simulate(trades, path=path, floor=floor)
    finally:
        vp.START_EQ = old
    t_reach = next((t for t, e in path if e < floor), None)
    return dict(reached=t_reach is not None, t_reach=t_reach, ruin=r["final"] <= 0.0,
                final=r["final"], taken=r["taken"])


def verdict(p_by_eq):
    """p_by_eq: {equity: P(reach)} (오름차순 equity)."""
    ps = [p_by_eq[e] for e in sorted(p_by_eq)]
    if all(p >= HI_P for p in ps) or all(p < LO_P for p in ps):
        return "EQUITY_INSENSITIVE"
    mono = all(ps[i + 1] <= ps[i] + MONO_TOL for i in range(len(ps) - 1))
    safe = [e for e in sorted(p_by_eq) if p_by_eq[e] < SAFE_P]
    if safe and mono:
        return "THRESHOLD_EXISTS"
    return "NO_SAFE_LEVEL"


def boot(pool, seed=SEED, n=BOOT_N):
    wins = windows_of(pool)
    rng = random.Random(seed)
    res = {e: [] for e in EQ_LADDER}
    for _ in range(n):
        path = one_year_path(wins, rng)
        for e in EQ_LADDER:           # 같은 재표집을 모든 equity 에 적용(짝지음)
            res[e].append(run_path(path, e))
    return res


def summarize(res):
    out = {}
    for e, lst in res.items():
        tr = [x["t_reach"] for x in lst if x["reached"]]
        out[e] = dict(p_reach=sum(x["reached"] for x in lst) / len(lst),
                      p_ruin=sum(x["ruin"] for x in lst) / len(lst),
                      t_reach_med=(st.median(tr) if tr else None),
                      final_med=st.median(x["final"] for x in lst),
                      taken_med=st.median(x["taken"] for x in lst))
    return out


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
    print(f"총 거래 {len(base)} (holdout {len(ho)}), 7일 창 {len(windows_of(base))}개", flush=True)
    main_s = summarize(boot(base))
    for e in EQ_LADDER:
        s = main_s[e]
        print(f"[전체 풀] eq {e:5.0f}  P(킬스위치 도달) {s['p_reach']*100:5.1f}%  파산 {s['p_ruin']*100:4.1f}%  "
              f"도달일 중앙 {s['t_reach_med']}  1년후 equity 중앙 {s['final_med']:.0f}  체결 중앙 {s['taken_med']}", flush=True)
    ho_s = summarize(boot(ho, seed=SEED + 1)) if len(windows_of(ho)) >= 8 else None
    if ho_s:
        for e in EQ_LADDER:
            s = ho_s[e]
            print(f"[holdout 풀 진단] eq {e:5.0f}  P(도달) {s['p_reach']*100:5.1f}%  파산 {s['p_ruin']*100:4.1f}%", flush=True)
    v = verdict({e: main_s[e]["p_reach"] for e in EQ_LADDER})
    print(f"[판정] {v} (DEPLOY_ON_PASS={DEPLOY_ON_PASS})")
    json.dump(dict(verdict=v, main={str(k): x for k, x in main_s.items()},
                   holdout={str(k): x for k, x in (ho_s or {}).items()}),
              open("_killswitch.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print("RESULT_JSON: " + json.dumps(dict(verdict=v, p={str(e): main_s[e]["p_reach"] for e in EQ_LADDER}), separators=(",", ":")))


if __name__ == "__main__":
    main()
