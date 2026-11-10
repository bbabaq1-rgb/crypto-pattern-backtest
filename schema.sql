create extension if not exists pgcrypto;

create table if not exists signals (
  id uuid primary key default gen_random_uuid(),
  date date, symbol text, pattern text, direction text, regime text,
  entry_price float8, stop_loss float8, created_at timestamptz default now());

create table if not exists positions (
  id uuid primary key default gen_random_uuid(),
  symbol text, pattern text, direction text, entry_date date, entry_price float8,
  stop_loss float8, size_usd float8, status text, method text,
  created_at timestamptz default now());

create table if not exists trades (
  id uuid primary key default gen_random_uuid(),
  symbol text, pattern text, direction text, entry_date date, entry_price float8,
  exit_date date, exit_price float8, return_pct float8, hold_bars int,
  exit_reason text, method text, created_at timestamptz default now());

create table if not exists daily_summary (
  id uuid primary key default gen_random_uuid(),
  date date unique, total_open int, signals_count int,
  cumulative_return_a float8, cumulative_return_d float8,
  created_at timestamptz default now());

-- 백엔드 전용 -> RLS 켜고 정책 없음 = anon/authenticated 차단. 쓰기는 service_role(RLS 우회)만.
-- (2026-11-10 정정: 종전엔 RLS 를 끄고 anon 에 전체 권한을 줘서 anon 키만으로 장부를 고칠 수 있었다.)
alter table signals       enable row level security;
alter table positions     enable row level security;
alter table trades        enable row level security;
alter table daily_summary enable row level security;
revoke all on signals, positions, trades, daily_summary from anon, authenticated;
grant select, insert, update, delete on signals, positions, trades, daily_summary to service_role;
