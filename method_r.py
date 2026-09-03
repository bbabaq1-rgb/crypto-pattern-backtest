"""
method_r.py — 방향 인지 레짐 청산 시험: 방식D vs 방식R (+ 2차 후속 arm).

배경
----
방식D(현행 실거래)의 레짐 전환 청산은 **방향을 보지 않는다.**

    regsw = regmap[date] not in (None, entry_reg)      # paper_executor.eval_D

진입 당시와 레짐이 다르기만 하면 롱·숏 가리지 않고 종가 청산한다. 그 결과
bear 에서 바닥을 잡은 롱(engulfing/marubozu/triple_bottom 이 bear 에서 롱으로 라우팅됨)은
레짐이 bull 로 **유리하게** 바뀌는 순간 청산된다 — 상승을 타야 할 때 내리는 셈이다.

사용자 관찰(2026-09-03): "하락 국면에서 바닥을 잡고 상승을 탔는데 상승 전환됐다고
청산되면 안 된다. 상승일 때 다 먹다가 다시 하락으로 바뀔 때 청산해야 고점을 보고
나온다." — 이 규칙이 방식R 이다.

방식R = 방식D 에서 레짐 조건만 교체: **불리한 국면으로 들어가는 전환**에만 청산.
  R1 : 롱 불리 = {bear},           숏 불리 = {bull_btc, bull_altseason}.  sideways 중립(유지)
  R2 : 롱 불리 = {bear, sideways}, 숏 불리 = {bull_*, sideways}.          횡보도 불리로 간주
'전환'은 직전 상태가 불리가 아니었다가 불리가 되는 순간이다. 진입 자체가 불리 국면이면
(bear 롱) 이미 불리 상태에서 시작하므로, 한 번 벗어났다가 **다시 들어올 때** 청산된다.
손절 -8% / 반대패턴 신호 / 최대 30봉은 방식D 와 동일하게 둔다.

1차 결과 (2026-09-03, run #1·#2, report_regime_exit.md)
---------------------------------------------------------
REJECT — 합산 +0.597%p(t 1.58, 패턴재표본 boot_p 0.006), 짝지음우위 6/7, CAGR우위 4/7,
그러나 분기 거래 285건 중 R 승률 44% 로 기준 ④ 탈락. R1≡R2(표본에 sideways 전환 0건).
**롱은 맞고 숏은 틀렸다**: bear 진입 fvg 롱 n=134 +2.39→+5.29%(boot_p 0.006) vs
bull 진입 fvg 숏 n=188 −2.05→−2.58%(boot_p 0.975). 그리고 건당이 올라도 fvg CAGR 이
22.9→12.3% — 보유가 길어져 회전율이 떨어지고, 손절이 **진입가 고정**이라 유리 국면에서
번 걸 되돌림 때 −8% 까지 반납(stop 206→244).

2차 — 후속 가설 3개 (사용자 지시 2026-09-03, 1차 결과를 보고 고른 **사후 선택**)
-------------------------------------------------------------------------------
  RL  : 롱만 R1, 숏은 D 그대로.              (1차의 롱/숏 비대칭에서)
  RB  : R1 + **유리 국면으로 전환되는 순간 손절을 진입가(본전)로 이동**. 양방향.
        (1차의 '반납' 문제에서. 트레일링이 아니라 1회 이동 — 결정론적, 짝지음 재현 가능.
         수익 중일 때만 옮긴다. 손실 중에 옮기면 다음 봉에 본전 체결이 되는 비현실적 결과.)
  RLB : 롱만 (R1 + 본전 이동), 숏은 D.
R2 는 1차에서 R1 과 완전 동일했으므로 2차 실행 목록에서 뺀다(코드는 남김, 테스트가 쓴다).

사전 등록 판정 기준 (2차 결과를 보기 전에 정한다)
-----------------------------------------------
1차의 4개에 ⑤를 얹는다 — 사후 선택된 가설이라 최소한의 과적합 방어:
  1) 7패턴 합산 짝지음 평균차이 > 0 이고 t > 2.0 (또는 부트스트랩 p < 0.05)
  2) CAGR 우위 패턴 수 >= 4/7
  3) 짝지음 t < -2.0 인 패턴이 하나도 없음
  4) 분기 거래 안에서 arm 승률 > 50%
  5) **시간 분할** — 진입일 중앙값 기준 전반/후반 각각의 합산 짝지음 평균차이가 둘 다 > 0
전부 만족해야 채택 후보. 하나라도 빠지면 REJECT. 2차는 같은 데이터에 대한 두 번째
검정이므로 통과해도 1차 가설 통과보다 약한 증거로 본다(리포트에 명시).

방법
----
method_t.py 와 같은 틀 — 같은 신호에 규칙들을 동시에 적용하는 **짝지음(paired)** 비교.
분기 거래(두 규칙이 실제로 갈라진 것)만 따로 떼어 어느 쪽이 이겼는지 센다.
사용자 시나리오(불리 국면 진입 거래)를 따로 잘라 본다.
자산곡선(가용잔고 20%/12포지션/2x, method_t 와 동일)으로 CAGR/MDD 도 병기한다.

3차 — altseason 인지 + 홀드아웃 (사용자 지시 2026-09-03, 2차 분해에서 나온 **사후 선택**)
-------------------------------------------------------------------------------
2차 분해: fvg 롱 분기 161건 중 bull 진입 ≈124건은 D 가 bull_btc↔bull_altseason 라벨 전환에서
청산하던 거래였고 R 은 '유리→유리'로 버티다 −8% 에 걸렸다. bull_altseason→bull_btc 는 알트가
BTC 에 뒤처지기 시작한다는 뜻이라 알트 롱에는 사실상 불리한 전환이다.
  RA : RL(롱만 방향 인지, 숏은 D) + **bull_altseason→bull_btc 전환을 롱 불리로 추가**.
       bear→bull_* 는 여전히 유리(유지). 비교군으로 RL 을 같이 돌려 순수 증분을 본다.
같은 5년 데이터에 대한 **세 번째** 검정이므로 홀드아웃을 붙인다:
  · 데이터 마지막 HOLDOUT_DAYS(365)일에 진입한 거래는 판정에서 제외(홀드아웃).
  · train(앞 4년)으로 기준 ①~⑤ 판정. 통과한 arm 만 홀드아웃에서 ⑥⑦ 확인.
      6) 홀드아웃 합산 짝지음 평균차이 > 0
      7) 홀드아웃 분기 거래 arm 승률 > 50%
  · 7개 전부 만족해야 PASS. 홀드아웃은 한 번만 본다(재시도 없음).

실행: python method_r.py   (Actions 러너 — 데이터 자동 수집, method_r.yml)
"""
import importlib
import json
import random
import statistics as st

