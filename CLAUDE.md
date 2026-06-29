# crypto-pattern-backtest

## 프로젝트 목적
암호화폐 차트 패턴 자동 감지 → 백테스트 → 자동매매 시스템

## 현재 상태 (2026-06-29)
- 검증 완료 패턴: engulfing(validated), fvg(passed), inverted_hammer(passed), marubozu(passed)
- 하모닉 패턴: gartley/bat/butterfly PASSED(4h), crab/shark/cypher 보류(표본부족/mean<eff)
- 레짐 스위치: bull_btc→롱, bear/altseason→숏
- 청산 로직: 방식A(±10%) / 방식D(-8% 손절+조건부 익절) 병행
- 방식D 게이트: Calmar 기반(기대값+MDD) — engulfing/fvg/engulfing_short → D 채택, fvg_short → A 유지
- 유니버스: 28종목 (OKX 데이터) + 하모닉은 43종목 4h
- 자동화: GitHub Actions(매일 UTC 00:00) + Supabase DB
- 페이퍼테스트: 진행 중 (A +6.59%, D +3.13%, 13건 — 표본 부족, 판단 유보)

## 다음 할 일
- [ ] OKX 선물 실거래 활성화 — GitHub Actions secrets(OKX_KEY/SECRET/PASSPHRASE) 등록만 남음
- [x] 하모닉 패턴 페이퍼테스트 등록 (gartley/bat/butterfly 4h, scheduler+paper_executor 지원)
- [ ] Streamlit 대시보드 (실거래 데이터 한 달 후)
- [ ] crab/shark/cypher 재시험 (데이터 누적 후)

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
- universe.json: 28종목 유니버스
- registry.json: 패턴 등록부 (passed 7종 포함)
- research_log.csv: 86건 시험 기록
