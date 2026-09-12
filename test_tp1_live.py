"""
test_tp1_live.py — 사용자 강제 실행 tp1_engulfing_1h(익절 +1% / 손절 −8% · $70(2026-09-10 $30→$70 상향) · 3x · top20 · 1포지션) 고정
(2026-09-09 사용자 결정 "그냥 30달러만 강제 진행해볼수 있어?").

이 규칙은 검증을 통과하지 못했다(tp_1h REJECTED). 여기서 고정하는 것은 '통과'가 아니라
**사용자가 정한 사양이 코드에 그대로 박혀 있고, 기존 경로(cascade·1d/4h 패턴)가 안 바뀌었다**는 것이다.

  1. exit_barriers — pct_barrier / atr_barrier 산식, 스케줄러·체결엔진 공용
  2. barriers_of — 비대칭 배리어를 대칭 복원하지 않는다(target 유실 시 +1% 로 재구성)
  3. live_cap — registry 값, exit_spec 없으면 무효, 체결엔진 소스가 캡 경로를 탄다
  4. 등재 — registry/universe 항목 정합(모듈·방향·tf·코호트), 스케줄러 소스가 cohort·detlib 로더 사용
  5. 기존 경로 불변 — cascade 배리어 수치 동일, 1d/4h 패턴 exit_spec 없음, 사이징 상수 불변
  6. eval_I 가 pct 배리어로도 검증 프레임(tp_1h.crossings/_resolve)과 같은 청산을 낸다

실행: python test_tp1_live.py
"""
import io
import json
import random
import sys

import exit_barriers as xb
import intraday_lab as ilab
import paper_executor as pe
import scheduler as sch
import sizing

fails = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f" — {detail}"))
    cond or fails.append(name)


def mkrows(n, seed=1, start=100.0):
    rng = random.Random(seed)
    rows, px = [], start
    for i in range(n):
        o = px
        c = o * (1 + rng.gauss(0, 0.01))
        h = max(o, c) * (1 + abs(rng.gauss(0, 0.004)))
        l = min(o, c) * (1 - abs(rng.gauss(0, 0.004)))
        rows.append(dict(date=f"2026-01-{1 + i // 24:02d}", ts=1_700_000_000_000 + i * 3_600_000,
                         o=o, h=h, l=l, c=c, v=1000 + rng.random() * 100))
        px = c
    return rows


PAT = "tp1_engulfing_1h"
reg = json.load(open("registry.json", encoding="utf-8"))
uni = json.load(open("universe.json", encoding="utf-8"))
rp = next(p for p in reg["patterns"] if p["id"] == PAT)
spec, cap = rp["exit_spec"], rp["live_cap"]

# ── 1. exit_barriers ─────────────────────────────────────────────────────────
check("spec_type: pct_barrier / atr_barrier(k_atr 만 있어도) / 없음",
      xb.spec_type(spec) == "pct_barrier" and xb.spec_type({"k_atr": 1.5}) == "atr_barrier"
      and xb.spec_type({}) is None and xb.spec_type(None) is None)
st, tg, info = xb.barriers(spec, None, 0, 100.0, "long")
check("pct 롱: 손절 92 / 익절 101 (진입 100)", abs(st - 92.0) < 1e-9 and abs(tg - 101.0) < 1e-9, (st, tg))
st_s, tg_s, _ = xb.barriers(spec, None, 0, 100.0, "short")
check("pct 숏: 손절 108 / 익절 99", abs(st_s - 108.0) < 1e-9 and abs(tg_s - 99.0) < 1e-9, (st_s, tg_s))
check("pct info 에 tp/sl 비율", info == dict(tp_pct=0.01, sl_pct=0.08), info)
rows = mkrows(300, seed=11)
li = len(rows) - 1
cspec = pe.EXIT_SPECS["cascade_fade_long_1h"]
ba = xb.barriers(cspec, rows, li, rows[li]["c"], "long")
atr = ilab.atr_series(rows, cspec["atr_period"])[li]
check("atr 경로: 종전 산식(±k×ATR)과 동일", ba is not None
      and abs(ba[0] - round(rows[li]["c"] - cspec["k_atr"] * atr, 8)) < 1e-9
      and abs(ba[1] - round(rows[li]["c"] + cspec["k_atr"] * atr, 8)) < 1e-9, ba)
check("atr 미산출(짧은 rows)이면 None → 진입 안 함", xb.barriers(cspec, rows[:5], 4, 100.0, "long") is None)
check("describe 가 두 타입을 구분", "익절 +1%" in xb.describe(spec) and "xATR" in xb.describe(cspec))

