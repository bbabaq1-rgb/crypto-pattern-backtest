"""test_minorder.py — validate_minorder 로직 고정 (네트워크 없음)"""
import validate_minorder as d
import sizing as sz
import paper_executor as pe

ok = fail = 0
def chk(n, c, x=""):
    global ok, fail
    if c: ok += 1
    else: fail += 1; print("  FAIL", n, x)

chk("DEPLOY False", d.DEPLOY_ON_PASS is False)
chk("FLOOR 가 실거래 킬스위치와 동일", d.FLOOR == pe.EQUITY_FLOOR, (d.FLOOR, getattr(pe, "EQUITY_FLOOR", None)))
chk("STOP 8%", d.STOP == 0.08)
chk("σ 없음 -> 1.0", abs(d.vscale(None) - 1.0) < 1e-9)
chk("스케일 범위", abs(d.vscale(10.0) - sz.VOL_LO / sz.VOL_S_NORM) < 1e-9 and abs(d.vscale(0.01) - sz.VOL_HI / sz.VOL_S_NORM) < 1e-9)
# 경계: 필요 equity 와 같으면 통과, 1원 낮으면 스킵
v = 0.6
n = d.need_equity(v)
chk("경계 통과", d.pass_rate([v], n + 1e-9) == 1.0 or d.pass_rate([v], max(n, d.FLOOR)) == 1.0)
chk("min_equity_for 와 일치", abs(n - sz.min_equity_for(v, 0.08)) < 1e-9)
# 주문 가능 여부가 실제 risk_based_size 스킵 경계와 일치
for vs in (0.45, 0.6, 1.0, 1.6):
    eq = d.need_equity(vs)
    chk(f"스킵 경계 {vs}", sz.risk_based_size(eq * 1.001, eq * 1.001, 0.08, vol_scale=vs) is not None
        and sz.risk_based_size(eq * 0.98, eq * 0.98, 0.08, vol_scale=vs) is None)
chk("킬스위치 미만 0", d.pass_rate([1.0], 99.0) == 0.0)
chk("빈 표본 None", d.pass_rate([], 200) is None)
chk("단조(equity↑ 비율↑)", d.pass_rate([0.45, 1.0, 1.8], 100) <= d.pass_rate([0.45, 1.0, 1.8], 240) <= d.pass_rate([0.45, 1.0, 1.8], 355))
chk("verdict NO_PROBLEM", d.verdict([1.8] * 10, [1.8] * 5) == "NO_PROBLEM")
chk("verdict PROBLEM", d.verdict([0.45] * 10, None) == "PROBLEM")
print(f"{ok} ok / {fail} fail")
raise SystemExit(1 if fail else 0)
