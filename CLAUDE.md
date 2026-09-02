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
- **매시 크론 전환 + cascade_fade_long_1h 실거래 배포** (2026-09-01, 사용자 승인):
  크론 `0 */4 * * *` → `0 * * * *` (24회/일). **배포된 패턴의 탐지 시각 집합은 불변.**
  · **느린 TF 게이팅** — `scheduler.SLOW_TICK_HOURS=(0,4,8,12,16,20)`. 1d FOCUS /
    adopted(1d·4h·1w) / 4h전용 / 하모닉 블록은 이 6틱에서만 돈다. 이유: scheduler 는
    `rows[last]`(형성 중인 봉)에서 탐지하고 중복 방어 키가 날짜 단위라, 실행을
    6→24회로 늘리면 '하루 1회 진입'이 **더 이른 시각·덜 형성된 봉**에서 잡혀
    진입 분포가 검증 당시와 달라진다.
  · **bat_1h/butterfly_1h 도 6틱 유지** — exit_spec 이 없어 진입 지연 민감도가
    측정된 적이 없다. 매시 도는 것은 **exit_spec 보유 패턴뿐**(현재 cascade 하나).
  · **닫힌 봉 탐지**(`_closed_idx`) — exit_spec 패턴은 형성 중인 마지막 행이 아니라
    `rows[-2]`(닫힌 봉)에서 탐지. CSV 마지막 행은 거래소가 주는 미완성 봉인데
    (fetch_data 가 걸러내지 않음) 검증은 닫힌 봉 종가 기준이라, 그냥 두면 검증과
    **다른 신호 집합**으로 실거래가 돈다. 합성 봉 기능 테스트로 고정.
  · **체결가 기준 배리어 재정렬** — 실체결가가 신호봉 종가와 다르면(시장가라 수십 분
    뒤 체결) ±k×ATR 을 **체결가 기준으로 재계산**하고 OCO 를 재등록한다.
    검증(`outcome_atr`)이 배리어를 진입가 기준으로 잡기 때문. 안 하면 체결가로부터의
    거리가 ±1.5ATR 이 아니게 된다.
  · **사이징·레버리지 규칙 신설 — sizing.py (2026-09-02, 기본 legacy)**: 현행 '가용잔고 x20%,
    2x 고정'은 **진입 순서**가 크기를 정하고(POL $96 → ARB $77 → ADA $31, 전부 free x0.2 로
    재현) 등급·확증 배수는 **페이퍼 기록에만** 곱해졌다(`[사이징]` 로그가 실주문과 2배 어긋남).
    · risk-based: 건당 위험 = equity x RISK_FRAC, 명목가 = 위험/손절거리, 레버리지 =
      floor(1/(2x손절+MMR)) 상한 LEV_CAP — **청산가가 손절가의 2배 밖**. 8% 손절이면 최대 5x.
      레버리지는 명목가를 바꾸지 않고 증거금만 줄여 동시 포지션 수를 늘린다(핵심 사실).
    · `paper_executor.SIZING_MODE="legacy"` 기본 — 머지만으로 실거래 불변. `sizing_study.py`
      (7패턴 방식D 거래 전부를 한 포트폴리오로 시간순 시뮬 + 블록부트스트랩 300회)가
      "boot MDD중앙 >= -35% AND P(ruin)<5% 중 Calmar 최대" 기준으로 RISK_FRAC/LEV_CAP 을
      정한 뒤 사용자가 "risk" 로 전환. 단일자산 Kelly 는 참고만(알트 상관으로 과대).
    · `exchange.place_swap_entry(leverage=)` 주문별 레버리지, 미지정 시 2x 폴백.
      test_sizing.py 34건 (legacy 가 실거래 로그 3건을 정확히 재현하는지 포함).
  · **스케줄 누락률 실측 + 워크플로 분리 (2026-09-02)**: 스케줄 실행 428건 전수.
    **발화율** 매시(6/29~7/02) 81% / **4h(7/02~9/01) 99%** / **매시(9/01 10:30~) 27%**
    (15틱 중 4: 15:24·19:16·22:27·00:52). 정시 매시 크론은 이 레포에서 반복 불안정 —
    GitHub 문서상 매 정시가 부하 피크. **캐스케이드 검증(실측 지연 100건)은 발화된
    실행만 표본이라 누락을 반영하지 않았다.** 현 상태로는 d<=1 81% 전제 미충족.
    · **게이팅 회귀**: `is_slow_tick(now.hour)` 는 큐 지연이 정각을 넘기면 느린틱을
      놓친다 — 4h 시대 364건 중 **27%**, 8/05·8/06·8/27 은 **6틱 전부**. 머지 후 9/1
      오후 1d/4h 탐지가 기대 4회 중 **1회**(00:52)만 돌았다.
    · **수정**: 메인 `daily_scheduler.yml` 을 `0 */4 * * *` 로 복귀 + **항상 --slow**;
      신설 `fast_scheduler.yml` 매시 **`7 * * * *`(정시 회피) + 항상 --fast**(exit_spec
      패턴 진입 + 청산/손절점검만). 같은 concurrency 그룹으로 직렬화. `scheduler._tick_flag`.
      시간 판정은 플래그 없을 때 폴백으로만. 기존 패턴 케이던스 **원상복구**.
    · **미해결**: 오프셋 매시 크론 발화율 — 며칠 실측 후 캐스케이드 배포 전제 재판정.
      부족하면 '서버 불필요' 결론 철회 → 외부 트리거(repository_dispatch) 또는 배포 철회.
    · OKX 감사(9/2 01:09): 실포지션 4(ADA/ARB/POL/UNI, 손절 4건 전부 live), uPnL +$24,
      8/30 이후 실현 −$2.81. **equity $502→$271 은 사용자 자금 이동으로 확인**(매매 아님,
      2026-09-02 확인 — 이상징후로 재조사 말 것). **POL 숏 절반 9/1 10:31 청산도 사용자
      수동 청산으로 확인.** 그 결과 POL 손절 algo 가 원수량(sz 213) vs 실포지션 107 로
      남았으나 **reduceOnly=True 라 위험 없음**(진입 로그에 폴백 경고 없음 → OKX 가
      포지션 크기로 제한). 단 `ensure_stop_orders` 는 손절 '존재'만 보고 **수량을 비교하지
      않는다** — 수동 개입 시 장부 수량이 어긋난 채 유지된다(기록 정확도 갭, 별도 과제).
      trades 테이블에도 live_mode/pnl_usd 컬럼 없음(pnl $200 가정 재구성 → daily_summary 왜곡).
  · **entry_ts 유실 — 배포 직후 실측으로 발견(2026-09-01)**: Supabase `positions` 에
    `entry_ts`/`target`/`live_mode` 컬럼이 없어 insert 시 `insert_tolerant` 가 자동
    제외한다(실행 로그 '스키마 미존재 컬럼 제외'). 러너는 파일시스템이 매번 비어
    DB 가 유일한 원천이므로 **2026-08-30 의 ts 교정이 실거래에선 무효였다.**
    복원된 1h 포지션은 `_bar_idx` 가 date 폴백 → 그날 첫 봉을 진입봉으로 잡아,
    eval_I 가 **진입 이전 봉**을 스캔해 있지도 않은 청산을 만들고 수익률까지 오염된다.
    · `target` 은 `barriers_of` 대칭 복원으로 이미 방어됨, `live_mode` 는 method 의
      LIVE 인코딩으로 폴백됨 — **실제 미방어는 `entry_ts` 하나.**
    · 임시 방어: exit_spec 패턴이 entry_ts 없이 복원되면 **엔진 청산을 보류**하고
      거래소 OCO 에 맡긴다(없는 청산을 만드는 것보다 안전). test_intraday_exit.py.
    · **근본 해결은 DB 컬럼 추가** — `positions.entry_ts`(bigint) 추가 시 분기는
      자동 소멸. 추가 전까지 캐스케이드는 시간청산(12봉)이 돌지 않는다.
  · **미해소 gap(의도적)**: 형성 중인 봉 탐지는 exit_spec 패턴에서만 고쳤다. 기존
    배포 패턴은 여전히 `rows[-1]` 에서 탐지한다 — 종전 동작을 바꾸지 않기 위해
    그대로 뒀다. **별도 과제로 재검토 필요**(레포 전반에 걸친 검증-실행 불일치).
  · test_cron_split.py (30건) / test_cascade_detector.py 8절이 크론 문자열·틱 시각·
    배포 상태를 고정 — 크론이 4h 로 돌아가면 테스트가 깨진다
  · **tests.yml 신설** — 종전에는 테스트를 도는 CI 가 아예 없어서 위 고정 장치가
    로컬 실행에만 의존했다(= 아무것도 못 막음). 이제 push/PR 마다 7종을 돌린다.
  · **스케줄 크론은 기본 브랜치 기준** — Actions schedule 은 default branch 의
    워크플로만 실행한다. 즉 크론 변경도 캐스케이드 배포도 **master 병합 시점에**
    발효된다(둘이 같은 커밋이라 원자적 — 매시 크론 없이 캐스케이드만 도는 구간 없음)
