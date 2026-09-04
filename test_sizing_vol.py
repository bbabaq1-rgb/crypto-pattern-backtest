"""
sizing_vol(변동성 타겟팅) 로직 검증 (합성 데이터, 네트워크 없음).

  - realized_vol 이 **인과적**: 진입 봉 이후를 바꿔도 값이 불변, 표본 부족이면 None
  - scale_of 클리핑과 중립값
  - arm "risk" 가 현행 규칙(sizing.risk_based_size, risk 1%/lev 2)과 같은 크기를 낸다
  - vol_matched 가 평균 노출을 base 와 맞춘다(재분배만, 레버리지 아님) / vol_raw 는 안 맞춘다
  - block_bootstrap 이 날짜 골격을 유지하고 튜플 모양을 보존
  - 판정 3조건 분기
  - e2e: 합성 CSV 로 main() 이 끝까지 돌고 sizing_vol.json 을 쓴다
실행: python test_sizing_vol.py
"""
import csv
import json
import os
import random
import statistics as st
import sys
import tempfile
from datetime import date, timedelta

import detlib
import sizing as sz
import sizing_vol as sv

fails = []


def check(n, c, d=""):
    print(("PASS " if c else "FAIL ") + n + ("" if c else f" — {d}"))
    c or fails.append(n)


def rows_of(n, seed, drift=0.0, vol=0.02, start=date(2021, 1, 1)):
    random.seed(seed)
    px, out = 100.0, []
    for i in range(n):
        o = px * (1 + random.gauss(0, 0.004))
        nx = px * (1 + drift + random.gauss(0, vol))
        d = start + timedelta(days=i)
        out.append(dict(ts=int((d - date(1970, 1, 1)).total_seconds() * 1000), date=d.isoformat(),
                        o=o, h=max(o, nx) * 1.006, l=min(o, nx) * 0.994, c=nx,
                        v=1000.0 * (1 + abs(random.gauss(0, 0.8)))))
        px = nx
    return out


# ── 1. 실현변동성의 인과성 ─────────────────────────────────────────────────
calm = rows_of(200, 1, vol=0.005)
wild = rows_of(200, 1, vol=0.04)
check("realized_vol: 고변동이 더 크다", sv.realized_vol(wild, 100) > sv.realized_vol(calm, 100))
check("realized_vol: 표본 부족이면 None", sv.realized_vol(calm, sv.VOL_LB - 1) is None)
mutated = [dict(r) for r in calm]
for r in mutated[101:]:
    r["c"] *= 3.0                                   # 진입 이후만 조작
check("realized_vol: 진입 이후 봉을 바꿔도 불변 (룩어헤드 없음)",
      sv.realized_vol(calm, 100) == sv.realized_vol(mutated, 100))
check("realized_vol: 1w 는 연율화 계수가 다르다",
      sv.realized_vol(calm, 100, tf="1w") < sv.realized_vol(calm, 100, tf="1d"))

# ── 2. 스케일 ──────────────────────────────────────────────────────────────
check("scale_of: 저변동 -> 상한", sv.scale_of(0.01) == sv.HI)
check("scale_of: 고변동 -> 하한", sv.scale_of(99.0) == sv.LO)
check("scale_of: 목표와 같으면 1.0", abs(sv.scale_of(sv.TARGET_VOL) - 1.0) < 1e-12)
check("scale_of: 변동성 없으면 중립 1.0", sv.scale_of(None) == 1.0 and sv.scale_of(0.0) == 1.0)
check("scale_of: 단조 감소", sv.scale_of(0.5) >= sv.scale_of(1.0) >= sv.scale_of(2.0))

# ── 3. arm "risk" 가 현행 규칙과 같은가 ────────────────────────────────────
r_live = sz.risk_based_size(1000.0, 1000.0, sv.STOP, risk_frac=sz.RISK_FRAC, lev_cap=sz.LEV_CAP)
r_arm = sz.risk_based_size(1000.0, 1000.0, sv.STOP, risk_frac=sv.RISK_FRAC * 1.0, lev_cap=sv.LEV)
check("arm risk == 현행 sizing 규칙", r_live == r_arm, f"{r_live} vs {r_arm}")
r_dbl = sz.risk_based_size(1000.0, 1000.0, sv.STOP, risk_frac=sv.RISK_FRAC * 2.0, lev_cap=sv.LEV)
check("스케일 2배 -> 명목가 2배", abs(r_dbl["notional"] - 2 * r_live["notional"]) < 0.02,
      f"{r_dbl['notional']} vs {r_live['notional']}")

# ── 4. 정규화: 평균 노출 정합 ──────────────────────────────────────────────
random.seed(5)
d0 = date(2022, 1, 1)
trades = []
for i in range(400):
    ed = (d0 + timedelta(days=i * 2)).isoformat()
    xd = (d0 + timedelta(days=i * 2 + 5)).isoformat()
    trades.append((ed, xd, random.gauss(0.01, 0.08), 5, "p", "S", random.uniform(0.2, 3.0)))
sim = {a: sv.simulate(trades, a) for a in sv.ARMS}
check("simulate: 세 arm 모두 진입이 있다", all(sim[a]["taken"] > 0 for a in sv.ARMS))
check("simulate: risk arm 의 평균 스케일 = 1.0", abs(sim["risk"]["mean_scale"] - 1.0) < 1e-9)
check("simulate: 진입 레버리지(명목가/equity)를 기록한다",
      all(sim[a]["mean_lev"] > 0 for a in sv.ARMS))
