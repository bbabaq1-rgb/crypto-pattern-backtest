"""
test_ai_elliott.py — AI 엘리엇 BTC 자율매매(2026-10-28 사용자 결정) 고정. 네트워크·API·거래소 없음.

사용자 지시 "엘리엇 파동에 따라 비트만 100usdt이하로 ai가 자율매매하도록 변경 원칙 변경" + 설정 선택
(전용 포트 $100 · 3배 · 롱·숏 · 매시간). 여기서 고정하는 것은 '수익이 난다'가 아니라
**사용자가 정한 한도와 안전장치가 코드에 그대로 박혀 있고, AI 가 그것을 넘을 길이 없다**는 것이다.

  1. 사양·등재 — registry exit_spec(signal_barrier)·live_cap(ledger 포트 $100·3배·1포지션), universe 스위치, 모델
  2. 격리 — ai_elliott 는 거래소·스케줄러·체결 엔진을 import 하지 않고 주문 함수를 부르지 않는다
  3. signal_barriers — 손절·익절 방향·거리 검증(0.3~8% / 0.3% 이상), 위반이면 None(진입 없음)
  4. 입력 — 닫힌 봉만(형성 중 봉·미래 봉 무시), 스윙 피벗
  5. 응답 파싱·검증 — 허용 밖 행동·막힌 방향·잘못된 가격은 전부 '아무것도 안 함'으로
  6. API 호출 — 거절·토큰 초과·예외·키 없음이 모두 오류 기록으로 끝난다(거래 경로 무영향)
  7. tick — 평탄/보유/정지/포트 소진 상태별 결과
  8. ledger 포트 — 포트 = 100 + 실현 손익, 증거금 = min(포트, 100), $10 미만 None. tp1 복리 경로 불변
  9. 반대 방향 가드(OKX net 모드)
 10. ai_close — 자기 몫만, OCO 집행분은 시장가 재주문 없이 기록, 실패는 보류
 11. 체결 엔진 배선(소스 순서)
 12. DB — 같은 날 반복 매매가 서로를 지우지 않는다(entry_ts 키), 복원이 새 포지션을 '청산됨'으로 오인하지 않는다
 13. exchange — 익절가가 이미 지나간 진입은 주문 전에 거부

실행: python test_ai_elliott.py
"""
import ast
import io
import json
import os
import types

import ai_elliott as ae
import exchange as ex_mod
import exit_barriers as xb
import paper_executor as pe
import sizing

fails = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f" — {detail}"))
    cond or fails.append(name)


H = 3_600_000


