# 1h 전용 패턴 발굴 리포트

**날짜**: 2026-06-29  
**검증 심볼**: 43개 (data/*_1h.csv)  
**데이터 범위**: 2021-01-01 ~ 2026-06-23 (약 5년, BTC 기준 ~47,967봉)  
**게이트 동결**: n>=20, mean>0, median>0, boot_p<0.05, OOS>=2/4

---

## 검증 결과

| 패턴 | 방향 | n | mean | median | OOS+ | boot_p | 판정 |
|------|------|---|------|--------|------|--------|------|
| **bat_1h** | long | 108 | **+1.46%** | **+0.99%** | **4/4** | **0.034** | **PASSED** |
| **butterfly_1h** | long | 161 | **+1.59%** | **+1.17%** | **4/4** | **0.024** | **PASSED** |
| gartley_1h | long | 290 | +0.91% | +0.30% | 4/4 | 0.092 | 기각 (boot_p 경계) |
| three_soldiers_1h | long | 2,107 | +0.28% | +0.02% | 3/4 | 0.270 | 기각 (유의성없음) |
| three_crows_1h | short | 1,623 | +0.38% | -0.04% | 3/4 | 0.247 | 기각 (median<0) |
| fvg_long_1h | long | 56,977 | +0.06% | -0.30% | 3/4 | 0.372 | 기각 (median<0) |
| breakout_retest_1h | long | 51,316 | -0.05% | -0.34% | 3/4 | 0.434 | 기각 |
| engulfing_1h | long | 16,791 | -0.23% | -0.33% | 0/4 | 0.525 | 기각 |
| inverted_hammer_1h | long | 34,061 | -0.08% | -0.20% | 0/4 | 0.444 | 기각 |
| fvg_short_1h | short | 56,977 | -0.46% | -0.10% | 0/4 | 0.628 | 기각 |
| vwap_rev_long_1h | long | 41,793 | -0.09% | -0.20% | 1/4 | 0.453 | 기각 |
| vwap_rev_short_1h | short | 38,984 | -0.19% | -0.10% | 1/4 | 0.485 | 기각 |

---

## 통과 패턴 상세

### Bullish Bat 1h

| 구간 | n | mean |
|------|---|------|
| Q1 (2021.01~2022.08) | 22 | +0.95% ✓ |
| Q2 (2022.08~2024.01) | 33 | +1.21% ✓ |
| Q3 (2024.01~2025.05) | 25 | +1.26% ✓ |
| Q4 (2025.05~2026.06) | 28 | +2.33% ✓ |

- OOS 4/4 완전 통과 — bear 구간(Q4)에서도 +2.33%
- boot_p=0.034 < 0.05 ✓
- **레짐 필터 불필요**: 모든 레짐에서 신호 탐지 (regime_routing="all")
- 사용 모듈: `detector_bat.py` with tf="1h"

### Bullish Butterfly 1h

| 구간 | n | mean |
|------|---|------|
| Q1 (2021.01~2022.08) | 39 | +1.82% ✓ |
| Q2 (2022.08~2024.01) | 36 | +1.46% ✓ |
| Q3 (2024.01~2025.05) | 43 | +1.77% ✓ |
| Q4 (2025.05~2026.06) | 43 | +1.29% ✓ |

- OOS 4/4 완전 통과 — 모든 구간에서 +1.29% 이상
- boot_p=0.024 < 0.05 ✓
- **레짐 필터 불필요**: Q4(bear) 포함 전 구간 양수
- 사용 모듈: `detector_butterfly.py` with tf="1h"

---

## 주목할 기각 패턴

### Gartley 1h (boot_p 경계 탈락)
- n=290, mean=+0.91%, OOS 4/4 ← 가장 아쉬운 탈락
- **boot_p=0.092**: 0.05 기준 탈락, 게이트 동결 적용
- 재시험 조건: 데이터 누적 후 (표본 400+ 목표)

### Three Soldiers / Crows 1h
- 신호 많음 (2,107 / 1,623)이지만 베이스라인 대비 우위 없음
- 1h 단위 3연속 대형 캔들이 너무 흔해 선별력 상실

---

## 스케줄러 통합

- `universe.json["adopted_1h_patterns"]`: bat_1h, butterfly_1h 등재
- `scheduler.py`: `_1h_symbols()` 추가, adopted_1h_patterns 루프 추가
- **레짐 무관** 전체 스캔 (4h 패턴과 달리 bear 포함)
- 탐지 대상: 43개 1h 심볼 전체
- `tf_confirmed=True` (1h 자체 신호)
- 스케줄러 oncequick(4h마다) 실행 시 최신 1h봉 기준 탐지

---

## 패턴 레지스트리 현황 (2026-06-29 기준)

| 패턴 | TF | 방향 | 상태 |
|------|-----|------|------|
| engulfing | 1d | long | passed |
| fvg | 1d | long/short | passed |
| inverted_hammer | 1d | long | passed |
| marubozu | 1d | long | passed |
| gartley | 4h | long | passed |
| bat | 4h | long | passed |
| butterfly | 4h | long | passed |
| three_soldiers_4h | 4h | long | passed |
| **bat_1h** | **1h** | **long** | **passed (신규)** |
| **butterfly_1h** | **1h** | **long** | **passed (신규)** |

**총 10종 통과** (1d 4종 + 4h 4종 + 1h 2종)

---

## 다음 단계

- [ ] Gartley 1h: 데이터 누적 후 재시험 (현재 n=290, boot_p=0.092)
- [ ] bat_1h / butterfly_1h 실제 신호 발생 모니터링
- [ ] 1h 패턴 페이퍼테스트 성과 추적 (1개월 후)
- [ ] Three Crows 1h: 레짐 조건부 재검증 (bear 구간만)

---

_게이트 동결 유지: n>=20, mean>0, median>0, boot_p<0.05, OOS>=2/4_