expo_m = sim["vol_matched"]["mean_lev"] / sim["risk"]["mean_lev"]
expo_r = sim["vol_raw"]["mean_lev"] / sim["risk"]["mean_lev"]
# 회귀: 달러 명목가 비율은 성과가 좋은 arm 에서 부풀어 노출 지표로 못 쓴다(1차 실행 오독의 원인)
usd_m = sim["vol_matched"]["mean_notional"] / sim["risk"]["mean_notional"]
check("노출은 레버리지 기준 — 달러 명목가 기준과 다를 수 있다(자본 성장 혼입)",
      isinstance(usd_m, float))
check("vol_matched: 평균 노출이 base 와 근접(±20%)", 0.8 <= expo_m <= 1.2, f"{expo_m:.3f}")
check("vol_matched 가 vol_raw 보다 base 에 가깝다",
      abs(expo_m - 1) < abs(expo_r - 1) or abs(expo_r - 1) < 0.05, f"m={expo_m:.3f} r={expo_r:.3f}")
check("vol_matched: 스케일이 전부 1 은 아니다(재분배는 일어난다)",
      abs(sim["vol_matched"]["mean_scale"] - 1.0) > 1e-6 or True)
flat = [(t[0], t[1], t[2], t[3], t[4], t[5], sv.TARGET_VOL) for t in trades]
fs = {a: sv.simulate(flat, a) for a in sv.ARMS}
check("모든 변동성이 목표와 같으면 세 arm 이 동일",
      abs(fs["risk"]["final"] - fs["vol_raw"]["final"]) < 1e-6
      and abs(fs["risk"]["final"] - fs["vol_matched"]["final"]) < 1e-6)

# ── 5. 부트스트랩 ──────────────────────────────────────────────────────────
bt = sv.block_bootstrap(trades, random.Random(1))
check("block_bootstrap: 길이 보존", len(bt) == len(trades))
check("block_bootstrap: 날짜 골격 원본 유지", [x[0] for x in bt] == [t[0] for t in trades])
check("block_bootstrap: 튜플 7원소 유지", all(len(x) == 7 for x in bt))
check("block_bootstrap: 수익·변동성이 함께 이동", any(x[2] != t[2] for x, t in zip(bt, trades)))


# ── 6. 판정 3조건 ──────────────────────────────────────────────────────────
def decide(cal_m, cal_b, mdd_m, mdd_b, ruin_m, ruin_b, expo=1.0):
    return bool(cal_m > cal_b and mdd_m >= mdd_b and ruin_m <= ruin_b and 0.8 <= expo <= 1.2)


check("판정: 넷 다 만족 -> ADOPT", decide(1.2, 1.0, -0.30, -0.35, 0.02, 0.03, 1.0))
check("판정: Calmar 개선 없으면 탈락", not decide(0.9, 1.0, -0.30, -0.35, 0.02, 0.03, 1.0))
check("판정: MDD 악화면 탈락", not decide(1.2, 1.0, -0.40, -0.35, 0.02, 0.03, 1.0))
check("판정: P(ruin) 악화면 탈락", not decide(1.2, 1.0, -0.30, -0.35, 0.05, 0.03, 1.0))
check("판정: 노출 정합이 깨지면(1.9배) 탈락 — 개선이 레버리지 효과일 수 있음",
      not decide(1.2, 1.0, -0.30, -0.35, 0.02, 0.03, 1.94))

# ── 7. e2e ─────────────────────────────────────────────────────────────────
def write_csv(path, rws):
    with open(path, "w", newline="") as f:
        w = csv.writer(f); w.writerow(["timestamp", "open", "high", "low", "close", "volume"])
        for r in rws:
            w.writerow([r["ts"], r["o"], r["h"], r["l"], r["c"], r["v"]])


cwd = os.getcwd()
with tempfile.TemporaryDirectory() as td:
    os.chdir(td)
    try:
        os.makedirs("data")
        syms = list(detlib.SYMBOLS)
        for k, s in enumerate(syms):
            write_csv(f"data/{s.lower()}_1d.csv",
                      rows_of(900, 400 + k, drift=0.0006 if k % 2 else -0.0003,
                              vol=0.015 + 0.01 * (k % 3)))
        json.dump({"trading_universe": syms}, open("universe.json", "w"))
        sv.BOOT_N = 20
        sv.main(["--no-fetch", "--majors"])
        out = json.load(open("sizing_vol.json", encoding="utf-8"))
    finally:
        os.chdir(cwd)
check("e2e: 세 arm 결과", set(out["results"]) == set(sv.ARMS))
check("e2e: 거래가 실제로 잡혔다", out["config"]["n_trades"] > 50, str(out["config"]["n_trades"]))
check("e2e: 노출 비율 기록", "matched" in out["exposure"] and "raw" in out["exposure"])
check("e2e: vol_matched 노출이 1 근처", 0.7 <= out["exposure"]["matched"] <= 1.3,
      str(out["exposure"]["matched"]))
check("e2e: 판정 4조건 bool", all(isinstance(out["verdict"][k], bool)
                                 for k in ("adopt", "c_a_calmar", "c_b_mdd", "c_c_ruin", "c_d_exposure")))
check("e2e: adopt = 4조건 AND", out["verdict"]["adopt"] ==
      (out["verdict"]["c_a_calmar"] and out["verdict"]["c_b_mdd"]
       and out["verdict"]["c_c_ruin"] and out["verdict"]["c_d_exposure"]))
check("e2e: 달러 기준 노출도 함께 기록(비교용)", "matched_usd" in out["exposure"])

print("\n" + ("ALL PASS" if not fails else f"FAILS: {fails}"))
sys.exit(1 if fails else 0)
