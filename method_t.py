"""
method_t.py — 고정 익절(Take-Profit) arm 시험: 방식D vs 방식T(k).

배경
----
방식D(현행 실거래)에는 **가격 기준 익절이 없다.** 청산은 -8% 손절 / 반대패턴 신호 /
레짐 전환 / 최대 30봉뿐이라, 진입가 대비 +20% 갔다가 본전으로 돌아와도 아무 조건도
걸리지 않는다(손절선이 고점이 아니라 '진입가' 기준이라 트레일링이 아님).
게다가 반대패턴 청산은 engulfing/fvg 에만 있고, 현재 자동 진입 3종
(inverted_hammer/marubozu/triple_bottom)은 반대 신호 자체가 없다.

방식T(k) = 방식D + 진입가 대비 +k% 도달 시 무조건 익절.

왜 실거래 자본을 쪼개지 않는가
-----------------------------
"+k% 도달 시 익절"은 가격 경로의 **결정론적 함수**라 과거 데이터로 정확히 재현된다.
그리고 포지션을 두 그룹으로 나누면 서로 다른 종목·시점을 비교하게 되어 차이의
대부분이 '규칙 차이'가 아니라 '어느 종목이 걸렸나'에서 온다. 같은 신호에 두 규칙을
동시에 적용하는 **짝지음(paired)** 비교가 같은 결론에 훨씬 적은 표본으로 도달한다.
이 스크립트는 그 짝지음 비교를 한다.

건당 평균만 보면 안 되는 이유
----------------------------
동결 게이트는 '건당 평균수익'을 본다. 그런데 복리는 **자본 회전율**에서 나온다.
빨리 청산하면 같은 기간에 더 많은 신호에 재투입되므로, 건당 수익이 낮아도 최종
자산은 클 수 있다. 그래서 per-trade 통계와 별도로 실제 사이징 규칙
(가용잔고 20%, 최대 12포지션, 레버리지 2x)을 적용한 **자산곡선 CAGR/MDD**를 병기한다.

과적합 방어
----------
k 를 5수준(10/15/20/25/30%) 전부 보고 **단조 반응**인지 확인한다. 특정 k 하나만
튀면 잡음일 가능성이 높고, k 에 따라 매끄럽게 변하면 실제 구조로 볼 근거가 된다.
'최적 k' 를 고르는 것이 목적이 아니라 '고정 익절이 방식D보다 나은가'가 목적이다.

실행: python method_t.py   (Actions 러너 — 데이터 자동 수집)
"""
import importlib
import json
import statistics as st
from datetime import date

import detlib
import fetch_data
import regime_switch as rs

# ── 동결 파라미터 (방식D와 동일 — 익절만 추가) ──────────────────────────────
STOP_LOSS_PCT = 0.08
MAX_HOLD = 30
FEE = detlib.FEE
TP_LEVELS = [0.10, 0.15, 0.20, 0.25, 0.30]

FETCH_DAYS = 1800          # 1d 약 5년 (triple_bottom 1w 리샘플에도 사용)

# 자산곡선 시뮬레이션 — 실거래 설정과 동일하게
SIM_POS_PCT   = 0.20       # paper_executor.LIVE_BAL_PCT
SIM_MAX_POS   = 12         # paper_executor.MAX_LIVE_POS
SIM_LEVERAGE  = 2          # exchange.OKX_LEVERAGE
SIM_START_EQ  = 1000.0

# (라벨, 방향, detector모듈, 반대detector|None, tf)
# 반대 detector 가 None 이면 opp_set 은 빈 집합 — paper_executor.OPP 의 동작과 동일.
PATS = [
    # method_d.py 가 이미 비교 중인 4종
    ("engulfing",       "long",  "detector_engulfing",       "detector_engulfing_short", "1d"),
    ("fvg",             "long",  "detector_fvg",             "detector_fvg_short",       "1d"),
    ("engulfing_short", "short", "detector_engulfing_short", "detector_engulfing",       "1d"),
    ("fvg_short",       "short", "detector_fvg_short",       "detector_fvg",             "1d"),
    # 현재 자동 진입 중인 3종 (반대 신호 청산이 없어 익절 부재의 영향이 가장 큼)
    ("inverted_hammer", "long",  "detector_inverted_hammer", None,                       "1d"),
    ("marubozu",        "long",  "detector_marubozu",        None,                       "1d"),
    ("triple_bottom",   "long",  "detector_triple_bottom",   None,                       "1w"),
]

# 레짐맵은 데이터 수집 이후에 만든다 (import 시점엔 CSV가 아직 없다).
REGMAP = {}


