"""
backtest_rs.py — RS(BTC 대비 상대강도) 진입 필터 백테스트.

기존 1d 검증 신호(engulfing·fvg 롱/숏, inverted_hammer·marubozu 롱, 7종목)에
'진입 시점' rs_score(look-ahead 없음)를 붙여 그룹 비교:
  - 롱: rs_score>0 그룹 vs <0 그룹  (숏은 부호 반전 — 약한 놈을 숏)
  - 임계값 탐색: 0 / 0.2 / 0.5
청산은 실거래 방식D(outcome_d) 기준. 지표: n·기대값·중앙·승률·MDD·Calmar + Welch t.
게이트 동결 — 판정 기준 신설 없음. 필터 채택 조건(사전 고정):
  유리군이 불리군 대비 mean·Calmar 모두 우위 AND 유리군 n>=100 (표본 방어).
BTC 신호는 rs=0 기준점이라 그룹 비교에서 제외.
"""
import sys
import json
import statistics as st
from math import sqrt, erf

import detlib
from method_d import outcome_d, summ, _calmar
from method_e import PATS_ALL
from relative_strength import compute_rs

import importlib


def _welch_p(x, y):
    if len(x) < 2 or len(y) < 2:
        return 1.0
    mx, my = st.mean(x), st.mean(y)
    vx, vy = st.variance(x), st.variance(y)
    se = sqrt(vx / len(x) + vy / len(y))
    if se == 0:
        return 1.0
    t = (mx - my) / se
    df = max(2, min(len(x), len(y)) - 1)
    z = abs(t) / sqrt(1 + t * t / df)
    return 2 * (1 - 0.5 * (1 + erf(z / sqrt(2))))


def collect_records():
    """신호별 (pattern, direction, rs_score, ret_D, hold) 레코드 수집."""
    btc = detlib.load_ohlcv("BTC", "1d")
    recs = []
    for label, direction, detmod, oppmod in PATS_ALL:
        mod = importlib.import_module(detmod)
        opp = importlib.import_module(oppmod) if oppmod else None
        for sym in detlib.SYMBOLS:
            try:
                rows = mod.load_ohlcv(sym, "1d")
            except FileNotFoundError:
                continue
            opp_set = set(opp.detect(rows)) if opp else set()
            for si in mod.detect(rows):
                ret, hold = outcome_d(rows, si, direction, opp_set)
                rs = (None if sym == "BTC"
                      else compute_rs(rows, btc, idx=si, symbol=sym)["rs_score"])
                recs.append(dict(pattern=label, direction=direction, symbol=sym,
                                 rs=rs, ret=ret, hold=hold))
    return recs


def _stats(rets, holds):
    s = summ(rets, holds)
    if not s:
        return None
    s["winrate"] = sum(1 for r in rets if r > 0) / len(rets)
    s["calmar"] = _calmar(s)
    return s


def group_table(recs, thr):
    """
    임계값 thr 기준 유리/불리 그룹.
    롱: rs> thr 유리 / rs<-thr 불리(경계 중립 제외).  숏: 부호 반전.
    """
    fav, unf = [], []
    for r in recs:
        if r["rs"] is None:
            continue
        adv = r["rs"] if r["direction"] == "long" else -r["rs"]
        if adv > thr:
            fav.append(r)
        elif adv < -thr:
            unf.append(r)
    return fav, unf


def print_group(tag, s):
    print(f"    {tag:<14} n={s['n']:>5} mean={s['mean']*100:+.2f}% "
          f"med={s['median']*100:+.2f}% wr={s['winrate']*100:.1f}% "
          f"MDD={s['maxloss']*100:+.1f}% Calmar={s['calmar']:.3f}")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    print("RS 필터 백테스트 — 방식D 청산, 진입시점 rs_score(look-ahead 없음)")
    recs = collect_records()
    n_btc = sum(1 for r in recs if r["rs"] is None)
    print(f"신호 {len(recs)}건 (BTC 제외 {len(recs)-n_btc}건이 그룹 대상)\n")

    out = {}
    for thr in (0.0, 0.2, 0.5):
        fav, unf = group_table(recs, thr)
        print(f"[임계값 |rs| > {thr}]  (방향 유리 = 롱·rs>{thr} / 숏·rs<-{thr})")
        sf = _stats([r["ret"] for r in fav], [r["hold"] for r in fav]) if fav else None
        su = _stats([r["ret"] for r in unf], [r["hold"] for r in unf]) if unf else None
        if sf: print_group("RS 유리군", sf)
        if su: print_group("RS 불리군", su)
        if sf and su:
            p = _welch_p([r["ret"] for r in fav], [r["ret"] for r in unf])
            edge = sf["mean"] - su["mean"]
            print(f"    차이 {edge*100:+.2f}%p  Welch p={p:.4f}")
            out[thr] = dict(fav={k: round(float(v), 5) for k, v in sf.items()},
                            unf={k: round(float(v), 5) for k, v in su.items()},
                            diff=round(edge, 5), p=round(p, 5))
        print()

    # 방향별 분해 (thr=0)
    print("[방향별 분해 — thr=0]")
    for d in ("long", "short"):
        sub = [r for r in recs if r["direction"] == d and r["rs"] is not None]
        adv_pos = [r for r in sub if (r["rs"] if d == "long" else -r["rs"]) > 0]
        adv_neg = [r for r in sub if (r["rs"] if d == "long" else -r["rs"]) < 0]
        for tag, g in ((f"{d} RS유리", adv_pos), (f"{d} RS불리", adv_neg)):
            s = _stats([r["ret"] for r in g], [r["hold"] for r in g]) if g else None
            if s: print_group(tag, s)
    # 패턴별 분해 (thr=0)
    print("\n[패턴별 분해 — thr=0, 유리 vs 불리 mean]")
    pats = sorted({r["pattern"] for r in recs})
    for p_ in pats:
        sub = [r for r in recs if r["pattern"] == p_ and r["rs"] is not None]
        fav = [r["ret"] for r in sub if (r["rs"] if r["direction"] == "long" else -r["rs"]) > 0]
        unf = [r["ret"] for r in sub if (r["rs"] if r["direction"] == "long" else -r["rs"]) < 0]
        if fav and unf:
            print(f"    {p_:<17} 유리 n={len(fav):>4} {st.mean(fav)*100:+.2f}%  |  "
                  f"불리 n={len(unf):>4} {st.mean(unf)*100:+.2f}%")

    json.dump(out, open("backtest_rs.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print("\n[저장] backtest_rs.json")
    return out


if __name__ == "__main__":
    main()
