"""
method_h.py — 청산 방식H (Higher-High 실패 익절) 백테스트.

방식H (롱 기준, 숏 대칭):
  손절: -8% 인트라바 고정(항상 우선).
  익절(가격구조):
    (1) 진입 후 신고가 추적 — 신고가 갱신을 3봉 연속 실패하면 당봉 종가 청산.
    (2) 진입 후 형성된 직전 스윙 저점(프랙탈: 양옆 봉보다 낮은 low, 다음 봉에서 확정)을
        종가가 하향 이탈하면 청산 (higher-low 구조 붕괴).
  최대 60봉 타임스탑(시가).

해석 판단: '신고가 갱신 실패'는 당봉 high < 현재까지의 최고가. 3봉 '연속' 실패
카운터는 신고가 갱신 시 0으로 리셋. 스윙 저점은 확정 시점(다음 봉)부터 유효.
모두 결정론적 — 게이트 동결 유지.

main(): A/D/G/H 4방식 비교표 + G·H vs D 게이트 + 패턴별 G 부분우위 분석.
"""
import json

from method_d import outcome_a, outcome_d, FEE, STOP_LOSS_PCT
from method_e import collect, print_table, gate_vs, PATS_ALL
from method_g import outcome_g

MAX_HOLD_H = 60
FAIL_BARS  = 3


def outcome_h(rows, si, direction, atr=None):
    """방식H 수익률. 반환 (ret, hold_bars)."""
    base = rows[si]["c"]
    last = len(rows) - 1
    end  = min(si + MAX_HOLD_H, last)
    sgn  = 1 if direction == "long" else -1

    def _ret(px):
        return sgn * (px - base) / base

    extreme   = rows[si]["h"] if direction == "long" else rows[si]["l"]
    fail_cnt  = 0
    swing_lvl = None          # 롱: 직전 확정 스윙저점 / 숏: 스윙고점

    for j in range(si + 1, end + 1):
        h, l, c = rows[j]["h"], rows[j]["l"], rows[j]["c"]

        # 손절 항상 우선(인트라바)
        hit_sl = (l <= base * (1 - STOP_LOSS_PCT)) if direction == "long" \
            else (h >= base * (1 + STOP_LOSS_PCT))
        if hit_sl:
            return -STOP_LOSS_PCT - FEE, j - si

        # 스윙 레벨 확정(직전 봉 j-1이 프랙탈인지 — 진입 이후 형성분만)
        if j - 2 > si:
            pl, ll, nl = rows[j - 2]["l"], rows[j - 1]["l"], l
            ph, lh, nh = rows[j - 2]["h"], rows[j - 1]["h"], h
            if direction == "long" and ll < pl and ll < nl:
                swing_lvl = ll                      # 확정된 스윙 저점
            if direction == "short" and lh > ph and lh > nh:
                swing_lvl = lh                      # 확정된 스윙 고점

        # (2) 구조 붕괴: 종가가 스윙 레벨 이탈
        if swing_lvl is not None:
            broke = (c < swing_lvl) if direction == "long" else (c > swing_lvl)
            if broke:
                return _ret(c) - FEE, j - si

        # (1) 신고가(신저가) 갱신 실패 카운트
        made_new = (h > extreme) if direction == "long" else (l < extreme)
        if made_new:
            extreme = h if direction == "long" else l
            fail_cnt = 0
        else:
            fail_cnt += 1
            if fail_cnt >= FAIL_BARS:
                return _ret(c) - FEE, j - si

    px = rows[end]["o"]
    return _ret(px) - FEE, end - si


METHOD_FNS_ADGH = {
    "A": lambda rows, si, d, opp, atr: outcome_a(rows, si, d),
    "D": lambda rows, si, d, opp, atr: outcome_d(rows, si, d, opp),
    "G": lambda rows, si, d, opp, atr: outcome_g(rows, si, d),
    "H": lambda rows, si, d, opp, atr: outcome_h(rows, si, d),
}


def main():
    print("=" * 88)
    print("청산방식 4종 비교: A(±10%) / D(-8%SL·반대·레짐) / "
          "G(복합스코어 60/80) / H(HigherHigh 실패)")
    print("=" * 88)
    data = collect(METHOD_FNS_ADGH)
    stats = print_table(data, ["A", "D", "G", "H"])

    out = {}
    partial_g = []            # G의 패턴별 부분 우위 기록
    print("  [게이트] 방식G·H vs 방식D (3축: 기대값·MDD·Calmar)")
    for label, per in stats.items():
        if "D" not in per:
            continue
        entry = {"stats": {t: {k: round(v, 5) for k, v in s.items()} for t, s in per.items()}}
        nm = "전체(pooled)" if label == "_pooled" else label
        for tag in ("G", "H"):
            if tag not in per:
                continue
            g = gate_vs(per["D"], per[tag], "D", tag)
            mark = {"adopt": "O", "keep_base": "X", "reject": "X"}[g["verdict"]]
            print(f"    {nm:<17}{tag} {mark} {g['detail']}"
                  + ("  [3축 전승]" if g["all_wins"] else ""))
            entry[f"gate_{tag.lower()}_vs_d"] = g
            if tag == "G" and label != "_pooled" and g["wins"] >= 2:
                partial_g.append((label, g["wins"], g["detail"]))
        out[label] = entry

    if partial_g:
        print("\n  [특별분석] G의 패턴별 부분 우위(2/3 이상):")
        for label, wins, detail in partial_g:
            print(f"    {label}: {wins}/3 — {detail}")
    else:
        print("\n  [특별분석] G가 2/3 이상 우위인 패턴 없음")

    json.dump(out, open("method_h.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2, default=lambda x: round(float(x), 5))
    print("\n[저장] method_h.json")
    return out


if __name__ == "__main__":
    main()
