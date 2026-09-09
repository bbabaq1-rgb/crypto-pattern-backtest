-- 펀딩비·OI 적재 권한 부여 (2026-09-08)
--
-- 증상: 12:00Z 실행에서 적재가 `permission denied for table perp_daily` (SQLSTATE 42501) 로 실패.
-- 원인: **RLS 정책 문제가 아니라 테이블 GRANT 문제.** RLS 위반이면 PostgREST 가
--   'new row violates row-level security policy' 를 낸다. 'permission denied for table' 은
--   해당 role 에 테이블 권한 자체가 없다는 뜻이다. 같은 실행에서 daily_summary UPSERT 는
--   성공했으므로 키·연결은 정상이고, 새로 만든 두 테이블에만 권한이 없다.
-- 실행: Supabase SQL Editor 에서 그대로 (멱등).
grant select, insert, update, delete on table public.perp_daily   to service_role;
grant select, insert, update, delete on table public.funding_daily to service_role;

-- 확인용(선택): 권한이 붙었는지 본다.
-- select grantee, privilege_type from information_schema.role_table_grants
--  where table_name in ('perp_daily','funding_daily') order by grantee, privilege_type;
