"""
test_perp_accrual.py — 무기한 펀딩비·OI 일별 적재 검증 (2026-09-08).

**적재 전용 모듈이다** — 매매 코드가 이 테이블을 읽지 않는다는 성질까지 여기서 고정한다.
네트워크 없이 _get 을 스텁으로 갈아끼워 파싱·집계·업서트 분리·시간 상한만 본다.

실행: python test_perp_accrual.py
"""
import sys

import perp_accrual as pa

fails = []


def check(n, c, d=""):
    print(("PASS " if c else "FAIL ") + n + ("" if c else f" — {d}"))
    c or fails.append(n)


# ── 1. 심볼 파싱 — 접미사 길이 하드코딩 버그 재발 방지 ────────────────────────
# 실제로 [:-11] 오프셋 탓에 'ETHW-USDT-SWAP' 이 'ETH' 로 잡혀 다른 종목 데이터가 섞였다.
check("BTC-USDT-SWAP → BTC", pa._sym("BTC-USDT-SWAP") == "BTC")
check("ETHW 는 ETH 로 잡히지 않는다(접미사 오프셋 버그)", pa._sym("ETHW-USDT-SWAP") == "ETHW")
check("한 글자 심볼도 정확", pa._sym("W-USDT-SWAP") == "W")
check("USDT 무기한이 아니면 None",
      pa._sym("BTC-USD-SWAP") is None and pa._sym("BTC-USDT-250101") is None)

# ── 2. 스냅샷 — 두 호출을 심볼로 합치고 유니버스 밖은 버린다 ──────────────────
FUND = {"data": [{"instId": "BTC-USDT-SWAP", "fundingRate": "0.0001"},
                 {"instId": "ETH-USDT-SWAP", "fundingRate": "-0.0002"},
                 {"instId": "DOGE-USDT-SWAP", "fundingRate": "0.5"},      # 유니버스 밖
                 {"instId": "BTC-USD-SWAP", "fundingRate": "9.9"}]}       # 코인마진 — 제외
OI = {"data": [{"instId": "BTC-USDT-SWAP", "oiCcy": "28000", "oiUsd": "2.2e9", "ts": "1788854637150"},
               {"instId": "ETH-USDT-SWAP", "oiCcy": "630000", "oiUsd": "1.5e9", "ts": "1788854637150"}]}


def stub(mapping):
    """가장 **긴** 키부터 매칭 — 'open-interest' 가 'open-interest-volume' 요청을 가로채면
    dict 응답을 리스트로 파싱하려다 죽는다(실제로 겪음)."""
    def _get(path, params=None):
        for key in sorted(mapping, key=len, reverse=True):
            if key in path:
                return mapping[key]
        return {"data": []}
    return _get


orig_get = pa._get
pa._get = stub({"funding-rate?": FUND, "funding-rate": FUND, "open-interest": OI})
snap = pa.snapshot(["BTC", "ETH"])
pa._get = orig_get
check("스냅샷: 유니버스 종목만", sorted(snap) == ["BTC", "ETH"], sorted(snap))
check("스냅샷: 펀딩·OI 가 한 행으로 합쳐진다",
      snap["BTC"] == {"funding_snap": 0.0001, "oi_snap_ccy": 28000.0,
                      "oi_snap_usd": 2.2e9, "oi_snap_ts": 1788854637150}, snap["BTC"])
check("스냅샷: 음수 펀딩도 보존", snap["ETH"]["funding_snap"] == -0.0002)

# ── 3. 펀딩 일별 집계 — 8h 정산을 UTC 날짜로 묶어 평균 ───────────────────────
D0 = 1788739200000           # 2026-09-07 00:00Z (자정 — 16:00Z 를 자정으로 착각한 픽스처 버그 수정)
HIST = {"data": [{"fundingTime": str(D0), "realizedRate": "0.001"},
                 {"fundingTime": str(D0 + 8 * 3600_000), "realizedRate": "0.003"},
                 {"fundingTime": str(D0 + 16 * 3600_000), "realizedRate": "0.002"},
                 {"fundingTime": str(D0 + 24 * 3600_000), "realizedRate": "0.010"},
                 {"fundingTime": str(D0 + 32 * 3600_000), "fundingRate": "0.020"},   # realized 없음 → 폴백
                 {"fundingTime": str(D0 + 40 * 3600_000), "realizedRate": ""}]}      # 빈 값 → 무시
pa._get = stub({"funding-rate-history": HIST})
fh = pa.funding_history("BTC")
pa._get = orig_get
check("펀딩: 같은 날 정산 평균 + 횟수",
      abs(fh["2026-09-07"][0] - 0.002) < 1e-12 and fh["2026-09-07"][1] == 3, fh)
check("펀딩: realizedRate 없으면 fundingRate 로 폴백",
      abs(fh["2026-09-08"][0] - 0.015) < 1e-12 and fh["2026-09-08"][1] == 2, fh)
check("펀딩: 빈 값은 집계에서 제외", "2026-09-09" not in fh, fh)

# ── 4. rubik OI 일별 ─────────────────────────────────────────────────────────
RUBIK = {"data": [[str(D0 + 86400000), "17299172.85", "274737779.18"],
                  [str(D0), "20330536.15", "575941685.64"],
                  ["bad", "x", "y"]]}
pa._get = stub({"open-interest-volume": RUBIK})
oh = pa.oi_history("ARB")
pa._get = orig_get
check("OI 일별: [ts, ccy, usd] 파싱",
      oh["2026-09-07"] == (20330536.15, 575941685.64), oh)
