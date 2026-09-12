# crypto-pattern-backtest

## 프로젝트 목적
암호화폐 차트 패턴 자동 감지 → 백테스트 → 자동매매 시스템

## 현재 상태 (2026-06-29)
- 검증 완료 패턴: engulfing(validated), fvg(passed), inverted_hammer(passed), marubozu(passed)
- 하모닉 패턴: gartley/bat/butterfly 4h + bat_1h/butterfly_1h **등재 정지(2026-09-03, 룩어헤드)** —
  아래 '전체 점검' 참조. crab/shark/cypher 보류(표본부족/mean<eff)
- **신규 4h 패턴**: three_soldiers_4h PASSED (n=908, mean=+1.04%, OOS 3/4, p<0.0001)
  - bull_btc/bull_altseason → 롱 전용, bear/sideways 스킵
  - 나머지 6종 기각 (three_crows/breakout_retest/equal_highs_lows/vwap_rev)
- **신규 1h 패턴**: bat_1h PASSED (n=108, mean=+1.46%, OOS 4/4, boot_p=0.034)
- **triple_bottom_1w 등재 정지 (2026-09-03, 룩어헤드 재검증 REJECT)** — 아래 '전체 점검' 참조. 종전 기록:
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
- 레짐 스위치: bull_btc→롱, bear/altseason→숏 (실제 표 direction_switch.json — bull_btc 롱/롱,
  bull_altseason engulfing 숏·fvg 롱, bear engulfing 롱·fvg 숏, sideways FLAT. 2026-06-24 고정 표,
  regime_switch.json by_pattern 의 n≥20·mean>0 만 본 것 — **median/boot_p/OOS 게이트는 미적용**.
  registry 의 engulfing_short/fvg_short 는 무조건부 표본에서 rejected. 2026-09-03 점검에서 확인, 사용자 판단 보류)
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
    · **연구 결과(2026-09-02, 1,093건·부트스트랩 300회)**: 사전 기준(MDD중앙≥−35%, P(ruin)<5%)을
      만족하는 건 **위험 0.5%/2x 뿐** — 현행 legacy 는 MDD중앙 **−59.9%**(p10 −77%)로 기준 밖.
      즉 **'작다'는 전제 기각, 현행이 오히려 크다.** 레버리지는 같은 위험에서 2→5x 올려도
      CAGR 43→36% / MDD −67→−76% — 명목가 불변, 동시 노출만 증가. 위험 1%에선 2x=3x 완전 동일.
      권고 규칙은 equity<$320(C등급 $457)에서 최소증거금 미달로 스킵 → **현 계좌($285)엔 작동
      불가**. 선택지 4개는 report_sizing.md.
    · **채택: risk 1%/2x (2026-09-02 사용자 결정 ③, 실거래 반영)** — `SIZING_MODE="risk"`,
      `RISK_FRAC=0.01`. 권고 0.5%가 현 계좌에서 주문이 안 나가 실사용 불가라, **지금 쓸 수 있는
      가장 큰 개선**을 택했다. legacy 대비 CAGR +39.3%→+38.8%(사실상 동일)인데 boot MDD중앙은
      −59.9%→**−43.1%**(p10 −77.1%→−60.7%). 문턱 equity $160. **사전 기준(MDD중앙≥−35%)은
      여전히 미충족** — 통과하는 건 0.5%뿐이므로 equity가 $320을 넘으면 0.5% 하향을 재검토.
    · **낙폭이 줄어드는 기전은 '항상 더 작아짐'이 아니다** — legacy 는 free×20%라 진입 순서가
      크기를 정해 첫 진입이 크고 뒤로 갈수록 잘게 쪼개진다($95.96→$76.83→$31.45). risk 는
      equity 기준이라 몇 번째든 같다. MDD 는 '큰 초기 진입들이 동시에 물릴 때' 생기므로
      잘리는 쪽은 초기 대형 진입이고, free 가 낮은 상태에선 risk 가 오히려 크다
      (현 계좌 실측: risk $17.83 > legacy $14.73). test_sizing.py 가 이 성질을 고정한다.
  · `paper_executor.SIZING_MODE` — 2026-09-02 "risk" 전환 완료(그 전 기본은 legacy). `sizing_study.py`
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
    · **오프셋 매시 크론도 실패 → 외부 트리거 전환 (2026-09-02, 사용자 결정 ①)**: 워크플로
      분리 머지(01:52) 후 fast `:07` 5틱(02~06시) **0/5**, daily 04:00 틱도 **미발화**
      (06:46 기준 166분 경과 — 4h 시대 368건 분포의 p99가 188분이라 사실상 유실).
      4h 크론까지 멈춘 건 워크플로 수정 직후라
      재등록 지연 가능성 있으나, 어느 쪽이든 GitHub schedule 만으로는 '1h 이내 진입' 전제를
      못 지킨다. **Supabase pg_cron → GitHub `workflow_dispatch` API** 로 러너를 깨운다
      (`supabase_external_trigger.sql`, 사용자가 Supabase SQL Editor 에서 실행). fast 매시
      :03 / daily 00:00 oncefull + 04·08·12·16·20:00 oncequick — **발화 시각 집합은 GitHub
      크론과 동일**(SLOW_TICK_HOURS).
    · **작동 확인 (2026-09-02)**: fast 09:03/10:03/11:03/12:03 전부 :03:01 정시 발화,
      러너 시작 지연 0초. daily 12:00:01 발화 + `실행 모드: oncequick --slow` 확인.
      두 달간 25분~3시간씩 밀리던 GitHub 크론과 질적으로 다르다.
    · **fast 의 GitHub schedule 폴백 제거 (2026-09-02)**: 폴백을 남기면 daily 와 공유하는
      concurrency 그룹에서 **먼저 대기 중이던 실행이 취소된다** — GitHub 는 같은 그룹에 새
      실행이 큐에 들어오면 pending 을 취소한다(`cancel-in-progress: false` 여도 그렇다).
      실측: 12:03 외부 트리거 실행이 12:04:30 폴백 진입으로 **cancelled**(이번엔 폴백이
      대신 돌아 손실 없음). 거울상으로 daily 가 pending 인 사이 fast 가 큐에 들어오면
      **daily 가 취소되어 느린TF 탐지를 4시간 통째로 잃는다.** 발화율 0~27% 짜리 폴백을
      위해 감수할 위험이 아니라 제거했다. daily 폴백은 유지(4h 간격이라 겹칠 창이 좁고
      두 달 99% 실적). 외부 트리거가 멈추면 로그 401 로 드러나며 수동 dispatch 로 메운다.
      PAT(fine-grained, Actions write 만, 1년 만료)는 Vault `github_pat_dispatch`, 발화·응답은
      `gh_dispatch_log`(204 정상/401 만료/404 권한/422 inputs). **발화율 측정은 이제
      `workflow_dispatch` 이벤트도 세야 한다.** 남은 위험: PAT 만료 시 조용히 멈춤(로그 401),
      Supabase 무료 플랜 프로젝트 일시정지(러너가 매 실행 DB 쓰므로 비활성 아님).
      04:00 누락분은 05:40 수동 dispatch 로 대체 실행(예외 없음, 신호 0, equity $281.73).
      test_external_trigger.py (31건) 가 SQL 의 워크플로명·mode·시각을 레포와 맞춘다.
    · OKX 감사(9/2 01:09): 실포지션 4(ADA/ARB/POL/UNI, 손절 4건 전부 live), uPnL +$24,
      8/30 이후 실현 −$2.81. **equity $502→$271 은 사용자 자금 이동으로 확인**(매매 아님,
      2026-09-02 확인 — 이상징후로 재조사 말 것). **POL 숏 절반 9/1 10:31 청산도 사용자
      수동 청산으로 확인.** 그 결과 POL 손절 algo 가 원수량(sz 213) vs 실포지션 107 로
      남았으나 **reduceOnly=True 라 위험 없음**(진입 로그에 폴백 경고 없음 → OKX 가
      포지션 크기로 제한). 단 `ensure_stop_orders` 는 손절 '존재'만 보고 **수량을 비교하지
      않는다** — 수동 개입 시 장부 수량이 어긋난 채 유지된다(기록 정확도 갭, 별도 과제).
      trades 테이블에도 live_mode/pnl_usd 컬럼 없음(pnl $200 가정 재구성 → daily_summary 왜곡).
    · **2026-09-03 22:04~23:03 KST equity $318→$262·free $107→$55 급감은 사용자 출금으로 확인**
      (2026-09-04 확인. OKX 감사: 포지션 3건·손절 4건 불변, 청산 이력 없음 — 이상징후 아님).
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
- **방향 인지 레짐 청산(방식R) 기각** (2026-09-03): 현행 eval_D 의 레짐 청산은
  `regmap[j] != entry_reg` 로 **방향을 안 본다** — bear 에서 잡은 롱이 bull 로 유리하게
  바뀌는 순간 청산된다(사용자 관찰). 방식R = '불리 국면으로 들어가는 전환'에만 청산.
  7패턴 n=1,091 짝지음: 합산 +0.597%p, t 1.58, 패턴재표본 boot_p 0.006, 짝지음우위 6/7,
  CAGR우위 4/7 — 그러나 **분기 거래 285건 중 R 승률 44%** 로 사전기준 ④ 탈락 → REJECT.
  · **롱은 맞고 숏은 틀리다**: bear 진입 fvg 롱 n=134 는 +2.39→+5.29% (boot_p 0.006)로
    사용자 직관대로. 그런데 bull 진입 fvg 숏 n=188 은 −2.05→−2.58% (boot_p 0.975)로 손해.
    대칭 규칙이 안 맞는다.
  · **건당은 올라도 CAGR 은 반토막(fvg 22.9→12.3%)**: 보유 10.5→14.5봉으로 회전율 하락 +
    손절이 진입가 고정이라 버티는 동안 번 걸 −8% 까지 반납(stop 206→244, 중앙값 −8.2%).
  · R1(sideways 중립)≡R2(sideways 불리) 전 패턴 동일 — 표본에 sideways 전환 0건.
  · **2차 후속 가설 3개도 전부 REJECT** (2026-09-03, 사용자 지시, 기준 ⑤ 전후반 양수 추가):
    RL(롱만 R1) +0.548%p CAGR우위 3/7 분기승률 46% / RB(R1+유리전환시 본전이동) +0.536%p
    분기승률 43% 후반 −0.11 / RLB +0.490%p. **본전 이동은 1,091건 중 12건만 발동**하고 R1 대비
    미세 악화. 해석 정정: fvg 롱 분기 161건 중 bull 진입 ≈124건은 D 가 **bull_btc↔bull_altseason
    라벨 전환**에서 청산하던 것을 R 이 '유리→유리'로 보고 버티다 −8% 에 걸린 것. 즉 D 의
    라벨 전환 청산이 bull 진입 알트 롱의 조기 출구 역할을 하고 있었고, 본전 이동은 '유리로
    들어가는' 순간에만 걸려 이미 bull 에서 진입한 거래엔 무효. **확실한 건 하나** — bear 진입
    롱을 bull 전환에 청산하지 않는 것은 옳다(fvg n=134 +2.9%p boot_p 0.006, 4 arm 동일).
  · **3차 RA(altseason 인지)+홀드아웃도 REJECT** (2026-09-03, 사용자 지시): 마지막 365일
    (n=233) 홀드아웃, train n=858. RA +0.387%p(비유의) CAGR우위 2/7 분기 40% — **RL(+0.744%p)
    보다 나쁨**. altseason→btc 불리 규칙이 triple_bottom(+21.3→−1.0)·IH 의 출구를 막았다 —
    R1 의 triple_bottom 대박은 정확히 그 전환을 버텨서 난 것. 2차 해석은 fvg 한 패턴에서만
    성립. **홀드아웃(bear 지배 해)**: RL 분기 6건 0승 7패, RA 는 D 와 분기 0건(발동 상황 없음).
  · **세 라운드 종합 — 여기서 멈춤(4번째 변형은 과적합)**. 불변 사실: bear 진입 롱의 bull 전환
    유지는 매번 재현(train fvg n=73 +5.3~5.5%p boot_p≤0.004). 그러나 규칙화하면 부작용이 상쇄 —
    분기 거래 승률이 한 번도 50% 를 못 넘음(44/46/43/44/47/40%). 남은 경로는 **실거래 병행
    기록**(A/D 처럼 R-롱한정을 3번째 장부로, 주문은 D 그대로) — 사용자 승인 사항.
  · **방식R 그림자 장부 배포** (2026-09-03, 사용자 승인): `paper_executor.eval_R`(RL 규칙,
    test_shadow_r 가 method_r.outcome_r("RL") 과 400 시나리오 완전 일치로 고정) +
    `shadow_r_records` — **R_SHADOW_SINCE(2026-09-03) 이후 진입한 방식D 롱 거래**(exit_spec
    패턴 제외, 숏은 RL≡D 라 미기록)를 매 실행 봉 데이터로 재평가해 해소되면 method="R"
    행 추가(live_mode=False). **주문·포지션 수명·live 집계 무변경** — 롱에서 R 청산은 항상
    D 와 같거나 늦으므로 포지션이 아니라 **D 거래 기록**에서 재평가한다(D 청산 뒤에도 R 은
    미결일 수 있음). 진입봉은 같은 실행이면 entry_ts, DB 복원분이면 date 폴백(D 와 동일).
    tf 는 universe.json adopted 목록 우선(`_pattern_tf`, triple_bottom→1w). daily_summary 는
    A/D 만 합산하므로 무영향, paper_summary 에 R 블록 추가. 현 오픈 3건(ARB/ADA/UNI, 9/3
    이전 진입)은 대상 아님. **판정 시점: 분기 거래 n≥50** — 그 전엔 기록만.
  · 실거래 주문 규칙 무변경(D 유지). method_r.py / test_method_r.py(65건) /
    test_shadow_r.py(26건) / report_regime_exit.md
