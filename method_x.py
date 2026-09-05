"""
method_x.py — 청산 변형 3종 시험 (2026-09-04 사전 등록, 사용자 지시 "전부 검증해봐").

출처: 사용자 제공 `quant_exit_catalog.md` 중 **레포에서 아직 시험하지 않은** 항목만 골랐다.
이미 끝난 것(고정 익절=method_t, Chandelier=method_e, 분할익절=method_f, 레짐이탈청산=방식D
본체·method_s, 방향인지 레짐청산=method_r)은 제외했다.

arm (base = D, 현행 실거래 규칙: -8% 고정손절 / 반대신호 / 레짐전환 / 30봉)
  A20 A25 A30 : **ATR 배수 손절** (카탈로그 A-). 손절폭 = clip(k x ATR14(진입봉) / 진입가,
                FLOOR, CAP). 나머지 청산 사유는 D 와 동일.
                동기: 변동성 타겟팅 채택(2026-09-04)으로 **명목가**는 σ 에 맞췄지만
                **손절 거리**는 여전히 8% 고정이다. 같은 -8% 가 BTC 에선 2~3xATR,
                소형 알트에선 1xATR 미만일 수 있어 후자는 노이즈 손절이다.
  T           : **조건부 시간 손절** (카탈로그 A-). 30봉에 도달했을 때 수익률이
                TIME_KEEP 이상이면 EXT_HOLD 까지 1회 연장, 아니면 D 와 동일하게 청산.
                동기: 현행은 이익 중인 포지션도 시계 때문에 자른다.
  S           : **구조적 손절** (카탈로그 B+). 패턴 무효화 지점 — 롱은 신호봉·직전봉의
                최저가, 숏은 최고가. clip(FLOOR, CAP).

**사이징을 반드시 함께 본다.** 손절폭이 arm 마다 다르므로 method_t.equity_curve(가용잔고
x20% 고정, stop 무시)를 쓰면 이 시험의 핵심을 놓친다 — 위험기준 사이징에서는 손절이 좁아지면
명목가가 커진다(명목가 = 위험/손절폭). 그래서 자산곡선은 **실거래와 같은 규칙**
(sizing.risk_based_size, RISK_FRAC/LEV_CAP, 변동성 타겟팅)에 arm 의 stop_pct 를 넘겨 만든다.

사전 등록 판정 기준 (실행 전 고정 — method_r 과 동일한 7개)
  train(홀드아웃 이전)에서 ①~⑤ 를 모두 만족하고, 그 뒤 holdout 에서 ⑥⑦ 도 만족해야 PASS.
   1) 7패턴 합산 짝지음 평균차이 > 0 이고 (t > 2.0 또는 부트스트랩 p < 0.05)
   2) 자산곡선 CAGR 우위 패턴 >= 4/7
   3) 짝지음 t < -2.0 인 패턴이 하나도 없음 (어느 패턴도 크게 망가뜨리지 않음)
   4) 분기 거래(두 규칙이 실제로 갈라진 것) 안에서 arm 승률 > 50%
   5) 시간 분할 — 전반/후반 합산 짝지음 평균차이가 둘 다 > 0
   6) holdout 합산 짝지음 평균차이 > 0
   7) holdout 분기 거래 arm 승률 > 50%

**다중검정 통제 (사전 고정)**: arm 이 5개다.
  · 주 판정 arm 은 **A25**(2~3xATR 관례의 중앙값)와 **T** 둘뿐이다.
  · A20/A30 은 **인접 파라미터 확증용** — A25 가 통과해도 인접 k 중 하나가 ① 을 만족하지
    못하면 '파라미터 칼끝'으로 보아 채택 후보에서 뺀다(STRICT).
  · S 는 탐색적. 통과해도 단독 채택하지 않고 후속 사전등록 대상으로만 기록한다.
실거래 무변경. 출력 method_x.json + RESULT_JSON.
실행: python method_x.py [--no-fetch] [--universe]
"""
import importlib
import json
import math
import random
import statistics as st
import sys

