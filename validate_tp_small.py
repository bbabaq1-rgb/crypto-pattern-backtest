"""
validate_tp_small.py — **작은 고정 익절(+1%) 복리** 사전 등록 시험 (2026-09-09, 사용자 지시
"응 돌려").

사용자 제안 원문: "10만원을 매일 하루씩 1퍼센트만 복리로 쌓아도 금액이 엄청커지잖아 …
포지션 진입했을때 무조건 플러스 1프로(레버리지 3프로)면 바로 익절되게".

즉 **진입 후 가격이 +1% 오르면 즉시 익절**(레버리지 3x 라 증거금 기준 +3%)하고, 그 돈을
그대로 다음 매매에 굴리는 규칙이다. 청산 사유를 배리어 둘(익절·손절)만 남긴다 —
레짐 전환·반대 신호·시간 청산 없음(사용자 표현 "무조건 … 바로 익절").

── 왜 이 시험이 필요한가 (레포 선행 결과로는 답이 안 나온다) ──────────────────
· method_t(2026-09-01)가 고정 익절을 기각했지만 **k=10~30%** 였고, 기각 기전이
  "오른쪽 꼬리 절단 — 회전율 2배로 빨라져도 복리 이득이 잘라낸 큰 승자를 보상 못함"이다.
  k=1% 는 회전율이 2배가 아니라 10배 안팎이라 그 기전이 그대로 옮겨오지 않는다.
· 반대로 **배리어 쌍은 그 자체로 가치를 만들지 않는다**: 무편향 랜덤워크에서
  P(+TP 먼저 도달) = SL/(TP+SL) 이고, 이때 기대값은 정확히 0(수수료 전)이다.
  1%/8% 면 88.89% 이고 왕복 수수료 0.2% 를 넘으려면 **91.11%** 가 필요하다.
  그래서 이 시험의 핵심 지표는 수익률이 아니라 **승률 리프트 = 실측승률 − SL/(TP+SL)** 이다.
  패턴이 진입 직후 상방으로 밀어주는 힘이 그만큼 있어야 한다.
· 사전 기록(결과 보기 전): 신호봉 프로필 연구(2026-09-07)에서 같은 달 안으로 demean 하면
  신호 직후의 상관이 −0.05~−0.09 로 **약간 음수**였다. 그래서 1%/8% 셀은 손익분기
  근처에서 **살짝 미달**할 것으로 예상한다. 예상이 빗나가면 그대로 기록한다.

── 두 자산곡선을 함께 잰다 ──────────────────────────────────────────────────
P1 포트폴리오: 현행 실거래 규칙(sizing.risk_based_size, RISK_FRAC/LEV_CAP/변동성 타겟팅,
   MAX_POS 슬롯). arm 의 손절폭이 명목가에 반영된다(method_x 와 같은 프레임).
P2 **전용 포트 순차 복리**: 사용자 제안 그대로 — 별도 자금 한 덩이로 **한 번에 한
   포지션만**, 명목가 = 포트 전액 x 레버리지 3x, 청산되면 그 금액을 그대로 다음 매매에.
   equity *= (1 + LEV x ret). '10만원이 얼마가 되나'에 직접 답하는 곳이다.
   주의: 한 번에 하나라 **신호 대부분을 못 받는다**(먼저 온 것만). 순서 의존이 크다.

── 사전 등록 판정 (실행 전 고정) ────────────────────────────────────────────
**주 판정 셀은 (익절 1% / 손절 8%) 하나** — 사용자가 지정한 규칙 그대로다.
나머지 11셀은 **진단**이며, 사후에 그중에서 골라 '살았다'고 하지 않는다.
9개 전부 만족해야 PASS:
  1) train 짝지음(같은 신호에 D 와 이 규칙을 동시 적용) 평균차이 > 0 이고 (t > 2 또는 boot_p < 0.05)
  2) train 건당 평균 > 0
  3) **승률 리프트 > 0** — 실측 승률 > 랜덤워크 도달률 SL/(TP+SL)
  4) 마찰 스트레스(왕복 0.4%)에서도 건당 평균 > 0
  5) 전반/후반 짝지음 차이 둘 다 > 0
  6) P1 CAGR 우위 패턴 >= 4/7
  7) holdout 짝지음 차이 > 0
  8) holdout 건당 평균 > 0
  9) P2(전용 포트) CAGR 이 train·holdout 둘 다 > 0

**DEPLOY_ON_PASS=False — 통과해도 실거래 반영 없음.** 관찰 기간(~2026-10-06)이고,
청산 규칙 변경은 실주문 경로를 건드린다. 배포는 사용자 결정.
실거래 무변경. 출력 _tp_small.json + RESULT_JSON.
실행: python validate_tp_small.py [--no-fetch] [--majors]
"""
import importlib
import json
import math
import random
import statistics as st
import sys

