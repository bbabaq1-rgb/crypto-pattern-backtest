"""
exit_barriers.py — registry `exit_spec` 의 손절·익절 가격 산출 (스케줄러·체결엔진 공용)

두 곳(scheduler 의 신호 표기, paper_executor 의 실주문·체결가 재정렬)이 같은 식을 써야
알림·장부·거래소 OCO 가 일치한다. 종전에는 ±k×ATR 식이 두 파일에 각각 적혀 있었다.

exit_spec.type
  "atr_barrier" (기본, type 없고 k_atr 있으면 이것) — 진입가 ± k×ATR(period). cascade_fade_long_1h.
  "pct_barrier"                                  — 진입가 × (1 ± pct). 익절 tp_pct / 손절 sl_pct 가
                                                   비대칭이라 손절 거리 대칭 복원(barriers_of 폴백)을
                                                   쓰면 안 된다 — pct_target() 으로 다시 만든다.
                                                   tp1_engulfing_1h (2026-09-09 사용자 강제 실행: 1%/8%).

이 모듈은 가벼워야 한다(스케줄러가 import). intraday_lab 은 ATR 이 필요할 때만 지연 import.
"""


def spec_type(spec):
    t = (spec or {}).get("type")
    if t:
        return t
    return "atr_barrier" if (spec or {}).get("k_atr") is not None else None


def pct_target(spec, entry, direction):
    """pct_barrier 의 익절가(진입가 기준). 다른 타입이면 None."""
    if spec_type(spec) != "pct_barrier" or not entry:
        return None
    tp = float(spec["tp_pct"])
    return entry * (1 + tp) if direction == "long" else entry * (1 - tp)


def pct_stop(spec, entry, direction):
    if spec_type(spec) != "pct_barrier" or not entry:
        return None
    sl = float(spec["sl_pct"])
    return entry * (1 - sl) if direction == "long" else entry * (1 + sl)


def barriers(spec, rows, ei, entry, direction):
    """
    (stop_px, target_px, info) | None.
    info: atr_barrier → dict(atr=..., dist=...) / pct_barrier → dict(tp_pct, sl_pct).
    None 이면 청산 규칙을 정의할 수 없다(ATR 미산출 등) → 진입하지 않는다.
    """
    t = spec_type(spec)
    if t == "pct_barrier":
        stop, tgt = pct_stop(spec, entry, direction), pct_target(spec, entry, direction)
        if stop is None or tgt is None:
            return None
        return round(stop, 8), round(tgt, 8), dict(tp_pct=float(spec["tp_pct"]), sl_pct=float(spec["sl_pct"]))
    if t == "atr_barrier":
        import intraday_lab as ilab
        atr = ilab.atr_series(rows, spec.get("atr_period", 14))[ei]
        if not atr or atr <= 0:
            return None
        dist = spec.get("k_atr", ilab.K_ATR) * atr
        if direction == "long":
            stop, tgt = entry - dist, entry + dist
        else:
            stop, tgt = entry + dist, entry - dist
        return round(stop, 8), round(tgt, 8), dict(atr=atr, dist=dist)
    return None


def describe(spec):
    """알림·대시보드용 청산 규칙 한 줄."""
    t = spec_type(spec)
    if t == "pct_barrier":
        return (f"익절 +{float(spec['tp_pct']) * 100:g}% / 손절 −{float(spec['sl_pct']) * 100:g}% "
                f"거래소 OCO 브래킷 / {spec.get('horizon_bars', 2000)}봉 시간청산")
    if t == "atr_barrier":
        return (f"±{spec.get('k_atr', 1.5)}xATR{spec.get('atr_period', 14)} "
                f"거래소 OCO 브래킷 / {spec.get('horizon_bars', 12)}봉 시간청산")
    return "exit_spec 미정의"
