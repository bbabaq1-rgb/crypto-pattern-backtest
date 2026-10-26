"""
test_ai_judge.py — AI 판단 레이어(2026-10-23) 고정. 네트워크 없음(HTTP 는 바꿔 끼운다).

  1. 특성은 신호봉까지만 본다(인과) · 결정론 · JSON 직렬화 가능
  2. 파싱: 정상/코드펜스/잡문/깨진 JSON/범위 밖 값 — size_mult 상한 1.0, take→1.0, skip→0.0
  3. apply: shadow 는 항상 1.0 / veto 는 skip 0·reduce m·take 1 / 판단 없으면 1.0
  4. 키 없음 → 호출 자체를 안 하고 error=no_key, 예외 없음 · HTTP 오류·파싱 실패도 예외 없음
  5. 가짜 API 로 judge 끝까지 — 기록 행 필드
  6. 현행 모드 shadow · 체결엔진 통합 지점(소스 고정) · AI 는 신호를 못 만든다
  7. 배선: 워크플로 secret · SQL(테이블+GRANT) · tests.yml · registry 사전 등록
  8. (2026-10-26) 특성 v2 — 포트폴리오 맥락·상위 TF 는 닫힌 일봉만(인과)·손절 ATR 배수·prompt_version·토큰
  9. (2026-10-26) 청산 검토(그림자) — exit_features 인과·배치 파싱·한 번 호출·오류 경로·기록 키·주문 무관
 10. (2026-10-26) 통합 — run(slow=)·1-c 블록 위치·exit_spec/d_closed 제외·scheduler 플래그·code_action 세분화·보고 배선
"""
import json
import math
import random

import ai_judge as aj
import paper_executor as pe

fails = []


def check(n, c, d=""):
    print(("PASS " if c else "FAIL ") + n + ("" if c else f" — {d}"))
    c or fails.append(n)


def walk(n, seed, start=100.0):
    rnd = random.Random(seed)
    px, rows = start, []
    for i in range(n):
        o = px
        c = max(1.0, o * (1 + rnd.gauss(0, 0.02)))
        h = max(o, c) * (1 + abs(rnd.gauss(0, 0.01)))
        l = min(o, c) * (1 - abs(rnd.gauss(0, 0.01)))
        rows.append(dict(o=o, h=h, l=l, c=c, v=100 * (1 + abs(rnd.gauss(0, 0.8))),
                         date=f"2026-{1 + i // 28 % 12:02d}-{1 + i % 28:02d}", ts=1_700_000_000_000 + i * 3_600_000))
        px = c
    return rows


SIG = dict(symbol="SOL", pattern="engulfing", direction="long", tf="1d", date="2026-03-05",
           ensemble_grade="C", regime="bull_btc", stop=92.0)

# ── 1. 특성 ──────────────────────────────────────────────────────────────────
rows = walk(300, 1)
ei = 250
btc = walk(300, 2, 60000.0)
ctx = {"rows_of": lambda sym, tf: btc, "avg_cap": 0.12, "regime": "bull_btc",
       "trades": [dict(pattern="engulfing", method="D", ret=0.03), dict(pattern="engulfing", method="D", ret=-0.082),
                  dict(pattern="fvg", method="D", ret=0.5), dict(pattern="engulfing", method="A", ret=0.9)]}
f1 = aj.features(rows, ei, dict(SIG, stop=rows[ei]["c"] * 0.92), ctx)
rows_future = [dict(r) for r in rows]
for r in rows_future[ei + 1:]:
    r["c"] *= 3; r["h"] *= 3; r["v"] *= 7            # 미래 봉을 망가뜨려도 특성이 같아야 한다
f2 = aj.features(rows_future, ei, dict(SIG, stop=rows[ei]["c"] * 0.92), ctx)
check("특성은 신호봉 이후 봉을 안 본다(인과)", f1 == f2)
check("특성 결정론(같은 입력 → 같은 dict)", f1 == aj.features(rows, ei, dict(SIG, stop=rows[ei]["c"] * 0.92), ctx))
json.dumps(f1)
check("특성 JSON 직렬화 가능, NaN 없음",
      all(not (isinstance(v, float) and not math.isfinite(v)) for v in f1.values()))
check("같은 패턴·방식D 거래만 센다(fvg·방식A 제외)", f1["pattern_recent_n"] == 2 and abs(f1["pattern_recent_win"] - 0.5) < 1e-9)
check("BTC/ETH 동반 수익 포함", "btc_ret_20" in f1 and f1["btc_ret_20"] is not None)
check("손절 폭 8% 기록", abs(f1["stop_pct"] - 0.08) < 1e-6)
f_short = aj.features(rows, 10, dict(SIG, stop=None), {})
check("짧은 이력에서도 예외 없이 None 채움", f_short["ma200_dist"] is None and f_short["ret_60"] is None)
check("프롬프트 해시 16자·결정론", len(aj.prompt_hash(f1)) == 16 and aj.prompt_hash(f1) == aj.prompt_hash(f2))
check("프롬프트 해시는 특성이 바뀌면 바뀐다", aj.prompt_hash(f1) != aj.prompt_hash(f_short))

