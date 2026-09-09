"""
validate_tp_1h.py — 작은 고정 익절 **1시간봉 재측정 + 넓은 손절 + 레버리지** 사전 등록
(2026-09-09, 사용자 지시 "1시간봉 데이터로 다시 돌려봐" / "익절 1퍼센트 손절 3퍼까지
버티기도 테스트된거 맞아?" / "레버리지를 아예 안쓰거나 손절범위를 8퍼센트 이상으로
늘려서 버티는것까지 테스트").

── 왜 다시 도는가 ──────────────────────────────────────────────────────────
1d 판(run 34313582686)은 REJECTED 였지만 **결과와 함께 기록한 측정 한계**가 있다:
좁은 익절 셀은 일봉이 봉 **안의 순서**를 못 본다. 같은 봉에서 익절·손절에 둘 다 닿으면
손절 우선(보수적·레포 관례)인데, ±1% 는 알트 일봉이 거의 매번 둘 다 건드린다 —
1d 무작위 T1S1 승률 18.4%(이론 50%), 1w T1S8 50.0%(이론 88.9%). **일봉은 익절 1%
규칙을 잴 해상도가 없다.** 1h 봉은 폭이 좁아 동률이 드물어진다.
그리고 **손절 3% 는 1d 격자에 없었다**(손절 {1,2,4,8}) — 사용자 질문 그대로 넣는다.

── 구조적 사실 (결과와 무관, 산술) ─────────────────────────────────────────
무편향 랜덤워크에서 P(익절 먼저) = SL/(TP+SL), 그 지점의 수수료 전 기대값은 정확히 0.
수수료를 넘기려면 **필요 리프트 = FEE/(TP+SL)** 만큼 그 위로 올라가야 한다.
  1%/2% +6.67%p · **1%/3% +5.00%p** · 1%/4% +4.00%p · **1%/8% +2.22%p**
  · 1%/12% +1.54%p · 1%/16% +1.18%p · **1%/20% +0.95%p**
**좁힐수록 어렵고 넓힐수록 쉽다** — 같은 수수료가 더 좁은 배리어 폭에 걸리기 때문.
사용자의 '3% 까지만 버틴다'는 8% 보다 두 배 넘게 어려운 조건이고, 반대로 '8% 이상으로
늘려 버틴다'는 **필요 엣지를 줄이는 옳은 방향**이다. 다만 넓힌다고 기대값이 생기지는
않는다 — 마팅게일 값은 여전히 정확히 0 이라 **패턴이 그 위로 밀어올려야 한다.**

── 레버리지는 이 판정에 영향이 없다 (사용자 질문 직답) ─────────────────────
배리어는 **가격 수익률**로 정의되고 레버리지는 손익과 증거금을 같은 배율로 곱한다.
승률·리프트·엣지·건당 부호가 전부 불변이므로 **기준 ①~⑦ 은 레버리지와 무관**하다.
레버리지가 바뀌는 곳은 **복리·파산 확률** 하나다 — 1d 판에서 전용 포트가 3x 로 0 이
된 것이 그 자리다. 그래서 레버리지는 판정이 아니라 **P2 전용 포트 스윕 {1,2,3}x**
진단으로 잰다. '레버리지를 아예 안 쓰면(1x) 살아남는가'에 그 표가 답한다.

── 동결 (실행 전 고정) ─────────────────────────────────────────────────────
· TF **1h**(주 판정) — 유니버스 80, 365일. 1d 는 진단으로 병기(해상도 대비 + SL 열 보강).
· 격자 익절 {1,2,3}% x 손절 {1,2,3,4,8,12,16,20,무손절} = 27셀.
· **주 판정 4셀 = T1S3, T1S8, T1S20, T1SX(무손절)** — 사용자가 지목한 넷. **Holm m=4**.
  나머지 23셀은 진단이며 사후 선택 금지.
· 패턴은 TF 무관 캔들 6종. triple_bottom(주봉 구조) 제외.
· 배리어만 — 레짐·반대신호·시간 청산 없음. 동률은 **손절 우선**(보수적, 1d 판과 동일).
· MAX_SCAN: 1h 2000봉(약 83일) / 1d 250봉. 미해소는 그 봉 시가 청산('open').
· 홀드아웃 1h 90일 / 1d 365일. 비용 왕복 0.2% 동결 + 0.4% 스트레스.

── 판정 기준이 1d 판과 다른 이유 (실행 전 명시) ────────────────────────────
1d 판의 ①은 '방식D 와의 짝지음'이었다. **1h 에서 방식D 는 정의가 없다** — −8% 손절·
30봉 보유·레짐 청산은 1d 검증 규칙이고 1h 에서 검증된 적이 없다. 그래서 1h 판은
규칙을 **그 자체의 조건**으로 잰다.

  1) train 건당 평균 > 0
  2) train 승률 > 손익분기 (SL+FEE)/(TP+SL)          [①과 동치이나 명시]
  3) **승률 리프트 > 0** — 실측 승률 > 랜덤워크 이론값 SL/(TP+SL)
  4) **패턴 엣지 > 0 이고 Holm 보정 boot_p < 0.05** — 같은 배리어를 **무작위 진입**에
     적용한 실측 승률보다 높을 것. (1d 판에서는 진단이었다. 1h 는 동률 오염이 작아
     이 비교가 깨끗해지므로 판정으로 올린다.)
  5) 마찰 0.4% 에서도 건당 평균 > 0
  6) 전반·후반 건당 평균 둘 다 > 0
  7) holdout 건당 평균 > 0
7개 전부 만족해야 PASS.
**무손절(T1SX) 셀 예외**: 손절이 없으면 랜덤워크 기준값·손익분기가 정의되지 않는다 →
②③ 은 N/A 로 통과 처리하고 **①④⑤⑥⑦ 다섯 개로 판정**한다(사후 완화가 아니라 실행 전
규정). 대신 그 셀은 미해소 비율·평균 보유·최대 손실을 반드시 병기한다.
**DEPLOY_ON_PASS=False — 통과해도 실거래 반영 없음**(관찰 기간, 청산 변경은 실주문 경로).

── 이번에 새로 재는 것 ─────────────────────────────────────────────────────
· **동률 비율** — 청산 봉이 양쪽 배리어를 다 건드린 비율. 1h 가 1d 대비 얼마나 떨어지는가가
  '1h 재측정이 의미 있는가'의 답이다.
· **낙관 상한 arm** — 동률을 전부 익절로 돌린 판(진단). 진실이 보수·낙관 사이에 갇힌다.
  **판정은 사전 등록대로 보수 판으로만 한다.**
· **P2 전용 포트 레버리지 스윕 {1,2,3}x** — 한 번에 한 포지션·전액·순차 복리.

── 사전 확률 (결과 보기 전 기록) ───────────────────────────────────────────
· 1h 동률 비율은 1d 보다 훨씬 낮고 실측 승률이 이론값에 가까워질 것이다.
· 그러나 **이론값 자체가 손익분기 아래**다. 통과하려면 패턴이 승률을 이론값 위로
  필요 리프트만큼 밀어야 하는데, 1d 판의 패턴 엣지는 **−4.36%p**(무작위보다 나빴다)였고
  신호봉 프로필 연구의 월 demean 상관도 −0.05~−0.09 였다. **네 셀 다 기각을 예상한다.**
· 넓은 손절(20%·무손절)은 필요 리프트가 작아 **가장 가망 있는 셀**이다. 대신 손실 한 번이
  −20% 이상이고 보유가 길어져 자본이 묶인다 — 그 대가는 P2 표에서 보인다.
· 레버리지 1x 는 파산을 늦출 뿐 기대값 부호를 못 바꾼다. 건당이 음수면 1x 도 우하향한다.
· 1d 판 사전 확률은 방향만 맞고 크기가 크게 빗나갔다(−14.32%p). 이번엔 크기를 적지 않는다.

실행: python validate_tp_1h.py [--no-fetch] [--tf 1h,1d]
출력 _tp_1h.json + RESULT_JSON. 실거래·DB 무관.
"""
import importlib
import json
import random
import statistics as st
import sys