# ── 2. barriers_of — 비대칭 복원 ────────────────────────────────────────────
s0, t0 = pe.barriers_of(dict(pattern=PAT, direction="long", entry_price=100.0, stop=92.0, target=None))
check("barriers_of(tp1): target 유실 시 +1% 로 재구성(대칭 +8% 아님)", abs(t0 - 101.0) < 1e-9 and s0 == 92.0, (s0, t0))
s1, t1 = pe.barriers_of(dict(pattern=PAT, direction="long", entry_price=100.0, stop=None, target=None))
check("barriers_of(tp1): stop 유실도 규격(−8%)으로", abs(s1 - 92.0) < 1e-9 and abs(t1 - 101.0) < 1e-9, (s1, t1))
s2, t2 = pe.barriers_of(dict(pattern=PAT, direction="long", entry_price=100.0, stop=92.0, target=101.5))
check("barriers_of(tp1): 기록된 target 이 있으면 그대로", t2 == 101.5)
s3, t3 = pe.barriers_of(dict(pattern="cascade_fade_long_1h", direction="long", entry_price=100.0, stop=98.5, target=None))
check("barriers_of(cascade): 대칭 복원 그대로(불변)", abs(t3 - 101.5) < 1e-9)
s4, t4 = pe.barriers_of(dict(pattern="engulfing", direction="long", entry_price=100.0, stop=92.0, target=None))
check("barriers_of(1d 패턴): 종전 대칭 복원(불변)", abs(t4 - 108.0) < 1e-9)
sm = pe.stop_map_of([dict(symbol="Q", pattern=PAT, direction="long", live_mode=True, d_closed=False,
                          entry_price=100.0, stop=92.0, target=None)])
check("stop_map: tp1 재등록 시 OCO 익절이 +1% (재구성)", abs(sm["Q"]["target"] - 101.0) < 1e-9 and sm["Q"]["stop"] == 92.0, sm)

# ── 3. live_cap ──────────────────────────────────────────────────────────────
check("live_cap 사양 = $70 · 3x · 1포지션 (사용자 결정, 2026-09-10 $30→$70)",
      cap["margin_usd"] == 70.0 and cap["leverage"] == 3 and cap["max_open"] == 1, cap)
check("exit_spec 사양 = 익절 1% / 손절 8% / 1h / 2000봉",
      spec["tp_pct"] == 0.01 and spec["sl_pct"] == 0.08 and spec["tf"] == "1h" and spec["horizon_bars"] == 2000, spec)
check("LIVE_CAPS 에 tp1 만", set(pe.LIVE_CAPS) == {PAT}, set(pe.LIVE_CAPS))
tmp = io.StringIO()
json.dump({"patterns": [{"id": "x", "live_cap": {"margin_usd": 5}}]}, tmp)
open("_tmp_caps.json", "w").write(tmp.getvalue())
check("live_cap 은 exit_spec 없으면 무효(손절 없는 실거래 금지)", pe.load_live_caps("_tmp_caps.json") == {})
import os; os.remove("_tmp_caps.json")
check("3x 에서 8% 손절은 청산가 안쪽(liq_safe_leverage 상한 이내)", sizing.liq_safe_leverage(0.08, cap=5) >= 3)
src = open("paper_executor.py", encoding="utf-8").read()
check("체결엔진: live_cap 패턴은 포트(cap_margin)·고정 레버리지로 주문(risk 사이징 우회)",
      'live_size_usd, live_lev = m_, int(cap.get("leverage", 1))' in src and "m_ = cap_margin(cap, s[\"pattern\"], trades)" in src)
check("체결엔진: live_cap 패턴은 자기 max_open 으로 제한, MAX_LIVE_POS 면제",
      "if pat_open >= int(cap.get(\"max_open\", 1)):" in src and "elif live_open_count >= MAX_LIVE_POS:" in src)
check("체결엔진: 중복 방어는 entry_blocked(메인/cap 분리)로, 슬롯 체크 뒤에",
      src.index("elif live_open_count >= MAX_LIVE_POS:") < src.index('if entry_blocked(s["symbol"], s["direction"], bool(cap), okx_dir_keys, main_keys, cap_keys):'))
