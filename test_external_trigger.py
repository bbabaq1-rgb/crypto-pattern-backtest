"""
외부 트리거(Supabase pg_cron → GitHub workflow_dispatch) 정의 고정.

supabase_external_trigger.sql 은 레포 밖(Supabase)에서 실행되는 SQL 이라 CI 가 직접
돌릴 수 없다. 대신 이 파일이 **레포와 어긋나면 실거래 케이던스가 바뀌는 지점**을
문자열 수준에서 고정한다:
  · 호출하는 워크플로 파일이 실제로 존재하고 workflow_dispatch 를 받는다
  · daily 의 mode 입력값이 yml 이 아는 값이고, 발화 시각이 SLOW_TICK_HOURS 와 같다
  · fast 는 inputs 없이 호출한다 (yml 에 inputs 가 없어 보내면 422)
  · 두 워크플로 모두 GitHub schedule 이 없다 — 발화는 이 SQL 전용(2026-09-06 폴백 제거).
    이 SQL 이 멈추면 아무것도 돌지 않는다
  · 토큰 리터럴이 파일에 없다
  · (2026-10-29) AI 엘리엇 15분 진입 판단 ai_quarter.yml — 매시 :18/:33/:48, fast(:03)와 합쳐 15분 간격.
    메인 스케줄러와 **다른 concurrency 그룹**(같은 그룹이면 큐 진입 순간 대기 중인 메인 실행이 취소된다)이고,
    게이트가 시각 창·시험 기간·메인 실행 중·대기를 보고 스스로 건너뛴다. :48 실행도 다음 메인 실행 전에 끝난다

실행: python test_external_trigger.py
"""
import os
import re
import sys

import scheduler as sch

HERE = os.path.dirname(os.path.abspath(__file__))
SQL = open(os.path.join(HERE, "supabase_external_trigger.sql"), encoding="utf-8").read()
WF_DIR = os.path.join(HERE, ".github", "workflows")

fails = []


def chk(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f" — {detail}"))
    if not cond:
        fails.append(name)


def wf(name):
    return open(os.path.join(WF_DIR, name), encoding="utf-8").read()


# ── 1. cron.schedule 파싱 ───────────────────────────────────────────────────
jobs = {}
for m in re.finditer(
        r"cron\.schedule\('([^']+)',\s*'([^']+)',\s*\$job\$(.*?)\$job\$\)", SQL, re.S):
    jobs[m.group(1)] = (m.group(2), m.group(3).strip())
chk("크론 5개 등록", set(jobs) == {"gh_fast_scheduler", "gh_daily_oncefull",
                                   "gh_daily_oncequick", "gh_dispatch_collect", "gh_ai_quarter"}, sorted(jobs))
_uns = re.search(r"foreach j in array array\[(.*?)\] loop", SQL, re.S)
chk("재등록 전 정리 목록에 5개 모두", _uns is not None and all(f"'{j}'" in _uns.group(1) for j in jobs),
    _uns and _uns.group(1))


def cron_fields(expr):
    return expr.split()


def hours_of(expr):
    f = cron_fields(expr)
    return set(range(24)) if f[1] == "*" else {int(h) for h in f[1].split(",")}


# ── 2. fast: 매시, 정각 회피, inputs 없음 ──────────────────────────────────
fast_cron, fast_cmd = jobs["gh_fast_scheduler"]
f = cron_fields(fast_cron)
chk("fast 는 매시", f[1:] == ["*", "*", "*", "*"], fast_cron)
chk("fast 분은 0 이 아님(닫힌 봉 확정 후)", 0 < int(f[0]) < 15, fast_cron)
chk("fast 는 fast_scheduler.yml 호출", "gh_dispatch('fast_scheduler.yml')" in fast_cmd, fast_cmd)
chk("fast 호출에 inputs 없음", "mode" not in fast_cmd, fast_cmd)
chk("fast_scheduler.yml 에 inputs 정의 없음(있으면 SQL 도 보내야 함)",
    "inputs:" not in wf("fast_scheduler.yml"))

