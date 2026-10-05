# 최상위 트레이더 매매 규칙 조사 — 레포 대조와 추가 후보 (2026-10-04)

대표님, 13개 트레이더 집단의 규칙 241건을 레포와 대조했습니다. 결과는 아래와 같습니다. 이번 조사로 실거래는 아무것도 바뀌지 않았고, 관찰 기간(~2026-10-06) 중이라 바꾸지도 않습니다.

## 0. 한 줄 결론

최상위 트레이더들의 규칙 대부분은 레포에 이미 들어와 있거나 이미 시험해서 기각됐습니다. 미시험·부분시험 후보 140건(미시험 36 + 부분시험 104)에 반증 3렌즈를 적용했고 44건이 남았습니다. 그러나 사전 확률 상위 5개는 전부 **새 엣지가 아니라 연구 위생 감사이거나 위험 수준 선택**입니다. 매매 규칙 후보 가운데 가장 높은 것도 Turtle Soup 17%, 터치 횟수 열화 15%, 낙폭 사다리 15% 정도입니다.

## 1. 방법

- **수집 그룹 13개**: 터틀·추세추종 CTA / 글로벌 매크로 디스크리셔너리 / 주식 모멘텀·돌파(CANSLIM 계열) / 시스템 트레이딩 프레임워크 저자 / 포지션 사이징·리스크 이론가 / 크립토 네이티브 / Market Wizards 종합 + 단기 시스템 / 아시아 전설 개인·프롭 / CTA·기관 리스크 데스크 / 옵션·변동성 매도자 / 대형 파산 사례(역교훈) / 백테스트 강건성 방법론 저자 / 캐리·베이시스·통계적 차익.
- **대조 절차**: 규칙마다 범주(진입·청산·손절·사이징·포트폴리오 위험·낙폭 통제·레짐 필터·타이밍·피라미딩·유니버스·프로세스·심리)를 붙였습니다. 그다음 레포의 코드, registry 키, research_log, report_*.md 와 맞춰 상태를 매겼습니다. 상태는 adopted / tested_rejected / tested_partial / untested_testable / untestable_discretionary / violates_invariant / data_missing 7가지입니다.
- **반증 3렌즈**(미시험·부분시험 후보 140건에만 적용):
  - ① **커버리지**: 이웃 시험이 이미 같은 기전을 덮었는가. 덮었다고 보면 상태를 정정합니다.
  - ② **실현성**: 데이터가 있는가, 결정론적인가, 불변 안전장치를 지키는가, 사전 등록과 실거래 경로가 가능한가.
  - ③ **사전 확률**: 레포의 기존 실증과 비교한 통과 확률. 15% 미만이면 반증으로 칩니다.
  - **생존** = 반증된 렌즈가 1개 이하.
- **웹 접근 상태**(그룹별):

| 그룹 | 상태 | 비고 |
|---|---|---|
| 터틀·CTA | ok | Turtle Rules·JWH 1998·DUNN·Covel PDF 를 로컬 추출. turtletrader 400, thebiggers 404, dunncapital 403 → 대체 소스. Basso 수치는 2차 문헌 |
| 글로벌 매크로 | ok | Market Wizards(1989)·HFMW(2012) PDF 판독. Druckenmiller NMW 는 2차 재현 2건. Bacon 은 2차·동료 전언 |
| CANSLIM 계열 | partial | Qullamaggie·Zanger·Brandt 는 1차. Livermore PDF 404, MW 503, Minervini·O'Neil 페이지 403 → 책·2차 요약 |
| 시스템 저자 | partial | Carver·Clenow·Chan 블로그, Kaufman·Antonacci 인터뷰. optimalmomentum 403. Carver 책 세부는 2차·기억 |
| 사이징 이론가 | partial | vantharp·Bandy github·Universa 접근. multicharts 520, wealth-lab 503, Thorp 1997 장은 스캔본 |
| 크립토 네이티브 | partial | GCR·Cobie·Light·Hsaka·Hayes 1차. CryptoCred Medium 403 → 기억 |
| MW 종합·단기 | partial | macro-ops·oxfordstrat 등. quantifiedstrategies·schwab 403, Street Smarts PDF 503 → 일부 책·기억 |
| 아시아 | partial | BNF·cis·テスタ·SMB·FTMO 1차. zhihu·dcinside 403. 워뇨띠·赵老哥는 커뮤니티 전사라 인용 정확도 한 단계 낮음 |
| CTA·기관 데스크 | ok | Winton·Turtle·Campbell·AHL·Bridgewater PDF 추출. man.com 403 |
| 옵션 매도자 | partial | tastytrade·LJM·XIV 는 검색 확인. Natenberg·Bennett·Sinclair 본문은 기억 |
| 파산 사례 | partial | SEC·Senate PSI·PWG 요약. 1차 PDF 전문은 미판독 → 일부 기억 |
| 방법론 저자 | partial | 논문 공식 위주 |
| 캐리·차익 | partial | GGR Wharton 503. AL·Vidyamurthy PDF 파싱 실패 → 창 길이·κ 필터·Kelly 등은 기억 |

## 2. 집계표

| 상태(매핑 단계) | 건수 |
|---|---|
| adopted (이미 실거래·연구 체계에 있음) | 50 |
| tested_rejected (시험 후 기각) | 21 |
| tested_partial (일부만 시험) | 104 |
| untested_testable (미시험·시험 가능) | 36 |
| untestable_discretionary (재량, 코드화 불가) | 11 |
| violates_invariant (불변 안전장치 위반) | 4 |
| data_missing (데이터 없음) | 15 |
| **합계** | **241** |

| 반증 3렌즈 | 건수 |
|---|---|
| 렌즈 대상(미시험·부분시험 후보) | 140 |
| 생존(반증 ≤1) | 44 |
| 탈락(반증 ≥2) | 96 |
| 세 렌즈 모두 통과 | 4 (Turtle Soup, 터치 횟수 열화, PBO, 가격 경로 순열) |

커버리지 렌즈는 매핑 단계 상태를 상당수 정정했습니다. 예를 들어 tested_partial 로 붙은 Clenow EMA50/100 필터는 F_slow 기각 가족이라 tested_rejected 로, Kovner 범위 확장 돌파는 vol_awakening_4h 배포 중이라 adopted 로 바꿨습니다. 위 표는 정정 **전** 수치입니다.

## 3. 이미 레포가 하고 있는 것 — 최상위 트레이더들과 일치하는 규칙

