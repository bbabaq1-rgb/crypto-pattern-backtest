# R-100 steward 공통 단위 전/후 (2026-11-08)

**steward 공통 단위 전/후 분리 INCONCLUSIVE (2026-11-08, 자율 연구 R-100, run 42501217105)**: registry `steward_common_prereg_2026_11_08` / validate_steward_common.py. 연구 전용, steward 상수·실거래 무변경, DEPLOY_ON_PASS=False. R-099 의 전(5단위)/후(3단위) 부호 반전이 단위 구성 때문인지 보려고 양 arm n>=10 인 공통 단위만 남겨 단위 안 층화 부트스트랩. 공통 단위 2개(tp1_engulfing_1h·vol_awakening_4h long): 전 n59 +1.21% CI [-1.04, 3.77] / 후 n34 -4.26% CI [-5.48, -2.94] / 후-전 -5.47 CI [-8.39, -2.80]. 단위별 tp1 -0.28→-1.78%, vol_awakening +2.56→-5.44%. 후 arm 공통 거래 34 < 40 이라 코드 판정 INCONCLUSIVE(전 평균 CI 하한<0 이라 n 요건 없이도 PHASE_EFFECT 아님 — 사후 라벨 변경 안 함). 같은 단위에서도 전→후 하락이 CI 로 확인돼 단위 구성만의 효과는 아니나 시간 감쇠와 국면 분리 불가. 진단 공통 prior 현행-NEVER: 전 -28.6 / 후 +273.5(부호 R-099 와 동일). 사전 INCONCLUSIVE 0.35 적중, PHASE_EFFECT 0.25 오답. 후속 R-102(전향 데이터)·R-103(entry_regime 라벨 분할).

사전 등록: registry steward_common_prereg_2026_11_08. 결과 아티팩트: run 42501217105 `_steward_common.json`.
