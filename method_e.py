"""
method_e.py — 청산 방식E (Chandelier Exit) 백테스트.

방식E 청산:
  진입 후 최고가(롱)를 추적, 손절선 = 최고가 - ATR(22봉)*3.
  최고가 갱신 시 손절선도 따라 올라감(내려가진 않음). 숏은 대칭(최저가 + ATR*3).
  가격이 chandelier 선 터치(인트라바) 시 청산. 별도 익절 없음(트레일링이 익절 겸함).
  최대 60봉 타임스탑(시가 청산 — 방식D 관행과 동일).

기존 1d 검증 통과 신호(engulfing·fvg 롱/숏, inverted_hammer·marubozu 롱)에 소급 적용,
방식A/D와 gate_d() 동일 3축(기대값·MDD·Calmar)으로 비교.
게이트 동결 유지 — 판정 기준 변경 없음, 청산 방식만 교체.
"""
import json
import importlib
import statistics as st

import detlib
import baseline
from method_d import (outcome_a, outcome_d, summ, _calmar,
                      STOP_LOSS_PCT, FEE)

ATR_N    = 22
ATR_MULT = 3.0
MAX_HOLD_E = 60

# (라벨, 방향, detector, 반대detector[방식D용] — 없으면 None)
PATS_ALL = [
    ("engulfing",       "long",  "detector_engulfing",       "detector_engulfing_short"),
    ("fvg",             "long",  "detector_fvg",             "detector_fvg_short"),
    ("engulfing_short", "short", "detector_engulfing_short", "detector_engulfing"),
    ("fvg_short",       "short", "detector_fvg_short",       "detector_fvg"),
    ("inverted_hammer", "long",  "detector_inverted_hammer", None),
    ("marubozu",        "long",  "detector_marubozu",        "detector_marubozu_short"),
]


def atr_series(rows, n=ATR_N):
    """봉별 ATR(n) — TR 단순이동평균. 인덱스 i = i봉 종료 시점 ATR."""
    trs = [rows[0]["h"] - rows[0]["l"]]
    for i in range(1, len(rows)):
        pc = rows[i - 1]["c"]
        trs.append(max(rows[i]["h"] - rows[i]["l"],
                       abs(rows[i]["h"] - pc), abs(rows[i]["l"] - pc)))
    atr, s = [None] * len(rows), 0.0
    for i, tr in enumerate(trs):
        s += tr
        if i >= n:
            s -= trs[i - n]
            atr[i] = s / n
        elif i == n - 1:
            atr[i] = s / n
    return atr


def outcome_e(rows, si, direction, atr=None):
    """방식E 수익률. 반환 (ret, hold_bars)."""
    if atr is None:
        atr = atr_series(rows)
    base = rows[si]["c"]
    last = len(rows) - 1
    end = min(si + MAX_HOLD_E, last)
    if direction == "long":
        extreme = rows[si]["h"]
        stop = None
        for j in range(si + 1, end + 1):
            extreme = max(extreme, rows[j]["h"])
            a = atr[j] if atr[j] is not None else atr[si] or (rows[j]["h"] - rows[j]["l"])
            cand = extreme - ATR_MULT * a
            stop = cand if stop is None else max(stop, cand)
            if rows[j]["l"] <= stop:
                px = min(stop, rows[j]["o"])   # 갭하락 시 시가 체결(보수적)
                return (px - base) / base - FEE, j - si
        px = rows[end]["o"]
        return (px - base) / base - FEE, end - si
    else:
        extreme = rows[si]["l"]
        stop = None
        for j in range(si + 1, end + 1):
            extreme = min(extreme, rows[j]["l"])
            a = atr[j] if atr[j] is not None else atr[si] or (rows[j]["h"] - rows[j]["l"])
            cand = extreme + ATR_MULT * a
            stop = cand if stop is None else min(stop, cand)
            if rows[j]["h"] >= stop:
                px = max(stop, rows[j]["o"])   # 갭상승 시 시가 체결(보수적)
                return (base - px) / base - FEE, j - si
        px = rows[end]["o"]
        return (base - px) / base - FEE, end - si


def gate_vs(sBase, sNew, tag_base="D", tag_new="E"):
    """
    방식New vs 방식Base 3축 비교 (gate_d와 동일 축: 기대값·MDD·Calmar).
    채택: New.mean>0 AND calmar(New)>0 AND 우위 >= 2/3.
    '3축 전승' 여부(all_wins)도 함께 반환 — 페이퍼 병행 등재 기준.
    """
    cb, cn = _calmar(sBase), _calmar(sNew)
    wins = [sNew["mean"] > sBase["mean"],
            sNew["maxloss"] > sBase["maxloss"],
            cn > cb]
    n_wins = sum(wins)
    detail = (f"E[R] {tag_new}={sNew['mean']*100:+.2f}% {tag_base}={sBase['mean']*100:+.2f}%  "
              f"MDD {tag_new}={sNew['maxloss']*100:+.1f}% {tag_base}={sBase['maxloss']*100:+.1f}%  "
              f"Calmar {tag_new}={cn:.3f} {tag_base}={cb:.3f}  우위 {n_wins}/3")
    if sNew["mean"] <= 0:
        verdict = "reject"
    elif cn <= 0:
        verdict = "reject"
    elif n_wins >= 2:
        verdict = "adopt"
    else:
        verdict = "keep_base"
    return dict(verdict=verdict, wins=n_wins, all_wins=n_wins == 3, detail=detail)


