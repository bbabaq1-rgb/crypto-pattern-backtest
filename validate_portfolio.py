"""
validate_portfolio.py — 포트폴리오 단위 확인 프레임 (사전 등록, 2026-09-10 사용자 승인)

**왜 필요한가.** 지금까지의 확인 시험(revival C3 / guard v4·v5 / engulf_tf)은 셀 하나를 홀로
자산곡선에 올린다. 그 프레임은 **슬롯 경합을 구조적으로 못 본다** — 연 약 1,900건을 쏘는
vol_awakening_4h 가 MAX_POS 16 을 채워 건당 두꺼운 1d 신호를 밀어내도, 패턴 단독 곡선에는
그 비용이 한 푼도 안 잡힌다. 2026-09-10 실측에서 실포지션 12건 중 8건이 vol_awakening_4h 였다.

레포에 같은 기전으로 기각한 선례가 있다 — bear fvg 롱(2026-09-05): 셀 자체는 +1.63% 인데
"건당 +1.6% 거래가 슬롯·증거금을 차지해 건당 +7.3% 자리를 빼앗는다" 로 holdout −43→−66%.
그 판정을 내린 도구가 바로 포트폴리오 곡선이었고, 지금 슬롯 정책에는 그 도구가 없다.

**이 시험이 답하는 것**: 배포 집합 전체를 한 자산곡선에 올렸을 때, 슬롯 배분 규칙을 바꾸면
포트폴리오가 나아지는가. 셀별 성적이 아니라 **포트폴리오 Calmar·CAGR** 로만 판정한다.

────────────────────────────────────────────────────────────────────────────
사전 등록 (결과 보기 전 고정 — registry portfolio_prereg_2026_09_10)

대상(배포 집합, 슬롯을 두고 경쟁하는 것만):
  1d  engulfing 롱·숏 / fvg 롱·숏  — 레짐→방향 라우팅(direction_switch) 적용, 패턴별 유니버스
  1d  inverted_hammer / marubozu   — 레짐 게이트 없음, 메이저 7종목
  4h  three_soldiers_4h(bull 만) / triple_bottom_4h(ALL) / equal_lows_4h(ALL) / vol_awakening_4h(ALL)
      — 전부 top30 코호트, 롱
  제외: cascade_fade_long_1h(±1.5ATR·12봉 = 보유 12h, 3년 n=312 → 슬롯 발자국이 사실상 0)
        tp1_engulfing_1h(별도 자본·자체 max_open, MAX_LIVE_POS 면제)
  제외 사유는 known_limits 에 남긴다 — 결과를 보고 뺀 것이 아니다.

청산: 전 셀 방식D(-8% 손절 + 레짐전환 + 30봉) — 실거래와 같다.
사이징: 실거래 그대로(sizing.risk_based_size + 변동성 타겟팅 sz.vol_scale, RISK_FRAC 1.5%,
        LEV_CAP 3, MAX_POS 16, START_EQ 1000). arm 마다 **바꾸지 않는다** — 바뀌는 건 슬롯 배분뿐.

arm (슬롯 배분 규칙만 다르다):
  current   현행 복제. 같은 시각 경합 시 1d 우선, 그다음 거래대금 순위.
            (실거래 앙상블 등급이 1d=C·4h=D 로 갈리는 것을 그대로 옮긴 것 — 2026-09-09 실측)
  cap4/6/8  어떤 패턴도 동시 N 슬롯 초과 불가. 나머지는 current 와 동일.
  prio_edge 우선순위를 **슬롯일당 기대값**(패턴 평균수익 ÷ 평균보유일)으로. 추정은 **인과적**
            — 그 시점까지 이미 청산된 거래만 쓴다(확장평균). 표본 <20 인 패턴은 중립(0).
  cohort20  4h 네 패턴의 코호트를 top30 → top20 으로 축소. 나머지는 current 와 동일.

분할: train < 2025-01-01 <= holdout (guard v4·v5 의 C 축과 같은 경계).
판정(holdout 기준, 다섯 개 전부 충족해야 ADOPT_CANDIDATE):
  J1 CAGR  > current
  J2 Calmar > current
  J3 짝지음 블록 부트스트랩 300회에서 P(arm Calmar > current Calmar) >= 0.60
  J4 MDD 가 current 보다 5%p 넘게 나빠지지 않는다
  J5 train 에서도 CAGR·Calmar 둘 다 current 이상 (단일 구간 의존 방지)
하나라도 실패하면 현행 유지. 여러 arm 이 통과하면 **holdout Calmar 최대** 하나만 후보.

DEPLOY_ON_PASS = False — 통과해도 자동 반영하지 않는다. 슬롯 규칙은 위험 배분이라
사용자 결정 사항이고, 관찰 기간(~2026-10-06) 중 실거래 규칙 변경 금지가 걸려 있다.

실행: python validate_portfolio.py [--no-fetch]
"""
import json
import random
import statistics as st
import sys
import time

