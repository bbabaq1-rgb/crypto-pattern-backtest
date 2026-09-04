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
              (더 나쁘지 않음) AND (c) P(ruin) <= base AND (d) 노출 비율 0.8~1.2.
              (d) 는 vol_matched 의 정의('평균 노출 정합')가 실제로 성립했는지 확인하는 가드다 —
              깨지면 (a)(b)(c) 개선이 재분배가 아니라 레버리지 효과일 수 있어 판정이 성립하지 않는다.
              노출은 **진입 시점 레버리지(명목가/equity)** 로 잰다. 달러 명목가로 재면 성과가 좋은
              arm 이 자본을 키워 명목가도 커져 '레버리지'와 '수익'이 뒤섞인다.
  vol_raw 는 진단 전용 — 좋아 보여도 평균 노출 비율(로그에 출력)이 1 보다 크면 그만큼은
  '변동성 타겟팅'이 아니라 그냥 레버리지다.
실거래 코드 무변경. 출력 sizing_vol.json + RESULT_JSON.
실행: python sizing_vol.py [--no-fetch] [--majors] [--routing]
  기본은 전 패턴 x 전 종목(표본 최대화 = 강건성 표본). --routing 은 **실거래 라우팅을 복제**해
  실제로 주문이 나갔을 집합만 남긴다 — 패턴별 유니버스(engulfing·fvg=top30, ih·marubozu=메이저)
  + 레짐->방향 라우팅(FOCUS 한정) + 정지 패턴 제외. 표본은 줄지만 **실주문 기준 판정**이다.
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
# 파라미터·함수는 **sizing.py 가 원본**이다(2026-09-04 채택 이후). 연구와 실거래가 같은
# 코드를 쓰지 않으면 검증한 규칙과 실제 주문이 조용히 갈라진다.
VOL_LB, TARGET_VOL = sz.VOL_LB, sz.VOL_TARGET_VOL
LO, HI = sz.VOL_LO, sz.VOL_HI
BARS_PER_YEAR = sz.VOL_BARS_PER_YEAR
ARMS = ["risk", "vol_raw", "vol_matched"]

# --routing: 실거래 라우팅 복제. 기본(전 패턴 x 80종목)은 '표본을 최대로 키운' 강건성 표본이고
# 실제 주문 집합이 아니다. 복제 모드는 scheduler 의 실제 진입 조건 세 겹을 그대로 건다.
#   (1) 패턴별 유니버스 — scheduler._syms_for_pattern (engulfing·fvg=top30, ih·marubozu=메이저)
#   (2) 레짐->방향 라우팅 — direction_switch.json routing (FOCUS 인 engulfing/fvg 에만 적용.
#       ROUTING_OVERRIDES 의 bear fvg FLAT 이 이 표에 이미 반영돼 있다)
#   (3) 정지 패턴 제외 — universe.json suspended_patterns (triple_bottom 1w)
# adopted_patterns(inverted_hammer / marubozu)는 스케줄러에서 레짐 게이트 없이 롱으로 진입한다.
ROUTING_MODE = False
FOCUS_PATTERNS = ("engulfing", "fvg")


def _base_pattern(label):
    return label[:-6] if label.endswith("_short") else label


def routing_ctx():
    """(syms_for_pattern, routing, regmap, suspended) — 실거래 진입 조건 재현용."""
    import scheduler as sch
    import regime_switch as rs
    routing = json.load(open("direction_switch.json", encoding="utf-8"))["routing"]
    uni = json.load(open("universe.json", encoding="utf-8"))
    suspended = {e["pattern"] for e in uni.get("suspended_patterns", [])}
    suspended |= {e["pattern"] for e in uni.get("suspended_1h_patterns", [])}
    return sch._syms_for_pattern, routing, rs.build_regime_map(), suspended


def routed_in(label, direction, date, routing, regmap):
    """그 날짜에 이 (패턴, 방향)이 실제로 나갔을 조건인가."""
    base = _base_pattern(label)
    if base not in FOCUS_PATTERNS:
        return True                      # adopted_patterns 는 레짐 게이트 없음
    g = regmap.get(date)
    if not g:
        return False                     # 레짐 미판정 구간은 스케줄러도 라우팅을 못 만든다
    return routing.get(g, {}).get(base) == direction


realized_vol = sz.realized_vol      # 진입 봉까지만 보는 연율 실현변동성(인과적)