# ── 데이터 ──────────────────────────────────────────────────────────────────
def ensure_data():
    ok = new = 0
    for s in detlib.SYMBOLS:
        try:
            n_new, total = fetch_data.update_csv(
                f"{s}/USDT", "1d", detlib.CSV(s, "1d"), window_days=FETCH_DAYS)
            if total:
                ok += 1
                new += n_new
        except Exception as e:
            print(f"  [fetch] {s} 실패: {str(e)[:60]}")
    print(f"[fetch] 1d {FETCH_DAYS}일: {ok}/{len(detlib.SYMBOLS)}종목 (+{new}봉)")


# ── 청산 규칙 ───────────────────────────────────────────────────────────────
def outcome_d(rows, si, direction, opp_set, tp_pct=None):
    """
    방식D 청산. tp_pct 를 주면 방식T(k) — 진입가 대비 +k% 도달 시 익절.

    익절 판정은 손절과 같은 기준(봉 내 고가/저가)으로 한다. 실제로는 지정가
    청산 주문이 봉 중간에 체결되기 때문. 같은 봉에서 손절·익절이 모두 닿으면
    **보수적으로 손절을 우선**한다(레포 관례: intraday_lab.outcome_atr 과 동일).

    반환: (ret, hold_bars, reason)
    """
    base = rows[si]["c"]
    entry_reg = REGMAP.get(rows[si]["date"])
    end = min(si + MAX_HOLD, len(rows) - 1)
    tp_px = None
    if tp_pct:
        tp_px = base * (1 + tp_pct) if direction == "long" else base * (1 - tp_pct)

    for j in range(si + 1, end + 1):
        # 1) 손절 (봉 내) — 익절보다 먼저 검사
        if direction == "long":
            if rows[j]["l"] <= base * (1 - STOP_LOSS_PCT):
                return -STOP_LOSS_PCT - FEE, j - si, "stop"
        else:
            if rows[j]["h"] >= base * (1 + STOP_LOSS_PCT):
                return -STOP_LOSS_PCT - FEE, j - si, "stop"
        # 2) 고정 익절 (봉 내) — 방식T 에만
        if tp_px is not None:
            if direction == "long" and rows[j]["h"] >= tp_px:
                return tp_pct - FEE, j - si, "tp_fixed"
            if direction == "short" and rows[j]["l"] <= tp_px:
                return tp_pct - FEE, j - si, "tp_fixed"
        # 3) 반대 신호 / 레짐 전환 (종가)
        regsw = REGMAP.get(rows[j]["date"]) not in (None, entry_reg)
        if j in opp_set or regsw:
            c = rows[j]["c"]
            r = (c - base) / base if direction == "long" else (base - c) / base
            return r - FEE, j - si, ("opp_signal" if j in opp_set else "regime_switch")

    px = rows[end]["o"]
    r = (px - base) / base if direction == "long" else (base - px) / base
    return r - FEE, end - si, "maxhold"


# ── 통계 ────────────────────────────────────────────────────────────────────
def summ(trades):
    """trades: [(entry_date, exit_date, ret, hold, reason)]"""
    if not trades:
        return None
    rets = [t[2] for t in trades]
    holds = [t[3] for t in trades]
    wins = [r for r in rets if r > 0]
    return dict(n=len(rets), mean=st.mean(rets), median=st.median(rets),
                maxloss=min(rets), maxwin=max(rets), avghold=st.mean(holds),
                winrate=len(wins) / len(rets))


def paired_stats(base_rets, arm_rets):
    """
    같은 신호에 두 규칙을 적용한 짝지음 비교.
    차이 d_i = arm_i - base_i 의 평균과 t통계량. 가격 경로가 동일하므로
    종목·시점 교란이 상쇄되어 분리 비교보다 검정력이 훨씬 높다.
    """
    d = [a - b for a, b in zip(arm_rets, base_rets)]
    n = len(d)
    if n < 2:
        return dict(n=n, mean_diff=0.0, t=0.0, wins=0, losses=0, ties=n)
    m = st.mean(d)
    sd = st.stdev(d)
    t = m / (sd / (n ** 0.5)) if sd > 0 else 0.0
    return dict(n=n, mean_diff=m, sd_diff=sd, t=t,
                wins=sum(1 for x in d if x > 1e-12),
                losses=sum(1 for x in d if x < -1e-12),
                ties=sum(1 for x in d if abs(x) <= 1e-12))


# ── 자산곡선 (회전율·복리 반영) ─────────────────────────────────────────────
def _dnum(ds):
    y, m, d = map(int, ds.split("-"))
    return date(y, m, d).toordinal()


