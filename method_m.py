"""
method_m.py — 레짐 스케일 연구 (2026-09-03, 사용자 지시 "기각된 규칙들이 레짐 문제일 수도").

질문: 현행 레짐은 일봉 한 스케일이다. 주단위(slow) / 시간단위(fast) 레짐을 (a) 진입 필터로
얹거나 (b) 청산 규칙의 레짐 소스로 바꾸면 나아지는가. 특히 방식R(방향 인지 청산, 3라운드
REJECT)의 기각이 레짐 스케일 문제였는가.

틀: method_r 과 동일 — 같은 신호에 arm 별 청산을 짝지음 비교, 자산곡선 CAGR, 분기 거래
승률, 전후반, 마지막 365일 홀드아웃. 판정 기준 ①~⑦ 그대로(method_r.verdict 재사용).

arm (base = D, 현행 일봉 레짐 방식D):
  D_slow / D_fast   : 방식D 규칙, 레짐 소스만 slow / fast 로
  RL / RL_slow / RL_fast : 롱 한정 방향 인지 청산(method_r RL), 레짐 소스 daily / slow / fast
  F_slow / F_fast   : 진입 필터 — 롱은 해당 스케일이 bear 면 진입 안 함, 숏은 bull_* 면 안 함.
                      막힌 거래는 ret 0(무거래)로 짝지음. 분기 거래 = 막힌 거래, 막힌 거래가
                      손실이었으면 arm 승.
공통 지지: 세 스케일 라벨이 모두 있는 신호만(fast 는 4h 1100일 → 약 3년). 그래서 n 은
method_r(1,091)보다 작다 — 결과에 명시.
실거래 코드 무변경. 출력 method_m.json.
"""
import importlib
import json
import random
import statistics as st
from datetime import date, timedelta

import detlib
import fetch_data
import method_t as mt
import method_r as mr
import regime_switch as rs
import regime_multi as rm

STOP, MAX_HOLD, FEE = mt.STOP_LOSS_PCT, mt.MAX_HOLD, mt.FEE
ARMS = ["D", "D_slow", "D_fast", "RL", "RL_slow", "RL_fast", "F_slow", "F_fast"]
ARM_RULE = {"D": "D", "D_slow": "D", "D_fast": "D", "RL": "RL", "RL_slow": "RL", "RL_fast": "RL",
            "F_slow": "F", "F_fast": "F"}
ARM_SCALE = {"D": "daily", "D_slow": "slow", "D_fast": "fast", "RL": "daily", "RL_slow": "slow",
             "RL_fast": "fast", "F_slow": "slow", "F_fast": "fast"}
HOLDOUT_DAYS = 365
# 데이터 창 — 사용자 지적(2026-09-03): 최근 5년만 쓰면 특정 국면(2021 상승/2026 하락)에
# 결과가 묶인다. 거래소가 주는 만큼 최대로 받는다(1d 3000일 ≈ 2018~, 4h 2200일 ≈ 2020~).
# 실제 받은 범위·연도별 레짐 구성은 로그에 찍어 표본이 어느 국면을 포함하는지 드러낸다.
DAILY_FETCH_DAYS = 3000
FAST_FETCH_DAYS = 2200
BULL = {"bull_btc", "bull_altseason"}

MAPS = {}          # scale -> RegimeMap ("daily" 는 date dict 로 별도)
REGMAP = {}        # 현행 일봉 레짐 (date -> label), method_r 와 동일 소스


def label_fn(scale, rows, tf):
    """봉 j 의 레짐 라벨 함수. daily 는 현행과 같은 date 조회(method_r D 와 완전 동일)."""
    if scale == "daily":
        return lambda j: REGMAP.get(rows[j]["date"])
    m = MAPS[scale]
    step = rm.TF_MS[tf]
    return lambda j: m.at(rows[j]["ts"] + step)


def outcome(rows, si, direction, opp_set, rule, lab):
    """
    rule "D": 손절/반대신호/레짐 라벨 변화/만기.  rule "RL": 롱은 bear 진입 전환만, 숏은 D.
    method_r.outcome_r 의 D·RL 과 동일 의미(테스트로 고정). 반환 (ret, hold, reason).
    """
    base = rows[si]["c"]
    entry_reg = lab(si)
    end = min(si + MAX_HOLD, len(rows) - 1)
    is_long = direction == "long"
    stop_px = base * (1 - STOP) if is_long else base * (1 + STOP)
    adv = {"bear"} if (rule == "RL" and is_long) else None
    prev_adv = (entry_reg in adv) if adv else None
    for j in range(si + 1, end + 1):
        hit = rows[j]["l"] <= stop_px if is_long else rows[j]["h"] >= stop_px
        if hit:
            return -STOP - FEE, j - si, "stop"
        cur = lab(j)
        if adv is None:
            regsw = cur not in (None, entry_reg)
        elif cur is None:
            regsw = False
        else:
            cur_adv = cur in adv
            regsw = cur_adv and not prev_adv
            prev_adv = cur_adv
        if j in opp_set or regsw:
            c = rows[j]["c"]
            r = (c - base) / base if is_long else (base - c) / base
            return r - FEE, j - si, ("opp_signal" if j in opp_set else "regime_switch")
    px = rows[end]["o"]
    r = (px - base) / base if is_long else (base - px) / base
    return r - FEE, end - si, "maxhold"