def collect_all(syms):
    """[(entry_date, exit_date, ret, hold, pattern, sym, vol)] 시간순. vol=None 이면 스케일 1."""
    out = []
    syms_for, routing, regmap, suspended = (routing_ctx() if ROUTING_MODE
                                            else (None, None, None, set()))
    for label, direction, detmod, oppmod, tf in mt.PATS:
        if ROUTING_MODE and label in suspended:
            print(f"  [{label}] 정지 패턴 — 제외", flush=True)
            continue
        pat_syms = syms
        if ROUTING_MODE:
            pat_syms = [s for s in syms_for(_base_pattern(label)) if s in set(syms)]
        mod = importlib.import_module(detmod)
        opp = importlib.import_module(oppmod) if oppmod else None
        n = n_routed_out = 0
        for sym in pat_syms:
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
                if ROUTING_MODE and not routed_in(label, direction, rows[si]["date"], routing, regmap):
                    n_routed_out += 1
                    continue
                ret, hold, _ = mt.outcome_d(rows, si, direction, opp_set)
                xi = min(si + hold, len(rows) - 1)
                out.append((rows[si]["date"], rows[xi]["date"], ret, hold, label, sym,
                            realized_vol(rows, si, tf=tf)))
                n += 1
        extra = (f" (종목 {len(pat_syms)}, 라우팅 제외 {n_routed_out}건)" if ROUTING_MODE else "")
        print(f"  [{label}] {n}건{extra}", flush=True)
    out.sort(key=lambda t: (t[0], t[4], t[5]))
    return out


