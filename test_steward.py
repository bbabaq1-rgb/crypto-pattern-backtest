"""
test_steward.py — 운용 점검(steward, 2026-10-26 정지·시동 권한 위임) 고정. 네트워크 없음.

  1. 규칙 상수가 registry steward_rules_2026_10_26 과 같다(사전 등록 — 한쪽만 바꾸면 깨진다)
  2. judge: S1(등급 U·n≥10·평균<0) / S2(n≥20·평균<0·기간≥28일·P<.05) 경계
  3. 주 클러스터 부트스트랩: 결정론 · 같은 주 거래는 한 덩어리 · 명백한 손실/이익의 방향
  4. 배포 단위: scheduler.adopted_regime_ok 와 같은 레짐 집합 · 라우팅 FLAT 은 배포 아님 · 정지 목록 제외
  5. 표본 범위: 꺼진 레짐의 거래는 패턴 층에 안 들어간다 · 4레짐 전부 켜진 단위만 레짐 미상('?')을 센다
  6. 실거래 장부 정의 = observation_report(method D · live_mode 또는 '실거래' 태그) · 페이퍼·A·R 제외
  7. 조치 문구: focus → ROUTING_OVERRIDES / adopted → suspended 이동 / 셀 → regimes 제외 / 1h 셀은 조치 없음
  8. 읽기 전용 — 매매 경로가 이 모듈을 import 하지 않고, 이 모듈은 쓰기·주문 호출이 없다
  9. 워크플로·배선: steward.yml(읽기 전용, dispatch), tests.yml 등록
 10. GitHub 주석: 자율 사이클 세션은 잡 로그를 못 받으므로(외부 저장소 리다이렉트) 판정을 주석으로 내보낸다
"""
import io
import json
import os
import re

import steward as sw

fails = []


def check(n, c, d=""):
    print(("PASS " if c else "FAIL ") + n + ("" if c else f" — {d}"))
    c or fails.append(n)


def T(pat, d, ed, ret, reg="bull_btc", live=True, method="D", usd=None, reason="방식D청산 ·실거래"):
    return dict(pattern=pat, direction=d, entry_date=ed, exit_date=ed, return_pct=ret, live_mode=live,
                method=method, entry_regime=reg, regime=reg, pnl_live_usd=usd, exit_reason=reason)


# ── 1. 사전 등록과 상수 ────────────────────────────────────────────────────────
reg = json.load(io.open("registry.json", encoding="utf-8"))
rules = reg.get(sw.RULES_ID) or {}
th = rules.get("thresholds", {})
check("registry 에 규칙 항목", bool(rules), sw.RULES_ID)
check("S1 문턱 = registry", th.get("S1_min_n") == sw.S1_MIN_N == 10, th)
check("S2 문턱 = registry", th.get("S2_min_n") == sw.S2_MIN_N == 20 and th.get("S2_min_span_days") == sw.S2_MIN_SPAN_DAYS == 28
      and th.get("S2_alpha") == sw.S2_ALPHA == 0.05 and th.get("boot") == sw.BOOT and th.get("seed") == sw.SEED, th)
check("확인 등급 V 목록 = registry", set(rules.get("confirmed_units", {})) == {f"{p}|{d}" for p, d in sw.CONFIRMED},
      (rules.get("confirmed_units"), sw.CONFIRMED))
check("위임 범위·사용자 영역이 적혀 있다", "delegated" in rules and "user_only" in rules
      and any("RISK_FRAC" in x for x in rules["user_only"]))

# ── 2. judge 경계 ──────────────────────────────────────────────────────────────
def st(n, mean, span=60, p=None):
    return dict(n=n, mean=mean, wins=0, usd=None, span=span, weeks=8, p=p)


