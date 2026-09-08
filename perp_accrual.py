"""
perp_accrual.py — 무기한 **펀딩비 + 미결제약정(OI)** 일별 적재 (2026-09-08, 사용자 지시).

**시험이 아니라 데이터 확보다.** 매매 로직은 이 테이블을 읽지 않는다(테스트가 고정).

## 왜 지금 시작하나
  · 펀딩 이력: OKX 는 `funding-rate-history` 를 약 3개월만 준다(2026-09-08 실측 오래된 값 2026-06-03).
    '펀딩비 극단' 계열 시험(quant_exit_catalog B+)은 최소 1~2년이 필요해 지금은 못 돈다.
  · OI: **종목별 OI 는 스냅샷뿐 이력이 없다.** 통화 단위 rubik 일별은 180일까지 준다.
    즉 지금 안 쌓으면 그 구간은 영영 못 만든다.

## 두 가지 측정을 섞지 않는다 (컬럼 분리)
  · `oi_snap_*`  — 그 종목의 USDT 무기한 **스냅샷**(호출 시점). 이력 없음 → 놓치면 끝.
  · `oi_day_*`   — rubik 통화 일별(해당 통화의 **모든 계약** 합산, USD/USDC 마진 포함). 180일 백필 가능.
  · `funding_rate`/`funding_n` — 그날 **정산된** 요율의 평균과 정산 횟수(8h 주기 → 보통 3). 백필 가능.
  · `funding_snap` — 스냅샷 시점의 '현재 기간' 예상 요율. 정산값과 다르다.

## 호출 비용 (2026-09-08 실측)
  · 가벼운 틱(매 느린틱): `funding-rate?instId=ANY` 1회 + `open-interest?instType=SWAP` 1회 = **2회 · 약 1초**.
    한 번에 458개 USDT 무기한이 다 온다.
  · 무거운 틱(oncefull, 하루 1회): 위 + 종목별 펀딩 이력 80회 + 통화별 rubik 80회 ≈ **160회 · 약 70초**.
    둘 다 백필 가능한 소스라 **하루를 통째로 놓쳐도 다음 무거운 틱이 메운다**.

## 안전
  · 매매에 일절 관여하지 않는다 — 스케줄러가 **주문·청산이 모두 끝난 뒤**([7] 이후) try/except 로 부른다.
  · DEADLINE_SEC 로 시간을 자른다. 초과하면 그때까지 모은 것만 넣고 반환한다.
  · 테이블이 없으면 조용히 건너뛴다(사용자가 supabase_schema_perp.sql 실행 필요).
  · 멱등 — (date, symbol) 유일키 업서트. 스냅샷/백필은 **컬럼이 겹치지 않게** 따로 업서트한다
    (한 번의 업서트에 섞으면 빠진 컬럼이 NULL 로 덮일 수 있다).

실행: python perp_accrual.py [--full]        테이블: supabase_schema_perp.sql
"""
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone

TABLE = "perp_daily"
BASE = "https://www.okx.com"
UA = {"User-Agent": "Mozilla/5.0"}
TIMEOUT = 20
DEADLINE_SEC = 240          # 무거운 틱 전체 상한 — 넘으면 모은 것만 저장
FUNDING_PAGE = 100          # 종목당 정산 1페이지(약 33일) — 갭 복구엔 충분
OI_BACKFILL_DAYS = 180      # rubik 이 주는 최대치
CHUNK = 1000                # 업서트 배치


def _get(path, params=None):
    url = BASE + path
    if params:
        url += "?" + "&".join(f"{k}={v}" for k, v in params.items())
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=TIMEOUT) as r:
        return json.loads(r.read().decode())


def _day(ms):
    return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


SWAP_SUFFIX = "-USDT-SWAP"


def _sym(inst_id):
    """BTC-USDT-SWAP -> BTC. USDT 무기한이 아니면 None.

    len(SWAP_SUFFIX) 로 자른다 — 하드코딩 오프셋을 쓰면 한 글자만 어긋나도
    'ETHW-USDT-SWAP' 이 'ETH' 로 잡혀 **다른 종목의 데이터가 섞인다**(실제로 발생, 테스트로 고정).
    """
    return inst_id[:-len(SWAP_SUFFIX)] if inst_id.endswith(SWAP_SUFFIX) else None


def universe():
    try:
        return json.load(open("universe.json", encoding="utf-8"))["trading_universe"]
    except Exception:
        return []


# ── 스냅샷 (2회 호출) ──────────────────────────────────────────────────────────
def snapshot(symbols):
    """{symbol: {funding_snap, oi_snap_ccy, oi_snap_usd, oi_snap_ts}} — 오늘 하루치."""
    want = set(symbols)
    out = {}
    try:
        for x in _get("/api/v5/public/funding-rate", {"instId": "ANY"}).get("data", []):
            s = _sym(x.get("instId", ""))
            if s in want and x.get("fundingRate") not in (None, ""):
                out.setdefault(s, {})["funding_snap"] = float(x["fundingRate"])
    except Exception as e:
        print(f"  [perp] funding 스냅샷 실패: {str(e)[:60]}")
    try:
        for x in _get("/api/v5/public/open-interest", {"instType": "SWAP"}).get("data", []):
            s = _sym(x.get("instId", ""))
            if s not in want:
                continue
            d = out.setdefault(s, {})
            for key, src in (("oi_snap_ccy", "oiCcy"), ("oi_snap_usd", "oiUsd")):
                if x.get(src) not in (None, ""):
                    d[key] = float(x[src])
            if x.get("ts"):
                d["oi_snap_ts"] = int(x["ts"])
    except Exception as e:
        print(f"  [perp] OI 스냅샷 실패: {str(e)[:60]}")
    return out