import detlib
import method_s as ms
import method_t as mt
import method_x as mx
import regime_switch as rs
import sizing as sz

FEE = mt.FEE                       # 0.002 왕복 (동결 가정)
PATS = mt.PATS                     # 배포 7종 — method_t/x/r 과 같은 표본
STOP_D = mt.STOP_LOSS_PCT          # 0.08 현행 고정 손절

# ── 동결 파라미터 (결과를 보고 바꾸지 않는다) ───────────────────────────────
TP_LEVELS = (0.01, 0.02, 0.03)     # 익절 1/2/3%
SL_LEVELS = (0.01, 0.02, 0.04, 0.08)  # 손절 1/2/4/8% (8% = 현행)
PRIMARY = (0.01, 0.08)             # **주 판정 셀 — 사용자가 지정한 규칙**
MAX_SCAN = 250                     # 배리어 미도달 시 강제 청산까지의 봉 수(무한 보유 방지)
FRICTION = 0.004                   # 마찰 스트레스 왕복 0.4% (캐스케이드 내성 한계와 같은 값)
POT_LEV = 3                        # P2 전용 포트 레버리지 (사용자 지정 "레버리지 3프로")
POT_START = 100_000.0              # P2 시작 자금 (사용자 예시 10만원 — 단위는 무관)
HOLDOUT_DAYS = 365
BOOT_N, BOOT_SEED = 2000, 7
DEPLOY_ON_PASS = False             # 통과해도 실거래 반영 없음

REGMAP = {}


def cell_name(tp, sl):
    return f"T{round(tp*100)}S{round(sl*100)}"


CELLS = [(tp, sl) for tp in TP_LEVELS for sl in SL_LEVELS]
ARMS = ["D"] + [cell_name(tp, sl) for tp, sl in CELLS]
CELL_OF = {cell_name(tp, sl): (tp, sl) for tp, sl in CELLS}
PRIMARY_ARM = cell_name(*PRIMARY)


# ── 배리어 규칙 ─────────────────────────────────────────────────────────────
def rw_hit(tp, sl):
    """무편향 랜덤워크에서 손절보다 익절에 먼저 닿을 확률 = SL/(TP+SL).
    이 값에서 기대값은 정확히 0(수수료 전) — 배리어 폭 자체는 가치를 만들지 않는다."""
    return sl / (tp + sl)


def breakeven_win(tp, sl, fee=FEE):
    """수수료를 넘기려면 필요한 승률: w(tp-fee) - (1-w)(sl+fee) = 0."""
    return (sl + fee) / (tp + sl)


def outcome_tp(rows, si, direction, tp, sl):
    """
    (ret, hold, reason) — **배리어만**. 레짐·반대신호·시간 청산 없음.
    같은 봉에서 익절과 손절이 겹치면 **손절 우선**(레포 관례, 시장가 엔진에서 보수적).
    MAX_SCAN 봉까지 어느 배리어에도 안 닿으면 그 봉 시가로 청산('open').
    """
    base = rows[si]["c"]
    if base <= 0:
        return None
    is_long = direction == "long"
    end = min(si + MAX_SCAN, len(rows) - 1)
    for j in range(si + 1, end + 1):
        if is_long:
            if rows[j]["l"] <= base * (1 - sl):
                return -sl - FEE, j - si, "stop"
            if rows[j]["h"] >= base * (1 + tp):
                return tp - FEE, j - si, "target"
        else:
            if rows[j]["h"] >= base * (1 + sl):
                return -sl - FEE, j - si, "stop"
            if rows[j]["l"] <= base * (1 - tp):
                return tp - FEE, j - si, "target"
    px = rows[end]["o"]
    r = (px - base) / base if is_long else (base - px) / base
    return r - FEE, end - si, "open"


