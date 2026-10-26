"""
validate_lottery_gate.py — R-001: 게이트 승률 조건 → 복권형 지표(top5 기여도·절사평균) 대체 시험.

사전 등록 registry `lottery_gate_prereg_2026_10_26`. DEPLOY_ON_PASS=False — 게이트 문턱 변경은 사용자 결정이라
설계·재실행·보고까지만 한다(gate.py 는 건드리지 않는다).

방법: audit_winrate.main() 이 만드는 셀 행(같은 모집단·같은 프레임)을 그대로 받아, 승률 조건 대신
L 게이트  L_ok = (top5_share <= TOP5_MAX) AND (trimmed_mean > TRIM_MIN)  을 적용했을 때의 분류를
홀드아웃 결과(선별과 독립인 core 모집단)로 비교한다. 새 셀을 고르지 않는다.

실행: python validate_lottery_gate.py [--no-fetch]
"""
import json
import statistics as st
import sys

import gate

TOP5_MAX = 0.50
TRIM_MIN = 0.0
TOP5_GRID = (0.40, 0.50, 0.60)     # 진단 — 최대값을 고르지 않는다
P1_GAP = 0.01
MIN_CORE = 10
MIN_GROUP = 3
MIN_NEW_CELLS = 2
MIN_NEW_PATTERNS = 2


def trimmed(row):
    if row.get("mean") is None or row.get("trim_gap") is None:
        return None
    return row["mean"] + row["trim_gap"]


def lottery_ok(row, top5_max=TOP5_MAX):
    """L 게이트. top5 가 None(총이익<=0)이거나 절사평균이 없으면 탈락."""
    t5, tm = row.get("top5"), trimmed(row)
    if t5 is None or tm is None:
        return False
    return t5 <= top5_max and tm > TRIM_MIN


def v2_ok(row):
    return row.get("win_rate") is not None and row["win_rate"] >= gate.WIN_RATE_MIN


def pattern_of(row):
    return row["cid"].split("|")[0]


def _mean(rows):
    xs = [r["ho_mean"] for r in rows if r.get("ho_mean") is not None]
    return st.mean(xs) if xs else None


def core_pop(rows):
    return [r for r in rows if not r.get("core_fails") and r.get("ho_mean") is not None]


def full_pop(rows):
    return [r for r in rows if not r.get("other_fails") and r.get("ho_mean") is not None]


def quadrants(rows):
    q = {"v2+L+": [], "v2+L-": [], "v2-L+": [], "v2-L-": []}
    for r in rows:
        q[f"v2{'+' if v2_ok(r) else '-'}L{'+' if lottery_ok(r) else '-'}"].append(r)
    return q


def judge(rows):
    core = core_pop(rows)
    l_pass = [r for r in core if lottery_ok(r)]
    l_fail = [r for r in core if not lottery_ok(r)]
    v_pass = [r for r in core if v2_ok(r)]
    m_lp, m_lf, m_vp = _mean(l_pass), _mean(l_fail), _mean(v_pass)
    enough = len(core) >= MIN_CORE and len(l_pass) >= MIN_GROUP and len(l_fail) >= MIN_GROUP \
        and len(v_pass) >= MIN_GROUP
    p1 = enough and m_lp is not None and m_lf is not None and (m_lp - m_lf) >= P1_GAP and m_lp > 0
    p2 = enough and m_lp is not None and m_vp is not None and m_lp >= m_vp
    new = [r for r in full_pop(rows) if (not v2_ok(r)) and lottery_ok(r)]
    pats = {pattern_of(r) for r in new}
    m_new = _mean(new)
    p3 = len(new) >= MIN_NEW_CELLS and len(pats) >= MIN_NEW_PATTERNS and m_new is not None and m_new > 0
    if not enough:
        v, why = "INCONCLUSIVE", f"core 모집단 {len(core)}(L통과 {len(l_pass)}/L탈락 {len(l_fail)}/v2통과 {len(v_pass)}) 표본 부족"
    elif p1 and p2 and p3:
        v, why = "L_SUPPORTED", "P1·P2·P3 전부 통과"
    elif not (p1 and p2):
        v, why = "L_NOT_SUPPORTED", f"P1={p1} P2={p2}"
    else:
        v, why = "INCONCLUSIVE", f"P1·P2 통과, P3 실패(새 셀 {len(new)}·패턴 {len(pats)}·평균 {m_new})"
    return dict(verdict=v, why=why, P1=p1, P2=p2, P3=p3, enough=enough,
                core_n=len(core), l_pass=len(l_pass), l_fail=len(l_fail), v2_pass=len(v_pass),
                ho_l_pass=m_lp, ho_l_fail=m_lf, ho_v2_pass=m_vp,
                new_cells=[r["cid"] for r in new], new_patterns=sorted(pats), ho_new=m_new)


def _f(v):
    return "   n/a " if v is None else f"{v*100:+7.2f}%"


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    import audit_winrate as aw          # 무거운 import 는 실행 때만
    out_aw = aw.main(argv)
    rows = out_aw["cells"]
    print(f"\n{'='*100}\nR-001 복권형 게이트 — L: top5<={TOP5_MAX:.0%} AND 절사평균>{TRIM_MIN:.0%} (셀 {len(rows)})")
    j = judge(rows)
    print(f"core {j['core_n']} · L통과 {j['l_pass']} 평균 {_f(j['ho_l_pass'])} · L탈락 {j['l_fail']} 평균 {_f(j['ho_l_fail'])} · "
          f"v2통과 {j['v2_pass']} 평균 {_f(j['ho_v2_pass'])}")
    print(f"P1={j['P1']} P2={j['P2']} P3={j['P3']} 새셀 {j['new_cells']} 패턴 {j['new_patterns']} 평균 {_f(j['ho_new'])}")
    q = quadrants(rows)
    for k, v in q.items():
        print(f"\n[{k}] {len(v)}셀")
        for r in v:
            print(f"  {r['cid'][:44]:<44} 승률 {r['win_rate']*100:3.0f}% top5 {_f(r['top5'])} 절사 {_f(trimmed(r))} "
                  f"홀드아웃 {_f(r.get('ho_mean'))} 승률외탈락 {','.join(r['other_fails']) or '없음'}")
    print("\n진단 — TOP5_MAX 격자(판정 아님)")
    grid = []
    for t in TOP5_GRID:
        lp = [r for r in core_pop(rows) if lottery_ok(r, t)]
        grid.append(dict(top5_max=t, n=len(lp), ho=_mean(lp)))
        print(f"  top5<={t:.0%}: L통과 {len(lp)} · 홀드아웃 평균 {_f(_mean(lp))}")
    import audit_winrate as aw2
    core = core_pop(rows)
    rho = {k: aw2.spearman([r.get(k2) for r in core], [r["ho_mean"] for r in core])
           for k, k2 in (("win_rate", "win_rate"), ("top5", "top5"), ("trim_gap", "trim_gap"))}
    print("  rho(·, 홀드아웃) core:", {k: (None if v is None else round(v, 3)) for k, v in rho.items()})
    print(f"\n**{j['verdict']}** — {j['why']}")
    print("게이트 문턱은 바뀌지 않았다(gate.WIN_RATE_MIN 그대로). 변경은 사용자 결정.")
    json.dump(dict(frame="lottery_gate", threshold_changed=False, judge=j, grid=grid, rho=rho,
                   quadrants={k: [r["cid"] for r in v] for k, v in q.items()}),
              open("lottery_gate.json", "w"), ensure_ascii=False, indent=1, default=str)
    return j


if __name__ == "__main__":
    main()
