"""
validate_dist_layer.py — R-070: 게이트의 분포 조건 층(승률>=35%)을 통째로 제거하면 판정이 나빠지는가.

사전 등록 registry `dist_layer_prereg_2026_11_09`. DEPLOY_ON_PASS=False — 게이트 문턱·층 구성 변경은 사용자 결정.
audit_winrate.main() 이 만드는 셀 행을 그대로 재사용한다(새 셀을 고르지 않는다). gate.py 는 건드리지 않는다.

정의(결과 전 고정)
  core      = core_fails 비어 있고(n·평균·boot_p·OOS) 홀드아웃 평균이 있는 셀 — 홀드아웃과 독립인 선별
  G_keep    = core ∧ 승률>=35%   (층이 있어도 들어오는 셀)
  G_add     = core ∧ 승률<35%    (층을 빼면 새로 들어오는 셀)
  패턴      = cid 의 '|' 앞 — 같은 패턴의 레짐·코호트 분해는 독립 증거가 아니므로 패턴 클러스터로 센다
판정
  P1  G_add 셀 >= 3 ∧ 패턴 >= 2
  P2  G_add 홀드아웃 평균 > 0 ∧ 홀드아웃 평균 > 0 인 패턴(패턴 내 평균) >= 2
  P3  패턴 클러스터 부트스트랩(2000회, 시드 고정)에서 G_add 평균의 5백분위 > 0
  ADD_SUPPORTED   = P1∧P2∧P3  (층 제거가 거짓양성을 늘리지 않는다는 증거)
  LAYER_NEEDED    = G_add >= 3 인데 G_add 홀드아웃 평균 <= 0
  INCONCLUSIVE    = 그 외(표본·패턴 수 부족, 부호는 양이나 CI 가 0 을 포함)
진단(판정 아님): 홀드아웃을 선별에 쓴 A3 목록(other_fails 없음 ∧ 승률<35%), G_keep 평균, 패턴별 표.
"""
import json
import random
import statistics as st
import sys

import gate

SEED = 20261109
N_BOOT = 2000
MIN_ADD = 3
MIN_PATTERNS = 2
BOOT_Q = 0.05


def pattern_of(row):
    return row["cid"].split("|")[0]


def is_core(r):
    return not r.get("core_fails") and r.get("ho_mean") is not None


def split(rows):
    core = [r for r in rows if is_core(r)]
    keep = [r for r in core if r.get("win_rate") is not None and r["win_rate"] >= gate.WIN_RATE_MIN]
    add = [r for r in core if r.get("win_rate") is not None and r["win_rate"] < gate.WIN_RATE_MIN]
    return core, keep, add


def by_pattern(rows):
    d = {}
    for r in rows:
        d.setdefault(pattern_of(r), []).append(r["ho_mean"])
    return {k: st.mean(v) for k, v in d.items()}


def cluster_boot(rows, n_boot=N_BOOT, seed=SEED):
    """패턴을 단위로 복원추출 → 셀 평균(셀 가중). 반환: (평균 분포 분위, 평균)"""
    groups = {}
    for r in rows:
        groups.setdefault(pattern_of(r), []).append(r["ho_mean"])
    keys = sorted(groups)
    if not keys:
        return None
    rng = random.Random(seed)
    means = []
    for _ in range(n_boot):
        vals = []
        for _k in keys:
            vals.extend(groups[rng.choice(keys)])
        means.append(sum(vals) / len(vals))
    means.sort()
    lo = means[int(BOOT_Q * n_boot)]
    return dict(q05=lo, median=means[n_boot // 2], mean=st.mean(r["ho_mean"] for r in rows))


def judge(rows):
    core, keep, add = split(rows)
    pats = by_pattern(add)
    pos_pats = sorted(p for p, m in pats.items() if m > 0)
    m_add = st.mean(r["ho_mean"] for r in add) if add else None
    m_keep = st.mean(r["ho_mean"] for r in keep) if keep else None
    boot = cluster_boot(add) if add else None
    p1 = len(add) >= MIN_ADD and len(pats) >= MIN_PATTERNS
    p2 = m_add is not None and m_add > 0 and len(pos_pats) >= MIN_PATTERNS
    p3 = boot is not None and boot["q05"] > 0
    if len(add) >= MIN_ADD and m_add is not None and m_add <= 0:
        v, why = "LAYER_NEEDED", f"G_add {len(add)}셀 홀드아웃 평균 {m_add:+.4f} <= 0 — 층이 거르는 셀이 실제로 나쁘다"
    elif p1 and p2 and p3:
        v, why = "ADD_SUPPORTED", "P1·P2·P3 전부 통과"
    else:
        v, why = "INCONCLUSIVE", f"P1={p1} P2={p2} P3={p3} (G_add {len(add)}셀·패턴 {len(pats)}·양수 패턴 {len(pos_pats)})"
    return dict(verdict=v, why=why, P1=p1, P2=p2, P3=p3, core_n=len(core), keep_n=len(keep), add_n=len(add),
                ho_keep=m_keep, ho_add=m_add, add_patterns=pats, pos_patterns=pos_pats, boot=boot,
                add_cells=[r["cid"] for r in add])


def a3(rows):
    """진단 — 홀드아웃을 선별에 쓴 판(other_fails 없음 ∧ 승률<35%)."""
    return [r["cid"] for r in rows if not r.get("other_fails") and r.get("win_rate") is not None
            and r["win_rate"] < gate.WIN_RATE_MIN]


def _f(v):
    return "   n/a " if v is None else f"{v*100:+7.2f}%"


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    import audit_winrate as aw
    rows = aw.main(argv)["cells"]
    j = judge(rows)
    print(f"\n{'='*100}\nR-070 분포 조건 층 제거 — core {j['core_n']} · G_keep {j['keep_n']} 평균 {_f(j['ho_keep'])} · "
          f"G_add {j['add_n']} 평균 {_f(j['ho_add'])}")
    for p, m in sorted(j["add_patterns"].items()):
        print(f"  패턴 {p:<24} 홀드아웃 평균 {_f(m)}")
    print(f"  클러스터 부트 5백분위 {_f(j['boot']['q05']) if j['boot'] else 'n/a'}")
    print(f"P1={j['P1']} P2={j['P2']} P3={j['P3']}  G_add 셀: {j['add_cells']}")
    print(f"진단 A3(홀드아웃 선별 포함): {a3(rows)}")
    print(f"\n**{j['verdict']}** — {j['why']}\n게이트는 바뀌지 않았다(WIN_RATE_MIN={gate.WIN_RATE_MIN}). 변경은 사용자 결정.")
    json.dump(dict(frame="dist_layer", threshold_changed=False, judge=j, a3=a3(rows)),
              open("dist_layer.json", "w"), ensure_ascii=False, indent=1, default=str)
    return j


if __name__ == "__main__":
    main()