check("S1: U·n=10·평균<0 → 발동", sw.judge("U", st(10, -0.01)) == ["S1"])
check("S1: n=9 → 미발동", sw.judge("U", st(9, -5.0)) == [])
check("S1: 평균 0 → 미발동(엄격 <)", sw.judge("U", st(30, 0.0)) == [])
check("S1: 등급 V 는 S1 면제", sw.judge("V", st(30, -1.0, p=0.5)) == [])
check("S2: V·n=20·기간 28·p .049 → 발동", sw.judge("V", st(20, -1.0, span=28, p=0.049)) == ["S2"])
check("S2: p .05 → 미발동(엄격 <)", sw.judge("V", st(20, -1.0, span=28, p=0.05)) == [])
check("S2: 기간 27일 → 미발동", sw.judge("V", st(40, -3.0, span=27, p=0.0)) == [])
check("S2: n=19 → 미발동", sw.judge("V", st(19, -3.0, span=60, p=0.0)) == [])
check("U 는 S1·S2 동시 발동 가능", sw.judge("U", st(25, -2.0, span=40, p=0.01)) == ["S1", "S2"])

# ── 3. 주 클러스터 부트스트랩 ───────────────────────────────────────────────────
loss = [T("x", "long", f"2026-0{1 + i // 4}-{10 + i % 4:02d}", -8.0 if i % 5 else 1.0) for i in range(24)]
gain = [dict(t, return_pct=-t["return_pct"]) for t in loss]
p1, p2 = sw.cluster_boot_p(loss), sw.cluster_boot_p(loss)
check("결정론(seed 고정)", p1 == p2, (p1, p2))
check("명백한 손실 → P(평균≥0) ≈ 0", p1 < 0.01, p1)
check("명백한 이익 → P(평균≥0) ≈ 1", sw.cluster_boot_p(gain) > 0.99)
# 한 주에 몰린 손실 20건 + 다른 9주 소폭 이익: 거래 단위면 유의해 보이지만 주 단위면 한 사건이다
burst = [T("x", "long", "2026-03-02", -8.0) for _ in range(20)] + \
        [T("x", "long", f"2026-0{4 + w // 4}-{1 + 7 * (w % 4):02d}", 3.0) for w in range(9)]
check("한 주에 몰린 손실은 주 클러스터 하나 — P 가 거래 단위보다 크다(덜 유의)", sw.cluster_boot_p(burst) > 0.05,
      sw.cluster_boot_p(burst))
check("week_key 는 ISO 주", sw.week_key("2026-10-26") == (2026, 44) and sw.week_key("2026-01-01") == (2026, 1))

# ── 4. 배포 단위 ────────────────────────────────────────────────────────────────
import scheduler as sch
for tf in ("1d", "4h"):
    for rg_field in (None, "all", ["bull_btc"], ["bear", "sideways"]):
        ap = {"pattern": "p", "direction": "long"}
        if rg_field is not None:
            ap["regimes"] = rg_field
        mine = sw.adopted_regimes(ap, tf)
        theirs = {r for r in sw.REGIMES if sch.adopted_regime_ok(ap, r, tf)}
        check(f"adopted_regimes == scheduler.adopted_regime_ok ({tf}, {rg_field})", mine == theirs, (mine, theirs))
check("1h 블록은 레짐 게이트 없음 → 4레짐", sw.adopted_regimes({"regimes": ["bear"]}, "1h") == set(sw.REGIMES))

uni = {"adopted_patterns": [{"pattern": "inverted_hammer", "direction": "long"}],
       "adopted_4h_patterns": [{"pattern": "three_soldiers_4h", "direction": "long"},
                               {"pattern": "vol_awakening_4h", "direction": "long", "regimes": "all"}],
       "adopted_1h_patterns": [{"pattern": "cascade_fade_long_1h", "direction": "long"},
                               {"pattern": "tp1_engulfing_1h", "direction": "long"}],
       "suspended_patterns": [{"pattern": "marubozu", "direction": "long", "suspended_date": "2026-10-22"}]}
