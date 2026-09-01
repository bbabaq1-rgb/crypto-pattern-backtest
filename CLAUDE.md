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
- **신규 1w 패턴**: triple_bottom_1w PASSED (2026-08-29 2차 연장검증, n=141,
  mean=+7.72%, median=+10.19%, boot_p=0.023, OOS 2/4) — 사용자 지정 패턴
  (차트 5장) 데이터화. 1d 5년 리샘플, 레짐 무관 롱, detlib가 1w/1M 리샘플 지원.
  **4h는 1차(130일 bear 단일구간) 통과였으나 2차(3년, n=1875)에서 median
  음수/boot_p 0.32로 번복·철회** — 단일 레짐 아티팩트 교훈. 15m/1h/1d/1M 및
  거울상 triple_top 전 셀 기각(1d는 median -4.8% 복권형, 1h는 n=2765로 확정
  기각, 1M은 mean 음수). report_triple_pattern.md
- **신규 1h 패턴**: butterfly_1h PASSED (n=161, mean=+1.59%, OOS 4/4, boot_p=0.024)
  - 레짐 무관 전 구간 양수 (bear Q4도 양수), 스케줄러 all regimes 탐지
  - 나머지 10종 기각 (gartley_1h boot_p=0.092 경계 탈락 포함)
- 레짐 스위치: bull_btc→롱, bear/altseason→숏
- 청산 로직: 방식A(±10%) / 방식D(-8% 손절+조건부 익절) 병행
- 방식D 게이트: Calmar 기반 — engulfing/fvg/engulfing_short → D 채택, fvg_short → A 유지
- **청산 방식 E·F 기각** (2026-07-03): E(Chandelier ATR22×3) vs D 0/3 전패(MDD -71.5%),
  F(50%익절+본전+트레일) pooled 0/3 (fvg_short만 2/3) — 페이퍼 병행 등재 안 함 (method_e/f.py, report.md)
- **고정 익절(방식T) 5수준 전부 기각** (2026-09-01): 방식D + 진입가 +k% 익절
  (k=10/15/20/25/30%) — 패턴 7종 x arm 6개 35셀. 최대표본 fvg(n=446)에서 전 수준
  **t=-3.4~-4.2 강한 유의 열세**(CAGR 27.0%→10.0%). 최선인 T25도 짝지음 2/7·CAGR 3/7.
  · **방법**: 실거래 자본 분할 대신 **같은 신호에 두 규칙 동시 적용(짝지음)** — 가격 경로가
    동일해 종목·시점 교란이 상쇄, 분할 대비 검정력 수십 배. '+k% 익절'은 가격의 결정론적
    함수라 백테스트로 정확히 재현되므로 실거래 분할이 불필요.
  · **자산곡선 병기**: 건당 평균은 자본 회전율(복리)을 못 본다 → 실사이징(잔고20%/12포지션/2x)
    시간순 시뮬레이션으로 CAGR/MDD/Calmar 측정. 회전율 2배로 빨라져도 복리 이득이
    잘라낸 큰 승자를 보상 못함.
  · **기전**: 익절은 승률·중앙값을 올리고 평균을 낮춘다(engulfing 승률 44%→56%,
    중앙 -5.30%→+9.80%, 평균 +4.64%→+2.16%) — 오른쪽 꼬리 절단.
  · 재시험 후보 2건: fvg_short 한정 T25/T30(t=2.12/2.79, 다중검정 미보정),
    inverted_hammer 한정 T10(Calmar 0.10→0.46이나 짝지음 t=0.17·비단조).
  · **익절 규칙 다섯 번째 기각**(E·F·G·H에 이어). 실거래 청산 규칙 변경 없음(방식D 유지).
    method_t.py / test_method_t.py / report_take_profit.md
- **청산 방식 G·H 기각** (2026-07-06): G(복합스코어 60/80점) pooled 0/3 — 단
  **inverted_hammer에서 2/3 우위(+8.32% vs +4.04%, Calmar 2배)** → 데이터 누적 후
  '해당 패턴 한정 G' 재검토 가치. H(HH 3봉실패) 전 패턴 0/3(조기청산). 참고: 손절 공유
  방식은 MDD 동률이라 3축 전승 구조적 불가 (method_g/h.py, report.md)