import detlib
import regime_switch as rs
import method_t as mt                       # PATS / ensure_data / summ / paired_stats / equity_curve

STOP_LOSS_PCT = mt.STOP_LOSS_PCT
MAX_HOLD      = mt.MAX_HOLD
FEE           = mt.FEE

ADVERSE = {
    "R1": {"long": {"bear"},
           "short": {"bull_btc", "bull_altseason"}},
    "R2": {"long": {"bear", "sideways"},
           "short": {"bull_btc", "bull_altseason", "sideways"}},
}
FAVORABLE = {"long": {"bull_btc", "bull_altseason"}, "short": {"bear"}}

# arm → 방향별 (레짐 규칙, 본전 이동 여부).  레짐 규칙 "D" = 현행, "R1"/"R2" = ADVERSE 키
ARM = {
    "D":   {"long": ("D",  False), "short": ("D",  False)},
    "R1":  {"long": ("R1", False), "short": ("R1", False)},
    "R2":  {"long": ("R2", False), "short": ("R2", False)},
    "RL":  {"long": ("R1", False), "short": ("D",  False)},
    "RB":  {"long": ("R1", True),  "short": ("R1", True)},
    "RLB": {"long": ("R1", True),  "short": ("D",  False)},
}
ARM["RA"] = {"long": ("R1", False), "short": ("D", False)}
# arm 별 '전환 자체가 불리'인 (from, to) 쌍 — 상태 집합(ADVERSE)과 별개로 검사
ADVERSE_TRANSITIONS = {"RA": {"long": {("bull_altseason", "bull_btc")}}}
MODES = ["D", "RL", "RA"]                    # 3차 실행 목록 (RL 은 비교군)
HOLDOUT_DAYS = 365
BOOT_N = 2000
BOOT_SEED = 7

