"""
validate_port_vol.py — 포트폴리오 단위 변동성 타겟팅 (사전 등록, 2026-09-21)

**왜.** 레포에서 실제로 효과가 확인된 두 가지가 모두 **배분 규칙**이다 — 건당 변동성
타겟팅(P(ruin) 37.7%→14.3%, 2026-09-04 채택)과 레짐 라우팅(boot Calmar −0.00→0.65).
그런데 변동성 타겟팅은 **거래 하나씩** 명목가를 맞출 뿐 포트폴리오 전체 노출은 보지 않는다.
알트는 상관이 높아 13 포지션을 들어도 분산이 거의 없다(명목가 합계가 equity 의 약 1.6배 =
사실상 하나의 베타 포지션). 그 축은 시험된 적이 없다.

────────────────────────────────────────────────────────────────────────────
사전 등록 (결과 보기 전 고정 — registry port_vol_prereg_2026_09_21)

프레임: validate_portfolio 그대로 — 배포 집합·방식D 청산·슬롯 배분(current)·MAX_POS·
        RISK_FRAC·LEV_CAP·START_EQ 전부 고정. **arm 이 바꾸는 것은 명목가 배율 하나뿐.**
        분할 train < 2025-01-01 <= holdout.
arm:    current / **port_vol(주 판정)** / port_mkt·port_corr·port_dd(진단).
port_vol: m = clip(TARGET / σ_p, 0.5, 2.0).
        σ_p = 오픈북(기존 + 신규)의 연율 포트폴리오 변동성
            = sqrt(ΣᵢΣⱼ wᵢwⱼ ρᵢⱼ σᵢσⱼ),  wᵢ = 명목가ᵢ/equity,  ρᵢⱼ = ρ̄(t)(i≠j)·1(i=j).
        **TARGET = train 구간 current arm 의 σ_p 중앙값** — holdout 에 그대로 적용(노출 정합).
ρ̄(t):  직전 60 거래일 top30 일간 수익률의 **평균 쌍상관**(인과적). 표본 <30 이면 직전 유효값,
        없으면 0.7.
판정:   holdout 기준 **J1~J6 전부** 충족해야 ADOPT_CANDIDATE.
        J1 CAGR>current / J2 Calmar>current / J3 짝지음 블록 부트 300회 우위 >= 0.60 /
        J4 MDD 가 current 보다 5%p 넘게 악화되지 않음 / J5 train 에서도 CAGR·Calmar 둘 다
        current 이상 / **J6 평균 진입 레버리지가 current 의 0.90~1.10배**(노출 정합 가드 —
        '그냥 작게 걸어 MDD 를 줄인 것'을 개선으로 세지 않는다).
DEPLOY_ON_PASS = False — 사이징은 사용자 결정 사항이고 관찰 기간(~2026-10-06) 중
실거래 규칙 변경 금지가 걸려 있다.

실행: python validate_port_vol.py [--no-fetch]
"""
import json
import math
import random
import statistics as st
import sys

import detlib
import method_t as mt
import regime_switch
import sizing as sz
import sizing_study as ss
import validate_portfolio as vp
import validate_regime_split_all as va
from validate_regime_split import turnover_rank

DEPLOY_ON_PASS = False

SPLIT = vp.SPLIT
START_EQ, MAX_POS, STOP = ss.START_EQ, ss.MAX_POS, ss.STOP
BOOT_N, BLOCK, SEED = ss.BOOT_N, ss.BLOCK, ss.SEED

