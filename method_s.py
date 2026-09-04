"""
method_s.py — 레짐 청산 소거 시험 (2026-09-04, 사용자 질문 "레짐이 방향도 모르는데 그걸 근거로
청산하는 게 이상하지 않나").

배경. 라벨 품질 벤치마크(regime_quality)는 라벨의 **수준**을 예측기로 쟀고 20/40/60/90일 전부
적중률 50% 미만이었다. 그런데 방식D 의 청산은 수준이 아니라 **변화**를 본다
(`regmap[j] != entry_reg`). 둘은 다른 물음이므로 모순은 아니지만, **레짐 청산을 아예 뺀 판을
한 번도 재본 적이 없다** — method_d 는 방식A 묶음 vs 방식D 묶음, method_r 은 좁힘,
method_m/method_q 는 라벨 소스 교체였다. 그래서 현재 증거는 두 해석과 모두 양립한다.
  (1) 레짐 전환이 실제 시장 상태 정보를 담는다.
  (2) 레짐 청산은 사실상 보유기간 상한이고 라벨은 평균 보유일수만 정해 준다.
(2)가 맞으면 레짐 부분은 장식이고 단순 N봉 상한이 더 견고하다(BTC.D 수집 의존·라벨 결정성·
히스테리시스 경로 의존이 전부 사라진다). 이 모듈이 그 둘을 가른다.

arm (base = D, 현행 실거래 규칙과 동일: 손절 −8% / 반대신호 / 레짐 전환 / 30봉 만기)
  D_norg    : 레짐 청산 **제거**. 손절·반대신호·30봉 만기만. (소거 시험 본체)
  D_time    : 레짐 청산을 **고정 보유 상한**으로 대체. 상한 = D 의 실측 평균 보유(패턴별,
              반올림). '레짐은 시계일 뿐인가'를 직접 묻는다.
  D_shuffle : **결정적 arm.** 레짐 라벨 시계열을 런(run) 단위로 블록 셔플해 전환 빈도와
              지속 길이 분포는 보존하고 시장과의 정렬만 파괴한다. D 가 D_shuffle 을 못 이기면
              레짐은 시계이고, 이기면 상태 정보가 실재한다. 한 draw 는 운일 수 있으므로
              SHUFFLES 회 반복해 합산 짝지음 차이의 분포를 낸다(표의 D_shuffle 은 seed 0 대표).

사전 등록 판정 (실행 전 고정, 홀드아웃은 마지막 365일)
  A. **상태 정보 실재**  : D_shuffle 분포가 D 보다 나쁜 쪽으로 치우침(우위 draw >= 90%) AND
                          D_norg 합산 차이 < 0.
  B. **레짐은 시계일 뿐**: D_shuffle 우위 draw <= 60% (D 와 구분 불가) OR D_time 이 D 와
                          동등 이상(합산 차이 >= 0 이고 t > -2).
  C. **레짐 청산이 해롭다**: D_norg 가 method_r.verdict 기준 ①~⑦ 전부 통과(= D 보다 유의 우위).
  D. **정보는 있으나 시계로 대체 가능**: A 와 B 가 동시에 성립. 레짐 정렬이 무작위보다는 낫지만
     단순 보유 상한이 같은 성과를 낸다 = 실무 결론은 '더 단순한 쪽'. 가장 있을 법한 결과다.
  넷 다 아니면 INCONCLUSIVE. 실거래 규칙 변경은 사용자 결정 사항 — 이 모듈은 무변경.

실행: python method_s.py [--no-fetch] [--shuffles N] [--universe]
  기본 표본은 메이저 7종목(method_r/m/q 와 정합). --universe 는 universe.json 의 80종목으로
  넓혀 '표본이 작아서 나온 결론인가'를 재확인한다. 출력 method_s.json / method_s_universe.json.
  주의: --universe 는 모든 패턴을 80종목 전체에 돌린다. 실거래 라우팅(PATTERN_UNIVERSE:
  engulfing→top30, inverted_hammer·marubozu→메이저)의 복제가 아니라 **표본 크기 강건성 확인**이다.
"""
import importlib
import json
import random
import statistics as st
import sys
from datetime import date, timedelta