def equity_curve(trades):
    """
    실거래 사이징으로 포트폴리오를 시간순 시뮬레이션.

    건당 평균수익은 '자본이 얼마나 빨리 회전하는가'를 보지 못한다. 빨리 청산하는
    규칙은 같은 기간에 더 많은 신호에 재투입되므로 건당 수익이 낮아도 최종 자산이
    클 수 있다. 그래서 실제 규칙(가용잔고 x20%, 최대 12포지션, 레버리지 2x)으로
    자산곡선을 만들어 CAGR/MDD 를 비교한다.

    - 진입: 슬롯이 남고 현금이 있으면 size = free x SIM_POS_PCT
    - 청산: equity += size x SIM_LEVERAGE x ret
    - 같은 날 여러 신호는 종목명 순으로 결정론적 처리(재현성)
    반환: dict(final, cagr, mdd, calmar, n_taken, n_skipped, days)
    """
    if not trades:
        return None
    evs = []
    for i, (ed, xd, ret, hold, reason) in enumerate(trades):
        evs.append((_dnum(ed), 0, i))          # 0 = 진입 (청산보다 뒤에 처리)
        evs.append((_dnum(xd), -1, i))         # -1 = 청산 먼저
    evs.sort()

    equity = SIM_START_EQ
    free = SIM_START_EQ
    open_pos = {}                              # idx -> size
    peak = equity
    mdd = 0.0
    taken = skipped = 0

    for day, kind, idx in evs:
        if kind == -1:                         # 청산
            size = open_pos.pop(idx, None)
            if size is None:
                continue
            ret = trades[idx][2]
            pnl = size * SIM_LEVERAGE * ret
            equity += pnl
            free += size + pnl
            peak = max(peak, equity)
            if peak > 0:
                mdd = min(mdd, equity / peak - 1)
        else:                                  # 진입
            if len(open_pos) >= SIM_MAX_POS or free <= 0:
                skipped += 1
                continue
            size = free * SIM_POS_PCT
            if size <= 0:
                skipped += 1
                continue
            free -= size
            open_pos[idx] = size
            taken += 1

    days = max(1, evs[-1][0] - evs[0][0])
    yrs = days / 365.25
    cagr = (equity / SIM_START_EQ) ** (1 / yrs) - 1 if equity > 0 and yrs > 0 else -1.0
    return dict(final=equity, cagr=cagr, mdd=mdd,
                calmar=(cagr / abs(mdd) if mdd < 0 else float("inf")),
                n_taken=taken, n_skipped=skipped, days=days)


# ── 실행 ────────────────────────────────────────────────────────────────────
def run_pattern(label, direction, detmod, oppmod, tf):
    mod = importlib.import_module(detmod)
    opp = importlib.import_module(oppmod) if oppmod else None

    arms = {"D": []}                            # 방식D (현행) + T(k)
    for k in TP_LEVELS:
        arms[f"T{int(k*100)}"] = []

    for sym in detlib.SYMBOLS:
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
            for name, tp in [("D", None)] + [(f"T{int(k*100)}", k) for k in TP_LEVELS]:
                ret, hold, reason = outcome_d(rows, si, direction, opp_set, tp)
                xi = min(si + hold, len(rows) - 1)
                arms[name].append((rows[si]["date"], rows[xi]["date"], ret, hold, reason))

    if not arms["D"]:
        return None

    base_rets = [t[2] for t in arms["D"]]
    out = {}
    for name, trades in arms.items():
        s = summ(trades)
        eq = equity_curve(sorted(trades, key=lambda t: t[0]))
        rec = dict(per_trade=s, equity=eq)
        if name != "D":
            rec["paired_vs_D"] = paired_stats(base_rets, [t[2] for t in trades])
            rec["tp_hit_rate"] = sum(1 for t in trades if t[4] == "tp_fixed") / len(trades)
        out[name] = rec
    return out


def monotonic(vals):
    """TP 수준을 높일수록 지표가 단조로 변하는가 (과적합 판별 보조)."""
    inc = all(b >= a - 1e-12 for a, b in zip(vals, vals[1:]))
    dec = all(b <= a + 1e-12 for a, b in zip(vals, vals[1:]))
    return "증가" if inc else ("감소" if dec else "비단조")


