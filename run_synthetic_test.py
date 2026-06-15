"""
run_synthetic_test.py — 합성 데이터로 전체 파이프라인 검증

실데이터 없이도 이 채팅 환경에서 fetch→backtest 플러밍이 끝까지 도는지 확인한다.
삼중바닥 에피소드 여러 개 + 랜덤워크 구간을 섞은 OHLCV 를 만들어 CSV 로 저장한 뒤,
backtest.py 의 워크포워드 하니스를 그대로 호출해 리포트를 출력한다.

실데이터로 돌릴 때는 이 파일 대신:
  python fetch_data.py --symbol BTC/USDT --timeframe 1d --since 2021-01-01 --out data/btc_1d.csv
  python backtest.py   --csv data/btc_1d.csv --detector all --hold 10
"""

import csv
import math
import os
import random

from backtest import run_backtest, print_report, DETECTORS, load_csv

random.seed(42)


def _leg(a, b, n, vol):
    ps = [a + (b - a) * (i / (n - 1)) for i in range(n)]
    vs = [vol * (1 + random.uniform(-0.12, 0.12)) for _ in range(n)]
    return ps, vs


def _triple_bottom_episode(level):
    """하나의 삼중바닥 + 돌파 + 반등 에피소드 (거래량 패턴 포함)."""
    P, V = [], []
    plan = [
        (level * 1.15, level,        20, 1000),  # 하락 → 저점1
        (level,        level * 1.11, 14,  750),  # 반등1
        (level * 1.11, level * 0.99, 15,  650),  # 하락 → 저점2
        (level * 0.99, level * 1.12, 14,  550),  # 반등2
        (level * 1.12, level * 1.005,15,  450),  # 하락 → 저점3 (거래량 최소)
        (level * 1.005,level * 1.13, 10, 1900),  # 저항 돌파 (거래량 급증)
        (level * 1.13, level * 1.25, 14,  900),  # 반등 지속 (→ 양의 forward return)
    ]
    for a, b, n, vol in plan:
        ps, vs = _leg(a, b, n, vol)
        P += ps; V += vs
    return P, V


def _random_walk(start, n, vol):
    P, V, p = [], [], start
    for _ in range(n):
        p *= (1 + random.uniform(-0.02, 0.02))
        P.append(p); V.append(vol * (1 + random.uniform(-0.15, 0.15)))
    return P, V


def build_synthetic():
    closes, vols = [], []
    levels = [100, 130, 90, 150, 110, 120]      # 에피소드마다 다른 가격대
    last = 115
    for k, lv in enumerate(levels):
        # 에피소드 사이 랜덤워크 필러
        rwP, rwV = _random_walk(last, random.randint(35, 55), 600)
        closes += rwP; vols += rwV
        last = rwP[-1]
        # 삼중바닥 에피소드
        epP, epV = _triple_bottom_episode(lv)
        closes += epP; vols += epV
        last = epP[-1]
    # 미세 노이즈(결정론적)
    closes = [round(c + 0.3 * math.sin(i / 2), 4) for i, c in enumerate(closes)]
    return closes, vols


def write_csv(closes, vols, path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "datetime", "open", "high", "low", "close", "volume"])
        ts = 1_600_000_000_000
        for i, (c, v) in enumerate(zip(closes, vols)):
            t = ts + i * 86_400_000              # 일봉 간격(ms)
            w.writerow([t, f"day{i}", c, c, c, c, round(v, 1)])


if __name__ == "__main__":
    closes, vols = build_synthetic()
    out = "data/synthetic.csv"
    write_csv(closes, vols, out)
    print(f"[합성] {len(closes)}개 캔들 → {out}")

    ohlcv = load_csv(out)
    for name in DETECTORS:
        res = run_backtest(ohlcv, DETECTORS[name], name, hold=10,
                           min_conf=0.0, fee=0.001, warmup=40)
        print_report(res)