import method_t as mt
import validate_regime_split_all as va

FEE = mt.FEE

# ── 동결 파라미터 ───────────────────────────────────────────────────────────
TFS = ("1h", "1d")
PRIMARY_TF = "1h"
TP_LEVELS = (0.01, 0.02, 0.03)
SL_LEVELS = (0.01, 0.02, 0.03, 0.04, 0.08, 0.12, 0.16, 0.20, None)   # None = 무손절
PRIMARY = ((0.01, 0.03), (0.01, 0.08), (0.01, 0.20), (0.01, None))   # 사용자 지목 4셀
MAX_SCAN_BY_TF = {"1h": 2000, "1d": 250}
HOLDOUT_BY_TF = {"1h": 90, "1d": 365}
FRICTION = 0.004
POT_LEVS = (1, 2, 3)               # P2 레버리지 스윕 (진단)
POT_START = 100_000.0
SIG_CAP = 15000
RAND_N, RAND_SEED = 8000, 11
BOOT_N, BOOT_SEED = 2000, 7
SIG_SEED = 5
DEPLOY_ON_PASS = False

PATS = [(lb, d, m) for lb, d, m, _o, _tf in mt.PATS if lb != "triple_bottom"]
CELLS = [(tp, sl) for tp in TP_LEVELS for sl in SL_LEVELS]