scale_of = sz.vol_scale_raw        # s_raw = clip(TARGET/σ, LO, HI)


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
    scales, notionals, lev_ratios = [], [], []
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
            if equity > 0:
                lev_ratios.append(r["notional"] / equity)     # 노출 = 명목가/자본 (달러 아님)
            taken += 1
    days = max(1, evs[-1][0] - evs[0][0]) if evs else 1
    yrs = days / 365.25
    cagr = (equity / START_EQ) ** (1 / yrs) - 1 if equity > 0 else -1.0
    return dict(final=equity, cagr=cagr, mdd=mdd,
                calmar=(cagr / abs(mdd) if mdd < 0 else float("inf")),
                taken=taken, skipped=skipped,
                mean_scale=(st.mean(scales) if scales else 0.0),
                mean_notional=(st.mean(notionals) if notionals else 0.0),
                mean_lev=(st.mean(lev_ratios) if lev_ratios else 0.0))


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
    global ROUTING_MODE
    argv = argv if argv is not None else sys.argv[1:]
    ROUTING_MODE = "--routing" in argv
    ms.UNIVERSE_MODE = "--majors" not in argv
    syms = ms.symbols()
    print(f"[표본] {len(syms)}종목 ({'유니버스 80' if ms.UNIVERSE_MODE else '메이저'})"
          f"{' | **실거래 라우팅 복제**' if ROUTING_MODE else ' | 전 패턴 x 전 종목(강건성 표본)'}")
    if "--no-fetch" not in argv:
        ms.ensure_data(ms.FETCH_DAYS, syms)
    out_path = "sizing_vol_routing.json" if ROUTING_MODE else "sizing_vol.json"
    trades = collect_all(syms)
    if not trades:
        print("거래 없음"); return
    vols = [t[6] for t in trades if t[6]]
    print(f"[거래] {len(trades)}건 | 변동성 산출 {len(vols)}건 "
          f"(중앙 연율 {st.median(vols)*100:.0f}%, 10~90분위 "
          f"{sorted(vols)[len(vols)//10]*100:.0f}~{sorted(vols)[len(vols)*9//10]*100:.0f}%)")
    # s_norm = 전 신호에 대한 s_raw 평균 = vol_matched 의 인과적 확장평균이 수렴하는 값.
    # 실거래(sizing.VOL_S_NORM)는 이 상수를 쓴다 — 앞으로 나갈 거래는 확장평균이 이미
    # 수렴한 지점에 있기 때문. 값이 sizing.VOL_S_NORM 과 어긋나면 아래에서 경고한다.
    s_norm = st.mean([scale_of(t[6]) for t in trades])
    print(f"[정규화] s_raw 평균(s_norm) = {s_norm:.4f}  | sizing.VOL_S_NORM = {sz.VOL_S_NORM}")
    if ROUTING_MODE and sz.VOL_S_NORM and abs(s_norm - sz.VOL_S_NORM) > 0.02:
        print(f"  [경고] 실거래 상수가 이 표본의 s_norm 과 {abs(s_norm - sz.VOL_S_NORM):.4f} 차이 "
              f"— sizing.VOL_S_NORM 갱신 검토")
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
    # 노출 비율은 **진입 시점 레버리지(명목가/equity)** 로 잰다. 달러 명목가로 재면
    # 성과가 좋은 arm 이 자본을 키워 명목가도 커지므로 '레버리지를 더 썼다'와 '돈을 더 벌었다'가
    # 구분되지 않는다(1차 실행에서 실제로 1.94배로 나와 오독을 유발했다).
    lev_base = res["risk"]["base"]["mean_lev"]
    expo = (res["vol_matched"]["base"]["mean_lev"] / lev_base) if lev_base else 0.0
    expo_raw = (res["vol_raw"]["base"]["mean_lev"] / lev_base) if lev_base else 0.0
    expo_usd = (res["vol_matched"]["base"]["mean_notional"] / res["risk"]["base"]["mean_notional"]
                if res["risk"]["base"]["mean_notional"] else 0.0)
    c_a = mat_b["calmar_med"] > base_b["calmar_med"]
    c_b = mat_b["mdd_med"] >= base_b["mdd_med"]
    c_c = mat_b["p_ruin"] <= base_b["p_ruin"]
    # (d) 정규화 가드 — vol_matched 의 존재 이유가 '평균 노출 정합'이므로 이게 깨지면
    #     (a)(b)(c) 개선은 재분배가 아니라 레버리지 효과일 수 있어 판정이 성립하지 않는다.
    c_d = 0.8 <= expo <= 1.2
    adopt = bool(c_a and c_b and c_c and c_d)
    print(f"\n[노출 비율] 진입 레버리지(명목가/equity) 기준 — vol_matched/risk = {expo:.2f}배 "
          f"(1.0 근처여야 정규화 작동) | vol_raw/risk = {expo_raw:.2f}배")
    print(f"             참고: 달러 명목가 기준은 {expo_usd:.2f}배 — 성과가 좋은 arm 이 자본을 키워"
          f" 커지므로 노출 판단에 쓰면 안 된다")
    print("\n[사전 등록 판정] 주 arm = vol_matched")
    print(f"  (a) boot Calmar 개선  {mat_b['calmar_med']:.2f} vs {base_b['calmar_med']:.2f}  -> {'통과' if c_a else '탈락'}")
    print(f"  (b) boot MDD 악화 없음 {mat_b['mdd_med']*100:+.1f}% vs {base_b['mdd_med']*100:+.1f}%  -> {'통과' if c_b else '탈락'}")
    print(f"  (c) P(ruin) 악화 없음  {mat_b['p_ruin']*100:.1f}% vs {base_b['p_ruin']*100:.1f}%  -> {'통과' if c_c else '탈락'}")
    print(f"  (d) 노출 정합 0.8~1.2  {expo:.2f}배  -> {'통과' if c_d else '탈락 (정규화 미작동 = 판정 불성립)'}")
    print(f"  => {'ADOPT 후보 (사용자 결정)' if adopt else 'REJECT'}")
    print(f"\n[진단] vol_raw 는 노출 {expo_raw:.2f}배 — 1 을 넘는 만큼은 변동성 타겟팅이 아니라 레버리지다.")
    # [문턱] 채택 시 실계좌에서 생기는 부작용을 숨기지 않고 센다. 고변동 신호는 명목가가
    # 줄어 최소 증거금($10)에 못 미치면 **주문 자체가 안 나간다**. 계좌가 작을수록 심하다.
    # 현행(risk)은 스케일 1.0 이라 equity >= min_equity_for(1.0) 이면 전 신호가 통과한다.
    vs_all = sorted(scale_of(t[6]) / s_norm for t in trades)
    base_floor = sz.min_equity_for(1.0, STOP)
    print(f"[문턱] 계좌 규모별 '스케일이 작아 최소증거금 미달로 스킵'되는 신호 비율 "
          f"(현행 규칙은 equity >= ${base_floor:.0f} 이면 0%)")
    for eq in (200, 250, 300, 400, 600, 1000):
        vs_min = sz.MIN_MARGIN * sz.liq_safe_leverage(STOP) * STOP / (RISK_FRAC * eq)
        blocked = sum(1 for v in vs_all if v < vs_min)
        print(f"    equity ${eq:>5}: vol_scale < {vs_min:.2f} 이면 스킵 → "
              f"{blocked}/{len(vs_all)} ({blocked/len(vs_all)*100:.1f}%)"
              + ("   ← 현행에서는 전 신호 스킵" if eq < base_floor else ""))
    json.dump(dict(config=dict(target_vol=TARGET_VOL, lo=LO, hi=HI, vol_lb=VOL_LB,
                               risk_frac=RISK_FRAC, lev=LEV, boot_n=BOOT_N, block=BLOCK,
                               n_symbols=len(syms), n_trades=len(trades),
                               routing_mode=ROUTING_MODE, s_norm=round(s_norm, 4)),
                   results=res, exposure=dict(matched=expo, raw=expo_raw, matched_usd=expo_usd),
                   verdict=dict(adopt=adopt, c_a_calmar=c_a, c_b_mdd=c_b, c_c_ruin=c_c,
                                c_d_exposure=c_d)),
              open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[저장] {out_path}")
    print("\nRESULT_JSON: " + json.dumps(dict(
        adopt=adopt, exposure_matched=round(expo, 3), s_norm=round(s_norm, 4),
        calmar={a: round(res[a]["boot"]["calmar_med"], 3) for a in ARMS},
        mdd={a: round(res[a]["boot"]["mdd_med"], 4) for a in ARMS}), separators=(",", ":")))


if __name__ == "__main__":
    main()