# ── P2 전용 포트 순차 복리 ──────────────────────────────────────────────────
def pot_curve(trades, lev=POT_LEV, start=POT_START):
    """
    trades: [(entry, exit, ret, ...)] — 시간순 정렬 후 **한 번에 하나만** 잡는다.
    포지션이 열려 있는 동안 도착한 신호는 버린다(사용자 규칙: 한 덩이 자금).
    equity *= (1 + lev x ret). ret 에 이미 왕복 수수료가 들어 있다.
    """
    if not trades:
        return None
    # 진입 시각만으로 정렬한다 — 청산 시각을 2차 키로 쓰면 같은 시각 신호 중 '먼저 끝날
    # 거래'(= 빠른 익절)를 고르는 셈이라 미래를 쓴다(2026-09-09 tp_1h 판에서 발견).
    # 동률은 입력 순서로 깬다. 이 판의 P2 는 전 arm 이 0 이었으므로 결론은 불변이고,
    # 편향이 낙관 쪽이었으므로 '파산' 결론은 오히려 강화된다.
    order = sorted(range(len(trades)), key=lambda i: (mx._tnum(trades[i][0]), i))
    seq = [trades[i] for i in order]
    eq, peak, mdd = start, start, 0.0
    busy_until = None
    taken = skipped = 0
    first = last = None
    for t in seq:
        e, x = mx._tnum(t[0]), mx._tnum(t[1])
        if busy_until is not None and e < busy_until:
            skipped += 1
            continue
        eq *= (1 + lev * t[2])
        taken += 1
        busy_until = x if x > e else e + 1e-9
        if first is None:
            first = e
        last = x
        if eq <= 0:
            eq = 0.0
            break
        peak = max(peak, eq)
        mdd = min(mdd, eq / peak - 1)
    if not taken:
        return None
    days = max(1.0, (last or 0) - (first or 0))
    yrs = days / 365.25
    cagr = (eq / start) ** (1 / yrs) - 1 if eq > 0 else -1.0
    return dict(final=eq, mult=eq / start, cagr=cagr, mdd=mdd,
                calmar=(cagr / abs(mdd) if mdd < 0 else float("inf")),
                taken=taken, skipped=skipped, days=days)


# ── 진단: 같은 배리어를 **무작위 진입**에 적용한 베이스라인 ─────────────────
# 랜덤워크 도달률 SL/(TP+SL) 은 '무편향' 가정이다. 실제 알트는 표본 구간에서 드리프트가
# 음수라 실측 승률이 그 아래로 내려갈 수 있다. 그러면 '패턴이 나쁘다'와 '배리어+드리프트가
# 나쁘다'가 섞인다. 같은 코호트에서 무작위 시점에 진입해 **같은 배리어**로 청산한 값을
# 옆에 놓아야 둘이 갈라진다. 판정 기준은 아니고 해석용이다(사후에 이걸로 뒤집지 않는다).
RAND_N, RAND_SEED = 4000, 11


def random_baseline(syms, tf, direction, cutoff):
    rng = random.Random(RAND_SEED)
    pool = []
    for sym in syms:
        try:
            rows = detlib.load_ohlcv(sym, tf)
        except (FileNotFoundError, RuntimeError):
            continue
        if len(rows) < 40:
            continue
        for i in range(30, len(rows) - 2):
            pool.append((sym, rows, i))
    if not pool:
        return None
    pick = pool if len(pool) <= RAND_N else rng.sample(pool, RAND_N)
    out = {sp: {} for sp in ("train", "holdout")}
    for tp, sl in CELLS:
        m = cell_name(tp, sl)
        buckets = {"train": [], "holdout": []}
        for _, rows, i in pick:
            o = outcome_tp(rows, i, direction, tp, sl)
            if o is None:
                continue
            buckets["train" if rows[i]["date"] < cutoff else "holdout"].append(o[0])
        for sp, rr in buckets.items():
            out[sp][m] = (dict(n=len(rr), mean=st.mean(rr),
                               winrate=sum(1 for x in rr if x > 0) / len(rr))
                          if rr else None)
    return out


# ── 통계 ────────────────────────────────────────────────────────────────────
def holm(pvals):
    """Holm step-down. None 은 가족에서 뺀다."""
    items = sorted(((k, v) for k, v in pvals.items() if v is not None), key=lambda x: x[1])
    m, out, prev = len(items), {}, 0.0
    for i, (k, p) in enumerate(items):
        prev = max(prev, min(1.0, (m - i) * p))
        out[k] = prev
    return out


def stressed(rets, fric=FRICTION):
    """왕복 마찰을 fric 로 올렸을 때의 건당 평균 (동결 가정 FEE 와의 차이만큼 더 뺀다)."""
    if not rets:
        return None
    return st.mean(rets) - (fric - FEE)


