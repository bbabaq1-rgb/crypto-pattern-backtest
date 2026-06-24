"""
alt_verify.py — 신규 알트 검증 + 채택.

(1) 종목별 채택 스크린: 각 신규 종목에서 engulfing/fvg 롱·숏(1d) 신호의
    합산 순기대값이 양수(평균>0) AND 신호 n>=10 이면 채택, 아니면 사유 기록.
    (개별 종목은 패턴 게이트의 n>=20을 못 채우므로, 종목 채택은 순기대값 기준.)
(2) 풀 확인: 채택 종목을 더한 확장 유니버스에서 engulfing/fvg(롱) 1d 패턴이
    여전히 게이트+OOS+베이스라인을 통과하는지(엣지 보존) 확인.
(3) universe.json(트레이딩 유니버스) 갱신 + 패턴별 월 총 신호 수 산출.
게이트 동결 유지.
"""
import json
import importlib
import statistics as st

import detlib
import gate
import baseline
import regime_switch as rs

BASE = list(detlib.SYMBOLS)        # 기존 트레이딩 유니버스(7)
VARIANTS = ["engulfing", "fvg", "engulfing_short", "fvg_short"]
LONGS = ["engulfing", "fvg"]
SPLIT_IS = ("2021-01-01", "2023-12-31")
SPLIT_OOS = ("2024-01-01", "2026-12-31")
MONTHS = 66
MIN_SIG = 10


def sym_rets(sym, variants):
    """한 종목의 패턴 변형 신호 수익 합산."""
    rets = []
    for pat in variants:
        mod = importlib.import_module(f"detector_{pat}")
        try:
            rows = mod.load_ohlcv(sym, "1d")
        except FileNotFoundError:
            return rets
        for si in mod.detect(rows):
            rets.append(mod.outcome(rows, si)[1])
    return rets


def collect(mod, symbols, dfrom=None, dto=None):
    rets = []
    for sym in symbols:
        try:
            rows = mod.load_ohlcv(sym, "1d")
        except FileNotFoundError:
            continue
        for si in mod.detect(rows):
            d = rows[si]["date"]
            if dfrom and d < dfrom: continue
            if dto and d > dto: continue
            rets.append(mod.outcome(rows, si)[1])
    return rets


def gate_v(rets):
    if not rets: return "표본없음"
    return gate.decide(len(rets), st.mean(rets), st.median(rets), gate.count_trials())[0]


def main():
    fetched = json.load(open("alt_fetch.json", encoding="utf-8"))
    ok_syms = [b for b, v in fetched.items() if v["status"] == "ok"]
    short_syms = [b for b, v in fetched.items() if v["status"] == "데이터부족"]
    print(f"신규 시도 {len(fetched)} | 데이터충분 {len(ok_syms)} | 데이터부족 {len(short_syms)}")

    # (1) 종목별 채택 스크린
    adopted, rejected = [], {}
    for sym in ok_syms:
        rets = sym_rets(sym, VARIANTS)
        if len(rets) < MIN_SIG:
            rejected[sym] = f"신호부족(n={len(rets)})"
        elif st.mean(rets) <= 0:
            rejected[sym] = f"순기대값 음수({st.mean(rets)*100:+.2f}%, n={len(rets)})"
        else:
            adopted.append(sym)
    print(f"\n채택 {len(adopted)}: {adopted}")
    print(f"기각 {len(rejected)}: {rejected}")

    # (2) 확장 유니버스 풀 확인
    universe = BASE + adopted
    print(f"\n확장 유니버스({len(universe)}종목) 패턴 보존 확인:")
    pool_conf = {}
    for pat in LONGS:
        mod = importlib.import_module(f"detector_{pat}")
        full = collect(mod, universe)
        v = gate_v(full)
        oos = "-"; bp = None; passed = False
        if v == "통과":
            vis = gate_v(collect(mod, universe, *SPLIT_IS))
            vos = gate_v(collect(mod, universe, *SPLIT_OOS))
            pool = []
            for sym in universe:
                try: rows = mod.load_ohlcv(sym, "1d")
                except FileNotFoundError: continue
                for i in range(len(rows) - 1): pool.append(mod.outcome(rows, i)[1])
            bt = baseline.test(pool, st.mean(full), st.median(full), len(full))
            bp = bt["p_mean"]; oos = f"{vis[:2]}/{vos[:2]}"
            passed = (vis == "통과" and vos == "통과" and bp < 0.05)
        pool_conf[pat] = dict(n=len(full), mean=round(st.mean(full), 5) if full else 0,
                              verdict=v, oos=oos, base_p=bp, passed=passed)
        print(f"  {pat}: n={len(full)} 평균={st.mean(full)*100:+.2f}% {v} OOS={oos} p={bp} -> {'보존' if passed else '주의'}")

    # (3) 패턴별 월 총 신호 수(채택 종목 합산)
    print("\n채택 종목 합산 월 총 신호 수:")
    freq = {}
    for pat in LONGS:
        mod = importlib.import_module(f"detector_{pat}")
        n = len(collect(mod, adopted)) if adopted else 0
        freq[pat] = round(n / MONTHS, 2)
        print(f"  {pat}: 월 {freq[pat]}건 (채택 {len(adopted)}종목 합산)")

    json.dump({"trading_universe": universe, "adopted_new": adopted,
               "rejected": rejected, "data_short": short_syms,
               "pool_confirm": pool_conf, "monthly_signals_adopted": freq,
               "tried": len(fetched)},
              open("universe.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("\n[저장] universe.json")


if __name__ == "__main__":
    main()
