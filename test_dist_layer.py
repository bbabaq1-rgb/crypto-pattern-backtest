"""test_dist_layer.py — R-070 판정 함수·동결 파라미터·게이트 불변 (네트워크 없음)."""
import gate
import validate_dist_layer as dl

fails = []


def check(name, cond, extra=""):
    (print(f"PASS {name}") if cond else (fails.append(name), print(f"FAIL {name} {extra}")))


def row(cid, wr, ho, core=(), other=()):
    return dict(cid=cid, win_rate=wr, ho_mean=ho, core_fails=list(core), other_fails=list(other))


check("동결", (dl.SEED, dl.N_BOOT, dl.MIN_ADD, dl.MIN_PATTERNS, dl.BOOT_Q) == (20261109, 2000, 3, 2, 0.05))
check("게이트 불변", gate.WIN_RATE_MIN == 0.35 and gate.GATE_VERSION == 2)
rs = [row("a|x", .40, .02), row("a|y", .31, .05), row("b|x", .30, -.01, core=["bp"]), row("c|x", .45, None)]
core, keep, add = dl.split(rs)
check("분할: core 는 core_fails 없고 ho 있는 셀", [r["cid"] for r in core] == ["a|x", "a|y"])
check("분할: 승률 경계", [r["cid"] for r in keep] == ["a|x"] and [r["cid"] for r in add] == ["a|y"])
check("승률 35% 경계 포함", dl.split([row("p|a", .35, .01)])[1] != [])


def mk(pats_vals):
    return [row(f"{p}|c{i}", .30, v) for i, (p, v) in enumerate(pats_vals)]


j = dl.judge(mk([("a", .05), ("a", .06), ("b", .04), ("c", .07)]))
check("지지: 패턴 3·평균 양·부트 하한 양", j["verdict"] == "ADD_SUPPORTED", str(j))
j = dl.judge(mk([("a", .20), ("a", .22), ("a", .18)]))
check("한 패턴뿐 → INCONCLUSIVE(P1)", j["verdict"] == "INCONCLUSIVE" and not j["P1"], str(j))
j = dl.judge(mk([("a", -.05), ("b", -.02), ("c", .01)]))
check("평균<=0 → LAYER_NEEDED", j["verdict"] == "LAYER_NEEDED", str(j))
j = dl.judge(mk([("a", .01)]))
check("표본 부족 → INCONCLUSIVE", j["verdict"] == "INCONCLUSIVE")
j = dl.judge(mk([("a", .30), ("b", .01), ("c", -.001), ("d", -.002)]))
check("양수 패턴 2 이나 부트 하한<=0 → INCONCLUSIVE", j["verdict"] == "INCONCLUSIVE" and j["P2"] and not j["P3"], str(j))
check("부트 결정론", dl.cluster_boot(mk([("a", .1), ("b", .2)])) == dl.cluster_boot(mk([("a", .1), ("b", .2)])))
check("A3 는 other_fails 없는 저승률 셀", dl.a3([row("a|x", .3, .1), row("b|x", .3, .1, other=["C3"]), row("c|x", .4, .1)]) == ["a|x"])
check("사용 후에도 gate 불변", gate.WIN_RATE_MIN == 0.35)
print("FAIL" if fails else "ALL PASS", fails)
raise SystemExit(1 if fails else 0)
