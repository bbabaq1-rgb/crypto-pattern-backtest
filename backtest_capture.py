"""
backtest_capture.py — 상승/하락 비대칭 포착(cap_score) 엣지 검증.

핵심 질문 2가지:
  (1) cap_score 자체가 방식D 수익을 가르는가? (rs_score와 같은 방식)
  (2) cap_score가 rs_score에 '추가' 엣지를 주는가? (rs 유리군 안에서 재분리)
      → 추가 가치가 없으면 rs와 중복이므로 채택 안 함.
게이트 동결: 새 판정기준 없음. 채택 조건(사전 고정) — 롱에서 유리군이 불리군 대비
mean·Calmar 동시 우위 AND 유리군 n>=100 AND rs 통제 후에도 우위 유지.
진입시점 지표(look-ahead 없음), 방식D 청산.
"""
import sys
import json
import statistics as st

import detlib
from method_d import outcome_d, summ, _calmar
from method_e import PATS_ALL
from relative_strength import compute_rs, compute_capture
from backtest_rs import _welch_p

import importlib


def collect():
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
                if sym == "BTC":
                    rs = cap = None
                else:
                    rs = compute_rs(rows, btc, idx=si, symbol=sym)["rs_score"]
                    cap = compute_capture(rows, btc, idx=si, symbol=sym)["cap_score"]
                recs.append(dict(pattern=label, direction=direction, symbol=sym,
                                 rs=rs, cap=cap, ret=ret, hold=hold))
    return recs


def _stats(g):
    rets = [r["ret"] for r in g]; holds = [r["hold"] for r in g]
    s = summ(rets, holds)
    if not s:
        return None
    s["winrate"] = sum(1 for x in rets if x > 0) / len(rets)
    s["calmar"] = _calmar(s)
    return s


def _pr(tag, s):
    print(f"    {tag:<22} n={s['n']:>5} mean={s['mean']*100:+.2f}% "
          f"med={s['median']*100:+.2f}% wr={s['winrate']*100:.1f}% "
          f"Calmar={s['calmar']:.3f}")


def _compare(name, group, thr, key="cap"):
    """방향-부호 조정 유리/불리 비교. 롱: key>thr 유리 / 숏: -key>thr 유리."""
    fav, unf = [], []
    for r in group:
        v = r.get(key)
        if v is None:
            continue
        adv = v if r["direction"] == "long" else -v
        if adv > thr:
            fav.append(r)
        elif adv < -thr:
            unf.append(r)
    sf, su = (_stats(fav) if fav else None), (_stats(unf) if unf else None)
    print(f"  [{name}] {key}>|{thr}|")
    if sf: _pr("유리군", sf)
    if su: _pr("불리군", su)
    if sf and su:
        p = _welch_p([r["ret"] for r in fav], [r["ret"] for r in unf])
        print(f"    차이 {(sf['mean']-su['mean'])*100:+.2f}%p  Welch p={p:.4f}")
    return sf, su


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    print("cap_score(상승/하락 비대칭) 백테스트 — 방식D, look-ahead 없음\n")
    recs = collect()
    longs = [r for r in recs if r["direction"] == "long" and r["cap"] is not None]
    shorts = [r for r in recs if r["direction"] == "short" and r["cap"] is not None]
    print(f"롱 {len(longs)}건 / 숏 {len(shorts)}건 (BTC 제외)\n")

    # (1) cap 단독 엣지
    print("=== (1) cap_score 단독 ===")
    for thr in (0.0, 0.15, 0.3):
        _compare(f"전체 thr={thr}", recs, thr, "cap")
    print("\n  방향 분해(thr=0):")
    _compare("롱만", longs, 0.0, "cap")
    _compare("숏만", shorts, 0.0, "cap")

    # (2) rs 통제 후 cap 추가 엣지 — rs>0.2 롱(=이미 필터 통과분) 안에서 cap 재분리
    print("\n=== (2) rs 통제 후 cap 추가엣지 (rs>0.2 롱 내부) ===")
    rs_pass = [r for r in longs if r["rs"] is not None and r["rs"] > 0.2]
    print(f"  대상: rs>0.2 롱 {len(rs_pass)}건")
    hi = [r for r in rs_pass if r["cap"] > 0]
    lo = [r for r in rs_pass if r["cap"] <= 0]
    for tag, g in (("  rs>0.2 & cap>0", hi), ("  rs>0.2 & cap<=0", lo)):
        s = _stats(g)
        if s: _pr(tag, s)
    if hi and lo:
        p = _welch_p([r["ret"] for r in hi], [r["ret"] for r in lo])
        print(f"    추가엣지 {(st.mean([r['ret'] for r in hi])-st.mean([r['ret'] for r in lo]))*100:+.2f}%p  p={p:.4f}")

    # (3) rs vs cap vs 결합(둘 다 양수) — 롱
    print("\n=== (3) 롱 필터 비교 ===")
    base = _stats(longs)
    if base: _pr("무필터(전체 롱)", base)
    for tag, cond in (
        ("rs>0.2",            lambda r: r["rs"] is not None and r["rs"] > 0.2),
        ("cap>0",             lambda r: r["cap"] > 0),
        ("rs>0.2 & cap>0",    lambda r: r["rs"] is not None and r["rs"] > 0.2 and r["cap"] > 0),
        ("rs>0.2 OR cap>0.15", lambda r: (r["rs"] is not None and r["rs"] > 0.2) or r["cap"] > 0.15),
    ):
        s = _stats([r for r in longs if cond(r)])
        if s: _pr(tag, s)

    json.dump({"n_long": len(longs), "n_short": len(shorts)},
              open("backtest_capture.json", "w"), ensure_ascii=False)
    return recs


if __name__ == "__main__":
    main()