| 규칙 | 누가 말했나 | 레포 구현·파라미터 (비고) |
|---|---|---|
| 건당 위험 = 자본의 고정 %, 수량 = 위험 ÷ 손절거리 | Tharp, Basso, Hite, Kovner, Marcus, Minervini, Ryan, CryptoCred, Williams | sizing.risk_based_size, RISK_FRAC 0.015, 손절 8% (Tharp·Hite 상한 ≤1% 보다 큼 — 사용자 낙폭 선호, risk_level_2026_09_18) |
| 변동성 단위 사이징 | Turtles(N), Carver, Clenow, MOP/AQR, Basso, Winton, Hull | sizing.vol_scale = clip(0.80/σ20, 0.5, 2.0)/1.1094, 두 프레임 4/4 (quant_batch1_2026_09_04, 재확인 run 35572055349). 실거래 손절 RAY −$2.40 vs 예산 $2.56 |
| 손절은 진입 전에 확정하고 거래소에 건다 | Tharp, Williams, Kovner, O'Shea, Schwartz, Raschke, Ellison(역교훈), Niederhoffer(역교훈) | 불변 안전장치. place_swap_entry 가 손절가를 사전 검증하고 sl_failed 면 진입을 되돌림. ensure_stop_orders 는 매 실행 |
| 물타기 금지 | PTJ, Livermore, O'Neil, Marcus, Steinhardt, cis, テスタ, 赵老哥, 炒股养家, SMB, 3AC·Amaranth(역교훈) | 추가 매수 경로 없음. live_dir_keys·_is_dup_entry 가 같은 종목·방향 재진입 차단 (예외: tp1 cap 프로젝트) |
| 익절 목표 없음, 이익을 달리게 둔다 | Marcus, Soros, Turtles, Parker, Hite | 방식D(손절·반대신호·레짐 전환·30봉, 목표 없음). 익절 6가족 기각이 뒷받침 |
| 총 명목 레버리지 상한 (변동성이 낮다고 늘리지 않음) | LTCM·Archegos·MF Global(역교훈) | MAX_TOTAL_NOTIONAL_FRAC 2.50, LEV_CAP 3, MAX_LIVE_POS 13 |
| 청산가를 정상 변동성 밖에 둔다 | Cobie, Light, GCR, BIS 'Crypto carry' | LIQ_SAFETY 2.0 → lev3 청산거리 32.3% = 손절의 4.0배 |
| 격리 마진, 한 포지션이 다른 포지션 증거금을 못 빨아감 | MF Global·Celsius(역교훈) | exchange.OKX_MARGIN_MODE='isolated', FREE_USE_MAX 0.95 |
| 파산 확률 > 0 인 베팅 금지 | 워뇨띠, Vince | 동결 사이징 기준 boot MDD 중앙 ≥ −35% AND P(ruin) < 5% (현행 1.5% 는 기준 밖임을 기록. Davey 의 '어느 크기로도 기준 미달이면 매매 중단'(return/DD≥2)은 미채택) |
| 강제 청산 매도자에게서 산다 | Cobie | cascade_fade_long_1h 배포 (n=312 +2.43%, 실측 지연 판 +1.54%) |
| 저시총 공매도 금지, 유동성 상위만 | GCR, O'Shea, Bacon, Trout | 코호트 top20/top30/메이저 7, 유니버스 80 (거래대금 순위) |
| 매크로 디스크리셔너리 → 결정론적 코드, 오버라이드 금지 | Simons, Parker, JWH, Hite, Dunn | '매매 결정은 결정론적 코드만' 불변. 엘리엇 브리핑은 매매 경로와 단절 |
| 진입 전에 계획을 문서화한다 | Cobie, Talbot, SMB, Niederhoffer(가설 계수) | 사전 등록 프로토콜(*_prereg_* 39건), DEPLOY_ON_PASS=False |
| 비용 포함, 2배 비용 스트레스 | Pardo, Davey, Aronson | FEE 0.2% 왕복 + 0.4% 스트레스 상시, 펀딩 비용 측정 (funding_cost_prereg_2026_09_21) |
| 최소 표본·자유도 | Pardo | gate.MIN_N 20 (Pardo ~30 보다 낮음), SMALL_N 200 INCONCLUSIVE |
| 위험 규칙은 포트폴리오 CAGR 로 판정 | Spitznagel, Taleb | C3 자산곡선(실거래 사이징), validate_portfolio J1~J6 |
| 진입 아이디어를 단순 청산으로 먼저 걸러 본다 | Davey | 1단계 동결 라벨(±10%/20봉) + 무작위 진입 베이스라인 |
| 삼중 배리어 청산 | López de Prado | cascade exit_spec ±1.5×ATR14 / 12봉, OKX OCO |
| 고정 위험으로 꾸준히 (자본곡선 필터 안 씀) | Alvarez, Sandberg·Öhman | 상수 RISK_FRAC + 변동성 타겟팅. HWM 축소 규칙 없음 |
| 현재 자본으로 재사이징 | LTCM(역교훈) | 진입마다 OKX equity 로 계산 (보유 포지션 축소는 안 함) |
| 통합 장부 | Archegos(역교훈) | [장부] 대조 로그, close_qty_for 지분 청산 |
| 포지션 관성(재조정 안 함) | Carver | 보유 중 재사이징 경로 없음 → 버퍼 조건이 자명하게 성립 |
| 랠리 중 공매도는 확인된 반전 뒤에만 | O'Shea, Soros | engulfing_short 은 bull_altseason 에서만, bear fvg 숏 OFF |
| 범위 확장(변동성 각성) 돌파 | Kovner, PTJ | vol_awakening_4h 배포 (v5 CONFIRMED, OOS +0.21%) (매핑 단계 tested_partial → 커버리지 정정 adopted; 속도 필터 추가분은 사전 10%로 탈락) |
| 엣지 감쇠 모니터링 | Thorp, GGR, Avellaneda-Lee | frame_v3 국면 홀드아웃·E 에피소드 OOS, 10/06 실거래 대조 |

## 4. 이미 시험해서 기각한 것 — 트레이더 규칙이 이 레포에서 안 먹힌 자리

