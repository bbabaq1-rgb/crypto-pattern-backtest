"""
baseline.py — 무작위 진입 베이스라인 + 유의성 검정.

목적: 패턴의 기대값이 '상승장 편승(드리프트)'을 넘는 진짜 엣지인지 검증.
  동일 종목·기간·타임프레임에서, 동일 트리플배리어(±10%/20봉/수수료)로
  '무작위 시점 진입'의 수익 풀을 만든 뒤, 크기 n의 표본평균/중앙값 null 분포를
  부트스트랩(B회)해서 패턴의 mean/median 이 상위 5% 안인지(p<0.05) 본다.

핵심: 풀에는 드리프트가 그대로 들어있으므로, 이를 유의하게 넘어야 '타이밍 엣지'.
"""
import random
import statistics as st

RISE, FALL, WINDOW, FEE = 0.10, -0.10, 20, 0.002
B_DEFAULT = 1000
ALPHA = 0.05


def _outcome(rows, si):
    base = rows[si]["c"]
    up, dn = base * (1 + RISE), base * (1 + FALL)
    hi = min(si + WINDOW, len(rows) - 1)
    for j in range(si + 1, hi + 1):
        if rows[j]["c"] >= up:
            return rows[j]["c"] / base - 1 - FEE
        if rows[j]["c"] <= dn:
            return rows[j]["c"] / base - 1 - FEE
    return rows[hi]["c"] / base - 1 - FEE


def entry_pool(mod, tf, date_from=None, date_to=None):
    """
    모든 봉을 무작위 진입 후보로 보고 트리플배리어 수익 풀 구성.
    mod.outcome 를 사용하므로 롱/숏 방향이 자동 정합(숏 패턴이면 숏 베이스라인).
    """
    pool = []
    oc = getattr(mod, "outcome", None)
    for sym in mod.SYMBOLS:
        try:
            rows = mod.load_ohlcv(sym, tf)
        except FileNotFoundError:
            continue
        for i in range(len(rows) - 1):
            d = rows[i]["date"]
            if date_from and d < date_from:
                continue
            if date_to and d > date_to:
                continue
            if oc is not None:
                pool.append(oc(rows, i)[1])
            else:
                pool.append(_outcome(rows, i))
    return pool


def test(pool, obs_mean, obs_median, n, B=B_DEFAULT, seed=42):
    """크기 n 무작위표본의 평균/중앙 null 분포 대비 관측치의 p값."""
    if not pool or n <= 0:
        return None
    rnd = random.Random(seed)
    means, meds = [], []
    for _ in range(B):
        samp = [pool[rnd.randrange(len(pool))] for _ in range(n)]
        means.append(st.mean(samp))
        meds.append(st.median(samp))
    p_mean = sum(1 for m in means if m >= obs_mean) / B
    p_med = sum(1 for m in meds if m >= obs_median) / B
    return dict(
        pool_mean=st.mean(pool), pool_median=st.median(pool),
        null_mean=st.mean(means), null_median=st.mean(meds),
        p_mean=p_mean, p_median=p_med,
        excess_mean=obs_mean - st.mean(means),
        excess_median=obs_median - st.mean(meds),
        significant=(p_mean < ALPHA),
    )
