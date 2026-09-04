# 기각·정지 패턴 55종 레짐별 전수 재시험 (2026-09-04)

사용자 질문: "지금까지 레짐 구분 없이 백테스트했으면 하모닉이든 다른 패턴이든 기각했던 것들도
전부 다시 봐야 하는 것 아닌가." → 배포 6종에서 쓴 레짐 분리 게이트(validate_regime_split)를
rejected / suspended_lookahead / holding 패턴 **전부**에 적용했다.
실행: validate_regime_split_all.yml run #1 (2026-09-04 10:09~10:35 KST, 25분). 실거래 코드 무변경.

## 설계 (실행 전 고정)
- 패턴 55: 1d 21(기각 15 + 캔들 6) / 1w 2 / 4h 15(기각 7 + 하모닉 6 인과판 + triple_bottom_4h +
  three_soldiers_4h 레짐 확인) / 1h 17(기각 14 + 하모닉 1h 인과판 3).
- 셀 = 패턴 × 진입 레짐(bull_btc / bull_altseason / bear / sideways / ALL) × 코호트(all / top30) = **440셀**
  (sideways 는 5년간 0일이라 셀 없음).
- 레짐 = 진입 봉 날짜의 일봉 레짐(4h/1h 도 같은 라벨 — 실거래 라우팅 기준).
- 라벨: 1d/1w/4h ±10%/20봉(원 검증과 동일), **1h ±1.5ATR/12봉**(intraday_lab, 원 ±10% 라벨은
  1h 에서 측정 오류였음). 하모닉·triple_bottom 은 룩어헤드 제거 판(confirm/causal)만.
- boot_p 베이스라인 = 같은 레짐·코호트·TF 무작위 진입. 게이트 동결(n≥20, mean>0, median>0, boot_p<.05, OOS≥2/4).
- 다중검정: STRICT = 두 코호트 PASSED + boot_p<.01 + 양수 해≥2. 440셀이면 α=.05 우연 통과 기대 ≈22.
- 데이터: 유니버스 80 종목. 1d 1800일(1580일 레짐: 2022 bear 237 / 2023 bull 334 / 2024 bull 331 /
  2025 bull 329 / 2026 bear), 4h 1100일, 1h 365일(**1h 는 1년치라 bear 77%** — 국면 편중).

## 결과 — PASSED 0 / STRICT 0 (440셀)
우연 통과 기대치 22 인데 0 이다. 게이트가 median>0·OOS 까지 요구해서 boot_p 단독보다 훨씬 좁다.
**레짐을 나눠도 기각 패턴은 살아나지 않는다.** 사용자 가설(레짐 상쇄)은 배포 6종에서는 맞았지만
(engulfing 롱 bull_btc 등 2셀), 기각 목록에는 숨어 있는 셀이 없다.

### boot_p 만 탈락한 셀 81 중 가까운 것 (n≥20, mean·median>0, OOS 통과)
| 패턴 | 코호트 | 레짐 | n | mean | med | 엣지 | boot_p |
|---|---|---|---|---|---|---|---|
| order_block_short_1d | all | bull_altseason | 39 | +5.69% | +11.28% | +3.80%p | .060 |
| triple_bottom_4h | all | bull_altseason | 167 | +2.02% | +1.98% | +2.29%p | .063 |
| triple_bottom_1w | top30 | ALL | 35 | +6.20% | +3.82% | +5.81%p | .078 |
| bat_1h | all | ALL | 50 | +0.23% | +0.70% | +0.53%p | .081 |
| three_crows_4h | top30 | bear | 24 | +1.90% | +2.06% | +1.75%p | .101 |
| marubozu_short_1d | all | bull_btc | 72 | +3.25% | +10.29% | +3.25%p | .123 |
| triple_bottom_1d | top30 | ALL | 206 | +2.82% | +1.60% | +2.91%p | .124 |
| liquidity_sweep_1d | top30 | ALL | 39 | +2.73% | +9.91% | +2.82%p | .130 |

- 전부 boot_p .06~.13 — 440셀 중 상위 몇 개가 .06 근처에 오는 것은 우연 분포 그대로다.
  가장 가까운 order_block_short(bull_altseason n=39)은 2023 altseason 62일에 몰린 표본.
- **triple_bottom 계열이 반복해서 위쪽에 온다**(1w top30 +6.2%, 4h altseason +2.0%, 1d top30 +2.8%).
  9/3 재검증에서 1w 인과판이 REJECT(median −11%) 였는데, top30 으로 좁히면 median 이 +3.8% 로
  바뀐다(n=35). 표본이 작아 판정 불가 — 데이터 누적 후 **'triple_bottom top30'** 하나만 사전 등록 재시험 후보.

### 배포·정지 패턴 sanity (ALL 레짐, all 코호트)
| 패턴 | n | mean | med | 엣지 | boot_p | 비고 |
|---|---|---|---|---|---|---|
| three_soldiers_4h (배포) | 360 | +0.52% | +0.10% | +0.80%p | .284 | bull_btc 셀 n=194 +1.57% med +1.82% bp .165 |
| triple_bottom_1w (정지) | 98 | +3.46% | −11.66% | +4.48%p | .146 | 9/3 재검증과 일치(median 음수) |
| gartley_4h / bat_4h / butterfly_4h | 54/52/41 | +0.66/+0.36/−0.31% | | | .25/.33/.50 | 인과판 전부 기각 재확인 |
| bat_1h / butterfly_1h / gartley_1h | 50/80/143 | +0.23/−0.13/−0.28% | | | .08/.32/.49 | ATR 프레임에서도 기각 |

- **three_soldiers_4h 주의**: 원 등재(n=908, +1.04%, boot_p<.0001)는 무조건부 베이스라인·다른 창이었다.
  같은 레짐 무작위 진입을 베이스라인으로 잡으면 bull_btc 셀이 boot_p .165 로 게이트 밖이다.
  이 프레임이 더 보수적인 것이지 패턴이 죽었다는 증거는 아니지만, **배포 유지 근거가 약해졌다** —
  별도 판정(원 프레임 + 레짐 베이스라인 병기, 4h 1100일 → 최대 창) 필요. 실거래는 bull 레짐에서만
  진입하므로 현 bear 레짐에서는 영향 없음.

## 결론
1. 기각·정지 55종은 레짐을 나눠도 **복귀 후보 0**. 재시험 종료.
2. 후속 후보는 하나: triple_bottom(top30 코호트) — 데이터 누적 후 사전 등록.
3. three_soldiers_4h 는 레짐 베이스라인으로 재판정 필요(배포 유지 여부는 사용자 결정).
4. 1h 셀은 1년치(bear 편중)라 bull 셀 결론은 약함 — 1h 는 결론을 '기각 유지'로만 읽을 것.

validate_regime_split_all.py / test_regime_split_all.py(34건) / _regime_split_all.json(artifact regime-split-all-1)
