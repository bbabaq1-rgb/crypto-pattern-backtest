"""
확인 프레임 v3(frame_v3) 고정 — 2026-09-06 사용자 결정.

확인 대상:
  - episodes: 레짐 연속 구간 병합(gap 이하 끊김 병합), ALL 은 달력 연도
  - holdout_dates: 국면 일수 기준 최근 365일(비연속), 부족하면 뒤쪽 절반, ALL 은 달력 365일
  - split / episode_table / episode_oos (적격 n>=5, 양수 >=2 이며 과반)
  - judge 판정 우선순위: 성능 실패 → REJECTED / 커버리지 부족 → INCONCLUSIVE / E 실패 → REJECTED / CONFIRMED
  - MA180 형 시나리오: 달력 홀드아웃(bear 해)엔 신호 6건이지만 국면 홀드아웃엔 충분 → 판정 가능
  - 동결 상수 · 실거래 코드 미import · regime_switch.build_regime_map(rows_by=) 후방호환 · load_ohlcv_long 접합 규칙

실행: python test_frame_v3.py
"""
import csv
import gzip
import os
import random
import sys
import tempfile
from datetime import date, timedelta

import frame_v3 as fv

fails = []


def check(n, c, d=""):
    print(("PASS " if c else "FAIL ") + n + ("" if c else f" — {d}"))
    c or fails.append(n)


def days(start, n):
    d0 = date.fromisoformat(start)
    return [(d0 + timedelta(days=i)).isoformat() for i in range(n)]


# ── 1. 에피소드 ─────────────────────────────────────────────────────────────
# bull 100일 / bear 200일 / bull 5일 깜빡임(bear 10일 뒤) / bear 60 / bull 120 / bear 400 / bull 150 / bear 300
seq = (["bull_btc"] * 100 + ["bear"] * 200 + ["bull_btc"] * 5 + ["bear"] * 10 + ["bull_btc"] * 60
       + ["bear"] * 400 + ["bull_btc"] * 150 + ["bear"] * 400)      # 마지막 400일 bear = MA180 상황
dl = days("2020-01-01", len(seq))
regmap = dict(zip(dl, seq))
eps = fv.episodes(regmap, "bull_btc")
check("에피소드: 10일 끊김은 병합(gap 30) → bull 3개", len(eps) == 3, eps)
check("에피소드: 첫 구간 100일", eps[0] == (dl[0], dl[99]))
check("에피소드: 200일 bear 는 병합 안 됨", eps[1][0] == dl[300])
check("ALL 은 달력 연도", fv.episodes(regmap, "ALL")[0] == ("2020-01-01", "2020-12-31") and len(fv.episodes(regmap, "ALL")) == 4)
check("없는 레짐은 빈 목록", fv.episodes(regmap, "sideways") == [])

# ── 2. 홀드아웃 ─────────────────────────────────────────────────────────────
hs = fv.holdout_dates(regmap, "bull_btc")
bull_days = [d for d in dl if regmap[d] == "bull_btc"]      # 315일 < 730 → 뒤쪽 절반 157일
check("국면 홀드아웃: 총 315 bull 일 < 730 → 뒤쪽 절반(157)", len(hs) == 157, len(hs))
check("국면 홀드아웃은 bull 날짜만·가장 최근", hs == set(bull_days[-157:]))
check("국면 홀드아웃은 달력상 비연속(마지막 bull 구간 150 + 앞 구간 7)", min(hs) < dl[-550])
long_seq = ["bull_btc"] * 900 + ["bear"] * 100
lm = dict(zip(days("2018-01-01", 1000), long_seq))
check("bull 900일이면 홀드아웃 = 최근 365 bull 일", len(fv.holdout_dates(lm, "bull_btc")) == 365)
ha = fv.holdout_dates(regmap, "ALL")
check("ALL 은 달력 마지막 365일(v2 동일)", len(ha) == 365 and max(ha) == dl[-1])


def sig(d, ret):
    return dict(date=d, ret=ret, hold=5, reason="target", stop_pct=0.08, vol=0.8, exit_date=d, t_in=0.0, t_out=1.0)


# ── 3. 에피소드 OOS ─────────────────────────────────────────────────────────
ep_sigs = [sig(dl[i], 0.05) for i in range(0, 60, 10)] + [sig(dl[300 + i], -0.03) for i in range(0, 60, 10)] \
    + [sig(dl[775 + i], 0.06) for i in range(0, 60, 10)]