- **캐스케이드 1h 크론 재평가 — 서버 불필요 결론** (2026-09-01): 실측 Actions 지연
  분포 + 마찰 민감도. **1시간 크론만으로 게이트 통과 → 상시 서버 투자 불필요**(비용 0).
  · **실측 지연 100건**(daily_scheduler schedule 실행): 중앙 25.1분 / 평균 40.7분 /
    p75 37.5 / p90 91.5 / p95 188.3 / 최대 231.5 / **60분 이내 82%**. 고정값이 아니라
    신호마다 부트스트랩 추출(시드 고정)해 씌운다 — 1차 지연시험은 고정값이었다.
  · **크론 비교**: 4h(현행) mean +0.58% / **median -0.37%** REJECTED (d<=1 비율 12%)
    vs 1h(제안) mean **+1.54%** / median **+0.31%** / boot_p 0.000 / OOS 2/4
    **PASSED** (d<=1 비율 **81%**). 결정적 차이는 d<=1 비율 12%→81%.
  · **서버 기여분은 '꼬리 제거'뿐**: `1h+서버` 행이 `이상 d=1` 과 수치가 완전히 같다
    (+1.88%) — 동결 라벨이 1h 봉보다 잘게 못 봐서 지연 1분과 59분이 같은 칸이다.
    즉 이 프레임은 한 시간 안쪽을 분해하지 못한다. d=0(+2.43%)=서버 상한,
    d=1(+1.88%)=60분 내 모든 지연의 하한, 실제는 그 사이. 측정 가능한 서버 가치는
    건당 +0.34%p(꼬리 제거), 상한까지 보면 +0.34~+0.89%p. **크론만으로 통과하므로
    배포에 서버는 불필요.**
  · **마찰 내성 왕복 0.4%** (동결 가정 0.2%의 2배, OKX taker 실비 0.1%). 0.6%부터
    중앙값 음수로 기각. 무너지는 건 항상 중앙값 — 평균은 0.8%에서도 +0.94% 양수라
    소수 대박 의존형으로 변질되고 게이트가 이를 잡는다. lab.evaluate 의 fee_ok 가
    동결 0.2% 고정 잣대라 스윕 arm 은 verdict_at_fee 로 재판정.
  · **지연 통계 정정**: 세션 중 median 16.0 / p90 172.9 로 잘못 보고했던 값을 실행
    로그에서 재계산해 정정(실제 25.1 / 91.5). 결론 불변이나 꼬리가 더 얇다.
  · **남은 blocker는 크론 분리 하나**: 크론을 `0 * * * *` 로 바꾸는 것만으로는 안 된다.
    scheduler 는 `rows[last]`(형성 중인 봉)에서 탐지하고 중복 방어 키가 날짜 단위라,
    매시 실행은 **1d/4h 배포 패턴의 탐지 기회를 6→24회로 늘려** '하루 1회 진입'이 더
    이른 시각·덜 형성된 봉에서 잡히게 만든다 = 배포된 engulfing/fvg/ih/marubozu/
    하모닉4h/bat_1h/butterfly_1h 의 진입 분포가 검증 당시와 달라진다. **권장 방안(A)**:
    크론은 매시로 바꾸되 UTC 00/04/08/12/16/20 이 아니면 1d/4h 탐지 블록을 스킵.
    청산·ensure_stop_orders 는 매시 돌아 오히려 개선.
  · **여유는 크지 않다**: median 이 문턱 위 +0.31%p(d=0 의 27%), OOS 2/4 는 최소 기준
    정확히 걸침, Q4 약세(n=27 mean -0.26%)를 1차와 공유. registry status
    **passed_not_deployed 유지** — 크론 분리 선행 + 실거래 활성화는 사용자 판단.
    validate_cascade_realistic.py / test_cascade_realistic.py / report_cascade_deployment.md
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
- **자동화**: `daily_scheduler.yml` **4h**(`0 */4`, --slow, oncefull@UTC00:00) +
  `fast_scheduler.yml` **매시 :07**(--fast, exit_spec 패턴만). 2026-09-02 분리
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
- [x] cascade_fade_long_1h **진입 경로** (2026-09-01) — detector_cascade_fade_1h.py +
      scheduler exit_spec 연동. 신호 집합이 검증 조건과 완전 일치(테스트 고정).
      **활성화는 adopted_1h_patterns 에 한 줄 추가** — 단 1h 이내 진입 보장 전엔 금지