REGMAP = {}


# ── 청산 규칙 ───────────────────────────────────────────────────────────────
def outcome_r(rows, si, direction, opp_set, mode):
    """
    mode="D"  : 방식D 그대로 (method_t.outcome_d 와 동일 결과 — 테스트로 고정)
    mode="R1"/"R2": 레짐 조건만 '불리 국면 진입 시'로 교체.
    mode="RL"/"RB"/"RLB": ARM 표 참조 (롱 한정 / 본전 이동 / 둘 다).
    mode="RA": RL + ADVERSE_TRANSITIONS (bull_altseason→bull_btc 를 롱 불리 전환으로).
    반환: (ret, hold_bars, reason)   reason ∈ stop / stop_be / opp_signal / regime_switch / maxhold
    """
    rule, be = ARM[mode][direction]
    base = rows[si]["c"]
    entry_reg = REGMAP.get(rows[si]["date"])
    end = min(si + MAX_HOLD, len(rows) - 1)
    adv = ADVERSE.get(rule, {}).get(direction, set())
    adv_tr = ADVERSE_TRANSITIONS.get(mode, {}).get(direction, set())
    fav = FAVORABLE[direction]
    prev_adv = entry_reg in adv
    prev_fav = entry_reg in fav
    prev_reg = entry_reg                        # 마지막으로 관측된 레짐 (None 제외)
    is_long = direction == "long"
    stop_px = base * (1 - STOP_LOSS_PCT) if is_long else base * (1 + STOP_LOSS_PCT)
    be_armed = False

    for j in range(si + 1, end + 1):
        # 1) 손절 (봉 내) — 항상 먼저. 본전 손절이면 수익률 0 - 수수료
        hit = rows[j]["l"] <= stop_px if is_long else rows[j]["h"] >= stop_px
        if hit:
            if be_armed:
                return -FEE, j - si, "stop_be"
            return -STOP_LOSS_PCT - FEE, j - si, "stop"

        # 2) 레짐 조건
        cur = REGMAP.get(rows[j]["date"])
        if rule == "D":
            regsw = cur not in (None, entry_reg)
        else:
            if cur is None:
                regsw = False                       # 레짐 정보 없는 봉은 판단 보류
            else:
                cur_adv = cur in adv
                regsw = (cur_adv and not prev_adv) or ((prev_reg, cur) in adv_tr)
                prev_adv = cur_adv
                prev_reg = cur

        # 3) 반대 신호 / 레짐 (종가)
        if j in opp_set or regsw:
            c = rows[j]["c"]
            r = (c - base) / base if is_long else (base - c) / base
            return r - FEE, j - si, ("opp_signal" if j in opp_set else "regime_switch")

        # 4) 본전 이동 — 유리 국면으로 '들어가는' 순간, 수익 중일 때만, 1회
        if be and cur is not None:
            cur_fav = cur in fav
            if cur_fav and not prev_fav and not be_armed:
                c = rows[j]["c"]
                if (is_long and c > base) or ((not is_long) and c < base):
                    stop_px = base
                    be_armed = True
            prev_fav = cur_fav

    px = rows[end]["o"]
    r = (px - base) / base if is_long else (base - px) / base
    return r - FEE, end - si, "maxhold"


# ── 통계 보조 ───────────────────────────────────────────────────────────────
def boot_p(diffs, n=BOOT_N, seed=BOOT_SEED):
    """짝지음 차이의 부트스트랩: 평균차이 <= 0 인 재표본 비율 (단측)."""
    if len(diffs) < 2:
        return 1.0
    rng = random.Random(seed)
    k = len(diffs)
    le = 0
    for _ in range(n):
        s = sum(diffs[rng.randrange(k)] for _ in range(k)) / k
        if s <= 0:
            le += 1
    return le / n


