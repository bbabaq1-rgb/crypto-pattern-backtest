"""
supabase_setup.py — Supabase 테이블 4종 생성 + INSERT/SELECT 테스트.

DDL은 PostgREST(anon/service 키)로는 실행 불가하므로 아래 순서로 시도:
  1) SUPABASE_DB_URL(postgres 연결문자열) 있으면 psycopg2로 CREATE TABLE IF NOT EXISTS.
  2) 없으면 schema.sql 생성 + Supabase SQL Editor에 붙여넣는 안내 출력.
그 후 supabase-py로 daily_summary INSERT/SELECT 왕복 테스트(테이블 존재 시).
키는 환경변수에서만 읽는다.
"""
import os
import json
from datetime import datetime, timezone

import supabase_client as sc

SCHEMA = """create extension if not exists pgcrypto;

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
"""
# RLS만 끄는 즉시 적용용(이미 테이블이 있을 때)
FIX_RLS = """alter table signals       disable row level security;
alter table positions     disable row level security;
alter table trades        disable row level security;
alter table daily_summary disable row level security;
"""
TABLES = ["signals", "positions", "trades", "daily_summary"]


def create_via_psycopg(db_url):
    import psycopg2
    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(SCHEMA)
    conn.close()
    return True


def main():
    open("schema.sql", "w", encoding="utf-8").write(SCHEMA)
    open("fix_rls.sql", "w", encoding="utf-8").write(FIX_RLS)
    print("[schema.sql / fix_rls.sql 생성됨]")

    db_url = os.environ.get("SUPABASE_DB_URL")
    created = False
    if db_url:
        try:
            create_via_psycopg(db_url)
            print("[1] psycopg2로 테이블 생성/확인 완료 (IF NOT EXISTS)")
            created = True
        except Exception as e:
            print(f"[1] psycopg2 생성 실패: {str(e)[:80]}")
    if not created:
        print("[안내] SUPABASE_DB_URL 미설정 또는 실패 -> Supabase SQL Editor에서 schema.sql을")
        print("       붙여넣어 1회 실행하세요: 대시보드 > SQL Editor > New query > schema.sql 내용 > Run")

    # INSERT/SELECT 왕복 테스트 (테이블이 이미 있어야 성공)
    if not sc.available():
        print("[테스트 스킵] SUPABASE_URL/KEY 미설정")
        return
    try:
        kr = sc.key_role(os.environ.get("SUPABASE_SERVICE_KEY"))
        print(f"[테스트] 사용 키 role = {kr} (service_role 이어야 RLS 우회)")
        cli = sc.get_client("service")          # 쓰기: service_role(RLS 우회)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        cli.table("daily_summary").upsert(
            {"date": today, "total_open": 0, "signals_count": 0,
             "cumulative_return_a": 0.0, "cumulative_return_d": 0.0},
            on_conflict="date").execute()
        rows = cli.table("daily_summary").select("*").eq("date", today).execute()
        print(f"[2] INSERT/SELECT 테스트 OK — daily_summary {len(rows.data)}행 조회")
        for t in TABLES:
            try:
                cli.table(t).select("id").limit(1).execute()
                print(f"    테이블 '{t}' 접근 OK")
            except Exception as e:
                print(f"    테이블 '{t}' 접근 실패(미생성?): {str(e)[:60]}")
    except Exception as e:
        msg = str(e)
        print(f"[2] 테스트 실패: {msg[:120]}")
        if "42501" in msg or "permission denied" in msg:
            print("    -> 원인: 테이블에 RLS가 켜져 있어 막혔습니다(키 부재 아님).")
            print("       해결: Supabase SQL Editor에서 fix_rls.sql 내용을 Run 하세요(4개 테이블 RLS 끔).")
            print("       또는 SUPABASE_SERVICE_KEY 에 진짜 'service_role secret' 키를 넣으세요(RLS 우회).")


if __name__ == "__main__":
    main()