# ── 3. daily: 발화 시각 = SLOW_TICK_HOURS, mode 는 yml 이 아는 값 ──────────
full_cron, full_cmd = jobs["gh_daily_oncefull"]
quick_cron, quick_cmd = jobs["gh_daily_oncequick"]
chk("daily 두 크론 모두 정각", cron_fields(full_cron)[0] == "0" and cron_fields(quick_cron)[0] == "0")
chk("oncefull 은 UTC 00 만", hours_of(full_cron) == {0}, full_cron)
chk("oncequick 은 04/08/12/16/20", hours_of(quick_cron) == {4, 8, 12, 16, 20}, quick_cron)
chk("daily 발화 시각 합집합 = SLOW_TICK_HOURS",
    hours_of(full_cron) | hours_of(quick_cron) == set(sch.SLOW_TICK_HOURS))
chk("oncefull 은 mode=oncefull", '"mode":"oncefull"' in full_cmd, full_cmd)
chk("oncequick 은 mode=oncequick", '"mode":"oncequick"' in quick_cmd, quick_cmd)
daily_yml = wf("daily_scheduler.yml")
chk("daily_scheduler.yml 이 mode 입력을 받음", re.search(r"inputs:\s*\n\s*mode:", daily_yml) is not None)
chk("daily yml 이 oncefull/oncequick 을 안다", "oncefull" in daily_yml and "oncequick" in daily_yml)

# ── 4. 호출 대상·헤더·ref ───────────────────────────────────────────────────
for name in ("fast_scheduler.yml", "daily_scheduler.yml"):
    chk(f"{name} 존재", os.path.exists(os.path.join(WF_DIR, name)))
    chk(f"{name} workflow_dispatch 수신", "workflow_dispatch:" in wf(name))

# 폴백 정책 (2026-09-06, 사용자 결정): **두 워크플로 다 GitHub schedule 없음.**
#   fast 는 2026-09-02 제거 — 매시 폴백이 daily 와 같은 concurrency 그룹에 큐로 들어오면
#   GitHub 가 **먼저 대기 중이던 실행을 취소**한다(실측: 12:03 외부 트리거 실행이
#   12:04:30 폴백 때문에 취소).
#   daily 는 2026-09-06 제거 — 9/05~9/06 에 5회 연속 지각(최대 2시간 19분)하며 이미 돈
#   느린틱을 재실행했고, 같은 취소 위험을 daily 쪽에도 안긴다. 외부 트리거는 9/02 이후
#   정시 100% 발화.
#   **대가**: 발화 경로가 이 SQL 하나뿐 — 멈추면 진입·청산·손절 점검이 전부 정지한다.
chk("daily 도 GitHub schedule 없음(2026-09-06 폴백 제거)",
    re.search(r"^\s*schedule:", wf("daily_scheduler.yml"), re.M) is None)
chk("fast 는 GitHub schedule 없음(큐 경합 제거)",
    re.search(r"^\s*schedule:", wf("fast_scheduler.yml"), re.M) is None)
chk("ref 는 master (스케줄 크론과 같은 기본 브랜치)", "'ref', 'master'" in SQL)
chk("레포 경로 정확", "repos/bbabaq1-rgb/crypto-pattern-backtest/actions/workflows/" in SQL)
chk("User-Agent 헤더(GitHub 필수)", "'User-Agent'" in SQL)
chk("Authorization Bearer", "'Bearer ' || v_pat" in SQL)

# ── 5. 보안 ─────────────────────────────────────────────────────────────────
chk("토큰 리터럴 없음", re.search(r"gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}", SQL) is None)
chk("PAT 는 vault 에서 읽음", "vault.decrypted_secrets" in SQL and "github_pat_dispatch" in SQL)
chk("자리표시자면 vault 갱신 건너뜀", "if new_pat like '<%'" in SQL)
chk("dispatch 함수 anon 실행 차단",
    re.search(r"revoke execute on function public\.gh_dispatch\(text, jsonb\) from public, anon, authenticated",
              SQL) is not None)
chk("로그 테이블 RLS", "alter table public.gh_dispatch_log enable row level security" in SQL)