RHO_WIN = 60            # ρ̄ 추정 창(거래일)
RHO_MIN = 30            # 그 창에서 필요한 최소 관측
RHO_DEFAULT = 0.70      # 알트 기본값 — 창이 없을 때만
RHO_STEP = 1            # 날짜마다 재계산(식이 O(n) 이라 전수로 충분)
MKT_WIN = 20            # 시장 σ — 직전 20봉 실현변동성의 횡단면 중앙값
CORR_REF_RHO = 0.70     # port_corr 의 N_ref 기준 상관
M_LO, M_HI = sz.VOL_LO, sz.VOL_HI      # 배율 상·하한 — 건당 타겟팅과 같은 [0.5, 2.0]
DD_TRIP, DD_MULT = 0.20, 0.5           # port_dd 진단
SIGMA_FLOOR = 0.05                     # σ 하한(연율) — 0 나누기 방어
DEFAULT_VOL = 0.80                     # σ 미산출 포지션의 대체값 = sizing.VOL_TARGET_VOL

J4_MDD_TOL, J3_WIN = vp.J4_MDD_TOL, vp.J3_WIN
J6_LO, J6_HI = 0.90, 1.10
ARMS = ["current", "port_vol", "port_mkt", "port_corr", "port_dd"]
MAIN_ARM = "port_vol"
OUT = "_port_vol.json"


# ── ρ̄ : 평균 쌍상관 ───────────────────────────────────────────────────────────
def avg_pair_corr(series):
    """
    표준화한 계열들의 **등가중 평균**의 분산에서 평균 쌍상관을 역산한다.
        Var(z̄) = (1 + (n−1)ρ̄) / n   →   ρ̄ = (n·Var(z̄) − 1) / (n − 1)
    쌍을 전부 돌면 O(n²·T) 인데 이 식은 O(n·T) 이고 **값은 정확히 같다**(테스트가 고정).
    """
    zs = []
    for xs in series:
        if len(xs) < 2:
            continue
        m = st.fmean(xs)
        sd = math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))
        if sd <= 0:
            continue
        zs.append([(x - m) / sd for x in xs])
    n = len(zs)
    if n < 2:
        return None
    T = min(len(z) for z in zs)
    zbar = [sum(z[t] for z in zs) / n for t in range(T)]
    mb = st.fmean(zbar)
    var = sum((x - mb) ** 2 for x in zbar) / (T - 1) if T > 1 else 0.0
    return max(-1.0 / (n - 1), min(1.0, (n * var - 1.0) / (n - 1)))


def rho_series(rows_by, cohort):
    """{date: ρ̄} — 그 날짜 **직전** RHO_WIN 거래일만 쓴다(인과적)."""
    rets, dates = {}, []
    for s in cohort:
        rows = rows_by.get(s)
        if not rows or len(rows) < 2:
            continue
        r = {}
        for i in range(1, len(rows)):
            p0 = rows[i - 1]["c"]
            if p0:
                r[rows[i]["date"]] = rows[i]["c"] / p0 - 1.0
        rets[s] = r
    for s in rets:
        dates.extend(rets[s])
    dates = sorted(set(dates))
    out, last = {}, None
    for i, d in enumerate(dates):
        if i % RHO_STEP == 0:
            win = dates[max(0, i - RHO_WIN):i]          # d 는 제외 — 인과적
            if len(win) >= RHO_MIN:
                series = []
                for s, r in rets.items():
                    xs = [r[w] for w in win if w in r]
                    if len(xs) >= RHO_MIN:
                        series.append(xs)
                v = avg_pair_corr(series)
                if v is not None:
                    last = v
        out[d] = last if last is not None else RHO_DEFAULT
    return out


def mkt_sigma_series(rows_by, cohort, tf="1d"):
    """{date: 시장 σ} — 그 날짜 기준 직전 MKT_WIN 봉 실현변동성의 횡단면 중앙값(인과적)."""
    import sizing_vol as sv
    per = {}
    for s in cohort:
        rows = rows_by.get(s)
        if not rows:
            continue
        for i in range(MKT_WIN, len(rows)):
            v = sv.realized_vol(rows, i, tf=tf)
            if v and v > 0:
                per.setdefault(rows[i]["date"], []).append(v)
    return {d: st.median(v) for d, v in per.items() if v}


