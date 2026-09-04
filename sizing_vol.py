"""
sizing_vol.py — 변동성 타겟팅 사이징 시험 (2026-09-04 사전 등록, 사용자 지시 1차 묶음 #1).

배경. 학술 증거가 가장 확실한 항목은 시그널이 아니라 **사이징**이다(Moreira & Muir 2017,
변동성 역가중이 샤프를 개선). 현행 실거래 규칙은 `risk 1% / 손절 8% 고정`이라
명목가 = equity x 1% / 0.08 로 **자산의 변동성과 무관하다.** 저변동 코인과 고변동 밈코인이
같은 크기로 들어간다. 이 모듈이 그 층을 시험한다. 디텍터 변경 없음 — 배포된 전 패턴에 동시 적용.

arm (base = risk, 현행 실거래 규칙)
  vol_raw     : 명목가에 s_i = clip(TARGET_VOL / σ_i, LO, HI) 를 곱한다. σ_i 는 진입 시점의
                20봉 실현변동성(연율). **평균 노출이 커질 수 있어 레버리지 효과가 섞인다.**
  vol_matched : 같은 s_i 를 **인과적 확장평균으로 정규화**(그때까지 본 s 의 평균으로 나눔)해
                평균 노출을 base 와 맞춘다. 레버리지 효과를 제거하고 **재분배 효과만** 남긴다.
                → 이쪽이 **주 판정 arm**이다.

σ_i 계산은 진입 봉까지만 본다(rows[:si+1]) — 룩어헤드 없음. 봉당 로그수익 20개의 표준편차를
TF 에 맞춰 연율화(1d √365 / 1w √52).

사전 등록 판정 (실행 전 고정, 부트스트랩 300회 블록 재표집)
  채택 후보 = **vol_matched** 가 (a) boot Calmar 중앙 > base AND (b) boot MDD 중앙 >= base
              (더 나쁘지 않음) AND (c) P(ruin) <= base. 셋 다 만족해야 한다.
  vol_raw 는 진단 전용 — 좋아 보여도 평균 노출 비율(로그에 출력)이 1 보다 크면 그만큼은
  '변동성 타겟팅'이 아니라 그냥 레버리지다.
실거래 코드 무변경. 출력 sizing_vol.json + RESULT_JSON.
실행: python sizing_vol.py [--no-fetch] [--majors]
"""
import importlib
import json
import math
import random
import statistics as st
import sys
from datetime import date

import detlib
import method_s as ms
import method_t as mt
import sizing as sz
import sizing_study as ss

STOP = ss.STOP
START_EQ, MAX_POS = ss.START_EQ, ss.MAX_POS
RISK_FRAC, LEV = sz.RISK_FRAC, sz.LEV_CAP
BOOT_N, BLOCK, SEED = ss.BOOT_N, ss.BLOCK, ss.SEED
RUIN_LEVEL = ss.RUIN_LEVEL
VOL_LB = 20                      # 실현변동성 lookback(봉)
TARGET_VOL = 0.80                # 연율 80% — 크립토 메이저의 통상 수준(사전 고정, 최적화 금지)
LO, HI = 0.5, 2.0                # 스케일 상하한
BARS_PER_YEAR = {"1d": 365.0, "4h": 365.0 * 6, "1h": 365.0 * 24, "1w": 52.0}
ARMS = ["risk", "vol_raw", "vol_matched"]


def realized_vol(rows, si, lb=VOL_LB, tf="1d"):
    """진입 봉까지만 보고 계산한 연율 실현변동성. 표본 부족·0 이면 None."""
    if si < lb:
        return None
    rets = []
    for j in range(si - lb + 1, si + 1):
        p0, p1 = rows[j - 1]["c"], rows[j]["c"]
        if p0 <= 0 or p1 <= 0:
            return None
        rets.append(math.log(p1 / p0))
    if len(rets) < 2:
        return None
    sd = st.pstdev(rets)
    if sd <= 0:
        return None
    return sd * math.sqrt(BARS_PER_YEAR.get(tf, 365.0))


def collect_all(syms):
    """[(entry_date, exit_date, ret, hold, pattern, sym, vol)] 시간순. vol=None 이면 스케일 1."""
    out = []
    for label, direction, detmod, oppmod, tf in mt.PATS:
        mod = importlib.import_module(detmod)
        opp = importlib.import_module(oppmod) if oppmod else None
        n = 0
        for sym in syms:
            try:
                rows = detlib.load_ohlcv(sym, tf)
            except (FileNotFoundError, RuntimeError):
                continue
            if len(rows) < 40:
                continue
            opp_set = set(opp.detect(rows)) if opp else set()
            for si in mod.detect(rows):
                if si + 1 >= len(rows):
                    continue
                ret, hold, _ = mt.outcome_d(rows, si, direction, opp_set)
                xi = min(si + hold, len(rows) - 1)
                out.append((rows[si]["date"], rows[xi]["date"], ret, hold, label, sym,
                            realized_vol(rows, si, tf=tf)))
                n += 1
        print(f"  [{label}] {n}건", flush=True)
    out.sort(key=lambda t: (t[0], t[4], t[5]))
    return out


