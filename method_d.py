"""
method_d.py — 청산 방식 A(고정 ±10%) vs D 비교 백테스트.

방식D 청산:
  손절: 진입가 대비 -STOP_LOSS_PCT(기본 -8%) 무조건(인트라바 저가/고가).
  익절: 먼저 오는 것 - (1) 반대 패턴 신호(롱이면 해당 숏 detector 신호),
        (2) 레짐 전환(진입일 레짐과 달라짐). 둘 다 없으면 MAX_HOLD봉 시가 청산.
  파라미터: STOP_LOSS_PCT=0.08, MAX_HOLD=30.

engulfing/fvg 롱·숏 각각 A/D 비교: n, 평균, 중앙, 베이스라인초과(p), 최대손실, 평균보유봉.
게이트 동결 유지(판정 기준 동일, 청산 방식만 교체).
"""
import json
import importlib
import statistics as st

import detlib
import baseline
import regime_switch as rs

STOP_LOSS_PCT = 0.08
MAX_HOLD = 30
FEE = detlib.FEE

# (라벨, 방향, 패턴detector, 반대detector)
PATS = [
    ("engulfing",       "long",  "detector_engulfing",       "detector_engulfing_short"),
    ("fvg",             "long",  "detector_fvg",             "detector_fvg_short"),
    ("engulfing_short", "short", "detector_engulfing_short", "detector_engulfing"),
    ("fvg_short",       "short", "detector_fvg_short",       "detector_fvg"),
]

REGMAP = rs.build_regime_map()


def outcome_a(rows, si, direction):
    base = rows[si]["c"]; up = base * 1.10; dn = base * 0.90
    hi = min(si + 20, len(rows) - 1)
    for j in range(si + 1, hi + 1):
        c = rows[j]["c"]
        if direction == "long":
            if c >= up: return c / base - 1 - FEE, j - si
            if c <= dn: return c / base - 1 - FEE, j - si
        else:
            if c <= dn: return (base - c) / base - FEE, j - si
            if c >= up: return (base - c) / base - FEE, j - si
    r = rows[hi]["c"] / base - 1
    return (r - FEE if direction == "long" else -r - FEE), hi - si


def outcome_d(rows, si, direction, opp_set):
    base = rows[si]["c"]; entry_reg = REGMAP.get(rows[si]["date"])
    end = min(si + MAX_HOLD, len(rows) - 1)
    for j in range(si + 1, end + 1):
        # 손절(인트라바)
        if direction == "long":
            if rows[j]["l"] <= base * (1 - STOP_LOSS_PCT):
                return -STOP_LOSS_PCT - FEE, j - si
        else:
            if rows[j]["h"] >= base * (1 + STOP_LOSS_PCT):
                return -STOP_LOSS_PCT - FEE, j - si
        # 익절: 반대신호 or 레짐전환(종가)
        regsw = REGMAP.get(rows[j]["date"]) not in (None, entry_reg)
        if j in opp_set or regsw:
            c = rows[j]["c"]
            r = (c - base) / base if direction == "long" else (base - c) / base
            return r - FEE, j - si
    px = rows[end]["o"]
    r = (px - base) / base if direction == "long" else (base - px) / base
    return r - FEE, end - si


def summ(rets, holds):
    if not rets:
        return None
    return dict(n=len(rets), mean=st.mean(rets), median=st.median(rets),
                maxloss=min(rets), avghold=st.mean(holds))


def _calmar(s):
    """mean / |maxloss|. maxloss=0이면 inf(손실 없음)."""
    if s["maxloss"] >= 0:
        return float("inf")
    return s["mean"] / abs(s["maxloss"])


