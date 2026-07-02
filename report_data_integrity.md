# 데이터 정합성 총점검 리포트 (2026-07-02)

## 요약

대시보드-DB-OKX 간 불일치의 근본 원인은 **5가지가 겹친 복합 장애**였다.
가장 심각한 것은 (1) 스케줄러가 22시간 동안 매번 강제 종료돼 동기화가 전면 정지된 것,
(2) 러너가 매 실행 6월 말 기준선으로 되돌아가 **같은 신호로 실거래 중복 진입**한 것이다.
전부 수정 완료했고, DB를 정본 기준으로 재구축했다.

| # | 원인 | 증상 | 수정 |
|---|---|---|---|
| 1 | `timeout-minutes: 10` × 실제 실행 106분 | 17회 연속 cancelled, 22시간 동기화 정지 | 증분 fetch로 실행 자체를 수분대로 단축 + timeout 15분 |
| 2 | `paper_positions.json`이 git에 커밋됨 | 러너가 매번 6월 말 상태로 시작 → openkeys 누락 → **실거래 중복 진입** (ZIL×5·IOTA×5 기록, 잔고 $17까지 소진) | git 추적 해제 + Supabase 상태 복원(`restore_state_db`) |
| 3 | Supabase에 `positions.live_mode`, `signals.ensemble_grade` 등 컬럼 미존재 | insert 전체 실패 → 실거래 포지션 기록 유실, signals 테이블 delete 후 insert 실패로 **소실** | 스키마 내성 insert(`insert_tolerant`) + insert 성공 후에만 삭제 |
| 4 | 주문 수량을 코인 수로 계산 (OKX는 계약 수 해석) | contractSize≠1 종목(AXS·COMP=0.1)이 **의도의 1/10 크기로 체결** ($20 의도 → $1.55 증거금) | `place_swap_entry`에서 계약 수 환산 (`notional/price/contractSize`) |
| 5 | 진입 기록에 신호가 사용 (실체결가 아님) | AXS 기록 0.9642 vs 실체결 0.9694 (-0.5%) | 체결 성공 시 실체결가·실손절가·실투입금으로 기록 |

---

## 항목 6 — 모바일 vs PC 표시 불일치