def date_of(t):
    """거래의 진입 날짜. t_in 은 1d 면 정수 ordinal, 4h 면 분수 ordinal 이라 내림이 곧 그 날이다."""
    from datetime import date as _d
    return _d.fromordinal(int(t["t_in"])).isoformat()


# ── 배율 ──────────────────────────────────────────────────────────────────────
def port_sigma(weights_vols, rho):
    """[(w, σ)] 와 ρ̄ 로 포트폴리오 연율 변동성. 대각은 1, 비대각은 ρ̄ 로 근사한다."""
    if not weights_vols:
        return None
    tot = sum(w * v for w, v in weights_vols)
    sq = sum((w * v) ** 2 for w, v in weights_vols)
    var = rho * tot * tot + (1.0 - rho) * sq        # ΣΣ wᵢwⱼσᵢσⱼ[ρ + (1−ρ)δᵢⱼ]
    return math.sqrt(max(var, 0.0))


def _open_wv(ctx):
    """오픈북의 [(명목가/equity, σ)]."""
    eq, tr = ctx["equity"], ctx["trades"]
    return [(n / eq, tr[j].get("vol") or DEFAULT_VOL)
            for j, (_m, n) in ctx["open_pos"].items()] if eq > 0 else []


def _new_notional(ctx, s_base):
    """신규 포지션의 명목가 추정 — 위험 기준 무제약 값.

    실제 크기는 σ_p 에 의존하고 σ_p 는 다시 그 크기에 의존하므로 **1스텝 근사**다
    (배율 1 일 때의 크기로 σ_p 를 잡고 그 배율을 적용한다). 상한(pos/total/free)에
    걸리는 경우는 추정이 과대해지지만, 그때는 상한이 크기를 정하므로 배율의 역할이 작다.
    """
    return ctx["equity"] * sz.RISK_FRAC * s_base / STOP


def make_mult(arm, rho_of, mkt_of, target, date_of):
    if arm == "current":
        return None

    def f(ctx):
        d = date_of(ctx["trades"][ctx["idx"]])
        rho = rho_of.get(d, RHO_DEFAULT)
        if arm == "port_dd":
            return DD_MULT if ctx["equity"] <= ctx["peak"] * (1 - DD_TRIP) else 1.0
        if arm == "port_corr":
            # **상관 축만** 본다. 포지션 수 효과는 주 판정 arm(port_vol)의 σ_p 가 이미 담고
            # 있으므로, 여기서는 책 크기를 MAX_POS 로 고정하고 ρ̄ 만 기준치에서 벗어난 만큼
            # 노출을 조절한다. ρ̄ = CORR_REF_RHO 이면 배율 1.0.
            #
            # 실행 전 수정(공개): 사전 등록 초안은 m = sqrt(N_eff/N_ref) 였는데 **부호가
            # 반대였다** — N_eff = n/(1+(n−1)ρ) 는 n 이 커질수록 커지므로 포지션이 늘수록
            # 배율이 커진다. 포트폴리오 σ 를 일정하게 두려면 등가중 비중은 sqrt(N_eff)/n 에
            # 비례해 **줄어야** 한다. 결과를 보기 전에 고쳤고 registry 에 남긴다.
            ref = 1.0 + (MAX_POS - 1) * CORR_REF_RHO
            cur = 1.0 + (MAX_POS - 1) * rho
            return max(M_LO, min(M_HI, math.sqrt(ref / max(cur, 1e-9))))
        if arm == "port_mkt":
            sig = mkt_of.get(d)
            if not sig:
                return 1.0
            return max(M_LO, min(M_HI, target / max(sig, SIGMA_FLOOR)))
        # port_vol
        tr = ctx["trades"][ctx["idx"]]
        s_base = vp._live_scale(tr.get("vol"))
        wv = _open_wv(ctx) + [(_new_notional(ctx, s_base) / ctx["equity"],
                               tr.get("vol") or DEFAULT_VOL)]
        sig = port_sigma(wv, rho)
        if not sig:
            return 1.0
        return max(M_LO, min(M_HI, target / max(sig, SIGMA_FLOOR)))
    return f