# ── 6. 응답 수집 ────────────────────────────────────────────────────────────
col_cron, col_cmd = jobs["gh_dispatch_collect"]
chk("응답 수집은 10분 주기(pg_net 응답 보존 6h 내)", col_cron.startswith("*/10 "), col_cron)
chk("수집 함수 호출", "gh_dispatch_collect()" in col_cmd)

# ── 7. AI 엘리엇 15분 진입 판단 (2026-10-29 사용자 지시 "진입판단을 15분마다 … 1주일만 테스트") ─────────────
q_cron, q_cmd = jobs["gh_ai_quarter"]
qf = cron_fields(q_cron)
q_minutes = sorted(int(m) for m in qf[0].split(","))
chk("15분 틱: 매시 :18/:33/:48", q_minutes == [18, 33, 48] and qf[1:] == ["*", "*", "*", "*"], q_cron)
chk("15분 틱 + fast(:03) = 15분 간격", sorted(q_minutes + [int(f[0])]) == [3, 18, 33, 48], (q_minutes, f[0]))
chk("15분 틱은 ai_quarter.yml 을 inputs 없이 호출", q_cmd == "select public.gh_dispatch('ai_quarter.yml')", q_cmd)
aq = wf("ai_quarter.yml")
chk("ai_quarter.yml 존재·workflow_dispatch 수신·inputs 없음", "workflow_dispatch:" in aq and "inputs:" not in aq)
chk("ai_quarter.yml 에 GitHub schedule 없음(외부 트리거 전용)", re.search(r"^\s*schedule:", aq, re.M) is None)


def group_of(text):
    m = re.search(r"concurrency:\s*\n\s*group:\s*(\S+)", text)
    return m.group(1) if m else None


chk("ai_quarter 는 메인 스케줄러와 다른 concurrency 그룹(메인 대기 실행을 취소시키지 않게)",
    group_of(aq) and group_of(aq) != group_of(wf("fast_scheduler.yml"))
    and group_of(wf("fast_scheduler.yml")) == group_of(wf("daily_scheduler.yml")),
    (group_of(aq), group_of(wf("fast_scheduler.yml"))))
gate = aq.split("- name: Gate", 1)[1].split("- name: Setup Python", 1)[0] if "- name: Gate" in aq else ""
lo, hi = (int(x) for x in re.search(r'\[ "\$m" -lt (\d+) \] \|\| \[ "\$m" -gt (\d+) \]', gate).groups())
chk("게이트 시각 창이 15분 틱 분을 모두 덮고 메인 틱(:00·:03)은 밖", all(lo <= m <= hi for m in q_minutes)
    and not (lo <= 0 <= hi) and not (lo <= int(f[0]) <= hi), (lo, hi))
chk("게이트: 시험 기간(entry_check_active) 확인", "entry_check_active()" in gate)
chk("게이트: daily·fast 실행 중·대기면 건너뜀", "daily_scheduler.yml fast_scheduler.yml" in gate
    and 'select(.status != "completed")' in gate)
chk("게이트: 조회 실패면 건너뜀(fail-closed)", "fail-closed" in gate and gate.count('echo "go=no"') >= 4)
chk("게이트 통과일 때만 설치·실행", aq.count("if: steps.gate.outputs.go == 'yes'") >= 4
    and "python paper_executor.py aitick" in aq)
chk("게이트는 Actions 읽기 권한만", re.search(r"permissions:\s*\n\s*contents: read\s*\n\s*actions: read", aq) is not None)
tmo = int(re.search(r"^    timeout-minutes: (\d+)", aq, re.M).group(1))
chk("마지막 15분 틱(:48)도 다음 메인 실행(:00) 전에 끝난다", max(q_minutes) + tmo < 60, (max(q_minutes), tmo))
chk("시험 기간 판정이 표준 라이브러리만으로(게이트는 의존성 설치 전)",
    "import requests" not in open(os.path.join(HERE, "ai_elliott.py"), encoding="utf-8").read()
    and "import exit_barriers as xb" in open(os.path.join(HERE, "ai_elliott.py"), encoding="utf-8").read())

print()
print(f"{'ALL PASS' if not fails else 'FAILED: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
