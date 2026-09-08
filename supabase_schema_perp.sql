-- 무기한 펀딩비 + 미결제약정(OI) 일별 적재 테이블 (2026-09-08, 사용자 지시)
--
-- 왜 지금 만드나:
--   · 펀딩 이력: OKX 는 약 3개월만 준다. '펀딩비 극단' 계열 시험은 1~2년이 필요하다.
--   · OI: **종목별 OI 는 스냅샷뿐 이력이 없다.** 지금 안 쌓으면 그 구간은 영영 못 만든다.
--     (통화 단위 rubik 일별은 180일까지 되므로 그쪽은 백필 가능)
--   적재만 하고 읽어 쓰는 매매 코드는 없다 — 규칙 변경이 아니다.
--
-- 두 가지 OI 를 섞지 않는다:
--   oi_snap_* = 그 종목의 USDT 무기한 스냅샷(호출 시점, 이력 없음)
--   oi_day_*  = OKX rubik 통화 일별(해당 통화의 모든 계약 합산, USD/USDC 마진 포함)
--
-- 실행: Supabase SQL Editor 에서 그대로 (멱등 — 여러 번 실행해도 안전).

create table if not exists public.perp_daily (
    date          date              not null,
    symbol        text              not null,
    funding_rate  double precision,          -- 그날 정산된 요율의 평균
    funding_n     integer,                   -- 그날 정산 횟수(8h 주기 → 보통 3)
    funding_snap  double precision,          -- 스냅샷 시점 '현재 기간' 예상 요율(정산값과 다름)
    oi_snap_ccy   double precision,          -- 스냅샷 OI (코인 수량)
    oi_snap_usd   double precision,          -- 스냅샷 OI (USD)
    oi_snap_ts    bigint,                    -- 스냅샷 시각 (epoch ms)
    oi_day_ccy    double precision,          -- rubik 통화 일별 OI (코인 수량)
    oi_day_usd    double precision,          -- rubik 통화 일별 OI (USD)
    primary key (date, symbol)
);
comment on table public.perp_daily is
  'OKX 무기한 펀딩비·OI 일별. perp_accrual.py 가 느린틱마다 스냅샷, oncefull 에 백필. 시험용 축적 전용 — 매매 미사용.';
create index if not exists perp_daily_symbol_date_idx on public.perp_daily (symbol, date desc);

-- 종전 BTC 전용 펀딩 테이블 (2026-09-04 신설분, funding_accrual.py 가 쓴다).
-- 아직 만든 적이 없다면 이 파일 한 번으로 둘 다 생긴다.
create table if not exists public.funding_daily (
    date  date              not null,
    inst  text              not null,
    rate  double precision  not null,
    primary key (date, inst)
);
comment on table public.funding_daily is
  'BTC 무기한 펀딩비 일평균. funding_accrual.py 가 매 느린틱 업서트. 시험용 이력 축적 전용.';
