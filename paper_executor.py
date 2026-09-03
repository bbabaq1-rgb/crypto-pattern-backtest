"""
paper_executor.py — 로컬 모의 체결 엔진 (실주문 없음).

signals_today.json -> 진입 기록(paper_positions.json).
매 실행마다 오픈 포지션 청산 모니터링:
  방식D: 손절 -8% / 반대패턴 신호 / 레짐 전환 / 최대30봉 시가청산.
  방식A: +10%/-10% / 최대20봉 종가청산 (병행 비교).
  방식R: 롱 한정 — 레짐 청산을 'bear 진입 전환'에만 (2026-09-03, 기록 전용 그림자 장부).
청산 시 paper_trades.json 에 기록(방식별 1행).

자본 $2,000, 포지션당 10%($200), 레버리지 1x. 체결가=시가/종가 가정(슬리피지 없음).
"""
import sys
import json
import os
import importlib
from datetime import datetime, timezone

import detlib
import intraday_lab as ilab
import sizing
import regime_switch as rs
import exchange as ex_mod

CAPITAL = 200.0    # 시뮬레이션 가상자본 $200
POS_PCT = 0.20
POS_USD = CAPITAL * POS_PCT   # $40 (시뮬레이션 포지션당 고정)
STOP = 0.08
MAX_HOLD_D = 30
MAX_HOLD_A = 20
# (구) TF별 방식D 최대보유 준비값. **의도적으로 미사용** — 이 값을 eval_D에 꽂으면
# 이미 배포된 4h/1h 패턴(three_soldiers_4h, bat_1h, butterfly_1h)의 청산 규칙이
# 검증 당시(동결 라벨 20봉/방식D 30봉)와 달라진다. 하위 TF 보유한도는 검증 프레임과
# 같은 값을 쓰는 EXIT_SPECS(ATR 배리어 경로)에서만 적용한다.
MAX_HOLD_BY_TF = {"1d": 30, "4h": 20, "1h": 48, "15m": 120}
FEE = detlib.FEE

# ── 방식R(롱 한정) 그림자 장부 (2026-09-03 사용자 승인) ─────────────────────────
# 방식D 의 레짐 청산은 `regmap[j] != entry_reg` 로 방향을 안 본다 — bear 에서 잡은
# 롱이 bull 로 유리하게 바뀌는 순간에도 청산된다. 방식R 은 롱에 한해 '불리 국면(bear)
# 으로 들어가는 전환'에만 청산한다(method_r.py 의 RL arm). 백테스트 3라운드는 규칙
# 전체로는 REJECT 였으나(분기 거래 승률 44~47%) bear 진입 롱의 bull 전환 유지만은 매번
# 재현됐다(report_regime_exit.md). 그래서 **주문은 D 그대로 내고 R 은 기록만** 한다 —
# 방식A 처럼 세 번째 장부로 나란히 쌓아 실거래 신호에서 두 규칙을 짝지어 비교한다.
#   · 대상: R_SHADOW_SINCE 이후 진입한 방식D **롱** 거래(exit_spec 패턴 제외 — 그쪽은
#     ATR 배리어라 D 자체가 안 돈다). 숏은 RL 에서 D 와 동일하므로 기록하지 않는다.
#   · 롱에서 R 의 청산 시점은 항상 D 와 같거나 늦다(손절·반대신호·만기는 동일, 레짐
#     조건은 D 의 부분집합). 따라서 D 가 청산돼 포지션이 사라진 뒤에도 R 은 미결일 수
#     있어 **포지션이 아니라 D 거래 기록에서** 매 실행 재평가한다(D 쌍둥이만 있고 R
#     쌍둥이가 없는 거래 → 해소되면 method="R" 행 추가). 포지션 수명·live 집계·주문에는
#     손대지 않는다. test_shadow_r.py 가 이 성질들을 고정한다.
R_SHADOW_SINCE = "2026-09-03"
R_ADVERSE_LONG = frozenset({"bear"})        # method_r.ADVERSE["R1"]["long"] 과 동일

# ── ATR 배리어 청산 경로 (하위 TF 전용) ────────────────────────────────────────
# 기존 방식A(±10%/20봉)·방식D(±8%/30봉)는 1d 기준으로 동결된 규칙이라 1h 이하
# 패턴에는 검증치와 5~10배 어긋난다(±1.5ATR ≈ 0.75~1.5% vs ±8%).
# registry.json 의 exit_spec 이 있는 패턴만 ATR 배리어로 청산한다 —
# 즉 등재된 1d/4h/1w/1h 기존 패턴의 청산 동작은 이 변경으로 바뀌지 않는다.
EXIT_SPEC_FILE = "registry.json"


def load_exit_specs(path=EXIT_SPEC_FILE):
    """{pattern_id: exit_spec} — registry 에 exit_spec 이 명시된 패턴만."""
    try:
        reg = json.load(open(path, encoding="utf-8"))
    except Exception:
        return {}
    out = {}
    for p in reg.get("patterns", []):
        spec = p.get("exit_spec")
        if spec and p.get("id"):
            out[p["id"]] = spec
    return out


EXIT_SPECS = load_exit_specs()

# 실거래 포지션 사이징 규칙
MAX_LIVE_POS   = 12    # 동시 최대 실거래 포지션 (2026-07-06 사용자 승인으로 5→12 상향)
LIVE_MIN_USD   = 10.0  # 최소 주문 금액 (이하 스킵)
LIVE_FIRST_USD = 20.0  # 첫 주문 고정 금액
LIVE_BAL_PCT   = 0.20  # 두 번째부터 가용잔고 × 20%

# 실거래 사이징 모드 (2026-09-02).
#   "legacy" : 첫 주문 $20 → 이후 가용잔고 x20%, 레버리지 2x 고정 (종전 동작 그대로)
#   "risk"   : sizing.risk_based_size — 건당 위험 = equity x RISK_FRAC, 명목가 = 위험/손절거리,
#              레버리지 = 청산가가 손절가의 2배 밖에 오도록 계산(상한 LEV_CAP). 등급·레짐 배수가
#              실주문에도 반영된다(legacy 에서는 페이퍼 기록에만 곱해졌다).
# 2026-09-02 사용자 결정 ③ — "risk" 전환(RISK_FRAC 1%, LEV_CAP 2). 근거는 sizing.py 주석:
# legacy 대비 CAGR 은 사실상 동일(+39.3% → +38.8%)한데 boot MDD 중앙이 -59.9% → -43.1% 로
# 줄어든다. 연구 권고값 0.5% 는 현 계좌($285)에서 최소증거금 미달로 주문이 안 나가 채택 불가.
# **이 상수를 바꾸면 실거래 주문 크기가 즉시 바뀐다.** 되돌리려면 "legacy".
SIZING_MODE = "risk"

# 계좌 킬스위치: equity가 하한선 밑으로 내려가면 신규 실거래 진입 중지.
# (개별 손절과 별개의 계좌 차원 브레이크. 기존 포지션 청산 모니터링은 계속 동작)
# 2026-08-29 사용자 지정: 절대 하한 $100.
# 이전 규칙(HWM $287.57 × -20% = $230.06)은 폐기 — 계좌 고점 기준이라 그보다 적은
# 금액을 재입금하면 입금 즉시 킬스위치가 걸려 신규 진입이 전면 차단되는 문제가 있었다.
EQUITY_FLOOR = 100.0