def cell_name(tp, sl):
    return f"T{round(tp*100)}S" + ("X" if sl is None else str(round(sl * 100)))


CELL_OF = {cell_name(tp, sl): (tp, sl) for tp, sl in CELLS}
PRIMARY_ARMS = [cell_name(*c) for c in PRIMARY]


# ── 산술 ────────────────────────────────────────────────────────────────────
def rw_hit(tp, sl):
    """무편향 랜덤워크에서 익절에 먼저 닿을 확률 = SL/(TP+SL). 무손절은 정의 없음."""
    return None if sl is None else sl / (tp + sl)


def breakeven_win(tp, sl, fee=FEE):
    return None if sl is None else (sl + fee) / (tp + sl)


def need_lift(tp, sl, fee=FEE):
    """손익분기 − 랜덤워크 = FEE/(TP+SL). **넓힐수록 작아진다.**"""
    return None if sl is None else fee / (tp + sl)


# ── 배리어 규칙 — 문턱 교차표 한 번으로 27셀 전부 ───────────────────────────
# 셀마다 다시 훑으면 같은 봉을 27번 읽는다. 그런데 셀 (tp, sl) 의 결과는
#   j_up[tp] = 유리 이탈이 tp 에 처음 닿은 봉 / j_dn[sl] = 불리 이탈이 sl 에 처음 닿은 봉
# 둘로 완전히 결정된다(더 이른 쪽이 청산, 같으면 동률). 그래서 **문턱 11개**(익절 3 +
# 손절 8)의 첫 교차만 한 번의 전방 스캔으로 구하면 27셀이 전부 나온다 — 셀 수와 무관하게
# 봉당 비용이 상수다. 낙관 판도 같은 교차표에서 동률 처리만 뒤집어 공짜로 얻는다.
# (test_tp_1h 가 이 최적화가 셀별 계산과 완전히 같음을 고정한다.)
TPS_SORTED = sorted(TP_LEVELS)
SLS_SORTED = sorted(x for x in SL_LEVELS if x is not None)
TP_IDX = {v: i for i, v in enumerate(TPS_SORTED)}
SL_IDX = {v: i for i, v in enumerate(SLS_SORTED)}


def crossings(rows, si, direction, max_scan):
    """(j_up, j_dn, end, base) — 문턱별 첫 교차 봉. **진입 봉 이후만** 본다(인과적)."""
    base = rows[si]["c"]
    if base <= 0:
        return None
    is_long = direction == "long"
    end = min(si + max_scan, len(rows) - 1)
    nt, ns = len(TPS_SORTED), len(SLS_SORTED)
    j_up, j_dn = [None] * nt, [None] * ns
    nu = nd = 0
    mu = md = -1.0
    for j in range(si + 1, end + 1):
        r = rows[j]
        if is_long:
            up, dn = (r["h"] - base) / base, (base - r["l"]) / base
        else:
            up, dn = (base - r["l"]) / base, (r["h"] - base) / base
        if up > mu:
            mu = up
            while nu < nt and mu >= TPS_SORTED[nu]:
                j_up[nu] = j
                nu += 1
        if dn > md:
            md = dn
            while nd < ns and md >= SLS_SORTED[nd]:
                j_dn[nd] = j
                nd += 1
        if nu == nt and nd == ns:
            break
    return j_up, j_dn, end, base


