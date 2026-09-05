"""
direction_switch.py — 레짐 -> 방향 -> 패턴 자동 라우팅.

regime_switch.json의 레짐별 기대값을 근거로, 각 레짐에서 engulfing/fvg의
롱·숏 중 '기대값 양수인 방향만' 켜는 규칙을 만든다.
  - 롱/숏 둘 다 양수면 더 높은 쪽 우선(+ 둘 다 켤 수 있음 표시)
  - 둘 다 음수면 FLAT(쉬기)
현재(최신 날짜) 레짐을 판정해 '지금 무엇을 켜야 하나'도 출력.
"""
import json
import statistics as st

import regime_switch as rs

MIN_N = 20          # 레짐별 최소 표본(미만은 신뢰 낮음 -> FLAT 처리)
FOCUS = ["engulfing", "fvg"]
REGIMES = ["bull_altseason", "bull_btc", "bear", "sideways"]

# 라우팅 강제 오버라이드 — decide() 결과 위에 덮어쓴다. main() 이 매 실행 regime_switch.json
# 의 '무조건부 n>=20·mean>0' 만으로 표를 다시 만들기 때문에 JSON 을 손으로 고쳐도 다음
# 실행에서 되돌아간다 → 예외는 반드시 여기(코드)에 둔다.
#   이력: (bear, fvg) FLAT — 2026-09-04 사용자 결정("bear 숏 끄고"). 근거는 레짐 분리 게이트의
#     'bear fvg 숏 엣지 −0.96%p' 였는데, 그 수치는 boot_p 베이스라인이 30표본에 묶여 있던(k=30)
#     시절 값이다. k=n 으로 고친 재실행(routing_gate run 33955072569)에서는 top20·bear 셀이
#     PASSED(n=356 +0.81% med +3.28% 엣지 +1.58%p bp .014 OOS 2/4), top30 bp .072, all bp .397.
#     2026-09-05 사용자 결정("bear fvg 숏 키고")으로 오버라이드 제거 → decide() 그대로(현 표 short).
#     유의: 그 셀의 수익은 2026 bear 단일 해(+5%)에서 나오고 2022·2024·2025 bear 는 음수다.
#     다시 끄려면 {("bear", "fvg"): "FLAT"} 을 넣는다. test_direction_switch 가 현 상태를 고정한다.
ROUTING_OVERRIDES = {
}


def decide(longm, longn, shortm, shortn):
    cands = []
    if longm is not None and longn >= MIN_N and longm > 0:
        cands.append(("long", longm))
    if shortm is not None and shortn >= MIN_N and shortm > 0:
        cands.append(("short", shortm))
    if not cands:
        return "FLAT", []
    cands.sort(key=lambda x: -x[1])
    return cands[0][0], cands


def main():
    data = json.load(open("regime_switch.json", encoding="utf-8"))
    bp = data["by_pattern"]

    print("=" * 80)
    print("레짐 -> 방향 라우팅 (engulfing/fvg, 기대값 양수 방향만, n>=%d)" % MIN_N)
    print("=" * 80)
    routing = {}
    for rg in REGIMES:
        print(f"\n[{rg}]")
        rg_route = {}
        for pat in FOCUS:
            lo = bp[pat][rg]; sh = bp[pat + "_short"][rg]
            d, cands = decide(lo["mean"], lo["n"], sh["mean"], sh["n"])
            detail = ", ".join(f"{dir}({m*100:+.2f}%)" for dir, m in cands) or "양수방향 없음"
            ov = ROUTING_OVERRIDES.get((rg, pat))
            tag = f"  ← 강제 {ov} (ROUTING_OVERRIDES)" if ov is not None and ov != d else ""
            print(f"  {pat:<10}: {d:<6} [{detail}]  (롱 n{lo['n']}/{_p(lo['mean'])}, 숏 n{sh['n']}/{_p(sh['mean'])}){tag}")
            rg_route[pat] = ov if ov is not None else d
        routing[rg] = rg_route

    # 현재 레짐 판정
    regmap = rs.build_regime_map()
    latest = max(regmap)
    cur = regmap[latest]
    print("\n" + "=" * 80)
    print(f"현재({latest}) 레짐: {cur}")
    if cur in routing:
        for pat in FOCUS:
            print(f"  -> {pat}: {routing[cur][pat]}")
    print("=" * 80)

    json.dump({"routing": routing,
               "overrides": {f"{rg}/{pat}": d for (rg, pat), d in ROUTING_OVERRIDES.items()},
               "current": {"date": latest, "regime": cur,
               "action": routing.get(cur, {})}},
              open("direction_switch.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("[저장] direction_switch.json")


def _p(m):
    return f"{m*100:+.2f}%" if m is not None else "-"


if __name__ == "__main__":
    main()