- **≤1h 단타 5축 전수 기각** (2026-08-29): 횡단면반전/펀딩극단/청산캐스케이드/
  시간대/거래량쇼크 15셀 전부 REJECTED. **선행 발견: 하위 TF 기존 판정은 측정
  오류** — 동결 라벨(±10%/20봉)이 1h에서 배리어 도달률 0%(전부 시간초과)라
  측정값이 '랜덤−수수료'로 수렴. 무엣지 랜덤워크 mean −0.218% ≈ 실측 15m −0.234%.
  하위TF 전용 프레임 신설(intraday_lab.py: ±1.5ATR 배리어, TF별 보유한도,
  수수료마진 게이트). 재측정 후에도 5축 전부 베이스라인(−0.25%)과 구분 불가.
  유일 실마리였던 cascade_fade_long_1h는 **2차 사전등록 재시험(1h 3년)에서
  통과** — n=312, mean +2.43%, median +1.17%, boot_p 0.000, OOS 3/4,
  절사평균 +1.87%(상위5거래 기여 10.8%). 고변동성 조건은 불필요(신호 79%가
  이미 고변동 국면). **단 배포 불가 — registry는 passed_not_deployed**:
  스케줄러 4h 주기·Actions 지연 10~90분으로 진입시점 이탈, eval_D/eval_A의
  ±8~10% 손절·30/20봉 보유가 검증치(±1.5ATR/12h)와 5~10배 불일치.
  실행 인프라(상시 서버 + 하위TF 청산 경로) 선결. report_intraday.md
- **하위 TF 청산 경로 구축** (2026-08-30): registry `exit_spec` 이 있는 패턴만
  ATR 배리어로 청산하는 별도 경로 신설 — 기존 1d/4h/1w/1h 등재 패턴의 청산
  동작은 불변(exit_spec 없음 → eval_D/eval_A 그대로).
  · `paper_executor.eval_I` — 진입 시 확정된 ±1.5×ATR14 배리어 + 12봉 시간청산.
    검증 프레임 `intraday_lab.outcome_atr` 과 수익률 완전 일치(테스트로 고정).
  · **거래소측 OCO 브래킷** — 진입 시 손절+익절을 OKX algo(ordType=oco)로 동시
    등록. ±1.5ATR(≈0.75~1.5%)는 스케줄러 4h 주기 안에 양방향 다 지나가므로
    엔진이 봉을 읽어 청산하는 방식으로는 집행 불가 → 거래소에 미리 걸어둔다.
    엔진이 담당하는 건 시간청산(12봉)뿐.
  · `ensure_stop_orders(stop_map=)` — 재등록 시 **포지션에 기록된 손절가** 사용
    (종전 ±8% 고정은 ATR 패턴에서 검증치와 5~10배 어긋남). oco 주문도 pending
    조회에 포함(중복 등록·고아 오인 방지), algoId 중복 제거.
  · **봉 식별 date→ts 교정** — `load_ohlcv` 에 ts 병기, 신호·포지션에 ts 기록.
    1h는 하루 24행이 같은 date 라 기존 `_date_idx` 가 그날 **첫 봉**을 진입봉으로
    잡던 문제(배포된 bat_1h/butterfly_1h에도 해당) 해소. 구 포지션은 date 폴백.
  · `MAX_HOLD_BY_TF` 는 **의도적으로 계속 미사용** — eval_D에 꽂으면 배포된
    4h/1h 패턴의 청산 규칙이 검증 당시와 달라진다. test_intraday_exit.py (42+7건)
- **캐스케이드 진입 지연 민감도** (2026-09-01): cascade_fade_long_1h 배포 선결조건 측정.
  신호는 고정하고 진입 봉만 뒤로 밀어(배리어·보유한도 모두 진입시점 재계산) 감쇠를 측정.
  d=0 이 1차 검증(n=312 +2.43%)을 정확히 재현 — 정합성 확인.
  · **엣지가 시간당 약 25% 감쇠**: d0 +2.43%(PASSED) / d1 +1.88%(PASSED) /
    d2 +1.09%(기각) / d3 +0.07% / d12 **-1.53%**(부호 역전, boot_p 1.000)
  · **현행 4h 주기(평균 지연 2.6~3.6h)는 전 조건 기각** — mean 은 +0.59~0.78%로
    boot_p 0.001~0.007(여전히 유의)이나 **중앙값이 음수**(-0.24~-0.37%)라 게이트 미달.
    지연되면 소수 대박 의존 형태로 변질(1차의 '상위5거래 10.8%' 건전 분포가 무너짐).
  · **판정 DELAY_SENSITIVE** — 엣지는 실재하나 **1시간 이내 진입이 배포 필수조건**.
    이제 기술 문제가 아니라 투자 판단. 단 d=1 자체가 23% 감쇠값이라 여유 작음.
    validate_cascade_delay.py / test_cascade_delay.py / report_followup_2026_09.md
