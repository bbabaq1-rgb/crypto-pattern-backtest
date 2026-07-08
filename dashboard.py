"""
dashboard.py — 암호화폐 패턴 자동매매 실시간 대시보드
실거래(OKX) / 페이퍼테스트 탭 분리 / 30초 자동갱신
"""
import streamlit as st
import pandas as pd
import json
import os
import time
from datetime import datetime, timezone, date
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ── 페이지 설정 ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Crypto Dashboard",
    page_icon="🪙",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
    .main .block-container {
        padding-top: 0.6rem; padding-bottom: 1rem;
        max-width: 700px; padding-left: 0.8rem; padding-right: 0.8rem;
    }
    h1 { font-size: 1.5rem !important; margin-bottom: 0.4rem; }
    h2, h3 { font-size: 1.15rem !important; margin-bottom: 0.3rem; }
    div[data-testid="stMetricValue"] { font-size: 1.45rem !important; }
    div[data-testid="stMetricLabel"] { font-size: 0.88rem !important; }
    div[data-testid="stMetricDelta"] { font-size: 0.88rem !important; }
    .stTabs [data-baseweb="tab"] { font-size: 0.95rem; padding: 6px 14px; }
    .stButton > button { font-size: 0.9rem; padding: 0.3rem 0.8rem; }
    [data-testid="stDataFrame"] table { font-size: 0.82rem !important; }
    .stCaption { font-size: 0.8rem; }