check("OI 일별: 깨진 행은 건너뛴다", len(oh) == 2, oh)
pa._get = stub({"open-interest-volume": RUBIK})
check("OI 일별: days 로 자른다", len(pa.oi_history("ARB", days=1)) == 1)
pa._get = orig_get

# ── 5. 업서트는 스냅샷/백필을 따로 — 컬럼이 섞이면 NULL 덮어쓰기 ─────────────
sent = []
orig_up = pa._upsert
pa._upsert = lambda rows: (sent.append([sorted(r) for r in rows]) or (len(rows), ""))
pa._get = stub({"funding-rate": FUND, "open-interest?": OI, "open-interest": OI,
                "funding-rate-history": HIST, "open-interest-volume": RUBIK})
n, msg = pa.accrue(["BTC"], full=True, quiet=True)
pa._upsert, pa._get = orig_up, orig_get
colsets = [set(tuple(c) for c in batch) for batch in sent]
check("업서트 3번 — 스냅샷 / 펀딩 / OI", len(sent) == 3, len(sent))
snap_cols = set().union(*colsets[0]) if colsets else set()
check("스냅샷 업서트에 funding_rate·oi_day 가 섞이지 않는다",
      "funding_rate" not in snap_cols and "oi_day_usd" not in snap_cols, sorted(snap_cols))
fund_cols = set().union(*colsets[1])
check("펀딩 백필 업서트에 OI 컬럼이 섞이지 않는다",
      fund_cols == {"date", "symbol", "funding_rate", "funding_n"}, sorted(fund_cols))
oi_cols = set().union(*colsets[2])
check("OI 백필 업서트에 펀딩 컬럼이 섞이지 않는다",
      oi_cols == {"date", "symbol", "oi_day_ccy", "oi_day_usd"}, sorted(oi_cols))
check("각 배치 안에서 행들의 컬럼 집합이 동일(PostgREST NULL 덮어쓰기 방지)",
      all(len(cs) == 1 for cs in colsets), [len(cs) for cs in colsets])

# 6) full=False 는 스냅샷만
sent.clear()
pa._upsert = lambda rows: (sent.append(rows) or (len(rows), ""))
pa._get = stub({"funding-rate": FUND, "open-interest": OI})
n2, msg2 = pa.accrue(["BTC"], full=False, quiet=True)
pa._upsert, pa._get = orig_up, orig_get
check("full=False 는 업서트 1번(스냅샷)", len(sent) == 1 and "스냅샷" in msg2, (len(sent), msg2))

# 7) 시간 상한 — 넘으면 남은 종목을 다음 실행으로 넘긴다
pa._upsert = lambda rows: (len(rows), "")
pa._get = stub({"funding-rate": FUND, "open-interest": OI,
                "funding-rate-history": HIST, "open-interest-volume": RUBIK})
n3, msg3 = pa.accrue(["BTC", "ETH", "SOL"], full=True, quiet=True, deadline_sec=-1)
pa._upsert, pa._get = orig_up, orig_get
check("deadline 초과 시 백필을 중단하고 알린다", "시간 초과" in msg3, msg3)

# 8) 실패해도 예외가 밖으로 나가지 않는다
pa._upsert = lambda rows: (0, "perp_daily 테이블 없음 — supabase_schema_perp.sql 실행 필요")
pa._get = stub({"funding-rate": FUND, "open-interest": OI})
n4, msg4 = pa.accrue(["BTC"], full=True, quiet=True)
pa._upsert, pa._get = orig_up, orig_get
check("테이블 없으면 조용히 안내 메시지", "테이블 없음" in msg4 and n4 == 0, msg4)


def boom(*a, **k):
    raise RuntimeError("네트워크 끊김")


pa._get = boom
n5, msg5 = pa.accrue(["BTC"], full=False, quiet=True)
pa._get = orig_get
check("네트워크 예외가 밖으로 나가지 않는다", isinstance(n5, int), (n5, msg5))
check("유니버스가 비면 조용히 종료", pa.accrue([], full=True, quiet=True) == (0, "유니버스 없음"))

# ── 9. 매매 무관 — 배선과 성질 고정 ──────────────────────────────────────────
src_s = open("scheduler.py", encoding="utf-8").read()
src_pe = open("paper_executor.py", encoding="utf-8").read()
check("체결 엔진은 적재 모듈을 import 하지 않는다",
      "perp_accrual" not in src_pe and "funding_accrual" not in src_pe)
check("적재는 주문·청산이 끝난 뒤([7] daily_summary 이후) 돈다",
      src_s.index("[8] 무기한 펀딩비·OI 적재") > src_s.index("[7] daily_summary"))
check("적재 호출부가 [2.5](주문 앞)에서 제거됐다",
      "[funding 적재] 건너뜀" not in src_s)
check("백필은 oncefull 에서만(느린틱 스냅샷은 매번)",
      '"full": bool(do_fetch and not quick)' in src_s and "if slow_tick:" in src_s)
check("적재는 try/except 로 감싸 매매를 막지 않는다",
      "except Exception as _e:" in src_s and "건너뜀" in src_s)
check("perp_accrual 은 매매 모듈을 import 하지 않는다",
      not any(m in open("perp_accrual.py", encoding="utf-8").read()
              for m in ("import paper_executor", "import exchange", "import scheduler")))
check("기본 유니버스는 universe.json trading_universe", len(pa.universe()) >= 20)

print(f"\n{len(fails)} failed")
sys.exit(1 if fails else 0)
