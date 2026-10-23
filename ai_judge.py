"""
ai_judge.py — 신호별 AI 판단 레이어 (2026-10-23, 사용자 결정 "매매 판단을 기존 거에 AI 판단으로 개선…
클로드 md 를 수정해서라도 이번 판단 규칙은 개선한다" → 그림자 기록 먼저 / 차트 수치만 / 전 배포 패턴).

무엇을 하나
  기존 디텍터가 낸 신호 하나하나를 LLM 이 검토해 take / reduce / skip 과 근거를 JSON 으로 돌려준다.
  AI 는 코드가 낸 신호를 **거르거나 줄일 수만** 있다 — 신호를 만들지도, 크기를 키우지도, 손절·청산을
  건드리지도 않는다. 손절 주문·청산 집행·사이징 상한·킬스위치는 종전대로 코드가 정한다.

모드 (MODE)
  "shadow"  판단을 기록만 한다. 주문은 종전과 바이트 단위로 같다. (현행 — 2026-10-23 사용자 결정)
  "veto"    live 사이징에 size_mult 를 곱한다(skip 이면 0 → 실주문 안 냄, 페이퍼 행은 그대로 둬 결과를 추적).
  전환은 registry `ai_judge_prereg_2026_10_23` 의 사전 등록 기준을 채운 뒤 사용자 결정.

왜 기록부터 하나
  이 레포에서 AI(주관) 판단이 영점을 이긴 기록이 아직 없다 — 엘리엇 채점 장부 누적 브리어 0.243 vs 무작위
  보행 0.205. 개선인지 악화인지 모르는 상태라 **몇 주 뒤 숫자로 볼 수 있게** 모든 판단을 저장한다
  (prompt_hash·model·응답). 그림자에서는 모든 신호가 종전대로 진입하므로 take/skip 두 집단의 실제 방식D
  결과를 그대로 비교할 수 있다 — 가상 추적이 필요 없다.

재현성
  온도 0, 입력은 그 봉까지의 수치뿐(인과), 프롬프트 해시 저장. 단 모델 자체가 바뀌면 같은 입력에 다른 답이
  나올 수 있다 — 그래서 model 을 함께 기록한다. API 키가 없거나 호출이 실패하면 error 를 기록하고
  **거래 경로는 아무 영향도 받지 않는다**(예외를 밖으로 내지 않는다).
"""
import hashlib
import json
import math
import os
import time
import urllib.error
import urllib.request

MODE = "shadow"                    # "shadow" | "veto"  — 전환은 사용자 결정(registry 사전 등록 참조)
MODEL = "claude-sonnet-5-5"
MAX_CALLS_PER_RUN = 25             # 한 실행에서 판단할 신호 상한(비용·지연 가드). 넘치면 뒤쪽은 미판단으로 기록.
TIMEOUT_S = 25
API_URL = "https://api.anthropic.com/v1/messages"
TABLE = "ai_judgments"
DECISIONS = ("take", "reduce", "skip")
SINCE = "2026-10-23"