def scale_of(vol):
    """s = clip(TARGET/σ, LO, HI). σ 없으면 1.0(중립)."""
    if vol is None or vol <= 0:
        return 1.0
    return max(LO, min(HI, TARGET_VOL / vol))


def simulate(trades, arm):
    """시간순 포트폴리오 시뮬. sizing_study.simulate 와 같은 회계, risk_frac 만 arm 별로 스케일."""
    evs = []
    for i, t in enumerate(trades):
        evs.append((ss._dnum(t[0]), 0, i))
        evs.append((ss._dnum(t[1]), -1, i))
    evs.sort()
    equity = free = START_EQ
    open_pos, peak, mdd = {}, START_EQ, 0.0
    taken = skipped = 0
    s_sum, s_cnt = 0.0, 0            # 인과적 확장평균(정규화용) — 지금까지 본 s 만 쓴다
    scales, notionals = [], []
    for day, kind, idx in evs:
        if kind == -1:
            rec = open_pos.pop(idx, None)
            if rec is None:
                continue
            margin, notional = rec
            pnl = notional * trades[idx][2]
            equity += pnl
            free += margin + pnl
            if equity <= 0:
                equity = 0.0
                break
            peak = max(peak, equity)
            mdd = min(mdd, equity / peak - 1)
        else:
            s_raw = scale_of(trades[idx][6])
            if arm == "risk":
                s = 1.0
            elif arm == "vol_raw":
                s = s_raw
            else:                                    # vol_matched
                mean_prev = (s_sum / s_cnt) if s_cnt else 1.0
                s = s_raw / mean_prev if mean_prev > 0 else s_raw
            s_sum += s_raw; s_cnt += 1               # 정규화 통계는 arm 무관하게 같은 열을 쓴다
            if len(open_pos) >= MAX_POS:
                skipped += 1; continue
            open_notional = sum(n for _, n in open_pos.values())
            r = sz.risk_based_size(equity, free, STOP, risk_frac=RISK_FRAC * s,
                                   lev_cap=LEV, open_notional=open_notional)
            if r is None:
                skipped += 1; continue
            free -= r["margin_usd"]
            open_pos[idx] = (r["margin_usd"], r["notional"])
            scales.append(s); notionals.append(r["notional"])
            taken += 1
    days = max(1, evs[-1][0] - evs[0][0]) if evs else 1
    yrs = days / 365.25
    cagr = (equity / START_EQ) ** (1 / yrs) - 1 if equity > 0 else -1.0
    return dict(final=equity, cagr=cagr, mdd=mdd,
                calmar=(cagr / abs(mdd) if mdd < 0 else float("inf")),
                taken=taken, skipped=skipped,
                mean_scale=(st.mean(scales) if scales else 0.0),
                mean_notional=(st.mean(notionals) if notionals else 0.0))


def block_bootstrap(trades, rng, block=BLOCK):
    """날짜 골격은 원본 유지, (수익·보유·패턴·심볼·변동성)을 블록 단위로 재표집."""
    n = len(trades)
    idx = []
    while len(idx) < n:
        s = rng.randrange(0, n)
        idx.extend(range(s, min(n, s + block)))
    idx = idx[:n]
    return [(trades[k][0], trades[k][1]) + tuple(trades[j][2:]) for k, j in enumerate(idx)]


