"""test_lottery_gate.py — R-001 판정 함수·동결 파라미터·게이트 불변 고정 (네트워크 없음)."""
import gate
import validate_lottery_gate as lg

fails = []


def check(name, cond, extra=""):
    (print(f"PASS {name}") if cond else (fails.append(name), print(f"FAIL {name} {extra}")))


def row(cid, wr, mean, trim_gap, top5, ho, core=(), other=()):
    return dict(cid=cid, win_rate=wr, mean=mean, trim_gap=trim_gap, top5=top5, ho_mean=ho,
                core_fails=list(core), other_fails=list(other))


check("동결 파라미터", (lg.TOP5_MAX, lg.TRIM_MIN, lg.TOP5_GRID, lg.P1_GAP, lg.MIN_CORE, lg.MIN_GROUP)
      == (0.50, 0.0, (0.40, 0.50, 0.60), 0.01, 10, 3))
check("게이트 불변", gate.WIN_RATE_MIN == 0.35 and gate.GATE_VERSION == 2)
check("L: top5 상한 경계 포함", lg.lottery_ok(row("a|x", .3, .05, -.01, 0.50, .0)))
check("L: top5 초과 탈락", not lg.lottery_ok(row("a|x", .3, .05, -.01, 0.51, .0)))
check("L: 절사평균 0 이하 탈락", not lg.lottery_ok(row("a|x", .3, .05, -.05, 0.3, .0)))
check("L: top5 None 탈락", not lg.lottery_ok(row("a|x", .3, .05, -.01, None, .0)))
check("v2: 35% 경계", lg.v2_ok(row("a|x", .35, 0, 0, .3, 0)) and not lg.v2_ok(row("a|x", .349, 0, 0, .3, 0)))
check("패턴 추출", lg.pattern_of(row("tb_1d|bull_btc", 0, 0, 0, 0, 0)) == "tb_1d")

# 표본 부족 → INCONCLUSIVE
check("표본 부족 INCONCLUSIVE", lg.judge([row(f"p{i}|a", .4, .05, -.01, .3, .02) for i in range(5)])["verdict"] == "INCONCLUSIVE")


def mk(n_lp, n_lf, n_vonly_new, new_pats, ho_lp=.05, ho_lf=-.01, ho_new=.10):
    rs = []
    for i in range(n_lp):   # L 통과 & v2 통과
        rs.append(row(f"p{i}|a", .45, .05, -.01, .3, ho_lp))
    for i in range(n_lf):   # L 탈락 & v2 탈락(core 통과)
        rs.append(row(f"q{i}|a", .30, .02, -.05, .7, ho_lf))
    for i in range(n_vonly_new):  # v2 탈락 & L 통과 & 승률외 통과
        rs.append(row(f"{new_pats[i % len(new_pats)]}|r{i}", .31, .08, -.01, .4, ho_new))
    return rs


j = lg.judge(mk(5, 5, 2, ["tb", "ma"]))
check("지지: P1·P2·P3 → L_SUPPORTED", j["verdict"] == "L_SUPPORTED", str(j))
j = lg.judge(mk(5, 5, 2, ["tb"]))
check("새 셀이 한 패턴뿐 → INCONCLUSIVE(P3)", j["verdict"] == "INCONCLUSIVE" and not j["P3"], str(j))
j = lg.judge(mk(5, 5, 2, ["tb", "ma"], ho_lp=-.01, ho_lf=-.02, ho_new=-.01))
check("L 통과 평균<=0 → NOT_SUPPORTED", j["verdict"] == "L_NOT_SUPPORTED", str(j))
j = lg.judge(mk(5, 5, 2, ["tb", "ma"], ho_lp=.005, ho_lf=.0, ho_new=.005))
check("P1 격차<1%p → NOT_SUPPORTED", j["verdict"] == "L_NOT_SUPPORTED", str(j))
q = lg.quadrants(mk(2, 2, 1, ["tb"]))
check("4분면 분류", (len(q["v2+L+"]), len(q["v2-L-"]), len(q["v2-L+"])) == (2, 2, 1))

# 새 셀 판정은 승률 외 층까지 통과한 셀만(other_fails) — core 통과만으론 새 셀이 아니다
rs = mk(5, 5, 0, ["tb"]) + [row("z|a", .31, .08, -.01, .4, .1, other=["holdout"]) for _ in range(3)]
check("other_fails 있는 셀은 새 셀 아님", lg.judge(rs)["new_cells"] == [])

# gate 불변 — 모듈 사용 후에도
check("사용 후에도 gate 불변", gate.WIN_RATE_MIN == 0.35 and gate.dist_ok([-.08] * 65 + [.3] * 35))
print("FAIL" if fails else "ALL PASS", fails)
raise SystemExit(1 if fails else 0)