import detlib
import intraday_lab as ilab
import method_s as ms
import method_t as mt
import regime_switch as rs
import sizing as sz
import sizing_study as ss

FEE = mt.FEE
STOP_D = mt.STOP_LOSS_PCT          # 0.08 — 현행 고정 손절
MAX_HOLD = mt.MAX_HOLD             # 30
PATS = mt.PATS

# ── arm 파라미터 (사전 고정, 튜닝 금지) ────────────────────────────────────
ATR_PERIOD = 14
ATR_K = {"A20": 2.0, "A25": 2.5, "A30": 3.0}
# 손절폭 상·하한. 상한이 없으면 알트 급등락 구간에서 ATR 이 부풀어 손절이 과도해진다
# (카탈로그 지적). 하한이 없으면 저변동 구간에서 수수료·슬리피지에 먹힌다.
STOP_FLOOR, STOP_CAP = 0.03, 0.15
TIME_KEEP = 0.03                   # 30봉 시점 수익률이 +3% 이상이면
EXT_HOLD = 60                      # 60봉까지 1회 연장 (T arm)
ARMS = ["D", "A20", "A25", "A30", "T", "S"]
PRIMARY = ["A25", "T"]             # 주 판정
ADJACENT = {"A25": ["A20", "A30"]}  # STRICT 확증 대상

HOLDOUT_DAYS = 365
BOOT_N, BOOT_SEED = 2000, 7
MAX_POS = ss.MAX_POS
START_EQ = ss.START_EQ

REGMAP = {}


# ── 손절폭 산출 (모두 진입 봉까지만 본다 — 룩어헤드 없음) ──────────────────
def stop_pct_of(rows, si, direction, arm, atr):
    """arm 별 손절폭(진입가 대비 비율). 산출 불가면 None → 그 arm 은 진입하지 않는다."""
    if arm == "D" or arm == "T":
        return STOP_D
    base = rows[si]["c"]
    if base <= 0:
        return None
    if arm in ATR_K:
        a = atr[si]
        if not a or a <= 0:
            return None
        raw = ATR_K[arm] * a / base
    elif arm == "S":
        # 패턴 무효화 지점 — 신호봉과 직전봉의 극값. 이 지점을 넘으면 '패턴이 틀렸다'.
        lo = min(rows[si]["l"], rows[si - 1]["l"]) if si >= 1 else rows[si]["l"]
        hi = max(rows[si]["h"], rows[si - 1]["h"]) if si >= 1 else rows[si]["h"]
        raw = (base - lo) / base if direction == "long" else (hi - base) / base
        if raw <= 0:
            return None
    else:
        return None
    return max(STOP_FLOOR, min(STOP_CAP, raw))


def outcome_x(rows, si, direction, opp_set, arm, stop):
    """
    (ret, hold, reason). 손절폭만 arm 값을 쓰고 나머지 청산 사유는 방식D 와 동일.
    T arm 은 시간 청산만 조건화한다(수익 중이면 EXT_HOLD 까지 1회 연장).
    같은 봉에서 손절과 다른 사유가 겹치면 **손절 우선**(레포 관례).
    """
    base = rows[si]["c"]
    is_long = direction == "long"
    entry_reg = REGMAP.get(rows[si]["date"])
    hard = MAX_HOLD if arm != "T" else EXT_HOLD
    end = min(si + hard, len(rows) - 1)

    for j in range(si + 1, end + 1):
        if is_long:
            if rows[j]["l"] <= base * (1 - stop):
                return -stop - FEE, j - si, "stop"
        else:
            if rows[j]["h"] >= base * (1 + stop):
                return -stop - FEE, j - si, "stop"
        regsw = REGMAP.get(rows[j]["date"]) not in (None, entry_reg)
        if j in opp_set or regsw:
            c = rows[j]["c"]
            r = (c - base) / base if is_long else (base - c) / base
            return r - FEE, j - si, ("opp_signal" if j in opp_set else "regime_switch")
        # 조건부 시간 청산: 30봉 시점에서 수익이 문턱 미만이면 여기서 끝낸다.
        if arm == "T" and j - si == MAX_HOLD:
            c = rows[j]["c"]
            r = (c - base) / base if is_long else (base - c) / base
            if r < TIME_KEEP:
                px = rows[j]["o"] if j == si + MAX_HOLD else c
                rr = (px - base) / base if is_long else (base - px) / base
                return rr - FEE, j - si, "maxhold"

    px = rows[end]["o"]
    r = (px - base) / base if is_long else (base - px) / base
    return r - FEE, end - si, ("maxhold_ext" if arm == "T" and end - si > MAX_HOLD else "maxhold")


