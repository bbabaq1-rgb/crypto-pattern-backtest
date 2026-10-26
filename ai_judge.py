"""
ai_judge.py — 신호별 AI 판단 레이어 (2026-10-23, 사용자 결정 "매매 판단을 기존 거에 AI 판단으로 개선…
클로드 md 를 수정해서라도 이번 판단 규칙은 개선한다" → 그림자 기록 먼저 / 차트 수치만 / 전 배포 패턴).
2026-10-26 확장(사용자 지시 "AI 를 통해서 판단 및 매매 개선할 수 있는 항목들 개선해서 구현"):
  · 진입 특성 v2 — 포트폴리오 맥락(book_*)·상위 TF(1d) 맥락(d1_*)·손절 ATR 배수·같은 종목 최근 성과
  · 청산 검토(그림자) — 방식D 로 들고 있는 포지션을 느린 틱마다 한 번의 배치 호출로 hold/exit 판정해 **기록만**
  · prompt_version — 표본 집계 키(prompt_hash 는 신호별 고유값이라 집계 키로 쓸 수 없었다)
  · 토큰 사용량 기록(비용 추적)

무엇을 하나
  기존 디텍터가 낸 신호 하나하나를 LLM 이 검토해 take / reduce / skip 과 근거를 JSON 으로 돌려준다.
  AI 는 코드가 낸 신호를 **거르거나 줄일 수만** 있다 — 신호를 만들지도, 크기를 키우지도, 손절·청산을
  건드리지도 않는다. 손절 주문·청산 집행·사이징 상한·킬스위치는 종전대로 코드가 정한다.
  청산 검토(judge_exits)도 같은 원칙 아래 있다 — **어떤 경로로도 주문에 닿지 않는 기록**이고, 평가는
  ai_judge_report.py 가 '그 시점 종가 청산 가상 수익 vs 실제 방식D 결과' 로 한다.

모드 (MODE)
  "shadow"  판단을 기록만 한다. 주문은 종전과 바이트 단위로 같다. (현행 — 2026-10-23 사용자 결정)
  "veto"    live 사이징에 size_mult 를 곱한다(skip 이면 0 → 실주문 안 냄, 페이퍼 행은 그대로 둬 결과를 추적).
  전환은 registry `ai_judge_prereg_2026_10_23` 의 사전 등록 기준을 채운 뒤 사용자 결정.
  청산 검토에는 veto 가 없다 — 청산 집행은 코드(CLAUDE.md 원칙 ②). 실효를 주려면 원칙 개정 + 사용자 결정.

왜 기록부터 하나
  이 레포에서 AI(주관) 판단이 영점을 이긴 기록이 아직 없다 — 엘리엇 채점 장부 누적 브리어 0.243 vs 무작위
  보행 0.205. 개선인지 악화인지 모르는 상태라 **몇 주 뒤 숫자로 볼 수 있게** 모든 판단을 저장한다
  (prompt_version·prompt_hash·model·응답). 그림자에서는 모든 신호가 종전대로 진입하므로 take/skip 두 집단의
  실제 방식D 결과를 그대로 비교할 수 있다 — 가상 추적이 필요 없다.

재현성
  입력은 그 봉까지의 수치뿐(인과), 프롬프트 해시·버전·모델 저장. **샘플링 파라미터(temperature/top_p/top_k)는 보내지
  않는다** — Claude 5.5 계열은 기본값 외 값에 400 을 돌려주고 API 버전 2026-10-21 부터는 어떤 값이든 400 이다.
  실측: 2026-10-23~26 실거래 호출은 전부 temperature=0 때문에 http_400 이었다(10/26 00:00Z 로그 `판단 실패(http_400)`).
  그래서 '같은 입력 → 같은 답' 은 보장되지 않고, 대신 model·prompt_version·features 를 행마다 기록해 추적한다.
  API 키가 없거나 호출이 실패하면 error(HTTP 응답의 type·message 포함) 를 기록하고 **거래 경로는 아무 영향도 받지
  않는다**(예외를 밖으로 내지 않는다).
"""
import hashlib
import json
import math
import os
import time
import urllib.error
import urllib.request