def _arm_stats(base, arm, idx, name):
    b, a = [base[i] for i in idx], [arm[i] for i in idx]
    if not b:
        return None
    rets = [t[2] for t in a]
    rec = dict(per_trade=mt.summ([(x[0], x[1], x[2], x[3], x[4]) for x in a]),
               equity=mx.equity_curve(sorted(a, key=lambda t: mx._tnum(t[0]))),
               pot=pot_curve(a),
               reasons=mx._count(t[4] for t in a),
               mean_stressed=stressed(rets),
               mean_stop=st.mean(t[5] for t in a),
               _trades=a)          # 합산 곡선용 — json 저장 전에 뺀다
    if name != "D":
        tp, sl = CELL_OF[name]
        wr = rec["per_trade"]["winrate"]
        rec["rw_hit"] = rw_hit(tp, sl)
        rec["breakeven_win"] = breakeven_win(tp, sl)
        rec["lift"] = wr - rec["rw_hit"]
        rec["lift_be"] = wr - rec["breakeven_win"]
        p = mt.paired_stats([x[2] for x in b], rets)
        p["boot_p"] = mx.boot_p([x - y for x, y in zip(rets, [x[2] for x in b])])
        rec["paired_vs_D"] = p
        rec["divergence"] = mx.divergence(b, a)
        rec["halves"] = mx.halves(b, a)
    return rec


def run_pattern(label, direction, detmod, oppmod, tf, cutoff, syms):
    mod = importlib.import_module(detmod)
    opp = importlib.import_module(oppmod) if oppmod else None
    arms = {m: [] for m in ARMS}
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
            outs = {}
            ok = True
            for m in ARMS:
                if m == "D":
                    o = mx.outcome_x(rows, si, direction, opp_set, "D", STOP_D)
                else:
                    tp, sl = CELL_OF[m]
                    o = outcome_tp(rows, si, direction, tp, sl)
                if o is None:
                    ok = False
                    break
                outs[m] = o
            # 한 arm 이라도 산출 불가면 **모든 arm 에서 이 신호를 뺀다** —
            # 짝지음은 같은 신호 집합 위에서만 성립한다.
            if not ok:
                continue
            vol = sz.realized_vol(rows, si, tf=tf)
            for m in ARMS:
                ret, hold, reason = outs[m]
                xi = min(si + hold, len(rows) - 1)
                stop = STOP_D if m == "D" else CELL_OF[m][1]
                arms[m].append((rows[si]["date"], rows[xi]["date"], ret, hold, reason, stop, vol))
    if not arms["D"]:
        return None
    base = arms["D"]
    tr = [i for i, t in enumerate(base) if t[0] < cutoff]
    ho = [i for i, t in enumerate(base) if t[0] >= cutoff]
    out = {m: dict(train=_arm_stats(base, arms[m], tr, m),
                   holdout=_arm_stats(base, arms[m], ho, m)) for m in ARMS}
    out["_n_train"], out["_n_holdout"] = len(tr), len(ho)
    return out


def pool(results, split, m):
    """패턴별 표본수 가중 합산 (method_x._pool 과 같은 구조) + 배리어 지표."""
    items, rets_all = [], []
    for lb, res in results.items():
        if lb.startswith("_"):
            continue
        r = res[m][split]
        if not r:
            continue
        p = r["paired_vs_D"]
        items.append((p["n"], p["mean_diff"], p.get("sd_diff", 0.0), r["divergence"],
                      r["halves"], r["per_trade"], lb))
    if not items:
        return None
    tot = sum(x[0] for x in items)
    mean_diff = sum(x[0] * x[1] for x in items) / tot
    var = sum((x[0] - 1) * (x[2] ** 2) for x in items) / max(1, tot - len(items))
    t = mean_diff / math.sqrt(var / tot) if var > 0 else 0.0
    rng = random.Random(BOOT_SEED)
    le = 0
    for _ in range(BOOT_N):
        pick = [items[rng.randrange(len(items))] for _ in items]
        w = sum(x[0] for x in pick)
        if sum(x[0] * x[1] for x in pick) / w <= 0:
            le += 1
    n1 = sum(x[4]["n1"] for x in items); n2 = sum(x[4]["n2"] for x in items)
    tp, sl = CELL_OF[m]
    wr = sum(x[0] * x[5]["winrate"] for x in items) / tot
    mean = sum(x[0] * x[5]["mean"] for x in items) / tot
    return dict(n=tot, n_patterns=len(items), mean_diff=mean_diff, t=t, boot_p=le / BOOT_N,
                mean=mean, mean_stressed=mean - (FRICTION - FEE), winrate=wr,
                rw_hit=rw_hit(tp, sl), breakeven_win=breakeven_win(tp, sl),
                lift=wr - rw_hit(tp, sl), lift_be=wr - breakeven_win(tp, sl),
                avghold=sum(x[0] * x[5]["avghold"] for x in items) / tot,
                divergence=dict(n=sum(x[3]["n"] for x in items),
                                arm_wins=sum(x[3]["arm_wins"] for x in items),
                                arm_losses=sum(x[3]["arm_losses"] for x in items)),
                halves=dict(n1=n1, n2=n2,
                            d1=sum(x[4]["d1"] * x[4]["n1"] for x in items) / n1 if n1 else 0.0,
                            d2=sum(x[4]["d2"] * x[4]["n2"] for x in items) / n2 if n2 else 0.0))