- [x] cascade_fade_long_1h 진입 지연 민감도 (2026-09-01) — **1h 이내 진입 필수** 확인
- [x] cascade_fade_long_1h 상시 실행 환경 판단 (2026-09-01) — **서버 불필요 결론.**
      실측 지연으로 재평가하니 1h 크론만으로 게이트 통과(+1.54%/median +0.31%)
- [x] **크론 분리** (2026-09-01) — 매시 실행 + SLOW_TICK_HOURS 게이팅. 배포 패턴 무영향
- [x] 캐스케이드 adopted_1h_patterns 등재 (2026-09-01, 사용자 승인) — registry deployed
- [ ] **형성 중인 봉 탐지 재검토** — 기존 배포 패턴은 아직 `rows[-1]`(미완성 봉)에서
      탐지한다. 검증은 닫힌 봉 기준이라 전반적 불일치. 영향 범위 측정 후 결정
- [ ] 캐스케이드 첫 실거래 후 체결 지연·슬리피지 실측 → 검증치와 대조
      (지연 1h 이내 / 마찰 왕복 0.4% 이내여야 함)
- [ ] 배포 후 캐스케이드 국면 실제 체결 슬리피지 실측 (내성 한계 왕복 0.4%)
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
- validate_cascade_realistic.py: 실측 Actions 지연 분포(100건 내장) + 마찰 스윕.
  1h vs 4h 크론 비교로 '서버가 필요한가'에 답한다. report_cascade_deployment.md
