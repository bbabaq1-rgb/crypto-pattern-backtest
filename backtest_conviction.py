"""
backtest_conviction.py — 오버레이 '곱셈' vs '종합점수' 사이징 검증.

질문: 현재 독립 곱셈 오버레이(grade×tf×rs×regime)가 이중 페널티를 내는가?
      종합 점수화가 out-of-sample로 실제 더 잘 순위화하는가?
사이징은 per-trade 평균을 안 바꾸므로, '오버레이 신호가 forward D수익을 순위화하는가'
(=고신뢰=고수익 정렬)로 평가. 롱 신호, look-ahead 없음.

검증 대상(연속·역사적 재현 가능한 판단신호):
  rs = 개별 종목 BTC 대비 상대강도(rs_score)
  cap = 시장 비대칭 레짐(진입일 유니버스 avg_cap; 낮을수록 롱 유리)
  (grade/tf는 4h·멀티TF 재구성 필요로 이 분석 범위 밖 — 별도 주석)
"""
import sys
import statistics as st

import detlib
from method_d import outcome_d, summ, _calmar
from method_e import PATS_ALL
from relative_strength import compute_rs
from backtest_regime_capture import build_breadth

import importlib


def _spearman(xs, ys):
    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0] * len(v)
        for rk, i in enumerate(order):
            r[i] = rk
        return r
    rx, ry = rank(xs), rank(ys)
    n = len(xs)
    mx, my = st.mean(rx), st.mean(ry)
    num = sum((rx[i]-mx)*(ry[i]-my) for i in range(n))
    den = (sum((rx[i]-mx)**2 for i in range(n))*sum((ry[i]-my)**2 for i in range(n)))**0.5
    return num/den if den else 0.0


def _s(g):
    if not g:
        return None
    rets = [r["ret"] for r in g]
    s = summ(rets, [r["hold"] for r in g])
    s["winrate"] = sum(1 for x in rets if x > 0)/len(rets)
    s["calmar"] = _calmar(s)
    return s


def _quint(recs, key, label):
    vals = sorted(r[key] for r in recs)
    qs = [vals[int(len(vals)*q)] for q in (0.2, 0.4, 0.6, 0.8)]
    bk = [[] for _ in range(5)]
    for r in recs:
        bk[sum(1 for q in qs if r[key] > q)].append(r)
    print(f"  [{label}] 5분위(낮음→높음 신뢰도)")
    monos = []
    for i, b in enumerate(bk):
        s = _s(b)
        if s:
            monos.append(s["mean"])
            print(f"    Q{i+1} n={s['n']:>4} mean={s['mean']*100:+.2f}% wr={s['winrate']*100:.0f}% Calmar={s['calmar']:.2f}")
    return monos


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    avg, _ma, _slope = build_breadth()
    btc = detlib.load_ohlcv("BTC", "1d")
    recs = []
    for label, direction, detmod, oppmod in PATS_ALL:
        if direction != "long":
            continue
        mod = importlib.import_module(detmod)
        opp = importlib.import_module(oppmod) if oppmod else None
        for sym in detlib.SYMBOLS:
            if sym == "BTC":
                continue
            try:
                rows = mod.load_ohlcv(sym, "1d")
            except FileNotFoundError:
                continue
            opp_set = set(opp.detect(rows)) if opp else set()
            for si in mod.detect(rows):
                d = rows[si]["date"]
                if d not in avg:
                    continue
                ret, hold = outcome_d(rows, si, direction, opp_set)
                rs = compute_rs(rows, btc, idx=si, symbol=sym)["rs_score"]
                recs.append(dict(rs=rs, cap=avg[d], ret=ret, hold=hold))
    print(f"롱 신호 {len(recs)}건\n")

    xs_rs = [r["rs"] for r in recs]; xs_cap = [r["cap"] for r in recs]; ys = [r["ret"] for r in recs]

    # 1) 두 신호 독립성 (상관 낮으면 곱셈 이중페널티 아님)
    corr = _spearman(xs_rs, xs_cap)
    print(f"=== (1) 신호 독립성: Spearman(rs, cap) = {corr:+.3f} "
          f"({'거의 독립' if abs(corr)<0.2 else '상관 있음(곱셈 이중페널티 우려)'}) ===\n")

    # 2) 개별 신호의 수익 순위력(Spearman)
    print("=== (2) 개별 신호 → forward D수익 순위상관 ===")
    print(f"  rs  vs 수익: {_spearman(xs_rs, ys):+.3f}   (높을수록 순위화 잘함)")
    print(f"  -cap vs 수익: {_spearman([-c for c in xs_cap], ys):+.3f}  (롱은 cap 낮을수록 유리)\n")

    # 3) 현재 '곱셈' 배수의 순위력 vs 종합점수의 순위력
    def mult(r):   # 현재 시스템 곱셈(롱): rs<0.2 → ×0.5, cap>0 → ×0.6
        m = 1.0
        if r["rs"] is not None and r["rs"] < 0.2:
            m *= 0.5
        if r["cap"] > 0:
            m *= 0.6
        return m
    def zscore(vals):
        m, s = st.mean(vals), (st.pstdev(vals) or 1.0)
        return [(v-m)/s for v in vals]
    zrs = zscore([r["rs"] if r["rs"] is not None else 0.0 for r in recs])
    zcap = zscore([-r["cap"] for r in recs])       # 롱 유리 방향(낮은 cap)
    for i, r in enumerate(recs):
        r["mult"] = mult(r)
        r["score"] = zrs[i] + zcap[i]              # 동일가중 종합점수(가중 미최적화)
    print("=== (3) 곱셈 배수 vs 종합점수 — 수익 순위상관 ===")
    print(f"  곱셈 배수  vs 수익: {_spearman([r['mult'] for r in recs], ys):+.3f}")
    print(f"  종합점수   vs 수익: {_spearman([r['score'] for r in recs], ys):+.3f}")

    print("\n=== (4) 종합점수 분위별 성과(단조성 확인) ===")
    _quint(recs, "score", "종합점수")

    print("\n=== (5) 곱셈 배수 구간별 성과(현행 사이징 보정도) ===")
    for m in (1.0, 0.6, 0.5, 0.3):
        g = [r for r in recs if abs(r["mult"]-m) < 1e-6]
        s = _s(g)
        if s:
            print(f"  배수 {m}: n={s['n']:>4} mean={s['mean']*100:+.2f}% wr={s['winrate']*100:.0f}%")


if __name__ == "__main__":
    main()
