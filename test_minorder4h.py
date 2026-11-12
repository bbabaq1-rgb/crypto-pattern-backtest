"""test_minorder4h.py — validate_minorder4h 로직 고정 (네트워크 없음)"""
import validate_minorder4h as d
import validate_minorder as vm

ok = fail = 0
def chk(n, c, x=""):
    global ok, fail
    if c: ok += 1
    else: fail += 1; print("  FAIL", n, x)

chk("DEPLOY False", d.DEPLOY_ON_PASS is False)
chk("주 판정 equity 240", d.PRIMARY_EQ == 240 and 240 in vm.EQ_GRID)
chk("문턱 0.90", d.THRESH == 0.90)
chk("R-107 함수 재사용", d.vm is vm)
chk("NO_PROBLEM", d.verdict([1.8] * 10) == "NO_PROBLEM")
chk("PROBLEM", d.verdict([0.45] * 10) == "PROBLEM")
chk("NO_DATA", d.verdict([]) == "NO_DATA")
# 경계: 정확히 90% 는 통과
need = vm.need_equity(1.0)
mix = [1.0] * 9 + [0.45]
chk("경계 90%", (d.verdict(mix) == "NO_PROBLEM") == (vm.pass_rate(mix, 240) >= 0.9))
print(f"{ok} ok / {fail} fail")
raise SystemExit(1 if fail else 0)
