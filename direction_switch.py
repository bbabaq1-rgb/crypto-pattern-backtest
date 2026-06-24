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
            print(f"  {pat:<10}: {d:<6} [{detail}]  (롱 n{lo['n']}/{_p(lo['mean'])}, 숏 n{sh['n']}/{_p(sh['mean'])})")
            rg_route[pat] = d
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

    json.dump({"routing": routing, "current": {"date": latest, "regime": cur,
               "action": routing.get(cur, {})}},
              open("direction_switch.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("[저장] direction_switch.json")


def _p(m):
    return f"{m*100:+.2f}%" if m is not None else "-"


if __name__ == "__main__":
    main()