tab = fv.episode_table(ep_sigs, eps)
check("에피소드 표: 3구간 각 n=6, 적격", all(r["n"] == 6 and r["qualifying"] for r in tab), tab)
ok, q, pos, share = fv.episode_oos(ep_sigs, eps)
check("E: 적격 3, 양수 2 → 과반 통과", ok and q == 3 and pos == 2)
check("E: 최대 비중 = 양수 이익 중 최댓값 비율", share is not None and 0.5 < share < 0.6, share)
ok2, *_ = fv.episode_oos([sig(dl[i], 0.05) for i in range(0, 60, 10)], eps)
check("E: 적격 에피소드 1개면 실패", not ok2)
ok3, q3, pos3, _ = fv.episode_oos(ep_sigs[:6] + [sig(dl[300 + i], -0.03) for i in range(0, 60, 10)]
                                  + [sig(dl[775 + i], -0.02) for i in range(0, 60, 10)], eps)
check("E: 양수 1/3 → 실패", not ok3 and q3 == 3 and pos3 == 1)

# ── 4. judge 시나리오 ────────────────────────────────────────────────────────
eq_ok = lambda tr, span: dict(cagr=0.2, mdd=-0.1, calmar=2.0)
pool = [-0.02] * 300
rng = random.Random(1)
# 좋은 셀: bull 3구간 전부 양수, 국면 홀드아웃(뒤 157일)에 12건 이상, train 넉넉
good = []
for a, b in eps:
    ds = [d for d in dl if a <= d <= b]
    for d in ds[::4]:
        good.append(sig(d, 0.08 if rng.random() < 0.6 else -0.04))
j = fv.judge(good, pool, regmap, "bull_btc", eq_ok)
check("judge: 좋은 셀 → CONFIRMED", j["verdict"] == "CONFIRMED", (j["verdict"], j["c1"]["fails"], j["E"], j["holdout"], j["train"]["n"]))
check("judge: holdout n 이 국면 홀드아웃 안 신호 수", j["holdout"]["n"] == sum(1 for s in good if s["date"] in hs))
check("judge: frame 표기·에피소드 표 포함", j["frame"] == "v3" and len(j["episodes"]) == 3)

# MA180 형: bull 셀인데 마지막 달력 365일이 bear 지배. 달력 홀드아웃엔 신호 6건 → v2 는 n<10 탈락.
# v3 국면 홀드아웃은 마지막 bull 구간(150일)을 통째로 포함해 n 이 충분하다.
cal_hold = set(dl[-365:])
ma = [s for s in good]
n_cal = sum(1 for s in ma if s["date"] in cal_hold)
check("MA180 형: 달력 홀드아웃 신호 수 < 10 (v2 판정 불가 상황 재현)", n_cal < 10, n_cal)
check("MA180 형: 국면 홀드아웃 신호 수 >= 10", sum(1 for s in ma if s["date"] in hs) >= 10)

# 성능 실패 → REJECTED (커버리지 부족이어도 REJECTED 가 우선)
bad = [sig(d, -0.05) for d in bull_days[::3]]
jb = fv.judge(bad, pool, regmap, "bull_btc", eq_ok)
check("judge: 평균 음수 → REJECTED", jb["verdict"] == "REJECTED" and not jb["c1_perf"])

# 커버리지 부족 → INCONCLUSIVE: 에피소드 1개뿐인 regmap
one = dict(zip(days("2023-01-01", 800), ["bull_btc"] * 400 + ["bear"] * 400))
one_sigs = [sig(d, 0.08 if rng.random() < 0.6 else -0.04) for d in days("2023-01-01", 400)[::5]]
jo = fv.judge(one_sigs, pool, one, "bull_btc", eq_ok)
check("judge: 성능 통과·적격 에피소드 1 → INCONCLUSIVE (기각 아님)", jo["verdict"] == "INCONCLUSIVE" and jo["c1_perf"], (jo["verdict"], jo["E"]))

# E 실패(양수 에피소드 1/3) but 성능·커버리지 통과 → REJECTED
mixed = []
for k, (a, b) in enumerate(eps):
    ds = [d for d in dl if a <= d <= b]
    for d in ds[::3]:
        mixed.append(sig(d, (0.12 if rng.random() < 0.7 else -0.04) if k == 2 else (0.03 if rng.random() < 0.35 else -0.04)))