</style>
""", unsafe_allow_html=True)

REFRESH_SEC = 30
PERF_START  = "2026-06-27"
PAPER_CAP   = 200.0    # 페이퍼 가상자본 $
INITIAL_CAP = 2000.0   # daily_summary 기준 자본 (비율 환산용)

# ── 환경변수 ──────────────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv(override=False)
except ImportError:
    pass

# Streamlit Cloud Secrets → os.environ
try:
    _KEYS = ("OKX_KEY", "OKX_SECRET", "OKX_PASSPHRASE",
             "SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_KEY")
    for _k in _KEYS:
        if _k in st.secrets and _k not in os.environ:
            os.environ[_k] = str(st.secrets[_k])
except Exception:
    pass

# ── Supabase ───────────────────────────────────────────────────────────────────
@st.cache_resource
def _supabase():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_ANON_KEY") or os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        return None
    try:
        from supabase import create_client
        return create_client(url, key)
    except Exception:
        return None


# ── 데이터 로더 ────────────────────────────────────────────────────────────────

@st.cache_data(ttl=25)
def load_trades():
    """Supabase trades + paper_trades.json. Supabase 우선 중복 제거."""
    dfs = []
    cli = _supabase()
    if cli:
        try:
            r = cli.table("trades").select("*").order("entry_date", desc=True).limit(200).execute()
            if r.data:
                df = pd.DataFrame(r.data)
                if "return_pct" not in df.columns and "ret" in df.columns:
                    df["return_pct"] = (df["ret"] * 100).round(4)
                df["_src"] = "db"
                dfs.append(df)
        except Exception:
            pass

    if os.path.exists("paper_trades.json"):
        try:
            data = json.load(open("paper_trades.json", encoding="utf-8"))
            if data:
                df2 = pd.DataFrame(data)
                if "return_pct" not in df2.columns and "ret" in df2.columns:
                    df2["return_pct"] = (df2["ret"] * 100).round(4)
                df2["_src"] = "json"
                dfs.append(df2)
        except Exception:
            pass

    if not dfs:
        return pd.DataFrame()

    combined = pd.concat(dfs, ignore_index=True)
    dedup = [c for c in ["symbol", "pattern", "direction", "entry_date", "method"] if c in combined.columns]
    if dedup:
        combined = combined.sort_values("_src")
        combined = combined.drop_duplicates(subset=dedup, keep="first")
    if "entry_date" in combined.columns:
        combined = combined.sort_values("entry_date", ascending=False)

    # live_mode 판정 — DB에 live_mode 컬럼이 없어도(=DDL 미적용) 동작하도록
    # exit_reason의 '실거래' 마커를 1차 기준으로 사용(모든 실거래 청산에 부여).
    # 컬럼이 있으면 그 값도 OR로 반영. 마커가 없던 과거 수동청산은 컬럼 부재 시에만 추론.
    had_live_col = "live_mode" in combined.columns
    if not had_live_col:
        combined["live_mode"] = False
    combined["live_mode"] = combined["live_mode"].fillna(False).astype(bool)
    if "exit_reason" in combined.columns:
        er = combined["exit_reason"].astype(str)
        combined.loc[er.str.contains("실거래", na=False), "live_mode"] = True
        if not had_live_col:   # 마커 이전 수동청산 호환(컬럼도 마커도 없을 때만)
            combined.loc[er.str.contains("수동", na=False), "live_mode"] = True

    return combined.drop(columns=["_src"], errors="ignore").head(200)


@st.cache_data(ttl=25)
def load_positions():
    cli = _supabase()
    if cli:
        try:
            r = cli.table("positions").select("*").eq("status", "open").execute()
            if r.data:
                df = pd.DataFrame(r.data)
                if "live_mode" not in df.columns:
                    df["live_mode"] = False
                df["live_mode"] = df["live_mode"].fillna(False).astype(bool)
                # method의 LIVE 인코딩(AD-LIVE)으로 실거래 판정 보강 — live_mode 컬럼 부재 대응
                if "method" in df.columns:
                    df.loc[df["method"].astype(str).str.upper().str.endswith("LIVE"),
                           "live_mode"] = True
                if "stop_loss" not in df.columns and "stop" in df.columns:
                    df["stop_loss"] = df["stop"]
                # 과거 중복 insert 오염 방어 (동일 키 첫 행만 표시)
                dedup_keys = [c for c in ("symbol", "pattern", "direction", "entry_date")
                              if c in df.columns]
                if dedup_keys:
                    df = df.drop_duplicates(subset=dedup_keys, keep="first")
                return df
        except Exception:
            pass
    return pd.DataFrame()


@st.cache_data(ttl=25)
def load_daily_summary():
    cli = _supabase()
    if cli:
        try:
            r = cli.table("daily_summary").select("*").order("date").execute()
            if r.data:
                return pd.DataFrame(r.data)
        except Exception:
            pass
    return pd.DataFrame()


@st.cache_data(ttl=25)
def load_signals():
    today = date.today().isoformat()
    cli   = _supabase()
    if cli:
        try:
            r = cli.table("signals").select("*").eq("date", today).execute()
            if r.data:
                return pd.DataFrame(r.data)
        except Exception:
            pass
    # Supabase 없거나 오늘 데이터 없으면 signals_today.json 폴백
    # (단, 파일이 오늘 생성된 경우만 — 어제 신호가 '오늘 신호'로 보이는 것 방지)
    try:
        if os.path.exists("signals_today.json"):
            raw = json.load(open("signals_today.json", encoding="utf-8"))
            gen = str(raw.get("generated_at", ""))[:10]
            sigs = raw.get("signals", [])
            if sigs and gen == today:
                return pd.DataFrame(sigs)
    except Exception:
        pass
    return pd.DataFrame()


def load_regime():
    if os.path.exists("direction_switch.json"):
        try:
            d = json.load(open("direction_switch.json", encoding="utf-8"))
            return d.get("current", {}), d.get("routing", {})
        except Exception:
            pass
    return {}, {}


@st.cache_data(ttl=60)
def load_onchain():
    """signals_today.json 상위 온체인 필드 반환. 없으면 None."""
    if os.path.exists("signals_today.json"):
        try:
            d = json.load(open("signals_today.json", encoding="utf-8"))
            score  = d.get("onchain_score")
            detail = d.get("onchain_detail", {})
            primary = d.get("primary_regime", d.get("regime", ""))
            final   = d.get("regime", "")
            if score is not None:
                return {"score": score, "detail": detail,
                        "primary_regime": primary, "final_regime": final}
        except Exception:
            pass
    return None


def _save_regime_to_supabase(regime_map):
    """레짐 히스토리를 Supabase daily_summary에 upsert (regime 컬럼)."""
    cli = _supabase()
    if not cli or not regime_map:
        return
    try:
        rows = [{"date": d, "regime": r} for d, r in regime_map.items()]
        for i in range(0, len(rows), 100):
            cli.table("daily_summary").upsert(
                rows[i:i+100], on_conflict="date"
            ).execute()
    except Exception:
        pass


@st.cache_data(ttl=3600)
def _load_regime_history():
    """날짜→레짐 dict. daily_summary → regime_switch.py → direction_switch.json 순으로 시도."""
    # 1. daily_summary에 regime 컬럼이 있으면 사용
    df = load_daily_summary()
    if not df.empty and "regime" in df.columns and "date" in df.columns:
        valid = df[df["regime"].notna() & (df["regime"].astype(str) != "")]
        if not valid.empty:
            return dict(zip(valid["date"].astype(str), valid["regime"]))

    # 2. 로컬 CSV 기반으로 regime_switch.py 실행 (Streamlit Cloud에선 CSV 없어 스킵)
    try:
        import regime_switch as rs
        regime_map = rs.build_regime_map()
        if regime_map:
            _save_regime_to_supabase(regime_map)
            return regime_map
    except Exception:
        pass

    # 3. direction_switch.json 현재 레짐만
    current, _ = load_regime()
    r  = current.get("regime")
    dt = current.get("date")
    if r and dt:
        return {dt: r}
    return {}


@st.cache_resource
def _okx_exchange():
    """ccxt OKX 인스턴스를 세션 1회만 생성(load_markets 포함)해 재사용.

    기존엔 청산·새로고침마다 connect_live()가 load_markets()(전 마켓 메타 수 초 소요)를
    매번 호출해 매우 느렸다. cache_resource로 마켓 로드를 1회로 고정 → 이후 잔고조회·
    주문은 즉시. 세션 내 공유(단일 사용자 대시보드라 안전).
    """
    import os
    import exchange as ex_mod
    if not ex_mod.is_live():
        return None
    try:
        import ccxt
        ex = ccxt.okx({
            "apiKey":   os.environ["OKX_KEY"],
            "secret":   os.environ["OKX_SECRET"],
            "password": os.environ["OKX_PASSPHRASE"],
            "enableRateLimit": True,
        })
        ex.load_markets()
        return ex
    except Exception:
        return None


@st.cache_data(ttl=25)
def fetch_account_balance():
    """
    OKX 잔고 + 실제 포지션 조회. (캐시된 exchange 재사용 — load_markets 반복 제거)
    반환: (bal_dict | None, okx_positions | [], is_live, err_msg | None)
    """
    import exchange as ex_mod
    if not ex_mod.is_live():
        return None, [], False, None  # 키 미설정
    ex = _okx_exchange()
    if ex is None:
        return None, [], True, "OKX 연결 실패(마켓 로드 실패)"
    try:
        conn = {"exchange": ex}
        bal  = ex_mod.get_balance(conn)
        poss = ex_mod.get_okx_positions(conn)
        if bal is None:
            return None, poss, True, "get_balance() returned None"
        return bal, poss, True, None
    except Exception as e:
        return None, [], True, str(e)[:200]


@st.cache_resource
def _okx_public():
    """시세 조회용 공개(키 불필요) OKX 인스턴스 — 세션 재사용."""
    try:
        import ccxt
        return ccxt.okx({"enableRateLimit": True})
    except Exception:
        return None


@st.cache_data(ttl=60)
def fetch_prices(symbols_tuple):
    """
    OKX 선물(USDT 무기한) 현재가 일괄 조회.
    fetch_tickers 배치 1회 호출(종목별 순차 fetch_ticker의 N회 왕복 → 1회로 단축).
    실패 시 스팟 일괄, 그래도 없으면 개별 폴백.
    """
    if not symbols_tuple:
        return {}
    ex = _okx_public()
    if ex is None:
        return {}
    result = {}
    swap_syms = [f"{s}/USDT:USDT" for s in symbols_tuple]
    # 1) 선물 일괄
    try:
        tk = ex.fetch_tickers(swap_syms)
        for s in symbols_tuple:
            t = tk.get(f"{s}/USDT:USDT")
            if t and t.get("last"):
                result[s] = float(t["last"])
    except Exception:
        pass
    # 2) 누락분 스팟 일괄
    missing = [s for s in symbols_tuple if s not in result]
    if missing:
        try:
            tk = ex.fetch_tickers([f"{s}/USDT" for s in missing])
            for s in missing:
                t = tk.get(f"{s}/USDT")
                if t and t.get("last"):
                    result[s] = float(t["last"])
        except Exception:
            pass
    return result


# ── 포맷 헬퍼 ─────────────────────────────────────────────────────────────────

REGIME_EMOJI = {"bear": "🐻", "bull_btc": "🐂", "bull_altseason": "🌊", "sideways": "↔️"}
DIR_LABEL    = {"long": "🟢 롱", "short": "🔴 숏", "FLAT": "— FLAT"}


def _fmt_price(v):
    try:
        v = float(v)
        if v == 0:   return "—"
        if v >= 100: return f"{v:,.2f}"
        if v >= 1:   return f"{v:.4f}"
        return f"{v:.6f}"
    except Exception:
        return "—"


def _fmt_pct(v, sign=True):
    try:
        v = float(v)
        return f"{v:+.2f}%" if sign else f"{v:.2f}%"
    except Exception:
        return "—"


def _ret_dot(v):
    try:
        return "🟢" if float(v) > 0 else "🔴" if float(v) < 0 else "⬜"
    except Exception:
        return "⬜"


def _rebase_cum(daily_df, col):
    if daily_df.empty or col not in daily_df.columns:
        return None
    df       = daily_df.sort_values("date")
    before   = df[df["date"] < PERF_START]
    baseline = float(before.iloc[-1][col]) if not before.empty else 0.0
    after    = df[df["date"] >= PERF_START]
    if after.empty:
        return None
    return round(float(after.iloc[-1][col]) - baseline, 4)


def _filter_by_mode(df, live):
    """DataFrame을 live_mode 컬럼으로 필터링. 컬럼 없으면 paper 전체/live 빈 df."""
    if df.empty:
        return df
    if "live_mode" in df.columns:
        return df[df["live_mode"] == live].copy()
    return df.copy() if not live else pd.DataFrame()


def _unrealized_pnl(pos_df, prices, live):
    """오픈 포지션 미실현 손익 합산."""
    df = _filter_by_mode(pos_df, live)
    total = 0.0
    for _, pos in df.iterrows():
        sym  = str(pos.get("symbol", ""))
        d    = str(pos.get("direction", ""))
        ep   = float(pos.get("entry_price") or 0)
        sz   = float(pos.get("size_usd") or 0)
        lv   = 2.0 if live else 1.0
        cp   = prices.get(sym)
        if cp and ep and sz:
            total += sz * lv * ((cp - ep) / ep if d == "long" else (ep - cp) / ep)
    return round(total, 2)


# ── 청산 헬퍼 ─────────────────────────────────────────────────────────────────

def _close_live_okx(sym, direction):
    try:
        ex = _okx_exchange()          # 캐시된 인스턴스(load_markets 생략)
        if ex is None:
            return False, "OKX 연결 실패"
        ccxt_sym = f"{sym}/USDT:USDT"
        for p in ex.fetch_positions([ccxt_sym]):
            qty = abs(float(p.get("contracts") or 0))
            if qty > 0:
                side = "sell" if direction == "long" else "buy"
                ex.create_market_order(ccxt_sym, side, qty, params={
                    "tdMode": "isolated", "reduceOnly": True,
                })
                return True, f"시장가 청산 qty={qty}"
        return False, "OKX에서 포지션 미확인"
    except Exception as e:
        return False, str(e)[:80]


def _record_manual_close(sym, direction, entry, exit_px, *, pattern=None,
                         entry_date=None, regime=None, pnl_usd=None,
                         size_usd=None, live_mode=True):
    """
    수동 청산을 trades 테이블 + paper_trades.json 에 기록.
    최근매매내역/일별PNL/패턴별성과가 전부 trades 를 읽으므로, 기록이 없으면
    청산해도 아무 화면에 안 뜬다 (OKX 폴백 청산 버튼의 누락 버그 수정).

    방식 A·D 두 행으로 기록 — 기존 _do_close_position 관례와 동일(양 탭 표시).
    pattern/entry_date/regime 미지정 시 positions 테이블에서 보강, 없으면 기본값.
    """
    today_str = date.today().isoformat()
    cli = _supabase()

    # positions 테이블에서 패턴/진입일/레짐 보강 (OKX 폴백엔 이 정보가 없음)
    if cli and (not pattern or not entry_date):
        try:
            q = (cli.table("positions").select("*")
                 .eq("symbol", sym).eq("direction", direction)
                 .order("entry_date", desc=True).limit(1).execute())
            if q.data:
                row = q.data[0]
                pattern    = pattern    or row.get("pattern")
                entry_date = entry_date or row.get("entry_date")
                regime     = regime     or row.get("regime")
                size_usd   = size_usd if size_usd is not None else row.get("size_usd")
        except Exception:
            pass
    pattern    = pattern or "수동"
    entry_date = entry_date or today_str
    ret_val    = ((exit_px - entry) / entry if direction == "long"
                  else (entry - exit_px) / entry) if (entry and exit_px) else 0.0
    if pnl_usd is None and size_usd:
        pnl_usd = round(ret_val * float(size_usd), 2)

    # '실거래' 마커: live_mode 컬럼이 없어도 실거래 청산으로 인식되게 exit_reason에 부여.
    # 실거래 수동청산은 '방식D 단일'로만 기록(실거래는 방식D=실제 매도, 방식A는 페이퍼
    # 비교 전용). 페이퍼 수동청산만 A·D 둘 다 기록. → 실거래 탭 A/D 중복 표시 방지.
    exit_reason = "수동청산 ·실거래" if live_mode else "수동청산"
    methods = ("D",) if live_mode else ("A", "D")
    recorded = 0
    if cli and entry and exit_px:
        for method in methods:
            try:
                _insert_trade_tolerant(cli, {
                    "symbol": sym, "pattern": pattern, "direction": direction,
                    "entry_date": entry_date, "entry_price": entry,
                    "exit_date": today_str, "exit_price": round(exit_px, 6),
                    "return_pct": round(ret_val * 100, 4), "hold_bars": 0,
                    "exit_reason": exit_reason, "method": method,
                    "pnl_usd": pnl_usd, "live_mode": bool(live_mode),
                })
                recorded += 1
            except Exception as e:
                print("[manual-close] trades insert 실패:", str(e)[:60])

    # 로컬 JSON에도 반영(러너/로컬 폴백)
    if os.path.exists("paper_trades.json") and entry and exit_px:
        try:
            tl = json.load(open("paper_trades.json", encoding="utf-8"))
            for method in methods:
                tl.append(dict(
                    method=method, symbol=sym, direction=direction, pattern=pattern,
                    regime=regime, entry_date=entry_date, entry_price=entry,
                    exit_date=today_str, exit_price=round(exit_px, 6),
                    ret=round(ret_val, 6),
                    pnl_usd=pnl_usd if pnl_usd is not None else round(ret_val * (size_usd or 0), 2),
                    hold_bars=0, reason=exit_reason, method_label=method, live_mode=bool(live_mode)))
            json.dump(tl, open("paper_trades.json", "w", encoding="utf-8"),
                      ensure_ascii=False, indent=2)
        except Exception:
            pass

    # 해당 오픈 포지션을 closed 로 표시
    if cli:
        try:
            (cli.table("positions").update({"status": "closed"})
             .eq("symbol", sym).eq("direction", direction).eq("status", "open").execute())
        except Exception:
            pass
    return recorded


def _insert_trade_tolerant(cli, row):
    """스키마에 없는 컬럼(pnl_usd/live_mode 등) 자동 제외 후 재시도."""
    import re
    r = dict(row)
    for _ in range(6):
        try:
            cli.table("trades").insert(r).execute()
            return
        except Exception as e:
            m = re.search(r"Could not find the '(\w+)' column", str(e))
            if not m:
                raise
            r.pop(m.group(1), None)
    raise RuntimeError("insert_trade_tolerant: 컬럼 제거 한도 초과")


def _do_close_position(pos_row, cur_price):
    sym        = str(pos_row.get("symbol", ""))
    direction  = str(pos_row.get("direction", ""))
    entry      = float(pos_row.get("entry_price") or 0)
    size_usd   = float(pos_row.get("size_usd") or 0)
    live       = bool(pos_row.get("live_mode", False))
    pos_id     = pos_row.get("id")
    entry_date = str(pos_row.get("entry_date", ""))
    pattern    = str(pos_row.get("pattern", ""))
    regime     = str(pos_row.get("regime", ""))
    today_str  = date.today().isoformat()
    msgs       = []

    if live:
        ok, msg = _close_live_okx(sym, direction)
        msgs.append(msg)
        if not ok:
            return False, msg

    cli = _supabase()
    if cli and pos_id:
        try:
            cli.table("positions").update({"status": "closed"}).eq("id", pos_id).execute()
            msgs.append("DB 업데이트")
        except Exception as e:
            msgs.append(f"DB 실패: {str(e)[:30]}")

    if cli and cur_price and entry:
        ret_val = (cur_price - entry) / entry if direction == "long" else (entry - cur_price) / entry
        for method in ["A", "D"]:
            try:
                cli.table("trades").insert({
                    "symbol": sym, "pattern": pattern, "direction": direction,
                    "entry_date": entry_date, "entry_price": entry,
                    "exit_date": today_str, "exit_price": round(cur_price, 4),
                    "return_pct": round(ret_val * 100, 4), "hold_bars": 0,
                    "exit_reason": "수동청산", "method": method,
                }).execute()
            except Exception:
                pass

    pos_key = (sym, pattern, direction, entry_date)
    if os.path.exists("paper_positions.json"):
        try:
            pl = json.load(open("paper_positions.json", encoding="utf-8"))
            for i, p in enumerate(pl):
                if (p.get("symbol"), p.get("pattern"), p.get("direction"), p.get("entry_date")) == pos_key:
                    pl[i]["d_closed"] = True
                    pl[i]["a_closed"] = True
                    break
            json.dump(pl, open("paper_positions.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        except Exception:
            pass

    if os.path.exists("paper_trades.json") and cur_price and entry:
        try:
            tl      = json.load(open("paper_trades.json", encoding="utf-8"))
            ret_val = (cur_price - entry) / entry if direction == "long" else (entry - cur_price) / entry
            for method in ["A", "D"]:
                tl.append(dict(
                    method=method, symbol=sym, direction=direction, pattern=pattern,
                    regime=regime, entry_date=entry_date, entry_price=entry,
                    exit_date=today_str, exit_price=round(cur_price, 4),
                    ret=round(ret_val, 5), pnl_usd=round(ret_val * size_usd, 2),
                    hold_bars=0, reason="수동청산", method_label=method,
                ))
            json.dump(tl, open("paper_trades.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        except Exception:
            pass

    return True, " · ".join(msgs) if msgs else "청산 완료"


# ── 온체인 보조 신호 공통 렌더 ────────────────────────────────────────────────

def _render_onchain_section(oc: dict):
    """온체인 보조 신호 expander 렌더. load_onchain() 반환값을 받음."""
    det   = oc.get("detail", {})
    score = oc.get("score", 0)
    pri   = oc.get("primary_regime", "")
    fin   = oc.get("final_regime", "")

    ICONS      = {"bull": "🟢", "bear": "🔴", "neutral": "🟡"}
    fund_icon  = ICONS.get(det.get("funding", "neutral"), "🟡")
    etf_icon   = ICONS.get(det.get("etf",     "neutral"), "🟡")
    stab_icon  = ICONS.get(det.get("stable",  "neutral"), "🟡")

    fund_rate  = det.get("funding_avg_rate")
    stable_pct = det.get("stable_7d_pct")
    etf_sig    = det.get("etf", "neutral")

    fund_label  = f"{fund_rate:+.4f}%" if fund_rate is not None else "—"
    etf_label   = ("3일 유입" if etf_sig == "bull"
                   else "3일 유출" if etf_sig == "bear" else "혼합")
    stable_label = f"{stable_pct:+.2f}%" if stable_pct is not None else "—"

    score_color = "#26a641" if score > 0 else "#f85149" if score < 0 else "#888"
    score_text  = (f"{score:+d} "
                   f"({'bull 우세' if score > 0 else 'bear 우세' if score < 0 else '중립'})")
    changed     = pri and fin and pri != fin
    adj_note    = f"  →  `{pri}` → `{fin}` (온체인 완화)" if changed else ""

    with st.expander("📡 온체인 보조 신호", expanded=False):
        c1, c2, c3 = st.columns(3)
        c1.markdown(
            f"{fund_icon} **펀딩비**: {det.get('funding', '—')}  \n`{fund_label}`")
        c2.markdown(
            f"{etf_icon} **ETF 유입**: {etf_sig}  \n{etf_label}")
        c3.markdown(
            f"{stab_icon} **스테이블코인**: {det.get('stable', '—')}  \n`{stable_label}`")
        st.markdown(
            f"<span style='color:{score_color};font-weight:700'>"
            f"온체인 종합 점수: {score_text}</span>{adj_note}",
            unsafe_allow_html=True,
        )


# ── 실거래 탭 섹션 ─────────────────────────────────────────────────────────────

def _load_alt_metric(field):
    """signals_today.json(오늘 생성분) → daily_summary 순으로 지표 로드."""
    try:
        if os.path.exists("signals_today.json"):
            raw = json.load(open("signals_today.json", encoding="utf-8"))
            if str(raw.get("generated_at", ""))[:10] == date.today().isoformat():
                v = raw.get(field)
                if v is not None:
                    return float(v)
    except Exception:
        pass
    try:
        df = load_daily_summary()
        if not df.empty and field in df.columns:
            v = df.sort_values("date")[field].dropna()
            if len(v):
                return float(v.iloc[-1])
    except Exception:
        pass
    return None


def _render_regime_header():
    """현재 레짐(불/베어 등) + 방향 라우팅 + 알트시즌 근접도 게이지."""
    current, _ = load_regime()
    regime      = current.get("regime", "—")
    regime_date = current.get("date", "")
    action      = current.get("action", {})
    r_emoji = REGIME_EMOJI.get(regime, "❓")
    dir_text = "  |  ".join(f"{k} → {DIR_LABEL.get(v, v)}" for k, v in action.items()) if action else "—"
    st.markdown(f"### {r_emoji} {regime} `{regime_date}`")
    st.caption(dir_text)

    # 알트시즌 근접도 게이지 (유니버스 평균 alt RS, -1 약세 ~ +1 강세)
    aar = _load_alt_metric("avg_alt_rs")
    if aar is not None:
        pct = int(round((aar + 1) / 2 * 100))          # -1..+1 → 0..100
        state = "🌊 알트 강세(로테이션)" if aar > 0.1 else \
                "🐂 BTC 주도" if aar < -0.1 else "😐 중립"
        st.progress(min(100, max(0, pct)) / 100,
                    text=f"알트시즌 근접도 {aar:+.2f} — {state}")

    # 시장 비대칭 국면 게이지 (avg_cap — 롱 타이밍 레짐 지표, 백테스트 채택)
    acap = _load_alt_metric("avg_alt_cap")
    if acap is not None:
        pct = int(round((acap + 1) / 2 * 100))
        # 낮을수록(집단 bleed) 반전 롱 우호 → 사이징 그대로 / 높으면 complacent → 롱 축소
        state = "💥 집단 bleed — 반전 롱 우호(풀사이즈)" if acap < -0.2 else \
                "😴 complacent — 신규 롱 축소(×0.6)" if acap > 0 else "😐 중립"
        st.progress(min(100, max(0, pct)) / 100,
                    text=f"시장 비대칭(avg_cap) {acap:+.2f} — {state}")


def section_live_summary(pos_df, trades_df, prices):
    now_str = datetime.now(timezone.utc).strftime("%m/%d %H:%M UTC")
    bal_dict, okx_poss, is_live_mode, err_msg = fetch_account_balance()

    if bal_dict is None:
        if is_live_mode:
            st.warning(f"OKX 연결 오류 — 30초 후 자동 재시도  \n`{err_msg}`")
        else:
            st.info("OKX 미연결 — Streamlit Secrets에 OKX_KEY / OKX_SECRET / OKX_PASSPHRASE 설정 시 실계좌 잔고 표시")
        live_pos_db = _filter_by_mode(pos_df, live=True)
        live_trd    = _filter_by_mode(trades_df, live=True)
        c1, c2 = st.columns(2)
        c1.metric("실거래 포지션", f"{len(live_pos_db)}개")
        c2.metric("실거래 체결",   f"{len(live_trd)}건")
        st.caption(f"🕐 {now_str}  ·  {REFRESH_SEC}초 자동갱신")
    else:
        equity = bal_dict.get("equity", 0.0)
        free   = bal_dict.get("free",   0.0)

        # OKX 실제 미실현 P&L (API 직접)
        okx_upnl = sum(p.get("unrealized_pnl", 0) for p in okx_poss)
        pnl_sign = "+" if okx_upnl >= 0 else ""
        pnl_dot  = "🟢" if okx_upnl >= 0 else "🔴"
        pnl_pct  = round(okx_upnl / equity * 100, 2) if equity > 0 else 0.0
        pct_sign = "+" if pnl_pct >= 0 else ""

        st.markdown(f"""
