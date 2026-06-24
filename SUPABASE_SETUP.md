# Supabase + GitHub Actions 설정 가이드

페이퍼테스트 신호/포지션/체결을 Supabase에 저장하고, GitHub Actions가 매일
UTC 00:00(한국 09:00)에 자동 실행한다. 실주문은 없다(데모/로컬 모의 체결만).

---

## 1. Supabase 테이블 생성 (1회)

키가 환경에 설정돼 있으면:
```
python supabase_setup.py
```
- `SUPABASE_DB_URL`(Postgres 연결문자열)이 있으면 자동으로 `CREATE TABLE IF NOT EXISTS` 실행.
- 없으면 `schema.sql`이 생성된다 → **Supabase 대시보드 > SQL Editor > New query** 에
  `schema.sql` 내용을 붙여넣고 **Run**. (signals / positions / trades / daily_summary 4종)
- 이후 같은 스크립트가 `daily_summary` INSERT/SELECT 왕복 테스트를 수행.

## 2. GitHub Secrets 등록 (대표님이 직접 — 값은 직접 입력)

브라우저에서 열기:
`https://github.com/bbabaq1-rgb/crypto-pattern-backtest/settings/secrets/actions`

`New repository secret` 버튼으로 아래를 **하나씩** 추가 (Name=키 이름, Secret=값):

| Name | 값 출처 |
|---|---|
| `SUPABASE_URL` | Supabase 대시보드 > Project Settings > Data API > Project URL (`https://<ref>.supabase.co`) |
| `SUPABASE_ANON_KEY` | 같은 화면의 `anon` `public` 키 |
| `SUPABASE_SERVICE_KEY` | 같은 화면의 `service_role` `secret` 키 (쓰기용, 절대 외부 노출 금지) |
| `BITGET_DEMO_KEY` | 비트겟 데모 API 키 (없으면 시뮬레이션 모드로 동작) |
| `BITGET_DEMO_SECRET` | 비트겟 데모 시크릿 |
| `BITGET_DEMO_PASSPHRASE` | 비트겟 데모 패스프레이즈 |

- 키는 **코드에 절대 넣지 않는다.** 워크플로가 `${{ secrets.* }}`로 주입한다.
- (선택) 테이블 자동생성을 CI에서 하려면 `SUPABASE_DB_URL`도 추가.

## 3. GitHub Actions 자동 실행

- 워크플로: `.github/workflows/daily_scheduler.yml`
- 트리거: 매일 `cron: '0 0 * * *'`(UTC 00:00) + 수동(`workflow_dispatch`).
- 수동 테스트: GitHub > **Actions** 탭 > `Daily Paper Scheduler` > **Run workflow**.
- 실패 시 로그/JSON이 아티팩트로 업로드되고 Actions 화면에 에러가 표시된다.

## 4. 전체 동작 확인 (로컬)

```
python supabase_setup.py     # 테이블 생성/확인 + 왕복 테스트
python scheduler.py oncefull # fetch -> 레짐 -> 신호 -> 페이퍼 체결 -> Supabase 저장
```
키가 없으면 자동으로 **시뮬레이션 + 로컬 JSON 폴백**으로 동작한다.

## 5. Supabase 대시보드에서 데이터 확인

대시보드 > **Table Editor** > 좌측에서 테이블 선택:
- `daily_summary` : 날짜별 오픈수/신호수/누적수익(A·D)
- `trades` : 청산된 모의 체결(방식 A/D 병행)
- `positions` : 현재 오픈 포지션
- `signals` : 당일 탐지 신호

또는 SQL Editor에서:
```sql
select * from daily_summary order by date desc limit 14;
select method, count(*), round(avg(return_pct),2) from trades group by method;
```

## 6. 기존 JSON 데이터 이관 (선택, 1회)

```
python paper_executor.py migrate
```
`paper_trades.json` / `paper_positions.json`의 기존 데이터를 Supabase로 INSERT.