def _resolve(cross, rows, si, direction, tp, sl, optimistic=False):
    """교차표에서 한 셀을 읽는다 → (ret, hold, reason, tie)."""
    j_up, j_dn, end, base = cross
    ju = j_up[TP_IDX[tp]]
    jd = None if sl is None else j_dn[SL_IDX[sl]]
    if ju is None and jd is None:
        px = rows[end]["o"]
        rr = (px - base) / base if direction == "long" else (base - px) / base
        return rr - FEE, end - si, "open", False
    if jd is None or (ju is not None and ju < jd):
        return tp - FEE, ju - si, "target", False
    if ju is None or jd < ju:
        return -sl - FEE, jd - si, "stop", False
    # 같은 봉 — 동률. 기본은 손절 우선(보수적), 낙관 판은 익절.
    return (((tp - FEE) if optimistic else (-sl - FEE)), ju - si,
            ("target" if optimistic else "stop"), True)


def outcomes_all(rows, si, direction, cells, max_scan, optimistic=False):
    """각 셀에 대해 (ret, hold, reason, tie). 전방 스캔 1회."""
    cross = crossings(rows, si, direction, max_scan)
    if cross is None:
        return None
    return [_resolve(cross, rows, si, direction, tp, sl, optimistic) for tp, sl in cells]


# ── P2 전용 포트 (한 번에 하나·전액·순차 복리) ──────────────────────────────
def pot_curve(recs, lev, start=POT_START):
    """recs: [(entry_num, exit_num, ret)] — 시간순, 열려 있는 동안 온 신호는 버린다."""
    if not recs:
        return None
    seq = sorted(recs)
    eq, peak, mdd, busy, taken, skipped = start, start, 0.0, None, 0, 0
    first = last = None
    for e, x, ret in seq:
        if busy is not None and e < busy:
            skipped += 1
            continue
        eq *= (1 + lev * ret)
        taken += 1
        busy = x if x > e else e + 1e-9
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
    yrs = max(1.0, (last or 0) - (first or 0)) / 365.25
    return dict(mult=eq / start, final=eq,
                cagr=((eq / start) ** (1 / yrs) - 1) if eq > 0 else -1.0,
                mdd=mdd, taken=taken, skipped=skipped)


# ── 통계 ────────────────────────────────────────────────────────────────────
def holm(pvals):
    items = sorted(((k, v) for k, v in pvals.items() if v is not None), key=lambda x: x[1])
    m, out, prev = len(items), {}, 0.0
    for i, (k, p) in enumerate(items):
        prev = max(prev, min(1.0, (m - i) * p))
        out[k] = prev
    return out


def summarize(recs):
    """recs: [(date, ret, hold, reason, tie)]"""
    if not recs:
        return None
    rets = [r[1] for r in recs]
    n = len(rets)
    return dict(n=n, mean=st.mean(rets), median=st.median(rets),
                winrate=sum(1 for x in rets if x > 0) / n,
                mean_stressed=st.mean(rets) - (FRICTION - FEE),
                maxloss=min(rets), avghold=st.mean(r[2] for r in recs),
                tie_rate=sum(1 for r in recs if r[4]) / n,
                open_rate=sum(1 for r in recs if r[3] == "open") / n)


def halves(recs):
    if len(recs) < 4:
        return dict(n1=0, m1=0.0, n2=0, m2=0.0)
    o = sorted(recs, key=lambda r: r[0])
    h = len(o) // 2
    return dict(n1=h, m1=st.mean(r[1] for r in o[:h]),
                n2=len(o) - h, m2=st.mean(r[1] for r in o[h:]))


def boot_edge_p(wins, rand_rate, n=BOOT_N, seed=BOOT_SEED):
    """패턴 승률이 무작위 진입 승률보다 높은가 — 부트스트랩 단측 p."""
    if not wins or rand_rate is None:
        return 1.0
    rng = random.Random(seed)
    k = len(wins)
    return sum(1 for _ in range(n)
               if sum(wins[rng.randrange(k)] for _ in range(k)) / k <= rand_rate) / n


