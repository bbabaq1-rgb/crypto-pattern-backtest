"""
funding_accrual.py — BTC 무기한 펀딩비 일별 이력 적재 (2026-09-04 신설).

**시험이 아니라 데이터 확보다.** `quant_exit_catalog.md` 의 '펀딩비 극단 청산'(B+)은
크립토 고유이고 구현 비용도 낮은데, 지금 시험할 수 없다 — OKX 가 펀딩 이력을 약 94일만
제공하기 때문이다(report_regime_quality.md: funding_cap 후보가 '미검증'으로 남은 이유).
94일로는 동결 게이트(OOS 4분할)도 레짐 층화도 성립하지 않는다.

그래서 지금 할 일은 시험이 아니라 **매 실행 적재를 시작해 6개월 뒤 시험 가능하게 만드는 것**이다.
러너 파일시스템은 매 실행 비어 있으므로 로컬 JSON 캐시로는 누적되지 않는다 → Supabase 에 넣는다.

성질:
  · **매매에 일절 관여하지 않는다.** 스케줄러에서 try/except 로 감싸 호출하며, 실패해도
    로그 한 줄만 남기고 진행한다. 테이블이 없으면 조용히 건너뛴다.
  · 멱등 — 같은 날짜를 다시 넣어도 (date, inst) 유일키로 덮어쓴다.
  · 적재만 하고 **읽어 쓰는 코드는 아직 없다**. 규칙 변경이 아니다.

테이블(사용자가 supabase_schema_funding.sql 실행 필요):
  funding_daily(date date, inst text, rate double precision, primary key(date, inst))
"""
import sys

INST = "BTC-USDT-SWAP"
LOOKBACK_DAYS = 120        # OKX 제공 한계(약 94일)보다 넉넉히 요청 — 겹치는 구간은 덮어쓴다
TABLE = "funding_daily"


def accrue(inst=INST, days=LOOKBACK_DAYS, quiet=False):
    """(넣은 행 수, 메시지). 어떤 실패도 예외를 밖으로 던지지 않는다."""
    try:
        import regime_alt as ra
        import supabase_client as sc
    except Exception as e:
        return 0, f"모듈 없음({str(e)[:40]})"
    if not sc.available():
        return 0, "Supabase 미설정"
    try:
        # 캐시 파일을 쓰지 않도록 별도 경로 — 러너에서는 어차피 매번 비어 있다.
        hist = ra.fetch_funding_history(inst=inst, days=days,
                                        cache="_funding_accrual_tmp.json", quiet=True)
    except Exception as e:
        return 0, f"fetch 실패({str(e)[:40]})"
    if not hist:
        return 0, "이력 없음"
    rows = [dict(date=d, inst=inst, rate=float(v)) for d, v in sorted(hist.items())]
    try:
        cli = sc.get_client()
        if cli is None:
            return 0, "클라이언트 없음"
        cli.table(TABLE).upsert(rows, on_conflict="date,inst").execute()
    except Exception as e:
        msg = str(e)[:60]
        if "does not exist" in msg or "PGRST205" in msg or "42P01" in msg:
            return 0, f"{TABLE} 테이블 없음 — supabase_schema_funding.sql 실행 필요"
        return 0, f"업서트 실패({msg})"
    if not quiet:
        print(f"  [funding 적재] {inst} {len(rows)}일 ({rows[0]['date']}~{rows[-1]['date']})")
    return len(rows), "ok"


if __name__ == "__main__":
    n, msg = accrue(quiet=False)
    print(f"적재 {n}행 — {msg}")
    sys.exit(0)