def gate_d(sA, sD, btA, btD):
    """
    방식D 채택 여부 게이트 (기대값+MDD 기반).

    3개 기준:
      1. 기대값 우위: D.mean > A.mean
      2. MDD 우위:   D.maxloss > A.maxloss  (음수끼리; 0에 가까울수록 좋음)
      3. Calmar 우위: calmar(D) > calmar(A)

    채택 조건: D.mean > 0  AND  calmar(D) > 0  AND  우위 항목 ≥ 2/3
    기각 조건: D.mean ≤ 0  OR  calmar(D) ≤ 0  OR  우위 항목 ≤ 1/3
    """
    ca, cd = _calmar(sA), _calmar(sD)
    wins = [
        sD["mean"] > sA["mean"],
        sD["maxloss"] > sA["maxloss"],
        cd > ca,
    ]
    n_wins = sum(wins)

    detail = (f"E[R] D={sD['mean']*100:+.2f}% A={sA['mean']*100:+.2f}%  "
              f"MDD D={sD['maxloss']*100:+.1f}% A={sA['maxloss']*100:+.1f}%  "
              f"Calmar D={cd:.3f} A={ca:.3f}  우위 {n_wins}/3")

    if sD["mean"] <= 0:
        return "reject_d", detail + "  [기각: D 기대값 음수]"
    if cd <= 0:
        return "reject_d", detail + "  [기각: D Calmar 음수]"
    if n_wins >= 2:
        return "adopt_d", detail
    return "keep_a", detail + "  [A 유지: 우위 부족]"


def main():
    out = {}
    print("=" * 100)
    print(f"청산방식 A(±10%/20봉) vs D(손절-{int(STOP_LOSS_PCT*100)}%/반대신호·레짐전환/최대{MAX_HOLD}봉)")
    print("=" * 100)
    hdr = f"  {'패턴':<16}{'방식':<4}{'n':>5}{'평균':>9}{'중앙':>9}{'베이스초과(p)':>16}{'최대손실':>9}{'평균보유':>8}"
    print(hdr); print("  " + "-" * 96)
    for label, direction, detmod, oppmod in PATS:
        mod = importlib.import_module(detmod)
        opp = importlib.import_module(oppmod)
        retsA, holdsA, retsD, holdsD = [], [], [], []
        poolA, poolD = [], []
        for sym in detlib.SYMBOLS:
            try:
                rows = mod.load_ohlcv(sym, "1d")
            except FileNotFoundError:
                continue
            opp_set = set(opp.detect(rows))
            sigs = mod.detect(rows)
            for si in sigs:
                ra, ha = outcome_a(rows, si, direction); retsA.append(ra); holdsA.append(ha)
                rd, hd = outcome_d(rows, si, direction, opp_set); retsD.append(rd); holdsD.append(hd)
            for i in range(len(rows) - 1):       # 베이스라인 풀(전봉)
                poolA.append(outcome_a(rows, i, direction)[0])
                poolD.append(outcome_d(rows, i, direction, opp_set)[0])
        sA, sD = summ(retsA, holdsA), summ(retsD, holdsD)
        btA = baseline.test(poolA, sA["mean"], sA["median"], sA["n"])
        btD = baseline.test(poolD, sD["mean"], sD["median"], sD["n"])
        verdict, detail = gate_d(sA, sD, btA, btD)
        out[label] = dict(
            A=dict(sA, excess=btA["excess_mean"], p=btA["p_mean"],
                   calmar=round(_calmar(sA), 4)),
            D=dict(sD, excess=btD["excess_mean"], p=btD["p_mean"],
                   calmar=round(_calmar(sD), 4)),
            gate=dict(verdict=verdict, detail=detail),
        )
        for tag, s, bt in (("A", sA, btA), ("D", sD, btD)):
            print(f"  {label:<16}{tag:<4}{s['n']:>5}{s['mean']*100:>+8.2f}%{s['median']*100:>+8.2f}%"
                  f"{bt['excess_mean']*100:>+9.2f}%(p{bt['p_mean']:.2f}){s['maxloss']*100:>+8.1f}%{s['avghold']:>7.1f}")
        ICONS = {"adopt_d": "O D 채택", "keep_a": "X A 유지", "reject_d": "X D 기각"}
        print(f"  {'':>18}[게이트] {ICONS[verdict]}  {detail}\n")
    json.dump(out, open("method_d.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2, default=lambda x: round(x, 5))
    print("[저장] method_d.json")


if __name__ == "__main__":
    main()