routing = {"bull_btc": {"engulfing": "long", "fvg": "long"}, "bear": {"engulfing": "long", "fvg": "FLAT"},
           "bull_altseason": {"engulfing": "FLAT", "fvg": "FLAT"}, "sideways": {"engulfing": "FLAT", "fvg": "FLAT"}}
U = sw.deployed_units(uni, routing)
check("focus: FLAT 레짐은 배포 아님", U[("fvg", "long")]["regimes"] == {"bull_btc"}
      and U[("engulfing", "long")]["regimes"] == {"bull_btc", "bear"}, U.get(("fvg", "long")))
check("4h 레짐 필드 없음 → bull 둘만(scheduler 종전 동작)", U[("three_soldiers_4h", "long")]["regimes"] == {"bull_btc", "bull_altseason"})
check("정지 목록은 배포 단위가 아니다", ("marubozu", "long") not in U)
check("등급: CONFIRMED 표에 있는 단위만 V", {k for k in U if sw.tier_of(*k) == "V"} == {("vol_awakening_4h", "long"), ("cascade_fade_long_1h", "long")})

# ── 5. 표본 범위 ────────────────────────────────────────────────────────────────
trades = ([T("fvg", "long", f"2026-09-{d:02d}", -8.0, reg="bull_altseason") for d in range(1, 13)]
          + [T("fvg", "long", f"2026-10-{d:02d}", 2.0, reg="bull_btc") for d in range(12, 15)]
          + [T("inverted_hammer", "long", f"2026-07-{d:02d}", -1.0, reg=None) for d in range(1, 11)]
          + [T("engulfing", "long", f"2026-07-{d:02d}", -5.0, reg=None) for d in range(1, 12)])
out, hits = sw.evaluate(trades, uni, routing)
row = {(r["unit"], r["regime"]): r for r in out}
check("꺼진 레짐(altseason)의 fvg 손실은 패턴 층 표본에 안 들어간다", row[(("fvg", "long"), None)]["stats"]["n"] == 3
      and not row[(("fvg", "long"), None)]["hits"], row[(("fvg", "long"), None)]["stats"])
check("4레짐 전부 켜진 ih 는 레짐 미상 거래를 센다 → S1", row[(("inverted_hammer", "long"), None)]["stats"]["n"] == 10
      and row[(("inverted_hammer", "long"), None)]["hits"] == ["S1"])
check("레짐 라우팅 단위(engulfing)는 레짐 미상 거래를 안 센다", row[(("engulfing", "long"), None)]["stats"]["n"] == 0)
check("발동 목록 = ih 패턴 하나", [(h["unit"], h["regime"]) for h in hits] == [(("inverted_hammer", "long"), None)], hits)

# 셀 층 발동: three_soldiers bull_btc 셀만 손실 · 패턴 전체는 양수
ts = ([T("three_soldiers_4h", "long", f"2026-10-{d:02d}", -6.0, reg="bull_btc") for d in range(1, 11)]
      + [T("three_soldiers_4h", "long", f"2026-09-{d:02d}", 9.0, reg="bull_altseason") for d in range(1, 11)])
out2, hits2 = sw.evaluate(ts, uni, routing)
check("셀 층 S1 → regimes 에서 그 레짐 제외 조치", len(hits2) == 1 and hits2[0]["regime"] == "bull_btc"
      and "regimes = ['bull_altseason']" in hits2[0]["action"], [(h["regime"], h["action"]) for h in hits2])
# 패턴 층이 발동하면 셀 발동은 따로 세지 않는다
ts_all_bad = [dict(t, return_pct=-abs(t["return_pct"])) for t in ts]
_, hits3 = sw.evaluate(ts_all_bad, uni, routing)
check("패턴 층 발동 시 셀 발동은 포함 처리(중복 조치 없음)", [(h["layer"], h["regime"]) for h in hits3] == [("패턴", None)],
      [(h["layer"], h["regime"]) for h in hits3])