- validate_ih_exit.py: 사후 선택된 셀의 반증 시험 3종 (시간분할/부트스트랩CI/대조군)
- detector_cascade_fade_1h.py: 캐스케이드 페이드 진입 디텍터 (동결 2.5ATR/3.0배/0.40).
  **evaluate 미노출** — 동결 ±10% 라벨은 1h에서 무의미해 orchestrator 오적용 방지
- test_cascade_detector.py: 신호 집합이 validate_cascade 조건과 일치 + 스케줄러 연동 검증
- test_method_t.py: method_t 로직 검증 (자산곡선이 회전율 차이를 잡는지 포함)
- detector_harmonic_base.py: 하모닉 공통 라이브러리 (find_pivots, check_ratios, make_detect)
- detector_gartley/bat/butterfly/crab/shark/cypher.py: 하모닉 6종 디텍터
- universe.json: 71종목 유니버스 (trading_universe), data_short 75종목, rejected 20종목
- expand_universe.py: 유니버스 확대 스크립트 (업비트KRW∩OKX선물, 재실행 가능)
- report_universe_expansion.md: 유니버스 확대 리포트
- registry.json: 패턴 등록부 (passed 11종: 1d×4 + 4h×4 + 1h×3, cascade 2026-09-01 배포)
- test_cron_split.py: 매시 크론이 배포 패턴 동작을 바꾸지 않음을 고정 (게이팅/닫힌봉/재정렬)
- research_log.csv: 106건 시험 기록
- detector_three_soldiers_4h.py: 3연속 장대 양봉 (4h, PASSED)
- detector_three_soldiers_1h.py / detector_three_crows_1h.py: 1h 버전 (검증용)
- detector_vwap_rev_long/short_1h.py / detector_breakout_retest_1h.py: 1h 기각
- report_4h_expansion.md: 4h 확장 + Three Crows 레짐 재검증 리포트
- report_1h_expansion.md: 1h 확장 리포트 (bat/butterfly 통과)
