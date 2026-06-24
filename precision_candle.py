"""
precision_candle.py — inverted_hammer / marubozu 정밀검증 (engulfing과 동일 방식, 28종목).
  슬리피지(+0.1%) 후 베이스라인 p<0.05 유지 + 평균·중앙>0,
  워크포워드 6개월 윈도우 >=60% 양수, 2025-07+ 마모 확인.
  통과 -> registry status=validated, 실패 -> passed 유지 + 사유. 게이트 동결.
"""
import json
import importlib
import statistics as st

import baseline
import research_log

SLIP = 0.001
CUT = "2025-07-01"
WF_MIN_SIG = 3
WF_MIN_POS_FRAC = 0.6
TARGETS = {"inverted_hammer": "Inverted Hammer", "marubozu": "Marubozu"}


def universe():
    return json.load(open("universe.json", encoding="utf-8"))["trading_universe"]


def six_month_windows():
    b = [f"{y}-{mm}-01" for y in range(2021, 2027) for mm in ("01", "07")
         if f"{y}-{mm}-01" <= "2026-07-01"]
    return [(b[i], b[i + 1]) for i in range(len(b) - 1)]


def sigs_of(mod, uni):
    out = []
    for sym in uni:
        try:
            rows = mod.load_ohlcv(sym, "1d")
        except FileNotFoundError:
            continue
        for si in mod.detect(rows):
            out.append((rows[si]["date"], mod.outcome(rows, si)[1]))
    return out


def pool_of(mod, uni):
    pool = []
    for sym in uni:
        try:
            rows = mod.load_ohlcv(sym, "1d")
        except FileNotFoundError:
            continue
        for i in range(len(rows) - 1):
            pool.append(mod.outcome(rows, i)[1])
    return pool


def main():
    uni = universe()
    reg = json.load(open("registry.json", encoding="utf-8"))
    by_id = {p["id"]: p for p in reg["patterns"]}
    for pid, name in TARGETS.items():
        mod = importlib.import_module(f"detector_{pid}")
        sigs = sigs_of(mod, uni)
        rets = [r for _, r in sigs]; n = len(rets)
        print(f"\n[{pid}] n={n} (28종목)")

        # 슬리피지
        sr = [r - SLIP for r in rets]
        sm, smd = st.mean(sr), st.median(sr)
        pool = [x - SLIP for x in pool_of(mod, uni)]
        bt = baseline.test(pool, sm, smd, n)
        slip_ok = sm > 0 and smd > 0 and bool(bt and bt["significant"])
        print(f"  슬리피지+0.1%: 평균 {sm*100:+.2f}%, 중앙 {smd*100:+.2f}%, p={bt['p_mean']:.3f} -> {'통과' if slip_ok else '실패'}")

        # 워크포워드
        pos = valid = 0
        for lo, hi in six_month_windows():
            wr = [r for d, r in sigs if lo <= d < hi]
            if len(wr) >= WF_MIN_SIG:
                valid += 1; pos += (st.mean(wr) > 0)
        pf = pos / valid if valid else 0
        wf_ok = valid >= 4 and pf >= WF_MIN_POS_FRAC
        print(f"  워크포워드: 유효 {valid} 중 양수 {pos} ({pf*100:.0f}%) -> {'통과' if wf_ok else '실패'}")

        # 마모
        tail = [r for d, r in sigs if d >= CUT]
        tail_mean = st.mean(tail) if tail else None
        worn = tail_mean is not None and tail_mean < 0
        print(f"  마모(2025-07+): n={len(tail)}, 평균 {tail_mean*100:+.2f}%" if tail_mean is not None else "  마모: 표본없음")

        ok = slip_ok and wf_ok
        status = "validated" if ok else "passed"
        fails = [x for x, c in [("슬리피지", slip_ok), ("워크포워드", wf_ok)] if not c]
        # registry upsert
        entry = by_id.get(pid, {"id": pid, "name": name, "category": "캔들",
                                "difficulty": 1, "detector_file": f"detector_{pid}.py"})
        entry.update(status=status, passed_tf="1d",
                     precision=dict(slip=dict(mean=round(sm, 5), median=round(smd, 5),
                                              p_mean=bt["p_mean"], ok=slip_ok),
                                    walkforward=dict(valid=valid, pos=pos, pos_frac=round(pf, 3), ok=wf_ok)),
                     wear=dict(cut=CUT, base_2025plus_mean=round(tail_mean, 5) if tail_mean is not None else None,
                               restored=False, note=("마모 징후(2025-07+ 음수)" if worn else "마모 없음")))
        if not ok:
            entry["precision_note"] = "강등유지: " + ", ".join(fails) + " 미통과"
        if pid not in by_id:
            reg["patterns"].append(entry)
        research_log.append_log(pid, "PRECISION@1d", {"slip_ok": slip_ok, "wf_ok": wf_ok},
                                n, 0.0, sm, smd, status)
        print(f"  => status={status}" + (f" ({entry.get('precision_note')})" if not ok else " (VALIDATED)"))

    json.dump(reg, open("registry.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("\n[저장] registry.json")


if __name__ == "__main__":
    main()