# ── 자산곡선 — 실거래 사이징 (arm 의 stop_pct 를 그대로 넘긴다) ─────────────
def equity_curve(trades, span_days=None):
    """
    trades: [(entry_date, exit_date, ret, hold, reason, stop_pct, vol[, size_mult])] 시간순 무관.
    sizing.risk_based_size 로 실거래와 같은 규칙(RISK_FRAC/LEV_CAP/변동성 타겟팅)을 쓴다.
    **손절폭이 arm 마다 다른 것이 명목가에 반영되는 것이 이 시험의 핵심**이다.

    span_days: CAGR 을 연율화할 기간(일). 기본 None 이면 **그 arm 자신의 첫~마지막 거래
    간격**을 쓴다 — method_x 처럼 arm 마다 거래 집합이 사실상 같은 시험에서는 문제가 없다.
    그러나 arm 이 서로 다른 신호를 잡는 시험(validate_routing)에서는 arm 마다 간격이 달라져
    **연율화 분모가 달라진다**: 거래가 짧은 구간에 몰린 arm 은 같은 손실이 훨씬 큰 CAGR 로
    부풀려진다(실측: holdout 41건 arm 이 MDD -36.6% 인데 CAGR -92.2%). 그런 비교에서는
    공통 창을 넘겨 분모를 맞춘다.
    """
    if not trades:
        return None
    evs = []
    for i, t in enumerate(trades):
        evs.append((ss._dnum(t[0]), 0, i))
        evs.append((ss._dnum(t[1]), -1, i))
    evs.sort()
    equity = free = START_EQ
    open_pos, peak, mdd = {}, START_EQ, 0.0
    taken = skipped = 0
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
            if len(open_pos) >= MAX_POS:
                skipped += 1; continue
            stop, vol = trades[idx][5], trades[idx][6]
            vs = sz.vol_scale_raw(vol) / sz.VOL_S_NORM if (sz.VOL_TARGETING and sz.VOL_S_NORM) else 1.0
            # 선택 8번째 원소 size_mult — 오버레이 arm(method_b) 이 거래별 배율을 준다. 없으면 1.0.
            # vol_scale 에 곱하면 risk_usd 에 선형으로 걸려 명목가만 바뀐다(손절가·레버리지 불변) —
            # 실거래 REGIME_CAP_MULT 오버레이와 같은 자리다.
            if len(trades[idx]) > 7 and trades[idx][7] is not None:
                vs *= trades[idx][7]
            open_notional = sum(n for _, n in open_pos.values())
            r = sz.risk_based_size(equity, free, stop, vol_scale=vs,
                                   open_notional=open_notional)
            if r is None:
                skipped += 1; continue
            free -= r["margin_usd"]
            open_pos[idx] = (r["margin_usd"], r["notional"])
            taken += 1
    days = span_days if span_days else (max(1, evs[-1][0] - evs[0][0]) if evs else 1)
    days = max(1, days)
    yrs = days / 365.25
    cagr = (equity / START_EQ) ** (1 / yrs) - 1 if equity > 0 else -1.0
    return dict(final=equity, cagr=cagr, mdd=mdd,
                calmar=(cagr / abs(mdd) if mdd < 0 else float("inf")),
                taken=taken, skipped=skipped)


# ── 통계 (method_r 과 동일한 도구) ──────────────────────────────────────────
def boot_p(diffs, n=BOOT_N, seed=BOOT_SEED):
    if len(diffs) < 2:
        return 1.0
    rng = random.Random(seed)
    k = len(diffs)
    return sum(1 for _ in range(n)
               if sum(diffs[rng.randrange(k)] for _ in range(k)) / k <= 0) / n