jm = fv.judge(mixed, pool, regmap, "bull_btc", eq_ok)
check("judge: 한 에피소드 의존(양수 1/3) → E 실패 → REJECTED", jm["verdict"] == "REJECTED" and not jm["E"]["ok"] and jm["coverage"],
      (jm["verdict"], jm["E"], jm["c1"]["fails"], jm["holdout"]))

# C3 실패 → REJECTED
jc = fv.judge(good, pool, regmap, "bull_btc", lambda tr, span: dict(cagr=-0.1, mdd=-0.3, calmar=-0.3))
check("judge: 자산곡선 음수 → REJECTED", jc["verdict"] == "REJECTED" and not jc["c3_equity"])
check("train span: 홀드아웃 일수를 뺀 달력 폭", fv.train_span_days([sig(dl[0], 0), sig(dl[999], 0)], set(dl[100:200])) == 999 - 100)

# ── 5. 동결 상수 · 격리 ─────────────────────────────────────────────────────
check("동결 상수: gap 30 / holdout 365 / min n 10 / 적격 5 / train 비율 0.5", fv.EPISODE_GAP == 30 and fv.HOLDOUT_DAYS == 365
      and fv.HOLDOUT_MIN_N == 10 and fv.EP_MIN_N == 5 and fv.TRAIN_MIN_RATIO == 0.5)
src = open("frame_v3.py", encoding="utf-8").read()
check("frame_v3 는 실거래 코드 미import", "paper_executor" not in src and "import scheduler" not in src)
check("프레임 문서에 판정 우선순위·4년주기 비가정 명시", "INCONCLUSIVE" in src and "4년 주기" in src)

# ── 6. 후방호환 — build_regime_map(rows_by=) · load_ohlcv_long 접합 ───────────
import inspect
import regime_switch as rs
import detlib
sig_rs = inspect.signature(rs.build_regime_map)
check("build_regime_map 은 rows_by 를 선택 인자로 받고 기본값 None(스케줄러 호출 불변)",
      "rows_by" in sig_rs.parameters and sig_rs.parameters["rows_by"].default is None)
check("validate_regime_split_all.load_tf(long=False) 기본", inspect.signature(__import__("validate_regime_split_all").load_tf).parameters["long"].default is False)

tmp = tempfile.mkdtemp()
cwd = os.getcwd()
try:
    os.chdir(tmp)
    os.makedirs("data"); os.makedirs("data_long")
    def wcsv(path, rows, gz=False):
        op = (lambda p: gzip.open(p, "wt", newline="")) if gz else (lambda p: open(p, "w", newline=""))
        with op(path) as f:
            w = csv.writer(f); w.writerow(["timestamp", "datetime", "open", "high", "low", "close", "volume"])
            for ts, c in rows:
                w.writerow([ts, "", c, c, c, c, 1])
    day = 86_400_000
    t0 = 1_600_000_000_000
    wcsv("data_long/zzz_1d.csv.gz", [(t0 + i * day, 1.0 + i) for i in range(10)], gz=True)     # 0..9
    wcsv("data/zzz_1d.csv", [(t0 + i * day, 100.0 + i) for i in range(6, 12)])                  # 6..11 (OKX)
    rows = detlib.load_ohlcv_long("ZZZ")
    check("접합: 장기 0~5 + OKX 6~11 = 12봉, 겹침은 OKX 값", len(rows) == 12 and rows[5]["c"] == 6.0 and rows[6]["c"] == 106.0)
    check("접합: 날짜 단조 증가", all(rows[i]["date"] < rows[i + 1]["date"] for i in range(len(rows) - 1)))
    os.remove("data/zzz_1d.csv")
    detlib._fetch_failed.add(("ZZZ", "1d")) if hasattr(detlib, "_fetch_failed") else None
    try:
        rows2 = detlib.load_ohlcv_long("ZZZ")
        check("접합: OKX 없으면 장기만", len(rows2) == 10)
    except Exception as e:
        check("접합: OKX 없으면 장기만", False, str(e)[:80])
finally:
    os.chdir(cwd)

print(f"\n{len(fails)} failed")
sys.exit(1 if fails else 0)
