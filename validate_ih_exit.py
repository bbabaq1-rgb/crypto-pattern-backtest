"""
validate_ih_exit.py — inverted_hammer 한정 청산 규칙 재시험 (선택 편향 통제).

배경
----
청산 규칙 시험을 다섯 번 했고 pooled 기준으로는 전부 기각됐다. 그런데 두 번은
**`inverted_hammer` 에서만** 방식D를 이겼다:

  - 방식G(복합스코어 60/80점, 2026-07-06): pooled 0/3 인데 IH 에서 2/3 우위
    (+8.32% vs D +4.04%, Calmar 2배)
  - 방식T10(고정 +10% 익절, 2026-09-01): 짝지음 t=0.17(무의미)인데
    Calmar 0.10→0.46, CAGR 4.3%→11.2%, MDD -41.7%→-24.4%

서로 다른 두 규칙이 같은 패턴에서만 신호를 냈다. 우연치고는 반복적이다.

그런데 이건 **사후 선택된 패턴**이다. 7개 패턴 × 여러 규칙을 본 뒤 가장 좋은 하나를
고른 것이라, 그 셀의 통계는 선택 편향으로 오염돼 있다. 그냥 다시 돌려서 "역시 좋다"가
나와도 아무 증거가 안 된다 — 같은 데이터에서 같은 답이 나오는 건 당연하다.

그래서 이 스크립트는 **"IH 가 특별한가"를 반증하려 시도**한다.

세 가지 반증 시험
----------------
1. **시간 분할 OOS** — 전체 구간을 전반/후반으로 나눠 각각에서 우위가 재현되는가.
   전반에만 있고 후반에 사라지면 잡음이다. (선택이 전체 구간 성과로 이루어졌으므로
   양쪽 절반 모두에서 살아남는 것이 최소 요건)
2. **짝지음 부트스트랩** — 짝지음 차이 d_i 를 재표본해 신뢰구간을 구한다.
   t검정의 정규성 가정 없이, 0을 포함하는지 본다.
3. **대조군(placebo)** — 같은 규칙을 나머지 패턴 전부에 적용했을 때 IH 의 우위가
   분포의 어디에 있는가. 7개 중 1등인 것이 우연히 나올 확률을 감안한다.
   IH 가 다른 패턴 대비 극단값이 아니라면 '특별함'의 근거가 없다.

실행: python validate_ih_exit.py   (Actions 러너)
"""
import importlib
import json
import random
import statistics as st

import detlib
import fetch_data
import method_t as mt
import regime_switch as rs

FETCH_DAYS = mt.FETCH_DAYS
TARGET = "inverted_hammer"
BOOT_N = 2000
SEED = 42

# 비교 대상 청산 규칙
#   D   = 현행 (익절 없음)
#   T10 = 방식T k=0.10 (method_t 에서 IH Calmar 4배가 나온 arm)
#   G   = 방식G 복합스코어 (method_g — 2026-07-06 IH 2/3 우위)
ARMS = ["D", "T10", "G"]

# 대조군: IH 를 제외한 나머지 패턴 (placebo 비교용)
PATS = mt.PATS


def _fetch():
    ok = 0
    for s in detlib.SYMBOLS:
        try:
            _, total = fetch_data.update_csv(f"{s}/USDT", "1d",
                                             detlib.CSV(s, "1d"),
                                             window_days=FETCH_DAYS)
            ok += 1 if total else 0
        except Exception as e:
            print(f"  [fetch] {s}: {str(e)[:50]}")
    print(f"[fetch] 1d {FETCH_DAYS}일: {ok}/{len(detlib.SYMBOLS)}종목")


def arm_outcome(arm, rows, si, direction, opp_set):
    """arm 별 (ret, hold). D/T10 은 method_t, G 는 method_g 로 위임."""
    if arm == "D":
        r, h, _ = mt.outcome_d(rows, si, direction, opp_set, None)
        return r, h
    if arm == "T10":
        r, h, _ = mt.outcome_d(rows, si, direction, opp_set, 0.10)
        return r, h
    if arm == "G":
        import method_g
        return method_g.outcome_g(rows, si, direction)
    raise ValueError(arm)


