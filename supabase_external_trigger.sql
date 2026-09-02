-- ============================================================================
-- supabase_external_trigger.sql — GitHub Actions 크론 누락 대체 (2026-09-02)
--
-- 왜: GitHub `schedule` 크론은 best-effort 라 이 레포에서 반복 누락됐다.
--   매시 :00 발화율 81%→27%, 오프셋 :07 은 5틱 0/5, 워크플로 수정 후엔 4h 크론
--   04:00 틱까지 유실(166분 경과). 캐스케이드는 1h 이내 진입이 배포 전제다.
-- 무엇: Supabase pg_cron 이 GitHub `workflow_dispatch` API 를 호출해 러너를 깨운다.
--   두 워크플로가 이미 workflow_dispatch 를 받으므로 레포 코드 변경은 없다.
--   GitHub 자체 schedule 은 **폴백으로 그대로 둔다** — 둘이 겹치면 같은 concurrency
--   그룹(cancel-in-progress: false)에서 직렬 대기하고, 진입 중복은 날짜 단위 dedup
--   키가 막는다. 레포가 public 이라 Actions 분은 무료.
--
-- 사용법:
--   1) 아래 [1단계] 의  '<PAT>'  를 GitHub fine-grained PAT 로 바꾼다.
--      GitHub → Settings → Developer settings → Fine-grained tokens → Generate
--        · Repository access : Only select repositories → crypto-pattern-backtest
--        · Permissions       : Repository → Actions = Read and write  (그 외 불필요)
--        · Expiration        : 최대(1년). 만료일 기록 — 만료되면 조용히 멈춘다.
--   2) Supabase SQL Editor 에 **전체를 붙여넣고 한 번에 Run**.
--   3) [6단계] 의 확인 쿼리를 돌린다.
--
-- 멱등 — 몇 번을 다시 돌려도 안전하다. 두 번째부터는 '<PAT>' 를 그대로 둬도 되며,
-- 그 경우 Vault 에 저장된 기존 토큰이 유지된다.
-- ============================================================================


-- ── [1단계] 확장 설치 ────────────────────────────────────────────────────────
-- 이미 켜져 있으면 그냥 통과한다. 권한 문제로 실패하면 NOTICE 만 남기고 계속 진행하며,
-- 그 경우 Dashboard → Database → Extensions 에서 pg_cron / pg_net 을 켠 뒤 재실행한다.
do $ext$
declare
  e text;
begin
  foreach e in array array['pg_cron', 'pg_net', 'supabase_vault'] loop
    begin
      execute format('create extension if not exists %I', e);
    exception when others then
      raise notice '[확장] % 설치 실패 (%). Dashboard → Database → Extensions 에서 켠 뒤 재실행하세요.', e, sqlerrm;
    end;
  end loop;
end
$ext$;


-- ── [2단계] PAT 를 Vault 에 저장 ─────────────────────────────────────────────
-- 아래 한 줄의 '<PAT>' 만 바꾼다. '<' 로 시작하면 자리표시자로 보고 건너뛴다.
do $pat$
declare
  new_pat text := '<PAT>';
  v_id    uuid;
begin
  if new_pat like '<%' then
    raise notice '[PAT] 자리표시자 — Vault 갱신을 건너뜁니다 (기존 값 유지).';
    return;
  end if;

  select id into v_id from vault.secrets where name = 'github_pat_dispatch';

  if v_id is null then
    perform vault.create_secret(
      new_pat,
      'github_pat_dispatch',
      'GitHub fine-grained PAT · actions:write · crypto-pattern-backtest');
    raise notice '[PAT] Vault 에 새로 저장했습니다.';
  else
    perform vault.update_secret(v_id, new_pat);
    raise notice '[PAT] Vault 의 기존 값을 갱신했습니다.';
  end if;
end
$pat$;


-- ── [3단계] 발화 로그 ────────────────────────────────────────────────────────
-- 외부 트리거의 발화율·응답코드·큐 지연을 실측하는 유일한 근거다.
create table if not exists public.gh_dispatch_log (
  id          bigserial primary key,
  fired_at    timestamptz not null default now(),
  workflow    text        not null,
  inputs      jsonb,
  request_id  bigint,
  status_code int,
  error       text
);

create index if not exists gh_dispatch_log_fired_at_idx
  on public.gh_dispatch_log (fired_at desc);

-- RLS 켜고 정책은 만들지 않는다 = anon/authenticated 는 아무것도 못 읽는다.
alter table public.gh_dispatch_log enable row level security;
revoke all on public.gh_dispatch_log from anon, authenticated;


-- ── [4단계] 디스패치 함수 ────────────────────────────────────────────────────
-- GitHub: POST /repos/{owner}/{repo}/actions/workflows/{file}/dispatches → 204
-- fast_scheduler.yml 은 inputs 정의가 없다 — 빈 inputs 를 보내면 422 라 생략한다.
create or replace function public.gh_dispatch(
  p_workflow text,
  p_inputs   jsonb default '{}'::jsonb
)
returns bigint
language plpgsql
security definer
set search_path = public, extensions, net, vault
as $fn$
declare
  v_pat  text;
  v_req  bigint;
  v_body jsonb;
