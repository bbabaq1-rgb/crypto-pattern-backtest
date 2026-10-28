"""
ai_elliott.py — AI 엘리엇 BTC 자율매매 (2026-10-28 사용자 결정)

  사용자 지시: "엘리엇 파동에 따라 비트만 100usdt이하로 ai가 자율매매하도록 변경 원칙 변경"
  사용자 선택(같은 날): 전용 포트 $100 · 레버리지 3배 · 롱·숏 둘 다 · 매시간 판단(모델 사용자 지정 — MODEL)

무엇을 하나
  매시 fast 틱(:03)마다 한 번, BTC 닫힌 봉(1h/4h/1d)·스윙 피벗·동결 엘리엇 카운트(elliott_count.json)·자기
  포지션과 포트 상태를 LLM 에 넘겨 엘리엇 구조에 따른 결정을 JSON 으로 받는다.
    평탄  → open_long / open_short (손절·익절 가격 포함) / wait
    보유  → hold / close
  주문은 체결 엔진(paper_executor)의 live_cap 경로가 낸다. 이 모듈은 거래소·스케줄러·체결 엔진을 import 하지
  않는다(test_ai_elliott 가 고정) — 결정과 기록 행만 만든다.

코드가 강제하는 것 — AI 는 이것을 바꿀 수 없다
  · BTC 하나, 동시 1포지션(registry live_cap.max_open), 증거금 = min(포트, $100), 레버리지 3배(격리)
  · 포트 = $100 + 이 프로젝트 실현 손익 합(paper_executor.cap_pot). $10 미만이면 진입하지 않는다(충전은 사용자)
  · 손절·익절 필수 — 거래소 OCO 로 걸린다. 손절 거리 0.3%~8%, 익절 0.3% 이상(exit_barriers.signal_barriers).
    AI 가 낸 가격이 이 범위를 벗어나면 진입하지 않는다(손절 없는 실거래 금지 원칙)
  · OKX 계정은 종목당 한 방향(net)이다. 다른 전략이 BTC 반대 방향을 들고 있으면 그 방향 진입은 막힌다.
    반대로 AI 가 BTC 숏을 들고 있는 동안엔 다른 전략의 BTC 롱도 막힌다(paper_executor.net_opposite_live)
  · 킬스위치(equity < $100)·trading_halt 적용 — 그때는 평탄 상태 판단을 아예 부르지 않는다
  · AI 오류·거절·파싱 실패·허용 밖 응답 → 아무것도 하지 않는다(진입 없음, 보유는 거래소 OCO 가 계속 지킨다)
  · 모든 판단을 ai_judgments(kind=elliott_btc)에 입력 요약·응답·모델·버전·토큰과 함께 기록한다

엘리엇 카운트는 읽기만 한다. 라벨의 유일한 원천은 elliott_count.json(revisions 로만 바뀜)이고, AI 는 그 아래
하위 차수 카운트를 스스로 세어 판단한다. 브리핑 스크립트(elliott_watch.py)와는 import 관계가 없다.

검증된 전략이 아니다 — 엘리엇 채점 장부는 무작위 보행보다 나빴다(누적 브리어 0.243 vs 0.205). 사용자가 소액 한도를
정하고 돌리는 실험이고 손실 상한은 포트 $100 이다. 프롬프트도 그 사실을 모델에게 알린다(과매매 억제).

비용: 하루 24회, 회당 입력 약 1만 토큰 · 출력(생각 포함) 수천 토큰 — 토큰은 행마다 기록한다.
프롬프트 캐시는 쓰지 않는다 — 호출 간격(1시간)이 기본 캐시 수명(5분)보다 길고, 1시간 캐시는 쓰기 비용이 2배라 이득이 없다.

실행: python ai_elliott.py --dry   (로컬 데이터로 입력만 만들어 보여 준다. 키가 있으면 판단까지, 주문은 절대 없음)
"""
import hashlib
import json
import math
import os
import time

