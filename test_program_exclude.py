"""
test_program_exclude.py — BTC 프로그램 매매 제외(2026-11-01 사용자 결정) 고정. 네트워크·API·거래소 없음.

사용자 지시 "btc는 앞으로 ai매매에만 활용하고 프로그램 매매에서는 대상에서 제외처리해". 계기: 메인 전략의 BTC 롱
(vol_awakening_4h, 10-30 진입)이 열려 있는 동안 OKX net 모드 가드 때문에 AI 엘리엇 BTC 숏이 막혔다(대기 189회 중 188회).
여기서 고정하는 것:

  1. 설정 — universe.json program_exclude = ["BTC"], AI 엘리엇 BTC 스위치(ai_traders)는 그대로
  2. 판정 함수 — 대소문자·공백 정규화, 키 없음·파일 없음·읽기 실패는 빈 집합(= 종전 동작), AI 트레이더 패턴은 항상 제외 아님
  3. scheduler.drop_program_excluded — 제외 종목 신호만 빠지고 나머지 신호·순서는 그대로, 목록이 비면 입력 그대로
  4. 배선(소스 순서) — scheduler: 마지막 탐지 블록 뒤·앙상블/저장 앞 / paper_executor: 진입 루프 맨 앞
     (봉 조회·중복 방어·AI 판단·사이징보다 앞 → 페이퍼 행도 안 만든다)
  5. 오프라인 e2e — 같은 실행에 BTC·ETH 프로그램 신호가 오면 ETH 만 진입, 목록을 비우면 둘 다 진입(종전 동작)
  6. 열린 포지션 관리 불변 — 제외 판정은 진입 루프 한 곳에만 있고 청산·손절 점검·정합성 보정 경로에는 없다
  7. 코호트 순위 불변 — 제외는 탐지 결과에서만 빠진다(_volume_ranked·_cohort_symbols 는 손대지 않음)

실행: python test_program_exclude.py
"""
import csv
import io
import json
import os
import random
import shutil
import sys
import tempfile

import ai_elliott as ae
import paper_executor as pe
import scheduler as sch

fails = []


def check(n, c, d=""):
    print(("PASS " if c else "FAIL ") + n + ("" if c else f" — {d}"))
    c or fails.append(n)


SRC_PE = io.open("paper_executor.py", encoding="utf-8").read()
SRC_SCH = io.open("scheduler.py", encoding="utf-8").read()
UNI = json.load(io.open("universe.json", encoding="utf-8"))

# ── 1. 설정 ─────────────────────────────────────────────────────────────────
check("universe.json program_exclude = ['BTC']", UNI.get("program_exclude") == ["BTC"], UNI.get("program_exclude"))
check("결정 기록(program_exclude_note)에 사용자 지시 원문", "btc는 앞으로 ai매매에만 활용하고"
      in (UNI.get("program_exclude_note") or ""))
_ai = [t for t in UNI.get("ai_traders") or [] if t.get("pattern") == ae.PATTERN]
check("AI 엘리엇 BTC 스위치는 그대로 켜져 있다(제외 대상은 프로그램 매매뿐)",
      len(_ai) == 1 and _ai[0].get("symbol") == "BTC" and ae.SYMBOL == "BTC", _ai)
check("실제 설정으로: 프로그램 패턴 BTC = 제외, AI 엘리엇 BTC = 제외 아님, 다른 종목 = 제외 아님",
      pe.program_excluded("BTC", "vol_awakening_4h") and pe.program_excluded("BTC", "engulfing")
      and not pe.program_excluded("BTC", ae.PATTERN) and not pe.program_excluded("ETH", "vol_awakening_4h"))


# ── 2. 판정 함수 ─────────────────────────────────────────────────────────────
def _with_file(content):
    d = tempfile.mkdtemp()
    p = os.path.join(d, "universe.json")
    if content is not None:
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
    return d, p