import detlib
import method_t as mt
import method_x as mx
import sizing as sz
import sizing_study as ss
import sizing_vol as sv
import validate_regime_split_all as va
from validate_regime_split import turnover_rank

DEPLOY_ON_PASS = False

STOP = ss.STOP
START_EQ, MAX_POS = ss.START_EQ, ss.MAX_POS
BOOT_N, BLOCK, SEED = ss.BOOT_N, ss.BLOCK, ss.SEED
SPLIT = "2025-01-01"
CAP_GRID = (4, 6, 8)
MIN_N_FOR_EDGE = 20          # prio_edge 확장추정 최소 표본 — 그 전엔 중립
J4_MDD_TOL = 0.05            # MDD 허용 악화폭
J3_WIN = 0.60                # 부트 우위 문턱
FETCH_WINDOWS = {"1d": 1800, "4h": 1100}

# 4h adopted — universe.json 배포 항목과 같은 조건(레짐·코호트·방향)
ADOPTED_4H = [
    # (패턴, 레짐 게이트, 코호트)  게이트 None = 전 레짐 / 코호트 None = 전 종목
    # three_soldiers_4h 는 universe.json 에 regimes·cohort 필드가 **없다** — 스케줄러 기본인
    # 4h bull 게이트 + 전 종목으로 돈다(top30 축소는 미실행 후속 과제). 실거래를 그대로 옮긴다.
    ("three_soldiers_4h", {"bull_btc", "bull_altseason"}, None),
    ("triple_bottom_4h",  None, "top30"),
    ("equal_lows_4h",     None, "top30"),
    ("vol_awakening_4h",  None, "top30"),
]
COHORT_N = {"current": 30, "cohort20": 20}


def fetch(syms):
    import fetch_data
    for tf, win in FETCH_WINDOWS.items():
        t0, ok = time.time(), 0
        for s in syms:
            try:
                _, total = fetch_data.update_csv(f"{s}/USDT", tf, detlib.CSV(s, tf), window_days=win)
                ok += total > 0
            except Exception as e:
                print(f"  [fetch] {s} {tf} 실패: {str(e)[:50]}")
        print(f"[fetch] {tf} {win}일 {ok}/{len(syms)} ({time.time()-t0:.0f}s)", flush=True)


def _live_scale(vol):
    """실거래가 명목가에 곱하는 배율. sizing.vol_scale 과 **같은 식**이되 σ 를 직접 받는다
    (여기서는 σ 를 이미 인과적으로 계산해 레코드에 넣어뒀다). 타겟팅 off / 상수 미설정 /
    σ 없음이면 1.0 — 채택 전 동작과 완전히 같다."""
    if not sz.VOL_TARGETING or not sz.VOL_S_NORM or not vol:
        return 1.0
    return sz.vol_scale_raw(vol) / sz.VOL_S_NORM


def _tf_rank(pattern):
    """current 우선순위의 1차 키 — 1d 가 4h 보다 앞선다(실거래 앙상블 등급 C vs D)."""
    return 1 if pattern.endswith("_4h") else 0


def collect_1d(syms):
    """1d 배포 셀 — sizing_vol 의 라우팅 복제를 그대로 쓴다(같은 코드로 재현)."""
    sv.ROUTING_MODE = True
    raw = sv.collect_all(syms)
    # (entry_date, exit_date, ret, hold, label, sym, vol) → 공통 레코드
    return [dict(t_in=mx._tnum(r[0]), t_out=mx._tnum(r[1]), ret=r[2], pattern=r[4],
                 sym=r[5], vol=r[6], tf="1d", rank=None) for r in raw]