# 앙상블 Grade 기반 포지션 사이징 배수
GRADE_SIZE_MULT = {"A": 1.5, "B": 1.0, "C": 0.7, "D": 0.5}

# 레짐 사이징 오버레이 (시장 비대칭 avg_cap 기반, 롱 전용·축소만).
# backtest_regime_capture.py: 집단 bleed 롱 승률 59%/+13% vs complacent 26%/+3.6%.
# 보수적 채택 — complacent 국면(avg_cap>0)에서 신규 롱만 축소, 공포국면 upsize 안 함.
# 타이밍 신호 과적합 방어 위해 임계 0.0(부호 경계, 비피팅)·완만한 0.6 배수.
REGIME_CAP_THR  = 0.0
REGIME_CAP_MULT = 0.6

POS_FILE = "paper_positions.json"
TRD_FILE = "paper_trades.json"
OPP = {("engulfing", "long"): "detector_engulfing_short",
       ("engulfing", "short"): "detector_engulfing",
       ("fvg", "long"): "detector_fvg_short",
       ("fvg", "short"): "detector_fvg",
       # 하모닉: 반대 패턴 없음 → None (opp_set = 빈 집합)
       ("gartley",   "long"): None,
       ("bat",       "long"): None,
       ("butterfly", "long"): None,
}
DETMOD = {("engulfing", "long"): "detector_engulfing",
          ("engulfing", "short"): "detector_engulfing_short",
          ("fvg", "long"): "detector_fvg",
          ("fvg", "short"): "detector_fvg"}


def _load(fn, default):
    return json.load(open(fn, encoding="utf-8")) if os.path.exists(fn) else default