def divergence(base, arm):
    idx = [i for i, (b, a) in enumerate(zip(base, arm))
           if b[3] != a[3] or b[4] != a[4] or abs(b[2] - a[2]) > 1e-12]
    if not idx:
        return dict(n=0, arm_wins=0, arm_losses=0)
    d = [arm[i][2] - base[i][2] for i in idx]
    return dict(n=len(idx), share=len(idx) / len(base), mean_diff=st.mean(d),
                base_mean=st.mean(base[i][2] for i in idx),
                arm_mean=st.mean(arm[i][2] for i in idx),
                arm_wins=sum(1 for x in d if x > 1e-12),
                arm_losses=sum(1 for x in d if x < -1e-12),
                base_reasons=_count(base[i][4] for i in idx),
                arm_reasons=_count(arm[i][4] for i in idx))


def halves(base, arm):
    order = sorted(range(len(base)), key=lambda i: base[i][0])
    if len(order) < 4:
        return dict(n1=0, d1=0.0, n2=0, d2=0.0)
    h = len(order) // 2
    a, b = order[:h], order[h:]
    return dict(n1=len(a), d1=st.mean(arm[i][2] - base[i][2] for i in a),
                n2=len(b), d2=st.mean(arm[i][2] - base[i][2] for i in b))


def _count(it):
    out = {}
    for x in it:
        out[x] = out.get(x, 0) + 1
    return out


def _arm_stats(base, arm, idx, m):
    b, a = [base[i] for i in idx], [arm[i] for i in idx]
    if not b:
        return None
    rec = dict(per_trade=mt.summ([(x[0], x[1], x[2], x[3], x[4]) for x in a]),
               equity=equity_curve(sorted(a, key=lambda t: t[0])),
               reasons=_count(t[4] for t in a),
               mean_stop=st.mean(t[5] for t in a))
    if m != "D":
        br, ar = [t[2] for t in b], [t[2] for t in a]
        p = mt.paired_stats(br, ar)
        p["boot_p"] = boot_p([x - y for x, y in zip(ar, br)])
        rec["paired_vs_D"] = p
        rec["divergence"] = divergence(b, a)
        rec["halves"] = halves(b, a)
    return rec


def run_pattern(label, direction, detmod, oppmod, tf, cutoff, syms):
    mod = importlib.import_module(detmod)
    opp = importlib.import_module(oppmod) if oppmod else None
    arms = {m: [] for m in ARMS}
    n_skip_stop = 0
    for sym in syms:
        try:
            rows = detlib.load_ohlcv(sym, tf)
        except (FileNotFoundError, RuntimeError):
            continue
        if len(rows) < 40:
            continue
        atr = ilab.atr_series(rows, ATR_PERIOD)
        opp_set = set(opp.detect(rows)) if opp else set()
        for si in mod.detect(rows):
            if si + 1 >= len(rows):
                continue
            stops = {m: stop_pct_of(rows, si, direction, m, atr) for m in ARMS}
            # 한 arm 이라도 손절폭을 못 구하면 **모든 arm 에서 이 신호를 뺀다** —
            # 짝지음 비교는 같은 신호 집합 위에서만 성립한다.
            if any(v is None for v in stops.values()):
                n_skip_stop += 1
                continue
            vol = sz.realized_vol(rows, si, tf=tf)
            for m in ARMS:
                ret, hold, reason = outcome_x(rows, si, direction, opp_set, m, stops[m])
                xi = min(si + hold, len(rows) - 1)
                arms[m].append((rows[si]["date"], rows[xi]["date"], ret, hold, reason,
                                stops[m], vol))
    if not arms["D"]:
        return None
    base = arms["D"]
    tr = [i for i, t in enumerate(base) if t[0] < cutoff]
    ho = [i for i, t in enumerate(base) if t[0] >= cutoff]
    out = {m: dict(train=_arm_stats(base, arms[m], tr, m),
                   holdout=_arm_stats(base, arms[m], ho, m)) for m in ARMS}
    out["_n_train"], out["_n_holdout"], out["_n_skip_stop"] = len(tr), len(ho), n_skip_stop
    return out