import exit_barriers as xb

PATTERN = "ai_elliott_btc"
KIND = "elliott_btc"                  # ai_judgments.kind — ai_judge_report 의 entry/exit 평가와 섞이지 않는다
SYMBOL = "BTC"
TF = "1h"
MODEL = "claude-sonnet-5-5"           # 사용자 선택(2026-10-28)
EFFORT = "medium"                     # 구조 판단이라 low 보다 한 단계 위. 생각은 이 모델에서 기본으로 켜져 있다
PROMPT_VERSION = "elliott_v1_2026_10_28"
FALLBACK_BETA = "server-side-fallback-2026-07-01"   # 안전 분류기 거절 시 서버가 다른 모델로 재시도("default")
MAX_TOKENS = 8000                     # 생각 토큰 포함 상한
TIMEOUT_S = 90
COUNT_FILE = "elliott_count.json"
UNIVERSE_FILE = "universe.json"
BARS = {"1h": 120, "4h": 90, "1d": 100}          # 프롬프트에 넣는 닫힌 봉 수
ZZ_PCT = {"1h": 0.006, "4h": 0.015, "1d": 0.05}  # 스윙 피벗(고저 지그재그) 임계
TF_MS = {"1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}
FLAT_ACTIONS = ("open_long", "open_short", "wait")
OPEN_ACTIONS = ("hold", "close")
ACTIONS = FLAT_ACTIONS + OPEN_ACTIONS

SYSTEM = (
    "You run a small, separately funded BTC-USDT perpetual futures account on OKX for the desk owner, trading only "
    "from Elliott Wave structure. You are called once per hour, just after a 1h candle closes, and you decide one "
    "action.\n\n"
    "What the code enforces (you cannot change it): one BTC position at a time; margin = min(pot, $100) at 3x "
    "isolated leverage; every entry carries a stop and a target that are placed on the exchange as an OCO bracket and "
    "fire between your hourly calls; the stop must be 0.3%-8% from the last close and the target at least 0.3% away, "
    "otherwise the entry is rejected; only the actions listed in allowed_actions are possible (a direction can be "
    "blocked because the account nets BTC exposure with another strategy); if the pot falls below $10 trading stops. "
    "Costs: about 0.1-0.2% of notional per round trip plus funding every 8 hours.\n\n"
    "Method: elliott_count is the desk's frozen higher-degree count. Treat its labels as fixed context and do not "
    "relabel them. Build your own lower-degree count from the 4h and 1h candles and the swing pivots provided "
    "(pivots are high/low zigzags; the last pivot is still forming). Respect the rules: wave 2 never retraces beyond "
    "the start of wave 1; wave 3 is never the shortest of waves 1, 3 and 5; wave 4 does not enter wave 1's territory "
    "except in diagonals; zigzags are 5-3-5, flats 3-3-5, triangles 3-3-3-3-3 and occur only as wave 4, B, X or the "
    "final wave of a combination; combinations are W-X-Y(-X-Z). Use common Fibonacci relationships (wave 2 at "
    "50-61.8%, wave 3 at 1.618x wave 1, wave 4 at 23.6-38.2%, C equal to A or 1.618x A) as guides, not rules. ETH "
    "pivots are there for cross-confirmation.\n\n"
    "Entries: act only when one count is clearly favored and its invalidation price is close. Put the stop just "
    "beyond the price that invalidates the count you are trading, never at an arbitrary percentage; if that price is "
    "closer than 0.3% or farther than 8%, wait. Put the target at a Fibonacci projection that the same count implies, "
    "and prefer reward/risk of at least 1.5. Waiting is the default and most hours should be wait: this desk's Elliott "
    "forecasts have so far scored worse than a random walk, and trading ambiguous structure is the main way this "
    "account loses money.\n\n"
    "Open position: hold unless the count you entered on has been invalidated or its target structure is complete. "
    "Small adverse moves are what the stop is for; close early only for a structural reason.\n\n"
    "Output: one JSON object matching the schema. stop and target are absolute BTC prices for open_long and "
    "open_short, and 0 for every other action. confidence is between 0 and 1. Write wave_view (the count you act on, "
    "one line), invalidation (the price and why) and rationale (at most three short sentences) in Korean."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": list(ACTIONS)},
        "stop": {"type": "number"},
        "target": {"type": "number"},
        "confidence": {"type": "number"},
        "wave_view": {"type": "string"},
        "invalidation": {"type": "string"},
        "rationale": {"type": "string"},
    },
    "required": ["action", "stop", "target", "confidence", "wave_view", "invalidation", "rationale"],
    "additionalProperties": False,
}