# ── 2. 파싱 ──────────────────────────────────────────────────────────────────
ok = aj.parse('{"decision":"reduce","size_mult":0.5,"confidence":0.7,"reasons":["a","b"]}')
check("정상 JSON 파싱", ok == {"decision": "reduce", "size_mult": 0.5, "confidence": 0.7, "reasons": ["a", "b"]})
check("코드펜스 안 JSON", aj.parse('```json\n{"decision":"skip","size_mult":0,"confidence":0.9,"reasons":[]}\n```')["decision"] == "skip")
check("앞뒤 잡문 허용", aj.parse('Sure. {"decision":"take","size_mult":1,"confidence":0.6,"reasons":["x"]} done')["decision"] == "take")
check("깨진 JSON → None", aj.parse('{"decision": "take", ') is None and aj.parse("") is None and aj.parse(None) is None)
check("모르는 decision → None", aj.parse('{"decision":"buy_more","size_mult":2}') is None)
check("size_mult 상한 1.0 — AI 는 키울 수 없다", aj.parse('{"decision":"reduce","size_mult":3.5,"confidence":0.5}')["size_mult"] == 1.0)
check("take 는 size_mult 1.0 고정", aj.parse('{"decision":"take","size_mult":0.3}')["size_mult"] == 1.0)
check("skip 은 size_mult 0.0 고정", aj.parse('{"decision":"skip","size_mult":0.8}')["size_mult"] == 0.0)
check("음수·NaN 클램프", aj.parse('{"decision":"reduce","size_mult":-1,"confidence":"x"}') == {"decision": "reduce", "size_mult": 0.0, "confidence": 0.5, "reasons": []})
check("reasons 3개·160자 절단", len(aj.parse('{"decision":"take","reasons":["1","2","3","4"]}')["reasons"]) == 3)

# ── 3. apply ─────────────────────────────────────────────────────────────────
rec_skip = {"decision": "skip", "size_mult": 0.0}
rec_red = {"decision": "reduce", "size_mult": 0.4}
rec_take = {"decision": "take", "size_mult": 1.0}
check("shadow: 어떤 판단이든 1.0", all(aj.apply(r, "shadow") == 1.0 for r in (rec_skip, rec_red, rec_take, None, {"error": "x"})))
check("veto: skip 0 / reduce 0.4 / take 1", aj.apply(rec_skip, "veto") == 0.0 and aj.apply(rec_red, "veto") == 0.4 and aj.apply(rec_take, "veto") == 1.0)
check("veto: 판단 없음(오류)은 1.0 — AI 장애가 거래를 막지 않는다", aj.apply({"decision": None, "error": "http_500"}, "veto") == 1.0 and aj.apply(None, "veto") == 1.0)
check("veto: 상한 1.0", aj.apply({"decision": "reduce", "size_mult": 5.0}, "veto") == 1.0)

# ── 4. 키 없음·오류 경로 ──────────────────────────────────────────────────────
import os
os.environ.pop("ANTHROPIC_API_KEY", None)
called = []
_orig_post = aj._post
aj._post = lambda body: called.append(body) or {"content": [{"type": "text", "text": '{"decision":"take"}'}]}
r0 = aj.judge(rows, ei, dict(SIG, stop=90.0), ctx)
check("키 없음 → error=no_key, 호출 안 함, 예외 없음", r0["error"] == "no_key" and r0["decision"] is None and not called)
check("키 없음에도 특성·해시는 기록", r0["prompt_hash"] and r0["features"])
os.environ["ANTHROPIC_API_KEY"] = "test-key"
import urllib.error
def _boom(body, timeout=None):
    raise urllib.error.HTTPError(aj.API_URL, 529, "overloaded", {}, None)
aj._post = _boom
r1 = aj.judge(rows, ei, dict(SIG, stop=90.0), ctx)
check("HTTP 오류 → error=http_529, 예외 없음", r1["error"] == "http_529" and r1["decision"] is None)
aj._post = lambda body: (_ for _ in ()).throw(TimeoutError("t"))
r2 = aj.judge(rows, ei, dict(SIG, stop=90.0), ctx)
check("타임아웃 → error=err_TimeoutError", r2["error"] == "err_TimeoutError")
aj._post = lambda body: {"content": [{"type": "text", "text": "I cannot decide."}]}
r3 = aj.judge(rows, ei, dict(SIG, stop=90.0), ctx)
check("파싱 실패 → error=parse_fail", r3["error"] == "parse_fail" and r3["decision"] is None)
r4 = aj.judge([], 0, dict(SIG), ctx)              # rows 비어 있음 → 특성 계산 예외
check("특성 계산 예외도 삼킨다(judge_*)", r4["error"].startswith("judge_"))
import io as _io
def _boom400(body, timeout=None):
    fp = _io.BytesIO(b'{"type":"error","error":{"type":"invalid_request_error","message":"temperature: non-default values are not supported"}}')
    raise urllib.error.HTTPError(aj.API_URL, 400, "bad request", {}, fp)
