"""
레짐 결정성 검증 (2026-09-03 전체 점검 후속).

  - build_regime_map 은 닫힌 봉만 쓴다: 형성 중인 오늘 봉의 가격을 바꿔도 라벨 불변,
    오늘 날짜 라벨 = 마지막 닫힌 봉 라벨(forward-fill)
  - eval_D / eval_R 은 기록된 entry_regime 을 맵 재조회보다 우선
  - 진입 시 entry_regime 기록, DB push/restore 경로에 포함
  - 스케줄러: 온체인 조정은 표시 전용(라우팅 미반영)
  - BTC.D fetch 실패 시 만료 캐시 우선(프록시 전환 금지)
  - 스키마 패치 SQL 이 코드가 밀어 넣는 컬럼을 전부 담고 있음

실행: python test_regime_determinism.py
"""
import random, re, sys, time
from datetime import datetime, timezone, timedelta

import detlib
import regime_switch as rs
import paper_executor as pe

fails = []


def check(n, c, d=""):
    print(("PASS " if c else "FAIL ") + n + ("" if c else f" — {d}"))
    c or fails.append(n)


# ── 1. build_regime_map: 닫힌 봉만 ─────────────────────────────────────────
DAY = 86_400_000
now_ms = int(time.time() * 1000)
today0 = now_ms - (now_ms % DAY)             # 오늘 00:00 UTC (형성 중인 봉의 ts)


def synth(seed, n=420, drift=0.0):
    random.seed(seed); px, rows = 100.0, []
    for i in range(n):
        ts = today0 - (n - 1 - i) * DAY
        nxt = px * (1 + drift + random.gauss(0, 0.02))
        d = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        rows.append(dict(ts=ts, date=d, o=px, h=max(px, nxt) * 1.01, l=min(px, nxt) * 0.99, c=nxt, v=1.0))
        px = nxt
    return rows


data = {"BTC": synth(1, drift=0.002), "ETH": synth(2, drift=0.001)}
for i, a in enumerate(rs.ALTS):
    data[a] = synth(10 + i)
orig_load, orig_fetch, orig_loadc = detlib.load_ohlcv, rs._fetch_btcd_from_cg, rs._load_btcd_cache
detlib.load_ohlcv = lambda sym, tf="1d": [dict(r) for r in data[sym]]
rs._fetch_btcd_from_cg = lambda: {}
rs._load_btcd_cache = lambda allow_stale=False: {}
try:
    m1 = rs.build_regime_map()
    today = data["BTC"][-1]["date"]; yday = data["BTC"][-2]["date"]
    check("오늘 날짜 라벨 존재(forward-fill)", today in m1, sorted(m1)[-3:])
    check("오늘 라벨 = 마지막 닫힌 봉 라벨", m1.get(today) == m1.get(yday), (m1.get(today), m1.get(yday)))
    # 형성 중인 봉을 극단으로 바꿔도 라벨 불변
    for sym in data:
        data[sym][-1]["c"] *= 0.5; data[sym][-1]["l"] *= 0.5
    m2 = rs.build_regime_map()
    check("형성 중인 봉 가격 변경 → 전 라벨 불변", m1 == m2, [(d, m1[d], m2.get(d)) for d in m1 if m1[d] != m2.get(d)][:3])
    # 대조군: 닫힌 봉(BTC 마지막 60일)을 급락시키면 가격 시그널이 반응한다
    # (레짐 라벨 자체는 3신호 히스테리시스라 단일 신호로는 안 바뀔 수 있다)
    p_before = rs._price_signal(rs._closed_rows(detlib.load_ohlcv("BTC")))
    for r in data["BTC"][-151:-1]:          # 200MA 기울기가 확실히 꺾이도록 150일 x0.3
        r["c"] *= 0.3; r["l"] *= 0.3; r["h"] *= 0.3; r["o"] *= 0.3
    p_after = rs._price_signal(rs._closed_rows(detlib.load_ohlcv("BTC")))
    check("닫힌 봉이 바뀌면 가격 시그널이 반응(대조군)", p_before[yday] != p_after[yday] and p_after[yday] == "down",
          (p_before[yday], p_after[yday]))
    m3 = rs.build_regime_map()
    # 마지막 봉이 이미 닫힌 경우(now 가 다음날) → forward-fill 없음, 그대로
    m4 = rs.build_regime_map(now_ms=today0 + DAY + 1)
    check("마지막 봉이 닫혀 있으면 그 봉 자체 라벨 사용(중복 fill 없음)", today in m4 and len(m4) == len(m3), (len(m4), len(m3)))
