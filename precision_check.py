"""
precision_check.py — 임의 패턴에 정밀검증 3종 + 마모 측정(제네릭).
사용: python precision_check.py <pattern_id>
  슬리피지(+0.1%), 워크포워드(6개월 롤링), 표본확대(신규5종), 마모(2025-07+).
  슬리피지·워크포워드·표본확대 모두 통과 -> validated, 아니면 passed + 사유.
게이트 동결 유지.
"""
import sys
import json
import importlib
import statistics as st

import baseline
import research_log

TF_DEFAULT = "1d"
SLIP = 0.001
NEW_SYMBOLS = ["LINK", "DOT", "LTC", "ATOM", "UNI"]
WF_MIN_SIG = 3
WF_MIN_POS_FRAC = 0.6
CUT_2025 = "2025-07-01"
MIN_N = 20


def signals_with_date(mod, tf, symbols=None):
    det = getattr(mod, "detect", None) or getattr(mod, "detect_sweeps")
    out = []
    for sym in (symbols or mod.SYMBOLS):
        try:
            rows = mod.load_ohlcv(sym, tf)
        except FileNotFoundError:
            continue
        for si in det(rows):
            _, ret = mod.outcome(rows, si)
            out.append((sym, rows[si]["date"], ret))
    return out


def six_month_windows():
    b = [f"{y}-{mm}-01" for y in range(2021, 2027) for mm in ("01", "07")
         if f"{y}-{mm}-01" <= "2026-07-01"]
    return [(b[i], b[i + 1]) for i in range(len(b) - 1)]


def main():
    pid = sys.argv[1]
    reg = json.load(open("registry.json", encoding="utf-8"))
    p = next(x for x in reg["patterns"] if x["id"] == pid)
    tf = p.get("passed_tf", TF_DEFAULT)
    mod = importlib.import_module(p["detector_file"][:-3])
    print(f"[{pid} 정밀검증] tf={tf}")

    sigs = signals_with_date(mod, tf)
    rets = [r for _, _, r in sigs]
    n = len(rets)

    # A1 슬리피지
    sr = [r - SLIP for r in rets]
    sm, smd = st.mean(sr), st.median(sr)
    pool = [x - SLIP for x in baseline.entry_pool(mod, tf)]
    bt = baseline.test(pool, sm, smd, n)
    slip_ok = sm > 0 and smd > 0 and bool(bt and bt["significant"])
    print(f"  슬리피지: 평균={sm*100:+.2f}%, 중앙={smd*100:+.2f}%, p={bt['p_mean']:.3f} -> {'통과' if slip_ok else '실패'}")
    research_log.append_log(pid, "PREC@slip", {"slip": SLIP, "p": bt["p_mean"]},
                            n, 0.0, sm, smd, "통과" if slip_ok else "실패")

    # A2 워크포워드
    pos = valid = 0
    wf = []
    for lo, hi in six_month_windows():
        wr = [r for _, d, r in sigs if lo <= d < hi]
        if len(wr) >= WF_MIN_SIG:
            valid += 1; m = st.mean(wr)
            pos += (m > 0); wf.append((lo[:7], len(wr), m))
    pf = pos / valid if valid else 0
    wf_ok = valid >= 4 and pf >= WF_MIN_POS_FRAC
    print(f"  워크포워드: 유효 {valid} 중 양수 {pos} ({pf*100:.0f}%) -> {'통과' if wf_ok else '실패'}")
    for lab, c, m in wf:
        print(f"      {lab}: n={c} {m*100:+.2f}%")
    research_log.append_log(pid, "PREC@walkforward", {"valid": valid, "pos": pos},
                            valid, pf, 0.0, 0.0, "통과" if wf_ok else "실패")

    # A3 표본확대
    nw = signals_with_date(mod, tf, NEW_SYMBOLS)
    nr = [r for _, _, r in nw]
    persym = sum(1 for s in NEW_SYMBOLS
                 if [r for ss, _, r in nw if ss == s] and st.mean([r for ss, _, r in nw if ss == s]) > 0)
    nm, nmd = (st.mean(nr), st.median(nr)) if nr else (0, 0)
    sym_ok = nm > 0 and nmd > 0
    print(f"  표본확대(5종): n={len(nr)}, 평균={nm*100:+.2f}%, 종목별 양수 {persym}/5 -> {'통과' if sym_ok else '실패'}")
    research_log.append_log(pid, "PREC@newsymbols", {"persym_pos": persym},
                            len(nr), 0.0, nm, nmd, "통과" if sym_ok else "실패")

    # 마모 (2025-07+ tail)
    tail = [r for _, d, r in sigs if d >= CUT_2025]
    tail_mean = st.mean(tail) if tail else None
    worn = (tail_mean is not None and tail_mean < 0)
    print(f"  마모(2025-07+): n={len(tail)}, 평균={tail_mean*100:+.2f}%" if tail_mean is not None
          else "  마모: 표본없음")

    fails = [name for name, ok in
             [("슬리피지", slip_ok), ("워크포워드", wf_ok), ("표본확대", sym_ok)] if not ok]
    p["precision"] = dict(
        slip=dict(mean=round(sm, 5), median=round(smd, 5), p_mean=bt["p_mean"], ok=slip_ok),
        walkforward=dict(valid=valid, pos=pos, pos_frac=round(pf, 3), ok=wf_ok),
        newsymbols=dict(n=len(nr), mean=round(nm, 5), median=round(nmd, 5),
                        persym_pos=persym, ok=sym_ok))
    p["wear"] = dict(cut=CUT_2025, base_2025plus_mean=round(tail_mean, 5) if tail_mean is not None else None,
                     restored=False, note=("마모 징후(2025-07+ 음수)" if worn else "마모 없음"))
    if not fails:
        p["status"] = "validated"; p.pop("reject_reason", None)
        print(f"=> {pid}: 정밀검증 3종 통과 -> VALIDATED")
    else:
        p["status"] = "passed"; p["precision_note"] = "강등: " + ", ".join(fails) + " 미통과"
        print(f"=> {pid}: {', '.join(fails)} 미통과 -> passed")
    json.dump(reg, open("registry.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
