"""
ai_elliott.py — AI 엘리엇 BTC 자율매매 (2026-10-28 사용자 결정)

  사용자 지시: "엘리엇 파동에 따라 비트만 100usdt이하로 ai가 자율매매하도록 변경 원칙 변경"
  사용자 선택(같은 날): 전용 포트 $100 · 레버리지 3배 · 롱·숏 둘 다 · 매시간 판단(모델 사용자 지정 — MODEL)
  같은 날 개정(v2): "AI 를 쓰는 건 일봉상의 관점뿐 아니라 시간마다 15분봉~4시간봉 등 여러 봉을 분석해 가며 더 작은
  사이즈의 신호를 찾아서 매매하라는 것" — 15m·1h·4h 를 매시간 같이 읽고 작은 차수 셋업으로 매매한다.
  일봉과 동결 카운트는 배경(방향 편향)으로만 쓴다.
  같은 날 개정(v3): "엘리엇 파동 관점 매매라고는 했지만 RSI 나 이중 지그재그 등 유사 패턴을 전부 보는 거겠지" — v2 까지는
  RSI 가 입력에 없었고 세부 형태(이중·삼중 지그재그, 확장·러닝 플랫, 다이애고널 등)는 지시문에 일반 언급뿐이었다.
  v3 에서 시간대마다 RSI(14)·엘리엇 오실레이터(EWO 5/35)를 피벗에 붙이고, 고점끼리·저점끼리 다이버전스를 코드가 계산해
  넘기며, 엘리엇 형태 전체 목록과 판별 지침(교대·채널·파동 동등·모멘텀)을 지시문에 넣고, 판단 근거 형태(structure)를 기록한다.
  15분 진입 판단 시험(2026-10-29 사용자 지시 "진입판단을 15분마다 변경하는걸로 1주일만 테스트해보자 1주일 후에 계속할지
  중단할지 나한테 다시 물어봐줘"): 평탄일 때만 매시 :18/:33/:48 에도 진입 판단을 한다(ai_quarter.yml →
  paper_executor.run(ai_only=True)). 보유 중 판단(hold/close)은 매시 :03 그대로다. 기간은 universe.json
  ai_traders[].entry_check.until 까지이고 지나면 코드가 스스로 매시 판단만 남긴다(entry_check_active). 켜져 있는 동안은
  지시문이 SYSTEM_Q15(호출 주기 문장만 다름)·버전 PROMPT_VERSION_Q15 이고, 기준 가격은 가장 최근에 닫힌 봉(15분 틱에선
  15m)이며, 진입 신호는 그 봉이 속한 1h 봉을 가리킨다(signal_bar). 같은 1h 봉 안에서 같은 방향 재진입은 체결 엔진의 중복
  방어(봉 시각 키)가 막으므로 그 방향을 미리 막고 이유를 알린다(entered).

무엇을 하나
  매시 fast 틱(:03)마다 한 번, BTC 닫힌 봉(15m/1h/4h/1d)·시간대별 스윙 피벗·동결 엘리엇 카운트(elliott_count.json)·
  자기 포지션과 포트 상태를 LLM 에 넘겨 엘리엇 구조에 따른 결정을 JSON 으로 받는다.
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
작은 차수 카운트를 15m·1h·4h 에서 스스로 세어 판단한다. 브리핑 스크립트(elliott_watch.py)와는 import 관계가 없다.

검증된 전략이 아니다 — 엘리엇 채점 장부는 무작위 보행보다 나빴다(누적 브리어 0.243 vs 0.205). 사용자가 소액 한도를
정하고 돌리는 실험이고 손실 상한은 포트 $100 이다. v1 프롬프트는 이 사실을 들어 '대부분 대기'를 기본값으로 뒀는데
첫 7틱이 전부 대기였고, 사용자가 작은 차수 매매를 지시해 v2 에서 뺐다. 과매매 억제는 이제 진입 기준(작은 차수 무효화
지점에 붙인 손절 · 비용 차감 후 손익비 1.5 이상)이 맡는다.

비용: 하루 24회, 회당 입력 약 2만 토큰(v1 실측 약 1.57만 + 15m) · 출력(생각 포함, effort high) 수천 토큰 —
토큰은 행마다 기록한다. 15분 진입 판단 시험 중에는 평탄인 시간만큼 늘어 최대 하루 96회(v3 실측 회당 입력 약 2.24만 ·
출력 0.6~1.7천 토큰).
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
EFFORT = "high"                       # v2: 세 시간대를 맞춰 읽는 판단이라 medium 에서 올렸다. 생각은 기본으로 켜져 있다
PROMPT_VERSION = "elliott_v5_2026_10_30"           # v5: 숏 금지로 읽히는 문장 정리(2026-10-30 사용자 지시)
PROMPT_VERSION_Q15 = "elliott_v5q15_2026_10_30"   # 15분 진입 판단 시험 중(entry_check_active) — 지시문 SYSTEM_Q15
ENTRY_CHECK_EVERY_MIN = 15            # universe.json ai_traders[].entry_check.every_min 이 이 값이어야 켜진다
FALLBACK_BETA = "server-side-fallback-2026-07-01"   # 안전 분류기 거절 시 서버가 다른 모델로 재시도("default")
MAX_TOKENS = 16000                    # 생각 토큰 포함 상한(SDK 비스트리밍 한도 안 — 예상 7.5분 < 10분)
TIMEOUT_S = 150
COUNT_FILE = "elliott_count.json"
UNIVERSE_FILE = "universe.json"
BTC_TFS = ("15m", "1h", "4h", "1d")    # 작은 차수(15m~4h)를 읽고 1d 는 배경
ETH_TFS = ("15m", "1h", "4h")          # 교차 확인용 피벗
BARS = {"15m": 96, "1h": 120, "4h": 90, "1d": 100}              # 프롬프트에 넣는 닫힌 봉 수(15m 96 = 24시간)
ZZ_PCT = {"15m": 0.003, "1h": 0.006, "4h": 0.015, "1d": 0.05}   # 스윙 피벗(고저 지그재그) 임계
TF_MS = {"15m": 900_000, "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}
FETCH_DAYS = {"15m": 7}                # 15m 는 7일만 받는다 — 기본 창(45일)은 OKX 호출이 약 35회라 매시간 낭비다
SETUP_TFS = ("15m", "1h", "4h", "1d")
RSI_N = 14                             # Wilder RSI — detector_rsi_divergence.rsi_series 와 같은 계산(테스트가 고정)
EWO_FAST, EWO_SLOW = 5, 35             # 엘리엇 오실레이터 = 중간가 SMA5 − SMA35, 종가 대비 %
STRUCTURES = ("impulse", "leading_diagonal", "ending_diagonal", "zigzag", "double_zigzag", "triple_zigzag",
              "regular_flat", "expanded_flat", "running_flat", "contracting_triangle", "barrier_triangle",
              "expanding_triangle", "double_three", "triple_three", "unclear")
FLAT_ACTIONS = ("open_long", "open_short", "wait")
OPEN_ACTIONS = ("hold", "close")
ACTIONS = FLAT_ACTIONS + OPEN_ACTIONS

SYSTEM = (
    "You run a small, separately funded BTC-USDT perpetual futures account on OKX for the desk owner, trading from "
    "Elliott Wave structure. You are called once per hour, just after a 1h candle closes, and you decide one action. "
    "The owner wants this account to trade lower-degree structure: every hour, read the 15m, 1h and 4h charts "
    "together and look for small-degree setups that can be traded now, rather than waiting for the daily picture to "
    "resolve.\n\n"
    "What the code enforces (you cannot change it): one BTC position at a time; margin = min(pot, $100) at 3x "
    "isolated leverage; every entry carries a stop and a target that are placed on the exchange as an OCO bracket and "
    "fire between your hourly calls; the stop must be 0.3%-8% from the last close and the target at least 0.3% away, "
    "otherwise the entry is rejected; long and short entries are both allowed, and only the actions listed in "
    "allowed_actions are possible on each call; if the pot falls below $10 trading stops; "
    "a position still open after max_hold_1h_bars is closed by time. Costs: about 0.1-0.2% of notional per round trip "
    "plus funding every 8 hours.\n\n"
    "Data: btc holds closed candles and swing pivots for 15m (the last 24 hours), 1h, 4h and 1d. Pivots are high/low "
    "zigzags whose threshold grows with the timeframe; the last pivot of each list is still forming. Each pivot is "
    "[type, price, time, rsi14, ewo_pct]: rsi14 is Wilder RSI(14) at that pivot bar's close and ewo_pct is the Elliott "
    "Wave Oscillator (5-period minus 35-period simple average of the median price, in % of price) at that bar. Each "
    "timeframe also carries its latest rsi14 and ewo_pct and a divergence summary computed by code: it compares the "
    "last two swing highs and the last two swing lows (regular divergence: price makes a new extreme and RSI does "
    "not; hidden divergence: the reverse); last_forming marks a comparison whose later pivot is still forming. eth "
    "holds pivots in the same format on 15m, 1h and 4h for cross-confirmation. elliott_count is the desk's frozen "
    "higher-degree count: treat its labels as fixed context and do not relabel them.\n\n"
    "Method: count top-down. Use 4h and 1d to place the current move inside the higher-degree count and to set your "
    "directional bias. Count the current swing on 1h, then its internal waves on 15m. Respect the rules: wave 2 never "
    "retraces beyond the start of wave 1; wave 3 is never the shortest of waves 1, 3 and 5; wave 4 does not enter "
    "wave 1's territory except in diagonals; zigzags are 5-3-5, flats 3-3-5, triangles 3-3-3-3-3 and occur only as "
    "wave 4, B, X or the final wave of a combination; combinations are W-X-Y(-X-Z). Use common Fibonacci "
    "relationships (wave 2 at 50-61.8%, wave 3 at 1.618x wave 1, wave 4 at 23.6-38.2%, C equal to A or 1.618x A) as "
    "guides, not rules.\n\n"
    "Consider the whole Elliott catalog, not only the basic forms: impulses with an extended wave (1, 3 or 5) and "
    "truncated fifths; leading diagonals (wave 1 or A) and ending diagonals (wave 5 or C: overlapping, wedge-shaped, "
    "usually followed by a fast retracement to where the diagonal began); single, double (W-X-Y) and triple "
    "(W-X-Y-X-Z) zigzags; regular, expanded (B beyond the start of A, C beyond the end of A) and running flats; "
    "contracting, barrier and expanding triangles; double and triple threes. To choose between competing counts use "
    "alternation between waves 2 and 4, channeling (the 2-4 line and its parallel through wave 3 for wave 5; the 0-2 "
    "line and its parallel for wave 4), equality (wave 5 near wave 1 when wave 3 is extended; C near A), volume "
    "(usually heaviest in wave 3 and lighter in wave 5 and in corrections) and momentum: wave 3 normally carries the "
    "strongest RSI and EWO reading of its sequence, wave 5 and C often end with divergence against wave 3 or A, wave "
    "4 pulls EWO back toward zero, and B and X waves usually show weak momentum. Use RSI, EWO and divergence to rank "
    "counts and to confirm that a wave is ending; never trade a divergence or an oscillator level on its own.\n\n"
    "Tradable lower-degree setups (examples, not a closed list): a correction (wave 2, 4, B or X; zigzag, flat, "
    "triangle or W-X-Y) that looks complete on 15m/1h at a Fibonacci zone, entered as price starts to move away "
    "from it; waves 1 and 2 done on 15m with the turn into wave 3 under way; a completed five-wave sequence on "
    "15m/1h ending a C wave or a fifth wave, traded for the reversal; a finished triangle traded for its thrust. A "
    "lower-degree setup does not need the daily picture to be resolved first, but setups that trade against the 4h "
    "and higher-degree bias need a completed lower-degree pattern and should aim for the nearer target.\n\n"
    "Entries: put the stop just beyond the price that invalidates the lower-degree count you are trading (for 15m/1h "
    "setups that is usually 0.3-2% away), never at an arbitrary percentage. Put the target at a Fibonacci projection "
    "or retracement that the same count implies. Take the trade only if the target distance, after about 0.2% of "
    "round-trip cost, is at least 1.5 times the stop distance; if the invalidation is closer than 0.3% or farther "
    "than 8%, or the timeframes conflict so that no count is clearly favored, wait and say what you are watching "
    "for. Do not trade just to be active, but do not wait for certainty either: a clear lower-degree setup with a "
    "close invalidation is exactly what this account is for.\n\n"
    "Open position: each hour re-read 15m and 1h. Close early if the lower-degree count you entered on has been "
    "invalidated (for example the move you expected as an impulse unfolded in three waves and is retracing) or its "
    "target structure is complete; otherwise hold and let the stop and target work.\n\n"
    "Output: one JSON object matching the schema. setup_tf is the timeframe whose structure drives the decision "
    "(15m, 1h, 4h or 1d), including for wait, hold and close; structure is the Elliott structure that decision rests "
    "on (unclear when no structure is favored). stop and target are absolute BTC prices for open_long "
    "and open_short, and 0 for every other action. confidence is between 0 and 1. Write wave_view (the count you act "
    "on, naming the timeframe, one line), invalidation (the price and why) and rationale (at most three short "
    "sentences) in Korean."
)

# 15분 진입 판단 시험(2026-10-29~) 동안의 지시문 — 호출 주기 문장만 바꾸고 나머지(규칙·형태 목록·진입 기준)는 그대로다.
# 각 원문은 SYSTEM 에 정확히 한 번 있어야 한다(없으면 import 시 실패 — 지시문을 고치고 이 표를 안 고치면 바로 드러난다).
_Q15_EDITS = (
    ("You are called once per hour, just after a 1h candle closes, and you decide one action. ",
     "While the account is flat you are called every 15 minutes, just after a 15m candle closes, to decide whether "
     "to enter; while a position is open you are called once per hour, just after a 1h candle closes, to decide "
     "hold or close. Each call decides one action. "),
    ("every hour, read the 15m, 1h and 4h charts together",
     "on every call, read the 15m, 1h and 4h charts together"),
    ("fire between your hourly calls;", "fire between your calls;"),
    ("btc holds closed candles and swing pivots for 15m (the last 24 hours), 1h, 4h and 1d.",
     "btc holds closed candles and swing pivots for 15m (the last 24 hours), 1h, 4h and 1d; last_close and "
     "last_bar_utc belong to the latest closed candle, on the timeframe named in ref_tf (15m when a 15m candle has "
     "closed since the last 1h close)."),
    ("Do not trade just to be active, but do not wait for certainty either:",
     "Being called more often gives earlier looks at the same kinds of setups; it does not lower these entry "
     "criteria. Do not trade just to be active, but do not wait for certainty either:"),
)


def _swap_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f"SYSTEM 에 정확히 한 번 있어야 한다: {old[:60]!r} ({text.count(old)}회)")
    return text.replace(old, new)


SYSTEM_Q15 = SYSTEM
for _old, _new in _Q15_EDITS:
    SYSTEM_Q15 = _swap_once(SYSTEM_Q15, _old, _new)

SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": list(ACTIONS)},
        "setup_tf": {"type": "string", "enum": list(SETUP_TFS)},
        "structure": {"type": "string", "enum": list(STRUCTURES)},
        "stop": {"type": "number"},
        "target": {"type": "number"},
        "confidence": {"type": "number"},
        "wave_view": {"type": "string"},
        "invalidation": {"type": "string"},
        "rationale": {"type": "string"},
    },
    "required": ["action", "setup_tf", "structure", "stop", "target", "confidence", "wave_view", "invalidation",
                 "rationale"],
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


def _iso_ms(s):
    """'2026-11-05T08:00:00Z' → epoch ms. 시간대가 없으면 UTC 로 본다. 읽을 수 없으면 None."""
    from datetime import datetime, timezone
    try:
        dt = datetime.fromisoformat(str(s).strip().replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def entry_check_active(cfg=None, now_ms=None):
    """
    15분 진입 판단 시험이 지금 켜져 있나(2026-10-29 사용자 지시 '1주일만'). ai_traders 항목의 entry_check 가
    every_min 15 이고 until(UTC) 전이면 True. 항목·until 이 없거나 읽을 수 없으면 False — 켜지 않는 쪽이다.
    워크플로 게이트(ai_quarter.yml)가 의존성 설치 전에 부르므로 이 모듈은 표준 라이브러리만 쓴다.
    """
    cfg = cfg if cfg is not None else (config() or {})
    ec = (cfg or {}).get("entry_check") or {}
    try:
        every = int(ec.get("every_min") or 0)
    except (TypeError, ValueError):
        return False
    until = _iso_ms(ec.get("until"))
    now_ms = now_ms or int(time.time() * 1000)
    return every == ENTRY_CHECK_EVERY_MIN and until is not None and now_ms < until


# ── 입력(인과: 닫힌 봉만) ──────────────────────────────────────────────────────
def closed(rows, tf, now_ms):
    """닫힌 봉만. CSV 마지막 행은 거래소가 주는 형성 중인 봉이다(scheduler._closed_idx 와 같은 이유)."""
    bar = TF_MS[tf]
    return [r for r in (rows or []) if r.get("ts") is not None and r["ts"] + bar <= now_ms]


def ref_bar(btc):
    """
    판단 기준 봉 = 가장 최근에 닫힌 봉과 그 시간대. 15m 봉이 마지막 1h 봉보다 늦게 닫혔으면 15m, 아니면 1h.
    매시 :03 틱에서는 둘이 같은 순간(정시)에 닫히므로 1h 그대로다(종전과 같은 값). 15분 진입 판단 시험 중에만 쓴다.
    """
    b1, b15 = btc.get("1h") or [], btc.get("15m") or []
    if b15 and b1 and b15[-1]["ts"] + TF_MS["15m"] > b1[-1]["ts"] + TF_MS["1h"]:
        return b15[-1], "15m"
    return (b1[-1], "1h") if b1 else (None, None)


def signal_bar(rows_1h, ref, ref_tf):
    """
    진입 신호가 가리킬 1h 봉 = 기준 봉이 속한 1h 봉. 기준이 1h 면 그 봉(종전과 같다), 15m 면 그 15m 봉이 들어 있는
    1h 봉(15분 틱에선 아직 형성 중인 봉)이다. 체결 엔진은 이 봉을 진입봉으로 적고(포지션 tf 는 1h 그대로 — 시간청산·
    보유 판단이 1h 봉 기준이다) 중복 방어 키도 이 봉 시각이다. rows_1h 는 형성 중인 봉까지 포함한 목록이어야 한다.
    그 봉이 없으면 None — 진입하지 않는다(체결 엔진의 날짜 폴백이 그날 첫 봉을 잡지 않게).
    """
    if ref is None:
        return None
    if ref_tf == "1h":
        return ref
    ts = int(ref["ts"]) // TF_MS["1h"] * TF_MS["1h"]
    for r in reversed(rows_1h or []):
        if r.get("ts") == ts:
            return r
        if r.get("ts") is not None and r["ts"] < ts:
            break
    return None


def pivots(rows, pct):
    """
    고저 기준 지그재그 스윙 [(kind 'H'/'L', price, index)]. 마지막 하나는 아직 진행 중(미확정)이다.
    신고점(신저점)을 낸 봉 자신의 저가(고가)로는 꺾임을 확정하지 않는다 — 봉 안에서 고가와 저가 중 무엇이 먼저였는지
    모르기 때문이다. 종전에는 시가 근처 고점에서 신저점으로 떨어진 봉이 '저점 뒤 반등 중'(같은 봉의 L·H 쌍)으로
    잘못 찍혔다(2026-10-28 15m 실측: 12:00 봉 고 81,225 → 저 80,774, 종가 80,798).
    """
    if not rows:
        return []
    piv, trend = [], None
    hi, lo = (rows[0]["h"], 0), (rows[0]["l"], 0)
    for i in range(1, len(rows)):
        r = rows[i]
        if trend in (None, "up"):
            if r["h"] >= hi[0]:
                hi = (r["h"], i)
            elif r["l"] <= hi[0] * (1 - pct):
                piv.append(("H",) + hi)
                trend, lo = "down", (r["l"], i)
                continue
        if trend in (None, "down"):
            if r["l"] <= lo[0]:
                lo = (r["l"], i)
            elif r["h"] >= lo[0] * (1 + pct):
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


def rsi_series(closes, n=RSI_N):
    """Wilder RSI — 앞 n개는 None. detector_rsi_divergence.rsi_series 와 같은 계산(test_ai_elliott 가 일치를 고정)."""
    out = [None] * len(closes)
    if len(closes) <= n:
        return out
    gains = losses = 0.0
    for i in range(1, n + 1):
        ch = closes[i] - closes[i - 1]
        gains += max(ch, 0.0)
        losses += max(-ch, 0.0)
    ag, al = gains / n, losses / n
    out[n] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    for i in range(n + 1, len(closes)):
        ch = closes[i] - closes[i - 1]
        ag = (ag * (n - 1) + max(ch, 0.0)) / n
        al = (al * (n - 1) + max(-ch, 0.0)) / n
        out[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def ewo_series(rows, fast=EWO_FAST, slow=EWO_SLOW):
    """엘리엇 오실레이터 — 중간가((고+저)/2)의 SMA(fast) − SMA(slow), 그 봉 종가 대비 %. 앞 slow-1 개는 None."""
    med = [(r["h"] + r["l"]) / 2 for r in rows]
    out = [None] * len(rows)
    for i in range(slow - 1, len(rows)):
        c = rows[i]["c"]
        if c:
            out[i] = (sum(med[i - fast + 1:i + 1]) / fast - sum(med[i - slow + 1:i + 1]) / slow) / c * 100
    return out


def _r(x, nd):
    return None if x is None else round(x, nd)


def pivots_compact(rows, pct, n=24, rsi=None, ewo=None):
    """[종류, 가격, 시각, RSI14, EWO%] — 지표는 그 피벗 봉 기준(인과: 그 봉까지의 종가만 쓴다)."""
    rsi = rsi if rsi is not None else rsi_series([r["c"] for r in rows])
    ewo = ewo if ewo is not None else ewo_series(rows)
    return [[k, _px(p), _t(rows[i]["ts"]), _r(rsi[i], 1), _r(ewo[i], 2)] for k, p, i in pivots(rows, pct)[-n:]]


def divergence(rows, piv, rsi):
    """
    마지막 두 고점·두 저점의 가격 대 RSI — 코드가 계산해 넘긴다(모델의 암산 오류 방지).
      고점: 가격 신고점 + RSI 낮은 고점 = bearish(정규) / 가격 낮은 고점 + RSI 높은 고점 = hidden_bearish
      저점: 가격 신저점 + RSI 높은 저점 = bullish(정규) / 가격 높은 저점 + RSI 낮은 저점 = hidden_bullish
    piv = pivots() 결과 [(kind, price, idx)]. 마지막 피벗은 형성 중이라 그 비교는 last_forming=True 로 표시한다.
    """
    out = {}
    last_idx = piv[-1][2] if piv else None
    for kind, key in (("H", "highs"), ("L", "lows")):
        ps = [p for p in piv if p[0] == kind and rsi[p[2]] is not None]
        if len(ps) < 2:
            out[key] = None
            continue
        (_, p1, i1), (_, p2, i2) = ps[-2], ps[-1]
        r1, r2 = rsi[i1], rsi[i2]
        if kind == "H":
            typ = "bearish" if p2 > p1 and r2 < r1 else "hidden_bearish" if p2 < p1 and r2 > r1 else "none"
        else:
            typ = "bullish" if p2 < p1 and r2 > r1 else "hidden_bullish" if p2 > p1 and r2 < r1 else "none"
        out[key] = {"type": typ, "prev": [_px(p1), round(r1, 1), _t(rows[i1]["ts"])],
                    "last": [_px(p2), round(r2, 1), _t(rows[i2]["ts"])], "last_forming": i2 == last_idx}
    return out


def tf_block(rows, tf, n_piv=24, with_bars=True):
    """시간대 하나의 입력 — 봉·피벗(RSI·EWO 포함)·최근 RSI/EWO·다이버전스."""
    if not rows:
        return {"bars_t_o_h_l_c_v": [], "pivots": []} if with_bars else {}
    rsi = rsi_series([r["c"] for r in rows])
    ewo = ewo_series(rows)
    piv = pivots(rows, ZZ_PCT[tf])
    blk = {"bars_t_o_h_l_c_v": bars_compact(rows, BARS[tf])} if with_bars else {"last_close": _px(rows[-1]["c"])}
    blk.update(pivots=pivots_compact(rows, ZZ_PCT[tf], n_piv, rsi, ewo), rsi14=_r(rsi[-1], 1),
               ewo_pct=_r(ewo[-1], 2))
    if with_bars:
        blk["divergence"] = divergence(rows, piv, rsi)
    return blk


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
                  trades_recent, decisions_recent, ref=None, ref_tf=None):
    """
    모델 입력(JSON). btc/eth = {tf: 닫힌 봉 목록}. 전부 now_ms 이전에 닫힌 봉에서 나온다.
    ref/ref_tf 는 15분 진입 판단 시험 중에만 준다 — last_close·last_bar_utc 를 그 봉에서 잡고 ref_tf 를 적는다.
    안 주면 종전과 같다(마지막 닫힌 1h 봉, ref_tf 키 없음).
    """
    b1 = btc.get("1h") or []
    b15 = btc.get("15m") or []
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
                "atr14_15m_pct": atr_pct(b15), "atr14_1h_pct": atr_pct(b1)},
        "eth": {},
    }
    if ref is not None:
        payload["btc"]["last_close"] = _px(ref["c"])
        payload["btc"]["last_bar_utc"] = _t(ref["ts"])
        payload["btc"]["ref_tf"] = ref_tf
    for tf in BTC_TFS:
        payload["btc"][tf] = tf_block(btc.get(tf) or [], tf)
    for tf in ETH_TFS:
        rs = eth.get(tf) or []
        if rs:
            payload["eth"][tf] = tf_block(rs, tf, n_piv=16, with_bars=False)
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
    stf = str(d.get("setup_tf") or "").strip().lower()
    st = str(d.get("structure") or "").strip().lower()
    return {"action": act, "setup_tf": stf if stf in SETUP_TFS else "", "structure": st if st in STRUCTURES else "",
            "stop": num("stop"), "target": num("target"), "confidence": round(c, 3),
            "wave_view": str(d.get("wave_view") or "")[:300],
            "invalidation": str(d.get("invalidation") or "")[:300],
            "rationale": str(d.get("rationale") or "")[:600]}


def _usage(resp):
    u = getattr(resp, "usage", None)
    if u is None:
        return {}
    return {"in": getattr(u, "input_tokens", None), "out": getattr(u, "output_tokens", None)}


def call(user_text, system=None):
    """(parsed, error, latency_ms, usage, served_model, raw_text). 예외를 밖으로 내지 않는다. system 기본은 SYSTEM."""
    if not available():
        return None, "no_key", 0, {}, None, None
    t0 = time.time()
    try:
        resp = _create(system or SYSTEM, user_text)
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
         now_ms=None, cfg=None, count=None, history=None, entered=None, tick_kind=None):
    """
    결정 1회. 반환 (rec, signal | None, close_pos | None).
      rec       — ai_judgments 기록 행. code_action 은 체결 엔진이 채운다(실제로 한 일).
      signal    — 평탄에서 진입이면 체결 엔진 진입 루프에 덧붙일 신호(가드는 거기서 전부 다시 탄다).
      close_pos — 보유 중 close 면 그 포지션(실행은 paper_executor.ai_close).
    rows_of(sym, tf) 는 체결 엔진의 캐시 로더(형성 중인 봉 포함) — 여기서 닫힌 봉만 고른다.
    entered   — 이 프로젝트가 이미 낸 진입의 {(방향, 진입봉 시각)}. 신호 1h 봉에 같은 방향 진입이 있으면 그 방향을 막는다
                (체결 엔진 중복 방어가 어차피 막는다 — 모델에게 미리 알려 헛판단을 줄인다).
    tick_kind — 기록용("hourly" 매시 :03 / "quarter" 15분 진입 판단 틱).
    """
    now_ms = now_ms or int(time.time() * 1000)
    cfg = cfg if cfg is not None else (config() or {})
    spec = spec or {}
    lev = int((cap or {}).get("leverage") or 3)
    q15 = entry_check_active(cfg, now_ms)       # 15분 진입 판단 시험 중이면 지시문·기준 봉이 달라진다

    def _rows(sym, tf):
        try:
            return closed(rows_of(sym, tf), tf, now_ms)
        except Exception:
            return []

    btc = {tf: _rows(SYMBOL, tf) for tf in BTC_TFS}
    eth = {tf: _rows("ETH", tf) for tf in ETH_TFS}
    b1 = btc["1h"]
    rec = {"judged_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now_ms / 1000)), "kind": KIND,
           "symbol": SYMBOL, "pattern": PATTERN, "direction": (position or {}).get("direction") or "none",
           "tf": TF, "entry_date": None, "entry_ts": None, "entry_px": None,
           "mode": "live", "model": MODEL, "prompt_version": PROMPT_VERSION, "prompt_hash": None,
           "decision": None, "size_mult": 1.0, "confidence": None, "reasons": None,
           "latency_ms": None, "tokens_in": None, "tokens_out": None, "error": None, "features": None,
           "code_action": None, "mark_ts": None, "mark_px": None, "unreal_ret": None, "bars_held": None,
           "live_mode": bool((position or {}).get("live_mode"))}
    if q15:
        rec["prompt_version"] = PROMPT_VERSION_Q15
    if len(b1) < 30:
        rec["error"] = "no_data"
        return rec, None, None
    last = b1[-1]
    if q15:
        # 기준 = 가장 최근에 닫힌 봉(15분 틱에선 15m). 신호는 그 봉이 속한 1h 봉(형성 중일 수 있다)을 가리킨다.
        ref, ref_tf = ref_bar(btc)
        try:
            raw1h = rows_of(SYMBOL, "1h") or []
        except Exception:
            raw1h = []
        sbar = signal_bar(raw1h, ref, ref_tf)
    else:
        ref, ref_tf, sbar = last, "1h", last          # 종전과 같다 — 마지막 닫힌 1h 봉
    price = float(ref["c"])
    ebar = sbar or last
    rec.update(entry_date=ebar["date"], entry_ts=ebar["ts"], entry_px=price, mark_ts=ref["ts"], mark_px=price)
    if sbar is None and not position:
        # 신호를 가리킬 1h 봉이 데이터에 없다 — 진입할 수 없으니 호출하지 않는다(비용 0, 다음 틱 재시도)
        rec["error"] = "no_entry_bar"
        return rec, None, None
    pstate = position_state(position, last)
    if pstate:
        rec["unreal_ret"] = round(pstate["unrealized_pct"] / 100, 6) if pstate["unrealized_pct"] is not None else None
        rec["bars_held"] = pstate["bars_held_1h"]
    blocked0 = set(blocked_dirs or ())
    dup = set()
    if not position and sbar is not None:
        dup = {d for d in ("long", "short") if (d, int(sbar["ts"])) in (entered or set())}
    allowed = allowed_actions(position, cfg, blocked0 | dup, can_enter and margin_next is not None)
    notes = []
    # 방향 안내는 평탄일 때만 — 보유 중엔 진입 행동이 없고, 거래소 실측에 AI 자신의 포지션이 들어 있어 '다른 전략'
    # 이라는 말이 거짓이 된다(2026-10-29 실측: 자기 롱 보유 중 'open_short blocked: another strategy …').
    # 숏은 허용이다(2026-10-30 사용자 지시) — 막히는 경우는 이번 호출에 한정된 사정으로만 적는다.
    if not position:
        for d in sorted(blocked0):
            opp = "long" if d == "short" else "short"
            notes.append(f"open_{d} unavailable on this call only: another strategy currently holds a BTC {opp} "
                         f"on this account, and the account nets BTC by symbol, so a {d} order would close that "
                         f"position instead of opening one. Both directions are otherwise allowed.")
        for d in sorted(dup - blocked0):
            notes.append(f"open_{d} unavailable until the next 1h bar: an AI {d} was already opened in the current "
                         f"1h bar (one entry per direction per 1h bar).")
    if not position and margin_next is None:
        notes.append("pot below $10 — entries disabled")
    if not position and not can_enter:
        notes.append("account kill switch or trading halt is on — entries disabled")
    count = count if count is not None else load_count()
    history = history if history is not None else recent_decisions()
    payload = build_payload(now_ms, btc, eth, count, pstate, pot, margin_next, lev, allowed, notes, spec,
                            recent_trades(trades), history,
                            ref=(ref if q15 else None), ref_tf=(ref_tf if q15 else None))
    text = prompt_text(payload)
    system = SYSTEM_Q15 if q15 else SYSTEM
    rec["prompt_hash"] = hashlib.sha256((system + "\n" + text).encode("utf-8")).hexdigest()[:16]
    parsed, err, ms, usage, served, raw = call(text, system)
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
            "setup_tf": (parsed or {}).get("setup_tf"), "structure": (parsed or {}).get("structure"),
            "bars_15m": len(btc["15m"]),
            "divergence": {tf: payload["btc"][tf].get("divergence") for tf in BTC_TFS},
            "rsi14": {tf: payload["btc"][tf].get("rsi14") for tf in BTC_TFS},
            "pivots_15m": payload["btc"]["15m"]["pivots"][-10:],
            "pivots_1h": payload["btc"]["1h"]["pivots"][-10:], "pivots_4h": payload["btc"]["4h"]["pivots"][-8:],
            "raw": raw, "tick": tick_kind}
    if q15:
        feat.update(q15=True, ref_tf=ref_tf, ref_ts=ref["ts"], signal_bar_ts=sbar["ts"] if sbar else None,
                    dup_dirs=sorted(dup))
    rec["features"] = json.dumps(feat, ensure_ascii=False, sort_keys=True)
    if why:
        rec["code_action"] = f"ignored:{why}"
    if plan:
        rec["direction"] = plan["direction"]
        sig = {"symbol": SYMBOL, "pattern": PATTERN, "direction": plan["direction"], "tf": TF,
               "date": sbar["date"], "ts": sbar["ts"], "stop": plan["stop"], "target": plan["target"],
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
    stf = (f" {f['setup_tf']}" if f.get("setup_tf") else "") + (f"/{f['structure']}" if f.get("structure") else "")
    return (f"[ai-elliott] {rec.get('decision')}{stf}{lv} (conf {rec.get('confidence')}, {rec.get('latency_ms')}ms, "
            f"tok {rec.get('tokens_in')}/{rec.get('tokens_out')}){tag} — {view} | {rec.get('model')}")


if __name__ == "__main__":
    import sys
    if "--dry" not in sys.argv:
        raise SystemExit("python ai_elliott.py --dry  (주문 없음 — 입력·판단만 본다)")
    import detlib
    import fetch_data
    cache = {}

    def _ro(sym, tf):
        if (sym, tf) not in cache:
            if tf in FETCH_DAYS:              # 실거래 경로(paper_executor)와 같은 짧은 창
                fetch_data.update_csv(f"{sym}/USDT", tf, detlib.CSV(sym, tf), window_days=FETCH_DAYS[tf])
            cache[(sym, tf)] = detlib.load_ohlcv(sym, tf)
        return cache[(sym, tf)]

    spec_ = {"type": "signal_barrier", "horizon_bars": 168, "min_stop_pct": 0.003, "max_stop_pct": 0.08,
             "min_target_pct": 0.003}
    r_, s_, c_ = tick(position=None, trades=[], rows_of=_ro, cap={"leverage": 3}, pot=100.0, margin_next=100.0,
                      blocked_dirs=set(), can_enter=True, spec=spec_, history=[])
    print(summary_line(r_))
    print(json.dumps({k: v for k, v in r_.items() if k != "features"}, ensure_ascii=False, indent=1))
    print("signal:", {k: v for k, v in (s_ or {}).items() if k != "_ai_rec"})