aj._post = _boom400
r4b = aj.judge(rows, ei, dict(SIG, stop=90.0), ctx)
check("HTTP 오류 본문의 type·message 를 error 에 남긴다(진단 가능)", r4b["error"].startswith("http_400:invalid_request_error:temperature"), r4b["error"])
aj._post = lambda body, timeout=None: {"content": [{"type": "thinking", "thinking": ""}], "stop_reason": "max_tokens", "usage": {"input_tokens": 9, "output_tokens": 4000}}
r4c = aj.judge(rows, ei, dict(SIG, stop=90.0), ctx)
check("텍스트 없는 응답은 stop_reason 으로 기록(empty_max_tokens)·토큰은 남긴다", r4c["error"] == "empty_max_tokens" and r4c["tokens_out"] == 4000)
aj._post = lambda body, timeout=None: {"content": [], "stop_reason": "refusal", "stop_details": {"type": "refusal", "category": "cyber"}}
check("안전 거절은 refusal:<category>", aj.judge(rows, ei, dict(SIG, stop=90.0), ctx)["error"] == "refusal:cyber")
check("요청 본문 어디에도 샘플링 파라미터가 없다(소스)", all(k not in open("ai_judge.py", encoding="utf-8").read() for k in ('"temperature"', '"top_p"', '"top_k"')))
check("모델은 claude-opus-5-5(2026-10-26 전환)·effort low", aj.MODEL == "claude-opus-5-5" and aj.EFFORT == "low")

# ── 5. 가짜 API 로 끝까지 ─────────────────────────────────────────────────────
seen = {}
def _fake(body):
    seen.update(body)
    return {"content": [{"type": "text", "text": '{"decision":"reduce","size_mult":0.5,"confidence":0.66,"reasons":["rsi hot","vol spike"]}'}]}
aj._post = _fake
r5 = aj.judge(rows, ei, dict(SIG, stop=90.0), ctx)
check("judge: 판단 필드", r5["decision"] == "reduce" and r5["size_mult"] == 0.5 and r5["confidence"] == 0.66
      and json.loads(r5["reasons"]) == ["rsi hot", "vol spike"] and r5["error"] is None)
check("judge: 키·모델·모드·ts 기록", r5["model"] == aj.MODEL and r5["mode"] == aj.MODE and r5["entry_ts"] == rows[ei]["ts"]
      and r5["symbol"] == "SOL" and r5["pattern"] == "engulfing")
check("호출: 샘플링 파라미터 미전송(temperature=0 이 실거래 http_400 원인)·effort low·시스템 프롬프트·모델",
      all(k not in seen for k in ("temperature", "top_p", "top_k", "thinking")) and seen.get("output_config") == {"effort": aj.EFFORT}
      and seen.get("system") == aj.SYSTEM and seen.get("model") == aj.MODEL and seen.get("max_tokens") >= 1024)
check("호출: 사용자 메시지는 특성 JSON 만", seen["messages"][0]["content"].endswith(r5["features"]))
check("시스템 프롬프트가 금지를 명시(신호 생성·크기 증가·손절 변경 불가)",
      "cannot create trades" in aj.SYSTEM and "raise size" in aj.SYSTEM and "change the stop" in aj.SYSTEM)
check("summary_line 집계", "reduce 1" in aj.summary_line([r5]) and "미판단/오류 1" in aj.summary_line([r5, r3]))
aj._post = _orig_post
os.environ.pop("ANTHROPIC_API_KEY", None)

# ── 6. 현행 모드·통합 지점 ────────────────────────────────────────────────────
check("현행 MODE 는 shadow (2026-10-23 사용자 결정 '그림자 기록 먼저')", aj.MODE == "shadow")
check("상한 1.0 — 어떤 경로로도 1.0 초과 배율이 안 나온다",
      all(aj.apply({"decision": d, "size_mult": m}, "veto") <= 1.0 for d in aj.DECISIONS for m in (-2, 0, 0.5, 1, 9)))
src = open("paper_executor.py", encoding="utf-8").read()
check("체결엔진: ai_judge import", "import ai_judge" in src)
i_dup = src.find("if _is_dup_entry(s, dup_ts, dup_dt, dup_all):")
i_judge = src.find("aj = ai_judge.judge(rows, ei, dict(s, stop=stop_px)")
i_size = src.find("bal_info  = ex_mod.get_balance(live_conn)")
i_order = src.find("result, reason = ex_mod.place_swap_entry(")
check("판단은 중복 방어 뒤·사이징 앞에서 한다", 0 < i_dup < i_judge < i_size < i_order)
check("판단은 신호 손절가(stop_px)를 넘겨 받는다 — 코드가 정한 손절", "dict(s, stop=stop_px)" in src)
check("키 없으면 호출 생략(빈 행 방지)", "ai_on = ai_judge.available()" in src and "if ai_on:" in src)
check("호출 상한 가드", "len(ai_records) < ai_judge.MAX_CALLS_PER_RUN" in src)
check("배율은 apply 로만 얻는다", "ai_mult = ai_judge.apply(aj)" in src)
check("veto 축소는 margin 에 곱하고 skip 은 주문을 안 낸다(페이퍼 행은 유지)",
      "live_size_usd = round(live_size_usd * ai_mult, 2)" in src and 'result, reason = None, f"ai_' in src)