<div style="padding:0.4rem 0 0.1rem 0">
  <div style="font-size:0.82rem;color:#888;margin-bottom:0.1rem">총 자산 (equity) · OKX 선물</div>
  <div style="font-size:2.6rem;font-weight:700;line-height:1.15;color:#fafafa">${equity:,.2f}</div>
  <div style="font-size:1.0rem;color:{'#00cc66' if okx_upnl>=0 else '#ff4444'};margin-top:0.15rem">
    {pnl_dot} 미실현 P&L (OKX): {pnl_sign}${okx_upnl:.2f} ({pct_sign}{pnl_pct:.2f}%)
  </div>
</div>""", unsafe_allow_html=True)
        st.caption(f"가용 잔고: ${free:,.2f}  ·  🕐 {now_str}  ·  {REFRESH_SEC}초 자동갱신")

        # 실거래 탭은 OKX 실측을 원천으로 하므로 DB 대조·경고는 표시하지 않는다.
        live_trd = _filter_by_mode(trades_df, live=True)
        c1, c2 = st.columns(2)
        c1.metric("진입 완료 (OKX)", f"{len(okx_poss)}개")
        c2.metric("청산 완료",       f"{len(live_trd)}건")

    # 현재 레짐(불/베어) — 페이퍼 탭과 동일하게 실거래 탭에도 표시
    _render_regime_header()

    # 온체인 보조 신호 (실거래 탭)
    oc = load_onchain()
    if oc is not None:
        _render_onchain_section(oc)
    st.divider()


# ── 페이퍼 탭 섹션 ─────────────────────────────────────────────────────────────

def section_paper_summary(pos_df, trades_df, daily_df, prices):
    now_str = datetime.now(timezone.utc).strftime("%m/%d %H:%M UTC")
    current, _ = load_regime()
    regime      = current.get("regime", "—")
    regime_date = current.get("date", "")
    action      = current.get("action", {})

    unreal_pnl   = _unrealized_pnl(pos_df, prices, live=False)
    paper_trd    = _filter_by_mode(trades_df, live=False)

    # 실현 손익: daily_summary 누적수익률 기준 (PERF_START 재기산)
    cum_a = _rebase_cum(daily_df, "cumulative_return_a")
    cum_d = _rebase_cum(daily_df, "cumulative_return_d")

    # daily_summary 없으면 trades pnl_usd 합산
    if cum_a is None and not paper_trd.empty:
        m = "method" if "method" in paper_trd.columns else "method_label" if "method_label" in paper_trd.columns else None
        tdf = paper_trd
        if "entry_date" in tdf.columns:
            tdf = tdf[tdf["entry_date"].astype(str) >= PERF_START]
        if m and "pnl_usd" in tdf.columns:
            cum_a = round(tdf[tdf[m] == "A"]["pnl_usd"].sum() / INITIAL_CAP * 100, 2)
            cum_d = round(tdf[tdf[m] == "D"]["pnl_usd"].sum() / INITIAL_CAP * 100, 2)
        elif m and "return_pct" in tdf.columns:
            cum_a = round(tdf[tdf[m] == "A"]["return_pct"].sum(), 2)
            cum_d = round(tdf[tdf[m] == "D"]["return_pct"].sum(), 2)

    # 페이퍼 총 평가금액 = 가상자본 + 실현손익(방식A 기준) + 미실현
    realized_pnl = PAPER_CAP * (cum_a or 0.0) / 100
    total_val    = PAPER_CAP + realized_pnl + unreal_pnl
    total_pnl    = realized_pnl + unreal_pnl
    pnl_pct      = round(total_pnl / PAPER_CAP * 100, 2)
    pnl_sign     = "+" if total_pnl >= 0 else ""
    pct_sign     = "+" if pnl_pct >= 0 else ""
    pnl_dot      = "🟢" if total_pnl >= 0 else "🔴"

    st.markdown(f"""
