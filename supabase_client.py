"""
supabase_client.py — 공용 Supabase 클라이언트.
환경변수에서 키를 읽어 클라이언트를 반환. 키는 코드에 하드코딩하지 않는다.
  SUPABASE_URL, SUPABASE_SERVICE_KEY(쓰기), SUPABASE_ANON_KEY(읽기)
키가 없으면 명확한 에러. available()로 사용 가능 여부만 조용히 확인 가능.
"""
import os

# 로컬 개발: 프로젝트 루트 .env 파일에서 키를 로드.
# GitHub Actions는 Secrets로 주입되므로 .env 불필요. .env는 .gitignore에 있어 커밋 안 됨.
try:
    from dotenv import load_dotenv
    load_dotenv(override=False)   # 이미 설정된 환경변수는 덮어쓰지 않음
except ImportError:
    pass

_cache = {}


def available():
    return bool(os.environ.get("SUPABASE_URL") and
                (os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_ANON_KEY")))


def key_role(key):
    """Supabase 키(JWT)의 role 클레임을 검증 없이 디코드해 반환('service_role'/'anon'/None)."""
    if not key:
        return None
    try:
        import jwt
        return jwt.decode(key, options={"verify_signature": False}).get("role")
    except Exception:
        return None


def get_client(role="service"):
    """role='service'(쓰기, RLS 우회) 또는 'anon'(읽기) 클라이언트 반환."""
    if role in _cache:
        return _cache[role]
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY") if role == "service" \
        else os.environ.get("SUPABASE_ANON_KEY")
    if not url or not key:
        raise RuntimeError(
            "Supabase 환경변수 미설정: SUPABASE_URL 및 "
            f"SUPABASE_{'SERVICE' if role == 'service' else 'ANON'}_KEY 를 설정하세요 "
            "(.env 또는 GitHub Secrets).")
    # 슬롯-키 불일치 감지(흔한 permission denied 원인): service 슬롯에 anon 키 등
    kr = key_role(key)
    if role == "service" and kr and kr != "service_role":
        raise RuntimeError(
            f"SUPABASE_SERVICE_KEY 에 service_role 키가 아니라 '{kr}' 키가 들어있습니다. "
            "Supabase > Project Settings > Data API 의 'service_role secret' 값을 다시 넣으세요. "
            "(anon 키로는 RLS에 막혀 permission denied가 납니다.)")
    from supabase import create_client
    cli = create_client(url, key)
    _cache[role] = cli
    return cli


def insert_tolerant(cli, table, rows):
    """
    스키마 내성 INSERT: 테이블에 없는 컬럼(PGRST204)을 에러 메시지에서 파싱해
    해당 키를 제거하고 재시도한다. (예: positions.live_mode, signals.ensemble_grade
    컬럼 미존재로 insert 전체가 실패해 데이터가 유실되던 문제의 방어막)

    성공 시 (inserted_rows, dropped_columns) 반환, 실패 시 예외 전파.
    """
    import re
    rows = [dict(r) for r in rows]   # 원본 보호
    dropped = []
    for _ in range(8):               # 최대 8개 컬럼까지 제거 시도
        try:
            res = cli.table(table).insert(rows).execute()
            return (res.data or []), dropped
        except Exception as e:
            m = re.search(r"Could not find the '(\w+)' column", str(e))
            if not m:
                raise
            col = m.group(1)
            dropped.append(col)
            rows = [{k: v for k, v in r.items() if k != col} for r in rows]
    raise RuntimeError(f"insert_tolerant: {table} 컬럼 제거 한도 초과 (dropped={dropped})")


def project_ref():
    """SUPABASE_URL(https://<ref>.supabase.co)에서 프로젝트 ref 추출."""
    url = os.environ.get("SUPABASE_URL", "")
    if "//" in url:
        host = url.split("//", 1)[1].split(".", 1)[0]
        return host or None
    return None
