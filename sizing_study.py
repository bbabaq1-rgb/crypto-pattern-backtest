"""
sizing_study.py — 사이징·레버리지 규칙을 실제 신호 분포로 계산해 정한다.

질문: "포지션 금액과 레버리지가 너무 작다. 계산 가능한 최적 로직은?"

방법
----
1) method_t 와 같은 파이프라인으로 배포 패턴 7종의 방식D 거래(진입일/청산일/수익)를
   1d 5년 전 종목에서 모은다. 이것이 실거래 엔진이 실제로 마주치는 신호 흐름이다.
2) **전 패턴을 하나의 포트폴리오로 시간순 시뮬레이션**한다 — 실거래는 패턴별이 아니라
   한 계좌에서 동시에 돌기 때문. 규칙 격자:
     legacy        : free x 20%, 2x (현행)
     risk-based    : risk_frac ∈ {0.5,1,1.5,2,3,4}% × lev ∈ {2,3,5}
   각 규칙으로 CAGR / MDD / Calmar / 최종자산을 낸다.
3) **블록 부트스트랩**(거래열 재표집, 블록 20)으로 각 규칙의 MDD 분포와
   파산확률 P(equity < 50%) 을 추정한다. 한 경로의 CAGR 은 운이 섞여 있어 단독으론 못 믿는다.
4) 선택 기준(사전 고정): 부트스트랩 중앙 MDD >= -35% AND P(ruin) < 5% 인 규칙 중
   중앙 Calmar 최대. — "최적"은 CAGR 최대가 아니라 **파산하지 않는 조건에서 Calmar 최대**다.

레버리지에 대한 사실
--------------------
risk-based 에서는 레버리지가 명목가를 바꾸지 않는다(명목가 = risk/stop). 레버리지는
증거금만 줄여 **동시에 더 많은 포지션을 담을 수 있게** 한다. 그래서 격자에서 lev 를
올렸을 때 성과가 좋아진다면 그 이유는 '슬롯 부족으로 놓치던 신호를 잡았기 때문'이고,
나빠진다면 '노출 합이 커져 MDD 가 깊어졌기 때문'이다. 이 스크립트가 그걸 분리해 보여준다.

단일자산 Kelly 를 참고로 같이 찍지만 **채택 기준으로 쓰지 않는다** — 알트는 서로 강하게
상관돼 12개를 동시에 들면 포트폴리오 Kelly 는 단일자산 Kelly 보다 훨씬 작다.

실행: python sizing_study.py  (Actions 러너; 로컬은 데이터 수집 불가)
"""
import json
import random
import statistics
import sys
from datetime import date

import detlib
import method_t as mt
import regime_switch as rs
import sizing as sz

STOP = mt.STOP_LOSS_PCT            # 0.08 — 방식D 손절
START_EQ = 1000.0
MAX_POS = 12
RISK_GRID = [0.005, 0.01, 0.015, 0.02, 0.03, 0.04]
LEV_GRID = [2, 3, 5]
BOOT_N = 300
BLOCK = 20
SEED = 7
RUIN_LEVEL = 0.5                   # 시작자본의 50% 미만 = 파산으로 간주
MDD_FLOOR = -0.35                  # 선택 기준
RUIN_MAX = 0.05


def collect_all():
    """전 패턴 방식D 거래 → [(entry_date, exit_date, ret, hold, pattern)] 시간순."""
    out = []
    for label, direction, detmod, oppmod, tf in mt.PATS:
        import importlib
        mod = importlib.import_module(detmod)
        opp = importlib.import_module(oppmod) if oppmod else None
        n = 0
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
                ret, hold, reason = mt.outcome_d(rows, si, direction, opp_set)
                xi = min(si + hold, len(rows) - 1)
                out.append((rows[si]["date"], rows[xi]["date"], ret, hold, label))
                n += 1
        print(f"  [{label}] {n}건")
    out.sort(key=lambda t: (t[0], t[4]))
    return out


def _dnum(ds):
    y, m, d = map(int, ds.split("-"))
    return date(y, m, d).toordinal()


