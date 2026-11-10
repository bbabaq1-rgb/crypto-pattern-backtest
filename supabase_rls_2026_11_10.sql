-- supabase_rls_2026_11_10.sql — 거래 장부 4개 테이블 접근 제한 (2026-11-10 적용 완료, 멱등)
--
-- 계기: trades·positions·signals·daily_summary 가 RLS 꺼짐 + anon/authenticated 에 전체 권한이라
-- 이 프로젝트의 anon 키만 있으면 누구나 장부를 읽고 고치고 지울 수 있었다(Supabase 보안 점검 ERROR
-- rls_disabled_in_public 4건). 같은 날 이 프로젝트에 공개 웹용 함수(yugaking_track_interest, anon
-- 실행 가능)가 추가돼 anon 키가 웹페이지에 실릴 수 있게 됐다 — anon 키는 공개를 전제로 한 키다.
--
-- 방식: 다른 테이블(ai_judgments·perp_daily·funding_daily·gh_dispatch_log)과 같다 — RLS 켜고 정책은
-- 만들지 않는다 = anon/authenticated 는 아무것도 못 한다. 매매·기록 코드는 전부 service_role 키
-- (rolbypassrls)로 접속하므로 동작 불변. dashboard.py 도 service 키를 먼저 쓰게 바꿨다.
--
-- 되돌리기: alter table public.<t> disable row level security; (+ 필요하면 grant ... to anon)

alter table public.trades        enable row level security;
alter table public.positions     enable row level security;
alter table public.signals       enable row level security;
alter table public.daily_summary enable row level security;

revoke all on table public.trades, public.positions, public.signals, public.daily_summary from anon, authenticated;

grant select, insert, update, delete on table public.trades, public.positions, public.signals, public.daily_summary to service_role;
