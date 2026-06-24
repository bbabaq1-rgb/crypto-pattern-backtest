"""
tf_verify.py — 타임프레임 확장 독립 검증 (B+C).

engulfing/fvg 롱·숏을 12종목에서 1d/4h/1h/15m 각각 독립 검증:
  기대값 게이트(n>=20, 평균>임계, 중앙>0) -> 통과시 OOS(시간분할) + 베이스라인
  부트스트랩(p<0.05) + 레짐 분리. 각 TF는 자기 게이트를 통과해야만 '추가'.
신호 빈도(종목당 월평균)도 함께 산출. 게이트 동결 유지.
"""
import json
import importlib
import statistics as st

import gate
import baseline
import regime_switch as rs

ALL = ["BTC", "SOL", "ETH", "BNB", "XRP", "ADA", "AVAX",
       "LINK", "DOT", "LTC", "ATOM", "UNI"]
TFS = ["1d", "4h", "1h", "15m"]
PATS = ["engulfing", "fvg", "engulfing_short", "fvg_short"]
SPLIT_IS = ("2021-01-01", "2023-12-31")
SPLIT_OOS = ("2024-01-01", "2026-12-31")
MONTHS = 66            # 2021-01 ~ 2026-06 ≈ 66개월
REGMAP = rs.build_regime_map()


def collect(mod, tf, dfrom=None, dto=None):
    rets, dates = [], []
    for sym in ALL:
        try:
            rows = mod.load_ohlcv(sym, tf)
        except FileNotFoundError:
            continue
        for si in mod.detect(rows):
            d = rows[si]["date"]
            if dfrom and d < dfrom:
                continue
            if dto and d > dto:
                continue
            rets.append(mod.outcome(rows, si)[1]); dates.append(d)
    return rets, dates


def pool_of(mod, tf):
    pool = []
    for sym in ALL:
        try:
            rows = mod.load_ohlcv(sym, tf)
        except FileNotFoundError:
            continue
        for i in range(len(rows) - 1):
            pool.append(mod.outcome(rows, i)[1])
    return pool


def gate_of(rets):
    n = len(rets)
    if n == 0:
        return "표본없음", 0, 0.0, 0.0
    m, md = st.mean(rets), st.median(rets)
    v, _ = gate.decide(n, m, md, gate.count_trials())
    return v, n, m, md


def main():
    results = {}
    print("=" * 104)
    print("타임프레임 확장 검증 (12종목, engulfing/fvg 롱·숏, 각 TF 독립 게이트)")
    print("=" * 104)
    print(f"  {'패턴':<18}{'TF':>4}{'n':>6}{'평균':>9}{'중앙':>9}{'게이트':>8}"
          f"{'OOS(IS/OOS)':>16}{'베이스p':>8}{'월/종목':>8}")
    print("  " + "-" * 100)
    import research_log as rl
    for pat in PATS:
        mod = importlib.import_module(f"detector_{pat}")
        for tf in TFS:
            rets, dates = collect(mod, tf)
            verdict, n, m, md = gate_of(rets)
            freq = round(n / len(ALL) / MONTHS, 2)
            rec = dict(n=n, mean=round(m, 5), median=round(md, 5), verdict=verdict,
                       freq_per_sym_month=freq, oos=None, base_p=None, passed=False)
            oos_str, base_str = "-", "-"
            if verdict == "통과":
                ri, _ = collect(mod, tf, *SPLIT_IS)
                ro, _ = collect(mod, tf, *SPLIT_OOS)
                vis = gate_of(ri)[0]; vos = gate_of(ro)[0]
                oos_ok = (vis == "통과" and vos == "통과")
                oos_str = f"{vis[:2]}/{vos[:2]}"
                bt = baseline.test(pool_of(mod, tf), m, md, n)
                base_p = bt["p_mean"] if bt else 1.0
                base_str = f"{base_p:.3f}"
                rec["oos"] = oos_str; rec["base_p"] = base_p
                rec["passed"] = bool(oos_ok and base_p < 0.05)
                rl.append_log(pat, f"TF@{tf}", {"tf": tf}, n, 0.0, m, md,
                              "검증통과" if rec["passed"] else "게이트후탈락")
            else:
                rl.append_log(pat, f"TF@{tf}", {"tf": tf}, n, 0.0, m, md, verdict)
            results[f"{pat}@{tf}"] = rec
            mark = " <== 통과" if rec["passed"] else ""
            print(f"  {pat:<18}{tf:>4}{n:>6}{m*100:>+8.2f}%{md*100:>+8.2f}%{verdict:>8}"
                  f"{oos_str:>16}{base_str:>8}{freq:>8}{mark}")

    json.dump(results, open("tf_verify.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    passed = [k for k, v in results.items() if v["passed"]]
    print("\n" + "=" * 104)
    print("최종 통과 TF:", passed if passed else "없음 (어떤 TF도 독립 게이트+OOS+베이스라인 통과 못함)")
    print("=" * 104)


if __name__ == "__main__":
    main()
