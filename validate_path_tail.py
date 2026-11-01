"""validate_path_tail.py — R-084 실현 경로의 꼬리 위치 (사전 등록 2026-11-01, registry path_tail_prereg_2026_11_01).

R-073: 실현 경로 현행 Calmar -0.00 인데 거래 20개 블록 재표집 Calmar 중앙은 4.75. 같은 거래를 섞으면 좋아지고 실제
순서는 나쁘다 = 손실이 20거래보다 길게 군집한다는 신호. 이를 계량한다. **계산 전용** — 판정은 부트스트랩의 낙관 정도에
대한 진단이고 위험 수준(사용자 결정)은 건드리지 않는다. DEPLOY_ON_PASS=False.

프레임: R-073 과 같은 거래열·validate_gap.simulate. 셀 3 = risk {1.5%(현행), 1.0%, 0.5%} x MAX_POS 13. 블록 3종:
 B20  = vp.block_bootstrap(거래 20개 연속)      B60 = 거래 60개 연속      T7 = 진입 7일 창 단위(창 안의 거래 묶음)
재표집은 날짜 골격 유지(t_in 은 원래 순서의 것을 쓰고 거래 내용만 교체) — vp.block_bootstrap 과 같은 방식.
주 판정 셀 = 현행(1.5%,13), 통계량 = 전기간 CAGR. 분위 = P(부트 CAGR <= 실현 CAGR) (낮을수록 실현이 나쁜 꼬리).

판정(위에서 아래로 첫 일치):
 NO_TAIL        현행 셀의 B20 분위 > 0.05            — 실현이 부트 안에 있다. 부트 낙관 아님
 BLOCK_INSENSITIVE  B20 분위 <= 0.05 이고 T7 중앙 Calmar > 0.75 x B20 중앙 Calmar
                                                   — 블록을 늘려도 부트 분포가 안 내려온다(군집이 시간 창으로 안 잡힘)
 PATH_CLUSTER   B20 분위 <= 0.05, T7 중앙 Calmar <= 0.75 x B20 중앙 Calmar, T7 분위 > 0.05
                                                   — 손실 군집이 7일보다 길고 시간 블록이 꼬리를 설명(B20 부트는 낙관)
 UNLUCKY_TAIL   B20 분위 <= 0.05, T7 중앙 <= 0.75 x B20 중앙, T7 분위 <= 0.05
                                                   — 시간 블록으로도 설명 안 되는 나쁜 경로(군집 이상의 무엇)
진단(판정 아님): 1.0%·0.5% 셀의 같은 분위, MDD 분위, 블록별 중앙 CAGR·MDD.
"""
import json
import math
import random
import statistics as st
import sys

import validate_gap as vg
import validate_portfolio as vp

DEPLOY_ON_PASS = False
RISKS = (0.015, 0.010, 0.005)
MAX_POS = 13
CURRENT = (0.015, 13)
BLOCKS = ("B20", "B60", "T7")
BOOT_N = 300
SEED = 84
Q_TAIL = 0.05
MED_DROP = 0.75
T7_DAYS = 7.0
BLOCK_LEN = {"B20": 20, "B60": 60}


def cells():
    return [(r, MAX_POS) for r in RISKS]


def run_cell(trades, cell):
    return vg.simulate(trades, max_pos=cell[1], risk=cell[0])


def _cal(x):
    return x["calmar"] if math.isfinite(x["calmar"]) else 1e9


def _reassign(trades, idx):
    out = []
    for k, j in enumerate(idx):
        src, dst = trades[j], trades[k]
        hold = max(src["t_out"] - src["t_in"], 0.0)
        out.append(dict(src, t_in=dst["t_in"], t_out=dst["t_in"] + hold))
    return out