check("체결엔진: 배리어·재정렬이 exit_barriers 공용 함수", src.count("xb.barriers(spec, rows, ei, entry, s[\"direction\"])") == 2)
check("체결엔진: ±k×ATR 인라인 산식 제거(한 곳만 정의)", "spec.get(\"k_atr\", ilab.K_ATR) * atr" not in src)

# ── 4. 등재 정합 ─────────────────────────────────────────────────────────────
ap = next(a for a in uni["adopted_1h_patterns"] if a["pattern"] == PAT)
check("universe: engulfing 디텍터 · 롱 · 1h · top20 · 닫힌 봉", ap["module"] == "detector_engulfing"
      and ap["direction"] == "long" and ap["tf"] == "1h" and ap["cohort"] == "top20" and ap["detects_on_closed_bar"] is True, ap)
check("universe: 사용자 강제 표시 + 검증 미통과 근거 기록", ap.get("forced_by_user") is True and "REJECTED" in ap["deploy_basis"])
check("registry: status forced_live_user, 검증 미통과 명시", rp["status"] == "forced_live_user" and "REJECTED" in rp["validation"])
check("스케줄러·체결엔진이 같은 exit_spec 을 본다", set(sch._exit_specs()) == set(pe.EXIT_SPECS))
check("_pattern_tf(tp1) == 1h (청산 평가 tf)", pe._pattern_tf(PAT) == "1h")
ssrc = open("scheduler.py", encoding="utf-8").read()
check("스케줄러: 1h adopted 에 cohort 적용", 'syms1 = _cohort_symbols(ap.get("cohort"), h1_syms)' in ssrc)
check("스케줄러: exit_spec 패턴은 ts 가 있는 detlib 로더로 읽는다",
      'detlib.load_ohlcv(sym, "1h") if spec_ap else mod1.load_ohlcv(sym, "1h")' in ssrc)
check("스케줄러: 배리어 표기가 exit_barriers 공용 함수", "xb.barriers(spec1, rows1h, last1, entry1, ap[\"direction\"])" in ssrc)
import detector_engulfing as de
check("디텍터는 인자 없이 호출 — 1d 배포 신호 집합 불변", de.detect.__code__.co_argcount == 1)
r1 = mkrows(120, seed=3)
check("detlib 로더 없이도 engulfing.detect 가 ts 키를 무시한다(신호 동일)",
      de.detect(r1) == de.detect([{k: v for k, v in r.items() if k != "ts"} for r in r1]))
_orig_rank = sch._volume_ranked
sch._volume_ranked = lambda: ["BBB", "AAA", "CCC"]      # 네트워크(auto-fetch) 없이 순위 고정
try:
    cs = sch._cohort_symbols("top20", ["AAA"])
finally:
    sch._volume_ranked = _orig_rank
check("_cohort_symbols(top20) 가 base 밖 심볼을 넣지 않는다", cs == ["AAA"], cs)

# ── 5. 기존 경로 불변 ────────────────────────────────────────────────────────
check("cascade exit_spec 불변(1.5xATR14 / 12봉)", cspec["k_atr"] == 1.5 and cspec["atr_period"] == 14 and cspec["horizon_bars"] == 12)
legacy = ["engulfing", "fvg", "inverted_hammer", "marubozu", "three_soldiers_4h", "triple_bottom_4h",
          "equal_lows_4h", "vol_awakening_4h", "triple_bottom", "engulfing_short", "fvg_short"]
check("기존 배포 패턴은 exit_spec/live_cap 없음", not [p for p in legacy if p in pe.EXIT_SPECS or p in pe.LIVE_CAPS])
check("메인 사이징 상수(RISK 1.0% / LEV_CAP 3 / MAX_LIVE_POS 16) — tp1 은 이 값을 안 쓴다",
      sizing.RISK_FRAC == 0.010 and sizing.LEV_CAP == 3 and pe.MAX_LIVE_POS == 16)
check("cascade 외 다른 1h adopted 는 그대로 하나(cascade)뿐", [a["pattern"] for a in uni["adopted_1h_patterns"]] == ["cascade_fade_long_1h", PAT])

