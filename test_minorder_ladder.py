"""test_minorder_ladder.py — validate_minorder_ladder 로직 고정 (네트워크 없음)"""
import validate_minorder_ladder as d
import validate_minorder as vm

ok = fail = 0
def chk(n, c, x=""):
    global ok, fail
    if c: ok += 1
    else: fail += 1; print("  FAIL", n, x)

chk("DEPLOY False", d.DEPLOY_ON_PASS is False)
chk("격자·주판정", d.EQ_LADDER == (160, 240, 355) and d.PRIMARY_EQ == 240)
chk("R-107 함수 재사용", d.vm is vm)
HI, LO = 0.45, 1.8     # 고변동(작은 배율)=필요 equity 큼
def T(vol_scale_hint, ret, t_in):
    # vol 를 직접 못 쓰므로 vscale 을 우회: vol=None -> scale 1.0, 필요 equity $160
    return dict(vol=None, ret=ret, t_in=t_in)
tr = [T(1, 0.01, 738000 + i * 15) for i in range(40)]
ps, sk = d.split_skip(tr, 240)
chk("scale 1.0 은 $240 통과", len(ps) == 40 and not sk)
ps, sk = d.split_skip(tr, 100)
chk("$100 에서는 필요 equity $160 이라 전부 스킵", not ps and len(sk) == 40)
# 분할 일관성
chk("통과+스킵=전체", all(len(a) + len(b) == 40 for a, b in [d.split_skip(tr, e) for e in d.EQ_LADDER]))
# 월 블록 부트: 스킵이 일관되게 높으면 P(diff<=0) 작다
P = [dict(vol=None, ret=0.0, t_in=738000 + i * 20) for i in range(60)]
S = [dict(vol=None, ret=0.05, t_in=738000 + i * 20) for i in range(60)]
le, ge = d.month_boot_diff(P, S, n=300)
chk("스킵 우위면 P(<=0)≈0", le is not None and le < 0.05 and ge > 0.95, (le, ge))
le, ge = d.month_boot_diff(S, P, n=300)
chk("반대면 P(>=0)≈0", ge < 0.05, (le, ge))
chk("한쪽 비면 None", d.month_boot_diff(P, [], n=10) == (None, None))
# 판정 함수
base = dict(n_skip=100, diff=0.02, p_diff_le0=0.05, p_diff_ge0=0.95,
            halves=dict(train=dict(diff=0.01), holdout=dict(diff=0.03)))
chk("COSTS", d.verdict(base) == "SKIP_COSTS_EDGE")
b2 = dict(base, halves=dict(train=dict(diff=-0.01), holdout=dict(diff=0.03)))
chk("전후반 부호 역전은 COSTS 아님", d.verdict(b2) == "INDETERMINATE")
b3 = dict(base, diff=-0.02, p_diff_le0=0.95, p_diff_ge0=0.04)
chk("PRESERVES", d.verdict(b3) == "SKIP_PRESERVES")
chk("INSUFFICIENT", d.verdict(dict(base, n_skip=5)) == "INSUFFICIENT" and d.verdict(None) == "INSUFFICIENT")
# analyse 전 경로(합성)
a = d.analyse(P + S, 100, 738000 + 600)
chk("analyse 키", {"n_pass", "n_skip", "diff", "halves"} <= set(a))
print(f"{ok} ok / {fail} fail")
raise SystemExit(1 if fail else 0)
