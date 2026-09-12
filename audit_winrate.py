"""
audit_winrate.py — **승률 35% 문턱 교정 감사** (2026-09-12).

사전 등록 registry `winrate_guard_audit_prereg_2026_09_12`.
사용자 지적: "건당·중앙·승률을 다 보면 너무 빡빡하다. 잃는 횟수가 더 많아도 먹을 때 크게 먹는 게 매매다.
이 수치들이 최적화된 것도 아니잖아."

먼저 정정 — **중앙값은 이미 판정에서 빠져 있다**(2026-09-05 게이트 v2). 남은 실질 쟁점은 승률 35% 하나다.

이 감사는 **문턱을 바꾸지 않는다. 측정만 한다.**
선례는 2026-09-09 audit_guards — 층별 독립 귀속으로 L8 이 12/12 기각하는 구조적 불가 층임을 드러냈고
판정에서 빼자 CONFIRMED 0→2 가 됐다. 같은 형태를 승률 층에 적용한다.

  A1 중복성      rho(승률, Calmar / 절사갭 / top5) — 승률이 다른 층의 재포장인가
  A2 증분 판별력  **승률 외 층을 전부 통과한 셀만** 승률 버킷별 국면 홀드아웃 건당  ← 주 판정
  A3 거짓음성    승률 **하나로만** 떨어진 셀 전수 + 그 셀들의 홀드아웃·Calmar
  A4 문턱 격자    {25,30,35,40}% 에서 통과 셀 수·홀드아웃 (진단 — 최대값을 고르지 않는다)

판정: REDUNDANT(A2 비단조 ∧ |rho|>=0.5) / INDEPENDENT(A2 단조 ∧ 최저버킷<=0) / INCONCLUSIVE(표본부족).

실행: python audit_winrate.py [--no-fetch]
"""
import importlib
import json
import statistics as st
import sys
import time
from datetime import date

import audit_guards as ag
import frame_v3 as f3
import gate
import regime_switch as rs
import validate_regime_split_all as va
import validate_revival as vr

COHORT = "top30"
WR_GRID = (0.25, 0.30, 0.35, 0.40)
WR_BUCKETS = ((0.00, 0.30), (0.30, 0.35), (0.35, 0.40), (0.40, 1.01))
RHO_THR = 0.50          # A1 중복 문턱 (사전 등록)
MIN_CELLS_A2 = 10       # A2 적격 셀 하한 (사전 등록)
MIN_PER_BUCKET = 3      # 버킷당 하한 (사전 등록)


# ── 셀 모집단 — 둘 다 이 질문 전에 레포에 있던 목록. 여기서 새로 고르지 않는다 ──────
def population():
    tbl = vr._pattern_table()
    cells, seen = [], set()
    for cid, g in vr.CANDIDATES:                      # revival 후보(기각·정지 셀 다수)
        if cid not in tbl or tbl[cid][0] not in ("1d", "4h"):
            continue
        tf, fn, d = tbl[cid]
        if (cid, g) in seen:
            continue
        seen.add((cid, g))
        cells.append(dict(cid=cid, regime=g, tf=tf, direction=d, fn=fn, src="revival"))
    for c in ag.CELLS:                                 # 실거래 라우팅·배포·관찰 셀
        cid, g = c["pattern"], c["regime"]
        if c["tf"] not in ("1d", "4h") or (cid, g) in seen:
            continue
        seen.add((cid, g))
        mod = importlib.import_module(c["det"])
        cells.append(dict(cid=cid, regime=g, tf=c["tf"], direction=c["direction"],
                          fn=(lambda rows, m=mod: m.detect(rows)), src="live:" + c["status"]))
    return cells


