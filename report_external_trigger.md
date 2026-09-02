# 외부 트리거 전환 — GitHub 크론 누락 대체 (2026-09-02)

## 결론

GitHub Actions `schedule` 만으로는 이 레포의 실행 케이던스를 지킬 수 없다. 워크플로
분리(PR #9, 01:52 UTC 머지) 이후 두 스케줄이 **모두 한 번도 발화하지 않았다.**
사용자 결정으로 **Supabase pg_cron → GitHub `workflow_dispatch` API** 외부 트리거로
전환한다. 레포 코드는 바뀌지 않는다(두 워크플로가 이미 dispatch 를 받는다).

| 워크플로 | 크론 | 관찰 구간 | 발화 |
|---|---|---|---|
| fast_scheduler | `7 * * * *` (정시 회피) | 02:07 ~ 06:07 (5틱) | **0/5** |
| daily_scheduler | `0 */4 * * *` | 04:00 | **미발화** (06:46 기준 166분) |

4h 시대(7/02~9/01) 368건의 지연 분포에서 p99 가 188분이므로, 166분이 지난 04:00 틱은
사실상 유실이다(최대 관측 231분이라 이론적 여지만 남는다). 오프셋 매시 크론 0/5 는 확정.
두 스케줄이 워크플로 파일
수정 직후 동시에 멈춘 점은 GitHub 의 스케줄 재등록 지연 가능성을 시사하나, 원인이
무엇이든 **'1h 이내 진입'(캐스케이드 배포 전제, d<=1 81%)을 GitHub 크론이 보장하지
못한다**는 결론은 같다.

04:00 누락분은 05:40 에 `daily_scheduler` 를 oncequick 으로 수동 dispatch 해 대체했다
(`판정=플래그`, `느린TF 포함`, 예외 없음, 신호 0건, 오픈 21건, equity $281.73, 킬스위치 통과).

## 설계

`supabase_external_trigger.sql` — Supabase SQL Editor 에서 전체 실행(멱등).

| pg_cron job | 시각(UTC) | 호출 |
|---|---|---|
| `gh_fast_scheduler` | 매시 :03 | `fast_scheduler.yml` (inputs 없음 — yml 에 inputs 가 없어 보내면 422) |
| `gh_daily_oncefull` | 00:00 | `daily_scheduler.yml` mode=oncefull |
| `gh_daily_oncequick` | 04·08·12·16·20:00 | `daily_scheduler.yml` mode=oncequick |
| `gh_dispatch_collect` | 10분마다 | pg_net 응답코드를 `gh_dispatch_log` 로 수집 |

- **발화 시각 집합은 GitHub 크론과 동일**하다. daily 는 `SLOW_TICK_HOURS` 6틱, fast 는
  매시. 배포 패턴의 탐지 시각 분포가 바뀌지 않는다(test_external_trigger.py 가 고정).
- **GitHub schedule 폴백은 daily 에만 남긴다** (fast 는 제거 — 아래 참조).
- fast 를 :03 으로 둔 이유: 닫힌 1h 봉(`rows[-2]`)이 확정된 직후이고, pg_cron 은 GitHub
  부하 피크와 무관하다.
- daily 의 workflow_dispatch 입력 `mode` 기본값이 oncefull 이므로 SQL 이 반드시 명시한다.

### 시크릿
fine-grained PAT — Repository access 를 이 레포 하나로, Permissions 는 **Actions: Read and
write** 만. Vault `github_pat_dispatch` 에 저장하고 함수가 실행 시 읽는다. SQL 파일에
토큰 리터럴은 없다(테스트가 정규식으로 확인). `gh_dispatch` 는 security definer 라
anon/authenticated 의 execute 를 회수했다. 만료 1년 — 만료되면 `gh_dispatch_log.status_code`
401 로 드러나고 크론은 **조용히 멈춘다.** 만료일을 캘린더에 기록할 것.

## 검증 방법 (실행 후)

1. `select public.gh_dispatch('fast_scheduler.yml');` → 1~2분 뒤 Actions 탭에
   `Crypto Pattern Scheduler (fast, sub-1h)` 의 workflow_dispatch 실행이 뜬다.
2. 10분 내 `select * from public.gh_dispatch_log order by fired_at desc limit 20;` 에서
   status_code 204. 401 = PAT 오류/만료, 404 = Actions write 권한 누락, 422 = inputs 불일치.
3. 며칠 뒤 발화율: `gh_dispatch_log.fired_at` 대 Actions run `created_at` — **이제 발화율
   측정은 `schedule` 이벤트만 세면 0 으로 보인다. `workflow_dispatch` 를 포함해야 한다.**
   차이가 곧 큐 지연이며, 캐스케이드 전제(60분 이내 81%)와 대조한다.

## 작동 확인 (2026-09-02)

| 틱 | 발화 | 러너 시작 | 결과 |
|---|---|---|---|
| fast 09:03 / 10:03 / 11:03 | :03:01 | 즉시 | 성공 |
| fast 12:03 | :03:01 | 대기 중 취소 | 아래 참조 |
| daily 12:00 | :00:01 | :00:07 | 성공, `실행 모드: oncequick --slow` |

두 달간 중앙 25분·최악 3시간씩 밀리던 GitHub 크론과 질적으로 다르다. daily 의 `mode`
입력도 정상 전달됐다(oncequick 으로 실행, 느린TF 블록 수행).

## fast 의 GitHub schedule 폴백 제거

12:03 외부 트리거 실행이 **취소**됐다. daily 12:00 이 실행 중이라 pending 이었는데,
12:04:30 에 GitHub 폴백(`7 * * * *`)이 큐에 들어오면서 밀려났다 — GitHub 는 같은
concurrency 그룹에 새 실행이 큐에 들어오면 **먼저 대기 중이던 실행을 취소**한다
(`cancel-in-progress: false` 여도 pending 은 취소 대상이다). 이번엔 폴백이 대신 돌아
손실이 없었다.

문제는 거울상이다. **daily 가 pending 인 사이 fast 가 큐에 들어오면 daily 가 취소되고,
느린TF 탐지를 4시간 통째로 잃는다.** 확률은 낮지만(daily 는 보통 7초 내 시작) 발화율
0~27% 짜리 폴백을 위해 감수할 위험이 아니다. `fast_scheduler.yml` 의 `schedule` 을
제거해 경합 자체를 없앴다.

daily 폴백은 유지한다 — 4h 간격이라 fast 와 큐가 겹칠 창이 좁고, 두 달간 99% 발화 실적이
있다. 외부 트리거가 멈추면 `gh_dispatch_log.status_code` 401 로 드러나며, 그때는 fast 를
수동 dispatch 하거나 크론을 임시로 되살린다.

## 남은 위험
- PAT 만료 — 알림 없음. 로그 401 로만 확인.
- Supabase 무료 플랜 비활성 일시정지 — 러너가 매 실행 DB 를 쓰므로 활성이 유지되지만,
  러너가 멈추면 pg_cron 도 함께 멈추는 순환 구조.
- fast 는 이제 폴백이 없다 — 외부 트리거가 멈추면 캐스케이드 진입·하위TF 청산이 daily
  6틱에만 의존하게 된다(진입 지연 전제 위반). 401 감시가 그만큼 중요해졌다.
