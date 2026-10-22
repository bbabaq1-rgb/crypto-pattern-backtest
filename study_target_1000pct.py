#!/usr/bin/env python3
"""
월 +1,000%(30일 안에 자본 10배) 목표의 실현가능성 시험 — 기록용 (2026-09-06, 사용자 지시).

배포 판정 아님. 실거래 코드·파라미터 무변경. 외부 데이터 불필요(러너 전용 data/ 없이 돈다).

무엇을 재나
  이 레포가 5년치 검증에서 실측한 거래 분포(승률·손절폭·건당 평균·월 거래 수)를 그대로 두고,
  '건당 위험 비율(RISK_FRAC)' 만 현행 1.5% 에서 100%(올인)까지 올렸을 때
    (a) 30일 안에 10배에 닿을 확률
    (b) 킬스위치($100)·−90% 파산 확률
    (c) 중앙값 결과
  를 몬테카를로로 잰다. 그 다음 거꾸로, 10배가 '중앙값' 이 되려면 건당 엣지가 얼마여야 하는지 푼다.

왜 이렇게 재나
  월 10배 = 30일 로그수익 ln(10) = 2.303. 현행(risk 1.5%/lev 3) boot CAGR +63% 는 월 로그수익 0.041.
  필요한 성장률이 실측의 56배다. 성장률은 위험 비율에 대해 켈리 이하에서만 대략 선형으로 오르고
  켈리를 넘으면 떨어진다 — 그러므로 '위험을 키우면 되는가' 는 켈리 최적점에서의 성장률 하나로 답이 난다.

분포 가정(레포 실측, CLAUDE.md / report_leverage_2026_09.md / report_take_profit.md)
  · 손절 −8%(방식D) = 위험액 전부 손실 = −1R
  · 승률 44%(engulfing D 44%, vol_awakening 44%, triple_bottom_4h 48%, 1d 후보 38~41%)
  · 건당 평균 +3.0% (engulfing +4.64%, fvg +2.4%, 4h 신규 +1.0~1.8% 의 라우팅 가중 근사)
      → R 단위 평균 +0.375R, 승자 평균 = (0.375 + 0.56) / 0.44 = 2.125R (지수분포, 오른쪽 꼬리 보존)
  · 월 30건 (라우팅 복제 991건 / 약 2.5년 ≈ 33건/월), 순차 복리(동시 포지션 상관은 무시 = 낙관)
  · 수수료·슬리피지 0 (낙관), 레버리지 청산·최소주문 제약 0 (낙관)
  즉 모든 단순화가 목표에 유리한 쪽이다. 여기서도 안 되면 실제로는 더 안 된다.
"""
import math
import random
import json

WIN_RATE = 0.44
MEAN_R = 0.375           # 건당 평균 +3.0% / 손절 8%
WIN_MEAN_R = (MEAN_R + (1 - WIN_RATE)) / WIN_RATE   # 2.125R
TRADES_PER_MONTH = 30
START_EQUITY = 400.0
KILL = 100.0             # paper_executor.EQUITY_FLOOR
TARGET = 10.0            # +1,000%
N_SIM = 20000
FRACS = [0.005, 0.015, 0.03, 0.05, 0.10, 0.20, 0.30, 0.50, 0.75, 1.00]


def draw_r(rng):
    if rng.random() < WIN_RATE:
        return rng.expovariate(1.0 / WIN_MEAN_R)
    return -1.0