# ── 6. eval_I + pct 배리어 = 검증 프레임(tp_1h) 청산 ────────────────────────
import validate_tp_1h as T
agree, n = 0, 0
for seed in range(40):
    r = mkrows(400, seed=100 + seed)
    for ei in (30, 80, 150):
        entry = r[ei]["c"]
        stop, tgt, _ = xb.barriers(spec, r, ei, entry, "long")
        ex = pe.eval_I(r, ei, "long", stop, tgt, spec["horizon_bars"])
        cross = T.crossings(r, ei, "long", spec["horizon_bars"])
        ret, hold, reason, tie = T._resolve(cross, r, ei, "long", 0.01, 0.08)
        n += 1
        if ex is None and reason == "open":
            agree += 1
        elif ex is not None and reason != "open":
            # 같은 봉·같은 사유(손절 우선 동률 처리 동일) — 수익률은 수수료 정의가 같으면 일치
            same_bar = (ex[0] - ei) == hold
            same_why = (reason == "stop") == (ex[3] == "atr_stop")
            agree += int(same_bar and same_why and abs(ex[2] - ret) < 1e-9)
check(f"eval_I(pct) 청산 봉·사유·수익률이 tp_1h 검증 프레임과 일치 ({agree}/{n})", agree == n and n > 0, (agree, n))


# ── 7. 독립 프로젝트 + 복리 포트 (2026-09-09 사용자 지시 "중복으로 말고 … 별도 관리 … 복리") ──
import exchange as ex_mod
tr = lambda pat, ret, method="D": dict(pattern=pat, method=method, ret=ret)
check("복리 포트: 시작 $70", pe.cap_margin(cap, PAT, []) == 70.0)
m1 = pe.cap_margin(cap, PAT, [tr(PAT, 0.008)])
check("복리 포트: 익절 1건(+1% − 0.2% 수수료)×3x → 70 × 1.024 = 71.68", abs(m1 - 71.68) < 1e-9, m1)
m2 = pe.cap_margin(cap, PAT, [tr(PAT, 0.008), tr(PAT, 0.008)])
check("복리 포트: 익절 2건 → 70 × 1.024² = 73.40", abs(m2 - round(70 * 1.024 ** 2, 2)) < 1e-9, m2)
m3 = pe.cap_margin(cap, PAT, [tr(PAT, 0.008), tr(PAT, -0.082)])
check("복리 포트: 손절 뒤 $70 리셋(reset_on_loss, 사용자 지시)", m3 == 70.0 and cap.get("reset_on_loss") is True, m3)
m4 = pe.cap_margin(cap, PAT, [tr(PAT, 0.008), tr(PAT, -0.082), tr(PAT, 0.008)])
check("복리 포트: 익절·손절·익절 → 리셋 후 다시 71.68", abs(m4 - 71.68) < 1e-9, m4)
_noreset = dict(cap, reset_on_loss=False)
check("reset_on_loss 없으면 손절도 복리로 줄어든다(71.68 × 0.754)",
      abs(pe.cap_margin(_noreset, PAT, [tr(PAT, 0.008), tr(PAT, -0.082)]) - round(71.68 * (1 - 0.246), 2)) < 1e-9)
_w = dict(tr(PAT, 0.008), exit_date="2026-09-10", entry_date="2026-09-10")
_l = dict(tr(PAT, -0.082), exit_date="2026-09-09", entry_date="2026-09-09")
check("복리 포트: 장부 순서가 뒤집혀 있어도 시간순으로 계산(손절이 먼저 → 71.68)",
      abs(pe.cap_margin(cap, PAT, [_w, _l]) - 71.68) < 1e-9)
check("복리 포트: 다른 패턴·방식A·R 행은 무시", pe.cap_margin(cap, PAT, [tr("engulfing", 0.5), tr(PAT, 0.5, "A"), tr(PAT, 0.5, "R")]) == 70.0)
check("복리 포트: $10 미만이면 None(주문 안 냄) — 리셋 없는 설정에서", pe.cap_margin(_noreset, PAT, [tr(PAT, -0.082)] * 8) is None)
check("복리 포트: 리셋 설정에서는 연속 손절도 $70 유지", pe.cap_margin(cap, PAT, [tr(PAT, -0.082)] * 5) == 70.0)
check("compound 아니면 margin_usd 고정", pe.cap_margin(dict(margin_usd=30.0, leverage=3), PAT, [tr(PAT, 0.5)]) == 30.0)
check("registry live_cap: compound·start_margin 70", cap.get("compound") is True and cap.get("start_margin") == 70.0)

rows_ = [dict(symbol="LTC", direction="long", pattern="engulfing", live_mode=True, d_closed=False, live_order=dict(qty=3.0)),
         dict(symbol="LTC", direction="long", pattern=PAT, live_mode=True, d_closed=False, live_order=dict(qty=1.0)),
         dict(symbol="ADA", direction="long", pattern="fvg", live_mode=True, d_closed=True),
         dict(symbol="SOL", direction="long", pattern=PAT, live_mode=True, d_closed=False, live_order=dict(qty=2.0)),
         dict(symbol="XRP", direction="long", pattern="fvg", live_mode=False, d_closed=False)]