# ── 수집 ────────────────────────────────────────────────────────────────────
def random_baseline(rows_by, direction, cutoff, max_scan):
    rng = random.Random(RAND_SEED)
    pool = [(rows, i) for rows in rows_by.values() for i in range(30, len(rows) - 2)]
    if not pool:
        return None
    pick = pool if len(pool) <= RAND_N else rng.sample(pool, RAND_N)
    buckets = {cell_name(tp, sl): {"train": [], "holdout": []} for tp, sl in CELLS}
    for rows, i in pick:
        cross = crossings(rows, i, direction, max_scan)
        if cross is None:
            continue
        sp = "train" if rows[i]["date"] < cutoff else "holdout"
        for tp, sl in CELLS:
            o = _resolve(cross, rows, i, direction, tp, sl)
            buckets[cell_name(tp, sl)][sp].append((rows[i]["date"], o[0], o[1], o[2], o[3]))
    return {m: {sp: summarize(v) for sp, v in b.items()} for m, b in buckets.items()}


def run_pattern(detmod, direction, rows_by, cutoff, max_scan):
    mod = importlib.import_module(detmod)
    sigs = []
    for rows in rows_by.values():
        if len(rows) < 40:
            continue
        for si in mod.detect(rows):
            if si + 1 < len(rows):
                sigs.append((rows, si))
    n_all = len(sigs)
    if n_all > SIG_CAP:
        sigs = random.Random(SIG_SEED).sample(sigs, SIG_CAP)
    arms = {cell_name(tp, sl): {"train": [], "holdout": []} for tp, sl in CELLS}
    opt = {m: {"train": [], "holdout": []} for m in PRIMARY_ARMS}
    pot = {m: [] for m in PRIMARY_ARMS}
    for rows, si in sigs:
        cross = crossings(rows, si, direction, max_scan)
        if cross is None:
            continue
        sp = "train" if rows[si]["date"] < cutoff else "holdout"
        d0 = rows[si]["date"]
        for tp, sl in CELLS:
            m = cell_name(tp, sl)
            o = _resolve(cross, rows, si, direction, tp, sl)
            arms[m][sp].append((d0, o[0], o[1], o[2], o[3]))
            if m in PRIMARY_ARMS:
                xi = min(si + o[1], len(rows) - 1)
                pot[m].append((_tnum(rows, si), _tnum(rows, xi), o[0]))
                # 낙관 판은 **같은 교차표**에서 동률 처리만 뒤집어 얻는다(스캔 1회).
                oo = _resolve(cross, rows, si, direction, tp, sl, optimistic=True)
                opt[m][sp].append((d0, oo[0], oo[1], oo[2], oo[3]))
    return arms, opt, pot, n_all, len(sigs)


def _tnum(rows, i):
    """봉 ts(ms) → 분수 일수. ts 가 없으면 날짜 ordinal 폴백."""
    ts = rows[i].get("ts")
    if ts:
        return float(ts) / 86_400_000.0
    import datetime as _dt
    y, mo, d = (int(x) for x in rows[i]["date"].split("-"))
    return float(_dt.date(y, mo, d).toordinal())


def verdict(cell, tr, ho, rand_win, hv, holm_p):
    tp, sl = CELL_OF[cell]
    be, rw = breakeven_win(tp, sl), rw_hit(tp, sl)
    c1 = tr["mean"] > 0
    c2 = True if be is None else tr["winrate"] > be        # 무손절은 N/A (사전 규정)
    c3 = True if rw is None else tr["winrate"] > rw
    c4 = rand_win is not None and tr["winrate"] > rand_win and holm_p < 0.05
    c5 = tr["mean_stressed"] > 0
    c6 = hv["m1"] > 0 and hv["m2"] > 0
    c7 = bool(ho) and ho["mean"] > 0
    return dict(pass_=bool(c1 and c2 and c3 and c4 and c5 and c6 and c7),
                c1_mean=c1, c2_breakeven=c2, c3_lift=c3, c4_edge=c4,
                c5_friction=c5, c6_halves=c6, c7_holdout=c7,
                na_barrier_ref=(be is None))