def simulate(trades, rule, risk_frac=None, lev=None):
    """
    규칙별 시간순 포트폴리오 시뮬레이션.
      rule='legacy' : margin = free x 20%, lev 2 (현행)
      rule='risk'   : sizing.risk_based_size(equity, free, STOP, risk_frac, lev_cap=lev)
    수익 = notional x ret. 증거금은 진입 시 잠기고 청산 시 풀린다.
    반환 dict(final, cagr, mdd, calmar, taken, skipped, skip_reason)
    """
    evs = []
    for i, (ed, xd, ret, hold, pat) in enumerate(trades):
        evs.append((_dnum(ed), 0, i))
        evs.append((_dnum(xd), -1, i))
    evs.sort()
    equity = free = START_EQ
    open_pos = {}                       # idx -> (margin, notional)
    peak, mdd = equity, 0.0
    taken = skipped = 0
    skip_reason = {"slots": 0, "size": 0}
    for day, kind, idx in evs:
        if kind == -1:
            rec = open_pos.pop(idx, None)
            if rec is None:
                continue
            margin, notional = rec
            pnl = notional * trades[idx][2]
            equity += pnl
            free += margin + pnl
            if equity <= 0:             # 계좌 소진
                equity = 0.0
                break
            peak = max(peak, equity)
            mdd = min(mdd, equity / peak - 1)
        else:
            if len(open_pos) >= MAX_POS:
                skipped += 1; skip_reason["slots"] += 1; continue
            open_notional = sum(n for _, n in open_pos.values())
            if rule == "legacy":
                r = sz.legacy_size(free, 1)
            else:
                r = sz.risk_based_size(equity, free, STOP, risk_frac=risk_frac, lev_cap=lev,
                                       open_notional=open_notional)
            if r is None:
                skipped += 1; skip_reason["size"] += 1; continue
            free -= r["margin_usd"]
            open_pos[idx] = (r["margin_usd"], r["notional"])
            taken += 1
    days = max(1, evs[-1][0] - evs[0][0])
    yrs = days / 365.25
    cagr = (equity / START_EQ) ** (1 / yrs) - 1 if equity > 0 else -1.0
    return dict(final=equity, cagr=cagr, mdd=mdd,
                calmar=(cagr / abs(mdd) if mdd < 0 else float("inf")),
                taken=taken, skipped=skipped, skip_reason=skip_reason)


def block_bootstrap(trades, rng, block=BLOCK):
    """거래열을 블록 단위로 재표집. 날짜는 원 순서를 유지해 중첩 구조를 보존한다."""
    n = len(trades)
    idx = []
    while len(idx) < n:
        s = rng.randrange(0, n)
        idx.extend(range(s, min(n, s + block)))
    idx = idx[:n]
    # 원본의 날짜 골격에 재표집된 수익/보유를 얹는다
    out = []
    for k, j in enumerate(idx):
        ed, xd, _, _, _ = trades[k]
        _, _, ret, hold, pat = trades[j]
        out.append((ed, xd, ret, hold, pat))
    return out