| 규칙 | 누가 | 레포 시험 · 기각 사유 · 출처키 |
|---|---|---|
| 고정 익절 (+20~25%, 크레딧 50%, 하방 70~90% 커버, ATH 에서 80% 분배, 측정이동 목표, 첫 수익 시가 청산) | O'Neil, tastytrade, GCR, Pentoshi, Brandt, Williams | method_t 35셀 fvg t −3.4~−4.2, tp_small·tp_1h·tp_regime·tp1_grid 전 셀 음수. 오른쪽 꼬리 절단 — rejected_exit_tp_2026_09, tp_1h_prereg_2026_09_09, tp1_grid_prereg_2026_09_21 |
| 이익 추적 손절 (고점 −3ATR, 3×EMA(ATR), 이익 20% 반납, +15% 후 래칫, 하락 시작 시 매도) | Clenow, Basso·Tharp, Raschke, 赵老哥·炒股养家, cis | method_e Chandelier 0/3 MDD −71.5%, method_f(본전+트레일) 0/3, method_h(3봉 실패) 0/3 — research_log method_e/f/h |
| 넓은 ATR 배수 손절 (2N, 3ATR) | Turtles, Parker, Clenow | method_x A20/A25/A30 건당 +0.7~1.0p 이나 CAGR 우위 2/7. 위험기준 사이징에서 손절이 넓으면 명목가가 준다 — exit_variants_2026_09_04 |
| 조기·시간 청산 (확인창, 1~3봉, 3주 무수익) | Druckenmiller, Marcus, Bandy, BNF | method_h 0/3, method_x T −0.325p t −3.31, D_time −3.62p t −4.80 — exit_variants_2026_09_04, regime_exit_ablation_2026_09_04 |
| 추세 필터 (200DMA, EMA50>100, 10개월 SMA, EMA10, GEM 절대모멘텀, 30주선) | PTJ, Clenow, Faber, Schwartz, Antonacci, Weinstein | F_slow −2.2~−2.8p: bear 진입 롱이 가장 수익 좋은 부분집합이라 막으면 손해 — regime_scale_2026_09 |
| 시장 국면 라벨러 (Market SQN, FTD/분산일, 4년 주기, 리스크 지표) | Tharp, O'Neil, Loukas, Cowen | 라벨러 9종 연도 일관성 탈락, 20~90일 방향 적중 47~49%, 알트시즌 판 잡음 대조 ≥ 실지표 — regime_labeler_2026_09_04, altseason_prereg_2026_09_22 |
| 돌파·확인 진입 (N일 고점, MA 크로스, 박스, '바닥 잡지 마라') | Turtles, Carver, Clenow, cis, GCR·Ansem, Darvas, Livermore | donchian20 bull_btc +5.85% 인데 med −8.20%, holdout −7.84%. ma180·ma3·yyy_cross·breakout_retest 전부 기각. 진입가가 높아 −8% 손절에 더 걸린다 — revival_2026_09_05, ma180_breakout_prereg_2026_09_06, kakao_patterns_prereg_2026_09_12 |
| 횡단면 모멘텀·상대강도 선도주 (12-1, slope×R², 강한 것 매수) | Asness, Clenow, Turtles, Minervini, GCR·Hsaka | 5/5 기각 (상위10 −88% vs 유니버스 −81%), |IC|≤.03, 신호봉 모멘텀 REVERSED — quant_batch1_2026_09_04, xsec_chars_prereg_2026_09_07, signal_profile_prereg_2026_09_07 |
| 돌파봉 거래량 1.5~2배 확인 | O'Neil, Zanger, Weinstein, Darvas, SMB(RVOL) | 배포 셀 신호봉 vol_ratio REVERSED, '거래량 급증 → 이후 나쁨' 3회 이상 재현 — signal_profile, xsec_chars, upbit_shoot_prereg_2026_09_21 |
| 단기 평균회귀 (RSI2, 80-20, IBS, NR7, Oops, 스윕) | Connors, Raschke, Crabel, Williams | rsi2_low·ibs_low·down_streak3·donchian20 4종 40셀 전부 기각(전 셀 중앙값 음수, 대부분 −8.20% 근처; rsi2_low 최선 셀 med −1.36% holdout n=8), nr7, liquidity_sweep 기각 — revival_2026_09_05, patterns |
| 상관 클러스터·방향 단위·베타 상한 | Turtles(4/6/10/12), Kovner, Aspect | port_vol J3 50%·J5 탈락, cap4/6/8 전부 기각, 8슬롯 Calmar 1.59 < 12슬롯 1.84 — port_vol_prereg_2026_09_21, portfolio_prereg_2026_09_10, slots_grid_2026_09_05 |
| 상시 진입 반전 롱숏 | JWH, Dunn | 숏 셀은 음수이거나 단일 해 의존, uncond/gated 라우팅 열세 — routing_gate_2026_09_05, short_exit_2026_09_04 |
| 사이클 초반 최대 위험, 노화 시 축소 | GCR | 경과월별 엣지가 비단조이고 12개월 이상이 최강 — diag_bull_phase_2026_09_06 |
| 메타라벨링 확률 사이징 | López de Prado | ML GBM 워크포워드 실라벨 +0.019 < 셔플 +0.076 — report.md ML 메타필터 2026-07-08 |
| 고승률·단기 보유 시스템 | Bandy | tp 격자 승률 77~97% 인데 전 셀 건당 ≈ −수수료 — tp_1h_prereg_2026_09_09 |
| 4년 주기·이평 지수 게이트로 알트 롱 차단 | Faber, PTJ, Loukas | btc_dist200 이 train +36%p 에서 holdout −9.7%p 로 뒤집힘 — altseason_prereg_2026_09_22 |
| 손절 후 진입가 복귀 재진입(Whipsaw) | Turtles | whipsaw_diag_2026_09_07 불장 코인 94% 가 보유보다 열세, cadence 의 이득은 앵커 리셋이며 슬리피지에 소멸 — whipsaw_diag_2026_09_07, cadence_prereg_2026_09_07 |

**유명 규칙이 여기서 실패한 이유는 세 가지로 모입니다.**

1. **'이익은 달리게 두되 추적 손절로 지켜라'**는 앞 절반(익절 없음)만 맞았습니다. 추적 손절·익절 변형은 여섯 가족이 전부 방식D 에 졌습니다. 이 레포의 알트 거래는 소수 대박이 평균을 만드는 구조라, 승률을 올리는 규칙이 평균을 깎습니다.
2. **'추세 방향으로만 매매하라'**는 배포 패턴이 대부분 반전형이라 정반대로 작동합니다. bear 진입 롱이 가장 좋은 부분집합이고, 레짐 라벨의 방향 예측력은 ≈0 입니다.
3. **'돌파·거래량·모멘텀 선도주'**는 주식 판에서는 강하지만, 방식D −8% 저가 손절 아래 알트 일봉에서는 진입가가 높아져 손절에 걸립니다. 거래량 급증은 이후 수익과 반대 부호였습니다.

## 5. 추가 후보 — 미시험·부분시험 중 반증 렌즈를 통과한 것 (상당수는 이미 일부 시험됨)

반증 표기는 커버리지 / 실현성 / 사전 순서이고, ○ = 반증 안 됨, × = 반증입니다. 여러 그룹에서 같은 기전이 나온 것은 한 행으로 합쳤고, 사전 확률은 개별 값의 범위로 적었습니다.

**생존 후보 (사전 확률 순)**

