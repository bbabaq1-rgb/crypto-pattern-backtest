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

-- 백엔드 전용(공개 클라이언트 없음) -> RLS 비활성화로 permission denied(42501) 방지.
alter table signals       disable row level security;
alter table positions     disable row level security;
alter table trades        disable row level security;
alter table daily_summary disable row level security;
