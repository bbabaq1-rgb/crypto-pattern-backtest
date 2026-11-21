"""
validate_turtle_soup.py — R-009 Turtle Soup 4h 롱 사전 등록 시험 (2026-11-21, 자율 연구 사이클).

registry `turtle_soup_prereg_2026_11_21`. validate_revival 프레임(방식D·레짐 조건부·k=n 베이스라인·PIT 아닌 정적 top30·
실거래 사이징 자산곡선) + frame_v3(국면 홀드아웃·E 에피소드·C2b)를 그대로 쓴다. 이 모듈이 하는 일:
  · 신규 패턴 목록을 turtle_soup_4h 하나로 바꿔 validate_revival.main 을 4h 로 돌린다
  · 주 판정 셀 = (turtle_soup_4h, ALL 레짐, top30) 롱 — v3 verdict == CONFIRMED 여야 통과
  · 진단(판정 아님): 레짐 4셀, liquidity_sweep 과 신호 겹침 비율
DEPLOY_ON_PASS = True (backlog R-009) — 통과 시 자율 반영 규칙(2026-09-05)대로 adopted_4h_patterns 등재(별도 커밋).
단 universe.json trading_halt 가 by=user 로 켜져 있어 반영돼도 즉시 주문은 없다.
실행: python validate_turtle_soup.py [--no-fetch]
"""
import json
import sys

import validate_revival as vr
import detector_turtle_soup_4h as ts

CID = "turtle_soup_4h"
PRIMARY = (CID, "ALL")
DEPLOY_ON_PASS = True
OVERLAP_WINDOW = 3          # 봉 — liquidity_sweep 신호와 이 거리 안이면 '겹침'


def overlap(a_idx, b_idx, window=OVERLAP_WINDOW):
    """a 신호 중 b 신호가 ±window 봉 안에 있는 비율(진단). a 가 비면 None."""
    if not a_idx:
        return None
    b = sorted(b_idx)
    hit = 0
    for i in a_idx:
        if any(abs(i - j) <= window for j in b):
            hit += 1
    return hit / len(a_idx)


def judge(results):
    """주 판정 셀 v3 verdict → (verdict, detail). 셀이 없으면 INCONCLUSIVE."""
    r = results.get(f"{PRIMARY[0]}|{PRIMARY[1]}")
    if not r or not r.get("confirm_v3"):
        return "INCONCLUSIVE", "주 판정 셀 없음"
    v = r["confirm_v3"]["verdict"]
    return v, r["confirm_v3"]


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    vr.NEW_PATTERNS[:] = [(CID, "4h", "detector_turtle_soup_4h", "long")]
    run = ["--new", "--tf", "4h", "--frame", "v3", "--long"] + (["--no-fetch"] if "--no-fetch" in argv else [])
    vr.main(run)
    out = json.load(open("_revival_new_v3.json", encoding="utf-8"))
    verdict, detail = judge(out["results"])
    print("\n" + "=" * 100)
    print(f"[R-009 주 판정] {CID} ALL top30 롱 → **{verdict}**")
    # 겹침 진단
    try:
        import detector_liquidity_sweep as ls
        import validate_regime_split_all as va
        from validate_regime_split import turnover_rank
        syms = va._syms()
        rows_1d = va.load_tf(syms, "1d")
        top = [s for s in turnover_rank(rows_1d)[:30]]
        rows_4h = va.load_tf(syms, "4h")
        tot_a = tot_b = hit_a = hit_b = 0
        for s in top:
            rows = rows_4h.get(s)
            if not rows:
                continue
            a = ts.detect(rows)
            b = ls.detect_sweeps(rows)
            tot_a += len(a); tot_b += len(b)
            hit_a += round((overlap(a, b) or 0) * len(a)); hit_b += round((overlap(b, a) or 0) * len(b))
        print(f"[진단] liquidity_sweep 겹침(±{OVERLAP_WINDOW}봉, top30): turtle 신호 {tot_a} 중 {hit_a} "
              f"({(hit_a/tot_a if tot_a else 0)*100:.0f}%) / sweep 신호 {tot_b} 중 turtle 와 겹침 {hit_b} "
              f"({(hit_b/tot_b if tot_b else 0)*100:.0f}%)")
    except Exception as e:
        print(f"[진단] 겹침 계산 실패: {str(e)[:80]}")
    json.dump(dict(primary=f"{PRIMARY[0]}|{PRIMARY[1]}", verdict=verdict, deploy_on_pass=DEPLOY_ON_PASS),
              open("_turtle_soup.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("RESULT_JSON: " + json.dumps(dict(verdict=verdict), ensure_ascii=False))


if __name__ == "__main__":
    main()
