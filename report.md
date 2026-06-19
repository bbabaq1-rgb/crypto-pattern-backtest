# 자동 패턴 연구 보고서

- 등재 패턴: **14개**
- 누적 시험(로그 행): **2건**
- 상태 분포: holding 1, needs_impl 12, rejected 1

## 상태 분류

| status | 패턴 |
|---|---|
| holding | liquidity_sweep |
| rejected | triple_bottom_desc |
| needs_impl | engulfing, pin_bar, nr7, bb_squeeze, double_bottom, fvg, inverse_hs, rsi_divergence, macd_divergence, order_block, bos_choch, spring_wyckoff |

## 패턴별 결과

| 패턴 | status | n | 진짜율 | verdict(전체) | OOS |
|---|---|---|---|---|---|
| engulfing | needs_impl | - | - | (미시험) | - |
| pin_bar | needs_impl | - | - | (미시험) | - |
| nr7 | needs_impl | - | - | (미시험) | - |
| bb_squeeze | needs_impl | - | - | (미시험) | - |
| double_bottom | needs_impl | - | - | (미시험) | - |
| liquidity_sweep | holding | 12 | 25.0% | 보류(표본부족) | - |
| fvg | needs_impl | - | - | (미시험) | - |
| inverse_hs | needs_impl | - | - | (미시험) | - |
| rsi_divergence | needs_impl | - | - | (미시험) | - |
| macd_divergence | needs_impl | - | - | (미시험) | - |
| order_block | needs_impl | - | - | (미시험) | - |
| bos_choch | needs_impl | - | - | (미시험) | - |
| spring_wyckoff | needs_impl | - | - | (미시험) | - |
| triple_bottom_desc | rejected | - | - | (미시험) | - |

## 현재 살아있는 후보

- 통과(passed) 후보 없음.

보류(표본부족, 재검토 대상):
- liquidity_sweep (Liquidity Sweep) — n=12, 진짜율 25.0%

## 기각(rejected) 요약

- triple_bottom_desc (Triple Bottom (descending)) — 사전 기각(별도 분석)
