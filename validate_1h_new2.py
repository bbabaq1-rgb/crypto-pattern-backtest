"""
validate_1h_new2.py — 신규 1h 패턴 2종(bb_zscore·rsi_extreme) 풀 파이프라인 검증.

기존 validate_1h_patterns.py 파이프라인 재사용:
  게이트 동결(n>=20, mean>0, median>0, boot_p<0.05) + OOS 4구간 + 부트스트랩 1000회
추가: 레짐 분리(진입일 레짐별 mean/n) 분석.
"""
import sys
import json
import statistics

import detlib
import regime_switch as rs
from validate_1h_patterns import _syms, _collect, run_pattern

import detector_bb_zscore_1h as bbz
import detector_rsi_extreme_1h as rex

REGMAP = rs.build_regime_map()


def regime_split(detect_fn, direction, syms):
    """진입일 레짐별 (n, mean)."""
    buckets = {}
    for d, ret in _collect(detect_fn, direction, syms):
        rg = REGMAP.get(d, "unknown")
        buckets.setdefault(rg, []).append(ret)
    return {rg: dict(n=len(v), mean=statistics.mean(v)) for rg, v in sorted(buckets.items())}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    syms = _syms()
    print(f"신규 1h 패턴 검증 — 심볼 {len(syms)}개")

    CANDS = [
        ("bb_zscore_1h",        bbz.detect_long,  "long"),
        ("bb_zscore_short_1h",  bbz.detect_short, "short"),
        ("rsi_extreme_1h",      rex.detect_long,  "long"),
        ("rsi_extreme_short_1h", rex.detect_short, "short"),
    ]

    results = []
    for label, fn, direction in CANDS:
        r = run_pattern(label, fn, direction, syms)
        # 레짐 분리 (표본이 있을 때만)
        if r.get("n", 0) >= 20:
            rsplit = regime_split(fn, direction, syms)
            r["regime_split"] = rsplit
            print("    레짐 분리:")
            for rg, s in rsplit.items():
                print(f"      {rg:<15} n={s['n']:>5} mean={s['mean']*100:+.2f}%")
        results.append(r)

    print("\n" + "=" * 64)
    print(f"{'패턴':<24} {'n':>6} {'mean':>8} {'median':>8} {'OOS':>5} {'boot_p':>8} {'판정':>8}")
    for r in results:
        print(f"{r['pattern']:<24} {r.get('n',0):>6} {r.get('mean',0)*100:>+7.2f}% "
              f"{r.get('median',0)*100:>+7.2f}% {r.get('oos_pos',0):>3}/4 "
              f"{r.get('boot_p',1.0):>8.4f} {r.get('verdict','?'):>8}"
              + (f"  [{r['reason']}]" if r.get("reason") else ""))

    json.dump(results, open("_1h_new2_results.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2, default=lambda x: round(float(x), 6))
    print("\n결과 -> _1h_new2_results.json")
    return results


if __name__ == "__main__":
    main()