def boot_index(trades, block, rng):
    """trades 는 t_in 오름차순. 반환 = 길이 n 인 원 인덱스 열."""
    n = len(trades)
    idx = []
    if block in BLOCK_LEN:
        L = BLOCK_LEN[block]
        while len(idx) < n:
            s = rng.randrange(0, n)
            idx.extend(range(s, min(n, s + L)))
        return idx[:n]
    # T7: 진입 7일 창 단위
    wins = {}
    for j, t in enumerate(trades):
        wins.setdefault(int(t["t_in"] // T7_DAYS), []).append(j)
    keys = sorted(wins)
    while len(idx) < n:
        idx.extend(wins[keys[rng.randrange(0, len(keys))]])
    return idx[:n]


def percentile_le(dist, x):
    """P(dist <= x)."""
    return sum(d <= x for d in dist) / len(dist)


def classify(q20, q7, med_cal20, med_cal7):
    if q20 > Q_TAIL:
        return "NO_TAIL"
    if not (med_cal7 <= MED_DROP * med_cal20):
        return "BLOCK_INSENSITIVE"
    return "PATH_CLUSTER" if q7 > Q_TAIL else "UNLUCKY_TAIL"


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    import detlib
    import method_t as mt
    import regime_switch as rs
    from validate_regime_split import turnover_rank
    syms = json.load(open("universe.json", encoding="utf-8"))["trading_universe"]
    if "--no-fetch" not in argv:
        vp.fetch(syms)
    rows_4h = {}
    for s in syms:
        try:
            rows_4h[s] = detlib.load_ohlcv(s, "4h")
        except (FileNotFoundError, RuntimeError):
            continue
    ranked = turnover_rank(rows_4h)
    regmap = rs.build_regime_map()
    mt.REGMAP = regmap
    base = sorted(vp.collect_1d(syms) + vp.collect_4h(rows_4h, ranked, regmap), key=lambda t: t["t_in"])
    print(f"거래 {len(base)}")
    real = {c: run_cell(base, c) for c in cells()}
    for c in cells():
        r = real[c]
        print(f"  실현 [{c[0]*100:.1f}%] CAGR {r['cagr']*100:+.1f}% MDD {r['mdd']*100:.1f}% Calmar {_cal(r):.2f}", flush=True)
    dist = {b: {c: [] for c in cells()} for b in BLOCKS}
    rng = random.Random(SEED)
    for b in BLOCKS:
        for _ in range(BOOT_N):
            bt = _reassign(base, boot_index(base, b, rng))
            bt.sort(key=lambda t: t["t_in"])
            for c in cells():
                dist[b][c].append(run_cell(bt, c))
        print(f"  부트 {b} 완료", flush=True)
    summ = {}
    for b in BLOCKS:
        for c in cells():
            rs_ = dist[b][c]
            cg = [x["cagr"] for x in rs_]
            md = [x["mdd"] for x in rs_]
            cl = [_cal(x) for x in rs_]
            summ[(b, c)] = dict(q_cagr=percentile_le(cg, real[c]["cagr"]), q_mdd=sum(m <= real[c]["mdd"] for m in md) / len(md),
                                cagr_med=st.median(cg), mdd_med=st.median(md), calmar_med=st.median(cl))
            s = summ[(b, c)]
            print(f"  [{b} {c[0]*100:.1f}%] 실현 CAGR 분위 {s['q_cagr']:.1%} · MDD 분위(<=실현) {s['q_mdd']:.1%} · "
                  f"중앙 CAGR {s['cagr_med']*100:+.1f}% MDD {s['mdd_med']*100:.1f}% Calmar {s['calmar_med']:.2f}")
    verdict = classify(summ[("B20", CURRENT)]["q_cagr"], summ[("T7", CURRENT)]["q_cagr"],
                       summ[("B20", CURRENT)]["calmar_med"], summ[("T7", CURRENT)]["calmar_med"])
    print(f"\n판정: {verdict}")
    json.dump(dict(prereg="path_tail_prereg_2026_11_01", verdict=verdict,
                   real={f"{c[0]}": {k: v for k, v in real[c].items() if k != "took"} for c in cells()},
                   summary={f"{b}_{c[0]}": summ[(b, c)] for b in BLOCKS for c in cells()}),
              open("_path_tail.json", "w"), indent=1, ensure_ascii=False, default=str)


if __name__ == "__main__":
    main()
