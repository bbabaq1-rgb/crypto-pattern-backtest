"""
test_tp1_live.py — 사용자 강제 실행 tp1_engulfing_1h(익절 +1% / 손절 −8% · $30 · 3x · top20 · 1포지션) 고정
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
check("live_cap 사양 = $30 · 3x · 1포지션 (사용자 결정)",
      cap["margin_usd"] == 30.0 and cap["leverage"] == 3 and cap["max_open"] == 1, cap)
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
check("체결엔진: live_cap 패턴은 고정 증거금·레버리지로 주문(risk 사이징 우회)",
      'live_size_usd, live_lev = float(cap["margin_usd"]), int(cap.get("leverage", 1))' in src)
check("체결엔진: live_cap 패턴은 자기 max_open 으로 제한, MAX_LIVE_POS 면제",
      "if pat_open >= int(cap.get(\"max_open\", 1)):" in src and "elif live_open_count >= MAX_LIVE_POS:" in src)
check("체결엔진: 같은 종목·방향 중복 방어는 캡 패턴에도 그대로",
      src.index("elif live_open_count >= MAX_LIVE_POS:") < src.index('if (s["symbol"], s["direction"]) in live_dir_keys:'))
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
cs = sch._cohort_symbols("top20", ["AAA"])
check("_cohort_symbols(top20) 가 base 밖 심볼을 넣지 않는다", set(cs) <= {"AAA"})

# ── 5. 기존 경로 불변 ────────────────────────────────────────────────────────
check("cascade exit_spec 불변(1.5xATR14 / 12봉)", cspec["k_atr"] == 1.5 and cspec["atr_period"] == 14 and cspec["horizon_bars"] == 12)
legacy = ["engulfing", "fvg", "inverted_hammer", "marubozu", "three_soldiers_4h", "triple_bottom_4h",
          "equal_lows_4h", "vol_awakening_4h", "triple_bottom", "engulfing_short", "fvg_short"]
check("기존 배포 패턴은 exit_spec/live_cap 없음", not [p for p in legacy if p in pe.EXIT_SPECS or p in pe.LIVE_CAPS])
check("메인 사이징 상수 불변(RISK 1.5% / LEV_CAP 3 / MAX_LIVE_POS 16)",
      sizing.RISK_FRAC == 0.015 and sizing.LEV_CAP == 3 and pe.MAX_LIVE_POS == 16)
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

print(f"\n{len(fails)} failed")
sys.exit(1 if fails else 0)