def _pool(results, split, m):
    items = []
    for lb, res in results.items():
        if lb.startswith("_"):
            continue
        r = res[m][split]
        if not r:
            continue
        p = r["paired_vs_D"]
        items.append((p["n"], p["mean_diff"], p.get("sd_diff", 0.0), r["divergence"], r["halves"]))
    if not items:
        return None
    tot = sum(x[0] for x in items)
    mean_diff = sum(x[0] * x[1] for x in items) / tot
    var = sum((x[0] - 1) * (x[2] ** 2) for x in items) / max(1, tot - len(items))
    t = mean_diff / math.sqrt(var / tot) if var > 0 else 0.0
    # 패턴 재표본 부트스트랩 — 패턴을 단위로 뽑아 '한 패턴이 끌고 가는' 결과를 걸러낸다.
    rng = random.Random(BOOT_SEED)
    le = 0
    for _ in range(BOOT_N):
        pick = [items[rng.randrange(len(items))] for _ in items]
        w = sum(x[0] for x in pick)
        if sum(x[0] * x[1] for x in pick) / w <= 0:
            le += 1
    dv = dict(n=sum(x[3]["n"] for x in items),
              arm_wins=sum(x[3]["arm_wins"] for x in items),
              arm_losses=sum(x[3]["arm_losses"] for x in items))
    n1 = sum(x[4]["n1"] for x in items); n2 = sum(x[4]["n2"] for x in items)
    return dict(n=tot, n_patterns=len(items), mean_diff=mean_diff, t=t, boot_p=le / BOOT_N,
                divergence=dv,
                halves=dict(n1=n1, n2=n2,
                            d1=sum(x[4]["d1"] * x[4]["n1"] for x in items) / n1 if n1 else 0.0,
                            d2=sum(x[4]["d2"] * x[4]["n2"] for x in items) / n2 if n2 else 0.0))


def verdict(results, arm):
    tr = results["_pooled"]["train"].get(arm)
    ho = results["_pooled"]["holdout"].get(arm)
    if not tr:
        return dict(pass_=False, reason="no train")
    pats = [lb for lb in results if not lb.startswith("_") and results[lb][arm]["train"]]
    c1 = tr["mean_diff"] > 0 and (tr["t"] > 2.0 or tr["boot_p"] < 0.05)
    cw = sum(1 for lb in pats
             if results[lb][arm]["train"]["equity"]["cagr"] > results[lb]["D"]["train"]["equity"]["cagr"])
    c2 = cw >= 4
    c3 = all(results[lb][arm]["train"]["paired_vs_D"]["t"] >= -2.0 for lb in pats)
    dv = tr["divergence"]
    c4 = dv["n"] > 0 and dv["arm_wins"] > dv["arm_losses"]
    hv = tr["halves"]
    c5 = hv["d1"] > 0 and hv["d2"] > 0
    train_pass = bool(c1 and c2 and c3 and c4 and c5)
    c6 = bool(ho) and ho["mean_diff"] > 0
    c7 = bool(ho) and ho["divergence"]["arm_wins"] > ho["divergence"]["arm_losses"]
    return dict(pass_=bool(train_pass and c6 and c7), train_pass=train_pass,
                c1_pooled_sig=c1, c2_cagr_wins=cw, c3_no_pattern_hurt=c3,
                c4_divergence_winrate=c4, c5_halves_both_pos=c5,
                c6_holdout_diff_pos=c6, c7_holdout_divergence=c7)


