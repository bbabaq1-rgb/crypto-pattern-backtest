# 자동 패턴 연구 보고서

- 등재 패턴: **14개**
- 누적 시험(로그 행): **21건**
- 상태 분포: needs_impl 10, passed 1, rejected 3
- 게이트(동결): n>=20 AND 평균수익>임계 AND 중앙값>0, 라벨 대칭 ±10%, 수수료 왕복 0.2%, 다중비교 보정은 평균임계.

## 상태 분류

| status | 패턴 |
|---|---|
| passed | engulfing |
| rejected | liquidity_sweep, rsi_divergence, triple_bottom_desc |
| needs_impl | pin_bar, nr7, bb_squeeze, double_bottom, fvg, inverse_hs, macd_divergence, order_block, bos_choch, spring_wyckoff |

## 패턴 × 타임프레임 결과

| 패턴 | TF | n | 평균수익 | 중앙값 | 진짜율 | verdict | OOS(IS/OOS) | 베이스라인 초과(p) |
|---|---|---|---|---|---|---|---|---|
| engulfing | 1d | 60 | +3.43% | +9.99% | 56.7% | 통과 | IS:통과(n35,+3.53%) / OOS:통과(n25,+3.28%) | +3.06% (p=0.033, 유의) |
| pin_bar | - | - | - | - | - | (미시험) | - | - |
| nr7 | - | - | - | - | - | (미시험) | - | - |
| bb_squeeze | - | - | - | - | - | (미시험) | - | - |
| double_bottom | - | - | - | - | - | (미시험) | - | - |
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
- **liquidity_sweep** @4h: up n27 평균-0.52%/중앙-2.76%, down n33 평균+2.42%/중앙+1.96%, side n169 평균+0.17%/중앙-0.08%, na n1 평균+17.70%/중앙+17.70%

## 현재 살아있는 수익모델 후보

- **engulfing** (Engulfing) — 1d 전체+OOS 통과, 승인 대기

## 기각(rejected) 요약

- liquidity_sweep (Liquidity Sweep) — OOS 미통과(과최적화)
- rsi_divergence (RSI Divergence) — 기대값 음수
- triple_bottom_desc (Triple Bottom (descending)) — 사전 기각(별도 분석)
