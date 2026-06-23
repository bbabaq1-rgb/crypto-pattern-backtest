"""
precision_filters.py — engulfing 마모(2025+ 음수) 복원 필터 실험.

base engulfing(이미 1.5x 거래량 내장)에 각 필터를 AND로 추가:
  vol2x   : 거래량 >= 직전 20봉 평균 x 2.0 (더 강한 거래량)
  regime  : 200일 MA 기울기 down/side 일 때만 (상승장 신호 제외)
  position: 직전 POS_LB봉 레인지 하단 30% 구간에서 발생

각 필터별 (전체 평균/중앙, 2025+ 평균, 베이스라인 p, n) 비교.
복원 = n>=20 AND 전체 평균·중앙>0 AND 2025+ 평균>0 AND 베이스라인 p<0.05.
복원 성공시 최다표본 필터를 RESTORED로 출력.
"""
import json
import statistics as st

import detector_engulfing as eng
import baseline
import regime

TF = "1d"
VOL2 = 2.0
POS_LB = 30
CUT_2025 = "2025-07-01"    # 마모 구간(2025-07, 2026-01 윈도우) 타깃
MIN_N = 20


def collect():
    """base engulfing 신호별 (date, ret, vol_ok, reg_ok, pos_ok)."""
    out = []
    for sym in eng.SYMBOLS:
        try:
            rows = eng.load_ohlcv(sym, TF)
        except FileNotFoundError:
            continue
        reg = regime.classify(rows)
        v = [r["v"] for r in rows]; hi = [r["h"] for r in rows]; lo = [r["l"] for r in rows]
        cl = [r["c"] for r in rows]
        for si in eng.detect(rows):
            _, ret = eng.outcome(rows, si)
            base = sum(v[si - 20:si]) / 20 if si >= 20 else 0
            vol_ok = base > 0 and v[si] >= VOL2 * base
            reg_ok = reg[si] in ("down", "side")
            lo_w = min(lo[max(0, si - POS_LB):si + 1]); hi_w = max(hi[max(0, si - POS_LB):si + 1])
            pos = (cl[si] - lo_w) / (hi_w - lo_w) if hi_w > lo_w else 1.0
            pos_ok = pos <= 0.30
            out.append((rows[si]["date"], ret, vol_ok, reg_ok, pos_ok))
    return out


def metrics(rows):
    rets = [r for _, r in rows]
    if not rets:
        return None
    r25 = [r for d, r in rows if d >= CUT_2025]
    m = st.mean(rets); md = st.median(rets)
    m25 = st.mean(r25) if r25 else None
    return dict(n=len(rets), mean=m, median=md,
                mean25=m25, n25=len(r25))


def main():
    sigs = collect()
    pool = baseline.entry_pool(eng, TF)

    FILTERS = {
        "base(필터없음)": lambda d, r, vo, ro, po: True,
        "vol2x":          lambda d, r, vo, ro, po: vo,
        "regime(down/side)": lambda d, r, vo, ro, po: ro,
        "position(low30%)":  lambda d, r, vo, ro, po: po,
        "regime+position":   lambda d, r, vo, ro, po: ro and po,
    }

    print("=" * 84)
    print("engulfing 마모 복원 필터 실험 (1d, 2025+ 양전환 여부)")
    print(f"  base는 이미 1.5x 거래량 내장. CUT={CUT_2025}, 복원기준 n>=20 & 전체·2025+ 양수 & p<0.05")
    print("=" * 84)
    print(f"  {'필터':<20} {'n':>4} {'전체평균':>9} {'중앙':>9} {'2025+평균':>10} {'2025+n':>7} {'base_p':>7} {'복원':>5}")
    print("  " + "-" * 80)

    restored = []
    rows_for_log = []
    for name, pred in FILTERS.items():
        sub = [(d, r) for (d, r, vo, ro, po) in sigs if pred(d, r, vo, ro, po)]
        mt = metrics(sub)
        if mt is None:
            print(f"  {name:<20} {'0':>4}  (신호 없음)")
            continue
        bt = baseline.test(pool, mt["mean"], mt["median"], mt["n"]) if mt["n"] > 0 else None
        p = bt["p_mean"] if bt else 1.0
        ok = (mt["n"] >= MIN_N and mt["mean"] > 0 and mt["median"] > 0
              and (mt["mean25"] is not None and mt["mean25"] > 0) and p < 0.05)
        if ok and name != "base(필터없음)":
            restored.append((name, mt["n"], mt, p))
        m25s = f"{mt['mean25']*100:+.2f}%" if mt["mean25"] is not None else "  -  "
        print(f"  {name:<20} {mt['n']:>4} {mt['mean']*100:>+8.2f}% {mt['median']*100:>+8.2f}% "
              f"{m25s:>10} {mt['n25']:>7} {p:>7.3f} {'O' if ok else 'X':>5}")
        rows_for_log.append((name, mt, p, ok))

    print("\n" + "=" * 84)
    if restored:
        restored.sort(key=lambda x: -x[1])      # 최다표본 우선
        win = restored[0]
        print(f"RESTORED: {win[0]} (n={win[1]}, 전체 {win[2]['mean']*100:+.2f}%, "
              f"2025+ {win[2]['mean25']*100:+.2f}%, p={win[3]:.3f})")
        result = {"restored": True, "filter": win[0], "n": win[1],
                  "mean": round(win[2]["mean"], 5), "mean25": round(win[2]["mean25"], 5),
                  "p": win[3]}
    else:
        print("RESTORED: NONE - 마모는 이 필터들로 복원 불가, 페이퍼테스트 필요")
        result = {"restored": False}
    print("=" * 84)

    with open("_filter_result.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False)


if __name__ == "__main__":
    main()