# ── 스위치 ─────────────────────────────────────────────────────────────────────
def config(path=UNIVERSE_FILE):
    """universe.json `ai_traders` 의 이 프로젝트 항목. 없으면 None — 켜고 끄는 스위치는 이 목록 하나다."""
    try:
        u = json.load(open(path, encoding="utf-8"))
    except Exception:
        return None
    for t in u.get("ai_traders", []) or []:
        if t.get("pattern") == PATTERN:
            return t
    return None


def enabled(path=UNIVERSE_FILE):
    return config(path) is not None


def available():
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


# ── 입력(인과: 닫힌 봉만) ──────────────────────────────────────────────────────
def closed(rows, tf, now_ms):
    """닫힌 봉만. CSV 마지막 행은 거래소가 주는 형성 중인 봉이다(scheduler._closed_idx 와 같은 이유)."""
    bar = TF_MS[tf]
    return [r for r in (rows or []) if r.get("ts") is not None and r["ts"] + bar <= now_ms]


def pivots(rows, pct):
    """고저 기준 지그재그 스윙 [(kind 'H'/'L', price, index)]. 마지막 하나는 아직 진행 중(미확정)이다."""
    if not rows:
        return []
    piv, trend = [], None
    hi, lo = (rows[0]["h"], 0), (rows[0]["l"], 0)
    for i in range(1, len(rows)):
        r = rows[i]
        if trend in (None, "up"):
            if r["h"] >= hi[0]:
                hi = (r["h"], i)
            if r["l"] <= hi[0] * (1 - pct):
                piv.append(("H",) + hi)
                trend, lo = "down", (r["l"], i)
                continue
        if trend in (None, "down"):
            if r["l"] <= lo[0]:
                lo = (r["l"], i)
            if r["h"] >= lo[0] * (1 + pct):
                piv.append(("L",) + lo)
                trend, hi = "up", (r["h"], i)
    if trend == "up":
        piv.append(("H",) + hi)
    elif trend == "down":
        piv.append(("L",) + lo)
    return piv


def _t(ts):
    return time.strftime("%m-%d %H:%M", time.gmtime(int(ts) / 1000))


def _px(x):
    x = float(x)
    return round(x) if x >= 10000 else round(x, 2)


def bars_compact(rows, n):
    """[시각(UTC), 시, 고, 저, 종, 거래량] — 토큰을 아끼려고 키 없이 배열로."""
    return [[_t(r["ts"]), _px(r["o"]), _px(r["h"]), _px(r["l"]), _px(r["c"]), round(float(r.get("v") or 0), 1)]
            for r in rows[-n:]]


def pivots_compact(rows, pct, n=24):
    return [[k, _px(p), _t(rows[i]["ts"])] for k, p, i in pivots(rows, pct)[-n:]]


