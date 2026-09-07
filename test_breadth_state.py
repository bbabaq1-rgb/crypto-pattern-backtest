"""validate_breadth_state 고정 — 동결 파라미터·런 길이 규칙·인과성·빠른 피처가 xsec_features 와 값 동일·판정 규칙·실거래 무변경.
실행: python test_breadth_state.py"""
import json
import random
import statistics as st
from datetime import date, timedelta

import validate_breadth_state as bsm
import validate_episode_profile as ve
import xsec_features as xf

fails = []
def check(n, c, d=""):
    print(("PASS " if c else "FAIL ") + n + ("" if c else f" — {d}")); c or fails.append(n)

# ── 1. 동결 ──────────────────────────────────────────────────────────────────────────────
check("임계 격자 (.4,.5,.6,.7) 주 .5 · 이탈허용 5 · 표집 5 · 지평 60(진단 20/120) · 분할 2023-01-01 · 부트 2000 · α .05",
      bsm.THR_GRID == (0.40, 0.50, 0.60, 0.70) and bsm.THR_PRIMARY == 0.50 and bsm.DIP_TOL == 5 and bsm.SAMPLE_STEP == 5
      and bsm.FWD_PRIMARY == 60 and bsm.FWD_DIAG == (20, 120) and bsm.SPLIT_DATE == "2023-01-01" and bsm.BOOT_N == 2000 and bsm.ALPHA == 0.05)
check("런 버킷 1-10/11-30/31-60/61-120/121+ · 수준 버킷 4", bsm.RUN_BUCKETS[:4] == ((1, 10), (11, 30), (31, 60), (61, 120))
      and bsm.RUN_BUCKETS[4][0] == 121 and len(bsm.SHARE_BUCKETS) == 4 and bsm.SHARE_BUCKETS[0] == (0.50, 0.60))
check("폭 정의는 에피소드 판과 같은 MA180·최소 15", bsm.BREADTH_MA == ve.BREADTH_MA == 180 and bsm.MIN_CS == ve.BREADTH_MIN_COINS == 15)
check("BROAD/DEFENSIVE 부호가 에피소드 전향 시험과 동일", dict(bsm.BROAD) == {"rvol20": 1, "age_bars": -1, "max_dd_1y": -1, "turnover_30d": -1, "mom_6m": -1, "bb_squeeze": 1}
      and dict(bsm.DEFENSIVE) == {"rvol20": -1, "beta_btc_60": -1, "max_dd_1y": 1, "age_bars": 1})
check("배포 반영 없음", bsm.DEPLOY_ON_PASS is False)
reg = json.load(open("registry.json", encoding="utf-8"))["breadth_state_prereg_2026_09_07"]
fp = reg["frozen"]
check("registry 사전 등록과 일치", fp["thr_primary"] == 0.50 and fp["dip_tol"] == 5 and fp["fwd"] == 60 and fp["split"] == "2023-01-01"
      and fp["sample_step"] == 5 and fp["run_buckets"] == [list(b) for b in bsm.RUN_BUCKETS] and reg["deploy_on_pass"] is False)
check("registry 가 프로필 부호를 에피소드 판에서 가져왔음을 명시", "episode_profile_breadth_prereg_2026_09_07" in reg["profile_source"])

# ── 2. 런 길이 규칙 ──────────────────────────────────────────────────────────────────────
def mk(closes, start="2020-01-01", vols=None):
    d0 = date.fromisoformat(start); out = []
    for i, c in enumerate(closes):
        o = closes[i - 1] if i else c
        out.append(dict(date=(d0 + timedelta(days=i)).isoformat(), ts=None, o=o, h=max(o, c) * 1.01, l=min(o, c) * 0.99, c=c, v=(vols[i] if vols else 100.0)))
    return out
# 20 코인 중 정확히 k 개가 MA180 위가 되도록: 앞 200일 평탄, 이후 일부만 상승
N, FLAT = 20, 260
def coin(rise_from):
    cl = [100.0] * FLAT
    for i in range(FLAT, 900):
        cl.append(cl[-1] * (1.01 if (rise_from is not None and i >= rise_from) else 1.0))
    return mk(cl)
rows = {f"c{k}": coin(FLAT + 20 if k < 12 else None) for k in range(N)}   # 12/20 = 60% 가 상승
state = bsm.breadth_state(rows, 0.5)
ds = sorted(state)
first_on = next(d for d in ds if state[d]["run_len"] == 1)
check("런 시작: 폭이 임계를 처음 넘는 날 run_len=1", state[first_on]["share"] >= 0.5 and state[ds[ds.index(first_on) - 1]]["run_len"] == 0)
check("런 지속: 연속 날짜에 run_len 이 1씩 증가", [state[d]["run_len"] for d in ds[ds.index(first_on):ds.index(first_on) + 5]] == [1, 2, 3, 4, 5])
check("run_max 는 런 안 최대 폭, 런 밖은 None", state[ds[-1]]["run_max"] is not None and state[ds[0]]["run_len"] == 0 and state[ds[0]]["run_max"] is None)
check("n_up 은 개수, n_tot 는 계산 대상 수", state[ds[-1]]["n_up"] == 12 and state[ds[-1]]["n_tot"] == 20)
# 이탈 허용: 합성 폭 시계열로 직접 확인
class FakeVE:
    pass