| 순위 | 규칙 | 출처 트레이더 | 범주 | 반증 | 사전 % | 시험 프레임 스케치 | 선결 조건 |
|---|---|---|---|---|---|---|---|
| 1 | 정화(purge)+엠바고 분할 | López de Prado | process | ×○○ | 85 | frame_v3 분할 옵션, v5 CONFIRMED 2셀만 재실행, 판정 불변이면 통과 | 없음 |
| 2 | 과소매매 (사이즈 절반) | Kovner | sizing | ×○○ | 75 | 이미 측정됨 (risk 0.5% 만 동결 기준 통과). sizing_vol --grid 재확인 | equity ≈ $1,065 이상, 위험 수준은 사용자 결정 |
| 3 | 최소 백테스트 길이(MinBTL) 시험 예산 | Bailey·Borwein·LdP·Zhu | process | ×○○ | 60 | research_log 시험 수 × 데이터 계층(1d/4h/1h) 표, 기록 전용 | 없음 |
| 4 | 파라미터 고원 안정성 (±1 격자) | Pardo, Tomasini·Jaekle | process | ×○○ | 45 | validate_revival 에서 triple_bottom_4h pivot/eq, vol_awakening, cascade 이웃값 평가 | 없음 |
| 5 | PBO (CSCV) | Bailey·LdP | process | ○○○ | 30 | audit_pbo.py: tp1_grid·tb_wide·sizing_vol 격자의 셀×시간 행렬 | 없음 |
| 6 | 가격 경로 순열 + 파이프라인 전체 재실행 | Masters | process | ○○○ | 25 | regime_split_all → revival 을 블록 순열 100회 | 러너 계산량(샤드) |
| 7 | 공분산 반영 반켈리 → RISK_FRAC 대응 | Carver, Chan | portfolio_risk | ×○○ | 20 | sizing_vol --routing 계산 전용 | 위험 수준은 사용자 결정 |
| 8 | Deflated Sharpe Ratio | Bailey·LdP | process | ×○○ | 20 | 감사 모듈, 유효 N 군집 규칙 사전 고정 | 없음 |
| 9 | Turtle Soup (20봉 신저가 실패 반전) | Raschke·Connors | entry | ○○○ | 17 | validate_revival 1h/4h/1d × 롱/숏, ATR 배리어·방식D, Holm m=6 | 1h 이력 365일 |
| 10 | 비용 ≤ 기대 SR/3 예산 | Carver | process | ×○○ | 15 | 감사 모듈, 사전 허용 필터 | 펀딩 커버 9.7% (하한) |
| 11 | 터치 횟수 열화 (첫 시험이 가장 강하다) | Hsaka | entry | ○○○ | 15 | equal_lows_4h·triple_bottom_4h 를 터치 버킷 {2,3,≥4}로 나눔 | 4h 2년 → bear INCONCLUSIVE 위험 |
| 12 | 성과 저하 스로틀 (rolling safe-f) | Bandy | drawdown_control | ×○○ | 15 | validate_portfolio decay_throttle | marubozu·ih 표본 부족 폴백 사전 고정 |
| 13 | 낙폭 사다리 (10%→×0.8 / 6·8·10% → 75·50·25% / −10% 절반·−20% 정지) | Turtles, Woodriff, Amaranth 역교훈 | drawdown_control | ×○○ / ○○× | 8~15 | validate_port_vol size_mult, J6 노출 정합 처리를 사전에 명시 | 실거래는 입출금 보정 NAV 필요 |
| 14 | 강건 변동성 추정량 (MAD·winsorize) | Transtrend, Winton | sizing | ○○× | 12 | sizing_vol --routing vol_robust 대 vol_matched | sizing.py 원본 동일성 |
| 15 | 무수익 시간 손절 (15봉째 손익 ≤0 이면 청산) | Darvas, Ryan, Livermore | exit | ○○× | 12 | method_x P15/P10 + validate_portfolio | 없음 |
| 16 | 일·월 손실 서킷 브레이커 (−2% / −4%·−10% / −1~2%·MTD −10%) | SMB, Trout, PTJ | drawdown_control | ○○× | 7~12 | validate_portfolio 진입 차단 훅, 발동일 커버리지 사전 선언 | 1d/4h 마크투마켓뿐 |
| 17 | RV10/RV60 역전 시 신규 사이즈 ×0.5 | Bennett, Sinclair | regime_filter | ○○× | 10 | validate_port_vol rv_inv | 없음 |
| 18 | 직전 돌파가 승자면 스킵 (S1) | Turtles | entry | ○○× | 10 | 마지막으로 해소된 결과만 쓰는 인과 필터, method_b ① | 없음 |
| 19 | 같은 아이디어 재시도마다 축소 | PTJ | pyramiding | ○○× | 10 | attempt_decay = 0.5^k (30일 내 손절 횟수) | 손절 판별은 exit_reason_of 기반 |
| 20 | 중첩 워크포워드 라우팅 표 재추정 | Masters | process | ○○× | 10 | 1d data_long 연간 폴드, routing replica | 레짐 셀 n 11~75 |
| 21 | 피라미딩 (이익 중 ½N·+0.5ATR 추가) | Turtles, O'Neil, Seykota, Schwartz, Raschke, 赵老哥 | pyramiding | ○○× | 6~10 | method_x 짝지음 (달러 손익) + validate_portfolio | 추가 진입 실거래 경로 없음 (live_dir_keys, 수량 재등록) |
| 22 | 연패·연승 사이징 | Schwartz, PTJ, McKay | drawdown_control | ○○× | 7~8 | 0.75^L 또는 연패 후 정지, J6 | 없음 |
| 23 | 최대 추격 % (피벗 +5%) | O'Neil, Zanger | timing | ○○× | 8 | forming bar 합성 + 지연 추출 | 9/02 이후 발화 지연 ≈0 → 거의 무발동 |
| 24 | Episodic Pivot (일봉 +10%, 거래량 3배, 평탄 베이스) | Kullamägi | entry | ○○× | 8 | 신규 디텍터 → validate_revival + portfolio | 촉매 조건은 제외 |
| 25 | 손익비 5:1 필터 | PTJ | entry | ○○× | 7 | 구조적 목표 정의 사전 고정, method_b ① | 목표 정의가 내 선택 |
| 26 | Holy Grail (ADX>30, EMA20 눌림) | Raschke·Connors | entry | ○○× | 7 | 신규 디텍터 + 구조 배리어 exit_spec | 최소 손절거리 사전 고정 |
| 27 | 갭 관통 체결 측정 → 크래시 스트레스 상한 | Sinclair, LJM·Niederhoffer 역교훈 | portfolio_risk | ○○× | 6 | 1단계는 측정만 (exit = min(stop, open)), 2단계는 진입 게이트 | MMR 확대는 가정치 |
| 28 | ρ=1 스트레스 상한 | LTCM 역교훈 | portfolio_risk | ○○× | 6 | validate_portfolio rho1_cap | eval_D 가 갭을 모델링 안 함 |
| 29 | 섹터·테마 상한 | Archegos 역교훈 | portfolio_risk | ○○× | 5 | 섹터 맵 사전 커밋 후 cap_k | 분류 소급 편향 |
| 30 | 페어·잔차 평균회귀 (SSD, 2σ, OU 잔차, 공적분, Vidyamurthy 문턱) | GGR, Avellaneda-Lee, Vidyamurthy | entry·universe | ○○× | 3~5 | 신규 validate_pairs.py, 두 다리 수수료, 무작위 짝 대조군 | 두 다리 원자적 진입·청산 인프라 없음 |
| 31 | ADV 참여율 상한 | Amaranth·Archegos 역교훈 | sizing | ○○× | 3 | sizing_vol arm, 무해성만 확인 | 현 equity 에서는 비구속 |

