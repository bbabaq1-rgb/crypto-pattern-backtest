"""업비트 일봉 특성 — study_upbit_shooting.features() 와 같은 정의의 롤링 구현.

**참조 구현은 study_upbit_shooting.features() 이고 이 모듈은 그것을 다시 쓴 것이다.**
정의가 한 줄이라도 갈리면 시험 수치 전부가 무의미하므로 test_upbit_shoot §1 이
합성 봉 + 실데이터에서 두 구현의 **모든 키 일치**(부동소수 허용오차 1e-9)를 고정한다.

왜 다시 쓰나: 참조 구현은 봉마다 볼밴 백분위를 120×20 재계산해 코인-일 35만 건에서
8억 연산이 된다. 사전 등록 시험은 여러 해·전 종목을 돌아야 하므로 롤링이 필요하다.
바꾼 것은 **계산 순서뿐이고 정의는 아니다** — 창 길이·경계·가드를 참조와 한 줄씩 맞췄다.
"""
import statistics as st
from collections import deque

MIN_HIST = 60
MAS = (5, 20, 60, 120, 180)
THR = 0.50          # shoots60 집계 문턱 — 참조 구현의 THR 과 같아야 한다


def _win_sum(xs, w):
    """out[i] = sum(xs[i-w+1 : i+1]) — 참조와 **같은 덧셈 순서**(슬라이스 합). None if i+1 < w.

    누적합을 굴리면 뺄셈 드리프트로 마지막 비트가 어긋나고, 그 한 비트가
    `c > ma` 나 `p < bbw` 같은 경계 비교를 뒤집는다(실측: n_ma_above 3↔4).
    창이 짧아 비용 차이가 작으므로 정의 일치를 택한다.
    """
    return [(sum(xs[i - w + 1:i + 1]) if i + 1 >= w else None) for i in range(len(xs))]


def _roll_sum(xs, w):
    """out[i] = sum(xs[i-w+1 : i+1]) — 정수 카운트 전용(드리프트 없음)."""
    out, s = [None] * len(xs), 0.0
    for i, x in enumerate(xs):
        s += x
        if i >= w:
            s -= xs[i - w]
        out[i] = s if i + 1 >= w else None
    return out


def _roll_ext(xs, back, is_max):
    """out[i] = max/min(xs[max(0, i-back) : i+1]) — 단조 덱."""
    out, dq = [None] * len(xs), deque()
    for i, x in enumerate(xs):
        while dq and ((xs[dq[-1]] <= x) if is_max else (xs[dq[-1]] >= x)):
            dq.pop()
        dq.append(i)
        while dq[0] < i - back:
            dq.popleft()
        out[i] = xs[dq[0]]
    return out


