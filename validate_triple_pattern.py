"""
validate_triple_pattern.py — 삼중바닥(롱)/삼중천장(숏) 멀티TF 검증 파이프라인.

사용자 요청(2026-08-29): '15분부터 월봉까지' 삼중바닥=롱 / 삼중천장=숏 자동 트리거.
게이트 동결(CLAUDE.md): n>=20, mean>0, median>0, boot_p<0.05, OOS 양구간>=2.
통과 TF만 스케줄러 등록 대상 — 기각/표본부족 TF는 기록만 남긴다.

TF별 데이터 (GitHub Actions 러너에서 fetch):
  15m(45일) / 1h(40일) / 4h(130일) / 1d(900일) — fetch_data.WINDOW_DAYS
  1w / 1M — 1d 리샘플(detlib.resample_rows). 월봉은 표본이 구조적으로 부족해
  카운팅만 가능함을 결과에 명시한다(약 30봉/종목).

OOS: TF마다 실제 데이터 기간을 4등분(날짜 기준, 결정론적).
출력: 사람용 로그 + 마지막 줄 'RESULT_JSON: {...}' (원격 로그 파싱용).
"""
import json
import gate
import statistics
import sys
import time
from math import erf, sqrt
import random

import detlib
import fetch_data
import detector_triple_bottom as tb
import detector_triple_top as tt

SEED = 42
BOOT_N = 1000
FETCH_TFS = ["1d", "4h", "1h", "15m"]
# 연장 검증 윈도 (2026-08-29 2차): 1차는 스케줄러 동결 윈도(1d900/4h130/1h40)를
# 그대로 써서 4h 통과 셀이 130일(bear 단일 레짐)만 검증됨 — 레포 기존 4h 패턴
# (three_soldiers, 2021~2026 5년)보다 약한 기준. 거래소가 주는 만큼 최대 수집.
FETCH_WINDOWS = {"1d": 1800, "4h": 1100, "1h": 365, "15m": 45}
ALL_TFS = ["15m", "1h", "4h", "1d", "1w", "1M"]
PATTERNS = [("triple_bottom", tb.detect, "long"),
            ("triple_top", tt.detect, "short")]


def _syms():
    u = json.load(open("universe.json", encoding="utf-8"))
    return u["trading_universe"]


def fetch_all(syms):
    for tf in FETCH_TFS:
        t0, ok, new = time.time(), 0, 0
        for s in syms:
            n_new, total = fetch_data.update_csv(
                f"{s}/USDT", tf, f"data/{s.lower()}_{tf}.csv",
                window_days=FETCH_WINDOWS.get(tf))
            if total > 0:
                ok += 1
                new += n_new
        print(f"[fetch] {tf}: {ok}/{len(syms)}종목 +{new}봉 "
              f"({time.time()-t0:.0f}s, window={FETCH_WINDOWS.get(tf)}d)",
              flush=True)


def load_tf(sym, tf):
    """TF별 rows. 1w/1M은 1d 리샘플."""
    if tf in ("1w", "1M"):
        return detlib.resample_rows(detlib.load_ohlcv(sym, "1d"), tf)
    return detlib.load_ohlcv(sym, tf)


def _pval(t, df):
    z = abs(t) / sqrt(1 + t * t / df)
    return 2 * (1 - 0.5 * (1 + erf(z / sqrt(2))))


def _collect(detect_fn, direction, syms, tf, date_from=None, date_to=None):
    rets = []
    for sym in syms:
        try:
            rows = load_tf(sym, tf)
        except Exception:
            continue
        for si in detect_fn(rows):
            d = rows[si]["date"]
            if date_from and d < date_from:
                continue
            if date_to and d > date_to:
                continue
            _, ret = detlib.outcome(rows, si, direction)
            rets.append((d, ret))
    return rets


def _date_range(syms, tf):
    lo = hi = None
    for sym in syms:
        try:
            rows = load_tf(sym, tf)
        except Exception:
            continue
        if rows:
            lo = rows[0]["date"] if lo is None else min(lo, rows[0]["date"])
            hi = rows[-1]["date"] if hi is None else max(hi, rows[-1]["date"])
    return lo, hi


