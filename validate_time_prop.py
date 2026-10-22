"""
validate_time_prop.py — 시간 비례 보유한도 (A안, 사전 등록 2026-10-22, 사용자 지시 "A안 사전등록해서 돌려줘")

**계기.** 글렌 닐리(NEoWave)의 파동 규모 관점 — 같은 규모의 움직임은 가격과 시간이 비례한다.
지금 방식D 의 보유한도는 TF·패턴과 무관하게 **30봉 고정**이다(4h 면 5일). 6봉 만에 만들어진
바닥과 60봉에 걸쳐 만들어진 바닥에 같은 시간을 준다. 닐리식으로 옮기면 "패턴이 형성되는 데
걸린 시간에 비례해 그 결과가 전개될 시간을 준다" — 보유한도 = k × 형성 봉수.

**대상** — 2026-10-22 1개월 실거래 관찰에서 실제로 돈을 번 4h 바닥형 두 개, 실거래 설정 그대로:
  triple_bottom_4h  (ALL, top30, 롱, 인과 판 detect_detail — 배포 신호 집합과 동일)
  equal_lows_4h     (ALL, top30, 롱)
  형성 봉수 F:  triple_bottom = 신호봉 − L1(첫 저점)
                equal_lows    = 신호봉 − (최저 피봇 ±0.3% 안 피봇 중 가장 이른 것)

────────────────────────────────────────────────────────────────────────────
사전 등록 (결과 보기 전 고정 — registry time_prop_prereg_2026_10_22)

arm:
  D        현행 — 손절 −8% · 레짐 전환 · 보유한도 30봉
  P(k)     보유한도만 H = clip(round(k·F), 6, 180) 봉. 손절·레짐 전환·수수료는 D 와 완전히 같다.
           **주 판정 k = 1.0**. k = 0.5 / 2.0 은 진단 — 사후에 골라 '살았다' 고 하지 않는다.

분할: train < 2025-01-01 <= holdout (validate_portfolio 와 같은 경계).

판정 — 전부 충족해야 ADOPT_CANDIDATE:
  [패턴 단위, 같은 신호 짝지음, diff = P − D]
  P1 전체 표본 두 패턴 합친 평균 diff > 0, 월 클러스터 부트스트랩(1000회) 단측 p < 0.05
  P2 두 패턴 각각 전체 평균 diff > 0 — 한 패턴이 전부 끌고 가지 않는다
  P3 달력 전·후반 둘 다 평균 diff > 0
  P4 holdout 평균 diff > 0
  [포트폴리오 단위 — validate_portfolio 프레임, 슬롯 arm current, 배경은 현 실거래 배포 집합]
  Q1 holdout CAGR·Calmar 둘 다 D 이상
  Q2 train  CAGR·Calmar 둘 다 D 이상
  Q3 holdout 짝지음 블록 부트스트랩 300회 P(P Calmar > D Calmar) >= 0.60

DEPLOY_ON_PASS = False — 통과해도 자동 반영하지 않는다(청산 규칙 변경은 사용자 결정).

사전 확률(결과 전 기록): 약 15%. 레포에서 청산 변형은 E·F·G·H·T·R·X·ATR 손절·조건부 시간손절
까지 전부 기각됐고, D_time(보유 상한만 바꾼 소거 시험)도 크게 졌다. 다만 이번은 '짧게 자르기'가
아니라 '형성 시간에 맞춰 늘리거나 줄이기' 라 기전이 같지 않다. 예상 실패 지점은 P2(한 패턴만
움직임) 또는 Q(늘린 보유가 슬롯을 잡아 포트폴리오에서 상쇄).

알려진 한계: 4h 이력 약 3년(1100일) · 정적 top30 코호트 · 형성 봉수 정의는 디텍터 구조에서
기계적으로 뽑은 것이지 닐리 원문 정의가 아니다(원문 확인 불가, 2차 자료만).

실행: python validate_time_prop.py [--no-fetch]
"""
import json
import random
import statistics as st
import sys