for label, content, want in (
        ("파일 없음 → 빈 집합(종전 동작)", None, set()),
        ("키 없음 → 빈 집합(종전 동작)", json.dumps({"trading_universe": ["BTC"]}), set()),
        ("빈 목록 → 빈 집합", json.dumps({"program_exclude": []}), set()),
        ("null → 빈 집합", json.dumps({"program_exclude": None}), set()),
        ("대소문자·공백 정규화, 빈 문자열 무시", json.dumps({"program_exclude": ["btc", " Eth ", "", "  "]}), {"BTC", "ETH"}),
        ("읽기 실패(깨진 JSON) → 빈 집합 — 같은 실행의 trading_halt_state 가 fail-closed 로 진입을 막는다",
         "{not json", set())):
    d, p = _with_file(content)
    try:
        got = pe.program_exclude_set(p)
        check(f"program_exclude_set: {label}", got == want, got)
    finally:
        shutil.rmtree(d, ignore_errors=True)

d, p = _with_file("{not json")
try:
    check("깨진 universe.json 이면 trading_halt_state 가 fail-closed(신규 실거래 진입 보류)",
          pe.trading_halt_state(p)[0] is True, pe.trading_halt_state(p))
finally:
    shutil.rmtree(d, ignore_errors=True)

d, p = _with_file(json.dumps({"program_exclude": ["BTC"], "ai_traders": []}))
try:
    check("ai_traders 가 비어도 AI 엘리엇 패턴은 AI 트레이더로 본다(스위치를 꺼도 프로그램 매매가 아니다)",
          ae.PATTERN in pe.ai_trader_patterns(p) and not pe.program_excluded("BTC", ae.PATTERN, path=p))
    check("ai_traders 비어도 프로그램 패턴 BTC 는 제외", pe.program_excluded("btc", "fvg", path=p))
finally:
    shutil.rmtree(d, ignore_errors=True)

d, p = _with_file(json.dumps({"program_exclude": ["BTC"], "ai_traders": [{"pattern": "ai_other_btc", "symbol": "BTC"}]}))
try:
    check("ai_traders 에 적힌 다른 AI 패턴도 제외 아님", not pe.program_excluded("BTC", "ai_other_btc", path=p)
          and "ai_other_btc" in pe.ai_trader_patterns(p))
finally:
    shutil.rmtree(d, ignore_errors=True)

EX, AIP = {"BTC"}, {ae.PATTERN}
check("명시 인자: 빈 집합이면 아무것도 제외 안 함(종전 동작)", not pe.program_excluded("BTC", "engulfing", set(), AIP))
check("명시 인자: 소문자·공백 심볼도 제외", pe.program_excluded(" btc ", "engulfing", EX, AIP))
check("명시 인자: 다른 종목은 제외 아님", not pe.program_excluded("SOL", "engulfing", EX, AIP))

# ── 3. scheduler.drop_program_excluded ──────────────────────────────────────
SIGS = [dict(symbol="ETH", pattern="vol_awakening_4h", direction="long"),
        dict(symbol="BTC", pattern="vol_awakening_4h", direction="long"),
        dict(symbol="SOL", pattern="engulfing", direction="long"),
        dict(symbol="BTC", pattern="cascade_fade_long_1h", direction="long"),
        dict(symbol="BTC", pattern=ae.PATTERN, direction="short"),
        dict(symbol="XRP", pattern="fvg", direction="long")]
_buf = io.StringIO()
_old = sys.stdout
sys.stdout = _buf
try:
    kept = sch.drop_program_excluded(list(SIGS), excluded=EX, ai_patterns=AIP)
finally:
    sys.stdout = _old
check("BTC 프로그램 신호 2건만 빠지고 나머지는 순서 그대로",
      [(s["symbol"], s["pattern"]) for s in kept]
      == [("ETH", "vol_awakening_4h"), ("SOL", "engulfing"), ("BTC", ae.PATTERN), ("XRP", "fvg")], kept)