def _quartiles(lo, hi):
    """날짜 문자열 구간을 4등분한 [(from,to)x4]."""
    from datetime import date, timedelta
    d0 = date(*map(int, lo.split("-")))
    d1 = date(*map(int, hi.split("-")))
    span = max(4, (d1 - d0).days)
    outs = []
    for q in range(4):
        a = d0 + timedelta(days=span * q // 4)
        b = d0 + timedelta(days=span * (q + 1) // 4 - (0 if q == 3 else 1))
        outs.append((a.isoformat(), b.isoformat()))
    return outs


def _bootstrap(direction, syms, tf, k, n=BOOT_N, seed=SEED):
    random.seed(seed)
    pool = []
    for sym in syms:
        try:
            rows = load_tf(sym, tf)
        except Exception:
            continue
        for i in range(len(rows) - detlib.LABEL_WINDOW - 1):
            pool.append((rows, i))
    if not pool:
        return None
    k = min(k, len(pool))
    means = []
    for _ in range(n):
        sample = random.choices(pool, k=k)
        means.append(statistics.mean(
            detlib.outcome(r, si, direction)[1] for r, si in sample))
    return means


def run_tf(label, detect_fn, direction, syms, tf):
    sigs = _collect(detect_fn, direction, syms, tf)
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

    out = dict(pattern=label, tf=tf, n=n,
               mean=round(mean, 5), median=round(med, 5),
               t=round(t, 3), p=round(p, 4))
    print(f"\n[{label} @ {tf}] n={n} mean={mean*100:+.2f}% "
          f"median={med*100:+.2f}% t={t:.2f} p={p:.4f}", flush=True)

    if n < 20:
        out.update(verdict="HOLD_N", boot_p=None, oos_pos=None)
        print(f"  -> 보류(표본부족 n={n}<20)"
              + (" — 월봉은 구조적으로 카운팅만 가능" if tf == "1M" else ""))
        return out

    boot = _bootstrap(direction, syms, tf, k=max(10, min(30, n)))
    boot_p = (sum(1 for b in boot if b >= mean) / len(boot)) if boot else 0.5
    out["boot_p"] = round(boot_p, 4)

    lo, hi = _date_range(syms, tf)
    oos_pos, oos_detail = 0, []
    for i, (d0, d1) in enumerate(_quartiles(lo, hi), 1):
        seg = _collect(detect_fn, direction, syms, tf, d0, d1)
        sr = [r for _, r in seg]
        sm = statistics.mean(sr) if sr else 0.0
        ok = sm > 0 and len(sr) >= 5
        oos_pos += 1 if ok else 0
        oos_detail.append(dict(q=i, n=len(sr), mean=round(sm, 5), ok=ok))
        print(f"  OOS Q{i} ({d0}~{d1}): n={len(sr)} mean={sm*100:+.2f}% "
              f"{'✓' if ok else '✗'}")
    out["oos"] = oos_detail
    out["oos_pos"] = oos_pos

    passed = (mean > 0 and gate.dist_ok(rets) and boot_p < 0.05 and oos_pos >= 2)
    out["verdict"] = "PASSED" if passed else "REJECTED"
    fails = []
    if mean <= 0:
        fails.append("mean<=0")
    if not gate.dist_ok(rets):
        fails.append(gate.dist_reason(rets))
    if boot_p >= 0.05:
        fails.append(f"boot_p={boot_p:.3f}")
    if oos_pos < 2:
        fails.append(f"OOS {oos_pos}/4")
    out["reason"] = ", ".join(fails)
    print(f"  boot_p={boot_p:.4f} | OOS {oos_pos}/4 -> {out['verdict']}"
          + (f" ({out['reason']})" if fails else ""))
    return out


def main():
    syms = _syms()
    print(f"유니버스 {len(syms)}종목 | TF: {ALL_TFS}")
    if "--no-fetch" not in sys.argv:
        fetch_all(syms)

    results = []
    for label, fn, direction in PATTERNS:
        for tf in ALL_TFS:
            try:
                results.append(run_tf(label, fn, direction, syms, tf))
            except Exception as e:
                print(f"[{label} @ {tf}] 오류: {str(e)[:100]}")
                results.append(dict(pattern=label, tf=tf, verdict="ERROR",
                                    error=str(e)[:100]))

    print("\n" + "=" * 64)
    for r in results:
        print(f"  {r['pattern']:>13} @ {r['tf']:<3}: {r.get('verdict')}"
              f"  n={r.get('n')} mean={r.get('mean')}")
    json.dump(results, open("_triple_pattern_results.json", "w"), indent=1)
    print("\nRESULT_JSON: " + json.dumps(results, separators=(",", ":")))


if __name__ == "__main__":
    main()