def mkrows(n, start=80000.0, step=None, t0=1_761_000_000_000, tf_ms=H):
    """결정론적 합성 봉 — 지그재그(10봉 올림·7봉 내림)."""
    rows, px = [], start
    for i in range(n):
        up = (i % 17) < 10
        o = px
        c = o * (1.004 if up else 0.995)
        rows.append(dict(ts=t0 + i * tf_ms, date="2026-10-%02d" % (1 + (i * tf_ms) // 86_400_000 % 28),
                         o=o, h=max(o, c) * 1.001, l=min(o, c) * 0.999, c=c, v=10.0 + i % 5))
        px = c
    return rows


reg = json.load(io.open("registry.json", encoding="utf-8"))
uni = json.load(io.open("universe.json", encoding="utf-8"))
rp = next(p for p in reg["patterns"] if p["id"] == ae.PATTERN)
SPEC, CAP = rp["exit_spec"], rp["live_cap"]

# ── 1. 사양·등재 ─────────────────────────────────────────────────────────────
check("모델 = 사용자 선택값", ae.MODEL == "claude-sonnet-5-5")
check("종목 BTC 하나 · 1h 판단", ae.SYMBOL == "BTC" and ae.TF == "1h")
check("exit_spec = signal_barrier, 손절 0.3~8% · 익절 0.3%+ · 168봉 시간청산",
      SPEC == {"type": "signal_barrier", "horizon_bars": 168, "min_stop_pct": 0.003, "max_stop_pct": 0.08,
               "min_target_pct": 0.003}, SPEC)
check("live_cap = 전용 포트 $100(ledger) · 건당 상한 $100 · 3배 · 1포지션",
      CAP["pot_mode"] == "ledger" and CAP["start_margin"] == 100.0 and CAP["max_margin"] == 100.0
      and CAP["leverage"] == 3 and CAP["max_open"] == 1, CAP)
check("registry 상태 = 사용자 강제(검증 안 됨 명시)", rp["status"] == "forced_live_user" and rp["validated"] is False)
check("체결 엔진이 같은 규격을 읽는다(EXIT_SPECS·LIVE_CAPS)",
      pe.EXIT_SPECS.get(ae.PATTERN) == SPEC and pe.LIVE_CAPS.get(ae.PATTERN) == CAP)
tr = [t for t in uni.get("ai_traders", []) if t.get("pattern") == ae.PATTERN]
check("universe ai_traders 스위치 — BTC·1h·롱숏", len(tr) == 1 and tr[0]["symbol"] == "BTC"
      and tr[0]["tf"] == "1h" and tr[0]["directions"] == ["long", "short"], tr)
check("enabled() 는 스위치를 따른다", ae.enabled() is True)
check("메인 슬롯·사이징 상수 불변(RISK 1.5% / LEV_CAP 3 / MAX_LIVE_POS 13)",
      sizing.RISK_FRAC == 0.015 and sizing.LEV_CAP == 3 and pe.MAX_LIVE_POS == 13)
check("steward 대상 아님(adopted_* 목록에 없음) — 손실 한도는 포트",
      ae.PATTERN not in json.dumps({k: uni.get(k) for k in ("adopted_patterns", "adopted_4h_patterns",
                                                             "adopted_1h_patterns")}))

# ── 2. 격리 ──────────────────────────────────────────────────────────────────
src = io.open("ai_elliott.py", encoding="utf-8").read()
tree = ast.parse(src)
top = set()
for node in tree.body:                      # 모듈 최상위 import 만(__main__ 블록의 detlib 은 dry-run 전용)
    if isinstance(node, ast.Import):
        top |= {a.name.split(".")[0] for a in node.names}
    elif isinstance(node, ast.ImportFrom) and node.module:
        top.add(node.module.split(".")[0])
check("최상위 import 에 거래소·스케줄러·체결엔진·detlib 없음",
      not (top & {"exchange", "scheduler", "paper_executor", "detlib", "elliott_watch"}), top)
check("주문 함수를 부르지 않는다",
      not any(k in src for k in ("place_swap_entry", "close_swap_position", "place_stop_algo", "create_market_order")))
check("SDK 는 _create 안에서만 import", src.count("import anthropic") == 2
      and "def _create" in src.split("import anthropic")[0])

# ── 3. signal_barriers ───────────────────────────────────────────────────────
sb = xb.signal_barriers
check("롱 정상", sb(SPEC, {"stop": 99.0, "target": 103.0}, 100.0, "long")[:2] == (99.0, 103.0))
check("숏 정상", sb(SPEC, {"stop": 101.0, "target": 97.0}, 100.0, "short")[:2] == (101.0, 97.0))
check("손절이 반대쪽이면 None", sb(SPEC, {"stop": 101.0, "target": 103.0}, 100.0, "long") is None
      and sb(SPEC, {"stop": 99.0, "target": 97.0}, 100.0, "short") is None)
check("익절이 반대쪽이면 None", sb(SPEC, {"stop": 99.0, "target": 99.5}, 100.0, "long") is None)
check("손절이 0.3% 보다 가까우면 None", sb(SPEC, {"stop": 99.8, "target": 103.0}, 100.0, "long") is None)
check("손절이 8% 보다 멀면 None", sb(SPEC, {"stop": 91.5, "target": 110.0}, 100.0, "long") is None)
check("경계 8% 는 허용", sb(SPEC, {"stop": 92.0, "target": 110.0}, 100.0, "long") is not None)
check("익절이 0.3% 보다 가까우면 None", sb(SPEC, {"stop": 99.0, "target": 100.2}, 100.0, "long") is None)
check("숫자 아님·0·음수·방향 오타 → None",
      sb(SPEC, {"stop": "x", "target": 103}, 100.0, "long") is None
      and sb(SPEC, {"stop": 0, "target": 103}, 100.0, "long") is None
      and sb(SPEC, {"stop": 99, "target": 103}, 100.0, "up") is None
      and sb(SPEC, None, 100.0, "long") is None)
check("다른 타입 spec 이면 None", sb({"type": "pct_barrier", "tp_pct": 0.01, "sl_pct": 0.08},
                                    {"stop": 99, "target": 103}, 100.0, "long") is None)
check("barriers(..., sig=) 가 signal_barrier 로 라우팅",
      xb.barriers(SPEC, None, 0, 100.0, "long", sig={"stop": 99.0, "target": 103.0})[:2] == (99.0, 103.0)
      and xb.barriers(SPEC, None, 0, 100.0, "long") is None)
check("pct·atr 경로는 sig 인자와 무관(종전 동일)",
      xb.barriers({"type": "pct_barrier", "tp_pct": 0.01, "sl_pct": 0.08}, None, 0, 100.0, "long", sig={"stop": 1})[:2]
      == (92.0, 101.0))
check("describe 한 줄", "신호 가격" in xb.describe(SPEC) and "168봉" in xb.describe(SPEC))

# ── 4. 입력: 닫힌 봉·피벗·인과 ───────────────────────────────────────────────
rows = mkrows(200)
now = rows[-1]["ts"] + H // 2           # 마지막 봉은 형성 중
cl = ae.closed(rows, "1h", now)
check("형성 중인 마지막 봉을 뺀다", len(cl) == len(rows) - 1 and cl[-1]["ts"] == rows[-2]["ts"])
check("정확히 닫힌 순간은 포함", len(ae.closed(rows, "1h", rows[-1]["ts"] + H)) == len(rows))
pv = ae.pivots(cl, 0.006)
check("피벗이 고/저 교대", len(pv) > 4 and all(pv[i][0] != pv[i + 1][0] for i in range(len(pv) - 1)))
check("피벗 가격이 봉 고저에서 나온다", all((k == "H" and p == cl[i]["h"]) or (k == "L" and p == cl[i]["l"])
                                        for k, p, i in pv))
btc = {"1h": cl, "4h": ae.closed(mkrows(120, tf_ms=4 * H), "4h", now), "1d": []}
p1 = ae.build_payload(now, btc, {}, None, None, 100.0, 100.0, 3, ["wait"], [], SPEC, [], [])
fut = rows + [dict(rows[-1], ts=rows[-1]["ts"] + H * k, c=1.0, h=1.0, l=1.0, o=1.0) for k in (1, 2, 3)]
btc2 = dict(btc, **{"1h": ae.closed(fut, "1h", now)})
p2 = ae.build_payload(now, btc2, {}, None, None, 100.0, 100.0, 3, ["wait"], [], SPEC, [], [])
check("미래 봉을 붙여도 입력이 같다(인과)", json.dumps(p1) == json.dumps(p2))
check("봉 수 상한(1h 120)", len(p1["btc"]["1h"]["bars_t_o_h_l_c_v"]) == ae.BARS["1h"])
cs = ae.count_summary(ae.load_count())
check("카운트 요약 — 파동 6개·시나리오 4개·트리거·레벨", cs and len(cs["waves"]) == 6 and len(cs["scenarios"]) == 4
      and cs["triggers"] and cs["levels"])
check("카운트 요약은 원본보다 훨씬 짧다", len(json.dumps(cs, ensure_ascii=False)) <
      len(io.open(ae.COUNT_FILE, encoding="utf-8").read()) * 0.5)

# ── 5. 파싱·검증 ─────────────────────────────────────────────────────────────
ok = ae.parse('잡문 {"action":"open_long","stop":79000,"target":84000,"confidence":1.7,'
              '"wave_view":"v","invalidation":"i","rationale":"r"} 끝')
check("파싱: 앞뒤 잡문 허용·confidence 클램프", ok and ok["action"] == "open_long" and ok["confidence"] == 1.0)
check("파싱: 모르는 행동 → None", ae.parse('{"action":"buy","stop":1,"target":2}') is None)
check("파싱: 가격 음수·NaN → 0", ae.parse('{"action":"wait","stop":-5,"target":"nan"}')["stop"] == 0.0)
check("파싱: 빈 응답 → None", ae.parse("") is None and ae.parse("no json") is None)
flat_all = ae.allowed_actions(None, {"directions": ["long", "short"]}, set(), True)
check("평탄 허용 = 롱·숏·대기", flat_all == ["open_long", "open_short", "wait"])
check("보유 허용 = 유지·청산", ae.allowed_actions({"direction": "long"}, {}, set(), True) == ["hold", "close"])
check("막힌 방향 제외", ae.allowed_actions(None, {}, {"short"}, True) == ["open_long", "wait"])
check("진입 불가(정지·포트 소진)면 대기만", ae.allowed_actions(None, {}, set(), False) == ["wait"])
check("롱만 설정이면 숏 없음", ae.allowed_actions(None, {"directions": ["long"]}, set(), True) == ["open_long", "wait"])
base = {"stop": 0, "target": 0, "confidence": 0.5, "wave_view": "", "invalidation": "", "rationale": ""}
a, plan, why = ae.validate(dict(base, action="open_long", stop=79000, target=84000), None, flat_all, 80500.0, SPEC)
check("검증: 정상 롱 → 계획", a == "open_long" and plan["stop"] == 79000 and plan["target"] == 84000 and why is None)
a, plan, why = ae.validate(dict(base, action="open_short", stop=81000, target=78000), None, ["open_long", "wait"],
                           80500.0, SPEC)
check("검증: 막힌 숏 → 대기", a == "wait" and plan is None and why == "not_allowed:open_short")
a, plan, why = ae.validate(dict(base, action="open_long", stop=81000, target=84000), None, flat_all, 80500.0, SPEC)
check("검증: 손절 반대쪽 → 대기", a == "wait" and why == "bad_barriers")
a, plan, why = ae.validate(dict(base, action="open_long", stop=70000, target=90000), None, flat_all, 80500.0, SPEC)
check("검증: 손절 8% 초과 → 대기", a == "wait" and why == "bad_barriers")
a, plan, why = ae.validate(dict(base, action="open_long", stop=79000, target=84000), {"direction": "long"},
                           ["hold", "close"], 80500.0, SPEC)
check("검증: 보유 중 진입 응답 → 유지", a == "hold" and why == "not_allowed:open_long")
check("검증: 보유 중 close → close", ae.validate(dict(base, action="close"), {"x": 1}, ["hold", "close"], 1.0, SPEC)[0]
      == "close")
check("검증: 응답 없음 → 대기/유지", ae.validate(None, None, flat_all, 1.0, SPEC)[0] == "wait"
      and ae.validate(None, {"x": 1}, ["hold", "close"], 1.0, SPEC)[0] == "hold")

# ── 6. API 호출(가짜) ────────────────────────────────────────────────────────
NS = types.SimpleNamespace


def fake_resp(text="", stop_reason="end_turn", model="claude-sonnet-5-5", category=None):
    return NS(content=[NS(type="thinking", thinking=""), NS(type="text", text=text)] if text else [],
              stop_reason=stop_reason, model=model, usage=NS(input_tokens=9000, output_tokens=1500),
              stop_details=NS(category=category) if category else None)


_orig_create = ae._create
os.environ.pop("ANTHROPIC_API_KEY", None)
check("키 없음 → no_key (호출 안 함)", ae.call("x")[1] == "no_key")
os.environ["ANTHROPIC_API_KEY"] = "test"
J = json.dumps(dict(base, action="wait"))
ae._create = lambda s, u: fake_resp(J)
parsed, err, ms, usage, served, raw = ae.call("x")
check("정상 응답 파싱 + 토큰·모델 기록", parsed and parsed["action"] == "wait" and err is None
      and usage == {"in": 9000, "out": 1500} and served == "claude-sonnet-5-5")
ae._create = lambda s, u: fake_resp(stop_reason="refusal", category="cyber")
check("거절 → refusal:카테고리", ae.call("x")[1] == "refusal:cyber")
ae._create = lambda s, u: fake_resp('{"action":"wa', stop_reason="max_tokens")
check("토큰 초과 → max_tokens", ae.call("x")[1] == "max_tokens")
ae._create = lambda s, u: fake_resp("not json")
check("파싱 실패 → parse_fail", ae.call("x")[1] == "parse_fail")


def boom(s, u):
    raise RuntimeError("down")


ae._create = boom
check("예외 → err_* (밖으로 안 나감)", ae.call("x")[1].startswith("err_RuntimeError"))
ae._create = lambda s, u: fake_resp(J, model="claude-sonnet-5")
check("서버 폴백이 다른 모델로 답하면 그 모델을 기록", ae.call("x")[4] == "claude-sonnet-5")

# ── 7. tick ──────────────────────────────────────────────────────────────────
R1 = mkrows(200)
R4 = mkrows(120, tf_ms=4 * H)
RD = mkrows(150, tf_ms=24 * H)
NOW = R1[-1]["ts"] + H // 2


def ro(sym, tf):
    return {"1h": R1, "4h": R4, "1d": RD}[tf] if sym == "BTC" else ({"1h": R1, "4h": R4}.get(tf) or [])


last_c = ae.closed(R1, "1h", NOW)[-1]["c"]
seen = {}


def answer(d):
    def f(s, u):
        seen["user"] = u
        return fake_resp(json.dumps(dict(base, **d)))
    return f


kw = dict(trades=[], rows_of=ro, cap=CAP, pot=100.0, margin_next=100.0, spec=SPEC, now_ms=NOW,
          cfg={"directions": ["long", "short"]}, count=ae.load_count(), history=[])
ae._create = answer(dict(action="open_long", stop=round(last_c * 0.99), target=round(last_c * 1.03),
                         wave_view="2파 끝 → 3파", invalidation="저점 이탈"))
rec, sg, cp = ae.tick(position=None, blocked_dirs=set(), can_enter=True, **kw)
check("평탄 + 롱 → 진입 신호(손절·익절 가격 그대로)", sg and sg["direction"] == "long" and cp is None
      and sg["stop"] == round(last_c * 0.99) and sg["target"] == round(last_c * 1.03)
      and sg["pattern"] == ae.PATTERN and sg["ai_elliott"] is True and sg["_ai_rec"] is rec)
check("신호봉 = 마지막 닫힌 봉", sg["ts"] == ae.closed(R1, "1h", NOW)[-1]["ts"])
check("기록 행: kind·모델·버전·결정·크기 1.0·근거(JSON)", rec["kind"] == "elliott_btc" and rec["model"] == ae.MODEL
      and rec["prompt_version"] == ae.PROMPT_VERSION and rec["decision"] == "open_long" and rec["size_mult"] == 1.0
      and json.loads(rec["reasons"])[0] == "2파 끝 → 3파" and rec["direction"] == "long")
check("기록 행의 키가 ai_judgments 컬럼에 전부 있다",
      all(k in io.open("supabase_schema_ai_judge.sql", encoding="utf-8").read() for k in rec),
      [k for k in rec if k not in io.open("supabase_schema_ai_judge.sql", encoding="utf-8").read()])
check("입력에 허용 행동·포트·카운트 요약·BTC/ETH 데이터", all(k in seen["user"] for k in
      ('"allowed_actions"', '"pot_usd"', '"elliott_count"', '"btc"', '"eth"', '"pivots"')))
ae._create = answer(dict(action="open_short", stop=round(last_c * 1.01), target=round(last_c * 0.97)))
rec, sg, cp = ae.tick(position=None, blocked_dirs={"short"}, can_enter=True, **kw)
check("숏이 막혔는데 숏 응답 → 아무것도 안 함", sg is None and cp is None and rec["code_action"] == "ignored:not_allowed:open_short")
check("막힌 이유를 모델에게 알린다", "open_short blocked" in seen["user"])
pos = dict(symbol="BTC", pattern=ae.PATTERN, direction="long", entry_price=last_c * 0.98, stop=last_c * 0.97,
           target=last_c * 1.05, entry_ts=R1[-30]["ts"], entry_date=R1[-30]["date"], live_mode=True, size_usd=100.0)
ae._create = answer(dict(action="close", rationale="카운트 무효"))
rec, sg, cp = ae.tick(position=pos, blocked_dirs=set(), can_enter=True, **kw)
check("보유 + close → 청산 대상 포지션 반환", cp is pos and sg is None and rec["decision"] == "close"
      and rec["bars_held"] == 28 and rec["unreal_ret"] > 0)
ae._create = answer(dict(action="hold"))
rec, sg, cp = ae.tick(position=pos, blocked_dirs=set(), can_enter=True, **kw)
check("보유 + hold → 아무것도 안 함", sg is None and cp is None and rec["decision"] == "hold")
ae._create = boom
rec, sg, cp = ae.tick(position=None, blocked_dirs=set(), can_enter=True, **kw)
check("API 오류 → 진입 없음 + 오류 기록", sg is None and cp is None and rec["error"].startswith("err_")
      and rec["decision"] == "wait")
ae._create = answer(dict(action="open_long", stop=round(last_c * 0.99), target=round(last_c * 1.03)))
rec, sg, cp = ae.tick(position=None, blocked_dirs=set(), can_enter=True, **dict(kw, margin_next=None, pot=8.0))
check("포트 < $10 → 대기만 허용·진입 없음", sg is None and "pot below $10" in seen["user"]
      and '"allowed_actions":["wait"]' in seen["user"])
rec, sg, cp = ae.tick(position=None, blocked_dirs=set(), can_enter=False, **kw)
check("정지 중 → 진입 없음", sg is None and "kill switch" in seen["user"])
rec, sg, cp = ae.tick(position=None, blocked_dirs=set(), can_enter=True,
                      **dict(kw, rows_of=lambda s, t: []))
check("데이터 없음 → no_data, 호출 안 함", rec["error"] == "no_data" and sg is None)
check("summary_line", ae.summary_line(rec).startswith("[ai-elliott]"))
ae._create = _orig_create
os.environ.pop("ANTHROPIC_API_KEY", None)

# ── 8. ledger 포트 ───────────────────────────────────────────────────────────
P = ae.PATTERN


def T(ret, pnl=None, d="2026-10-29"):
    return dict(pattern=P, method="D", ret=ret, pnl_live_usd=pnl, exit_date=d, entry_date=d)


check("거래 없음 → 포트 100, 증거금 100", pe.cap_pot(CAP, P, []) == 100.0 and pe.cap_margin(CAP, P, []) == 100.0)
check("실현 손익 합(pnl_live_usd)", pe.cap_pot(CAP, P, [T(0.02, 6.0), T(-0.01, -3.2)]) == 102.8)
check("포트 > 100 이어도 건당 증거금 100", pe.cap_margin(CAP, P, [T(0.1, 30.0)]) == 100.0)
check("손실 뒤 증거금 = 포트", pe.cap_margin(CAP, P, [T(-0.08, -24.6)]) == 75.4)
check("pnl 없으면 증거금x3xret 로", pe.cap_pot(CAP, P, [T(-0.05)]) == 85.0)
check("포트 < $10 → None(진입 없음)", pe.cap_margin(CAP, P, [T(-0.3, -91.0)]) is None)
check("다른 패턴·방식A 거래는 안 센다", pe.cap_pot(CAP, P, [dict(T(0.5, 50.0), pattern="fvg"),
                                                     dict(T(0.5, 50.0), method="A")]) == 100.0)
tp1cap = pe.LIVE_CAPS.get("tp1_engulfing_1h")
tp1tr = [dict(pattern="tp1_engulfing_1h", method="D", ret=0.008, exit_date="2026-09-11", entry_date="2026-09-11")]
check("tp1 복리 경로 불변(70 x (1+0.008x3))", tp1cap and pe.cap_margin(tp1cap, "tp1_engulfing_1h", tp1tr) == 71.68)

# ── 9. 반대 방향 가드 ────────────────────────────────────────────────────────
K = {("BTC", "long"), ("ETH", "short")}
check("BTC 롱 보유 중 BTC 숏 → 막힘", pe.net_opposite_live("BTC", "short", K))
check("BTC 롱 보유 중 BTC 롱 → 가드 아님(같은 방향은 캡 경로가 몫을 나눈다)", not pe.net_opposite_live("BTC", "long", K))
check("ETH 숏 보유 중 ETH 롱 → 막힘", pe.net_opposite_live("ETH", "long", K))
check("다른 종목 무관", not pe.net_opposite_live("SOL", "long", K) and not pe.net_opposite_live("SOL", "short", K))

# ── 10. ai_close ─────────────────────────────────────────────────────────────
import notify
_orig = (ex_mod.algo_state, ex_mod.close_swap_position, notify.send)
notify.send = lambda *a, **k: False
calls = []
apos = dict(symbol="BTC", pattern=P, direction="long", tf="1h", entry_price=80000.0, stop=79000.0,
            target=84000.0, entry_ts=R1[-20]["ts"], entry_date=R1[-20]["date"], live_mode=True, size_usd=100.0,
            live_order={"qty": 3.7, "leverage": 3, "sl_order_id": "A1"})
mpos = dict(symbol="BTC", pattern="marubozu", direction="long", entry_price=82953.6, live_mode=True, size_usd=46.0,
            live_order=None)
ex_mod.algo_state = lambda lc, aid, inst_id=None: {"state": "live"}


def fake_close(lc, sym, d, sl_algo_id=None, qty=None, qty_frac=None):
    calls.append(dict(sym=sym, d=d, sl=sl_algo_id, qty=qty, frac=qty_frac))
    return 81000.0, "ok"


ex_mod.close_swap_position = fake_close
trs = []
r_ = {"reasons": json.dumps(["v", "i", "r"])}
okc = pe.ai_close(apos, [apos, mpos], object(), trs, ro, r_)
check("겹친 BTC 롱: 자기 계약 수만 닫는다(메인 몫 보존)", okc and calls[-1]["qty"] == 3.7 and calls[-1]["sl"] == "A1")
check("D 거래 기록 — 사유 ai_close · 실손익(100x3x(ret-수수료))", trs and trs[-1]["reason"] == "ai_close"
      and trs[-1]["method"] == "D" and abs(trs[-1]["pnl_live_usd"] - round((1000 / 80000 - pe.FEE) * 300, 2)) < 1e-9
      and apos["d_closed"] and r_["code_action"] == "closed")
ex_mod.algo_state = lambda lc, aid, inst_id=None: {"state": "effective", "actual_px": 84000.0, "actual_side": "tp"}
calls.clear()
bpos = dict(apos, d_closed=False, a_closed=False)
trs2 = []
okc = pe.ai_close(bpos, [bpos], object(), trs2, ro, {})
check("OCO 가 이미 집행됐으면 시장가 재주문 없이 그 체결로 기록(사유 ai_target)",
      okc and not calls and trs2[-1]["reason"] == "ai_target" and trs2[-1]["exit_price"] == 84000.0)
ex_mod.algo_state = lambda lc, aid, inst_id=None: None
cpos = dict(apos, d_closed=False, a_closed=False)
check("OCO 상태 모름 → 보류", pe.ai_close(cpos, [cpos], object(), [], ro, {}) is False and not cpos["d_closed"])
ex_mod.algo_state = lambda lc, aid, inst_id=None: {"state": "live"}
ex_mod.close_swap_position = lambda *a, **k: (None, "network")
dpos = dict(apos, d_closed=False, a_closed=False)
rr = {}
check("주문 실패 → 보류(다음 틱)", pe.ai_close(dpos, [dpos], object(), [], ro, rr) is False
      and rr["code_action"] == "close_network")
check("OKX 미연결 → 보류", pe.ai_close(dict(apos, d_closed=False), [], None, [], ro, {}) is False)
ppos = dict(apos, live_mode=False, live_order=None, d_closed=False, a_closed=False)
trs3 = []
check("페이퍼 행은 마지막 닫힌 봉 종가로 기록", pe.ai_close(ppos, [ppos], None, trs3, ro, {})
      and trs3[-1]["exit_price"] == round(ae.closed(R1, "1h", int(__import__("time").time() * 1000))[-1]["c"], 8))
ex_mod.algo_state, ex_mod.close_swap_position, notify.send = _orig

# ── 11. 체결 엔진 배선 ───────────────────────────────────────────────────────
es = io.open("paper_executor.py", encoding="utf-8").read()
i_sig = es.find('sig = _load("signals_today.json"')
i_tick = es.find("ai_elliott.tick(")
i_loop = es.find('for s in sig.get("signals", []):')
check("AI 판단은 신호 파일 로드 뒤·진입 루프 앞", 0 < i_sig < i_tick < i_loop)
check("매시 fast 틱에서만(--slow 틱 제외) · 스위치 확인", "if not slow and ai_elliott.enabled():" in es)
check("정지·킬스위치 중 평탄 판단 생략", "el_can_enter = bool(el_cap) and not (live_conn and kill_switch)" in es
      and "elif el_pos is None and not el_can_enter:" in es)
check("진입 신호는 sig 에 덧붙여 같은 가드를 탄다", 'sig.setdefault("signals", []).append(el_sig)' in es)
check("AI 신호에는 진입 AI 판단(ai_judge)을 또 붙이지 않는다",
      es.find('if s.get("ai_elliott"):') < es.find("elif ai_on:") < es.find("aj = ai_judge.judge(rows, ei"))
i_block = es.find("if entry_blocked(s[\"symbol\"]")
i_net = es.find('if net_opposite_live(s["symbol"], s["direction"], live_dir_keys):')
i_bal = es.find("bal_info  = ex_mod.get_balance(live_conn)")
check("반대 방향 가드: 중복 방어 뒤·사이징 앞(모든 신호)", 0 < i_block < i_net < i_bal)
check("배리어 산출에 신호를 넘긴다", 'xb.barriers(spec, rows, ei, entry, s["direction"], sig=s)' in es)
check("signal_barrier 는 체결가 기준 재정렬을 안 한다", 'and xb.spec_type(spec) != "signal_barrier":' in es)
check("킬스위치 중 cap 은 페이퍼 행을 안 만든다", "if cap:\n                continue        # cap 프로젝트(tp1·AI 엘리엇)" in es)
check("AI 조기 청산 실행은 ai_close 로만", es.count("ai_close(el_close") == 1)
check("판단 행은 ai_records 로 DB 기록", "ai_records.append(el_rec)" in es)
check("tf 맵에 ai_traders 포함(복원 tf 1h)", pe._pattern_tf(ae.PATTERN) == "1h")
check("barriers_of: signal_barrier 는 대칭 복원 안 함",
      pe.barriers_of(dict(pattern=P, stop=79000.0, target=None, entry_price=80000.0)) == (79000.0, None))

# ── 12. DB — 같은 날 반복 매매 ──────────────────────────────────────────────
class FQ:
    def __init__(self, store, table):
        self.store, self.table, self.op, self.f, self.ors, self.rng, self.upd = store, table, None, [], [], None, None

    def select(self, *a):
        self.op = "select"
        return self

    def delete(self):
        self.op = "delete"
        return self

    def update(self, d):
        self.op, self.upd = "update", d
        return self

    def eq(self, k, v):
        self.f.append((k, v))
        return self

    def or_(self, s):
        self.ors.append(s)
        return self

    def order(self, *a, **k):
        return self

    def range(self, a, b):
        self.rng = (a, b)
        return self

    def limit(self, n):
        return self

    def execute(self):
        self.store["log"].append((self.table, self.op, list(self.f), list(self.ors), self.rng))
        rows = [r for r in self.store.get(self.table, []) if all(r.get(k) == v for k, v in self.f)]
        if self.rng:
            rows = rows[self.rng[0]:self.rng[1] + 1]
        return NS(data=rows)


class FC:
    def __init__(self, store):
        self.store = store

    def table(self, t):
        return FQ(self.store, t)


st = {"log": []}
pe._dedupe_delete(FC(st), "trades", {"symbol": "BTC", "method": "D"}, 1761000000000)
check("ts 있으면 같은 ts·ts 없는 행만 지운다", st["log"][-1][3] == ["entry_ts.eq.1761000000000,entry_ts.is.null"])
pe._dedupe_delete(FC(st), "trades", {"symbol": "BTC"}, None)
check("ts 없으면 종전 키", st["log"][-1][3] == [] and st["log"][-1][1] == "delete")
import supabase_client as sc
_orig_db, _orig_ins = pe._db, sc.insert_tolerant
ins = []
pe._db = lambda: FC(st)
sc.insert_tolerant = lambda cli, table, rows, **k: (ins.append((table, rows)) or rows, [])
pe.push_trades_db([dict(symbol="BTC", pattern=P, direction="long", entry_date="2026-10-29", entry_price=1.0,
                        exit_date="2026-10-29", exit_price=1.1, ret=0.1, hold_bars=3, reason="ai_close",
                        method="D", entry_ts=1761000000000)])
check("trades 행에 entry_ts", ins[-1][0] == "trades" and ins[-1][1][0]["entry_ts"] == 1761000000000)
check("trades 재삽입 방지 삭제가 ts 키", st["log"][-1][3] == ["entry_ts.eq.1761000000000,entry_ts.is.null"])
pe.mark_closed_db([dict(symbol="BTC", pattern=P, direction="long", entry_date="2026-10-29", entry_ts=1761000000000)])
check("mark_closed 도 ts 로 좁힌다", st["log"][-1][1] == "update"
      and st["log"][-1][3] == ["entry_ts.eq.1761000000000,entry_ts.is.null"])
# 복원: 같은 날 앞 거래(ts1)가 청산됐고 새 포지션(ts2)이 열려 있다 → 새 포지션은 열린 것으로 복원돼야 한다
ts1, ts2 = 1761000000000, 1761014400000
store = {"log": [],
         "trades": [dict(method="D", symbol="BTC", direction="long", pattern=P, entry_date="2026-10-29",
                         entry_price=1.0, exit_price=1.1, return_pct=10.0, exit_reason="ai_close", entry_ts=ts1),
                    dict(method="D", symbol="ETH", direction="long", pattern="fvg", entry_date="2026-10-20",
                         entry_price=1.0, exit_price=1.1, return_pct=10.0, exit_reason="stop", entry_ts=None)],
         "positions": [dict(symbol="BTC", direction="long", pattern=P, entry_date="2026-10-29", entry_ts=ts2,
                            entry_price=2.0, stop_loss=1.9, target=2.2, status="open", live_mode=True, tf="1h"),
                       dict(symbol="ETH", direction="long", pattern="fvg", entry_date="2026-10-20", entry_ts=999,
                            entry_price=1.0, stop_loss=0.9, status="open", live_mode=True)]}
pe._db = lambda: FC(store)
pos_r, tr_r = pe.restore_state_db([], [])
bt = next(p for p in pos_r if p["symbol"] == "BTC")
et = next(p for p in pos_r if p["symbol"] == "ETH")
check("같은 날 앞 거래 청산이 새 포지션을 '청산됨'으로 만들지 않는다(ts 대조)", bt["d_closed"] is False)
check("ts 없는 구 거래는 날짜로 대조(종전 동작)", et["d_closed"] is True)
check("복원 거래에 entry_ts", any(t.get("entry_ts") == ts1 for t in tr_r))
check("복원은 range 페이지로 읽는다(1000행 상한 회피)",
      any(l[0] == "trades" and l[1] == "select" and l[4] == (0, 999) for l in store["log"]))
pe._db, sc.insert_tolerant = _orig_db, _orig_ins
sql = io.open("supabase_schema_patch_2026_10_28.sql", encoding="utf-8").read()
check("스키마 패치 SQL: trades.entry_ts + 인덱스", "alter table public.trades add column if not exists entry_ts bigint" in sql)

# ── 13. exchange 익절가 사전 검증 ────────────────────────────────────────────
class FX:
    def __init__(self, last):
        self.last, self.orders = last, []

    def set_margin_mode(self, *a, **k): pass

    def set_leverage(self, *a, **k): pass

    def fetch_ticker(self, s): return {"last": self.last}

    def fetch_balance(self): return {"USDT": {"free": 500.0}}

    def market(self, s): return {"contractSize": 0.01, "limits": {"amount": {"min": 0.01}}}

    def amount_to_precision(self, s, q): return f"{q:.2f}"

    def price_to_precision(self, s, p): return f"{float(p):.1f}"

    def create_market_order(self, *a, **k):
        self.orders.append(a)
        raise AssertionError("주문이 나가면 안 된다")


fx = FX(81000.0)
res, why = ex_mod.place_swap_entry({"exchange": fx}, "BTC", "long", 79000.0, size_usd=100.0, target_px=80500.0, leverage=3)
check("롱 익절가가 이미 시세 아래 → 주문 전 거부", res is None and why.startswith("target_px_wrong_side") and not fx.orders)
fx = FX(79000.0)
res, why = ex_mod.place_swap_entry({"exchange": fx}, "BTC", "short", 81000.0, size_usd=100.0, target_px=79500.0, leverage=3)
check("숏 익절가가 이미 시세 위 → 주문 전 거부", res is None and why.startswith("target_px_wrong_side") and not fx.orders)

print(f"\n{len(fails)} failed")
raise SystemExit(1 if fails else 0)