def collect_4h(rows_by, ranked, regmap):
    """4h adopted 4종 — 방식D, top30 코호트, 항목별 레짐 게이트."""
    table = {c[0]: (c[1], c[2], c[3]) for c in va.PATTERNS}
    rank_of = {s: i for i, s in enumerate(ranked)}
    out = []
    for pat, gate, cohort in ADOPTED_4H:
        tf, detect, direction = table[pat]
        n = n_gate = 0
        pool = ranked[:COHORT_N["current"]] if cohort == "top30" else ranked
        for sym in pool:
            rows = rows_by.get(sym)
            if not rows or len(rows) < 40:
                continue
            for si in detect(rows):
                if si + 1 >= len(rows):
                    continue
                if gate is not None and regmap.get(rows[si]["date"]) not in gate:
                    n_gate += 1
                    continue
                ret, hold, _ = mt.outcome_d(rows, si, direction, set())
                xi = min(si + hold, len(rows) - 1)
                out.append(dict(t_in=mx._tnum(rows[si].get("ts") or rows[si]["date"]),
                                t_out=mx._tnum(rows[xi].get("ts") or rows[xi]["date"]),
                                ret=ret, pattern=pat, sym=sym,
                                vol=sv.realized_vol(rows, si, tf="4h"), tf="4h",
                                rank=rank_of.get(sym, 999)))
                n += 1
        print(f"  [{pat}] {n}건 (종목 {len(pool)}, 레짐 제외 {n_gate})", flush=True)
    return out


def simulate(trades, arm, cap=None):
    """
    시간순 포트폴리오 시뮬 — sizing_study/sizing_vol 과 같은 회계.
    arm 이 바꾸는 것은 **슬롯 배분뿐**: 진입 우선순위와 패턴별 상한. 사이징은 실거래 고정.
    """
    evs = []
    for i, t in enumerate(trades):
        evs.append((t["t_out"], -1, i))       # 같은 시각이면 청산 먼저(슬롯을 비우고 경쟁)
        evs.append((t["t_in"], 0, i))
    evs.sort(key=lambda e: (e[0], e[1]))
    equity = free = START_EQ
    open_pos, peak, mdd = {}, START_EQ, 0.0
    taken = skip_slot = skip_cap = skip_margin = 0
    blocked_by = {}                            # 진단: 밀린 패턴 → 그때 점유 패턴 분포
    pat_sum, pat_hold, pat_n = {}, {}, {}      # prio_edge 확장추정(인과적)
    # 같은 시각 진입 후보를 모아 우선순위대로 처리한다
    i = 0
    while i < len(evs):
        t0 = evs[i][0]
        batch = []
        while i < len(evs) and evs[i][0] == t0:
            _, kind, idx = evs[i]
            if kind == -1:
                rec = open_pos.pop(idx, None)
                if rec is not None:
                    margin, notional = rec
                    tr = trades[idx]
                    pnl = notional * tr["ret"]
                    equity += pnl
                    free += margin + pnl
                    peak = max(peak, equity)
                    mdd = min(mdd, equity / peak - 1)
                    p = tr["pattern"]
                    pat_sum[p] = pat_sum.get(p, 0.0) + tr["ret"]
                    pat_hold[p] = pat_hold.get(p, 0.0) + max(tr["t_out"] - tr["t_in"], 0.25)
                    pat_n[p] = pat_n.get(p, 0) + 1
            else:
                batch.append(idx)
            i += 1
        if equity <= 0:
            equity = 0.0
            break
        if not batch:
            continue

        def edge_key(idx):
            p = trades[idx]["pattern"]
            if arm != "prio_edge" or pat_n.get(p, 0) < MIN_N_FOR_EDGE:
                return 0.0
            return -(pat_sum[p] / pat_n[p]) / (pat_hold[p] / pat_n[p])   # 음수 = 앞선다

        batch.sort(key=lambda idx: (edge_key(idx), _tf_rank(trades[idx]["pattern"]),
                                    trades[idx]["rank"] if trades[idx]["rank"] is not None else 500,
                                    trades[idx]["sym"]))
        for idx in batch:
            tr = trades[idx]
            if cap is not None:
                held = sum(1 for j in open_pos if trades[j]["pattern"] == tr["pattern"])
                if held >= cap:
                    skip_cap += 1
                    continue
            if len(open_pos) >= MAX_POS:
                skip_slot += 1
                occ = {}
                for j in open_pos:
                    occ[trades[j]["pattern"]] = occ.get(trades[j]["pattern"], 0) + 1
                b = blocked_by.setdefault(tr["pattern"], {})
                for k, v in occ.items():
                    b[k] = b.get(k, 0) + v
                continue
            s = _live_scale(tr["vol"])
            r = sz.risk_based_size(equity, free, STOP, vol_scale=s,
                                   open_notional=sum(n for _, n in open_pos.values()))
            if r is None:
                skip_margin += 1      # 증거금·최소주문·총명목가 상한(2.5x) 합산
                continue
            free -= r["margin_usd"]
            open_pos[idx] = (r["margin_usd"], r["notional"])
            taken += 1
    span = max(1.0, evs[-1][0] - evs[0][0]) if evs else 1.0
    cagr = (equity / START_EQ) ** (365.25 / span) - 1 if equity > 0 else -1.0
    return dict(final=equity, cagr=cagr, mdd=mdd,
                calmar=(cagr / abs(mdd) if mdd < 0 else float("inf")),
                taken=taken, skip_slot=skip_slot, skip_cap=skip_cap, skip_margin=skip_margin,
                blocked_by=blocked_by)