def divergence(base, arm):
    """
    두 규칙이 실제로 갈라진 거래만 비교.
    base/arm: [(entry_date, exit_date, ret, hold, reason)] 같은 순서.
    """
    idx = [i for i, (b, a) in enumerate(zip(base, arm))
           if b[3] != a[3] or b[4] != a[4] or abs(b[2] - a[2]) > 1e-12]
    if not idx:
        return dict(n=0, arm_wins=0, arm_losses=0)
    bd = [base[i][2] for i in idx]
    ad = [arm[i][2] for i in idx]
    d = [a - b for a, b in zip(ad, bd)]
    return dict(n=len(idx),
                share=len(idx) / len(base),
                base_mean=st.mean(bd), arm_mean=st.mean(ad),
                base_median=st.median(bd), arm_median=st.median(ad),
                mean_diff=st.mean(d),
                arm_wins=sum(1 for x in d if x > 1e-12),
                arm_losses=sum(1 for x in d if x < -1e-12),
                base_reasons=_count(base[i][4] for i in idx),
                arm_reasons=_count(arm[i][4] for i in idx),
                base_hold=st.mean(base[i][3] for i in idx),
                arm_hold=st.mean(arm[i][3] for i in idx))


def halves(base, arm):
    """
    시간 분할 — 진입일 순으로 정렬해 전반/후반의 짝지음 평균차이.
    사후 선택된 가설의 최소 과적합 방어(기준 ⑤). 반환: (n1, d1, n2, d2)
    """
    order = sorted(range(len(base)), key=lambda i: base[i][0])
    if len(order) < 4:
        return dict(n1=0, d1=0.0, n2=0, d2=0.0)
    h = len(order) // 2
    a, b = order[:h], order[h:]
    d1 = st.mean(arm[i][2] - base[i][2] for i in a)
    d2 = st.mean(arm[i][2] - base[i][2] for i in b)
    return dict(n1=len(a), d1=d1, n2=len(b), d2=d2)


def split_idx(trades, cutoff):
    """진입일 기준 train(< cutoff) / holdout(>= cutoff) 인덱스. cutoff 는 'YYYY-MM-DD'."""
    tr = [i for i, t in enumerate(trades) if t[0] < cutoff]
    ho = [i for i, t in enumerate(trades) if t[0] >= cutoff]
    return tr, ho


def _count(it):
    out = {}
    for x in it:
        out[x] = out.get(x, 0) + 1
    return out


def _jsonable(x):
    """json.dump default — set 을 정렬 리스트로 (1차 실행이 ADVERSE 의 set 에서 죽었다)."""
    if isinstance(x, (set, frozenset)):
        return sorted(x)
    raise TypeError(f"not serializable: {type(x).__name__}")


# ── 실행 ────────────────────────────────────────────────────────────────────
def _arm_stats(base, arm, idx, entry_regs, m, direction, with_halves):
    """한 패턴·한 arm·한 분할(train/holdout)의 통계. idx 가 비면 None."""
    b = [base[i] for i in idx]
    a = [arm[i] for i in idx]
    if not b:
        return None
    rec = dict(per_trade=mt.summ(a),
               equity=mt.equity_curve(sorted(a, key=lambda t: t[0])),
               reasons=_count(t[4] for t in a))
    if m != "D":
        br = [t[2] for t in b]
        ar = [t[2] for t in a]
        p = mt.paired_stats(br, ar)
        p["boot_p"] = boot_p([x - y for x, y in zip(ar, br)])
        rec["paired_vs_D"] = p
        rec["divergence"] = divergence(b, a)
        if with_halves:
            rec["halves"] = halves(b, a)
        rule = ARM[m][direction][0]
        adv = ADVERSE.get(rule, {}).get(direction, set())
        sub = [k for k, i in enumerate(idx) if entry_regs[i] in adv]
        if adv and len(sub) >= 2:
            sb = [br[k] for k in sub]
            sa = [ar[k] for k in sub]
            ps = mt.paired_stats(sb, sa)
            ps["boot_p"] = boot_p([x - y for x, y in zip(sa, sb)])
            ps["base_mean"] = st.mean(sb)
            ps["arm_mean"] = st.mean(sa)
            rec["adverse_entry_subset"] = ps
    return rec