def main():
    global REGMAP
    ensure_data()
    REGMAP = rs.build_regime_map()
    print(f"[regime] 레짐맵 {len(REGMAP)}일")
    names = ["D"] + [f"T{int(k*100)}" for k in TP_LEVELS]
    results = {}

    print("=" * 108)
    print(f"방식D(익절 없음) vs 방식T(k) — 진입가 +k% 고정 익절 추가 "
          f"| 손절 -{int(STOP_LOSS_PCT*100)}% / 최대 {MAX_HOLD}봉 동결")
    print(f"자산곡선: 시작 ${SIM_START_EQ:.0f}, 가용잔고x{SIM_POS_PCT:.0%}, "
          f"최대 {SIM_MAX_POS}포지션, 레버리지 {SIM_LEVERAGE}x")
    print("=" * 108)

    for label, direction, detmod, oppmod, tf in PATS:
        try:
            res = run_pattern(label, direction, detmod, oppmod, tf)
        except Exception as e:
            print(f"\n[{label}] 실행 오류: {str(e)[:80]}")
            continue
        if not res:
            print(f"\n[{label}] 신호 없음 — 스킵")
            continue
        results[label] = res

        print(f"\n[{label} @{tf} {direction}]  "
              f"{'반대신호 청산 있음' if oppmod else '반대신호 청산 없음'}")
        print(f"  {'arm':<5}{'n':>5}{'건당평균':>10}{'중앙':>9}{'승률':>7}{'평균보유':>8}"
              f"{'익절체결':>8}  |{'짝지음차이':>11}{'t':>7}{'승/패':>10}"
              f"  |{'CAGR':>8}{'MDD':>8}{'Calmar':>8}")
        print("  " + "-" * 104)
        for nm in names:
            r = results[label][nm]
            s, eq = r["per_trade"], r["equity"]
            if nm == "D":
                pair = f"{'(기준)':>11}{'':>7}{'':>10}"
                tph = f"{'-':>8}"
            else:
                p = r["paired_vs_D"]
                pair = (f"{p['mean_diff']*100:>+10.2f}%{p['t']:>7.2f}"
                        f"{p['wins']:>5}/{p['losses']:<5}")
                tph = f"{r['tp_hit_rate']:>7.0%}"
            print(f"  {nm:<5}{s['n']:>5}{s['mean']*100:>+9.2f}%{s['median']*100:>+8.2f}%"
                  f"{s['winrate']:>6.0%}{s['avghold']:>8.1f}{tph}  |{pair}"
                  f"  |{eq['cagr']*100:>+7.1f}%{eq['mdd']*100:>+7.1f}%{eq['calmar']:>8.2f}")

        # 단조성 — 특정 k 만 튀면 잡음, 매끄러우면 구조
        tvals = [results[label][f"T{int(k*100)}"] for k in TP_LEVELS]
        print(f"  [단조성] 건당평균 {monotonic([r['per_trade']['mean'] for r in tvals])}"
              f" / CAGR {monotonic([r['equity']['cagr'] for r in tvals])}"
              f" / 짝지음차이 {monotonic([r['paired_vs_D']['mean_diff'] for r in tvals])}")

    # ── 종합: 어떤 arm 이 몇 개 패턴에서 방식D를 이겼나 ──────────────────────
    print("\n" + "=" * 108)
    print("종합 — 방식D 대비 우위 패턴 수 (짝지음 평균차이 > 0 / CAGR 우위)")
    print("=" * 108)
    summary = {}
    for nm in names[1:]:
        pw = sum(1 for lb in results if results[lb][nm]["paired_vs_D"]["mean_diff"] > 0)
        cw = sum(1 for lb in results
                 if results[lb][nm]["equity"]["cagr"] > results[lb]["D"]["equity"]["cagr"])
        tsig = sum(1 for lb in results if results[lb][nm]["paired_vs_D"]["t"] > 2.0)
        summary[nm] = dict(paired_wins=pw, cagr_wins=cw, t_gt2=tsig, n_pat=len(results))
        print(f"  {nm:<5} 짝지음우위 {pw}/{len(results)}  "
              f"CAGR우위 {cw}/{len(results)}  t>2 유의 {tsig}/{len(results)}")

    payload = dict(config=dict(stop=STOP_LOSS_PCT, max_hold=MAX_HOLD, fee=FEE,
                               tp_levels=TP_LEVELS, fetch_days=FETCH_DAYS,
                               sim=dict(pos_pct=SIM_POS_PCT, max_pos=SIM_MAX_POS,
                                        leverage=SIM_LEVERAGE, start=SIM_START_EQ)),
                   patterns=results, summary=summary)
    json.dump(payload, open("method_t.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1, default=lambda x: round(x, 6))
    print("\n[저장] method_t.json")
    print("RESULT_SUMMARY: " + json.dumps(summary, separators=(",", ":")))


if __name__ == "__main__":
    main()