import detlib
import method_t as mt
import method_x as mx
import sizing_vol as sv
import validate_portfolio as vp
import validate_revival as vr
from validate_regime_split import turnover_rank

DEPLOY_ON_PASS = False

K_MAIN = 1.0
K_DIAG = (0.5, 2.0)
H_MIN, H_MAX = 6, 180
TARGETS = ("triple_bottom_4h", "equal_lows_4h")
SPLIT = vp.SPLIT
BOOT_MONTH_N = 1000
BOOT_PORT_N = vp.BOOT_N
SEED = 20261022
P_ALPHA = 0.05
Q3_WIN = 0.60


def hold_limit(F, k):
    """보유한도 H = clip(round(k·F), H_MIN, H_MAX)."""
    return int(min(H_MAX, max(H_MIN, round(k * F))))


# ── 형성 봉수 ─────────────────────────────────────────────────────────────────
def tb_signals(rows):
    """triple_bottom_4h — 배포·검증과 같은 인과 판. [(sig, F)]."""
    import detector_triple_bottom as tb
    return [(d["sig"], d["sig"] - d["L1"]) for d in tb.detect_detail(rows, causal=True)]


def el_signals(rows):
    """equal_lows_4h — detector_equal_lows_4h.detect 와 같은 순회. [(sig, F)]."""
    import detector_equal_lows_4h as el
    out = []
    for i in range(el.LOOKBACK, len(rows)):
        pivots = el._pivot_lows(rows, i - el.LOOKBACK, i)
        if len(pivots) < 2:
            continue
        ref = min(rows[j]["l"] for j in pivots)
        near = [j for j in pivots if abs(rows[j]["l"] - ref) / (ref or 1e-9) <= el.TOLERANCE]
        if len(near) < 2:
            continue
        if abs(rows[i]["l"] - ref) / (ref or 1e-9) <= el.TOLERANCE:
            out.append((i, i - min(near)))
    return out


SIG_FN = {"triple_bottom_4h": tb_signals, "equal_lows_4h": el_signals}


def outcome_h(rows, si, H):
    """방식D 그대로, 보유한도만 H. mt.MAX_HOLD 를 잠시 바꿨다 되돌린다."""
    old = mt.MAX_HOLD
    mt.MAX_HOLD = H
    try:
        return mt.outcome_d(rows, si, "long", set())
    finally:
        mt.MAX_HOLD = old


def collect_targets(rows_by, ranked, ks):
    """대상 두 패턴의 신호마다 D(30봉)·P(k) 결과를 같이 계산한다."""
    rank_of = {s: i for i, s in enumerate(ranked)}
    pool = ranked[:vp.COHORT_N["current"]]
    out = []
    for pat in TARGETS:
        n = 0
        for sym in pool:
            rows = rows_by.get(sym)
            if not rows or len(rows) < 40:
                continue
            for si, F in SIG_FN[pat](rows):
                if si + 1 >= len(rows):
                    continue
                rec = dict(pattern=pat, sym=sym, F=F, rank=rank_of.get(sym, 999),
                           vol=sv.realized_vol(rows, si, tf="4h"), t_in=vr._tnum(rows[si]),
                           month=str(rows[si]["date"])[:7], arms={})
                for arm, H in [("D", mt.MAX_HOLD)] + [(f"P{k}", hold_limit(F, k)) for k in ks]:
                    ret, hold, why = outcome_h(rows, si, H)
                    xi = min(si + hold, len(rows) - 1)
                    rec["arms"][arm] = dict(ret=ret, hold=hold, why=why, H=H, t_out=vr._tnum(rows[xi]))
                out.append(rec)
                n += 1
        print(f"  [{pat}] {n}건", flush=True)
    return out


