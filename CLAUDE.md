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
  · **레짐 라벨러 강화 연구 REJECT (2026-09-04, 사용자 지시 "레짐 정확도를 올릴 변수 추가")**: report_regime_quality.md.
    breadth/vol/funding 신호로 라벨러 6후보(fast_slope/breadth_price/vote4/vol_side/funding_cap/breadth_only) —
    1단계 라벨 품질(분리폭·적중·지연·flips, 사전 규칙 4개) **후보 0**, 2단계 짝지음 19 arm **전부 REJECT**.
    **핵심 발견: 현행 레짐은 20일 지평 방향 예측력 ≈0** — 적중 49%, bear 라벨 날 선행수익 +0.04%, bull 3년
    연도별 분리폭 음수(−20.9/−7.2/−4.3), 전환 지연 평균 50일·중앙 72일(28회 중 13회 90일 내 미포착).
    라벨을 빠르게 하면(D_*) D 의 레짐 전환 청산이 잦아져 전부 악화 — 레짐의 기여는 예측이 아니라 청산
    트리거·셀 분리. **'레짐을 예측기로 쓰지 말 것'**이 결론. D_vote4 train t 2.54 이나 holdout 분기 0건,
    F_*(bear 롱 차단)는 train 손해·holdout(bear 해) +1%p 단일국면. funding 은 OKX 이력 94일뿐(미검증).
    regime_alt.py / regime_quality.py / method_q.py / test_regime_quality.py(43건) / regime_quality.yml
  · **bear fvg 숏 OFF (2026-09-04, 사용자 결정 "bear 숏 끄고")**: `direction_switch.ROUTING_OVERRIDES`
    {(bear, fvg): FLAT}. main() 이 매 실행 regime_switch.json 의 무조건부 n≥20·mean>0 로 표를 다시
    만들므로(bear fvg 숏 +2.54% 로 여전히 short) JSON 편집은 무효 → 코드에 예외를 둔다. bear fvg 롱
    (엣지 +1.34%p)은 동결 게이트 미통과라 켜지 않고 FLAT. 현 레짐이 bear 라 즉시 효력 — bear 에서는
    engulfing 롱만 나간다. 나머지 5셀 유지. test_direction_switch.py(20건) 가 고정.
- **1h 추가 기각** (2026-07-03): bb_zscore_1h·rsi_extreme_1h 롱/숏 4방향 전부 REJECTED
  (mean 음수, boot_p 0.42~0.60, 저볼륨 필터로도 미달 — registry rejected_1h 14건)
- 유니버스: **80종목** (OKX 무기한 30일 거래대금 상위 80, 2026-09-04. 종전 업비트KRW∩OKX선물 71→67)
- **패턴별 차등 유니버스** (2026-07-06 사용자 결정, 거래대금 코호트 분석 기반):
  engulfing→top20, fvg→top30 (30일 평균 거래대금 상위, 매 실행 재계산),
  inverted_hammer/marubozu→메이저 7종목 (scheduler.PATTERN_UNIVERSE).
  근거: 코호트 분석 — engulfing top20까지 엣지 유지(+2.65%/중앙+9.9%), fvg top30이
  전체보다 질 우위(+2.36%/중앙+6.5%), ih·marubozu는 top7 밖 급감/불안정.
  하모닉 4h·1h 패턴은 기존 검증 유니버스 유지. 경계 과적합 주의 — 분기별 재점검 권장
- **자동화**: `daily_scheduler.yml` **4h**(`0 */4`, --slow, oncefull@UTC00:00) +
  `fast_scheduler.yml` (--fast, exit_spec 패턴만, **schedule 없음**). 2026-09-02 분리.
  **발화는 Supabase pg_cron → workflow_dispatch**(fast 매시 :03 / daily 정각) —
  daily 만 GitHub schedule 폴백 유지. 발화율 측정 시 dispatch 이벤트 포함
- **실거래 안전장치** (2026-07-06): MAX_LIVE_POS 12(사용자 승인 5→12) ·
  킬스위치(equity < $100 → 신규 진입 중지, paper_executor.EQUITY_FLOOR —
  2026-08-29 사용자 지정 절대 하한. 기존 HWM 대비 -20%($230.06) 규칙은 폐기) ·
  손절 algo 주문 매 실행 자동점검(ensure_stop_orders — 누락 시 재등록 +
  포지션 없는 고아 주문 취소, 주문은 reduceOnly 청산 전용. 2026-08-29) ·
  텔레그램 알림(notify.py — TELEGRAM_BOT_TOKEN/CHAT_ID secrets 등록 시 활성)
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
- [ ] **three_soldiers_4h 재판정** — 레짐 베이스라인(같은 레짐 무작위 진입)으로 bull_btc 셀 bp .165. 원 프레임과 병기해 배포 유지 여부 판단
- [ ] triple_bottom top30 코호트 사전 등록 재시험 (데이터 누적 후, 현재 n=35 bp .078)
- [ ] 캐스케이드 1h 재검증 on 새 유니버스 (4단계) — 신규 24종목 1h 365일 수집 후
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
- regime_alt.py / regime_quality.py / method_q.py: 레짐 라벨러 후보·라벨 품질 벤치마크·짝지음 시험(기각 기록용). report_regime_quality.md
- validate_regime_split.py / validate_regime_split_all.py: 레짐별 분리 게이트(배포 6종 / 기각·정지 55종). report_regime_split(_all).md
- direction_switch.py: 레짐→방향 라우팅. ROUTING_OVERRIDES 가 코드 예외(bear fvg FLAT). test_direction_switch.py
- expand_universe.py: 유니버스 확대 스크립트 (업비트KRW∩OKX선물, 재실행 가능)
- report_universe_expansion.md: 유니버스 확대 리포트
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
- research_log.csv: 106건 시험 기록
- detector_three_soldiers_4h.py: 3연속 장대 양봉 (4h, PASSED)
- detector_three_soldiers_1h.py / detector_three_crows_1h.py: 1h 버전 (검증용)
- detector_vwap_rev_long/short_1h.py / detector_breakout_retest_1h.py: 1h 기각
- report_4h_expansion.md: 4h 확장 + Three Crows 레짐 재검증 리포트
- report_1h_expansion.md: 1h 확장 리포트 (bat/butterfly 통과)
