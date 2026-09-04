# 전체 로직 점검 (2026-09-03)

사용자 요청: "현재 전체 로직에서 개선할 사항 있는지 전체 점검" → "전체 수정필요사항 너가 최적의
형태로 검토해서 진행해". 실행 엔진·거래소, 스케줄러·레짐, 데이터·검증 프레임 세 갈래를
읽고, 심각한 항목은 합성 데이터로 재현해 확인한 뒤 고쳤다. 주문 규칙(방식D)은 그대로다.

## 1. 확인된 결함과 조치

| # | 결함 | 확인 근거 | 조치 | 테스트 |
|---|---|---|---|---|
| 1 | **하모닉 5종이 실거래에서 절대 발화하지 못함** — 신호 = D 피벗 봉인데 피벗 확정에 이후 3봉 필요 → 마지막 봉은 피벗이 될 수 없음 | 합성 300회 마지막 봉 발화 0/300, 신호는 끝에서 최소 7봉 전 | 신호 = D+PIVOT_WINDOW(확정 봉). 5종 `suspended_lookahead`, 스케줄러 4h 블록·adopted_1h 에서 제거 | test_confirm_bar |
| 2 | 위 백테스트가 **룩어헤드** — 미래 3봉 저가로 D 를 고른 뒤 D 종가에서 수익률 | 코드 `find_pivots(range(window, n-window))` | validate_confirm_bar.py 가 new(인과)/old(종전) 두 판을 같은 라벨·게이트로 비교 → 부풀림 측정 + 복귀 판정 | revalidate_confirm_bar.yml |
| 3 | triple_bottom 이 L3 확정 전(L3+1·L3+2) 돌파를 백테스트에서만 셈 | 합성 신호 중 약 8% | causal: 첫 돌파가 L3 확정 전이면 셋업 폐기 → 실거래 집합과 동일, 수치만 재검증 | test_confirm_bar |
| 4 | 채택한 위험 1% 가 실제 0.5~0.7% — 앙상블 등급이 실주문에 곱해짐 | 단독 1d 3.6점=C(x0.7), 단독 4h/1h=D(x0.5); sizing_study 에 grade 없음; ADA 첫 주문 증거금과 일치 | 실주문 grade_mult=1.0. 등급·TF확증은 페이퍼·표기 전용. 레짐 오버레이 유지 | test_sizing |
| 5 | 저가 코인(SHIB/BONK, fvg top30 대상) 진입가 4자리 반올림 → 0 → 실거래 청산 시 0 나누기 → run() 전체 중단 | 코드 `round(entry, 4)`, 예외 미포착 | 8자리 + 0 방어 | test_executor_safety (e2e 1e-7 가격) |
| 6 | 복원 후 triple_bottom(1w) 이 1d 로 평가 — 열린 UNI 가 30일 만기·일봉 레짐 | `_derive_tf` 접미사 추정 | 복원 tf = DB 컬럼 or universe adopted 목록(`_pattern_tf`) | test_executor_safety |
| 7 | 체결가 기준 배리어 재정렬이 무효 — 진입 OCO 가 이미 있어 '손절 있음'으로 건너뜀 | exchange.ensure_stop_orders covered 스킵 | `replace=` 로 기존 algo 취소 후 재등록 | test_executor_safety |
| 8 | reconcile 이 엔진 D 청산 포지션을 'OKX청산'으로 재기록 → delete-then-insert 로 원래 D 행 덮어씀, A 유실 | 코드 경로 | d_closed 포지션 스킵 | test_executor_safety |
| 9 | 체결가 = 주문 직전 시세 (시장가 응답에 average 없음) | ccxt/OKX 응답 형식 | fetch_order 재조회, 실패 시 폴백 | test_executor_safety |
| 10 | DB 저장 실패·두 패턴 동시 진입 시 같은 종목·방향 중복 실포지션, 첫 D 청산이 둘 다 닫음 | 진입 전 거래소 대조 없음 | 거래소 실측 ∪ 장부 live 키에 있으면 스킵 | test_executor_safety |
| 11 | 킬스위치 fail-open — 잔고 조회 실패 시 '통과' | `if equity and ...` | bal None → 진입 보류 | test_executor_safety |
| 12 | 레짐 라벨이 하루 안에 뒤집힐 수 있음 — 형성 중인 일봉·실시간 BTC.D 로 오늘 라벨 계산, eval_D 가 전환으로 읽음 | build_regime_map 입력 | 닫힌 봉만 + 오늘 = 마지막 닫힌 봉 라벨(forward-fill) | test_regime_determinism |
| 13 | 진입 레짐을 매 실행 맵에서 재조회 — BTC.D 캐시 창 이동·히스테리시스 경로 의존으로 과거 라벨이 밀리면 오판 청산 | 코드 경로 | positions.entry_regime 기록·우선. DB 컬럼 필요 | test_regime_determinism |
| 14 | BTC.D fetch 실패 시 {} 저장 → 전 기간 프록시로 조용히 전환 | 코드 경로 | 만료 캐시 우선 | 소스 고정 |
| 15 | 온체인 레짐 조정이 실거래에만 있고 미검증 | orchestrator/method_* 미참조 | 표시 전용 | 소스 고정 |
| 16 | 실거래 손익 미기록(페이퍼 $40 기준만) | 기존 알려진 갭 | pnl_live_usd(실거래 D 청산·reconcile) | test_executor_safety |
| 17 | DB 컬럼 부재로 entry_ts/target/live_mode/tf 유실 | 기존 알려진 갭 | supabase_schema_patch_2026_09.sql (사용자 실행) | test_regime_determinism (SQL ⊇ push 키) |

