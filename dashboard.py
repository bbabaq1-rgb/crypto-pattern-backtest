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


@st.cache_data(ttl=25)
def fetch_account_balance():
    """
    OKX 잔고 + 실제 포지션 조회.
    반환: (bal_dict | None, okx_positions | [], is_live, err_msg | None)
    """
    import exchange as ex_mod
    if not ex_mod.is_live():
        return None, [], False, None  # 키 미설정
    try:
        conn = ex_mod.connect_live()
        if not conn:
            return None, [], True, "connect_live() returned None (API 연결 실패)"
        bal  = ex_mod.get_balance(conn)
        poss = ex_mod.get_okx_positions(conn)
        if bal is None:
            return None, poss, True, "get_balance() returned None"
        return bal, poss, True, None
    except Exception as e:
        return None, [], True, str(e)[:200]


@st.cache_data(ttl=60)
def fetch_prices(symbols_tuple):
    """
    OKX 선물(USDT 무기한) 현재가 조회.
    실패 시 스팟 가격으로 폴백.
    """
    if not symbols_tuple:
        return {}
    try:
        import ccxt
        ex = ccxt.okx({"enableRateLimit": True})
        result = {}
        for sym in symbols_tuple:
            try:
                # 1순위: 선물(USDT 무기한) 가격
                result[sym] = float(ex.fetch_ticker(f"{sym}/USDT:USDT")["last"])
            except Exception:
                try:
                    # 폴백: 스팟
                    result[sym] = float(ex.fetch_ticker(f"{sym}/USDT")["last"])
                except Exception:
                    pass
        return result
    except Exception:
        return {}


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
        import ccxt
        ex = ccxt.okx({
            "apiKey":   os.environ.get("OKX_KEY"),
            "secret":   os.environ.get("OKX_SECRET"),
            "password": os.environ.get("OKX_PASSPHRASE"),
            "enableRateLimit": True,
        })
        ex.load_markets()
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

    # '실거래' 마커: live_mode 컬럼이 없어도 실거래 청산으로 인식되게 exit_reason에 부여
    exit_reason = "수동청산 ·실거래" if live_mode else "수동청산"
    recorded = 0
    if cli and entry and exit_px:
        for method in ("A", "D"):
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
            for method in ("A", "D"):
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

        # OKX 실제 포지션 vs Supabase DB 포지션 대조
        live_pos_db = _filter_by_mode(pos_df, live=True)
        live_trd    = _filter_by_mode(trades_df, live=True)
        okx_cnt     = len(okx_poss)
        db_cnt      = len(live_pos_db)
        mismatch    = okx_cnt != db_cnt

        # 경고: DB > OKX (DB에만 있는 포지션 → 이미 청산됐을 수 있음)
        # 정상: OKX >= DB (runner 파일 소멸로 DB 미등록은 정상 운영 상황)
        db_gt_okx = db_cnt > okx_cnt

        c1, c2, c3 = st.columns(3)
        c1.metric("진입 완료 (OKX)", f"{okx_cnt}개")
        c2.metric("DB 추적 포지션",  f"{db_cnt}개",
                  delta="⚠ DB>OKX 확인 필요" if db_gt_okx else None,
                  delta_color="inverse" if db_gt_okx else "normal")
        c3.metric("청산 완료",       f"{len(live_trd)}건")

        if okx_poss:
            with st.expander(f"🔍 OKX 실제 포지션 {okx_cnt}개", expanded=False):
                okx_rows = []
                for p in okx_poss:
                    upnl = p.get("unrealized_pnl", 0)
                    okx_rows.append({
                        "종목":      p.get("symbol", ""),
                        "방향":      "🟢 롱" if p["direction"] == "long" else "🔴 숏",
                        "수량":      p.get("qty", 0),
                        "진입가":    _fmt_price(p.get("entry_price")),
                        "미실현P&L": f"{'+'if upnl>=0 else ''}{upnl:.2f}",
                    })
                st.dataframe(pd.DataFrame(okx_rows), hide_index=True,
                             use_container_width=True, key="okx_pos_table")
        if db_gt_okx:
            st.warning(f"DB {db_cnt}개 > OKX {okx_cnt}개 — DB에 이미 청산된 포지션이 남아있을 수 있습니다")

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
        rows.append({
            "등급":       grade_str,
            "점수":       score_str,
            "종목":       s.get("symbol", ""),
            "패턴":       pats,
            "방향":       DIR_LABEL.get(d, d),
            "진입가":     _fmt_price(s.get(entry_col)),
            "손절가":     _fmt_price(s.get(stop_col)),
            "거래량배수": f"{s['strength_vol_ratio']:.2f}x" if s.get("strength_vol_ratio") else "—",
            "레짐":       s.get("regime", ""),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True,
                 key=f"signals_df_{tab_key}")
    st.divider()


def section_positions(live: bool, pos_df, prices, tab_key: str):
    """오픈 포지션 + 청산 버튼. HTML 없이 순수 Streamlit 컴포넌트만 사용."""
    st.subheader("📂 오픈 포지션")
    df = _filter_by_mode(pos_df, live)

    # Live 탭 & DB 비어있을 때 → OKX 실제 포지션으로 폴백 (청산 버튼 포함)
    if df.empty and live:
        bal_dict, okx_poss, is_live_mode, _ = fetch_account_balance()
        if okx_poss:
            st.caption("📡 OKX 실제 포지션 (DB 미등록 — 다음 스케줄러 실행 후 자동 등록)")
            if "confirm_close" not in st.session_state:
                st.session_state.confirm_close = None

            # ── 합계 요약 (자산 대비 맥락 — '자산 초과' 오인 방지) ──────────
            equity     = float(bal_dict.get("equity")) if bal_dict else None
            tot_margin = sum(float(p.get("margin") or 0) for p in okx_poss)
            tot_notn   = sum(abs(float(p.get("notional") or 0)) for p in okx_poss)
            s1, s2, s3 = st.columns(3)
            s1.metric("총 투입증거금", f"${tot_margin:.2f}",
                      help="실제 계좌에서 묶인 증거금 합계 — 자산과 비교할 값")
            s2.metric("총 명목금액", f"${tot_notn:.2f}",
                      help="레버리지 반영 포지션 규모(≈증거금×레버리지). 자산의 여러 배가 정상")
            if equity is not None:
                lev_eff = (tot_notn / equity) if equity else 0
                s3.metric("총 자산(equity)", f"${equity:.2f}",
                          f"명목/자산 {lev_eff:.2f}x")
            st.caption("ℹ️ '명목금액'은 레버리지가 곱해진 값이라 자산보다 큰 게 정상입니다. "
                       "실제 위험자본은 '투입증거금'입니다.")

            GRID = [0.9, 0.7, 1.1, 1.2, 1.1, 1.1, 1.1, 1.2, 0.9, 0.8]

            # ── 헤더 행 ───────────────────────────────────────────────────
            hcols = st.columns(GRID)
            for c, label in zip(hcols, ["종목", "방향", "수량(코인)", "투입증거금", "명목",
                                        "진입가", "현재가", "손익", "수익률", ""]):
                c.caption(f"**{label}**")

            # ── 데이터 행 (각 행 오른쪽 끝 청산 버튼) ──────────────────────
            for i, p in enumerate(okx_poss):
                sym      = p.get("symbol", "")
                d        = p.get("direction", "")
                ep       = float(p.get("entry_price") or 0)
                upnl     = float(p.get("unrealized_pnl") or 0)
                coin_qty = p.get("coin_qty")
                notional = abs(float(p.get("notional") or 0))
                margin   = p.get("margin")
                lev      = p.get("leverage")
                if margin is None:  # 폴백: 명목/레버리지 → 명목/2
                    margin = notional / lev if lev else notional / 2
                cur      = prices.get(sym)
                d_lbl    = DIR_LABEL.get(d, d)
                dot      = "🟢" if upnl >= 0 else "🔴"
                ret_str  = "—"
                if cur and ep:
                    ret_pct = (cur - ep) / ep * 100 if d == "long" else (ep - cur) / ep * 100
                    ret_str = f"{'+' if ret_pct>=0 else ''}{ret_pct:.2f}%"
                qty_str  = f"{coin_qty:g}" if coin_qty is not None else f"{p.get('qty','—')}"
                lev_str  = f"  ·{lev:g}x" if lev else ""
                pos_key  = f"okx_{tab_key}_{sym}_{d}_{i}"

                rc = st.columns(GRID)
                rc[0].write(f"**{sym}**")
                rc[1].write(d_lbl)
                rc[2].write(qty_str)
                rc[3].write(f"${margin:.2f}{lev_str}")
                rc[4].write(f"${notional:.2f}")
                rc[5].write(_fmt_price(ep))
                rc[6].write(_fmt_price(cur) if cur else "—")
                rc[7].write(f"{dot} {'+' if upnl>=0 else ''}{upnl:.2f}")
                rc[8].write(ret_str)
                if rc[9].button("청산", key=f"close_{pos_key}", type="secondary"):
                    st.session_state.confirm_close = pos_key

            # ── 청산 확인 다이얼로그 ──────────────────────────────────────
            for i, p in enumerate(okx_poss):
                sym = p.get("symbol", "")
                d   = p.get("direction", "")
                qty = p.get("qty", 0)
                d_lbl   = DIR_LABEL.get(d, d)
                pos_key = f"okx_{tab_key}_{sym}_{d}_{i}"
                if st.session_state.confirm_close == pos_key:
                    st.warning(f"⚠️ **{sym} {d_lbl}** OKX 시장가 청산하시겠습니까?")
                    cc1, cc2 = st.columns(2)
                    if cc1.button("✅ 확인 청산", key=f"confirm_{pos_key}", type="primary"):
                        with st.spinner("OKX 청산 중..."):
                            try:
                                import exchange as ex_mod
                                conn = ex_mod.connect_live()
                                if conn:
                                    ex  = conn["exchange"]
                                    sym_ccxt = f"{sym}/USDT:USDT"
                                    close_side = "sell" if d == "long" else "buy"
                                    order = ex.create_market_order(
                                        sym_ccxt, close_side, float(qty),
                                        params={"tdMode": "isolated", "reduceOnly": True},
                                    )
                                    # 실체결가 캡처 → 없으면 현재가 폴백
                                    fill = float(order.get("average") or order.get("price") or 0) \
                                        or float(prices.get(sym) or 0)
                                    entry_px = float(p.get("entry_price") or 0)
                                    cq = p.get("coin_qty")
                                    # 실현손익: 코인수량×가격차 (없으면 미실현P&L 근사)
                                    if cq and entry_px and fill:
                                        realized = (fill - entry_px) * cq if d == "long" \
                                            else (entry_px - fill) * cq
                                    else:
                                        realized = float(p.get("unrealized_pnl") or 0)
                                    n = _record_manual_close(
                                        sym, d, entry_px, fill,
                                        pnl_usd=round(realized, 2),
                                        size_usd=p.get("margin"), live_mode=True)
                                    st.success(f"{sym} {d_lbl} 청산 완료 "
                                               f"(체결 {_fmt_price(fill)}, 매매내역 {n}건 기록)")
                                else:
                                    st.error("OKX 연결 실패")
                            except Exception as e:
                                st.error(f"청산 오류: {str(e)[:80]}")
                        st.session_state.confirm_close = None
                        st.cache_data.clear()
                        time.sleep(1.2)
                        st.rerun()
                    if cc2.button("취소", key=f"cancel_{pos_key}"):
                        st.session_state.confirm_close = None
            st.divider()
            return
        st.info("오픈 포지션 없음")
        st.divider()
        return

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
                st.cache_data.clear()
                if ok:
                    st.success(f"청산 완료 — {msg}")
                else:
                    st.error(f"청산 실패 — {msg}")
                time.sleep(1.2)
                st.rerun()
            if cc2.button("❌ 취소", key=f"cancel_{pos_key}"):
                st.session_state.confirm_close = None
                st.rerun()

        st.markdown("---")

    st.divider()


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

    tab_a, tab_d = st.tabs(["📗 방식A", "📘 방식D"])
    for tab, meth in [(tab_a, "A"), (tab_d, "D")]:
        with tab:
            sub = (df[df[m_col] == meth] if m_col else df).head(20)
            if sub.empty:
                st.info(f"방식{meth} 청산 없음")
                continue
            rows = []
            for _, t in sub.iterrows():
                ret_val = float(t.get(ret_col) or 0) * mult
                reason  = t.get("exit_reason") or t.get("reason", "")
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
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True,
                         key=f"trades_df_{tab_key}_{meth}")
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

    # 방식A 기준 (없으면 전체)
    sub = df[df[m_col] == "A"] if m_col else df
    if "exit_date" not in sub.columns:
        st.info("청산 내역 없음")
        st.divider()
        return
    closed = sub[sub["exit_date"].notna()].copy()
    closed = closed[closed["exit_date"].astype(str).str.strip() != ""]

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
/* 모바일 세로모드에서 st.columns가 세로로 쌓이는 것 방지 — 포지션 그리드 가로 유지.
   Streamlit은 좁은 뷰포트에서 컬럼을 스택하는데, 청산 버튼 행이 세로로 풀어지면
   그리드가 깨진다. nowrap + min-width:0 으로 강제 가로 배치(가로 스크롤 허용). */