def block_bootstrap(trades, rng):
    """날짜 골격 유지, (수익·패턴·심볼·변동성·보유)를 블록 단위로 재표집 — sizing_vol 과 같은 방식."""
    n = len(trades)
    idx = []
    while len(idx) < n:
        s = rng.randrange(0, n)
        idx.extend(range(s, min(n, s + BLOCK)))
    idx = idx[:n]
    out = []
    for k, j in enumerate(idx):
        src, dst = trades[j], trades[k]
        hold = max(src["t_out"] - src["t_in"], 0.0)
        out.append(dict(src, t_in=dst["t_in"], t_out=dst["t_in"] + hold))
    return out


ARMS = ["current", "cap4", "cap6", "cap8", "prio_edge", "cohort20"]


def arm_cfg(arm):
    return (arm, int(arm[3:])) if arm.startswith("cap") else (arm, None)


def run_split(trades_by_arm, tag):
    res = {}
    for arm in ARMS:
        a, cap = arm_cfg(arm)
        res[arm] = simulate(trades_by_arm[arm], a, cap)
        r = res[arm]
        print(f"  [{tag}] {arm:10} CAGR {r['cagr']*100:+7.1f}%  MDD {r['mdd']*100:6.1f}%  "
              f"Calmar {r['calmar']:5.2f}  체결 {r['taken']:5}  "
              f"스킵 슬롯 {r['skip_slot']:4} / 상한 {r['skip_cap']:4} / 증거금 {r['skip_margin']:4}",
              flush=True)
    return res


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    print("=" * 100)
    print("포트폴리오 단위 확인 프레임 — 배포 집합 전체를 한 자산곡선에 (사전 등록 2026-09-10)")
    print(f"MAX_POS {MAX_POS} · RISK {sz.RISK_FRAC*100:.1f}% · LEV {sz.LEV_CAP} · 변동성타겟팅 "
          f"{sz.VOL_TARGETING} · 분할 {SPLIT} · DEPLOY_ON_PASS={DEPLOY_ON_PASS}")
    print("=" * 100)
    syms = json.load(open("universe.json", encoding="utf-8"))["trading_universe"]
    if "--no-fetch" not in argv:
        fetch(syms)

    import regime_switch as rs
    rows_4h = {}
    for s in syms:
        try:
            rows_4h[s] = detlib.load_ohlcv(s, "4h")
        except (FileNotFoundError, RuntimeError):
            continue
    ranked = turnover_rank(rows_4h)
    regmap = rs.build_regime_map()

    print("\n[1] 1d 배포 셀 (라우팅 복제)")
    t1d = collect_1d(syms)
    print("\n[2] 4h adopted 셀")
    t4h = collect_4h(rows_4h, ranked, regmap)

    base = sorted(t1d + t4h, key=lambda t: t["t_in"])
    top20 = set(ranked[:COHORT_N["cohort20"]])
    variants = {a: base for a in ARMS}
    # cohort20 은 **top30 코호트로 배포된 4h 셀만** 줄인다. three_soldiers_4h 는 전 종목
    # 배포라 이 arm 의 대상이 아니다(코호트 축소는 별도 사전 등록 과제).
    _c30 = {p for p, _g, c in ADOPTED_4H if c == "top30"}
    variants["cohort20"] = [t for t in base
                            if t["pattern"] not in _c30 or t["sym"] in top20]
    print(f"\n총 거래 {len(base)}건 (1d {len(t1d)} / 4h {len(t4h)}) · cohort20 판 {len(variants['cohort20'])}건")

    cut = mx._tnum(SPLIT)
    tr_by_arm = {a: [t for t in variants[a] if t["t_in"] < cut] for a in ARMS}
    ho_by_arm = {a: [t for t in variants[a] if t["t_in"] >= cut] for a in ARMS}
    print(f"train {len(tr_by_arm['current'])}건 / holdout {len(ho_by_arm['current'])}건\n")

    print("[3] train")
    tr = run_split(tr_by_arm, "train")
    print("\n[4] holdout")
    ho = run_split(ho_by_arm, "holdout")

    print("\n[5] 짝지음 블록 부트스트랩 (holdout, 같은 재표집을 전 arm 에 동일 적용)")
    rng = random.Random(SEED)
    wins = {a: 0 for a in ARMS}
    for _ in range(BOOT_N):
        bs = block_bootstrap(ho_by_arm["current"], rng)
        bs20 = [t for t in bs if t["pattern"] not in _c30 or t["sym"] in top20]
        cur = simulate(bs, "current")["calmar"]
        for arm in ARMS:
            if arm == "current":
                continue
            a, cap = arm_cfg(arm)
            s = simulate(bs20 if arm == "cohort20" else bs, a, cap)["calmar"]
            wins[arm] += int(s > cur)
    for arm in ARMS:
        if arm != "current":
            print(f"  P({arm} Calmar > current) = {wins[arm]/BOOT_N:.0%}")

    print("\n[6] 판정 (J1~J5 전부 충족해야 ADOPT_CANDIDATE)")
    cur_ho, cur_tr = ho["current"], tr["current"]
    verdicts = {}
    for arm in ARMS:
        if arm == "current":
            continue
        h, t = ho[arm], tr[arm]
        j = dict(J1=h["cagr"] > cur_ho["cagr"],
                 J2=h["calmar"] > cur_ho["calmar"],
                 J3=wins[arm] / BOOT_N >= J3_WIN,
                 J4=h["mdd"] >= cur_ho["mdd"] - J4_MDD_TOL,
                 J5=t["cagr"] >= cur_tr["cagr"] and t["calmar"] >= cur_tr["calmar"])
        ok = all(j.values())
        verdicts[arm] = dict(pass_all=ok, **j)
        fails = [k for k, v in j.items() if not v]
        print(f"  {arm:10} {'ADOPT_CANDIDATE' if ok else 'REJECTED'}"
              f"{'' if ok else '  실패: ' + ','.join(fails)}")
    winners = [a for a, v in verdicts.items() if v["pass_all"]]
    best = max(winners, key=lambda a: ho[a]["calmar"]) if winners else None
    print(f"\n판정: {'후보 ' + best if best else '통과 arm 없음 — 현행 유지'}"
          f"   (DEPLOY_ON_PASS={DEPLOY_ON_PASS} — 반영은 사용자 결정)")

    print("\n[7] 진단 — current 에서 무엇이 무엇에게 밀렸나 (holdout, 슬롯 만석 스킵)")
    for pat, occ in sorted(cur_ho["blocked_by"].items(), key=lambda kv: -sum(kv[1].values()))[:8]:
        tot = sum(occ.values())
        top = ", ".join(f"{k} {v/tot:.0%}" for k, v in
                        sorted(occ.items(), key=lambda kv: -kv[1])[:3])
        print(f"  {pat:20} 밀린 순간의 점유: {top}")

    json.dump(dict(prereg="portfolio_prereg_2026_09_10", split=SPLIT, arms=ARMS,
                   deploy_on_pass=DEPLOY_ON_PASS,
                   n_trades=dict(total=len(base), d1=len(t1d), h4=len(t4h)),
                   train={a: {k: v for k, v in tr[a].items() if k != "blocked_by"} for a in ARMS},
                   holdout={a: {k: v for k, v in ho[a].items() if k != "blocked_by"} for a in ARMS},
                   boot_win={a: wins[a] / BOOT_N for a in ARMS},
                   verdicts=verdicts, best=best,
                   blocked_by=cur_ho["blocked_by"]),
              open("_portfolio.json", "w"), indent=1, ensure_ascii=False)
    print("\n저장: _portfolio.json")


if __name__ == "__main__":
    main()
