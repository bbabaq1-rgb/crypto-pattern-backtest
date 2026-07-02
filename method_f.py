"""
method_f.py — 청산 방식F (Scaling Out + Breakeven) 백테스트.

방식F 청산:
  R = 진입가~손절가(-8%) 거리. 손절: -8% 인트라바(전량, 1R 도달 전).
  +1R(+8%) 도달 시 50% 익절 + 잔여분 손절가를 진입가(본전)로 이동.
  잔여 50%는 Chandelier(ATR22*3) 트레일링(본전선과 max) 운용.
  같은 봉에서 -8%와 +8% 동시 도달 시 손절 우선(보수적).
  최대 60봉 타임스탑(시가 청산).

기존 1d 신호에 소급 적용, A/D/E와 4방식 비교표 + 3축 게이트(vs D).
게이트 동결 유지.
"""
import json

from method_d import outcome_a, outcome_d, FEE
from method_e import (atr_series, outcome_e, collect, print_table, gate_vs,
                      ATR_MULT, MAX_HOLD_E, PATS_ALL)

R_PCT = 0.08          # 1R = 8% (손절 -8% 거리와 동일)
MAX_HOLD_F = 60


def outcome_f(rows, si, direction, atr=None):
    """방식F 수익률. 반환 (ret, hold_bars)."""
    if atr is None:
        atr = atr_series(rows)
    base = rows[si]["c"]
    last = len(rows) - 1
    end = min(si + MAX_HOLD_F, last)
    sgn = 1 if direction == "long" else -1
    sl_px = base * (1 - sgn * R_PCT)          # 초기 손절 (-1R)
    tp_px = base * (1 + sgn * R_PCT)          # +1R 익절 트리거
    scaled = False                            # 50% 익절 완료 여부
    extreme = rows[si]["h"] if direction == "long" else rows[si]["l"]
    trail = None

    def _ret(px):   # 방향 반영 단순 수익률
        return sgn * (px - base) / base

    for j in range(si + 1, end + 1):
        h, l, o = rows[j]["h"], rows[j]["l"], rows[j]["o"]
        hit_sl = (l <= sl_px) if direction == "long" else (h >= sl_px)
        hit_tp = (h >= tp_px) if direction == "long" else (l <= tp_px)

        if not scaled:
            if hit_sl:                        # 손절 우선(보수적) — 전량 -1R
                return -R_PCT - FEE, j - si
            if hit_tp:                        # 50% 익절 + 본전 이동
                scaled = True
                sl_px = base                  # breakeven
        else:
            # 잔여분: 본전선 vs chandelier 중 유리한(높은/낮은) 쪽
            if hit_sl_scaled(rows, j, direction, sl_px):
                px = exit_px(rows, j, direction, sl_px)
                return 0.5 * R_PCT + 0.5 * _ret(px) - FEE, j - si

        # chandelier 갱신 (진입 후 극값 기준, scaled 여부 무관하게 추적)
        extreme = max(extreme, h) if direction == "long" else min(extreme, l)
        a = atr[j] if atr[j] is not None else (h - l)
        cand = extreme - sgn * ATR_MULT * a
        if trail is None:
            trail = cand
        else:
            trail = max(trail, cand) if direction == "long" else min(trail, cand)
        if scaled:
            # 잔여분 손절선 = max(본전, chandelier) (롱 기준; 숏은 min)
            new_sl = max(base, trail) if direction == "long" else min(base, trail)
            sl_px = new_sl

    # 타임스탑 (시가)
    px = rows[end]["o"]
    if scaled:
        return 0.5 * R_PCT + 0.5 * _ret(px) - FEE, end - si
    return _ret(px) - FEE, end - si


def hit_sl_scaled(rows, j, direction, sl_px):
    return (rows[j]["l"] <= sl_px) if direction == "long" else (rows[j]["h"] >= sl_px)


def exit_px(rows, j, direction, sl_px):
    """갭 통과 시 시가 체결(보수적)."""
    o = rows[j]["o"]
    if direction == "long":
        return min(sl_px, o) if o < sl_px else sl_px
    return max(sl_px, o) if o > sl_px else sl_px


METHOD_FNS_4 = {
    "A": lambda rows, si, d, opp, atr: outcome_a(rows, si, d),
    "D": lambda rows, si, d, opp, atr: outcome_d(rows, si, d, opp),
    "E": lambda rows, si, d, opp, atr: outcome_e(rows, si, d, atr),
    "F": lambda rows, si, d, opp, atr: outcome_f(rows, si, d, atr),
}


def main():
    print("=" * 88)
    print("청산방식 4종 비교: A(±10%) / D(-8%SL·반대·레짐) / "
          f"E(Chandelier x{ATR_MULT:g}) / F(50%익절+본전+트레일)")
    print("=" * 88)
    data = collect(METHOD_FNS_4)
    stats = print_table(data, ["A", "D", "E", "F"])

    out = {}
    print("  [게이트] 방식E·F vs 방식D (3축: 기대값·MDD·Calmar)")
    for label, per in stats.items():
        if "D" not in per:
            continue
        entry = {"stats": {t: {k: round(v, 5) for k, v in s.items()} for t, s in per.items()}}
        nm = "전체(pooled)" if label == "_pooled" else label
        for tag in ("E", "F"):
            if tag not in per:
                continue
            g = gate_vs(per["D"], per[tag], "D", tag)
            mark = {"adopt": "O", "keep_base": "X", "reject": "X"}[g["verdict"]]
            print(f"    {nm:<17}{tag} {mark} {g['detail']}"
                  + ("  [3축 전승]" if g["all_wins"] else ""))
            entry[f"gate_{tag.lower()}_vs_d"] = g
        out[label] = entry

    json.dump(out, open("method_f.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2, default=lambda x: round(float(x), 5))
    print("\n[저장] method_f.json")
    return out


if __name__ == "__main__":
    main()