def verdict(results, pooled, pots, arm):
    tr, ho = pooled["train"].get(arm), pooled["holdout"].get(arm)
    if not tr:
        return dict(pass_=False, reason="no train")
    pats = [lb for lb in results if not lb.startswith("_") and results[lb][arm]["train"]]
    c1 = tr["mean_diff"] > 0 and (tr["t"] > 2.0 or tr["boot_p"] < 0.05)
    c2 = tr["mean"] > 0
    c3 = tr["lift"] > 0
    c4 = tr["mean_stressed"] > 0
    hv = tr["halves"]
    c5 = hv["d1"] > 0 and hv["d2"] > 0
    cw = sum(1 for lb in pats
             if results[lb][arm]["train"]["equity"]
             and results[lb]["D"]["train"]["equity"]
             and results[lb][arm]["train"]["equity"]["cagr"]
             > results[lb]["D"]["train"]["equity"]["cagr"])
    c6 = cw >= 4
    c7 = bool(ho) and ho["mean_diff"] > 0
    c8 = bool(ho) and ho["mean"] > 0
    pt, ph = pots["train"].get(arm), pots["holdout"].get(arm)
    c9 = bool(pt) and bool(ph) and pt["cagr"] > 0 and ph["cagr"] > 0
    return dict(pass_=bool(c1 and c2 and c3 and c4 and c5 and c6 and c7 and c8 and c9),
                c1_paired_sig=c1, c2_mean_pos=c2, c3_lift_pos=c3, c4_friction=c4,
                c5_halves=c5, c6_cagr_wins=cw, c7_holdout_diff=c7, c8_holdout_mean=c8,
                c9_pot_cagr=c9)


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    ms.UNIVERSE_MODE = "--majors" not in argv       # 기본 유니버스 80 (동결)
    syms = ms.symbols()
    print(f"[표본] {len(syms)}종목 ({'유니버스 80' if ms.UNIVERSE_MODE else '메이저'}) "
          f"· 패턴 {len(PATS)}종")
    if "--no-fetch" not in argv:
        ms.ensure_data(mt.FETCH_DAYS, syms)
    global REGMAP
    REGMAP = rs.build_regime_map()
    mt.REGMAP = mx.REGMAP = REGMAP
    from datetime import date as _date, timedelta as _td
    last = max(REGMAP) if REGMAP else "2026-01-01"
    cutoff = (_date(*(int(x) for x in last.split("-"))) - _td(days=HOLDOUT_DAYS)).isoformat()
    print(f"[분할] train < {cutoff} <= holdout (마지막 {HOLDOUT_DAYS}일)")
    print(f"[격자] 익절 {[f'{x:.0%}' for x in TP_LEVELS]} x 손절 {[f'{x:.0%}' for x in SL_LEVELS]} "
          f"= {len(CELLS)}셀 | **주 판정 {PRIMARY_ARM}** (익절 {PRIMARY[0]:.0%}/손절 {PRIMARY[1]:.0%})")
    print(f"[규칙] 배리어만 — 레짐·반대신호·시간 청산 없음 | 미도달 시 {MAX_SCAN}봉에서 강제청산")
    print(f"[비용] 왕복 {FEE:.1%} (동결) / 스트레스 {FRICTION:.1%} "
          f"| P1 사이징 risk={sz.RISK_FRAC:.1%} lev<={sz.LEV_CAP} "
          f"| P2 전용포트 {POT_LEV}x 시작 {POT_START:,.0f}")
    print(f"[반영] DEPLOY_ON_PASS={DEPLOY_ON_PASS} — 통과해도 실거래 변경 없음\n")

    results = {}
    for label, direction, detmod, oppmod, tf in PATS:
        r = run_pattern(label, direction, detmod, oppmod, tf, cutoff, syms)
        if r:
            results[label] = r
            print(f"  [{label}] train {r['_n_train']} / holdout {r['_n_holdout']}", flush=True)
    if not results:
        print("거래 없음"); return

    pooled = {sp: {m: pool(results, sp, m) for m in ARMS if m != "D"}
              for sp in ("train", "holdout")}

    # 합산 곡선 — 전 패턴 거래를 한 계좌에 넣는다. P1 은 슬롯·증거금이 있는 실거래 사이징,
    # P2 는 사용자 제안 그대로 한 번에 한 포지션인 전용 포트.
    pot_trades = {sp: {m: [] for m in ARMS} for sp in ("train", "holdout")}
    for lb, res in results.items():
        if lb.startswith("_"):
            continue
        for m in ARMS:
            for sp in ("train", "holdout"):
                r = res[m][sp]
                if r:
                    pot_trades[sp][m] += r.pop("_trades", [])
    pots = {sp: {m: pot_curve(pot_trades[sp][m]) for m in ARMS} for sp in ("train", "holdout")}
    p1 = {sp: {m: (mx.equity_curve(sorted(pot_trades[sp][m], key=lambda x: mx._tnum(x[0])))
                   if pot_trades[sp][m] else None) for m in ARMS}
          for sp in ("train", "holdout")}
    # D 기준선 요약 (합산)
    base_sum = {}
    for sp in ("train", "holdout"):
        rows = [results[lb]["D"][sp] for lb in results if not lb.startswith("_")
                and results[lb]["D"][sp]]
        n = sum(r["per_trade"]["n"] for r in rows)
        base_sum[sp] = dict(n=n,
                            mean=sum(r["per_trade"]["n"] * r["per_trade"]["mean"] for r in rows) / n,
                            winrate=sum(r["per_trade"]["n"] * r["per_trade"]["winrate"] for r in rows) / n,
                            avghold=sum(r["per_trade"]["n"] * r["per_trade"]["avghold"] for r in rows) / n) if n else None

    # 진단 베이스라인 — (tf, 방향) 조합마다 한 번
    combos = sorted({(tf, d) for _, d, _, _, tf in PATS})
    rand = {}
    for tf, d in combos:
        rb = random_baseline(syms, tf, d, cutoff)
        if rb:
            rand[f"{tf}:{d}"] = rb
        print(f"  [무작위 베이스라인] {tf} {d} — 준비", flush=True)

    # pooled 셀마다 '같은 패턴 구성' 가중 무작위 베이스라인을 붙인다(진단 열).
    tf_of = {lb: (tf, d) for lb, d, _, _, tf in PATS}
    for sp in ("train", "holdout"):
        for m in ARMS:
            if m == "D" or not pooled[sp].get(m):
                continue
            num_m = num_w = den = 0.0
            for lb in results:
                if lb.startswith("_") or not results[lb][m][sp]:
                    continue
                rb = rand.get(f"{tf_of[lb][0]}:{tf_of[lb][1]}", {}).get(sp, {}).get(m)
                if not rb:
                    continue
                w = results[lb][m][sp]["per_trade"]["n"]
                num_m += w * rb["mean"]; num_w += w * rb["winrate"]; den += w
            if den:
                pooled[sp][m]["rand_mean"] = num_m / den
                pooled[sp][m]["rand_winrate"] = num_w / den
                pooled[sp][m]["edge_mean"] = pooled[sp][m]["mean"] - num_m / den
                pooled[sp][m]["edge_win"] = pooled[sp][m]["winrate"] - num_w / den

    print("\n" + "=" * 150)
    print("작은 고정 익절 격자 — 배리어만 (익절/손절). 기준선 D = 현행 실거래 청산")
    print("=" * 150)
    for sp in ("train", "holdout"):
        b = base_sum[sp]
        print(f"\n[{sp}]  기준선 D: n={b['n']} 건당 {b['mean']*100:+.2f}% 승률 {b['winrate']:.0%} "
              f"보유 {b['avghold']:.1f}봉" if b else f"\n[{sp}] 기준선 없음")
        print(f"  {'셀':<7}{'익절':>5}{'손절':>5}{'n':>6}{'건당':>8}{'마찰0.4%':>10}{'승률':>7}"
              f"{'랜덤워크':>9}{'리프트':>8}{'무작위승률':>11}{'엣지':>8}{'분기점':>8}{'보유':>7}"
              f"  |{'짝지음':>9}{'t':>7}{'boot_p':>8}{'Holm':>7}"
              f"  |{'P1 CAGR':>9}{'MDD':>8}  |{'P2 배수':>10}{'P2 CAGR':>9}{'P2 MDD':>8}")
        print("  " + "-" * 165)
        pv = {m: pooled[sp][m]["boot_p"] for m in ARMS if m != "D" and pooled[sp].get(m)}
        hp = holm(pv)
        for tp, sl in CELLS:
            m = cell_name(tp, sl)
            r = pooled[sp].get(m)
            if not r:
                print(f"  {m:<7}  (거래 없음)"); continue
            eq = p1[sp][m]
            p2 = pots[sp][m]
            p1c = f"{eq['cagr']*100:>+8.1f}%{eq['mdd']*100:>+7.1f}%" if eq else f"{'-':>9}{'-':>8}"
            p2c = (f"{p2['mult']:>9.2f}x{p2['cagr']*100:>+8.1f}%{p2['mdd']*100:>+7.1f}%"
                   if p2 else f"{'-':>10}{'-':>9}{'-':>8}")
            star = " *" if m == PRIMARY_ARM else "  "
            print(f"  {m:<5}{star}{tp:>5.0%}{sl:>5.0%}{r['n']:>6}{r['mean']*100:>+7.2f}%"
                  f"{r['mean_stressed']*100:>+9.2f}%{r['winrate']:>7.1%}{r['rw_hit']:>9.1%}"
                  f"{r['lift']*100:>+7.1f}p"
                  f"{(r.get('rand_winrate') or 0):>11.1%}"
                  f"{(r.get('edge_win') or 0)*100:>+7.1f}p"
                  f"{r['breakeven_win']:>8.1%}{r['avghold']:>7.1f}"
                  f"  |{r['mean_diff']*100:>+8.2f}%{r['t']:>7.2f}{r['boot_p']:>8.3f}"
                  f"{hp.get(m, 1.0):>7.3f}  |{p1c}  |{p2c}")

    print("\n" + "=" * 150)
    print("[진단] 같은 배리어를 **무작위 진입**에 적용 — '배리어+드리프트' 와 '패턴' 을 가른다")
    print("  (판정 기준 아님. 리프트 = 패턴 승률 − 랜덤워크 이론값, 엣지 = 패턴 − 무작위 실측)")
    print("=" * 150)
    for key, rb in rand.items():
        print(f"\n  [{key}]  {'셀':<7}{'무작위n':>8}{'무작위건당':>11}{'무작위승률':>11}"
              f"{'이론값':>8}{'실측−이론':>10}")
        for tp, sl in CELLS:
            m = cell_name(tp, sl)
            r = rb["train"].get(m)
            if not r:
                continue
            print(f"          {m:<7}{r['n']:>8}{r['mean']*100:>+10.2f}%{r['winrate']:>11.1%}"
                  f"{rw_hit(tp, sl):>8.1%}{(r['winrate']-rw_hit(tp,sl))*100:>+9.1f}p")

    # ── P1 통합 자산곡선 (전 패턴 한 포트폴리오) ─────────────────────────────
    print("\n" + "=" * 150)
    print("P1 통합 포트폴리오 자산곡선 (전 패턴 한 계좌, 실거래 사이징·슬롯)")
    print("=" * 150)
    for sp in ("train", "holdout"):
        print(f"\n[{sp}]  {'arm':<7}{'거래':>7}{'CAGR':>9}{'MDD':>8}{'Calmar':>8}{'슬롯스킵':>9}")
        for m in ARMS:
            e = p1[sp][m]
            if not e:
                print(f"  {m:<7}  (없음)"); continue
            print(f"        {m:<7}{e['taken']:>7}{e['cagr']*100:>+8.1f}%{e['mdd']*100:>+7.1f}%"
                  f"{e['calmar']:>8.2f}{e['skipped']:>9}")

    # ── 판정 ────────────────────────────────────────────────────────────────
    print("\n" + "=" * 150)
    print(f"사전 등록 판정 — 주 판정 셀 {PRIMARY_ARM} (익절 {PRIMARY[0]:.0%} / 손절 {PRIMARY[1]:.0%})")
    print("=" * 150)
    v = verdict(results, pooled, pots, PRIMARY_ARM)
    tr = pooled["train"][PRIMARY_ARM]
    ho = pooled["holdout"].get(PRIMARY_ARM)
    names = ["①짝지음유의", "②건당>0", "③승률리프트>0", "④마찰0.4%>0", "⑤전후반양수",
             "⑥CAGR우위>=4/7", "⑦holdout짝지음", "⑧holdout건당", "⑨전용포트CAGR"]
    keys = ["c1_paired_sig", "c2_mean_pos", "c3_lift_pos", "c4_friction", "c5_halves",
            "c6_cagr_wins", "c7_holdout_diff", "c8_holdout_mean", "c9_pot_cagr"]
    for nm, k in zip(names, keys):
        val = v.get(k)
        ok = (val >= 4) if k == "c6_cagr_wins" else bool(val)
        print(f"  {'O' if ok else 'X'} {nm}"
              + (f"  ({val}/7)" if k == "c6_cagr_wins" else ""))
    print(f"\n  train n={tr['n']} 건당 {tr['mean']*100:+.2f}% 승률 {tr['winrate']:.2%} "
          f"(랜덤워크 {tr['rw_hit']:.2%}, 분기점 {tr['breakeven_win']:.2%}) "
          f"리프트 {tr['lift']*100:+.2f}p / 분기점 대비 {tr['lift_be']*100:+.2f}p")
    if tr.get("rand_winrate") is not None:
        print(f"  [진단] 같은 배리어 무작위 진입 승률 {tr['rand_winrate']:.2%} 건당 "
              f"{tr['rand_mean']*100:+.2f}% → 패턴 엣지 {tr['edge_win']*100:+.2f}p / "
              f"{tr['edge_mean']*100:+.2f}%p")
    if ho:
        print(f"  holdout n={ho['n']} 건당 {ho['mean']*100:+.2f}% 승률 {ho['winrate']:.2%} "
              f"리프트 {ho['lift']*100:+.2f}p")
    pt, ph = pots["train"].get(PRIMARY_ARM), pots["holdout"].get(PRIMARY_ARM)
    if pt:
        print(f"  P2 전용포트 train {POT_START:,.0f} → {pt['final']:,.0f} ({pt['mult']:.2f}x, "
              f"CAGR {pt['cagr']*100:+.1f}%, MDD {pt['mdd']*100:+.1f}%, "
              f"{pt['taken']}건 체결 / {pt['skipped']}건 미체결)")
    if ph:
        print(f"  P2 전용포트 holdout {ph['mult']:.2f}x CAGR {ph['cagr']*100:+.1f}% "
              f"MDD {ph['mdd']*100:+.1f}% ({ph['taken']}건)")
    ptd = pots["train"].get("D")
    if ptd:
        print(f"  (참고) 같은 자금·같은 순차 규칙을 **현행 D** 로 돌리면 train {ptd['mult']:.2f}x "
              f"CAGR {ptd['cagr']*100:+.1f}% MDD {ptd['mdd']*100:+.1f}%")
    print(f"\n  => {'PASS' if v['pass_'] else 'REJECTED'}"
          f"  (DEPLOY_ON_PASS={DEPLOY_ON_PASS} — 실거래 변경 없음)")
    print("  진단 11셀은 사후 선택 금지 — 표만 기록한다.")

    out = dict(config=dict(tp=list(TP_LEVELS), sl=list(SL_LEVELS), primary=list(PRIMARY),
                           primary_arm=PRIMARY_ARM, max_scan=MAX_SCAN, fee=FEE,
                           friction=FRICTION, pot_lev=POT_LEV, cutoff=cutoff,
                           holdout_days=HOLDOUT_DAYS, n_symbols=len(syms),
                           universe=ms.UNIVERSE_MODE, deploy_on_pass=DEPLOY_ON_PASS),
               baseline=base_sum, rand=rand, pooled=pooled, pot=pots, p1=p1,
               verdict=v, per_pattern=results)
    json.dump(out, open("_tp_small.json", "w", encoding="utf-8"), ensure_ascii=False,
              indent=1, default=lambda o: sorted(o) if isinstance(o, (set, frozenset)) else str(o))
    print("\n[저장] _tp_small.json")
    print("RESULT_JSON: " + json.dumps(dict(
        verdict="PASS" if v["pass_"] else "REJECTED", arm=PRIMARY_ARM,
        n=tr["n"], mean=round(tr["mean"], 5), winrate=round(tr["winrate"], 4),
        rw=round(tr["rw_hit"], 4), lift=round(tr["lift"], 4),
        pot_mult=round(pt["mult"], 3) if pt else None,
        deployed=False), separators=(",", ":")))


if __name__ == "__main__":
    main()
