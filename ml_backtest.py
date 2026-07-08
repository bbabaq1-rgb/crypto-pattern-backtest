"""
ml_backtest.py — 패턴신호 메타필터(GBM)의 워크포워드 검증.

규율:
  - 워크포워드(확장윈도우): 과거로 학습→미래 예측, 미래 데이터 절대 미사용.
  - 셔플 대조군: 라벨 셔플로 재학습 → 엣지가 나오면 방법론 누수(자기기만) 경보.
  - 베이스라인(전 신호 방식D)을 OOS에서 이겨야만 의미. 못 이기면 정직히 기각.
모델: sklearn HistGradientBoostingRegressor(방식D 수익 회귀), 소표본이라 강한 규제.
라이브 미연결 — 순수 연구.
"""
import sys
import statistics as st
import random

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor

from ml_features import build_dataset, FEATURE_NAMES

SEED = 42
INIT_FRAC = 0.45      # 초기 학습 비율
N_FOLDS   = 6         # 이후 구간을 6개 폴드로 롤포워드


def _model():
    return HistGradientBoostingRegressor(
        loss="squared_error", learning_rate=0.03, max_iter=250,
        max_depth=3, min_samples_leaf=40, l2_regularization=1.0,
        max_leaf_nodes=8, random_state=SEED)


def walk_forward(X, y, dates_order, shuffle=False):
    """확장윈도우 OOS 예측 반환: pred[list], idx_oos[list] (원본 인덱스)."""
    n = len(X)
    order = dates_order                       # 날짜 오름차순 인덱스
    Xo = X[order]; yo = np.array(y)[order]
    if shuffle:
        ys = yo.copy(); rng = np.random.default_rng(SEED); rng.shuffle(ys); yo = ys
    init = int(n * INIT_FRAC)
    step = (n - init) // N_FOLDS
    preds = np.full(n, np.nan)
    for f in range(N_FOLDS):
        tr_end = init + f * step
        te_end = n if f == N_FOLDS - 1 else init + (f + 1) * step
        m = _model()
        m.fit(Xo[:tr_end], yo[:tr_end])
        preds[tr_end:te_end] = m.predict(Xo[tr_end:te_end])
    mask = ~np.isnan(preds)
    return preds[mask], order[mask]


def _stats(rets):
    if len(rets) == 0:
        return None
    mean = float(np.mean(rets)); mx = float(np.min(rets))
    wr = float(np.mean([1 if r > 0 else 0 for r in rets]))
    calmar = mean / abs(mx) if mx < 0 else float("inf")
    return dict(n=len(rets), mean=mean, wr=wr, maxloss=mx, calmar=calmar)


def _pr(tag, s):
    if s:
        print(f"    {tag:<22} n={s['n']:>4} mean={s['mean']*100:+.2f}% "
              f"wr={s['wr']*100:.1f}% MDD={s['maxloss']*100:+.1f}% Calmar={s['calmar']:.2f}")


def _spearman(a, b):
    ra = np.argsort(np.argsort(a)); rb = np.argsort(np.argsort(b))
    return float(np.corrcoef(ra, rb)[0, 1])


def evaluate(name, X, y, dates_order, meta, shuffle=False):
    preds, idx = walk_forward(X, y, dates_order, shuffle=shuffle)
    actual = np.array(y)[idx]
    print(f"\n=== {name} (OOS {len(idx)}건) ===")
    base = _stats(actual)
    _pr("베이스라인(전체)", base)
    # 예측 상·하위 절반
    med = np.median(preds)
    top = actual[preds > med]; bot = actual[preds <= med]
    _pr("모델 상위50%", _stats(top)); _pr("모델 하위50%", _stats(bot))
    # 예측>0 (수익 예측分만 진입)
    sel = actual[preds > 0]
    _pr("모델 진입(pred>0)", _stats(sel))
    print(f"    순위상관 Spearman(pred, actual) = {_spearman(preds, actual):+.3f}")
    # 상위50%가 베이스라인·하위50% 이기는지
    st_top, st_bot = _stats(top), _stats(bot)
    edge = (st_top["mean"] - st_bot["mean"]) if (st_top and st_bot) else 0
    print(f"    상위-하위 차이 {edge*100:+.2f}%p")
    return dict(base=base, top=_stats(top), bot=_stats(bot), sel=_stats(sel),
                spearman=_spearman(preds, actual), edge=edge, n=len(idx),
                preds=preds, actual=actual, idx=idx)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    random.seed(SEED); np.random.seed(SEED)
    Xl, yr, yb, meta = build_dataset()
    X = np.array(Xl, dtype=float); y = np.array(yr, dtype=float)
    dates = [m["date"] for m in meta]
    order = np.array(sorted(range(len(dates)), key=lambda i: dates[i]))
    print(f"샘플 {len(X)}, 특징 {X.shape[1]}, 기간 {min(dates)}~{max(dates)}")

    real = evaluate("실제 라벨", X, y, order, meta, shuffle=False)
    null = evaluate("셔플 대조군(엣지 나오면 누수경보)", X, y, order, meta, shuffle=True)

    # 특징 중요도(전체 적합, 순열 중요도)
    print("\n=== 특징 중요도(permutation, 상위 10) ===")
    from sklearn.inspection import permutation_importance
    m = _model(); m.fit(X, y)
    r = permutation_importance(m, X, y, n_repeats=8, random_state=SEED,
                               scoring="neg_mean_squared_error")
    imp = sorted(zip(FEATURE_NAMES, r.importances_mean), key=lambda x: -x[1])[:10]
    for name, v in imp:
        print(f"    {name:<16} {v:.5f}")

    # 판정
    print("\n" + "=" * 60)
    print("판정 (사전 고정 기준):")
    ok_edge  = real["edge"] > 0 and real["top"]["mean"] > real["base"]["mean"]
    ok_calmar = real["top"]["calmar"] > real["base"]["calmar"]
    ok_null  = abs(null["edge"]) < real["edge"] * 0.5 if real["edge"] > 0 else True
    ok_spear = real["spearman"] > 0.05 and real["spearman"] > 2 * abs(null["spearman"])
    print(f"  1) 모델 상위50% > 베이스라인 mean: {ok_edge} "
          f"({real['top']['mean']*100:+.2f}% vs {real['base']['mean']*100:+.2f}%)")
    print(f"  2) 상위50% Calmar > 베이스라인:    {ok_calmar}")
    print(f"  3) 셔플 대조군 엣지 미미(누수 없음): {ok_null} "
          f"(실제 {real['edge']*100:+.2f}%p vs 셔플 {null['edge']*100:+.2f}%p)")
    print(f"  4) 순위상관 실제>>셔플:            {ok_spear} "
          f"({real['spearman']:+.3f} vs {null['spearman']:+.3f})")
    passed = ok_edge and ok_calmar and ok_null and ok_spear
    print(f"\n  >>> {'채택 후보(추가검증 필요)' if passed else '기각 — OOS 엣지 불충분'}")


if __name__ == "__main__":
    main()