<div style="padding:0.4rem 0 0.1rem 0">
  <div style="font-size:0.82rem;color:#888;margin-bottom:0.1rem">페이퍼 평가금액 (가상자본 ${PAPER_CAP:.0f})</div>
  <div style="font-size:2.6rem;font-weight:700;line-height:1.15;color:#fafafa">${total_val:,.2f}</div>
  <div style="font-size:1.0rem;color:{'#00cc66' if total_pnl>=0 else '#ff4444'};margin-top:0.15rem">
    {pnl_dot} 누적손익: {pnl_sign}${total_pnl:.2f} ({pct_sign}{pnl_pct:.2f}%)  |  미실현: {'+' if unreal_pnl>=0 else ''}${unreal_pnl:.2f}
  </div>
</div>""", unsafe_allow_html=True)
    st.caption(f"🕐 {now_str}  ·  {REFRESH_SEC}초 자동갱신")
    st.divider()

    # 레짐 + 누적수익률
    r_emoji  = REGIME_EMOJI.get(regime, "❓")
    dir_text = "  |  ".join(f"{k} → {DIR_LABEL.get(v, v)}" for k, v in action.items()) if action else "—"
    st.markdown(f"### {r_emoji} {regime} `{regime_date}`")
    st.caption(dir_text)

    # 온체인 보조 신호
    oc = load_onchain()
    if oc is not None:
        _render_onchain_section(oc)

    pnl_a_usd = round(cum_a / 100 * INITIAL_CAP, 2) if cum_a is not None else None
    pnl_d_usd = round(cum_d / 100 * INITIAL_CAP, 2) if cum_d is not None else None
    c1, c2 = st.columns(2)
    c1.metric("방식A 누적수익 (since 06-27)",
              _fmt_pct(cum_a) if cum_a is not None else "데이터 없음",
              delta=f"${pnl_a_usd:+.2f}" if pnl_a_usd is not None else None)
    c2.metric("방식D 누적수익 (since 06-27)",
              _fmt_pct(cum_d) if cum_d is not None else "데이터 없음",
              delta=f"${pnl_d_usd:+.2f}" if pnl_d_usd is not None else None)

    paper_pos = _filter_by_mode(pos_df, live=False)
    c3, c4 = st.columns(2)
    c3.metric("페이퍼 포지션", f"{len(paper_pos)}개")
    c4.metric("페이퍼 체결",   f"{len(paper_trd)}건")
    st.divider()


# ── 공용 섹션 ─────────────────────────────────────────────────────────────────

def section_signals(tab_key="live"):
    st.subheader("🔔 오늘 신호")
    df = load_signals()
    if df.empty:
        st.info("오늘 신호 없음")
        st.divider()
        return

    # 앙상블 점수 기준 정렬 (없으면 priority_score 폴백)
    sort_col = "ensemble_score" if "ensemble_score" in df.columns else "priority_score"
    if sort_col in df.columns:
        df = df.sort_values(sort_col, ascending=False)

    entry_col = "entry" if "entry" in df.columns else "entry_price"
    stop_col  = "stop"  if "stop"  in df.columns else "stop_loss"

    GRADE_ICON = {"A": "🔥", "B": "⭐", "C": "🔵", "D": "⚪"}

    rows = []
    for _, s in df.iterrows():
        d     = str(s.get("direction", ""))
        grade = str(s.get("ensemble_grade", ""))
        score = s.get("ensemble_score") if "ensemble_score" in df.columns else s.get("priority_score")
        icon  = GRADE_ICON.get(grade, "")
        grade_str = f"{icon}{grade}" if grade else "—"
        score_str = f"{float(score):.1f}" if score is not None and pd.notna(score) else "—"
        # patterns_fired는 리스트일 수 있음
        pats  = s.get("patterns_fired", s.get("pattern", ""))
        if isinstance(pats, list):
            pats = ", ".join(pats)
        # RS(BTC 대비 상대강도, 롱 필터에 사용) — rs_score 필드가 있으면 표시
        rs = s.get("rs_score") if "rs_score" in df.columns else None
        if rs is not None and pd.notna(rs):
            from relative_strength import rs_emoji
            rs_str = f"{rs_emoji(float(rs))} {float(rs):+.2f}"
        else:
            rs_str = "—"
        # 비대칭(상승/하락 포착) — 진단 전용(필터 아님). cap<0 = 빠질 때 더 빠짐
        cap = s.get("cap_score") if "cap_score" in df.columns else None
        cap_str = f"{float(cap):+.2f}" if (cap is not None and pd.notna(cap)) else "—"
        rows.append({
            "등급":       grade_str,
            "점수":       score_str,
            "종목":       s.get("symbol", ""),
            "패턴":       pats,
            "방향":       DIR_LABEL.get(d, d),
            "RS":         rs_str,
            "비대칭":     cap_str,
            "진입가":     _fmt_price(s.get(entry_col)),
            "손절가":     _fmt_price(s.get(stop_col)),
            "거래량배수": f"{s['strength_vol_ratio']:.2f}x" if s.get("strength_vol_ratio") else "—",
            "레짐":       s.get("regime", ""),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True,
                 key=f"signals_df_{tab_key}")
    st.caption("RS = BTC 대비 상대강도, 비대칭 = 상승/하락 포착차 — 둘 다 진단용 표시. "
               "매매 반영 안 함(RS는 레짐 중복으로 필터 폐기, 비대칭은 눌림목 매수에 역효과). "
               "사이징에 쓰는 시장신호는 레짐 게이지(avg_cap)뿐.")
    st.divider()


def _render_okx_positions(okx_poss, bal_dict, prices, tab_key):
    """실거래 오픈 포지션 — OKX API 실측을 원천으로 바이낸스식 그리드 렌더.

    DB(positions 테이블)는 러너 소멸·중복으로 실제와 어긋날 수 있으므로,
    실거래 탭 표시는 항상 OKX 실측을 신뢰한다(요구: 오픈포지션이 실제와 일치).
    스탑로스 설정란은 두지 않는다(진입 시 algo 손절 자동 설정 — 표시만).
    """
    if "confirm_close" not in st.session_state:
        st.session_state.confirm_close = None

    # 합계 요약
    equity     = float(bal_dict.get("equity")) if bal_dict else None
    tot_margin = sum(float(p.get("margin") or 0) for p in okx_poss)
    tot_notn   = sum(abs(float(p.get("notional") or 0)) for p in okx_poss)
    tot_upnl   = sum(float(p.get("unrealized_pnl") or 0) for p in okx_poss)
    s1, s2, s3 = st.columns(3)
    s1.metric("포지션", f"{len(okx_poss)}개")
    s2.metric("투입증거금", f"${tot_margin:.2f}",
              help="실제 계좌에서 묶인 증거금 합계 — 자산과 비교할 값")
    s3.metric("미실현손익", f"{'+' if tot_upnl>=0 else ''}${tot_upnl:.2f}",
              delta=f"명목 ${tot_notn:.0f}" if equity else None, delta_color="off")

    # 포지션 카드(반응형): 아이폰 세로에선 필드가 2~3열로 자동 reflow, 가로에선 5열.
    # st.columns 강제 가로그리드 대신 카드라 세로모드에서도 깨지지 않는다.
    st.markdown(_POS_CARD_CSS, unsafe_allow_html=True)
    for i, p in enumerate(okx_poss):
        sym      = p.get("symbol", "")
        d        = p.get("direction", "")
        ep       = float(p.get("entry_price") or 0)
        upnl     = float(p.get("unrealized_pnl") or 0)
        coin_qty = p.get("coin_qty")
        margin   = p.get("margin") or 0.0
        lev      = p.get("leverage")
        liq      = p.get("liq_price")
        roe      = p.get("roe")
        # 현재가: 포지션 응답의 mark price 우선(시세 재조회 불필요) → prices 폴백
        cur      = p.get("mark_price") or prices.get(sym)
        dir_cls   = "long" if d == "long" else "short"
        dir_txt   = "롱" if d == "long" else "숏"
        lev_badge = f"{lev:g}x" if lev else ""
        pnl_cls   = "pos" if upnl >= 0 else "neg"
        roe_str   = f"{'+' if roe>=0 else ''}{roe:.1f}%" if roe is not None else "—"
        upnl_str  = f"{'+' if upnl>=0 else ''}${upnl:.2f}"
        qty_str   = f"{coin_qty:g}" if coin_qty is not None else f"{p.get('qty','—')}"
        pos_key   = f"okx_{tab_key}_{sym}_{d}_{i}"
        # 가격변동(진입 대비) — 손절은 '가격 -8%' 기준이므로 ROE와 구분해 표시.
        # 손절가 = 진입 ±8%(레버리지 무관). 손절은 가격이 여기 닿을 때만 발동.
        if cur and ep:
            price_ret = (cur - ep) / ep * 100 if d == "long" else (ep - cur) / ep * 100
        else:
            price_ret = None
        pret_cls  = "pos" if (price_ret or 0) >= 0 else "neg"
        pret_str  = f"{'+' if price_ret>=0 else ''}{price_ret:.2f}%" if price_ret is not None else "—"
        stop_px   = ep * 0.92 if d == "long" else ep * 1.08

        card = f"""