def _fmt_pct(x, w=8, d=1):
    return f"{'-':>{w}}" if x is None else f"{x:>{w}.{d}%}"


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    tfs = TFS
    for i, a in enumerate(argv):
        if a == "--tf" and i + 1 < len(argv):
            tfs = tuple(x.strip() for x in argv[i + 1].split(","))
    syms = va._syms()
    print(f"[표본] {len(syms)}종목 · 패턴 {len(PATS)}종 · TF {tfs} (주 판정 {PRIMARY_TF})")
    print(f"[격자] 익절 {[f'{x:.0%}' for x in TP_LEVELS]} x 손절 "
          f"{['무손절' if x is None else f'{x:.0%}' for x in SL_LEVELS]} = {len(CELLS)}셀")
    print(f"[주 판정] {PRIMARY_ARMS} (Holm m={len(PRIMARY_ARMS)}) — 사용자 지목 4셀")
    print("[산술] 필요 리프트 = 수수료/(익절+손절): " + " · ".join(
        f"{cell_name(tp, sl)} " + ("N/A" if need_lift(tp, sl) is None
                                   else f"{need_lift(tp, sl)*100:+.2f}p")
        for tp, sl in PRIMARY))
    print("[레버리지] 기준 ①~⑦ 과 무관(배리어는 가격 수익률). "
          f"P2 전용 포트 {POT_LEVS}x 스윕으로만 잰다")
    print(f"[반영] DEPLOY_ON_PASS={DEPLOY_ON_PASS} — 통과해도 실거래 변경 없음\n")
    if "--no-fetch" not in argv:
        va.fetch(syms, list(tfs))

    out = {}
    for tf in tfs:
        rows_by = va.load_tf(syms, tf)
        if not rows_by:
            print(f"[{tf}] 데이터 없음 — 건너뜀")
            continue
        last = max(r["date"] for rows in rows_by.values() for r in rows)
        from datetime import date as _d, timedelta as _td
        cutoff = (_d(*(int(x) for x in last.split("-")))
                  - _td(days=HOLDOUT_BY_TF[tf])).isoformat()
        ms = MAX_SCAN_BY_TF[tf]
        nb = sum(len(v) for v in rows_by.values())
        print(f"[{tf}] {len(rows_by)}종목 {nb:,}봉 | train < {cutoff} <= holdout "
              f"(마지막 {HOLDOUT_BY_TF[tf]}일) | 스캔한도 {ms}봉", flush=True)

        rnd = {}
        for d in ("long", "short"):
            rnd[d] = random_baseline(rows_by, d, cutoff, ms)
            print(f"  [무작위 베이스라인] {tf} {d} 준비", flush=True)

        pats, pot_all = {}, {m: [] for m in PRIMARY_ARMS}
        for lb, direction, detmod in PATS:
            arms, opt, pot, n_all, n_used = run_pattern(detmod, direction, rows_by,
                                                        cutoff, ms)
            pats[lb] = dict(direction=direction, arms=arms, opt=opt)
            for m in PRIMARY_ARMS:
                pot_all[m] += pot[m]
            cap = f" → {n_used:,} 표집(상한)" if n_used < n_all else ""
            print(f"  [{lb}] 신호 {n_all:,}{cap}", flush=True)

        pooled, wins_by = {}, {}
        for tp, sl in CELLS:
            m = cell_name(tp, sl)
            for sp in ("train", "holdout"):
                recs, rw_num, rw_den = [], 0.0, 0
                for P in pats.values():
                    v = P["arms"][m][sp]
                    if not v:
                        continue
                    recs += v
                    rb = (rnd[P["direction"]] or {}).get(m, {}).get(sp)
                    if rb:
                        rw_num += len(v) * rb["winrate"]
                        rw_den += len(v)
                s = summarize(recs)
                if s:
                    s["rand_winrate"] = rw_num / rw_den if rw_den else None
                    s["halves"] = halves(recs)
                    if sp == "train":
                        wins_by[m] = [1 if r[1] > 0 else 0 for r in recs]
                pooled.setdefault(m, {})[sp] = s
        opt_pool = {m: {sp: summarize(sum((P["opt"][m][sp] for P in pats.values()), []))
                        for sp in ("train", "holdout")} for m in PRIMARY_ARMS}
        pots = {m: {f"{lv}x": pot_curve(pot_all[m], lv) for lv in POT_LEVS}
                for m in PRIMARY_ARMS}
        out[tf] = dict(cutoff=cutoff, n_symbols=len(rows_by), n_bars=nb,
                       pooled=pooled, opt=opt_pool, pot=pots, wins=wins_by)

        print("\n" + "=" * 158)
        print(f"[{tf}] 배리어 격자 — 익절/손절만. 동률은 손절 우선(보수적). * = 주 판정")
        print("=" * 158)
        for sp in ("train", "holdout"):
            print(f"\n  [{sp}]  {'셀':<8}{'익절':>5}{'손절':>7}{'n':>7}{'건당':>8}"
                  f"{'마찰0.4%':>10}{'승률':>8}{'랜덤워크':>9}{'리프트':>8}{'분기점':>8}"
                  f"{'필요리프트':>11}{'무작위':>8}{'엣지':>8}{'동률':>7}{'미해소':>7}"
                  f"{'보유':>8}{'최대손실':>10}")
            print("  " + "-" * 156)
            for tp, sl in CELLS:
                m = cell_name(tp, sl)
                r = pooled.get(m, {}).get(sp)
                if not r:
                    continue
                rwv, be, nl = rw_hit(tp, sl), breakeven_win(tp, sl), need_lift(tp, sl)
                rd = r.get("rand_winrate")
                star = " *" if m in PRIMARY_ARMS else "  "
                slt = "무손절" if sl is None else f"{sl:.0%}"
                print(f"  {m:<6}{star}{tp:>5.0%}{slt:>7}{r['n']:>7}"
                      f"{r['mean']*100:>+7.2f}%{r['mean_stressed']*100:>+9.2f}%"
                      f"{r['winrate']:>8.1%}{_fmt_pct(rwv, 9)}"
                      + (f"{'-':>8}" if rwv is None else f"{(r['winrate']-rwv)*100:>+7.1f}p")
                      + _fmt_pct(be, 8)
                      + (f"{'-':>11}" if nl is None else f"{nl*100:>+10.2f}p")
                      + _fmt_pct(rd, 8)
                      + (f"{'-':>8}" if rd is None else f"{(r['winrate']-rd)*100:>+7.1f}p")
                      + f"{r['tie_rate']:>7.1%}{r['open_rate']:>7.1%}"
                        f"{r['avghold']:>8.1f}{r['maxloss']*100:>+9.1f}%")

    print("\n" + "=" * 158)
    print(f"사전 등록 판정 — TF {PRIMARY_TF} · 주 판정 {PRIMARY_ARMS}")
    print("=" * 158)
    verdicts, raw_p = {}, {}
    P = out.get(PRIMARY_TF)
    if not P:
        print(f"  {PRIMARY_TF} 데이터 없음 — 판정 불가")
    else:
        for m in PRIMARY_ARMS:
            tr = P["pooled"].get(m, {}).get("train")
            if tr:
                raw_p[m] = boot_edge_p(P["wins"].get(m, []), tr.get("rand_winrate"))
        hp = holm(raw_p)
        for m in PRIMARY_ARMS:
            tp, sl = CELL_OF[m]
            tr = P["pooled"].get(m, {}).get("train")
            ho = P["pooled"].get(m, {}).get("holdout")
            if not tr:
                print(f"\n  [{m}] train 거래 없음")
                continue
            rb = tr.get("rand_winrate")
            v = verdict(m, tr, ho, rb, tr["halves"], hp.get(m, 1.0))
            verdicts[m] = v
            slt = "무손절" if sl is None else f"{sl:.0%}"
            print(f"\n  [{m}] 익절 {tp:.0%} / 손절 {slt}   (n={tr['n']:,})")
            for nm, k in (("①건당>0", "c1_mean"), ("②승률>손익분기", "c2_breakeven"),
                          ("③리프트>0", "c3_lift"), ("④패턴엣지>0 & Holm p<.05", "c4_edge"),
                          ("⑤마찰0.4%>0", "c5_friction"), ("⑥전후반양수", "c6_halves"),
                          ("⑦holdout건당>0", "c7_holdout")):
                na = v["na_barrier_ref"] and k in ("c2_breakeven", "c3_lift")
                print(f"      {'-' if na else ('O' if v[k] else 'X')} {nm}"
                      + ("  (무손절 — 기준값 정의 없음, 사전 규정대로 N/A)" if na else ""))
            be, rw, nl = breakeven_win(tp, sl), rw_hit(tp, sl), need_lift(tp, sl)
            if rw is not None:
                print(f"      승률 {tr['winrate']:.2%} | 랜덤워크 {rw:.2%} | 손익분기 {be:.2%} "
                      f"(필요 리프트 {nl*100:+.2f}p) → 리프트 {(tr['winrate']-rw)*100:+.2f}p")
            else:
                print(f"      승률 {tr['winrate']:.2%} (무손절 — 랜덤워크 기준값 없음)")
            print(f"      무작위 진입 {_fmt_pct(rb, 6, 2).strip()} → **패턴 엣지 "
                  f"{((tr['winrate']-rb)*100 if rb is not None else 0):+.2f}p** "
                  f"(boot_p {raw_p.get(m, 1.0):.3f} → Holm {hp.get(m, 1.0):.3f})")
            print(f"      건당 {tr['mean']*100:+.2f}% / 마찰0.4% {tr['mean_stressed']*100:+.2f}%"
                  + (f" | holdout n={ho['n']:,} {ho['mean']*100:+.2f}%" if ho else ""))
            print(f"      동률 {tr['tie_rate']:.1%} · 미해소 {tr['open_rate']:.1%} "
                  f"· 보유 {tr['avghold']:.1f}봉 · 최대손실 {tr['maxloss']*100:+.1f}%")
            ob = P["opt"][m]["train"]
            if ob and tr["tie_rate"] > 0:
                print(f"      [진단 상한] 동률을 전부 익절로 돌리면 승률 {ob['winrate']:.2%} "
                      f"건당 {ob['mean']*100:+.2f}% — 진실은 보수와 이 값 사이. "
                      f"**판정은 보수 판(사전 등록).**")
            pl = P["pot"][m]
            cells_txt = " · ".join(
                f"{lv}x {pl[lv]['mult']:.2f}배(CAGR {pl[lv]['cagr']*100:+.0f}% "
                f"MDD {pl[lv]['mdd']*100:+.0f}%)" if pl[lv] else f"{lv}x -"
                for lv in (f"{x}x" for x in POT_LEVS))
            print(f"      [P2 전용포트 레버리지] {cells_txt}")
            print(f"      => {'PASS' if v['pass_'] else 'REJECTED'}")

    if "1d" in out and PRIMARY_TF in out:
        print("\n  [해상도 확인] 동률 비율 — 청산 봉이 양쪽 배리어를 다 건드린 비율")
        for m in PRIMARY_ARMS + ["T1S1", "T1S2", "T3S8"]:
            a = out[PRIMARY_TF]["pooled"].get(m, {}).get("train")
            b = out["1d"]["pooled"].get(m, {}).get("train")
            if a and b:
                print(f"      {m:<7} 1h {a['tie_rate']:>6.1%}  vs  1d {b['tie_rate']:>6.1%}"
                      + ("   ← 주 판정" if m in PRIMARY_ARMS else ""))

    for tf in out:
        out[tf].pop("wins", None)
    json.dump(dict(config=dict(tfs=list(tfs), primary_tf=PRIMARY_TF,
                               tp=list(TP_LEVELS),
                               sl=["none" if x is None else x for x in SL_LEVELS],
                               primary=PRIMARY_ARMS, max_scan=MAX_SCAN_BY_TF,
                               holdout=HOLDOUT_BY_TF, fee=FEE, friction=FRICTION,
                               pot_levs=list(POT_LEVS), deploy_on_pass=DEPLOY_ON_PASS),
                   by_tf=out, verdicts=verdicts, boot_p=raw_p),
              open("_tp_1h.json", "w", encoding="utf-8"), ensure_ascii=False,
              indent=1, default=str)
    print("\n[저장] _tp_1h.json")
    print("RESULT_JSON: " + json.dumps(dict(
        tf=PRIMARY_TF, deployed=False,
        cells={m: dict(
            verdict="PASS" if verdicts.get(m, {}).get("pass_") else "REJECTED",
            n=(P["pooled"][m]["train"]["n"] if P and P["pooled"].get(m, {}).get("train") else 0),
            win=(round(P["pooled"][m]["train"]["winrate"], 4)
                 if P and P["pooled"].get(m, {}).get("train") else None),
            need=(round(breakeven_win(*CELL_OF[m]), 4)
                  if breakeven_win(*CELL_OF[m]) is not None else None),
            tie=(round(P["pooled"][m]["train"]["tie_rate"], 4)
                 if P and P["pooled"].get(m, {}).get("train") else None))
            for m in PRIMARY_ARMS}), separators=(",", ":"), ensure_ascii=False))


if __name__ == "__main__":
    main()
