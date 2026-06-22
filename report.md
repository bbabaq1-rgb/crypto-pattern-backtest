# 자동 패턴 연구 보고서

- 등재 패턴: **14개**
- 누적 시험(로그 행): **39건**
- 상태 분포: needs_impl 7, rejected 6, validated 1
- 게이트(동결): n>=20 AND 평균수익>임계 AND 중앙값>0, 라벨 대칭 ±10%, 수수료 왕복 0.2%, 다중비교 보정은 평균임계.

## 상태 분류

| status | 패턴 |
|---|---|
| validated | engulfing |
| rejected | pin_bar, nr7, double_bottom, liquidity_sweep, rsi_divergence, triple_bottom_desc |
| needs_impl | bb_squeeze, fvg, inverse_hs, macd_divergence, order_block, bos_choch, spring_wyckoff |

## 패턴 × 타임프레임 결과

| 패턴 | TF | n | 평균수익 | 중앙값 | 진짜율 | verdict | OOS(IS/OOS) | 베이스라인 초과(p) |
|---|---|---|---|---|---|---|---|---|
| engulfing | 1d | 60 | +3.43% | +9.99% | 56.7% | 통과 | IS:통과(n35,+3.53%) / OOS:통과(n25,+3.28%) | +3.06% (p=0.033, 유의) |
| pin_bar | 1d | 21 | -2.31% | -10.22% | 42.9% | 기각 | - | - |
| pin_bar | 4h | 213 | -0.37% | -0.69% | 12.2% | 기각 | - | - |
| pin_bar | 1h | 1106 | -0.32% | -0.17% | 2.7% | 기각 | - | - |
| nr7 | 1d | 2219 | +0.03% | -0.69% | 38.3% | 기각 | - | - |
| nr7 | 4h | 13531 | -0.14% | -0.34% | 13.6% | 기각 | - | - |
| nr7 | 1h | 57090 | -0.16% | -0.24% | 3.1% | 기각 | - | - |
| bb_squeeze | - | - | - | - | - | (미시험) | - | - |
| double_bottom | 1d | 465 | +1.04% | +1.02% | 43.2% | 통과 | IS:통과(n254,+1.87%) / OOS:기각(n211,+0.04%) | +0.66% (p=0.144, 미초과) |
| double_bottom | 4h | 1562 | +0.58% | -0.35% | 22.1% | 기각 | - | - |
| double_bottom | 1h | 1870 | +0.56% | +0.16% | 12.8% | 통과 | IS:통과(n1382,+0.75%) / OOS:기각(n488,+0.02%) | +0.66% (p=0.0, 유의) |
| liquidity_sweep | 1d | 12 | +3.31% | +9.92% | 58.3% | 보류(표본부족) | - | - |
| liquidity_sweep | 4h | 230 | +0.49% | +0.17% | 17.4% | 통과 | IS:기각(n107,-0.08%) / OOS:통과(n123,+0.98%) | +0.49% (p=0.159, 미초과) |
| liquidity_sweep | 1h | 1463 | -0.18% | +0.05% | 1.8% | 기각 | - | - |
| fvg | - | - | - | - | - | (미시험) | - | - |
| inverse_hs | - | - | - | - | - | (미시험) | - | - |
| rsi_divergence | 1d | 378 | -0.75% | -2.30% | 36.8% | 기각 | - | - |
| rsi_divergence | 4h | 2169 | -0.16% | -0.19% | 13.2% | 기각 | - | - |
| rsi_divergence | 1h | 8502 | -0.22% | -0.12% | 2.9% | 기각 | - | - |
| macd_divergence | - | - | - | - | - | (미시험) | - | - |
| order_block | - | - | - | - | - | (미시험) | - | - |
| bos_choch | - | - | - | - | - | (미시험) | - | - |
| spring_wyckoff | - | - | - | - | - | (미시험) | - | - |
| triple_bottom_desc | - | - | - | - | - | (미시험) | - | - |

## 레짐별 기대값 (상승장 편승 여부 검증)

- **engulfing** @1d: up n10 평균+3.06%/중앙+10.14%, down n21 평균+5.70%/중앙+10.23%, side n22 평균-0.07%/중앙-0.35%, na n7 평균+8.08%/중앙+10.45%
- **double_bottom** @1d: up n132 평균-0.17%/중앙-2.39%, down n161 평균+0.28%/중앙-1.43%, side n132 평균+1.28%/중앙+1.72%, na n40 평균+7.26%/중앙+11.42%
- **double_bottom** @1h: up n351 평균+1.08%/중앙+0.05%, down n274 평균-0.41%/중앙-0.37%, side n1196 평균+0.51%/중앙+0.23%, na n49 평균+3.38%/중앙+2.32%
- **liquidity_sweep** @4h: up n27 평균-0.52%/중앙-2.76%, down n33 평균+2.42%/중앙+1.96%, side n169 평균+0.17%/중앙-0.08%, na n1 평균+17.70%/중앙+17.70%

## 1순위 후보 정밀검증

- **engulfing** (Engulfing) — status=**validated**
  - 슬리피지(+0.1%): 평균 +3.33%, 중앙 +9.89%, 베이스라인 p=0.033 → 통과
  - 워크포워드: 유효윈도우 8개 중 양수 5개 (62%) → 통과
  - 표본확대(신규5종): n=30, 평균 +3.89%, 종목별 양수 3/5 → 통과

## 현재 살아있는 수익모델 후보

- **engulfing** (Engulfing) — 1d 전체+OOS+베이스라인+정밀검증, 실거래 검토 가능(validated)

## 기각(rejected) 요약

- pin_bar (Pin Bar) — 기대값 음수
- nr7 (NR7 (Narrow Range 7)) — 기대값 음수
- double_bottom (Double Bottom) — OOS 미통과(과최적화)
- liquidity_sweep (Liquidity Sweep) — OOS 미통과(과최적화)
- rsi_divergence (RSI Divergence) — 기대값 음수
- triple_bottom_desc (Triple Bottom (descending)) — 사전 기각(별도 분석)
