# 자동 패턴 연구 보고서

- 등재 패턴: **14개**
- 누적 시험(로그 행): **8건**
- 상태 분포: needs_impl 10, passed 1, pending 2, rejected 1
- 게이트(동결): n>=20 AND 평균수익>임계 AND 중앙값>0, 라벨 대칭 ±10%, 수수료 왕복 0.2%, 다중비교 보정은 평균임계.

## 상태 분류

| status | 패턴 |
|---|---|
| passed | engulfing |
| rejected | triple_bottom_desc |
| needs_impl | pin_bar, nr7, bb_squeeze, double_bottom, fvg, inverse_hs, macd_divergence, order_block, bos_choch, spring_wyckoff |
| pending | liquidity_sweep, rsi_divergence |

## 패턴 × 타임프레임 결과

| 패턴 | TF | n | 평균수익 | 중앙값 | 진짜율 | verdict | OOS(IS/OOS) |
|---|---|---|---|---|---|---|---|
| engulfing | 1d | 60 | +3.43% | +9.99% | 56.7% | 통과 | IS:통과(n35,+3.53%) / OOS:통과(n25,+3.28%) |
| pin_bar | - | - | - | - | - | (미시험) | - |
| nr7 | - | - | - | - | - | (미시험) | - |
| bb_squeeze | - | - | - | - | - | (미시험) | - |
| double_bottom | - | - | - | - | - | (미시험) | - |
| liquidity_sweep | - | - | - | - | - | (미시험) | - |
| fvg | - | - | - | - | - | (미시험) | - |
| inverse_hs | - | - | - | - | - | (미시험) | - |
| rsi_divergence | - | - | - | - | - | (미시험) | - |
| macd_divergence | - | - | - | - | - | (미시험) | - |
| order_block | - | - | - | - | - | (미시험) | - |
| bos_choch | - | - | - | - | - | (미시험) | - |
| spring_wyckoff | - | - | - | - | - | (미시험) | - |
| triple_bottom_desc | - | - | - | - | - | (미시험) | - |

## 현재 살아있는 수익모델 후보

- **engulfing** (Engulfing) — 1d 전체+OOS 통과, 승인 대기

## 기각(rejected) 요약

- triple_bottom_desc (Triple Bottom (descending)) — 사전 기각(별도 분석)
