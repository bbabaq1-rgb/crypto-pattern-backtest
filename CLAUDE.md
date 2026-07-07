# crypto-pattern-backtest

## 프로젝트 목적
암호화폐 차트 패턴 자동 감지 → 백테스트 → 자동매매 시스템

## 현재 상태 (2026-06-29)
- 검증 완료 패턴: engulfing(validated), fvg(passed), inverted_hammer(passed), marubozu(passed)
- 하모닉 패턴: gartley/bat/butterfly PASSED(4h), crab/shark/cypher 보류(표본부족/mean<eff)
- **신규 4h 패턴**: three_soldiers_4h PASSED (n=908, mean=+1.04%, OOS 3/4, p<0.0001)
  - bull_btc/bull_altseason → 롱 전용, bear/sideways 스킵
  - 나머지 6종 기각 (three_crows/breakout_retest/equal_highs_lows/vwap_rev)
- **신규 1h 패턴**: bat_1h PASSED (n=108, mean=+1.46%, OOS 4/4, boot_p=0.034)
- **신규 1h 패턴**: butterfly_1h PASSED (n=161, mean=+1.59%, OOS 4/4, boot_p=0.024)
  - 레짐 무관 전 구간 양수 (bear Q4도 양수), 스케줄러 all regimes 탐지
  - 나머지 10종 기각 (gartley_1h boot_p=0.092 경계 탈락 포함)
- 레짐 스위치: bull_btc→롱, bear/altseason→숏
- 청산 로직: 방식A(±10%) / 방식D(-8% 손절+조건부 익절) 병행
- 방식D 게이트: Calmar 기반 — engulfing/fvg/engulfing_short → D 채택, fvg_short → A 유지
- **청산 방식 E·F 기각** (2026-07-03): E(Chandelier ATR22×3) vs D 0/3 전패(MDD -71.5%),
  F(50%익절+본전+트레일) pooled 0/3 (fvg_short만 2/3) — 페이퍼 병행 등재 안 함 (method_e/f.py, report.md)
- **청산 방식 G·H 기각** (2026-07-06): G(복합스코어 60/80점) pooled 0/3 — 단
  **inverted_hammer에서 2/3 우위(+8.32% vs +4.04%, Calmar 2배)** → 데이터 누적 후
  '해당 패턴 한정 G' 재검토 가치. H(HH 3봉실패) 전 패턴 0/3(조기청산). 참고: 손절 공유
  방식은 MDD 동률이라 3축 전승 구조적 불가 (method_g/h.py, report.md)
- **1h 추가 기각** (2026-07-03): bb_zscore_1h·rsi_extreme_1h 롱/숏 4방향 전부 REJECTED
  (mean 음수, boot_p 0.42~0.60, 저볼륨 필터로도 미달 — registry rejected_1h 14건)
- 유니버스: **71종목** (업비트KRW∩OKX선물, 2026-06-29)
- **패턴별 차등 유니버스** (2026-07-06 사용자 결정, 거래대금 코호트 분석 기반):
  engulfing→top20, fvg→top30 (30일 평균 거래대금 상위, 매 실행 재계산),
  inverted_hammer/marubozu→메이저 7종목 (scheduler.PATTERN_UNIVERSE).
  근거: 코호트 분석 — engulfing top20까지 엣지 유지(+2.65%/중앙+9.9%), fvg top30이
  전체보다 질 우위(+2.36%/중앙+6.5%), ih·marubozu는 top7 밖 급감/불안정.
  하모닉 4h·1h 패턴은 기존 검증 유니버스 유지. 경계 과적합 주의 — 분기별 재점검 권장
- **자동화**: GitHub Actions 4h마다 실행 (oncefull@UTC00:00 / oncequick@04~20시)
- **실거래 안전장치** (2026-07-06): MAX_LIVE_POS 12(사용자 승인 5→12) ·
  킬스위치(equity HWM $287.57 대비 -20% → 신규 진입 중지, paper_executor.EQUITY_HWM) ·
  손절 algo 주문 매 실행 자동점검(ensure_stop_orders, 누락 시 재등록) ·
  텔레그램 알림(notify.py — TELEGRAM_BOT_TOKEN/CHAT_ID secrets 등록 시 활성)