def run_pattern(label, direction, detmod, oppmod, tf, cutoff):
    mod = importlib.import_module(detmod)
    opp = importlib.import_module(oppmod) if oppmod else None

    arms = {m: [] for m in MODES}
    entry_regs = []

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
            entry_regs.append(REGMAP.get(rows[si]["date"]))
            for m in MODES:
                ret, hold, reason = outcome_r(rows, si, direction, opp_set, m)
                xi = min(si + hold, len(rows) - 1)
                arms[m].append((rows[si]["date"], rows[xi]["date"], ret, hold, reason))

    if not arms["D"]:
        return None

    base = arms["D"]
    tr, ho = split_idx(base, cutoff)
    out = {}
    for m in MODES:
        out[m] = dict(train=_arm_stats(base, arms[m], tr, entry_regs, m, direction, True),
                      holdout=_arm_stats(base, arms[m], ho, entry_regs, m, direction, False))
    out["_entry_regime_counts"] = _count(entry_regs)
    out["_n_train"] = len(tr)
    out["_n_holdout"] = len(ho)
    return out


def _pool(results, split, m):
    """패턴별 결과를 표본수 가중으로 합산. 해당 분할이 없는 패턴은 건너뜀."""
    items = []
    for lb, res in results.items():
        if lb.startswith("_"):
            continue
        r = res[m][split]
        if not r:
            continue
        p = r["paired_vs_D"]
        n = r["per_trade"]["n"]
        items.append((p["mean_diff"], p.get("sd_diff", 0.0), n, r["divergence"], r.get("halves")))
    if not items:
        return None
    tot = sum(x[2] for x in items)
    mean_diff = sum(x[0] * x[2] for x in items) / tot
    var = sum((x[1] ** 2) * x[2] for x in items) / tot
    t = mean_diff / ((var ** 0.5) / (tot ** 0.5)) if var > 0 else 0.0
    rng = random.Random(BOOT_SEED)
    pairs = [(x[0], x[2]) for x in items]
    le = 0
    for _ in range(BOOT_N):
        smp = [pairs[rng.randrange(len(pairs))] for _ in pairs]
        s = sum(a * w for a, w in smp) / sum(w for _, w in smp)
        if s <= 0:
            le += 1
    dv = dict(n=sum(x[3]["n"] for x in items),
              arm_wins=sum(x[3].get("arm_wins", 0) for x in items),
              arm_losses=sum(x[3].get("arm_losses", 0) for x in items))
    out = dict(n=tot, n_patterns=len(items), mean_diff=mean_diff, t=t, boot_p=le / BOOT_N,
               divergence=dv)
    hv = [x[4] for x in items if x[4]]
    if hv:
        n1 = sum(h["n1"] for h in hv); n2 = sum(h["n2"] for h in hv)
        out["halves"] = dict(n1=n1, n2=n2,
                             d1=sum(h["d1"] * h["n1"] for h in hv) / n1 if n1 else 0.0,
                             d2=sum(h["d2"] * h["n2"] for h in hv) / n2 if n2 else 0.0)
    return out


def verdict(results, arm):
    """train 으로 ①~⑤, 통과 시 holdout 으로 ⑥⑦. 7개 전부 만족해야 PASS."""
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
    hv = tr.get("halves", {})
    c5 = hv.get("d1", 0) > 0 and hv.get("d2", 0) > 0
    train_pass = bool(c1 and c2 and c3 and c4 and c5)
    c6 = bool(ho) and ho["mean_diff"] > 0
    c7 = bool(ho) and ho["divergence"]["arm_wins"] > ho["divergence"]["arm_losses"]
    return dict(pass_=bool(train_pass and c6 and c7), train_pass=train_pass,
                c1_pooled_sig=c1, c2_cagr_wins=cw, c3_no_pattern_hurt=c3,
                c4_divergence_winrate=c4, c5_halves_both_pos=c5,
                c6_holdout_diff_pos=c6, c7_holdout_divergence=c7)


