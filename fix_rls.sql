-- 1) RLS 비활성화 (permission denied 42501 방지)
alter table signals       disable row level security;
alter table positions     disable row level security;
alter table trades        disable row level security;
alter table daily_summary disable row level security;

-- 2) 역할별 권한 부여 (hint: "Grant the required privileges" 해결)
grant all on signals, positions, trades, daily_summary
  to anon, authenticated, service_role;