# ── 백필 (종목당 1회씩) ───────────────────────────────────────────────────────
def funding_history(symbol):
    """{date: (평균 정산 요율, 정산 횟수)} — 최근 1페이지."""
    try:
        data = _get("/api/v5/public/funding-rate-history",
                    {"instId": f"{symbol}-USDT-SWAP", "limit": FUNDING_PAGE}).get("data", [])
    except Exception:
        return {}
    acc = {}
    for x in data:
        rate = x.get("realizedRate") or x.get("fundingRate")
        if rate in (None, "") or not x.get("fundingTime"):
            continue
        acc.setdefault(_day(x["fundingTime"]), []).append(float(rate))
    return {d: (sum(v) / len(v), len(v)) for d, v in acc.items()}


def oi_history(symbol, days=OI_BACKFILL_DAYS):
    """{date: (oi_ccy, oi_usd)} — rubik 통화 일별(해당 통화 전체 계약 합산)."""
    try:
        data = _get("/api/v5/rubik/stat/contracts/open-interest-volume",
                    {"ccy": symbol, "period": "1D"}).get("data", [])
    except Exception:
        return {}
    out = {}
    for row in data[:days]:
        try:
            out[_day(row[0])] = (float(row[1]), float(row[2]))
        except (IndexError, KeyError, TypeError, ValueError):
            continue        # 응답 모양이 바뀌어도 적재가 매매 뒤에서 조용히 끝나도록
    return out


# ── 업서트 ────────────────────────────────────────────────────────────────────
def _upsert(rows):
    """(넣은 행 수, 오류 메시지). 컬럼 집합이 같은 행들만 한 번에 보낸다."""
    if not rows:
        return 0, ""
    try:
        import supabase_client as sc
    except Exception as e:
        return 0, f"모듈 없음({str(e)[:40]})"
    if not sc.available():
        return 0, "Supabase 미설정"
    cli = sc.get_client()
    if cli is None:
        return 0, "클라이언트 없음"
    n = 0
    for i in range(0, len(rows), CHUNK):
        try:
            cli.table(TABLE).upsert(rows[i:i + CHUNK], on_conflict="date,symbol").execute()
            n += len(rows[i:i + CHUNK])
        except Exception as e:
            msg = str(e)[:70]
            if "does not exist" in msg or "PGRST205" in msg or "42P01" in msg:
                return n, f"{TABLE} 테이블 없음 — supabase_schema_perp.sql 실행 필요"
            return n, f"업서트 실패({msg})"
    return n, ""


def accrue(symbols=None, full=False, quiet=False, deadline_sec=DEADLINE_SEC):
    """
    (넣은 행 수, 메시지). 어떤 실패도 예외를 밖으로 던지지 않는다.
    full=False 는 스냅샷만(2회 호출), True 는 종목별 백필까지.
    """
    t0 = time.time()
    # `or` 대신 None 검사 — 빈 리스트를 넘겼는데 유니버스 전체로 확장되면
    # 호출자가 의도한 '아무것도 안 함'이 80종목 수집으로 바뀐다.
    symbols = universe() if symbols is None else symbols
    if not symbols:
        return 0, "유니버스 없음"
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    total, err = 0, ""

    snap = snapshot(symbols)
    if snap:
        keys = ("funding_snap", "oi_snap_ccy", "oi_snap_usd", "oi_snap_ts")
        rows = [dict(date=today, symbol=s, **{k: v.get(k) for k in keys})
                for s, v in sorted(snap.items())]
        n, err = _upsert(rows)
        total += n
        if err:
            return total, err
        if not quiet:
            print(f"  [perp] 스냅샷 {n}종목 ({today})")

    if not full:
        return total, "ok(스냅샷)"

    fund_rows, oi_rows, done, skipped = [], [], 0, 0
    for s in symbols:
        if time.time() - t0 > deadline_sec:
            skipped = len(symbols) - done
            break
        for d, (rate, cnt) in funding_history(s).items():
            fund_rows.append(dict(date=d, symbol=s, funding_rate=rate, funding_n=cnt))
        for d, (ccy, usd) in oi_history(s).items():
            oi_rows.append(dict(date=d, symbol=s, oi_day_ccy=ccy, oi_day_usd=usd))
        done += 1

    for label, rows in (("funding", fund_rows), ("OI", oi_rows)):
        n, err = _upsert(rows)
        total += n
        if err:
            return total, err
        if n and not quiet:
            print(f"  [perp] {label} 백필 {n}행")

    msg = f"ok(백필 {done}/{len(symbols)}종목, {time.time()-t0:.0f}s)"
    if skipped:
        msg += f" — 시간 초과로 {skipped}종목 다음 실행으로"
    return total, msg


if __name__ == "__main__":
    n, msg = accrue(full="--full" in sys.argv, quiet=False)
    print(f"적재 {n}행 — {msg}")
