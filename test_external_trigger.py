"""
외부 트리거(Supabase pg_cron → GitHub workflow_dispatch) 정의 고정.

supabase_external_trigger.sql 은 레포 밖(Supabase)에서 실행되는 SQL 이라 CI 가 직접
돌릴 수 없다. 대신 이 파일이 **레포와 어긋나면 실거래 케이던스가 바뀌는 지점**을
문자열 수준에서 고정한다:
  · 호출하는 워크플로 파일이 실제로 존재하고 workflow_dispatch 를 받는다
  · daily 의 mode 입력값이 yml 이 아는 값이고, 발화 시각이 SLOW_TICK_HOURS 와 같다
  · fast 는 inputs 없이 호출한다 (yml 에 inputs 가 없어 보내면 422)
  · GitHub 자체 schedule 은 폴백으로 남아 있다 (둘 다 없으면 아무것도 안 돈다)
  · 토큰 리터럴이 파일에 없다

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
chk("크론 4개 등록", set(jobs) == {"gh_fast_scheduler", "gh_daily_oncefull",
                                   "gh_daily_oncequick", "gh_dispatch_collect"}, sorted(jobs))


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
    chk(f"{name} GitHub schedule 폴백 유지", re.search(r"^\s*schedule:", wf(name), re.M) is not None)
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

print()
print(f"{'ALL PASS' if not fails else 'FAILED: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
