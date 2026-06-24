"""
candle_verify.py — 캔들 패턴 8종 검증(28종목 일봉, 독립 게이트->OOS->베이스라인->레짐).
통과(게이트+OOS 양구간+베이스라인 p<0.05)한 패턴을 universe.json['adopted_patterns']에
추가 -> scheduler/paper_executor 자동 픽업. 게이트 동결 유지.
"""
import json
import importlib
import statistics as st

import detlib
import gate
import baseline
import regime_switch as rs

MODS = ["inverted_hammer", "hammer", "piercing_line", "dark_cloud_cover",
        "morning_star", "evening_star", "marubozu", "marubozu_short"]
DIRN = {"dark_cloud_cover": "short", "evening_star": "short", "marubozu_short": "short"}
SPLIT_IS = ("2021-01-01", "2023-12-31")
SPLIT_OOS = ("2024-01-01", "2026-12-31")
REGS = ["bull_altseason", "bull_btc", "bear", "sideways"]


def universe():
    try:
        u = json.load(open("universe.json", encoding="utf-8")).get("trading_universe")
        return u or list(detlib.SYMBOLS)
    except FileNotFoundError:
        return list(detlib.SYMBOLS)


UNI = universe()
REGMAP = rs.build_regime_map()


def collect(mod, dfrom=None, dto=None):
    rets, dates = [], []
    for sym in UNI:
        try:
            rows = mod.load_ohlcv(sym, "1d")
        except FileNotFoundError:
            continue
        for si in mod.detect(rows):
            d = rows[si]["date"]
            if dfrom and d < dfrom: continue
            if dto and d > dto: continue
            rets.append(mod.outcome(rows, si)[1]); dates.append(d)
    return rets, dates


def gv(rets):
    if not rets: return "표본없음"
    return gate.decide(len(rets), st.mean(rets), st.median(rets), gate.count_trials())[0]


def main():
    import research_log as rl
    results = {}; adopted = []
    print("=" * 92)
    print(f"캔들 패턴 8종 검증 ({len(UNI)}종목 일봉, 독립 게이트+OOS+베이스라인)")
    print("=" * 92)
    print(f"  {'패턴':<18}{'방향':>6}{'n':>7}{'평균':>9}{'중앙':>9}{'게이트':>8}{'OOS':>10}{'베이스p':>8}{'결과':>7}")
    print("  " + "-" * 88)
    for name in MODS:
        mod = importlib.import_module(f"detector_{name}")
        dirn = DIRN.get(name, "long")
        rets, _ = collect(mod)
        v = gv(rets); n = len(rets)
        m = st.mean(rets) if rets else 0; md = st.median(rets) if rets else 0
        oos = "-"; bp = None; passed = False
        if v == "통과":
            vis = gv(collect(mod, *SPLIT_IS)[0]); vos = gv(collect(mod, *SPLIT_OOS)[0])
            pool = []
            for sym in UNI:
                try: rows = mod.load_ohlcv(sym, "1d")
                except FileNotFoundError: continue
                for i in range(len(rows) - 1): pool.append(mod.outcome(rows, i)[1])
            bt = baseline.test(pool, m, md, n); bp = bt["p_mean"]
            oos = f"{vis[:2]}/{vos[:2]}"
            passed = (vis == "통과" and vos == "통과" and bp < 0.05)
        results[name] = dict(direction=dirn, n=n, mean=round(m, 5), median=round(md, 5),
                             verdict=v, oos=oos, base_p=bp, passed=passed)
        rl.append_log(name, "CANDLE@1d", {"dir": dirn}, n, 0.0, m, md,
                      "검증통과" if passed else (v if v != "통과" else "게이트후탈락"))
        if passed:
            adopted.append({"module": f"detector_{name}", "pattern": name, "direction": dirn})
        print(f"  {name:<18}{dirn:>6}{n:>7}{m*100:>+8.2f}%{md*100:>+8.2f}%{v:>8}{oos:>10}"
              f"{(bp if bp is not None else '-'):>8}{'통과' if passed else '기각':>7}")

    # universe.json 갱신
    uni = json.load(open("universe.json", encoding="utf-8"))
    uni["adopted_patterns"] = adopted
    uni["candle_results"] = results
    json.dump(uni, open("universe.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("\n" + "=" * 92)
    print("통과 캔들 패턴:", [a["pattern"] for a in adopted] if adopted else "없음")
    print("=" * 92)


if __name__ == "__main__":
    main()