- **멀티 TF 확증**: 1d 신호 → 4h 최근 3봉 확증. 비확증 시 size 50% 축소
- **RS 필터** (2026-07-08, 롱 전용 채택): BTC 대비 상대강도(relative_strength.py,
  베타조정 7/14/30봉 가중). 롱 rs_score<0.2 → weak_rs 사이징 ×0.5. 백테스트:
  롱 RS유리 +11.32%(Calmar 1.38) vs 불리 +6.58%. **숏은 무상관으로 미적용**.
  앙상블 동점 시 롱은 RS 높은 종목 우선. avg_alt_rs(알트시즌 근접도)는 관측 모드
  (레짐 통합은 REGMAP 재검증 필요 — 데이터 축적 후)
- 페이퍼테스트: 진행 중 (A +6.59%, D +3.13%, 13건 — 표본 부족, 판단 유보)

## 다음 할 일
- [ ] OKX 선물 실거래 활성화 — GitHub Actions secrets(OKX_KEY/SECRET/PASSPHRASE) 등록만 남음
- [x] 하모닉 패턴 페이퍼테스트 등록 (gartley/bat/butterfly 4h)
- [x] 트레이딩 유니버스 확대 (업비트KRW x OKX선물, 71종목)
- [x] 4h 스케줄러 (oncefull/oncequick, 4시간마다, GitHub Actions 6회/일)
- [x] 멀티 TF 확증 필터 (1d 신호 → 4h 3봉 확증, 비확증 size 50%)
- [x] 4h 전용 패턴 발굴 (7종 테스트, three_soldiers_4h 통과)
- [x] 1h 전용 패턴 발굴 (12종 테스트, bat_1h/butterfly_1h 통과)
- [ ] Streamlit 대시보드 (실거래 데이터 한 달 후)
- [ ] crab/shark/cypher 재시험 (데이터 누적 후)
- [ ] gartley_1h 재시험 (데이터 누적 후, 현재 boot_p=0.092)
- [ ] 데이터 부족 종목 재검토 (universe.json data_short 75종목, 6개월 후)

## 핵심 원칙
- 게이트 동결: n≥20, 평균수익>0, 중앙값>0, 베이스라인 p<0.05, OOS 양구간 통과
- 매매 결정은 결정론적 코드만 — LLM은 코드 생성/수정만
- 손절 주문 없으면 실거래 절대 안 됨

## 주요 파일
- scheduler.py: 메인 스케줄러
- paper_executor.py: 페이퍼/실거래 체결 엔진
- exchange.py: OKX 연결
- regime_switch.py: 레짐 판정
- orchestrator.py: 패턴 검증 루프
- method_d.py: 방식A vs D 비교 + Calmar 게이트 (method_d.json 출력)
- detector_harmonic_base.py: 하모닉 공통 라이브러리 (find_pivots, check_ratios, make_detect)
- detector_gartley/bat/butterfly/crab/shark/cypher.py: 하모닉 6종 디텍터
- universe.json: 71종목 유니버스 (trading_universe), data_short 75종목, rejected 20종목
- expand_universe.py: 유니버스 확대 스크립트 (업비트KRW∩OKX선물, 재실행 가능)
- report_universe_expansion.md: 유니버스 확대 리포트
- registry.json: 패턴 등록부 (passed 10종: 1d×4 + 4h×4 + 1h×2)
- research_log.csv: 106건 시험 기록
- detector_three_soldiers_4h.py: 3연속 장대 양봉 (4h, PASSED)
- detector_three_soldiers_1h.py / detector_three_crows_1h.py: 1h 버전 (검증용)
- detector_vwap_rev_long/short_1h.py / detector_breakout_retest_1h.py: 1h 기각
- report_4h_expansion.md: 4h 확장 + Three Crows 레짐 재검증 리포트
- report_1h_expansion.md: 1h 확장 리포트 (bat/butterfly 통과)