finally:
    detlib.load_ohlcv, rs._fetch_btcd_from_cg, rs._load_btcd_cache = orig_load, orig_fetch, orig_loadc

# _closed_rows 단위
rows = [dict(ts=today0 - DAY, date="a"), dict(ts=today0, date="b")]
check("_closed_rows: 형성 중인 마지막 봉 제거", [r["date"] for r in rs._closed_rows(rows)] == ["a"])
check("_closed_rows: ts 없으면 그대로(합성 데이터 호환)", rs._closed_rows([dict(date="x")]) == [dict(date="x")])

# ── 2. eval_D / eval_R entry_reg 우선 ───────────────────────────────────────
def flat(n=30):          # 30봉: ei=5 기준 만기(30봉) 전 → 미해소는 None
    return [dict(date=(datetime(2026, 1, 1) + timedelta(days=i)).strftime("%Y-%m-%d"),
                 o=100, h=100.5, l=99.5, c=100, v=1, ts=i) for i in range(n)]


rows = flat()
regmap = {r["date"]: "bear" for r in rows}          # 맵상 진입일도 bear
d_map = pe.eval_D(rows, 5, "long", set(), regmap)
d_rec = pe.eval_D(rows, 5, "long", set(), regmap, entry_reg="bull_btc")
check("eval_D: 맵 기준이면 전환 없음(만기 전 None)", d_map is None, d_map)
check("eval_D: 기록된 entry_regime(bull_btc)이 있으면 그 기준으로 첫 봉 regime_switch", d_rec and d_rec[0] == 6 and d_rec[3] == "regime_switch", d_rec)
r_rec = pe.eval_R(rows, 5, "long", set(), regmap, entry_reg="bull_btc")
check("eval_R: 기록 entry_regime(bull) → bear 진입 전환으로 청산", r_rec and r_rec[0] == 6 and r_rec[3] == "regime_switch", r_rec)
check("eval_R: 기록 entry_regime 이 bear 면 유지", pe.eval_R(rows, 5, "long", set(), regmap, entry_reg="bear") is None)
check("eval_R(숏)도 entry_reg 전달", pe.eval_R(rows, 5, "short", set(), regmap, entry_reg="bull_btc") and
      pe.eval_R(rows, 5, "short", set(), regmap, entry_reg="bull_btc")[3] == "regime_switch")

# ── 3. 기록·전달 경로 (소스 고정) ────────────────────────────────────────────
src = open("paper_executor.py", encoding="utf-8").read()
check("진입 시 entry_regime 기록", 'entry_regime=regmap.get(rows[ei]["date"])' in src)
check("청산 평가에 entry_regime 전달", 'entry_reg=pos.get("entry_regime")' in src)
check("그림자 R 도 entry_regime 전달", 'entry_reg=t.get("entry_regime")' in src)
check("positions push 에 entry_regime/tf 포함", '"entry_regime": p.get("entry_regime")' in src and '"tf": p.get("tf")' in src)
check("positions 복원에 entry_regime", 'entry_regime=p.get("entry_regime")' in src)
sc = open("scheduler.py", encoding="utf-8").read()
check("스케줄러: 온체인 조정이 라우팅 레짐에 대입되지 않음", "regime  = oc.adjust_regime" not in src + sc
      and "onchain_adjusted_regime = oc.adjust_regime" in sc and "regime = primary_regime" in sc)
rsrc = open("regime_switch.py", encoding="utf-8").read()
check("BTC.D fetch 실패 시 만료 캐시 우선", "_load_btcd_cache(allow_stale=True)" in rsrc)

# ── 4. 스키마 패치가 코드의 push 컬럼을 덮는가 ──────────────────────────────
sql = open("supabase_schema_patch_2026_09.sql", encoding="utf-8").read()
cols = {(t, c) for t, c in re.findall(r"alter table (\w+) add column if not exists (\w+)", sql)}
need_pos = {"entry_ts", "target", "live_mode", "tf", "regime", "entry_regime"}
need_tr = {"live_mode", "pnl_usd", "pnl_live_usd", "regime", "entry_regime"}
check("SQL: positions 컬럼 전부", need_pos <= {c for t, c in cols if t == "positions"})
check("SQL: trades 컬럼 전부", need_tr <= {c for t, c in cols if t == "trades"})
# push 코드가 미는 키와 대조
pos_keys = set(re.findall(r'"(\w+)": p\.get\("\w+"\)', src.split("def push_positions_db")[1].split("try:")[0]))
check("positions push 키 ⊆ 기존 스키마 ∪ 패치", pos_keys <= need_pos | {"stop_loss", "size_usd"}, pos_keys)

print(f"\n{len(fails)} failed")
sys.exit(1 if fails else 0)