import detlib
import fetch_data
import method_m as mm
import method_r as mr
import method_t as mt
import regime_switch as rs

STOP, MAX_HOLD, FEE = mt.STOP_LOSS_PCT, mt.MAX_HOLD, mt.FEE
HOLDOUT_DAYS = 365
FETCH_DAYS = mm.DAILY_FETCH_DAYS
SHUFFLES = 20
SHUFFLE_SEED0 = 1000
ARMS = ["D", "D_norg", "D_time", "D_shuffle"]
ARM_RULE = {"D": "regime", "D_norg": "none", "D_time": "cap", "D_shuffle": "regime"}

# 표본 범위. 기본은 메이저 7종목 — method_r/method_m/method_q 와 표본을 맞춰 결론을 직접
# 비교하기 위해서다. --universe 를 주면 universe.json trading_universe(80종목)로 넓혀
# '표본이 작아서 나온 결론인가'를 재확인한다. 두 판 모두 기록한다.
UNIVERSE_MODE = False


def symbols():
    if UNIVERSE_MODE:
        try:
            u = json.load(open("universe.json", encoding="utf-8")).get("trading_universe")
            if u:
                return list(u)
        except Exception as e:
            print(f"[universe] universe.json 읽기 실패({str(e)[:50]}) — 메이저 폴백")
    return list(detlib.SYMBOLS)


def ensure_data(days, syms):
    ok = new = 0
    for s in syms:
        try:
            n_new, total = fetch_data.update_csv(f"{s}/USDT", "1d", detlib.CSV(s, "1d"), window_days=days)
            if total:
                ok += 1; new += n_new
        except Exception as e:
            print(f"  [fetch] {s} 실패: {str(e)[:60]}")
    print(f"[fetch] 1d {days}일: {ok}/{len(syms)}종목 (+{new}봉)", flush=True)


# ── 청산 규칙 ───────────────────────────────────────────────────────────────
def outcome(rows, si, direction, opp_set, lab, use_regime=True, max_hold=MAX_HOLD):
    """
    (ret, hold, reason). use_regime=True + max_hold=30 이면 paper_executor.eval_D 와 같은 규칙
    (method_m.outcome(rule="D") 와도 동일 — 테스트로 고정).
    """
    base = rows[si]["c"]
    entry_reg = lab(si)
    end = min(si + max_hold, len(rows) - 1)
    is_long = direction == "long"
    stop_px = base * (1 - STOP) if is_long else base * (1 + STOP)
    for j in range(si + 1, end + 1):
        hit = rows[j]["l"] <= stop_px if is_long else rows[j]["h"] >= stop_px
        if hit:
            return -STOP - FEE, j - si, "stop"
        regsw = use_regime and lab(j) not in (None, entry_reg)
        if j in opp_set or regsw:
            c = rows[j]["c"]
            r = (c - base) / base if is_long else (base - c) / base
            return r - FEE, j - si, ("opp_signal" if j in opp_set else "regime_switch")
    px = rows[end]["o"]
    r = (px - base) / base if is_long else (base - px) / base
    return r - FEE, end - si, "maxhold"


# ── 블록 셔플 ───────────────────────────────────────────────────────────────
def runs_of(regmap):
    """레짐 맵 -> [(label, 길이)] 런 분해 (날짜 오름차순)."""
    dates = sorted(regmap)
    if not dates:
        return []
    out, cur, n = [], regmap[dates[0]], 1
    for d in dates[1:]:
        if regmap[d] == cur:
            n += 1
        else:
            out.append((cur, n)); cur, n = regmap[d], 1
    out.append((cur, n))
    return out


