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
# v2(같은 날 사용자 지시 "15분봉~4시간봉 등 여러 봉을 분석해 가며 더 작은 사이즈의 신호를 찾아서 매매")
check("v3 — 버전·effort high·토큰 상한(비스트리밍 10분 한도 안)",
      ae.PROMPT_VERSION == "elliott_v3_2026_10_28" and ae.EFFORT == "high"
      and 3600 * ae.MAX_TOKENS / 128000 < 600, (ae.PROMPT_VERSION, ae.EFFORT, ae.MAX_TOKENS))
check("v2 — BTC 15m·1h·4h·1d, ETH 15m·1h·4h", ae.BTC_TFS == ("15m", "1h", "4h", "1d")
      and ae.ETH_TFS == ("15m", "1h", "4h") and all(tf in ae.BARS and tf in ae.ZZ_PCT and tf in ae.TF_MS
                                                    for tf in ae.BTC_TFS))
check("v2 — 15m 96봉(24시간)·피벗 임계가 시간대와 함께 커진다", ae.BARS["15m"] == 96
      and ae.ZZ_PCT["15m"] < ae.ZZ_PCT["1h"] < ae.ZZ_PCT["4h"] < ae.ZZ_PCT["1d"])
check("v2 — 15m 수집 창은 짧게(OKX 일반 캔들 범위 15일 안)", 0 < ae.FETCH_DAYS["15m"] <= 14)
check("v2 — 프롬프트가 15m·1h·4h 작은 차수 매매를 지시하고 '대부분 대기' 기본값이 없다",
      all(k in ae.SYSTEM for k in ("15m", "1h and 4h", "lower-degree", "setup_tf"))
      and "most hours should be wait" not in ae.SYSTEM and "Waiting is the default" not in ae.SYSTEM)
check("v2 — 손익비 1.5·비용 차감·무효화 지점 손절은 그대로", all(k in ae.SYSTEM for k in
      ("1.5 times the stop distance", "0.2% of round-trip cost", "invalidates the lower-degree count")))
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
ae._create = answer(dict(action="open_long", setup_tf="15m", structure="double_zigzag", stop=round(last_c * 0.99),
                         target=round(last_c * 1.03), wave_view="15m: (ii) 끝 → (iii)", invalidation="저점 이탈"))
rec, sg, cp = ae.tick(position=None, blocked_dirs=set(), can_enter=True, **kw)
check("tick 이 BTC 15m·1h·4h·1d, ETH 15m·1h·4h 를 읽는다", set(asked) == {("BTC", t) for t in ae.BTC_TFS}
      | {("ETH", t) for t in ae.ETH_TFS}, sorted(set(asked)))
_f = json.loads(rec["features"])
check("기록 특성에 setup_tf·15m 봉 수·15m 피벗", _f["setup_tf"] == "15m" and _f["bars_15m"] > 90
      and _f["pivots_15m"])
check("기록 특성에 structure·시간대별 RSI·다이버전스", _f["structure"] == "double_zigzag"
      and set(_f["rsi14"]) == set(ae.BTC_TFS) and set(_f["divergence"]) == set(ae.BTC_TFS))
check("입력에 RSI·EWO·다이버전스", all(k in seen["user"] for k in ('"rsi14"', '"ewo_pct"', '"divergence"')))
check("입력에 15m 데이터", '"15m":{"bars_t_o_h_l_c_v"' in seen["user"])
check("로그 한 줄에 시간대·형태", ae.summary_line(rec).startswith("[ai-elliott] open_long 15m/double_zigzag "))
check("평탄 + 롱 → 진입 신호(손절·익절 가격 그대로)", sg and sg["direction"] == "long" and cp is None
      and sg["stop"] == round(last_c * 0.99) and sg["target"] == round(last_c * 1.03)
      and sg["pattern"] == ae.PATTERN and sg["ai_elliott"] is True and sg["_ai_rec"] is rec)
check("신호봉 = 마지막 닫힌 봉", sg["ts"] == ae.closed(R1, "1h", NOW)[-1]["ts"])
check("기록 행: kind·모델·버전·결정·크기 1.0·근거(JSON)", rec["kind"] == "elliott_btc" and rec["model"] == ae.MODEL
      and rec["prompt_version"] == ae.PROMPT_VERSION and rec["decision"] == "open_long" and rec["size_mult"] == 1.0
      and json.loads(rec["reasons"])[0] == "15m: (ii) 끝 → (iii)" and rec["direction"] == "long")
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

print(f"\n{len(fails)} failed")
raise SystemExit(1 if fails else 0)