def evaluate_rule(trades, rule, risk_frac=None, lev=None):
    base = simulate(trades, rule, risk_frac, lev)
    rng = random.Random(SEED)
    mdds, calmars, ruins = [], [], 0
    for _ in range(BOOT_N):
        bt = block_bootstrap(trades, rng)
        s = simulate(bt, rule, risk_frac, lev)
        mdds.append(s["mdd"]); calmars.append(min(s["calmar"], 50.0))
        if s["final"] < START_EQ * RUIN_LEVEL:
            ruins += 1
    mdds.sort(); calmars.sort()
    return dict(base=base,
                boot=dict(mdd_med=mdds[len(mdds)//2], mdd_p10=mdds[int(len(mdds)*0.1)],
                          calmar_med=calmars[len(calmars)//2], p_ruin=ruins / BOOT_N))


def kelly_single(rets):
    m = statistics.mean(rets); v = statistics.pvariance(rets)
    return (m / v) if v > 0 else float("nan")


def main():
    mt.ensure_data()
    mt.REGMAP = rs.build_regime_map()
    print("[collect] 방식D 거래 수집 (7패턴, 1d 5년):")
    trades = collect_all()
    print(f"  합계 {len(trades)}건 | {trades[0][0]} ~ {trades[-1][1]}")
    if len(trades) < 50:
        print("표본 부족 — 중단"); return

    # 참고: 단일자산 Kelly (채택 기준 아님)
    print("\n[참고] 단일자산 Kelly f* (명목가/equity) — 상관 무시라 과대추정, 채택 기준 아님")
    bypat = {}
    for t in trades:
        bypat.setdefault(t[4], []).append(t[2])
    for pat, rs_ in sorted(bypat.items()):
        if len(rs_) >= 20:
            print(f"  {pat:<18} n={len(rs_):>4} mean={statistics.mean(rs_)*100:+.2f}% "
                  f"sd={statistics.pstdev(rs_)*100:.1f}% Kelly={kelly_single(rs_):.2f} 반Kelly={kelly_single(rs_)/2:.2f}")

    results = {}
    print("\n" + "=" * 110)
    print(f"규칙별 자산곡선 (시작 ${START_EQ:.0f}, 최대 {MAX_POS}포지션, 손절 {STOP:.0%}) "
          f"+ 블록부트스트랩 {BOOT_N}회")
    print("=" * 110)
    hdr = (f"  {'규칙':<22}{'CAGR':>8}{'MDD':>8}{'Calmar':>8}{'체결':>6}{'슬롯스킵':>8}{'크기스킵':>8}"
           f"  |{'boot MDD중앙':>12}{'MDD p10':>9}{'Calmar중앙':>11}{'P(ruin)':>9}")
    print(hdr); print("  " + "-" * 106)

    def row(name, r):
        b, bo = r["base"], r["boot"]
        print(f"  {name:<22}{b['cagr']*100:>+7.1f}%{b['mdd']*100:>+7.1f}%{min(b['calmar'],99):>8.2f}"
              f"{b['taken']:>6}{b['skip_reason']['slots']:>8}{b['skip_reason']['size']:>8}"
              f"  |{bo['mdd_med']*100:>+11.1f}%{bo['mdd_p10']*100:>+8.1f}%{bo['calmar_med']:>11.2f}"
              f"{bo['p_ruin']:>9.1%}")

    r = evaluate_rule(trades, "legacy"); results["legacy"] = r; row("legacy free20%/2x", r)
    print("  " + "-" * 106)
    for lev in LEV_GRID:
        for rf in RISK_GRID:
            key = f"risk{rf*100:g}%_lev{lev}"
            r = evaluate_rule(trades, "risk", rf, lev); results[key] = r
            row(key, r)
        print("  " + "-" * 106)

    # 선택: 사전 고정 기준
    ok = {k: v for k, v in results.items()
          if k != "legacy" and v["boot"]["mdd_med"] >= MDD_FLOOR and v["boot"]["p_ruin"] < RUIN_MAX}
    print(f"\n선택 기준: boot MDD중앙 >= {MDD_FLOOR:.0%} AND P(ruin) < {RUIN_MAX:.0%} → 후보 {len(ok)}개")
    if ok:
        best = max(ok.items(), key=lambda kv: kv[1]["boot"]["calmar_med"])
        k, v = best
        print(f"=> 권고: {k}  (boot Calmar중앙 {v['boot']['calmar_med']:.2f}, MDD중앙 {v['boot']['mdd_med']*100:+.1f}%, "
              f"P(ruin) {v['boot']['p_ruin']:.1%}; 단일경로 CAGR {v['base']['cagr']*100:+.1f}%)")
        lg = results["legacy"]
        print(f"   vs legacy: Calmar중앙 {lg['boot']['calmar_med']:.2f}, MDD중앙 {lg['boot']['mdd_med']*100:+.1f}%, "
              f"P(ruin) {lg['boot']['p_ruin']:.1%}, CAGR {lg['base']['cagr']*100:+.1f}%")
        rec = dict(rule=k, risk_frac=float(k.split("%")[0][4:]) / 100, lev_cap=int(k.split("lev")[1]))
    else:
        print("=> 기준을 만족하는 risk-based 규칙 없음 — legacy 유지 권고")
        rec = dict(rule="legacy")

    # 레버리지의 역할 분해: 같은 risk_frac 에서 lev 만 바꿨을 때 슬롯스킵/MDD 변화
    print("\n[레버리지 분해] 같은 위험(2%)에서 lev 만 변경:")
    for lev in LEV_GRID:
        v = results.get(f"risk2%_lev{lev}")
        if v:
            print(f"  lev {lev}: 슬롯스킵 {v['base']['skip_reason']['slots']:>4} 크기스킵 {v['base']['skip_reason']['size']:>4} "
                  f"CAGR {v['base']['cagr']*100:+.1f}% MDD {v['base']['mdd']*100:+.1f}% P(ruin) {v['boot']['p_ruin']:.1%}")

    json.dump(dict(n_trades=len(trades), start=trades[0][0], end=trades[-1][1],
                   stop=STOP, max_pos=MAX_POS, boot_n=BOOT_N, criteria=dict(mdd_floor=MDD_FLOOR, ruin_max=RUIN_MAX),
                   results=results, recommendation=rec),
              open("_sizing_study.json", "w"), indent=1, default=str)
    print("\nRESULT_JSON: " + json.dumps(dict(recommendation=rec,
          legacy=dict(cagr=results["legacy"]["base"]["cagr"], mdd_med=results["legacy"]["boot"]["mdd_med"],
                      p_ruin=results["legacy"]["boot"]["p_ruin"])), separators=(",", ":")))


if __name__ == "__main__":
    main()
