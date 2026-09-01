"""
detector_cascade_fade_1h.py — 청산 캐스케이드 페이드 (1h, 롱).

과매도 급락 직후의 반등을 노린다. 강제청산 연쇄(liquidation cascade)로 가격이
과도하게 눌린 뒤 매수세가 들어와 봉 하단에서 회복되는 순간을 잡는다.

동결 파라미터 (2026-08-29 사전등록 재시험 통과 조건 — 절대 변경 금지)
--------------------------------------------------------------------
  MOVE_ATR = 2.5   하락폭이 ATR14 의 2.5배 이상
  VOL_MULT = 3.0   거래량이 직전 20봉 평균의 3배 이상
  RECOVER  = 0.40  종가가 봉 범위의 하단 40% 지점 위로 회복

검증 결과: n=312, mean +2.43%, median +1.17%, boot_p 0.000, OOS 3/4,
절사평균 +1.87%, 상위 5거래 기여 10.8% (소수 대박 의존 아님).
민감도는 단조 — 완화하면 즉시 소멸(2.0ATR/2.5배/0.3 → mean +0.01%),
엄격하면 강해짐(3.0/4.0/0.5 → +5.04%). 임의 최적점이 아니다.

청산은 registry.json 의 `exit_spec` 이 지정한다 (±1.5×ATR14 / 12봉).
paper_executor.eval_I + OKX OCO 브래킷이 집행한다 — 여기서는 진입만 판정한다.

**배포 상태: passed_not_deployed.**
2026-09-01 진입 지연 민감도 측정에서 엣지가 시간당 약 25% 감쇠함이 확인됐다:
  d=0 +2.43%(통과) / d=1 +1.88%(통과) / d=2 +1.09%(기각)
현행 스케줄러(4h 주기 + Actions 큐 지연)는 평균 2.6~3.6시간 늦게 진입해 전 조건
기각이다. 따라서 이 디텍터는 작성돼 있지만 `universe.json` 의
`adopted_1h_patterns` 에 **등록하지 않는다** — 등록하면 검증이 기각한 조건으로
실거래가 돌아간다. 1시간 이내 진입이 보장되는 상시 실행 환경을 갖춘 뒤,
그 환경의 실측 지연으로 재확인하고 등록한다.
(validate_cascade_delay.py / report_followup_2026_09.md 참조)
"""
import detlib

# 동결 파라미터 — validate_cascade.py 와 동일해야 한다(test_cascade_detector.py 로 고정)
MOVE_ATR = 2.5
VOL_MULT = 3.0
RECOVER = 0.40
ATR_N = 14
VOL_N = 20
WARMUP = 25          # ATR14 + 20봉 거래량 평균에 필요한 최소 이력


def _atr(rows, period=ATR_N):
    """단순평균 ATR. intraday_lab.atr_series 와 동일한 계산."""
    out = [None] * len(rows)
    trs = []
    for i in range(1, len(rows)):
        hi, lo, pc = rows[i]["h"], rows[i]["l"], rows[i - 1]["c"]
        trs.append(max(hi - lo, abs(hi - pc), abs(lo - pc)))
        if len(trs) >= period:
            out[i] = sum(trs[-period:]) / period
    return out


def detect(rows):
    """
    캐스케이드 페이드 신호(롱)가 발생한 봉 인덱스 리스트.

    백테스트용 탐지와 달리 **마지막 봉까지 검사한다** — 스케줄러가 실시간으로
    `last in detect(rows)` 를 보기 때문이다. 전방 데이터가 필요한 것은 라벨링
    쪽이지 탐지 조건이 아니므로, 여기서 뒤를 잘라내면 실거래 신호가 영영
    발생하지 않는다.
    """
    if len(rows) <= WARMUP:
        return []
    atr = _atr(rows)
    out = []
    for i in range(WARMUP, len(rows)):
        a = atr[i]
        if not a or a <= 0:
            continue
        r0 = rows[i]
        rng = r0["h"] - r0["l"]
        if rng <= 0:
            continue
        # 1) 하락폭이 ATR 의 MOVE_ATR 배 이상 (음봉만)
        move = r0["c"] - r0["o"]
        if move >= 0 or abs(move) < MOVE_ATR * a:
            continue
        # 2) 거래량 급증
        vavg = sum(x["v"] for x in rows[i - VOL_N:i]) / VOL_N
        if vavg <= 0 or r0["v"] < vavg * VOL_MULT:
            continue
        # 3) 봉 하단에서 회복 — 캐스케이드가 소진되고 매수세가 들어온 흔적
        if (r0["c"] - r0["l"]) / rng < RECOVER:
            continue
        out.append(i)
    return out


# 스케줄러가 쓰는 진입점.
load_ohlcv = detlib.load_ohlcv
SYMBOLS = detlib.SYMBOLS

# **evaluate 를 의도적으로 노출하지 않는다.**
# detlib.make_evaluate 는 동결 라벨(±10% / 20봉 / 1d 기준)을 쓴다. 그 라벨은 1h 에서
# 배리어 도달률이 0%라 측정값이 '랜덤 - 수수료'로 수렴한다 — 이 레포의 하위 TF 판정이
# 전부 측정 오류였다는 2026-08-29 발견의 핵심이다. evaluate 를 노출하면
# orchestrator(hasattr(mod,"evaluate") 로 탐지)가 이 패턴을 그 라벨로 재평가해
# 검증된 수치를 무의미한 값으로 덮어쓸 수 있다.
# 이 패턴의 성과 측정은 ATR 프레임(intraday_lab.outcome_atr)을 쓰는
# validate_cascade.py / validate_cascade_delay.py 로만 한다.