# 1h 셀(등급 U): 조치 수단이 없어 발동으로 세지 않는다(패턴 층만) — bear 셀 n11 −1% 이지만 패턴 전체는 양수
c1 = [T("tp1_engulfing_1h", "long", f"2026-10-{d:02d}", -1.0, reg="bear") for d in range(1, 12)] + \
     [T("tp1_engulfing_1h", "long", f"2026-09-{d:02d}", 3.0, reg="bull_btc") for d in range(1, 12)]
out4, hits4 = sw.evaluate(c1, uni, routing)
check("1h 셀은 조치 없음 — 발동 0", hits4 == [] and any(r.get("note") for r in out4 if r["layer"] == "셀"), hits4)

# ── 6. 장부 정의 ────────────────────────────────────────────────────────────────
mix = [T("inverted_hammer", "long", "2026-07-01", -5.0, live=False, reason="방식D청산"),        # 페이퍼
       T("inverted_hammer", "long", "2026-07-02", -5.0, live=None, reason="방식D청산 ·실거래"),  # 태그 실거래
       T("inverted_hammer", "long", "2026-07-03", -5.0, method="A"),
       T("inverted_hammer", "long", "2026-07-04", -5.0, method="R", live=False),
       dict(T("inverted_hammer", "long", "2026-07-05", None), return_pct=None)]
check("live_d: 태그 실거래만 남는다(페이퍼·A·R·수익률 없음 제외)", [t["entry_date"] for t in sw.live_d(mix)] == ["2026-07-02"])

# ── 7. 조치 문구 ────────────────────────────────────────────────────────────────
check("focus 패턴 조치 = ROUTING_OVERRIDES", "ROUTING_OVERRIDES" in sw.action_text(("fvg", "long"), U[("fvg", "long")])
      and "('bull_btc', 'fvg'): 'FLAT'" in sw.action_text(("fvg", "long"), U[("fvg", "long")]))
check("adopted_1d 패턴 조치 = suspended_patterns 이동",
      "adopted_patterns → suspended_patterns" in sw.action_text(("inverted_hammer", "long"), U[("inverted_hammer", "long")]))
check("adopted_1h 패턴 조치 = suspended_1h_patterns 이동",
      "suspended_1h_patterns" in sw.action_text(("cascade_fade_long_1h", "long"), U[("cascade_fade_long_1h", "long")]))
check("adopted_1h 셀 조치 = None", sw.action_text(("cascade_fade_long_1h", "long"), U[("cascade_fade_long_1h", "long")], "bear") is None)

# ── 8. 읽기 전용 ────────────────────────────────────────────────────────────────
src = io.open("steward.py", encoding="utf-8").read()
code = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))
check("쓰기·주문 호출 없음", not re.search(r"\.(insert|update|upsert|delete)\(|place_|close_swap|create_order|exchange", code)
      and "insert_tolerant" not in code)
check("파일 쓰기는 보고서 하나뿐", code.count('"w"') == 1 and "a.out" in code)
for f in ("scheduler.py", "paper_executor.py", "exchange.py", "sizing.py", "direction_switch.py"):
    check(f"{f} 는 steward 를 import 하지 않는다", not re.search(r"^\s*(import steward|from steward)", io.open(f, encoding="utf-8").read(), re.M))

# ── 9. 배선 ─────────────────────────────────────────────────────────────────────
wf = io.open(".github/workflows/steward.yml", encoding="utf-8").read() if os.path.exists(".github/workflows/steward.yml") else ""
check("steward.yml: dispatch + 로직 테스트 + 보고서 업로드", "workflow_dispatch" in wf and "python test_steward.py" in wf
      and "steward.py" in wf and "upload-artifact" in wf)
check("steward.yml: 매매 시크릿(OKX) 없음 — DB 읽기·텔레그램만", "OKX" not in wf and "SUPABASE_SERVICE_KEY" in wf)
check("tests.yml 에 test_steward", "test_steward.py" in io.open(".github/workflows/tests.yml", encoding="utf-8").read())