MODE = "shadow"                    # "shadow" | "veto"  — 전환은 사용자 결정(registry 사전 등록 참조)
MODEL = "claude-opus-5-5"             # 2026-10-26 전환(종전 claude-sonnet-5-5). 행마다 model 을 기록하므로 표본은 (model, prompt_version) 로 갈린다.
EFFORT = "low"                        # 짧은 JSON 분류 — 추론 깊이는 effort 로만 조절(thinking 은 이 모델에서 항상 켜져 있다)
# 표본 집계 키. 프롬프트·특성·모델 구성을 바꾸면 올린다 — 사전 등록 'no_post_hoc' 가 이 값으로 표본을 가른다.
# (prompt_hash 는 특성값까지 해시해 신호마다 다르므로 집계 키가 될 수 없다 — 2026-10-26 정정)
PROMPT_VERSION = "entry_v2_2026_10_26"
EXIT_PROMPT_VERSION = "exit_v1_2026_10_26"
MAX_CALLS_PER_RUN = 25             # 한 실행에서 판단할 신호 상한(비용·지연 가드). 넘치면 뒤쪽은 미판단으로 기록.
MAX_EXIT_POS = 20                  # 청산 검토 배치 한 번에 넣는 포지션 상한(MAX_LIVE_POS 13 + 페이퍼 여유)
TIMEOUT_S = 25
EXIT_TIMEOUT_S = 60                # 배치 응답이 길다
ENTRY_MAX_TOKENS = 4000            # 생각 토큰 포함 상한(실사용은 수백 토큰 — 비용은 usage 로 추적)
API_URL = "https://api.anthropic.com/v1/messages"
TABLE = "ai_judgments"
DECISIONS = ("take", "reduce", "skip")
EXIT_DECISIONS = ("hold", "exit")
SINCE = "2026-10-23"
EXIT_SINCE = "2026-10-26"
TF_MS = {"15m": 900_000, "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000, "1w": 604_800_000}

SYSTEM = (
    "You are a risk reviewer for a systematic crypto perpetual-futures desk. A deterministic rule has "
    "already produced an entry signal; your only job is to decide whether to TAKE it as-is, REDUCE its size, "
    "or SKIP it, using only the numeric market context provided. You cannot create trades, raise size, or "
    "change the stop. Be skeptical: the desk's measured per-trade edge is thin (+0.2~1.6%) and most signals "
    "lose to the -8% stop. Fields: ret_*/ma*_dist/d1_* are fractions as of the signal bar close; d1_* is the "
    "closed daily-bar context for intraday signals; book_* is the current portfolio (live positions, max slots, "
    "direction mix, whether this symbol is already held); stop_atr is the stop distance in ATR units; "
    "pattern_recent_*/sym_recent_* are the desk's own recent realized results for this pattern/symbol. "
    "Respond with ONE JSON object and nothing else: "
    '{"decision": "take"|"reduce"|"skip", "size_mult": number in [0,1], "confidence": number in [0,1], '
    '"reasons": [up to 3 short strings]}. For take use size_mult 1.0; for skip use 0.0.'
)

SYSTEM_EXIT = (
    "You are a risk reviewer for a systematic crypto perpetual-futures desk. The desk holds the open positions "
    "listed below under a fixed exit rule (stop at -8% from entry on the bar low, opposite-pattern signal, regime "
    "label switch, or 30-bar max hold exited at the bar open). For EACH position decide HOLD (let the rule run) "
    "or EXIT (close now at the mark price). This review is recorded and later scored against what the rule "
    "actually did; it places no orders and cannot move the stop. Use only the numeric context. Be skeptical: in "
    "this desk's backtests every early-exit variant that cut winners lost to the plain rule; the only exits worth "
    "calling are those that avoid a likely -8% stop. Fields are fractions as of the mark bar close: unreal_ret "
    "(open P&L), stop_dist (distance to the stop), mfe/mae (best/worst excursion since entry), bars_held/bars_left. "
    'Respond with ONE JSON object and nothing else: {"reviews": [{"id": "p1", "decision": "hold"|"exit", '
    '"confidence": number in [0,1], "reasons": [up to 2 short strings]}, ...]} covering every id exactly once.'
)


def available():
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


# ── 특성(그 봉까지만 — 인과) ──────────────────────────────────────────────────
def _ret(rows, ei, k):
    if ei - k < 0 or rows[ei - k]["c"] <= 0:
        return None
    return round(rows[ei]["c"] / rows[ei - k]["c"] - 1.0, 5)


def _atr(rows, ei, n=14):
    if ei < n:
        return None
    trs = []
    for j in range(ei - n + 1, ei + 1):
        h, l, pc = rows[j]["h"], rows[j]["l"], rows[j - 1]["c"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / n


def _rsi(rows, ei, n=14):
    if ei < n:
        return None
    g = l = 0.0
    for j in range(ei - n + 1, ei + 1):
        d = rows[j]["c"] - rows[j - 1]["c"]
        g += max(d, 0.0); l += max(-d, 0.0)
    if l == 0:
        return 100.0
    return round(100.0 - 100.0 / (1.0 + g / l), 2)


def _ma_dist(rows, ei, n):
    if ei + 1 < n:
        return None
    ma = sum(r["c"] for r in rows[ei - n + 1:ei + 1]) / n
    return round(rows[ei]["c"] / ma - 1.0, 5) if ma else None


def _align(rows_b, ts):
    """다른 종목 봉에서 ts 이하 마지막 봉 인덱스(없으면 None). 미래 봉은 절대 안 본다."""
    if not rows_b or ts is None:
        return None
    k = None
    for i, r in enumerate(rows_b):
        if r.get("ts") is None or r["ts"] > ts:
            break
        k = i
    return k


def _align_closed(rows_b, close_ts, bar_ms):
    """
    상위 TF 봉 중 **close_ts 시점에 이미 닫힌** 마지막 봉 인덱스. 봉 ts 는 시가 시각이므로
    ts + bar_ms <= close_ts 인 봉만 쓴다 — 4h/1h 신호가 형성 중인 일봉을 보면 룩어헤드다.
    """
    if not rows_b or close_ts is None:
        return None
    k = None
    for i, r in enumerate(rows_b):
        if r.get("ts") is None or r["ts"] + bar_ms > close_ts:
            break
        k = i
    return k


def _recent(trades, key, val, n, method="D"):
    """결과를 아는 과거 방식D 거래만. (n, mean, win) — 현재 신호와는 무관."""
    tr = [t for t in (trades or [])
          if t.get(key) == val and t.get("method") == method and t.get("ret") is not None][-n:]
    if not tr:
        return 0, None, None
    rets = [float(t["ret"]) for t in tr]
    return len(tr), round(sum(rets) / len(rets), 5), round(sum(1 for x in rets if x > 0) / len(rets), 3)


def _bar_state(rows, i):
    """봉 i 기준 상태 특성(진입 신호봉·청산 검토 마크봉 공용). rows[:i+1] 만 본다."""
    r = rows[i]
    px = r["c"]
    atr = _atr(rows, i)
    lo60 = min(x["l"] for x in rows[max(0, i - 59):i + 1])
    hi60 = max(x["h"] for x in rows[max(0, i - 59):i + 1])
    vol20 = [x["v"] for x in rows[max(0, i - 19):i + 1]]
    vol60 = [x["v"] for x in rows[max(0, i - 59):i + 1]]
    v20 = sum(vol20) / len(vol20) if vol20 else 0.0
    v60 = sum(vol60) / len(vol60) if vol60 else 0.0
    return atr, {
        "bar_date": r.get("date"),
        "ret_1": _ret(rows, i, 1), "ret_5": _ret(rows, i, 5), "ret_20": _ret(rows, i, 20), "ret_60": _ret(rows, i, 60),
        "atr14_pct": round(atr / px, 5) if atr and px else None,
        "bar_range_pct": round((r["h"] - r["l"]) / px, 5) if px else None,
        "body_pct": round((r["c"] - r["o"]) / px, 5) if px else None,
        "pos_in_60": round((px - lo60) / (hi60 - lo60), 4) if hi60 > lo60 else None,
        "vol_last_over_20": round(r["v"] / v20, 3) if v20 else None,
        "vol_20_over_60": round(v20 / v60, 3) if v60 else None,
        "rsi14": _rsi(rows, i),
        "ma20_dist": _ma_dist(rows, i, 20), "ma50_dist": _ma_dist(rows, i, 50), "ma200_dist": _ma_dist(rows, i, 200),
    }


def features(rows, ei, sig, ctx=None):
    """
    신호 하나의 수치 특성. rows[:ei+1] 만 쓴다(테스트가 인과성 고정). ctx:
      rows_of(sym, tf) · regime · avg_cap · trades(최근 같은 패턴·종목 실거래 성과) ·
      book(현재 장부 행 목록)/max_pos(슬롯 상한) — v2(2026-10-26) 포트폴리오 맥락
    """
    ctx = ctx or {}
    r = rows[ei]
    entry = r["c"]
    tf = sig.get("tf", "1d")
    atr, state = _bar_state(rows, ei)
    f = {
        "pattern": sig.get("pattern"), "direction": sig.get("direction"), "tf": tf,
        "grade": sig.get("ensemble_grade"), "regime": ctx.get("regime") or sig.get("regime"),
        "avg_alt_cap": ctx.get("avg_cap"),
        "bar_hour_utc": (int(r["ts"] // 3_600_000) % 24) if r.get("ts") is not None else None,
        "stop_pct": (round(abs(entry - sig["stop"]) / entry, 5) if sig.get("stop") and entry else None),
        "stop_atr": (round(abs(entry - sig["stop"]) / atr, 3) if sig.get("stop") and atr else None),
    }
    f.update(state)
    rows_of = ctx.get("rows_of")
    if rows_of:
        for ref in ("BTC", "ETH"):
            try:
                rb = rows_of(ref, tf)
            except Exception:
                rb = None
            k = _align(rb, r.get("ts")) if rb else None
            f[f"{ref.lower()}_ret_5"] = _ret(rb, k, 5) if k is not None else None
            f[f"{ref.lower()}_ret_20"] = _ret(rb, k, 20) if k is not None else None
        # 상위 TF 맥락(v2): 하위 TF 신호에 **신호봉 마감 시점에 닫힌** 일봉만 붙인다.
        if tf in TF_MS and tf not in ("1d", "1w") and r.get("ts") is not None:
            try:
                rd = rows_of(sig.get("symbol"), "1d")
            except Exception:
                rd = None
            k = _align_closed(rd, r["ts"] + TF_MS[tf], TF_MS["1d"]) if rd else None
            f["d1_ret_5"] = _ret(rd, k, 5) if k is not None else None
            f["d1_ret_20"] = _ret(rd, k, 20) if k is not None else None
            f["d1_rsi14"] = _rsi(rd, k) if k is not None else None
            f["d1_ma50_dist"] = _ma_dist(rd, k, 50) if k is not None else None
            f["d1_ma200_dist"] = _ma_dist(rd, k, 200) if k is not None else None
    # 같은 패턴·같은 종목의 최근 실거래 결과(방식D) — 결과를 아는 과거 거래만, 현재 신호와는 무관.
    f["pattern_recent_n"], f["pattern_recent_mean"], f["pattern_recent_win"] = _recent(
        ctx.get("trades"), "pattern", sig.get("pattern"), 20)
    f["sym_recent_n"], f["sym_recent_mean"], _ = _recent(ctx.get("trades"), "symbol", sig.get("symbol"), 5)
    # 포트폴리오 맥락(v2) — 이 신호를 받을 때의 장부. live 활성 행(실포지션)만 슬롯을 먹는다.
    book = ctx.get("book")
    if book is not None:
        act = [p for p in book if p.get("live_mode") and not p.get("d_closed")]
        f["book_rows"] = len(book)
        f["book_live"] = len(act)
        f["book_max"] = ctx.get("max_pos")
        f["book_long"] = sum(1 for p in act if p.get("direction") == "long")
        f["book_short"] = sum(1 for p in act if p.get("direction") == "short")
        f["book_same_pattern"] = sum(1 for p in act if p.get("pattern") == sig.get("pattern"))
        f["book_symbol_held"] = any(p.get("symbol") == sig.get("symbol") and not p.get("d_closed") for p in book)
    return f


def prompt_text(feat):
    return "Signal context (all values known at the signal bar close; returns are fractions):\n" + \
        json.dumps(feat, ensure_ascii=False, sort_keys=True)


def prompt_hash(feat):
    return hashlib.sha256((SYSTEM + "\n" + prompt_text(feat)).encode("utf-8")).hexdigest()[:16]


# ── 호출·파싱 ─────────────────────────────────────────────────────────────────
def _post(body, timeout=None):
    """실제 HTTP. 테스트는 이 함수를 바꿔 끼운다."""
    req = urllib.request.Request(
        API_URL, data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"content-type": "application/json", "x-api-key": os.environ["ANTHROPIC_API_KEY"],
                 "anthropic-version": "2023-06-01"})
    with urllib.request.urlopen(req, timeout=timeout or TIMEOUT_S) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _body(system, user_text, max_tokens):
    """
    Messages 요청 본문. **temperature/top_p/top_k 를 넣지 않는다** — 2026-10-23~26 의 실거래 호출이 전부
    temperature=0 으로 http_400 이었다(Claude 5.5 계열: 기본값 외 샘플링 값 400 / API 2026-10-21: 어떤 값이든 400).
    thinking 은 이 모델에서 항상 켜져 있어 보내지 않고, 깊이는 output_config.effort 로만 조절한다.
    max_tokens 는 생각 토큰까지 포함하므로 짧은 JSON 답이라도 넉넉히 준다(부족하면 stop_reason=max_tokens 로 빈 답).
    """
    return {"model": MODEL, "max_tokens": max_tokens, "system": system,
            "output_config": {"effort": EFFORT},
            "messages": [{"role": "user", "content": user_text}]}


def _http_detail(e):
    """HTTPError 응답 본문의 error.type / error.message — 진단용(종전엔 코드만 남아 원인을 못 봤다)."""
    try:
        j = json.loads(e.read().decode("utf-8", "replace"))
        er = j.get("error") or {}
        return f":{er.get('type', '')}:{str(er.get('message', ''))[:120]}"
    except Exception:
        return ""


def _call_raw(system, user_text, max_tokens, timeout=None):
    """(text, error, latency_ms, usage). 키 없음·HTTP 오류·빈 답은 (None, err, ms, usage)."""
    if not available():
        return None, "no_key", 0, {}
    body = _body(system, user_text, max_tokens)
    t0 = time.time()
    try:
        out = _post(body) if timeout is None else _post(body, timeout)
    except urllib.error.HTTPError as e:
        return None, f"http_{e.code}{_http_detail(e)}", int((time.time() - t0) * 1000), {}
    except Exception as e:
        return None, f"err_{type(e).__name__}", int((time.time() - t0) * 1000), {}
    ms = int((time.time() - t0) * 1000)
    text = "".join(blk.get("text", "") for blk in (out.get("content") or []) if blk.get("type") == "text")
    usage = out.get("usage") or {}
    usage = usage if isinstance(usage, dict) else {}
    if not text:
        sr = out.get("stop_reason")
        if sr == "refusal":          # 안전 분류기 거절 — 카테고리를 남긴다(stop_details)
            cat = (out.get("stop_details") or {}).get("category") or "?"
            return None, f"refusal:{cat}", ms, usage
        return None, f"empty_{sr or 'response'}", ms, usage
    return text, None, ms, usage


def _json_obj(text):
    """응답 텍스트에서 첫 JSON 객체(dict)를 꺼낸다. 코드펜스·앞뒤 잡문 허용. 실패 None."""
    if not text:
        return None
    s = text.strip()
    if "```" in s:
        s = s.split("```", 2)[1] if s.count("```") >= 2 else s.replace("```", "")
        if s.startswith("json"):
            s = s[4:]
    a, b = s.find("{"), s.rfind("}")
    if a < 0 or b <= a:
        return None
    try:
        d = json.loads(s[a:b + 1])
    except Exception:
        return None
    return d if isinstance(d, dict) else None


def _conf(d):
    try:
        c = float(d.get("confidence", 0.5))
    except Exception:
        c = 0.5
    return round(min(1.0, max(0.0, c)) if math.isfinite(c) else 0.5, 3)


def _reasons(d, n=3):
    reasons = d.get("reasons") or []
    if not isinstance(reasons, list):
        reasons = [str(reasons)]
    return [str(x)[:160] for x in reasons][:n]


def parse(text):
    """모델 응답 → 검증된 dict 또는 None. 코드펜스·앞뒤 잡문 허용, 범위 밖 값은 클램프, 상한 1.0 고정."""
    d = _json_obj(text)
    if d is None:
        return None
    dec = str(d.get("decision", "")).lower()
    if dec not in DECISIONS:
        return None
    try:
        m = float(d.get("size_mult", 1.0 if dec == "take" else 0.0))
    except Exception:
        m = 1.0 if dec == "take" else 0.0
    if not math.isfinite(m):
        m = 0.0
    m = min(1.0, max(0.0, m))          # AI 는 키울 수 없다 — 상한 1.0
    if dec == "take":
        m = 1.0
    elif dec == "skip":
        m = 0.0
    elif m >= 1.0:                      # reduce 인데 1.0 이면 사실상 take
        m = 1.0
    return {"decision": dec, "size_mult": round(m, 3), "confidence": _conf(d), "reasons": _reasons(d)}


def call(feat):
    """(parsed, error, latency_ms, raw_text). 키 없음·HTTP 오류·파싱 실패 전부 (None, err, ...) 로 돌려준다."""
    text, err, ms, _usage = _call_raw(SYSTEM, prompt_text(feat), ENTRY_MAX_TOKENS)
    if err:
        return None, err, ms, None
    parsed = parse(text)
    return parsed, (None if parsed else "parse_fail"), ms, text[:600]


def judge(rows, ei, sig, ctx=None, mode=None):
    """신호 하나를 판단해 기록 행을 돌려준다. 절대 예외를 내지 않는다(거래 경로 보호)."""
    mode = mode or MODE
    rec = {"judged_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "kind": "entry",
           "symbol": sig.get("symbol"), "pattern": sig.get("pattern"), "direction": sig.get("direction"),
           "tf": sig.get("tf", "1d"), "entry_date": sig.get("date"),
           "entry_ts": sig.get("ts") or (rows[ei].get("ts") if 0 <= ei < len(rows) else None),
           "entry_px": (rows[ei].get("c") if 0 <= ei < len(rows) else None),
           "mode": mode, "model": MODEL, "prompt_version": PROMPT_VERSION, "prompt_hash": None,
           "decision": None, "size_mult": None, "confidence": None, "reasons": None,
           "latency_ms": None, "tokens_in": None, "tokens_out": None, "error": None, "features": None}
    try:
        feat = features(rows, ei, sig, ctx)
        rec["features"] = json.dumps(feat, ensure_ascii=False, sort_keys=True)
        rec["prompt_hash"] = prompt_hash(feat)
        text, err, ms, usage = _call_raw(SYSTEM, prompt_text(feat), ENTRY_MAX_TOKENS)
        rec["latency_ms"] = ms
        rec["tokens_in"], rec["tokens_out"] = usage.get("input_tokens"), usage.get("output_tokens")
        parsed = parse(text) if not err else None
        rec["error"] = err or (None if parsed else "parse_fail")
        if parsed:
            rec.update(decision=parsed["decision"], size_mult=parsed["size_mult"],
                       confidence=parsed["confidence"], reasons=json.dumps(parsed["reasons"], ensure_ascii=False))
    except Exception as e:                      # 특성 계산 등 어떤 오류도 거래 경로로 새지 않게
        rec["error"] = f"judge_{type(e).__name__}"
    return rec


def apply(rec, mode=None):
    """
    실주문 사이징에 곱할 배율. shadow → 항상 1.0 (주문 무변경). veto → skip 0.0 / reduce m / take 1.0.
    판단이 없거나(오류·미판단) 결과를 못 믿으면 1.0 — AI 장애가 거래를 막지 않는다(fail-open 은 여기서만:
    AI 는 보조 필터이고 안전장치는 코드가 따로 가진다).
    """
    mode = mode or MODE
    if mode != "veto" or not rec or rec.get("decision") is None:
        return 1.0
    return float(min(1.0, max(0.0, rec.get("size_mult") or 0.0)))


# ── 청산 검토(그림자, 2026-10-26) ─────────────────────────────────────────────
# 기록 전용. 주문·청산·포지션 수명 어디에도 연결되지 않는다 — 평가는 ai_judge_report.py.
def exit_features(rows, ei, mi, pos, ctx=None):
    """
    열린 포지션 하나의 '지금 상태'. rows[:mi+1] 만 쓴다(mi = 마크봉, 보통 마지막 행). ctx:
      rows_of · regmap(날짜→레짐) · trades · max_hold(방식D 보유 상한)
    """
    ctx = ctx or {}
    direction = pos.get("direction")
    sgn = 1.0 if direction == "long" else -1.0
    entry = float(pos.get("entry_price") or rows[ei]["c"])
    mark = rows[mi]["c"]
    stop = pos.get("stop")
    max_hold = int(ctx.get("max_hold") or 30)
    atr, state = _bar_state(rows, mi)
    path = rows[ei + 1:mi + 1]
    mfe = max((sgn * (x["h"] if sgn > 0 else x["l"]) / entry - sgn) for x in path) if path else 0.0
    mae = min((sgn * (x["l"] if sgn > 0 else x["h"]) / entry - sgn) for x in path) if path else 0.0
    regmap = ctx.get("regmap") or {}
    reg_now = regmap.get(rows[mi]["date"])
    f = {
        "pattern": pos.get("pattern"), "direction": direction, "tf": pos.get("tf", "1d"),
        "entry_date": pos.get("entry_date"), "live": bool(pos.get("live_mode")),
        "bars_held": mi - ei, "bars_left": max(0, max_hold - (mi - ei)),
        "unreal_ret": round(sgn * (mark / entry - 1.0), 5) if entry else None,
        "stop_dist": (round(sgn * (mark - float(stop)) / mark, 5) if stop and mark else None),
        "mfe": round(mfe, 5), "mae": round(mae, 5),
        "entry_regime": pos.get("entry_regime"), "regime_now": reg_now,
        "regime_changed": (bool(reg_now != pos.get("entry_regime")) if reg_now and pos.get("entry_regime") else None),
    }
    f.update(state)
    rows_of = ctx.get("rows_of")
    if rows_of:
        try:
            rb = rows_of("BTC", pos.get("tf", "1d"))
        except Exception:
            rb = None
        k = _align(rb, rows[mi].get("ts")) if rb else None
        f["btc_ret_5"] = _ret(rb, k, 5) if k is not None else None
    f["pattern_recent_n"], f["pattern_recent_mean"], f["pattern_recent_win"] = _recent(
        ctx.get("trades"), "pattern", pos.get("pattern"), 20)
    return f


def exit_prompt_text(items_feat):
    """items_feat: [(id, feat)] → 배치 프롬프트. id 순서는 호출자가 정한다(p1, p2, …)."""
    return ("Open positions (all values as of the mark bar close; returns are fractions):\n" +
            json.dumps({"positions": [dict(feat, id=pid) for pid, feat in items_feat]},
                       ensure_ascii=False, sort_keys=True))


def parse_batch(text, ids):
    """배치 응답 → {id: {decision, confidence, reasons}} (검증된 것만). 없는 id 는 빠진다."""
    d = _json_obj(text)
    if d is None:
        return {}
    revs = d.get("reviews")
    if revs is None and len(d) == 1 and isinstance(next(iter(d.values())), list):
        revs = next(iter(d.values()))
    if not isinstance(revs, list):
        return {}
    out, want = {}, set(ids)
    for rv in revs:
        if not isinstance(rv, dict):
            continue
        pid = str(rv.get("id", "")).strip()
        dec = str(rv.get("decision", "")).lower().strip()
        if pid not in want or pid in out or dec not in EXIT_DECISIONS:
            continue
        out[pid] = {"decision": dec, "confidence": _conf(rv), "reasons": _reasons(rv, 2)}
    return out


def judge_exits(items, ctx=None, mode=None):
    """
    열린 포지션 묶음을 **한 번의 호출**로 hold/exit 판정해 포지션마다 기록 행을 돌려준다.
    items: [{"pos": pos, "rows": rows, "ei": 진입봉, "mi": 마크봉}]. 절대 예외를 내지 않는다.
    기록만 한다 — 반환값을 주문·청산에 쓰는 코드는 없다(test_ai_judge 가 소스로 고정).
    """
    mode = mode or MODE
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    recs, feats = [], []
    for n, it in enumerate(items):
        pos, rows, ei, mi = it["pos"], it["rows"], it["ei"], it["mi"]
        sgn = 1.0 if pos.get("direction") == "long" else -1.0
        rec = {"judged_at": now, "kind": "exit",
               "symbol": pos.get("symbol"), "pattern": pos.get("pattern"), "direction": pos.get("direction"),
               "tf": pos.get("tf", "1d"), "entry_date": pos.get("entry_date"), "entry_ts": pos.get("entry_ts"),
               "entry_px": pos.get("entry_price"), "mark_ts": None, "mark_px": None, "unreal_ret": None,
               "bars_held": None, "live_mode": bool(pos.get("live_mode")),
               "mode": mode, "model": MODEL, "prompt_version": EXIT_PROMPT_VERSION, "prompt_hash": None,
               "decision": None, "size_mult": None, "confidence": None, "reasons": None,
               "latency_ms": None, "tokens_in": None, "tokens_out": None, "error": None, "features": None,
               "code_action": "open"}
        try:
            mark = rows[mi]
            entry = float(pos.get("entry_price") or rows[ei]["c"])
            rec["mark_ts"], rec["mark_px"] = mark.get("ts"), mark["c"]
            rec["unreal_ret"] = round(sgn * (mark["c"] / entry - 1.0), 5) if entry else None
            rec["bars_held"] = mi - ei
            feat = exit_features(rows, ei, mi, pos, ctx)
            rec["features"] = json.dumps(feat, ensure_ascii=False, sort_keys=True)
            if n >= MAX_EXIT_POS:
                rec["error"] = "max_pos"
            else:
                feats.append((f"p{n + 1}", feat))
        except Exception as e:
            rec["error"] = f"judge_{type(e).__name__}"
        recs.append(rec)
    if not feats:
        return recs
    try:
        user = exit_prompt_text(feats)
        h = hashlib.sha256((SYSTEM_EXIT + "\n" + user).encode("utf-8")).hexdigest()[:16]
        text, err, ms, usage = _call_raw(SYSTEM_EXIT, user, min(16000, 1500 + 300 * len(feats)), EXIT_TIMEOUT_S)
        answers = parse_batch(text, [pid for pid, _ in feats]) if not err else {}
        by_id = {pid: i for i, (pid, _) in enumerate(feats)}
        pending = [r for r in recs if r["error"] is None]
        for pid, i in by_id.items():
            r = pending[i]
            r["prompt_hash"], r["latency_ms"] = h, ms
            r["tokens_in"], r["tokens_out"] = usage.get("input_tokens"), usage.get("output_tokens")
            a = answers.get(pid)
            if err:
                r["error"] = err
            elif not a:
                r["error"] = "parse_fail" if not answers else "no_answer"
            else:
                r.update(decision=a["decision"], confidence=a["confidence"],
                         reasons=json.dumps(a["reasons"], ensure_ascii=False))
    except Exception as e:
        for r in recs:
            if r["error"] is None:
                r["error"] = f"judge_{type(e).__name__}"
    return recs


# ── 기록·요약 ─────────────────────────────────────────────────────────────────
def push_db(records):
    """ai_judgments 테이블에 기록(베스트에포트). 컬럼 미존재는 insert_tolerant 가 제외."""
    if not records:
        return 0
    try:
        import supabase_client as sc
        if not sc.available():
            return 0
        cli = sc.get_client("service")
        # entry/exit 행은 키 집합이 다르다 — PostgREST 벌크 insert 는 객체 키가 같아야 하므로 합집합으로 맞추고 빈 칸은 None.
        keys = sorted({k for r in records for k in r})
        rows = [{k: r.get(k) for k in keys} for r in records]
        # max_drop=32: 확장 컬럼 10개가 아직 없는 DB(사용자가 SQL 재실행 전)에서도 기록이 들어가야 한다.
        # 기본 8 이면 10개째에서 RuntimeError 로 전부 유실된다(2026-10-26 04:00Z 실측 — 판단 7행 DB+0).
        inserted, dropped = sc.insert_tolerant(cli, TABLE, rows, max_drop=32)
        if dropped:
            print(f"  [ai] {TABLE} 스키마 미존재 컬럼 제외 {len(dropped)}개: {dropped} — supabase_schema_ai_judge.sql 재실행 필요")
        return len(inserted)
    except Exception as e:
        print(f"  [ai] {TABLE} 기록 실패(무시): {str(e)[:300]}")
        return 0


def summary_line(records):
    recs = [r for r in records if r.get("kind", "entry") == "entry"]
    n = len(recs)
    if not n:
        return "[ai] 판단 0건"
    dec = {}
    err = 0
    for r in recs:
        if r.get("decision"):
            dec[r["decision"]] = dec.get(r["decision"], 0) + 1
        else:
            err += 1
    parts = " ".join(f"{k} {v}" for k, v in sorted(dec.items()))
    return f"[ai] {MODE} 판단 {n}건 — {parts}" + (f" | 미판단/오류 {err}" if err else "") + f" | {MODEL}"


def exit_summary_line(records):
    recs = [r for r in records if r.get("kind") == "exit"]
    n = len(recs)
    if not n:
        return "[ai-exit] 청산 검토 0건"
    dec = {}
    err = 0
    for r in recs:
        if r.get("decision"):
            dec[r["decision"]] = dec.get(r["decision"], 0) + 1
        else:
            err += 1
    parts = " ".join(f"{k} {v}" for k, v in sorted(dec.items()))
    ex = [f"{r['symbol']}({r['pattern']})" for r in recs if r.get("decision") == "exit"]
    return (f"[ai-exit] 그림자 청산 검토 {n}건 — {parts}" + (f" | 미판단/오류 {err}" if err else "")
            + (f" | exit 제안: {', '.join(ex)}" if ex else "") + " [기록만 — 주문 무변경]")