<div class="pos-card">
  <div class="pos-head">
    <span class="sym">{sym}</span>
    <span class="badge {dir_cls}">{dir_txt}</span>
    <span class="badge lev">{lev_badge}</span>
    <span class="pnl {pnl_cls}">{upnl_str} <small>(ROE {roe_str})</small></span>
  </div>
  <div class="pos-grid">
    <div><label>수량</label><b>{qty_str}</b></div>
    <div><label>진입가</label><b>{_fmt_price(ep)}</b></div>
    <div><label>현재가</label><b>{_fmt_price(cur) if cur else '—'}</b></div>
    <div><label>가격변동</label><b class="{pret_cls}">{pret_str}</b></div>
    <div><label>손절(-8%)</label><b>{_fmt_price(stop_px)}</b></div>
    <div><label>증거금</label><b>${margin:.2f}</b></div>
    <div><label>청산가</label><b>{_fmt_price(liq) if liq else '—'}</b></div>
  </div>
</div>"""
        st.markdown(card, unsafe_allow_html=True)
        bc1, bc2 = st.columns([4, 1])
        if bc2.button("청산", key=f"close_{pos_key}", type="secondary",
                      use_container_width=True):
            st.session_state.confirm_close = pos_key

    # 청산 확인 다이얼로그
    for i, p in enumerate(okx_poss):
        sym, d = p.get("symbol", ""), p.get("direction", "")
        qty = p.get("qty", 0)
        d_lbl = DIR_LABEL.get(d, d)
        pos_key = f"okx_{tab_key}_{sym}_{d}_{i}"
        if st.session_state.confirm_close == pos_key:
            st.warning(f"⚠️ **{sym} {d_lbl}** OKX 시장가 전량 청산하시겠습니까?")
            cc1, cc2 = st.columns(2)
            if cc1.button("✅ 확인 청산", key=f"confirm_{pos_key}", type="primary"):
                with st.spinner("OKX 청산 중..."):
                    try:
                        ex = _okx_exchange()          # 캐시된 인스턴스(load_markets 생략)
                        if ex is not None:
                            sym_ccxt = f"{sym}/USDT:USDT"
                            close_side = "sell" if d == "long" else "buy"
                            order = ex.create_market_order(
                                sym_ccxt, close_side, float(qty),
                                params={"tdMode": "isolated", "reduceOnly": True})
                            # 체결가: 주문응답 average → 포지션 mark price → prices 순.
                            # (실거래부는 prices가 비어있으므로 mark_price 폴백 필수 —
                            #  없으면 fill=0이 되어 매매내역 기록이 스킵되던 버그)
                            fill = float(order.get("average") or order.get("price") or 0) \
                                or float(p.get("mark_price") or prices.get(sym) or 0)
                            entry_px = float(p.get("entry_price") or 0)
                            cq = p.get("coin_qty")
                            if cq and entry_px and fill:
                                realized = (fill - entry_px) * cq if d == "long" \
                                    else (entry_px - fill) * cq
                            else:
                                realized = float(p.get("unrealized_pnl") or 0)
                            n = _record_manual_close(
                                sym, d, entry_px, fill, pnl_usd=round(realized, 2),
                                size_usd=p.get("margin"), live_mode=True)
                            st.success(f"{sym} {d_lbl} 청산 완료 "
                                       f"(체결 {_fmt_price(fill)}, 매매내역 {n}건 기록)")
                        else:
                            st.error("OKX 연결 실패")
                    except Exception as e:
                        st.error(f"청산 오류: {str(e)[:80]}")
                st.session_state.confirm_close = None
                # 전체 cache clear(콜드 리로드) 대신 바뀐 것만 무효화 → 빠른 갱신
                fetch_account_balance.clear()
                load_positions.clear()
                load_trades.clear()
                st.rerun()
            if cc2.button("취소", key=f"cancel_{pos_key}"):
                st.session_state.confirm_close = None
    st.divider()


def section_positions(live: bool, pos_df, prices, tab_key: str):
    """오픈 포지션. 실거래 탭은 OKX 실측 우선(바이낸스식), 페이퍼는 DB 그리드."""
    st.subheader("📂 오픈 포지션")

    # 실거래 탭: OKX 실측을 원천으로 표시(DB 드리프트와 무관하게 실제와 일치)
    if live:
        bal_dict, okx_poss, is_live_mode, _ = fetch_account_balance()
        if okx_poss:
            _render_okx_positions(okx_poss, bal_dict, prices, tab_key)
            return
        if not is_live_mode:
            st.info("OKX 미연결 — 실계좌 포지션을 표시하려면 OKX 키 설정 필요")
        else:
            st.info("오픈 포지션 없음")
        st.divider()
        return

    df = _filter_by_mode(pos_df, live)
    if df.empty:
        st.info("오픈 포지션 없음")
        st.divider()
        return

    if "confirm_close" not in st.session_state:
        st.session_state.confirm_close = None

    st.caption("청산 버튼으로 수동 청산 가능")

    for i, (_, pos) in enumerate(df.iterrows()):
        sym        = str(pos.get("symbol", ""))
        direction  = str(pos.get("direction", ""))
        entry      = float(pos.get("entry_price") or 0)
        stop       = float(pos.get("stop_loss") or pos.get("stop") or 0)
        size_usd   = float(pos.get("size_usd") or 0)
        leverage   = 2.0 if live else 1.0
        notional   = size_usd * leverage
        entry_date = str(pos.get("entry_date", ""))[:10]
        pattern    = str(pos.get("pattern", ""))
        pos_key    = f"{tab_key}_{sym}_{pattern}_{direction}_{entry_date}_{i}"

        cur = prices.get(sym)
        if cur and entry and notional:
            ret_pct = (cur - entry) / entry * 100 if direction == "long" else (entry - cur) / entry * 100
            pnl_usd = notional * ((cur - entry) / entry if direction == "long" else (entry - cur) / entry)
            cur_val = size_usd + pnl_usd
            dot     = "🟢" if pnl_usd >= 0 else "🔴"
            pnl_str = f"{dot} {'+' if pnl_usd>=0 else ''}${pnl_usd:.2f} ({'+' if ret_pct>=0 else ''}{ret_pct:.2f}%)"
            cur_val_str = f"${cur_val:.2f}"
        else:
            pnl_str     = "가격 조회 중..."
            cur_val_str = "—"
            pnl_usd     = None
            cur         = None

        d_lbl = DIR_LABEL.get(direction, direction)

        col_info, col_price, col_btn = st.columns([2.4, 3.6, 1.2])
        col_info.write(f"**{sym}** {d_lbl}")
        col_info.caption(f"{pattern}  ·  {entry_date}")

        col_price.write(f"진입 {_fmt_price(entry)}  →  현재 {_fmt_price(cur) if cur else '—'}")
        col_price.write(pnl_str)
        col_price.caption(f"투입 ${size_usd:.0f}  →  평가 {cur_val_str}  |  손절 {_fmt_price(stop)}")

        if col_btn.button("청산", key=f"close_{pos_key}", type="secondary"):
            st.session_state.confirm_close = pos_key

        if st.session_state.confirm_close == pos_key:
            action_label = "실거래: OKX 시장가 주문 제출" if live else "페이퍼: 수동청산으로 기록"
            st.warning(f"⚠️ **{sym} {d_lbl}** 포지션을 청산하시겠습니까? ({action_label})")
            cc1, cc2 = st.columns(2)
            if cc1.button("✅ 확인 청산", key=f"confirm_{pos_key}", type="primary"):
                with st.spinner("청산 중..."):
                    ok, msg = _do_close_position(dict(pos), cur)
                st.session_state.confirm_close = None
                fetch_account_balance.clear()
                load_positions.clear()
                load_trades.clear()
                if ok:
                    st.success(f"청산 완료 — {msg}")
                else:
                    st.error(f"청산 실패 — {msg}")
                st.rerun()
            if cc2.button("❌ 취소", key=f"cancel_{pos_key}"):
                st.session_state.confirm_close = None
                st.rerun()

        st.markdown("---")

    st.divider()


def _trades_table(sub, ret_col, mult, key):
    """청산 거래 DataFrame을 표로 렌더."""
    rows = []
    for _, t in sub.iterrows():
        ret_val = float(t.get(ret_col) or 0) * mult
        reason  = str(t.get("exit_reason") or t.get("reason", "") or "")
        reason  = reason.replace(" ·실거래", "")   # 내부 마커는 표시 안 함
        ex_date = str(t.get("exit_date", "") or "")[:10]
        rows.append({
            "":       _ret_dot(ret_val),
            "종목":   t.get("symbol", ""),
            "방향":   DIR_LABEL.get(str(t.get("direction", "")), ""),
            "패턴":   t.get("pattern", ""),
            "진입일": str(t.get("entry_date", ""))[:10],
            "청산일": ex_date if ex_date else "—",
            "수익률": _fmt_pct(ret_val),
            "사유":   reason,
            "봉수":   int(t.get("hold_bars") or 0),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, key=key)


def section_trades(live: bool, trades_df, tab_key="live"):
    st.subheader("📋 최근 매매 내역 (청산 완료)")
    df = _filter_by_mode(trades_df, live)

    if df.empty:
        st.info("청산 완료 거래 없음")
        st.divider()
        return

    m_col   = "method" if "method" in df.columns else ("method_label" if "method_label" in df.columns else None)
    ret_col = "return_pct" if "return_pct" in df.columns else "ret"
    mult    = 1.0 if ret_col == "return_pct" else 100.0

    # 실거래는 '방식D'만 실제 매도(방식A ±10%는 페이퍼 비교 전용). 따라서 A/D로 나누지
    # 않고 단일 목록으로 표시한다. 같은 청산이 A·D 중복 기록된 경우 D를 우선해 dedupe
    # → 과거 'A탭·D탭 같은 내용' 중복 표시 문제 해소.
    if live:
        sub = df.copy()
        if m_col:
            sub["_mrank"] = (sub[m_col].astype(str) != "D").astype(int)  # D 우선(0)
            keys = [c for c in ("symbol", "entry_date", "exit_date") if c in sub.columns]
            sub = sub.sort_values("_mrank").drop_duplicates(subset=keys, keep="first")
        sort_col = "exit_date" if "exit_date" in sub.columns else "entry_date"
        sub = sub.sort_values(sort_col, ascending=False, na_position="last").head(20)
        _trades_table(sub, ret_col, mult, f"trades_df_{tab_key}_live")
        st.caption("실거래 매도는 방식D(-8% 손절·반대신호·레짐전환·30봉) 기준으로 실행됩니다.")
        st.divider()
        return

    # 페이퍼 탭: 방식A vs D 비교(둘은 서로 다른 청산 전략이므로 별도 표시)
    tab_a, tab_d = st.tabs(["📗 방식A", "📘 방식D"])
    for tab, meth in [(tab_a, "A"), (tab_d, "D")]:
        with tab:
            sub = (df[df[m_col] == meth] if m_col else df).head(20)
            if sub.empty:
                st.info(f"방식{meth} 청산 없음")
                continue
            _trades_table(sub, ret_col, mult, f"trades_df_{tab_key}_{meth}")
    st.divider()


def section_pattern_perf(live: bool, trades_df, chart_key="live"):
    st.subheader("🏆 패턴별 성과")
    df = _filter_by_mode(trades_df, live)

    if df.empty or "pattern" not in df.columns:
        st.info("집계 데이터 없음")
        st.divider()
        return

    ret_col = "return_pct" if "return_pct" in df.columns else "ret"
    mult    = 1.0 if ret_col == "return_pct" else 100.0
    grp     = df.groupby("pattern")[ret_col]
    agg     = pd.DataFrame({
        "패턴":        grp.count().index,
        "건수":        grp.count().values,
        "평균수익(%)": (grp.mean() * mult).round(2).values,
        "승률(%)":     grp.apply(lambda x: round((x > 0).mean() * 100, 1)).values,
    })
    agg["표본"] = agg["건수"].apply(lambda n: "⚠ 표본부족" if n < 10 else "✓")
    st.dataframe(agg, use_container_width=True, hide_index=True,
                 key=f"pattern_agg_{chart_key}")
    if len(agg) >= 1:
        _chart_pattern_bars(agg, chart_key=chart_key)
    st.divider()


_CHART_CFG = {"displayModeBar": False, "responsive": True}
_CHART_H   = 235   # 모바일 대응 높이(px)
_REGIME_COLORS = {
    "bull_btc":      "#4a9eff",
    "bull_altseason":"#26a641",
    "bear":          "#f85149",
    "sideways":      "#6e7681",
}


# ── 차트 1: 누적수익률 라인 차트 ────────────────────────────────────────────────

def _chart_cum_from_daily(daily_df, chart_key):
    """페이퍼 정식 트랙 — daily_summary의 cumulative_return_a/d 라인."""
    if daily_df.empty or "date" not in daily_df.columns:
        st.info("아직 데이터 없음 — GitHub Actions 실행 후 채워집니다")
        st.divider(); return
    df = daily_df.sort_values("date").copy()
    df = df[df["date"].astype(str) >= PERF_START]
    has_a = "cumulative_return_a" in df.columns
    has_d = "cumulative_return_d" in df.columns
    if df.empty or (not has_a and not has_d):
        st.info("아직 데이터 없음"); st.divider(); return
    fig = go.Figure()
    if has_a:
        base = float(df["cumulative_return_a"].iloc[0])
        fig.add_trace(go.Scatter(x=df["date"], y=(df["cumulative_return_a"]-base).round(3),
                                 name="방식A", mode="lines", line=dict(color="#4a9eff", width=2)))
    if has_d:
        base = float(df["cumulative_return_d"].iloc[0])
        fig.add_trace(go.Scatter(x=df["date"], y=(df["cumulative_return_d"]-base).round(3),
                                 name="방식D", mode="lines", line=dict(color="#ff8c42", width=2)))
    fig.add_hline(y=0, line_dash="dot", line_color="gray", line_width=1)
    fig.update_layout(template="plotly_dark", height=_CHART_H, margin=dict(l=0, r=0, t=8, b=8),
                      legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1,
                                  font=dict(size=11)),
                      yaxis=dict(title="%", ticksuffix="%"), xaxis=dict(title=None),
                      hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True, config=_CHART_CFG, key=f"chart_cum_{chart_key}")
    st.divider()


def chart_cumulative_return(live, trades_df, daily_df=None, chart_key="live"):
    """
    방식A/D 누적수익률.
      - 실거래 탭: trades(실거래 청산)의 청산일별 return_pct 누적 — DYDX 등 즉시 반영.
      - 페이퍼 탭: daily_summary 정식 트랙(cumulative_return_a/d) — 러너가 전체
        paper_trades로 계산한 값(DB trades엔 exit_date 누락 청산이 있어 신뢰도 낮음).
    """
    st.subheader("📈 누적수익률 (방식A vs D)")
    if not live:
        _chart_cum_from_daily(daily_df if daily_df is not None else pd.DataFrame(), chart_key)
        return

    df = _filter_by_mode(trades_df, live)
    if df.empty or "exit_date" not in df.columns:
        st.info("청산 완료 거래 없음")
        st.divider()
        return

    ret_col = "return_pct" if "return_pct" in df.columns else "ret"
    mult    = 1.0 if ret_col == "return_pct" else 100.0
    m_col   = "method" if "method" in df.columns else (
              "method_label" if "method_label" in df.columns else None)

    df = df.copy()
    df = df[df["exit_date"].notna()]
    df = df[df["exit_date"].astype(str).str.strip() != ""]
    if df.empty:
        st.info("청산 완료 거래 없음")
        st.divider()
        return
    df["_dt"]  = pd.to_datetime(df["exit_date"].astype(str).str[:10])
    df["_ret"] = df[ret_col].astype(float) * mult

    fig = go.Figure()
    plotted = False
    for meth, color, label in [("A", "#4a9eff", "방식A"), ("D", "#ff8c42", "방식D")]:
        sub = df[df[m_col] == meth] if m_col else df
        if sub.empty:
            continue
        daily = sub.groupby("_dt")["_ret"].sum().sort_index()
        cum   = daily.cumsum()
        fig.add_trace(go.Scatter(
            x=cum.index, y=cum.round(3).values,
            name=label, mode="lines+markers",
            line=dict(color=color, width=2),
        ))
        plotted = True
        if m_col is None:   # 방식 구분 없으면 1개 라인만
            break

    if not plotted:
        st.info("청산 완료 거래 없음")
        st.divider()
        return

    fig.add_hline(y=0, line_dash="dot", line_color="gray", line_width=1)
    fig.update_layout(
        template="plotly_dark", height=_CHART_H,
        margin=dict(l=0, r=0, t=8, b=8),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1,
                    font=dict(size=11)),
        yaxis=dict(title="%", ticksuffix="%"),
        xaxis=dict(title=None),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True, config=_CHART_CFG,
                    key=f"chart_cum_{chart_key}")
    st.divider()


# ── 차트 2: 일별 PNL 막대 차트 ─────────────────────────────────────────────────

def chart_daily_pnl(live: bool, trades_df, chart_key="live"):
    st.subheader("📊 일별 PNL")
    df = _filter_by_mode(trades_df, live)
    if df.empty:
        st.info("아직 데이터 없음")
        st.divider()
        return

    ret_col = "return_pct" if "return_pct" in df.columns else "ret"
    mult    = 1.0 if ret_col == "return_pct" else 100.0
    m_col   = "method" if "method" in df.columns else (
              "method_label" if "method_label" in df.columns else None)

    # 기준 방식: 실거래=D(실제 매도), 페이퍼=A(비교 기준). exit_date 있는 것만.
    # 선호 방식이 비면 반대 방식으로 폴백(단일 방식이라 중복합산 없음).
    # (과거엔 항상 방식A로 필터 → 실거래는 D뿐이라 일별PNL이 빈 화면이던 버그)
    def _pick(m):
        s = df[df[m_col] == m] if m_col else df
        if "exit_date" not in s.columns:
            return s.iloc[0:0]
        s = s[s["exit_date"].notna()].copy()
        return s[s["exit_date"].astype(str).str.strip() != ""]

    pref, alt = ("D", "A") if live else ("A", "D")
    closed = _pick(pref)
    if closed.empty:
        closed = _pick(alt)

    if closed.empty:
        st.info("청산 내역 없음")
        st.divider()
        return

    closed["_dt"]  = pd.to_datetime(closed["exit_date"].astype(str).str[:10])
    closed["_ret"] = closed[ret_col].astype(float) * mult
    daily = closed.groupby("_dt")["_ret"].sum().reset_index().sort_values("_dt")

    colors = ["#26a641" if v >= 0 else "#f85149" for v in daily["_ret"]]
    fig = go.Figure(go.Bar(
        x=daily["_dt"], y=daily["_ret"].round(3),
        marker_color=colors,
        text=daily["_ret"].round(2).astype(str) + "%",
        textposition="outside",
    ))
    fig.add_hline(y=0, line_dash="dot", line_color="gray", line_width=1)
    fig.update_layout(
        template="plotly_dark", height=_CHART_H,
        margin=dict(l=0, r=0, t=8, b=8),
        yaxis=dict(title="%", ticksuffix="%"),
        xaxis=dict(title=None),
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True, config=_CHART_CFG,
                    key=f"chart_pnl_{chart_key}")
    st.divider()


# ── 차트 3 헬퍼: 패턴별 가로 막대 차트 ─────────────────────────────────────────

def _chart_pattern_bars(agg: pd.DataFrame, chart_key="live"):
    """agg: columns = ['패턴', '건수', '평균수익(%)', '승률(%)']"""
    if agg.empty:
        return

    n_pats = len(agg)
    height = max(160, min(_CHART_H, 60 + n_pats * 30))

    colors_mean = ["#26a641" if v >= 0 else "#f85149" for v in agg["평균수익(%)"]]
    insuf = ["표본부족" if n < 10 else "" for n in agg["건수"]]

    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=["평균수익률 (%)", "승률 (%)"],
        horizontal_spacing=0.12,
    )
    fig.add_trace(go.Bar(
        y=agg["패턴"], x=agg["평균수익(%)"],
        orientation="h", marker_color=colors_mean,
        text=insuf, textposition="outside",
        hovertemplate="%{y}: %{x:.2f}%<extra></extra>",
        showlegend=False,
    ), row=1, col=1)
    fig.add_trace(go.Bar(
        y=agg["패턴"], x=agg["승률(%)"],
        orientation="h", marker_color="#4a9eff",
        text=insuf, textposition="outside",
        hovertemplate="%{y}: %{x:.1f}%<extra></extra>",
        showlegend=False,
    ), row=1, col=2)

    fig.add_vline(x=0,  line_dash="dot", line_color="gray", line_width=1, row=1, col=1)
    fig.add_vline(x=50, line_dash="dot", line_color="gray", line_width=1, row=1, col=2)

    fig.update_layout(
        template="plotly_dark", height=height,
        margin=dict(l=0, r=0, t=30, b=8),
    )
    fig.update_xaxes(ticksuffix="%")
    st.plotly_chart(fig, use_container_width=True, config=_CHART_CFG,
                    key=f"chart_pat_{chart_key}")


# ── 차트 4: 레짐 히스토리 타임라인 ─────────────────────────────────────────────

def chart_regime_timeline(chart_key="live"):
    st.subheader("🌐 레짐 히스토리")
    regime_map = _load_regime_history()
    if not regime_map:
        st.info("아직 데이터 없음 — 스케줄러 실행 시 자동 생성")
        st.divider()
        return

    dates_sorted = sorted(regime_map.keys())
    current_regime = load_regime()[0].get("regime", "")

    # 연속 구간 집계
    segments = []
    s_start  = dates_sorted[0]
    s_regime = regime_map[s_start]
    for d in dates_sorted[1:]:
        if regime_map[d] != s_regime:
            segments.append((s_start, d, s_regime))
            s_start  = d
            s_regime = regime_map[d]
    segments.append((s_start, dates_sorted[-1], s_regime))

    fig = go.Figure()

    # 컬러 블록
    for start, end, regime in segments:
        color      = _REGIME_COLORS.get(regime, "#6e7681")
        is_current = (end == dates_sorted[-1] and regime == current_regime)
        fig.add_shape(
            type="rect",
            x0=start, x1=end, y0=0, y1=1,
            fillcolor=color,
            opacity=1.0 if is_current else 0.65,
            line=dict(width=2 if is_current else 0, color="white"),
        )

    # 범례용 더미 트레이스
    for label, color in _REGIME_COLORS.items():
        fig.add_trace(go.Scatter(
            x=[None], y=[None], mode="markers",
            marker=dict(symbol="square", size=11, color=color),
            name=label, showlegend=True,
        ))

    fig.update_layout(
        template="plotly_dark", height=110,
        margin=dict(l=0, r=0, t=8, b=30),
        xaxis=dict(type="date", tickformat="%y/%m", showgrid=False),
        yaxis=dict(visible=False, range=[0, 1]),
        legend=dict(orientation="h", yanchor="top", y=-0.35,
                    xanchor="left", x=0, font=dict(size=10)),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, use_container_width=True, config=_CHART_CFG,
                    key=f"chart_regime_{chart_key}")
    st.divider()


def section_daily_chart():
    """구버전 호환용 — chart_cumulative_return 으로 대체됨."""
    pass


# ── 메인 ─────────────────────────────────────────────────────────────────────
@st.cache_resource
def _app_version():
    """배포 버전 확인용 — git 커밋 해시 (모바일/PC 표시 불일치 진단)."""
    try:
        import subprocess
        h = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True, timeout=5)
        if h.returncode == 0 and h.stdout.strip():
            return h.stdout.strip()
    except Exception:
        pass
    try:
        mt = os.path.getmtime(__file__)
        return datetime.fromtimestamp(mt).strftime("%m%d-%H%M")
    except Exception:
        return "unknown"


_MOBILE_GRID_CSS = """
<style>
/* 모바일 여백 축소(아이폰 14 Pro 세로 393px 기준 가로폭 확보) */
@media (max-width: 640px) {
  .block-container { padding-left: 0.6rem !important; padding-right: 0.6rem !important;
                     padding-top: 1.2rem !important; }
  h1 { font-size: 1.5rem !important; }
  div[data-testid="stMetricValue"] { font-size: 1.05rem !important; }
  div[data-testid="stMetricLabel"] p { font-size: 0.72rem !important; }
}
</style>
"""

# 반응형 포지션 카드 — 아이폰 세로에서 필드가 자동 reflow(2~3열), 가로에서 5열.
_POS_CARD_CSS = """
<style>
.pos-card { background:#161a1e; border:1px solid #262b31; border-radius:10px;
  padding:0.55rem 0.7rem; margin:0.35rem 0 0.15rem 0; }