check("포지션에 판단 요약 3필드", "ai_decision=(aj or {}).get(\"decision\")" in src and "ai_confidence=" in src)
check("code_action 기록(live / paper(+사유) / 스킵 지점별)", 'aj["code_action"] = "live" if live_info else (' in src
      and 'aj["code_action"] = "not_entered"' in src)
check("실행 끝에 DB 기록", "ai_judge.push_db(" in src)
# AI 레이어는 신호를 만들지 않는다 — 신호 집합·슬롯·중복·손절 코드에 손대지 않는다
asrc = open("ai_judge.py", encoding="utf-8").read()
check("ai_judge 는 주문·거래소·스케줄러를 import 하지 않는다",
      not any(f"import {m}" in asrc for m in ("exchange", "scheduler", "paper_executor", "detlib")))
check("ai_judge 는 signals 를 만들거나 바꾸지 않는다", "signals" not in asrc.replace("signal", "") and ".append(" not in asrc.split("def judge")[0].split("def features")[1])
check("MAX_LIVE_POS·STOP·EXIT_SPECS 불변(AI 와 무관)", pe.MAX_LIVE_POS == 13 and pe.STOP == 0.08 and "cascade_fade_long_1h" in pe.EXIT_SPECS)

# ── 7. 배선 ──────────────────────────────────────────────────────────────────
for wf in (".github/workflows/fast_scheduler.yml", ".github/workflows/daily_scheduler.yml"):
    check(f"{wf.split('/')[-1]} 에 ANTHROPIC_API_KEY secret", "ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}" in open(wf, encoding="utf-8").read())
check("tests.yml 에 test_ai_judge", "test_ai_judge.py" in open(".github/workflows/tests.yml", encoding="utf-8").read())
sql = open("supabase_schema_ai_judge.sql", encoding="utf-8").read()
check("SQL: 테이블 생성 + GRANT 같은 파일(perp_daily 교훈)", f"public.{aj.TABLE}" in sql and f"grant select, insert, update, delete on table public.{aj.TABLE} to service_role" in sql)
check("SQL: positions 판단 3컬럼", all(c in sql for c in ("ai_decision", "ai_size_mult", "ai_confidence")))
rec_keys = set(r5.keys()) | {"code_action"}
check("기록 행의 모든 키가 SQL 컬럼에 있다", all(k in sql for k in rec_keys), [k for k in rec_keys if k not in sql])
reg = json.load(open("registry.json", encoding="utf-8"))["ai_judge_prereg_2026_10_23"]
check("registry 사전 등록: status·평가 기준·승격 규칙·prior", reg["status"] == "SHADOW_RECORDING" and "primary" in reg["evaluation_prereg"]
      and "promotion" in reg["evaluation_prereg"] and "prior" in reg)
check("registry: mode_now 가 코드와 일치", aj.MODE in reg["mode_now"])
cl = open("CLAUDE.md", encoding="utf-8").read()
check("CLAUDE.md 원칙 개정 반영", "AI 판단 레이어" in cl and "매매 결정은 결정론적 코드만 — LLM은 코드 생성/수정만" not in cl)


# ── 8. 특성 v2 (2026-10-26) ──────────────────────────────────────────────────
book = [dict(symbol="SOL", direction="long", pattern="fvg", live_mode=True, d_closed=False),
        dict(symbol="ADA", direction="short", pattern="engulfing_short", live_mode=True, d_closed=False),
        dict(symbol="XRP", direction="long", pattern="engulfing", live_mode=True, d_closed=True),     # 유령 — 슬롯 안 먹음
        dict(symbol="DOT", direction="long", pattern="engulfing", live_mode=False, d_closed=False)]   # 페이퍼
fb = aj.features(rows, ei, dict(SIG, stop=rows[ei]["c"] * 0.92), dict(ctx, book=book, max_pos=13))
check("book: 행 4 · live 활성 2(유령·페이퍼 제외) · 상한 13 · 롱1/숏1", fb["book_rows"] == 4 and fb["book_live"] == 2 and fb["book_max"] == 13
      and fb["book_long"] == 1 and fb["book_short"] == 1)
check("book: 같은 종목 보유 · 같은 패턴 수", fb["book_symbol_held"] is True and fb["book_same_pattern"] == 0)
check("book 없으면 v1 키 집합 유지(하위 호환)", "book_live" not in f1 and "d1_ret_5" not in f1)
check("손절 ATR 배수 = stop_pct / atr14_pct", abs(fb["stop_atr"] - fb["stop_pct"] / fb["atr14_pct"]) < 1e-2 and fb["bar_hour_utc"] is not None)
check("같은 종목 최근 거래(방식D)만", aj.features(rows, ei, dict(SIG, stop=90.0), dict(ctx, trades=[
      dict(symbol="SOL", method="D", ret=0.02), dict(symbol="SOL", method="A", ret=0.5), dict(symbol="BTC", method="D", ret=0.1)]))["sym_recent_n"] == 1)