def blocked(direction, lab_entry):
    return (lab_entry == "bear") if direction == "long" else (lab_entry in BULL)


def _arm_stats(base, arm, idx, m, with_halves):
    b = [base[i] for i in idx]
    a = [arm[i] for i in idx]
    if not b:
        return None
    traded = [t for t in a if t[4] != "filtered"]
    rec = dict(per_trade=mt.summ(a), per_trade_traded=mt.summ(traded),
               equity=mt.equity_curve(sorted(traded, key=lambda t: t[0])) if traded else None,
               reasons=mr._count(t[4] for t in a))
    if m != "D":
        br = [t[2] for t in b]; ar = [t[2] for t in a]
        p = mt.paired_stats(br, ar)
        p["boot_p"] = mr.boot_p([x - y for x, y in zip(ar, br)])
        rec["paired_vs_D"] = p
        rec["divergence"] = mr.divergence(b, a)
        if with_halves:
            rec["halves"] = mr.halves(b, a)
    return rec


def run_pattern(label, direction, detmod, oppmod, tf, cutoff):
    mod = importlib.import_module(detmod)
    opp = importlib.import_module(oppmod) if oppmod else None
    arms = {m: [] for m in ARMS}
    n_skipped = 0
    entry_labels = {"slow": [], "daily": [], "fast": []}
    entry_daily = []                          # 거래별 진입 일봉 레짐(층화 진단용)
    for sym in detlib.SYMBOLS:
        try:
            rows = detlib.load_ohlcv(sym, tf)
        except (FileNotFoundError, RuntimeError):
            continue
        if len(rows) < 40:
            continue
        opp_set = set(opp.detect(rows)) if opp else set()
        labs = {s: label_fn(s, rows, tf) for s in ("daily", "slow", "fast")}
        for si in mod.detect(rows):
            if si + 1 >= len(rows):
                continue
            ent = {s: labs[s](si) for s in labs}
            if any(v is None for v in ent.values()):
                n_skipped += 1
                continue                      # 공통 지지 밖
            for s in ent:
                entry_labels[s].append(ent[s])
            entry_daily.append(ent["daily"])
            for m in ARMS:
                rule, scale = ARM_RULE[m], ARM_SCALE[m]
                if rule == "F":
                    if blocked(direction, ent[scale]):
                        arms[m].append((rows[si]["date"], rows[si]["date"], 0.0, 0, "filtered"))
                        continue
                    ret, hold, reason = outcome(rows, si, direction, opp_set, "D", labs["daily"])
                else:
                    ret, hold, reason = outcome(rows, si, direction, opp_set, rule, labs[scale])
                xi = min(si + hold, len(rows) - 1)
                arms[m].append((rows[si]["date"], rows[xi]["date"], ret, hold, reason))
    if not arms["D"]:
        return None
    base = arms["D"]
    tr, ho = mr.split_idx(base, cutoff)
    out = {}
    for m in ARMS:
        out[m] = dict(train=_arm_stats(base, arms[m], tr, m, True),
                      holdout=_arm_stats(base, arms[m], ho, m, False))
    out["_entry_labels"] = {s: mr._count(v) for s, v in entry_labels.items()}
    # ⑧ 층화 진단(판정 기준 아님): 진입 일봉 레짐별·연도별 짝지음 차이. 한 국면에서만
    # 양수면 '단일 레짐 의존'으로 표시한다 — 데이터 창의 국면 구성에 결과가 묶이는지 본다.
    out["_strata"] = {}
    for m in ARMS:
        if m == "D":
            continue
        d = [arms[m][i][2] - base[i][2] for i in range(len(base))]
        by_reg, by_year = {}, {}
        for i, x in enumerate(d):
            by_reg.setdefault(entry_daily[i], []).append(x)
            by_year.setdefault(base[i][0][:4], []).append(x)
        out["_strata"][m] = dict(
            by_regime={k: dict(n=len(v), diff=st.mean(v)) for k, v in by_reg.items()},
            by_year={k: dict(n=len(v), diff=st.mean(v)) for k, v in sorted(by_year.items())})
    out["_n_train"], out["_n_holdout"], out["_n_skipped_no_support"] = len(tr), len(ho), n_skipped
    return out