import types
def fake_series(share_seq, start="2021-01-01"):
    d0 = date.fromisoformat(start)
    return {(d0 + timedelta(days=i)).isoformat(): (v, 20) for i, v in enumerate(share_seq)}
orig = ve.breadth_series
seq = [0.6] * 10 + [0.2] * 5 + [0.6] * 10 + [0.2] * 6 + [0.6] * 10      # 5일 이탈은 유지, 6일 이탈은 끊김
ve.breadth_series = lambda r, ma=None, min_coins=None: fake_series(seq)
try:
    s2 = bsm.breadth_state({}, 0.5)
finally:
    ve.breadth_series = orig
d2 = sorted(s2)
check("이탈 5일(허용)은 런 유지 — 재개일 run_len 이 이어짐", s2[d2[15]]["run_len"] == 16 and s2[d2[24]]["run_len"] == 25)
check("이탈 6일은 런 끊김 — 재개일 run_len=1, 블록 id 증가", s2[d2[31]]["run_len"] == 1 and s2[d2[31]]["block"] > s2[d2[24]]["block"])
check("이탈 중에도 run_len 은 달력일수로 증가(끊기기 전까지)", s2[d2[12]]["run_len"] == 13)
check("버킷 배정", bsm.bucket_of(1, bsm.RUN_BUCKETS) == 0 and bsm.bucket_of(10, bsm.RUN_BUCKETS) == 0 and bsm.bucket_of(11, bsm.RUN_BUCKETS) == 1
      and bsm.bucket_of(120, bsm.RUN_BUCKETS) == 3 and bsm.bucket_of(121, bsm.RUN_BUCKETS) == 4 and bsm.bucket_of(0, bsm.RUN_BUCKETS) is None)

# ── 3. 빠른 피처가 xsec_features 와 값이 같은가 (핵심) ─────────────────────────────────────
rng = random.Random(11)
def rw(n, start="2018-01-01"):
    cl = [100.0]
    for _ in range(n - 1):
        cl.append(max(cl[-1] * (1 + rng.uniform(-0.05, 0.05)), 1e-6))
    return mk(cl, start, vols=[100 + rng.random() * 50 for _ in range(n)])
r1, rb = rw(900), rw(900)
ff = bsm.FastFeatures(r1, rb)
bad = []
for i in (300, 420, 555, 700, 899):
    fast, slow = ff.at(i), xf.all_at(xf.FeatureSeries(r1, rb), i)
    for k in bsm.FEATS:
        a, b = fast.get(k), slow.get(k)
        if (a is None) != (b is None) or (a is not None and abs(a - b) > 1e-9):
            bad.append((i, k, a, b))
check("FastFeatures 7종이 xsec_features.all_at 과 값 동일(5개 인덱스)", not bad, str(bad[:3]))
check("bb_squeeze 사전계산이 이력 부족 구간에서 None", ff.at(100)["bb_squeeze"] is None and ff.at(899)["bb_squeeze"] is not None)
check("fast_features 는 심볼당 인스턴스 하나를 재사용", bsm.fast_features("Z", r1, rb) is bsm.fast_features("Z", r1, rb))
check("max_dd_1y 캐시가 값을 바꾸지 않음", ff._max_dd(600) == ff._max_dd(600) == xf.all_at(xf.FeatureSeries(r1, rb), 600)["max_dd_1y"])
check("max_dd_1y 는 252봉 전 None, 이후 <= 0", ff.at(200)["max_dd_1y"] is None and ff.at(600)["max_dd_1y"] <= 0)
alt = [dict(x) for x in r1]
for x in alt[601:]:
    x["c"] *= 4; x["h"] *= 4; x["l"] *= 4
f_alt = bsm.FastFeatures(alt, rb).at(600)
check("인과성: 미래 봉 변경에 600 인덱스 피처 불변", all((ff.at(600)[k] is None) == (f_alt[k] is None) and (ff.at(600)[k] is None or abs(ff.at(600)[k] - f_alt[k]) < 1e-9) for k in bsm.FEATS))

# ── 4. 프로필 점수 ────────────────────────────────────────────────────────────────────────
items = [(f"c{k}", {"rvol20": k / 10, "age_bars": float(100 - k), "max_dd_1y": -k / 10, "turnover_30d": float(-k),
                    "mom_6m": -k / 10, "bb_squeeze": float(k), "beta_btc_60": 1.0 - k / 100}) for k in range(20)]