def simulate(frac, rng, n_sim=N_SIM):
    hit = ruin = kill = 0
    finals = []
    for _ in range(n_sim):
        eq = START_EQUITY
        peak_hit = False
        for _ in range(TRADES_PER_MONTH):
            eq *= 1.0 + frac * draw_r(rng)
            if eq >= START_EQUITY * TARGET:
                peak_hit = True
            if eq <= 0:
                eq = 0.0
                break
        finals.append(eq / START_EQUITY)
        hit += peak_hit
        ruin += finals[-1] <= 0.10
        kill += eq < KILL
    finals.sort()
    return dict(frac=frac, p_hit_10x=hit / n_sim, p_ruin_90=ruin / n_sim, p_kill=kill / n_sim,
                median=finals[n_sim // 2], p10=finals[n_sim // 10], p90=finals[9 * n_sim // 10],
                mean=sum(finals) / n_sim)


def growth_per_trade(frac, rng, n=200000):
    """E[ln(1+f R)] — 켈리 목적함수. f=1 이면 손절 한 번에 −100% 라 −inf."""
    s = 0.0
    for _ in range(n):
        v = 1.0 + frac * draw_r(rng)
        if v <= 0:
            return float("-inf")
        s += math.log(v)
    return s / n


def kelly(rng):
    best = (0.0, 0.0)
    for f in [i / 100 for i in range(1, 100)]:
        g = growth_per_trade(f, rng, 40000)
        if g > best[1]:
            best = (f, g)
    return best


def required_edge(rng):
    """월 10배가 '중앙값' 이 되려면(순차 30건, 켈리 최적) 승률·승자평균이 얼마여야 하나."""
    need = math.log(TARGET) / TRADES_PER_MONTH      # 건당 로그성장 0.0768
    out = []
    for wr in [0.44, 0.55, 0.65, 0.75, 0.85]:
        for win_mean in [1.0, 2.125, 3.0, 5.0, 10.0]:
            # 이 분포에서 켈리 최적 성장률
            best = 0.0
            for f in [i / 50 for i in range(1, 50)]:
                s = 0.0
                ok = True
                for _ in range(8000):
                    r = rng.expovariate(1.0 / win_mean) if rng.random() < wr else -1.0
                    v = 1 + f * r
                    if v <= 0:
                        ok = False
                        break
                    s += math.log(v)
                if ok:
                    best = max(best, s / 8000)
            out.append(dict(win_rate=wr, win_mean_R=win_mean, kelly_growth=best, enough=best >= need))
    return need, out


def main():
    rng = random.Random(20260906)
    print(f"가정: 승률 {WIN_RATE:.0%} / 손절 −1R(−8%) / 승자평균 {WIN_MEAN_R:.3f}R / 건당평균 {MEAN_R:+.3f}R(+3.0%) "
          f"/ 월 {TRADES_PER_MONTH}건 / 시작 ${START_EQUITY:.0f} / 목표 {TARGET:.0f}배 / 시뮬 {N_SIM:,}회\n")
    print(f"{'risk':>6} | {'P(10x)':>7} | {'P(-90%)':>8} | {'P(<$100)':>8} | {'중앙값':>7} | {'p10':>6} | {'p90':>6} | {'평균':>6}")
    rows = []
    for f in FRACS:
        r = simulate(f, rng)
        rows.append(r)
        print(f"{f:>6.1%} | {r['p_hit_10x']:>7.2%} | {r['p_ruin_90']:>8.2%} | {r['p_kill']:>8.2%} | "
              f"{r['median']:>6.2f}x | {r['p10']:>5.2f}x | {r['p90']:>5.2f}x | {r['mean']:>5.2f}x")

    kf, kg = kelly(rng)
    monthly = math.exp(kg * TRADES_PER_MONTH)
    print(f"\n켈리 최적 위험 비율 f* = {kf:.0%} → 건당 로그성장 {kg:.4f} → 월 기대 {monthly:.2f}배 "
          f"(연 {monthly**12:.1f}배, 이론 상한 — 상관·수수료·청산 0 가정)")
    print(f"월 10배에 필요한 건당 로그성장 = ln(10)/{TRADES_PER_MONTH} = {math.log(TARGET)/TRADES_PER_MONTH:.4f} "
          f"= 켈리 상한의 {math.log(TARGET)/TRADES_PER_MONTH/kg:.0f}배")

    need, tbl = required_edge(rng)
    print(f"\n역산: 월 10배가 중앙값이 되는 분포 (켈리 최적 성장 ≥ {need:.4f}/건 인 셀만 ●)")
    wrs = sorted({t['win_rate'] for t in tbl})
    wms = sorted({t['win_mean_R'] for t in tbl})
    print("승률\\승자평균 " + " ".join(f"{w:>6.2f}R" for w in wms))
    for wr in wrs:
        line = f"{wr:>10.0%}   "
        for wm in wms:
            t = next(x for x in tbl if x['win_rate'] == wr and x['win_mean_R'] == wm)
            line += f"{'●' if t['enough'] else '·'}{t['kelly_growth']:>6.3f} "
        print(line)
    json.dump(dict(assumptions=dict(win_rate=WIN_RATE, mean_R=MEAN_R, win_mean_R=WIN_MEAN_R,
                                    trades_per_month=TRADES_PER_MONTH, start=START_EQUITY, target=TARGET),
                   grid=rows, kelly=dict(frac=kf, growth=kg, monthly_x=monthly),
                   required=dict(need_per_trade=need, table=tbl)),
              open("study_target_1000pct.json", "w"), indent=1, ensure_ascii=False)
    print("\n→ study_target_1000pct.json")


if __name__ == "__main__":
    main()