def _print_split(res, split):
    print(f"  [{split}]")
    print(f"  {'arm':<4}{'n':>5}{'건당평균':>10}{'중앙':>9}{'승률':>7}{'평균보유':>8}"
          f"  |{'짝지음차이':>11}{'t':>7}{'boot_p':>8}{'승/패':>9}"
          f"  |{'분기n':>6}{'분기승률':>9}  |{'전반':>8}{'후반':>8}"
          f"  |{'CAGR':>8}{'MDD':>8}{'Calmar':>8}")
    print("  " + "-" * 114)
    for m in MODES:
        r = res[m][split]
        if not r:
            print(f"  {m:<4}    0  (해당 분할 거래 없음)")
            continue
        s, eq = r["per_trade"], r["equity"]
        if m == "D":
            pair = f"{'(기준)':>11}{'':>7}{'':>8}{'':>9}"
            dvs = f"{'-':>6}{'-':>9}"
            hv = f"{'-':>8}{'-':>8}"
        else:
            p = r["paired_vs_D"]; dv = r["divergence"]; h = r.get("halves")
            pair = (f"{p['mean_diff']*100:>+10.2f}%{p['t']:>7.2f}{p['boot_p']:>8.3f}"
                    f"{p['wins']:>4}/{p['losses']:<4}")
            tot = dv["arm_wins"] + dv["arm_losses"]
            dvs = f"{dv['n']:>6}{(dv['arm_wins']/tot if tot else 0):>8.0%}"
            hv = (f"{h['d1']*100:>+7.2f}%{h['d2']*100:>+7.2f}%" if h else f"{'-':>8}{'-':>8}")
        print(f"  {m:<4}{s['n']:>5}{s['mean']*100:>+9.2f}%{s['median']*100:>+8.2f}%"
              f"{s['winrate']:>6.0%}{s['avghold']:>8.1f}  |{pair}  |{dvs}  |{hv}"
              f"  |{eq['cagr']*100:>+7.1f}%{eq['mdd']*100:>+7.1f}%{eq['calmar']:>8.2f}")
        print(f"       사유 {r['reasons']}")
    for m in MODES[1:]:
        r = res[m][split]
        sub = r.get("adverse_entry_subset") if r else None
        if sub:
            print(f"  [{m} 불리국면 진입만 n={sub['n']}] D {sub['base_mean']*100:+.2f}% → {m} "
                  f"{sub['arm_mean']*100:+.2f}%  차이 {sub['mean_diff']*100:+.2f}%p "
                  f"t={sub['t']:.2f} boot_p={sub['boot_p']:.3f} 승/패 {sub['wins']}/{sub['losses']}")


