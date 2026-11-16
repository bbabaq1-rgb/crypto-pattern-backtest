"""
test_ai_elliott.py — AI 엘리엇 BTC 자율매매(2026-10-28 사용자 결정) 고정. 네트워크·API·거래소 없음.

사용자 지시 "엘리엇 파동에 따라 비트만 100usdt이하로 ai가 자율매매하도록 변경 원칙 변경" + 설정 선택
(전용 포트 $100 · 3배 · 롱·숏 · 매시간). 여기서 고정하는 것은 '수익이 난다'가 아니라
**사용자가 정한 한도와 안전장치가 코드에 그대로 박혀 있고, AI 가 그것을 넘을 길이 없다**는 것이다.

  1. 사양·등재 — registry exit_spec(signal_barrier)·live_cap(ledger 포트 $100·3배·1포지션), universe 스위치, 모델
  2. 격리 — ai_elliott 는 거래소·스케줄러·체결 엔진을 import 하지 않고 주문 함수를 부르지 않는다
  3. signal_barriers — 손절·익절 방향·거리 검증(0.3~8% / 0.3% 이상), 위반이면 None(진입 없음)
  4. 입력 — 닫힌 봉만(형성 중 봉·미래 봉 무시), 스윙 피벗, 15m~4h 다중 시간대(2026-10-28 v2),
     RSI·EWO·다이버전스(v3 — 같은 날 "RSI 나 이중 지그재그 등 유사 패턴을 전부 보는 거겠지")
  5. 응답 파싱·검증 — 허용 밖 행동·막힌 방향·잘못된 가격은 전부 '아무것도 안 함'으로
  6. API 호출 — 거절·토큰 초과·예외·키 없음이 모두 오류 기록으로 끝난다(거래 경로 무영향)
  7. tick — 평탄/보유/정지/포트 소진 상태별 결과
  8. ledger 포트 — 포트 = 100 + 실현 손익, 증거금 = min(포트, 100), $10 미만 None. tp1 복리 경로 불변
  9. 반대 방향 가드(OKX net 모드)
 10. ai_close — 자기 몫만, OCO 집행분은 시장가 재주문 없이 기록, 실패는 보류
 11. 체결 엔진 배선(소스 순서)
 12. DB — 같은 날 반복 매매가 서로를 지우지 않는다(entry_ts 키), 복원이 새 포지션을 '청산됨'으로 오인하지 않는다
 13. exchange — 익절가가 이미 지나간 진입은 주문 전에 거부
 14. 15분 진입 판단 시험(2026-10-29 사용자 지시 "진입판단을 15분마다 … 1주일만 테스트") — 기간 판정, 지시문 변형은
     호출 주기 문장뿐, 기준 봉(15m)·신호 1h 봉(형성 중)·같은 봉 같은 방향 안내, 꺼져 있으면 종전과 같음,
     체결 엔진 ai_only 경로(메인 전략 무접촉·보유 중 판단 없음·메인 신호 무시) 오프라인 e2e
 16. v6 게이트(2026-11-16 사용자 지시 "①②③④ 다 반영해서 v6 만들어줘") — ① 4h·1d 추세 역행 금지 ② confidence 0.6
     ③ setup_tf 1h 이상·손절 1%·손익비 1.5 ④ 계획 파일 트리거·무효화·만료, 두 방향 다 막히면 판단 호출 없음(gated),
     실제 elliott_plan.json 의 형식·방향 정합. §1~§15 는 게이트를 연 상태(추세 flat·계획 양방향 무장)에서 종전 동작을 본다

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

# v6 게이트(§16 에서 실제 함수로 시험)를 §1~§15 동안은 연다 — 추세 flat · 계획 양방향 무장 · 무효화 없음.
# 종전 시험들은 게이트와 무관한 경로(입력·검증·기록·체결 엔진 배선)를 보는 것이라 게이트가 끼어들면 안 된다.
_ORIG_TREND_GATE, _ORIG_LOAD_PLAN = ae.trend_gate, ae.load_plan
PLAN_OPEN = {"as_of": "2026-01-01T00:00:00Z", "valid_until": "2099-01-01T00:00:00Z", "context": "test",
             "long": {"enabled": True, "trigger": {"tf": "1h", "type": "close_above", "px": 1}},
             "short": {"enabled": True, "trigger": {"tf": "1h", "type": "close_below", "px": 10 ** 9}}}
ae.trend_gate = lambda btc: (set(), {"4h": {"state": "flat"}, "1d": {"state": "flat"}})
ae.load_plan = lambda path=None: PLAN_OPEN


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
# v2(같은 날 사용자 지시 "15분봉~4시간봉 등 여러 봉을 분석해 가며 더 작은 사이즈의 신호를 찾아서 매매")
check("v6 — 버전·effort high·토큰 상한(비스트리밍 10분 한도 안)",
      ae.PROMPT_VERSION == "elliott_v6_2026_11_16" and ae.EFFORT == "high"
      and 3600 * ae.MAX_TOKENS / 128000 < 600, (ae.PROMPT_VERSION, ae.EFFORT, ae.MAX_TOKENS))
check("v2 — BTC 15m·1h·4h·1d, ETH 15m·1h·4h", ae.BTC_TFS == ("15m", "1h", "4h", "1d")
      and ae.ETH_TFS == ("15m", "1h", "4h") and all(tf in ae.BARS and tf in ae.ZZ_PCT and tf in ae.TF_MS
                                                    for tf in ae.BTC_TFS))
check("v2 — 15m 96봉(24시간)·피벗 임계가 시간대와 함께 커진다", ae.BARS["15m"] == 96
      and ae.ZZ_PCT["15m"] < ae.ZZ_PCT["1h"] < ae.ZZ_PCT["4h"] < ae.ZZ_PCT["1d"])
check("v2 — 15m 수집 창은 짧게(OKX 일반 캔들 범위 15일 안)", 0 < ae.FETCH_DAYS["15m"] <= 14)
check("v6 — 프롬프트: 15m·1h·4h 를 함께 읽되 진입은 1h 이상 셋업만, 15m 는 타이밍용",
      all(k in ae.SYSTEM for k in ("read the 15m, 1h and 4h charts together", "1h-or-higher setup", "setup_tf",
                                   "use 15m only to read its internal waves and to time an entry")))
check("v6 — 손익비 1.5·비용 차감·무효화 지점 손절(1h 이상 카운트)", all(k in ae.SYSTEM for k in
      ("1.5 times the stop distance", "0.2% of round-trip cost", "invalidates the 1h-or-higher count")))
check("v2 — 응답 스키마에 setup_tf(필수, 시간대 열거)", ae.SCHEMA["properties"]["setup_tf"]["enum"]
      == list(ae.SETUP_TFS) and "setup_tf" in ae.SCHEMA["required"])
# v3(같은 날 사용자 질문 "RSI 나 이중 지그재그 등 유사 패턴을 전부 보는 거겠지")
check("v3 — 응답 스키마에 structure(필수, 엘리엇 형태 열거 + unclear)",
      ae.SCHEMA["properties"]["structure"]["enum"] == list(ae.STRUCTURES) and "structure" in ae.SCHEMA["required"]
      and {"double_zigzag", "triple_zigzag", "expanded_flat", "running_flat", "ending_diagonal",
           "leading_diagonal", "barrier_triangle", "expanding_triangle", "double_three", "unclear"} <= set(ae.STRUCTURES))
check("v3 — 프롬프트: 형태 목록(이중·삼중 지그재그·확장·러닝 플랫·다이애고널·삼각형 종류·3중 결합)",
      all(k in ae.SYSTEM for k in ("double (W-X-Y)", "triple", "expanded", "running flats", "ending diagonals",
                                   "leading diagonals", "barrier and expanding triangles", "truncated fifths")))
check("v3 — 프롬프트: 판별 지침(교대·채널·동등·거래량·모멘텀) + 지표 단독 매매 금지",
      all(k in ae.SYSTEM for k in ("alternation", "channeling", "equality", "volume", "strongest RSI and EWO",
                                   "divergence against wave 3 or A", "never trade a divergence or an oscillator")))
check("v3 — 프롬프트가 피벗 형식[type, price, time, rsi14, ewo_pct]·다이버전스 요약을 설명",
      "[type, price, time, rsi14, ewo_pct]" in ae.SYSTEM and "divergence summary computed by code" in ae.SYSTEM)
check("종목 BTC 하나 · 1h 판단", ae.SYMBOL == "BTC" and ae.TF == "1h")
check("exit_spec = signal_barrier, 손절 1~8%(v6) · 익절 0.3%+ · 168봉 시간청산",
      SPEC == {"type": "signal_barrier", "horizon_bars": 168, "min_stop_pct": 0.01, "max_stop_pct": 0.08,
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
# 봉 안 순서 — 신저점 봉 자신의 고가로 반등을 확정하지 않는다(2026-10-28 15m 실측 결함)
_sb = [dict(ts=k, h=h, l=l, c=c) for k, (h, l, c) in enumerate([(100, 99, 99.5), (99.6, 98, 98.2), (98.4, 97, 97.1),
                                                                 (98.0, 96.0, 96.2), (97.5, 96.5, 97.4)])]
check("신저점 봉의 고가로 L·H 쌍을 만들지 않는다(마지막은 형성 중 저점)",
      ae.pivots(_sb[:4], 0.006) == [("H", 100, 0), ("L", 96.0, 3)], ae.pivots(_sb[:4], 0.006))
check("반등 확정은 다음 봉에서", ae.pivots(_sb, 0.006) == [("H", 100, 0), ("L", 96.0, 3), ("H", 97.5, 4)],
      ae.pivots(_sb, 0.006))
check("실데이터 형태 피벗에 같은 봉 연속 쌍이 없다", all(pv[k][2] != pv[k + 1][2] for k in range(len(pv) - 1)))
Q = H // 4
r15 = mkrows(300, t0=rows[-1]["ts"] - 297 * Q, tf_ms=Q)      # 마지막 두 봉이 형성 중/방금 닫힘
cl15 = ae.closed(r15, "15m", now)
check("15m 도 형성 중인 봉을 뺀다", cl15 and cl15[-1]["ts"] + Q <= now and len(cl15) < len(r15))
btc = {"15m": cl15, "1h": cl, "4h": ae.closed(mkrows(120, tf_ms=4 * H), "4h", now), "1d": []}
p1 = ae.build_payload(now, btc, {}, None, None, 100.0, 100.0, 3, ["wait"], [], SPEC, [], [])
fut = rows + [dict(rows[-1], ts=rows[-1]["ts"] + H * k, c=1.0, h=1.0, l=1.0, o=1.0) for k in (1, 2, 3)]
btc2 = dict(btc, **{"1h": ae.closed(fut, "1h", now)})
p2 = ae.build_payload(now, btc2, {}, None, None, 100.0, 100.0, 3, ["wait"], [], SPEC, [], [])
check("미래 봉을 붙여도 입력이 같다(인과)", json.dumps(p1) == json.dumps(p2))
check("봉 수 상한(1h 120)", len(p1["btc"]["1h"]["bars_t_o_h_l_c_v"]) == ae.BARS["1h"])
check("15m 봉 96·피벗·ATR 이 입력에 들어간다", len(p1["btc"]["15m"]["bars_t_o_h_l_c_v"]) == ae.BARS["15m"]
      and len(p1["btc"]["15m"]["pivots"]) > 4 and p1["btc"]["atr14_15m_pct"] is not None)
check("15m 피벗이 1h 보다 촘촘하다(같은 구간 기준)",
      len(ae.pivots(cl15[-96:], ae.ZZ_PCT["15m"])) >= len(ae.pivots(cl15[-96:], ae.ZZ_PCT["1h"])))
fut15 = r15 + [dict(r15[-1], ts=r15[-1]["ts"] + Q * k, c=1.0, h=1.0, l=1.0, o=1.0) for k in (1, 2, 3)]
p3 = ae.build_payload(now, dict(btc, **{"15m": ae.closed(fut15, "15m", now)}), {}, None, None, 100.0, 100.0, 3,
                      ["wait"], [], SPEC, [], [])
check("15m 에 미래 봉을 붙여도 입력이 같다(인과)", json.dumps(p1) == json.dumps(p3))
pe_eth = ae.build_payload(now, btc, {"15m": cl15, "1h": cl}, None, None, 100.0, 100.0, 3, ["wait"], [], SPEC, [], [])
check("ETH 15m·1h 피벗(교차 확인)", set(pe_eth["eth"]) == {"15m", "1h"} and pe_eth["eth"]["15m"]["pivots"])

# v3 지표 — RSI(Wilder)·EWO·다이버전스
import detector_rsi_divergence as drd
cls_ = [r["c"] for r in cl]
check("RSI = 레포의 Wilder 구현(detector_rsi_divergence.rsi_series)과 일치",
      all((a is None and b is None) or abs(a - b) < 1e-9 for a, b in zip(ae.rsi_series(cls_), drd.rsi_series(cls_, 14))))
check("RSI 경계: 전부 상승 100 · 전부 하락 0 · 앞 14개 None",
      ae.rsi_series([float(i) for i in range(30)])[-1] == 100.0
      and ae.rsi_series([float(30 - i) for i in range(30)])[-1] == 0.0
      and ae.rsi_series([float(i) for i in range(30)])[:14] == [None] * 14)
flat = [dict(h=101.0, l=99.0, c=100.0) for _ in range(40)]
check("EWO: 평평하면 0, 앞 34개 None", ae.ewo_series(flat)[-1] == 0.0 and ae.ewo_series(flat)[:34] == [None] * 34)
rise = [dict(h=100.0 + i + 1, l=100.0 + i - 1, c=100.0 + i) for i in range(40)]
_e = ae.ewo_series(rise)[-1]
check("EWO: 꾸준한 상승이면 양수 — (SMA5−SMA35)/종가 = 15/139 %", _e > 0 and abs(_e - 15 / 139 * 100) < 1e-9, _e)
check("피벗에 RSI·EWO 가 붙는다([종류, 가격, 시각, rsi, ewo])",
      all(len(x) == 5 for x in p1["btc"]["1h"]["pivots"]) and p1["btc"]["1h"]["pivots"][-1][3] is not None
      and p1["btc"]["1h"]["rsi14"] is not None and p1["btc"]["1h"]["ewo_pct"] is not None)


def piv_rows(seq):
    """(고, 저, 종) 수열로 봉 목록."""
    return [dict(ts=1_761_000_000_000 + k * H, date="2026-10-01", o=c, h=h, l=l, c=c, v=1.0)
            for k, (h, l, c) in enumerate(seq)]


_rr = piv_rows([(1, 1, 1)] * 10)
_piv = [("H", 110.0, 3), ("L", 100.0, 5), ("H", 112.0, 7), ("L", 98.0, 9)]
_rsi = [None, None, None, 70.0, None, 30.0, None, 65.0, None, 35.0]
dv = ae.divergence(_rr, _piv, _rsi)
check("다이버전스: 가격 신고점·RSI 낮은 고점 = bearish / 가격 신저점·RSI 높은 저점 = bullish",
      dv["highs"]["type"] == "bearish" and dv["lows"]["type"] == "bullish"
      and dv["lows"]["last_forming"] is True and dv["highs"]["last_forming"] is False, dv)
_piv2 = [("H", 112.0, 3), ("L", 98.0, 5), ("H", 110.0, 7), ("L", 100.0, 9)]
dv2 = ae.divergence(_rr, _piv2, [None, None, None, 65.0, None, 35.0, None, 70.0, None, 30.0])
check("숨은 다이버전스: 낮은 고점·RSI 높은 고점 = hidden_bearish / 높은 저점·RSI 낮은 저점 = hidden_bullish",
      dv2["highs"]["type"] == "hidden_bearish" and dv2["lows"]["type"] == "hidden_bullish", dv2)
dv3 = ae.divergence(_rr, [("H", 110.0, 3), ("L", 100.0, 5), ("H", 112.0, 7)], [None, None, None, 60.0, None, 30.0,
                                                                              None, 70.0, None, None])
check("다이버전스 없음·저점 하나뿐 → none / None", dv3["highs"]["type"] == "none" and dv3["lows"] is None, dv3)
check("BTC 시간대마다 다이버전스 요약(highs·lows), ETH 는 피벗만",
      all(set(p1["btc"][tf].get("divergence") or {}) == {"highs", "lows"} for tf in ("15m", "1h", "4h"))
      and "divergence" not in pe_eth["eth"]["1h"] and len(pe_eth["eth"]["1h"]["pivots"][0]) == 5)
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
check("파싱: structure 정규화(모르는 값·누락 → 빈 문자열)",
      ae.parse('{"action":"wait","structure":"Double_Zigzag"}')["structure"] == "double_zigzag"
      and ae.parse('{"action":"wait","structure":"head_and_shoulders"}')["structure"] == ""
      and ae.parse('{"action":"wait"}')["structure"] == "")
check("파싱: setup_tf 정규화(모르는 값·누락 → 빈 문자열)",
      ae.parse('{"action":"wait","setup_tf":"15M"}')["setup_tf"] == "15m"
      and ae.parse('{"action":"wait","setup_tf":"5m"}')["setup_tf"] == ""
      and ae.parse('{"action":"wait"}')["setup_tf"] == "")
flat_all = ae.allowed_actions(None, {"directions": ["long", "short"]}, set(), True)
check("평탄 허용 = 롱·숏·대기", flat_all == ["open_long", "open_short", "wait"])
check("보유 허용 = 유지·청산", ae.allowed_actions({"direction": "long"}, {}, set(), True) == ["hold", "close"])
check("막힌 방향 제외", ae.allowed_actions(None, {}, {"short"}, True) == ["open_long", "wait"])
check("진입 불가(정지·포트 소진)면 대기만", ae.allowed_actions(None, {}, set(), False) == ["wait"])
check("롱만 설정이면 숏 없음", ae.allowed_actions(None, {"directions": ["long"]}, set(), True) == ["open_long", "wait"])
base = {"stop": 0, "target": 0, "confidence": 0.65, "setup_tf": "1h", "structure": "zigzag", "wave_view": "",
        "invalidation": "", "rationale": ""}
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

# 요청 형태 — 가짜 SDK 모듈로 실제 _create 가 보내는 인자를 잡는다(설치된 SDK 와 무관)
import sys
cap_kw = {}


class _FakeMessages:
    def create(self, **kw):
        cap_kw.update(kw)
        return fake_resp(J)


class _FakeClient:
    def __init__(self, **kw):
        cap_kw["_client"] = kw
        self.beta = NS(messages=_FakeMessages())


_real_sdk = sys.modules.get("anthropic")
sys.modules["anthropic"] = types.SimpleNamespace(Anthropic=_FakeClient)
try:
    _orig_create(ae.SYSTEM, "u")
finally:
    if _real_sdk is not None:
        sys.modules["anthropic"] = _real_sdk
    else:
        sys.modules.pop("anthropic", None)
check("요청: 모델·effort·JSON 스키마·서버 폴백·타임아웃, 샘플링·thinking 미전송",
      cap_kw.get("model") == ae.MODEL and cap_kw.get("max_tokens") == ae.MAX_TOKENS
      and cap_kw.get("output_config") == {"effort": ae.EFFORT, "format": {"type": "json_schema", "schema": ae.SCHEMA}}
      and cap_kw.get("fallbacks") == "default" and cap_kw.get("betas") == [ae.FALLBACK_BETA]
      and cap_kw["_client"] == {"timeout": ae.TIMEOUT_S, "max_retries": 1}
      and not any(k in cap_kw for k in ("temperature", "top_p", "top_k", "thinking")), cap_kw)

# ── 7. tick ──────────────────────────────────────────────────────────────────
R1 = mkrows(200)
R4 = mkrows(120, tf_ms=4 * H)
RD = mkrows(150, tf_ms=24 * H)
NOW = R1[-1]["ts"] + H // 2
R15 = mkrows(300, t0=R1[-1]["ts"] - 297 * (H // 4), tf_ms=H // 4)
asked = []


def ro(sym, tf):
    asked.append((sym, tf))
    if sym == "BTC":
        return {"15m": R15, "1h": R1, "4h": R4, "1d": RD}[tf]
    return {"15m": R15, "1h": R1, "4h": R4}.get(tf) or []


last_c = ae.closed(R1, "1h", NOW)[-1]["c"]
seen = {}


def answer(d):
    def f(s, u):
        seen["user"] = u
        return fake_resp(json.dumps(dict(base, **d)))
    return f


kw = dict(trades=[], rows_of=ro, cap=CAP, pot=100.0, margin_next=100.0, spec=SPEC, now_ms=NOW,
          cfg={"directions": ["long", "short"]}, count=ae.load_count(), history=[])
ae._create = answer(dict(action="open_long", setup_tf="1h", structure="double_zigzag", stop=round(last_c * 0.985),
                         target=round(last_c * 1.03), wave_view="1h: (ii) 끝 → (iii)", invalidation="저점 이탈"))
rec, sg, cp = ae.tick(position=None, blocked_dirs=set(), can_enter=True, **kw)
check("tick 이 BTC 15m·1h·4h·1d, ETH 15m·1h·4h 를 읽는다", set(asked) == {("BTC", t) for t in ae.BTC_TFS}
      | {("ETH", t) for t in ae.ETH_TFS}, sorted(set(asked)))
_f = json.loads(rec["features"])
check("기록 특성에 setup_tf·15m 봉 수·15m 피벗", _f["setup_tf"] == "1h" and _f["bars_15m"] > 90
      and _f["pivots_15m"])
check("기록 특성에 structure·시간대별 RSI·다이버전스", _f["structure"] == "double_zigzag"
      and set(_f["rsi14"]) == set(ae.BTC_TFS) and set(_f["divergence"]) == set(ae.BTC_TFS))
check("입력에 RSI·EWO·다이버전스", all(k in seen["user"] for k in ('"rsi14"', '"ewo_pct"', '"divergence"')))
check("입력에 15m 데이터", '"15m":{"bars_t_o_h_l_c_v"' in seen["user"])
check("로그 한 줄에 시간대·형태", ae.summary_line(rec).startswith("[ai-elliott] open_long 1h/double_zigzag "))
check("평탄 + 롱 → 진입 신호(손절·익절 가격 그대로)", sg and sg["direction"] == "long" and cp is None
      and sg["stop"] == round(last_c * 0.985) and sg["target"] == round(last_c * 1.03)
      and sg["pattern"] == ae.PATTERN and sg["ai_elliott"] is True and sg["_ai_rec"] is rec)
check("신호봉 = 마지막 닫힌 봉", sg["ts"] == ae.closed(R1, "1h", NOW)[-1]["ts"])
check("기록 행: kind·모델·버전·결정·크기 1.0·근거(JSON)", rec["kind"] == "elliott_btc" and rec["model"] == ae.MODEL
      and rec["prompt_version"] == ae.PROMPT_VERSION and rec["decision"] == "open_long" and rec["size_mult"] == 1.0
      and json.loads(rec["reasons"])[0] == "1h: (ii) 끝 → (iii)" and rec["direction"] == "long")
check("기록 행의 키가 ai_judgments 컬럼에 전부 있다",
      all(k in io.open("supabase_schema_ai_judge.sql", encoding="utf-8").read() for k in rec),
      [k for k in rec if k not in io.open("supabase_schema_ai_judge.sql", encoding="utf-8").read()])
check("입력에 허용 행동·포트·카운트 요약·BTC/ETH 데이터", all(k in seen["user"] for k in
      ('"allowed_actions"', '"pot_usd"', '"elliott_count"', '"btc"', '"eth"', '"pivots"')))
ae._create = answer(dict(action="open_short", stop=round(last_c * 1.01), target=round(last_c * 0.97)))
rec, sg, cp = ae.tick(position=None, blocked_dirs={"short"}, can_enter=True, **kw)
check("숏이 막혔는데 숏 응답 → 아무것도 안 함", sg is None and cp is None and rec["code_action"] == "ignored:not_allowed:open_short")
_nt = json.loads(rec["features"]).get("notes") or []
check("막힌 이유를 모델에게 알린다 — 이번 호출에 한정, 평소엔 양방향 허용(2026-10-30)",
      "open_short unavailable on this call only" in seen["user"] and len(_nt) == 1
      and _nt[0].startswith("open_short unavailable on this call only: another strategy currently holds a BTC long")
      and _nt[0].endswith("Both directions are otherwise allowed."), _nt)
pos = dict(symbol="BTC", pattern=ae.PATTERN, direction="long", entry_price=last_c * 0.98, stop=last_c * 0.97,
           target=last_c * 1.05, entry_ts=R1[-30]["ts"], entry_date=R1[-30]["date"], live_mode=True, size_usd=100.0)
ae._create = answer(dict(action="close", rationale="카운트 무효"))
rec, sg, cp = ae.tick(position=pos, blocked_dirs=set(), can_enter=True, **kw)
check("보유 + close → 청산 대상 포지션 반환", cp is pos and sg is None and rec["decision"] == "close"
      and rec["bars_held"] == 28 and rec["unreal_ret"] > 0)
ae._create = answer(dict(action="hold"))
rec, sg, cp = ae.tick(position=pos, blocked_dirs=set(), can_enter=True, **kw)
check("보유 + hold → 아무것도 안 함", sg is None and cp is None and rec["decision"] == "hold")
# 2026-10-30 사용자 지시 "AI 엘리엇 숏도 허용이야 숏 허용되지 않는다는 문장 있으면 삭제해".
# 보유 중엔 거래소 실측에 AI 자신의 포지션이 들어 있어 반대 방향이 blocked_dirs 로 들어온다(paper_executor el_block).
# 종전엔 그때 "open_short blocked: another strategy …" 라는 거짓 안내가 붙었다(10-29 06:08 실측) — 이제 안 붙는다.
ae._create = answer(dict(action="hold"))
rec, sg, cp = ae.tick(position=pos, blocked_dirs={"short"}, can_enter=True, **kw)
check("보유 중(자기 롱이 blocked_dirs 로 들어와도) 방향 안내를 붙이지 않는다",
      json.loads(rec["features"]).get("notes") == [] and '"notes":[]' in seen["user"]
      and "another strategy" not in seen["user"]
      and '"allowed_actions":["hold","close"]' in seen["user"], json.loads(rec["features"]).get("notes"))
check("지시문: 양방향 허용을 적고, '방향이 막힐 수 있다'는 일반 문장은 없다(v5)",
      all("long and short entries are both allowed" in t for t in (ae.SYSTEM, ae.SYSTEM_Q15))
      and not any(k in t for t in (ae.SYSTEM, ae.SYSTEM_Q15) for k in ("can be blocked", "blocked because")))
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
i_pref = es.find("for _tf, _days in ai_elliott.FETCH_DAYS.items():")
check("15m 짧은 창 수집이 판단 바로 앞(BTC·ETH, 캐시에 없을 때만, 실패는 기본 창으로)",
      0 < i_sig < i_pref < i_tick and "for _sym in (ai_elliott.SYMBOL, \"ETH\"):" in es[i_pref - 200:i_pref]
      and "if (_sym, _tf) not in rows_cache:" in es[i_pref:i_tick]
      and "window_days=_days" in es[i_pref:i_tick] and "except Exception" in es[i_pref:i_tick])
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

# ── 14. 15분 진입 판단 시험 ──────────────────────────────────────────────────
# 2026-10-29 사용자 지시 "진입판단을 15분마다 변경하는걸로 1주일만 테스트해보자 1주일 후에 계속할지 중단할지 나한테
# 다시 물어봐줘". 평탄일 때 :18/:33/:48 에도 진입 판단, 보유 판단은 매시 그대로, until 이 지나면 스스로 꺼진다.
import hashlib
check("지시문 v6(SYSTEM) 불변 — 고치면 PROMPT_VERSION 을 올리고 이 값을 갱신",
      hashlib.sha256(ae.SYSTEM.encode("utf-8")).hexdigest()[:16] == "bc2c5ab4e879496f",
      hashlib.sha256(ae.SYSTEM.encode("utf-8")).hexdigest()[:16])
_s = ae.SYSTEM_Q15
for _o, _n in reversed(ae._Q15_EDITS):
    _s = _s.replace(_n, _o)
check("SYSTEM_Q15 는 호출 주기 문장만 다르다(편집을 되돌리면 SYSTEM 과 같다)", _s == ae.SYSTEM and ae.SYSTEM_Q15 != ae.SYSTEM)
check("SYSTEM_Q15: 평탄이면 15분마다·보유면 매시", "every 15 minutes, just after a 15m candle closes" in ae.SYSTEM_Q15
      and "while a position is open you are called once per hour" in ae.SYSTEM_Q15
      and "Open position: each hour re-read 1h and 4h, with 15m for detail." in ae.SYSTEM_Q15)
check("SYSTEM_Q15: 자주 불러도 진입 기준은 그대로", "it does not lower these entry criteria" in ae.SYSTEM_Q15)
check("SYSTEM_Q15: ref_tf 설명(v3 에는 없다)", "ref_tf" in ae.SYSTEM_Q15 and "ref_tf" not in ae.SYSTEM)
check("버전: 15분 판단 중 v6q15 · 아니면 v6", ae.PROMPT_VERSION == "elliott_v6_2026_11_16"
      and ae.PROMPT_VERSION_Q15 == "elliott_v6q15_2026_11_16")
try:
    ae._swap_once("abc", "x", "y")
    _sw = False
except ValueError:
    _sw = True
check("편집 원문이 지시문에 없으면 import 단계에서 실패한다", _sw)

_T = ae._iso_ms("2026-11-05T06:30:00Z")


def EC(**k):
    return {"entry_check": dict({"every_min": 15, "until": "2026-11-05T06:30:00Z"}, **k)}


check("entry_check: 기간 안 → 켜짐", ae.entry_check_active(EC(), _T - 1))
check("entry_check: until 정각부터 꺼짐", not ae.entry_check_active(EC(), _T) and not ae.entry_check_active(EC(), _T + 60_000))
check("entry_check: 항목 없음·until 없음·읽기 실패 → 꺼짐", not ae.entry_check_active({}, _T - 1)
      and not ae.entry_check_active(EC(until=None), _T - 1) and not ae.entry_check_active(EC(until="내일"), _T - 1))
check("entry_check: every_min 이 15 가 아니면 꺼짐", not ae.entry_check_active(EC(every_min=60), _T - 1)
      and not ae.entry_check_active(EC(every_min="x"), _T - 1))
check("entry_check: 시간대 없는 until 은 UTC", ae._iso_ms("2026-11-05T06:30:00") == _T)
# 2026-11-12 사용자 결정 '중단' — entry_check 를 지우고 이력만 남긴다. 실제 설정으로 15분 판단이 꺼져 있어야 한다
_uat = next(t for t in uni["ai_traders"] if t["pattern"] == P)
check("universe: 15분 진입 판단 중단(entry_check 없음 → 실제 설정으로 꺼짐)", "entry_check" not in _uat
      and not ae.entry_check_active(_uat, _T - 1), _uat.get("entry_check"))
_ueh = (_uat.get("entry_check_history") or [{}])[-1]
check("universe: 시험 이력(15분 · 2026-10-29 시작 · 11-12 종료 · 사용자 지시·연장·중단 기록)", _ueh.get("every_min") == 15
      and _ueh.get("started") == "2026-10-29" and str(_ueh.get("ended", "")).startswith("2026-11-12")
      and "1주일" in _ueh.get("decided", "") and "사용자 결정 2026-11-12" in _ueh.get("stopped", "")
      and any(x.get("on") == "2026-11-05" and "사용자 결정" in x.get("decided", "") for x in _ueh.get("extensions", [])), _ueh)
check("registry: 시험 기록(deploy_on_pass false · 2주차 결과·중단 결정)", rp.get("entry_check_test_2026_10_29", {}).get("deploy_on_pass") is False
      and "중단" in rp.get("entry_check_test_2026_10_29", {}).get("week2_result_2026_11_12", {}).get("decision", ""))

# 정렬된 합성 봉 — TA = 2026-10-29 00:00Z. 00:20 = 15분 틱(15m 00:00 봉이 막 닫힘, 1h 00:00 봉 형성 중), 00:03 = 매시 틱.
TA = ae._iso_ms("2026-10-29T00:00:00Z")
Q1 = mkrows(200, t0=TA - 199 * H)
Q15 = mkrows(102, start=90000.0, t0=TA - 100 * (H // 4), tf_ms=H // 4)    # 가격대가 1h 와 다르다 — 기준 가격 판별용
Q4 = mkrows(120, t0=TA - 119 * 4 * H, tf_ms=4 * H)
QD = mkrows(150, t0=TA - 149 * 24 * H, tf_ms=24 * H)
NOWQ, NOWH = TA + 20 * 60_000, TA + 3 * 60_000


def roq_f(drop_forming=False):
    def roq(sym, tf):
        if tf == "15m":
            return Q15
        if tf == "1h":
            return Q1[:-1] if drop_forming else Q1
        if tf == "4h":
            return Q4
        return QD if sym == "BTC" else []
    return roq


_ref, _rtf = ae.ref_bar({"1h": ae.closed(Q1, "1h", NOWQ), "15m": ae.closed(Q15, "15m", NOWQ)})
check("기준 봉: 15분 틱이면 막 닫힌 15m 봉", _rtf == "15m" and _ref["ts"] == TA, (_rtf, _ref and _ref["ts"]))
_refh, _rtfh = ae.ref_bar({"1h": ae.closed(Q1, "1h", NOWH), "15m": ae.closed(Q15, "15m", NOWH)})
check("기준 봉: 매시 :03 틱이면 1h 봉 그대로(15m 와 같은 순간에 닫힘)", _rtfh == "1h" and _refh is ae.closed(Q1, "1h", NOWH)[-1])
check("신호 1h 봉: 15m 기준이면 그 봉이 속한 1h 봉(형성 중)", ae.signal_bar(Q1, _ref, "15m") is Q1[-1])
check("신호 1h 봉: 1h 기준이면 그 봉", ae.signal_bar(Q1, _refh, "1h") is _refh)
check("신호 1h 봉: 데이터에 없으면 None(날짜 폴백 금지)", ae.signal_bar(Q1[:-1], _ref, "15m") is None)

os.environ["ANTHROPIC_API_KEY"] = "test"
calls = []
REFC = _ref["c"]


def answer_q(d):
    def f(s, u):
        calls.append((s, u))
        return fake_resp(json.dumps(dict(base, **d)))
    return f


CFG_Q = dict({"directions": ["long", "short"]}, **EC())
kwq = dict(trades=[], rows_of=roq_f(), cap=CAP, pot=100.0, margin_next=100.0, spec=SPEC, now_ms=NOWQ, cfg=CFG_Q,
           count=ae.load_count(), history=[])
OPEN_L = dict(action="open_long", setup_tf="1h", structure="zigzag", stop=round(REFC * 0.985), target=round(REFC * 1.03),
              wave_view="1h: c 끝", invalidation="저점 이탈")
ae._create = answer_q(OPEN_L)
rec, sg, cp = ae.tick(position=None, blocked_dirs=set(), can_enter=True, tick_kind="quarter", **kwq)
_f = json.loads(rec["features"])
check("15분 틱 진입: 신호가 형성 중인 1h 봉을 가리킨다", sg and sg["ts"] == Q1[-1]["ts"] and sg["date"] == Q1[-1]["date"]
      and sg["direction"] == "long" and sg["tf"] == "1h", sg and {k: sg[k] for k in ("ts", "date", "tf")})
check("15분 틱 진입: 손절·익절 = 기준(15m) 가격 기준 — 1h 종가 기준이면 롱 손절이 시세 위라 거부됐을 값",
      sg and sg["stop"] == OPEN_L["stop"] and OPEN_L["stop"] > ae.closed(Q1, "1h", NOWQ)[-1]["c"])
check("15분 틱: 지시문 SYSTEM_Q15 · 버전 v5q15", calls[-1][0] == ae.SYSTEM_Q15 and rec["prompt_version"] == ae.PROMPT_VERSION_Q15)
check("15분 틱: 입력의 기준 가격·시각이 15m 봉(ref_tf)", '"ref_tf":"15m"' in calls[-1][1]
      and f'"last_close":{ae._px(REFC)}' in calls[-1][1])
check("15분 틱: 기록 — tick·ref_tf·신호 봉·진입봉 시각·마크 시각", _f.get("tick") == "quarter" and _f.get("ref_tf") == "15m"
      and _f.get("q15") is True and _f.get("signal_bar_ts") == Q1[-1]["ts"] and rec["entry_ts"] == Q1[-1]["ts"]
      and rec["mark_ts"] == TA and rec["mark_px"] == REFC, (_f.get("tick"), _f.get("ref_tf"), rec["entry_ts"], rec["mark_ts"]))
rec, sg, cp = ae.tick(position=None, blocked_dirs=set(), can_enter=True, tick_kind="quarter",
                      entered={("long", Q1[-1]["ts"])}, **kwq)
check("같은 1h 봉에 AI 롱이 이미 있으면 롱을 막고 이유를 알린다(숏은 가능)", sg is None
      and rec["code_action"] == "ignored:not_allowed:open_long"
      and "already opened in the current 1h bar" in calls[-1][1]
      and "open_long unavailable until the next 1h bar" in calls[-1][1]
      and '"allowed_actions":["open_short","wait"]' in calls[-1][1])
rec, sg, cp = ae.tick(position=None, blocked_dirs=set(), can_enter=True, tick_kind="quarter",
                      entered={("long", Q1[-2]["ts"]), ("short", Q1[-1]["ts"])}, **kwq)
check("다른 봉의 진입·다른 방향은 막지 않는다", sg is not None and sg["direction"] == "long"
      and json.loads(rec["features"]).get("dup_dirs") == ["short"])
_n = len(calls)
rec, sg, cp = ae.tick(position=None, blocked_dirs=set(), can_enter=True, tick_kind="quarter",
                      **dict(kwq, rows_of=roq_f(drop_forming=True)))
check("신호를 가리킬 1h 봉이 없으면 호출하지 않는다(no_entry_bar)", rec["error"] == "no_entry_bar" and sg is None
      and len(calls) == _n)
C1H = ae.closed(Q1, "1h", NOWH)[-1]["c"]                 # 매시 틱의 기준 가격 = 마지막 닫힌 1h 종가
ae._create = answer_q(dict(OPEN_L, stop=round(C1H * 0.985), target=round(C1H * 1.03)))
rec, sg, cp = ae.tick(position=None, blocked_dirs=set(), can_enter=True, tick_kind="hourly", **dict(kwq, now_ms=NOWH))
check("시험 중 매시 :03 틱: 신호 = 마지막 닫힌 1h 봉(종전과 같다) · 지시문은 Q15", sg is not None
      and sg["ts"] == ae.closed(Q1, "1h", NOWH)[-1]["ts"] and calls[-1][0] == ae.SYSTEM_Q15
      and '"ref_tf":"1h"' in calls[-1][1] and json.loads(rec["features"]).get("tick") == "hourly")
rec, sg, cp = ae.tick(position=None, blocked_dirs=set(), can_enter=True, tick_kind="hourly",
                      **dict(kwq, cfg={"directions": ["long", "short"]}))
check("시험이 꺼져 있으면 종전과 같다 — v6 지시문·버전, ref_tf 없음, 15분 시각이어도 신호 = 마지막 닫힌 1h 봉",
      calls[-1][0] == ae.SYSTEM and rec["prompt_version"] == ae.PROMPT_VERSION and '"ref_tf"' not in calls[-1][1]
      and rec["mark_ts"] == ae.closed(Q1, "1h", NOWQ)[-1]["ts"]
      and sg is not None and sg["ts"] == ae.closed(Q1, "1h", NOWQ)[-1]["ts"])
_posq = dict(symbol="BTC", pattern=P, direction="long", entry_price=Q1[-30]["c"], stop=Q1[-30]["c"] * 0.97,
             target=Q1[-30]["c"] * 1.05, entry_ts=Q1[-30]["ts"], entry_date=Q1[-30]["date"], live_mode=True, size_usd=100.0)
ae._create = answer_q(dict(action="hold"))
rec, sg, cp = ae.tick(position=_posq, blocked_dirs=set(), can_enter=True, tick_kind="hourly", **dict(kwq, now_ms=NOWH))
check("시험 중 보유 판단(매시): hold 그대로·보유 봉 수는 1h 기준", sg is None and cp is None and rec["decision"] == "hold"
      and rec["bars_held"] == 28)

# 체결 엔진 배선(소스) — ai_only
_r = es.split("def run(", 1)[1]
check("run(..., ai_only=False)", "def run(stamp=None, slow=None, ai_only=False):" in es)
check("ai_only: 시험 기간 밖·키 없음이면 아무것도 안 하고 끝", "if not (ai_elliott.enabled() and ai_elliott.entry_check_active()):" in _r
      and 'skipped="inactive"' in _r and 'skipped="no_key"' in _r)
check("ai_only: 레짐 계산 안 함", "regmap = {} if ai_only else rs.build_regime_map()" in _r)
_i_ai = _r.find("if ai_only:\n            # 15분 틱은 메인 전략 장부·주문을 건드리지 않는다")
check("ai_only: 정합성 보정·청산 감지·손절 점검 생략(그 블록 앞에서 갈린다)",
      0 < _i_ai < _r.find("reconcile_live_flag(positions, live_conn)")
      < _r.find("reconcile_closed_positions(positions, trades, live_conn)") < _r.find("ensure_stop_orders(live_conn, stop_map=stop_map,"))
_b_ai = _r[_i_ai:_r.find("reconcile_live_flag(positions, live_conn)")]
check("ai_only: 청산 이력 대조(키로 맞추는 reconcile)는 15분 틱에서 부르지 않는다 — OCO 집행은 settle_by_algo 가 그 algo 로 본다"
      "(2026-10-29 — 이력 지연·포지션 조회 실패 시 직전 거래 청산가를 붙일 위험)", "reconcile" not in _b_ai.split("else:")[0], _b_ai)
check("ai_only: 킬스위치·정지 판정은 그대로(갈림 블록 밖)", "\n        bal = ex_mod.get_balance(live_conn)\n" in _r
      and "\n        halt_on, halt_why = trading_halt_state()\n" in _r)
check("ai_only: 청산 루프는 AI 행만 자기 OCO 확인(settle_by_algo)", "if ai_only:\n            # 15분 틱: AI 엘리엇 행만" in _r
      and "and settle_by_algo(pos, live_conn, trades, datetime.now(timezone.utc).strftime(\"%Y-%m-%d\"))):" in _r)
check("ai_only: 방식R 그림자 생략", "r_added = 0 if ai_only else shadow_r_records(trades, rows_of, regmap)" in _r)
check("ai_only: 메인 신호 무시", 'if ai_only:\n        sig = {"signals": []}' in _r)
check("ai_only: 보유 중이면 판단을 부르지 않는다(보유 판단은 매시)",
      0 < _r.find("elif ai_only and el_pos is not None:") < _r.find("elif el_pos is None and not el_can_enter:"))
check("AI 판단에 이미 낸 진입(entered)·틱 종류 전달", 'entered=el_entered, tick_kind=("quarter" if ai_only else "hourly"))' in _r)
check("AI 신호는 봉 시각이 정확히 맞아야 진입(날짜 폴백 금지)",
      'if ei is None or (s.get("ai_elliott") and rows[ei].get("ts") != s.get("ts")):' in _r)
check("스킵 사유를 AI 판단 행에(no_rows·no_bar·dup_bar)",
      all(f'_ai_action(s.get("_ai_rec"), "{k}")' in _r for k in ("no_rows", "no_bar", "dup_bar")))
check("python paper_executor.py aitick → run(slow=False, ai_only=True)", 'elif arg == "aitick":' in es
      and "run(slow=False, ai_only=True)" in es)


# 오프라인 e2e — 거래소·DB 없음(페이퍼). 15m 를 1h·4h 로 합쳐 형성 중인 봉까지 실제처럼 만든다.
def _agg(rows15, span):
    out, order = {}, []
    for r in rows15:
        k = r["ts"] // span * span
        if k not in out:
            out[k] = dict(ts=k, o=r["o"], h=r["h"], l=r["l"], c=r["c"], v=r["v"])
            order.append(k)
        else:
            b = out[k]
            b["h"], b["l"], b["c"], b["v"] = max(b["h"], r["h"]), min(b["l"], r["l"]), r["c"], b["v"] + r["v"]
    return [out[k] for k in order]


def _q_e2e():
    import csv as _csv, shutil, tempfile, time as _rt
    import detlib, fetch_data
    repo, tmp = os.getcwd(), tempfile.mkdtemp()
    qnow = TA + 20 * 60_000
    env_keep = {k: os.environ.pop(k) for k in ("OKX_KEY", "OKX_SECRET", "OKX_PASSPHRASE", "SUPABASE_URL",
                                               "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_KEY") if k in os.environ}
    keep = dict(time=ae.time, create=ae._create, rd=ae.recent_decisions, af=detlib._auto_fetch,
                uc=fetch_data.update_csv, rg=pe.rs.build_regime_map)
    got = {"calls": [], "af": [], "out": []}

    def wcsv(path, rows):
        with open(path, "w", newline="") as f:
            w = _csv.writer(f)
            w.writerow(["timestamp", "open", "high", "low", "close", "volume"])
            for x in rows:
                w.writerow([x["ts"], x["o"], x["h"], x["l"], x["c"], x["v"]])

    def uni_with(until):
        u = json.load(io.open(os.path.join(repo, "universe.json"), encoding="utf-8"))
        for t in u["ai_traders"]:
            if t["pattern"] == P:
                t["entry_check"] = {"every_min": 15, "until": until}
        # 운용 스위치(사용자 지시 정지 등)는 이 e2e 의 측정 대상이 아니다 — 레포 상태와 무관하게 꺼 둔다
        u["trading_halt"] = {"active": False}
        json.dump(u, open("universe.json", "w", encoding="utf-8"), ensure_ascii=False)

    def auto_fetch(sym, tf):
        got["af"].append((sym, tf))
        raise FileNotFoundError(f"{sym} {tf}")

    def regime_forbidden(*a, **k):
        raise AssertionError("15분 틱에서 레짐 계산을 부르면 안 된다")

    try:
        for fn in ("registry.json", "elliott_count.json"):
            shutil.copy(fn, os.path.join(tmp, fn))
        os.chdir(tmp)
        os.makedirs("data", exist_ok=True)
        uni_with("2026-10-30T00:00:00Z")
        for sym, start in (("BTC", 80000.0), ("ETH", 2700.0)):
            r15 = mkrows(10 * 96 + 2, start=start, t0=TA - (10 * 96) * (H // 4), tf_ms=H // 4)   # 마지막 = 00:15(형성 중)
            wcsv(f"data/{sym.lower()}_15m.csv", r15)
            wcsv(f"data/{sym.lower()}_1h.csv", _agg(r15, H))
            wcsv(f"data/{sym.lower()}_4h.csv", _agg(r15, 4 * H))
        wcsv("data/btc_1d.csv", mkrows(150, t0=TA - 149 * 24 * H, tf_ms=24 * H))
        main_pos = dict(symbol="SOL", direction="long", pattern="marubozu", tf="1d", entry_date="2026-10-20",
                        entry_ts=None, entry_price=150.0, stop=138.0, size_usd=40.0, d_closed=False, a_closed=False)
        json.dump([main_pos], open("paper_positions.json", "w"))
        json.dump([], open("paper_trades.json", "w"))
        json.dump({"signals": [dict(symbol="SOL", pattern="marubozu", direction="long", tf="1d", date="2026-10-28",
                                    ts=None, regime="bull_btc")]}, open("signals_today.json", "w"))
        ae.time = types.SimpleNamespace(time=lambda: qnow / 1000, strftime=_rt.strftime, gmtime=_rt.gmtime)
        ae.recent_decisions = lambda n=3: []
        detlib._auto_fetch = auto_fetch
        fetch_data.update_csv = lambda *a, **k: (0, 0)
        pe.rs.build_regime_map = regime_forbidden
        r15b = detlib.load_ohlcv("BTC", "15m")
        ref_c = [r for r in r15b if r["ts"] == TA][0]["c"]
        h1 = detlib.load_ohlcv("BTC", "1h")

        def create(s, u):
            got["calls"].append((s, u))
            return fake_resp(json.dumps(dict(base, action="open_long", setup_tf="1h", structure="zigzag",
                                             stop=round(ref_c * 0.985), target=round(ref_c * 1.03))))
        ae._create = create
        got["out"].append(pe.run(ai_only=True))                       # ① 평탄 → 판단 → 진입(페이퍼)
        got["pos1"] = json.load(open("paper_positions.json"))
        got["out"].append(pe.run(ai_only=True))                       # ② 보유 → 판단 안 부름
        got["n_after_hold"] = len(got["calls"])
        json.dump([main_pos], open("paper_positions.json", "w"))      # ③ AI 거래 청산 뒤, 같은 1h 봉
        json.dump([dict(method="D", symbol="BTC", direction="long", pattern=P, entry_date=h1[-1]["date"],
                        entry_ts=TA, entry_price=ref_c, exit_date="2026-10-29", exit_price=ref_c * 0.99,
                        ret=-0.012, pnl_live_usd=None, reason="ai_stop", hold_bars=0)], open("paper_trades.json", "w"))
        got["out"].append(pe.run(ai_only=True))
        got["pos3"] = json.load(open("paper_positions.json"))
        uni_with("2026-10-29T00:00:00Z")                              # ④ 시험 기간 종료
        got["n_before_off"] = len(got["calls"])
        got["out"].append(pe.run(ai_only=True))
        got["h1_last"], got["ref_c"] = h1[-1], ref_c
    finally:
        ae.time, ae._create, ae.recent_decisions = keep["time"], keep["create"], keep["rd"]
        detlib._auto_fetch, fetch_data.update_csv, pe.rs.build_regime_map = keep["af"], keep["uc"], keep["rg"]
        os.environ.update(env_keep)
        os.chdir(repo)
        shutil.rmtree(tmp, ignore_errors=True)
    return got


g = _q_e2e()
_ai_pos = [p for p in g["pos1"] if p.get("pattern") == P]
_sol = [p for p in g["pos1"] if p.get("symbol") == "SOL"]
check("e2e ① 평탄 → 15분 틱 진입 1건(페이퍼)", g["out"][0].get("new") == 1 and len(_ai_pos) == 1, g["out"][0])
check("e2e ① 진입봉 = 형성 중인 1h 봉(정확한 ts) · tf 1h · 진입가 = 그 봉 종가(최신 가격)",
      _ai_pos and _ai_pos[0]["entry_ts"] == TA and _ai_pos[0]["tf"] == "1h"
      and abs(_ai_pos[0]["entry_price"] - round(g["h1_last"]["c"], 8)) < 1e-9 and g["h1_last"]["ts"] == TA,
      _ai_pos and {k: _ai_pos[0][k] for k in ("entry_ts", "tf", "entry_price")})
check("e2e ① 손절·익절 = AI 가격 그대로(OCO 대상)", _ai_pos and _ai_pos[0]["stop"] == round(g["ref_c"] * 0.985)
      and _ai_pos[0]["target"] == round(g["ref_c"] * 1.03))
check("e2e ① 메인 신호(signals_today)는 무시, 메인 포지션은 손대지 않는다", len(g["pos1"]) == 2 and len(_sol) == 1
      and _sol[0]["d_closed"] is False and _sol[0]["a_closed"] is False)
check("e2e ① 메인 종목 봉 데이터를 읽지 않는다(자동 수집 0) · 레짐 계산 안 함", g["af"] == [], g["af"])
check("e2e ① 지시문 Q15 · 입력 기준 15m", g["calls"] and g["calls"][0][0] == ae.SYSTEM_Q15
      and '"ref_tf":"15m"' in g["calls"][0][1])
check("e2e ② 보유 중 → 판단을 부르지 않는다", g["out"][1].get("new") == 0 and g["n_after_hold"] == 1, g["n_after_hold"])
check("e2e ③ 같은 1h 봉에 낸 롱이 있으면 롱을 막고 알린다 → 진입 없음",
      g["out"][2].get("new") == 0 and len(g["calls"]) == 2
      and "already opened in the current 1h bar" in g["calls"][1][1]
      and not [p for p in g["pos3"] if p.get("pattern") == P])
check("e2e ④ 시험 기간이 끝나면 아무것도 안 한다", g["out"][3].get("skipped") == "inactive"
      and len(g["calls"]) == g["n_before_off"])

# ── 15. 15분 틱 — AI OCO 청산 감지(2026-10-29 실측) ─────────────────────────
# OCO 익절(14:33:47Z 체결) 6초 뒤 14:33 틱이 AI 를 '보유 중'으로 보고 진입 판단을 건너뛰었다. 15분 틱은 settle_by_algo 로
# 자기 OCO 집행을 보는데, 시장가 OCO 의 OKX 이력은 actualPx 가 "" 라 algo_state 가 체결가를 못 읽어 settle_by_algo 가 늘
# False 였다(배포 이래). algo_state 가 집행으로 생긴 시장가 주문(ordIdList)의 avgPx 를 읽게 고쳤다 — 여기서는 **실제
# algo_state** 를 진단 실행에서 받은 OKX 응답 모양 그대로의 스텁 거래소에 물려 끝까지 돌린다.
class OkxStub:
    def __init__(self, history=None, pending=None, orders=None, order_raises=False):
        self.history, self.pending = history or {}, pending or {}
        self.orders, self.order_raises, self.order_calls = orders or {}, order_raises, []

    def _lookup(self, table, p):
        o = table.get(p["algoId"])
        if o is None or o["ordType"] != p["ordType"]:
            raise Exception('okx {"code":"51603","data":[],"msg":"Order does not exist"}')
        return {"code": "0", "data": [o]}

    def privateGetTradeOrdersAlgoPending(self, p):
        return self._lookup(self.pending, p)

    def privateGetTradeOrdersAlgoHistory(self, p):
        return self._lookup(self.history, p)

    def privateGetTradeOrder(self, p):
        self.order_calls.append(p)
        if self.order_raises:
            raise Exception("network")
        return {"code": "0", "data": [self.orders[p["ordId"]]]}


ALGO15 = "4051395198249181184"
OCO15 = {"algoId": ALGO15, "instId": "BTC-USDT-SWAP", "ordType": "oco", "state": "effective", "actualPx": "",
         "actualSide": "tp", "actualSz": "0.37", "tpTriggerPx": "80743", "tpOrdPx": "-1", "slTriggerPx": "79590",
         "slOrdPx": "-1", "ordId": "4052772330579890181", "ordIdList": ["4052772330579890181"], "sz": "0.37"}
FILL15 = {"4052772330579890181": {"ordId": "4052772330579890181", "state": "filled", "ordType": "market",
                                  "side": "sell", "avgPx": "80752.2", "accFillSz": "0.37"}}
AI15 = dict(symbol="BTC", pattern=P, direction="long", tf="1h", entry_price=79865.0, stop=79590.0, target=80743.0,
            entry_ts=TA - 12 * H, entry_date="2026-10-28", live_mode=True, size_usd=100.0, d_closed=False,
            a_closed=False, live_order={"qty": 0.37, "leverage": 3, "sl_order_id": ALGO15})
ADA15 = dict(symbol="ADA", pattern="equal_lows_4h", direction="long", tf="4h", entry_price=0.5, stop=0.46,
             entry_date="2026-10-28", entry_ts=None, live_mode=True, size_usd=50.0, d_closed=False, a_closed=False)
MARU15 = dict(ADA15, symbol="BTC", pattern="marubozu", tf="1d", entry_price=82953.6, stop=76313.7)


def _q_live(open_keys, okx, rows_pos):
    """15분 틱 실거래 경로 오프라인 e2e — OKX 는 스텁 거래소(algo_state 는 실제 함수), 주문 함수는 호출되면 기록, DB 없음."""
    import csv as _csv, shutil, tempfile, time as _rt
    import detlib, fetch_data
    repo, tmp = os.getcwd(), tempfile.mkdtemp()
    qnow = TA + 20 * 60_000
    env_keep = {k: os.environ.pop(k) for k in ("SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_KEY")
                if k in os.environ}
    keep = dict(time=ae.time, create=ae._create, rd=ae.recent_decisions, af=detlib._auto_fetch,
                uc=fetch_data.update_csv, rg=pe.rs.build_regime_map, il=ex_mod.is_live, cl=ex_mod.connect_live,
                gb=ex_mod.get_balance, gp=ex_mod.get_okx_positions, gh=ex_mod.get_okx_closed_positions,
                pse=ex_mod.place_swap_entry, csp=ex_mod.close_swap_position, ns=notify.send)
    got = {"calls": [], "orders": []}

    def wcsv(path, rows):
        with open(path, "w", newline="") as f:
            w = _csv.writer(f)
            w.writerow(["timestamp", "open", "high", "low", "close", "volume"])
            for x in rows:
                w.writerow([x["ts"], x["o"], x["h"], x["l"], x["c"], x["v"]])

    def no_auto_fetch(sym, tf):
        raise FileNotFoundError(f"{sym} {tf}")

    def regime_forbidden(*a, **k):
        raise AssertionError("15분 틱에서 레짐 계산을 부르면 안 된다")

    def history_forbidden(*a, **k):
        raise AssertionError("15분 틱에서 청산 이력 대조를 부르면 안 된다")

    def order_forbidden(*a, **k):
        got["orders"].append((a, k))
        return None, "test_forbidden"

    def create(s, u):
        got["calls"].append((s, u))
        return fake_resp(json.dumps(dict(base, action="wait", setup_tf="15m", structure="unclear")))

    try:
        for fn in ("registry.json", "elliott_count.json"):
            shutil.copy(fn, os.path.join(tmp, fn))
        os.chdir(tmp)
        os.makedirs("data", exist_ok=True)
        u = json.load(io.open(os.path.join(repo, "universe.json"), encoding="utf-8"))
        for t in u["ai_traders"]:
            if t["pattern"] == P:
                t["entry_check"] = {"every_min": 15, "until": "2026-10-30T00:00:00Z"}
        u["trading_halt"] = {"active": False}   # 운용 스위치는 측정 대상 아님(위와 같음)
        json.dump(u, open("universe.json", "w", encoding="utf-8"), ensure_ascii=False)
        for sym, start in (("BTC", 80000.0), ("ETH", 2700.0)):
            r15 = mkrows(10 * 96 + 2, start=start, t0=TA - (10 * 96) * (H // 4), tf_ms=H // 4)
            wcsv(f"data/{sym.lower()}_15m.csv", r15)
            wcsv(f"data/{sym.lower()}_1h.csv", _agg(r15, H))
            wcsv(f"data/{sym.lower()}_4h.csv", _agg(r15, 4 * H))
        wcsv("data/btc_1d.csv", mkrows(150, t0=TA - 149 * 24 * H, tf_ms=24 * H))
        json.dump(rows_pos, open("paper_positions.json", "w"))
        json.dump([], open("paper_trades.json", "w"))
        json.dump({"signals": []}, open("signals_today.json", "w"))
        ex_mod.is_live = lambda: True
        ex_mod.connect_live = lambda: {"exchange": okx, "usdt_free": 203.47}
        ex_mod.get_balance = lambda lc: {"equity": 525.37, "free": 203.47, "total": 500.0}
        ex_mod.get_okx_positions = lambda lc: [dict(symbol=s, direction=d) for s, d in open_keys]
        ex_mod.get_okx_closed_positions = history_forbidden
        ex_mod.place_swap_entry = order_forbidden
        ex_mod.close_swap_position = order_forbidden
        notify.send = lambda *a, **k: False
        ae.time = types.SimpleNamespace(time=lambda: qnow / 1000, strftime=_rt.strftime, gmtime=_rt.gmtime)
        ae.recent_decisions = lambda n=3: []
        ae._create = create
        detlib._auto_fetch = no_auto_fetch
        fetch_data.update_csv = lambda *a, **k: (0, 0)
        pe.rs.build_regime_map = regime_forbidden
        got["out"] = pe.run(ai_only=True)
        got["pos"] = json.load(open("paper_positions.json"))
        got["trades"] = json.load(open("paper_trades.json"))
    finally:
        ae.time, ae._create, ae.recent_decisions = keep["time"], keep["create"], keep["rd"]
        detlib._auto_fetch, fetch_data.update_csv, pe.rs.build_regime_map = keep["af"], keep["uc"], keep["rg"]
        (ex_mod.is_live, ex_mod.connect_live, ex_mod.get_balance, ex_mod.get_okx_positions,
         ex_mod.get_okx_closed_positions, ex_mod.place_swap_entry, ex_mod.close_swap_position) = (
            keep["il"], keep["cl"], keep["gb"], keep["gp"], keep["gh"], keep["pse"], keep["csp"])
        notify.send = keep["ns"]
        os.environ.update(env_keep)
        os.chdir(repo)
        shutil.rmtree(tmp, ignore_errors=True)
    return got


_gross15 = 80752.2 / 79865.0 - 1
# ⑤ 실측 그대로: AI 단독 BTC 롱의 시장가 OCO 익절 집행(이력 actualPx "") → 15분 틱이 주문 체결가로 기록하고 평탄 판단
o5 = OkxStub(history={ALGO15: OCO15}, orders=FILL15)
q5 = _q_live([("ADA", "long")], o5, [AI15, ADA15])
_t5 = [t for t in q5["trades"] if t.get("pattern") == P]
check("e2e ⑤ 시장가 OCO 익절(actualPx \"\") → 15분 틱이 시장가 주문 체결가 80,752.2 로 기록 · 사유 ai_target — 종전엔 '보유 중'",
      len(_t5) == 1 and _t5[0]["exit_price"] == 80752.2 and _t5[0]["reason"] == "ai_target"
      and _t5[0]["method"] == "D" and _t5[0]["live_mode"] is True, q5["trades"])
check("e2e ⑤ 손익 = 수수료 차감 수익률 · 실손익 = 그 수익률 x 증거금 100 x 3배",
      _t5 and abs(_t5[0]["ret"] - round(_gross15 - pe.FEE, 5)) < 1e-9
      and abs(_t5[0]["pnl_live_usd"] - round((_gross15 - pe.FEE) * 300, 4)) < 1e-9, _t5)
check("e2e ⑤ 체결 주문 조회는 그 algo 의 ordIdList 로 한 번", o5.order_calls == [
      {"instId": "BTC-USDT-SWAP", "ordId": "4052772330579890181"}], o5.order_calls)
check("e2e ⑤ 장부에서 AI 행이 빠지고 메인 행은 그대로",
      [p["symbol"] for p in q5["pos"]] == ["ADA"] and q5["pos"][0]["d_closed"] is False, q5["pos"])
check("e2e ⑤ 같은 틱에서 평탄 판단 1회(Q15 지시문 · 기준 15m) · 주문 함수 호출 0(관망) · 청산 이력 대조 호출 0",
      len(q5["calls"]) == 1 and q5["calls"][0][0] == ae.SYSTEM_Q15 and '"ref_tf":"15m"' in q5["calls"][0][1]
      and q5["orders"] == [] and q5["out"].get("new") == 0, (len(q5["calls"]), q5["orders"], q5["out"]))
# ⑥ 메인 BTC 롱과 함께 든 경우(포지션이 거래소에 남는다) — 같은 경로로 AI 몫만 기록, 메인 행 불변
o6 = OkxStub(history={ALGO15: OCO15}, orders=FILL15)
q6 = _q_live([("BTC", "long"), ("ADA", "long")], o6, [AI15, MARU15])
_t6 = [t for t in q6["trades"] if t.get("pattern") == P]
check("e2e ⑥ 함께 든 BTC 롱 — OCO 집행 체결가로 AI 몫만 기록 · 메인 행 불변 · 평탄 판단 1회 · 주문 0",
      len(_t6) == 1 and _t6[0]["exit_price"] == 80752.2 and [p["pattern"] for p in q6["pos"]] == ["marubozu"]
      and q6["pos"][0]["d_closed"] is False and len(q6["calls"]) == 1 and q6["orders"] == [],
      (q6["trades"], q6["pos"], len(q6["calls"])))
# ⑦ 체결 주문 조회 실패 → 기록하지 않고 '보유 중'(다음 틱에 다시) — 트리거 가격 같은 근사치를 장부에 남기지 않는다
q7 = _q_live([("ADA", "long")], OkxStub(history={ALGO15: OCO15}, order_raises=True), [AI15, ADA15])
check("e2e ⑦ 체결가를 모르면 보류 — 거래 기록 0 · AI 행 유지 · 판단 호출 0 · 주문 0",
      not [t for t in q7["trades"] if t.get("pattern") == P] and len(q7["pos"]) == 2
      and q7["calls"] == [] and q7["orders"] == [], (q7["trades"], q7["pos"], len(q7["calls"])))
# ⑧ OCO 가 아직 대기(live) — 보유 유지, 체결 주문 조회 없음
o8 = OkxStub(pending={ALGO15: dict(OCO15, state="live", actualSide="", ordId="", ordIdList=[])})
q8 = _q_live([("BTC", "long"), ("ADA", "long")], o8, [AI15, ADA15])
check("e2e ⑧ OCO 대기 중 → 보유 유지 · 판단 호출 0 · 주문 조회 0",
      not q8["trades"] and len(q8["pos"]) == 2 and q8["calls"] == [] and o8.order_calls == [],
      (q8["trades"], len(q8["pos"]), len(q8["calls"])))
os.environ.pop("ANTHROPIC_API_KEY", None)

# ── 16. v6 게이트 ────────────────────────────────────────────────────────────
# 2026-11-16 사용자 지시 "①②③④ 다 반영해서 v6 만들어줘". 실거래 24건 7승 17패 −$11.75 부검 — 하락장 바닥 잡는 롱
# (15건 −$11.87)·15분봉 셋업(22/24)·평균 손실 −0.75%·확신도 전부 0.40~0.50. 네 가지를 코드가 강제하는지 본다.
ae.trend_gate, ae.load_plan = _ORIG_TREND_GATE, _ORIG_LOAD_PLAN


def lin(n, start, mult, tf_ms, t0=1_761_000_000_000):
    out, px = [], start
    for i in range(n):
        o, c = px, px * mult
        out.append(dict(ts=t0 + i * tf_ms, date="2026-10-01", o=o, h=max(o, c) * 1.001, l=min(o, c) * 0.999,
                        c=c, v=10.0))
        px = c
    return out


UP4, DN4 = lin(80, 60000, 1.003, 4 * H), lin(80, 90000, 0.997, 4 * H)
UPD, DND = lin(40, 60000, 1.01, 24 * H), lin(40, 90000, 0.99, 24 * H)
check("v6 상수 — 확신도 0.6 · 셋업 1h/4h/1d · 손절 1% · 손익비 1.5 · 비용 0.2% · 추세 EMA(4h 50·6봉 / 1d 20·5봉)",
      ae.MIN_CONF_ENTRY == 0.6 and ae.ENTRY_SETUP_TFS == ("1h", "4h", "1d") and ae.MIN_STOP_PCT == 0.01
      and ae.MIN_RR == 1.5 and ae.RR_COST == 0.002 and ae.TREND_SPEC == {"4h": (50, 6), "1d": (20, 5)})
_e = ae.ema_series([1.0, 2.0, 3.0, 4.0], 2)
check("EMA — 첫 값은 앞 n개 평균, 이후 k=2/(n+1)", _e[:2] == [None, 1.5] and abs(_e[2] - 2.5) < 1e-9
      and abs(_e[3] - 3.5) < 1e-9 and ae.ema_series([1.0], 2) == [])
check("추세: 오르는 4h → up · 내리는 4h → down · 봉 부족 → unknown",
      ae.trend_of(UP4, "4h")["state"] == "up" and ae.trend_of(DN4, "4h")["state"] == "down"
      and ae.trend_of(UP4[:50], "4h")["state"] == "unknown")
check("추세: 1d 도 같은 규칙(EMA20·5봉)", ae.trend_of(UPD, "1d")["state"] == "up"
      and ae.trend_of(DND, "1d")["state"] == "down")
_flat4 = lin(80, 70000, 1.0, 4 * H)
check("추세: 평평하면 flat", ae.trend_of(_flat4, "4h")["state"] == "flat")
check("추세 게이트 ① — 4h 하락이면 롱만 막는다", ae.trend_gate({"4h": DN4, "1d": _flat4[:40]})[0] == {"long"})
check("추세 게이트 ① — 1d 하락이면 4h 가 상승이어도 롱 금지, 4h 상승이라 숏도 금지(충돌 = 둘 다)",
      ae.trend_gate({"4h": UP4, "1d": DND})[0] == {"long", "short"})
check("추세 게이트 ① — 둘 다 상승이면 숏만 막는다", ae.trend_gate({"4h": UP4, "1d": UPD})[0] == {"short"})
check("추세 게이트 ① — 데이터 부족(unknown)이면 둘 다 막는다", ae.trend_gate({"4h": UP4[:10], "1d": UPD})[0]
      == {"long", "short"})

NOW6 = ae._iso_ms("2026-11-16T05:00:00Z")
B1 = {"1h": [dict(ts=NOW6 - 2 * H, date="2026-11-16", o=65000, h=65200, l=64800, c=65000, v=1)]}


def PL(**k):
    pl = {"as_of": "2026-11-16T04:00:00Z", "valid_until": "2026-11-17T16:00:00Z", "context": "c",
          "long": {"enabled": True, "trigger": {"tf": "1h", "type": "close_above", "px": 66100},
                   "invalidation_px": 63726, "targets": [69580]},
          "short": {"enabled": True, "trigger": {"tf": "1h", "type": "close_below", "px": 63726},
                    "invalidation_px": 65500, "targets": [60350]}}
    pl.update(k)
    return pl


check("계획 게이트 ④ — 계획 없음 → 둘 다 막힘(missing)", ae.plan_gate(None, B1, NOW6)[0] == {"long", "short"}
      and ae.plan_gate(None, B1, NOW6)[1]["status"] == "missing")
check("계획 게이트 ④ — 만료(valid_until 정각부터) → 둘 다 막힘",
      ae.plan_gate(PL(valid_until="2026-11-16T05:00:00Z"), B1, NOW6)[0] == {"long", "short"}
      and ae.plan_gate(PL(valid_until="2026-11-16T05:00:00Z"), B1, NOW6)[1]["status"] == "expired")
check("계획 게이트 ④ — valid_until 없음 → 둘 다 막힘", ae.plan_gate(PL(valid_until=None), B1, NOW6)[0] == {"long", "short"})
check("계획 게이트 ④ — 65,000 은 두 트리거 사이 → 둘 다 막힘(무장 없음)", ae.plan_gate(PL(), B1, NOW6)[0] == {"long", "short"})
_b_up = {"1h": [dict(B1["1h"][0], c=66200)]}
_b_dn = {"1h": [dict(B1["1h"][0], c=63600)]}
_g, _i = ae.plan_gate(PL(), _b_up, NOW6)
check("계획 게이트 ④ — 1h 종가 66,200 > 66,100 → 롱만 무장", _g == {"short"} and _i["long"]["armed"] is True
      and _i["long"]["invalidation_px"] == 63726 and _i["status"] == "active")
check("계획 게이트 ④ — 1h 종가 63,600 < 63,726 → 숏만 무장", ae.plan_gate(PL(), _b_dn, NOW6)[0] == {"long"})
check("계획 게이트 ④ — 같은 가격(경계)은 무장 아님(초과·미만만)",
      ae.plan_gate(PL(), {"1h": [dict(B1["1h"][0], c=66100)]}, NOW6)[0] == {"long", "short"})
check("계획 게이트 ④ — enabled false · 모르는 트리거 · 모르는 시간대 → 막힘",
      ae.plan_gate(PL(long={"enabled": False, "trigger": {"tf": "1h", "type": "close_above", "px": 1}}), _b_up, NOW6)[0]
      >= {"long"}
      and ae.plan_gate(PL(long={"enabled": True, "trigger": {"tf": "1h", "type": "touch", "px": 1}}), _b_up, NOW6)[0]
      >= {"long"}
      and ae.plan_gate(PL(long={"enabled": True, "trigger": {"tf": "5m", "type": "close_above", "px": 1}}), _b_up, NOW6)[0]
      >= {"long"})

# ②③④ — 검증
FA = ["open_long", "open_short", "wait"]
_pi = {"long": {"invalidation_px": 63726}, "short": {"invalidation_px": 65500}}
_ok = dict(base, action="open_long", setup_tf="1h", confidence=0.65, stop=63500, target=69580)
check("검증 ③ — 1h 셋업·확신 0.65·손절 2.3%·손익비 충족·무효화 바깥 → 계획",
      ae.validate(_ok, None, FA, 65000.0, SPEC, _pi)[0] == "open_long")
check("검증 ③ — setup_tf 15m → setup_tf_below_1h",
      ae.validate(dict(_ok, setup_tf="15m"), None, FA, 65000.0, SPEC, _pi)[2] == "setup_tf_below_1h")
check("검증 ③ — setup_tf 누락 → setup_tf_below_1h", ae.validate(dict(_ok, setup_tf=""), None, FA, 65000.0, SPEC)[2]
      == "setup_tf_below_1h")
check("검증 ② — confidence 0.55 → low_confidence(0.6 정확히는 통과)",
      ae.validate(dict(_ok, confidence=0.55), None, FA, 65000.0, SPEC, _pi)[2] == "low_confidence"
      and ae.validate(dict(_ok, confidence=0.6), None, FA, 65000.0, SPEC, _pi)[0] == "open_long")
check("검증 ③ — 손절 0.6% → stop_below_1pct(registry 가 0.3% 여도 1% 를 강제)",
      ae.validate(dict(_ok, stop=64610, target=67000), None, FA, 65000.0,
                  dict(SPEC, min_stop_pct=0.003))[2] == "stop_below_1pct")
check("검증 ③ — 손익비: 손절 2% · 익절 3% → (3−0.2) < 1.5×2 → rr_below_1_5",
      ae.validate(dict(_ok, stop=63700, target=66950), None, FA, 65000.0, SPEC)[2] == "rr_below_1_5")
check("검증 ③ — 손익비 경계: 손절 2% · 익절 3.2% → 통과",
      ae.validate(dict(_ok, stop=63700, target=67080), None, FA, 65000.0, SPEC)[0] == "open_long")
check("검증 ④ — 롱 손절이 계획 무효화(63,726)보다 안쪽(63,900) → stop_inside_plan_invalidation",
      ae.validate(dict(_ok, stop=63900, target=69580), None, FA, 65000.0, SPEC, _pi)[2]
      == "stop_inside_plan_invalidation")
check("검증 ④ — 숏 손절이 계획 무효화(65,500)보다 안쪽(65,200) → stop_inside_plan_invalidation",
      ae.validate(dict(_ok, action="open_short", stop=65200, target=59000), None, FA, 63500.0, SPEC, _pi)[2]
      == "stop_inside_plan_invalidation")
check("검증 ④ — 숏 손절이 무효화 바깥(65,600) · 손익비 충족 → 계획",
      ae.validate(dict(_ok, action="open_short", stop=65600, target=59000), None, FA, 63500.0, SPEC, _pi)[0]
      == "open_short")
check("검증 — 보유 중 hold/close 는 v6 조건과 무관", ae.validate(dict(base, action="hold", setup_tf="15m", confidence=0.1),
                                                          {"x": 1}, ["hold", "close"], 1.0, SPEC)[0] == "hold")

# tick — 게이트 통합(실제 trend_gate·plan_gate)
os.environ["ANTHROPIC_API_KEY"] = "test"
called = []


def must_not_call(s, u):
    called.append(1)
    raise AssertionError("v6 게이트로 막힌 틱에서 API 를 불렀다")


def ro6(t4, td, last_1h):
    r1 = mkrows(200, t0=NOW6 - 200 * H)
    r1[-1] = dict(r1[-1], c=last_1h, h=max(r1[-1]["h"], last_1h), l=min(r1[-1]["l"], last_1h))   # 마지막 닫힌 1h 봉
    r15 = mkrows(120, start=last_1h, t0=NOW6 - 120 * (H // 4), tf_ms=H // 4)

    def f(sym, tf):
        return {"15m": r15, "1h": r1, "4h": t4, "1d": td}[tf]
    return f


T4D = lin(80, 90000, 0.997, 4 * H, t0=NOW6 - 81 * 4 * H)       # 4h 하락
TDF = lin(40, 66000, 1.0, 24 * H, t0=NOW6 - 41 * 24 * H)        # 1d 평평
kw6 = dict(trades=[], cap=CAP, pot=100.0, margin_next=100.0, spec=SPEC, now_ms=NOW6,
           cfg={"directions": ["long", "short"]}, count=ae.load_count(), history=[], tick_kind="hourly")
ae._create = must_not_call
rec, sg, cp = ae.tick(position=None, blocked_dirs=set(), can_enter=True, rows_of=ro6(T4D, TDF, 65000.0), plan=PL(),
                      **kw6)
_f6 = json.loads(rec["features"])
check("tick ① ④ — 4h 하락(롱 금지) + 숏 트리거 미충족 → 판단 호출 없음 · gated · 대기", not called and sg is None
      and cp is None and rec["code_action"] == "gated" and rec["decision"] == "wait"
      and _f6["v6"]["gate_blocked"] == ["long", "short"], (called, rec["code_action"], _f6.get("v6")))
check("tick gated — 이유 두 줄(추세·계획)이 기록·로그에 남는다",
      any("v6 trend rule" in n for n in _f6["notes"]) and any("v6 plan rule" in n for n in _f6["notes"])
      and ae.summary_line(rec).startswith("[ai-elliott] 대기 — v6 게이트"))
rec, sg, cp = ae.tick(position=None, blocked_dirs=set(), can_enter=True, rows_of=ro6(T4D, TDF, 65000.0), plan=None,
                      **dict(kw6, now_ms=NOW6))
check("tick ④ — 계획 인자 없음 → 계획 파일을 읽는다(load_plan)", rec["code_action"] in ("gated", None)
      and json.loads(rec["features"])["v6"]["plan"]["status"] in ("active", "expired", "missing"))
seen6 = {}


def ans6(d):
    def f(s, u):
        seen6["user"] = u
        return fake_resp(json.dumps(dict(base, **d)))
    return f


ae._create = ans6(dict(action="open_short", setup_tf="1h", confidence=0.65, stop=65600, target=59000))
rec, sg, cp = ae.tick(position=None, blocked_dirs=set(), can_enter=True, rows_of=ro6(T4D, TDF, 63600.0), plan=PL(),
                      **kw6)
check("tick ① ④ — 4h 하락 + 숏 트리거 충족 → 허용 = 숏·대기, 판단 호출, 숏 진입 신호",
      '"allowed_actions":["open_short","wait"]' in seen6["user"] and sg is not None and sg["direction"] == "short"
      and sg["stop"] == 65600, (sg, seen6.get("user", "")[:200]))
check("tick — 입력에 trend·plan·v6 진입 규칙", all(k in seen6["user"] for k in ('"trend"', '"plan"', '"entry_rules_v6"',
                                                                              '"min_confidence":0.6')))
ae._create = ans6(dict(action="open_short", setup_tf="1h", confidence=0.5, stop=65600, target=59000))
rec, sg, cp = ae.tick(position=None, blocked_dirs=set(), can_enter=True, rows_of=ro6(T4D, TDF, 63600.0), plan=PL(),
                      **kw6)
check("tick ② — 확신 0.5 숏 → 진입 없음 · ignored:low_confidence", sg is None
      and rec["code_action"] == "ignored:low_confidence")
_pos6 = dict(symbol="BTC", pattern=ae.PATTERN, direction="long", entry_price=64000.0, stop=63000.0, target=67000.0,
             entry_ts=NOW6 - 5 * H, entry_date="2026-11-16", live_mode=True, size_usd=100.0)
ae._create = ans6(dict(action="hold"))
rec, sg, cp = ae.tick(position=_pos6, blocked_dirs=set(), can_enter=True, rows_of=ro6(T4D, TDF, 65000.0), plan=None,
                      **kw6)
check("tick — 보유 중엔 게이트가 판단을 막지 않는다(hold/close 판단은 계속)", rec["decision"] == "hold"
      and rec["code_action"] != "gated" and '"allowed_actions":["hold","close"]' in seen6["user"])
ae._create = _orig_create
os.environ.pop("ANTHROPIC_API_KEY", None)

# 지시문 v6 · registry
check("지시문 v6 — 24건 부검 사실·네 규칙을 적는다", all(k in ae.SYSTEM for k in (
    "This is version 6", "7 wins, 17 losses", "setup_tf is 1h, 4h or 1d", "confidence is at least 0.6",
    "the stop is 1%-8%", "not inside the plan's invalidation price", "1.5 times the stop distance",
    "trend is computed by code", "a long is unavailable while either is down", "plan is the desk's current trade plan",
    "honest probability that price reaches the target before the stop", "Do not raise it to get a trade through")))
check("지시문 v6 — 바닥 잡기·추세 역행 셋업 문구가 없다(v5 의 '4h 반대 셋업 허용' 삭제)",
      "setups that trade against the 4h" not in ae.SYSTEM and "Do not buy a decline or sell a rally" in ae.SYSTEM)
check("registry — v6 버전·이력·가드", rp["ai_trader"]["prompt_version"] == ae.PROMPT_VERSION
      and rp["ai_trader"]["prompt_versions"][-1]["version"] == ae.PROMPT_VERSION
      and rp["ai_trader"]["prompt_versions"][-1]["q15_version"] == ae.PROMPT_VERSION_Q15
      and any(g.startswith("v6(2026-11-16)") for g in rp["guards"]))

# 실제 계획 파일 — 형식·방향 정합(무효화·목표가 트리거의 맞는 쪽)
REAL = json.load(io.open(ae.PLAN_FILE, encoding="utf-8"))
_a, _v = ae._iso_ms(REAL.get("as_of")), ae._iso_ms(REAL.get("valid_until"))
check("elliott_plan.json — as_of < valid_until ≤ as_of + 48시간", _a and _v and _a < _v <= _a + 48 * H, (_a, _v))
for _d, _typ in (("long", "close_above"), ("short", "close_below")):
    _p = REAL.get(_d) or {}
    _tr = _p.get("trigger") or {}
    _px, _inv, _tg = _tr.get("px"), _p.get("invalidation_px"), _p.get("targets") or []
    _side = (lambda x: x < _px) if _d == "long" else (lambda x: x > _px)
    check(f"elliott_plan.json {_d} — 트리거 {_typ}·tf ∈ 입력 시간대·무효화는 진입 반대쪽·목표는 진입 쪽",
          _tr.get("type") == _typ and _tr.get("tf") in ae.BTC_TFS and isinstance(_px, (int, float))
          and _inv is not None and _side(_inv) and _tg and all(not _side(t) for t in _tg), _p)
check("elliott_plan.json — context(현재 카운트, 한국어)와 문서 설명이 있다", len(REAL.get("context") or "") > 50
      and "검증된 신호가 아니다" in REAL.get("_doc", ""))

print(f"\n{len(fails)} failed")
raise SystemExit(1 if fails else 0)