# 상위 TF: 4h 신호 + 1d 맥락 — 신호봉 마감 시점에 닫힌 일봉만
DAY = 86_400_000
d1 = walk(400, 5, 100.0)
for i, r in enumerate(d1):
    r["ts"] = 1_700_000_000_000 + i * DAY
h4 = walk(400, 6, 100.0)
for i, r in enumerate(h4):
    r["ts"] = d1[300]["ts"] + i * 14_400_000           # 300일째 00:00 부터 4h 봉
def rows_of_mixed(sym, tf):
    return d1 if tf == "1d" else btc
si = 2                                                  # 300일째 08:00 봉(마감 12:00) → 300일째 일봉은 아직 열려 있다
sig4 = dict(SIG, tf="4h", stop=h4[si]["c"] * 0.92)
f4 = aj.features(h4, si, sig4, {"rows_of": rows_of_mixed})
d1_mut = [dict(r) for r in d1]
d1_mut[300]["c"] *= 2; d1_mut[300]["h"] *= 2            # 같은 날(형성 중) 일봉을 망가뜨려도
f4b = aj.features(h4, si, sig4, {"rows_of": lambda s_, tf: d1_mut if tf == "1d" else btc})
check("상위 TF 맥락은 형성 중인 일봉을 안 본다(인과)", f4["d1_ret_5"] is not None and f4 == f4b)
d1_mut2 = [dict(r) for r in d1]
d1_mut2[299]["c"] *= 2
f4c = aj.features(h4, si, sig4, {"rows_of": lambda s_, tf: d1_mut2 if tf == "1d" else btc})
check("전날 닫힌 일봉은 본다", f4c["d1_ret_5"] != f4["d1_ret_5"])
si20 = 5                                                # 300일째 20:00 봉(마감 = 다음날 00:00) → 그날 일봉은 닫힘
f4d = aj.features(h4, si20, dict(SIG, tf="4h", stop=1.0), {"rows_of": rows_of_mixed})
f4e = aj.features(h4, si20, dict(SIG, tf="4h", stop=1.0), {"rows_of": lambda s_, tf: d1_mut if tf == "1d" else btc})
check("20:00 4h 봉 마감 시점엔 그날 일봉이 닫혀 있어 반영된다", f4d["d1_ret_5"] != f4e["d1_ret_5"])
check("1d 신호에는 d1_* 를 붙이지 않는다", "d1_ret_5" not in aj.features(rows, ei, dict(SIG, stop=90.0), {"rows_of": rows_of_mixed}))
check("_align_closed: ts+bar_ms <= close_ts 인 마지막 봉", aj._align_closed(d1, d1[10]["ts"] + DAY, DAY) == 10
      and aj._align_closed(d1, d1[10]["ts"] + DAY - 1, DAY) == 9 and aj._align_closed([], 1, DAY) is None)
os.environ["ANTHROPIC_API_KEY"] = "test-key"
aj._post = lambda body, timeout=None: {"content": [{"type": "text", "text": '{"decision":"take","confidence":0.8}'}],
                                       "usage": {"input_tokens": 1234, "output_tokens": 31}}
r8 = aj.judge(rows, ei, dict(SIG, stop=90.0), ctx)
check("judge: kind=entry · prompt_version · 토큰 · 신호봉 종가 기록", r8["kind"] == "entry" and r8["prompt_version"] == aj.PROMPT_VERSION
      and r8["tokens_in"] == 1234 and r8["tokens_out"] == 31 and r8["entry_px"] == rows[ei]["c"])
check("PROMPT_VERSION 은 v2(2026-10-26) 표기", aj.PROMPT_VERSION.startswith("entry_v2") and aj.EXIT_PROMPT_VERSION.startswith("exit_v1"))
check("시스템 프롬프트 v2 가 새 필드(d1_/book_/stop_atr)를 설명한다", all(k in aj.SYSTEM for k in ("d1_", "book_", "stop_atr")))
aj._post = _orig_post
os.environ.pop("ANTHROPIC_API_KEY", None)

# ── 9. 청산 검토(그림자) ─────────────────────────────────────────────────────
POS = dict(symbol="SOL", pattern="fvg", direction="long", tf="1d", entry_date=rows[200]["date"], entry_ts=rows[200]["ts"],
           entry_price=rows[200]["c"], stop=rows[200]["c"] * 0.92, entry_regime="bull_btc", live_mode=True)
mi = 210
xctx = {"rows_of": lambda s_, tf: btc, "trades": ctx["trades"], "regmap": {rows[mi]["date"]: "bear"}, "max_hold": 30}
xf = aj.exit_features(rows, 200, mi, POS, xctx)
rows_mut = [dict(r) for r in rows]
for r in rows_mut[mi + 1:]:
    r["c"] *= 3; r["l"] *= 0.1
check("exit_features 는 마크봉 이후를 안 본다(인과)·결정론", xf == aj.exit_features(rows_mut, 200, mi, POS, xctx) == aj.exit_features(rows, 200, mi, POS, xctx))
check("보유 10봉 · 남은 20봉 · 미실현 = 종가/진입−1", xf["bars_held"] == 10 and xf["bars_left"] == 20
      and abs(xf["unreal_ret"] - (rows[mi]["c"] / POS["entry_price"] - 1)) < 1e-6)