# ── 패턴 단위 짝지음 ──────────────────────────────────────────────────────────
def month_boot_p(recs, arm, rng, n=BOOT_MONTH_N):
    """월 클러스터 부트스트랩 — 단측 p = P(재표집 평균 diff <= 0)."""
    by = {}
    for r in recs:
        by.setdefault(r["month"], []).append(r["arms"][arm]["ret"] - r["arms"]["D"]["ret"])
    months = list(by)
    if len(months) < 2:
        return 1.0
    le0 = 0
    for _ in range(n):
        d = []
        for _m in range(len(months)):
            d.extend(by[rng.choice(months)])
        le0 += int(st.mean(d) <= 0)
    return le0 / n


def mean_diff(recs, arm):
    d = [r["arms"][arm]["ret"] - r["arms"]["D"]["ret"] for r in recs]
    return st.mean(d) if d else 0.0


def paired_report(recs, arm, cut, rng):
    t_lo = min(r["t_in"] for r in recs)
    t_hi = max(r["t_in"] for r in recs)
    mid = (t_lo + t_hi) / 2
    res = dict(
        n=len(recs),
        diff=mean_diff(recs, arm),
        p=month_boot_p(recs, arm, rng),
        by_pat={p: mean_diff([r for r in recs if r["pattern"] == p], arm) for p in TARGETS},
        n_pat={p: sum(r["pattern"] == p for r in recs) for p in TARGETS},
        half1=mean_diff([r for r in recs if r["t_in"] < mid], arm),
        half2=mean_diff([r for r in recs if r["t_in"] >= mid], arm),
        holdout=mean_diff([r for r in recs if r["t_in"] >= cut], arm),
        n_holdout=sum(r["t_in"] >= cut for r in recs),
        changed=sum(r["arms"][arm]["hold"] != r["arms"]["D"]["hold"] for r in recs),
        mean_D=st.mean(r["arms"]["D"]["ret"] for r in recs),
        mean_P=st.mean(r["arms"][arm]["ret"] for r in recs),
        hold_D=st.mean(r["arms"]["D"]["hold"] for r in recs),
        hold_P=st.mean(r["arms"][arm]["hold"] for r in recs),
    )
    res["P1"] = res["diff"] > 0 and res["p"] < P_ALPHA
    res["P2"] = all(v > 0 for v in res["by_pat"].values())
    res["P3"] = res["half1"] > 0 and res["half2"] > 0
    res["P4"] = res["holdout"] > 0
    return res