check("뺀 신호마다 로그 한 줄", _buf.getvalue().count("[프로그램 제외]") == 2, _buf.getvalue())
check("목록이 비면 입력을 그대로 돌려준다(종전 동작 — 같은 객체)",
      sch.drop_program_excluded(SIGS, excluded=set(), ai_patterns=AIP) is SIGS)
check("기본 인자(실제 universe.json)로도 BTC 프로그램 신호를 뺀다",
      [s["symbol"] for s in sch.drop_program_excluded([dict(symbol="BTC", pattern="fvg", direction="long"),
                                                       dict(symbol="ADA", pattern="fvg", direction="long")])] == ["ADA"])

# ── 4. 배선(소스 순서) ──────────────────────────────────────────────────────
_main = SRC_SCH.split("def run_once(", 1)[1].split("\ndef ", 1)[0]       # 스케줄러 1회 실행 본문
i_drop = _main.find("signals = drop_program_excluded(signals)")
i_harm = _main.find("for pat, modname in HARMONIC_FOCUS")
i_1h = _main.find("adopted_1h_patterns")
i_rs = _main.find("signals = _attach_rs(signals)")
i_dump = _main.find('json.dump(out, open("signals_today.json"')
check("scheduler: 제외는 모든 탐지 블록(1h adopted·하모닉) 뒤", i_drop > i_harm > 0 and i_drop > i_1h > 0,
      (i_drop, i_harm, i_1h))
check("scheduler: 제외는 RS·앙상블과 signals_today.json 저장 앞", 0 < i_drop < i_rs < i_dump, (i_drop, i_rs, i_dump))
check("scheduler: 제외 호출은 run_once 안 한 곳(정의 1 + 호출 1)", _main.count("drop_program_excluded(") == 1
      and SRC_SCH.count("drop_program_excluded(") == 2, SRC_SCH.count("drop_program_excluded("))

_run = SRC_PE.split("def run(", 1)[1]
i_loop = _run.find('for s in sig.get("signals", []):')
_loop = _run[i_loop:]
i_guard = _loop.find("if program_excluded(")
check("paper_executor: 제외 집합은 진입 루프 직전에 실행당 1회 읽는다",
      0 < _run.find("prog_ex, ai_pats = program_exclude_set(), ai_trader_patterns()") < i_loop)
_order = [_loop.find(k) for k in ("rows = rows_of(", "_is_dup_entry(", "ai_judge.judge(", "size_for_pos")]
check("paper_executor: 판정이 진입 루프 맨 앞 — 봉 조회·중복 방어·AI 판단·사이징보다 앞",
      0 < i_guard and all(i_guard < k for k in _order) and _order == sorted(_order) and -1 not in _order,
      (i_guard, _order))
check("paper_executor: 판정 뒤 continue(주문·페이퍼 행 없음)",
      "continue" in _loop[i_guard:_loop.find("rows = rows_of(")])

# ── 6. 열린 포지션 관리 불변 ────────────────────────────────────────────────
check("판정 호출은 진입 루프 한 곳뿐(정의 1 + 호출 1) — 청산·손절 점검·정합성 보정 경로에는 없다",
      SRC_PE.count("program_excluded(") == 2 and _run.count("program_excluded(") == 1, SRC_PE.count("program_excluded("))
for fn in ("def reconcile_closed_positions", "def ensure_stop_orders", "def settle_by_algo", "def ai_close",
           "def engine_live_close"):
    if fn in SRC_PE:
        body = SRC_PE.split(fn, 1)[1].split("\ndef ", 1)[0]
        check(f"{fn[4:]} 는 제외 목록을 보지 않는다", "program_exclude" not in body)

# ── 7. 코호트 순위 불변 ─────────────────────────────────────────────────────
for fn in ("def _volume_ranked", "def _cohort_symbols", "def _syms_for_pattern"):
    body = SRC_SCH.split(fn, 1)[1].split("\ndef ", 1)[0]
    check(f"scheduler {fn[4:]} 는 제외 목록을 보지 않는다(순위·코호트 정의 불변)", "program_exclude" not in body)


