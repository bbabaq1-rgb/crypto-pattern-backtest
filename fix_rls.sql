-- 1) RLS 켜기 (정책 없음 = anon/authenticated 차단, service_role 은 우회)
alter table signals       enable row level security;
alter table positions     enable row level security;
alter table trades        enable row level security;
alter table daily_summary enable row level security;

-- 2) 공개 키 권한 회수 + service_role 권한 유지
revoke all on signals, positions, trades, daily_summary from anon, authenticated;
grant select, insert, update, delete on signals, positions, trades, daily_summary to service_role;
