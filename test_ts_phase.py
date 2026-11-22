"""test_ts_phase.py — validate_ts_phase 판정·층화 로직 고정 (네트워크 없음)"""
from datetime import date
import validate_ts_phase as v
import frame_v3 as f3

ok = fail = 0
def chk(n, c, x=""):
    global ok, fail
    if c: ok += 1
    else: fail += 1; print("  FAIL", n, x)

print("§1 날짜 복원·레짐 병합")
t = float(date(2025, 3, 5).toordinal()) + 0.5
chk("day_of 분수 일수", v.day_of(t) == "2025-03-05")
rm = {"2024-01-01": "bull_btc", "2024-01-02": "bull_altseason", "2024-01-03": "bear"}
b = v.bull_regmap(rm)
chk("bull 병합", b["2024-01-01"] == "bull" and b["2024-01-02"] == "bull" and b["2024-01-03"] == "bear")
chk("에피소드 하나로", f3.episodes(b, "bull") == [("2024-01-01", "2024-01-02")])

print("§2 판정")
def E(i, n, m): return dict(i=i, start="", end="", n=n, mean=m, q=n >= v.EP_N)
tr_e = [E(0, 20, .02), E(1, 20, .01), E(2, 8, -.01)]
J = v.judge
chk("약세 없음", J((.02, 50), (.01, 20), tr_e, [E(3, 20, .01)], (.01, 20)) == "NO_WEAKNESS")
chk("표본 부족", J((.02, 10), (-.01, 20), tr_e, [E(3, 20, -.01)], (.0, 0)) == "INCONCLUSIVE")
chk("holdout n<10", J((.02, 50), (-.01, 5), tr_e, [E(3, 5, -.01)], (.0, 0)) == "INCONCLUSIVE")
chk("국면: 한 에피소드 손실·나머지 양수", J((.02, 50), (-.005, 40), tr_e, [E(3, 25, -.03), E(4, 15, .02)], (.02, 15)) == "EPISODE_PHASE")
chk("감쇠: 적격 에피소드 전부 음수", J((.02, 50), (-.02, 40), tr_e, [E(3, 20, -.03), E(4, 20, -.01)], (.0, 0)) == "PATTERN_DECAY")
chk("train 에피소드 양수 1개뿐 -> MIXED", J((.02, 50), (-.02, 40), [E(0, 20, .03), E(1, 20, -.01)], [E(3, 20, -.03), E(4, 20, -.01)], (.0, 0)) == "MIXED")
chk("손실 에피소드 하나뿐 + 나머지 양수 아님 -> MIXED", J((.02, 50), (-.01, 40), tr_e, [E(3, 25, -.03), E(4, 15, .01)], (-.01, 15)) == "MIXED")
chk("배포 없음", v.DEPLOY_ON_PASS is False)
print(f"\ntest_ts_phase: {ok} ok / {fail} fail")
raise SystemExit(1 if fail else 0)