- **전체 로직 점검 → 수정 (2026-09-03, 사용자 지시 "최적의 형태로 진행")**: report_audit_2026_09.md
  · **하모닉 5종 룩어헤드 — 등재 정지**: detect_harmonic 이 D 피벗 봉을 신호로 찍는데 피벗 확정에
    이후 3봉이 필요해 마지막 봉은 절대 신호가 못 됐다(합성 300회 0/300, **배포 이래 진입 0건**).
    백테스트는 미래 3봉을 보고 D 를 골라 등재 수치가 낙관 편향. 신호를 확정 봉(D+PIVOT_WINDOW)으로
    고치고(confirm=True) gartley/bat/butterfly 4h·bat_1h/butterfly_1h 를 suspended_lookahead 로.
    복귀는 validate_confirm_bar.py(new/old 두 판) PASSED 셀만, 사용자 결정. triple_bottom 도 L3
    미확정 돌파를 세고 있었음 → causal 판(실거래 집합 불변, 수치만 재검증). test_confirm_bar.py
  · **실행 엔진**: 진입·손절·청산가 8자리(4자리는 SHIB/BONK 진입가를 0 으로 → 0 나누기로 run()
    전체 중단 경로) · DB 복원 tf 를 universe 기준으로(triple_bottom 1w 가 1d 로 복원돼 UNI 가 30일
    만기·일봉 레짐으로 평가되고 있었음) · reconcile 이 엔진 D 청산 포지션을 다시 기록해 원래 행을
    덮어쓰던 것 차단 · 킬스위치 fail-closed(잔고 조회 실패 → 진입 보류) · 같은 종목·방향 실포지션
    (거래소 실측+장부) 중복 진입 스킵 · 실체결가는 주문 재조회(종전은 주문 직전 시세) · 체결가 기준
    배리어 재정렬이 '손절 있음'으로 건너뛰어 무효였던 것을 replace= 로 교체 · 실거래 손익
    pnl_live_usd 기록. test_executor_safety.py
  · **사이징**: '위험 1%' 가 실제로는 0.5~0.7% 였다 — 앙상블 등급(백테스트 근거 없음)이 실주문에
    곱해져 단독 1d=C(x0.7), 단독 4h/1h=D(x0.5). 사이징 연구는 등급 없이 돌렸음. 실주문은 등급·TF확증
    배수 없이 equity x 1%(레짐 오버레이만 유지), 등급·확증은 페이퍼 장부·표기 전용.
  · **레짐 결정성**: 형성 중인 오늘 일봉과 실시간 BTC.D 로 오늘 라벨을 만들어 하루 안에 뒤집힐 수
    있었고 eval_D 가 그걸 전환으로 읽을 수 있었다 → 닫힌 봉만 + 오늘=마지막 닫힌 봉 라벨. 진입
    시 raw 레짐을 positions.entry_regime 에 기록해 청산 판정이 맵 재조회에 의존하지 않게. BTC.D
    fetch 실패 시 만료 캐시 우선(프록시 전환 금지). 온체인 레짐 조정은 미검증이라 표시 전용.
    test_regime_determinism.py
  · **재검증 결과(2026-09-03, validate_confirm_bar #1)**: 인과 판 **7셀 전부 REJECT**. gartley_4h +1.48%
    bp.109 / bat_4h −0.26% / butterfly_4h −0.33% / gartley_1h +0.45% med −0.01% / bat_1h −0.82% /
    butterfly_1h −0.36% / **triple_bottom_1w +3.07% med −11.36% bp.164**. old(룩어헤드) 판은 등재 수치를
    재현(부풀림 +0.9~+4.7%p). triple_bottom 은 L3 미확정 돌파 38건(평균 ≈+20%)이 엣지 전부였고 실거래가
    잡을 수 있는 104건은 게이트 미달 → **triple_bottom_1w 도 suspended_lookahead**(신규 진입 정지, 열린 UNI
    는 D 규칙대로). 복귀 후보 없음. `_pattern_tf` 는 suspended 목록도 읽어 UNI 청산 tf(1w) 유지.
    후속 가설(미검증): 미확정 돌파 셋업을 L3+3 에서 '지각 진입' — 별도 사전등록 필요.
  · **DB 스키마 패치 필요(사용자 실행)**: supabase_schema_patch_2026_09.sql — positions.entry_ts/
    target/live_mode/tf/regime/entry_regime, trades.live_mode/pnl_usd/pnl_live_usd/regime/
    entry_regime. 실행 전까지 해당 값은 복원 시 유실(코드는 폴백으로 동작).
  · **손대지 않은 것(판단 보류·후속)**: 숏 라우팅(위 레짐 스위치 항목) · 방식D 가 1d engulfing/fvg
    외 TF 에서 미검증(ih/marubozu/three_soldiers/1h/1w 는 ±10%/20봉 라벨로만 통과) · 기존 패턴
    형성 중인 봉 탐지(별도 과제 유지) · 유니버스 드리프트 · fvg/ih/marubozu 워크포워드 실패 플래그
- **레짐 스케일 연구 기각** (2026-09-03, 사용자 가설 "기각된 규칙이 레짐 문제일 수도"): 현행 일봉 레짐
  (200일선 20일 기울기)에 주봉(slow: 30주선 4주) / 4h(fast: 200봉 20봉) 스케일을 같은 3-신호 구조로
  만들어 청산 소스 교체(D_slow/D_fast, RL_slow/RL_fast)와 진입 필터(F_slow/F_fast)로 짝지음 시험.
  5년 창(n=470)과 최대 창(1d 2019~, n=570) **둘 다 7 arm 전부 REJECT**, 결론 불변.
  · 주봉 레짐 청산 D_slow −2.4~−2.7%p(t −2~−3): 전환이 늦어 번 걸 반납. 4h 레짐 D_fast −5~−6.6%p
    (t −4.4~−4.8, CAGR 우위 0/7): 너무 자주 바뀌어 조기 청산. 진입 필터 F_slow −2.2~−2.8%p: **bear
    진입 롱이 가장 수익 좋은 부분집합**이라 막으면 손해(방식R 불변 사실과 일치). F_fast −0.3%p.
  · 방식R 은 **일봉 스케일에서 가장 좋다**(RL +0.95~+1.66%p, max 창 train 통과 · holdout −0.18 탈락 —
    method_r 결론 그대로). RL_slow/RL_fast 는 RL 보다 나쁨. 층화: slow 계열은 bear 진입에서만 양수
    (단일 레짐 의존), 2024 상승장에서 slow/fast 전부 크게 음수. **레짐 스케일은 원인이 아니다.**
  · regime_multi.py / method_m.py / test_method_m.py(20건) / method_m.yml / report_regime_scale.md
- **유니버스 확대 검토 — OKX 무기한 거래대금 기준** (2026-09-04, 사용자 지시): report_universe_okx.md.
  OKX 무기한 452 중 500봉 이상 101(현 67 + 신규 34). **롱 엣지는 거래대금 1~20위에만**(engulfing top20 PASS
  +3.65%, 21위 이하 전부 기각 — 7월 코호트와 동일). 확대의 실효는 '순위 기준을 무기한 캔들로' 바꾸는 것
  (top20 의 6/20 교체: HYPE/ENA/BICO/BCH/ONDO/TAO 진입). engulfing 숏은 31~101위·현 유니버스에서 통과.
  **fvg 는 900일 창 전 코호트 기각**(마모 플래그 일치, 별도 판정 필요). 전 종목 확대는 근거 없음(81위 이하
  무통과, 틱 4배). 제안 N=80(무기한 30일 거래대금, 토큰화 자산 제외, 500봉 이상).
  · **N=80 적용 (2026-09-04, 사용자 결정 "유니버스 80 적용")**: trading_universe 67 → **80**
    (스캔 #4 순위 1~80). 추가 24(BICO/BCH/ONDO/TAO/CRV/OKB/ORDI/FARTCOIN/JTO/VIRTUAL/LDO/GRASS/
    TRB/MORPHO/BIO/STRK/MERL/CORE/AR/SUSHI/APE/LPT/SSV/KSM) / 제외 11(ICX/PENDLE/IOST/NEO/GRT/GLM/
    1INCH/QTUM/CELO/API3/ZRX — 81위 이하, 데이터 문제 아님). HYPE/ENA/KAITO 는 500봉 미만이라 후보 제외.
    근거·목록은 universe.json `universe_basis_2026_09_04`. 오픈 포지션 ADA(7위)/ARB(11위)/UNI(6위) 전부
    잔류. 신규 종목 1d/4h/1h CSV 는 다음 oncefull 에서 처음 수집(900/130/40일) — 4h/1h 블록은
    data/*_4h.csv 존재 종목을 돌므로 자동 편입. **4단계(캐스케이드 1h 재검증)는 미실행** — 새 종목
    1h 365일 수집 뒤 별도. 분기마다 universe_okx_scan 재실행으로 갱신.
- **게이트 v2 재실행 → triple_bottom_4h(전 레짐)·equal_lows_4h(bear) 배포 (2026-09-05, 자율 반영)**: report_revival.md §7.
  사용자 결정으로 분포 조건 `중앙값>0` → `승률≥35%`(gate.py v2, 핵심 원칙 참조) 후 revival/regime_split_all/
  routing_gate/intraday 재실행. **revival CONFIRMED 3 / 배포 2**:
  · **triple_bottom_4h · ALL 롱 · top30** — n=646 +1.79% med −0.52% 승률 48% bp .000 OOS 3/4, holdout n=212 +1.62%,
    train CAGR +65.9% MDD −13.7% **Calmar 4.83**, 4년 전부 양수. v1 에서는 중앙값 하나로 기각됐던 셀.
  · **equal_lows_4h · bear 롱 · top30** — n=469 +0.97% med −0.01% 승률 50% bp .001, holdout n=406 +1.17%, CAGR +4.0%
    MDD −8.4% Calmar 0.48. **기대값 작음** — '수익이 발생할 수 있으면 진행' 기준 배포. bear 에서만 돌아 지금은 대기.
  · vwap_rev_short_4h · bear 는 여전히 Calmar 0.06 경계값 → 미배포(사용자가 켜면 한 줄).
  · 1d 후보(triple_bottom_1d/double_bottom_1d/donchian20)는 승률이 아니라 **holdout 음수**로 탈락 — v2 로도 안 살아남.
  · **배포 경로**: `adopted_4h_patterns` 항목별 `cohort`("top30" = `_volume_ranked()[:30]`, 검증 turnover_rank 와 같은 정의)
    + `detect_on_closed_bar`(`_closed_idx`) — `scheduler._cohort_symbols`. three_soldiers_4h 는 두 필드 없음 → 불변.
    청산은 eval_D 그대로(OPP 매핑 없음 → 검증 opp_set=∅ 와 일치). 중복 키가 날짜 단위라 종목·일 1회 진입(검증보다 적음).
  · regime_split_all: PASSED 31→39 / STRICT 8→10. 신규 STRICT breakout_retest_4h·ALL / vol_awakening_4h·ALL 을
    CANDIDATES 에 추가(다음 revival 실행에서 확인). routing_gate 18셀·intraday 15셀 판정 불변(기각 셀은 평균 음수).
- **4h 자산곡선(C3) 프레임 정정 → vol_awakening_4h(전 레짐)·equal_lows_4h(bear→전 레짐) 추가 배포 (2026-09-05 저녁, 자율 반영)**:
  report_revival.md §8. method_x.equity_curve 가 거래 시각을 날짜 정수로 받아 **같은 날 진입·청산 거래(4h 6봉 미만, 주로 손절)를
  버리고 진입만 남겨 슬롯·증거금을 영구 잠갔다**. 봉 ts 분수 일수 정렬로 정정(`_tnum`). 정정 후 4h C3: triple_bottom_4h
  Calmar **4.83→2.79**(유지) / equal_lows bear 0.48→1.11 / vwap_rev_short bear 0.06→0.18(경계 유지) / **vol_awakening_4h ALL
  −0.24→1.38 CONFIRMED** / **equal_lows_4h ALL −0.47→0.45 CONFIRMED**. **1d 는 무영향**(보유≥1일). run 33961032437.
  · vol_awakening_4h · ALL 롱 · top30: n=4992 +1.21% 승률 44% bp .000 OOS 3/4, holdout n=1477 **+0.12%**(얇음), CAGR +99.8%
    MDD −72% 단독. **연 약 1,900건 고빈도** — 슬롯 12 를 채워 engulfing/fvg 진입을 밀어낼 수 있다(패턴 단독 프레임의 한계).
    MAX_POS 격자에서 16 이 Calmar 동일·슬롯 스킵 462→47 → 이 배포와 MAX_POS 16 상향은 한 쌍(사용자 결정).
  · **MAX_POS 격자 결과** (quant_batch1 33961480251, risk 1.5%/lev 3): 8 Calmar 1.59 MDD −55.6% / **12 1.84 −58.4%** / 16 1.85 −60.4%
    (슬롯스킵 462→47) / 20 1.83 −60.4% / 24 1.83 −60.4%(스킵 0). 동결 기준(MDD중앙≥−35%) 통과 셀 없음 — 위험 1.5% 자체가 기준 밖.
    16 이상은 증거금 스킵이 대신 늘어(125→498) 계좌 크기에 막힌다.
  · **1h 8셀(새 채점표) 0 CONFIRMED** — bull_btc 3셀은 holdout 90일(2026 bear)에 거래 0 으로 판정 불가, 나머지 C3 음수.
    rsi_extreme_short_1h bull_btc 는 train Calmar 3.96 — bull 국면 holdout 생기면 첫 후보.
  · **코호트 스캔 v2 결론 불변** — engulfing 1~20위 PASSED, 21~30위 boot_p .132 기각(중앙값 아님). fvg 전 코호트 기각.
- **중복 진입 방어 키 date → 봉 ts (2026-09-05, 사용자 결정 "봉 시각 기준으로, 앞으로 모든 규칙은 다 이렇게")**:
  `paper_executor._entry_key/_record_keys/_is_dup_entry`. 종전 (symbol,pattern,direction,**date**) 키는 4h/1h 를
  '심볼·패턴당 하루 1회'로 묶어 검증(봉마다 진입 가능)보다 거래가 적었다. 이제 봉 ts 가 있으면 ts 로 대조(같은 봉만
  중복), ts 없는 구 기록은 date 로 보수 대조. 1d 는 봉=날짜라 동작 동일. 같은 종목·방향 실포지션 중복 방어(live_dir_keys)
  는 그대로. **원칙**: 검증 프레임과 실거래 규칙이 다르면 실거래를 검증에 맞춘다. test_executor_safety 8건.
- **1h 채점표 신설 (2026-09-05, 사용자 지시)**: validate_revival 의 C3(자산곡선)이 1h 에서 계산 불가였던 원인은 거래
  시각을 날짜 문자열로 넘겨 같은 날 진입·청산이 청산→진입 순으로 정렬돼 거래가 통째로 빠진 것. `_tnum`(봉 ts →
  분수 일수) + `method_x._tnum`(숫자 그대로) 로 고침. TF 별 holdout `HOLDOUT_DAYS_BY_TF`(1h 90일 — 데이터 365일).
  1h PASSED 8셀(engulfing/engulfing_short/vwap_rev_long·short/bb_zscore_short/rsi_extreme·short)을 CANDIDATES 에 추가.
  1h 통과 셀 배포는 exit_spec(ATR 배리어)+adopted_1h_patterns+매시 fast 경로가 필요 — cascade 와 같은 길.
- **bear fvg 숏 ON (2026-09-05, 사용자 결정 "bear fvg 숏 키고")**: `direction_switch.ROUTING_OVERRIDES` 의
  (bear, fvg) FLAT 제거 → decide() 그대로 short. 9/4 OFF 의 근거 '엣지 −0.96%p' 는 k=30 베이스라인 시절 값이었고,
  k=n 재실행(routing_gate 33955072569)에서 top20·bear 셀 PASSED(n=356 +0.81% med +3.28% 엣지 +1.58%p bp .014),
  top30 bp .072, all bp .397. **유의**: 수익이 2026 bear 단일 해(+5%)에서 나오고 2022·2024 bear 는 음수 —
  실거래 fvg 는 top30 코호트라 경계 셀이다. 현 레짐 bull_altseason 에서는 즉시 변화 없음. test_direction_switch 갱신.
  · **같은 날 저녁 다시 OFF (사용자 결정 "이건 꺼주고")** — 잣대: "2026년 한 해만 이익인 규칙은 적용하지 않는다"(vwap_rev_short_4h
    미배포와 동일). bear 국면 연도별 top20 2022 −2.4% / 2024 −7.6% / 2025 −10.8% / 2026 +5.1%. 켜져 있던 약 3시간 동안 실주문 0.
    `ROUTING_OVERRIDES` {(bear, fvg): FLAT} 복원. **원칙 기록**: 단일 해(특히 현재 진행 중인 해) 의존 셀은 게이트를 넘어도 켜지 않는다.
- **MAX_POS 슬롯 격자 사전 등록 (2026-09-05, 사용자 지시 "맥스포스 12 시험")**: `sizing_vol.py --routing --slots`
  — MAX_POS {8,12,16,20,24}, risk 1.5%/lev 3/vol_matched 고정, 동결 기준(boot MDD중앙≥−35% AND P(ruin)<5% 중
  Calmar 최대). 슬롯 상한은 레버리지와 달리 동시 노출을 직접 키우므로 MDD·P(ruin) 이 먼저. **채택은 사용자 결정.**
- **beta_slope 오버레이 2단계(method_b) 기각 (2026-09-05)**: report_beta_overlay.md. B_skip(롱·하위 3분위 스킵)
  6/7, B_size(×0.5) 5/7 — 둘 다 **기준 ①(걸러진 거래가 음수)** 에서 탈락. 걸러진 n=991 의 방식D 수익
  **+2.15%**(나머지 +4.43%, p .02) — 덜 벌지만 번다. ②~⑦ 통과는 **D 기준선이 CAGR −47%/MDD −92%(7패턴
  무조건부 × 80종목, 스킵 7,141건)** 인 슬롯 범람 프레임에서 '거래를 빼면 뭐든 좋아지는' 아티팩트.
  · **설계 결함**: 오버레이 시험을 실거래 라우팅 복제 프레임(sizing_vol ROUTING_MODE)에서 돌려야 했다.
    sizing_vol 이 이미 배운 교훈 반복. 다음 오버레이 시험부터 필수.
  · beta_slope 는 필터가 아니라 **우선순위** 정보(더 좋은 vs 덜 좋은). 패턴별로 전혀 달라 engulfing 은 효과
    0, inverted_hammer·triple_bottom 은 하위 음수(−1.17/−2.91%) — **IH 한정은 사후 선택 셀**, validate_ih_exit
    교훈대로 사전 등록+반증 3종 없이는 추격 금지. 레짐 축 연구 종료.
  · method_x.equity_curve 에 선택 8번째 원소 size_mult(기본 1.0, 7-튜플 불변) 추가.
- **살릴 후보 확인 시험 + bear fvg 롱 + 신규 진입 후보 4종 + beta_slope 독립성 (2026-09-05, 사용자 지시
  "살릴 만한 것 / 스스로 찾아서 실거래에서 통과될 것")**: report_revival.md. **실거래 반영 없음.**
  · **선별 → 확인 2단계**: 베이스라인 수정 커밋이 validate_regime_split_all 을 자동 재실행(run 33947910532)
    → 기각·정지 55패턴 440셀 **PASSED 0→31 / STRICT 0→8**(우연 ≈22). STRICT 8 을 `validate_revival.py`
    가 **실거래 프레임**(방식D 청산·레짐 조건부 진입·같은 청산 규칙의 k=n 베이스라인·실거래 사이징
    자산곡선)으로 다시 잼. 기준 = 동결 5 + C1 두 코호트 + C2 holdout 365일 + C3 Calmar>0.
  · **결과 8 중 7 기각 — 1d 후보 전 셀 중앙값 −8.20%(= −8% 손절+수수료)**. 방식D 에서 거래 절반 이상이
    손절(triple_bottom 62%, double_bottom 53%). 선별 라벨(±10% 대칭)은 이 성질을 못 본다. 평균은 크게
    양수(triple_bottom_1d bull_btc top30 **+8.22%** 엣지 +6.03%p Calmar 1.18)지만 복권형 — **동결 게이트
    median>0 이 정확히 거르는 것**. 가장 가까운 기각: triple_bottom_4h ALL(holdout +1.62% Calmar 4.83,
    중앙값 −0.52%).
  · **vwap_rev_short_4h · bear — 경계 통과, 미반영**: C1~C3 문자상 통과이나 **Calmar 0.06(CAGR +1.65%)**,
    표본 92% 가 holdout 창(train n≈118, 2025 −0.9%), 2026 bear 단일 해 아티팩트 위험. 자율 반영 조항의
    '경계값 제외' 첫 적용. registry passed_boundary_not_deployed — 사용자가 켤 수 있으나 기대값 연 1.65%.
  · **설계 결함**: C2 가 holdout n≥10 만 요구해 train 이 비어도 통과. 다음 설계부터 train 자체 게이트 통과
    요구(사후 변경 금지로 이번엔 미적용 — 적용해도 판정 동일).
  · **three_soldiers_4h 재판정**: top30 bull_btc PASSED(n=84 +2.92% med +0.98% bp .011) / all REJECTED
    (med −0.49%). 배포 유지(원 프레임 근거 불변). 실거래는 all 코호트에서 돎 → **top30 축소 사전 등록 후속**.
  · **bear fvg 롱 단일 셀(route_bfl) 기각**: 셀 n=538 +1.63% 는 맞으나 CAGR 103→90% / Calmar 2.29→1.77 /
    holdout −43→**−66%**(2026 bear 에 추가 거래 273건 몰림) / 부트 우위 31%. 건당 +1.6% 거래가 슬롯·증거금을
    차지해 건당 +7.3% 자리를 빼앗는다. **어제 FLAT 결정 옳음.** 새 arm 은 기준 ③ 셀별 부호 규칙(PER_CELL_ARMS).
  · **신규 진입 후보 4종 40셀 0 확인**: ibs_low(bull_btc 엣지 **−1.58%p** 역신호) / rsi2_low / down_streak3 /
    donchian20(bull_btc +5.85% 인데 med −8.20%, holdout −7.84%). 전 셀 중앙값 음수, 자산곡선 MDD −85~−92%.
    **캔들 가족에 이어 일봉 평균회귀 지표·Donchian 추세추종도 방식D 프레임에서 닫힘.**
  · **beta_slope vs avg_cap — 독립 축 확인**: Pearson 0.139 / Spearman 0.089, cap 하위·중간 3분위 안에서
    beta 스프레드 **+5.89 / +8.43%p**(p .000), 상위에선 −1.35(p .129). 사전 규칙 충족 → **2단계 method_b
    사전 등록** (D / D+beta 하위 스킵 / D+beta 사이징, method_r 7기준). 레짐 축 연구의 유일한 생존 축.
  · **배포 경로 준비**: `scheduler.adopted_regime_ok` — adopted 항목별 `regimes`(없음=종전 · "all" · [레짐]).
    현 배포 3항목 동작 불변(test_adopted_regimes 14건). 4h 항목 방향·숏 손절 방향 처리.
  validate_revival.py / test_revival.py(46) / test_adopted_regimes.py(14) / revival.yml / report_revival.md
- **라우팅 게이트 — boot_p 베이스라인 버그 수정 + 진입 방향 arm 시험 (2026-09-05, 사용자 지시
  "레짐이 매매를 막을 수도 있는 것 아닌가")**: report_routing_gate.md. **실거래 무변경.**
  · **`gate_cell` 베이스라인이 30 표본에 묶여 있었다** — `k = min(max(10, min(30,n)), len(pool))`.
    셀이 n=75 여도 베이스라인은 30 개만 뽑아 평균의 표준오차가 sqrt(30) 에 고정되고, 분포가
    넓어진 만큼 **boot_p 가 부풀려졌다(보수적)**. engulfing 숏 altseason 의 `.045 ↔ .055` 진동은
    데이터가 아니라 이 추정량 탓이었다. **k=n 으로 수정 — 게이트 문턱은 불변**이고 한쪽으로
    느슨해지는 변경도 아니다(엣지 양수 셀은 내려가고 음수 셀은 올라간다, 테스트가 양방향 고정).
    validate_regime_split_all.py:166 의 복사본도 함께.
  · **재실행: 통과 셀 2개 → 18개.** engulfing 롱 bull_btc(3코호트)+ALL(2) / **engulfing_short
    bull_altseason 3코호트 전부** / fvg 롱 bull_btc(3) / fvg_short top20:bear / IH bear(3)+ALL(2) /
    marubozu all:ALL. **종전 "72셀 중 2셀 통과"는 상당 부분 측정 결함이었다.**
  · **진입 방향 arm 시험 (validate_routing.py, 사전 등록 7기준)** — 청산은 세 arm 모두 방식D 동일,
    다른 건 진입 방향뿐. route(현행 복제) / uncond(레짐 미사용, 둘 다 롱) / gated(분리 게이트 통과
    셀만). **uncond·gated 둘 다 현행 유지.** train CAGR route +103.2% / uncond +82.3% / gated +71.0%,
    Calmar 2.29 / 1.63 / 1.65, 부트 Calmar 우위 uncond 31% · gated 7%.
  · **사용자 질문 직답 — bull_altseason engulfing: route 숏 n=53 +0.32% vs uncond 롱 n=11 −2.77%.**
    그 레짐의 롱은 11건뿐이고 음수다. 숏이 낫고, 레짐 분리 게이트도 그 숏 셀을 통과시킨다.
  · **3단계 제안(라우팅에 동결 게이트 적용)은 시험했고 기각** — gated arm 이 정확히 그것이었다.
    꺼지는 셀이 bear engulfing 롱(n=47 **+2.41%**)과 altseason fvg 롱(n=146 +0.02%)인데 앞의 것이
    수익 셀이다. **레짐별로 쪼갠 셀은 표본이 작아 게이트를 못 넘을 뿐 엣지가 없다는 뜻이 아니다** —
    게이트를 라우팅 계층에 옮기면 '표본 부족'을 '엣지 없음'으로 오독한다.
  · route 와 gated 는 8셀 중 **6셀이 동일**하고, 방향을 두고 충돌하는 셀은 **하나도 없다**
    (다른 2셀은 게이트가 아무것도 통과 못 시킨 자리에서 route 가 거래하는 경우).
  · **방법 결함 자체 발견·수정**: equity_curve 가 CAGR 을 **arm 자신의 거래 간격**으로 연율화해
    arm 마다 분모가 달랐다. 1차에서 gated holdout 이 **MDD −36.6% 인데 CAGR −92.2%** 로 찍혔다.
    `equity_curve(trades, span_days=None)` 추가(기본값은 종전 동작 = method_x 수치 불변), 분할
    공통 창으로 통일. 수정 후 −35.7% 로 기준 ⑦ 이 뒤집혔으나 **판정은 불변**. 전반/후반 mid 도
    arm 별 중앙값 → 달력 중점으로 통일.
  · **기준 ③은 엉뚱한 이유로 통과** — uncond 분기 우위(+1.54% vs +0.32%)가 전부 bear fvg 롱
    538건에서 나왔고 정작 altseason engulfing 셀에서는 크게 졌다. 분기 표본을 셀 구분 없이 합친
    설계 한계. **사후 기준 변경은 사전등록 위반이라 판정은 그대로 두고**, 다음 설계에 '분기 평균은
    셀별 부호 요구'를 넣는다(validate_short_exit 대조군의 부호 조건 누락과 같은 종류).
  · **종전 리포트 boot_p 는 전부 보수 편향분** — report_regime_split(_all).md 재해석 대상,
    `_all` 의 "440셀 PASSED 0" 도 재실행 필요.
  validate_routing.py / test_routing.py(47건) / routing_gate.yml / report_routing_gate.md
- **레짐별 분리 게이트** (2026-09-04, 사용자 제안 "레짐 나눠서 테스트해야 맞다"): report_regime_split.md.
  1d 패턴 6종 x 진입레짐 4 x 코호트 3 = 72셀. boot_p 베이스라인을 **같은 레짐·코호트 무작위 진입**으로
  잡아 "상승장이라 오른 것"을 엣지로 오인하지 않게 함(test_regime_split 이 성질 고정).
  · **통과 2셀**: engulfing 롱 top20 **bull_btc**(n=52 +4.84% med+10.14% bp.049) /
    engulfing 숏 top30 **bull_altseason**(n=75 +5.70% med+10.28% bp.045 OOS4/4).
  · **사용자 가설 확인** — 같은 패턴 레짐 간 최대 13%p 차(engulfing 롱 bull_btc +1.78% vs
    altseason −6.97%). 전체 기간 하나로 재면 상쇄돼 전부 기각으로 보인다.
  · **레짐 자체 수익 vs 패턴 엣지 분리 (재실행, 사용자 의문 제기 후)**: 셀마다 같은 레짐·코호트
    무작위 진입 평균을 함께 출력. **bull_altseason 의 무작위 롱은 20봉 −3.04%** — 라벨이 후행
    지표라 국면 끝자락에 몰리기 때문. 5년 중 173일뿐인 짧은 국면.
  · **첫 보고의 '라우팅 부호 반대 2건' 중 altseason fvg 롱은 오진 — 철회.** 그 셀 엣지는
    **+0.92~+1.95%p 양수**이고 절대 수익이 음수인 것은 레짐 탓이다. 엣지 기준으로 보면
    **현재 라우팅 6셀 중 5셀이 맞다.** 유일한 불일치는 **bear 의 fvg 숏**(롱 엣지 +1.34 vs 숏 −0.96).
  · **fvg 롱은 세 레짐 모두 엣지 양수**(+2.39/+0.92/+1.34), **fvg 숏은 세 레짐 모두 엣지 음수**
    (−1.40/−1.25/−0.96) — 숏은 레짐 문제가 아니라 패턴 문제.
  · 주의: boot_p 베이스라인이 30건 표본이라 n 큰 셀에 보수적 — 표본 수 정합 후속 필요.
    재실행에서 engulfing 숏 altseason 이 bp .045→.055 로 경계 이탈(엣지 +3.59%p 유지).
  · **기각·정지 55종 전수 레짐 재시험 (2026-09-04)**: report_regime_split_all.md. 440셀 **PASSED 0 / STRICT 0**
    (우연 기대 22). 레짐을 나눠도 기각 패턴은 살아나지 않음 — 재시험 종료. 가까운 셀은 boot_p .06~.13
    (order_block_short altseason n=39, triple_bottom_4h altseason, triple_bottom_1w top30 n=35 +6.2%).
    후속 후보 하나: **triple_bottom top30** 데이터 누적 후 사전 등록. **three_soldiers_4h 주의** — 레짐
    베이스라인으로 재면 bull_btc 셀 bp .165(ALL +0.52% bp .284), 원 등재는 무조건부 베이스라인. 배포
    유지 근거 약화, 별도 판정 필요. 1h 셀은 1년치(bear 77%)라 '기각 유지'로만 읽을 것.
    validate_regime_split_all.py / test_regime_split_all.py(34건)
  · **레짐 청산 소거 시험 — 레짐 청산 유지 확정 (2026-09-04, 사용자 질문 "레짐이 방향도 모르는데
    그걸 근거로 청산하는 게 이상하지 않나")**: report_regime_exit_ablation.md. **모순 아님** —
    라벨 품질은 라벨의 **수준**을 예측기로 쟀고(적중 <50%), eval_D 는 라벨의 **변화**만 본다.
    다만 레짐 청산을 아예 뺀 판은 한 번도 재본 적이 없었다(method_d 묶음비교/method_r 좁힘/
    method_m·q 소스교체). 4 arm 짝지음(메이저 7종목, 2,780일, train n=729, 홀드아웃 365일):
    · **D_shuffle 19/20 패배 (합산 −2.58%p, t −3.40)** — 라벨별 일수·런 길이·**전환 수까지 정확히
      보존**하고 정렬만 파괴한 라벨이 20 draw 중 19 개에서 D 에 짐(중앙 −0.72%, 유일 예외 +0.018%p
      로 사실상 동률). **청산 시점에 정보가 실재.**
    · **D_time −3.62%p (t −4.80, CAGR우위 1/7)** — D 의 실측 평균 보유를 그대로 상한으로 줘도
      무너짐. '레짐 청산은 그냥 시계'라는 해석 기각.
    · **D_norg — 메이저 −0.045%p(t −0.14, 구분 불가) 이나 유니버스 80 에서 −1.788%p(t −12.83)**.
      **정정: '순기여가 작다'는 표본 부족 탓이었다.** 80종목 train n=4,136 에서 분기 거래 1,126건
      중 D 가 76% 승리, 패턴별 승률 21~24% 로 일관. 즉 제때 나가면 이득, 엉뚱하게 나가면 손해,
      **안 나가면 손해**.
    · **유니버스 80 재확인 (2026-09-04, 사용자 지시)**: 판정 A 동일, 모든 지표가 더 강함 —
      셔플 20/20(중앙 −1.70%p, 20 draw 전부 음수), D_time −3.30%p, D_shuffle −3.15%p.
      **홀드아웃(2025-09~2026-09)은 판별력 없음** — 2026 이 bear 247일 단일이라 레짐 전환이
      거의 없어 arm 이 안 갈라진다(D_norg 분기 1,126→약 96건). 숏 2셀만 홀드아웃에서 D_norg
      우세(engulfing_short +0.93%p t2.19, fvg_short +0.26%p t3.19) — 방식R 의 '롱·숏 비대칭'과
      같은 방향, n 작아 후속 과제. 주의: --universe 는 모든 패턴을 80종목에 돌려 실거래 라우팅
      (engulfing→top30 등)의 복제가 아니라 표본 크기 강건성 확인.
    · 청산 사유에서 레짐 전환은 fvg 의 약 1/3(134/366)을 담당하는 주 출구. 빼면 손절·만기가 대체.
    · 방법 정정: 1차 무제약 셔플은 전환 수가 97→43~61 로 줄어(같은 라벨 런 병합) 청산이 절반이
      되며 D_norg 쪽으로 끌려갔다 → `_sequence_no_adjacent` 로 전환 수 정확 보존(2차). 편향이
      결론에 불리하게 작용했음이 확인 — 격차가 −0.98%p(1차) → −2.58%p(2차) 로 벌어짐.
    · **판정 A_상태정보_실재. 실거래 무변경(방식D 유지).** method_s.py / test_method_s.py(41건) / method_s.yml
  · **퀀트 카탈로그 1차 묶음 (2026-09-04, 사용자 지시)**: report_quant_batch1.md. 학술 A등급 중
    레포 미시험 2건을 사전 등록해 시험.
    · **변동성 타겟팅 사이징 — 채택·실거래 반영 완료(2026-09-04 사용자 결정).** 현행은 risk 1%/손절 8%
      고정이라 명목가가 자산 변동성과 무관한데, 진입 시점 20봉 실현변동성이 중앙 연율 86%·10~90분위
      49~144% 로 3배 차이. arm risk/vol_raw/vol_matched(노출 정합, 주 판정), 거래 6,640건 부트 300회.
      **4조건 전부 통과** — boot Calmar 0.18 vs −0.00 / boot MDD −73.0% vs −81.8% /
      **P(ruin) 14.3% vs 37.7%** / 노출 0.98배. 가장 큰 변화는 수익이 아니라 파산 확률.
      유보: 6,640건 중 5,227건이 슬롯·증거금 스킵. 반영하려면 sizing.risk_based_size 에 σ 스케일
      인자 + 진입 시점 변동성 전달 경로 필요.
      · **실거래 라우팅 복제 판 (2026-09-04 사용자 지시, `--routing`)**: 스케줄러 진입 조건 세 겹
        (패턴별 유니버스 / 레짐→방향 라우팅 — FOCUS 한정, ih·marubozu 는 무게이트 / 정지 패턴 제외)을
        그대로 걸어 재측정. 표본 6,640 → **991건**(fvg_short 는 bear OFF + bull 롱 라우팅이라 **0건**).
        **판정 동일 — 4조건 전부 통과**: boot Calmar **1.06 vs 0.65** / boot MDD −45.4% vs −51.8% /
        P(ruin) 0.3% vs 3.7% / 노출 0.96배.
        **정정 성격의 발견 — 라우팅 자체가 큰 개선이다.** 현행(risk) arm 만 봐도 boot Calmar
        −0.00 → 0.65, P(ruin) 37.7% → 3.7%. 전 표본 판에서 '현행 사이징이 취약'해 보인 상당 부분은
        라우팅이 걸러내는 셀까지 넣고 잰 탓이다. 그 위에서도 vol_matched 가 이기지만 **개선의 근거는
        P(ruin)이 아니라 Calmar·MDD** 로 옮겨간다(0.3%는 이미 낮은 값에서의 감소).
        유보: 현재 라우팅 표를 과거에 소급 적용한 판이라 절대 수준은 낙관적(세 arm 이 같은 신호
        집합이라 arm 비교는 상쇄). 표본이 1/7 이라 부트 변동 큼. 출력 sizing_vol_routing.json.
      · **실거래 반영 (2026-09-04)**: `s_raw = clip(0.80/σ, 0.5, 2.0)`, `vol_scale = s_raw/1.1094`,
        `risk_usd = equity x 1% x regime_mult x vol_scale`. **배율 0.45~1.80배, 손절가·레버리지 불변 —
        바뀌는 건 명목가뿐.** 1.1094 는 라우팅 표본의 s_raw 평균(s_norm); 연구의 인과적 확장평균이
        수렴하는 값이라 '앞으로 나갈 거래'에는 상수가 충실한 구현이다. sizing_vol 이 매 실행 이
        상수와 대조해 0.02 이상 벌어지면 경고.
        · **sizing.py 가 원본** — realized_vol/vol_scale_raw 가 여기 있고 sizing_vol(연구)이 import.
          연구와 실거래가 다른 구현을 쓰면 검증한 규칙과 주문이 조용히 갈라진다(test 가 `is` 로 고정).
          risk_based_size(..., vol_scale=) 추가(연구의 risk_frac 스케일과 수식상 동치, 테스트로 확인).
          폴백 3종(타겟팅 off / 상수 미설정 / σ 산출 불가)에서 1.0 = 채택 전과 완전 동일.
        · **부작용 ① 건당 달러 위험이 1% 고정이 아니다** — 손절 8% 고정 + 명목가만 이동이라
          risk_usd 는 약 0.45~1.80%. 일정해지는 건 달러 위험이 아니라 변동성 기여(명목가 x σ)이고
          검증에서 개선된 것도 그쪽. 종전 '위험 1% 고정' 표현과 어긋나므로 명시.
        · **부작용 ② 현 계좌에서 고변동 신호는 주문이 안 나간다** — 명목가가 줄면 증거금이 최소
          주문($10) 미달로 스킵. 문턱 equity = 160/vol_scale: 1.80→$89 / 1.00→$160 /
          **0.58→$276(현 계좌, σ 약 124%/yr)** / 0.45→$355. **실측 스킵 비율(라우팅 991건)**:
          equity $200 **37.1%** / $250 20.3% / **$276 약 12~15%** / $300 8.4% / **$400 이상 0%**
          (최저 배율 0.45 아래로는 잘릴 신호가 없다). 즉 **$400 넘으면 부작용 소멸, 계좌가 작아지면
          급격히 악화** — 채택 전에는 equity>=$160 이면 스킵 0% 였으므로 이 구간은 거래 기회를
          실제로 잃는 교환이다. sizing_vol 이 계좌 규모별 스킵 비율을 표로 찍고,
          실거래 스킵 로그에도 필요 equity 를 남긴다. **레버리지 상향으로 해소 가능하나 안 했다** —
          sizing_study 에서 상향은 동시 노출만 키워 MDD 악화(2→5x, CAGR 43→36%/MDD −67→−76%).
        · 되돌리기: `sizing.VOL_TARGETING = False` 한 줄. sizing_vol_live 테스트가 그 성질을 고정.
  · **레버리지·위험 격자 — 레버리지 상향 권고 안 함 (2026-09-04, 사용자 질문 "좀 더 공격적으로")**:
    report_leverage_2026_09.md. `sizing_vol.py --routing --grid`, risk{0.5,1,1.5,2,3}% x lev{2,3,5},
    사전 기준은 sizing_study 와 동일 동결(boot MDD중앙>=-35% AND P(ruin)<5% 중 Calmar 최대).
    · **통과 3셀 전부 risk 0.5%** (최적 0.5%/lev5, Calmar 1.08). 현행 1% 는 MDD중앙 -45.4% 로
      기준 밖 — 2026-09-02 결론과 동일. 변동성 타겟팅·유니버스 80·라우팅 복제를 얹어도 불변.
    · **레버리지는 살 게 없다** — 현행 risk 1% 에서 lev2 의 **증거금 스킵이 이미 0**. lev 2/3/5 가
      Calmar 1.06/1.05/1.06, MDD -45.4/-45.5/-45.0% 로 노이즈 수준 동일. 순효과는 청산 여유
      49%→19% 감소뿐. 이 표본에서 진입을 막는 건 증거금이 아니라 **슬롯(MAX_POS 12, 391건)**.
    · **역효과 발견 — 레버리지를 올리면 최소주문에 더 자주 걸린다.** 최소주문 제약은 증거금에
      걸리는데 레버리지가 그 증거금을 줄인다(필요 equity = 10 x lev x stop / (risk x vol_scale),
      레버리지에 비례). **$400 계좌 기준 필요 vol_scale >= 0.2 x lev**: lev2 0% 스킵 /
      lev3 약 14% / **lev5 절반 이상**(σ<=72%만 통과, 표본 중앙 σ 78%).
    · **Calmar 가 격자 전체에서 0.99~1.14 로 평평하다** — risk 를 6배 올려도 CAGR 과 MDD 가 같은
      비율로 커진다. **최적 위험은 없고 낙폭 선호의 문제다.** 0.5%: CAGR+26%/MDD-25% ·
      1%(현행): +49%/-45% · 1.5%: +69%/-61%(p10 -80%, Calmar 최대 1.14).
    · **판정: 레버리지 상향 안 함.** 위험 수준은 사용자 결정. 남은 유효 레버는 MAX_POS 이나
      동시 노출을 직접 키우므로 별도 사전 등록 필요(미실행).
    · **RISK_FRAC 1% → 1.5% 상향 (2026-09-04, 사용자 결정 "리스크 1.5%로 올려줘", 계좌 $400+ 충전 후)**:
      명목가 = equity x 1.5% / 8% = **equity 의 18.8%**(종전 12.5%). equity $400 기준 건당 위험
      $6 · 명목가 $75 · 증거금 $37.5(lev 2).
      · **사전 기준은 여전히 미충족** — 통과 셀은 risk 0.5% 뿐. 근거는 'Calmar 평평'(격자 15셀
        0.99~1.14)이라 최적 위험이 존재하지 않고 낙폭 선호가 정한다는 것. 1.5% 지점의 뜻:
        boot CAGR **+63.0%**(1%는 +49.1%) / boot MDD중앙 **−59.7%**(−45.4%) / **p10 −80.5%**(−65.1%)
        / P(ruin) 2.3%(0.3%). **5번 중 1번 −80% 낙폭**을 받아들인 선택.
      · **부수효과 ① 최소주문 문턱이 내려간다** — 문턱 = 10 x lev x stop /(risk x vol_scale) 이라
        risk 에 반비례. 최고변동(배율 0.45) 신호까지 통과하는 equity 가 **$355 → $237**. 즉 고변동
        스킵 문제는 오히려 **해소**됐다(현 계좌에서 어떤 변동성이든 스킵 0).
      · **부수효과 ② 증거금이 새 제약이 된다** — equity $400 에서 포지션당 $37.5 라 MAX_POS 12 를
        채우려면 $450 필요, 10개쯤에서 free 가 마른다. 격자에서도 risk 1.5%/lev2 는 증거금 스킵
        109건이고 **lev 3 에서 15건으로 줄며 Calmar 1.03→1.13**. **risk 1% 에서 무의미했던
        레버리지 상향이 1.5% 부터는 의미가 생긴다** — LEV_CAP 은 2 유지, 별도 사용자 결정 사항.
        (참고: $400 에서 lev 3 도 최소주문 스킵 0%, lev 5 는 배율 0.67 미만이 스킵)
      · test_sizing / test_sizing_vol_live 가 값과 문턱을 고정. 문턱 단언은 하드코딩 대신
        **파라미터에서 유도**하도록 고쳤다 — 1%→1.5% 상향에서 하드코딩 단언이 조용히 무의미해졌다.
    · **LEV_CAP 2 → 3 상향 (2026-09-04, 사용자 결정, risk 1.5% 와 한 쌍)**: 2026-09-02 의 '레버리지
      상향은 이득 없이 MDD 만 악화'는 **risk 1% 에서의 결론**이었다 — 거기선 증거금이 남아돌아
      (증거금 스킵 0건) 살 게 없었다. risk 1.5% 에서는 증거금이 제약이 되므로 결론이 뒤집힌다.
      · 격자(라우팅 991건): risk1.5%/lev2 증거금스킵 109건·Calmar 1.03·MDD중앙 −59.7% →
        **lev3 증거금스킵 15건·Calmar 1.13·MDD중앙 −60.8%**. 레버리지가 실제로 진입 94건을 사 온다.
        MDD 는 −1.1%p 더 깊어지지만 CAGR 이 +63.0→+68.7% 로 더 올라 Calmar 개선.
      · 안전: 8% 손절에서 lev3 청산거리 = 1/3 − MMR = **32.3%, 손절폭의 4.0배**(LIQ_SAFETY 2.0 여유
        충족, liq_safe_leverage 상한 5 보다 낮음). lev2 는 49%·6.1배였다.
      · equity $400 에서 포지션당 증거금 $37.5 → **$25**, 12슬롯 $450 → **$300** 으로 equity 안에 들어온다.
      · **대가: 최소주문 문턱이 레버리지에 비례해 올라간다** — 전 신호 통과 equity 가
        lev2 $237 → **lev3 $355**. 현 계좌 $400 에서는 스킵 0 이지만 **$355 밑으로 내려가면
        고변동 신호부터 주문이 안 나간다.** 여유가 $45 뿐이라 계좌 감소 시 주시 필요.
      · **2026-09-10 RISK_FRAC 1.5% → 1.0% 하향 (사용자 결정 "1%/3배로 적용해줘")** — LEV_CAP 은 3 유지.
        낙폭 선호를 한 단계 낮춘 결정이고, 격자 기준 **수익도 낙폭도 약 3분의 2**가 된다:
        boot CAGR +68.7%→**+49.1%** / MDD중앙 −60.8%→**−45.4%** / p10 −80.5%→**−65.1%** /
        P(ruin) 2.3%→0.3% / Calmar 1.13→1.06. Calmar 가 거의 안 움직이는 것이 '좋아진 게 아니라
        볼륨을 낮춘 것'이라는 증거다(격자 15셀 0.99~1.14). **사전 기준(MDD중앙≥−35%)은 여전히
        미충족** — 통과 셀은 0.5% 뿐인데 그건 문턱 $1,067 이라 현 계좌($763)에서 주문이 안 나간다.
        · **산 것: 총 명목가 상한(2.5x)이 풀렸다** — 건당 명목가 18.75%→12.5% 라 상한 도달이
          13.3개 → **20개**. 종전에는 **MAX_POS 16 을 구조적으로 못 채웠다**(16슬롯 증거금이
          equity 의 100%). 이제 67%. 9/10 포트폴리오 프레임이 holdout 병목을 슬롯 440 vs
          증거금 2,750 으로 짚은 자리가 여기다. 시험 두 건이 이 역전을 잡아 고정했다.
        · **대가: 최소주문 문턱이 risk 에 반비례해 올라간다** — 전 신호 통과 equity
          $355 → **$533**(배율 1.0 기준 $160 → $240). 현 계좌 $763, 여유 약 $230.
        · **lev 2 가 아니라 3 인 이유**: risk 1%/lev2 는 1.5%/lev3 과 증거금(6.25%)·문턱($355)이
          **완전히 동일**하고 명목가만 줄어든다(risk/lev 이 같으므로). lev 3 이 사는 것은 포지션당
          증거금 6.25%→4.17% 뿐이고 그게 정확히 16슬롯 문제의 해답이다. 2026-09-04 의 '레버리지는
          risk 1% 에서 무의미'는 MAX_POS 12·equity $400 시절 결론이라 지금은 성립하지 않는다.
        · 게이트 문턱(−35%)은 **건드리지 않았다** — 풀어도 주문이 한 건도 안 바뀌고 사후 변경이 된다.
        · 되돌리기: `sizing.RISK_FRAC = 0.015` 한 줄. registry `risk_level_2026_09_10`.
      · 현행 요약: **RISK_FRAC 1.0% / LEV_CAP 3 / 손절 8% / 변동성 타겟팅 on**.
        명목가 = equity x 12.5% x vol_scale(0.45~1.80), 증거금 = 명목가/3 = equity x 4.17%.
    · **횡단면 모멘텀 — 전 셀 기각(5/5).** 주간 리밸런스·상위10·skip-1·L={7,14,28,56,84}.
      mean −0.57~−1.08%, 엣지 +0.02~+0.51%p, boot_p .41~.49. **프레임 탓 기각 아님** — 추세 60봉
      진단도 전부 음수(−5.4~−7.8%). 포트폴리오는 상위10 −88% vs 유니버스 −81% 로 **더 나쁨**.
      RS 필터 기각(2026-07-08)과 같은 방향 — 상대강도는 필터로도 단독 규칙으로도 작동 안 함.
      **관측 창 2024~2026(2.4년) 한계** — 유니버스 80 은 대부분 900봉이라 2024 이전은 20종목이
      동시에 이력을 갖지 못한다. --min-bars 1800 확장 시도했으나 해당 종목이 3개뿐이라 신호 0건.
      코드 문제가 아니라 데이터 현실. 이력 누적 후(6개월~1년) 재시험 가능.
    · **방법 정정(run #1→#2)**: 노출 지표를 달러 명목가로 재 1.94배로 오독 — 성과 좋은 arm 이 자본을
      키워 명목가도 커지므로 레버리지와 수익이 뒤섞인다. **진입 시점 레버리지(명목가/equity)** 로
      교체하니 0.98배. 판정에 (d) 노출 정합 가드 추가.
    sizing_vol.py / validate_xsec_momentum.py / test_sizing_vol.py(35) / test_xsec_momentum.py(28) / quant_batch1.yml
  · **숏 레짐 청산 재검토 REJECT (2026-09-04, 사용자 지시)**: report_regime_exit_ablation.md.
    method_s 홀드아웃에서 숏 두 셀만 D_norg 우세였던 것(사후 선택 셀)을 반증 시도. 유니버스 80
    전 구간. arm: S_norg(숏 레짐청산 제거) / **S_adv(숏은 불리 국면 진입 전환에만 청산 — method_r
    RL 의 거울상, 최초 시험)**. 반증 4종 중 **둘 다 1/4 NOISE**.
    · ④ 레짐층화가 결정타: bear 만 −0.39/+0.00%p, bull_btc −0.05, **bull_altseason −2.67%p** —
      홀드아웃(2026 bear 단일) 관찰은 국면 아티팩트. ① 전후반 양쪽 음수, ② 부트 CI 가 0 을
      배제하되 **음수 쪽**(D 가 유의하게 우위).
    · **③ 대조군 통과는 무의미** — 사전 규칙을 '숏>롱'으로만 두고 부호를 안 걸어, 숏 −0.45%p /
      롱 −1.54%p 로 둘 다 D 보다 나쁜데 통과로 집계됐다. '숏>롱 **이고** 숏>0' 이었다면 0/4.
      다음 대조군 설계 시 부호 조건 필수(기록).
    · 부수: 롱 대조군 −1.21~−1.54%p 가 method_s D_norg·method_r RL 기각을 독립 재현.
      S_adv 가 S_norg 보다 일관되게 덜 나쁨(방향 인지가 낫지만 D 에는 못 미침).
    · **실효 범위**: 라우팅상 숏이 나가는 셀은 bull_altseason engulfing_short 뿐이고 bear fvg 숏은
      이미 OFF — 그 유일한 셀이 층화 최악 구간이라 바꿨으면 손해. 실거래 무변경.
    validate_short_exit.py / test_short_exit.py(36건) / short_exit.yml
  · **레짐 라벨러 강화 연구 REJECT (2026-09-04, 사용자 지시 "레짐 정확도를 올릴 변수 추가")**: report_regime_quality.md.
    breadth/vol/funding 신호로 라벨러 6후보(fast_slope/breadth_price/vote4/vol_side/funding_cap/breadth_only) —
    1단계 라벨 품질(분리폭·적중·지연·flips, 사전 규칙 4개) **후보 0**, 2단계 짝지음 19 arm **전부 REJECT**.
    **핵심 발견: 현행 레짐은 20일 지평 방향 예측력 ≈0** — 적중 49%, bear 라벨 날 선행수익 +0.04%, bull 3년
    연도별 분리폭 음수(−20.9/−7.2/−4.3), 전환 지연 평균 50일·중앙 72일(28회 중 13회 90일 내 미포착).
    라벨을 빠르게 하면(D_*) D 의 레짐 전환 청산이 잦아져 전부 악화 — 레짐의 기여는 예측이 아니라 청산
    트리거·셀 분리. **'레짐을 예측기로 쓰지 말 것'**이 결론. D_vote4 train t 2.54 이나 holdout 분기 0건,
    F_*(bear 롱 차단)는 train 손해·holdout(bear 해) +1%p 단일국면. funding 은 OKX 이력 94일뿐(미검증).
    **지평 진단(run #2)**: 20/40/60/90일 전부 적중률 47~49%, 40·60일 분리폭 음수 — 느려서가 아니라 신호 집합에
    방향 정보가 없다. 폭 라벨은 긴 지평에서 강한 역행(90일 −18.7%p). **레짐은 상태 분류기로만 유지.**
    라벨러 채택 시 재검증 경로: `validate_regime_split(_all).py --labeler <name>` (셀 재정의) + 라우팅 재생성 +
    method_d 청산 재검증 — 세 곳 모두 라벨에 의존(사용자 질문 2026-09-04 "레짐 바뀌면 패턴 재테스트?" → 예, 단
    지금은 채택된 라벨러가 없어 대상 없음).
    regime_alt.py / regime_quality.py / method_q.py / test_regime_quality.py(43건) / regime_quality.yml
  · **bear fvg 숏 OFF (2026-09-04, 사용자 결정 "bear 숏 끄고")**: `direction_switch.ROUTING_OVERRIDES`
    {(bear, fvg): FLAT}. main() 이 매 실행 regime_switch.json 의 무조건부 n≥20·mean>0 로 표를 다시
    만들므로(bear fvg 숏 +2.54% 로 여전히 short) JSON 편집은 무효 → 코드에 예외를 둔다. bear fvg 롱
    (엣지 +1.34%p)은 동결 게이트 미통과라 켜지 않고 FLAT. 현 레짐이 bear 라 즉시 효력 — bear 에서는
    engulfing 롱만 나간다. 나머지 5셀 유지. test_direction_switch.py(20건) 가 고정.
- **청산 변형 3종 기각 + 레짐 추가 축 5종 중 1종만 생존 + 삼각수렴 비권장** (2026-09-04, 사용자
  제공 카탈로그 2종 + 사용자 제안): report_exit_regime_axis.md
  · **청산 5 arm 전부 REJECT** (train n=7,752 짝지음): ATR 배수 손절 A20/A25/A30 은 **건당 평균을
    올리지만(+0.70~0.98%p, t 3.7~4.8) CAGR 우위가 2/7**. 위험기준 사이징에서 **손절을 넓히면
    명목가가 그만큼 줄어**(명목가=위험/손절폭) 건당 수익률 개선이 복리로 안 붙는다. 분기 승률
    26~28%(드물게 크게 이기고 자주 작게 짐), 전반 음수·후반만 양수, 패턴 재표본 boot_p .24~.28.
    · **이 발견은 자산곡선을 바꿔서 나왔다** — method_t.equity_curve 는 가용잔고 x20% 고정이라
      stop_pct 를 안 본다. 그대로 썼으면 ATR 손절이 순수 승리로 보였을 것. method_x 는 실거래와
      같은 sizing.risk_based_size 에 arm 의 손절폭·변동성 배율을 넘긴다.
    · **T(조건부 시간손절) 는 유의하게 악화** −0.325%p t=−3.31. 카탈로그 §6-3 조언("이익 중인
      포지션을 시간 때문에 자르지 마라")이 이 데이터에서는 반대로 작동 — 수익은 초기에 집중되고
      그 뒤엔 평균회귀가 이긴다(method_t/e 기각과 같은 방향). S(구조적) +0.515%p 이나 boot_p .31.
  · **레짐 축 1단계 진단 — ADX·효율비는 방향이 예상과 반대**: 저ADX(횡보) +2.97% vs 고ADX +0.43%,
    효율비 +3.10% vs +0.15%. 카탈로그는 '횡보 셀에 손실 집중'을 예측했으나 **반전형 눌림목 매수라
    추세가 죽은 구간에서 더 번다**(cap_score 역효과와 같은 기전). 단조(B)는 만족하나 **어느 분위도
    음수가 아니라 C 탈락 — 걸러낼 구간이 없다.** volpct/alt_breadth 도 비단조로 기각.
    · **생존 1종 = beta_slope**(횡단면 베타 팩터 수익률, 사용자 제안 5번). 하위 −0.80% → 상위
      +3.67%, 스프레드 +4.48%p. **단 현행 avg_cap 이 −4.73%p 로 더 강하다.** 두 축은 부호가 반대인데
      둘 다 알트 강세 계열 — **상충인지 상보인지(상관) 확인이 2단계의 첫 물음**이고 그 전엔 arm 미제작.
    · **사용자 제안 β⁺−β⁻ 는 이미 시험됨** — relative_strength.compute_capture 의 cap_score 와 같은
      정보. 2026-07-08 종목 필터 기각·시장평균(avg_cap) 채택되어 실거래에 이미 돈다. 제안 3번은
      up_capture 분자와 동일, 1번(롤링 베타)은 RS 와 상관 높고 RS 는 레짐 통제 후 소멸.
  · **4파 삼각수렴 비권장 (표본 없음)**: triangle_census 36셀 중 **n>=20 은 4셀뿐**(전부 1d·터치4·
    zz<=0.05, 최대 48건 = 80종목 5년 전체). **4h·1h 전 셀 미달**(최대 9건). **터치 4→5 에서 48→2건
    (−96%)**, zigzag ±40% 에 2.7배 차이(48/38/18) — zz 0.07 은 n=18 이라 '세 임계값 동시 통과'
    요건 자체가 적용 불가. 환원형(bb_squeeze/nr7/breakout_retest 4h·1h/equal_highs·lows_4h)이 이미
    6번 기각. 진입 A(하단선 터치)는 봉 내 사건이라 시장가 엔진에서 실행 불가. 재검토 조건:
    1d 이력 2배 누적 후 터치4·zz0.05 셀 n>=60.
  · **펀딩비 적재 시작** — 시험이 아니라 데이터 확보. OKX 이력 94일뿐이라 '펀딩 극단 청산'은 지금
    시험 불가. funding_accrual.py 가 매 느린틱 Supabase 업서트(매매 무관, try/except, 테이블 없으면
    스킵). **사용자가 supabase_schema_funding.sql 실행해야 쌓인다.** OI 는 수집 코드 자체가 없음.
  · method_x.py / regime_axis.py / triangle_census.py / test_method_x(38) / test_regime_axis(28) /
    funding_accrual.py / exit_regime_axis.yml / triangle_census.yml
- **triple_bottom 1w 지각 진입(L3+3봉) 사전 등록 (2026-09-05 저녁, 사용자 지시)**: 9/3 룩어헤드 점검에서 엣지 전부였던
  'L3 미확정 돌파 38건(평균 약 +20%)'을 실거래가 처음 알 수 있는 봉(L3+3, 스윙 저점 확정 봉)에서 뒤늦게 진입하는 인과 규칙.
  `detector_triple_bottom.detect(mode="late")` — 미확정 돌파 셋업만, 신호=L3+3, 그 봉 종가>넥라인. **기본 mode="breakout" 은
  종전과 바이트 단위로 동일**(test_late_entry 가 detail 일치·인과성·시나리오로 고정, 스케줄러는 mode 를 넘기지 않음).
  기준(사전 등록, validate_late_entry.py 상단): 1단계 동결 라벨 게이트 v2(k=n 베이스라인) → 2단계 실거래 프레임 C1(코호트 all =
  1w 스케줄러 범위, 방식D) · C2 holdout 365일 n≥10 & mean>0(n<10 은 INCONCLUSIVE) · C3 자산곡선 Calmar>0. **판정은 late 한 arm 만**,
  late_nohold/causal/early_ceiling/union_live 는 진단. PASSED 면 자율 반영(adopted 1w 항목 mode=late). late_entry.yml.
  · **결과 INCONCLUSIVE (run 33966797748)**: 1단계 동결 라벨 **PASSED**(n=30 +12.42% med +13.74% 승률 67% bp .004 OOS 2/4).
    감쇠: 돌파봉 +15.7% → L3+3(≈돌파+1주) +12.4% — 지각 비용은 작다. 그러나 **2단계 방식D 에서 30건 중 23건이 −8% 손절**
    (승률 20%, med −8.20%, bp .298) → C1 탈락, holdout n=1 로 규칙상 INCONCLUSIVE. **죽이는 건 지연이 아니라 청산 규칙** —
    방식D(−8% 저가 손절)는 1d 검증 규칙이고 주봉 저가 폭엔 맞지 않는다(보류 항목 '방식D 를 1d 외 TF 에서 검증'의 실증).
    실거래 반영 없음. 후속(사용자 결정): 1w 전용 청산 사전 등록. **부수 발견**: validate_confirm_bar 의 boot 베이스라인이
    k=30 으로 남아 있었다(routing_gate 수정 누락) → k=n 으로 고침. k=n 이면 causal 1w 도 1단계 통과(bp .038, 종전 .133)이나
    방식D 에서는 승률 13% 로 기각. **하모닉 6셀 k=n 재실행(run 33967559035)도 전부 REJECTED**(bp .20~.71, 평균 −0.5~+0.7% —
    베이스라인 탓이 아니라 엣지 부재). 복귀 후보 없음, 정지 유지.
- **triple_bottom 1w 전용 청산 사전 등록 (2026-09-06, 사용자 지시 "돌려줘")**: 지각 진입 시험이 '청산 규칙이 문제'를
  가리켜 라벨 일치 청산을 시험. 주 판정 셀 (late, A_label) — A_label = 종가 ±10%/20주(= eval_A) + 거래소 재해용 손절
  −20%(저가). 진단 arm: A_notarget/S_base(세 바닥 최저가)/N_neck(넥라인)/D_close(D 손절만 종가)/D. 기준 C1(k=n 같은 청산
  규칙 풀)·C2 holdout **730일**(주봉 희소성, 사전 결정) n≥10·C3 자산곡선. **PASSED 여도 자율 반영 안 함** — 실거래 청산
  변경은 사용자 보고 후 적용(eval_A 를 실주문 청산에 쓰는 경로 + 재해 손절 주문은 신규 코드). validate_exit_1w.py / exit_1w.yml.
  · **결과 REJECTED (run 33986204668)**: (late, A_label) n=30 **+11.39% 승률 63% bp .004**, holdout(2년) n=22 +15.5%, Calmar 0.20
    — C2·C3 통과인데 **OOS 1/4** 로 C1 탈락. 연도별 2022 −16.7%(n1) / 2023 −5.2%(n5) / **2024 +18.6%(n22)** / 2025 −12.7%(n2):
    30건 중 22건·수익 전부가 2024 한 해 → 사용자 원칙 '단일 해 의존 셀은 켜지 않는다'. 같은 신호에서 D 대비 +9.47%p(t 2.82).
    **부수 발견**: 익절을 빼면(A_notarget/S_base/N_neck) 23~27/30 이 −20% 재해 손절 — 삼중바닥 돌파의 엣지는 '돌파 직후 +10% 한 번'이고
    그 뒤 대부분 무너진다. D_close(손절만 종가 판정)가 D 대비 +4.3%p(t 2.3) — 저가 판정이 주봉을 과도하게 털어낸다는 독립 증거.
    causal 은 A_label 로도 +2.2%/holdout −1.3% 기각. **등재 정지 유지, 청산 변경 없음, 2024 외 표본 누적 전 재시험 무가치.**
  · **사용자 질문 "1h 빼고 전부 D 인데 진입 검증 프레임에 맞게 다 검증해야 하지 않나"** → 맞다. 방식D 로 실거래 프레임
    확인을 거친 것은 engulfing/fvg(method_d) 와 9/5 배포 4h 3종(revival C1~C3 가 방식D) 뿐. **inverted_hammer/marubozu(1d)·
    three_soldiers_4h 는 ±10%/20봉 라벨로만 통과하고 D 로 실거래 중** — validate_exit_consistency.py 로 D vs 라벨 일치 청산을
    짝지음·실거래 프레임에서 비교. 판정 규칙 사전 등록: D_OK→유지 / ¬D∧A∧짝지음 우위(t>2)→청산 전환 후보 / ¬D∧¬A→패턴
    재판정 후보 — 전부 사용자 결정, 자율 반영 없음. 참고로 4h 신규 3종도 같은 표에(판정 아님). exit_consistency.yml.
    · **결과 (run 33985949280) — 판정 3종 전부 PATTERN_REJUDGE_CANDIDATE, 실거래 변경 없음(사용자 결정 대기)**:
      inverted_hammer D n=104 **−0.63% 승률 33% bp .69** / A_label +0.79% bp .18 — 두 청산 모두 무작위와 구분 안 됨(가장 약한 배포 패턴).
      marubozu 메이저 5년 **n=19** — D +9.88%(손절 11/19, 복권형) / A −1.59% — 표본이 판정 불가 수준. three_soldiers_4h(bull 만, 레짐
      정합 k=n 풀) D **+2.27% bp .003 Calmar 3.99 C1·C3 통과**, **holdout(2025-09~, bear 해) n=28 −1.48% 하나로 탈락**, A_label 은 bp .057
      로 D 보다 나쁨(−1.44%p t −1.88) → 정지보다 관찰 권고. **참고 4h 3종은 전부 D_OK 이고 A_label 이 D 보다 나쁨**(t −2.0~−2.8) —
      라벨 일치 청산이 항상 옳은 게 아니다. 1w 는 주봉 저가 폭 때문에 D 가 무너진 특수 사례. 청산 규칙은 전 패턴 D 유지가 맞다.
    · **사용자 결정 (2026-09-06) — 세 패턴 다 유지, 1개월 실거래 관찰**: "그냥 유지해주고 1달 정도 실거래로 관찰해보자".
      정지하지 않는다(실거래·코드 변경 없음). 근거: ih 는 무작위와 구분 불가라는 것이 **엣지 부재의 증거이지 손실의 증거는
      아니고**, marubozu 는 n=19 로 판정 자체가 불가능하다 — 백테스트 표본이 답을 못 주므로 실거래 표본으로 본다.
      **관찰 종료 2026-10-06**: ih/marubozu 실거래 진입 건수·건당 수익·손절 비율을 표로 보고하고 정지/유지 재결정.
      three_soldiers_4h 도 같은 취급(원 프레임 근거 불변, holdout 이 bear 단일 해라 판정 보류).
- **장기 이평 돌파 슈팅 스터디 (2026-09-06, 사용자 지시)**: study_ma_breakout.py — 일봉 MA180/200/250 상향 돌파(직전 20봉 이상
  아래였던 fresh 교차, 진입=돌파봉 종가) 뒤 전방 수익·**슈팅률(MFE ≥20/30/50%)**·MAE·재하향·라벨 게이트·방식D 를 무작위 진입
  베이스라인과 비교. 필터 셀 raw/decisive/volume/slope/deep/rebreak, 레짐·연도·코호트·메이저 분해. **탐색적 분석 — 배포 판정 아님**,
  진입 후보로 쓰려면 별도 사전 등록. ma_breakout.yml.
  · **결과 (run 33988287687)**: 무작위 진입 40일 내 +20% 도달 44.5% / +30% 31% / +50% 17% 인데 **MA180 첫 돌파(20일 이상 아래→위)
    n=438 은 57/44/27%**, MFE40 중앙 +25% vs +17%, +20d +8.3%(승률 47%). 라벨 +2.74% bp .000 OOS 3/4 PASSED, decisive(≥MA×1.02)
    n=250 라벨 +4.19% med +10% 승률 56% OOS 4/4. MA200 유사, **MA250 은 라벨 탈락**(MAE 커서 손절 선행), **재돌파(rebreak) 는 무작위보다
    나쁨**. **레짐 결정적**: bull_btc n=211 +20d +18.1% 슈팅 65/56/38% / bear 종가 음수 / bull_altseason 전부 음수. **연도 편중**: 2023·2024
    가 전부, 2025·2026 음수. MAE 중앙 −19%, 20일 내 MA 재하향 73% — 크게 튀고 크게 흔들리는 셋업. 진입 후보 사전 등록 시
    bull_btc 레짐 셀만 가망, holdout(2025-09~)이 음수 해라 통과 가능성 낮음. 실거래 변경 없음.
- **MA180 돌파 진입 후보 사전 등록 — 기록용 (2026-09-06, 사용자 지시 "MA180 사전 등록은 기록용 진행해줘")**:
  위 스터디의 이벤트를 실거래 디텍터로 옮겨(`detector_ma180_breakout`, study 와 신호 집합 동일함을 테스트로 고정)
  실거래 프레임에서 잰다. **주 판정 셀은 (ma180_decisive, bull_btc, top30) 롱 하나** — 진입 = MA180 fresh 돌파봉
  (직전 20봉 이상 아래) 종가이고 종가 ≥ MA×1.02, 청산은 방식D.
  · **기록용 — 통과해도 실거래 반영 없음**(`DEPLOY_ON_PASS=False`). 자율 반영 조항의 명시적 예외로 사용자가 지정.
    통과 시 registry `passed_not_deployed` 로 남기고 배포는 사용자 결정. universe/scheduler 미등재를 테스트가 고정.
  · 기준: C1 게이트 v2(같은 레짐·코호트 k=n 베이스라인·같은 청산) · C2 holdout 365일 n≥10 & mean>0 ·
    **C2b train 자체 게이트 통과 AND train n ≥ holdout n/2** · C3 자산곡선 CAGR>0 & Calmar>0.
  · **C2b 는 2026-09-05 에 기록한 설계 결함의 첫 적용** — vwap_rev_short_4h 가 표본 92%를 holdout 에 두고 C2 를
    통과했던 구멍을 막는다('다음 설계부터' 항목 소진).
  · 진단 셀(판정 아님): ma180_decisive|ALL · ma180_raw|bull_btc·ALL · ma200_decisive|bull_btc · all 코호트.
    **사후에 이 중에서 골라 살았다고 하지 않는다**(validate_ih_exit 교훈).
  · 사전 기대: holdout 이 2025-09~2026-09 bear 지배라 C2 탈락 가능성이 높다고 실행 전에 기록.
  · **결과 REJECTED (run 34013456038)** — 주 셀 n=44 **+10.57%** med −6.64% 승률 41% 엣지 **+8.42%p** bp .022 OOS 3/4,
    C1·C2b(train n=38)·C3(CAGR +24.1% MDD −8.5% **Calmar 2.85**) 전부 통과인데 **C2 holdout 하나로 탈락 — n=6, 6건 전부 −8% 손절.**
    지난 1년에 bull_btc 국면이 거의 없어 신호가 6건뿐이라 '판정 불가'에 가깝지만, 사전 등록 규칙상 n<10·mean<0 둘 다 탈락 사유다.
    연도별 train 은 일관 양수(2023 +9.9 / 2024 +23.4 / 2025 +0.2). **진단 5셀도 전부 C2 에서 탈락** — ma180_raw|bull_btc|top30 이
    train 최강(n=79 +9.60% med −0.78% 승률 48% OOS 4/4 Calmar 4.47)이나 holdout 은 같은 6건 −8.20%. 사후 선택하지 않는다.
  · **주의**: 게이트를 통과한 train 셀도 **top5 기여 69% · 절사평균 +2.35%**(평균 +10.57%) 로 복권형이다 — 스터디의
    MAE 중앙 −19% · 20일 내 MA 재하향 73% 와 같은 성질. 재시험은 bull_btc 국면이 누적돼 holdout n≥10 이 될 때.
    실거래 변경 없음, 복귀 후보 없음.
    detector_ma180_breakout.py / validate_ma180.py / test_ma180.py(33건) / ma180.yml
- **확인 프레임 v3 — 국면 기준 홀드아웃 + 장기 이력 (2026-09-06, 사용자 지시 "1~3번 전부 진행 / 홀드아웃에서만 탈락한 것 전부 다시 검증")**:
  사용자 지적 — "지난 1년은 최악의 하락기였는데 홀드아웃을 거기서 하니 통과를 못 한다. 방향성이 중요하다. 4년 주기로 더 공정하게,
  데이터가 모자라면 끌어와서." v2 홀드아웃(달력 마지막 365일)은 레짐 조건부 셀에서 그 1년의 국면이 결과를 먼저 정한다 —
  MA180 bull_btc 셀이 정확히 그 사례(신호 6건 전부 손절 → '판정 불가'가 REJECTED 로 기록).
  · **frame_v3.py (동결)**: 에피소드 = 레짐 연속 구간(30일 이하 끊김 병합, ALL 은 달력 연도) · 홀드아웃 = **셀 레짐으로 라벨된 날 중
    가장 최근 365일**(달력상 비연속; ALL 은 종전 달력 365일) · **E 에피소드 OOS** = 적격(n≥5) 에피소드 ≥2, 양수 ≥2 이며 과반
    (v2 G5 4분위 대체) · COV = 적격 에피소드 ≥2 & holdout n≥10 & train n≥20. **판정 우선순위**: 성능(mean/승률/boot_p/holdout
    mean/train/C3) 실패 → REJECTED / 성능 통과·COV 실패 → **INCONCLUSIVE**(기각 아님) / E 실패 → REJECTED / 전부 → CONFIRMED.
    4년 주기는 예측 가정이 아니라 커버리지 요건(독립 국면 ≥2)으로만 쓴다.
  · **장기 데이터 data_long/ (2017~, 1d 만)**: 러너에서 okx/coinbaseexchange/kucoin/gate/htx… 순으로 probe 해 종목별 가장 이른
    소스를 gzip CSV 로 브랜치 data-long 에 커밋(build_data_long.py). `detlib.load_ohlcv_long` 이 OKX 첫 봉 이전만 장기 소스로 채움
    (겹치면 OKX). `regime_switch.build_regime_map(rows_by=)` 로 장기 라벨(365일 밖은 종전과 같은 프록시). 스케줄러 무관.
    **한계**: 생존 편향 · 현물/무기한 혼합 · 4h/1h 는 장기 이력 없음(그 셀은 기존 범위에서 v3 → 에피소드 부족이면 INCONCLUSIVE).
    1차 수집(run 34015653158)은 probe 결함으로 kraken 720봉뿐 → 폐기·재실행.
  · **적용 범위**: 프레임 변경은 후보 전체(게이트 v2 전환 원칙) — validate_revival 전 후보+신규 4종 / validate_ma180 /
    validate_exit_consistency(three_soldiers_4h D arm 병기). `--frame v3 --long`. v2 수치도 나란히 찍어 어느 셀이 홀드아웃 설계로
    뒤집혔는지 보고한다. test_frame_v3.py(33건).
  · **결과 (2026-09-06, revival run 34019730685 / ma180 34019731790)**: 34셀 v3 **CONFIRMED 6 / INCONCLUSIVE 8 / REJECTED 20**
    (v2 CONFIRMED 5). **v2 홀드아웃 탈락 → v3 CONFIRMED 3셀**:
    · **double_bottom_1d · bull_btc · top30** — n=1028 +7.29% 승률 38% top5 13% 엣지 +4.05%p bp .000 OOS 4/4, **E 8/12**(2017·2018·
      2020×2·2021×3·2023-24·2024-25 양수 / 2019×2·2021-22·2025-08~11 음수), 국면 홀드아웃 n=365 **+7.78%**, Calmar 1.78.
      v2 는 holdout n=42 −7.96% 로 탈락했었다. **유일한 다중 사이클 확인 셀** — 배포는 사용자 결정(현 레짐 bull_altseason 이라 즉시 발화 없음).
    · vol_awakening_4h · bull_btc (Calmar **0.08**) / breakout_retest_4h · bull_btc (Calmar **0.30**, MDD −62%) — 경계값, 4h 라 2023~ 두
      에피소드뿐. 비권고. breakout_retest ALL 은 v3 도 holdout −0.48% 탈락.
    · **홀드아웃 문제는 풀렸지만 다른 데서 걸린 셀**: triple_bottom_1d|bull_btc holdout +21% 인데 승률 30%(복권형) / inverse_hs_1d|bull_btc
      holdout +5.1% E 8/10 인데 bp .088(bull 무작위 +3.3% 를 못 이김) / three_soldiers_4h|bull_btc top30 holdout +4.95% E 3/3 인데 train n=37
      bp .39 / **ma180 holdout n=30 +13.05% 인데 train n=29 bp .066**. 4셀 다 C2b·분포·boot_p 로 REJECTED.
    · **INCONCLUSIVE 8**: 4h bear 3셀(equal_lows/vwap_rev_short/vol_awakening — 4h bear 에피소드 2개, 국면 홀드아웃이 전부 삼켜 train 0.
      즉 v2 의 bear CONFIRMED 는 단일 bear 에피소드(2025-11~) 위였다; equal_lows 는 ALL 배포라 ALL 셀 E 3/4 가 근거) + 1h 5셀(365일뿐).
    · 신규 4종 20셀 v3 도 전부 REJECTED. exit_consistency: three_soldiers_4h(all·BULL) 국면 홀드아웃 n=92 **−0.42%** REJECTED — 하락기 탓 아님.
    · **주의**: 2017~22 에피소드는 '오늘의 top30 중 당시 존재한 종목'(생존 편향). C2b 가 검정력 부족(n≈30·bp .06~.10)을 기각으로
      분류하는 건 설계 메모(사후 변경 안 함). 실거래 변경 없음.
- **bull_btc 국면 위치 진단 — 진단 전용 (2026-09-06, 사용자 사양 9항목)**: 핵심 질문 "bull_btc 하나의 레짐 안에서 시간이 지나며 패턴
  엣지가 체계적으로 감소하는가"(→ bull_early/late/reentry 시간축 레짐 근거) vs "BTC 강한 달 = 패턴 강한 달"(→ 새 레짐 불필요).
  **엣지 = 패턴 − 같은 조건(같은 달/버킷/코호트/청산D) 무작위 진입.** 월별(2023-01~) 전수 + 경과개월 0-2/3-5/6-8/9-11/12+ ·
  재점등(직전 bull 종료 6개월 이내) · BTC 1년 고점 낙폭 0/−10/−20% 고정 버킷 · bull 월의 BTC fwd 3m/6m(국면 품질) · ETH/BTC·알트
  바스켓 상대수익(TOTAL3 없음). 7패턴(우선 double_bottom/MA180/inverse_hs/three_soldiers + triple_bottom/engulfing/fvg).
  **버킷 사후 변경 금지·필터 실거래 적용 없음·결과 전 제외/채택 없음.** 판정은 {패턴/BTC 레짐/알트 레짐/표본 부족} 중 증거와 함께.
  (앞서 내가 짠 90/270일 버킷+필터 arm 판 validate_phase 는 실행 전 취소·삭제 — 버킷이 달라 두 판을 같이 보면 사후 선택이 된다.)
  diag_bull_phase.py / test_diag_bull_phase.py(17) / diag_bull_phase.yml
  · **결과 (run 34024883650)**: **시간축 감소 가설 기각.** 경과개월별 엣지(패턴−같은 버킷 무작위)는 비단조이고 12m+ 가 오히려 최강
    (double_bottom +5.96 t2.7 / fvg +6.59 / inverse_hs +8.00 / three_soldiers +2.99; 무작위는 12m+ +0.68%). **재점등 가설도 기각** —
    재점등 엣지가 신규보다 높은 패턴 5/7. 2025-08~11 붕괴는 패턴 −8.2% 인데 같은 달 무작위도 −8% → 엣지 ≈ −0.1%: **라벨이 bull 을
    잘못 가리킨 구간**(BTC fwd3m −22%). 엣지는 BTC 가 1년 고점 0~−10% 안일 때 집중, −10~−20% 조정 구간에선 ≈0. ρ(패턴평균,BTC월)
    0.5~0.7 / ρ(엣지,BTC월) ≈0.
    · **더 엄격한 월 대조(같은 달 무작위)에서 2023~25 1d 반전 패턴의 패턴 고유 엣지 ≈0 또는 음수**: double_bottom **−0.93%**(n=762,
      양수 달 8/32) / fvg −0.32% / inverse_hs **−5.01%** / three_soldiers_4h **+2.18%**(유일 양수) / ma180·engulfing·triple_bottom 표본 부족.
      버킷 대조 +4~9%(t2~4.6)와의 차이 = 신호가 강한 달(2023-10·2024-02·2024-11)에 2~3배 몰린 효과 — 시장 수준의 '하락 뒤 반등 매수'
      타이밍이지 진입일 선택 엣지가 아닐 수 있다.
    · **판정: BTC 레짐(라벨 품질) 1차 + 1d 반전 패턴은 월 대조에서 패턴 문제.** 알트 레짐 증거 없음. 시간축 레짐(bull_early/late/reentry)
      신설 근거 없음. **double_bottom_1d 배포 권고 철회(보류).** 후속: 확인 프레임에 '같은 달/20일 창 무작위 대조' 가드 사전 등록.
    · **사용자 검토·결정 (2026-09-06)**: 보수적 조치(시간축 레짐 안 함·double_bottom 보류·같은 달 대조 추가 검증) 타당. **정정 4건** —
      ① 진단의 월 대조는 동일 코인·월중 위치·중복/재진입 규칙을 안 맞췄다(신호가 월초/말·변동성 이벤트에 몰리면 진짜 시간 선택 능력까지
      빼버림) ② −0.93%(n=762)는 거래 단위, 실질 표본은 월 32개 — 월/코인-월 클러스터 부트스트랩으로 CI 재산출 필요 ③ '라벨 품질 문제'는
      1차 가설 수준 — 레짐은 예측기가 아니라 조건부 기대값 라우터일 수 있음(bull 안 무작위 장기 부호·비-bull 대비·fwd3m 분리·OOS 유지 비교
      필요) ④ 월 대조를 결과 본 뒤 v3 기준으로 교체하면 사후 선택 — 다음 프레임은 사전 등록. three_soldiers '유일 생존' 선언 철회(다중검정).
      **결정**: 시간축 레짐 신설 안 함 / double_bottom·inverse_hs 통과 판단 철회 → 미확인·그림자 / fvg·engulfing·three_soldiers 주문 무변경,
      동일 코인·동일 월·동일 실행조건 대조 포함 재검증 대상 / BTC 레짐 유지 / **v4 가드는 매칭 규칙·클러스터 추론·OOS 분할·통과/보류 기준을
      먼저 고정**(registry guard_v4_prereg_draft — 2026-09-06 사용자 확정 → 아래 v4 항목).
- **확인 프레임 v4 — 3중 대조 가드 실행 (2026-09-06, 사용자 확정 파라미터, run 34030352467)**: validate_guard_v4.py / test_guard_v4.py(41) /
  guard_v4.yml / registry `guard_v4_prereg_draft_2026_09_06.result_2026_09_06`. **CONFIRMED 0 / UNCONFIRMED_SHADOW 6 / REJECTED 5. 실거래 무변경.**
  · **고정(결과 전)**: A 레짐·코호트 무작위 k=n / B 같은 코인·같은 달·**같은 레짐 라벨**·같은 TF·방향·진입가능봉(신호봉 제외, 풀<5 제외) /
    C train<2025-01-01≤OOS. train = 적격성(A 게이트 v2 + B 월클러스터 p<.05·세 가중>0), OOS = 재현(A mean>0·승률≥35%·bp<.05 + B 세 가중>0·
    **Holm** p<.05·엣지≥+0.20%p + 왕복 0.4% 에서 mean>0). 월 클러스터 블록 부트 1000(코인-월 병기). REJECTED 는 전체 A mean≤0·승률<35% 만.
    주 셀 11 = 실거래 라우팅 복제 7(engulfing bull/bear 롱·altseason 숏, fvg bull/altseason 롱, three_soldiers bull/altseason) + 관찰 2(ih/marubozu) +
    그림자 2(double_bottom_1d/inverse_hs_1d bull_btc). DEPLOY_ON_PASS=False.
  · **핵심 결과 — B 는 1d 반전 패턴에서 train·OOS 모두 강한 음수**: fvg|bull_btc train −6.92%p(p 1.000, CI [−9.5,−4.1]) / OOS −3.21%p,
    double_bottom −4.29/−2.22, inverse_hs −6.43/−2.19, fvg altseason −3.58/−8.68. A 엣지(+4~+6.6%p, bp .000)와 정반대. ±10봉 창(D3)도 동일.
    **해석**: A 엣지는 '어느 코인-월에 있느냐'(코인-월 선택)에서 나오고, 그 코인-월 **안의** 진입일은 무작위보다 나쁘다(갭·돌파 뒤 추격).
    단 B 벤치는 신호 이후 봉까지 포함해 '그 달이 좋은 달'이라는 정보를 쓴다(사후 조건화) — B 음수 ≠ 실거래 손실. B 는 월 안 타이밍 검정.
  · **OOS(2025~) 절대 성능**: engulfing|bull_btc n34 **+7.0%**(edge +8.76 bp .004, 0.4% 비용에도 +6.8%) / engulfing_short|altseason n40 +1.14%
    (bp .011, **B +4.40% Holm .000 — 유일한 OOS B 통과**, 그러나 train A bp .449·B −0.63% 로 미적격 → SHADOW) / fvg bull −0.33% / three_soldiers bull
    −0.06% / double_bottom −0.17% / inverse_hs +2.00%(bp .051) / ih +0.40% / marubozu n8. engulfing|bull_btc 는 train 게이트가 bp .368 로 실패(n75).
  · **REJECTED 5 중 실거래 라우팅 셀 3**: **engulfing|bear 롱**(전체 승률 24%, OOS n33 −3.65% 손절 28/33 승률 15%) · **fvg|bull_altseason 롱**
    (승률 26%, OOS n82 −0.78%) · **three_soldiers_4h|bull_altseason**(n35, mean −1.29%, OOS −3.17%). 나머지 2 는 관찰 셀 ih(승률 30%)·marubozu
    (승률 28%, OOS n8). 라우팅 표는 2026-06-24 n≥20·mean>0 만으로 만들어져 게이트를 거친 적이 없다 — **변경은 사용자 결정(주문 무변경)**.
  · **D1 레짐 = 조건부 기대값 라우터?**: bull_btc 월 top30 롱 무작위 train +5.24%(p .005, 양수월 53%) vs 비-bull +2.19% → train 에선 작동.
    OOS −1.70%(p .767) vs 비-bull −0.18% → 2025~ 역전. **D2** BTC fwd3m 은 OOS 에서도 bull +2.3%(양수 58%) vs bear −9.4%(24%) 로 분리 —
    라벨은 BTC 방향은 가르지만 **알트 롱 수익은 못 가른다**(bull_btc = BTC 주도 국면, 알트 지체). sideways 라벨 일수 0(라벨러가 사실상 안 냄).
  · D4 실거래 행 4건(패턴당 1) — 표본 없음. 그림자 2 셀 유지, 관찰 2 셀 10/06 까지 유지.
- **상승 에피소드 승자 프로필 + 신호봉 승자 프로필 (2026-09-07, 사용자 지시 "2021 불장에서 많이 오른 코인은 시작 시점에 뭐가 달랐나, 전체 코인으로" + 승인 "신호봉 시험 사전 등록해서 돌려줘")**:
  registry `episode_profile_prereg_2026_09_07`(run 34090039511) / `signal_profile_prereg_2026_09_07`(run 34089345934). **실거래 무변경.**
  · **데이터 확장**: build_data_long `--okx-all` 6샤드 병렬(run 34088487916) → data-long 브랜치 **248코인**(OKX 무기한 456 중 이력 소스 있는 것,
    2021 이전 시작 73). master 의 data_long/ 은 81 그대로 — 연구 워크플로가 data-long 브랜치를 체크아웃. build_data_long.yml 은 dispatch 전용.
  · **에피소드 프로필**: 레짐 bull_btc∪bull_altseason 연속 구간(≥60일) 5개, 시작 시점 35 변수(24 + 볼밴 %B·폭·수축/ADX/ATH 낙폭·경과/이력/BTC 상관/
    1년 최대낙폭/양봉비율/MA180 연속일) vs 에피소드 수익. 에피소드 내 순열 p·Holm·일관성 75%. **PROFILE 5 / EPISODE_DEPENDENT 2 / NONE 28 / REVERSED 1.**
    · **핵심 발견 — 레짐 bull_btc ≠ 알트 불장.** 코인 상승 비율: 2019 9% / **2021 98%**(중앙 +318%) / 2023-24 48%(중앙 −4%, BTC +185%) / 2024-25 **16%**
      (388일 bull 라벨, 중앙 −54%, BTC +27%). 알트가 실제로 오른 에피소드는 2021 하나.
    · PROFILE = beta_btc_60(−, 4/4) · max_dd_1y(+) · ret_1w(+) · rvol20(−) · age_bars(+) — **'알트가 안 오른 3 에피소드에서 누가 덜 떨어졌나'의 방어적
      프로필**. 유일한 알트 불장 2021 에서는 **부호가 반대**(rvol20 +0.32, age −0.43: 젊고 변동성 크고 볼밴 확장 중·ADX 높은 코인이 이김). 알트 불장
      표본이 1개라 '올랐을 때의 공통점'은 통계로 못 세운다 — 다음 알트 불장이 전향 시험. 생존 편향 큼(2021 n=42 = 당시 상장+현재 OKX 교집합).
    · REVERSED vol_ratio_30_90: 세 연구 모두 '최근 거래대금 증가 → 이후 나쁨'.
  · **알트 폭 '상태' 시험 — 판정 NONE, H2 는 정반대 (2026-09-07, 사용자 지시 "폭을 일별로 기록해서 50% 이상 며칠째 유지되면
    넓은 폭을 예상한다든가", run 34097499748)**: registry `breadth_state_prereg_2026_09_07`. 관측 단위를 에피소드에서 **하루**로 바꿔
    (며칠째 · 몇 % · 몇 개) → 이후 60봉 횡단면. 사용자 지적 "3.5년에 한 번 오는 불장을 기록용으로 날릴 수 없다"에 대한 프레임 교체.
    · **H1 기각(비단조)**: 임계 50% 에서 코인 중앙 fwd60 이 1-10일 −7.4% / 11-30일 −0.6% / 31-60일 **+12.9%** / 61-120일 **+14.3%** /
      **121+일 −17.3%**(양수 코인 31%). 오래 유지될수록 좋은 게 아니라 **너무 오래면 늦은 것**. 폭 수준도 60-70% 에서 +24.6% 최고,
      85-100% 는 −1.8% — 가장 넓을 때가 가장 좋은 게 아니다.
    · **H2 기각, 부호 정반대**: ic_broad 가 4 임계 × 5 버킷 **20셀 전부 음수**(−0.05~−0.26), ic_def 는 20셀 전부 양수(+0.11~+0.26).
      폭이 며칠째 유지되든 60봉 창에서는 **방어 프로필이 이긴다**. '폭 지속 → 공격형 전환' 규칙의 근거는 없다.
    · **에피소드 판과의 화해**: 그 판의 '젊고·작고·고변동 승자'는 **첫날 진입해 끝(최대 404일)까지 보유**했을 때의 이야기다. 구간 안
      임의의 날에서 60일을 보면 그 프로필은 진다 — 대박이 특정 시점에 몰린 복권 구조(xsec_chars 의 'rvol20 은 순위 예측이지
      평균수익이 아니다'와 같은 성질). 표본은 작지만(버킷당 29~62 관측일, 블록 약 30) 부호가 20셀 전부 일치.
    · 현재 상태: 2026-09-07 폭 44.4%(225개 중 100개) · 런 미시작 · 20일 기울기 +33.5%p.
  · **[사전 등록 시험 2026-09-08, run 34170599619] 재구성 주기 — 유니버스 고정 판. 판정 MECHANISM_NOT_SELECTION**:
    registry `cadence_prereg_2026_09_07`. basket 민감도의 '월 재구성 압도'가 주기 때문인지 **신규 상장 접근** 때문인지 가른다.
    창 전체를 관통하는 고정 집합(W1 31 코인 · W2 71)에서 모든 주기 arm 이 같은 후보에서 고르게 하고, 재구성이 하는 일 셋을
    분해했다 — 종목 재선택 / 자본 재균등화 / **띠 규칙 진입가 앵커 리셋**.
    · **J1 통과 — 월 우위는 교란이 아니었다**(사전 확률과 다름). W1 N=20 monthly **1.01** vs none **0.34**, N 격자 3/3 동부호.
      W2 도 0.12 vs 0.02 (J4 통과).
    · **J2·J3 실패 — 종목 선택은 오히려 해가 된다.** 무작위선택 200회 중앙 1.19·95백분위 1.54 인데 거래대금 상위 선택은
      **14백분위**. 분해: none 0.34 → **anchor 1.09(앵커 리셋 +0.75)** → reweight 1.21(재균등화 +0.11) → reselect 1.01
      (**재선택 −0.20**). **이득의 거의 전부가 앵커 리셋이다.**
    · **기전**: 앵커를 리셋하지 않으면 손절 뒤 진입가 P 로 못 돌아온 종목이 **영원히 현금**으로 남는다. 주기적으로 P 를 그날
      종가로 다시 잡으면 낮아진 가격에 다시 걸린다. 즉 '재구성'의 실체는 종목 교체가 아니라 **띠의 재설정**이다.
    · **D4 가 이를 독립 확인** — 띠 규칙 없이 같은 주기로 재균등화만 하면 none 0.37 → weekly −0.15 / monthly 0.19 로 **전부
      더 나쁘다**. 고전적 리밸런싱 프리미엄이 아니라 띠 규칙 고유의 성질.
    · **짧을수록 좋아 보이지만 마찰이 먹는다** — anchor weekly Calmar 1.93(최종 **102x**)인데 **D5 재구성 슬리피지 0.141%만
      물려도 reselect weekly 0.56→0.19**, D1 수수료 2배에서 0.05, D2 로 주간은 연 수수료 **10.4%**. monthly 는 슬리피지
      0.141% 에서 1.01→0.88, 수수료 2배에서 0.68 로 견딘다.
    · **'월 재구성을 채택하라'가 아니다** — 주기 효과의 **출처**만 가렸다. 채택하려면 마찰을 판정에 넣은 사전 등록(현행 D5 는
      진단) + 재구성 시각을 실제 스케줄러 틱에 맞춘 실행 가능성 + 기존 패턴 시스템과의 슬롯·자본 분리가 선결.
    · **실행 전 수정 1건(공개)**: 로컬 스모크에서 W1 고정 유니버스가 18 코인이라 N=20 이 후보 전부를 골라 reselect ≡ reweight
      ≡ random 이 되고 J2·J3 가 **2e-15 부동소수 잡음**으로 통과하는 퇴화를 발견 → 판정 기준은 그대로 두고 가드 3개 추가
      (MAX_SELECT_RATIO 0.75 · Calmar 비교 EPS 1e-6 · D5). 전부 엄격해지는 방향. 스모크 수치는 결과로 쓰지 않는다.
    validate_cadence.py / test_cadence.py(37) / cadence.yml. DEPLOY_ON_PASS=False, **실거래 무변경**.
  · **[사전 등록 시험 2026-09-07, run 34133975572] 띠 규칙 바스켓 구성 — 판정 NO_SELECTION_EDGE**: registry
    `basket_prereg_2026_09_07`. band_rule 이 남긴 '어느 코인에 걸 것인가'. 주 판정 N=20·분기재구성, 무작위 200회 Calmar
    중앙 0.48 · **95백분위 0.631**. liquidity 5.65x/Calmar 0.459(백분위 40%) · lowvol 6.43x/0.494(60%) ·
    defensive 7.94x/0.554(80%) · broad 9.00x/0.522(71%) — **어느 기준도 95백분위 미달, Holm p 전부 .600**.
    사전 확률에 적어둔 그대로이고, 답은 **'거래대금 상위 N 을 쓰라'**. 네 번째 독립 프레임에서 종목 선택이 안 된다는 결론
    (xsec_chars / episode_profile / breadth_state 에 이어).
    · defensive·broad 가 liquidity 보다 Calmar 는 높지만 무작위 분포 **안**이고, 사전 등록 known_limits 에 '생존 편향이
      방어 계열을 구조적으로 유리하게 한다 → 방어가 이겨도 강한 증거가 아니다'를 결과 전에 적어뒀다. 순서를 증거로 쓰지 않는다.
    · **띠 규칙 자체의 값은 크다** — 같은 종목·기간에서 **그냥 보유 2.57x/CAGR 13.9%/MDD −90.4%/Calmar 0.15** vs
      띠 규칙 5.65x/26.9%/−58.6%/**0.459**. Calmar 약 3배, 개선의 대부분은 낙폭(−90 → −59%). band_rule 의 '약세장 보험' 성격과 일치.
    · **민감도(판정 아님, 사전 등록대로 서술만)** liquidity Calmar — none N5~N40 0.67/0.50/0.35/0.35 · quarterly 0.56/0.43/0.46/0.53 ·
      **monthly 0.67/1.01/1.05/1.15**(최종 10.4x/20.8x/32.5x/46.1x). **월 재구성이 압도적으로 보이지만 주기는 판정 대상이 아니다** —
      결과를 보고 격자 최대값을 고르는 것이 이 설계가 막으려던 과적합이고, 사전 등록에 적은 교란(재구성 arm 만 신규 상장 코인에
      접근)이 그대로 남는다. 추격하려면 유니버스를 고정한 별도 사전 등록이 필요.
    · 남은 미해결: 재진입 폴링 지연으로 '아예 못 사는' 빈도(분 단위 데이터 필요) · 스프레드·상장폐지 미반영 · 기존 패턴 시스템과의
      자본·슬롯 분리. DEPLOY_ON_PASS=False, **실거래 무변경**(관찰 기간 ~2026-10-06).
  · **[사전 등록 시험 2026-09-07, run 34103360568] 고정 띠 규칙 체결 마찰 3종 — 판정 VIABLE (3/3)**: registry
    `band_rule_prereg_2026_09_07`. **J1 지연**: 1시간 지연의 실효 슬리피지 **δ = 0.141%**, 이를 적용한 불장 바스켓이 즉시 체결의
    **98.4%**(문턱 85%) — 지연 걱정은 기우. **J2 재교차**: 1h 봉 순환 10.5회 vs 1d 5.0회로 **일봉이 절반 과소계상**은 사실이나
    결과비 **97.3%** (추가 순환이 값싼 왕복). **J3 바스켓**: 약세 2022 **0.92x vs 보유 0.25x** · 불장 **9.53x vs 보유 10.92x = 87.3%**
    (여유 2.3%p, 경계).
    · **중요 뉘앙스 — 바스켓이 중앙값보다 불장 상승분을 더 내준다**(87% vs 95%). 바스켓 평균은 최대 승자가 지배하는데 띠 규칙이
      그 승자를 더 자주 끊는다. 앞선 중앙값 수치는 실제 운용보다 낙관적이었다.
    · **출력 표 라벨 오류**: '1h 지연' 열은 실제로는 1일 지연(delay 인자가 봉 단위). 판정 J1 은 δ 적용 열을 쓰므로 영향 없음.
    · 남은 한계: δ 를 약세·횡보 구간에서 쟀다(불장에선 더 클 것) · 불장 바스켓 15종목(생존 편향) · 분 단위 재교차 미측정.
    · **'채택하라'가 아니다** — 마찰 셋만 봤고 **종목 선택 문제는 그대로 미해결**. DEPLOY_ON_PASS=False, 실거래 무변경.
  · **[체결 시험 2026-09-07]** 거래소 2개는 불필요(문제는 거래소가 아니라 주문 유효성 — 보유 중엔 가격이 P 위라 'P로 오르면 매수'
    트리거가 성립 안 함). **직전 답의 'OKX 그리드가 정석'은 철회** — 그리드는 내리면 사고 오르면 파는 정반대 구조.
    **시장가 트리거는 거의 공짜**(불장 지정가 5.04x → 시장가+0.1% 5.02x → +0.3% 4.82x). **진짜 비용은 지연** — 그날 종가로 늦으면
    넓은 불장 5.04x→**3.19x**, 대기+불장 3.10x→**1.75x**(결과의 40~46% 소실). 약세장에선 지연이 무해(어차피 재진입 안 됨).
    **유일한 미지수: 1시간 지연 비용**(현행 fast 경로 구멍). 1h 데이터 필요 — 이 하나가 성패를 가른다.
    **미해결 설계 문제**: 측정치는 코인별 중앙값인데 중앙값 코인은 살 수 없다. 종목 선택 문제로 되돌아간다.
  · **[재정정 2026-09-07] 사용자 규칙의 재진입가는 손절가가 아니라 '최초 진입가'** — 진입가 밑에서는 사지 않고 진입가로 올라왔을 때만 매수.
    띠 [P×(1−stop), P] 고정, 회당 비용 = 손절폭+수수료(결정론적). 측정(중앙): 넓은 불장 손절1% **5.04x**(보유 5.29x, 순환 7) /
    대기+불장 **3.10x**(3.22x, 11) / 약세 2022 **0.96x**(0.16x, 3) / 최근 침체 **0.94x**(0.18x, 5). **손절 1% 가 전 구간 최선** —
    회당 비용은 손절폭 그대로지만 최초 진입가로 완전 회복돼야 재진입하므로 순환이 폭발하지 않는다.
    · **인프라**: 손절은 **이미 상시**(OKX algo 주문 + ensure_stop_orders). 구멍은 재진입 — 손절 체결 후에야 매수를 걸 수 있고 주기가
      4시간(느린)/1시간(빠른)이다. 보유 중 P 지정가 매수를 미리 걸면 포지션이 2배가 되므로 불가.
      **실패 모드는 '비싸게 산다'가 아니라 '아예 못 산다'** — 손절 직후 P 위로 달아나면 영영 재진입 못 하고 상승을 통째로 놓친다.
      길은 셋: fast_scheduler 매시 사용 / 상시 리스너 / **OKX 네이티브 그리드 주문(이 전략의 정석)**.
    · **미측정 2건, 둘 다 인트라데이 필요**: 장중 재교차 빈도(일봉은 하루 1회만 셈) · 폴링 지연으로 재진입을 놓치는 빈도.
  · **[정정 2026-09-07] 위 진단의 재진입 규칙이 틀렸다** — 사용자 지적 "재진입이 왜 5% 위에서 되나, 같은 가격에 다시 진입해야지".
    손절가에 **지정가를 걸어두면 같은 가격에 체결**된다. 종가 재진입 판은 회당 비용을 4~6%p 과장했고 결론이 뒤집힌다:
    넓은 불장 손절1% **0.85x → 5.18x**(보유 5.29x), 약세 2022 0.98x → 0.95x(보유 0.16x). 갭+슬리피지 1% 스트레스에서도
    불장 4.62x / 약세 0.84x 로 개념 유지. **'1% 손절'은 손실을 1%로 묶는다는 뜻이 아니다** — 재진입 시 기준가가 손절가로
    리셋돼 손절선이 한 단계씩 내려가고 최악 체결은 −8.3%(갭)였다. 좁은 고정 손절이 아니라 '내려가는 손절 + 현금 대기'다.
    **미측정 위험: 일봉은 장중 재교차를 못 본다**(하루 1회 순환만 계산) — 손절이 좁을수록 순환·수수료가 배로 늘 수 있다.
    사전 등록 시험이 아니므로 채택 근거가 아니다(구간 임의 선택, 36셀 관찰, OOS·다중검정 통제 없음).
  · **반복 손절·재매수 진단 (2026-09-07, 사용자 질문 "내려가면 손절 올라오면 재매수 무한반복하면 수수료 외엔 손해 없지 않나")**:
    registry `whipsaw_diag_2026_09_07`. **사전 등록 시험 아님 — 즉석 계산, 판정 아님.** 규칙(−8% 손절 → 종가가 손절가 위로 오면 재매수)
    을 248 코인에 적용한 중앙값: 대기+불장(2019-06~2021-06) 규칙 **2.18x vs 보유 3.22x**(손절 7회, 규칙이 나은 코인 **6%**) /
    넓은 불장 4.50x vs 5.29x(5%) / 약세 2022 **0.71x vs 0.16x**(92%) / 최근 침체 0.71x vs 0.18x(82%).
    · **수수료만 드는 게 아니다** — 손절은 장중 저가에 걸리고 재매수는 회복된 종가에 된다. 그 틈이 **회당 약 5%**(왕복 수수료 0.2% 의 25배).
    · **전제와 반대로 작동한다** — '불장이 온다'가 맞으면 손해(코인 94%가 보유보다 나쁨), '안 온다'가 맞으면 크게 이긴다. 불장 확신을
      표현하는 도구가 아니라 확신이 틀렸을 때의 보험. 확신의 올바른 표현은 손절 없이 버틸 수 있는 크기로 보유하는 것.
    · 승률 20~30% 자체는 문제가 아니다(게이트 v2 가 35% 허용). 다만 평균이 양수임을 보여야 한다 — 레포에 승률 15%·평균 −3.65% 인
      측정 셀이 있다(v4 engulfing|bear OOS n=33, 손절 28/33).
  · **알트 폭 에피소드 재시험 (2026-09-07, 사용자 지시 "에피소드 정의를 레짐 라벨이 아니라 알트 폭으로", run 34093346604)**: registry
    `episode_profile_breadth_prereg_2026_09_07`. 에피소드 = MA180 위 코인 비율 ≥50% 연속 구간(60일+), 나머지 규칙 동일. **7 에피소드** — 폭은 레짐이
    놓친 **2023-10~2024-05 알트 불장(코인 90% 상승, 중앙 +75%)** 을 잡고 2024-25 가짜 상승을 388→74일로 줄였다. 넓은 불장은 2020-21(중앙 +578%)·
    2023-24 둘, 나머지 5개는 얕음. **PROFILE 0 / EPISODE_DEPENDENT 3 / NONE 32.**
    · **프로필 부호가 에피소드 세기에 따라 뒤집힌다**: 넓은 불장 둘에서는 고변동(+0.15/+0.18)·젊은 코인(−0.29/−0.24)·더 빠져 있던 코인(max_dd −0.23/−0.12)·
      저거래대금이 이기고, 얕은 5개에서는 전부 반대(방어적). 2021 승자는 laggards 보다 거래대금 약 7배 작고 6개월 모멘텀 −1% vs +38%(laggards 는 이미
      올라 있었음). 넓은 불장 둘은 서로 같은 부호이나 **2개라 사전 기준(≥3) 미달** — 세기는 사후에만 알 수 있어 진입 시점에 못 쓴다.
    · **전향 시험 사전 등록(부호 고정)**: 다음 폭 에피소드 종료 시 과반 상승이면 '넓은 불장 프로필'(rvol20 +, age −, max_dd −, turnover −, mom_6m −,
      bb_squeeze +), 미만이면 방어 프로필 재현 여부. 규칙 승격 없음, 실거래 무변경.
  · **신호봉 프로필**: 배포 1d 롱 4셀 신호봉 n=1,936(train 1,557/OOS 379) 35 변수 vs 방식D 수익, 월 클러스터 부트·Holm·OOS. **CANDIDATE 5**
    (rvol20 −/bb_width −/bb_squeeze −/adx14 −/corr_btc_60 +) **/ TRAIN_ONLY 8 / REVERSED 6**(mom_1m·mom_3m·ma_align·ma180_slope·ichi_tk·vol_ratio —
    반전 패턴 거래 안에선 신호봉 추세·모멘텀이 강할수록 나쁨). 손절 비율 저/중/고변동 42/58/77%.
    · **주의: 월 demean(같은 달 안) rho 는 −0.05~−0.09** 로 풀 rho(.13~.28)의 1/3 이하 — 대부분 '조용한 달이 좋은 달' 시간 효과. 슬롯 우선순위는 같은
      시점 비교라 실효 상한이 그 크기. rvol20 은 채택된 변동성 타겟팅과 같은 규칙, bb_width·adx14 는 근사 중복 — 새 정보는 '신호봉 ADX' 하나.
    · 후속 후보(사용자 결정): 라우팅 복제 프레임에서 'adx14 상위 1/3 사이징 ×0.5' 짝지음 시험. 기대 효과 작음.
  xsec_features.EXTRA / validate_episode_profile.py / test_episode_profile.py(38) / episode_profile.yml / validate_signal_profile.py / test_signal_profile.py(22) / signal_profile.yml
- **횡단면 특성 연구 — 24변수 중 저변동(rvol20) 하나만 순위 예측, 선택 규칙 승격 없음 (2026-09-07, 사용자 지시 "패턴 말고 다른 방향 … 어떤 조건에 있던 코인이 더 많이 빠르게 올랐나" + "일목·다이버전스·60/120/180선 위치 등 싹 다", run 34085937594)**:
  registry `xsec_chars_prereg_2026_09_07`. 월말 PIT liquid 유니버스(2017~, data_long)에서 상태 변수 24종의 fwd20 스피어만 IC — train(<2025-01) Holm 적격
  (연도 일관성·최고 연도 제외) → OOS 재현(IC·p·TOP 상대/절대 − 비용 0.4%). 코인 80 · 코인-월 5,267 · 114개월. **CONFIRMED 1 / REJECTED 23 / REVERSED 1. 실거래 무변경.**
  · **rvol20(−, 저변동 → 높은 순위) CONFIRMED**: train IC +0.098 ICIR 3.77 Holm .000 연도 7/7, OOS IC +0.150 p .003 TOP +1.30%p. 레짐 무관·top30 에서 더 강함.
    **그러나 순위 예측이지 평균수익이 아니다** — train 에서 저변동 TOP − 유니버스 **−0.82%p**, 저변동−고변동 스프레드 **−3.2%p**(고변동은 중앙값이 낮아도 소수 대박으로 평균이 높다).
    OOS 스프레드 +2.2%p 는 2025~26 bear 단일 국면. 40봉 내 +20% 도달률은 저변동 43% vs 50% — **'빠르게 오르는 코인'은 고변동 쪽이고 그것들이 크게 깨지기도 한다.**
    이미 채택된 변동성 타겟팅 사이징과 같은 방향의 독립 증거로만 기록. 진입·선택 규칙 승격 없음.
  · **REVERSED vol_ratio_30_90**: '거래량 각성 +' 예상이 train IC −0.051(ICIR −2.27, 연도 양수 1/7) OOS −0.022 — 최근 거래대금이 늘어난 코인이 이후 더 나쁘다. 추격하려면 별도 사전 등록.
  · **나머지 전부 무정보**: 모멘텀 5·MA60/120/180 거리·정배열·기울기 5·일목 4·RSI14·RSI 다이버전스·가격위치 2·거래대금 수준: |IC| ≤ 0.03, Holm 1.000. 사용자가 지목한 일목·다이버전스·이평 위치는
    월 단위 횡단면에서 예측 정보 없음. MA 거리·모멘텀·RSI 는 서로 ρ .7~.9(같은 정보). 근접 셀 dd_1y(p .022)·저베타(p .034, train TOP +4.87%p)는 Holm 미통과 — 사후 선택 안 함.
  · D5(사용자 원 질문 그대로, 최근 365일): n=80 전부 하락(Q1 −81%/Q4 −34%), mom_12m ρ .42·dd_1y ρ .39 — 단일 bear 해 횡단면이라 증거 아님(월 프레임 mom_12m IC .03 비유의).
  · 공개: 커밋 전 로컬 스모크 1회에서 결과를 봤고 그 뒤 rs_btc_1m 제거(횡단면에서 BTC 수익은 상수 → mom_1m 과 순위 동일) 외 무변경. 설계 메모: train 에 TOP 평균 조건을 안 걸어
    '순위 통과·평균 실패' 셀이 CONFIRMED 로 찍힌다 — 다음 프레임은 train 에도 TOP−유니버스 > 0 요구(사후 변경 안 함).
  xsec_features.py / validate_xsec_chars.py / test_xsec_chars.py(57) / xsec_chars.yml
- **레짐 라벨러 alt_side 기각 (2026-09-07, 사용자 지적 "BTC 상승일 때뿐 아니라 횡보일 때도 도미넌스가 하락하면 알트불장 아닌가", run 34082489857)**:
  registry `regime_altside_prereg_2026_09_07`. 횡보 띠 ±0.1%→**±1%**(SIDE_THR) + p=='side' 에서 alt_v>btc_v 면 bull_altseason.
  히스테리시스도 이 라벨러에서만 '횡보'를 알트불장 지지 1표로 센다(안 그러면 도미넌스 단독 하락이 2표를 못 채워 정의가 무력화).
  **1단계 ✗b / 2단계 3 arm 전부 REJECT / 채택 0. 실거래 무변경.**
  · **1단계**: 분리폭 **+1.38%**(current +0.59%) 로 (a) 통과, 지연 50.2(동률·c 통과), flips 10.6(d 통과). **(b) 연도 일관성 탈락** —
    2022 +1.5 / 2023 **−31.7** / 2024 +3.8 / 2025 −10.5 / 2026 +2.8 → 양수 3/5(60%) < 75%. 참고로 current 자신은 2/5(40%)로 더 나쁘지만
    기준은 절대값이다. 9 라벨러 전부 ✗b — 2026-09-04 실행과 같은 결론.
  · **2단계**: D_alt_side −0.222%p(t −1.34) / RL_alt_side +0.542%p(bp .088, CAGR우위 3/7, 분기승률 42%) / F_alt_side −0.555%p. 전부 REJECT.
    26 arm 중 PASS 는 RL_vote4 하나이고 1단계 미통과라 adopt 0.
  · **사용자 지적은 국소적으로 옳다** — 현행이 bear 로 부르는 날 중 도미넌스가 알트 쪽인 **12일**(bear→bull_altseason)의 유니버스 롱
    20일 선행수익 **+6.41%**, 알트바스켓−BTC **+1.23%**. 현행 bear 라벨 전체는 +0.25% / −0.92%. 방향은 맞다. **그러나 1,579일 중 0.8%**
    라 어떤 판정 지표도 움직이지 못한다. 반대로 bull_btc→bull_altseason 5일은 alt_rel −3.11% 로 틀리게 집었다.
  · **분리폭이 오른 진짜 원인은 도미넌스 규칙이 아니라 띠 확대** — 규칙 없이 띠만 넓힌 wide_side 가 거의 같은 수치(+1.03%)이고,
    두 라벨러의 차이는 17일뿐. **긴 지평에서 특히 크다**: sep40d current −2.55% → +3.38%, sep60d −1.74% → +5.62%, sep90d +3.73% → +8.41%
    (wide_side +3.42/+5.47/+8.41 로 거의 동일). 판정 지평은 20일 고정(사전 등록)이라 이 관찰은 **진단**이고, 추격하려면
    '판정 지평을 왜 바꾸는가'를 먼저 정하고 별도 사전 등록해야 한다 — 사후에 지평을 골라 통과시키지 않는다.
  · sideways 는 alt_side 에서도 8일(0.5%)뿐. 실행 전 기록한 대로 띠를 넓혀도 히스테리시스가 sideways 후보에 2표를 요구해 거의 발화하지 않는다.
  · regime_alt.py(SIDE_THR/_candidate_altside/_support_altside) / regime_quality.py(alt_rel_forward/disagreement 진단) / test_regime_quality +18건
- **PIT(point-in-time) 코호트 재검증 (2026-09-06, 사용자 의견 → 사전 등록 → run 34033988347)**: validate_pit_cohort.py / test_pit_cohort.py(25) /
  pit_cohort.yml / registry `pit_cohort_prereg_2026_09_06`. 검증 코호트(top20/top30)가 데이터 끝 순위를 과거에 소급한 정적 집합이었던 룩어헤드를
  월말 30일 거래대금 순위(다음 달 적용, 적격 60봉)로 교체해 v4 11셀을 재계산. **STABLE 10 / SHIFTED 1 — 실거래 무변경.**
  · **SHIFTED: fvg|bull_btc SHADOW→REJECTED**(PIT 승률<35%). 1d 반전 패턴은 정적 코호트가 A 엣지를 1.5~2%p 부풀렸다 — fvg +6.30→+4.71,
    double_bottom +4.02→+2.47, inverse_hs +2.49→+1.72, 코인 양수 비율 93→69% / 83→58%. '나중에 살아남은 코인'을 고른 효과.
  · engulfing 계열은 PIT 에서 같거나 강함(bull_btc OOS +6.8% bp .007, 숏 altseason B OOS +4.59% Holm .000 — mid 코호트도 통과). 단
    **engulfing|bull_btc 는 상위 3 코인 제외 시 A 엣지 ≈0**(+2.79→+0.07) — 코인 집중.
  · PIT top30 월평균 4.3 코인 교체(≈14%/월), 정적 vs 2026-09 PIT 겹침 29/30. 무조건부 코호트 스캔은 static·PIT 전부 REJECTED, mid-cap
    engulfing 은 PIT 에서 더 약함(+1.72→+0.16). 한계: 상장폐지 이력 없음(생존 편향 잔존), 스프레드 없음.
  · **이후 확인 프레임은 PIT 코호트를 기본으로 쓴다**(사전 등록 시 명시). 배포 판정 변화 없음(CONFIRMED 0 유지).
  · **사용자 결정 (2026-09-06 저녁) — "현 상태에서 더 이상 끄지 않고 실거래로 1달 정도 돌려본다"**: REJECTED 라우팅 셀 3 포함 배포 집합
    전부 유지, 관찰 종료 **2026-10-06**(ih/marubozu 와 동일). 종료 시 셀별 실거래 표를 v4 OOS 와 나란히 보고 후 재결정. 실거래 무변경.
- **BTC.D 오늘 점 척도 정정 (2026-09-05 저녁)**: `_fetch_btcd_from_cg` 가 365일 시계열은 5종(BTC/ETH/SOL/XRP/ADA)
  시총 합산 비율(≈78%)로 만들고 **오늘 점만 /global 전체시장 BTC 점유율(≈59%)** 을 넣어 실행 로그에 77.8% 와 59.1% 가
  같은 지표로 찍혔다. **라벨 영향 없음** — build_regime_map 은 닫힌 봉 날짜만 쓰고 오늘 점은 어느 날짜의 기울기에도
  들어가지 않으며, 러너는 매 실행 새로 받는다(커밋된 btc_dominance.json 은 7/6 만료분, 워크플로가 되밀지 않음).
  오늘 점을 /global 의 5종 점유율로 같은 비율로 환산(`_proxy_from_global_pct`, 하나라도 없으면 생략). test_regime_determinism +5.
- **1h 추가 기각** (2026-07-03): bb_zscore_1h·rsi_extreme_1h 롱/숏 4방향 전부 REJECTED
  (mean 음수, boot_p 0.42~0.60, 저볼륨 필터로도 미달 — registry rejected_1h 14건)
- 유니버스: **80종목** (OKX 무기한 30일 거래대금 상위 80, 2026-09-04. 종전 업비트KRW∩OKX선물 71→67)
- **패턴별 차등 유니버스** (2026-07-06 사용자 결정, 거래대금 코호트 분석 기반):
  engulfing→top20, fvg→top30 (30일 평균 거래대금 상위, 매 실행 재계산),
  inverted_hammer/marubozu→메이저 7종목 (scheduler.PATTERN_UNIVERSE).
  근거: 코호트 분석 — engulfing top20까지 엣지 유지(+2.65%/중앙+9.9%), fvg top30이
  전체보다 질 우위(+2.36%/중앙+6.5%), ih·marubozu는 top7 밖 급감/불안정.
  하모닉 4h·1h 패턴은 기존 검증 유니버스 유지. 경계 과적합 주의 — 분기별 재점검 권장
- **자동화**: `daily_scheduler.yml` (--slow, oncefull@UTC00:00) + `fast_scheduler.yml`
  (--fast, exit_spec 패턴만). 2026-09-02 분리. **발화는 Supabase pg_cron → workflow_dispatch
  전용**(daily UTC 00/04/08/12/16/20 정각 / fast 매시 :03) — **두 워크플로 다 GitHub schedule 없음
  (2026-09-06 사용자 결정 "폴백 제거해줘")**. daily 폴백은 9/05~9/06 에 5회 연속 지각(최대 2시간
  19분)하며 이미 돈 느린틱을 재실행했고, 지각한 폴백은 같은 concurrency 그룹의 pending 을
  취소시킬 수 있다(fast 쪽 실측). **대가: 발화 경로가 하나뿐** — pg_cron 이 멈추면 진입·청산·
  손절 점검이 전부 정지한다(PAT 만료는 gh_dispatch_log 401 로 드러남, 복구는 수동 dispatch).
  발화 시각 집합·모드·패턴 케이던스는 불변. 발화율 측정 시 dispatch 이벤트 포함
- **장부 행 수 ≠ 실포지션 수 — 진단 로그 추가 (2026-09-08, 사용자 지적 "OKX 앱 실제 살아있는 포지션은 13개인데 16개라고 하는 거 보면")**:
  registry `ledger_diagnostic_2026_09_08`. `[paper] 오픈 N건` 은 `len(still_open)` = **장부 행 수**다.
  still_open 은 A(±10%/20봉)·D 두 다리가 **둘 다** 닫혀야 빠지는데(paper_executor:839) 실포지션은 D 로
  청산되므로, A 가 남아 있으면 실포지션이 없어도 행이 '오픈'으로 남는다.
  · **정정**: 9/07 점검 보고의 '오픈 16/16 슬롯 만석'은 **오류**. 슬롯 계수는 live_open_count 이고 진입
    루프에서 최대포지션 체크가 중복 체크보다 **먼저** 돈다(:936 → :939) — 그날 TAO/DOT 이 '중복'
    메시지를 받았으므로 live_open_count < 16 이 증명된다. 슬롯은 차지 않았다.
  · **미해결 결함(사용자 결정 대기) — d_closed 유령 슬롯**: D 다리가 닫힌 행은 실포지션이 이미 없는데도
    live_mode=True 를 유지해 **슬롯(live_open_count)을 먹고 같은 종목·방향 재진입(live_dir_keys)을 막는다**.
    reconcile_closed_positions 는 d_closed 행을 의도적으로 건너뛴다(:639). 고치려면 두 곳에서 d_closed 를
    제외해야 하는데 그건 **거래를 늘리는 방향의 동작 변경**이라 관찰 기간 중 적용은 사용자 결정.
  · **이번에 넣은 것은 출력뿐**(사용자 결정 B): `ledger_breakdown()` + 진입 루프 직전 `[장부]` 한 줄
    (행 수 / 실거래 / 페이퍼 / OKX 실포지션 수 / 슬롯 / 유령 행 심볼). live_open_count 정의와
    live_dir_keys 최종 값은 **불변**(test_executor_safety 7건이 고정).
  · **C 실측 검증 (2026-09-08 12:00Z)**: `[장부] 오픈 17행 = 실거래 17 + 페이퍼 0 | OKX 실포지션 14건 |
    슬롯 14/16 | D청산 완료·A만 남은 행 2건 ['ADA','BTC'] ← 슬롯·중복방어에서 제외됨`. 유령 **3행**
    (ADA·BTC×2, 심볼 표기는 중복 제거) 제외로 17 → 14. **C 적용 전이었다면 17/16 만석이라 신규 진입이
    전부 막혔을 것.** BTC 페이퍼 2행은 실포지션 생성으로 live 승격됐으나 d_closed 라 슬롯에서 빠진다.
  · **stop_map d_closed 필터 (2026-09-09 사용자 승인, 해소)**: 종전 `stop_map` 은 `live_mode` 만 봐서
    BTC 처럼 장부에 3행(유령 2 + 실포지션 1)이 있으면 심볼 키 dict 에서 **죽은 행의 손절가가 실포지션
    손절 재등록에 쓰일 수 있었다**(유령 71,310/73,478 vs 실포지션 72,566). ensure_stop_orders 는 손절
    **누락 시에만** 재등록하므로 상시 오작동은 아니었으나, 누락되는 순간 검증치와 다른 손절가가 걸린다.
    · 인라인 루프를 **`paper_executor.stop_map_of(positions)`** 로 빼고 거기서 `d_closed` 를 제외했다.
      헬퍼로 뺀 이유는 성질을 **문자열 고정이 아니라 동작으로** 시험하기 위해서다(C 는 소스 문자열 고정).
      target 은 종전대로 exit_spec 패턴에만 — 기존 1d/4h 패턴에 익절 주문을 붙이면 검증된 적 없는
      청산 규칙이 실계좌에서 돈다.
    · **거래 동작은 안 바뀐다** — 진입·슬롯·중복 방어와 무관하고, 손절이 누락됐을 때 재등록되는
      **가격**만 달라진다(살아 있는 행의 값으로). test_executor_safety +7(실측 BTC 3행 재현 포함).
  · **선택지 C 적용 (2026-09-08 사용자 승인, 거래 동작 변경)**: `live_open_count`·`live_dir_keys` 의 장부 합집합에서
    **d_closed 행 제외**. 슬롯 계수 14 → 13, ADA 롱 재진입 차단 해제 — **거래를 늘리는 방향**. 거래소 실측 집합은
    불변이라 '장부에 없는 실포지션' 방어는 유지. 부수 효과로 `live_filled_count` 이중계상도 해소된다
    (_record_trade 가 D 청산에만 live_mode 를 붙여 d_closed 행은 이미 trades 쪽에서 세어지고 있었다).
    reconcile 의 d_closed 스킵·ensure_stop_orders(거래소 실포지션만 순회)는 불변. test_executor_safety +5.
  · **구성 확인(같은 날, 네트워크 개방 후 아티팩트 직접 판독)**: 16행 = **실포지션 13 + 유령 1(ADA marubozu, D 청산됨·A 미해소·
    live_mode 유지) + 페이퍼 전용 2(BTC marubozu 8/21·BTC IH 8/28)**. 사용자가 본 13 과 일치. **유령 슬롯 실재** — ADA 가 슬롯
    1개를 먹고 ADA 롱 재진입을 막는 중. C 적용 여부는 사용자 결정 대기. NEAR/DOT/TAO 는 A 만 먼저 해소된 정상 실포지션.
- **vol_awakening_4h 편중 → 계측 + 포트폴리오 프레임 (2026-09-10, 사용자 승인 2건)**: 실포지션 12건 중
  **8건이 vol_awakening_4h**(9/05 하루에 7건 진입한 버스트). 방식D 보유 상한이 30봉이고 TF 를 안 보므로
  4h 는 5일 점유 — A 다리는 20봉째인 9/08 에 먼저 청산됐고 D 다리는 9/10 만기라 **이 편중 자체는 오늘 풀린다**.
  · **기전은 선점이다** — 진입 순서(앙상블 점수)는 1d=C·4h=D 로 **같은 틱 안에서는** 이미 1d 가 앞선다
    (9/09 만석 때 C등급 XRP 진입·D등급 4h 스킵이 실측). 문제는 그 정렬이 빈 슬롯에만 작동한다는 것 —
    4h 8건이 5일 자리를 잡으면 3일차 1d 신호는 점수와 무관하게 자리가 없다.
  · **증거는 직관과 반대 방향** — vol_awakening_4h 는 v5 CONFIRMED 2셀 중 하나(OOS n=2593 +0.21% bp .000)이고
    밀려날까 걱정하는 engulfing|bull_btc 는 INCONCLUSIVE 다. 확인된 셀을 끄고 미확인 셀을 보호하는 셈이 된다.
    **실제 경합 비용도 아직 관측 안 됨** — 9/09 만석 때 밀린 4건 중 3건이 vol_awakening 자신이었다.
  · **① 계측(적용 완료)**: `paper_executor.slot_occupancy` / `occupancy_txt` — 매 실행 `[슬롯점유]` 한 줄로
    패턴별 점유를 찍고, 만석 스킵 로그에 **밀린 신호의 패턴·등급 + 그때의 점유 분포**를 남긴다.
    세는 집합은 `live_open_count`·`ledger_breakdown.live_active` 와 같다(유령·페이퍼 제외).
    **출력만 — 진입 판정·슬롯 계수·중복 방어 전부 무변경**(test_executor_safety +10).
  · **② 포트폴리오 프레임 — 결과: 규칙 후보 전부 기각, 현행 유지 (2026-09-10, run 34432328827)**: 배포 집합 전체를
    한 자산곡선에 올려 슬롯 배분 규칙만 바꿔 비교. 총 8449건(1d 1270 / 4h 7179), train 4210 / holdout 4239.
    **holdout Calmar current -0.63 vs cap4/cap6/cap8/prio_edge/cohort20 -0.66/-0.66/-0.64/-0.66/-0.66 — 5 arm 전부 REJECTED.**
    · **편중은 계량됐다** — 1d 신호가 밀린 순간의 점유 1위는 언제나 vol_awakening_4h: **inverted_hammer 69% ·
      engulfing 53% · triple_bottom_4h 42% · fvg 36%**. 우려의 사실관계는 맞았다.
    · **그런데 막으면 더 나빠진다** — 패턴별 상한 3종 전부 악화. 상한을 걸면 4h 체결이 상한 스킵으로 바뀔 뿐
      **그 자리를 1d 가 못 채운다**(cap4 체결 1049→926 로 순감). 그 시각에 1d 신호가 존재하지 않는다.
    · prio_edge(슬롯일당 기대값 우선, 인과적 확장추정)만 **train 에서 current 를 이겼고**(Calmar 0.86 vs 0.82)
      holdout 최하위(-0.66). 과거 기대값으로 슬롯을 배분하는 것은 재현되지 않는다.
    · **holdout 진짜 병목은 슬롯이 아니라 증거금** — current 스킵 슬롯 440 vs **증거금 2750**. 자산이 줄면
      슬롯 규칙 자체가 무의미해진다. J4(MDD 5%p 이내)는 전 arm 통과 — 낙폭도 안 줄었다.
    · 유보: **전 arm holdout 이 깊은 음수**(CAGR -58~-61%, MDD -88~-93%). 2025-01~2026-09 bear 지배 + 정적 코호트
      소급이라 **절대 수준을 실거래 예보로 읽지 말 것**. arm 비교는 같은 신호 집합이라 상쇄된다.
    · **1차 실행(34429748383)은 INVALID** — `collect_4h` 가 ms 단위 ts 를 그대로 시간축에 넣어 4h 거래가 1d 뒤에
      전부 정렬됐다(측정하려던 슬롯 경합이 아예 일어나지 않음 + 분할 9%/91% + CAGR 0). `vr._tnum` 으로 고치고
      회귀 테스트로 고정한 뒤 재실행. **그 수치는 인용 금지.**
  · **MAX_POS 상향은 권고 안 함** — 격자에서 16→20/24 는 Calmar 1.85→1.83 이고 증거금이 곧 다음 병목.
- **실거래 안전장치** (2026-07-06): MAX_LIVE_POS **16**(사용자 승인 5→12 2026-07-06 → 16 2026-09-05, 슬롯 격자 근거 —
  12→16 슬롯 스킵 462→47·Calmar 1.84→1.85·MDD −2%p, equity $400 에서 16슬롯 증거금 $400 이라 그 아래면 증거금이 먼저 막음 — **2026-09-10 risk 1% 하향으로
  16슬롯 증거금이 equity 의 67% 가 되어 이 제약은 해소**) ·
  킬스위치(equity < $100 → 신규 진입 중지, paper_executor.EQUITY_FLOOR —
  2026-08-29 사용자 지정 절대 하한. 기존 HWM 대비 -20%($230.06) 규칙은 폐기) ·
  손절 algo 주문 매 실행 자동점검(ensure_stop_orders — 누락 시 재등록 +
  포지션 없는 고아 주문 취소, 주문은 reduceOnly 청산 전용. 2026-08-29) ·
  텔레그램 알림(notify.py — TELEGRAM_BOT_TOKEN/CHAT_ID secrets 등록 시 활성)
- **삼중바닥 넓은 스윙 판(pivot 5 / eq 0.45) 사전 등록 (2026-09-08, 사용자 지시 "5 / 0.45로 사전등록해서 돌려줘 …
  1시간, 4시간, 1d, 1w 로 다 돌려봤으면")**: registry `tb_wide_prereg_2026_09_08`. validate_tb_wide.py /
  test_tb_wide.py(28) / tb_wide.yml. **DEPLOY_ON_PASS=False — 통과해도 실거래 반영 없음**(관찰 기간, 배포는 사용자 결정).
  · **계기**: 사용자가 실전에서 가장 많이 매매하는 감속형 바닥(저점 두 번 연속 갱신 + 갱신 폭 축소)이 배포 파라미터
    (pivot 3 / eq 0.35)로는 안 잡힌다. 2026-06~08 BTC 사례에서 조건 6개 중 **동일수준 하나만** 깊이의 4% 차이로 탈락.
  · **사용자 사례(사전 등록에 고정)**: 업비트 KRW-BTC 06-05 90,500,000 → 07-01 88,770,000(−1.91%) → 08-14 88,342,000
    (−0.48%), 갱신 폭 4.0배 축소, 넥라인 100,992,000, 08-21 돌파 후 **+27.3%**. 5/0.45 로 잡히고 3/0.35 로는 안 잡힌다.
  · **OKX/업비트 괴리 — 중요**: 같은 기간 **OKX USDT 는 저점을 갱신하지 않았다**(59,078 → 57,750 → 62,227). 원화 약세로
    KRW 차트에서만 하강 구조가 나온 것. 판정은 거래 가능한 USDT 로만 하고, KRW 는 진단 D3(탐지 소스를 바꿀 가치가 있는가)로만 본다.
  · 동결: pivot 5 / eq 0.45, 나머지 상수 불변, causal=True, TF 1h·4h·1d·1w, top30·ALL·롱, **Holm 보정 m=4**,
    홀드아웃 1h 90 / 4h·1d 365 / **1w 730일**. C1 게이트 v2 + C2 홀드아웃 + C3 자산곡선.
  · **디텍터 파라미터화는 배포 패턴에 무영향** — `detect(rows, pivot_half=None, eq_frac=None)` 기본값이 종전 상수와
    같아 triple_bottom_4h 신호 집합이 한 건도 안 바뀐다(test 가 신호 집합 일치로 고정, 스케줄러는 인자를 안 넘김).
  · **실행 전 수정(공개)**: 1w 는 OKX 범위만으로는 train 이 통째로 비어(홀드아웃 730일이 전 표본을 삼킴) 판정이
    성립하지 않는다 → 1d 를 data_long(2017~)에 잇는 것을 기본으로. 결과를 보고 고른 변경이 아니다.
  · **결과 (run 34240822675) — 4h CONFIRMED / 1h·1d·1w REJECTED. 실거래 무변경**:
    **4h** n=805 +1.74% med −0.92% 승률 46% 엣지 +1.76% boot_p .000→Holm .000 · holdout n=283 **+2.69%** · Calmar 1.50.
    **1h** n=1308 −0.19% Holm .068 OOS 0/4 · **1d** n=399 **+8.65%** 엣지 +5.88% OOS 4/4 Calmar 1.39 인데 **승률 26%**(게이트 35%)
    이고 holdout n=35 **−4.00%** — 두 사유 독립 탈락, 복권형 · **1w** n=61 승률 15% boot_p .755.
    · **D2 가 핵심 — 사용자 패턴 자체는 엣지가 아니다**: 하강형(L1>L2>L3 & 갱신폭 축소) 부분집합이 **전 TF 에서 전체보다 나쁘다** —
      1h n=98 −0.01% / 4h n=46 **+1.24%**(전체 +1.74%) / 1d n=20 **−0.64%**(전체 +8.65%) / 1w n=6 −8.20%. 4h 의 엣지는
      **수평형 삼중바닥**에서 나오고 감속 하강형은 그 안에서 열세다. n 이 작아 '열세 확정'은 아니고 **'지지 없음'**으로 읽을 것.
    · **D1 — 넓히는 것 자체가 이득이 아니다**: 4h 격자 9칸 평균이 +1.1~+1.9% 로 평평하고 최고는 **배포값 3/0.35(+1.9%)**.
      5/0.45 는 신호를 679→805 로 늘릴 뿐 건당은 같거나 낮다. 1d 는 5/0.35 +10.5% · 7/0.35 +11.4% 가 더 높으나
      **사후에 격자 최대값을 고르지 않는다**(사전 등록).
    · **CONFIRMED 4h 셀은 이미 배포된 triple_bottom_4h(ALL·top30·롱)의 재파라미터화** — 배포판 Calmar 2.79(revival §8) vs
      이번 1.50. 신호는 25% 많고 holdout 건당은 낫지만(+2.69 vs +1.62%) 자산곡선이 나쁘다. **교체 근거 없음, 파라미터 불변.**
    · **D3 — 탐지 소스를 업비트 KRW 로 바꿀 근거 없음**: KRW 신호가 훨씬 적고 날짜가 거의 안 겹친다(BTC KRW 3건 vs USDT 15건,
      일치 0 / 8 메이저 합쳐 일치 4건). 사용자 사례 2026-08-20 은 KRW 3건 중 하나.
    · 사전 기록과 부분 일치 — n 은 예상대로 4h·1d 에 붙었으나 1w·1h 는 '판정 불가'가 아니라 REJECTED 로 떨어졌다.
- **engulfing TF 재시험 사전 등록 — 1h / 4h / 1w (2026-09-09, 사용자 지시 "4h랑 1w 돌려봐 1h도 돌려봐")**:
  registry `engulf_tf_prereg_2026_09_09`. validate_engulf_tf.py / test_engulf_tf.py(38) / engulf_tf.yml.
  **DEPLOY_ON_PASS=False — 통과해도 실거래 반영 없음**(관찰 기간, 배포는 사용자 결정).
  · **계기**: engulfing 은 레포에서 OOS 증거가 가장 강한데(v4 bull_btc 롱 OOS n=34 +7.0%, 엣지 +8.76%p,
    왕복 0.4% 비용에도 +6.8%, PIT 로도 유지) 실거래는 **1d 만** 배포돼 있다. TF 스윕은 **2026-06-24 한 번뿐**:
    1d 검증통과(n=90 +3.58% med +9.99%) / **4h 게이트후탈락(n=1103 +0.75% med +0.44%)** / 1h 기각(n=5801 −0.23%) /
    15m 기각. 숏은 1d 게이트후탈락·나머지 기각.
  · **구멍 둘**: **1w 는 한 번도 안 돌렸다**(연구 로그 0건). **4h 는 구 게이트 탈락 후 재시험된 적 없다** —
    기각 55종 레짐 재시험(validate_regime_split_all)의 4h 목록 21개에 engulfing 이 없고 1h 판만 들어가 있다.
  · **그 사이 프레임이 네 번 바뀌었다**: 게이트 v1(중앙값>0)→**v2**(승률≥35%) · boot_p 베이스라인
    **k=30→k=n 버그 수정**(엣지 양수 셀의 p 를 부풀리던 편향 — 수정 후 통과 셀 2→18개. **옛 4h 탈락이 정확히
    이 편향을 안고 있었다**) · 라벨→실거래 프레임 · 정적→**PIT 코호트**. 앞 셋은 통과 쪽, PIT 는 기각 쪽.
  · 동결: 디텍터 **인자 없이 호출**(배포 1d 신호 집합 불변, test 고정) · 주 판정 6셀 = TF{1h,4h,1w} × 방향{long,short} ·
    레짐 ALL · 코호트 **core20 PIT** · **Holm m=6** · 홀드아웃 1h 90 / 4h 365 / **1w 730일** · validate_revival 프레임.
  · 판정: C1 게이트 v2 + C2 홀드아웃 + **C2b(train 자체 게이트 통과 AND train n ≥ holdout n/2)** + C3 자산곡선.
    **C2b 는 ma180 에서 도입한 가드의 두 번째 적용** — vwap_rev_short_4h 가 표본 92%를 홀드아웃에 두고 통과한 구멍.
  · 진단(판정 아님): D1 **1d 참조 셀**(프레임 정합성 — Holm 가족 아님) · D2 정적 top20 대비 · D3 레짐 분해 ·
    D4 코호트 확대 · D5 **왕복 마찰 0.4% 스트레스**. 사후에 진단에서 골라 '살았다'고 하지 않는다.
  · **사전 확률(결과 전 기록)**: 4h 가 가장 가망 있으나 **왕복 0.4% 면 +0.75%의 절반 이상이 날아가고**, 통과해도
    1d 의 +3.58% 와 체급이 다르며 신호 1,103건이라 vol_awakening_4h 처럼 슬롯을 잠식할 위험이 있다(패턴 단독
    프레임은 그걸 못 본다). 1h 기각 유력(두 번 기각 + 2026-09-05 ATR 채점표 확인 0 CONFIRMED). 1w INCONCLUSIVE 유력
    — validate_exit_1w 에서 **방식D(−8% 저가 손절)가 주봉 폭에 안 맞는다**가 이미 확인됐다. 숏 세 셀 전부 기각 예상.
  · 스모크는 8종목 1w 관통 확인뿐 — **수치는 결과가 아니다**(코호트 셋이 같아져 D2·D4 퇴화).
  · **결과 (run 34301698148) — 6셀 전부 REJECTED. 실거래 무변경**:
    **4h 롱이 가장 근접 — C2 홀드아웃 하나로 탈락.** n=1014 +0.67% med −0.40% 승률 48% 엣지 +1.07%
    boot_p **.000→Holm .000** OOS **4/4**, C2b(train n=617)·C3(Calmar 1.12) 통과인데 **holdout n=397 −0.21%**.
    **옛 판의 '게이트후탈락' 은 새 프레임에서 뒤집혔다** — boot_p 편향 수정 효과가 실재했다. 다만 홀드아웃에서 재현 안 됨.
    나머지: 4h 숏 −0.30% · 1h 롱 −0.26%(OOS 0/4, 세 번째 기각) · 1h 숏 −0.12% · **1w 롱 n=24 +3.76% 인데 승률 29% med −8.20%** ·
    1w 숏 n=32 승률 28%.
    · **D1 이 결정적 맥락 — 참조 1d 도 이 설정에선 게이트를 못 넘는다**(long n=210 +4.39% 승률 35% **boot_p .090**).
      레짐 ALL·core20 PIT·방식D 조합은 배포 1d 를 통과시킨 프레임보다 엄하다. **같은 잣대에서 4h 만 boot_p .000 으로
      1d(.090)보다 강했다** — '4h 가 1d 보다 못하다'로 읽으면 안 된다. 배포 1d 의 근거는 레짐 조건부 셀
      (v4 bull_btc OOS +7.0%)이고 이 판은 레짐을 안 나눴다(known_limits 에 결과 전 기록).
    · **D5 마찰 — 사전 확률 적중**: 4h 롱 +0.67% → **+0.27%**(왕복 0.4%, 60% 소실). 양수는 유지하나 1d 체급이 아니다.
    · **D3 — 4h 롱은 세 레짐 전부 엣지 양수**(+1.01 / +1.04 / +0.95%p)이나 bear 절대수익은 −0.12%.
      홀드아웃 365일이 2025-09~2026-09 bear 지배라 탈락이 기전상 설명된다. **그러나 이 관찰로 판정을 뒤집지 않는다** —
      사전 등록은 달력 홀드아웃(v2)이고, 결과를 본 뒤 v3 국면 홀드아웃으로 갈아타면 사후 선택이다.
    · D4 4h 롱 엣지가 순위에 단조(core20 +1.07 > top30 +0.91 > liquid +0.65%p) — engulfing top20 원칙과 같은 방향.
    · **사전 확률 3/3 방향 적중** (4h 가장 가망 · 1h 기각 · 1w 는 손절에 털림). 1w 만 'INCONCLUSIVE 유력' 예상과 달리
      승률 문턱으로 REJECTED.
    · **후속 후보(사용자 결정)**: 4h 롱을 v3 국면 홀드아웃으로 **별도 사전 등록**. 단 선결 둘 — 마찰 후 +0.27% 는 얇고,
      신호 1,014건(연 약 500)이라 vol_awakening_4h 처럼 슬롯을 잠식한다(9/09 실측 16/16 만석). **포트폴리오 단위 확인 프레임이 먼저다.**
- **작은 고정 익절(+1%) 복리 사전 등록 (2026-09-09, 사용자 제안 "포지션 진입했을때 무조건 플러스 1프로(레버리지 3프로)면
  바로 익절되게" + 승인 "응 돌려")**: registry `tp_small_prereg_2026_09_09`. validate_tp_small.py / test_tp_small.py(60건) /
  tp_small.yml. **DEPLOY_ON_PASS=False — 통과해도 실거래 반영 없음**(관찰 기간, 청산 규칙 변경은 실주문 경로).
  · **규칙**: 진입 후 **배리어만** — 익절 +TP%, 손절 −SL%. 레짐 전환·반대 신호·시간 청산 없음(사용자 표현 "무조건 … 바로").
    미도달 시 250봉 강제청산. 격자 익절 {1,2,3}% x 손절 {1,2,4,8}% = 12셀 + 기준선 D. **주 판정은 T1S8(1%/8%) 하나**,
    나머지 11셀은 진단이며 사후 선택 금지.
  · **핵심 지표는 수익률이 아니라 승률 리프트** — 무편향 랜덤워크에서 P(익절 먼저) = SL/(TP+SL) 이고 그 지점의 기대값은
    정확히 0(수수료 전)이다. **배리어 폭 자체는 가치를 만들지 않는다.** 1%/8% 는 도달률 **88.89%**, 왕복 0.2% 를 넘으려면
    **91.11%** 가 필요하다. 즉 '1% 복리' 직관은 그 1%가 보장될 때만 성립한다.
  · **method_t 로는 답이 안 나온다** — 그 기각은 k=10~30% 였고 기전이 "오른쪽 꼬리 절단, 회전율 2배로는 복리가 보상 못함"인데
    k=1% 는 회전율이 10배 안팎이라 기전이 그대로 옮겨오지 않는다.
  · **입금 불필요** — 같은 신호에 두 규칙을 동시 적용하는 짝지음으로 백테스트에서 잰다(자본 분할 대비 검정력 수십 배).
  · **두 자산곡선**: P1 포트폴리오(실거래 사이징·MAX_POS 16) + **P2 전용 포트**(사용자 제안 그대로 — 한 번에 한 포지션,
    전액 x3x, 순차 복리, 시작 100,000). P2 가 '10만원이 얼마가 되나'에 직접 답한다. 한 번에 하나라 신호 대부분을 못 받는다.
  · 기준 9개 전부 만족해야 PASS(①짝지음 유의 ②건당>0 ③리프트>0 ④마찰 0.4%>0 ⑤전후반 양수 ⑥P1 CAGR우위>=4/7
    ⑦⑧holdout ⑨P2 CAGR). 진단(판정 아님): **같은 배리어를 무작위 진입에 적용한 베이스라인** — '배리어+드리프트가 나쁘다'와
    '패턴이 도움이 안 된다'를 가른다.
  · **사전 확률(결과 전 기록)**: 신호봉 프로필(2026-09-07)의 같은 달 demean 상관이 −0.05~−0.09 로 약간 음수 → T1S8 은
    손익분기 근처에서 살짝 미달 예상. 스모크는 메이저 7종목·구 데이터로 배관 확인뿐이고 **수치는 결과가 아니다**
    (스모크 후 추가한 것은 무작위 베이스라인 진단 열뿐, 판정 기준 무변경).
- **익절 1h 재측정 + 손절 3%/12~20%/무손절 + 레버리지 스윕 (2026-09-09, 사용자 지시 "1시간봉 데이터로 다시 돌려봐" /
  "익절 1퍼센트 손절 3퍼까지 버티기도 테스트된거 맞아?" / "레버리지를 아예 안쓰거나 손절범위를 8퍼센트 이상으로 늘려서
  버티는것까지 테스트")**: registry `tp_1h_prereg_2026_09_09`. **결과 4셀 전부 REJECTED (run 34317260194). 실거래 무변경.**
  · **손절 3% 는 시험된 적이 없었다** — 1d 격자가 {1,2,4,8}% 였다. 이번에 넣었다.
  · **1h 재측정은 정당했다** — 동률 비율(청산 봉이 양쪽 배리어를 다 건드린 비율) 1d→1h: T1S1 **70.6%→5.7%** /
    T1S2 56.8%→2.0% / T1S3 **44.4%→0.9%** / T1S8 13.3%→0.1%. **일봉 측정이 실제로 오염돼 있었다.**
  · **1d 판 해석 정정** — 그때 '패턴 엣지 −4.36%p(무작위보다 나쁘다)'로 보고했으나 대부분 동률 아티팩트였다. 1h 실측은
    네 셀 −0.17~−0.82p 이고 **전부 Holm 1.000 — 무작위와 구분 안 됨**. 옳은 서술은 **'패턴 엣지 ≈ 0'**.
    (1차 +0.18p ↔ 2차 −0.17p 로 부호가 흔들린 것도 ≈0 의 증거 — 유리한 쪽을 고르지 않는다.)
  · **남는 건 수수료뿐** — 리프트가 1d −12.10p → **1h −0.89p** 로 이론값에 붙었다. 1%/8% 는 완벽한 마팅게일이어도
    건당 −0.20%(왕복 수수료), 실측 −0.28%. 회전율이 빠를수록 그 수수료를 더 자주 낸다.
  · 4셀(train n=47,903 / holdout 17,246): **T1S3** 승률 73.11%(필요 80.00%) 건당 −0.28% · **T1S8** 88.00%(91.11%) −0.28% ·
    **T1S20** 94.30%(96.19%) −0.39% · **T1SX 무손절** 96.98% −0.49%, 보유 104.9봉, **최대손실 −154.4%**(숏은 손절을
    빼면 손실이 무한 — 원금 초과).
  · **손절 넓히기는 순효과 없음** — 필요 리프트는 +2.22p→+0.95p 로 줄었으나 실현 리프트도 −0.89→−0.94p 로 같이 내려가
    상쇄됐고 건당은 −0.28%→−0.39% 로 악화(보유 17→37.8봉, 자본이 묶인다). 격자 전체가 같은 모양(손절 4%에서 최악,
    20%까지 개선, 무손절에서 다시 악화).
  · **레버리지 1배도 못 산다** — P2 전용포트(한 번에 하나·전액·순차 복리) 1x/2x/3x: T1S3 0.03/0.00/0.00배 ·
    T1S8 0.12/0.01/0.00 · T1S20 **0.58**/0.17/0.02 · 무손절 0.00(첫 대형 손실에 파산). 1배가 어디서나 가장 덜 나쁘지만
    전부 1배 미만 — **레버리지는 파산을 늦출 뿐 기대값 부호를 못 바꾼다**(사전 등록 그대로). 최선 T1S20 1x 도 연 −42%.
  · **룩어헤드 결함 발견·수정(내가 넣은 것)** — 1차 결과에서 T1S8 건당 −0.27% 인데 P2 1x 가 +89,495배로 모순. 원인은
    `sorted(recs)` 가 (진입,청산,수익) 튜플이라 **같은 진입 시각 중 청산이 이른 것**을 먼저 잡은 것 — 배리어에서 빠른
    청산 ≈ 익절이므로 '먼저 끝날 거래'를 미리 아는 셈. 진입 시각만으로 정렬 + 동률은 입력 순서로 수정, 테스트로 고정.
    **기준 ①~⑦ 은 P2 를 안 쓰므로 판정은 1·2차 동일.** validate_tp_small(1d)에도 같은 결함이 있어 함께 고쳤다 —
    그 판은 P2 가 전 arm 0 이라 결론 불변이고 편향이 낙관 쪽이라 '파산' 결론은 강화된다.
  · **사전 확률 3/3 적중**(네 셀 기각 · 넓은 손절은 자본이 묶인다 · 레버리지 1배도 부호 불변). 1d 판에서 크기를 크게
    틀렸기에 이번엔 크기를 안 적었고 그 판단이 옳았다(실제 부족분 −0.89~−6.89%p 로 셀마다 크게 달랐다).
  · 한계: 1h 도 봉 안 순서를 완전히 보지는 못한다(동률 잔여 0.1~0.9%) — 낙관 상한으로 폭을 가뒀고(T1S8 88.00~88.10%)
    판정은 보수 판. 완전 해소는 틱 데이터 필요. 데이터가 1h 365일뿐이라 홀드아웃 90일.
  validate_tp_1h.py / test_tp_1h.py(52건) / tp_1h.yml
  · **결과 REJECTED (run 34313582686) — 9기준 0통과, 12셀 전부 음수. 실거래 무변경**:
    T1S8 train n=7746 건당 **−1.29%** 승률 **76.79%**(필요 91.11%) 리프트 −12.10p / 분기점 대비 **−14.32p**,
    holdout n=2527 −1.26% 승률 76.97% 로 **그대로 재현**. 짝지음 D 대비 −3.49%p **t −12.14**. 12셀 전부 t −9.9~−13.2 열세,
    익절이 좁을수록 나쁜 단조 관계(최선 T3S8 −0.73%).
    · **진단이 손실을 둘로 가른다** — 이론 88.89% → **무작위 진입 실측 81.15%**(−7.74p, 배리어+실제 가격 과정: 갭·팻테일·드리프트)
      → **패턴 76.79%**(−4.36p, 신호 직후가 무작위보다 나쁘다). 둘 다 음수라 어느 쪽으로도 살릴 길이 없다.
    · **P2 전용 포트는 모든 arm 이 0 — 현행 D 포함.** 승률 30%·손절 −8%×3x = −24% 인데 분산이 없어 연패가 그대로 파산이다.
      **'10만원 3x 순차 복리' 구조 자체가 청산 규칙과 무관하게 못 쓴다**(D 기준선이 그것을 증명한다).
    · **내가 적은 실행 근거가 틀렸다** — 'method_t 의 오른쪽 꼬리 절단 기전은 회전율 10배에선 그대로 안 옮겨온다'가 실행
      이유였는데 정확히 그대로 옮겨왔다. 보유 9.1→1.2봉(약 7.6배 회전)인데 승률 30%→77% 상승이 평균 +2.20%→−1.29% 하락을
      전혀 보상 못 했다. **익절 규칙 여섯 번째 기각**(E·F·G·H·T 에 이어).
    · **사전 확률은 방향만 맞았다** — '손익분기 근처에서 살짝 미달' 이라 적었으나 −14.32%p 는 근처가 아니다.
    · **측정 한계(중요)**: 좁은 익절 셀은 일봉이 봉 안 순서를 못 본다. 동률 시 손절 우선(보수적)인데 ±1% 는 알트 일봉이
      거의 매번 둘 다 건드린다 — 1d 무작위 T1S1 승률 **18.4%**(이론 50%), 1w T1S8 **50.0%**(이론 88.9%)가 증거. T1 행 절대
      수치는 **하한**이다. 다만 판정은 안 뒤집힌다 — 결정에 쓰는 양은 'D 보다 나은가'이고 12셀 전부 열세이며, 동률이 드문
      T3S8(11% 범위 봉이라야 동률)에서도 무작위 69.0% vs 이론 72.7%(−3.7p)·패턴 엣지 −1.8p·건당 −0.73%. 제대로 재려면
      1h 이하 데이터 필요(band_rule 과 같은 구멍).
    · **프레임 유보**: P1 은 무조건부 7패턴×80종목 슬롯 범람 판(D CAGR +6.2% MDD −84.6%, 스킵 5,737) — method_b 결함과 같은 자리.
      짝지음 건당 비교는 무관하나 P1 절대 수준을 실거래 성과로 읽지 말 것.
- **배리어 격자 레짐 분해 (2026-09-09, 사용자 지적 "1%/8% 레짐이나 상승국면에서 테스트한거 맞아?" → 아니오, 풀링뿐이었다)**:
  registry `tp_regime_prereg_2026_09_09`, run 34321686679. **8셀 전부 REJECTED 이나 사유가 갈리고 내 사전 확률이 양방향으로 틀렸다.**
  · **bull_btc — 드리프트 수확 없음, 패턴은 무작위보다 나쁨**: T1S8 승률 86.03% / 같은 레짐 무작위 **88.77%**(≈ 마팅게일 88.89%) → 엣지 −2.74p,
    건당 −0.46%. 17시간 지평에서 드리프트가 0 이다. 2026-09-04 의 0.26%/일은 2023-24 top30 20일 수치였고 1h 창의 bull_btc 라벨은 '가짜 상승'
    종류(2024-25 라벨 코인 중앙 −54%). 사전 확률 '경계' 오답.
  · **bull_altseason — 패턴 엣지 실재, 그러나 얇고 최근에 안 섬**: T1S3 승률 83.90%(손익분기 80.00%) 무작위 76.48% → **엣지 +7.41p Holm .000**,
    건당 **+0.16%**; T1S8 92.76%(91.11%) 무작위 86.45% → **+6.31p Holm .000**, 건당 **+0.15%**. ①②③④⑥ 통과. 탈락은 ⑤(왕복 0.4% 에서 −0.04%)와
    ⑦(최근 90 altseason 일 = 지금 국면 **−0.27%**). 사전 확률 '음수' 오답.
  · **세 번째 정정 — 'tp_1h 의 패턴 엣지 ≈ 0' 은 풀링 아티팩트였다.** altseason +6~7p 와 bull_btc −2.7p 가 상쇄돼 −0.17p 로 보였다.
    tp_small·tp_1h 두 판 모두 이 프레임 오류를 안고 있었다. **레짐 분해가 결과를 바꿨다 — 사용자가 옳았다.**
  · 커버리지 예측도 틀렸다(bull_btc 1h train 5,714). 맞은 건 'bear 음수'와 '크기를 적지 않는다'뿐. DRIFT_HARVEST 0. 1d 진단 8셀도 holdout 전부 음수.
- **지인 카톡 캔들 규칙 3종 사전 등록 → 6셀 전부 REJECTED (2026-09-12, 사용자 지시 "전부 사전 등록해서 돌려줘", run 34678062587)**:
  registry `kakao_patterns_prereg_2026_09_12` / report_kakao.md. **실거래 무변경, DEPLOY_ON_PASS=False.**
  · 사용자가 지인 카톡(김명규·김승준)을 공유 — 책에서 정리한 국내주식 캔들 규칙 3종. **양양양 / 양양음 / 3이평돌파.**
  · **양양양은 배포된 three_soldiers_4h 와 다른 패턴이다** — 원문에서 김승준 "캔들 말하는 거지 **모양이나 크기 없고**" →
    김명규 "응". 즉 그냥 3연속 양봉이고 배포판(바디≥60%·위꼬리≤20%·종가 계단상승)이 아니다. 실측 BTC 1200봉에서
    **plain 137건 vs strict 2건**. 진입도 다르다 — 원문은 **3봉 고점 돌파**, 배포판은 3봉 종가.
  · 주 판정 6셀 = {ma3_breakout, yyb, yyy_plain} x {1d,4h} · 롱 · ALL · top30 · **Holm m=6** · C1 게이트 v2 +
    C2 국면 홀드아웃(frame_v3) + C2b + C3 자산곡선. **전부 REJECTED**(CONFIRMED 0 / INCONCLUSIVE 0).
  · **1d 세 셀 중앙값이 정확히 −8.20%**(= −8% 손절+수수료), 승률 29~32% — report_revival 의 '1d 후보 전 셀 median
    −8.20%' 와 같은 자리. **돌파 진입이라 진입가가 높아져 손절이 더 자주 걸린다**(사전 확률 적중). 평균은 크게
    양수(+3.3~5.1%)지만 게이트 v2 승률 문턱이 정확히 이 형태를 거른다.
  · **6셀 전부 국면 홀드아웃 음수**(−0.19~−3.73%). 연도별 2017~2024 양수 / 2025·2026 전부 음수. **이번 판은 이미
    frame_v3 국면 홀드아웃이라 '달력 홀드아웃 탓' 여지가 없다** — engulf_tf 4h 처럼 프레임 바꿔 재판정할 자리가 없다.
  · **가장 근접 = ma3_breakout@4h**: C1(Holm .028)·C2b(train n=1761)·C3(Calmar 1.41) 통과, **C2 홀드아웃 −0.19% 하나로
    탈락**. 단 **D5 마찰 0.4% 면 +0.54%→+0.14%** 로 통과했어도 체급이 안 난다. **yyb 가 가장 약함** — 1d bp .333
    (무작위와 구분 불가), 4h 평균 −0.34%.
  · **진단(사후 선택 금지)**: yyy_cross(MA5x20 크로스)가 변형 중 두 TF 다 최고(1d 엣지 +2.70% bp .000 / 4h +0.57%
    bp .000) — 사전 등록에 '사후에 진단에서 골라 살았다고 하지 않는다' 를 명시했으므로 **추격은 별도 사전 등록**
    (validate_ih_exit 교훈). D3 레짐: yyb 1d bull_altseason 엣지 +4.72% / bear −2.29% 로 원문 '양양음은 우상향에서
    유효' 와 방향 일치, ma3 는 bull_btc +5.18% 로 추세추종답다 — 둘 다 진단.
  · **실행 전 수정(공개)**: prior_swing_high 피벗을 `<=` → **엄격 `<`**. `<=` 면 고가 동률 횡보에서 모든 봉이 피벗이
    되어 평평한 구간이 '언덕' 으로 잡히고 돌파 신호가 원인과 무관하게 늘어난다(합성 테스트로 발견). 결과 보기 **전**
    수정이고 신호를 줄이는 방향.
  · **사전 확률 5/5 방향 적중**(ma3 최유망·ma3 도 기각·yyb 최약·yyy 기각·돌파는 손절에 더 걸림). 절반만 맞은 것 하나:
    'plain 이 strict 보다 약할 것' — 건당은 strict(+5.40%)가 높으나 n=43 으로 bp .238 이라 유의하지 않고, n 이 큰
    plain 이 통계적으로는 더 강하다. '약하다' 를 건당/유의성 중 무엇으로 읽는지 구분해 적었어야 했다.
  · 한계: 코호트가 **정적 top30**(PIT 아님, 1d 엣지 1.5~2%p 낙관 가능 — 기각 결론은 강화) · 국내주식 일/월봉 규칙을
    암호화폐 1d/4h 로 옮김 · '직전 언덕'(피벗 3)·'돌파 대기 10봉' 은 원문에 없어 내가 고정.
  · **복귀 후보 없음. 배포 three_soldiers_4h 신호 집합 불변**(test_kakao 가 고정). detector_kakao_base/ma3_breakout/
    yyb/yyy.py · validate_kakao.py · test_kakao.py(33) · kakao.yml
- **양양양 + MA5x20 크로스 추격 → 두 셀 다 REJECTED (2026-09-12, 사용자 지시 "ma 5 20 크로스로 사전등록해서 돌려봐", run 34680013945)**:
  registry `yyy_cross_prereg_2026_09_12` / report_yyy_cross.md. **실거래 무변경, DEPLOY_ON_PASS=False.**
  · **사후 선택 셀의 추격이다** — kakao 판 진단에서 최고였던 셀을 그 수치를 보고 골랐다. 그래서 확인 기준만 다시 재는 건
    정보가 없고 validate_ih_exit 선례대로 **반증 3종**을 붙였다: **F1** 걸러진 거래(plain ∖ cross)가 음수여야 한다(method_b
    교훈) · **F2** 달력 전후반 둘 다 양수(ih_exit 교훈) · **F3** 같은 크로스를 배포 패턴 4종에 붙여 개선폭이 yyy 보다 작아야
    한다. **PASS = 확인 4 + 반증 3 전부.** 동결 파라미터는 kakao 판 그대로 하나도 안 바꿨다.
  · **1d** n=2678 +5.47% 승률 **34%** 엣지 +2.92% Holm .000 OOS 3/4 Calmar 2.23 — 탈락 **C1(승률)·C2(국면 홀드아웃 n=295
    −4.62%)·F1(걸러진 n=2896 이 +3.90% 양수)**. F2·F3·C2b·C3 통과.
  · **4h** n=7310 +0.61% 승률 46% 엣지 +0.60% Holm .000 OOS 3/4 Calmar 0.30 — 탈락 **C2(n=2194 −0.83%)·F2(후반 −0.09%)·
    F3**. C1·C2b·C3·**F1 통과**.
  · **새 정보는 4h 의 F1 통과** — 크로스가 걸러낸 6,399건이 **−0.37%** 로 실제로 손실 거래를 버린다(method_b 의 +2.15%,
    1d 의 +3.90% 와 반대). **그러나 F3 이 되돌린다**: 같은 필터가 engulfing **+1.33%p** / marubozu +0.84 / ih +0.69 /
    fvg +0.47 를 개선하는데 yyy 는 +0.33%p 뿐 — **양양양 전용이 아니라 어느 패턴에나 먹히는 상승 추세 필터이고 하필
    양양양에서 가장 덜 먹힌다.**
  · **진단 cross_only — 답이 TF 마다 반대**: 1d 교차 봉 단독 엣지 +1.49% bp .016(yyy_cross +2.92%, 양양양이 보탠다) /
    **4h +0.02% bp .434**(yyy_cross +0.60%, 교차 단독은 0 이고 캔들 조건이 전부). F3 과 나란히 읽으면 4h 는 '엣지는 캔들에서
    나오는데 크로스 필터 이득은 다른 패턴이 더 크게 받는다' — 둘 다 '특별하지 않다' 쪽이다.
  · **실행 전 공개 — 로컬 확인이 1d 판정을 실제로 돌렸다**: `--no-fetch` 는 일괄 프리페치만 건너뛰고 `load_tf` 가 자동
    수집한다. 1d 주 판정 셀이 계산됐고 러너 전에 결과를 봤다. **본 뒤 기준·파라미터·판정식 무변경**, registry 에 본 수치를
    적고 그 커밋으로 러너를 돌렸다. 데이터 상태 차로 수치가 조금 다르고(엣지 +3.71 vs +2.92%) **1d F3 은 로컬 탈락 /
    러너 통과로 부호가 갈렸다** — 판정과 결정 사유는 동일. **러너 수치가 공식.**
  · **사전 확률 — 반증 두 층이 TF 별로 갈렸다**: 'F1 에서 탈락할 가능성이 제일 높다' 는 1d 적중·**4h 오답**(통과),
    'F3 은 다른 패턴에도 비슷하게 먹힐 것' 은 4h 적중·**1d 오답**. 1d 기각·마찰 얇음은 적중. **반증을 하나만 돌렸으면
    어느 쪽이든 틀린 결론이 났다** — 3종을 다 돌린 값이 여기 있다.
  · 한계: 정적 top30(PIT 아님, 기각 강화 방향) · 4h 이력 2년이라 F2 분할이 각 1년 · 사후 선택 셀이라 통과했어도
    '기각을 면했다' 였다.
  · **추격 종료, 복귀 후보 없음.** detector_ma_cross.py · validate_yyy_cross.py · test_yyy_cross.py(27) · yyy_cross.yml
- **확인 프레임 가드 교정 감사 (2026-09-09, 사용자 지시 "가드 너무 엄한것 같으면 그걸 재점검해야지")**: registry `guard_audit_2026_09_09`,
  run 34321686702. 실거래 12셀 × 층 9개 독립 적용. **문턱 무변경(측정만) — 변경은 사용자 결정.**
  · **주범 = L8 B 벤치. 12/12 기각.** 단독 기각이 있는 유일한 층(2셀), OOS 양수 셀 기각 5 로 최다. 누적 통과 **L1 5 → L2 3 → L3~L7 3 → L8 0**.
    4h 3셀(triple_bottom **OOS n=365 +1.59%** / equal_lows n=668 +0.97% / vol_awakening n=2,592 +0.19%)이 L1~L7·L9 전부 통과하고 **L8 하나로**
    떨어진다. 신호 이전 봉만 쓰는 인과 B 로 바꿔도 11/12 기각. 이 층은 '같은 코인·달 안 진입일 타이밍'을 재지 수익성을 재지 않는다 —
    9/06 에 내가 그렇게 기록해놓고 판정 기준에 넣었다. **v4 이후 어떤 실거래 셀도 통과할 수 없는 층이 판정에 있었다** — 사용자가 느낀
    '정답이 정해진 것 같다'의 구조적 원인. 차단이 아니라 내 설계 오류.
  · L1 게이트 v2 는 7/12 기각이고 **OOS 최강 engulfing|bull_btc(n=35 +6.56%)를 떨어뜨린다** — 레짐 매칭 k=n 베이스라인이 높고 n=111 로
    검정력 부족(9/05 '표본 부족 ≠ 엣지 없음' 그대로). L2 달력 홀드아웃 9/12 기각이나 fvg|bull_btc(OOS −1.26%) 등 옳은 기각 포함;
    **L6 국면 홀드아웃(4/12, 거짓음성 1)이 더 잘 교정돼 있다** — v3 가 옳은 수정이었다.
  · **내 의심 셋 중 맞은 건 하나.** Holm 은 m=12 에서 equal_lows 하나만 추가 탈락(과장). 소표본 4중 처벌은 1셀이고 그것도 옳은 기각(과장).
  · 옳은 기각도 있다: three_soldiers_4h|bull_altseason(전층 X, OOS −3.17%), engulfing|bear(OOS −4.25%).
  · **사용자 결정용 권고 순서**: ① L8 을 판정에서 빼 진단으로(통과 0→3, 전부 OOS 양수) ② 레짐 셀 L1 은 n<200 이면 INCONCLUSIVE
    ③ L2 를 L6 으로 대체. Holm·E·C3 는 유지 가능. 캐비앗: OOS 는 2025-01~ 20개월 bear 지배, engulfing|bull_btc OOS n=35 얇음.
  validate_tp_regime.py / test_tp_regime.py(20) / audit_guards.py / test_audit_guards.py(19) / tp_regime.yml / audit_guards.yml
- **확인 프레임 결정 ①②③ + v5 재판정 (2026-09-09, 사용자 결정 "1,2는 진행" → "3번도 진행, b벤치 영향 있는거 재테스트도 수행")**:
  registry `frame_default_2026_09_09` / `frame_v5_2026_09_09`(run 34327549849). **실거래 무변경(관찰 기간).**
  · **결정**: ① B 벤치(같은 코인·달·레짐 무작위)는 판정에서 빼고 진단으로 병기 ② 레짐 조건부 셀은 n<200 이고 train 게이트
    탈락 사유가 boot_p 뿐이면 REJECTED 대신 **INCONCLUSIVE**(통과 아님, SMALL_N=200 은 내 값) ③ 홀드아웃은 **국면 기준(frame_v3)이
    기본** — validate_revival 은 이미 v3, validate_engulf_tf 는 FRAME_DEFAULT="v3" 로 전환. 게이트 v2 문턱·C2b·C3·PIT·Holm·E·0.4% 스트레스 불변.
  · **재실행 범위 원칙**: 프레임 변경은 후보 전체에 적용하되 **재실행은 '바뀐 층 하나로만 탈락했던 셀'에 한정** — 나머지를 다시 돌리면
    결과를 보고 셀을 고르는 것이 된다. 범위 = guard_v4 14셀(v5) · pit_cohort 11셀(B 가 판정 기준이었던 두 번째이자 마지막 시험, `--rules v5`) ·
    engulf_tf 4h 롱(달력 홀드아웃 하나로 탈락, `--frame v3`). 익절 3판·청산 변형·tb_wide(승률+홀드아웃)·late_entry·exit_1w(단일 해)·
    ma180(이미 v3, C2b 탈락)은 대상 아님.
  · **v5 결과 — CONFIRMED 2 / INCONCLUSIVE 2 / SHADOW 5 / REJECTED 5** (v4 는 CONFIRMED 0):
    **triple_bottom_4h|ALL → CONFIRMED**(OOS n=365 +1.59% bp .000, 비용 후 양수) · **vol_awakening_4h|ALL → CONFIRMED**(OOS n=2593 +0.21%
    bp .000 — 건당 얇음, 슬롯 점유는 이 프레임 밖) · **engulfing|bull_btc → INCONCLUSIVE**(train n=76 boot_p .376 뿐, OOS n=35 **+6.56%** bp .002
    — 판정 불가로 남는 유일한 강한 OOS 셀) · engulfing_short|bull_altseason → INCONCLUSIVE(단 OOS −0.15% bp .112 라 규칙 2 없이도 OOS 탈락).
    **equal_lows_4h|ALL 은 SHADOW 유지 — train(2025 이전 n=445) 게이트 boot_p .907**: OOS n=668 +0.97% bp .000 이 강한데 train 에 엣지가
    없다 = 2025~26 bear 단일 국면 엣지(revival v3 의 bear INCONCLUSIVE 와 같은 그림). ALL 셀이라 규칙 2 미적용. **사전 확률 'CONFIRMED
    유력' 오답** — 감사 L1 은 전체 표본, v5 는 train 분할이라 같은 층이 아니었다. 1d 라우팅 나머지(fvg/double_bottom/three_soldiers bull)는
    OOS A 음수라 B 제거로 못 살린다(사전 확률대로). REJECTED 5 는 전부 A_full 사유로 v4 와 동일.
  · B(진단)는 CONFIRMED 두 셀에서 +1.23% / −0.45% 로 부호가 갈린다 — 월 안 타이밍 검정이 수익성과 독립임을 재확인.
  · 두 CONFIRMED 셀은 이미 배포 중(revival §7·§8)이라 배포 집합 불변. 관찰 종료(10-06) 보고에 v5 판정 열 병기.
  validate_guard_v5.py / test_guard_v5.py(20) / guard_v5.yml
  · **pit_cohort v5 재판정 (run 34329267674)**: CONFIRMED 0(사전 확률대로), static/PIT STABLE 8 / SHIFTED 3. engulfing|bull_btc 는 두 판 다
    INCONCLUSIVE(PIT OOS +6.82% bp .007), engulfing_short|altseason 은 PIT 에서 SHADOW(train 게이트 — PIT OOS A +1.52% bp .026 은 통과),
    fvg|bull_btc PIT REJECTED(승률) 그대로. **B 제거가 바꾼 건 라벨뿐** — 1d 라우팅 셀을 막는 건 OOS A(2025~ bear)와 train 검정력이다.
  · **engulf_tf 4h 롱 국면 홀드아웃 재판정 (run 34329267607)**: bull_btc / bull_altseason / bear **3셀 전부 REJECTED**. 핵심은 bull_btc —
    n=561 +1.11% Holm .027 통과 · E 2/3 통과 · **국면 홀드아웃 n=317 +1.36% 통과(달력 판 −0.21% 가 뒤집혔다)** · 마찰 후 +0.71% 인데
    **train(n=244) 자체 게이트에서 탈락(사유 boot_p .156 하나, 재실행 34331332635 병기)**. 홀드아웃 반대는 해소됐고 남은 문제는 4h 이력이 bull_btc 에피소드 하나(2023-24)에 몰려 train 이
    얇다는 것(국면 홀드아웃이 표본 57% 를 삼킴). altseason 은 표본 전부가 홀드아웃(train 0)이고 boot_p .075 라 성능 우선 규칙으로 REJECTED
    (사전 확률 'INCONCLUSIVE' 는 규칙 순서를 놓침). bear 는 −0.12%. 재시험 조건: 4h 이력이 bull_btc 에피소드 3개 이상을 덮을 때. 배포 근거 없음.
    1차 출력이 train 탈락 사유를 안 찍어 병기 재실행(판정 동일). validate_engulf_tf.py(FRAME_DEFAULT=v3, judge_v3) / validate_pit_cohort.py(--rules v5)
- **사용자 강제 실행 — tp1_engulfing_1h, $30 (2026-09-09, 사용자 지시 "그냥 30달러만 강제 진행해볼수 있어? 지금 btc 들어가있는거 청산하고")**:
  registry `tp1_engulfing_1h`(status forced_live_user) / universe `adopted_1h_patterns`. **검증 미통과 규칙의 실거래 — 자율 반영 조항 밖, 사용자 결정 기록.**
  · 규칙: engulfing 1h 롱(디텍터 인자 없음, 1d 배포 신호 집합 불변) · 코호트 top20 · 레짐 무관 · 닫힌 봉 탐지 · **익절 +1% / 손절 −8%
    OKX OCO 브래킷**(exit_spec type `pct_barrier`, 2000봉 시간청산) · **$30 증거금 고정 · 3x · 한 번에 1포지션**(registry `live_cap`).
    사전에 물어 확정한 사양(BTC 는 앱에서 직접 청산 / 1%·8%·3x / engulfing 1h top20).
  · 기대값: tp_1h 실측 승률 88.00%(손익분기 91.11%), 건당 −0.28% ≈ 왕복 수수료 — 명목 $90 기준 약 −$0.25/건, 월 $5~10 소진이 기본값.
    관찰 목적은 실거래 승률·체결이 백테스트와 맞는지. **진입 30건 또는 10-06 에 대조 보고**, 정지는 사용자 결정.
  · 구현: `exit_barriers.py`(스케줄러·체결엔진 공용 배리어 산식 — 종전 ±k×ATR 인라인 두 벌을 한 곳으로) · `paper_executor.LIVE_CAPS`
    (고정 증거금·레버리지, risk_based_size·변동성 타겟팅·레짐 오버레이 우회, **MAX_LIVE_POS 슬롯 면제 + 자기 max_open**, 같은 종목·방향
    중복 방어 유지) · `barriers_of` 가 pct 배리어를 대칭 복원하지 않고 규격(+1%)으로 재구성(positions.target 컬럼 부재 대비) ·
    scheduler 1h adopted 에 `cohort` 적용 + exit_spec 패턴은 ts 있는 detlib 로더. cascade 배리어 수치·1d/4h 경로·사이징 상수 불변(test 고정).
  · **한계**: OKX 계약 단위(BTC 0.01·ETH 0.1)가 명목 $90 를 넘는 종목은 qty_below_lot_min 으로 자동 스킵 — 사실상 알트만 체결.
    positions 스키마 패치 미실행 시 entry_ts 유실 → 엔진 시간청산 보류(OCO 는 유효), cascade 와 같은 갭.
  · test_tp1_live.py(33) — eval_I(pct) 가 tp_1h 검증 프레임(crossings/_resolve)과 청산 봉·사유·수익률 일치 120/120.
  · **독립 프로젝트 + 복리 (2026-09-09 저녁, 사용자 지시 "중복으로 말고 계좌 내 1개 프로젝트로만 별도 관리 … 30+1퍼센트 복리로 계속")**:
    첫 신호(12:00Z LTC)가 메인 전략의 LTC 롱 때문에 중복 방어로 스킵된 것을 보고 내린 결정.
    · **복리 포트** `paper_executor.cap_margin`: 증거금 = 30 × Π(1 + ret×3) — 이 패턴의 방식D 청산 거래 전부. 익절 1건(+1% − 0.2%
      수수료 = +0.8%)×3x → +2.4%(30 → 30.72 → 31.46 …), 손절(−8.2%)×3x → −24.6%. 충전 없음, $10 미만이면 주문 안 냄(충전은 사용자).
      주문 실패 시 페이퍼 행을 만들지 않는다(DB trades 에 live_mode 컬럼이 없어 포트 계산이 장부 행을 그대로 읽기 때문).
    · **메인과 독립** `entry_blocked`/`dir_key_sets`: cap 신호는 메인 행이 같은 종목·방향을 들어도 진입(자기 max_open=1 만), 메인 신호는
      거래소 포지션이 cap 행만으로 설명되면 막지 않는다(장부에 없는 실포지션 방어는 유지). 같은 종목을 나눠 들면 OKX(net 모드)에서
      포지션이 합쳐지므로 **청산은 자기 계약 수만**(`close_qty_for` → `exchange.close_swap_position(qty=)`, 실포지션까지로 클램프).
    · **OCO 집행 확인** `settle_by_algo` + `exchange.algo_state`: 배리어 행은 매 틱 자기 algo 상태를 조회해 `effective` 면 그 체결가로 D
      기록(봉·entry_ts 무관). 이유 둘 — 나눠 든 종목은 포지션이 안 사라져 청산 이력(reconcile)으로 못 잡고, positions.entry_ts 컬럼이
      없어 eval_I 가 보류되면 max_open 이 영영 안 풀린다. D 청산 시장가 전에도 algo 가 effective 면 주문을 안 낸다(메인 몫 이중 청산 방지),
      조회 실패면 보류·재시도.
    · 같은 날 재진입: 중복 키가 봉 ts 라 청산 뒤 다음 봉 신호면 바로 진입. 메인 배포 집합·사이징·슬롯 불변(test_executor_safety).
  · **시작 증거금 $30 → $70 (2026-09-10, 사용자 지시 "증거금 367.46 USDT 추가입금했어 … 기본 포지션 스타트 금액 70으로 상향")**:
    registry `live_cap.margin_usd/start_margin` 70. 포트 = 70 × Π(1+ret×3), 손절 시 $70 리셋(익절 1건 70 → 71.68 → 73.40 …).
    명목 $210(3x) — 계약 단위 스킵 문턱이 $90 → $210 으로 올라 ETH(0.1 계약 ≈ $300~400)는 여전히 스킵, BTC 도 스킵. 규칙·경로 무변경, 금액만.
    포트는 거래 이력에서 매 실행 재계산하므로 상향 전 거래가 있어도 새 시작값 70 에 곱해진다.
- **무기한 펀딩비·OI 일별 적재 시작 (2026-09-08, 사용자 지시)**: registry `perp_accrual_2026_09_08`.
  perp_accrual.py / supabase_schema_perp.sql / test_perp_accrual.py(27건). **적재 전용 — 매매 코드는 이 테이블을 읽지 않는다.**
  · **왜 급한가**: 펀딩 이력은 OKX 가 약 3개월만 준다. **종목별 OI 는 스냅샷뿐 이력이 아예 없어** 지금 안 쌓으면 영구 손실이다
    (통화 단위 rubik 일별만 180일 백필 가능).
  · **호출이 싸다(실측)**: `funding-rate?instId=ANY` **1회로 458종목 전부**, `open-interest?instType=SWAP` 1회로 스냅샷 전부 —
    느린틱마다 2회·**1.1초**. 백필(종목별 160회·**약 64초**)은 oncefull 에서만, 상한 240초.
  · **[7] daily_summary 이후로 옮겼다** — 종전 funding_accrual 은 [2.5](주문 앞)에 있어 무거워지면 진입이 늦어진다.
    적재는 늦어도 되지만 주문은 아니다.
  · **두 OI 를 섞지 않는다**: `oi_snap_*`(그 종목 USDT 무기한 스냅샷·이력 없음) vs `oi_day_*`(rubik 통화 일별 = 해당 통화
    **모든 계약** 합산). 펀딩도 `funding_rate`(정산 평균)·`funding_n` vs `funding_snap`(현재기간 예상)로 구분.
  · **업서트 3분할** — 스냅샷/펀딩백필/OI백필을 컬럼이 겹치지 않게 따로 보낸다. 한 번에 섞으면 PostgREST 가 payload 키
    합집합으로 컬럼을 잡아 빠진 값이 NULL 로 덮인다.
  · **스모크에서 잡은 버그**: `_sym` 이 `[:-11]` 하드코딩이라(접미사는 10자) **'ETHW-USDT-SWAP' 이 'ETH' 로 잡혀 다른 종목
    데이터가 섞였다.** 80종목 중 5개만 매칭되던 게 단서. `len(SWAP_SUFFIX)` 로 교정 → 80/80.
  · **첫 실행(12:00Z) 적재 실패 — GRANT 누락**: `permission denied for table perp_daily` (42501).
    **RLS 정책이 아니라 테이블 권한 문제** — RLS 위반이면 'new row violates row-level security policy' 가 나온다.
    같은 실행에서 daily_summary UPSERT 는 성공했으므로 키·연결은 정상. 해결은 `supabase_grant_perp.sql`
    (`grant ... to service_role`) 1회. **'service_role 이 RLS 를 우회하니 그대로 된다'던 내 설명은 반쪽**이었다 —
    우회는 정책 평가를 건너뛸 뿐, 테이블 GRANT 가 없으면 여전히 막힌다.
  · **GRANT 실행 완료 (2026-09-09 사용자, SQL Editor)** — 그 전까지 9/08 12:00Z·16:00Z·20:00Z·9/09 00:00Z
    네 틱 모두 `permission denied` 로 적재 0 이었다(로그로 확인). 사용자가 **테이블 생성 SQL 은 9/08 오전에
    이미 실행**했고, GRANT 는 그 뒤 12:38 에 생긴 별개 파일이라 실행 전이었던 것 — 두 SQL 을 하나로
    합쳐두지 않은 내 구성 탓이다. **다음에 스키마 SQL 을 낼 때는 GRANT 를 같은 파일에 넣는다.**
  · **선결 해소 (2026-09-08 사용자 실행 완료)**: perp_daily·funding_daily 생성됨. RLS 를 켜도 적재는 그대로 —
    `supabase_client.get_client()` 기본이 role='service' 이고 service_role 은 RLS 를 우회한다(키가 잘못 꽂히면
    get_client 가 즉시 에러 → 조용한 실패 없음). 2026-09-04 의 supabase_schema_funding.sql 은 끝내 실행되지 않아
    나흘간 적재가 0이었는데, 새 SQL 이 그것까지 함께 만들어 해소했다.
- **스테이블코인 신호 소스 교체 — CoinGecko → DefiLlama (2026-09-08, 사용자 승인)**: registry
  `stablecoin_source_swap_2026_09_08`. CoinGecko `/coins/{id}/market_chart` 가 무료 티어에서 막혀 매 실행
  `7d=None%` 로 찍히고 있었다 — **신호가 사실상 죽어 있었다**. DefiLlama `stablecoincharts` 는 키 없이 열리고
  이력 3,206일. **정의·문턱 불변**(USDT·USDC 7일 시총 변화율 평균, ±3%), 출처만 교체. 실호출 +0.584%
  (USDT +0.049 / USDC +1.119). **표시 전용이라 매매 무영향** — 다만 집계 공급의 7일 변화는 ±3% 를 거의 못 넘어
  대부분 neutral 로 읽힌다. 이번 교체의 값은 판정이 아니라 **수치가 기록되기 시작한다는 것**(향후 연구용 축적).
  test_onchain_stable.py 15건이 파싱·문턱·폴백과 '매매 경로가 이 신호를 안 읽는다'를 고정.
- **멀티 TF 확증**: 1d 신호 → 4h 최근 3봉 확증. 비확증 시 **페이퍼** size 50% 축소
  (실주문에는 미적용 — 2026-09-03 확인. 확증 판정은 형성 중인 4h 봉 포함)
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
- [x] **변동성 타겟팅 사이징 채택 + 실거래 반영** (2026-09-04 사용자 결정) — 두 판 모두 4조건 통과.
      sizing.vol_scale / risk_based_size(vol_scale=) / paper_executor 진입 경로. **되돌리기는
      VOL_TARGETING=False 한 줄**
- [x] **위험 수준(RISK_FRAC) 1% → 1.5%** (2026-09-04 사용자 결정) — 사전 기준 미충족을 알고 내린
      낙폭 선호 결정(boot MDD중앙 -59.7%, p10 -80.5%). 최소주문 문턱은 $355->$237 로 개선
- [x] **LEV_CAP 2 → 3** (2026-09-04 사용자 결정) — risk 1.5% 에서 증거금이 제약이 되므로 상향.
      12슬롯 증거금 $450→$300, 청산거리 32.3%(손절의 4.0배)
- [ ] **equity $533 하한 주시** (2026-09-10 갱신 — risk 1% 하향으로 $355 → $533) — 전 신호 통과
      문턱이 $533 다. 계좌가 그 밑으로 내려가면 고변동 신호부터 주문이 안 나간다. 스킵 로그에 필요 equity 가 찍힌다.
      · **2026-09-12 00:06Z equity $561.96 — 여유 $29** (9/11 중 매매로 감소, 자금 이동 아님 — free 는 오히려 상승).
      · **첫 근접 사례 (2026-09-11 16:00Z)**: ETHFI **σ=190%/yr → 배율 0.45(하한)**, equity $569.06 에서
        명목 $32.06 · 증거금 **$10.69** 로 최소주문 $10 을 **$0.69 차로 통과**. 스킵은 아직 0건이지만
        equity 가 $533 밑이면 이 주문부터 끊긴다 — 사다리가 실측으로 확인됐다.
      · risk 1%/lev3 사다리: **최고변동(배율 0.45) $533 / 중간(1.00) $240 / 최저(1.80) $133 / 킬스위치 $100.**
        즉 $533 아래에서도 전면 중단이 아니라 **변동성 큰 종목부터 순서대로** 주문이 끊긴다.
      · **출금 판별법(기록)**: 격리마진에서 평가손은 free 를 안 건드린다 — free 와 equity 가 1:1 로 같이
        떨어지면 자금 이동, equity 만 떨어지면 매매 손실. 9/10 건이 이 서명으로 잡혔다.
- [x] bear fvg 롱 단일 셀 시험 (2026-09-05) — **기각**. 셀은 +1.63% 지만 포트폴리오 악화(holdout −43→−66%)
- [x] 종전 boot_p 재해석 (2026-09-05) — `_all` 재실행 PASSED 0→31 / STRICT 0→8. STRICT 8 확인 시험 → 7 기각 1 경계
- [x] method_b — beta_slope 2단계 (2026-09-05) — **기각**. 걸러진 거래가 +2.15% 로 양수(필터 부적합). 프레임 결함 기록
- [ ] **beta_slope 슬롯 우선순위 사전 등록** — 슬롯이 꽉 찼을 때 beta 상위 신호 우선. 선결: 실거래 MAX_POS 스킵 빈도 실측
- [ ] **오버레이 시험은 라우팅 복제 프레임으로** — method_b 가 무조건부 프레임(D CAGR −47%)에서 슬롯 아티팩트를 냈다
- [ ] **three_soldiers_4h top30 축소 사전 등록** (2026-09-05 신규) — 실거래 프레임 재판정에서 top30 PASSED /
      all REJECTED(med −0.49%). 실거래는 all 코호트에서 돎. 짝지음으로 코호트 축소 효과 측정
- [x] **확인 시험 C2 보강** (2026-09-06) — validate_ma180 의 **C2b**(train 자체 게이트 통과 AND train n ≥ holdout n/2)로
      첫 적용. vwap_rev_short_4h 가 표본 92% holdout 으로 통과한 구멍을 막는다. 다음 확인 시험 설계에도 그대로 이식
- [x] **MA180 사전 등록 결과 판독** (2026-09-06, run 34013456038) — **REJECTED**. train 은 강한데(엣지 +8.42%p, Calmar 2.85)
      holdout n=6 이 전부 손절 → C2 탈락. **사전 기대(bear 지배 해 탈락)와 일치.** 실거래 변경 없음
- [ ] **MA180 재시험 조건** — bull_btc 국면이 1년 이상 누적돼 holdout n≥10 이 될 때. 그 전 재시험은 무가치
- [ ] **ih / marubozu / three_soldiers_4h 1개월 실거래 관찰 (~2026-10-06, 사용자 결정)** — 정지하지 않고 유지.
      진입 건수·건당 수익·손절 비율을 누적해 관찰 종료 시 표로 보고 후 정지/유지 재결정. 백테스트 표본이
      답을 못 주는 셀(ih 무작위와 구분 불가, marubozu n=19)이라 실거래 표본으로 판단
- [x] **게이트 v2 재실행 + 배포** (2026-09-05) — triple_bottom_4h(ALL·top30)·equal_lows_4h(bear·top30) adopted_4h_patterns 등재
- [x] **breakout_retest_4h·ALL / vol_awakening_4h·ALL 확인 시험** (2026-09-05, run 33957277149) — **둘 다 기각**.
      breakout_retest holdout −0.41%(C2), vol_awakening 자산곡선 CAGR −6.3%(C3). n≈5천의 얇은 엣지 신호는 슬롯을 채우며
      자산곡선을 끌어내린다. 배포 집합 불변
- [x] **선별 완화(한 코호트 PASSED) 1d/4h 14셀 확인 시험** (2026-09-05, run 33960053517) — **0 CONFIRMED**. 가까운 셀
      inverse_hs_1d·bull_btc(C1 통과 Calmar 2.89)는 holdout n=12 전부 손절. equal_lows_4h·ALL 은 자산곡선 음수(bear 셀만 배포가 맞음)
- [x] **1h 8셀 확인 시험 판독** (2026-09-05, run 33961032437) — 0 CONFIRMED. bull_btc 셀은 holdout 거래 0(2026 bear) → 판정 불가
- [x] **MAX_POS 슬롯 격자 판독** (2026-09-05, run 33961480251) — 16: Calmar 1.85(=12) MDD −2%p 슬롯스킵 462→47
- [x] **MAX_POS 12 → 16** (2026-09-05 사용자 결정 "맥스포스 16으로") — paper_executor.MAX_LIVE_POS, sizing_study.MAX_POS 동기
- [x] **하모닉 5종 + triple_bottom_1w 인과 판 v2 재검증** (2026-09-05, run 33961480261) — **7셀 전부 REJECTED 유지**.
      탈락 사유는 전부 boot_p(.13~.58) 또는 평균 음수 — 승률 문턱과 무관. gartley_4h 인과 +0.66% bp .237, triple_bottom_1w
      인과 +3.65% bp .133. 룩어헤드 판은 여전히 +0.85~+3.09%p 부풀림. 등재 정지 유지, 복귀 후보 없음
- [x] **방식R 재판정(분기 승률 문턱 50%→35%, 사용자 결정)** (2026-09-05, run 33962938139) — **RL·RA 둘 다 REJECT 유지**.
      ④는 통과(RL 45%, RA 42%)하지만 ②CAGR 우위 3/7(기준 4/7)과 홀드아웃 ⑥(RL −0.18%p t −2.19)·⑦(분기 1승 11패)이 남는다.
      승률이 결정타가 아니었다. 방식D 유지
- [x] **4h C3 프레임 정정 → vol_awakening_4h·equal_lows_4h(ALL) 배포** (2026-09-05 저녁) — report_revival §8
- [x] **vol_awakening_4h 슬롯 점유 관찰 — 실측 (2026-09-09 00:00Z)**: **슬롯이 실제로 찼다.** XRP(marubozu) 진입으로
      16/16 이 되자 **EGLD(three_soldiers_4h)·DOT·ETC·ICP(vol_awakening_4h) 4건이 `최대 포지션(16개) 도달` 로 스킵**.
      우려대로 고빈도 4h 신호가 슬롯을 채우지만, 이번엔 **점수 순서 덕에 밀린 쪽이 D등급**이고 C등급 XRP 는 들어갔다
      (앙상블 점수 내림차순 진입이라 우선순위가 작동). 3틱 추이: 16:00Z 14/16 → 20:00Z 15/16 → 00:00Z 16/16 만석.
      · **증거금 스킵은 한 건도 없었다 — 슬롯이 먼저 막았다**(점검 항목 3 의 답). 다만 free 가 $50.57 → $30.96 까지
        내려왔고 포지션당 증거금 약 $25 라, 슬롯을 올려도 **증거금이 곧바로 다음 병목**이 된다(16×$25=$400 vs equity $435).
        MAX_POS 격자에서도 16→20/24 는 Calmar 1.85→1.83 으로 개선이 없다. **상향 권고 안 함**(위험 수준은 사용자 결정).
- [x] **포트폴리오 단위 확인 프레임 사전 등록** (2026-09-10 사용자 승인) — validate_portfolio.py.
      배포 집합 전체를 한 자산곡선에. arm = current / cap4·6·8(패턴별 슬롯 상한) / prio_edge(슬롯일당 기대값,
      인과적 확장추정) / cohort20. 판정은 holdout 포트폴리오 Calmar·CAGR J1~J5 전부. DEPLOY_ON_PASS=False.
      registry portfolio_prereg_2026_09_10. **결과 (run 34432328827) — 통과 arm 0, 현행 슬롯 배분 유지.**
      train 4210 / holdout 4239. holdout Calmar current **-0.63** vs cap4 -0.66 / cap6 -0.66 / cap8 -0.64 /
      prio_edge -0.66 / cohort20 -0.66 — **5 arm 전부 REJECTED**(J1·J2 실패, 부트 우위 52~69% 로 J3 문턱 60% 도 대부분 미달).
      prio_edge 만 train 에서 current 를 이겼고(Calmar 0.86 vs 0.82) holdout 최하위. **실거래 무변경.**
- [ ] **신규 4h 패턴 첫 실거래 관찰** — triple_bottom_4h 첫 진입 시 `[live 사이징]`·손절 algo·닫힌 봉 신호(rows[-2]) 확인.
      신호봉 종가 vs 체결가 슬리피지 기록
- [ ] **vwap_rev_short_4h · bear 경계 통과분** — 사용자가 켜라고 하면 켤 수 있음(regimes=["bear"], short,
      detector 에 load_ohlcv 추가 필요). 기대값 연 +1.65%, MDD −29%. 기본은 미반영
- [ ] **beta_slope vs avg_cap 상관 확인** — 레짐 축 진단에서 beta_slope 만 생존했으나 현행 avg_cap 이
      더 강하다(스프레드 +4.48 vs −4.73%p). 부호가 반대인 두 알트강세 축이 상충인지 상보인지 먼저.
      상관 높으면 재포장일 뿐 → 2단계 arm 제작 전 선결
- [x] **supabase_schema_perp.sql 실행 완료** (2026-09-08 사용자, SQL Editor) — perp_daily·funding_daily 생성됨
- [x] **supabase_grant_perp.sql 실행 완료** (2026-09-09 사용자, SQL Editor) — 테이블 GRANT 누락으로 네 틱 연속
      적재 0 이던 것 해소. **확인**: 다음 느린틱에 `[perp_accrual] 80행 — ok(스냅샷)`, 백필(펀딩 약 2,550행 +
      OI 약 14,400행)은 다음 oncefull(00:00Z)
- [x] **MAX_POS 슬롯 격자 결과 보고** (2026-09-10, run 33961480251 전체 표 판독 — 채택은 2026-09-05 에 이미 12→16):
      risk 1.5%/lev 3/vol_matched 고정, 라우팅 복제 990건. **8** 진입 633 슬롯스킵 696 증거금스킵 0 bootCAGR +86.5%
      MDD중앙 −55.6% **Calmar 1.59** / **12**(당시 현행) 742 / 462 / 125 / +105.6% / −58.4% / **1.84** /
      **16**(채택) 784 / **47** / 498 / +111.2% / −60.4% / **1.85** / **20** 788 / 32 / 509 / +113.1% / −60.4% / 1.83 /
      **24** 790 / **0** / 539 / +113.2% / −60.4% / 1.83. **동결 기준(MDD중앙≥−35% AND P(ruin)<5%) 통과 셀 0** —
      P(ruin) 은 전 셀 0.0% 이고 걸리는 건 MDD 뿐이라 **위험 1.5% 자체가 기준 밖**(격자·레버리지 판과 같은 결론).
      · **12→16 이 유일한 실질 변화** — 슬롯스킵 462→47, 진입 +42. Calmar 는 +0.01 로 사실상 동률이고 MDD중앙은
        −2.0%p 깊어진다(원 자산곡선 MDD 는 −67.7→−62.2% 로 반대 방향 — 판정은 부트 중앙값 기준).
      · **16 이상은 살 게 없다** — 20/24 는 진입 +6, Calmar 1.85→1.83, MDD중앙 동일. 슬롯스킵이 증거금스킵으로
        옮겨갈 뿐(498→509→539)이고 **포화는 24 에서**(슬롯스킵 0). 상향 권고 안 함은 이 표에서 나온다.
      · **12 부터 증거금이 병목으로 바뀐다**(증거금스킵 8:0 → 12:125 → 16:498). 슬롯을 올려도 계좌 크기가 먼저 막는다.
      · 8 은 명확히 열등(Calmar −0.25, 슬롯스킵 +234) — 낮추는 방향은 근거 없음.
- [ ] **고변동 신호 스킵 관찰** — 현 계좌 $276 에서 실측 약 12~15% 스킵(σ>약 124%/yr). **equity
      $400 을 넘으면 0% 로 소멸**하므로 기본 해법은 계좌 성장 대기. 실제 스킵 로그를 누적해
      예상과 맞는지 확인 (레버리지 상향은 sizing_study 상 MDD 악화라 기본 아님)
- [ ] 횡단면 모멘텀 재시험 (이력 누적 후 6개월~1년, 현재는 2024 이전 표본 자체가 없음)
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
- [ ] **supabase_schema_patch_2026_09.sql 실행** (사용자, SQL Editor) — 실행 전까지 entry_ts/tf/
      entry_regime 등이 복원 시 유실
- [x] **하모닉 5종 재검증 결과 판독** (2026-09-03) — 7셀 전부 인과 판 REJECT, triple_bottom_1w 도 정지
- [ ] **UNI(triple_bottom 1w 롱) 처리** — 패턴은 정지, 포지션은 D 규칙대로 유지 중. 수동 청산 여부는 사용자 판단
- [ ] **방식D 를 1d engulfing/fvg 외 배포 TF 에서 검증** (method_d 확장) — ih/marubozu/
      three_soldiers_4h/triple_bottom_1w 는 ±10%/20봉 라벨로만 통과
- [x] bear fvg 숏 OFF (2026-09-04) / 유니버스 N=80 적용 (2026-09-04)
- [x] 레짐 청산 소거 시험 유니버스 80종목 재확인 (2026-09-04) — 판정 A 동일, D_norg 결론 정정
- [x] **숏의 레짐 청산 재검토 (2026-09-04) — NOISE, 추격 중단.** 반증 4종 중 1개만 통과(그 1개도 부호 미요구 규칙 탓 무의미). bear 에서만 중립(+0.00%p)이고 bull_btc −0.05 / bull_altseason −2.67%p — 홀드아웃 관찰은 bear 국면 아티팩트. 숏 청산도 방식D 유지
- [ ] **three_soldiers_4h 재판정** — 레짐 베이스라인(같은 레짐 무작위 진입)으로 bull_btc 셀 bp .165. 원 프레임과 병기해 배포 유지 여부 판단
- [ ] triple_bottom top30 코호트 사전 등록 재시험 (데이터 누적 후, 현재 n=35 bp .078)
- [ ] 캐스케이드 1h 재검증 on 새 유니버스 (4단계) — 신규 24종목 1h 365일 수집 후
- [x] **v4 REJECTED 라우팅 셀 3 처리 → 사용자 결정 "현 상태에서 더 이상 끄지 않고 실거래로 1달 돌려본다" (2026-09-06)** —
      engulfing|bear 롱 / fvg|bull_altseason 롱 / three_soldiers_4h|bull_altseason 포함 배포 집합 전부 유지. 끄는 방법은 참고로 남김
      (direction_switch.ROUTING_OVERRIDES FLAT + adopted_4h regimes). **관찰 종료 2026-10-06** — ih/marubozu 관찰과 같은 날
- [ ] **tp1_engulfing_1h $70(9/10 상향 전 $30) 강제 실행 대조 보고** — 진입 30건 또는 10-06: 실거래 승률·건당·수수료 합·포트 잔액 vs tp_1h(88.00% / −0.28%). 정지·충전은 사용자 결정
      · **1건차 (LTC 롱, 2026-09-11 02:03Z 청산) — 익절.** 거래소 OCO 가 +1% 에서 체결(fill 52.88, 진입 52.372).
        가격수익 **+0.976%**(익절선 52.896 대비 0.03% 미끄러짐) → 수수료 0.2% 차감 **+0.776%** ×3x = 포트 **+2.33%**.
        복리 포트 **70 → $71.63**(무슬리피지 이상치 71.68 대비 −$0.05). OKX 실현 +$1.80. 청산 감지는 settle_by_algo 가
        아니라 reconcile-close(포지션 소멸) — LTC 는 메인과 안 겹쳐 정상 경로.
      · **2건차 (SOL 롱, 2026-09-11 13:03Z 청산) — 익절.** 진입 99.37 → 체결 100.29 **+0.93%**, 실현 +$2.90.
        포트 **71.63 → $73.19**. 단 메인 equal_lows_4h 와 같은 종목이라 합쳐진 OCO 가 메인까지 청산
        (registry `shared_symbol_oco_2026_09_11`).
      · **3건차 (ETH 롱, 2026-09-11 14:03Z 청산) — 익절.** 진입 2504.99(13:03Z) → 체결 2529.57 **+0.98%**,
        실현 +$8.01. 포트 **73.19 → 약 $74.90**(다음 진입 로그로 확인). 이것도 메인 equal_lows_4h 와 겹쳤다.
      · **누적 3건 3승** (tp_1h 검증 승률 88.00% 대비 표본 부족 — 판단 유보). 세 건 다 OCO 익절이 정확히
        +1% 부근에서 체결(미끄러짐 0.02~0.07%p).
- [x] **겹친 종목 OCO — 선택지 B 적용 (2026-09-12 사용자 결정 "b로 진행해줘")**: 겹친 종목에서는 체결가 기준
      배리어 재정렬을 **건너뛴다**(`paper_executor` 진입 경로 `_merged`). **코드를 읽고 9/11 의 B 설명을 정정했다** —
      `place_swap_entry` 는 OCO 를 `filled_qty` = **자기 계약 수**로 등록하므로(exchange.py:495) 진입 시점 OCO 는
      원래 올바르고, 망가뜨리는 건 재정렬 한 단계뿐이다(`replace={sym}` 으로 algo 둘을 취소하고 `p["qty"]` 전체에
      하나로 재등록). 따라서 건너뛰면 **진입 OCO(자기 계약 수)와 메인 자기 손절이 둘 다 산다** — 두 규칙이 검증된
      대로 돈다. 대가는 tp1 배리어 기준점이 체결가가 아니라 신호봉 종가라는 것뿐(실측 편차 SOL 0.05% / ETH 0.20%,
      둘 다 체결가가 더 낮아 롱에 유리했으므로 부호도 일정하지 않다).
      · **`entered_main_run` 이 필요한 이유** — `main_keys`·`okx_dir_keys` 는 실행 시작 스냅샷이라 **같은 실행에서
        메인이 먼저 들고 cap 이 뒤따르는** 경우를 못 본다. 9/11 SOL 이 정확히 그랬다(12:00Z 한 실행에서 #1 메인,
        #2 tp1). 이 집합은 **재정렬 판정 전용**이고 `entry_blocked` 에는 안 넘긴다 — 중복 방어 동작 불변.
      · **범위**: cap 진입에만 걸린다. 메인 1d/4h 는 exit_spec 이 없어 재정렬 블록을 안 타고, cascade 는 exit_spec 은
        있으나 cap 이 아니고 `entry_blocked` 가 메인 겹침을 이미 막으므로 동작 불변. **손절 주문 경로 무변경** —
        겹칠 때 메인 손절이 취소되지 않으므로 종전보다 오히려 보수적이다. test_tp1_live +13.
      · **남은 D 잔여(관찰 종료 후 별도 사전 등록)**: `ensure_stop_orders` 가 손절 **누락 시** 재등록할 때는 여전히
        `p["qty"]`(전체)를 쓴다. 겹친 종목에서 algo 가 사라지는 드문 경우에만 발생 — 2026-09-02 POL 수량 불일치와 같은 자리.
      · 기각: **A**(관찰 표본 오염 — 9/11 은 SHADOW 셀이 맞았지만 다음은 CONFIRMED 셀일 수 있다) · **C**(9/09 사용자가
        명시적으로 푼 독립성을 되돌림, 30건 대조가 어려워짐) · **D**(B 이후 추가 이득은 0.05~0.2% 기준점 하나인데
        대가로 손절 주문 경로 전체를 건드린다). 종전 기록:
- [ ] ~~**겹친 종목 OCO (2026-09-11 발견)**~~ — 위 B 로 해소. registry
      `shared_symbol_oco_2026_09_11`. tp1 과 메인이 같은 종목·방향을 동시에 들면 OKX net 모드가 포지션을 합치고,
      tp1 진입 시 '체결가 기준 배리어 재정렬'이 **합쳐진 수량 전체**에 stop 91.42 / **target +1%** OCO 를 다시 건다
      (`ensure_stop_orders` 가 `p["qty"]` = 거래소 포지션 전체를 넘긴다). 즉 **방식D 로만 검증된 메인 레그가 +1% 에
      잘린다.** `stop_map_of` 의 'target 은 exit_spec 패턴에만' 가드는 주기적 SL점검 경로만 덮고 진입 시 재정렬은
      자기 stop_map 을 직접 넘겨 지나친다. 손절은 걸려 있어 불변 안전장치 위반은 아니다(91.42 vs 메인 91.47).
      선택지 A(무조치)/B(겹치면 재정렬 스킵)/C(겹치면 tp1 스킵)/D(행별 수량으로 OCO) — **기록만, 실거래·코드 무변경**
      · **실측 2회 발동 (2026-09-11, 기록 1시간 안에)** — 둘 다 메인 **equal_lows_4h** 레그가 함께 잘렸다.
        **SOL 13:03Z** 메인 99.36 → 100.29 **+0.94%** 실현 +$2.90 / tp1 99.37 → +0.93% (포트 71.63 → $73.19).
        **ETH 14:03Z** 메인 약 2468.35(9/10 진입) → 2529.57 **+2.48%** 실현 +$8.01 / tp1 2504.99 → +0.98%
        (포트 73.19 → 약 $74.90). ETH 는 tp1 진입 시점에 메인이 이미 +1.5% 였고 합쳐진 OCO 가 거기서 끊었다.
      · **빈도 정정** — '겹치는 동안만'이라 적었으나 실제로는 **1시간에 2회**. tp1(top20)과 메인 배포 패턴이
        둘 다 유동성 상위에 몰려 겹칠 확률이 내가 암시한 것보다 훨씬 높다.
      · **아직 안 나온 나쁜 경우** — 두 사례 다 메인 진입가 M < tp1 진입가 P 라 메인이 더 벌고 끝났다.
        반대 배치(M > P×1.01)면 **메인이 손실에서 강제 청산된다**. tp1 의 engulfing 신호는 하락 뒤에 나오므로
        메인이 더 높이 먼저 들어가 물려 있는 조합이 오히려 자연스럽다 — 지금까지 이익으로 끝난 것은
        규칙이 안전해서가 아니라 표본 2건이 유리한 배치였기 때문이다.
- [ ] **실거래 1개월 관찰 보고 (2026-10-06)** — 패턴·레짐 셀별 진입 건수 / 건당 수익 / 손절 비율 / 슬리피지를 v4 OOS 수치와 나란히 표로.
      정지/유지 재결정은 사용자. 관찰 중 코드·라우팅·사이징 변경 없음(사용자 별도 지시 외)
- [ ] **B 벤치 사후 조건화 보완(다음 프레임 사전 등록)** — 같은 코인-월 풀을 신호 **이전** 봉으로만 제한한 변형(인과 B)을 병기.
      현 B 는 월 안 타이밍 검정이라 코인-월 선택 엣지를 못 본다
- [ ] **숏 라우팅 재판정** — 레짐 조건부 engulfing_short(bull_altseason)/fvg_short(bear) 셀을
      동결 게이트(median/boot_p/OOS)로. 통과 못 하면 숏 중단은 사용자 결정
- [ ] **형성 중인 봉 탐지 재검토** — 기존 배포 패턴은 아직 `rows[-1]`(미완성 봉)에서
      탐지한다. 검증은 닫힌 봉 기준이라 전반적 불일치. 영향 범위 측정 후 결정
- [ ] 캐스케이드 첫 실거래 후 체결 지연·슬리피지 실측 → 검증치와 대조
      (지연 1h 이내 / 마찰 왕복 0.4% 이내여야 함)
- [ ] 배포 후 캐스케이드 국면 실제 체결 슬리피지 실측 (내성 한계 왕복 0.4%)
- [ ] crab/shark/cypher 재시험 (데이터 누적 후)
- [ ] gartley_1h 재시험 (데이터 누적 후, 현재 boot_p=0.092)
- [ ] 데이터 부족 종목 재검토 (universe.json data_short 75종목, 6개월 후)

## 핵심 원칙
- **자율 반영 권한 (2026-09-05, 사용자 지시 "테스트 통과된 건 나한테 물어볼 필요 없이 바로 반영해도 돼")**:
  사전 등록된 기준을 **전부** 통과한 패턴·규칙은 사용자 확인 없이 실거래에 반영하고 master 에 병합한다.
  '통과' 의 정의는 바꾸지 않는다 — 동결 게이트 5조건 + 해당 시험의 사전 등록 확인 기준(holdout·자산곡선·
  두 코호트 등) 전부. 경계값·부분 통과·사후 기준 변경은 반영 대상이 아니다. 반영 후에는 무엇을 왜 켰는지
  보고한다. **여전히 사용자 결정으로 남는 것**: 위험 수준(RISK_FRAC/LEV_CAP/MAX_POS — 낙폭 선호 문제,
  통계가 답하지 않음) · 열린 포지션 수동 청산 · 자금 이동 · 게이트 문턱 자체의 변경.
  불변 안전장치는 권한과 무관: 손절 주문 없으면 실거래 없음 · 매매 결정은 결정론적 코드만 · tests.yml 그린.
- **게이트 v2 (2026-09-05 사용자 결정 "승률 35~45% 까지는 허용, 수익이 발생할 수 있으면 진행")**:
  n≥20, 평균수익>0, **승률≥35%**, 베이스라인 p<0.05, OOS 양구간 통과. v1 의 '중앙값>0' 은 방식D(−8% 손절)에서
  중앙값이 손절값에 붙어 사실상 승률 50% 이상을 요구했고, 승률 35~45% 로 수익을 내는 추세·돌파형을 구조적으로
  막았다(report_revival.md: 1d 후보 전 셀 median −8.20%). 구현은 `gate.dist_ok` 한 곳 — 검증 모듈은 자체 판정을
  두지 않는다(test_gate 가 고정). 복권형 방어는 boot_p·OOS·holdout·자산곡선이 맡고 절사평균·상위5기여도는 진단
  병기. 확인 단계 C1 도 같은 날 '두 코호트' → '실거래 코호트(top30)' 로 완화(내가 얹었던 조건).
  **v1 기록**: 2026-06 ~ 2026-09-05 의 모든 판정은 median>0 기준 — 그 시기 리포트를 v2 잣대로 읽지 말 것.
- **확인 프레임 기본값 (2026-09-09 사용자 결정 ①②③ — "3번 국면 홀드아웃 기본 전환")**: 새 사전 등록은 전부
  ① B 벤치(같은 코인·달·레짐 무작위)는 **진단**만, 판정 기준 아님 ② 레짐 조건부 셀이 n<200 이고 train 게이트 탈락
  사유가 boot_p 뿐이면 **INCONCLUSIVE**(통과 아님, `validate_guard_v5.SMALL_N`) ③ 홀드아웃은 **국면 기준**(`frame_v3`:
  셀 레짐으로 라벨된 최근 365일, ALL 은 달력 365일, E 에피소드 OOS + COV) — 달력 마지막 365일은 레짐 조건부 셀에서
  '규칙이 틀렸다'와 '채점 구간에 그 국면이 없었다'를 못 가른다. `--frame` 이 있는 모듈(validate_revival / validate_ma180 /
  validate_engulf_tf)은 기본 v3, v2 는 재현용 인자. 게이트 v2 문턱·C2b·C3·PIT 코호트·Holm·0.4% 스트레스는 불변.
  **재실행 원칙**: 프레임이 바뀌면 '바뀐 층 하나로만 탈락했던 셀'만 다시 돌린다 — 나머지를 다시 돌리면 결과를 보고 셀을
  고르는 것이 된다(2026-09-09 범위: guard_v4 14셀 → v5 / pit_cohort 11셀 → `--rules v5` / engulf_tf 4h 롱 → v3).
  달력 홀드아웃만 있는 종료된 시험(tb_wide·tp_*·late_entry·exit_1w·routing)은 홀드아웃 외 사유로 끝났으므로 그대로 둔다.
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
- method_r.py: 방향 인지 레짐 청산 시험 (D vs R1/R2, 분기 거래·불리국면 진입 부분집합). 기각 기록용.
  report_regime_exit.md
- paper_executor.eval_R / shadow_r_records: 방식R(롱 한정) 그림자 장부 — 2026-09-03 이후 D 롱 거래에
  R 청산을 나란히 기록(주문 무관). test_shadow_r.py 가 검증 프레임과의 일치·기록 전용 성질을 고정
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
- universe.json: 80종목 유니버스 (trading_universe, 2026-09-04 무기한 거래대금 기준, universe_basis_2026_09_04), data_short 75종목, rejected 20종목
- sizing.py: 실거래 사이징 원본 — risk_based_size(vol_scale=) + realized_vol/vol_scale(변동성 타겟팅,
  2026-09-04 채택) + min_equity_for(스킵 문턱). 연구 모듈이 이 함수들을 import 한다
- report_leverage_2026_09.md: 레버리지·위험 격자 — 레버리지 상향 권고 안 함, 위험은 낙폭 선호 문제
- sizing_vol.py: 변동성 타겟팅 사이징 시험 (risk/vol_raw/vol_matched, 노출 정합 가드). `--grid` 는
  (risk x lev) 격자(sizing_grid.json, 스킵을 슬롯/증거금으로 분리). `--routing` 은
  실거래 라우팅 복제 판(sizing_vol_routing.json) + s_norm·계좌규모별 스킵 비율 출력 — report_quant_batch1.md
- test_sizing_vol_live.py: 채택분 고정 — 연구/실거래 구현 동일성(`is`), 배율이 명목가에만 걸리는지,
  폴백 3종, 문턱 함수가 실제 스킵 경계와 일치, 동결 파라미터·상수
- validate_xsec_momentum.py: 횡단면 모멘텀 단독 진입 (동결 게이트 + 추세·포트폴리오 진단). 기각 기록용
- validate_short_exit.py: 숏 레짐 청산 반증 4종(시간분할/부트CI/롱 대조군/레짐층화). 기각 기록용
- method_s.py: 레짐 청산 소거 시험 (D vs 제거/보유상한/셔플 대조군). `--universe` 로 80종목 재확인. report_regime_exit_ablation.md
- regime_alt.py / regime_quality.py / method_q.py: 레짐 라벨러 후보·라벨 품질 벤치마크·짝지음 시험(기각 기록용). report_regime_quality.md
- validate_regime_split.py / validate_regime_split_all.py: 레짐별 분리 게이트(배포 6종 / 기각·정지 55종). report_regime_split(_all).md
- method_b.py: beta_slope 오버레이(B_skip/B_size) 짝지음 시험 — 기각 기록용. report_beta_overlay.md
- validate_band_rule.py: 고정 띠 규칙(손절 → 진입가 복귀 재매수)의 체결 마찰 3종 사전 등록 시험 — 지연 δ / 장중 재교차 / 바스켓. 판정 VIABLE, 배포 없음. test_band_rule.py(20)
- validate_breadth_state.py: 알트 폭 '상태'(며칠째·몇 %·몇 개) → 선행 60봉. 관측 단위가 하루라 에피소드 진행 중 적용 가능. 판정 NONE(넓은 프로필 IC 20셀 전부 음수). test_breadth_state.py(24)
- validate_episode_profile.py / validate_signal_profile.py: 상승 에피소드 승자 프로필(전 코인, data-long) / 신호봉 승자 프로필(배포 셀). 서술·후보 탐색용, 규칙 승격 없음
- build_data_long.py: 장기 1d 수집 — `--okx-all --shard i/n --skip-existing --out` 로 OKX 무기한 전 종목 병렬 수집(data-long 브랜치 248코인). master data_long/ 은 81
- xsec_features.py / validate_xsec_chars.py: 횡단면 특성 연구(24 상태 변수 fwd20 순위 IC, 인과 피처·PIT 유니버스·월 부트·Holm). rvol20 만 순위 예측, 선택 규칙 승격 없음. test_xsec_chars.py(57)
- validate_pit_cohort.py: PIT 코호트(월말 30일 거래대금 → 다음 달 적용) static vs PIT 재검증 + 코인별 분산 + 무조건부 스캔. test_pit_cohort.py(25)
- validate_guard_v4.py: 확인 프레임 v4 = 3중 대조(A 레짐·코호트 / B 같은 코인·월·레짐 / C 시간 OOS 2025-01-01) + 월 클러스터 부트 + Holm +
  비용 스트레스 + 진단 D1~D4. 사전 등록 registry guard_v4_prereg_draft_2026_09_06. DEPLOY_ON_PASS=False. test_guard_v4.py(41)
- validate_revival.py: 선별(validate_regime_split_all STRICT)을 통과한 후보를 **실거래 프레임**(방식D/ATR·레짐
  조건부·같은 청산 규칙 베이스라인·실거래 사이징)으로 확인. `--new` 는 신규 디텍터 전 셀. report_revival.md
- detector_ibs_low / rsi2_low / down_streak3 / donchian20.py: 2026-09-05 신규 후보 4종 — **전부 rejected**, 미등재
- validate_routing.py: 진입 **방향** 라우팅 arm 시험 (route/uncond/gated/route_bfl). 청산은 세 arm 모두 방식D 동일.
  arm 마다 신호 집합이 달라 짝지음이 안 되므로 **같은 시간 블록을 재표집**해 비교(paired_block_boot).
  자산곡선은 method_x.equity_curve 를 공통 창(span_days)으로 호출. report_routing_gate.md
- direction_switch.py: 레짐→방향 라우팅. ROUTING_OVERRIDES 가 코드 예외(bear fvg FLAT). test_direction_switch.py
- expand_universe.py: 유니버스 확대 스크립트 (업비트KRW∩OKX선물, 재실행 가능)
- report_universe_expansion.md: 유니버스 확대 리포트
- validate_portfolio.py: 포트폴리오 단위 확인 프레임 — 배포 집합 전체를 한 자산곡선에 올려 **슬롯 배분 규칙**만
  바꿔 비교(current / cap4·6·8 / prio_edge / cohort20). 사이징·청산은 실거래 고정. 패턴 단독 C3 가 못 보는
  슬롯 경합이 대상. 사전 등록 registry portfolio_prereg_2026_09_10, DEPLOY_ON_PASS=False. test_portfolio.py
- paper_executor.slot_occupancy / occupancy_txt: 슬롯 점유 패턴 분포 — 진단 출력 전용(2026-09-10)
- registry.json: 패턴 등록부 (2026-09-03: 하모닉 5종 + triple_bottom_1w suspended_lookahead → 배포 중
  1d×4(engulfing/fvg/ih/marubozu) + 4h×1(three_soldiers) + 1h×1(cascade))
- regime_multi.py / method_m.py: 레짐 스케일(주봉/4h) 연구 — 기각 기록용. report_regime_scale.md
- validate_confirm_bar.py / test_confirm_bar.py / revalidate_confirm_bar.yml: 룩어헤드 제거 재검증
- test_executor_safety.py / test_regime_determinism.py: 2026-09-03 점검 수정분 고정
- supabase_schema_patch_2026_09.sql: 매매 DB 컬럼 보강(사용자 실행)
- report_audit_2026_09.md: 전체 점검 결과·수정·보류 목록
- test_cron_split.py: 매시 크론이 배포 패턴 동작을 바꾸지 않음을 고정 (게이팅/닫힌봉/재정렬)
- supabase_external_trigger.sql: GitHub 크론 누락 대체 — Supabase pg_cron 이 매시/4h
  `workflow_dispatch` 호출. Vault PAT, gh_dispatch_log. test_external_trigger.py 가 레포와 정합 고정
- elliott_detect.py / terminal_detect.py: **미검증·실거래 미등재** (2026-09-04 파일 상단 주석으로 고정).
  게이트를 통과한 적이 없고 registry/universe/scheduler 어디에도 없다. 다만 죽은 코드는 아니다 —
  zigzag/Signal/Pivot 을 triple_bottom_volume(=triple_bottom_desc, rejected) · breakout_indicators ·
  reversal_patterns 가 import 한다. 엘리엇 하위구조(지그재그·플랫·다이애고널·삼각형)의 환원 개념은
  이미 별도 디텍터로 전부 시험해 기각(liquidity_sweep=가짜돌파반전, bb_squeeze·nr7=변동성수축돌파,
  rsi_divergence·macd_divergence=모멘텀 약화). **신규 검증 대상 아님.** 배포 목록 출처는 registry.json
- method_x.py: 청산 변형 시험 (ATR 손절/조건부 시간손절/구조적 손절). **자산곡선이 arm 의 stop_pct 를
  사이징에 반영** — method_t.equity_curve 와 달리 실거래 risk_based_size 를 쓴다. 기각 기록용
- regime_axis.py: 레짐 추가 축 1단계 진단 (adx/er/volpct/alt_breadth/beta_slope + 비교기준 avg_cap).
  3분위 A∧B∧C. 2단계는 통과 축이 나왔을 때 별도 사전등록
- triangle_census.py: 4파 삼각수렴 후보 **개수만** 세는 실현가능성 조사 (전략 구현 아님)
- funding_accrual.py / supabase_schema_funding.sql: 펀딩비 일별 적재 (시험용 축적 전용, 매매 무관)
- report_exit_regime_axis.md: 위 3종 판정 + 검토 중 확인한 레포 사실(docs/research 부재, Signal
  인터페이스 이중화, 봉 데이터 DB 미저장, OI 수집 없음)
- research_log.csv: 106건 시험 기록
- detector_three_soldiers_4h.py: 3연속 장대 양봉 (4h, PASSED)
- detector_three_soldiers_1h.py / detector_three_crows_1h.py: 1h 버전 (검증용)
- detector_vwap_rev_long/short_1h.py / detector_breakout_retest_1h.py: 1h 기각
- report_4h_expansion.md: 4h 확장 + Three Crows 레짐 재검증 리포트
- report_1h_expansion.md: 1h 확장 리포트 (bat/butterfly 통과)
