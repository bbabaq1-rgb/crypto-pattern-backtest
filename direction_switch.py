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
#   (bear, fvg) FLAT — 2026-09-04 레짐 분리 게이트(validate_regime_split, report_regime_split.md):
#     bear 진입 fvg 숏은 같은 레짐 무작위 진입 대비 엣지 −0.96%p(전 코호트 음수)이고 fvg 숏은
#     4 레짐 전부 엣지 음수. bear 에서 fvg 롱은 엣지 +1.34%p 로 부호가 맞으나 동결 게이트
#     (median/boot_p/OOS)는 통과하지 못했으므로 롱으로 뒤집지 않고 FLAT. 사용자 결정(2026-09-04
#     "bear 숏 끄고"). 되돌리려면 이 항목을 지운다.
ROUTING_OVERRIDES = {
    ("bear", "fvg"): "FLAT",
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
