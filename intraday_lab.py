"""
intraday_lab.py — ≤1h 단타 연구 공용 프레임 (라벨/게이트/베이스라인).

기존 detlib 라벨(±10% 트리플배리어 / 20봉 / 수수료 0.2%)은 1d 기준으로 동결된
것이라 하위 TF에서 구조적으로 엣지를 탐지하지 못한다:
  - 15m에서 20봉 = 5시간, ±10%는 사실상 도달 불가 -> 전부 시간초과 청산.
    측정값이 '5시간 뒤 랜덤수익 - 수수료'가 되어 mean이 항상 -0.2% 근처로 수렴.
    (2026-08-29 실측: triple_bottom 15m mean -0.234%, triple_top -0.279%)
  - 기각된 1h 패턴 14종의 총수익(net+fee)은 0.1~0.3%로, 왕복 수수료 0.2%가
    그 대부분을 잠식. 통과한 harmonic 2종만 건당 1.5%+ (수수료 비중 11%).

따라서 하위 TF 연구는 다음을 쓴다:
  1) 배리어를 ±k x ATR(14) 로 (가격 변동성 비례, TF 무관 동일 의미)
  2) 보유 한도를 TF별 실제 시간으로 (1h 12봉=12시간, 15m 16봉=4시간)
  3) 게이트에 '수수료 마진' 기준 추가: 순수익 mean > 왕복 수수료
     (= 총수익이 수수료의 2배 이상) — 마찰을 여유 있게 넘는 신호만 채택

동결 게이트(n>=20, mean>0, median>0, boot_p<0.05, OOS 2/4+)는 그대로 병기해
기존 패턴들과 비교 가능하게 남긴다. 라벨 변경은 '하위 TF 연구 전용'이며
1d/4h/1w 기존 등재 패턴의 판정에는 영향을 주지 않는다.
"""
import csv
import glob
import json
import os
import random
import statistics
from datetime import datetime, timezone
from math import erf, sqrt

FEE = 0.002              # 왕복 수수료 0.2% (레포 동결값, 슬리피지 포함 보수적)
FEE_REALISTIC = 0.001    # OKX taker 0.05% x2 — 참고용 병기
K_ATR = 1.5              # 배리어 = 진입가 ± K_ATR x ATR14
HORIZON = {"15m": 16, "1h": 12, "4h": 12}   # 15m 4시간 / 1h 12시간
BOOT_N = 1000
SEED = 42

CSV = lambda s, tf: f"data/{s.lower()}_{tf}.csv"


# ── 로더 (타임스탬프 보존 — 횡단면 정렬·시간대 분석에 필수) ──────────────────
def load_raw(sym, tf):
    """[{ts(ms), dt(UTC), date, hour, o,h,l,c,v}] — detlib은 date만 남겨 1h 정렬 불가."""
    rows = []
    with open(CSV(sym, tf), newline="") as f:
        for r in csv.DictReader(f):
            ts = int(float(r["timestamp"]))
            dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
            rows.append(dict(ts=ts, dt=dt, date=dt.strftime("%Y-%m-%d"),
                             hour=dt.hour, o=float(r["open"]), h=float(r["high"]),
                             l=float(r["low"]), c=float(r["close"]),
                             v=float(r["volume"])))
    rows.sort(key=lambda r: r["ts"])
    return rows


def symbols_with(tf):
    return sorted({os.path.basename(f)[: -len(f"_{tf}.csv")].upper()
                   for f in glob.glob(f"data/*_{tf}.csv")})


# ── ATR ─────────────────────────────────────────────────────────────────────
def atr_series(rows, period=14):
    """각 인덱스의 ATR(단순평균). period 미만은 None."""
    out = [None] * len(rows)
    trs = []
    for i in range(1, len(rows)):
        hi, lo, pc = rows[i]["h"], rows[i]["l"], rows[i - 1]["c"]
        trs.append(max(hi - lo, abs(hi - pc), abs(lo - pc)))
        if len(trs) >= period:
            out[i] = sum(trs[-period:]) / period
    return out


# ── 라벨: ATR 배리어 + TF별 보유한도 ────────────────────────────────────────
def outcome_atr(rows, si, direction, atr, horizon, k=K_ATR, fee=FEE):
    """
    (label, ret) — label in {"real","fake","neutral"}.
    배리어: 진입가 ± k x ATR(진입시점). 먼저 닿는 쪽이 승/패, 미도달 시 시간초과.
    ret 은 수수료 차감 후. short 은 부호 반전.
    """
    a = atr[si]
    if a is None or a <= 0:
        return None, None
    base = rows[si]["c"]
    up, dn = base + k * a, base - k * a
    end = min(si + horizon, len(rows) - 1)
    for j in range(si + 1, end + 1):
        hi, lo = rows[j]["h"], rows[j]["l"]
        if direction == "long":
            # 같은 봉에서 양쪽 다 닿으면 보수적으로 손절 우선
            if lo <= dn:
                return "fake", (dn / base - 1) - fee
            if hi >= up:
                return "real", (up / base - 1) - fee
        else:
            if hi >= up:
                return "fake", (base - up) / base - fee
            if lo <= dn:
                return "real", (base - dn) / base - fee
    c = rows[end]["c"]
    r = (c / base - 1) if direction == "long" else (base - c) / base
    return "neutral", r - fee