def collect(method_fns, pats=PATS_ALL, tf="1d"):
    """
    패턴별 신호에 여러 방식 함수를 동시 적용.
    method_fns: {tag: fn(rows, si, direction, opp_set, atr) -> (ret, hold)}
    반환: {pattern_label: {tag: {"rets": [...], "holds": [...]}}, "_pooled": ...}
    """
    out = {}
    pooled = {t: {"rets": [], "holds": []} for t in method_fns}
    for label, direction, detmod, oppmod in pats:
        mod = importlib.import_module(detmod)
        opp = importlib.import_module(oppmod) if oppmod else None
        per = {t: {"rets": [], "holds": []} for t in method_fns}
        for sym in detlib.SYMBOLS:
            try:
                rows = mod.load_ohlcv(sym, tf)
            except FileNotFoundError:
                continue
            opp_set = set(opp.detect(rows)) if opp else set()
            atr = atr_series(rows)
            for si in mod.detect(rows):
                for tag, fn in method_fns.items():
                    r, h = fn(rows, si, direction, opp_set, atr)
                    per[tag]["rets"].append(r); per[tag]["holds"].append(h)
                    pooled[tag]["rets"].append(r); pooled[tag]["holds"].append(h)
        out[label] = per
    out["_pooled"] = pooled
    return out


METHOD_FNS = {
    "A": lambda rows, si, d, opp, atr: outcome_a(rows, si, d),
    "D": lambda rows, si, d, opp, atr: outcome_d(rows, si, d, opp),
    "E": lambda rows, si, d, opp, atr: outcome_e(rows, si, d, atr),
}


def winrate(rets):
    return sum(1 for r in rets if r > 0) / len(rets) if rets else 0.0


def print_table(data, tags):
    hdr = (f"  {'패턴':<17}{'방식':<4}{'n':>5}{'평균':>9}{'중앙':>9}"
           f"{'승률':>7}{'최대손실':>9}{'Calmar':>8}{'평균보유':>8}")
    print(hdr); print("  " + "-" * 78)
    rows_out = {}
    for label in [p[0] for p in PATS_ALL] + ["_pooled"]:
        if label not in data:
            continue
        rows_out[label] = {}
        for tag in tags:
            d = data[label][tag]
            s = summ(d["rets"], d["holds"])
            if not s:
                continue
            s["winrate"] = winrate(d["rets"])
            s["calmar"] = _calmar(s)
            rows_out[label][tag] = s
            nm = "전체(pooled)" if label == "_pooled" else label
            print(f"  {nm:<17}{tag:<4}{s['n']:>5}{s['mean']*100:>+8.2f}%{s['median']*100:>+8.2f}%"
                  f"{s['winrate']*100:>6.1f}%{s['maxloss']*100:>+8.1f}%{s['calmar']:>8.3f}{s['avghold']:>7.1f}")
        print()
    return rows_out


def main():
    print("=" * 88)
    print(f"청산방식 비교: A(±10%/20봉) vs D(-8%SL/반대·레짐/30봉) vs "
          f"E(Chandelier ATR{ATR_N}x{ATR_MULT:g}/{MAX_HOLD_E}봉)")
    print("=" * 88)
    data = collect(METHOD_FNS)
    stats = print_table(data, ["A", "D", "E"])

    # 게이트: E vs D (패턴별 + 풀)
    out = {}
    print("  [게이트] 방식E vs 방식D (3축: 기대값·MDD·Calmar)")
    for label, per in stats.items():
        if "D" not in per or "E" not in per:
            continue
        g = gate_vs(per["D"], per["E"], "D", "E")
        nm = "전체(pooled)" if label == "_pooled" else label
        mark = {"adopt": "O", "keep_base": "X", "reject": "X"}[g["verdict"]]
        print(f"    {nm:<17}{mark} {g['detail']}" + ("  [3축 전승]" if g["all_wins"] else ""))
        out[label] = dict(stats={t: {k: round(v, 5) for k, v in s.items()} for t, s in per.items()},
                          gate_e_vs_d=g)
    json.dump(out, open("method_e.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2, default=lambda x: round(float(x), 5))
    print("\n[저장] method_e.json")
    return out


if __name__ == "__main__":
    main()
