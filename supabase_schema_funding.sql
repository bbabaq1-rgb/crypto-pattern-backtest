-- 펀딩비 일별 이력 적재 테이블 (2026-09-04)
-- 왜: OKX 는 펀딩 이력을 약 94일만 제공한다. '펀딩비 극단 청산'(quant_exit_catalog B+)을
--     시험하려면 최소 1~2년치가 필요하므로 지금부터 매 실행 적재해 쌓는다.
--     적재만 하고 읽어 쓰는 매매 코드는 아직 없다 — 규칙 변경이 아니다.
-- 실행: Supabase SQL Editor 에서 그대로 실행 (멱등).
create table if not exists public.funding_daily (
    date  date              not null,
    inst  text              not null,
    rate  double precision  not null,
    primary key (date, inst)
);
comment on table public.funding_daily is
  'BTC 무기한 펀딩비 일평균. funding_accrual.py 가 매 느린틱 업서트. 시험용 이력 축적 전용.';
