"""
test_ai_judge_report.py — AI 판단 그림자 평가 보고(2026-10-26) 고정. 네트워크 없음(DB 는 함수 밖).

  1. 거래 색인·매칭: 방식D 만 · 판단 시각 이후 청산된 첫 거래 · 손절 판정
  2. 월 블록 부트: 결정론 · 강한 우위 p≈0 · 역우위 p≈1 · 빈 집단 None
  3. 진입 평가: 그룹 키(prompt_version 없으면 v1) · 표본 부족 / 필터 비율 / PRIMARY 충족·미충족 · 미해소 집계
  4. 청산 검토 평가: adv 정의 · 첫 exit 제안 선택 · hold-only 대조군 · 미해소 포지션 · secondary(손절률)
  5. 렌더·텔레그램 텍스트 · 빈 입력 · 보고 모듈은 읽기 전용(쓰기 호출·매매 모듈 import 없음)
  6. 배선: 워크플로(dispatch/주간/시크릿/테스트 선행) · tests.yml
  7. 확장 컬럼 없이 적재된 행의 복원(2026-10-26): kind 는 decision 어휘 → 특성 키, prompt_version 은 특성 마커,
     unreal_ret/bars_held 는 features 폴백 — 컬럼이 있을 때와 평가 결과가 같다 · SQL 백필이 같은 규칙
"""
import io
import random

import ai_judge_report as rp

fails = []


def check(n, c, d=""):
    print(("PASS " if c else "FAIL ") + n + ("" if c else f" — {d}"))
    c or fails.append(n)


def J(sym, pat, dec, judged, entry_date, kind="entry", pv="entry_v2_2026_10_26", conf=0.7, **kw):
    r = dict(kind=kind, symbol=sym, pattern=pat, direction="long", entry_date=entry_date, judged_at=judged,
             model="claude-sonnet-5-5", prompt_version=pv, decision=dec, confidence=conf,
             reasons='["r1","r2"]', tokens_in=100, tokens_out=20, latency_ms=900, code_action="live")
    r.update(kw)
    return r


def T(sym, pat, entry_date, exit_date, ret_pct, method="D", reason="maxhold", live=True, pnl=None):
    return dict(method=method, symbol=sym, pattern=pat, direction="long", entry_date=entry_date,
                exit_date=exit_date, return_pct=ret_pct, exit_reason=reason, live_mode=live, pnl_live_usd=pnl)


# ── 1. 색인·매칭 ────────────────────────────────────────────────────────────
trades = [T("SOL", "fvg", "2026-10-24", "2026-10-30", 3.0), T("SOL", "fvg", "2026-10-24", "2026-10-26", -8.2, reason="stop"),
          T("SOL", "fvg", "2026-10-24", "2026-11-02", 1.0, method="A"), T("ADA", "fvg", "2026-10-24", "2026-10-28", 2.0, method="R")]
idx = rp.d_trade_index(trades)
check("방식D 만 색인(A·R 제외)", set(idx) == {("SOL", "fvg", "long", "2026-10-24")} and len(idx[("SOL", "fvg", "long", "2026-10-24")]) == 2)
check("ret 는 소수(return_pct/100)·청산일 순 정렬",
      [round(t["ret"], 4) for t in idx[("SOL", "fvg", "long", "2026-10-24")]] == [-0.082, 0.03])
j = J("SOL", "fvg", "take", "2026-10-27T04:00:00Z", "2026-10-24")
check("판단 시각 이후 청산된 첫 거래를 고른다", rp.match_trade(idx, j)["ret"] == 0.03)
check("매칭 없음 → None", rp.match_trade(idx, J("XRP", "fvg", "take", "2026-10-27T04:00:00Z", "2026-10-24")) is None)
check("손절 판정: '손절'+음수 / reason stop → True, 수익 '손절' 오라벨 → False",
      rp.is_stop_trade(dict(exit_reason="손절(OKX algo) ·실거래", ret=-0.082)) and rp.is_stop_trade(dict(exit_reason="stop", ret=-0.082))
      and not rp.is_stop_trade(dict(exit_reason="손절(OKX algo)", ret=0.0056)) and not rp.is_stop_trade(dict(exit_reason="maxhold", ret=-0.03)))