**탈락 후보 (가족별, 반증한 렌즈)**

| 가족 | 대표 규칙 | 반증한 렌즈 | 사전 % |
|---|---|---|---|
| 돌파·추세 진입 패키지 | Turtle 55일, Clenow 50일, TSMOM, KAMA, Darvas 박스, Qullamaggie, Livermore | 커버리지·사전 | 3~10 |
| 추적·익절·조기 청산 | 채널 청산, MA 종가 청산, 래칫, 클라이맥스, BNF 부분회복, Chan 반감기, MAE 손절, Brandt | 커버리지·사전 (Zanger·Brandt 는 실현성도) | 2~10 |
| 추세·레짐 필터 | EMA50/100, EMA10, Minervini 템플릿, FTD, Market SQN, BNF 레짐 문턱, Loukas, Cowen | 커버리지·사전 (Loukas·Cowen 실현성) | 3~8 |
| 상관·베타·슬롯 상한 | Turtle 단위 상한, Kovner·Marcus 클러스터, Aspect 베타, beta-weighted, 섹터(SMB) | 커버리지·사전 | 5~10 |
| 성과 연동 사이징 | Minervini 연패, Simons perf_cut, SQN 티어, SMB 티어, Bandy safe-f(정적), port 감소 | 커버리지·사전 | 7~14 |
| 위험 수준 재표현 | Kelly·optimal f, Vince, Taleb barbell, FTMO 10%, テスタ −40%, 워뇨띠 −20%, Wintermute 25% | 커버리지·사전 (실현성 다수) | 3~12 |
| 단기 평균회귀 | 80-20, RSI2+SMA5, Crabel ORB, Williams 변동성 돌파·Oops | 커버리지·실현성·사전 | 2~8 |
| 거래량·모멘텀 필터 | 거래량 확인, buy strength, In Play RVOL, trading time | 커버리지·사전 | 4~10 |
| 진입 지연·폐봉 | GGR 1일 대기, 닫힌 봉 고정 캐던스 | 커버리지·사전 (closed_bar_prereg 이미 기각) | 8~10 |
| 옵션·캐리 전이 | 50%/21DTE, BPR 사다리, XIV 회피, Dalio 위험균형 | 실현성·사전 | 2~6 |
| 방법론 | 롤링 WFA 재최적화, White RC, Davey MC·incubation, decorr, CUSUM | 커버리지·사전 | 3~12 |

### 5-1. 상위 5 생존 후보 사전 등록 스케치

상위 5개는 전부 **수익 규칙이 아니라 감사·위험 수준 항목**입니다. 공통 조건: DEPLOY_ON_PASS=False, 실거래 반영은 사용자 결정, 착수는 관찰 기간(10/06) 이후입니다.

- **① 정화+엠바고 (사전 85%)**
  - **셀**: v5 CONFIRMED 2셀 (triple_bottom_4h|ALL, vol_awakening_4h|ALL). 재실행 원칙상 이 둘만 다시 돌립니다.
  - **프레임**: frame_v3 분할에서 [진입, 청산]이 홀드아웃 시작 경계를 가로지르는 train 거래를 버리고, 방식D 최대 보유 30봉을 엠바고로 둡니다.
  - **통과**: 판정(CONFIRMED)과 OOS 부호 불변.
  - **한계**: 4h 보유가 최대 5일이라 누설이 원래 작아 정보 가치가 낮습니다. CPCV 는 셀이 적어 과합니다.
- **② Kovner 과소매매 (75%)**
  - 이미 측정이 끝났습니다. sizing_vol --grid 에서 risk 0.5% 만 동결 기준을 통과합니다.
  - **셀**: risk {0.5, 0.75, 1.0}% × lev 3, 블록 부트 300.
  - **통과**: 동결 기준 충족(0.5% 에서 이미 충족).
  - **한계**: Calmar 가 위험 수준과 무관하게 평평합니다(0.99~1.14). 그래서 '통과'는 낙폭 선호를 바꾸는 것이지 개선이 아닙니다. 최소주문 문턱 ≈ $1,065 라 현 계좌에서는 주문이 나가지 않습니다. **위험 수준은 사용자 결정**입니다.
- **③ MinBTL 예산 (60%)**
  - **셀**: 데이터 계층 4개 (1d OKX 5년 / data_long 9년 / 4h ≈2년 / 1h 365일).
  - **프레임**: research_log 시험 수를 계층별로 군집화하고, 관측된 최고 연율 Sharpe 로 MinBTL 을 계산해 예산 초과 계층을 표시합니다.
  - **통과**: 결정적인 예산표 산출. 기록 전용이며 앞으로의 규칙으로 '예산이 소진된 계층의 신규 사전 등록은 기존 홀드아웃 너머 OOS 를 요구'를 둡니다.
  - **사전 기대**: 1h·4h 는 이미 초과 (≈85%).
  - **한계**: 공식이 독립·정규 시험을 가정하는데, 디텍터 가족은 서로 군집되어 있습니다.
- **④ 파라미터 고원 (45%)**
  - **셀**: triple_bottom_4h (pivot 3/5/7 × eq .35/.45/.55), vol_awakening_4h 문턱 ±1단계, cascade 2.5ATR/3.0x/0.40 ±1단계.
  - **프레임**: validate_revival v3, PIT top30.
  - **통과**: 모든 이웃이 mean>0, boot_p<.10, 3^k 격자의 70% 이상이 양수.
  - **사전 기대**: triple_bottom 은 tb_wide D1 이 이미 평평한 양수라 ≈60%. vol_awakening 은 얇은 엣지라 0.4% 에서 부호가 뒤집힐 수 있습니다. cascade 는 한 번도 흔들어 본 적이 없어 ≈30%.
  - **한계**: 감사일 뿐이고 파라미터는 바꾸지 않습니다. 사후 최대값은 선택하지 않습니다.
- **⑤ PBO/CSCV (30%)**
  - **셀**: tp1_grid(60셀, 1h 365일), tb_wide D1(9셀, 1d data_long), sizing_vol --grid(15셀).
  - **프레임**: S=16 (4h 는 S=8), 로짓 순위.
  - **통과 의미**: PBO<0.5 = 그 격자의 IS 최고 셀이 OOS 정보를 갖는다. PBO>0.5 면 그 격자에서 나오는 '최고 셀'은 앞으로 금지합니다.
  - **사전 기대**: tp 격자 PBO>0.5 ≈70% (전 셀 음수, 순위가 잡음), tb_wide ≈40%.
  - **한계**: 엣지를 만들지 않고 '격자 최대값 사후 선택 금지' 원칙을 수치로 뒷받침할 뿐입니다.

### 5-2. 매매 규칙 후보 상위 3 (참고)

