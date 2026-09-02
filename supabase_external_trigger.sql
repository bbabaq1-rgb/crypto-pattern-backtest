-- ============================================================================
-- supabase_external_trigger.sql — GitHub Actions 크론 누락 대체 (2026-09-02)
--
-- 왜: GitHub `schedule` 크론은 best-effort 라 이 레포에서 반복 누락됐다.
--   매시 :00 발화율 81%→27%, 오프셋 :07 은 0/4, 워크플로 수정 후엔 4h 크론까지
--   0/1 (CLAUDE.md '스케줄 누락률 실측'). 캐스케이드는 1h 이내 진입이 배포 전제.
-- 무엇: Supabase pg_cron 이 매시 GitHub `workflow_dispatch` API 를 호출해 러너를
--   깨운다. 두 워크플로가 이미 workflow_dispatch 를 받으므로 레포 코드 변경 없음.
--   GitHub 자체 schedule 은 **폴백으로 그대로 둔다** — 둘이 겹치면 같은
--   concurrency 그룹(cancel-in-progress: false)에서 직렬 대기하고, 진입 중복은
--   날짜 단위 dedup 키가 막는다. 레포가 public 이라 Actions 분은 무료.
--
-- 실행: Supabase SQL Editor(크립토 프로젝트)에서 **전체 실행**. 멱등 — 재실행 안전.
-- 사전 준비 (한 번):
--   GitHub → Settings → Developer settings → Fine-grained tokens → Generate
--     · Repository access: Only select repositories → crypto-pattern-backtest
--     · Permissions → Repository → Actions: Read and write  (그 외 불필요)
--     · Expiration: 최대(1년). 만료일을 기록해 둘 것 — 만료되면 크론이 조용히 멈춘다
--       (gh_dispatch_log.status_code 401 로 드러남).
--   아래 1절의 '<PAT>' 를 토큰으로 바꿔 실행. 이후 재실행 시엔 '<PAT>' 그대로 두면
--   기존 vault 값이 유지된다(자리표시자는 저장하지 않음).
-- ============================================================================

create extension if not exists pg_cron;
create extension if not exists pg_net;
create extension if not exists supabase_vault;

-- ── 1. PAT 를 Vault 에 저장 (자리표시자 '<...' 로 시작하면 건너뜀) ──────────────
do $blk$
declare
  new_pat text := '<PAT>';
  v_id uuid;
begin
  if new_pat like '<%' then
    raise notice 'PAT 자리표시자 — vault 갱신 건너뜀';
    return;
  end if;
  select id into v_id from vault.secrets where name = 'github_pat_dispatch';
  if v_id is null then
    perform vault.create_secret(new_pat, 'github_pat_dispatch',
                                'GitHub fine-grained PAT, actions:write, crypto-pattern-backtest');
  else
    perform vault.update_secret(v_id, new_pat);
  end if;
end $blk$;

-- ── 2. 발화 로그 — 외부 트리거 발화율·응답 실측용 ───────────────────────────────
create table if not exists public.gh_dispatch_log (
  id          bigserial primary key,
  fired_at    timestamptz not null default now(),
  workflow    text        not null,
  inputs      jsonb,
  request_id  bigint,
  status_code int,
  error       text
);
alter table public.gh_dispatch_log enable row level security;   -- 정책 없음 = anon/authenticated 차단
revoke all on public.gh_dispatch_log from anon, authenticated;

-- ── 3. 디스패치 함수 ─────────────────────────────────────────────────────────────
-- GitHub: POST /repos/{owner}/{repo}/actions/workflows/{file}/dispatches  → 204
-- fast_scheduler.yml 은 inputs 가 없다 — inputs 를 보내면 422 라 비어 있으면 생략.
create or replace function public.gh_dispatch(p_workflow text, p_inputs jsonb default '{}'::jsonb)
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
    from vault.decrypted_secrets where name = 'github_pat_dispatch';
  if v_pat is null or v_pat like '<%' then
    insert into public.gh_dispatch_log(workflow, inputs, error)
    values (p_workflow, p_inputs, 'PAT 미설정 (vault github_pat_dispatch 없음)');
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
end $fn$;

-- anon 키로 호출 못 하게 (security definer 함수는 기본이 public execute)
revoke execute on function public.gh_dispatch(text, jsonb) from public, anon, authenticated;

-- ── 4. 응답 수집 — pg_net 응답은 net._http_response 에 잠시(기본 6h)만 남는다 ────
create or replace function public.gh_dispatch_collect()
returns void
language sql
security definer
set search_path = public, net
as $fn$
  update public.gh_dispatch_log l
     set status_code = r.status_code,
         error = coalesce(r.error_msg,
                          case when r.status_code <> 204 then left(r.content::text, 300) end)
    from net._http_response r
   where r.id = l.request_id
     and l.status_code is null
     and l.error is null;
$fn$;
revoke execute on function public.gh_dispatch_collect() from public, anon, authenticated;

-- ── 5. 크론 등록 (이름 기준 멱등 — 재실행 시 갱신) ───────────────────────────────
-- 시각은 UTC. 발화 시각 집합은 GitHub 크론과 동일하게 유지한다:
--   fast   : 매시 :03  (닫힌 1h 봉 확정 직후. GitHub 폴백 :07 과 겹치면 직렬 대기)
--   daily  : 00:00 oncefull / 04,08,12,16,20:00 oncequick  (= SLOW_TICK_HOURS)
-- daily_scheduler.yml 은 workflow_dispatch 입력 mode 기본값이 oncefull 이라 반드시 명시.
select cron.schedule('gh_fast_scheduler',  '3 * * * *',
  $job$select public.gh_dispatch('fast_scheduler.yml')$job$);
select cron.schedule('gh_daily_oncefull',  '0 0 * * *',
  $job$select public.gh_dispatch('daily_scheduler.yml', '{"mode":"oncefull"}'::jsonb)$job$);
select cron.schedule('gh_daily_oncequick', '0 4,8,12,16,20 * * *',
  $job$select public.gh_dispatch('daily_scheduler.yml', '{"mode":"oncequick"}'::jsonb)$job$);
select cron.schedule('gh_dispatch_collect', '*/10 * * * *',
  $job$select public.gh_dispatch_collect()$job$);

-- ── 6. 확인 쿼리 (실행 후 손으로) ────────────────────────────────────────────────
-- 즉시 1회 시험 발화:   select public.gh_dispatch('fast_scheduler.yml');
--   → 1~2분 뒤 Actions 탭에 'Crypto Pattern Scheduler (fast, sub-1h)' workflow_dispatch 실행이 떠야 한다.
-- 응답 코드 확인(10분 내 수집):  select * from public.gh_dispatch_log order by fired_at desc limit 20;
--   204 = 정상 / 401 = PAT 만료·오류 / 404 = 권한(Actions write) 누락 / 422 = inputs 불일치
-- 크론 목록:  select jobname, schedule, active from cron.job where jobname like 'gh_%';
-- 실행 이력:  select * from cron.job_run_details order by start_time desc limit 20;
-- 해제:       select cron.unschedule(jobname) from cron.job where jobname like 'gh_%';