# ── 10. GitHub 주석 — 자율 사이클이 잡 로그 대신 check-runs annotations API 로 읽는다 ──────────────
ann0 = sw.annotations([], 8, 179)
check("발동 없음 → notice 한 줄, 제목 'steward' 로 시작", len(ann0) == 1 and ann0[0].startswith("::notice title=steward"), ann0)
_, hits_a = sw.evaluate(trades, uni, routing)
ann1 = sw.annotations(hits_a, 9, 40)
check("발동 → warning 줄, 제목에 규칙·본문에 단위·조치", len(ann1) == len(hits_a) == 1
      and ann1[0].startswith("::warning title=steward S1::") and "inverted_hammer·long" in ann1[0] and "조치:" in ann1[0], ann1)
check("주석은 한 줄(줄바꿈 없음)", all("\n" not in a for a in ann0 + ann1))
check("주석 상한 10(단계당 경고 주석 한도)", len(sw.annotations(hits_a * 15, 1, 1)) == 10)
check("주석은 Actions 안에서만 찍는다", 'os.environ.get("GITHUB_ACTIONS") == "true"' in src)

# ── 11. 집행 기록 — 실제 universe/registry 상태가 집행 장부와 맞는다 ──────────────────────
# 2026-10-26 첫 집행(inverted_hammer S1). 정지는 신규 진입만 — 열린 포지션 청산 tf 는 suspended 목록에서 1d 로 유지된다.
real_uni = json.load(io.open("universe.json", encoding="utf-8"))
real_reg = json.load(io.open("registry.json", encoding="utf-8"))
acts = real_reg[sw.RULES_ID].get("actions", [])
check("집행 장부: 항목마다 날짜·규칙·단위·n·평균·run", acts and all(
      a.get("date") and a.get("rule") in ("S1", "S2", "S3", "S4", "H") and a.get("unit") and a.get("run")
      and ("n" in a and "mean_pct" in a or a.get("rule") in ("S3", "H")) for a in acts), acts)
ih_act = [a for a in acts if a.get("unit", "").startswith("inverted_hammer|long")]
check("inverted_hammer S1 집행 기록(n17 −0.73%)", len(ih_act) == 1 and ih_act[0]["rule"] == "S1"
      and ih_act[0]["n"] == 17 and abs(ih_act[0]["mean_pct"] + 0.73) < 1e-9, ih_act)
check("inverted_hammer 는 adopted_patterns 에 없다",
      "inverted_hammer" not in {a["pattern"] for a in real_uni.get("adopted_patterns", [])})
ih_s = [a for a in real_uni.get("suspended_patterns", []) if a["pattern"] == "inverted_hammer"]
check("inverted_hammer 는 suspended_patterns 에 — tf 1d·규칙 id·정지일", len(ih_s) == 1 and ih_s[0].get("tf") == "1d"
      and sw.RULES_ID in ih_s[0].get("suspended_by", "") and ih_s[0].get("suspended_date") == "2026-10-26", ih_s)
ih_r = [p for p in real_reg["patterns"] if p.get("id") == "inverted_hammer"]
check("registry: 위임 규칙 정지는 suspended_steward(사용자 정지 suspended_user 와 구분)",
      len(ih_r) == 1 and ih_r[0].get("status") == "suspended_steward", [p.get("status") for p in ih_r])
_real_routing = json.load(io.open("direction_switch.json", encoding="utf-8"))["routing"]
check("정지 뒤 운용 점검은 inverted_hammer 를 배포 단위로 세지 않는다",
      ("inverted_hammer", "long") not in sw.deployed_units(real_uni, _real_routing))
import paper_executor as _pe
check("열린 ih 포지션 청산 tf = 1d(_pattern_tf 가 suspended 목록을 읽는다)", _pe._pattern_tf("inverted_hammer") == "1d")

print(f"\n{len(fails)} failed")
raise SystemExit(1 if fails else 0)
