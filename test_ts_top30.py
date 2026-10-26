"""test_ts_top30.py — validate_ts_top30 로직 고정 (네트워크 없음)"""
import random
import validate_ts_top30 as v
import validate_portfolio as vp

ok = fail = 0
def chk(n, c, x=""):
    global ok, fail
    if c: ok += 1
    else: fail += 1; print("  FAIL", n, x)

def T(pat, rank, ret, t=739000.0):
    return dict(pattern=pat, rank=rank, ret=ret, t_in=t, t_out=t + 1, sym="X", vol=0.8, tf="4h")

print("§1 arm 구성: 제거 대상은 three_soldiers_4h 의 순위>=30 뿐")
base = [T(v.PAT, 0, .1), T(v.PAT, 29, .1), T(v.PAT, 30, -.1), T(v.PAT, None, -.1),
        T("vol_awakening_4h", 80, .1), T("engulfing", None, .1)]
a = v.make_arms(base)
chk("current 불변", a["current"] == base)
chk("top30 제거 2건만", len(a["top30"]) == 4 and all(not v.is_removed(t) for t in a["top30"]))
chk("타 패턴 보존", any(t["pattern"] == "vol_awakening_4h" for t in a["top30"]) and any(t["pattern"] == "engulfing" for t in a["top30"]))
chk("current 는 vp.ADOPTED_4H 의 three_soldiers 가 코호트 None", [c for p, g, c in vp.ADOPTED_4H if p == v.PAT][0] is None)
chk("TOP_N 은 포트폴리오 top30 정의와 동일", v.TOP_N == vp.COHORT_N["current"])

print("§2 월 블록 부트")
neg = [dict(t_in=739000.0 + 31 * i, ret=-0.02) for i in range(12)]
pos = [dict(t_in=739000.0 + 31 * i, ret=0.02) for i in range(12)]
chk("전부 음수 -> 1.0", v.month_boot_p_neg(neg, random.Random(1), 200) == 1.0)
chk("전부 양수 -> 0.0", v.month_boot_p_neg(pos, random.Random(1), 200) == 0.0)
chk("빈 입력 None", v.month_boot_p_neg([], random.Random(1)) is None)
chk("결정론", v.month_boot_p_neg(neg + pos[:3], random.Random(5), 200) == v.month_boot_p_neg(neg + pos[:3], random.Random(5), 200))

print("§3 판정 규칙")
J = dict(J1=True, J2=True, J3=True, J4=True, J5=True)
good = dict(removed_mean=-.01, removed_pneg=.95, rm_tr=(-.01, 50), rm_ho=(-.02, 30), kept_tr=(.01, 40), kept_ho=(.02, 20), J=J)
chk("전부 통과 PASSED", v.judge(good)[0] == "PASSED")
chk("F1 부트 미달 REJECTED", v.judge(dict(good, removed_pneg=.8))[0] == "REJECTED")
chk("걸러진 holdout 양수 REJECTED", v.judge(dict(good, rm_ho=(.01, 30)))[0] == "REJECTED")
chk("J3 실패 REJECTED", v.judge(dict(good, J=dict(J, J3=False)))[0] == "REJECTED")
chk("남는 holdout n<10 만 -> INCONCLUSIVE", v.judge(dict(good, kept_ho=(.02, 5)))[0] == "INCONCLUSIVE")
chk("남는 holdout 음수 REJECTED", v.judge(dict(good, kept_ho=(-.01, 30)))[0] == "REJECTED")
chk("표본 부족 + 다른 실패 -> REJECTED", v.judge(dict(good, kept_ho=(.02, 5), removed_pneg=.5))[0] == "REJECTED")

print("§4 프레임 동결")
chk("MIN_N·F1_P", v.MIN_N == 10 and v.F1_P == 0.90)
chk("J3 문턱 재사용", vp.J3_WIN == 0.60)
print(f"\ntest_ts_top30: {ok} ok / {fail} fail")
raise SystemExit(1 if fail else 0)