sb = bsm.profile_score(items, bsm.BROAD)
check("BROAD 점수: 전 변수가 같은 방향으로 정렬된 합성 자료에서 순위와 일치", sb["c19"] == max(sb.values()) and sb["c0"] == min(sb.values()))
sd = bsm.profile_score(items, bsm.DEFENSIVE)
check("DEFENSIVE 는 반대쪽 코인을 높게", sd["c0"] > sd["c19"])
check("결측 있는 코인 제외 · 코인 15 미만이면 빈 dict", bsm.profile_score(items[:10], bsm.BROAD) == {}
      and "cX" not in bsm.profile_score(items + [("cX", {"rvol20": 1.0})], bsm.BROAD))

# ── 5. 통계·판정 ─────────────────────────────────────────────────────────────────────────
recs_pos = [dict(block=b, v=0.02 + 0.001 * i) for b in range(8) for i in range(20)]
bb = bsm.block_boot(recs_pos, "v")
check("블록 부트: 전부 양수면 p=0, 블록 수 집계", bb["p"] == 0.0 and bb["blocks"] == 8 and bb["mean"] > 0)
check("전부 음수면 p=1", bsm.block_boot([dict(block=b, v=-0.01) for b in range(6) for _ in range(5)], "v")["p"] == 1.0)
check("한 블록에 몰린 자료는 블록 1개로 잡혀 CI 가 넓다", bsm.block_boot([dict(block=1, v=0.05) for _ in range(50)], "v")["blocks"] == 1)
check("단조 판정", bsm.nondecreasing([1, 1, 2, 3]) and not bsm.nondecreasing([1, 3, 2]) and bsm.nondecreasing([None, 1, 2]))
def synth(run_lens, ic_b, ic_d, uni, date0="2019-01-01", block0=0):
    d0 = date.fromisoformat(date0); out = []
    for i, rl in enumerate(run_lens):
        out.append(dict(date=(d0 + timedelta(days=i * 5)).isoformat(), block=block0 + i // 10, share=0.6, n_up=30, run_len=rl,
                        run_max=0.7, slope20=0.1, n=30, uni_fwd=uni(rl), up_fwd=0.6, ic_broad=ic_b(rl), ic_def=ic_d(rl)))
    return out
rl_seq = [1 + (i % 200) for i in range(600)]
good = synth(rl_seq, lambda r: 0.05 + r / 2000, lambda r: 0.05 - r / 2000, lambda r: 0.01 + r / 5000)
good += synth(rl_seq, lambda r: 0.05 + r / 2000, lambda r: 0.05 - r / 2000, lambda r: 0.01 + r / 5000, date0="2024-01-01", block0=100)
j = bsm.judge(good)
check("H1·H2 성립 자료 → RULE_CANDIDATE", j["verdict"] == "RULE_CANDIDATE" and j["h1_train"] and j["h2_train"] and j["oos_sign"])
flat = synth(rl_seq, lambda r: 0.0, lambda r: 0.0, lambda r: 0.0) + synth(rl_seq, lambda r: 0.0, lambda r: 0.0, lambda r: 0.0, date0="2024-01-01", block0=100)
check("무신호 자료 → NONE", bsm.judge(flat)["verdict"] == "NONE")
oos_bad = synth(rl_seq, lambda r: 0.05 + r / 2000, lambda r: 0.05 - r / 2000, lambda r: 0.01 + r / 5000)
oos_bad += synth(rl_seq, lambda r: -0.05, lambda r: 0.05, lambda r: -0.02, date0="2024-01-01", block0=100)
check("train 만 통과하고 OOS 부호 반대 → SUGGESTIVE", bsm.judge(oos_bad)["verdict"] == "SUGGESTIVE")
check("판정에 쓰는 건 run_len>=1 인 날뿐(런 밖 제외)", bsm.judge(good + [dict(good[0], run_len=0, ic_broad=-9.0, uni_fwd=-9.0)])["verdict"] == "RULE_CANDIDATE")

# ── 6. 무변경·등재 ────────────────────────────────────────────────────────────────────────
src = open("validate_breadth_state.py", encoding="utf-8").read()
check("실거래·배포 코드 없음", "import paper_executor" not in src and "import scheduler" not in src and "adopted_" not in src and "ROUTING_OVERRIDES" not in src)
sched = open("scheduler.py", encoding="utf-8").read() + open("paper_executor.py", encoding="utf-8").read()
check("스케줄러·실행기가 이 모듈을 읽지 않음", "validate_breadth_state" not in sched)
wf = open(".github/workflows/breadth_state.yml", encoding="utf-8").read()
check("워크플로: data-long 체크아웃 + 테스트 선행 + 실행", "data-long" in wf and "python test_breadth_state.py" in wf and "python validate_breadth_state.py" in wf)
check("tests.yml 등재", "test_breadth_state.py" in open(".github/workflows/tests.yml", encoding="utf-8").read())

print(f"\n{'ALL PASS' if not fails else 'FAILED: ' + ', '.join(fails)} ({len(fails)} fail)")
import sys; sys.exit(1 if fails else 0)