# ── 2. 월 블록 부트 ─────────────────────────────────────────────────────────
rnd = random.Random(7)
A = [(f"2026-{m:02d}", 0.05 + rnd.gauss(0, 0.01)) for m in (8, 9, 10) for _ in range(20)]
B = [(f"2026-{m:02d}", -0.02 + rnd.gauss(0, 0.01)) for m in (8, 9, 10) for _ in range(20)]
p1 = rp.month_block_boot(A, B)
check("부트 결정론(같은 시드 → 같은 p)", p1 == rp.month_block_boot(A, B))
check("강한 우위 → p≈0", p1 is not None and p1 < 0.01, p1)
check("역우위 → p≈1", rp.month_block_boot(B, A) > 0.99)
check("빈 집단 → None", rp.month_block_boot([], B) is None and rp.month_block_boot(A, []) is None)
check("한 달뿐이어도 돈다(월 1개 블록)", rp.month_block_boot([("2026-10", 0.1)] * 5, [("2026-10", -0.1)] * 5) == 0.0)

# ── 3. 진입 평가 ────────────────────────────────────────────────────────────
def make_entry(n_take, n_other, take_ret, other_ret, pv="entry_v2_2026_10_26", seed=1, start_day=1):
    rnd = random.Random(seed)
    js, ts = [], []
    k = 0
    for dec, n, mu in (("take", n_take, take_ret), ("skip", n_other // 2, other_ret), ("reduce", n_other - n_other // 2, other_ret)):
        for _ in range(n):
            k += 1
            m = 8 + (k % 3)
            d = f"2026-{m:02d}-{start_day + (k % 20):02d}"
            sym = f"S{k}"
            js.append(J(sym, "fvg", dec, f"{d}T00:05:00Z", d, pv=pv, conf=0.6 + 0.3 * (dec == "take")))
            ts.append(T(sym, "fvg", d, f"2026-{m:02d}-28", 100 * (mu + rnd.gauss(0, 0.01)), reason=("stop" if mu < 0 else "maxhold"), pnl=1.0))
    return js, ts

js, ts = make_entry(50, 30, 0.04, -0.03)
ev = rp.entry_eval(js, ts)
g = ev[("claude-sonnet-5-5", "entry_v2_2026_10_26")]
check("그룹 키 = (model, prompt_version)", list(ev) == [("claude-sonnet-5-5", "entry_v2_2026_10_26")])
check("집계: 판단 80 · 해소 80 · take 50 / other 30", g["n_judged"] == 80 and g["n_resolved"] == 80 and g["n_take"] == 50 and g["n_other"] == 30)
check("diff = mean(take) − mean(other) 양수, p 작음", g["diff"] > 0.05 and g["boot_p"] < 0.01)
check("필터 비율 = (skip+reduce)/판단", abs(g["filter_share"] - 30 / 80) < 1e-9)
check("손절률: other 전부 손절, take 0", g["stop_other"] == 1.0 and g["stop_take"] == 0.0)
check("PRIMARY 충족 문구(n≥60·diff≥1%p·other<0·p<.10)", g["verdict"].startswith("PRIMARY 충족"), g["verdict"])
check("실현 $ 간이 지표: 전부 80 vs take 만 50", g["live_pnl_all"] == 80.0 and g["live_pnl_take_only"] == 50.0)
check("확신 구간 보정표가 있다", any(k.startswith("take") for k in g["calibration"]) and any(k.startswith("other") for k in g["calibration"]))
js2, ts2 = make_entry(50, 30, 0.01, 0.012)
g2 = rp.entry_eval(js2, ts2)[("claude-sonnet-5-5", "entry_v2_2026_10_26")]
check("효과 없음 → PRIMARY 미충족", g2["verdict"] == "PRIMARY 미충족", g2["verdict"])
js3, ts3 = make_entry(20, 10, 0.04, -0.03)
g3 = rp.entry_eval(js3, ts3)[("claude-sonnet-5-5", "entry_v2_2026_10_26")]
check("n<60 → 표본 부족", g3["verdict"].startswith("표본 부족"), g3["verdict"])
js4, ts4 = make_entry(80, 0, 0.04, -0.03)
js4 += [J("Z1", "fvg", "skip", "2026-10-01T00:05:00Z", "2026-10-01")]
ts4 += [T("Z1", "fvg", "2026-10-01", "2026-10-05", -8.2, reason="stop")]
g4 = rp.entry_eval(js4, ts4)[("claude-sonnet-5-5", "entry_v2_2026_10_26")]
check("skip+reduce 비율 10% 미만 → '필터로 기능 안 함'", "필터로 기능 안 함" in g4["verdict"], g4["verdict"])
js5 = [J("A1", "fvg", "take", "2026-10-20T00:05:00Z", "2026-10-20", pv=None), J("A2", "fvg", None, "2026-10-20T00:05:00Z", "2026-10-20", pv=None, error="http_529"),
       J("A3", "fvg", "skip", "2026-10-21T00:05:00Z", "2026-10-21", pv=None, code_action="slot_full"),
       J("B1", "fvg", "hold", "2026-10-21T00:05:00Z", "2026-10-21", kind="exit", pv="exit_v1_2026_10_26")]
g5 = rp.entry_eval(js5, [T("A1", "fvg", "2026-10-20", "2026-10-25", 2.0)])
k5 = ("claude-sonnet-5-5", "v1")
check("prompt_version 없는 구 행은 'v1' 로 묶고 exit 행은 진입 평가에서 제외", list(g5) == [k5])
check("오류 행은 n_error · 미해소는 pending · code_action 분포", g5[k5]["n_error"] == 1 and g5[k5]["pending"] == 1 and g5[k5]["n_resolved"] == 1
      and g5[k5]["code_action"] == {"live": 2, "slot_full": 1})
check("토큰 합계·지연 중앙", g5[k5]["tokens_in"] == 300 and g5[k5]["latency_med"] == 900)

# ── 4. 청산 검토 평가 ────────────────────────────────────────────────────────
FEE = rp.FEE
def X(sym, dec, judged, unreal, entry_date="2026-10-20", bars=5, pv="exit_v1_2026_10_26"):
    return J(sym, "fvg", dec, judged, entry_date, kind="exit", pv=pv, unreal_ret=unreal, bars_held=bars, mark_px=1.0, code_action="open")

xj = [X("P1", "hold", "2026-10-21T00:05:00Z", 0.01), X("P1", "exit", "2026-10-22T00:05:00Z", 0.03), X("P1", "exit", "2026-10-23T00:05:00Z", 0.05),
      X("P2", "hold", "2026-10-21T00:05:00Z", -0.02), X("P2", "hold", "2026-10-22T00:05:00Z", -0.03),
      X("P3", "exit", "2026-10-21T00:05:00Z", -0.01),      # 미해소(거래 없음)
      X("P4", "exit", "2026-10-25T00:05:00Z", 0.02)]       # 거래 청산(10/24) 뒤에 붙은 검토 → 매칭 불가(unmatched)
xt = [T("P1", "fvg", "2026-10-20", "2026-10-30", -8.2, reason="손절(OKX algo) ·실거래"),
      T("P2", "fvg", "2026-10-20", "2026-10-30", 4.0),
      T("P4", "fvg", "2026-10-20", "2026-10-24", 1.0)]
xe = rp.exit_eval(xj, xt, min_n=1)
gx = xe[("claude-sonnet-5-5", "exit_v1_2026_10_26")]
check("exit 평가: 행 7 · hold/exit 집계", gx["n_rows"] == 7 and gx["decisions"] == {"hold": 3, "exit": 4})
check("첫 exit 제안(P1 10/22, unreal 0.03) 기준 adv = (0.03−FEE) − (−0.082)",
      gx["n_exit"] == 1 and abs(gx["mean_adv_exit"] - ((0.03 - FEE) - (-0.082))) < 1e-9, gx)
check("hold-only(P2) 는 첫 검토 기준 adv = (−0.02−FEE) − 0.04", gx["n_hold"] == 1 and abs(gx["mean_adv_hold"] - ((-0.02 - FEE) - 0.04)) < 1e-9, gx)
check("미해소 포지션(P3) · 매칭 불가(P4) 집계", gx["n_pos_open"] == 1 and gx["n_unmatched"] == 1, (gx["n_pos_open"], gx["n_unmatched"]))
check("청산 뒤에 붙은 검토(P4: 거래 10/24 청산, 검토 10/25)는 어느 집단에도 안 들어간다", gx["n_exit"] + gx["n_hold"] == 2)
check("secondary: exit 제안 포지션 손절률 1.0 > hold-only 0.0", gx["stop_rate_exit"] == 1.0 and gx["stop_rate_hold"] == 0.0 and gx["secondary_ok"])
check("min_n=1 에서 PRIMARY 충족 문구가 원칙 ② 개정·사용자 결정을 명시", "원칙 ②" in gx["verdict"] and "사용자 결정" in gx["verdict"], gx["verdict"])
gx2 = rp.exit_eval(xj, xt)[("claude-sonnet-5-5", "exit_v1_2026_10_26")]
check("기본 min_n=40 → 표본 부족", gx2["verdict"].startswith("표본 부족"), gx2["verdict"])
# 효과 없음: exit 제안이 실제보다 나쁜 시점
xj3 = [X(f"Q{i}", "exit", "2026-10-21T00:05:00Z", -0.03, entry_date="2026-10-20") for i in range(45)] + \
      [X(f"H{i}", "hold", "2026-10-21T00:05:00Z", -0.03, entry_date="2026-10-20") for i in range(45)]
xt3 = [T(f"Q{i}", "fvg", "2026-10-20", "2026-10-30", 2.0) for i in range(45)] + [T(f"H{i}", "fvg", "2026-10-20", "2026-10-30", 2.0) for i in range(45)]
gx3 = rp.exit_eval(xj3, xt3)[("claude-sonnet-5-5", "exit_v1_2026_10_26")]
check("exit 제안이 손해(adv<0) → PRIMARY 미충족", gx3["verdict"] == "PRIMARY 미충족" and gx3["mean_adv_exit"] < 0, gx3["verdict"])

# ── 5. 렌더·빈 입력·읽기 전용 ─────────────────────────────────────────────────
entry, exits, md = rp.build(js + xj, ts + xt, "2026-10-26")
check("렌더: 두 표 + 근거 상위 + 읽기 전용 문구", "## 1. 진입 판단" in md and "## 2. 청산 검토" in md and "근거 상위" in md and "실거래 무변경" in md)
check("렌더: p 값 3자리", "| 0.000 |" in md or "| 0.00" in md, md[:200])
tg = rp.telegram_text(entry, exits, "2026-10-26")
check("텔레그램 텍스트 3500자 이내·그룹 줄 포함", len(tg) <= 3500 and "진입 entry_v2_2026_10_26" in tg and "청산 exit_v1_2026_10_26" in tg)
e0, x0, md0 = rp.build([], [], "t")
check("빈 입력에도 예외 없음", e0 == {} and x0 == {} and "0건" in md0 and "기록 없음" in rp.telegram_text(e0, x0))
check("reasons 집계: skip/reduce/exit 만", rp.reasons_tally(js + xj)[0][1] >= 30 and all(n > 0 for _, n in rp.reasons_tally(js + xj)))
src = io.open("ai_judge_report.py", encoding="utf-8").read()
check("보고 모듈은 매매 모듈을 import 하지 않는다", not any(f"import {m}" in src for m in ("exchange", "paper_executor", "scheduler", "ai_judge\n", "detlib")))
check("보고 모듈은 DB 에 쓰지 않는다(select 만)", all(w not in src for w in (".insert(", ".update(", ".delete(", ".upsert(")) and ".select(" in src)
check("기준 상수가 사전 등록과 같다", rp.ENTRY_PRIMARY_DIFF == 0.01 and rp.EXIT_PRIMARY_ADV == 0.005 and rp.BOOT_P == 0.10
      and rp.MIN_ENTRY_N == 60 and rp.MIN_EXIT_N == 40 and rp.FILTER_SHARE == (0.10, 0.70) and rp.BOOT_N == 1000)
import paper_executor as pe
check("가상 청산 수수료 = 체결엔진 FEE", rp.FEE == pe.FEE)

# ── 6. 배선 ────────────────────────────────────────────────────────────────
wf = io.open(".github/workflows/ai_judge_report.yml", encoding="utf-8").read()
check("워크플로: dispatch + 주간 schedule + 경로 트리거", "workflow_dispatch" in wf and "schedule:" in wf and "ai_judge_report.py" in wf)
check("워크플로: 테스트 선행 · --notify(push 는 알림 없음) · Supabase/Telegram 시크릿", "python test_ai_judge_report.py" in wf and "'--notify'" in wf
      and "github.event_name == 'push'" in wf
      and "SUPABASE_SERVICE_KEY: ${{ secrets.SUPABASE_SERVICE_KEY }}" in wf and "TELEGRAM_CHAT_ID" in wf)
check("워크플로: OKX·ANTHROPIC 키를 받지 않는다(읽기 전용 보고)", "OKX_KEY" not in wf and "ANTHROPIC_API_KEY" not in wf)
check("tests.yml 에 test_ai_judge_report", "test_ai_judge_report.py" in io.open(".github/workflows/tests.yml", encoding="utf-8").read())

# ── 7. 확장 컬럼 없이 적재된 행의 복원 (2026-10-26) ───────────────────────────
# 배경: 2026-10-26 04:00Z 틱에서 AI 판단 7행이 전부 유실됐다(insert_tolerant 제거 한도). 한도를 올린 뒤에도 사용자가
# SQL 을 재실행하기 전까지는 kind/prompt_version/unreal_ret/bars_held 가 빠진 채 적재된다 — 그 행들이 entry 로
# 오분류되거나 'v1' 로 갈리면 사전 등록 표본(n≥60)이 쪼개진다. decision 과 features(JSON) 는 항상 남으므로 거기서 되살린다.
import json as _json
import ai_judge as aj
check("복원 상수가 ai_judge 와 같다", rp.ENTRY_V2 == aj.PROMPT_VERSION and rp.EXIT_V1 == aj.EXIT_PROMPT_VERSION
      and tuple(rp.EXIT_DECISIONS) == tuple(aj.EXIT_DECISIONS) and not set(aj.DECISIONS) & set(aj.EXIT_DECISIONS))
_rows = [dict(date=f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", ts=1_700_000_000_000 + i * 86_400_000,
              o=100 + i * 0.1, h=101 + i * 0.1, l=99 + i * 0.1, c=100.5 + i * 0.1, v=1000.0 + i) for i in range(80)]
_ef = aj.features(_rows, 79, dict(pattern="fvg", direction="long", tf="1d", stop=92.0, symbol="SOL"), {"book": [], "max_pos": 13})
_xf = aj.exit_features(_rows, 60, 79, dict(pattern="fvg", direction="long", tf="1d", entry_price=_rows[60]["c"], stop=90.0), {})
check("v2 진입 마커 키는 실제 진입 특성에 있고 청산 특성에는 없다", all(k in _ef for k in rp.V2_MARKER_KEYS) and not any(k in _xf for k in rp.V2_MARKER_KEYS))
check("청산 마커 키는 실제 청산 특성에 있고 진입 특성에는 없다", all(k in _xf for k in rp.EXIT_MARKER_KEYS) and not any(k in _ef for k in rp.EXIT_MARKER_KEYS))
def _E(**kw):   # 확장 컬럼이 전부 빠진 entry 행(kind/prompt_version None)
    r = J("SOL", "fvg", "take", "2026-10-27T04:00:00Z", "2026-10-24", kind=None, pv=None, features=_json.dumps(_ef)); r.update(kw); return r
def _X(**kw):   # 확장 컬럼이 전부 빠진 exit 행
    r = J("SOL", "fvg", "exit", "2026-10-27T04:00:00Z", "2026-10-24", kind=None, pv=None, features=_json.dumps(_xf)); r.update(kw); return r
check("kind 복원: decision 어휘로(take/reduce/skip → entry, hold/exit → exit)",
      rp.kind_of(_E()) == "entry" and rp.kind_of(_E(decision="reduce")) == "entry" and rp.kind_of(_X()) == "exit" and rp.kind_of(_X(decision="hold")) == "exit")
check("kind 복원: 오류 행(decision 없음)은 특성 키로", rp.kind_of(_E(decision=None)) == "entry" and rp.kind_of(_X(decision=None)) == "exit")
check("kind 컬럼이 있으면 그대로", rp.kind_of(_E(kind="exit")) == "exit")
check("prompt_version 복원: exit → EXIT_V1 · v2 특성 → ENTRY_V2 · 마커 없으면 v1 · 있으면 그대로",
      rp.pv_of(_X()) == rp.EXIT_V1 and rp.pv_of(_E()) == rp.ENTRY_V2
      and rp.pv_of(_E(features='{"ret_5": 0.01}')) == rp.V1_LABEL and rp.pv_of(_E(prompt_version="zzz")) == "zzz")
check("깨진·빈 features 에도 예외 없음(entry / v1)", rp.kind_of(_E(decision=None, features="{broken")) == "entry"
      and rp.pv_of(_E(features=None)) == rp.V1_LABEL and rp.feat_of(_E(features="[1,2]")) == {})
_r = _E(); _f1 = rp.feat_of(_r); _r["features"] = '{"ret_5": 0.01}'
check("features 문자열이 바뀌면 캐시를 버린다", rp.feat_of(_r) == {"ret_5": 0.01} and _f1 is not rp.feat_of(_r))
check("col_or_feat: 컬럼 우선, 없으면 features", rp.col_or_feat(_X(), "unreal_ret") == _xf["unreal_ret"] and rp.col_or_feat(_X(unreal_ret=0.5), "unreal_ret") == 0.5
      and rp.col_or_feat(_E(), "bars_held") is None)
_mix = [_E(), _X()]
check("kind 없는 exit 행은 진입 집계에 안 들어가고 청산 집계에 들어간다",
      list(rp.entry_eval(_mix, []).values())[0]["n_judged"] == 1 and list(rp.exit_eval(_mix, []).values())[0]["n_rows"] == 1
      and list(rp.entry_eval(_mix, [])) == [("claude-sonnet-5-5", rp.ENTRY_V2)] and list(rp.exit_eval(_mix, [])) == [("claude-sonnet-5-5", rp.EXIT_V1)])
_js_b = [dict(j, kind=None, prompt_version=None, features=_json.dumps(_ef)) for j in js]
check("확장 컬럼 없이 적재된 entry 행도 같은 그룹·같은 평가 결과", rp.entry_eval(_js_b, ts) == rp.entry_eval(js, ts))
_xj_b = [dict(j, kind=None, prompt_version=None, unreal_ret=None, bars_held=None, mark_px=None, live_mode=None,
              features=_json.dumps(dict(_xf, unreal_ret=j["unreal_ret"], bars_held=j["bars_held"]))) for j in xj]
check("확장 컬럼 없이 적재된 exit 행도 같은 그룹·같은 평가 결과(unreal_ret/bars_held 를 features 에서)",
      rp.exit_eval(_xj_b, xt, min_n=1) == rp.exit_eval(xj, xt, min_n=1))
_sql = io.open("supabase_schema_ai_judge.sql", encoding="utf-8").read()
check("SQL 백필: 보고와 같은 어휘·마커로 kind/prompt_version/unreal_ret/bars_held 를 되살린다(멱등 where … is null)",
      "where kind is null" in _sql and "where prompt_version is null" in _sql and all(v in _sql for v in (rp.ENTRY_V2, rp.EXIT_V1, "'v1'"))
      and '"stop_atr"' in _sql and '"bars_held"' in _sql and "features::jsonb ->> 'unreal_ret'" in _sql and "decision in ('hold', 'exit')" in _sql)

print(f"\n{len(fails)} failed")
raise SystemExit(1 if fails else 0)