def collect(label, direction, detmod, oppmod, tf):
    """{arm: [(date, ret, hold)]} — 같은 신호 집합에 모든 arm 적용(짝지음)."""
    mod = importlib.import_module(detmod)
    opp = importlib.import_module(oppmod) if oppmod else None
    out = {a: [] for a in ARMS}
    for sym in detlib.SYMBOLS:
        try:
            rows = detlib.load_ohlcv(sym, tf)
        except (FileNotFoundError, RuntimeError):
            continue
        if len(rows) < 80:
            continue
        opp_set = set(opp.detect(rows)) if opp else set()
        for si in mod.detect(rows):
            if si + 1 >= len(rows):
                continue
            for a in ARMS:
                try:
                    r, h = arm_outcome(a, rows, si, direction, opp_set)
                except Exception:
                    r, h = None, None
                if r is None:
                    out[a].append(None)
                else:
                    # 청산일을 실제 봉에서 읽는다 — 자산곡선이 보유기간 중복을
                    # 반영하려면 (진입일, 청산일) 쌍이 정확해야 한다.
                    xi = min(si + h, len(rows) - 1)
                    out[a].append((rows[si]["date"], rows[xi]["date"], r, h))
    # 한 arm 이라도 실패한 신호는 짝지음이 깨지므로 통째로 제외
    keep = [i for i in range(len(out["D"]))
            if all(out[a][i] is not None for a in ARMS)]
    return {a: [out[a][i] for i in keep] for a in ARMS}


def paired(base, arm):
    d = [a[2] - b[2] for a, b in zip(arm, base)]
    n = len(d)
    if n < 2:
        return dict(n=n, mean_diff=0.0, t=0.0)
    m, sd = st.mean(d), st.stdev(d)
    return dict(n=n, mean_diff=m, t=(m / (sd / n ** 0.5) if sd else 0.0),
                wins=sum(1 for x in d if x > 1e-12),
                losses=sum(1 for x in d if x < -1e-12))


def boot_ci(base, arm, n=BOOT_N, seed=SEED):
    """짝지음 차이의 부트스트랩 95% 신뢰구간 (정규성 가정 없음)."""
    d = [a[2] - b[2] for a, b in zip(arm, base)]
    if len(d) < 5:
        return None
    rnd = random.Random(seed)
    means = sorted(st.mean([d[rnd.randrange(len(d))] for _ in d]) for _ in range(n))
    lo, hi = means[int(n * 0.025)], means[int(n * 0.975)]
    p_le0 = sum(1 for m in means if m <= 0) / n
    return dict(lo=lo, hi=hi, p_le0=p_le0, includes_zero=(lo <= 0 <= hi))


def split_half(base, arm):
    """시간 분할 OOS — 날짜 기준 전반/후반 각각의 짝지음 우위."""
    idx = sorted(range(len(base)), key=lambda i: base[i][0])
    mid = len(idx) // 2
    out = {}
    for tag, part in (("전반", idx[:mid]), ("후반", idx[mid:])):
        b = [base[i] for i in part]
        a = [arm[i] for i in part]
        p = paired(b, a)
        p["from"], p["to"] = b[0][0], b[-1][0]
        out[tag] = p
    return out