def ensure_fast_data():
    ok = 0
    for s in [rs.MARKET] + rs.ALTS:
        try:
            _, total = fetch_data.update_csv(f"{s}/USDT", "4h", detlib.CSV(s, "4h"),
                                             window_days=FAST_FETCH_DAYS)
            ok += total > 0
        except Exception as e:
            print(f"  [fetch] {s} 4h 실패: {str(e)[:60]}")
    print(f"[fetch] 4h {FAST_FETCH_DAYS}일: {ok}/{1 + len(rs.ALTS)}종목")


def _print(res, split):
    print(f"  [{split}]")
    print(f"  {'arm':<8}{'n':>5}{'거래n':>6}{'건당':>8}{'중앙':>8}{'승률':>6}{'보유':>6}"
          f" |{'짝지음':>8}{'t':>6}{'boot_p':>7}{'승/패':>8} |{'분기n':>6}{'분기승':>7}"
          f" |{'CAGR':>7}{'MDD':>7} |{'전반':>7}{'후반':>7}")
    for m in ARMS:
        r = res[m][split]
        if not r:
            continue
        pt, eq = r["per_trade"], r["equity"] or {}
        tn = (r["per_trade_traded"] or {}).get("n", 0)
        line = (f"  {m:<8}{pt['n']:>5}{tn:>6}{pt['mean']*100:>+7.2f}%{pt['median']*100:>+7.2f}%"
                f"{pt['winrate']*100:>5.0f}%{pt['avghold']:>6.1f}")
        if m == "D":
            line += f" |{'':>8}{'':>6}{'':>7}{'':>8} |{'':>6}{'':>7}"
        else:
            p, d = r["paired_vs_D"], r["divergence"]
            dw = f"{d['arm_wins']}/{d['arm_losses']}" if d["n"] else "-"
            wr = (d["arm_wins"] / (d["arm_wins"] + d["arm_losses"]) * 100
                  if d["arm_wins"] + d["arm_losses"] else 0)
            line += (f" |{p['mean_diff']*100:>+7.2f}%{p['t']:>6.2f}{p['boot_p']:>7.3f}{dw:>8}"
                     f" |{d['n']:>6}{wr:>6.0f}%")
        line += f" |{(eq.get('cagr') or 0)*100:>+6.1f}%{(eq.get('mdd') or 0)*100:>+6.1f}%"
        h = r.get("halves")
        line += f" |{h['d1']*100:>+6.2f}%{h['d2']*100:>+6.2f}%" if h else ""
        print(line)