mk, ck = pe.dir_key_sets(rows_)
check("dir_key_sets: 메인 {LTC} / cap {LTC, SOL}, 유령·페이퍼 제외", mk == {("LTC", "long")} and ck == {("LTC", "long"), ("SOL", "long")}, (mk, ck))
okx = {("LTC", "long"), ("SOL", "long"), ("DOT", "long")}
check("cap 신호: 메인이 LTC 롱을 들어도 막지 않는다(독립 프로젝트)", not pe.entry_blocked("LTC", "long", True, okx, {("LTC", "long")}, set()))
check("cap 신호: 자기 프로젝트가 이미 들면 막는다", pe.entry_blocked("SOL", "long", True, okx, mk, ck))
check("메인 신호: cap 만 든 SOL 롱은 막지 않는다(거래소 포지션이 cap 행으로 설명됨)", not pe.entry_blocked("SOL", "long", False, okx, mk, ck))
check("메인 신호: 장부에 없는 거래소 포지션(DOT)은 여전히 막는다", pe.entry_blocked("DOT", "long", False, okx, mk, ck))
check("메인 신호: 메인 행이 있으면 막는다", pe.entry_blocked("LTC", "long", False, okx, mk, ck))
check("close_qty_for: 같은 종목·방향을 나눠 들면 자기 계약 수만", pe.close_qty_for(rows_[1], rows_) == 1.0 and pe.close_qty_for(rows_[0], rows_) == 3.0)
check("close_qty_for: 단독이면 None(전량, 종전 동작)", pe.close_qty_for(rows_[3], rows_) is None)

# close_swap_position qty 클램프 — 가짜 거래소
class _Ex:
    def __init__(self): self.orders = []
    def fetch_positions(self, syms): return [dict(side="long", contracts=3.0)]
    def create_market_order(self, sym, side, qty, params=None):
        self.orders.append((side, qty, params)); return dict(average=100.0)
    def market_id(self, s): return "X-USDT-SWAP"
    def privatePostTradeCancelAlgos(self, a): pass
fx = _Ex(); fill, why = ex_mod.close_swap_position(dict(exchange=fx), "X", "long", qty=1.0)
check("close_swap_position(qty=1) 은 1계약만 닫는다(reduceOnly)", why == "ok" and fx.orders[0][1] == 1.0 and fx.orders[0][2]["reduceOnly"] is True, fx.orders)
fx = _Ex(); ex_mod.close_swap_position(dict(exchange=fx), "X", "long", qty=9.0)
check("close_swap_position(qty>실포지션) 은 실포지션까지만", fx.orders[0][1] == 3.0)
fx = _Ex(); ex_mod.close_swap_position(dict(exchange=fx), "X", "long")
check("close_swap_position(qty 없음) 은 전량(종전)", fx.orders[0][1] == 3.0)

# settle_by_algo — 거래소가 OCO 를 집행한 경우 봉 없이 기록
_orig_state = ex_mod.algo_state
try:
    ex_mod.algo_state = lambda lc, aid, inst_id=None: dict(state="effective", actual_px=101.0, actual_side="tp")
    pos_ = dict(symbol="LTC", direction="long", pattern=PAT, live_mode=True, d_closed=False, entry_price=100.0,
                stop=92.0, target=101.0, size_usd=70.0, entry_date="2026-09-09", live_order=dict(sl_order_id="a1", leverage=3, qty=1.0))
    trs = []
    ok_ = pe.settle_by_algo(pos_, dict(exchange=None), trs, "2026-09-09")
    check("settle_by_algo: effective → D 기록(+1% − 수수료), d_closed", ok_ and pos_["d_closed"] and len(trs) == 1
          and abs(trs[0]["ret"] - (0.01 - pe.FEE)) < 1e-9 and trs[0]["reason"] == "atr_target" and trs[0]["live_mode"], trs)
    check("settle_by_algo: pnl_live_usd ≈ 1% × 명목 $210", abs(trs[0]["pnl_live_usd"] - 2.1) < 1e-6, trs[0]["pnl_live_usd"])
    check("복리 포트가 그 기록을 읽는다 → $71.68", abs(pe.cap_margin(cap, PAT, trs) - 71.68) < 1e-9)
    ex_mod.algo_state = lambda lc, aid, inst_id=None: dict(state="live", actual_px=None, actual_side="")
    pos2 = dict(pos_, d_closed=False); trs2 = []
    check("settle_by_algo: live 면 아무것도 안 한다", not pe.settle_by_algo(pos2, dict(exchange=None), trs2, "2026-09-09") and not trs2)
    ex_mod.algo_state = lambda lc, aid, inst_id=None: None
    check("settle_by_algo: 조회 실패면 아무것도 안 한다", not pe.settle_by_algo(dict(pos_, d_closed=False), dict(exchange=None), [], "2026-09-09"))
