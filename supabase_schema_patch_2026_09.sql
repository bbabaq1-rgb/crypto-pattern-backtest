-- supabase_schema_patch_2026_09.sql — 매매 DB 스키마 보강 (2026-09-03 전체 점검 후속)
--
-- 왜: 러너는 매 실행 파일시스템이 비어 Supabase 가 유일한 상태 원천인데, 아래 컬럼이
-- 없어 insert_tolerant 가 자동 제외해 왔다(실행 로그 '스키마 미존재 컬럼 제외').
-- 그 결과 (1) positions.entry_ts 유실 → 1h 포지션 진입봉을 그날 첫 봉으로 오인
-- (2) target/live_mode 는 폴백으로 버팀 (3) tf 유실 → triple_bottom 1w 가 1d 로 복원
-- (4) entry_regime 없음 → 레짐 청산이 실행마다 다시 계산한 맵에 의존
-- (5) trades 에 실거래 손익·live 표시 없음.
-- 실행: Supabase SQL Editor 에서 이 파일 전체를 붙여 넣고 Run (멱등 — 여러 번 실행 가능).
-- 코드는 컬럼이 생기는 즉시 자동으로 채운다(코드 변경·재배포 불필요).

alter table positions add column if not exists entry_ts     bigint;
alter table positions add column if not exists target       float8;
alter table positions add column if not exists live_mode    boolean;
alter table positions add column if not exists tf           text;
alter table positions add column if not exists regime       text;
alter table positions add column if not exists entry_regime text;

-- (6) live_order 3종 (2026-09-17 추가). 이 셋이 없어 진입 **다음 실행부터** 자기 계약 수를
-- 몰랐고, close_qty_for 가 전량 청산으로 떨어져 같은 종목을 나눠 든 메인 레그까지 닫혔다
-- (2026-09-16 ONDO −3.51%, 2026-09-14 ETH). sl_order_id 가 없으면 'OCO 가 이미 집행됐는가'
-- 가드도 건너뛴다. 코드는 컬럼이 없어도 지분 비율 폴백으로 안전하게 돌지만, 있으면 정확해진다.
alter table positions add column if not exists qty         float8;
alter table positions add column if not exists leverage    float8;
alter table positions add column if not exists sl_order_id text;

alter table trades add column if not exists live_mode    boolean;
alter table trades add column if not exists pnl_usd      float8;
alter table trades add column if not exists pnl_live_usd float8;
alter table trades add column if not exists regime       text;
alter table trades add column if not exists entry_regime text;

-- 확인용
select column_name from information_schema.columns where table_name = 'positions' order by 1;
select column_name from information_schema.columns where table_name = 'trades' order by 1;