# ── 5. 오프라인 e2e — 체결 엔진 진입 루프 ────────────────────────────────────
def mkrows(n, seed, scale, step=86400000, start_ts=1_600_000_000_000):
    from datetime import datetime, timezone
    random.seed(seed)
    px, ts, rows = 100.0 * scale, start_ts, []
    for _ in range(n):
        nxt = px * (1 + random.gauss(0, 0.004))
        d = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        rows.append(dict(ts=ts, date=d, o=px, h=max(px, nxt) * 1.002, l=min(px, nxt) * 0.998, c=nxt, v=100.0))
        px, ts = nxt, ts + step
    return rows


def _e2e(exclude):
    import detlib
    import regime_switch as rs
    repo, tmp = os.getcwd(), tempfile.mkdtemp()
    env_keep = {k: os.environ.pop(k) for k in ("OKX_KEY", "OKX_SECRET", "OKX_PASSPHRASE", "SUPABASE_URL",
                                               "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_KEY", "ANTHROPIC_API_KEY")
                if k in os.environ}
    keep = dict(rg=rs.build_regime_map, af=detlib._auto_fetch)

    def no_fetch(sym, tf):
        raise FileNotFoundError(f"{sym} {tf}")

    try:
        shutil.copy("registry.json", os.path.join(tmp, "registry.json"))
        u = json.load(io.open("universe.json", encoding="utf-8"))
        if exclude is None:
            u.pop("program_exclude", None)
        else:
            u["program_exclude"] = exclude
        os.chdir(tmp)
        os.makedirs("data", exist_ok=True)
        json.dump(u, open("universe.json", "w", encoding="utf-8"), ensure_ascii=False)
        rr = {}
        for sym, seed, scale in (("BTC", 11, 800.0), ("ETH", 22, 27.0)):
            rr[sym] = mkrows(120, seed, scale)
            with open(f"data/{sym.lower()}_1d.csv", "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["timestamp", "open", "high", "low", "close", "volume"])
                for x in rr[sym]:
                    w.writerow([x["ts"], x["o"], x["h"], x["l"], x["c"], x["v"]])
        si = 110
        rs.build_regime_map = lambda *a, **k: {r["date"]: "bull_btc" for r in rr["BTC"]}
        detlib._auto_fetch = no_fetch
        json.dump({"signals": [dict(symbol=s, pattern="engulfing", direction="long", tf="1d",
                                    date=rr[s][si]["date"], ts=rr[s][si]["ts"], regime="bull_btc")
                               for s in ("BTC", "ETH")]}, open("signals_today.json", "w"))
        buf, old = io.StringIO(), sys.stdout
        sys.stdout = buf
        try:
            pe.run()
        finally:
            sys.stdout = old
        return json.load(open("paper_positions.json")), buf.getvalue()
    finally:
        rs.build_regime_map, detlib._auto_fetch = keep["rg"], keep["af"]
        os.environ.update(env_keep)
        os.chdir(repo)
        shutil.rmtree(tmp, ignore_errors=True)


pos, log = _e2e(["BTC"])
check("e2e: BTC·ETH engulfing 신호 중 ETH 만 진입(페이퍼)",
      sorted(p["symbol"] for p in pos) == ["ETH"] and all(p["pattern"] == "engulfing" for p in pos), pos)
check("e2e: BTC 는 '프로그램 매매 제외 종목' 사유로 스킵 로그", "BTC engulfing long — 프로그램 매매 제외 종목" in log,
      log[-600:])
check("e2e: 실행 시작에 제외 목록 한 줄", "[프로그램 제외] ['BTC']" in log)
pos0, log0 = _e2e(None)
check("e2e: program_exclude 키가 없으면 둘 다 진입(종전 동작)", sorted(p["symbol"] for p in pos0) == ["BTC", "ETH"], pos0)
check("e2e: 키가 없으면 제외 로그도 없다", "[프로그램 제외]" not in log0 and "프로그램 매매 제외 종목" not in log0)

print(f"\n{len(fails)} failed")
sys.exit(1 if fails else 0)