check("mfe ≥ 미실현 ≥ mae (롱)", xf["mfe"] >= xf["unreal_ret"] - 1e-9 >= xf["mae"] - 1e-9)
check("손절 거리 = (마크−손절)/마크 · 레짐 전환 플래그", abs(xf["stop_dist"] - (rows[mi]["c"] - POS["stop"]) / rows[mi]["c"]) < 1e-4
      and xf["regime_now"] == "bear" and xf["regime_changed"] is True)
xs = aj.exit_features(rows, 200, mi, dict(POS, direction="short"), xctx)
check("숏은 부호 반전(미실현·손절 거리)", abs(xs["unreal_ret"] + xf["unreal_ret"]) < 1e-9 and xs["mfe"] >= xs["unreal_ret"] - 1e-9)
check("exit 특성 JSON 직렬화·BTC 동반·패턴 최근 성과(fvg 방식D 1건)", json.dumps(xf) and "btc_ret_5" in xf and xf["pattern_recent_n"] == 1)
pb = aj.parse_batch('```json\n{"reviews":[{"id":"p1","decision":"EXIT","confidence":1.7,"reasons":["a","b","c"]},'
                    '{"id":"p2","decision":"hold"},{"id":"p2","decision":"exit"},{"id":"p9","decision":"hold"},{"id":"p3","decision":"buy"}]}\n```', ["p1", "p2", "p3"])
check("parse_batch: 대소문자·클램프·근거 2개·중복 id 첫 것·모르는 id/decision 무시",
      pb == {"p1": {"decision": "exit", "confidence": 1.0, "reasons": ["a", "b"]}, "p2": {"decision": "hold", "confidence": 0.5, "reasons": []}}, pb)
check("parse_batch: 다른 키로 싼 리스트도 허용 · 깨진 입력 {}", aj.parse_batch('{"result":[{"id":"p1","decision":"hold"}]}', ["p1"])["p1"]["decision"] == "hold"
      and aj.parse_batch("nope", ["p1"]) == {} and aj.parse_batch('{"reviews": "x"}', ["p1"]) == {} and aj.parse_batch(None, ["p1"]) == {})
items = [{"pos": POS, "rows": rows, "ei": 200, "mi": mi},
         {"pos": dict(POS, symbol="ADA", direction="short", pattern="engulfing_short", live_mode=False), "rows": rows, "ei": 205, "mi": mi},
         {"pos": dict(POS, symbol="BAD"), "rows": [], "ei": 0, "mi": 0}]                       # 특성 계산 실패 행
os.environ["ANTHROPIC_API_KEY"] = "test-key"
calls = []
def _fake_batch(body, timeout=None):
    calls.append(body)
    return {"content": [{"type": "text", "text": '{"reviews":[{"id":"p1","decision":"exit","confidence":0.8,"reasons":["near stop"]},'
                                                 '{"id":"p2","decision":"hold","confidence":0.6}]}'}],
            "usage": {"input_tokens": 2000, "output_tokens": 80}}
aj._post = _fake_batch
xr = aj.judge_exits(items, xctx)
check("judge_exits: 한 번 호출로 포지션별 행", len(calls) == 1 and len(xr) == 3)
check("judge_exits: 판정·확신·근거·배치 해시 공유·토큰", xr[0]["decision"] == "exit" and xr[1]["decision"] == "hold" and xr[0]["confidence"] == 0.8
      and json.loads(xr[0]["reasons"]) == ["near stop"] and xr[0]["prompt_hash"] == xr[1]["prompt_hash"] and len(xr[0]["prompt_hash"]) == 16
      and xr[0]["tokens_in"] == 2000)
check("judge_exits: 기록 필드(kind/exit·mark·unreal·bars·live·code_action=open·size_mult 없음·EXIT_PROMPT_VERSION)",
      xr[0]["kind"] == "exit" and xr[0]["mark_px"] == rows[mi]["c"] and xr[0]["mark_ts"] == rows[mi]["ts"] and xr[0]["bars_held"] == 10
      and abs(xr[0]["unreal_ret"] - xf["unreal_ret"]) < 1e-9 and xr[0]["live_mode"] is True and xr[1]["live_mode"] is False
      and xr[0]["code_action"] == "open" and xr[0]["size_mult"] is None and xr[0]["prompt_version"] == aj.EXIT_PROMPT_VERSION
      and xr[0]["entry_px"] == POS["entry_price"] and xr[0]["entry_ts"] == POS["entry_ts"])
check("judge_exits: 깨진 항목은 judge_* 오류로 격리되고 나머지는 정상", xr[2]["error"].startswith("judge_") and xr[2]["decision"] is None and xr[0]["error"] is None)
check("호출: 배치 시스템 프롬프트·샘플링 미전송·사용자 메시지에 두 id", calls[0]["system"] == aj.SYSTEM_EXIT and "temperature" not in calls[0]
      and '"id": "p1"' in calls[0]["messages"][0]["content"] and '"id": "p2"' in calls[0]["messages"][0]["content"] and '"p3"' not in calls[0]["messages"][0]["content"])
