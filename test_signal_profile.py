"""validate_signal_profile 고정 — 동결 파라미터·주 가족(배포 1d 롱 4셀)·월 부트·3분위 스프레드·판정 규칙·실거래 무변경.
실행: python test_signal_profile.py"""
import json
import random

import validate_guard_v4 as g4
import validate_signal_profile as vs
import xsec_features as xf

fails = []
def check(n, c, d=""):
    print(("PASS " if c else "FAIL ") + n + ("" if c else f" — {d}")); c or fails.append(n)

check("분할 2025-01-01(v4) · 부트 1000 · α .05 · train>=60 · OOS>=20 · 변수 35", vs.SPLIT_DATE == "2025-01-01" and vs.BOOT_N == 1000 and vs.ALPHA == 0.05
      and vs.MIN_TRAIN_N == 60 and vs.MIN_OOS_N == 20 and len(vs.KEYS) == 35)
check("주 가족 = v4 CELLS 의 1d·long·deployed 4셀과 정확히 일치", set(vs.PRIMARY_CIDS) == {c["cid"] for c in g4.CELLS if c["tf"] == "1d" and c["direction"] == "long" and c["status"] == "deployed"})
check("숏 셀은 진단 전용(주 가족 밖)", vs.SHORT_CID not in vs.PRIMARY_CIDS and vs.SHORT_CID in {c["cid"] for c in g4.CELLS})
check("배포 반영 없음", vs.DEPLOY_ON_PASS is False)
reg = json.load(open("registry.json", encoding="utf-8"))["signal_profile_prereg_2026_09_07"]
check("registry 사전 등록과 일치", reg["family_size"] == 35 and reg["primary_cells"] == list(vs.PRIMARY_CIDS) and reg["split"] == vs.SPLIT_DATE)

def synth(n, slope, seed=0, start_month=0):
    r = random.Random(seed); out = []
    for k in range(n):
        f = r.uniform(0, 1)
        m = start_month + k // 8
        out.append(dict(sym=f"c{k%7}", i=100 + k, date=f"{2020 + m // 12}-{m % 12 + 1:02d}-{1 + k % 28:02d}", month=f"{2020 + m // 12}-{m % 12 + 1:02d}",
                        ret=slope * f + r.uniform(-0.05, 0.05), reason=("stop" if f < 0.3 else "hold"), f={"rvol20": f, "dist_ma60": -f}))
    return out