def main():
    _fetch()
    mt.REGMAP = rs.build_regime_map()
    print(f"[regime] 레짐맵 {len(mt.REGMAP)}일\n")

    per_pattern = {}
    for label, direction, detmod, oppmod, tf in PATS:
        try:
            per_pattern[label] = collect(label, direction, detmod, oppmod, tf)
        except Exception as e:
            print(f"[{label}] 수집 실패: {str(e)[:70]}")

    if TARGET not in per_pattern or not per_pattern[TARGET]["D"]:
        print(f"{TARGET} 신호 없음 — 중단")
        return

    print("=" * 96)
    print(f"{TARGET} 한정 청산 규칙 재시험 — 선택 편향 통제 3종")
    print("=" * 96)

    ih = per_pattern[TARGET]
    base = ih["D"]
    results = {}

    # ── 전체 구간 기본 통계 ────────────────────────────────────────────────
    print(f"\n[0] 전체 구간 (n={len(base)})")
    print(f"  {'arm':<5}{'건당평균':>10}{'중앙':>9}{'승률':>7}{'평균보유':>9}"
          f"{'짝지음차이':>11}{'t':>7}{'CAGR':>9}{'MDD':>8}{'Calmar':>8}")
    print("  " + "-" * 92)
    for a in ARMS:
        rets = [x[2] for x in ih[a]]
        eq = mt.equity_curve([(ed, xd, r, h, "x") for ed, xd, r, h in ih[a]])
        p = paired(base, ih[a]) if a != "D" else None
        pstr = f"{p['mean_diff']*100:>+10.2f}%{p['t']:>7.2f}" if p else f"{'(기준)':>18}"
        print(f"  {a:<5}{st.mean(rets)*100:>+9.2f}%{st.median(rets)*100:>+8.2f}%"
              f"{sum(1 for r in rets if r>0)/len(rets):>6.0%}"
              f"{st.mean([x[3] for x in ih[a]]):>9.1f}{pstr}"
              f"{eq['cagr']*100:>+8.1f}%{eq['mdd']*100:>+7.1f}%{eq['calmar']:>8.2f}")
        results[a] = dict(n=len(rets), mean=st.mean(rets), median=st.median(rets),
                          equity=eq, paired=p)

    # ── 1. 시간 분할 OOS ───────────────────────────────────────────────────
    print(f"\n[1] 시간 분할 — 전반/후반 각각에서 우위가 재현되는가")
    print("     (전반에만 있고 후반에 사라지면 잡음)")
    for a in ARMS[1:]:
        sp = split_half(base, ih[a])
        line = "  ".join(
            f"{tag} n={v['n']} {v['mean_diff']*100:+.2f}%(t={v['t']:+.2f})"
            for tag, v in sp.items())
        both = all(v["mean_diff"] > 0 for v in sp.values())
        print(f"  {a:<5}{line}   →  {'양쪽 우위 O' if both else '재현 실패 X'}")
        results[a]["split"] = sp
        results[a]["split_both_positive"] = both

    # ── 2. 짝지음 부트스트랩 신뢰구간 ──────────────────────────────────────
    print(f"\n[2] 짝지음 차이 부트스트랩 95% CI (정규성 가정 없음)")
    for a in ARMS[1:]:
        ci = boot_ci(base, ih[a])
        if not ci:
            continue
        print(f"  {a:<5}[{ci['lo']*100:+.2f}%, {ci['hi']*100:+.2f}%]  "
              f"P(차이<=0)={ci['p_le0']:.3f}  "
              f"→  {'0 포함 — 유의하지 않음' if ci['includes_zero'] else '0 미포함 — 유의'}")
        results[a]["boot_ci"] = ci

    # ── 3. 대조군(placebo) — IH 가 정말 특별한가 ───────────────────────────
    print(f"\n[3] 대조군 — 같은 규칙을 전 패턴에 적용했을 때 IH 의 위치")
    print("     (IH 가 극단값이 아니면 '특별함'의 근거 없음)")
    for a in ARMS[1:]:
        rows = []
        for lb, d in per_pattern.items():
            if not d["D"] or a not in d or not d[a]:
                continue
            p = paired(d["D"], d[a])
            rows.append((lb, p["mean_diff"], p["t"]))
        rows.sort(key=lambda x: -x[1])
        rank = next((i + 1 for i, (lb, _, _) in enumerate(rows) if lb == TARGET), None)
        print(f"  {a:<5}짝지음차이 순위 {rank}/{len(rows)}  |  " +
              "  ".join(f"{lb}:{md*100:+.1f}%" for lb, md, _ in rows))
        results[a]["placebo_rank"] = rank
        results[a]["placebo"] = [(lb, round(md, 5), round(t, 3)) for lb, md, t in rows]

    # ── 종합 ────────────────────────────────────────────────────────────────
    print("\n" + "=" * 96)
    print("종합 판정")
    print("=" * 96)
    verdicts = {}
    for a in ARMS[1:]:
        r = results[a]
        c1 = r.get("split_both_positive", False)
        c2 = not r.get("boot_ci", {}).get("includes_zero", True)
        c3 = r.get("placebo_rank") == 1
        passed = sum([c1, c2, c3])
        v = "SURVIVES" if passed == 3 else ("PARTIAL" if passed == 2 else "NOISE")
        verdicts[a] = dict(split=c1, boot=c2, placebo_top=c3, n_passed=passed,
                           verdict=v)
        print(f"  {a:<5}시간분할 {'O' if c1 else 'X'} | "
              f"부트스트랩 {'O' if c2 else 'X'} | 대조군1위 {'O' if c3 else 'X'}"
              f"  →  {v}")
    print("\n  판정 기준: 3개 반증 시험을 모두 넘어야 SURVIVES(채택 검토 대상).")
    print("  2개면 PARTIAL(데이터 누적 후 재시험), 1개 이하는 NOISE(추격 중단).")

    json.dump(dict(target=TARGET, arms=ARMS, results=results, verdicts=verdicts),
              open("_ih_exit.json", "w"), indent=1,
              default=lambda x: round(x, 6) if isinstance(x, float) else str(x))
    print("\nRESULT_JSON: " + json.dumps(verdicts, separators=(",", ":")))


if __name__ == "__main__":
    main()