check("배치 시스템 프롬프트가 '주문 없음·손절 불변' 을 명시", "places no orders" in aj.SYSTEM_EXIT and "cannot move the stop" in aj.SYSTEM_EXIT)
aj._post = lambda body, timeout=None: {"content": [{"type": "text", "text": '{"reviews":[{"id":"p1","decision":"hold"}]}'}]}
xr2 = aj.judge_exits(items[:2], xctx)
check("일부만 답하면 빠진 id 는 error=no_answer", xr2[0]["decision"] == "hold" and xr2[1]["error"] == "no_answer")
aj._post = lambda body, timeout=None: {"content": [{"type": "text", "text": "cannot"}]}
check("배치 파싱 실패 → 전 행 parse_fail", all(r["error"] == "parse_fail" for r in aj.judge_exits(items[:2], xctx)))
aj._post = _boom
check("배치 HTTP 오류 → 전 행 http_529, 예외 없음", all(r["error"] == "http_529" for r in aj.judge_exits(items[:2], xctx)))
_mx = aj.MAX_EXIT_POS
aj.MAX_EXIT_POS = 1
aj._post = _fake_batch
calls.clear()
xr3 = aj.judge_exits(items[:2], xctx)
check("MAX_EXIT_POS 초과 행은 max_pos 로 미판단(특성은 기록)", xr3[1]["error"] == "max_pos" and xr3[1]["features"] and xr3[0]["decision"] == "exit"
      and '"p2"' not in calls[0]["messages"][0]["content"])
aj.MAX_EXIT_POS = _mx
os.environ.pop("ANTHROPIC_API_KEY", None)
xr4 = aj.judge_exits(items[:2], xctx)
check("키 없음 → no_key, 호출 없음", all(r["error"] == "no_key" for r in xr4))
check("judge_exits 는 쓰레기 입력에도 예외를 안 낸다", aj.judge_exits([{"pos": {}, "rows": None, "ei": 0, "mi": 0}], None)[0]["error"].startswith("judge_")
      and aj.judge_exits([], None) == [])
check("exit_summary_line 집계·'기록만' 표기", "exit 1" in aj.exit_summary_line(xr) and "hold 1" in aj.exit_summary_line(xr) and "주문 무변경" in aj.exit_summary_line(xr)
      and "미판단/오류 1" in aj.exit_summary_line(xr))
check("summary_line 은 entry 행만 센다", aj.summary_line(xr) == "[ai] 판단 0건")
check("exit 기록 행의 모든 키가 SQL 컬럼에 있다", all(k in sql for k in xr[0].keys()), [k for k in xr[0].keys() if k not in sql])
check("entry 기록 행의 새 키(kind/prompt_version/tokens/entry_px)도 SQL 에 있다", all(k in sql for k in r8.keys()), [k for k in r8.keys() if k not in sql])
check("SQL: 기존 설치 보강용 alter 가 새 컬럼 전부", all(f"add column if not exists {c}" in sql for c in
      ("kind", "prompt_version", "entry_px", "mark_ts", "mark_px", "unreal_ret", "bars_held", "live_mode", "tokens_in", "tokens_out")))
aj._post = _orig_post

# ── 10. 통합 (2026-10-26) ─────────────────────────────────────────────────────
src = open("paper_executor.py", encoding="utf-8").read()
check("run(stamp=None, slow=None) — 느린 틱 플래그를 받는다", "def run(stamp=None, slow=None):" in src)
i_shadow_r = src.find("r_added = shadow_r_records(trades, rows_of, regmap)")
i_exit = src.find("ai_judge.judge_exits(")
i_sig = src.find('sig = _load("signals_today.json"')
check("1-c 청산 검토는 shadow-R 뒤·신규 진입 앞", 0 < i_shadow_r < i_exit < i_sig)
check("청산 검토 대상: exit_spec 패턴·d_closed·진입봉 미특정 제외",
      'if pos.get("d_closed") or EXIT_SPECS.get(pos["pattern"]) or pos.get("entry_idx") is None:' in src)
check("느린 틱에서만(ai_on and slow) · 폴백 시각 = scheduler.SLOW_TICK_HOURS", "if ai_on and slow:" in src
      and "slow = datetime.now(timezone.utc).hour in AI_EXIT_REVIEW_HOURS" in src)
import scheduler as sch
check("AI_EXIT_REVIEW_HOURS == scheduler.SLOW_TICK_HOURS", pe.AI_EXIT_REVIEW_HOURS == sch.SLOW_TICK_HOURS)
check("scheduler 가 느린 틱 플래그를 넘긴다", "paper_executor.run(stamp, slow=slow_tick)" in open("scheduler.py", encoding="utf-8").read())
check("청산 검토 결과는 기록(ai_records)에만 들어간다 — 주문·청산 코드가 ex_recs 를 읽지 않는다",
      src.count("ex_recs") == 3 and "ai_records.extend(ex_recs)" in src and "exit_summary_line(ex_recs)" in src)