pos = synth(160, 0.5)
mb = vs.month_boot_rho(pos, "rvol20")
check("월 부트: rho > 0.9, p_pos 0, p_neg 1, 월 수 20", mb["rho"] > 0.9 and mb["p_pos"] == 0.0 and mb["p_neg"] == 1.0 and mb["months"] == 20 and mb["n"] == 160)
check("n_boot=0 이면 rho 만(진단용), p None", vs.month_boot_rho(pos, "rvol20", n_boot=0)["p_two"] is None)
null = synth(160, 0.0, seed=4)
check("무관 자료 양측 p > .05", vs.month_boot_rho(null, "rvol20")["p_two"] > 0.05)
sp, good, bad = vs.tercile_spread(pos, "rvol20", "+")
check("3분위 스프레드: 방향 + 면 상위 1/3 − 하위 1/3 > 0, − 면 부호 반전", sp > 0.2 and good > bad and vs.tercile_spread(pos, "rvol20", "-")[0] == -sp)
oos = synth(60, 0.5, seed=7, start_month=61)
for s in oos: s["date"] = "2025-" + s["date"][5:]
rec = vs.judge_var("rvol20", "?", pos, oos); rec["p_holm"] = rec["train_p"]; vs.finalize(rec)
check("'?' 변수: 방향 = train 부호, 양측 p, OOS 재현 → CANDIDATE", rec["dir"] == "+" and rec["train_p"] == vs.month_boot_rho(pos, "rvol20")["p_two"] and rec["verdict"] == "CANDIDATE")
rec2 = vs.judge_var("rvol20", "-", pos, oos); rec2["p_holm"] = rec2["train_p"]; vs.finalize(rec2)
check("지정 부호 − 인데 양의 상관 유의 → NONE + REVERSED", rec2["verdict"] == "NONE" and rec2["reversed"])
rec3 = vs.judge_var("dist_ma60", "-", pos, oos); rec3["p_holm"] = rec3["train_p"]; vs.finalize(rec3)
check("지정 부호 − 와 자료 부호 일치(dist_ma60 = −f) → 단측 p_neg 사용, CANDIDATE", rec3["train_p"] == vs.month_boot_rho(pos, "dist_ma60")["p_neg"] and rec3["verdict"] == "CANDIDATE")
rec4 = vs.judge_var("rvol20", "?", pos, oos[:10]); rec4["p_holm"] = rec4["train_p"]; vs.finalize(rec4)
check("OOS n < 20 → TRAIN_ONLY", rec4["verdict"] == "TRAIN_ONLY")
rec5 = vs.judge_var("rvol20", "?", pos[:40], oos); rec5["p_holm"] = rec5["train_p"]; vs.finalize(rec5)
check("train n < 60 → NONE", rec5["verdict"] == "NONE")
oos_neg = [dict(s, ret=-s["ret"]) for s in oos]
rec6 = vs.judge_var("rvol20", "?", pos, oos_neg); rec6["p_holm"] = rec6["train_p"]; vs.finalize(rec6)
check("OOS 부호 반대 → TRAIN_ONLY", rec6["verdict"] == "TRAIN_ONLY" and rec6["oos_rho_dir"] < 0)
rec7 = vs.judge_var("rvol20", "?", pos, oos); rec7["p_holm"] = 0.3; vs.finalize(rec7)
check("Holm p >= .05 → NONE", rec7["verdict"] == "NONE")
fam = vs.judge_family(pos, oos, keys=["rvol20", "dist_ma60"])
check("가족 판정: Holm 은 g4.holm", fam["rvol20"]["p_holm"] == g4.holm({k: v["train_p"] for k, v in fam.items()})["rvol20"])
check("D2 승자 vs 패자 rb > 0(양의 기울기), D3 손절비율 low 1/3 = 100%", vs.winner_rb(pos, "rvol20") > 0.3 and vs.stop_share_by_tercile(pos, "rvol20")[0] > 0.6 and vs.stop_share_by_tercile(pos, "rvol20")[2] == 0.0)
check("D4 월 demean rho > 0", vs.demeaned(pos, "rvol20") > 0.5)

# 피처 부착: 신호봉 i 의 인과 피처
from datetime import date, timedelta
rng = random.Random(2); cl = [100.0]
for _ in range(399): cl.append(cl[-1] * (1 + rng.uniform(-0.03, 0.03)))
d0 = date(2023, 1, 1)
rows = [dict(date=(d0 + timedelta(days=k)).isoformat(), ts=None, o=c, h=c * 1.01, l=c * 0.99, c=c, v=100.0) for k, c in enumerate(cl)]
sigs = [dict(sym="X", i=300, date=rows[300]["date"], month=rows[300]["date"][:7], ret=0.01, reason="hold")]
vs.attach_features(sigs, {"X": rows}, rows)
fs = xf.FeatureSeries(rows, rows)
check("attach_features = all_at(신호봉 i), 35 키", set(sigs[0]["f"]) == set(vs.KEYS) and sigs[0]["f"]["rvol20"] == xf.all_at(fs, 300)["rvol20"])

src = open("validate_signal_profile.py", encoding="utf-8").read()
check("실거래·배포 코드 없음", "import paper_executor" not in src and "import scheduler" not in src and "adopted_" not in src)
sched = open("scheduler.py", encoding="utf-8").read() + open("paper_executor.py", encoding="utf-8").read()
check("스케줄러·실행기가 모듈을 읽지 않음", "validate_signal_profile" not in sched)
wf = open(".github/workflows/signal_profile.yml", encoding="utf-8").read()
check("워크플로 등재 + 테스트 선행", "python validate_signal_profile.py" in wf and "python test_signal_profile.py" in wf)
check("tests.yml 등재", "test_signal_profile.py" in open(".github/workflows/tests.yml", encoding="utf-8").read())
print(f"\n{'ALL PASS' if not fails else 'FAILED: ' + ', '.join(fails)} ({len(fails)} fail)")
import sys; sys.exit(1 if fails else 0)