def main():
    global REGMAP
    from datetime import date, timedelta
    mt.ensure_data()
    REGMAP = rs.build_regime_map()
    mt.REGMAP = REGMAP
    last = max(REGMAP)
    cutoff = (date.fromisoformat(last) - timedelta(days=HOLDOUT_DAYS)).isoformat()
    print(f"[regime] 레짐맵 {len(REGMAP)}일  |  홀드아웃 cutoff {cutoff} (마지막 {HOLDOUT_DAYS}일, 데이터 끝 {last})")
    results = {}

    print("=" * 118)
    print("3차 — 방식D vs RL(롱만 방향인지) vs RA(RL + bull_altseason→bull_btc 롱 불리) | train 판정 → holdout 확인")
    print(f"  손절 -{int(STOP_LOSS_PCT*100)}% / 반대신호 / 최대 {MAX_HOLD}봉 동일. "
          f"자산곡선 가용잔고x{mt.SIM_POS_PCT:.0%}/{mt.SIM_MAX_POS}포지션/{mt.SIM_LEVERAGE}x")
    print("=" * 118)

    for label, direction, detmod, oppmod, tf in mt.PATS:
        try:
            res = run_pattern(label, direction, detmod, oppmod, tf, cutoff)
        except Exception as e:
            print(f"\n[{label}] 실행 오류: {str(e)[:80]}")
            continue
        if not res:
            print(f"\n[{label}] 신호 없음 — 스킵")
            continue
        results[label] = res
        print(f"\n[{label} @{tf} {direction}]  진입레짐 {res['_entry_regime_counts']}  "
              f"train {res['_n_train']} / holdout {res['_n_holdout']}")
        _print_split(res, "train")
        _print_split(res, "holdout")

    if not results:
        print("결과 없음")
        return

    results["_pooled"] = {"train": {}, "holdout": {}}
    print("\n" + "=" * 118)
    print("종합 — 7패턴 합산")
    print("=" * 118)
    for split in ("train", "holdout"):
        for m in MODES[1:]:
            p = _pool(results, split, m)
            results["_pooled"][split][m] = p
            if not p:
                print(f"  [{split}] {m}: 거래 없음")
                continue
            pats = [lb for lb in results if not lb.startswith("_") and results[lb][m][split]]
            pw = sum(1 for lb in pats if results[lb][m][split]["paired_vs_D"]["mean_diff"] > 0)
            cw = sum(1 for lb in pats
                     if results[lb][m][split]["equity"]["cagr"] > results[lb]["D"][split]["equity"]["cagr"])
            hurt = [lb for lb in pats if results[lb][m][split]["paired_vs_D"]["t"] < -2.0]
            dv = p["divergence"]
            hv = p.get("halves")
            hvs = f" | 전반 {hv['d1']*100:+.2f}%p 후반 {hv['d2']*100:+.2f}%p" if hv else ""
            print(f"  [{split:<7}] {m:<3}: n={p['n']} ({p['n_patterns']}패턴) 짝지음 {p['mean_diff']*100:+.3f}%p "
                  f"t={p['t']:.2f} boot_p={p['boot_p']:.3f} | 짝지음우위 {pw}/{len(pats)} CAGR우위 {cw}/{len(pats)} "
                  f"| 분기 {dv['n']}건 승/패 {dv['arm_wins']}/{dv['arm_losses']}{hvs} | t<-2 {hurt or '없음'}")

    summary = {}
    for m in MODES[1:]:
        v = verdict(results, m)
        summary[m] = v
        print(f"  [{m} 판정] {'PASS' if v['pass_'] else 'REJECT'}  "
              f"train: ①{v['c1_pooled_sig']} ②{v['c2_cagr_wins']}/7 ③{v['c3_no_pattern_hurt']} "
              f"④{v['c4_divergence_winrate']} ⑤{v['c5_halves_both_pos']} → {'통과' if v['train_pass'] else '탈락'}"
              f"  | holdout: ⑥{v['c6_holdout_diff_pos']} ⑦{v['c7_holdout_divergence']}")

    payload = dict(config=dict(stop=STOP_LOSS_PCT, max_hold=MAX_HOLD, fee=FEE,
                               adverse={m: {d: sorted(s) for d, s in v.items()} for m, v in ADVERSE.items()},
                               adverse_transitions={m: {d: sorted(list(x) for x in s) for d, s in v.items()}
                                                    for m, v in ADVERSE_TRANSITIONS.items()},
                               favorable={d: sorted(s) for d, s in FAVORABLE.items()},
                               arms={m: ARM[m] for m in MODES}, holdout_days=HOLDOUT_DAYS,
                               cutoff=cutoff, data_end=last, boot_n=BOOT_N,
                               sim=dict(pos_pct=mt.SIM_POS_PCT, max_pos=mt.SIM_MAX_POS,
                                        leverage=mt.SIM_LEVERAGE, start=mt.SIM_START_EQ)),
                   patterns={k: v for k, v in results.items() if not k.startswith("_")},
                   pooled=results["_pooled"], summary=summary)
    json.dump(payload, open("method_r.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1, default=_jsonable)
    print("\n[저장] method_r.json")
    print("RESULT_SUMMARY: " + json.dumps(summary, separators=(",", ":")))


if __name__ == "__main__":
    main()