def atr_pct(rows, n=14):
    if len(rows) <= n:
        return None
    trs = []
    for j in range(len(rows) - n, len(rows)):
        h, l, pc = rows[j]["h"], rows[j]["l"], rows[j - 1]["c"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return round(sum(trs) / n / rows[-1]["c"] * 100, 3) if rows[-1]["c"] else None


def load_count(path=COUNT_FILE):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return None


def _short(v, n):
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    return s if len(s) <= n else s[:n] + "…"


def count_summary(count):
    """동결 카운트의 요약 — 라벨·시나리오·확률·레벨·트리거·최근 재평가. 파일을 그대로 넣으면 4만 자라 줄인다."""
    if not count:
        return None
    o = count.get("outlook") or {}
    sc = count.get("scenarios") or {}
    pct = o.get("scenarios_pct") or {}
    scen = []
    for short, full in (o.get("scenario_keys") or {}).items():
        s = sc.get(full) or {}
        item = {"pct": pct.get(short), "label": s.get("label"), "desc": _short(s.get("desc", ""), 240)}
        for k in ("w2_targets", "w3_proj_from_0618", "invalidation", "pullback_zone", "trigger", "status_2026_10_09"):
            if k in s:
                item[k] = _short(s[k], 240)
        scen.append(item)
    aw = (count.get("correction") or {}).get("aw_update_2026_09_30") or {}
    revs = count.get("revisions") or []
    return {
        "labeled_on": count.get("labeled_on"),
        "degree_note": count.get("degree_note"),
        "prior_context": count.get("context"),
        "waves": [{k: w.get(k) for k in ("label", "date", "price", "kind")} for w in count.get("waves", [])],
        "scenarios": scen,
        "outlook_as_of": o.get("as_of"),
        "wave2_shape_pct_if_first_scenario": o.get("wave2_shape_pct_within_S1"),
        "triggers": [{k: t.get(k) for k in ("px", "dir", "name")} for t in o.get("triggers", [])],
        "levels": [{"px": lv.get("px"), "dir": lv.get("dir"), "name": lv.get("name"),
                    "means": _short(lv.get("means", ""), 90)} for lv in count.get("levels", [])],
        "correction_AW": aw.get("AW"),
        "correction_read": aw.get("read"),
        "recent_revisions": [{"date": r.get("date"), "what": _short(r.get("what", ""), 500)} for r in revs[-1:]],
    }


def position_state(pos, last):
    """보유 포지션 상태(마크 = 마지막 닫힌 1h 봉 종가). 없으면 None."""
    if not pos:
        return None
    px, e = float(last["c"]), float(pos.get("entry_price") or 0)
    long_ = pos.get("direction") == "long"
    unreal = ((px - e) / e if long_ else (e - px) / e) if e else None
    held = None
    if pos.get("entry_ts"):
        held = int((int(last["ts"]) - int(pos["entry_ts"])) // TF_MS["1h"])
    return {"direction": pos.get("direction"), "entry_price": e, "stop": pos.get("stop"), "target": pos.get("target"),
            "entry_time_utc": _t(pos["entry_ts"]) if pos.get("entry_ts") else pos.get("entry_date"),
            "unrealized_pct": round(unreal * 100, 3) if unreal is not None else None,
            "bars_held_1h": held, "margin_usd": pos.get("size_usd")}


def recent_trades(trades, n=6):
    tr = [t for t in trades or [] if t.get("pattern") == PATTERN and t.get("method") == "D"]
    tr.sort(key=lambda t: (str(t.get("exit_date") or ""), str(t.get("entry_date") or "")))
    return [{"dir": t.get("direction"), "entry": t.get("entry_price"), "exit": t.get("exit_price"),
             "ret_pct": round(float(t.get("ret") or 0) * 100, 3), "reason": t.get("reason"),
             "pnl_usd": t.get("pnl_live_usd"), "entry_date": t.get("entry_date"), "exit_date": t.get("exit_date")}
            for t in tr[-n:]]


def recent_decisions(n=3):
    """직전 판단 몇 개(ai_judgments) — 시간마다 견해가 뒤집히지 않게 연속성을 준다. 실패하면 빈 목록."""
    try:
        import supabase_client as sc
        if not sc.available():
            return []
        cli = sc.get_client("service")
        rows = (cli.table("ai_judgments").select("judged_at,decision,reasons,code_action,error")
                .eq("kind", KIND).order("judged_at", desc=True).limit(n).execute().data) or []
    except Exception:
        return []
    out = []
    for r in rows:
        rs = r.get("reasons")
        try:
            rs = json.loads(rs) if isinstance(rs, str) else rs
        except Exception:
            pass
        out.append({"at": r.get("judged_at"), "action": r.get("decision"), "code_action": r.get("code_action"),
                    "view": rs[0] if isinstance(rs, list) and rs else rs, "error": r.get("error")})
    return out


def allowed_actions(pos, cfg, blocked_dirs, can_enter):
    """상태별로 가능한 행동. 보유 중이면 hold/close, 평탄이면 막히지 않은 방향의 진입 + wait."""
    if pos:
        return list(OPEN_ACTIONS)
    acts = []
    dirs = set((cfg or {}).get("directions") or ("long", "short"))
    if can_enter:
        if "long" in dirs and "long" not in blocked_dirs:
            acts.append("open_long")
        if "short" in dirs and "short" not in blocked_dirs:
            acts.append("open_short")
    acts.append("wait")
    return acts


def build_payload(now_ms, btc, eth, count, pos_state, pot, margin_next, lev, allowed, notes, spec,
                  trades_recent, decisions_recent):
    """모델 입력(JSON). btc/eth = {tf: 닫힌 봉 목록}. 전부 now_ms 이전에 닫힌 봉에서 나온다."""
    b1 = btc.get("1h") or []
    payload = {
        "now_utc": time.strftime("%Y-%m-%d %H:%M", time.gmtime(now_ms / 1000)),
        "allowed_actions": allowed,
        "notes": notes,
        "account": {"pot_usd": pot, "margin_next_usd": margin_next, "leverage": lev,
                    "stop_range_pct": [float(spec.get("min_stop_pct", xb.SIGNAL_MIN_STOP)) * 100,
                                       float(spec.get("max_stop_pct", xb.SIGNAL_MAX_STOP)) * 100],
                    "min_target_pct": float(spec.get("min_target_pct", xb.SIGNAL_MIN_TARGET)) * 100,
                    "max_hold_1h_bars": spec.get("horizon_bars")},
        "position": pos_state,
        "recent_trades": trades_recent,
        "recent_decisions": decisions_recent,
        "elliott_count": count_summary(count),
        "btc": {"last_close": _px(b1[-1]["c"]) if b1 else None,
                "last_bar_utc": _t(b1[-1]["ts"]) if b1 else None,
                "atr14_1h_pct": atr_pct(b1)},
        "eth": {},
    }
    for tf in ("1h", "4h", "1d"):
        rs = btc.get(tf) or []
        payload["btc"][tf] = {"bars_t_o_h_l_c_v": bars_compact(rs, BARS[tf]), "pivots": pivots_compact(rs, ZZ_PCT[tf])}
    for tf in ("1h", "4h"):
        rs = eth.get(tf) or []
        if rs:
            payload["eth"][tf] = {"last_close": _px(rs[-1]["c"]), "pivots": pivots_compact(rs, ZZ_PCT[tf], 16)}
    return payload


def prompt_text(payload):
    return "Decision input (JSON; times UTC; bars are closed candles only):\n" + \
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


# ── 호출·파싱 ─────────────────────────────────────────────────────────────────
def _create(system, user_text):
    """
    실제 API 호출 — 테스트는 이 함수를 바꿔 끼운다. SDK 는 여기서만 import 한다(키 없는 환경·테스트에서 불필요).
    thinking 은 보내지 않는다(이 모델에서 기본으로 켜져 있다). 샘플링 파라미터(temperature 등)는 400 이라 보내지 않는다.
    fallbacks="default": 안전 분류기가 거절하면 서버가 범주별 권장 모델로 같은 요청을 재시도한다.
    """
    import anthropic
    client = anthropic.Anthropic(timeout=TIMEOUT_S, max_retries=1)
    return client.beta.messages.create(
        model=MODEL, max_tokens=MAX_TOKENS, system=system,
        betas=[FALLBACK_BETA], fallbacks="default",
        output_config={"effort": EFFORT, "format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": user_text}])


def _err(e):
    """SDK 예외 → 짧은 오류 문자열(구체적인 것부터)."""
    try:
        import anthropic
        if isinstance(e, anthropic.RateLimitError):
            return "rate_limited"
        if isinstance(e, anthropic.APIStatusError):
            return f"http_{e.status_code}:{str(getattr(e, 'message', ''))[:160]}"
        if isinstance(e, anthropic.APITimeoutError):
            return "timeout"
        if isinstance(e, anthropic.APIConnectionError):
            return "conn"
    except Exception:
        pass
    return f"err_{type(e).__name__}:{str(e)[:120]}"


def _json_obj(text):
    if not text:
        return None
    s = text.strip()
    a, b = s.find("{"), s.rfind("}")
    if a < 0 or b <= a:
        return None
    try:
        d = json.loads(s[a:b + 1])
    except Exception:
        return None
    return d if isinstance(d, dict) else None


def parse(text):
    """모델 응답 → 정규화된 dict 또는 None. 가격은 양의 유한수만(아니면 0), confidence 는 0~1 로 자른다."""
    d = _json_obj(text)
    if d is None:
        return None
    act = str(d.get("action", "")).strip().lower()
    if act not in ACTIONS:
        return None

    def num(k):
        try:
            v = float(d.get(k) or 0)
        except (TypeError, ValueError):
            return 0.0
        return v if math.isfinite(v) and v > 0 else 0.0

    try:
        c = float(d.get("confidence", 0.0))
    except (TypeError, ValueError):
        c = 0.0
    c = min(1.0, max(0.0, c)) if math.isfinite(c) else 0.0
    return {"action": act, "stop": num("stop"), "target": num("target"), "confidence": round(c, 3),
            "wave_view": str(d.get("wave_view") or "")[:300],
            "invalidation": str(d.get("invalidation") or "")[:300],
            "rationale": str(d.get("rationale") or "")[:600]}


def _usage(resp):
    u = getattr(resp, "usage", None)
    if u is None:
        return {}
    return {"in": getattr(u, "input_tokens", None), "out": getattr(u, "output_tokens", None)}


def call(user_text):
    """(parsed, error, latency_ms, usage, served_model, raw_text). 예외를 밖으로 내지 않는다."""
    if not available():
        return None, "no_key", 0, {}, None, None
    t0 = time.time()
    try:
        resp = _create(SYSTEM, user_text)
    except Exception as e:
        return None, _err(e), int((time.time() - t0) * 1000), {}, None, None
    ms = int((time.time() - t0) * 1000)
    usage, served = _usage(resp), getattr(resp, "model", None)
    sr = getattr(resp, "stop_reason", None)
    if sr == "refusal":
        cat = getattr(getattr(resp, "stop_details", None), "category", None)
        return None, f"refusal:{cat or '?'}", ms, usage, served, None
    text = "".join(getattr(b, "text", "") or "" for b in (getattr(resp, "content", None) or [])
                   if getattr(b, "type", None) == "text")
    if sr == "max_tokens":
        return None, "max_tokens", ms, usage, served, (text[:600] or None)
    if not text:
        return None, f"empty_{sr or 'response'}", ms, usage, served, None
    parsed = parse(text)
    return parsed, (None if parsed else "parse_fail"), ms, usage, served, text[:800]


# ── 검증 — 코드가 실행할 계획 ──────────────────────────────────────────────────
def validate(parsed, pos, allowed, price, spec):
    """
    AI 응답 → (action, plan | None, why). 규칙 밖이면 아무것도 하지 않는 쪽(wait / hold)으로 떨어진다.
      plan = dict(direction, stop, target, stop_pct, target_pct) — open_long / open_short 일 때만.
    """
    idle = "hold" if pos else "wait"
    if not parsed:
        return idle, None, "no_decision"
    a = parsed["action"]
    if a not in allowed:
        return idle, None, f"not_allowed:{a}"
    if a in ("wait", "hold", "close"):
        return a, None, None
    d = "long" if a == "open_long" else "short"
    bar = xb.signal_barriers(spec, {"stop": parsed["stop"], "target": parsed["target"]}, price, d)
    if bar is None:
        return "wait", None, "bad_barriers"
    stop, tgt, info = bar
    return a, dict(direction=d, stop=stop, target=tgt, **info), None


# ── 한 틱 ─────────────────────────────────────────────────────────────────────
def tick(*, position, trades, rows_of, cap, pot, margin_next, blocked_dirs, can_enter, spec,
         now_ms=None, cfg=None, count=None, history=None):
    """
    결정 1회. 반환 (rec, signal | None, close_pos | None).
      rec       — ai_judgments 기록 행. code_action 은 체결 엔진이 채운다(실제로 한 일).
      signal    — 평탄에서 진입이면 체결 엔진 진입 루프에 덧붙일 신호(가드는 거기서 전부 다시 탄다).
      close_pos — 보유 중 close 면 그 포지션(실행은 paper_executor.ai_close).
    rows_of(sym, tf) 는 체결 엔진의 캐시 로더(형성 중인 봉 포함) — 여기서 닫힌 봉만 고른다.
    """
    now_ms = now_ms or int(time.time() * 1000)
    cfg = cfg if cfg is not None else (config() or {})
    spec = spec or {}
    lev = int((cap or {}).get("leverage") or 3)

    def _rows(sym, tf):
        try:
            return closed(rows_of(sym, tf), tf, now_ms)
        except Exception:
            return []

    btc = {tf: _rows(SYMBOL, tf) for tf in ("1h", "4h", "1d")}
    eth = {tf: _rows("ETH", tf) for tf in ("1h", "4h")}
    b1 = btc["1h"]
    rec = {"judged_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now_ms / 1000)), "kind": KIND,
           "symbol": SYMBOL, "pattern": PATTERN, "direction": (position or {}).get("direction") or "none",
           "tf": TF, "entry_date": None, "entry_ts": None, "entry_px": None,
           "mode": "live", "model": MODEL, "prompt_version": PROMPT_VERSION, "prompt_hash": None,
           "decision": None, "size_mult": 1.0, "confidence": None, "reasons": None,
           "latency_ms": None, "tokens_in": None, "tokens_out": None, "error": None, "features": None,
           "code_action": None, "mark_ts": None, "mark_px": None, "unreal_ret": None, "bars_held": None,
           "live_mode": bool((position or {}).get("live_mode"))}
    if len(b1) < 30:
        rec["error"] = "no_data"
        return rec, None, None
    last = b1[-1]
    price = float(last["c"])
    rec.update(entry_date=last["date"], entry_ts=last["ts"], entry_px=price, mark_ts=last["ts"], mark_px=price)
    pstate = position_state(position, last)
    if pstate:
        rec["unreal_ret"] = round(pstate["unrealized_pct"] / 100, 6) if pstate["unrealized_pct"] is not None else None
        rec["bars_held"] = pstate["bars_held_1h"]
    allowed = allowed_actions(position, cfg, blocked_dirs or set(), can_enter and margin_next is not None)
    notes = []
    for d in sorted(blocked_dirs or ()):
        notes.append(f"open_{d} blocked: another strategy holds the opposite BTC direction (account nets by symbol)")
    if not position and margin_next is None:
        notes.append("pot below $10 — entries disabled")
    if not position and not can_enter:
        notes.append("account kill switch or trading halt is on — entries disabled")
    count = count if count is not None else load_count()
    history = history if history is not None else recent_decisions()
    payload = build_payload(now_ms, btc, eth, count, pstate, pot, margin_next, lev, allowed, notes, spec,
                            recent_trades(trades), history)
    text = prompt_text(payload)
    rec["prompt_hash"] = hashlib.sha256((SYSTEM + "\n" + text).encode("utf-8")).hexdigest()[:16]
    parsed, err, ms, usage, served, raw = call(text)
    rec.update(latency_ms=ms, tokens_in=usage.get("in"), tokens_out=usage.get("out"), error=err)
    if served:
        rec["model"] = served
    action, plan, why = validate(parsed, position, allowed, price, spec)
    rec["decision"] = action
    if parsed:
        rec["confidence"] = parsed["confidence"]
        rec["reasons"] = json.dumps([parsed["wave_view"], parsed["invalidation"], parsed["rationale"]],
                                    ensure_ascii=False)
    feat = {"allowed": allowed, "notes": notes, "price": price, "pot": pot, "margin_next": margin_next,
            "position": pstate, "model_requested": MODEL, "raw_action": (parsed or {}).get("action"),
            "raw_stop": (parsed or {}).get("stop"), "raw_target": (parsed or {}).get("target"),
            "why": why, "plan": plan, "count_as_of": (count or {}).get("labeled_on"),
            "pivots_1h": payload["btc"]["1h"]["pivots"][-10:], "pivots_4h": payload["btc"]["4h"]["pivots"][-8:],
            "raw": raw}
    rec["features"] = json.dumps(feat, ensure_ascii=False, sort_keys=True)
    if why:
        rec["code_action"] = f"ignored:{why}"
    if plan:
        rec["direction"] = plan["direction"]
        sig = {"symbol": SYMBOL, "pattern": PATTERN, "direction": plan["direction"], "tf": TF,
               "date": last["date"], "ts": last["ts"], "stop": plan["stop"], "target": plan["target"],
               "regime": None, "ai_elliott": True, "_ai_rec": rec}
        return rec, sig, None
    if action == "close" and position:
        return rec, None, position
    return rec, None, None


def summary_line(rec):
    """로그 한 줄."""
    if not rec:
        return "[ai-elliott] -"
    if rec.get("error") and not rec.get("reasons"):
        return f"[ai-elliott] 판단 실패({rec['error']}) — 아무것도 안 함 | {rec.get('model')}"
    try:
        f = json.loads(rec.get("features") or "{}")
    except Exception:
        f = {}
    plan = f.get("plan") or {}
    lv = (f" 손절 {plan['stop']:,.0f} / 익절 {plan['target']:,.0f}" if plan else "")
    try:
        view = (json.loads(rec.get("reasons") or "[]") or [""])[0]
    except Exception:
        view = ""
    tag = f" [{f.get('why')}]" if f.get("why") else ""
    return (f"[ai-elliott] {rec.get('decision')}{lv} (conf {rec.get('confidence')}, {rec.get('latency_ms')}ms, "
            f"tok {rec.get('tokens_in')}/{rec.get('tokens_out')}){tag} — {view} | {rec.get('model')}")


if __name__ == "__main__":
    import sys
    if "--dry" not in sys.argv:
        raise SystemExit("python ai_elliott.py --dry  (주문 없음 — 입력·판단만 본다)")
    import detlib
    cache = {}

    def _ro(sym, tf):
        if (sym, tf) not in cache:
            cache[(sym, tf)] = detlib.load_ohlcv(sym, tf)
        return cache[(sym, tf)]

    spec_ = {"type": "signal_barrier", "horizon_bars": 168, "min_stop_pct": 0.003, "max_stop_pct": 0.08,
             "min_target_pct": 0.003}
    r_, s_, c_ = tick(position=None, trades=[], rows_of=_ro, cap={"leverage": 3}, pot=100.0, margin_next=100.0,
                      blocked_dirs=set(), can_enter=True, spec=spec_, history=[])
    print(summary_line(r_))
    print(json.dumps({k: v for k, v in r_.items() if k != "features"}, ensure_ascii=False, indent=1))
    print("signal:", {k: v for k, v in (s_ or {}).items() if k != "_ai_rec"})
