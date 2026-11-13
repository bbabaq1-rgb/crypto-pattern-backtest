-- ============================================================================
-- supabase_schema_channel_alerts.sql — 채널 이탈 알림 기록 (2026-11-13)
--
-- channel_watch.py(대표님 개인용 채널 알림 봇)가 쓴다. 매매 코드는 이 테이블을 읽지 않는다.
--   · alert_key 유니크 — 같은 채널(두 기준점)이 같은 쪽으로 깨진 것은 한 번만 알린다.
--   · ret_1 / ret_5 / ret_20 — 이탈 봉 종가 기준 이후 1·5·20봉 수익(이탈 방향 부호).
--     '어떤 이탈이 실제로 의미 있었나'를 쌓는 장부다.
-- 접근: RLS 켜고 정책 없음 + anon/authenticated 권한 회수(2026-11-10 거래 장부와 같은 원칙).
--   러너는 service_role 키로 쓴다. 멱등 — 다시 돌려도 안전하다.
-- ============================================================================
create table if not exists public.channel_alerts (
  id           bigserial primary key,
  created_at   timestamptz not null default now(),
  symbol       text        not null,
  tf           text        not null,
  side         text        not null check (side in ('up', 'down')),
  bar_ts       bigint      not null,
  bar_time     text,
  close        double precision,
  upper        double precision,
  lower        double precision,
  width        double precision,
  depth        double precision,
  kind         text,
  anchor       text,
  start_ts     bigint,
  span         int,
  touches_lo   int,
  touches_hi   int,
  vol_ratio    double precision,
  alert_key    text        not null unique,
  sent         boolean     not null default false,
  ret_1        double precision,
  ret_5        double precision,
  ret_20       double precision,
  outcome_done boolean     not null default false
);

create index if not exists channel_alerts_pending_idx
  on public.channel_alerts (outcome_done, symbol, tf);

alter table public.channel_alerts enable row level security;
revoke all on public.channel_alerts from anon, authenticated;
grant select, insert, update, delete on public.channel_alerts to service_role;
grant usage, select on sequence public.channel_alerts_id_seq to service_role;