def _save(fn, obj):
    json.dump(obj, open(fn, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def eval_D(rows, ei, direction, opp_set, regmap):
    base = rows[ei]["c"]; entry_reg = regmap.get(rows[ei]["date"]); last = len(rows) - 1
    end = min(ei + MAX_HOLD_D, last)
    for j in range(ei + 1, end + 1):
        if direction == "long" and rows[j]["l"] <= base * (1 - STOP):
            return j, base * (1 - STOP), -STOP - FEE, "stop"
        if direction == "short" and rows[j]["h"] >= base * (1 + STOP):
            return j, base * (1 + STOP), -STOP - FEE, "stop"
        regsw = regmap.get(rows[j]["date"]) not in (None, entry_reg)
        if j in opp_set or regsw:
            c = rows[j]["c"]; r = (c - base) / base if direction == "long" else (base - c) / base
            return j, c, r - FEE, ("opp_signal" if j in opp_set else "regime_switch")
    if last >= ei + MAX_HOLD_D:
        px = rows[end]["o"]; r = (px - base) / base if direction == "long" else (base - px) / base
        return end, px, r - FEE, "maxhold"
    return None


def eval_R(rows, ei, direction, opp_set, regmap):
    """
    방식R(롱 한정) — method_r.outcome_r(mode="RL") 과 같은 규칙, eval_D 와 같은 반환형.

    롱: 손절 -8%(봉 내) / 반대신호 / **bear 로 들어가는 전환**(직전 관측 레짐이 bear 가
        아닌데 이번 봉이 bear) / 최대 30봉 시가청산. 레짐 정보 없는 봉(None)은 판단 보류.
    숏: 방식D 와 동일(eval_D 위임) — RL arm 정의.
    반환: (j, exit_px, ret, reason) | None(미해소)
    """
    if direction != "long":
        return eval_D(rows, ei, direction, opp_set, regmap)
    base = rows[ei]["c"]; entry_reg = regmap.get(rows[ei]["date"]); last = len(rows) - 1
    end = min(ei + MAX_HOLD_D, last)
    prev_adv = entry_reg in R_ADVERSE_LONG
    for j in range(ei + 1, end + 1):
        if rows[j]["l"] <= base * (1 - STOP):
            return j, base * (1 - STOP), -STOP - FEE, "stop"
        cur = regmap.get(rows[j]["date"])
        regsw = False
        if cur is not None:
            cur_adv = cur in R_ADVERSE_LONG
            regsw = cur_adv and not prev_adv
            prev_adv = cur_adv
        if j in opp_set or regsw:
            c = rows[j]["c"]
            return j, c, (c - base) / base - FEE, ("opp_signal" if j in opp_set else "regime_switch")
    if last >= ei + MAX_HOLD_D:
        px = rows[end]["o"]
        return end, px, (px - base) / base - FEE, "maxhold"
    return None


def eval_A(rows, ei, direction):
    base = rows[ei]["c"]; up = base * 1.10; dn = base * 0.90; last = len(rows) - 1
    end = min(ei + MAX_HOLD_A, last)
    for j in range(ei + 1, end + 1):
        c = rows[j]["c"]
        if direction == "long":
            if c >= up: return j, c, c / base - 1 - FEE, "tp"
            if c <= dn: return j, c, c / base - 1 - FEE, "sl"
        else:
            if c <= dn: return j, c, (base - c) / base - FEE, "tp"
            if c >= up: return j, c, (base - c) / base - FEE, "sl"
    if last >= ei + MAX_HOLD_A:
        c = rows[end]["c"]; r = c / base - 1
        return end, c, (r - FEE if direction == "long" else -r - FEE), "timestop"
    return None


def eval_I(rows, ei, direction, stop_px, target_px, horizon):
    """
    ATR 배리어 청산 (하위 TF 전용) — intraday_lab.outcome_atr 과 동일 규칙.

    배리어는 '진입 시점에 확정된 가격'(stop_px/target_px)을 그대로 쓴다.
    ATR을 매 실행 재계산하지 않는 이유: 실제 OKX 에 걸려 있는 OCO 주문의 트리거가
    그 가격이라, 재계산하면 장부와 거래소가 어긋난다.

    - 봉 내 고저(h/l)로 판정, 같은 봉에서 양쪽 다 닿으면 보수적으로 손절 우선
      (검증 프레임 outcome_atr 과 동일)
    - horizon 봉 경과 시 종가 시간청산
    반환: (j, exit_px, ret, reason) | None
    """
    if not stop_px or not target_px:
        return None
    base = rows[ei]["c"]
    last = len(rows) - 1
    end = min(ei + horizon, last)
    for j in range(ei + 1, end + 1):
        hi, lo = rows[j]["h"], rows[j]["l"]
        if direction == "long":
            if lo <= stop_px:
                return j, stop_px, (stop_px / base - 1) - FEE, "atr_stop"
            if hi >= target_px:
                return j, target_px, (target_px / base - 1) - FEE, "atr_target"
        else:
            if hi >= stop_px:
                return j, stop_px, (base - stop_px) / base - FEE, "atr_stop"
            if lo <= target_px:
                return j, target_px, (base - target_px) / base - FEE, "atr_target"
    if last >= ei + horizon:
        c = rows[end]["c"]
        r = (c / base - 1) if direction == "long" else (base - c) / base
        return end, c, r - FEE, "atr_timestop"
    return None


def barriers_of(pos):
    """
    포지션의 (손절가, 익절가). 익절가는 미기록 시 손절 거리 대칭으로 복원한다.

    ±k×ATR 브래킷은 진입가 기준 양쪽 거리가 같으므로
    target = entry + (entry - stop) (롱) 으로 정확히 되살릴 수 있다.
    Supabase positions 테이블에 target 컬럼이 없어(복원 시 유실) 필요한 폴백.
    """
    stop = pos.get("stop")
    tgt = pos.get("target")
    entry = pos.get("entry_price")
    if tgt is None and stop is not None and entry:
        tgt = entry + (entry - stop)      # 롱/숏 모두 부호가 알아서 맞는다
    return stop, tgt


def _date_idx(rows, date):
    for i, r in enumerate(rows):
        if r["date"] == date:
            return i
    return None


def _bar_idx(rows, entry_ts=None, entry_date=None):
    """
    진입봉 인덱스. ts(ms)가 있으면 그것으로 정확히 찾고, 없으면 date 폴백.

    date 폴백은 1h/15m 에서 하루 24/96 봉이 같은 date 라 그날 첫 봉을 가리킨다
    (구 포지션·DB 복원분 호환용). 신규 포지션은 항상 entry_ts 를 기록한다.
    """
    if entry_ts:
        for i, r in enumerate(rows):
            if r.get("ts") == entry_ts:
                return i
    if entry_date:
        return _date_idx(rows, entry_date)
    return None


def _record_trade(trades, pos, method, ex, exit_date=None):
    j, exit_px, ret, reason = ex
    # 실거래 판정: 방식D만 실제 OKX 청산과 연결됨(af7b3c4 결정). 방식A(±10%)는
    # 페이퍼 비교 전용이므로 live 포지션이라도 A청산은 '페이퍼'로 기록해야 한다.
    # (과거엔 A청산도 live_mode를 상속 → '실거래' 마커가 붙어 매도로 오인, 포지션은
    #  D가 홀딩 중이라 오픈으로 남아 매매내역↔오픈포지션 불일치 발생: UNI 사례)
    is_live_trade = bool(pos.get("live_mode", False)) and method == "D"
    trades.append(dict(method=method, symbol=pos["symbol"], direction=pos["direction"],
                       pattern=pos["pattern"], regime=pos.get("regime"),
                       entry_date=pos["entry_date"], entry_price=pos["entry_price"],
                       exit_date=exit_date, exit_price=round(exit_px, 4), ret=round(ret, 5),
                       pnl_usd=round(ret * POS_USD, 2), hold_bars=j - pos["entry_idx"],
                       reason=reason, method_label=method,
                       live_mode=is_live_trade,
                       # 같은 실행 안에서 방식R 그림자가 진입봉을 ts 로 특정하기 위한 참고값.
                       # DB trades 에는 컬럼이 없어 복원 시 유실 → date 폴백(_bar_idx).
                       entry_ts=pos.get("entry_ts"), tf=pos.get("tf")))


# ---- Supabase 동기화 (베스트에포트; 실패/미설정 시 JSON 폴백) ----
def _db():
    try:
        import supabase_client as sc
        return sc.get_client("service") if sc.available() else None
    except Exception:
        return None


def push_trades_db(new_trades):
    cli = _db()
    if not cli or not new_trades:
        return 0
    # '실거래' 마커: DB에 live_mode 컬럼이 없어도(DDL 미적용) 대시보드가
    # exit_reason으로 실거래/페이퍼를 구분할 수 있게 실거래 청산에 마커 부여.
    def _reason(t):
        r = t["reason"]
        return f"{r} ·실거래" if t.get("live_mode") and "실거래" not in str(r) else r
    rows = [{"symbol": t["symbol"], "pattern": t["pattern"], "direction": t["direction"],
             "entry_date": t["entry_date"], "entry_price": t["entry_price"],
             "exit_date": t.get("exit_date"), "exit_price": t["exit_price"],
             "return_pct": round(t["ret"] * 100, 4), "hold_bars": t["hold_bars"],
             "exit_reason": _reason(t), "method": t["method"],
             "pnl_usd": t.get("pnl_usd"),
             "live_mode": bool(t.get("live_mode", False))} for t in new_trades]
    try:
        import supabase_client as sc
        # 재실행 중복 방어: 동일 키(method 포함) 기존 행 제거 후 삽입
        for r in rows:
            (cli.table("trades").delete()
             .eq("symbol", r["symbol"]).eq("pattern", r["pattern"])
             .eq("direction", r["direction"]).eq("entry_date", r["entry_date"])
             .eq("method", r["method"]).execute())
        _, dropped = sc.insert_tolerant(cli, "trades", rows)
        if dropped:
            print("  [DB] trades 스키마 미존재 컬럼 제외:", dropped)
        return len(rows)
    except Exception as e:
        print("  [DB] trades insert 실패(로컬 JSON 유지):", str(e)[:60])
        return 0


def push_positions_db(new_positions):
    cli = _db()
    if not cli or not new_positions:
        return 0
    # method에 LIVE 인코딩: positions 테이블에 live_mode 컬럼이 없어도(DDL 미적용)
    # 러너 복원·대시보드가 실거래 여부를 알 수 있게 한다.
    rows = [{"symbol": p["symbol"], "pattern": p["pattern"], "direction": p["direction"],
             "entry_date": p["entry_date"], "entry_price": p["entry_price"],
             "stop_loss": p.get("stop"), "size_usd": p.get("size_usd"),
             # 하위 TF ATR 배리어용 — 컬럼 미존재 시 insert_tolerant 가 자동 제외.
             # target 이 유실돼도 barriers_of() 가 손절 거리 대칭으로 복원한다.
             "target": p.get("target"), "entry_ts": p.get("entry_ts"),
             "live_mode": bool(p.get("live_mode", False)),
             "status": "open",
             "method": "AD-LIVE" if p.get("live_mode") else "AD"} for p in new_positions]
    try:
        import supabase_client as sc
        # 재실행 중복 방어: 동일 키 기존 행 제거 후 삽입 (ZIL×5 오염 재발 방지)
        for r in rows:
            (cli.table("positions").delete()
             .eq("symbol", r["symbol"]).eq("pattern", r["pattern"])
             .eq("direction", r["direction"]).eq("entry_date", r["entry_date"]).execute())
        _, dropped = sc.insert_tolerant(cli, "positions", rows)
        if dropped:
            print("  [DB] positions 스키마 미존재 컬럼 제외:", dropped)
        return len(rows)
    except Exception as e:
        print("  [DB] positions insert 실패(로컬 JSON 유지):", str(e)[:60])
        return 0


def mark_closed_db(closed_positions):
    """완전 청산(A·D 모두)된 포지션의 DB status를 'closed'로 갱신."""
    cli = _db()
    if not cli or not closed_positions:
        return 0
    n = 0
    for p in closed_positions:
        try:
            (cli.table("positions").update({"status": "closed"})
             .eq("symbol", p["symbol"]).eq("pattern", p["pattern"])
             .eq("direction", p["direction"]).eq("entry_date", p["entry_date"]).execute())
            n += 1
        except Exception as e:
            print("  [DB] positions close 갱신 실패(무시):", str(e)[:60])
    return n


def _derive_tf(pattern):
    """패턴명 접미사에서 timeframe 복원 (DB에 tf 컬럼이 없어서 사용)."""
    if pattern.endswith("_4h"):
        return "4h"
    if pattern.endswith("_1h"):
        return "1h"
    return "1d"


_UNIVERSE_TF = None


def _pattern_tf(pattern, path="universe.json"):
    """
    패턴의 검증 timeframe. universe.json 의 adopted_* 목록에 적힌 tf 를 우선하고
    (triple_bottom → 1w 처럼 접미사로는 알 수 없는 것), 없으면 _derive_tf 폴백.
    """
    global _UNIVERSE_TF
    if _UNIVERSE_TF is None:
        m = {}
        try:
            u = json.load(open(path, encoding="utf-8"))
            for key in ("adopted_patterns", "adopted_4h_patterns", "adopted_1h_patterns"):
                for p in u.get(key, []) or []:
                    if p.get("pattern") and p.get("tf"):
                        m[p["pattern"]] = p["tf"]
        except Exception:
            pass
        _UNIVERSE_TF = m
    return _UNIVERSE_TF.get(pattern) or _derive_tf(pattern)


def shadow_r_records(trades, rows_of, regmap, since=R_SHADOW_SINCE):
    """
    방식R 그림자 장부 갱신 — R_SHADOW_SINCE 이후 진입한 방식D 롱 거래 중 R 쌍둥이가
    없는 것을 봉 데이터로 재평가해, 해소된 것만 method="R" 행으로 추가한다.

    기록 전용: 포지션 목록·live 집계·주문에는 관여하지 않는다. 진입봉은 같은 실행에서
    D 가 방금 기록한 거래면 entry_ts 로, DB 복원분이면 date 폴백으로 특정한다(D 도
    복원 시 같은 폴백을 쓴다). 반환: 새로 추가한 R 행 수.
    """
    have_r = {(t["symbol"], t["pattern"], t["direction"], t["entry_date"])
              for t in trades if t.get("method") == "R"}
    added = 0
    for t in list(trades):
        if t.get("method") != "D" or t.get("direction") != "long":
            continue
        if not t.get("entry_date") or t["entry_date"] < since:
            continue
        if t["pattern"] in EXIT_SPECS:
            continue
        key = (t["symbol"], t["pattern"], t["direction"], t["entry_date"])
        if key in have_r:
            continue
        rows = rows_of(t["symbol"], _pattern_tf(t["pattern"]))
        if rows is None:
            continue
        ei = _bar_idx(rows, t.get("entry_ts"), t["entry_date"])
        if ei is None:
            continue
        oppname = OPP.get((t["pattern"], t["direction"]))
        opp_set = set(importlib.import_module(oppname).detect(rows)) if oppname else set()
        ex = eval_R(rows, ei, "long", opp_set, regmap)
        if not ex:
            continue                      # 미해소 — 다음 실행에 재평가
        pos_like = dict(symbol=t["symbol"], direction="long", pattern=t["pattern"],
                        regime=t.get("regime"), entry_date=t["entry_date"],
                        entry_price=t["entry_price"], entry_idx=ei,
                        entry_ts=t.get("entry_ts"), tf=_pattern_tf(t["pattern"]),
                        live_mode=False)
        _record_trade(trades, pos_like, "R", ex, rows[ex[0]]["date"])
        have_r.add(key)
        added += 1
        print(f"  [shadow-R] {t['symbol']} {t['pattern']} 롱 R청산 기록 ({ex[3]}, "
              f"{ex[2]*100:+.2f}%, {ex[0]-ei}봉) — D 는 {t.get('reason')} {float(t.get('ret') or 0)*100:+.2f}%")
    return added


def restore_state_db(positions, trades):
    """
    러너(빈 파일시스템)에서 Supabase로 상태 복원.

    GitHub Actions는 매 실행 파일시스템이 초기화되므로 paper_positions/trades
    JSON이 비어 있다. 복원 없이는 openkeys/closedkeys가 비어 같은 신호로
    매 실행 재진입(실거래 중복 매수!)하고 청산 거래가 매번 재기록된다.
    로컬 JSON이 있으면 그것을 원천으로 쓰고 DB 복원은 건너뛴다.
    """
    cli = _db()
    if not cli:
        return positions, trades
    try:
        if not trades:
            tr = cli.table("trades").select("*").limit(1000).execute().data or []
            for t in tr:
                ret = (t.get("return_pct") or 0) / 100.0
                # pnl_usd: DB 값 우선. 컬럼 없으면 과거 트레이드 기준 size $200으로
                # 재구성 (현재 POS_USD로 재계산하면 daily_summary 누적%가 왜곡됨)
                pnl = t.get("pnl_usd")
                if pnl is None:
                    pnl = round(ret * 200.0, 2)
                trades.append(dict(
                    method=t.get("method"), symbol=t.get("symbol"),
                    direction=t.get("direction"), pattern=t.get("pattern"),
                    regime=t.get("regime"), entry_date=t.get("entry_date"),
                    entry_price=t.get("entry_price"), exit_date=t.get("exit_date"),
                    exit_price=t.get("exit_price"), ret=ret,
                    pnl_usd=pnl, hold_bars=t.get("hold_bars"),
                    reason=t.get("exit_reason"), method_label=t.get("method"),
                    live_mode=bool(t.get("live_mode") or False)))
            if tr:
                print(f"  [restore] Supabase trades {len(tr)}건 복원")
        if not positions:
            pr = (cli.table("positions").select("*").eq("status", "open")
                  .limit(500).execute().data) or []
            closed_am = {(t["symbol"], t["pattern"], t["direction"],
                          t["entry_date"], t["method"]) for t in trades}
            seen = set()
            for p in pr:
                key = (p["symbol"], p["pattern"], p["direction"], p["entry_date"])
                if key in seen:          # 과거 중복 오염 방어 — 첫 행만 채택
                    continue
                seen.add(key)
                # live 판정: live_mode 컬럼(있으면) OR method의 LIVE 인코딩
                is_live = bool(p.get("live_mode")) or \
                    str(p.get("method", "")).upper().endswith("LIVE")
                positions.append(dict(
                    symbol=p["symbol"], direction=p["direction"], pattern=p["pattern"],
                    regime=p.get("regime"), tf=_derive_tf(p["pattern"]),
                    entry_date=p["entry_date"],
                    entry_ts=p.get("entry_ts"),
                    entry_price=p.get("entry_price"), stop=p.get("stop_loss"),
                    target=p.get("target"),
                    size_usd=p.get("size_usd") or POS_USD,
                    live_mode=is_live,
                    d_closed=key + ("D",) in closed_am,
                    a_closed=key + ("A",) in closed_am))
            if pr:
                print(f"  [restore] Supabase 오픈 포지션 {len(positions)}건 복원"
                      f" (원본 {len(pr)}행, 중복 {len(pr)-len(positions)}행 무시)")
    except Exception as e:
        print("  [restore] DB 상태 복원 실패(무시):", str(e)[:60])
    return positions, trades


def reconcile_live_flag(positions, live_conn):
    """
    OKX 실측을 기준으로 DB 복원 포지션의 live_mode를 보정.

    OKX에 (symbol, direction)이 실재하면 해당 DB 포지션을 live_mode=True로 승격한다.
    이렇게 해야 방식D 청산 모니터가 그 포지션을 '실거래'로 보고 조건 충족 시
    실제 OKX reduceOnly 주문을 낸다(자동 매도 사각지대 제거). entry_date가 캔들에
    매핑 안 되면 D-eval이 안전하게 스킵되므로 잘못된 청산 위험은 없다.
    """
    try:
        okx = ex_mod.get_okx_positions(live_conn)
    except Exception as e:
        print("  [reconcile] OKX 포지션 조회 실패(무시):", str(e)[:60])
        return positions
    okx_keys = {(p["symbol"], p["direction"]) for p in okx}
    promoted = []
    for pos in positions:
        if (pos["symbol"], pos["direction"]) in okx_keys and not pos.get("live_mode"):
            pos["live_mode"] = True
            promoted.append(pos["symbol"])
    if promoted:
        print(f"  [reconcile] OKX 실재 → 실거래 승격 {len(promoted)}건: {sorted(set(promoted))}")
    return positions


def reconcile_closed_positions(positions, trades, live_conn):
    """
    엔진 몰래 OKX에서 청산된 실거래 포지션을 잡아 기록·정리.

    OKX algo 손절이 장중 터지거나(엔진 일봉 eval_D는 미감지) 앱에서 직접 닫으면,
    엔진 포지션은 계속 open으로 남아 P&L·매매내역에 반영 안 됨(GLM 사례).
    OKX에 '없는데' 청산이력엔 '있는' live 포지션을 방식D 거래로 소급 기록하고 제거.
    반환: (남은 positions, 새로 기록한 심볼 리스트)
    """
    if not live_conn:
        return positions, []
    open_keys = {(p["symbol"], p["direction"])
                 for p in ex_mod.get_okx_positions(live_conn)}
    history = ex_mod.get_okx_closed_positions(live_conn)
    kept, closed_syms = [], []
    for pos in positions:
        key = (pos["symbol"], pos["direction"])
        if not pos.get("live_mode") or key in open_keys:
            kept.append(pos); continue
        hist = history.get(key)
        if not hist or not hist.get("close_px"):
            kept.append(pos); continue          # OKX엔 없지만 이력도 없음 → 유지(다음 점검)
        base = pos["entry_price"]; fill = hist["close_px"]
        ret = ((fill - base) / base if pos["direction"] == "long"
               else (base - fill) / base)
        reason = "손절(OKX algo)" if hist.get("type") in ("2", "3", "5") else "OKX청산"
        pos["entry_idx"] = pos.get("entry_idx", 0)
        _record_trade(trades, pos, "D",
                      (pos["entry_idx"], fill, ret - FEE, reason),
                      exit_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
        closed_syms.append(pos["symbol"])
        # DB 포지션 status=closed
        cli = _db()
        if cli:
            try:
                (cli.table("positions").update({"status": "closed"})
                 .eq("symbol", pos["symbol"]).eq("direction", pos["direction"])
                 .eq("status", "open").execute())
            except Exception:
                pass
        print(f"  [reconcile-close] {pos['symbol']} {pos['direction']} OKX청산 감지 "
              f"→ 기록 (fill={fill}, {ret*100:+.2f}%, 실현 {hist['pnl']:+.2f})")
    if closed_syms:
        try:
            import notify
            notify.send("🔴 <b>OKX 청산 감지→기록</b> (엔진 외부 청산)\n" +
                        "\n".join(f"  {s}" for s in closed_syms))
        except Exception:
            pass
    return kept, closed_syms


def run(stamp=None):
    stamp = stamp or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    regmap = rs.build_regime_map()
    positions = _load(POS_FILE, [])
    trades = _load(TRD_FILE, [])
    # 러너 파일시스템은 매 실행 초기화 → Supabase에서 상태 복원
    # (복원 없이는 openkeys가 비어 실거래 중복 진입 발생)
    positions, trades = restore_state_db(positions, trades)
    rows_cache = {}

    def rows_of(sym, tf="1d"):
        key = (sym, tf)
        if key not in rows_cache:
            try:
                rows_cache[key] = detlib.load_ohlcv(sym, tf)
            except (FileNotFoundError, RuntimeError):
                rows_cache[key] = None  # OKX 미상장 등 데이터 없음
        return rows_cache[key]

    t0 = len(trades)                  # 이번 실행에서 새로 체결되는 거래 추적
    new_positions = []

    # 실거래 연결 — 청산 모니터링(방식D 실주문)에서도 쓰므로 루프 앞에서 생성
    live_conn = ex_mod.connect_live() if ex_mod.is_live() else None
    kill_switch = False       # True면 신규 실거래 진입 중지(청산 모니터링은 계속)
    if live_conn:
        print(f"[live] OKX 선물 실거래 모드 | USDT free={live_conn['usdt_free']:.2f}")
        # 실거래 정합성 보정: OKX에 실재하는 포지션인데 DB엔 페이퍼(live_mode=False)로
        # 남은 것들을 실거래로 승격 → 방식D 청산 모니터가 실제 OKX 주문을 내도록.
        # (과거 진입경로/복원에서 live 표기가 유실돼 실거래인데 자동청산 사각지대이던 문제)
        positions = reconcile_live_flag(positions, live_conn)

        # 안전망 0: 엔진 몰래 OKX에서 청산된 포지션(장중 algo 손절·앱 수동청산) 감지→기록
        # (일봉 eval_D가 못 잡는 인트라바 손절 정합성 갭 — GLM 사례)
        positions, okx_closed = reconcile_closed_positions(positions, trades, live_conn)

        # 안전망 1: 손절(algo) 주문 상시 점검 — 누락 포지션에 재등록
        # 재등록 시 '포지션에 기록된 손절가'를 쓰도록 전달. 없으면 종전대로 ±8%.
        # (ATR 배리어 패턴은 손절이 0.75~1.5%라 ±8% 재등록이 검증치와 5~10배 어긋난다)
        # target 은 ATR 배리어 패턴에만 준다 — 기존 1d/4h 패턴에 익절 주문을 붙이면
        # 검증된 적 없는 청산 규칙이 실계좌에서 돌아간다.
        stop_map = {}
        for p in positions:
            if not p.get("live_mode"):
                continue
            s, t = barriers_of(p)
            if not s:
                continue
            stop_map[p["symbol"]] = {
                "stop": s,
                "target": t if p["pattern"] in EXIT_SPECS else None,
            }
        fixed_sl, orphan_sl = ex_mod.ensure_stop_orders(live_conn, stop_map=stop_map)
        if fixed_sl:
            import notify
            notify.send("⚠️ <b>손절 주문 누락 감지 → 재등록</b>\n" +
                        "\n".join(f"  {s}: SL @ {px}" for s, px in fixed_sl))
        # 안전망 1-b: 포지션 없는 고아 손절 주문 취소(트리거 시 신규 진입 방지)
        if orphan_sl:
            import notify
            notify.send("🧹 <b>고아 손절 주문 취소</b>(대응 포지션 없음)\n" +
                        "\n".join(f"  {inst}" for inst, _ in orphan_sl))

        # 안전망 2: 계좌 킬스위치 — equity가 하한선(EQUITY_FLOOR) 미만이면 신규 중지
        bal = ex_mod.get_balance(live_conn)
        equity = (bal or {}).get("equity") or 0.0
        if equity and equity < EQUITY_FLOOR:
            kill_switch = True
            msg = (f"🛑 킬스위치 발동: equity ${equity:.2f} < 하한 ${EQUITY_FLOOR:.2f}"
                   f" — 신규 실거래 진입 중지")
            print(f"  [kill] {msg}")
            import notify
            notify.send(msg)
        else:
            print(f"  [kill] equity ${equity:.2f} / 하한 ${EQUITY_FLOOR:.2f} — 통과")

    # 1) 오픈 포지션 청산 모니터링
    #    방식D 청산 조건 충족 + live_mode 포지션 → 실제 OKX reduceOnly 청산 주문.
    #    (과거엔 페이퍼 기록만 하고 실주문이 없어 실거래 익절이 영영 실행 안 되던 버그)
    still_open = []
    closed_now = []                   # 이번 실행에서 A·D 모두 청산 완료된 포지션
    for pos in positions:
        rows = rows_of(pos["symbol"], pos.get("tf", "1d"))
        if rows is None:          # 데이터 미수집 종목(OKX 미상장 등) -> 포지션 유지
            still_open.append(pos); continue
        ei = _bar_idx(rows, pos.get("entry_ts"), pos["entry_date"])
        if ei is None:
            still_open.append(pos); continue
        pos["entry_idx"] = ei
        spec = EXIT_SPECS.get(pos["pattern"])
        if spec:
            # ATR 배리어 경로: 방식A/D 비교는 1d 구조물이라 의미 없음 → A는 닫힌 것으로 표시
            pos["a_closed"] = True
            # **진입봉을 특정하지 못하면 평가하지 않는다.**
            # Supabase positions 에 entry_ts 컬럼이 없어 DB 복원 시 유실된다
            # (insert_tolerant 가 자동 제외 — 실행 로그의 '스키마 미존재 컬럼 제외').
            # 하위 TF 에서 date 폴백은 그날 **첫 봉**을 가리키므로, 그대로 두면 eval_I 가
            # 진입보다 이른 봉들을 스캔해 진입 전 가격으로 청산을 만들고(실거래 오청산),
            # base=rows[ei]["c"] 도 틀려 수익률까지 오염된다.
            # 배리어는 거래소 OCO 가 이미 지키고 있으므로 엔진은 손대지 않고 유지한다.
            # positions.entry_ts 컬럼이 생기면 이 분기는 자동으로 사라진다.
            if not pos.get("entry_ts") and _derive_tf(pos["pattern"]) != "1d":
                print(f"  [hold] {pos['symbol']} {pos['pattern']} entry_ts 유실 — "
                      f"진입봉 특정 불가로 엔진 청산 보류(거래소 OCO 유효). "
                      f"positions.entry_ts 컬럼 추가 필요")
                still_open.append(pos)
                continue
        oppname = OPP.get((pos["pattern"], pos["direction"]))
        opp_set = set(importlib.import_module(oppname).detect(rows)) if oppname else set()
        if not pos.get("d_closed"):
            if spec:
                stop_px, target_px = barriers_of(pos)
                ex = eval_I(rows, ei, pos["direction"], stop_px, target_px,
                            spec.get("horizon_bars", MAX_HOLD_A))
            else:
                ex = eval_D(rows, ei, pos["direction"], opp_set, regmap)
            if ex:
                do_record = True
                if pos.get("live_mode"):
                    if live_conn is None:
                        do_record = False    # 연결 없으면 유지 → 다음 실행 재시도
                        print(f"  [live] {pos['symbol']} D청산 조건 충족했으나 OKX 미연결 — 유지")
                    else:
                        sl_id = (pos.get("live_order") or {}).get("sl_order_id")
                        fill, why = ex_mod.close_swap_position(
                            live_conn, pos["symbol"], pos["direction"], sl_algo_id=sl_id)
                        if why == "ok":
                            if fill:         # 실체결가로 D 기록 교체
                                base = pos["entry_price"]
                                r = ((fill - base) / base if pos["direction"] == "long"
                                     else (base - fill) / base)
                                ex = (ex[0], fill, r - FEE, ex[3])
                            print(f"  [live] {pos['symbol']} {pos['direction']} D청산 실행 "
                                  f"({ex[3]}) fill={fill}")
                            import notify
                            d_ko = "롱" if pos["direction"] == "long" else "숏"
                            notify.send(f"🔵 <b>실거래 청산(방식D)</b> {pos['symbol']} {d_ko}\n"
                                        f"사유: {ex[3]} | 수익률 {ex[2]*100:+.2f}%\n"
                                        f"진입 {pos['entry_price']} → 청산 {fill}")
                        elif why == "no_position":
                            print(f"  [live] {pos['symbol']} 이미 닫힘(손절 체결 추정) — 기록만")
                        else:
                            do_record = False
                            print(f"  [live] {pos['symbol']} D청산 주문 실패({why}) — 유지, 재시도")
                if do_record:
                    _record_trade(trades, pos, "D", ex, rows[ex[0]]["date"]); pos["d_closed"] = True
        if not pos.get("a_closed"):
            ex = eval_A(rows, ei, pos["direction"])
            if ex:
                _record_trade(trades, pos, "A", ex, rows[ex[0]]["date"]); pos["a_closed"] = True
        if not (pos.get("d_closed") and pos.get("a_closed")):
            still_open.append(pos)
        else:
            closed_now.append(pos)

    # 1-b) 방식R(롱 한정) 그림자 장부 — 기록 전용, 주문·포지션 무관 (상단 주석 참조)
    r_added = shadow_r_records(trades, rows_of, regmap)
    if r_added:
        print(f"  [shadow-R] 방식R 행 {r_added}건 추가(기록 전용)")

    # 2) 신규 진입 (signals_today.json)

    # 실거래 포지션 현황 — 사이징·max 체크용
    live_open_count   = sum(1 for p in still_open if p.get("live_mode"))
    live_filled_count = live_open_count + sum(1 for t in trades if t.get("live_mode"))

    sig = _load("signals_today.json", {"signals": []})
    # 레짐 사이징 오버레이(보수적): 시장 avg_cap>0(알트 complacent 국면)이면 신규 롱
    # 사이즈 축소. 백테스트(backtest_regime_capture.py) — 집단 bleed 국면 롱 승률
    # 59% vs complacent 26%. 축소만(공포 국면 upsize 안 함), 타이밍 과적합 방어.
    market_cap = sig.get("avg_alt_cap")
    regime_long_weak = market_cap is not None and market_cap > REGIME_CAP_THR
    openkeys  = {(p["symbol"], p["pattern"], p["direction"], p["entry_date"]) for p in still_open}
    closedkeys = {(t["symbol"], t["pattern"], t["direction"], t["entry_date"]) for t in trades}
    new = 0
    live_orders = 0
    for s in sig.get("signals", []):
        rows = rows_of(s["symbol"], s.get("tf", "1d"))
        if rows is None:
            continue
        ei = _bar_idx(rows, s.get("ts"), s["date"])
        if ei is None:
            continue
        # 중복 진입 방어 키는 date 단위 유지 — 하위 TF에서는 '심볼·패턴당 하루 1회'
        # 라는 보수적 상한으로 작동한다(같은 날 여러 봉 신호 시 첫 건만).
        key = (s["symbol"], s["pattern"], s["direction"], s["date"])
        if key in openkeys or key in closedkeys:
            continue

        entry   = rows[ei]["c"]
        sig_entry = entry           # 신호봉 종가 — 실체결과 비교해 배리어 재정렬 판단
        spec    = EXIT_SPECS.get(s["pattern"])
        target_px = None
        atr = None
        if spec:
            # ATR 배리어 패턴: 손절·익절 모두 검증 프레임과 같은 ±k×ATR 로 산출.
            # ATR을 못 구하면(데이터 부족) 청산 규칙 자체가 정의되지 않으므로 진입 안 함.
            atr = ilab.atr_series(rows, spec.get("atr_period", 14))[ei]
            if not atr or atr <= 0:
                print(f"  [skip] {s['symbol']} {s['pattern']} ATR 산출 불가 — 진입 스킵")
                continue
            dist = spec.get("k_atr", ilab.K_ATR) * atr
            if s["direction"] == "long":
                stop_px, target_px = entry - dist, entry + dist
            else:
                stop_px, target_px = entry + dist, entry - dist
        else:
            stop_px = entry * (1 - STOP) if s["direction"] == "long" else entry * (1 + STOP)

        live_info    = {}
        # 앙상블 Grade 기반 사이징: A×1.5 / B×1.0 / C×0.7 / D×0.5
        grade        = s.get("ensemble_grade", "B")
        grade_mult   = GRADE_SIZE_MULT.get(grade, 1.0)
        size_for_pos = round(POS_USD * grade_mult, 2)
        # tf_confirmed=False → 추가로 ×0.5
        tf_ok        = s.get("tf_confirmed", True)
        if not tf_ok:
            size_for_pos = round(size_for_pos * 0.5, 2)
        # (RS weak_rs 필터 폐기 2026-07-08 — 레짐 중복, backtest_rs_controlled.py)
        # 레짐 오버레이: complacent 국면 + 롱 → ×REGIME_CAP_MULT (보수적, 축소만)
        regime_cut = bool(regime_long_weak and s["direction"] == "long")
        if regime_cut:
            size_for_pos = round(size_for_pos * REGIME_CAP_MULT, 2)
        if grade != "B" or not tf_ok or regime_cut:
            tf_tag = " [4h비확증×0.5]" if not tf_ok else ""
            rg_tag = f" [complacent×{REGIME_CAP_MULT}]" if regime_cut else ""
            print(f"  [사이징·페이퍼] {s['symbol']} {grade}등급×{grade_mult}{tf_tag}{rg_tag} → ${size_for_pos:.1f}"
                  f"  (실주문 크기는 아래 [live] 라인 — SIZING_MODE={SIZING_MODE})")

        # 킬스위치 발동 시 실주문 블록 전체 스킵(페이퍼 기록은 아래에서 계속)
        if live_conn and kill_switch:
            print(f"  [live] 킬스위치 발동 중 — {s['symbol']} 실거래 진입 스킵(페이퍼만)")

        if live_conn and not kill_switch:
            # 동시 최대 포지션 체크
            if live_open_count >= MAX_LIVE_POS:
                print(f"  [live] 최대 포지션({MAX_LIVE_POS}개) 도달 — {s['symbol']} 스킵")
                continue

            # 포지션 사이징 — SIZING_MODE 참조
            bal_info  = ex_mod.get_balance(live_conn)
            usdt_free = bal_info["free"] if isinstance(bal_info, dict) else float(bal_info or 0)
            live_lev  = None
            if SIZING_MODE == "risk":
                eq_now   = (bal_info or {}).get("equity") if isinstance(bal_info, dict) else None
                eq_now   = float(eq_now or 0.0)
                stop_pct = abs(entry - stop_px) / entry if entry else 0.0
                # 이미 열린 실거래 포지션의 명목가 합 (총 노출 캡용)
                open_notional = sum(
                    float(p.get("size_usd") or 0) * float((p.get("live_order") or {}).get("leverage") or 2)
                    for p in still_open if p.get("live_mode"))
                sz_ = sizing.risk_based_size(
                    eq_now, usdt_free, stop_pct, grade_mult=grade_mult,
                    regime_mult=(REGIME_CAP_MULT if regime_cut else 1.0),
                    open_notional=open_notional)
                if sz_ is None:
                    print(f"  [live 사이징] {s['symbol']} risk-based 스킵 (equity ${eq_now:.2f}, "
                          f"free ${usdt_free:.2f}, stop {stop_pct:.2%})")
                    continue
                live_size_usd, live_lev = sz_["margin_usd"], sz_["leverage"]
                print(f"  [live 사이징] {s['symbol']} risk={sz_['risk_usd']} notional=${sz_['notional']} "
                      f"lev={live_lev}x margin=${live_size_usd} ({sz_['capped_by']}) "
                      f"| equity ${eq_now:.2f} stop {stop_pct:.2%} 등급x{grade_mult}")
            else:
                # legacy: 첫 주문 $20 고정 / 이후 잔고 20% / complacent 롱 x0.6
                sz_ = sizing.legacy_size(usdt_free, live_filled_count,
                                         regime_mult=(REGIME_CAP_MULT if regime_cut else 1.0))
                if sz_ is None:
                    print(f"  [live] 최소주문금액 미만 — {s['symbol']} 스킵 (free ${usdt_free:.2f})")
                    continue
                live_size_usd = sz_["margin_usd"]

            result, reason = ex_mod.place_swap_entry(
                live_conn, s["symbol"], s["direction"], stop_px,
                size_usd=live_size_usd, target_px=target_px,
                **({"leverage": live_lev} if live_lev else {}),
            )
            if result is None:
                print(f"  [live] {s['symbol']} {s['direction']} 주문 실패: {reason}")
                # 주문 실패 시 size_for_pos = POS_USD (페이퍼 기록만 유지)
            else:
                live_info    = {"live_order": result, "live_mode": True}
                # 실체결 기준으로 기록 (신호가와 체결가 불일치 방지)
                entry        = result["entry_price"]
                stop_px      = result["stop_price"]
                if result.get("target_price"):
                    target_px = result["target_price"]
                # ATR 배리어 패턴은 배리어가 **진입가 기준 ±k×ATR** 로 정의된다
                # (intraday_lab.outcome_atr 이 base=rows[j]["c"] 로 잡는다).
                # 그런데 위에서 넘긴 손절·익절은 신호봉 종가 기준이고 실제 체결은
                # 수십 분 뒤 시장가라, 그대로 두면 체결가로부터의 거리가 ±1.5ATR 이
                # 아니게 된다 = 검증과 다른 청산 규칙. 체결가 기준으로 다시 걸어준다.
                if spec and abs(entry - sig_entry) > 1e-12:
                    dist_r = spec.get("k_atr", ilab.K_ATR) * atr
                    if s["direction"] == "long":
                        stop_px, target_px = entry - dist_r, entry + dist_r
                    else:
                        stop_px, target_px = entry + dist_r, entry - dist_r
                    ok_r = ex_mod.ensure_stop_orders(
                        live_conn,
                        stop_map={s["symbol"]: {"stop": stop_px, "target": target_px}})
                    print(f"  [live] {s['symbol']} 배리어를 체결가 기준으로 재정렬 "
                          f"(신호 {sig_entry:.6f} → 체결 {entry:.6f}, "
                          f"±{dist_r:.6f}) 재등록={ok_r}")
                size_for_pos = result.get("size_usd", live_size_usd)
                live_open_count   += 1
                live_filled_count += 1
                live_orders       += 1
                print(f"  [live] {s['symbol']} {s['direction']} 진입 OK | "
                      f"size=${size_for_pos:.2f} entry={result['entry_price']:.4f} "
                      f"sl={result['stop_price']:.4f}")
                import notify
                d_ko = "롱" if s["direction"] == "long" else "숏"
                notify.send(f"🟢 <b>실거래 진입</b> {s['symbol']} {d_ko}\n"
                            f"패턴: {s['pattern']} | ${size_for_pos:.2f}\n"
                            f"진입 {result['entry_price']:.4f} / 손절 {result['stop_price']:.4f}")

        rank      = s.get("priority_rank")
        cnt       = s.get("pattern_count", 1)
        fired     = s.get("patterns_fired", [s.get("pattern")])
        score     = s.get("ensemble_score")
        grade_out = s.get("ensemble_grade", "B")
        GRADE_ICON = {"A": "🔥", "B": "⭐", "C": "🔵", "D": "⚪"}
        rank_str  = f"#{rank}" if rank else ""
        score_str = f" [{score:.1f}]" if score is not None else ""
        multi_str = " [멀티]" if cnt > 1 else ""
        icon_str  = GRADE_ICON.get(grade_out, "")
        print(f"  [paper] 신규: {rank_str} {icon_str}{grade_out}{score_str} "
              f"{s['symbol']} {fired} {s['direction']}{multi_str} ${size_for_pos:.0f}")
        p = dict(symbol=s["symbol"], direction=s["direction"], pattern=s["pattern"],
                 regime=s.get("regime"), tf=s.get("tf", "1d"),
                 entry_date=s["date"], entry_ts=s.get("ts") or rows[ei].get("ts"),
                 entry_idx=ei,
                 entry_price=round(entry, 4),
                 # ATR 배리어는 거리가 0.75~1.5%로 좁아 4자리 반올림이 저가 코인에서
                 # 배리어를 유의미하게 왜곡한다 → spec 패턴만 8자리 보존.
                 stop=round(stop_px, 8 if spec else 4),
                 target=(round(target_px, 8) if target_px else None),
                 size_usd=size_for_pos, d_closed=False,
                 a_closed=bool(spec),      # ATR 경로는 방식A 병행 비교 없음
                 **live_info)
        still_open.append(p); new_positions.append(p); new += 1

    # JSON은 항상 저장(로컬 폴백/원천)
    _save(POS_FILE, still_open)
    _save(TRD_FILE, trades)
    # Supabase 동기화(가능 시): 이번 실행 신규 체결/신규 포지션만 INSERT
    new_trades = trades[t0:]
    dbt = push_trades_db(new_trades)
    dbp = push_positions_db(new_positions)
    mark_closed_db(closed_now)
    dbmsg = f" | DB동기화 trades+{dbt}/positions+{dbp}" if _db() else " | DB미설정(JSON만)"
    live_msg = f" | 실거래주문 {live_orders}건" if live_conn else ""
    print(f"[paper] 신규진입 {new}건 | 오픈 {len(still_open)}건 | 누적 체결 {len(trades)}건{live_msg}{dbmsg}")
    return dict(new=new, open=len(still_open), trades=len(trades))


def selftest():
    """과거 engulfing 롱 신호 1건을 끝까지(진입->청산) 돌려 엔진 검증(파일 미기록)."""
    regmap = rs.build_regime_map()
    eng = importlib.import_module("detector_engulfing")
    opp = importlib.import_module("detector_engulfing_short")
    rows = eng.load_ohlcv("BTC", "1d")
    opp_set = set(opp.detect(rows))
    for ei in eng.detect(rows):
        if rows[ei]["date"] < "2023-06-01":           # 청산될 만큼 과거
            d = eval_D(rows, ei, "long", opp_set, regmap)
            a = eval_A(rows, ei, "long")
            print(f"[selftest] BTC engulfing long 진입 {rows[ei]['date']} @ {rows[ei]['c']:.1f}")
            print(f"  방식D 청산: bar+{d[0]-ei}, px {d[1]:.1f}, ret {d[2]*100:+.2f}%, 사유 {d[3]}")
            print(f"  방식A 청산: bar+{a[0]-ei}, px {a[1]:.1f}, ret {a[2]*100:+.2f}%, 사유 {a[3]}")
            return


def seed(days=60):
    """최근 days봉의 라우팅-방향 engulfing/fvg 신호로 페이퍼 포트폴리오 부트스트랩.
    (오늘 신호가 없을 때 실데이터로 전체 사이클을 시연하기 위한 1회 킥스타트.)"""
    regmap = rs.build_regime_map()
    routing = _load("direction_switch.json", {"routing": {}})["routing"]
    positions = _load(POS_FILE, [])
    keys = {(p["symbol"], p["pattern"], p["direction"], p["entry_date"]) for p in positions}
    universe = _load("universe.json", {}).get("trading_universe") or list(detlib.SYMBOLS)
    added = 0
    for sym in universe:
        rows = detlib.load_ohlcv(sym, "1d")
        last = len(rows) - 1
        for pat in ("engulfing", "fvg"):
            for d in ("long", "short"):
                mod = importlib.import_module(DETMOD[(pat, d)])
                for ei in mod.detect(rows):
                    if ei < last - days:
                        continue
                    rg = regmap.get(rows[ei]["date"])
                    if not rg or routing.get(rg, {}).get(pat) != d:
                        continue
                    key = (sym, pat, d, rows[ei]["date"])
                    if key in keys:
                        continue
                    entry = rows[ei]["c"]
                    stop_px = entry * (1 - STOP) if d == "long" else entry * (1 + STOP)
                    positions.append(dict(symbol=sym, direction=d, pattern=pat, regime=rg,
                                          entry_date=rows[ei]["date"], entry_idx=ei,
                                          entry_price=round(entry, 4), stop=round(stop_px, 4),
                                          size_usd=POS_USD, d_closed=False, a_closed=False))
                    keys.add(key); added += 1
    _save(POS_FILE, positions)
    print(f"[seed] 최근 {days}봉에서 {added}건 진입 시드 -> 모니터링 실행")
    run()


def migrate():
    """기존 JSON(paper_trades/positions)을 Supabase로 1회 마이그레이션."""
    if not _db():
        print("[migrate] DB 미설정 - 스킵(JSON 유지)")
        return
    n = push_trades_db(_load(TRD_FILE, []))
    p = push_positions_db(_load(POS_FILE, []))
    print(f"[migrate] Supabase 이관: trades {n}건 / positions {p}건")


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "selftest":
        selftest()
    elif arg == "seed":
        seed()
    elif arg == "migrate":
        migrate()
    else:
        run()