- **Turtle Soup (17%, 세 렌즈 모두 통과)**
  - 살아남은 유일한 패닉 페이드(cascade)와 같은 '손절 사냥 반전' 가족이고 equal_lows_4h 도 배포 중이라 여지가 있습니다.
  - 반대로 liquidity_sweep 기각, 1d 반전 중앙값 −8.20%, 1h ATR 채점표 0 CONFIRMED 가 있습니다.
  - 장중 매수 스톱은 실행 경로가 없어 **신호봉 종가 진입**으로 바꿔 등록해야 합니다.
- **터치 횟수 열화 (15%, 세 렌즈 모두 통과)**
  - 한 번도 잰 적 없는 축입니다. 다만 배포 셀이 오히려 3번째 이상 터치에서 벌고 있어(equal_lows ≥2 선행 터치, triple_bottom 정확히 3) **부호가 Hsaka 와 반대일 가능성**이 큽니다.
- **낙폭 사다리 (8~15%)**
  - 레포가 미충족으로 남겨 둔 동결 기준(boot MDD 중앙 ≥ −35%)을 직접 겨냥하는 유일한 레버입니다.
  - 그러나 J6 노출 정합이 '그냥 작게 건 것'을 개선으로 세지 않습니다. port_dd 진단은 판정된 적이 없고, 위험 격자의 평평한 Calmar 가 그 한계를 시사합니다.
  - HWM 규칙은 입출금 때문에 2026-08-29 에 폐기됐습니다. 실거래로 가려면 순유입 보정 NAV 가 선결입니다.

## 6. 부분 시험 (tested_partial) — 무엇이 달라서 남았나

| 규칙 | 시험된 부분 (출처키) | 남은 부분 | 남은 부분 사전 % |
|---|---|---|---|
| Turtle 패키지 (55일 + 10/20일 채널 청산 + N 사이징) | donchian20 진입만 방식D 로 (revival_2026_09_05) | 채널 청산 arm, 2N 재해 손절 | 7 |
| Weinstein MA210 래칫 / Qullamaggie MA10 트레일 / 炒股养家 MA5·MA20 이탈 | method_m D_slow, method_g 의 EMA20 성분, method_h | 단독 MA 종가 청산 arm | 5~8 |
| BNF 25MA 이격 −20% 패닉 매수 | 1d 평균회귀 4종 40셀, cascade 1h | 25MA 척도, 1d, 레짐별 문턱 | 6~8 |
| Connors RSI2 + SMA5 청산 | rsi2_low 를 방식D 로 (revival_2026_09_05) | SMA5/RSI>70 청산 + 재해 손절 | 8 |
| Kelly·optimal f·Davey MC | kelly_single 참고 출력, 위험 격자 (sizing_study_2026_09) | 공분산 포트폴리오 Kelly, return/DD≥2 기준 열 | 3~20 |
| 변동성 거부권·보유 중 재사이징 (Hite, Basso) | vol_scale 하한 0.45, MIN_MARGIN 스킵 | σ 백분위 진입 거부, 보유 포지션 축소 | 12 |
| 종목별 상관 기여·베타 가중·섹터 상한 | port_vol·port_corr, cap4/6/8 | 종목·섹터 단위 상한 | 5~9 |
| Chan 반감기 시간청산 + 재해 손절 | method_x T, D_time, A-arms | OU 반감기 유도 보유 상한 | 7 |
| Carver 연속 예측 사이징 | conviction, 등급 배수 제거 (2026-09-03), method_b B_size | ±20 예측이 진입·청산까지 결정 (무손절이라 불변 위반) | 7 |
| Crabel ORB / Williams 변동성 돌파 | nr7 방향 롱 | 양방향 스톱 진입 (실행 경로 없음) | 3~6 |
| 클라이맥스 청산 / 포물선 숏 | 익절 가족, 숏 셀, upbit 슈팅 후 D+1 중앙 −13.5% | 1d 포물선 숏 디텍터 | 10 |
| FTMO 총손실 10% / テスタ HWM −40% / 워뇨띠 −20% 중단 | boot MDD 중앙 −60.8% (risk_level_2026_09_18) | P(HWM −40%) 확률표 | 4~5 |
| Clenow 강도순 슬롯 우선 | prio_edge (확인 후 뒤집힘, 교란), signal_profile 모멘텀 REVERSED | (close−close63)/N 정렬 | 7 |
| 시장 변동성 수준 스케일 (port_mkt) | port_vol 진단 셀이 train·holdout 모두 우위 (port_vol_prereg_2026_09_21) | 별도 사전 등록 | ≈35~40 (입력 언급, 사후 선택 할인 전) |
| 자본곡선 필터 (Trout·PTJ 형) | port_dd 진단 (미판정) | 일·월 손실 정지 | 7~12 |
| 롤링 WFA·WFE (Pardo) | precision_check 고정 파라미터 6개월 창 | 재최적화 + WFE ≥0.5 | 12 |

공통 이유: 이 항목들은 **같은 기전의 이웃 시험이 이미 기각되었거나 판정 없이 진단만 남은 자리**입니다. '남은 부분'은 대부분 파라미터나 그룹 키만 바꾼 재표현입니다.

## 7. 측정 불가·데이터 없음·불변 안전장치 위반

**불변 안전장치 위반 (4)**

| 규칙 | 누가 | 위반 내용 |
|---|---|---|
| 손절을 거래소에 걸지 않고 데스크에서 관리 | Turtles, JWH | 거래소 손절 주문 없는 실거래 금지 |
| −z 비례 분할 매수 | Chan | 손절 없는 물타기 |
| TPS 하락 시 10/20/30/40% 추가 | Connors | 무손절 마틴게일 (ext_evidence_bitmex_aoa_2026_09_22 와 같은 판정) |
| 스프레드 교차까지 손절 없이 보유 | GGR | 무손절 (T1SX 최대손실 −154% 선례) |

**데이터 없음 (15)**

| 규칙 | 없는 데이터 |
|---|---|
| tastytrade IV Rank 진입 / Sinclair IV−RV 예측 / Natenberg 그릭 한도 | IV·옵션 데이터 |
| Spitznagel 꼬리 위험 풋 / Thorp 전환사채 헤지 | 옵션 가격·주문 경로 |
| KMPV 횡단면·시계열 캐리 / 현물-선물 베이시스 / BIS 고캐리 혼잡 경고 / Terra 보조금 캐리 | 다년 펀딩·베이시스 이력 (OKX ≈3개월, Bybit 0건, perp_daily 는 2026-09-09 부터) |
| Melvin 혼잡 숏 회피 | 종목별 OI 이력 (스냅샷만) |
| PTJ 이벤트 전 축소 | 매크로 이벤트 캘린더 |
| Druckenmiller 유동성 / Hayes USD 유동성 지수 | 중앙은행·FRED 계열 |
| Woo 온체인 (Difficulty Ribbon, NVT, 코인 나이) | 온체인 시계열 |