check("청산 검토 블록 안에 주문·청산 호출이 없다",
      all(w not in src[i_exit - 1500:i_exit + 400] for w in ("close_swap_position", "place_swap_entry", "ensure_stop_orders", "_record_trade(")))
check("진입 판단 ctx 에 포트폴리오 맥락(book·max_pos)", '"book": still_open, "max_pos": MAX_LIVE_POS' in src)
check("code_action 세분화: 스킵 지점마다 사유", all(f'_ai_action(aj, "{a}")' in src for a in
      ("slot_full", "dup_live", "cap_full", "cap_pot_empty", "size_skip", "order_fail", "kill_switch")))
pe._ai_action(None, "x")
_a = {"code_action": "not_entered"}
pe._ai_action(_a, "slot_full")
check("_ai_action: 판단 없으면 무시 · 있으면 기록", _a["code_action"] == "slot_full")
check("최대 포지션·중복 방어 판정 줄은 종전 그대로(test_executor_safety 가 보는 문자열)",
      "elif live_open_count >= MAX_LIVE_POS:" in src and 'if entry_blocked(s["symbol"], s["direction"], bool(cap), okx_dir_keys, main_keys, cap_keys):' in src)
check("실행 끝 DB 기록은 진입·청산 행을 한 번에", "ai_judge.push_db(" in src and src.count("ai_judge.push_db(") == 1)
check("tests.yml 에 test_ai_judge_report", "test_ai_judge_report.py" in open(".github/workflows/tests.yml", encoding="utf-8").read())
check("보고 워크플로 존재", os.path.exists(".github/workflows/ai_judge_report.yml"))
regx = json.load(open("registry.json", encoding="utf-8"))["ai_exit_prereg_2026_10_26"]
check("registry 청산 검토 사전 등록: status·primary·실효 조건(원칙 개정·사용자 결정)", regx["status"] == "SHADOW_RECORDING"
      and "primary" in regx["evaluation_prereg"] and "promotion" in regx["evaluation_prereg"] and "사용자 결정" in regx["evaluation_prereg"]["promotion"])
check("registry 진입 사전 등록에 prompt_version 이력", "prompt_versions" in reg and aj.PROMPT_VERSION in json.dumps(reg["prompt_versions"], ensure_ascii=False))
check("CLAUDE.md 에 청산 검토·보고 반영", "청산 검토" in cl and "ai_judge_report" in cl)


# ── 11. DB 기록 — 확장 컬럼 10개가 아직 없는 DB (2026-10-26 04:00Z 실측 결함) ───────────────
import supabase_client as sc
MISSING = ["kind", "prompt_version", "entry_px", "mark_ts", "mark_px", "unreal_ret", "bars_held", "live_mode", "tokens_in", "tokens_out"]
class _FakeQ:
    def __init__(self, store, rows): self.store, self.rows = store, rows
    def execute(self):
        for col in MISSING:                       # PostgREST 는 모르는 컬럼을 한 번에 하나씩만 알려준다
            if any(col in r for r in self.rows):
                raise Exception(f"{{'message': \"Could not find the '{col}' column of 'ai_judgments' in the schema cache\", 'code': 'PGRST204'}}")
        self.store.extend(self.rows)
        class _R: pass
        r = _R(); r.data = list(self.rows); return r
class _FakeT:
    def __init__(self, store): self.store = store
    def insert(self, rows): return _FakeQ(self.store, rows)
class _FakeCli:
    def __init__(self): self.store = []
    def table(self, name): return _FakeT(self.store)
_store_cli = _FakeCli()
try:
    sc.insert_tolerant(_store_cli, "ai_judgments", [dict(r5), xr[0]])
    _default_ok = True
except RuntimeError:
    _default_ok = False
check("insert_tolerant 기본 한도(8)로는 확장 컬럼 10개 미존재 DB 에서 유실된다(실측 재현)", not _default_ok and _store_cli.store == [])
_store_cli = _FakeCli()
ins, drp = sc.insert_tolerant(_store_cli, "ai_judgments", [dict(r5), xr[0]], max_drop=32)
check("max_drop=32 면 10개를 제외하고 기록된다", len(ins) == 2 and set(drp) == set(MISSING) and len(_store_cli.store) == 2
      and all(c not in _store_cli.store[0] for c in MISSING) and _store_cli.store[0]["decision"] == "reduce")
_orig_av, _orig_gc = sc.available, sc.get_client
_store_cli = _FakeCli()
sc.available = lambda: True
sc.get_client = lambda role="service": _store_cli
n_pushed = aj.push_db([dict(r5), xr[0], xr[1]])
sc.available, sc.get_client = _orig_av, _orig_gc
check("push_db: SQL 재실행 전 DB 에서도 entry·exit 행이 전부 기록된다(키 집합 통일 포함)", n_pushed == 3 and len(_store_cli.store) == 3
      and len({tuple(sorted(r.keys())) for r in _store_cli.store}) == 1)
check("push_db 는 max_drop=32 를 넘긴다(소스)", "insert_tolerant(cli, TABLE, rows, max_drop=32)" in open("ai_judge.py", encoding="utf-8").read())

print(f"\n{len(fails)} failed")
raise SystemExit(1 if fails else 0)