def _print_split(res, split):
    print(f"  [{split}]")
    print(f"  {'arm':<5}{'n':>5}{'평균손절':>9}{'건당평균':>10}{'중앙':>9}{'승률':>7}{'보유':>7}"
          f"  |{'짝지음차이':>11}{'t':>7}{'boot_p':>8}{'승/패':>10}"
          f"  |{'분기n':>6}{'분기승률':>9}  |{'전반':>8}{'후반':>8}"
          f"  |{'CAGR':>8}{'MDD':>8}")
    print("  " + "-" * 130)
    for m in ARMS:
        r = res[m][split]
        if not r:
            print(f"  {m:<5}    0  (해당 분할 거래 없음)")
            continue
        s, eq = r["per_trade"], r["equity"]
        if m == "D":
            pair = f"{'(기준)':>11}{'':>7}{'':>8}{'':>10}"
            dvs, hv = f"{'-':>6}{'-':>9}", f"{'-':>8}{'-':>8}"
        else:
            p, dv, h = r["paired_vs_D"], r["divergence"], r["halves"]
            pair = (f"{p['mean_diff']*100:>+10.2f}%{p['t']:>7.2f}{p['boot_p']:>8.3f}"
                    f"{p['wins']:>5}/{p['losses']:<4}")
            tot = dv["arm_wins"] + dv["arm_losses"]
            dvs = f"{dv['n']:>6}{(dv['arm_wins']/tot if tot else 0):>8.0%}"
            hv = f"{h['d1']*100:>+7.2f}%{h['d2']*100:>+7.2f}%"
        print(f"  {m:<5}{s['n']:>5}{r['mean_stop']*100:>8.1f}%{s['mean']*100:>+9.2f}%"
              f"{s['median']*100:>+8.2f}%{s['winrate']:>7.0%}{s['avghold']:>7.1f}"
              f"  |{pair}  |{dvs}  |{hv}"
              f"  |{eq['cagr']*100:>+7.1f}%{eq['mdd']*100:>+7.1f}%")


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    ms.UNIVERSE_MODE = "--universe" in argv
    syms = ms.symbols()
    print(f"[표본] {len(syms)}종목 ({'유니버스 80' if ms.UNIVERSE_MODE else '메이저'})")
    if "--no-fetch" not in argv:
        ms.ensure_data(mt.FETCH_DAYS, syms)
    global REGMAP
    REGMAP = rs.build_regime_map()
    mt.REGMAP = REGMAP
    from datetime import date as _date, timedelta as _td
    last = max(REGMAP) if REGMAP else "2026-01-01"
    cutoff = (_date(*(int(x) for x in last.split("-"))) - _td(days=HOLDOUT_DAYS)).isoformat()
    print(f"[분할] train < {cutoff} <= holdout (마지막 {HOLDOUT_DAYS}일)")
    print(f"[설정] ATR{ATR_PERIOD} k={list(ATR_K.values())} clip[{STOP_FLOOR:.0%},{STOP_CAP:.0%}] "
          f"| T: {MAX_HOLD}봉에서 수익 >= {TIME_KEEP:.0%} 면 {EXT_HOLD}봉까지 연장 "
          f"| 사이징 risk={sz.RISK_FRAC:.1%} lev<={sz.LEV_CAP} voltarget={sz.VOL_TARGETING}")

    results = {}
    for label, direction, detmod, oppmod, tf in PATS:
        r = run_pattern(label, direction, detmod, oppmod, tf, cutoff, syms)
        if r:
            results[label] = r
            skip = r["_n_skip_stop"]
            extra = f" (손절폭 산출불가 {skip}건 제외)" if skip else ""
            print(f"  [{label}] train {r['_n_train']} / holdout {r['_n_holdout']}{extra}", flush=True)
    if not results:
        print("거래 없음"); return
    results["_pooled"] = {sp: {m: _pool(results, sp, m) for m in ARMS if m != "D"}
                          for sp in ("train", "holdout")}

    print("=" * 132)
    print("청산 변형 — D(현행) vs ATR손절(A20/A25/A30) / 조건부시간손절(T) / 구조적손절(S)")
    print("=" * 132)
    for lb in [x for x in results if not x.startswith("_")]:
        print(f"\n[{lb}]")
        for sp in ("train", "holdout"):
            _print_split(results[lb], sp)

    print("\n" + "=" * 132)
    print("합산 (패턴별 표본수 가중) + 사전 등록 판정")
    print("=" * 132)
    verdicts = {}
    for m in ARMS:
        if m == "D":
            continue
        v = verdict(results, m)
        verdicts[m] = v
        tr = results["_pooled"]["train"].get(m)
        ho = results["_pooled"]["holdout"].get(m)
        if not tr:
            print(f"  {m}: train 없음"); continue
        tag = "주판정" if m in PRIMARY else ("인접확증" if m in sum(ADJACENT.values(), []) else "탐색")
        print(f"  {m:<4}({tag}) train n={tr['n']} 짝지음 {tr['mean_diff']*100:+.3f}%p "
              f"t={tr['t']:.2f} boot_p={tr['boot_p']:.3f} | CAGR우위 {v['c2_cagr_wins']}/7 "
              f"| 분기 {tr['divergence']['n']}건 승률 "
              f"{(tr['divergence']['arm_wins']/max(1,tr['divergence']['arm_wins']+tr['divergence']['arm_losses'])):.0%} "
              f"| 전반 {tr['halves']['d1']*100:+.2f}%p 후반 {tr['halves']['d2']*100:+.2f}%p")
        print(f"        기준 ①{'O' if v['c1_pooled_sig'] else 'X'} ②{'O' if v['c2_cagr_wins']>=4 else 'X'} "
              f"③{'O' if v['c3_no_pattern_hurt'] else 'X'} ④{'O' if v['c4_divergence_winrate'] else 'X'} "
              f"⑤{'O' if v['c5_halves_both_pos'] else 'X'} → train {'통과' if v['train_pass'] else '탈락'}"
              + (f" | holdout ⑥{'O' if v['c6_holdout_diff_pos'] else 'X'} ⑦{'O' if v['c7_holdout_divergence'] else 'X'}"
                 f" (n={ho['n'] if ho else 0}, 차이 {ho['mean_diff']*100:+.3f}%p)" if v['train_pass'] and ho else "")
              + f"  => {'PASS' if v['pass_'] else 'REJECT'}")

    print("\n[다중검정 STRICT] 주 판정 arm 만 채택 후보 — ATR 계열은 인접 k 확증 필요")
    adopt = []
    for m in PRIMARY:
        v = verdicts.get(m)
        if not v or not v["pass_"]:
            print(f"  {m}: 사전 기준 미통과 → 채택 후보 아님"); continue
        adj = ADJACENT.get(m, [])
        ok_adj = [a for a in adj if results["_pooled"]["train"].get(a)
                  and results["_pooled"]["train"][a]["mean_diff"] > 0
                  and (results["_pooled"]["train"][a]["t"] > 2.0
                       or results["_pooled"]["train"][a]["boot_p"] < 0.05)]
        if adj and not ok_adj:
            print(f"  {m}: 통과했으나 인접 k {adj} 가 모두 ① 미달 → 파라미터 칼끝, 채택 후보 제외")
            continue
        adopt.append(m)
        print(f"  {m}: **채택 후보** (사용자 결정)" + (f" | 인접 확증 {ok_adj}" if adj else ""))
    if not adopt:
        print("  => 채택 후보 없음")

    json.dump(dict(config=dict(atr_k=ATR_K, floor=STOP_FLOOR, cap=STOP_CAP,
                              time_keep=TIME_KEEP, ext_hold=EXT_HOLD, cutoff=cutoff,
                              risk_frac=sz.RISK_FRAC, lev_cap=sz.LEV_CAP,
                              n_symbols=len(syms), universe=ms.UNIVERSE_MODE),
                   results=results, verdicts=verdicts, adopt=adopt),
              open("method_x.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1,
              default=lambda o: sorted(o) if isinstance(o, (set, frozenset)) else str(o))
    print("\n[저장] method_x.json")
    print("RESULT_JSON: " + json.dumps(dict(
        adopt=adopt,
        pooled={m: dict(diff=round(results["_pooled"]["train"][m]["mean_diff"], 5),
                        t=round(results["_pooled"]["train"][m]["t"], 2),
                        boot_p=results["_pooled"]["train"][m]["boot_p"])
                for m in ARMS if m != "D" and results["_pooled"]["train"].get(m)}),
        separators=(",", ":")))


if __name__ == "__main__":
    main()