**측정 불가·재량 (11)**: Seykota·Basso 다섯 규칙과 우선순위 / Soros·Druckenmiller 확신 집중 / Marcus 3중 합치 / Steinhardt 순노출 재량 / GCR 컨센서스 역행 / Ansem 70/30 금고 분리 / 워뇨띠 시나리오 무효화 / SMB One Good Trade / Schwager 프로세스 교훈 / Terra 담보 상관 판단 / PTJ·Hite·Seykota 방어 우선. 이 중 코드화할 수 있는 조각(사전 손절, 결정론, 계획 사전 고정)은 이미 불변 원칙에 들어 있습니다.

## 8. 교차 관찰 — 최상위 트레이더들이 공통으로 말하는 것 vs 이 레포의 실증

| 대가들의 공통 원칙 | 레포 실증 | 일치 여부 |
|---|---|---|
| 손실은 빨리, 작게 자른다 | 거래소 손절 불변, 실현 손절이 위험 예산 안 (ETHFI −$2.83, RAY −$2.40) | 일치 |
| 건당 위험 ≤1%, 과소매매 | 동결 기준은 0.5% 만 통과. 현행 1.5% 는 사용자 선택 | 기준은 일치, 운용은 대가들보다 공격적 |
| 변동성에 반비례해 사이징 | 4/4 통과·채택. 저변동 방어는 5회 독립 재현 | 강하게 일치 |
| 이익은 달리게 둔다 (익절 없음) | 익절 6가족 기각 | 일치 |
| 추적 손절로 이익을 지킨다 | Chandelier·본전+트레일·3봉 실패 전부 방식D 에 열세 | **불일치** |
| 추세 방향으로만 | 추세 필터 −2.2~−2.8p, 레짐 방향 적중 49% | **불일치** (배포 엣지가 반전형) |
| 돌파는 거래량이 확인한다 | 거래량 급증 → 이후 나쁨 (REVERSED 반복) | **불일치** |
| 모멘텀 선도주를 산다 | 횡단면 모멘텀 5/5 기각, 신호봉 모멘텀 REVERSED | **불일치** |
| 물타기 금지 | 구조적으로 불가능 | 일치 |
| 이기는 포지션에 추가 (피라미딩) | 미시험, 사전 6~10% (이익이 초기에 몰리고 이후 평균회귀) | 미확인, 회의적 |
| 넓게 분산하라 | 알트 평균 쌍상관 ρ̄ 0.64 → 실효 독립 베팅 2~3개 | 전제가 성립하지 않음 |
| 낙폭에서 사이즈를 줄인다 | 주 판정으로 시험한 적 없음. 위험 격자 Calmar 평평 | 미확인, 비율 개선은 회의적 |
| 데이터마이닝 보정 | Holm·k=n 베이스라인·log2(T)·잡음 대조군 3회 실증 | 대체로 일치, DSR·PBO·MinBTL 은 미도입 |

요약하면 대가들이 공통으로 강조하는 **위험 관리 쪽(손실 절단, 소액 위험, 변동성 사이징, 물타기 금지)은 레포 데이터와 맞고 대부분 이미 채택**됐습니다. **진입·청산 쪽(추세 추종, 돌파, 추적 손절, 모멘텀)은 이 유니버스·청산 체계에서 반대로 작동**했습니다. 대가들의 근거가 저상관 다시장 선물이나 주식 장기 추세였다는 점과 맞는 결과입니다.

## 9. 권고

전부 사전 등록 대상이고, 실거래 변경은 없으며, 착수는 10/06 이후입니다.

1. **연구 위생 감사 묶음** (정화·엠바고, MinBTL, PBO, 파라미터 고원, DSR, 그리고 갭 관통 체결 측정 1단계)
   - 기록·감사 전용이라 실거래와 무관합니다. 지금까지의 판정을 더 단단하게 하거나, 부풀려진 자리를 드러냅니다.
   - 특히 갭 관통 측정은 '손절가에 정확히 체결된다'는 가정이 MDD·P(ruin) 을 얼마나 낙관하는지 재는 일입니다.
   - **사용자 결정 칸**: 착수 여부와 순서.
2. **낙폭·서킷 계열에서 주 판정 arm 하나만 사전 등록** (DD 사다리 1개 + 일 손실 차단 1개, 진단 최소)
   - 위험 수준 미충족을 직접 겨냥하는 유일한 미시험 레버입니다. J6 노출 정합을 어떻게 처리할지는 결과 전에 명시합니다.
   - **사용자 결정 칸**: 통과해도 낙폭 선호 문제이므로 적용 여부와 입출금 보정 NAV 구현 여부.
3. **매매 규칙 후보 하나 사전 등록**: Turtle Soup (4h 롱 주 판정, 신호봉 종가 진입, Holm 가족 사전 고정).
   - 터치 횟수 열화는 같은 프레임의 진단 축으로만 붙입니다.
   - **사용자 결정 칸**: 착수 여부. 통과 시 배포는 포트폴리오 프레임 확인 후 별도로 결정합니다.

## 10. 한계

- **웹 커버리지 부분적**: 13그룹 중 3그룹만 ok. Livermore·O'Neil·Minervini·CryptoCred·Natenberg·Bennett·Sinclair·Vidyamurthy·Thorp 일부 파라미터는 책 기억이나 2차 요약입니다. 워뇨띠·赵老哥는 커뮤니티 전사입니다.
- **시장 이전 문제**: 대부분 규칙은 저상관 다시장 선물이나 미국 주식에서 나왔습니다. 24시간 알트 무기한(ρ̄≈0.64, 세션 갭 없음, 펀딩)으로 옮기면 전제가 깨지는 경우가 많습니다.
- **사전 확률은 주관적 추정**입니다. 반증 렌즈의 판단이지 실행 결과가 아닙니다. **이번 조사에서 시험은 하나도 돌리지 않았습니다.**
- **같은 기전이 여러 그룹에서 중복 집계**됐습니다 (예: 피라미딩 5회, 낙폭 사다리 4회). 241건은 독립 규칙 수가 아닙니다.
- 집계표 상태는 매핑 단계 기준이고, 커버리지 렌즈 정정분은 반영하지 않았습니다.
- 관찰 기간이라 실거래 변경이 없습니다. registry·research_log 에도 이번 조사를 시험으로 기록하지 않습니다.

## 11. 출처

