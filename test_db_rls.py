"""test_db_rls.py — 거래 장부 테이블 접근 제한(2026-11-10)이 레포에서 뒤집히지 않게 고정한다.

DB 쪽 실제 상태는 supabase_rls_2026_11_10.sql 이 적용된 결과다(이 테스트는 DB 에 접속하지 않는다).
여기서 고정하는 것:
  1) SQL 파일이 4개 테이블 모두 RLS 를 켜고 anon/authenticated 권한을 회수한다. 정책은 만들지 않는다.
  2) 레포의 어떤 SQL 도 그 4개 테이블에 RLS 를 끄거나 anon 에 권한을 주지 않는다.
  3) dashboard.py 는 service 키를 먼저 쓴다(anon 키로는 빈 결과).
  4) 장부를 쓰는 코드는 anon 클라이언트로 쓰지 않는다(쓰기는 service_role 만 — RLS 우회).
"""
import glob
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
TABLES = ("trades", "positions", "signals", "daily_summary")
_fail = []


def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        _fail.append(msg)


def read(path):
    with open(os.path.join(HERE, path), encoding="utf-8") as f:
        return f.read()


def sql_body(text):
    """주석 줄을 뺀 SQL 본문(소문자, 공백 정규화)."""
    lines = [ln.split("--", 1)[0] for ln in text.splitlines()]
    return re.sub(r"\s+", " ", " ".join(lines)).lower()


# 1) 적용 SQL
sql = sql_body(read("supabase_rls_2026_11_10.sql"))
for t in TABLES:
    check(f"alter table public.{t} enable row level security" in sql, f"RLS 켜기 — {t}")
revoke = re.search(r"revoke all on table ([^;]+) from anon, authenticated", sql)
check(revoke is not None, "anon·authenticated 권한 회수 문장 존재")
if revoke:
    for t in TABLES:
        check(f"public.{t}" in revoke.group(1), f"권한 회수 대상 — {t}")
check("create policy" not in sql, "정책을 만들지 않는다(외부 접근 전부 차단)")
check(not re.search(r"grant [^;]* to [^;]*\banon\b", sql), "anon 에 권한을 주지 않는다")

# 2) 레포 전체 SQL 이 그 4개 테이블을 다시 열지 않는다
for path in sorted(glob.glob(os.path.join(HERE, "*.sql"))):
    body = sql_body(open(path, encoding="utf-8").read())
    name = os.path.basename(path)
    for t in TABLES:
        check(f"alter table public.{t} disable row level security" not in body
              and f"alter table {t} disable row level security" not in body,
              f"{name}: {t} RLS 끄기 없음")
        bad = re.search(rf"grant [^;]* on (table )?(public\.)?[^;]*\b{t}\b[^;]* to [^;]*\b(anon|authenticated)\b", body)
        check(bad is None, f"{name}: {t} 를 anon·authenticated 에 열지 않음")

# 2b) 설치 스크립트가 만드는 SQL(schema.sql·fix_rls.sql 원본)도 같은 규칙을 지킨다.
#     2026-11-10 이전에는 이 문자열이 RLS 를 끄고 anon 에 grant all 을 줬다 — DB 가 열려 있던 원인.
import ast  # noqa: E402
_setup = {}
for node in ast.parse(read("supabase_setup.py")).body:
    if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) \
            and node.targets[0].id in ("SCHEMA", "FIX_RLS"):
        _setup[node.targets[0].id] = node.value.value
for name, fname in (("SCHEMA", "schema.sql"), ("FIX_RLS", "fix_rls.sql")):
    body = sql_body(_setup.get(name, ""))
    for t in TABLES:
        check(f"alter table {t} enable row level security" in body, f"supabase_setup.{name}: {t} RLS 켜기")
        check("disable row level security" not in body, f"supabase_setup.{name}: RLS 끄기 없음 ({t})")
    check(not re.search(r"grant [^;]* to [^;]*\b(anon|authenticated)\b", body),
          f"supabase_setup.{name}: anon·authenticated 에 권한 주지 않음")
    check("from anon, authenticated" in body, f"supabase_setup.{name}: anon·authenticated 권한 회수")
    check(read(fname) == _setup.get(name), f"{fname} 이 supabase_setup.{name} 과 같다(재생성 일치)")

# 3) dashboard 는 service 키를 먼저 쓴다
dash = read("dashboard.py")
m = re.search(r'key = os\.environ\.get\("(\w+)"\) or os\.environ\.get\("(\w+)"\)', dash)
check(m is not None and m.group(1) == "SUPABASE_SERVICE_KEY",
      "dashboard.py 가 SUPABASE_SERVICE_KEY 를 먼저 쓴다")

# 4) 장부 테이블 쓰기는 anon 클라이언트로 하지 않는다
writes = re.compile(r'get_client\(\s*["\']anon["\']\s*\)\s*\.table\(\s*["\'](\w+)["\']\s*\)\s*\.(insert|upsert|update|delete)')
for path in sorted(glob.glob(os.path.join(HERE, "*.py"))):
    if os.path.basename(path).startswith("test_"):
        continue
    src = open(path, encoding="utf-8").read()
    for mm in writes.finditer(src):
        check(mm.group(1) not in TABLES, f"{os.path.basename(path)}: anon 클라이언트로 {mm.group(1)} 쓰기 없음")
sc = read("supabase_client.py")
check('def get_client(role="service")' in sc, "supabase_client.get_client 기본값은 service")

print(f"\n{'FAIL' if _fail else 'PASS'} — 실패 {len(_fail)}건")
raise SystemExit(1 if _fail else 0)
