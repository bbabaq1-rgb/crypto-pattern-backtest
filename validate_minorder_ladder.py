"""validate_minorder_ladder.py — R-110: 최소주문 스킵 집합 vs 통과 집합의 방식D 수익 (진단 전용, 2026-11-13).

R-107/R-108: equity $240 에서 신호 약 27% 가 최소주문($10 증거금)에 걸려 스킵된다. 그 스킵 집합의 수익은 미측정이었다.
거래 집합 = validate_iso_skip 과 같은 배포 집합(1d 라우팅 복제 + 4h 4종, 방식D+레짐청산, REGMAP 켬).
각 거래의 진입 시점 σ -> vol_scale -> 필요 equity(validate_minorder.need_equity). 필요 equity > E 면 스킵.
E in {160, 240, 355}, 주 판정 E=240. 사전 등록: registry minorder_ladder_prereg_2026_11_13.
"""
import json
import random
import sys

import validate_minorder as vm
import validate_vol_burst as vb

DEPLOY_ON_PASS = False
EQ_LADDER = (160, 240, 355)
PRIMARY_EQ = 240
SEED = 110
BOOT_N = 2000
P_BOOT = 0.10
MIN_SKIP = 30


def split_skip(trades, eq):
    """(통과, 스킵) 거래 목록. 킬스위치(eq<FLOOR)는 의미 없어 호출하지 않는다."""
    ps, sk = [], []
    for t in trades:
        (ps if vm.need_equity(vm.vscale(t.get("vol"))) <= eq else sk).append(t)
    return ps, sk


def mean(xs):
    return sum(xs) / len(xs) if xs else None


def month_boot_diff(trades_pass, trades_skip, seed=SEED, n=BOOT_N):
    """월 블록 재표집으로 mean(skip)-mean(pass) 분포. 반환 (P(diff<=0), P(diff>=0)). 한쪽이 비면 (None, None)."""
    by = {}
    for t in trades_pass:
        by.setdefault(vb.month_key(t["t_in"]), ([], []))[0].append(t["ret"])
    for t in trades_skip:
        by.setdefault(vb.month_key(t["t_in"]), ([], []))[1].append(t["ret"])
    months = sorted(by)
    if not trades_pass or not trades_skip:
        return None, None
    rng = random.Random(seed)
    le = ge = tot = 0
    for _ in range(n):
        p, s = [], []
        for _ in months:
            a, b = by[rng.choice(months)]
            p += a; s += b
        if not p or not s:
            continue
        d = sum(s) / len(s) - sum(p) / len(p)
        tot += 1; le += d <= 0; ge += d >= 0
    return (le / tot, ge / tot) if tot else (None, None)


def analyse(trades, eq, cut):
    ps, sk = split_skip(trades, eq)
    mp, ms = mean([t["ret"] for t in ps]), mean([t["ret"] for t in sk])
    halves = {}
    for nm, f in (("train", lambda t: t["t_in"] < cut), ("holdout", lambda t: t["t_in"] >= cut)):
        a = [t["ret"] for t in ps if f(t)]; b = [t["ret"] for t in sk if f(t)]
        halves[nm] = dict(n_pass=len(a), n_skip=len(b), mean_pass=mean(a), mean_skip=mean(b),
                          diff=(mean(b) - mean(a)) if a and b else None)
    p_le, p_ge = month_boot_diff(ps, sk)
    return dict(eq=eq, n_pass=len(ps), n_skip=len(sk), skip_share=len(sk) / len(trades) if trades else None,
                mean_pass=mp, mean_skip=ms, diff=(ms - mp) if ms is not None and mp is not None else None,
                p_diff_le0=p_le, p_diff_ge0=p_ge, halves=halves)


def verdict(a):
    """주 판정 셀(E=240) 분석 dict -> 판정.
    SKIP_COSTS_EDGE : diff>0, P(diff<=0)<.10, 전후반 diff 둘 다 >0 (사전 등록 반증 조건 + 부호 일관)
    SKIP_PRESERVES  : diff<=0 이고 P(diff>=0)<.10
    그 밖 INDETERMINATE. 스킵 n<MIN_SKIP 이면 INSUFFICIENT."""
    if a is None or a["n_skip"] < MIN_SKIP or a["diff"] is None:
        return "INSUFFICIENT"
    h = a["halves"]
    both_pos = all(h[k]["diff"] is not None and h[k]["diff"] > 0 for k in ("train", "holdout"))
    if a["diff"] > 0 and a["p_diff_le0"] is not None and a["p_diff_le0"] < P_BOOT and both_pos:
        return "SKIP_COSTS_EDGE"
    if a["diff"] <= 0 and a["p_diff_ge0"] is not None and a["p_diff_ge0"] < P_BOOT:
        return "SKIP_PRESERVES"
    return "INDETERMINATE"


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    import detlib
    import method_t as mt
    import regime_switch as rs
    import validate_portfolio as vp
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
    trades = sorted(vp.collect_1d(syms) + vp.collect_4h(rows_4h, ranked, regmap), key=lambda t: t["t_in"])
    cut = vp.mx._tnum(vp.SPLIT)
    print(f"[표본] 거래 {len(trades)} (σ 없음 {sum(1 for t in trades if not t.get('vol'))})")
    out = {}
    f = lambda x: float("nan") if x is None else x * 100
    for eq in EQ_LADDER:
        a = analyse(trades, eq, cut)
        out[eq] = a
        print(f"E=${eq}: 통과 {a['n_pass']} 평균 {f(a['mean_pass']):+.2f}% | 스킵 {a['n_skip']}({f(a['skip_share']):.1f}%) "
              f"평균 {f(a['mean_skip']):+.2f}% | 차 {f(a['diff']):+.2f}%p P(차<=0)={a['p_diff_le0']} P(차>=0)={a['p_diff_ge0']}")
        for k, h in a["halves"].items():
            print(f"    {k}: 통과 {h['n_pass']} {f(h['mean_pass']):+.2f}% 스킵 {h['n_skip']} {f(h['mean_skip']):+.2f}%")
    by = {}
    for t in trades:
        by.setdefault(t["pattern"], []).append(t)
    diag = {}
    for p, ts in sorted(by.items()):
        ps, sk = split_skip(ts, PRIMARY_EQ)
        diag[p] = dict(n=len(ts), n_skip=len(sk), mean_pass=mean([t["ret"] for t in ps]), mean_skip=mean([t["ret"] for t in sk]))
        print(f"  [진단] {p:<22} n={len(ts):>5} 스킵 {len(sk):>5} 통과평균 {f(diag[p]['mean_pass']):+.2f}% 스킵평균 {f(diag[p]['mean_skip']):+.2f}%")
    v = verdict(out[PRIMARY_EQ])
    print(f"[판정] {v}")
    json.dump(dict(verdict=v, ladder=out, patterns=diag, n=len(trades)), open("_minorder_ladder.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1, default=str)
    print("RESULT_JSON: " + json.dumps(dict(verdict=v, diff240=out[PRIMARY_EQ]["diff"], p_le0=out[PRIMARY_EQ]["p_diff_le0"],
          skip240=out[PRIMARY_EQ]["n_skip"]), separators=(",", ":")))


if __name__ == "__main__":
    main()
