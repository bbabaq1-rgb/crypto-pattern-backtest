"""
supabase_client.py — 공용 Supabase 클라이언트.
환경변수에서 키를 읽어 클라이언트를 반환. 키는 코드에 하드코딩하지 않는다.
  SUPABASE_URL, SUPABASE_SERVICE_KEY(쓰기), SUPABASE_ANON_KEY(읽기)
키가 없으면 명확한 에러. available()로 사용 가능 여부만 조용히 확인 가능.
"""
import os

_cache = {}


def available():
    return bool(os.environ.get("SUPABASE_URL") and
                (os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_ANON_KEY")))


def get_client(role="service"):
    """role='service'(쓰기) 또는 'anon'(읽기) 클라이언트 반환."""
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
    from supabase import create_client
    cli = create_client(url, key)
    _cache[role] = cli
    return cli


def project_ref():
    """SUPABASE_URL(https://<ref>.supabase.co)에서 프로젝트 ref 추출."""
    url = os.environ.get("SUPABASE_URL", "")
    if "//" in url:
        host = url.split("//", 1)[1].split(".", 1)[0]
        return host or None
    return None