def compute(rows):
    """rows(오름차순 일봉) → 인덱스별 특성 dict 목록. i < MIN_HIST 는 None."""
    n = len(rows)
    out = [None] * n
    if n <= MIN_HIST:
        return out
    cl = [r["c"] for r in rows]
    hi = [r["h"] for r in rows]
    lo = [r["l"] for r in rows]
    vol = [r["v"] for r in rows]
    krw = [r["krw"] for r in rows]

    ma = {}
    for w in MAS:
        s = _win_sum(cl, w)
        ma[w] = [(x / w if x is not None else None) for x in s]
    # 볼밴 폭 — 참조와 같은 st.pstdev(cl[i-19:i+1]) 를 그대로 쓴다(O(20)).
    # 아낀 것은 백분위 쪽: 참조는 과거 120봉마다 pstdev 를 다시 돌린다.
    bbw = [None] * n
    for i in range(19, n):
        m = ma[20][i]
        if m:
            bbw[i] = 4 * st.pstdev(cl[i - 19:i + 1]) / m
    # ATR14: TR[i] = max(h-l, |h-c_prev|, |l-c_prev|), atr(i) = mean(TR[i-13..i])
    tr = [0.0] * n
    for i in range(1, n):
        p = cl[i - 1]
        tr[i] = max(hi[i] - lo[i], abs(hi[i] - p), abs(lo[i] - p))
    tr_s = _win_sum(tr, 14)
    # RSI14: i-13..i 의 일간 차분
    gain, loss = [0.0] * n, [0.0] * n
    for i in range(1, n):
        d = cl[i] - cl[i - 1]
        gain[i], loss[i] = max(d, 0.0), max(-d, 0.0)
    g_s, l_s = _win_sum(gain, 14), _win_sum(loss, 14)
    # 극값 창 — 참조 구현의 슬라이스 길이를 그대로 맞춘다
    hi120 = _roll_ext(hi, 120, True)      # rows[max(0,i-120):i+1]
    lo60 = _roll_ext(lo, 60, False)       # rows[i-60:i+1]
    hi250 = _roll_ext(hi, 250, True)      # rows[max(0,i-250):i+1]
    hi20 = _roll_ext(hi, 19, True)        # rows[i-19:i+1]
    lo20 = _roll_ext(lo, 19, False)
    rng7 = _roll_ext([h - l for h, l in zip(hi, lo)], 6, False)   # rows[i-6:i+1]
    # 연속 봉 — 참조의 역방향 루프와 같은 값을 주는 전방 점화식
    streak, sgn = [0] * n, [0] * n
    for i in range(1, n):
        d = cl[i] - cl[i - 1]
        s = 0 if d == 0 else (1 if d > 0 else -1)
        sgn[i] = s
        if s == 0:
            streak[i] = 0
        elif sgn[i - 1] == s:
            streak[i] = streak[i - 1] + s
        else:
            streak[i] = s
    # 슈팅·대형일 카운트 (창 61봉 = 참조의 range(max(1,i-60), i+1))
    big, shoot = [0] * n, [0] * n
    for i in range(1, n):
        r = cl[i] / cl[i - 1] - 1
        big[i] = 1 if r >= 0.20 else 0
        shoot[i] = 1 if r >= THR else 0
    big_s, shoot_s = _roll_sum(big, 61), _roll_sum(shoot, 61)

    for i in range(MIN_HIST, n):
        c, r = cl[i], rows[i]
        f = {}
        for w in MAS:
            f[f"dist_ma{w}"] = (c / ma[w][i] - 1) if ma[w][i] else None
        avail = [w for w in MAS if ma[w][i]]
        f["n_ma_above"] = sum(1 for w in avail if c > ma[w][i])
        f["n_ma_avail"] = len(avail)
        f["ma_aligned_bull"] = int(len(avail) >= 3 and all(ma[a][i] > ma[b][i] for a, b in zip(avail, avail[1:])))
        f["ma_aligned_bear"] = int(len(avail) >= 3 and all(ma[a][i] < ma[b][i] for a, b in zip(avail, avail[1:])))
        m20p = ma[20][i - 20] if i >= 40 else None
        f["ma20_slope20"] = (ma[20][i] / m20p - 1) if (ma[20][i] and m20p) else None
        m60p = ma[60][i - 20] if i >= 80 else None
        f["ma60_slope20"] = (ma[60][i] / m60p - 1) if (ma[60][i] and m60p) else None
        v20 = sum(vol[i - 20:i]) / 20
        f["vol_ratio20"] = vol[i] / v20 if v20 else None
        f["vol_ratio20_prev5"] = (sum(vol[i - 4:i + 1]) / 5) / v20 if v20 else None
        f["turnover20_krw"] = sum(krw[i - 20:i + 1]) / 21
        f["ret5"] = c / cl[i - 5] - 1
        f["ret20"] = c / cl[i - 20] - 1
        f["ret60"] = c / cl[i - 60] - 1
        f["dd_120h"] = c / hi120[i] - 1
        f["from_60lo"] = c / lo60[i] - 1
        f["dd_250h"] = c / hi250[i] - 1
        a = tr_s[i] / 14 if i >= 14 else None
        f["atr14_pct"] = a / c if a else None
        f["range20_pct"] = (hi20[i] - lo20[i]) / c
        f["bb_width"] = bbw[i]
        pool = [x for x in bbw[max(20, i - 120):i] if x is not None]
        f["bb_width_pctile120"] = (sum(1 for p in pool if p < bbw[i]) / len(pool)) if (bbw[i] and pool) else None
        f["rsi14"] = (100.0 if l_s[i] == 0 else 100 - 100 / (1 + g_s[i] / l_s[i])) if i >= 14 else None
        f["streak"] = streak[i]
        rg = r["h"] - r["l"]
        f["body_pct"] = abs(r["c"] - r["o"]) / rg if rg else 0
        f["upper_wick_pct"] = (r["h"] - max(r["o"], r["c"])) / rg if rg else 0
        f["lower_wick_pct"] = (min(r["o"], r["c"]) - r["l"]) / rg if rg else 0
        f["bull_candle"] = int(r["c"] > r["o"])
        f["day_ret"] = c / cl[i - 1] - 1
        p = rows[i - 1]
        f["inside_bar"] = int(r["h"] <= p["h"] and r["l"] >= p["l"])
        f["nr7"] = int(rg <= rng7[i])
        f["engulf_bull"] = int(r["c"] > r["o"] and p["c"] < p["o"] and r["c"] >= p["o"] and r["o"] <= p["c"])
        f["hammer"] = int(rg > 0 and f["lower_wick_pct"] >= 0.6 and f["body_pct"] <= 0.3)
        f["doji"] = int(rg > 0 and f["body_pct"] <= 0.1)
        f["bars_hist"] = i
        f["shoots60"] = int(shoot_s[i]) if shoot_s[i] is not None else sum(shoot[max(1, i - 60):i + 1])
        f["big_days60"] = int(big_s[i]) if big_s[i] is not None else sum(big[max(1, i - 60):i + 1])
        out[i] = f
    return out
