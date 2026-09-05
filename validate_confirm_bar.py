"""
validate_confirm_bar.py — 룩어헤드 제거 후 재검증 (2026-09-03).

대상 셀 (검증 당시와 같은 라벨 ±10%/20봉, 같은 게이트):
  gartley / bat / butterfly @4h  — 모듈 CFG (4h 등재 당시 파라미터)
  gartley / bat / butterfly @1h  — validate_1h_patterns.HARMONIC_CFG (1h 등재 당시 파라미터)
  triple_bottom @1w              — detector_triple_bottom (1d 1800일 리샘플)
각 셀을 **new(인과, 실거래 발화 가능)** 와 **old(종전, 룩어헤드)** 두 판으로 돌려
등재 수치가 얼마나 부풀려 있었는지와 인과 판이 게이트를 넘는지를 같이 본다.
게이트 v2(2026-09-05): n>=20, mean>0, 승률>=35%(gate.dist_ok), boot_p<0.05, OOS 4분위 양구간>=2(n>=5).
복귀 규칙: new 가 PASSED 인 셀만 등재 복귀 후보 — 사용자 결정.
출력: _confirm_bar.json + 마지막 줄 RESULT_JSON.
"""
import json
import gate as gt   # 이 모듈의 로컬 함수 gate() 와 이름 충돌 방지
import random
import statistics
import sys
import time
from math import erf, sqrt

import detlib
import fetch_data
import detector_harmonic_base as hb
import detector_bat, detector_gartley, detector_butterfly
import detector_triple_bottom as tb
from validate_1h_patterns import HARMONIC_CFG as CFG_1H

SEED, BOOT_N = 42, 1000
FETCH_WINDOWS = {"1d": 1800, "4h": 1100, "1h": 365}
LABEL_W = detlib.LABEL_WINDOW


def _syms():
    return json.load(open("universe.json", encoding="utf-8"))["trading_universe"]


def fetch_all(syms):
    for tf, win in FETCH_WINDOWS.items():
        t0, ok = time.time(), 0
        for s in syms:
            try:
                _, total = fetch_data.update_csv(f"{s}/USDT", tf, f"data/{s.lower()}_{tf}.csv",
                                                 window_days=win)
                ok += total > 0
            except Exception as e:
                print(f"  [fetch] {s} {tf} 실패: {str(e)[:60]}")
        print(f"[fetch] {tf}: {ok}/{len(syms)} ({time.time()-t0:.0f}s, {win}d)", flush=True)


def _load(sym, tf):
    return detlib.load_ohlcv(sym, tf)      # 1w 는 detlib 가 1d 리샘플


def _pval(t, df):
    z = abs(t) / sqrt(1 + t * t / df)
    return 2 * (1 - 0.5 * (1 + erf(z / sqrt(2))))


def _collect(detect_fn, syms, tf, direction="long"):
    out = []
    for sym in syms:
        try:
            rows = _load(sym, tf)
        except Exception:
            continue
        for si in detect_fn(rows):
            if si + 1 >= len(rows):
                continue
            _, ret = detlib.outcome(rows, si, direction)
            out.append((rows[si]["date"], ret))
    return out


def _bootstrap(syms, tf, k, direction="long", n=BOOT_N):
    random.seed(SEED)
    pool = []
    for sym in syms:
        try:
            rows = _load(sym, tf)
        except Exception:
            continue
        pool.extend((rows, i) for i in range(len(rows) - LABEL_W - 1))
    if not pool:
        return [0.0]
    k = min(k, len(pool))
    return [statistics.mean(detlib.outcome(r, i, direction)[1] for r, i in random.choices(pool, k=k))
            for _ in range(n)]