finally:
    ex_mod.algo_state = _orig_state
src2 = open("paper_executor.py", encoding="utf-8").read()
check("청산 루프: 배리어 행은 OCO 상태를 먼저 보고 집행됐으면 시장가를 안 낸다", 'elif st_.get("state") == "effective":' in src2 and "qty=close_qty_for(pos, positions)" in src2)
check("청산 루프: settle_by_algo 가 entry_ts 유실 보류보다 먼저", src2.index("if settle_by_algo(pos, live_conn, trades") < src2.index("entry_ts 유실 — "))
check("진입: cap 주문 실패 시 페이퍼 행을 만들지 않는다(포트 계산 오염 방지)", "if cap:\n                    continue        # cap 프로젝트는 실주문만" in src2)

# ── 겹친 종목 OCO — 선택지 B (2026-09-12 사용자 결정) ────────────────────────────
# OKX net 모드가 같은 종목·방향을 한 포지션으로 합치는데 ensure_stop_orders 는 OCO 를
# 거래소 포지션 **전체 수량**에 건다. 겹친 채로 재정렬하면 tp1 의 +1% 가 방식D 로만
# 검증된 메인 레그까지 덮는다(9/11 SOL·ETH 2회 실측). 겹치면 재정렬을 건너뛴다.
_i_merged = src2.index("_merged = bool(cap) and (")
_i_realign = src2.index('replace={s["symbol"]})')
check("재정렬 판정이 재정렬 호출보다 앞에 있다", _i_merged < _i_realign)
check("겹침 판정은 cap 에만 걸린다(메인·cascade 는 종전 경로)", "_merged = bool(cap) and (" in src2)
check("겹침 판정이 세 출처를 다 본다(복원 메인행 / 같은 실행 메인진입 / 장부 밖 실포지션)",
      "_k in main_keys or _k in entered_main_run" in src2
      and "_k in okx_dir_keys and _k not in cap_keys" in src2)
check("겹치면 ensure_stop_orders 를 부르지 않는다", "if spec and _merged:" in src2
      and src2.index("if spec and _merged:") < src2.index("elif spec and abs(entry - sig_entry)"))
check("entered_main_run 은 메인 진입만 담는다", "if not cap:\n                    entered_main_run.add(_k)" in src2)
check("entered_main_run 은 entry_blocked 에 안 넘어간다(중복 방어 동작 불변)",
      "entry_blocked(s[\"symbol\"], s[\"direction\"], bool(cap), okx_dir_keys, main_keys, cap_keys)" in src2)

# 판정 로직 자체를 동작으로 고정 — 9/11 SOL 실측 재현(같은 실행에서 메인이 먼저 진입)
def _merged_of(is_cap, k, main_keys, entered, okx, capk):
    return bool(is_cap) and (k in main_keys or k in entered
                             or (k in okx and k not in capk))
K = ("SOL", "long")
check("SOL 실측: 같은 실행에서 메인이 먼저 들면 cap 재정렬 생략",
      _merged_of(True, K, set(), {K}, set(), set()))
check("ETH 실측: 전날 진입한 메인 행(복원)도 겹침으로 잡는다",
      _merged_of(True, ("ETH", "long"), {("ETH", "long")}, set(), set(), set()))
check("장부에 없는 실포지션도 겹침으로 잡는다",
      _merged_of(True, K, set(), set(), {K}, set()))
check("cap 자기 포지션만 있는 경우는 겹침 아님", not _merged_of(True, K, set(), set(), {K}, {K}))
check("안 겹치면 종전대로 재정렬한다", not _merged_of(True, K, set(), set(), set(), set()))
check("메인 신호(cap 아님)는 이 분기를 안 탄다 — cascade 배리어 동작 불변",
      not _merged_of(False, K, {K}, {K}, {K}, set()))

print(f"\n{len(fails)} failed")
sys.exit(1 if fails else 0)