- **inverted_hammer 한정 청산(G/T10) 기각** (2026-09-01): 방식G(2026-07-06)와
  방식T10(2026-09-01)이 IH 에서만 방식D를 이겨 반복적으로 보였으나, **사후 선택된 셀**이라
  '특별하다'를 반증하는 3종 시험을 설계. 결과 **T10 1/3, G 0/3 → NOISE, 추격 중단**.
  · 시간분할: T10 전반 -0.33%/후반 +0.72%, G 전반 +2.39%/후반 -1.00% (둘 다 부호 역전)
  · 부트스트랩 CI: T10 [-2.19%,+2.34%], G [-1.99%,+4.03%] — 둘 다 0 포함
  · 대조군: T10 은 IH 1위지만 +0.2%로 2위와 동률, G 는 triple_bottom(+18.3%)이 IH(+0.7%) 압도
  · 짝지음으로 재면 IH 우위가 +0.20~0.68%p 에 불과. 2026-07-06 의 'G +8.32% vs D +4.04%'는
    현 데이터·프레임에서 재현 안 됨 — '두 규칙이 같은 패턴에서 신호' 관찰 자체가 착시.
    validate_ih_exit.py / report_followup_2026_09.md
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
  킬스위치(equity < $100 → 신규 진입 중지, paper_executor.EQUITY_FLOOR —
  2026-08-29 사용자 지정 절대 하한. 기존 HWM 대비 -20%($230.06) 규칙은 폐기) ·
  손절 algo 주문 매 실행 자동점검(ensure_stop_orders — 누락 시 재등록 +
  포지션 없는 고아 주문 취소, 주문은 reduceOnly 청산 전용. 2026-08-29) ·
  텔레그램 알림(notify.py — TELEGRAM_BOT_TOKEN/CHAT_ID secrets 등록 시 활성)
- **멀티 TF 확증**: 1d 신호 → 4h 최근 3봉 확증. 비확증 시 size 50% 축소
- **RS 필터 폐기** (2026-07-08): 상대강도(relative_strength.py)는 rs_score 계산·표시만.
  당초 롱 rs<0.2 ×0.5 필터를 채택했으나, 레짐 통제 검증(backtest_rs_controlled.py)에서
  rs 순진 엣지(+2.76%p)가 시장 레짐(avg_cap)의 교란으로 판명 — 통제 후 cap구간 우위 1/3,
  Welch p=0.38로 독립 엣지 소멸 → 필터·앙상블 정렬에서 제거(자유도 감소). rs/cap은 표시 전용.
- **시장 비대칭(avg_cap) 레짐 사이징** (2026-07-08 채택): 유니버스 평균 cap_score.
  complacent(avg_cap>0) → 신규 롱 ×0.6(축소만, backtest_regime_capture.py). 사이징에
  쓰는 유일한 시장신호. 레짐정의(bull/bear) 불변 — 오버레이 계층이라 게이트 동결 유지
- **상승/하락 비대칭(cap_score) 기각** (2026-07-08): up/down capture 비대칭 지표.
  백테스트에서 반전패턴 눌림목매수엔 역효과(bleeder가 더 과매도→반등커서 방식D
  수익↑) — cap>0 롱 +7.87% vs cap<0 +11.47%. **필터 미채택, 진단 표시만**
  (relative_strength.compute_capture, backtest_capture.py)
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
- [x] cascade_fade_long_1h **청산 경로** (ATR 배리어 + 거래소 OCO 브래킷, 2026-08-30)
- [ ] cascade_fade_long_1h 진입 경로 — detector_cascade_fade_1h.py 작성 +
      scheduler 탐지 등록 (현재 검증 로직이 validate_cascade.py 안에만 있음)
- [x] cascade_fade_long_1h 진입 지연 민감도 (2026-09-01) — **1h 이내 진입 필수** 확인
- [ ] cascade_fade_long_1h 상시 실행 환경 — **1시간 이내 진입 보장** 필요(투자 판단).
      d=1 +1.88% 통과 / d=2 +1.09% 기각이라 여유가 작다
- [ ] 상시 환경 확보 시 실측 지연으로 최종 확인 → 통과하면 adopted_patterns 등재
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
- paper_executor.eval_I / exchange.place_stop_algo(tp_px=): 하위TF ATR 배리어 청산
  + OKX OCO 브래킷. 라우팅은 registry.json 의 exit_spec 유무로만 결정
- test_intraday_exit.py: 청산 경로 테스트 (신규 경로 + 기존 경로 무변화 e2e)
- method_t.py: 고정 익절 arm 시험 (짝지음 비교 + 회전율 반영 자산곡선). 기각 기록용
- validate_cascade_delay.py: 캐스케이드 진입 지연 민감도 (고정지연 + 실제 스케줄러 격자)
- validate_ih_exit.py: 사후 선택된 셀의 반증 시험 3종 (시간분할/부트스트랩CI/대조군)
- test_method_t.py: method_t 로직 검증 (자산곡선이 회전율 차이를 잡는지 포함)
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