def main():
    global REGMAP, MAPS
    mt.ensure_data(DAILY_FETCH_DAYS)
    ensure_fast_data()
    REGMAP = rs.build_regime_map()
    mr.REGMAP = REGMAP
    MAPS = {s: rm.build_scale_map(s) for s in ("slow", "fast")}
    last = max(REGMAP)
    cutoff = (date.fromisoformat(last) - timedelta(days=HOLDOUT_DAYS)).isoformat()
    from datetime import datetime, timezone
    for s, m in MAPS.items():
        f = datetime.fromtimestamp(m.first_ts() / 1000, tz=timezone.utc).strftime("%Y-%m-%d") if len(m) else None
        cnt = mr._count(m.lab)
        print(f"[regime:{s}] {len(m)}봉 라벨, 시작 {f}, 분포 {cnt}")
    ymix = {}
    for d, g in REGMAP.items():
        ymix.setdefault(d[:4], {}).setdefault(g, 0)
        ymix[d[:4]][g] += 1
    print(f"[regime:daily] {len(REGMAP)}일 | 홀드아웃 cutoff {cutoff}")
    print("[regime:daily] 연도별 구성: " + "  ".join(f"{y}:{v}" for y, v in sorted(ymix.items())))
    print("=" * 130)
    print("레짐 스케일 연구 — D(현행) vs D_slow/D_fast vs RL/RL_slow/RL_fast vs 진입필터 F_slow/F_fast")
    print("=" * 130)
    results = {}
    for label, direction, detmod, oppmod, tf in mt.PATS:
        try:
            res = run_pattern(label, direction, detmod, oppmod, tf, cutoff)
        except Exception as e:
            import traceback; traceback.print_exc()
            print(f"\n[{label}] 실행 오류: {str(e)[:80]}")
            continue
        if not res:
            print(f"\n[{label}] 신호 없음 — 스킵"); continue
        results[label] = res
        print(f"\n[{label} @{tf} {direction}] train {res['_n_train']} / holdout {res['_n_holdout']} "
              f"/ 공통지지 밖 {res['_n_skipped_no_support']}  진입라벨 {res['_entry_labels']}")
        _print(res, "train"); _print(res, "holdout")
    if not results:
        print("결과 없음"); return
    results["_pooled"] = {"train": {}, "holdout": {}}
    print("\n" + "=" * 130)
    print("합산(표본 가중) + 판정 ①합산유의 ②CAGR우위>=4/7 ③t<-2 패턴없음 ④분기승률>50% ⑤전후반양수 ⑥⑦홀드아웃")
    verdicts = {}
    for m in ARMS:
        if m == "D":
            continue
        for split in ("train", "holdout"):
            results["_pooled"][split][m] = mr._pool(results, split, m)
        v = mr.verdict(results, m)
        verdicts[m] = v
        tr = results["_pooled"]["train"][m] or {}
        ho = results["_pooled"]["holdout"][m] or {}
        dv = tr.get("divergence", {})
        wr = dv.get("arm_wins", 0) / max(1, dv.get("arm_wins", 0) + dv.get("arm_losses", 0)) * 100
        print(f"  {m:<8} train n={tr.get('n')} diff={tr.get('mean_diff', 0)*100:+.3f}%p t={tr.get('t', 0):.2f} "
              f"boot_p={tr.get('boot_p', 1):.3f} CAGR우위 {v['c2_cagr_wins']}/7 분기 {dv.get('n', 0)}건 승률 {wr:.0f}% "
              f"| holdout diff={ho.get('mean_diff', 0)*100:+.3f}%p → {'PASS' if v['pass_'] else 'REJECT'} "
              f"(train {'통과' if v['train_pass'] else '탈락'})")
    results["_verdicts"] = verdicts
    # ⑧ 층화 진단 합산: 진입 레짐별 / 연도별 (표본 가중)
    print("\n" + "=" * 130)
    print("⑧ 층화 진단 — 합산 짝지음 차이(%p) 진입 일봉 레짐별 · 연도별. 한 국면에서만 양수면 단일 레짐 의존")
    strata_pooled = {}
    for m in ARMS:
        if m == "D":
            continue
        agg_r, agg_y = {}, {}
        for lb, res in results.items():
            if lb.startswith("_"):
                continue
            for k, v in res["_strata"][m]["by_regime"].items():
                a = agg_r.setdefault(k, [0, 0.0]); a[0] += v["n"]; a[1] += v["diff"] * v["n"]
            for k, v in res["_strata"][m]["by_year"].items():
                a = agg_y.setdefault(k, [0, 0.0]); a[0] += v["n"]; a[1] += v["diff"] * v["n"]
        reg = {k: dict(n=n, diff=(sd / n if n else 0.0)) for k, (n, sd) in agg_r.items()}
        yr = {k: dict(n=n, diff=(sd / n if n else 0.0)) for k, (n, sd) in sorted(agg_y.items())}
        pos_regs = [k for k, v in reg.items() if v["n"] >= 20 and v["diff"] > 0]
        big_regs = [k for k, v in reg.items() if v["n"] >= 20]
        single = len(big_regs) >= 2 and len(pos_regs) == 1
        strata_pooled[m] = dict(by_regime=reg, by_year=yr, single_regime_dependent=single)
        rs_txt = "  ".join(f"{k}:{v['diff']*100:+.2f}%p(n{v['n']})" for k, v in reg.items())
        yr_txt = "  ".join(f"{k}:{v['diff']*100:+.2f}%p(n{v['n']})" for k, v in yr.items())
        print(f"  {m:<8} 레짐별 {rs_txt}{'  ← 단일 레짐 의존' if single else ''}")
        print(f"  {'':<8} 연도별 {yr_txt}")
    results["_strata_pooled"] = strata_pooled
    results["_config"] = dict(arms=ARMS, scales=rm.SCALES, holdout_days=HOLDOUT_DAYS, cutoff=cutoff,
                              daily_fetch_days=DAILY_FETCH_DAYS, fast_fetch_days=FAST_FETCH_DAYS,
                              daily_year_mix=ymix, thr_rule="0.1% x lookback_days/20")
    json.dump(results, open("method_m.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1,
              default=mr._jsonable)
    print("\nRESULT_JSON: " + json.dumps({m: dict(pass_=v["pass_"], train_pass=v["train_pass"],
                                                  c2=v["c2_cagr_wins"]) for m, v in verdicts.items()}))


if __name__ == "__main__":
    main()