def gate(label, sigs, syms, tf):
    rets = [r for _, r in sigs]
    n = len(rets)
    mean = statistics.mean(rets) if rets else 0.0
    med = statistics.median(rets) if rets else 0.0
    if n >= 2 and statistics.stdev(rets) > 0:
        t = mean / (statistics.stdev(rets) / sqrt(n)); p = _pval(t, n - 1)
    else:
        t, p = 0.0, 1.0
    boot = _bootstrap(syms, tf, k=max(10, min(30, n)))
    boot_p = sum(1 for b in boot if b >= mean) / len(boot)
    # OOS: 실제 신호 날짜 범위를 4등분(결정론적)
    oos = []
    if n >= 20:
        dates = sorted(d for d, _ in sigs)
        cuts = [dates[len(dates) * i // 4] for i in range(1, 4)]
        for q in range(4):
            lo = cuts[q - 1] if q else "0000"
            hi = cuts[q] if q < 3 else "9999"
            qr = [r for d, r in sigs if lo <= d < hi]
            qm = statistics.mean(qr) if qr else 0.0
            oos.append(dict(q=q + 1, n=len(qr), mean=qm, ok=len(qr) >= 5 and qm > 0))
    oos_pos = sum(1 for o in oos if o["ok"])
    ok = n >= 20 and mean > 0 and gt.dist_ok(rets) and boot_p < 0.05 and oos_pos >= 2
    fails = []
    if n < 20: fails.append("n<20")
    if mean <= 0: fails.append("mean<=0")
    if not gt.dist_ok(rets): fails.append(gt.dist_reason(rets))
    if boot_p >= 0.05: fails.append(f"boot_p={boot_p:.3f}")
    if n >= 20 and oos_pos < 2: fails.append(f"OOS {oos_pos}/4")
    rec = dict(label=label, n=n, mean=mean, median=med, t=t, p=p, boot_p=boot_p,
               oos=oos, oos_pos=oos_pos, verdict="PASSED" if ok else "REJECTED",
               reason=", ".join(fails))
    print(f"  {label:<28} n={n:>5} mean={mean*100:+6.2f}% med={med*100:+6.2f}% "
          f"boot_p={boot_p:.3f} OOS={oos_pos}/4 -> {rec['verdict']} {rec['reason']}")
    return rec


def cells():
    out = []
    for name, mod in (("gartley", detector_gartley), ("bat", detector_bat), ("butterfly", detector_butterfly)):
        cfg = mod.CFG
        out.append((f"{name}_4h", "4h",
                    lambda r, c=cfg: hb.detect_harmonic(r, c, confirm=True),
                    lambda r, c=cfg: hb.detect_harmonic(r, c, confirm=False)))
    for name, cfg in CFG_1H.items():
        out.append((f"{name}_1h", "1h",
                    lambda r, c=cfg: hb.detect_harmonic(r, c, confirm=True),
                    lambda r, c=cfg: hb.detect_harmonic(r, c, confirm=False)))
    out.append(("triple_bottom_1w", "1w", lambda r: tb.detect(r, causal=True),
                lambda r: tb.detect(r, causal=False)))
    return out


def main():
    syms = _syms()
    print(f"확정 봉 재검증 | 유니버스 {len(syms)} | 라벨 ±10%/{LABEL_W}봉 | 부트스트랩 {BOOT_N}")
    if "--no-fetch" not in sys.argv:
        fetch_all(syms)
    results = []
    for label, tf, fn_new, fn_old in cells():
        print(f"\n[{label}]")
        new = gate(label + " (new/인과)", _collect(fn_new, syms, tf), syms, tf)
        old = gate(label + " (old/룩어헤드)", _collect(fn_old, syms, tf), syms, tf)
        results.append(dict(cell=label, tf=tf, new=new, old=old,
                            inflation_pp=round((old["mean"] - new["mean"]) * 100, 3)))
    print("\n" + "=" * 72)
    for r in results:
        print(f"  {r['cell']:<18} new {r['new']['verdict']:<8} n={r['new']['n']:<5} mean={r['new']['mean']*100:+.2f}%"
              f"  | old {r['old']['verdict']:<8} n={r['old']['n']:<5} mean={r['old']['mean']*100:+.2f}%"
              f"  | 부풀림 {r['inflation_pp']:+.2f}%p")
    json.dump(results, open("_confirm_bar.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\nRESULT_JSON: " + json.dumps(results, separators=(",", ":"), ensure_ascii=False))


if __name__ == "__main__":
    main()
