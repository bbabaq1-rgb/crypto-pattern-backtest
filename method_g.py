"""
method_g.py — 청산 방식G (복합 스코어 익절) 백테스트.

방식G:
  손절: 방식D와 동일 -8% 인트라바 고정 — 점수 무관 항상 우선.
  익절: 매 봉 종가 기준 아래 5개 청산 신호를 점수화(롱 기준, 숏 대칭),
        당봉 합산 점수 ≥60 → 50% 익절(1회), ≥80 → 전량 익절.
    - 최고가 대비 2.5×ATR(22) 하락            → 40점
    - 20 EMA 종가 하향 이탈                    → 20점
    - 거래량 ≥ 20봉 평균×1.5 + 음봉            → 20점
    - MACD(12,26,9) 데드크로스(시그널 하향)     → 10점
    - RSI(14) ≥70 에서 하락 전환               → 10점
  최대 60봉 타임스탑(시가 — 방식D 관행).

해석 판단(스펙의 '누적'): 조건 다수가 지속 상태(EMA 이탈 등)라 봉 간 누적하면
수 봉 만에 무조건 청산돼 변별력이 없다. '당봉에 동시 발화한 신호의 합산 점수'로
해석한다(최대 100점, 임계 60/80과 정합). 판단 근거를 여기 기록해 둔다.

게이트 동결 — 판정 기준(gate_d 3축) 변경 없음, 청산 방식만 교체.
"""
import json

from method_d import outcome_a, outcome_d, FEE, STOP_LOSS_PCT
from method_e import atr_series, collect, print_table, gate_vs, PATS_ALL

MAX_HOLD_G  = 60
ATR_MULT_G  = 2.5
SCORE_HALF  = 60
SCORE_FULL  = 80

# rows 객체별 지표 캐시 (id 기준 — 같은 실행 내 재계산 방지, 결정론 유지)
_IND_CACHE: dict[int, dict] = {}


def _ema(vals, n):
    out = [None] * len(vals)
    if len(vals) < n:
        return out
    k = 2 / (n + 1)
    s = sum(vals[:n]) / n
    out[n - 1] = s
    for i in range(n, len(vals)):
        s = vals[i] * k + s * (1 - k)
        out[i] = s
    return out