def probe_sigma(trades, rho_of, mkt_of, date_of, kind):
    """current arm 을 돌리면서 σ_p(또는 시장 σ)를 수집 — TARGET 산출용. 배율은 항상 1."""
    seen = []

    def f(ctx):
        d = date_of(ctx["trades"][ctx["idx"]])
        if kind == "mkt":
            v = mkt_of.get(d)
        else:
            tr = ctx["trades"][ctx["idx"]]
            s_base = vp._live_scale(tr.get("vol"))
            v = port_sigma(_open_wv(ctx) + [(_new_notional(ctx, s_base) / ctx["equity"],
                                             tr.get("vol") or DEFAULT_VOL)],
                           rho_of.get(d, RHO_DEFAULT))
        if v:
            seen.append(v)
        return 1.0
    vp.simulate(trades, "current", size_mult=f)
    return seen


# ── 실행 ──────────────────────────────────────────────────────────────────────
def run_arms(trades, rho_of, mkt_of, targets, date_of, tag):
    res = {}
    for arm in ARMS:
        f = make_mult(arm, rho_of, mkt_of, targets.get(arm), date_of)
        r = vp.simulate(trades, "current", size_mult=f)
        res[arm] = r
        print(f"  [{tag}] {arm:10} CAGR {r['cagr']*100:+7.1f}%  MDD {r['mdd']*100:6.1f}%  "
              f"Calmar {r['calmar']:5.2f}  체결 {r['taken']:5}  노출 {r['exposure']:.2f}x  "
              f"스킵 슬롯 {r['skip_slot']:4} / 증거금 {r['skip_margin']:4}", flush=True)
    return res