def spearman(xs, ys):
    """동률 평균 순위 스피어만."""
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    if len(pairs) < 5:
        return None
    def rank(vs):
        order = sorted(range(len(vs)), key=lambda i: vs[i])
        r = [0.0] * len(vs)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and vs[order[j + 1]] == vs[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r
    rx, ry = rank([p[0] for p in pairs]), rank([p[1] for p in pairs])
    mx, my = st.mean(rx), st.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return (num / den) if den else None


def _f(v, w=8):
    return f"{'n/a':>{w}}" if v is None else f"{v*100:>+{w-1}.2f}%"


def other_fails(rec, jd, core_only=False):
    """**승률을 뺀** 나머지 층의 실패 목록. 이게 비어야 '승률 하나로만 떨어졌다'.
    core_only=True 면 C1 계열(n·평균·boot_p·OOS)만 본다 — A2b 진단용."""
    f = []
    if rec["n"] < gate.MIN_N: f.append("n<20")
    if rec["mean"] <= 0: f.append("mean<=0")
    if rec["boot_p"] >= 0.05: f.append(f"bp={rec['boot_p']:.3f}")
    if rec["n"] >= gate.MIN_N and rec["oos_pos"] < 2: f.append(f"OOS{rec['oos_pos']}/4")
    if core_only: return f
    if not jd["c2_holdout"]: f.append("holdout")
    if not jd["c2b_train"]: f.append("C2b")
    if not jd["c3_equity"]: f.append("C3")
    if not jd["E"]["ok"]: f.append("E")
    return f


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    print("승률 35% 문턱 교정 감사 — **문턱 변경 없음, 측정만**")
    print(f"버킷 {[f'{a:.0%}~{b:.0%}' for a,b in WR_BUCKETS]} | 격자 {[f'{g:.0%}' for g in WR_GRID]} "
          f"| A1 문턱 |rho|>={RHO_THR} | A2 하한 셀{MIN_CELLS_A2}·버킷{MIN_PER_BUCKET}", flush=True)

    syms = va._syms()
    if "--no-fetch" not in argv:
        va.fetch(syms, ["1d", "4h"])
    rows_1d = va.load_tf(syms, "1d", long=True)
    regmap = rs.build_regime_map(rows_by=rows_1d)
    ranked = vr.turnover_rank(rows_1d)

    ctx = {}
    for tf in ("1d", "4h"):
        t0 = time.time()
        rows_by = rows_1d if tf == "1d" else va.load_tf(syms, tf)
        rows_by = {s: r for s, r in rows_by.items() if len(r) > 60}
        cs = set(s for s in ranked[:30] if s in rows_by)
        pools, atrs = vr.build_context(tf, rows_by, {COHORT: cs}, regmap)
        ctx[tf] = dict(rows_by=rows_by, cs=cs, pools=pools, atrs=atrs, pool_cache={})
        print(f"[{tf}] 종목 {len(rows_by)} · top30 {len(cs)} ({time.time()-t0:.0f}s)", flush=True)

    cells, rows = population(), []
    print(f"\n셀 모집단 {len(cells)} (revival 후보 + 실거래/배포/관찰)", flush=True)
    for c in cells:
        k, tf = ctx[c["tf"]], c["tf"]
        if c["regime"] not in vr.REGIMES + ["ALL"]:
            continue
        pk = (c["regime"], c["direction"])
        if pk not in k["pool_cache"]:
            k["pool_cache"][pk] = vr.eval_pool(tf, k["pools"][(COHORT, c["regime"])],
                                               k["rows_by"], k["atrs"], regmap, c["direction"])
        pool = k["pool_cache"][pk]
        by = vr.collect(tf, c["fn"], c["direction"], k["rows_by"], k["atrs"], regmap)
        sigs = [x for s in k["cs"] for x in by.get(s, [])
                if c["regime"] == "ALL" or x["regime"] == c["regime"]]
        if len(sigs) < gate.MIN_N:
            continue
        rec = vr.gate_cell(sigs, pool)
        jd = f3.judge(sigs, pool, regmap, c["regime"], equity_fn=lambda t, s: vr.equity(t, s))
        eq = jd["equity"] or {}
        rows.append(dict(
            cid=f"{c['cid']}|{c['regime']}", tf=tf, src=c["src"], n=rec["n"],
            mean=rec["mean"], median=rec["median"], win_rate=rec["win_rate"],
            trim_gap=(rec["trimmed_mean"] - rec["mean"]) if rec["trimmed_mean"] is not None else None,
            top5=rec["top5_share"], boot_p=rec["boot_p"], edge=rec["edge"], oos=rec["oos_pos"],
            calmar=eq.get("calmar"), cagr=eq.get("cagr"),
            ho_n=jd["holdout"]["n"], ho_mean=jd["holdout"]["mean"],
            other_fails=other_fails(rec, jd), core_fails=other_fails(rec, jd, core_only=True),
            verdict=jd["verdict"]))
        print(f"  {rows[-1]['cid'][:42]:<42} n={rec['n']:>5} 승률 {rec['win_rate']*100:>3.0f}% "
              f"건당 {_f(rec['mean'])} 홀드아웃 {_f(jd['holdout']['mean'])} "
              f"Calmar {eq.get('calmar', 0) or 0:>6.2f} | 승률외 탈락 {','.join(rows[-1]['other_fails']) or '없음'}",
              flush=True)

    out = dict(frame="winrate_guard_audit", threshold_changed=False, cells=rows)
    print(f"\n{'='*100}\n== A1 중복성 — 승률이 다른 층의 재포장인가 (n={len(rows)}셀) ==")
    wr = [r["win_rate"] for r in rows]
    a1 = {}
    for name, key in (("Calmar", "calmar"), ("절사갭(절사평균−평균)", "trim_gap"), ("top5 기여도", "top5")):
        rho = spearman(wr, [r[key] for r in rows])
        a1[key] = rho
        mark = "**중복 시사**" if rho is not None and abs(rho) >= RHO_THR else "독립적"
        print(f"  rho(승률, {name:<18}) = {'n/a' if rho is None else f'{rho:+.3f}'}  {mark}")
    out["A1"] = a1

    print(f"\n== A2 증분 판별력 (주 판정) — **승률 외 층을 전부 통과한 셀만** ==")
    elig = [r for r in rows if not r["other_fails"] and r["ho_mean"] is not None]
    print(f"  적격 셀 {len(elig)} (하한 {MIN_CELLS_A2})")
    a2, thin = [], False
    for lo, hi in WR_BUCKETS:
        b = [r for r in elig if lo <= r["win_rate"] < hi]
        m = st.mean(r["ho_mean"] for r in b) if b else None
        a2.append(dict(lo=lo, hi=hi, n=len(b), ho_mean=m, cids=[r["cid"] for r in b]))
        if len(b) < MIN_PER_BUCKET:
            thin = True
        print(f"  승률 {lo:.0%}~{hi:.0%}: 셀 {len(b):>2} · 홀드아웃 건당 평균 {_f(m)}"
              + (f"   {', '.join(r['cid'] for r in b)[:70]}" if b else ""))
    out["A2"] = a2
    ms = [b["ho_mean"] for b in a2 if b["ho_mean"] is not None]
    monotone = len(ms) >= 2 and all(ms[i] <= ms[i + 1] for i in range(len(ms) - 1))
    low = next((b["ho_mean"] for b in a2 if b["hi"] <= 0.30), None)

    print(f"\n== A2b 진단 (판정 아님) — **C1 계열(n·평균·boot_p·OOS)만** 통과한 셀로 넓혀 본 같은 표 ==")
    print("   사전 확률에 'A2 는 적격 셀 부족으로 INCONCLUSIVE 일 것'이라 적어서, 정보 없는 실행을 막으려고")
    print("   **실행 전에** 넓은 판을 하나 더 붙였다. 판정식은 그대로다(A2 만 판정).")
    elig_b = [r for r in rows if not r["core_fails"] and r["ho_mean"] is not None]
    a2b_rows = []
    print(f"  적격 셀 {len(elig_b)}")
    for lo, hi in WR_BUCKETS:
        b = [r for r in elig_b if lo <= r["win_rate"] < hi]
        m = st.mean(r["ho_mean"] for r in b) if b else None
        pos = sum(1 for r in b if r["ho_mean"] > 0)
        a2b_rows.append(dict(lo=lo, hi=hi, n=len(b), ho_mean=m, ho_pos=pos))
        print(f"  승률 {lo:.0%}~{hi:.0%}: 셀 {len(b):>2} · 홀드아웃 건당 평균 {_f(m)} · 홀드아웃 양수 {pos}")
    out["A2b_diag"] = a2b_rows

    print(f"\n== A3 거짓음성 — **승률 하나로만** 떨어진 셀 ==")
    fn_cells = [r for r in rows if not r["other_fails"] and r["win_rate"] < gate.WIN_RATE_MIN]
    if not fn_cells:
        print("  없음 — 승률로 떨어진 셀은 전부 다른 층에서도 떨어졌다")
    for r in sorted(fn_cells, key=lambda x: -(x["ho_mean"] or -9)):
        print(f"  {r['cid'][:40]:<40} 승률 {r['win_rate']*100:>3.0f}% 건당 {_f(r['mean'])} "
              f"**홀드아웃 {_f(r['ho_mean'])}**(n={r['ho_n']}) Calmar {r['calmar'] or 0:>6.2f} "
              f"절사갭 {_f(r['trim_gap'])} top5 {_f(r['top5'])}")
    out["A3"] = fn_cells

    print(f"\n== A4 문턱 격자 (진단 — 최대값을 사후에 고르지 않는다) ==")
    a4 = []
    for g in WR_GRID:
        p = [r for r in rows if not r["other_fails"] and r["win_rate"] >= g]
        hm = st.mean(r["ho_mean"] for r in p if r["ho_mean"] is not None) if p else None
        pos = sum(1 for r in p if (r["ho_mean"] or 0) > 0)
        a4.append(dict(thr=g, n_pass=len(p), ho_mean=hm, ho_pos=pos))
        print(f"  승률>={g:.0%}: 통과 셀 {len(p):>2} · 홀드아웃 평균 {_f(hm)} · 홀드아웃 양수 {pos}")
    out["A4"] = a4

    print(f"\n{'='*100}\n== 판정 ==")
    if len(elig) < MIN_CELLS_A2 or thin:
        v = "INCONCLUSIVE"
        why = f"A2 적격 셀 {len(elig)}<{MIN_CELLS_A2}" if len(elig) < MIN_CELLS_A2 else f"버킷당 셀<{MIN_PER_BUCKET}"
    elif monotone and low is not None and low <= 0:
        v, why = "INDEPENDENT", "A2 단조 증가 + 최저 버킷 홀드아웃<=0 — 승률이 독립적으로 막는 것이 있다"
    elif (not monotone) and any(r is not None and abs(r) >= RHO_THR for r in a1.values()):
        v, why = "REDUNDANT", "A2 비단조 + A1 중복 — 승률은 다른 층의 재포장. 완화 후보"
    else:
        v, why = "INCONCLUSIVE", "REDUNDANT·INDEPENDENT 어느 조건도 충족 안 됨"
    out["verdict"], out["why"] = v, why
    print(f"  **{v}** — {why}")
    print(f"\n**문턱은 바뀌지 않았다** (승률 문턱 그대로 {gate.WIN_RATE_MIN:.0%}). "
          "완화·유지는 사용자 결정(CLAUDE.md: 게이트 문턱 변경은 사용자 결정).")
    json.dump(out, open("winrate_audit.json", "w"), ensure_ascii=False, indent=1, default=str)
    print("→ winrate_audit.json")
    return out


if __name__ == "__main__":
    main()