begin
  select decrypted_secret into v_pat
    from vault.decrypted_secrets
   where name = 'github_pat_dispatch';

  if v_pat is null or v_pat like '<%' then
    insert into public.gh_dispatch_log(workflow, inputs, error)
    values (p_workflow, p_inputs, 'PAT 미설정 — Vault 에 github_pat_dispatch 가 없습니다');
    return null;
  end if;

  v_body := jsonb_build_object('ref', 'master');
  if p_inputs is not null and p_inputs <> '{}'::jsonb then
    v_body := v_body || jsonb_build_object('inputs', p_inputs);
  end if;

  select net.http_post(
    url := 'https://api.github.com/repos/bbabaq1-rgb/crypto-pattern-backtest/actions/workflows/'
           || p_workflow || '/dispatches',
    body := v_body,
    headers := jsonb_build_object(
      'Authorization',        'Bearer ' || v_pat,
      'Accept',               'application/vnd.github+json',
      'X-GitHub-Api-Version', '2022-11-28',
      'User-Agent',           'supabase-pg-cron-dispatch',
      'Content-Type',         'application/json'),
    timeout_milliseconds := 10000
  ) into v_req;

  insert into public.gh_dispatch_log(workflow, inputs, request_id)
  values (p_workflow, p_inputs, v_req);

  return v_req;
end
$fn$;

-- security definer 함수는 기본이 public execute — anon 키로 못 부르게 회수한다.
revoke execute on function public.gh_dispatch(text, jsonb) from public, anon, authenticated;


-- ── [5단계] 응답 수집 함수 ───────────────────────────────────────────────────
-- pg_net 응답은 net._http_response 에 잠깐(기본 6시간)만 남으므로 주기적으로 옮긴다.
create or replace function public.gh_dispatch_collect()
returns void
language sql
security definer
set search_path = public, net
as $fn$
  update public.gh_dispatch_log l
     set status_code = r.status_code,
         error = coalesce(
                   r.error_msg,
                   case when r.status_code <> 204 then left(r.content::text, 300) end)
    from net._http_response r
   where r.id = l.request_id
     and l.status_code is null
     and l.error is null;
$fn$;

revoke execute on function public.gh_dispatch_collect() from public, anon, authenticated;


-- ── [6단계] 크론 등록 ────────────────────────────────────────────────────────
-- 시각은 모두 UTC. **발화 시각 집합을 GitHub 크론과 동일하게 유지**한다 —
-- 이게 어긋나면 배포된 패턴의 탐지 분포가 검증 당시와 달라진다.
--   fast  : 매시 :03            (닫힌 1h 봉 확정 직후)
--   daily : 00:00 oncefull + 04·08·12·16·20:00 oncequick  (= scheduler.SLOW_TICK_HOURS)
-- daily_scheduler.yml 의 workflow_dispatch 입력 mode 기본값이 oncefull 이므로 반드시 명시.
--
-- 같은 이름으로 다시 부르면 갱신된다(pg_cron 1.4+). 구버전 대비로 먼저 정리한다.
do $unsched$
declare
  j text;
begin
  foreach j in array array['gh_fast_scheduler', 'gh_daily_oncefull',
                           'gh_daily_oncequick', 'gh_dispatch_collect'] loop
    begin
      perform cron.unschedule(j);
    exception when others then
      null;   -- 없으면 그만
    end;
  end loop;
end
$unsched$;

select cron.schedule('gh_fast_scheduler',  '3 * * * *',
  $job$select public.gh_dispatch('fast_scheduler.yml')$job$);

select cron.schedule('gh_daily_oncefull',  '0 0 * * *',
  $job$select public.gh_dispatch('daily_scheduler.yml', '{"mode":"oncefull"}'::jsonb)$job$);

select cron.schedule('gh_daily_oncequick', '0 4,8,12,16,20 * * *',
  $job$select public.gh_dispatch('daily_scheduler.yml', '{"mode":"oncequick"}'::jsonb)$job$);

select cron.schedule('gh_dispatch_collect', '*/10 * * * *',
  $job$select public.gh_dispatch_collect()$job$);


-- ── [7단계] 등록 결과 확인 ───────────────────────────────────────────────────
select jobname, schedule, active
  from cron.job
 where jobname like 'gh\_%'
 order by jobname;


-- ============================================================================
-- 실행 후 손으로 돌릴 확인 쿼리
-- ============================================================================
--
-- ① 즉시 1회 시험 발화
--      select public.gh_dispatch('fast_scheduler.yml');
--    → 1~2분 뒤 Actions 탭에 'Crypto Pattern Scheduler (fast, sub-1h)' 의
--      workflow_dispatch 실행이 떠야 한다.
--
-- ② 응답 코드 확인 (10분 안에 자동 수집되며, 즉시 보려면 먼저 수집 함수를 부른다)
--      select public.gh_dispatch_collect();
--      select * from public.gh_dispatch_log order by fired_at desc limit 20;
--    204 = 정상 / 401 = PAT 만료·오류 / 404 = Actions write 권한 누락 / 422 = inputs 불일치
--
-- ③ 크론 실행 이력
--      select * from cron.job_run_details order by start_time desc limit 20;
--
-- ④ 전체 해제
--      select cron.unschedule(jobname) from cron.job where jobname like 'gh\_%';
-- ============================================================================