# ── 통계 ────────────────────────────────────────────────────────────────────
def _pval(t, df):
    z = abs(t) / sqrt(1 + t * t / df)
    return 2 * (1 - 0.5 * (1 + erf(z / sqrt(2))))


def bootstrap_baseline(pool, direction_of, horizon, k=K_ATR, n=BOOT_N,
                       sample_k=30, seed=SEED):
    """
    pool: [(rows, atr, si)] 무작위 진입 후보. direction_of(si) -> 'long'/'short'
    같은 배리어·보유한도로 무작위 진입 평균수익 분포를 만든다.
    """
    random.seed(seed)
    if not pool:
        return None
    sample_k = min(sample_k, len(pool))
    means = []
    for _ in range(n):
        rets = []
        for rows, atr, si in random.choices(pool, k=sample_k):
            _, r = outcome_atr(rows, si, direction_of(si), atr, horizon, k)
            if r is not None:
                rets.append(r)
        if rets:
            means.append(statistics.mean(rets))
    return means or None


def quartiles(dates):
    """날짜 문자열 리스트를 4등분한 경계 [(from,to)x4]."""
    if not dates:
        return []
    lo, hi = min(dates), max(dates)
    from datetime import date, timedelta
    d0 = date(*map(int, lo.split("-")))
    d1 = date(*map(int, hi.split("-")))
    span = max(4, (d1 - d0).days)
    out = []
    for q in range(4):
        a = d0 + timedelta(days=span * q // 4)
        b = d0 + timedelta(days=span * (q + 1) // 4 - (0 if q == 3 else 1))
        out.append((a.isoformat(), b.isoformat()))
    return out


def evaluate(label, sigs, boot_means=None, min_oos_n=5, verbose=True,
             extra=None):
    """
    sigs: [(date, ret)] — 수수료 차감 후 수익.
    반환 dict: 동결게이트(frozen_ok) + 수수료마진(fee_ok) + 종합(verdict).
    """
    rets = [r for _, r in sigs]
    n = len(rets)
    mean = statistics.mean(rets) if rets else 0.0
    med = statistics.median(rets) if rets else 0.0
    if n >= 2:
        sd = statistics.stdev(rets)
        t = mean / (sd / sqrt(n)) if sd > 0 else 0.0
        p = _pval(t, n - 1)
    else:
        t, p = 0.0, 1.0
    boot_p = (sum(1 for b in boot_means if b >= mean) / len(boot_means)
              if boot_means else None)

    # OOS 4분위
    oos, oos_pos = [], 0
    for i, (d0, d1) in enumerate(quartiles([d for d, _ in sigs]), 1):
        seg = [r for d, r in sigs if d0 <= d <= d1]
        m = statistics.mean(seg) if seg else 0.0
        ok = m > 0 and len(seg) >= min_oos_n
        oos_pos += 1 if ok else 0
        oos.append(dict(q=i, n=len(seg), mean=round(m, 5), ok=ok))

    frozen_ok = (n >= 20 and mean > 0 and med > 0
                 and (boot_p is not None and boot_p < 0.05) and oos_pos >= 2)
    fee_ok = mean > FEE          # 순수익이 왕복 수수료보다 크다 = 총수익 2배 이상
    verdict = "PASSED" if (frozen_ok and fee_ok) else "REJECTED"
    if n < 20:
        verdict = "HOLD_N"

    out = dict(study=label, n=n, mean=round(mean, 5), median=round(med, 5),
               t=round(t, 3), p=round(p, 4),
               boot_p=(round(boot_p, 4) if boot_p is not None else None),
               oos=oos, oos_pos=oos_pos,
               mean_at_realistic_fee=round(mean + (FEE - FEE_REALISTIC), 5),
               frozen_ok=frozen_ok, fee_ok=fee_ok, verdict=verdict)
    if extra:
        out.update(extra)
    if verbose:
        print(f"\n[{label}] n={n} mean={mean*100:+.3f}% median={med*100:+.3f}% "
              f"t={t:.2f} p={p:.4f}")
        print(f"  boot_p={out['boot_p']} | OOS {oos_pos}/4 | "
              f"수수료마진({mean*100:+.3f}% vs {FEE*100:.2f}%) "
              f"{'✓' if fee_ok else '✗'} | 동결게이트 {'✓' if frozen_ok else '✗'}"
              f" -> {verdict}")
        for o in oos:
            print(f"    OOS Q{o['q']}: n={o['n']} mean={o['mean']*100:+.3f}% "
                  f"{'✓' if o['ok'] else '✗'}")
    return out


def dump(results, path):
    json.dump(results, open(path, "w"), indent=1)
    print("\nRESULT_JSON: " + json.dumps(results, separators=(",", ":")))
