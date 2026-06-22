"""
precision_engulfing.py — engulfing 실거래 전 정밀검증 3종.

A1 슬리피지 : 진입+청산 각 0.05%(합 0.1%)를 추가 비용으로 빼고도
              베이스라인 유의 + 기대값(평균·중앙) 양수 유지되는지.
A2 워크포워드: 6개월 롤링 윈도우별 평균수익이 일관되게 양수인지
              (한두 구간만 좋고 나머지 음수면 불안정).
A3 표본확대  : 기존 7종목 외 중상위 알트 5종(LINK/DOT/LTC/ATOM/UNI)에서도
              양의 기대값인지(종목 의존 아닌지).

셋 다 통과 -> status=validated. 하나라도 무너지면 passed로 강등 + 사유 기록.
게이트 동결 유지(±10%, n>=20, 기대값 양수, 베이스라인 p<0.05).
"""
import json
import statistics as st

import detector_engulfing as eng
import baseline
import research_log

REGISTRY = "registry.json"
TF = "1d"
SLIP = 0.001                       # 0.05% x 2 (진입+청산)
NEW_SYMBOLS = ["LINK", "DOT", "LTC", "ATOM", "UNI"]
WF_MIN_SIG = 3                     # 윈도우 유효 최소 신호수
WF_MIN_POS_FRAC = 0.6             # 양의 윈도우 비율 기준


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
    bounds = []
    for y in range(2021, 2027):
        for mm in ("01", "07"):
            b = f"{y}-{mm}-01"
            if b <= "2026-07-01":
                bounds.append(b)
    return [(bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1)]


def main():
    sigs = signals_with_date(eng, TF)               # (sym, date, ret) 7종목
    rets = [r for _, _, r in sigs]
    n = len(rets)
    print(f"[engulfing 정밀검증] 기준 신호 n={n} (tf={TF})")

    # ---- A1 슬리피지 ----
    slip_rets = [r - SLIP for r in rets]
    s_mean, s_med = st.mean(slip_rets), st.median(slip_rets)
    pool = [x - SLIP for x in baseline.entry_pool(eng, TF)]
    bt = baseline.test(pool, s_mean, s_med, n)
    slip_ok = (s_mean > 0 and s_med > 0 and bool(bt and bt["significant"]))
    print(f"  A1 슬리피지(+0.1%): 평균={s_mean*100:+.2f}%, 중앙={s_med*100:+.2f}%, "
          f"베이스라인 p={bt['p_mean']:.3f} -> {'통과' if slip_ok else '실패'}")
    research_log.append_log("engulfing", "PREC@slip",
                            {"slip": SLIP, "p_mean": bt["p_mean"]},
                            n, 0.0, s_mean, s_med,
                            "통과" if slip_ok else "실패")

    # ---- A2 워크포워드 ----
    wins = six_month_windows()
    wf_rows, pos, valid = [], 0, 0
    for lo, hi in wins:
        wr = [r for _, d, r in sigs if lo <= d < hi]
        if len(wr) >= WF_MIN_SIG:
            valid += 1
            m = st.mean(wr)
            if m > 0:
                pos += 1
            wf_rows.append((lo[:7], len(wr), m))
    pos_frac = pos / valid if valid else 0.0
    wf_ok = (valid >= 4 and pos_frac >= WF_MIN_POS_FRAC)
    print(f"  A2 워크포워드: 유효윈도우 {valid}개 중 양수 {pos}개 ({pos_frac*100:.0f}%) "
          f"-> {'통과' if wf_ok else '실패'}")
    for lab, c, m in wf_rows:
        print(f"      {lab}: n={c} 평균={m*100:+.2f}%")
    research_log.append_log("engulfing", "PREC@walkforward",
                            {"valid_windows": valid, "pos": pos},
                            valid, pos_frac, 0.0, 0.0,
                            "통과" if wf_ok else "실패")

    # ---- A3 표본확대(신규 5종목) ----
    new_sigs = signals_with_date(eng, TF, NEW_SYMBOLS)
    new_rets = [r for _, _, r in new_sigs]
    persym_pos = 0
    for sym in NEW_SYMBOLS:
        sr = [r for s, _, r in new_sigs if s == sym]
        if sr and st.mean(sr) > 0:
            persym_pos += 1
    if new_rets:
        nm, nmd = st.mean(new_rets), st.median(new_rets)
        sym_ok = (nm > 0 and nmd > 0)
    else:
        nm = nmd = 0.0; sym_ok = False
    print(f"  A3 표본확대(5종): n={len(new_rets)}, 평균={nm*100:+.2f}%, 중앙={nmd*100:+.2f}%, "
          f"종목별 양수 {persym_pos}/5 -> {'통과' if sym_ok else '실패'}")
    research_log.append_log("engulfing", "PREC@newsymbols",
                            {"symbols": NEW_SYMBOLS, "persym_pos": persym_pos},
                            len(new_rets), 0.0, nm, nmd,
                            "통과" if sym_ok else "실패")

    # ---- 종합 판정 ----
    fails = []
    if not slip_ok: fails.append("슬리피지")
    if not wf_ok: fails.append("워크포워드")
    if not sym_ok: fails.append("표본확대")

    with open(REGISTRY, encoding="utf-8") as f:
        reg = json.load(f)
    for p in reg["patterns"]:
        if p["id"] == "engulfing":
            p["precision"] = dict(
                slip=dict(mean=round(s_mean, 5), median=round(s_med, 5),
                          p_mean=bt["p_mean"], ok=slip_ok),
                walkforward=dict(valid=valid, pos=pos, pos_frac=round(pos_frac, 3), ok=wf_ok),
                newsymbols=dict(n=len(new_rets), mean=round(nm, 5), median=round(nmd, 5),
                                persym_pos=persym_pos, ok=sym_ok),
            )
            if not fails:
                p["status"] = "validated"
                p.pop("reject_reason", None)
                print("\n=> engulfing: 3종 정밀검증 모두 통과 -> status=VALIDATED (실거래 검토 가능)")
            else:
                p["status"] = "passed"
                p["precision_note"] = "강등 사유: " + ", ".join(fails) + " 미통과"
                print(f"\n=> engulfing: {', '.join(fails)} 미통과 -> passed로 강등")
            break
    with open(REGISTRY, "w", encoding="utf-8") as f:
        json.dump(reg, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
