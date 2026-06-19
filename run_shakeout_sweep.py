"""
run_shakeout_sweep.py — 셰이크아웃 필터 dip_pct x vol_mult 격자 스윕.
  shakeout_stage2 와 동일한 필터/verdict 로직을, dip_pct·vol_mult만 격자로
  바꿔가며 적용. 어떤 조합에서 verdict가 '통과'로 바뀌는지 한눈에.
  (recover_bars, vol_lookback, scan_window, verdict 기준값은 2단계 기본 고정)
"""
import csv
from datetime import datetime, timezone
from collections import defaultdict

# 고정 파라미터 (2단계 기본값)
RECOVER_BARS  = 4
VOL_LOOKBACK  = 20
SCAN_WINDOW   = 20
MIN_N         = 20
MIN_TRUE_RATE = 0.55

# 격자
DIP_PCTS  = [0.01, 0.02, 0.03, 0.05, 0.08]
VOL_MULTS = [1.5, 2.0, 2.5, 3.0, 4.0]

IN_CSV = "data/shakeout_stage1_signals.csv"
CSV_1D = lambda s: f"data/{s.lower()}_1d.csv"


def load_ohlcv(sym):
    rows, idx = [], {}
    with open(CSV_1D(sym), newline="") as f:
        for r in csv.DictReader(f):
            ts = int(float(r["timestamp"]))
            d  = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
            idx[d] = len(rows)
            rows.append(dict(h=float(r["high"]), l=float(r["low"]),
                             c=float(r["close"]), v=float(r["volume"])))
    return idx, rows


def confirmed(rows, si, dip_pct, vol_mult):
    n = len(rows)
    end = min(si + SCAN_WINDOW, n - 1)
    running_min = rows[si]["l"]
    for k in range(si + 1, end + 1):
        if rows[k]["l"] <= running_min * (1 - dip_pct):
            broke = running_min
            rec_end = min(k + RECOVER_BARS, n - 1)
            rec_bar = None
            for j in range(k, rec_end + 1):
                if rows[j]["c"] > broke:
                    rec_bar = j
                    break
            if rec_bar is not None:
                lo = k - VOL_LOOKBACK
                if lo >= 0:
                    base = sum(rows[m]["v"] for m in range(lo, k)) / VOL_LOOKBACK
                    peak = max(rows[m]["v"] for m in range(k, rec_bar + 1))
                    if base > 0 and peak >= vol_mult * base:
                        return True
        running_min = min(running_min, rows[k]["l"])
    return False


def main():
    # 입력 + OHLCV 캐시 로드
    sig = list(csv.DictReader(open(IN_CSV, newline="", encoding="utf-8-sig")))
    cache = {}
    for r in sig:
        s = r["symbol"]
        if s not in cache:
            cache[s] = load_ohlcv(s)

    LK = {"진짜": "real", "페이크": "fake", "중립": "neutral"}

    # 각 (dip, vol) 조합 평가
    grid = {}   # (dip, vol) -> dict(n, real, verdict, rate)
    passes = []
    for dip in DIP_PCTS:
        for vm in VOL_MULTS:
            n = real = fake = neu = 0
            for r in sig:
                idx, rows = cache[r["symbol"]]
                if r["date"] not in idx:
                    continue
                si = idx[r["date"]]
                if confirmed(rows, si, dip, vm):
                    n += 1
                    k = LK.get(r["label"], "neutral")
                    if k == "real": real += 1
                    elif k == "fake": fake += 1
                    else: neu += 1
            rate = real / n if n else 0.0
            if n < MIN_N:
                v = "보류"
            elif rate >= MIN_TRUE_RATE:
                v = "통과"; passes.append((dip, vm, n, rate))
            else:
                v = "기각"
            grid[(dip, vm)] = dict(n=n, real=real, rate=rate, v=v)

    # 출력: 격자 (행=dip_pct, 열=vol_mult), 셀=진짜율%(n) + verdict약자
    print("=" * 78)
    print("셰이크아웃 필터 dip_pct x vol_mult 격자 스윕")
    print(f"고정: recover_bars={RECOVER_BARS}, vol_lookback={VOL_LOOKBACK}, "
          f"scan_window={SCAN_WINDOW} | 기준: n>={MIN_N}, 진짜율>={MIN_TRUE_RATE*100:.0f}%")
    print("  셀 = 진짜율%(잔존n) [P=통과 X=기각 H=보류]")
    print("=" * 78)
    header = "  dip\\vol |" + "".join(f"{vm:>13}" for vm in VOL_MULTS)
    print(header)
    print("  " + "-" * (len(header) - 2))
    tag = {"통과": "P", "기각": "X", "보류": "H"}
    for dip in DIP_PCTS:
        cells = []
        for vm in VOL_MULTS:
            g = grid[(dip, vm)]
            cells.append(f"{g['rate']*100:4.0f}%({g['n']:>3}){tag[g['v']]}")
        print(f"  {dip*100:5.0f}%  |" + "".join(f"{c:>13}" for c in cells))

    print("\n" + "=" * 78)
    if passes:
        print(f"통과 조합 {len(passes)}개:")
        for dip, vm, n, rate in passes:
            print(f"  dip_pct={dip}, vol_mult={vm}  ->  n={n}, 진짜율 {rate*100:.1f}%")
    else:
        print("통과(P) 조합 없음 - 모든 격자에서 verdict가 기각 또는 보류.")
        # 참고: 진짜율 최대 조합(표본 충분한 것 중)
        ok = [(k, v) for k, v in grid.items() if v["n"] >= MIN_N]
        if ok:
            bk, bv = max(ok, key=lambda kv: kv[1]["rate"])
            print(f"  (n>={MIN_N} 중 최고 진짜율: dip_pct={bk[0]}, vol_mult={bk[1]} "
                  f"-> {bv['rate']*100:.1f}% (n={bv['n']}))")
    print("=" * 78)


if __name__ == "__main__":
    main()
