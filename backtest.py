"""
backtest.py — 워크포워드 백테스트 하니스

핵심 원칙
  - look-ahead 차단: i번째 봉 판정 시 detector에 candles[:i+1]만 넘긴다.
  - 결과(forward return)는 그 '이후' N봉으로만 측정한다.
  - 같은 패턴을 중복 매매하지 않는다(피벗 시그니처 dedup + 보유기간 쿨다운).
  - 수수료(왕복)를 차감한다.
  - confidence 구간별 실제 승률을 집계해 '보정'의 근거를 만든다.

사용 예:
  python backtest.py --csv data/btc_1d.csv --detector triple_bottom --hold 7 --min-conf 0.6
  python backtest.py --csv data/btc_1d.csv --detector all --hold 10 --fee 0.001
"""

import argparse
import csv
import statistics as st

from elliott_detect import detect as detect_elliott
from terminal_detect import detect_terminal
from triple_bottom_volume import detect_triple_bottom, detect_triple_bottom_descending
from reversal_patterns import (detect_inverse_hs, detect_hs,
                               detect_double_bottom, detect_double_top)
from breakout_indicators import (detect_breakout, detect_rsi_divergence,
                                 detect_ma_cross)


# ----------------------------------------------------------------------
# detector 레지스트리 (통일된 호출 인터페이스)
# ----------------------------------------------------------------------
DETECTORS = {
    "elliott":         lambda c: detect_elliott(c),
    "terminal":        lambda c: detect_terminal(c),
    "triple_bottom":   lambda c: detect_triple_bottom(c),
    "triple_bottom_desc": lambda c: detect_triple_bottom_descending(c),
    "inverse_hs":      lambda c: detect_inverse_hs(c),
    "hs":              lambda c: detect_hs(c),
    "double_bottom":   lambda c: detect_double_bottom(c),
    "double_top":      lambda c: detect_double_top(c),
    "breakout":        lambda c: detect_breakout(c),
    "rsi_divergence":  lambda c: detect_rsi_divergence(c),
    "ma_cross":        lambda c: detect_ma_cross(c),
}

NON_MATCH = {"none", "no_clear_impulse", "no_terminal",
             "no_triple_bottom", "error", "forming"}


def signal_is_match(sig):
    """패턴 일치 여부. triple_bottom 은 명시적 matched, 나머지는 패턴+confidence."""
    if sig.pattern in NON_MATCH:
        return False
    if "matched" in sig.detail:           # 거래량까지 일치해야 하는 패턴
        return bool(sig.detail["matched"])
    return sig.confidence > 0.0


def signal_signature(sig):
    """같은 패턴 인스턴스를 식별하는 키(피벗 인덱스). 중복 매매 방지용."""
    for key in ("pivots", "wedge_pivots", "impulse_pivots"):
        if key in sig.detail:
            return (sig.pattern, tuple(p[0] for p in sig.detail[key]))
    return (sig.pattern,)


# ----------------------------------------------------------------------
# CSV 로더
# ----------------------------------------------------------------------
def load_csv(path):
    """fetch_data.py 가 만든 CSV → OHLCV 리스트 [ts,o,h,l,c,v]."""
    rows = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            rows.append([int(float(r["timestamp"])), float(r["open"]),
                         float(r["high"]), float(r["low"]),
                         float(r["close"]), float(r["volume"])])
    rows.sort(key=lambda x: x[0])
    return rows


# ----------------------------------------------------------------------
# 워크포워드 백테스트
# ----------------------------------------------------------------------
def run_backtest(ohlcv, detector_fn, name, hold=7, min_conf=0.0,
                 fee=0.001, warmup=60, step=1):
    """
    각 봉에서 과거만 보고 신호를 판정 → 신호 시 hold봉 뒤 종가로 수익 측정.
    direction='up'은 롱, 'down'은 숏으로 부호 처리. 왕복 수수료 2*fee 차감.
    """
    trades = []
    traded_sig = set()
    next_allowed = warmup

    for i in range(warmup, len(ohlcv) - hold, step):
        window = ohlcv[:i + 1]                      # look-ahead 차단
        sig = detector_fn(window)
        if not signal_is_match(sig) or sig.confidence < min_conf:
            continue
        if i < next_allowed:                        # 보유기간 중 중복 진입 금지
            continue
        sigkey = signal_signature(sig)
        if sigkey in traded_sig:                    # 같은 패턴 인스턴스 재매매 금지
            continue

        entry = ohlcv[i][4]
        exitp = ohlcv[i + hold][4]
        raw = (exitp - entry) / entry
        ret = (raw if sig.direction == "up" else -raw) - 2 * fee

        trades.append(dict(idx=i, ts=ohlcv[i][0], pattern=sig.pattern,
                           direction=sig.direction, confidence=sig.confidence,
                           entry=entry, exit=exitp, ret=ret))
        traded_sig.add(sigkey)
        next_allowed = i + hold

    return aggregate(name, trades, hold, min_conf, fee)


