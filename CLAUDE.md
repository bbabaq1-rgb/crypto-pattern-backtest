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
- 유니버스: **71종목** (업비트KRW∩OKX선물, 2026-06-29)
- **자동화**: GitHub Actions 4h마다 실행 (oncefull@UTC00:00 / oncequick@04~20시)
- **멀티 TF 확증**: 1d 신호 → 4h 최근 3봉 확증. 비확증 시 size 50% 축소
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