def evaluate(trades, arm):
    base = simulate(trades, arm)
    rng = random.Random(SEED)
    mdds, calmars, cagrs, ruins = [], [], [], 0
    for _ in range(BOOT_N):
        s = simulate(block_bootstrap(trades, rng), arm)
        mdds.append(s["mdd"]); calmars.append(min(s["calmar"], 50.0)); cagrs.append(s["cagr"])
        if s["final"] < START_EQ * RUIN_LEVEL:
            ruins += 1
    mdds.sort(); calmars.sort(); cagrs.sort()
    m = len(mdds) // 2
    return dict(base=base, boot=dict(mdd_med=mdds[m], mdd_p10=mdds[int(len(mdds) * 0.1)],
                                     calmar_med=calmars[m], cagr_med=cagrs[m],
                                     p_ruin=ruins / BOOT_N))


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    ms.UNIVERSE_MODE = "--majors" not in argv
    syms = ms.symbols()
    print(f"[표본] {len(syms)}종목 ({'유니버스 80' if ms.UNIVERSE_MODE else '메이저'})")
    if "--no-fetch" not in argv:
        ms.ensure_data(ms.FETCH_DAYS, syms)
    trades = collect_all(syms)
    if not trades:
        print("거래 없음"); return
    vols = [t[6] for t in trades if t[6]]
    print(f"[거래] {len(trades)}건 | 변동성 산출 {len(vols)}건 "
          f"(중앙 연율 {st.median(vols)*100:.0f}%, 10~90분위 "
          f"{sorted(vols)[len(vols)//10]*100:.0f}~{sorted(vols)[len(vols)*9//10]*100:.0f}%)")
    print(f"[설정] TARGET_VOL={TARGET_VOL*100:.0f}% clip[{LO},{HI}] risk={RISK_FRAC*100:.1f}% lev<={LEV} "
          f"boot={BOOT_N} block={BLOCK}")
    print("=" * 118)
    print("변동성 타겟팅 사이징 — risk(현행) vs vol_raw(스케일 그대로) vs vol_matched(평균 노출 정합)")
    print("=" * 118)
    print(f"  {'arm':<13}{'진입':>6}{'스킵':>6}{'평균s':>7}{'평균명목':>10}{'CAGR':>9}{'MDD':>9}{'Calmar':>8}"
          f" | {'bootCAGR':>9}{'bootMDD':>9}{'bootCal':>8}{'P(ruin)':>9}")
    res = {}
    for arm in ARMS:
        r = evaluate(trades, arm)
        res[arm] = r
        b, t = r["base"], r["boot"]
        print(f"  {arm:<13}{b['taken']:>6}{b['skipped']:>6}{b['mean_scale']:>7.2f}"
              f"{b['mean_notional']:>10.0f}{b['cagr']*100:>+8.1f}%{b['mdd']*100:>+8.1f}%{b['calmar']:>8.2f}"
              f" | {t['cagr_med']*100:>+8.1f}%{t['mdd_med']*100:>+8.1f}%{t['calmar_med']:>8.2f}{t['p_ruin']*100:>8.1f}%")
    base_b, mat_b = res["risk"]["boot"], res["vol_matched"]["boot"]
    raw_b = res["vol_raw"]["boot"]
    expo = (res["vol_matched"]["base"]["mean_notional"] / res["risk"]["base"]["mean_notional"]
            if res["risk"]["base"]["mean_notional"] else 0.0)
    expo_raw = (res["vol_raw"]["base"]["mean_notional"] / res["risk"]["base"]["mean_notional"]
                if res["risk"]["base"]["mean_notional"] else 0.0)
    c_a = mat_b["calmar_med"] > base_b["calmar_med"]
    c_b = mat_b["mdd_med"] >= base_b["mdd_med"]
    c_c = mat_b["p_ruin"] <= base_b["p_ruin"]
    adopt = bool(c_a and c_b and c_c)
    print(f"\n[노출 비율] vol_matched/risk = {expo:.2f}배 (1.0 근처여야 정규화가 작동) | "
          f"vol_raw/risk = {expo_raw:.2f}배")
    print("\n[사전 등록 판정] 주 arm = vol_matched")
    print(f"  (a) boot Calmar 개선  {mat_b['calmar_med']:.2f} vs {base_b['calmar_med']:.2f}  -> {'통과' if c_a else '탈락'}")
    print(f"  (b) boot MDD 악화 없음 {mat_b['mdd_med']*100:+.1f}% vs {base_b['mdd_med']*100:+.1f}%  -> {'통과' if c_b else '탈락'}")
    print(f"  (c) P(ruin) 악화 없음  {mat_b['p_ruin']*100:.1f}% vs {base_b['p_ruin']*100:.1f}%  -> {'통과' if c_c else '탈락'}")
    print(f"  => {'ADOPT 후보 (사용자 결정)' if adopt else 'REJECT'}")
    print(f"\n[진단] vol_raw 는 노출 {expo_raw:.2f}배 — 1 을 넘는 만큼은 변동성 타겟팅이 아니라 레버리지다.")
    json.dump(dict(config=dict(target_vol=TARGET_VOL, lo=LO, hi=HI, vol_lb=VOL_LB,
                               risk_frac=RISK_FRAC, lev=LEV, boot_n=BOOT_N, block=BLOCK,
                               n_symbols=len(syms), n_trades=len(trades)),
                   results=res, exposure=dict(matched=expo, raw=expo_raw),
                   verdict=dict(adopt=adopt, c_a_calmar=c_a, c_b_mdd=c_b, c_c_ruin=c_c)),
              open("sizing_vol.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\nRESULT_JSON: " + json.dumps(dict(
        adopt=adopt, exposure_matched=round(expo, 3),
        calmar={a: round(res[a]["boot"]["calmar_med"], 3) for a in ARMS},
        mdd={a: round(res[a]["boot"]["mdd_med"], 4) for a in ARMS}), separators=(",", ":")))


if __name__ == "__main__":
    main()