.pos-head { display:flex; align-items:center; flex-wrap:wrap; gap:0.35rem; margin-bottom:0.4rem; }
.pos-head .sym { font-size:1.05rem; font-weight:700; color:#fafafa; }
.pos-head .badge { font-size:0.68rem; font-weight:600; padding:0.05rem 0.4rem;
  border-radius:4px; }
.pos-head .badge.long { background:rgba(38,166,65,0.18); color:#26d367; }
.pos-head .badge.short{ background:rgba(248,81,73,0.18); color:#ff6b6b; }
.pos-head .badge.lev  { background:#2a2f36; color:#c9d1d9; }
.pos-head .pnl { margin-left:auto; font-size:1.0rem; font-weight:700; }
.pos-head .pnl small { font-size:0.72rem; font-weight:600; }
.pos-head .pnl.pos { color:#26d367; }
.pos-head .pnl.neg { color:#ff6b6b; }
.pos-grid { display:grid; grid-template-columns:repeat(auto-fit, minmax(80px, 1fr));
  gap:0.3rem 0.6rem; }
.pos-grid > div { display:flex; flex-direction:column; line-height:1.25; }
.pos-grid label { font-size:0.66rem; color:#7d8590; }
.pos-grid b { font-size:0.86rem; color:#e6edf3; font-weight:600; }
.pos-grid b.pos { color:#26d367; }
.pos-grid b.neg { color:#ff6b6b; }
</style>
"""


@st.fragment(run_every=f"{REFRESH_SEC}s")
def _live_dynamic():
    """실거래 실시간부(잔고·미실현·오픈포지션)만 REFRESH_SEC마다 부분 갱신.

    바이낸스처럼 '숫자만' 업데이트 — 전체 페이지 rerun(폰트 페이드/깜빡임) 없이
    이 프래그먼트의 DOM만 교체된다. 아래 정적 섹션(매매내역·차트)은 재렌더 안 함.
    """
    # 실거래부는 시세 재조회 불필요 — 포지션 응답의 mark price를 그대로 사용.
    pos_df = load_positions()
    trades = load_trades()
    section_live_summary(pos_df, trades, {})
    section_positions(live=True, pos_df=pos_df, prices={}, tab_key="live")


def main():
    st.markdown(_MOBILE_GRID_CSS, unsafe_allow_html=True)
    col_h, col_btn = st.columns([5, 1])
    with col_h:
        st.title("🪙 크립토 대시보드")
        st.caption(f"버전 {_app_version()}  ·  실시간부 {REFRESH_SEC}초 부분갱신")
    with col_btn:
        st.write("")
        if st.button("🔄"):
            st.cache_data.clear()
            st.rerun()

    # 정적 섹션용 공통 데이터(Supabase — 캐시). 시세는 실거래부엔 불필요하므로
    # 페이퍼 탭에서만 지연 로드 → 실거래 탭 첫 표시가 시세 조회를 기다리지 않음.
    all_pos    = load_positions()
    all_trades = load_trades()
    daily_df   = load_daily_summary()

    tab_live, tab_paper = st.tabs(["📈 실거래", "📋 페이퍼"])

    with tab_live:
        _live_dynamic()                       # ← 30초 부분갱신(잔고·포지션, mark price)
        section_signals(tab_key="live")       # 이하 정적(스케줄러 주기로만 변동)
        section_trades(live=True,  trades_df=all_trades, tab_key="live")
        chart_cumulative_return(live=True, trades_df=all_trades, chart_key="live")
        chart_daily_pnl(live=True,  trades_df=all_trades, chart_key="live")
        section_pattern_perf(live=True,  trades_df=all_trades, chart_key="live")
        chart_regime_timeline(chart_key="live")

    with tab_paper:                            # 페이퍼는 정적(4시간 주기 변동)
        paper_syms = tuple(sorted(
            _filter_by_mode(all_pos, live=False)["symbol"].unique().tolist())) \
            if not all_pos.empty else ()
        prices = fetch_prices(paper_syms)      # 페이퍼 포지션 시세만(배치)
        section_paper_summary(all_pos, all_trades, daily_df, prices)
        section_signals(tab_key="paper")
        section_positions(live=False, pos_df=all_pos, prices=prices, tab_key="paper")
        section_trades(live=False, trades_df=all_trades, tab_key="paper")
        chart_cumulative_return(live=False, trades_df=all_trades, daily_df=daily_df, chart_key="paper")
        chart_daily_pnl(live=False, trades_df=all_trades, chart_key="paper")
        section_pattern_perf(live=False, trades_df=all_trades, chart_key="paper")
        chart_regime_timeline(chart_key="paper")


main()
