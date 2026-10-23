"""
test_ai_judge.py — AI 판단 레이어(2026-10-23) 고정. 네트워크 없음(HTTP 는 바꿔 끼운다).

  1. 특성은 신호봉까지만 본다(인과) · 결정론 · JSON 직렬화 가능
  2. 파싱: 정상/코드펜스/잡문/깨진 JSON/범위 밖 값 — size_mult 상한 1.0, take→1.0, skip→0.0
  3. apply: shadow 는 항상 1.0 / veto 는 skip 0·reduce m·take 1 / 판단 없으면 1.0
  4. 키 없음 → 호출 자체를 안 하고 error=no_key, 예외 없음 · HTTP 오류·파싱 실패도 예외 없음
  5. 가짜 API 로 judge 끝까지 — 기록 행 필드
  6. 현행 모드 shadow · 체결엔진 통합 지점(소스 고정) · AI 는 신호를 못 만든다
  7. 배선: 워크플로 secret · SQL(테이블+GRANT) · tests.yml · registry 사전 등록
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
def _boom(body):
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
check("호출: 온도 0·시스템 프롬프트·모델", seen.get("temperature") == 0 and seen.get("system") == aj.SYSTEM and seen.get("model") == aj.MODEL)
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
check("code_action 기록(live/paper/not_entered)", 'aj["code_action"] = "live" if live_info else "paper"' in src
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

print(f"\n{len(fails)} failed")
raise SystemExit(1 if fails else 0)
