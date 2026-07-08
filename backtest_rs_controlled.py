"""
backtest_rs_controlled.py — 레짐(시장 cap) 통제 후 rs 순증분 엣지 검증.

질문: weak_rs 필터(롱 rs<0.2 → ×0.5)가 진짜 독립 엣지인가, 아니면 시장 레짐(cap)의
중복인가? rs와 cap은 상관 0.33 → rs>0.2 필터의 표면 엣지가 레짐 교란일 수 있음.
방법(look-ahead 없음, 방식D): 같은 '시장 cap 구간' 안에서 rs>0.2 vs rs<0.2 비교.
  레짐을 통제했는데도 rs가 여전히 가르면 → 독립 엣지(유지). 사라지면 → 중복(폐기).
판정(사전 고정): 통제 후에도 3개 이상 cap구간에서 rs유리>불리 mean AND 전체 유의
(Welch p<0.10) → 유지. 아니면 폐기(자유도 감소).
"""
import sys
import statistics as st

import detlib
from method_d import outcome_d, summ, _calmar
from method_e import PATS_ALL
from relative_strength import compute_rs
from backtest_regime_capture import build_breadth, OOS
from backtest_rs import _welch_p

import importlib

RS_THR = 0.2


def _s(g):
    if not g:
        return None
    rets = [r["ret"] for r in g]
    s = summ(rets, [r["hold"] for r in g])
    s["winrate"] = sum(1 for x in rets if x > 0) / len(rets)
    s["calmar"] = _calmar(s)
    return s


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    avg, _ma, _sl = build_breadth()
    btc = detlib.load_ohlcv("BTC", "1d")
    recs = []
    for label, direction, dm, om in PATS_ALL:
        if direction != "long":
            continue
        mod = importlib.import_module(dm)
        opp = importlib.import_module(om) if om else None
        for sym in detlib.SYMBOLS:
            if sym == "BTC":
                continue
            try:
                rows = mod.load_ohlcv(sym, "1d")
            except FileNotFoundError:
                continue
            os_ = set(opp.detect(rows)) if opp else set()
            for si in mod.detect(rows):
                d = rows[si]["date"]
                if d not in avg:
                    continue
                ret, hold = outcome_d(rows, si, direction, os_)
                rs = compute_rs(rows, btc, idx=si, symbol=sym)["rs_score"]
                if rs is None:
                    continue
                recs.append(dict(rs=rs, cap=avg[d], ret=ret, hold=hold, date=d))
    print(f"롱 신호 {len(recs)}건\n")

    # 통제 전(순진한 비교) — 참고
    hi0 = [r for r in recs if r["rs"] > RS_THR]
    lo0 = [r for r in recs if r["rs"] < RS_THR]
    print("=== 통제 전 (naive) ===")
    print(f"  rs>0.2 n={len(hi0)} mean={st.mean([r['ret'] for r in hi0])*100:+.2f}%")
    print(f"  rs<0.2 n={len(lo0)} mean={st.mean([r['ret'] for r in lo0])*100:+.2f}%")
    print(f"  차이 {(st.mean([r['ret'] for r in hi0])-st.mean([r['ret'] for r in lo0]))*100:+.2f}%p\n")

    # 시장 cap 3분위(bleed/중립/complacent)로 통제
    caps = sorted(r["cap"] for r in recs)
    c1, c2 = caps[len(caps)//3], caps[2*len(caps)//3]
    def bucket(c):
        return "bleed" if c <= c1 else ("complacent" if c > c2 else "중립")
    print(f"=== 레짐 통제 후 (cap 3분위: bleed≤{c1:+.2f}<중립≤{c2:+.2f}<complacent) ===")
    wins = 0
    all_hi, all_lo = [], []
    for bk in ("bleed", "중립", "complacent"):
        sub = [r for r in recs if bucket(r["cap"]) == bk]
        hi = [r for r in sub if r["rs"] > RS_THR]
        lo = [r for r in sub if r["rs"] < RS_THR]
        sh, sl = _s(hi), _s(lo)
        if not (sh and sl):
            continue
        all_hi += [r["ret"] for r in hi]; all_lo += [r["ret"] for r in lo]
        diff = sh["mean"] - sl["mean"]
        better = diff > 0
        wins += better
        print(f"  [{bk}] rs>0.2 n={sh['n']:>4} {sh['mean']*100:+.2f}%/wr{sh['winrate']*100:.0f}% | "
              f"rs<0.2 n={sl['n']:>4} {sl['mean']*100:+.2f}%/wr{sl['winrate']*100:.0f}% | "
              f"차이 {diff*100:+.2f}%p {'✓rs유리' if better else '✗'}")
    p = _welch_p(all_hi, all_lo)
    print(f"\n  통제 후 전체: rs>0.2 {st.mean(all_hi)*100:+.2f}% vs rs<0.2 {st.mean(all_lo)*100:+.2f}% "
          f"(차이 {(st.mean(all_hi)-st.mean(all_lo))*100:+.2f}%p, Welch p={p:.4f})")
    print(f"  cap구간 우위: {wins}/3")

    verdict = "유지(독립 엣지)" if (wins >= 3 and p < 0.10) else "폐기(레짐 중복)"
    print(f"\n>>> 판정: weak_rs {verdict}")
    return verdict


if __name__ == "__main__":
    main()