def judge(train, hold, boot_win):
    """J1~J6 — holdout 기준(J5 만 train). 전부 충족해야 ADOPT_CANDIDATE."""
    c, a = hold["current"], hold[MAIN_ARM]
    ct, at = train["current"], train[MAIN_ARM]
    j = {}
    j["J1 CAGR>current"] = a["cagr"] > c["cagr"]
    j["J2 Calmar>current"] = a["calmar"] > c["calmar"]
    j[f"J3 부트 우위>={J3_WIN:.2f}"] = boot_win >= J3_WIN
    j[f"J4 MDD 악화<={J4_MDD_TOL*100:.0f}%p"] = a["mdd"] >= c["mdd"] - J4_MDD_TOL
    j["J5 train 도 우위"] = at["cagr"] >= ct["cagr"] and at["calmar"] >= ct["calmar"]
    ex = a["exposure"] / c["exposure"] if c["exposure"] else 0.0
    j[f"J6 노출 {J6_LO:.2f}~{J6_HI:.2f}x"] = J6_LO <= ex <= J6_HI
    return j, ex


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    print("=" * 104)
    print("포트폴리오 변동성 타겟팅 — 사전 등록 (registry port_vol_prereg_2026_09_21)")
    print(f"  주 판정 arm: {MAIN_ARM} | J1~J6 전부 충족 시 ADOPT_CANDIDATE | "
          f"DEPLOY_ON_PASS={DEPLOY_ON_PASS}")
    print("=" * 104, flush=True)

    syms = va._syms()
    if "--no-fetch" not in argv:
        vp.fetch(syms)
    rows_1d = va.load_tf(syms, "1d")
    rows_4h = va.load_tf(syms, "4h")
    # 비워 두면 outcome_d 의 레짐 전환 청산이 조용히 꺼진다(2026-09-21 발견).
    mt.REGMAP = regime_switch.build_regime_map()
    ranked = turnover_rank(rows_4h)
    trades = vp.collect_1d(syms) + vp.collect_4h(rows_4h, ranked, mt.REGMAP)
    trades.sort(key=lambda t: (t["t_in"], t["pattern"], t["sym"]))
    print(f"[거래] {len(trades)}건", flush=True)

    cohort = turnover_rank(rows_1d)[:30]
    rho_of = rho_series(rows_1d, cohort)
    mkt_of = mkt_sigma_series(rows_1d, cohort)
    rv = [v for v in rho_of.values() if v is not None]
    print(f"[ρ̄] {len(rho_of)}일  중앙 {st.median(rv):.3f}  "
          f"10~90분위 {st.quantiles(rv, n=10)[0]:.3f}~{st.quantiles(rv, n=10)[-1]:.3f}", flush=True)

    cut = vp.mx._tnum(SPLIT)
    tr_train = [t for t in trades if t["t_in"] < cut]
    tr_hold = [t for t in trades if t["t_in"] >= cut]
    print(f"[분할] train {len(tr_train)} / holdout {len(tr_hold)} (경계 {SPLIT})", flush=True)

    # TARGET — train 의 current arm 에서 관측된 σ 중앙값 (holdout 에 그대로 적용)
    targets = {}
    for arm, kind in (("port_vol", "port"), ("port_mkt", "mkt")):
        seen = probe_sigma(tr_train, rho_of, mkt_of, date_of, kind)
        targets[arm] = st.median(seen) if seen else DEFAULT_VOL
        print(f"[TARGET] {arm}: train 관측 {len(seen)}건 중앙 {targets[arm]:.3f} (연율)", flush=True)

    print("\n[arm] train")
    res_train = run_arms(tr_train, rho_of, mkt_of, targets, date_of, "train")
    print("[arm] holdout")
    res_hold = run_arms(tr_hold, rho_of, mkt_of, targets, date_of, "hold")

    # J3 — 짝지음 블록 부트스트랩(같은 재표집 집합에서 두 arm 비교)
    rng = random.Random(SEED)
    f_main = make_mult(MAIN_ARM, rho_of, mkt_of, targets.get(MAIN_ARM), date_of)
    wins = 0
    for _ in range(BOOT_N):
        bt = vp.block_bootstrap(tr_hold, rng)
        a = vp.simulate(bt, "current", size_mult=f_main)["calmar"]
        c = vp.simulate(bt, "current")["calmar"]
        wins += a > c
    boot_win = wins / BOOT_N
    print(f"\n[부트] holdout {BOOT_N}회 — {MAIN_ARM} Calmar 우위 {boot_win*100:.0f}%", flush=True)

    j, ex = judge(res_train, res_hold, boot_win)
    verdict = "ADOPT_CANDIDATE" if all(j.values()) else "REJECTED"
    print("\n" + "=" * 104)
    print(f"판정 ({MAIN_ARM}): {verdict}")
    for k, v in j.items():
        print(f"  {'O' if v else 'X'}  {k}")
    print(f"  (노출비 {ex:.3f}x)")
    print("  진단 arm(port_mkt/port_corr/port_dd)은 판정 대상이 아니다 — 사후에 골라 쓰지 않는다.")
    print(f"실거래 무변경 (DEPLOY_ON_PASS={DEPLOY_ON_PASS})")
    print("=" * 104)

    keep = ("cagr", "mdd", "calmar", "taken", "exposure", "skip_slot", "skip_margin")
    json.dump(dict(verdict=verdict, main_arm=MAIN_ARM, judgement=j, exposure_ratio=ex,
                   boot_win=boot_win, targets=targets,
                   train={a: {k: res_train[a][k] for k in keep} for a in ARMS},
                   holdout={a: {k: res_hold[a][k] for k in keep} for a in ARMS},
                   rho_median=st.median(rv), n_trades=len(trades),
                   split=SPLIT, deploy_on_pass=DEPLOY_ON_PASS),
              open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print(f"[저장] {OUT}")


if __name__ == "__main__":
    main()