def _sequence_no_adjacent(runs, rng):
    """
    런을 '인접 런의 라벨이 서로 다르도록' 재배열. 남은 개수가 가장 많은 라벨을 먼저 놓는
    표준 구성법(동수는 무작위) — 가능하면 항상 성공하고, 불가능하면 None.
    이렇게 해야 전환 수(= 런 수 − 1)가 원본과 **정확히** 같아진다.
    """
    by = {}
    for lab, n in runs:
        by.setdefault(lab, []).append(n)
    for lab in by:
        rng.shuffle(by[lab])
    out, prev = [], None
    for _ in range(len(runs)):
        cands = [l for l in by if by[l] and l != prev]
        if not cands:
            return None
        mx = max(len(by[l]) for l in cands)
        lab = rng.choice([l for l in cands if len(by[l]) == mx])
        out.append((lab, by[lab].pop()))
        prev = lab
    return out


def shuffle_regmap(regmap, seed, preserve_flips=True):
    """
    런 순서만 섞어 같은 날짜 축에 다시 깐다. 라벨별 일수와 런 길이 다중집합을 **정확히 보존**,
    시장과의 정렬만 파괴.

    preserve_flips=True 면 인접 런의 라벨이 겹치지 않게 재배열해 **전환 수까지 정확히 보존**한다.
    단순 무작위 셔플은 같은 라벨 런이 인접해 병합되면서 전환 수가 실측 40% 가까이 줄어(97 -> 43~61)
    '같은 빈도, 틀린 정렬' 이라는 대조군 정의를 못 지켰다 — 그래서 제약 셔플을 기본으로 한다.
    """
    dates = sorted(regmap)
    rr = runs_of(regmap)
    rng = random.Random(seed)
    order = _sequence_no_adjacent(rr, rng) if preserve_flips else None
    if order is None:
        order = list(rr); rng.shuffle(order)
    out, i = {}, 0
    for lab, n in order:
        for _ in range(n):
            out[dates[i]] = lab; i += 1
    return out


def flips(regmap):
    ds = sorted(regmap)
    return sum(1 for a, b in zip(ds, ds[1:]) if regmap[a] != regmap[b])


# ── 신호 수집 (디텍터는 한 번만 돌리고 arm 평가에서 재사용) ────────────────
def collect(detmod, oppmod, tf, syms=None):
    mod = importlib.import_module(detmod)
    opp = importlib.import_module(oppmod) if oppmod else None
    out = []
    for sym in (syms if syms is not None else detlib.SYMBOLS):
        try:
            rows = detlib.load_ohlcv(sym, tf)
        except (FileNotFoundError, RuntimeError):
            continue
        if len(rows) < 40:
            continue
        opp_set = set(opp.detect(rows)) if opp else set()
        sigs = [si for si in mod.detect(rows) if si + 1 < len(rows)]
        if sigs:
            out.append((rows, opp_set, sigs))
    return out


def eval_arm(collected, direction, regmap, use_regime, max_hold):
    trades = []
    for rows, opp_set, sigs in collected:
        lab = (lambda j, r=rows: regmap.get(r[j]["date"]))
        for si in sigs:
            ret, hold, reason = outcome(rows, si, direction, opp_set, lab,
                                        use_regime=use_regime, max_hold=max_hold)
            xi = min(si + hold, len(rows) - 1)
            trades.append((rows[si]["date"], rows[xi]["date"], ret, hold, reason))
    return trades


def weighted(pairs):
    tot = sum(n for _, n in pairs)
    return (sum(d * n for d, n in pairs) / tot) if tot else 0.0