def aggregate(name, trades, hold, min_conf, fee):
    rets = [t["ret"] for t in trades]
    res = dict(detector=name, hold=hold, min_conf=min_conf, fee=fee,
               n_trades=len(trades), trades=trades)
    if not rets:
        res.update(win_rate=None, avg_ret=None, median_ret=None,
                   best=None, worst=None, buckets={})
        return res

    wins = sum(r > 0 for r in rets)
    res.update(
        win_rate=round(wins / len(rets), 4),
        avg_ret=round(st.mean(rets), 4),
        median_ret=round(st.median(rets), 4),
        best=round(max(rets), 4),
        worst=round(min(rets), 4),
        expectancy=round(st.mean(rets), 4),
    )

    # confidence 구간별 승률·평균수익 → 보정 근거
    edges = [(0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 1.01)]
    buckets = {}
    for lo, hi in edges:
        grp = [t["ret"] for t in trades if lo <= t["confidence"] < hi]
        if grp:
            buckets[f"{lo:.1f}-{hi if hi <= 1 else 1.0:.1f}"] = dict(
                n=len(grp), win_rate=round(sum(r > 0 for r in grp) / len(grp), 3),
                avg_ret=round(st.mean(grp), 4))
    res["buckets"] = buckets
    return res


def print_report(res):
    print(f"\n{'='*58}\n  {res['detector']}  (보유 {res['hold']}봉, "
          f"min_conf {res['min_conf']}, 수수료 {res['fee']})\n{'='*58}")
    if not res["n_trades"]:
        print("  신호 없음 — 임계값/기간/데이터를 확인하세요.")
        return
    print(f"  신호 수      : {res['n_trades']}")
    print(f"  승률         : {res['win_rate']*100:.1f}%")
    print(f"  평균 수익    : {res['avg_ret']*100:+.2f}%  (중앙값 {res['median_ret']*100:+.2f}%)")
    print(f"  최고 / 최저  : {res['best']*100:+.2f}% / {res['worst']*100:+.2f}%")
    if res["buckets"]:
        print("  --- confidence 구간별 (← 이 표로 confidence를 실제 확률에 보정) ---")
        for k, b in res["buckets"].items():
            print(f"    {k} | n={b['n']:3d} | 승률 {b['win_rate']*100:5.1f}% | 평균 {b['avg_ret']*100:+.2f}%")


def main():
    p = argparse.ArgumentParser(description="워크포워드 백테스트")
    p.add_argument("--csv", required=True, help="fetch_data.py 가 만든 OHLCV CSV")
    p.add_argument("--detector", default="all",
                   choices=list(DETECTORS) + ["all"])
    p.add_argument("--hold", type=int, default=7, help="보유 봉 수 (forward return 측정 구간)")
    p.add_argument("--min-conf", type=float, default=0.0, dest="min_conf")
    p.add_argument("--fee", type=float, default=0.001, help="편도 수수료율 (0.001=0.1%)")
    p.add_argument("--warmup", type=int, default=60, help="초기 워밍업 봉 수")
    args = p.parse_args()

    ohlcv = load_csv(args.csv)
    print(f"[로드] {len(ohlcv)}개 캔들 ({args.csv})")

    names = list(DETECTORS) if args.detector == "all" else [args.detector]
    for name in names:
        res = run_backtest(ohlcv, DETECTORS[name], name,
                           hold=args.hold, min_conf=args.min_conf,
                           fee=args.fee, warmup=args.warmup)
        print_report(res)


if __name__ == "__main__":
    main()