**원인 분석:**
1. **데이터가 실제로 안 변하고 있었다** — 최근 22시간 스케줄러 전면 정지(위 #1)로
   어느 기기에서 봐도 오래된 데이터. 캐시 문제가 아니라 원천 데이터 정지.
2. **Streamlit 세션 지속성** — 모바일 브라우저는 탭을 오래 유지해 이전 배포
   프로세스에 붙어 있는 경우가 많다. push 후에도 열려 있던 세션은 옛 UI를 유지.
3. `@st.cache_data(ttl=25)`는 25초라 문제 없음.

**조치:**
- 대시보드 제목 아래 **버전 캡션(git 커밋 해시)** 추가.
  → 모바일과 PC에서 버전 문자열이 다르면 모바일에서 **새로고침** 하면 됨.
- Streamlit Cloud 재배포 로그는 콘솔 로그인 필요라 코드로 직접 확인 불가 —
  버전 캡션이 그 역할을 대신한다.

## 항목 7 — 오픈 포지션 증거금 불일치

**OKX 실계좌 감사 결과 (audit_okx 워크플로, 2026-07-02 04:59 UTC):**

| 종목 | 계약수 | 코인수량 | 진입가 | 명목 | **실증거금** | 레버리지 | 손절주문 |
|---|---|---|---|---|---|---|---|
| AXS | 32 | 3.2 | 0.9699 | $3.21 | **$1.55** | 2x | ✅ 0.8871 |
| GAS | 33 | 33 | 1.0790 | $34.22 | **$17.85** | 2x | ✅ 0.9852 |
| COMP | 2 | 0.2 | 15.63 | $3.16 | **$1.56** | 2x | ✅ 14.45 |
| UNI | 13 | 13 | 2.866 | $36.96 | **$18.62** | 2x | ✅ 2.656 |
| ATOM | 19 | 19 | 1.571 | $29.53 | **$14.92** | 2x | ✅ 1.44 |
| LTC | 0.9 | 0.9 | 42.76 | $38.76 | **$19.24** | 2x | ✅ 38.9 |

잔고: equity $87.96 / free $15.74. **6개 포지션 전부 손절 algo 주문 live 확인** (손절 원칙 준수).

**불일치 원인 3가지 (전부 수정):**
1. 표시단: `투입 = 명목/2` 가정 + `collateral`(미실현손익 포함) 사용
   → OKX가 보고하는 **격리 실증거금**(`info.margin`) 우선으로 변경.
2. 주문단: AXS·COMP가 $20 의도 대비 $1.5 체결 — contractSize 환산 누락 버그 (위 #4).
3. 기록단: 신호가로 기록돼 실체결가와 상이 (위 #5).

## 항목 8 — 전체 데이터 정합성 점검 결과

| 점검 항목 | 점검 전 | 조치 | 점검 후 |
|---|---|---|---|
| Supabase trades vs paper_trades.json | **0건 vs 13건** (백필 없었음) | 13건 백필 | **13 = 13 ✅** |
| daily_summary 누적수익률 vs trades 재계산 | 검증 불가(trades 0건) | 백필 후 재계산 | **A +6.59% / D +3.13% 정확히 일치 ✅** |
| Supabase positions vs paper_positions.json | **17행(오염: ZIL×5·IOTA×5 등 중복) vs 5건** | 오염 17행 id 삭제, 정본 재구축 | **6 = 6 ✅** (XRP·ADA×2·BTC·MOVE 페이퍼 + AXS 실거래) |
| positions vs OKX 실계좌 | 대조 불가 | audit_okx 워크플로 신설 | AXS 일치 ✅ / **GAS·COMP·UNI·ATOM·LTC 5종 미추적** (아래 참조) |
| signals vs 진입 포지션 | signals 테이블 **소실(0건)** | insert-먼저 순서 + 스키마 내성 | 파일 기준 3신호 모두 포지션 매칭 ✅ (BTC·ADA fvg short, MOVE i.h. long) |
| 레짐 라우팅 vs 진입 방향 | — | 검증 | bear: fvg→short ✅, 반전패턴(inverted_hammer 등)은 방향 고정 롱 = 설계대로 ✅ |

### ⚠️ 미추적 실거래 포지션 5종 (GAS·COMP·UNI·ATOM·LTC)

6/29–30에 진입됐으나 당시 `live_mode` 컬럼 오류로 **DB 기록이 유실**된 포지션.
- 손절 주문은 전부 OKX에 걸려 있어 **하방은 보호됨**.
- 단, 엔진이 모르는 포지션이라 **방식D(반대신호·레짐전환) 청산 로직이 적용되지 않음** —
  청산은 손절 도달 또는 수동(대시보드 청산 버튼)으로만 이뤄진다.
- **선택지**: ① 그대로 두고 손절/수동 관리 ② 대시보드에서 수동 청산 후 엔진 신규 신호로 재출발.
  (자동 청산은 하지 않았음 — 실거래 청산은 지시 없이 실행하지 않는다)

---

## 필요한 조치 (Supabase SQL Editor에서 1회 실행)

스키마에 없는 컬럼은 현재 자동 제외돼 저장되지만, 실거래/페이퍼 구분과 앙상블 정보를
DB에 온전히 남기려면 아래를 실행해야 한다 (Supabase → SQL Editor → 붙여넣기 → Run):

```sql
alter table positions add column if not exists live_mode boolean default false;
alter table trades    add column if not exists live_mode boolean default false;
alter table signals   add column if not exists ensemble_score numeric;
alter table signals   add column if not exists ensemble_grade text;
alter table signals   add column if not exists patterns_fired text;
alter table signals   add column if not exists tf_confirmed boolean;

-- 컬럼 추가 후 기존 실거래 행 표기 복구
update positions set live_mode = true
 where symbol = 'AXS' and entry_date = '2026-07-01';
```

실행 전까지는 AXS가 DB상 페이퍼로 보이며(대시보드 실거래 탭은 OKX API 폴백으로 정상 표시),
실행 후부터 완전한 실거래/페이퍼 구분이 저장된다.

## 파이프라인 성능

- 수정 전: oncequick 실제 **106분** (fetch "생략"이라 로그에 찍고 lazy로 전 종목 since-2021 재수집,
  binance/bybit 차단으로 종목당 ~30초 낭비, 1h는 수십 종목 전멸)
- 수정 후: in-process 증분 fetch (okx 우선, 1d 900일 / 4h 130일 / 1h 40일 윈도우)
  - 로컬 스모크: BTC 1d 증분 3.2초, GAS 1h 신규 960봉 0.8초
  - 러너 실측: (수동 실행 측정값 — 하단 갱신)
- cron `0 */4 * * *` (6회/일, 문서와 일치) + concurrency 그룹(중첩 차단, 진행 중 완주) + timeout 15분

## 남은 리스크 / 참고

- `.env` 첫 줄에 BOM이 있어 로컬 dotenv가 키를 못 읽는 경우가 있다 (Actions/Streamlit은 무관).
  메모장 등으로 재저장 시 "UTF-8(BOM 없음)" 선택 권장.
- 1d 히스토리를 900일 윈도우로 줄여 러너의 레짐 히스토리 차트가 ~2024년부터 표시된다
  (레짐 판정 자체는 200MA+20 기울기라 여유 충분). 로컬 데이터는 2021년부터 유지.
- daily_summary의 6/30–7/1 total_open 숫자는 당시 오염된 기준선 기준이라 참고용.
  청산 발생 시점부터 다시 정확해진다.