# ── 포트폴리오 단위 ───────────────────────────────────────────────────────────
def to_trade(rec, arm):
    a = rec["arms"][arm]
    return dict(t_in=rec["t_in"], t_out=a["t_out"], ret=a["ret"], pattern=rec["pattern"],
                sym=rec["sym"], vol=rec["vol"], tf="4h", rank=rec["rank"])


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    ks = (K_MAIN,) + K_DIAG
    print("=" * 100)
    print("시간 비례 보유한도 (A안, 사전 등록 2026-10-22) — 보유한도 = clip(round(k·형성봉수), "
          f"{H_MIN}, {H_MAX})  주 판정 k={K_MAIN}  DEPLOY_ON_PASS={DEPLOY_ON_PASS}")
    print("=" * 100)
    syms = json.load(open("universe.json", encoding="utf-8"))["trading_universe"]
    if "--no-fetch" not in argv:
        vp.fetch(syms)

    import regime_switch as rs
    rows_4h = {}
    for s in syms:
        try:
            rows_4h[s] = detlib.load_ohlcv(s, "4h")
        except (FileNotFoundError, RuntimeError):
            continue
    ranked = turnover_rank(rows_4h)
    regmap = rs.build_regime_map()
    mt.REGMAP = regmap        # 레짐 전환 청산을 켠다(2026-09-21 결함 재발 방지)

    print("\n[1] 대상 두 패턴 — D 와 P(k) 를 같은 신호에서")
    recs = collect_targets(rows_4h, ranked, ks)
    Fs = [r["F"] for r in recs]
    print(f"  형성 봉수 F: 중앙 {st.median(Fs):.0f} · 10~90분위 "
          f"{sorted(Fs)[len(Fs)//10]}~{sorted(Fs)[len(Fs)*9//10]} · 최소 {min(Fs)} 최대 {max(Fs)}")
    for k in ks:
        Hs = [r['arms'][f'P{k}']['H'] for r in recs]
        print(f"  P{k} 보유한도 H: 중앙 {st.median(Hs):.0f} · 30봉 미만 {sum(h < 30 for h in Hs)}건"
              f" · 초과 {sum(h > 30 for h in Hs)}건")

    cut = mx._tnum(SPLIT)
    rng = random.Random(SEED)
    paired = {}
    print("\n[2] 패턴 단위 짝지음 (diff = P − D, %p)")
    for k in ks:
        arm = f"P{k}"
        r = paired_report(recs, arm, cut, rng)
        paired[arm] = r
        tag = "주 판정" if k == K_MAIN else "진단"
        print(f"  {arm:5} [{tag}] n={r['n']} 보유가 달라진 거래 {r['changed']} | 평균 D {r['mean_D']*100:+.2f}% → "
              f"P {r['mean_P']*100:+.2f}% (보유 {r['hold_D']:.1f} → {r['hold_P']:.1f}봉)")
        print(f"        diff {r['diff']*100:+.3f}%p 월부트 p {r['p']:.3f} | 패턴별 "
              + " / ".join(f"{p} {v*100:+.3f}(n{r['n_pat'][p]})" for p, v in r["by_pat"].items())
              + f" | 전반 {r['half1']*100:+.3f} 후반 {r['half2']*100:+.3f} | holdout(n{r['n_holdout']}) "
              f"{r['holdout']*100:+.3f}")
        print(f"        P1 {r['P1']} P2 {r['P2']} P3 {r['P3']} P4 {r['P4']}")

    print("\n[3] 포트폴리오 배경 — 현 실거래 배포 집합 (2026-10-22: marubozu·tp1 정지 반영)")
    t1d = [t for t in vp.collect_1d(syms) if t["pattern"] != "marubozu"]
    t4h_all = vp.collect_4h(rows_4h, ranked, regmap)
    t4h_other = [t for t in t4h_all if t["pattern"] not in TARGETS]
    vp_targets = sorted((t["pattern"], t["sym"], round(t["t_in"], 6), round(t["ret"], 10))
                        for t in t4h_all if t["pattern"] in TARGETS)
    mine_d = sorted((r["pattern"], r["sym"], round(r["t_in"], 6), round(r["arms"]["D"]["ret"], 10))
                    for r in recs)
    same = vp_targets == mine_d
    print(f"  정합 점검: validate_portfolio 의 대상 D 거래와 이 판의 D 가 {'완전히 같다' if same else '다르다 — 판정 무효'}"
          f" ({len(vp_targets)} vs {len(mine_d)})")

    def book(arm):
        return sorted(t1d + t4h_other + [to_trade(r, arm) for r in recs], key=lambda t: t["t_in"])

    port = {}
    for arm in ["D"] + [f"P{k}" for k in ks]:
        b = book(arm)
        tr = vp.simulate([t for t in b if t["t_in"] < cut], "current")
        ho = vp.simulate([t for t in b if t["t_in"] >= cut], "current")
        port[arm] = dict(train=tr, holdout=ho)
        print(f"  {arm:5} train CAGR {tr['cagr']*100:+7.1f}% Calmar {tr['calmar']:5.2f} | holdout CAGR "
              f"{ho['cagr']*100:+7.1f}% MDD {ho['mdd']*100:6.1f}% Calmar {ho['calmar']:5.2f} "
              f"체결 {ho['taken']} 스킵 슬롯 {ho['skip_slot']} 증거금 {ho['skip_margin']}")

    print(f"\n[4] holdout 짝지음 블록 부트스트랩 {BOOT_PORT_N}회 — 대상 거래의 짝을 유지한 채 재표집")
    ho_recs = [r for r in recs if r["t_in"] >= cut]
    ho_other = [t for t in t1d + t4h_other if t["t_in"] >= cut]
    # 짝 유지: 블록 재표집을 '레코드 인덱스' 로 한 번 뽑고 그 인덱스를 모든 arm 에 쓴다.
    units = [("o", i) for i in range(len(ho_other))] + [("r", i) for i in range(len(ho_recs))]
    units.sort(key=lambda u: ho_other[u[1]]["t_in"] if u[0] == "o" else ho_recs[u[1]]["t_in"])
    brng = random.Random(SEED + 1)
    wins = {f"P{k}": 0 for k in ks}

    def t_of(u):
        return ho_other[u[1]]["t_in"] if u[0] == "o" else ho_recs[u[1]]["t_in"]

    for _ in range(BOOT_PORT_N):
        idx = []
        while len(idx) < len(units):
            s = brng.randrange(0, len(units))
            idx.extend(range(s, min(len(units), s + vp.BLOCK)))
        idx = idx[:len(units)]
        books = {}
        for arm in ["D"] + [f"P{k}" for k in ks]:
            out = []
            for k_pos, j in enumerate(idx):
                src = units[j]
                t0 = t_of(units[k_pos])
                tr = ho_other[src[1]] if src[0] == "o" else to_trade(ho_recs[src[1]], arm)
                out.append(dict(tr, t_in=t0, t_out=t0 + max(tr["t_out"] - tr["t_in"], 0.0)))
            books[arm] = vp.simulate(out, "current")["calmar"]
        for k in ks:
            wins[f"P{k}"] += int(books[f"P{k}"] > books["D"])
    for k in ks:
        print(f"  P(P{k} Calmar > D) = {wins[f'P{k}']/BOOT_PORT_N:.0%}")

    print("\n[5] 판정 (P1~P4, Q1~Q3 전부)")
    verdicts = {}
    for k in ks:
        arm = f"P{k}"
        pr, pD = port[arm], port["D"]
        q = dict(Q1=pr["holdout"]["cagr"] >= pD["holdout"]["cagr"] and pr["holdout"]["calmar"] >= pD["holdout"]["calmar"],
                 Q2=pr["train"]["cagr"] >= pD["train"]["cagr"] and pr["train"]["calmar"] >= pD["train"]["calmar"],
                 Q3=wins[arm] / BOOT_PORT_N >= Q3_WIN)
        pp = {c: paired[arm][c] for c in ("P1", "P2", "P3", "P4")}
        ok = same and all(pp.values()) and all(q.values())
        verdicts[arm] = dict(pass_all=ok, consistency=same, **pp, **q)
        fails = [c for c, v in {**pp, **q}.items() if not v] + ([] if same else ["정합"])
        tag = "주 판정" if k == K_MAIN else "진단"
        print(f"  {arm:5} [{tag}] {'ADOPT_CANDIDATE' if ok else 'REJECTED'}"
              f"{'' if ok else '  실패: ' + ','.join(fails)}")
    main_v = verdicts[f"P{K_MAIN}"]
    print(f"\n판정(주 판정 k={K_MAIN}): {'ADOPT_CANDIDATE' if main_v['pass_all'] else 'REJECTED'}"
          f"   (DEPLOY_ON_PASS={DEPLOY_ON_PASS} — 반영은 사용자 결정, 진단 k 는 사후 선택 금지)")

    def slim(d):
        return {k: v for k, v in d.items() if k != "blocked_by"}

    json.dump(dict(prereg="time_prop_prereg_2026_10_22", k_main=K_MAIN, k_diag=list(K_DIAG),
                   h_bounds=[H_MIN, H_MAX], split=SPLIT, deploy_on_pass=DEPLOY_ON_PASS,
                   n=len(recs), paired=paired,
                   portfolio={a: {s: slim(v) for s, v in d.items()} for a, d in port.items()},
                   boot_win={a: w / BOOT_PORT_N for a, w in wins.items()},
                   verdicts=verdicts),
              open("_time_prop.json", "w"), indent=1, ensure_ascii=False, default=str)
    print("\n저장: _time_prop.json")


if __name__ == "__main__":
    main()