def main(argv=None):
    global UNIVERSE_MODE
    argv = argv if argv is not None else sys.argv[1:]
    n_shuf = int(argv[argv.index("--shuffles") + 1]) if "--shuffles" in argv else SHUFFLES
    UNIVERSE_MODE = "--universe" in argv
    syms = symbols()
    print(f"[표본] {'유니버스 80' if UNIVERSE_MODE else '메이저'} {len(syms)}종목: "
          f"{', '.join(syms[:12])}{' …' if len(syms) > 12 else ''}")
    if "--no-fetch" not in argv:
        ensure_data(FETCH_DAYS, syms)
    regmap = rs.build_regime_map()
    last = max(regmap)
    cutoff = (date.fromisoformat(last) - timedelta(days=HOLDOUT_DAYS)).isoformat()
    ymix = {}
    for d, g in regmap.items():
        ymix.setdefault(d[:4], {}).setdefault(g, 0); ymix[d[:4]][g] += 1
    rr = runs_of(regmap)
    print(f"[regime] {len(regmap)}일 | 런 {len(rr)}개 | 전환 {flips(regmap)}회 | 홀드아웃 cutoff {cutoff}")
    print("[regime] 연도별: " + "  ".join(f"{y}:{v}" for y, v in sorted(ymix.items())))
    shufs = [shuffle_regmap(regmap, SHUFFLE_SEED0 + s) for s in range(n_shuf)]
    fl = [flips(m) for m in shufs]
    ok_days = all(mr._count(m.values()) == mr._count(regmap.values()) for m in shufs)
    ok_flips = all(f == flips(regmap) for f in fl)
    print(f"[shuffle] {n_shuf} draw | 전환 수 {min(fl)}~{max(fl)} (원본 {flips(regmap)}, 정확 보존 {ok_flips}) "
          f"| 라벨 일수 보존 {ok_days}")
    mm.ARMS, mm.ARM_RULE = ARMS, ARM_RULE
    print("=" * 130)
    print("레짐 청산 소거 시험 — D(현행) vs D_norg(제거) vs D_time(보유상한 대체) vs D_shuffle(정렬 파괴)")
    print("=" * 130)
    results, caps, shuf_pairs = {}, {}, [[] for _ in range(n_shuf)]
    for label, direction, detmod, oppmod, tf in mt.PATS:
        collected = collect(detmod, oppmod, tf, syms)
        if not collected:
            print(f"\n[{label}] 신호 없음 — 스킵"); continue
        base = eval_arm(collected, direction, regmap, True, MAX_HOLD)
        if not base:
            print(f"\n[{label}] 신호 없음 — 스킵"); continue
        cap = max(1, min(MAX_HOLD, round(st.mean(t[3] for t in base))))
        caps[label] = cap
        arms = {
            "D": base,
            "D_norg": eval_arm(collected, direction, regmap, False, MAX_HOLD),
            "D_time": eval_arm(collected, direction, regmap, False, cap),
            "D_shuffle": eval_arm(collected, direction, shufs[0], True, MAX_HOLD),
        }
        tr, ho = mr.split_idx(base, cutoff)
        res = {m: dict(train=mm._arm_stats(base, arms[m], tr, m, True),
                       holdout=mm._arm_stats(base, arms[m], ho, m, False)) for m in ARMS}
        res["_reasons"] = {m: mr._count(t[4] for t in arms[m]) for m in ARMS}
        res["_cap"], res["_n_train"], res["_n_holdout"] = cap, len(tr), len(ho)
        results[label] = res
        print(f"\n[{label} @{tf} {direction}] train {len(tr)} / holdout {len(ho)} | D 평균보유 "
              f"{st.mean(t[3] for t in base):.1f}봉 -> D_time 상한 {cap}봉")
        print(f"  청산사유 D {res['_reasons']['D']}")
        print(f"           D_norg {res['_reasons']['D_norg']}")
        mm._print(res, "train"); mm._print(res, "holdout")
        # 셔플 draw 분포 (train 구간 짝지음)
        bt = [base[i] for i in tr]
        for s in range(n_shuf):
            full = eval_arm(collected, direction, shufs[s], True, MAX_HOLD)
            at = [full[i] for i in tr]
            shuf_pairs[s].append((st.mean(a[2] - b[2] for a, b in zip(at, bt)), len(bt)))
    if not results:
        print("결과 없음"); return
    results["_pooled"] = {"train": {}, "holdout": {}}
    print("\n" + "=" * 130)
    print("합산 + 판정 (arm 이 D 보다 나으면 양수. 소거 arm 이 음수면 = 레짐 청산이 일하고 있다)")
    verdicts = {}
    for m in ARMS:
        if m == "D":
            continue
        for split in ("train", "holdout"):
            results["_pooled"][split][m] = mr._pool(results, split, m)
        v = mr.verdict(results, m)
        verdicts[m] = v
        trp = results["_pooled"]["train"][m] or {}
        hop = results["_pooled"]["holdout"][m] or {}
        dv = trp.get("divergence", {})
        wr = dv.get("arm_wins", 0) / max(1, dv.get("arm_wins", 0) + dv.get("arm_losses", 0)) * 100
        print(f"  {m:<12} train n={trp.get('n')} diff={trp.get('mean_diff', 0)*100:+.3f}%p "
              f"t={trp.get('t', 0):.2f} boot_p={trp.get('boot_p', 1):.3f} CAGR우위 {v['c2_cagr_wins']}/7 "
              f"분기 {dv.get('n', 0)}건 승률 {wr:.0f}% | holdout diff={hop.get('mean_diff', 0)*100:+.3f}%p "
              f"→ {'PASS(D 보다 우위)' if v['pass_'] else 'REJECT'}")
    sd = [weighted(p) for p in shuf_pairs if p]
    d_wins = sum(1 for x in sd if x < 0)
    frac = d_wins / len(sd) if sd else 0.0
    sd_sorted = sorted(sd)
    print(f"\n[셔플 분포] {len(sd)} draw 합산 짝지음(D_shuffle − D): "
          f"중앙 {st.median(sd)*100:+.3f}%p  범위 {sd_sorted[0]*100:+.3f}~{sd_sorted[-1]*100:+.3f}%p")
    print(f"[셔플 분포] D 가 이긴 draw {d_wins}/{len(sd)} ({frac*100:.0f}%) "
          f"— 사전 기준: >=90% 면 상태 정보 실재, <=60% 면 시계")
    norg = results["_pooled"]["train"].get("D_norg") or {}
    dtime = results["_pooled"]["train"].get("D_time") or {}
    A = frac >= 0.90 and norg.get("mean_diff", 0) < 0
    B = frac <= 0.60 or (dtime.get("mean_diff", 0) >= 0 and dtime.get("t", 0) > -2)
    C = bool(verdicts.get("D_norg", {}).get("pass_"))
    verdict = ("C_레짐청산_해로움" if C
               else "A_상태정보_실재" if A and not B
               else "B_레짐은_시계" if B and not A
               else "D_정보있음_그러나_시계로대체가능" if A and B
               else "INCONCLUSIVE")
    print(f"\n[판정] {verdict}  (A={A} B={B} C={C})")
    results["_shuffle"] = dict(n=len(sd), diffs=sd, d_win_frac=frac,
                               median=st.median(sd) if sd else None,
                               orig_flips=flips(regmap), shuf_flips=fl)
    results["_verdicts"], results["_verdict"] = verdicts, verdict
    results["_config"] = dict(arms=ARMS, caps=caps, holdout_days=HOLDOUT_DAYS, cutoff=cutoff,
                              shuffles=n_shuf, stop=STOP, max_hold=MAX_HOLD, fetch_days=FETCH_DAYS,
                              year_mix=ymix, universe_mode=UNIVERSE_MODE, n_symbols=len(syms),
                              symbols=syms)
    out_path = "method_s_universe.json" if UNIVERSE_MODE else "method_s.json"
    json.dump(results, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1,
              default=mr._jsonable)
    print(f"[저장] {out_path}")
    print("\nRESULT_JSON: " + json.dumps(dict(
        verdict=verdict, universe="80" if UNIVERSE_MODE else "majors", n_symbols=len(syms),
        d_win_frac=round(frac, 3),
        pooled={m: round((results["_pooled"]["train"].get(m) or {}).get("mean_diff", 0), 5)
                for m in ARMS if m != "D"}), separators=(",", ":")))


if __name__ == "__main__":
    main()