SYSTEM = (
    "You are a risk reviewer for a systematic crypto perpetual-futures desk. A deterministic rule has "
    "already produced an entry signal; your only job is to decide whether to TAKE it as-is, REDUCE its size, "
    "or SKIP it, using only the numeric market context provided. You cannot create trades, raise size, or "
    "change the stop. Be skeptical: the desk's measured per-trade edge is thin (+0.2~1.6%) and most signals "
    "lose to the -8% stop. Respond with ONE JSON object and nothing else: "
    '{"decision": "take"|"reduce"|"skip", "size_mult": number in [0,1], "confidence": number in [0,1], '
    '"reasons": [up to 3 short strings]}. For take use size_mult 1.0; for skip use 0.0.'
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


def features(rows, ei, sig, ctx=None):
    """
    신호 하나의 수치 특성. rows[:ei+1] 만 쓴다(테스트가 인과성 고정). ctx:
      rows_of(sym, tf) · regime · avg_cap · trades(최근 같은 패턴 실거래 성과) · equity
    """
    ctx = ctx or {}
    r = rows[ei]
    entry = r["c"]
    atr = _atr(rows, ei)
    lo60 = min(x["l"] for x in rows[max(0, ei - 59):ei + 1])
    hi60 = max(x["h"] for x in rows[max(0, ei - 59):ei + 1])
    vol20 = [x["v"] for x in rows[max(0, ei - 19):ei + 1]]
    vol60 = [x["v"] for x in rows[max(0, ei - 59):ei + 1]]
    v20 = sum(vol20) / len(vol20) if vol20 else 0.0
    v60 = sum(vol60) / len(vol60) if vol60 else 0.0
    f = {
        "pattern": sig.get("pattern"), "direction": sig.get("direction"), "tf": sig.get("tf", "1d"),
        "grade": sig.get("ensemble_grade"), "regime": ctx.get("regime") or sig.get("regime"),
        "avg_alt_cap": ctx.get("avg_cap"),
        "bar_date": r.get("date"),
        "ret_1": _ret(rows, ei, 1), "ret_5": _ret(rows, ei, 5), "ret_20": _ret(rows, ei, 20), "ret_60": _ret(rows, ei, 60),
        "atr14_pct": round(atr / entry, 5) if atr and entry else None,
        "bar_range_pct": round((r["h"] - r["l"]) / entry, 5) if entry else None,
        "body_pct": round((r["c"] - r["o"]) / entry, 5) if entry else None,
        "pos_in_60": round((entry - lo60) / (hi60 - lo60), 4) if hi60 > lo60 else None,
        "vol_last_over_20": round(r["v"] / v20, 3) if v20 else None,
        "vol_20_over_60": round(v20 / v60, 3) if v60 else None,
        "rsi14": _rsi(rows, ei),
        "ma20_dist": _ma_dist(rows, ei, 20), "ma50_dist": _ma_dist(rows, ei, 50), "ma200_dist": _ma_dist(rows, ei, 200),
        "stop_pct": (round(abs(entry - sig["stop"]) / entry, 5) if sig.get("stop") and entry else None),
    }
    rows_of = ctx.get("rows_of")
    if rows_of:
        for ref in ("BTC", "ETH"):
            try:
                rb = rows_of(ref, sig.get("tf", "1d"))
            except Exception:
                rb = None
            k = _align(rb, r.get("ts")) if rb else None
            f[f"{ref.lower()}_ret_5"] = _ret(rb, k, 5) if k is not None else None
            f[f"{ref.lower()}_ret_20"] = _ret(rb, k, 20) if k is not None else None
    # 같은 패턴의 최근 실거래 결과(방식D) — 결과를 아는 과거 거래만, 현재 신호와는 무관.
    tr = [t for t in (ctx.get("trades") or [])
          if t.get("pattern") == sig.get("pattern") and t.get("method") == "D" and t.get("ret") is not None]
    tr = tr[-20:]
    f["pattern_recent_n"] = len(tr)
    f["pattern_recent_mean"] = round(sum(float(t["ret"]) for t in tr) / len(tr), 5) if tr else None
    f["pattern_recent_win"] = round(sum(1 for t in tr if float(t["ret"]) > 0) / len(tr), 3) if tr else None
    return f


def prompt_text(feat):
    return "Signal context (all values known at the signal bar close; returns are fractions):\n" + \
        json.dumps(feat, ensure_ascii=False, sort_keys=True)


def prompt_hash(feat):
    return hashlib.sha256((SYSTEM + "\n" + prompt_text(feat)).encode("utf-8")).hexdigest()[:16]


# ── 호출·파싱 ─────────────────────────────────────────────────────────────────
def _post(body):
    """실제 HTTP. 테스트는 이 함수를 바꿔 끼운다."""
    req = urllib.request.Request(
        API_URL, data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"content-type": "application/json", "x-api-key": os.environ["ANTHROPIC_API_KEY"],
                 "anthropic-version": "2023-06-01"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
        return json.loads(resp.read().decode("utf-8"))


def parse(text):
    """모델 응답 → 검증된 dict 또는 None. 코드펜스·앞뒤 잡문 허용, 범위 밖 값은 클램프, 상한 1.0 고정."""
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
    try:
        c = float(d.get("confidence", 0.5))
    except Exception:
        c = 0.5
    c = min(1.0, max(0.0, c)) if math.isfinite(c) else 0.5
    reasons = d.get("reasons") or []
    if not isinstance(reasons, list):
        reasons = [str(reasons)]
    reasons = [str(x)[:160] for x in reasons][:3]
    return {"decision": dec, "size_mult": round(m, 3), "confidence": round(c, 3), "reasons": reasons}


def call(feat):
    """(parsed, error, latency_ms, raw_text). 키 없음·HTTP 오류·파싱 실패 전부 (None, err, ...) 로 돌려준다."""
    if not available():
        return None, "no_key", 0, None
    body = {"model": MODEL, "max_tokens": 300, "temperature": 0, "system": SYSTEM,
            "messages": [{"role": "user", "content": prompt_text(feat)}]}
    t0 = time.time()
    try:
        out = _post(body)
    except urllib.error.HTTPError as e:
        return None, f"http_{e.code}", int((time.time() - t0) * 1000), None
    except Exception as e:
        return None, f"err_{type(e).__name__}", int((time.time() - t0) * 1000), None
    ms = int((time.time() - t0) * 1000)
    text = "".join(blk.get("text", "") for blk in (out.get("content") or []) if blk.get("type") == "text")
    parsed = parse(text)
    return parsed, (None if parsed else "parse_fail"), ms, text[:600]


def judge(rows, ei, sig, ctx=None, mode=None):
    """신호 하나를 판단해 기록 행을 돌려준다. 절대 예외를 내지 않는다(거래 경로 보호)."""
    mode = mode or MODE
    rec = {"judged_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "symbol": sig.get("symbol"), "pattern": sig.get("pattern"), "direction": sig.get("direction"),
           "tf": sig.get("tf", "1d"), "entry_date": sig.get("date"),
           "entry_ts": sig.get("ts") or (rows[ei].get("ts") if 0 <= ei < len(rows) else None),
           "mode": mode, "model": MODEL, "prompt_hash": None,
           "decision": None, "size_mult": None, "confidence": None, "reasons": None,
           "latency_ms": None, "error": None, "features": None}
    try:
        feat = features(rows, ei, sig, ctx)
        rec["features"] = json.dumps(feat, ensure_ascii=False, sort_keys=True)
        rec["prompt_hash"] = prompt_hash(feat)
        parsed, err, ms, _raw = call(feat)
        rec["latency_ms"] = ms
        rec["error"] = err
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


def push_db(records):
    """ai_judgments 테이블에 기록(베스트에포트). 컬럼 미존재는 insert_tolerant 가 제외."""
    if not records:
        return 0
    try:
        import supabase_client as sc
        if not sc.available():
            return 0
        cli = sc.get_client("service")
        inserted, dropped = sc.insert_tolerant(cli, TABLE, records)
        if dropped:
            print(f"  [ai] {TABLE} 스키마 미존재 컬럼 제외: {dropped}")
        return len(inserted)
    except Exception as e:
        print(f"  [ai] {TABLE} 기록 실패(무시): {str(e)[:100]}")
        return 0


def summary_line(records):
    n = len(records)
    if not n:
        return "[ai] 판단 0건"
    dec = {}
    err = 0
    for r in records:
        if r.get("decision"):
            dec[r["decision"]] = dec.get(r["decision"], 0) + 1
        else:
            err += 1
    parts = " ".join(f"{k} {v}" for k, v in sorted(dec.items()))
    return f"[ai] {MODE} 판단 {n}건 — {parts}" + (f" | 미판단/오류 {err}" if err else "") + f" | {MODEL}"