def _rsi(closes, n=14):
    out = [None] * len(closes)
    if len(closes) <= n:
        return out
    gains = losses = 0.0
    for i in range(1, n + 1):
        d = closes[i] - closes[i - 1]
        gains += max(d, 0); losses += max(-d, 0)
    ag, al = gains / n, losses / n
    out[n] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    for i in range(n + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        ag = (ag * (n - 1) + max(d, 0)) / n
        al = (al * (n - 1) + max(-d, 0)) / n
        out[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def indicators(rows):
    """rows당 1회 계산: ATR22, EMA20, RSI14, MACD(12,26,9), 거래량 20MA."""
    key = id(rows)
    if key in _IND_CACHE:
        return _IND_CACHE[key]
    closes = [r["c"] for r in rows]
    vols   = [r["v"] for r in rows]
    atr    = atr_series(rows)              # n=22
    ema20  = _ema(closes, 20)
    rsi14  = _rsi(closes, 14)
    e12, e26 = _ema(closes, 12), _ema(closes, 26)
    macd   = [None if (a is None or b is None) else a - b for a, b in zip(e12, e26)]
    # 시그널(9EMA of MACD): None 구간 건너뛰고 계산
    sig    = [None] * len(rows)
    vals   = [(i, m) for i, m in enumerate(macd) if m is not None]
    if len(vals) >= 9:
        k = 2 / 10
        s = sum(m for _, m in vals[:9]) / 9
        sig[vals[8][0]] = s
        for i, m in vals[9:]:
            s = m * k + s * (1 - k)
            sig[i] = s
    volma = [None] * len(rows)
    run = 0.0
    for i, v in enumerate(vols):
        run += v
        if i >= 20:
            run -= vols[i - 20]
            volma[i] = run / 20
        elif i == 19:
            volma[i] = run / 20
    ind = dict(atr=atr, ema20=ema20, rsi=rsi14, macd=macd, sig=sig, volma=volma)
    _IND_CACHE[key] = ind
    return ind


def bar_score(rows, j, direction, extreme, ind):
    """당봉 j의 복합 청산 점수(롱 기준 정의, 숏은 대칭). 결정론."""
    c, o, v = rows[j]["c"], rows[j]["o"], rows[j]["v"]
    sgn = 1 if direction == "long" else -1
    pts = 0
    a = ind["atr"][j]
    if a is not None:
        # 1) 극값 대비 2.5 ATR 역행 (롱: 최고가에서 하락폭, 숏: 최저가에서 상승폭)
        adverse = (extreme - c) if direction == "long" else (c - extreme)
        if adverse >= ATR_MULT_G * a:
            pts += 40
    e = ind["ema20"][j]
    if e is not None and sgn * (e - c) > 0:            # 롱: 종가<EMA20, 숏: 종가>EMA20
        pts += 20
    vm = ind["volma"][j]
    adverse_candle = (c < o) if direction == "long" else (c > o)
    if vm and v >= 1.5 * vm and adverse_candle:        # 고거래량 역방향 봉
        pts += 20
    m0, s0 = ind["macd"][j], ind["sig"][j]
    m1, s1 = (ind["macd"][j - 1], ind["sig"][j - 1]) if j >= 1 else (None, None)
    if None not in (m0, s0, m1, s1):
        crossed_down = m1 >= s1 and m0 < s0
        crossed_up   = m1 <= s1 and m0 > s0
        if (direction == "long" and crossed_down) or (direction == "short" and crossed_up):
            pts += 10
    r0, r1 = ind["rsi"][j], ind["rsi"][j - 1] if j >= 1 else None
    if r0 is not None and r1 is not None:
        if direction == "long" and r1 >= 70 and r0 < r1:
            pts += 10
        if direction == "short" and r1 <= 30 and r0 > r1:
            pts += 10
    return pts


def outcome_g(rows, si, direction, atr=None):
    """방식G 수익률. 반환 (ret, hold_bars)."""
    ind  = indicators(rows)
    base = rows[si]["c"]
    last = len(rows) - 1
    end  = min(si + MAX_HOLD_G, last)
    sgn  = 1 if direction == "long" else -1
    extreme = rows[si]["h"] if direction == "long" else rows[si]["l"]
    half_done = False
    half_ret  = 0.0

    def _ret(px):
        return sgn * (px - base) / base

    for j in range(si + 1, end + 1):
        # 손절 항상 우선(인트라바)
        hit_sl = (rows[j]["l"] <= base * (1 - STOP_LOSS_PCT)) if direction == "long" \
            else (rows[j]["h"] >= base * (1 + STOP_LOSS_PCT))
        if hit_sl:
            if half_done:
                return half_ret + 0.5 * (-STOP_LOSS_PCT) - FEE, j - si
            return -STOP_LOSS_PCT - FEE, j - si

        # 극값 갱신 후 당봉 점수
        extreme = max(extreme, rows[j]["h"]) if direction == "long" \
            else min(extreme, rows[j]["l"])
        pts = bar_score(rows, j, direction, extreme, ind)
        c = rows[j]["c"]
        if pts >= SCORE_FULL:
            rem = 0.5 if half_done else 1.0
            return half_ret + rem * _ret(c) - FEE, j - si
        if pts >= SCORE_HALF and not half_done:
            half_done = True
            half_ret  = 0.5 * _ret(c)

    px = rows[end]["o"]                     # 타임스탑(시가)
    rem = 0.5 if half_done else 1.0
    return half_ret + rem * _ret(px) - FEE, end - si


def factory_fns():
    from method_e import outcome_e  # noqa: F401 (참고용 — G 비교엔 미사용)
    return {
        "A": lambda rows, si, d, opp, atr: outcome_a(rows, si, d),
        "D": lambda rows, si, d, opp, atr: outcome_d(rows, si, d, opp),
        "G": lambda rows, si, d, opp, atr: outcome_g(rows, si, d),
    }


def main():
    print("=" * 88)
    print("청산방식 비교: A(±10%) / D(-8%SL·반대·레짐) / G(복합 스코어 익절 60/80점)")
    print("=" * 88)
    data = collect(factory_fns())
    stats = print_table(data, ["A", "D", "G"])
    out = {}
    print("  [게이트] 방식G vs 방식D (3축: 기대값·MDD·Calmar)")
    for label, per in stats.items():
        if "D" not in per or "G" not in per:
            continue
        g = gate_vs(per["D"], per["G"], "D", "G")
        nm = "전체(pooled)" if label == "_pooled" else label
        mark = {"adopt": "O", "keep_base": "X", "reject": "X"}[g["verdict"]]
        print(f"    {nm:<17}{mark} {g['detail']}" + ("  [3축 전승]" if g["all_wins"] else ""))
        out[label] = dict(stats={t: {k: round(v, 5) for k, v in s.items()} for t, s in per.items()},
                          gate_g_vs_d=g)
    json.dump(out, open("method_g.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2, default=lambda x: round(float(x), 5))
    print("\n[저장] method_g.json")
    return out


if __name__ == "__main__":
    main()