## 2. 손대지 않은 것 (판단 보류·후속)

- **숏 라우팅**: engulfing_short(bull_altseason n=23 +7.6%) / fvg_short(bear n=164 +2.5%) 는
  regime_switch.json 의 n≥20·mean>0 만으로 켜졌고 median/boot_p/OOS 게이트를 거치지 않았다.
  registry 무조건부 표본에서는 rejected. CLAUDE.md 의 "fvg_short → A 유지"도 코드에 없다.
  방향 하나를 끄는 건 전략 결정이라 사용자 판단으로 남긴다.
- **방식D 의 TF 검증 범위**: method_d 는 1d engulfing/fvg(±short) 만. ih/marubozu/three_soldiers_4h/
  triple_bottom_1w 는 ±10%/20봉 라벨로 통과했고 실거래는 −8% 봉내/30봉이다. method_d 확장이 후속.
- **기존 패턴 형성 중인 봉 탐지**: CLAUDE.md 의 별도 과제 그대로(영향 범위 측정 후 결정).
- 유니버스 드리프트(4h/1h 는 data/ 에 있는 CSV 기준), fvg/ih/marubozu 워크포워드 실패 플래그,
  `_tf_confirm` 이 형성 중인 4h 봉 포함, daily 정각 이중 발화 — 알려진 항목, 변경 없음.

## 3. 실거래에 미치는 즉시 효과

- 하모닉 5종: 어차피 발화하지 않던 블록이 명시적으로 꺼진다. 신호 집합 변화 없음.
- 실주문 크기: 다음 진입부터 등급 배수 없이 equity x 1%. 종전 대비 단독 신호는 1.4~2배 커진다
  (그게 채택 규칙이다). 레짐 축소(x0.6)는 그대로.
- UNI(triple_bottom 1w): 복원 tf 가 1w 로 돌아와 30주 만기·주봉 레짐으로 평가된다.
- 레짐 라벨: 오늘 라벨이 하루 안에 바뀌지 않는다. 전환 청산은 닫힌 봉 기준으로 하루 늦게 잡힐 수 있다.
- 온체인 조정이 빠져 bear/bull_btc 가 sideways 로 완화되던 드문 경우에 진입이 열린다.

## 4. 사용자 액션

1. `supabase_schema_patch_2026_09.sql` 을 매매 DB SQL Editor 에서 실행.
2. revalidate_confirm_bar.yml 결과(아티팩트 `_confirm_bar.json`)로 하모닉 복귀·triple_bottom 수치 갱신 결정.
3. 숏 라우팅 재판정 여부 결정.

## 5. 재검증 결과 (2026-09-03 18:00 KST, revalidate_confirm_bar #1)

라벨 ±10%/20봉, 유니버스 67종목, 부트스트랩 1000. new = 인과(실거래가 잡을 수 있는 집합), old = 종전(룩어헤드).

| 셀 | new n | new mean | new median | boot_p | OOS | new 판정 | old mean | old 판정 | 부풀림 |
|---|---|---|---|---|---|---|---|---|---|
| gartley_4h | 44 | +1.48% | +0.05% | 0.109 | 2/4 | REJECT | +4.58% | PASSED | +3.10%p |
| bat_4h | 49 | −0.26% | −0.37% | 0.522 | 1/4 | REJECT | +2.27% | PASSED | +2.53%p |
| butterfly_4h | 45 | −0.33% | −0.32% | 0.540 | 1/4 | REJECT | +2.09% | REJECT | +2.42%p |
| gartley_1h | 107 | +0.45% | −0.01% | 0.119 | 4/4 | REJECT | +1.35% | PASSED | +0.91%p |
| bat_1h | 40 | −0.82% | −1.22% | 0.743 | 1/4 | REJECT | +0.32% | REJECT | +1.15%p |
| butterfly_1h | 71 | −0.36% | −0.60% | 0.482 | 2/4 | REJECT | +0.76% | REJECT | +1.12%p |
| **triple_bottom_1w** | 104 | +3.07% | **−11.36%** | 0.164 | 2/4 | **REJECT** | +7.73% (n=142) | PASSED | +4.65%p |

- old 판이 등재 수치를 재현했으므로(triple_bottom n=142 +7.73% ≈ 등재 141 +7.72%) 차이는 오로지 룩어헤드 제거에서 온다.
- triple_bottom: 종전 142건 중 38건이 L3 확정 전 돌파였고 그 38건의 평균이 약 +20%. 실거래가 잡을 수 있는 104건은
  중앙값 −11% — 엣지가 '아직 확정 안 된 바닥에서 바로 튀어오르는 강한 돌파'에만 있었고 그건 실시간으로 못 잡는다.
- **조치**: triple_bottom_1w 도 `suspended_lookahead`. 신규 진입 정지. 열린 UNI 포지션은 방식D 규칙(주봉 30봉/레짐/−8%)
  그대로 관리되며 수동 청산 여부는 사용자 판단. `_pattern_tf` 가 suspended 목록도 읽어 UNI 의 tf(1w)는 유지된다.
- 후속 가설(사전등록 필요): 미확정 돌파 셋업을 L3+3 에서 지각 진입하는 변형. 이번엔 만들지 않았다(검증되지 않은 새 신호 집합).