- **Turtles (Dennis·Eckhardt)**: Curtis Faith, *The Original Turtle Trading Rules* (oxfordstrat.com turtle-rules.pdf)
- **Ed Seykota**: seykota.com/tribe/TSP (S/R, EA) / Market Wizards (Schwager 1989)
- **Andreas Clenow**: followingthetrend.com/the-trading-system/trading-system-rules, /stocks-on-the-move / *Following the Trend* (2013) / *Stocks on the Move* (2015)
- **Jerry Parker**: thehedgefundjournal.com/chesapeake-capitals-jerry-parker / mutinyfund.com/jerry-parker / toptradersunplugged.com
- **Tom Basso**: tradingmomentum.substack.com 'art and science of position sizing' / inthemoneybyzerodha.substack.com / Tharp's Thoughts #803 / *The New Market Wizards* (1992)
- **John W. Henry**: JWH Geneva 1998 (turtletrader.com/swiss.pdf) / SEC 424B3 prospectus
- **Bill Dunn**: DUNN WMA 4-page update Nov 2017 (dunncapital.com)
- **Larry Hite**: the7circles.uk/larry-hite-respecting-risk
- **Kovner, Marcus, PTJ, Steinhardt, Schwartz, McKay**: Market Wizards (1989), valueplays.net PDF / ivanhoff.com / turtletrader.com / newtraderu.com (Schwartz Amherst 2013) / Robbins *Money: Master the Game* (2014)
- **Druckenmiller**: Lost Tree Club 2015 transcript / *New Market Wizards* (1992)
- **Soros**: *The Alchemy of Finance*
- **Colm O'Shea, Woodriff**: *Hedge Fund Market Wizards* (2012) / the7circles.uk/jaffray-woodriff-third-way
- **Louis Bacon**: Institutional Investor (2000) / Forbes (2004) / Moore Q1-2010 letter
- **Monroe Trout, Blair Hull**: *New Market Wizards* / macro-ops.com / the7circles.uk / mebfaber.com ep.89
- **Linda Raschke·Larry Connors**: *Street Smarts* (1995) / tradergav.com 50 rules / newtraderu.com 12 rules
- **Larry Connors·Cesar Alvarez**: *Short Term Trading Strategies That Work* (2008) / *High Probability ETF Trading* (2009) / stockcharts RSI(2)
- **Toby Crabel**: *Day Trading with Short Term Price Patterns* (1990) / oxfordstrat.com
- **Larry Williams**: *Long-Term Secrets to Short-Term Trading* (1999) / mql5.com / elitetrader 인용
- **William O'Neil**: *How to Make Money in Stocks*
- **Mark Minervini**: *Think & Trade Like a Champion*
- **David Ryan**: Market Wizards
- **Livermore**: *How to Trade in Stocks* (1940)
- **Nicolas Darvas**: *How I Made $2,000,000*
- **Stan Weinstein**: *Secrets for Profiting in Bull and Bear Markets*
- **Kullamägi**: qullamaggie.com
- **Zanger**: blogchartpattern.wordpress.com
- **Brandt**: peterlbrandt.com, *Diary of a Professional Commodity Trader*
- **Robert Carver**: *Systematic Trading* (2015) / *Leveraged Trading* (2019) / qoppac.blogspot.com
- **Moskowitz·Ooi·Pedersen**: 'Time Series Momentum', JFE 2012
- **Hurst·Ooi·Pedersen**: 'A Century of Evidence on Trend-Following' (AQR)
- **Asness·Moskowitz·Pedersen**: 'Value and Momentum Everywhere', JoF 2013
- **Antonacci**: *Dual Momentum Investing* (2014) / bettersystemtrader #009
- **Faber**: 'A Quantitative Approach to Tactical Asset Allocation' (2007)
- **Kaufman**: *Smarter Trading* / *Trading Systems and Methods* / bettersystemtrader #010
- **Ernest Chan**: *Quantitative Trading* / *Algorithmic Trading* / epchan.blogspot.com
- **Simons**: Institutional Investor (2000) / Zuckerman *The Man Who Solved the Market* (2019)
- **Dalio·Bridgewater**: 'Engineering Targeted Returns and Risks' / 'The All Weather Story'
- **Van Tharp**: *Trade Your Way to Financial Freedom* / *Definitive Guide to Position Sizing* / vantharpinstitute.com
- **Thorp**: 'The Kelly Criterion…' (1997/2006) / *Beat the Market* (1967) / *A Man for All Markets*
- **Vince**: *Mathematics of Money Management* (1992) / bettersystemtrader #011
- **Bandy**: *Quantitative Technical Analysis* / github.com/howardbandy / bettersystemtrader #061
- **Taleb, Spitznagel**: *The Black Swan* / *Antifragile* / *The Dao of Capital* / *Safe Haven* / Institutional Investor (2020)
- **Crypto natives**:
  - GCR: theblockbeats.news/36968, techflowpost.com/11871, cryptonarratives.substack.com
  - Cobie: cobie.substack.com, theblackswans.substack.com
  - Light: threadreaderapp 1354025289685245953
  - Hsaka: threadreaderapp 1004835241578524672
  - Pentoshi: threadreaderapp 1480701619863965697
  - Ansem: cryptonews.com ep.290
  - CryptoCred: Medium (403, 기억)
  - Woo: woobull.com
  - Loukas: x.com/BobLoukas, tradingview
  - Cowen: x.com/intocryptoverse
  - Hayes: cryptohayes.substack.com
  - Ellison·SBF: elmwealth.com, unusual_whales
  - 3AC: decrypt.co/105735
  - Wintermute·Jump: bitget.com/news, panews.io
- **Asia·prop**:
  - BNF: toushi-strategy.com, nehori.com
  - cis: diamond.jp/zai 197252, note.com
  - テスタ: finance.yahoo.co.jp
  - 赵老哥: maimai.cn, tgb.cn
  - 炒股养家: sina.cn, cnblogs
  - 워뇨띠: coinexpert.co.kr, mathnet.or.kr, threads.com
  - SMB: smbtraining.com
  - FTMO: ftmo.com
- **CTA·institutional**: Winton 2014 whitepaper / Man AHL 'The Need for Speed' / Campbell 2015 (Kaminski) / HFJ Aspect·Transtrend / Alvarez Quant Trading / Sandberg·Öhman KTH 2014
- **Options sellers**: sjoptions.com (tastytrade) / steadyoptions.com (Bruton, LJM) / CNBC 2018 / SEC XIV filing / Natenberg, Bennett, Sinclair 책 (기억)
- **Blow-ups**:
  - SEC 2022-70 (Archegos)
  - Senate PSI 2007 (Amaranth)
  - President's Working Group 1999 (LTCM)
  - Lowenstein *When Genius Failed*
  - Washington Post 1997-11-17 (Niederhoffer)
  - arXiv 2207.13914, FEDS 2023-044 (Terra)
  - OECD 2022
  - BIS WP 1087 'Crypto carry'
- **Methodology**:
  - Pardo, *Evaluation and Optimization of Trading Strategies*
  - Tomasini·Jaekle, *Trading Systems*
  - Bailey·López de Prado, Deflated Sharpe / PBO / MinBTL 논문
  - López de Prado, *Advances in Financial Machine Learning*
  - Aronson, *Evidence-Based Technical Analysis*
  - Masters, *Permutation and Randomization Tests*
  - Davey, *Building Winning Algorithmic Trading Systems*
- **Carry·arbitrage**:
  - Gatev·Goetzmann·Rouwenhorst, RFS 2006
  - Avellaneda·Lee, Quantitative Finance 2010
  - Vidyamurthy, *Pairs Trading* (2004)
  - Koijen·Moskowitz·Pedersen·Vrugt, 'Carry', JFE 2018