@media (max-width: 640px) {
  div[data-testid="stHorizontalBlock"] {
    flex-wrap: nowrap !important;
    overflow-x: auto;
    gap: 0.3rem !important;
  }
  div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"],
  div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
    min-width: 0 !important;
    flex: 1 1 0% !important;
  }
  div[data-testid="stHorizontalBlock"] p { font-size: 0.78rem; }
  div[data-testid="stHorizontalBlock"] button p { font-size: 0.75rem; }
}
</style>
"""


def main():
    st.markdown(_MOBILE_GRID_CSS, unsafe_allow_html=True)
    col_h, col_btn = st.columns([5, 1])
    with col_h:
        st.title("🪙 크립토 대시보드")
        st.caption(f"버전 {_app_version()} — 모바일과 PC에서 이 값이 다르면 "
                   f"브라우저 새로고침(캐시 삭제) 필요")
    with col_btn:
        st.write("")
        if st.button("🔄"):
            st.cache_data.clear()
            st.rerun()

    # 공통 데이터 (탭 전환 시 재로드 방지)
    all_pos    = load_positions()
    all_trades = load_trades()
    daily_df   = load_daily_summary()

    all_syms = tuple(sorted(all_pos["symbol"].unique().tolist())) if not all_pos.empty else ()
    prices   = fetch_prices(all_syms)

    tab_live, tab_paper = st.tabs(["📈 실거래", "📋 페이퍼"])

    with tab_live:
        section_live_summary(all_pos, all_trades, prices)
        section_signals(tab_key="live")
        section_positions(live=True,  pos_df=all_pos, prices=prices, tab_key="live")
        section_trades(live=True,  trades_df=all_trades, tab_key="live")
        chart_cumulative_return(live=True, trades_df=all_trades, chart_key="live")
        chart_daily_pnl(live=True,  trades_df=all_trades, chart_key="live")
        section_pattern_perf(live=True,  trades_df=all_trades, chart_key="live")
        chart_regime_timeline(chart_key="live")

    with tab_paper:
        section_paper_summary(all_pos, all_trades, daily_df, prices)
        section_signals(tab_key="paper")
        section_positions(live=False, pos_df=all_pos, prices=prices, tab_key="paper")
        section_trades(live=False, trades_df=all_trades, tab_key="paper")
        chart_cumulative_return(live=False, trades_df=all_trades, daily_df=daily_df, chart_key="paper")
        chart_daily_pnl(live=False, trades_df=all_trades, chart_key="paper")
        section_pattern_perf(live=False, trades_df=all_trades, chart_key="paper")
        chart_regime_timeline(chart_key="paper")

    st.caption(f"⏱ {REFRESH_SEC}초 후 자동갱신...")
    time.sleep(REFRESH_SEC)
    st.rerun()


main()
