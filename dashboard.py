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
                if "stop_loss" not in df.columns and "stop" in df.columns:
                    df["stop_loss"] = df["stop"]
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
    return pd.DataFrame()


def load_regime():
    if os.path.exists("direction_switch.json"):
        try:
            d = json.load(open("direction_switch.json", encoding="utf-8"))
            return d.get("current", {}), d.get("routing", {})
        except Exception:
            pass
    return {}, {}


@st.cache_data(ttl=25)
def fetch_account_balance():
    """(balance | None, is_live). OKX 키 없으면 (None, False)."""
    try:
        import exchange as ex_mod
        if ex_mod.is_live():
            conn = ex_mod.connect_live()
            if conn:
                return ex_mod.get_balance(conn), True
    except Exception:
        pass
    return None, False


@st.cache_data(ttl=60)
def fetch_prices(symbols_tuple):
    if not symbols_tuple:
        return {}
    try:
        import ccxt
        ex = ccxt.okx({"enableRateLimit": True})
        result = {}
        for sym in symbols_tuple:
            try:
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


# ── 실거래 탭 섹션 ─────────────────────────────────────────────────────────────

def section_live_summary(pos_df, trades_df, prices):
    now_str = datetime.now(timezone.utc).strftime("%m/%d %H:%M UTC")
    balance, _ = fetch_account_balance()
    unreal_pnl = _unrealized_pnl(pos_df, prices, live=True)

    if balance is None:
        st.info("OKX 미연결 — Streamlit Secrets에 OKX_KEY / OKX_SECRET / OKX_PASSPHRASE 설정 시 실계좌 잔고 표시")
    else:
        pnl_pct  = round(unreal_pnl / balance * 100, 2) if balance > 0 else 0.0
        pnl_sign = "+" if unreal_pnl >= 0 else ""
        pct_sign = "+" if pnl_pct >= 0 else ""
        pnl_dot  = "🟢" if unreal_pnl >= 0 else "🔴"
        st.markdown(f"""
<div style="padding:0.4rem 0 0.1rem 0">
  <div style="font-size:0.82rem;color:#888;margin-bottom:0.1rem">Est. Total Value · OKX 선물</div>
  <div style="font-size:2.6rem;font-weight:700;line-height:1.15;color:#fafafa">${balance:,.2f}</div>
  <div style="font-size:1.0rem;color:{'#00cc66' if unreal_pnl>=0 else '#ff4444'};margin-top:0.15rem">
    {pnl_dot} Today PNL (미실현): {pnl_sign}${unreal_pnl:.2f} ({pct_sign}{pnl_pct:.2f}%)
  </div>
</div>""", unsafe_allow_html=True)

    st.caption(f"🕐 {now_str}  ·  {REFRESH_SEC}초 자동갱신")

    live_pos = _filter_by_mode(pos_df, live=True)
    live_trd = _filter_by_mode(trades_df, live=True)
    c1, c2   = st.columns(2)
    c1.metric("실거래 포지션", f"{len(live_pos)}개")
    c2.metric("실거래 체결",   f"{len(live_trd)}건")
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

def section_signals():
    st.subheader("🔔 오늘 신호")
    df = load_signals()
    if df.empty:
        st.info("오늘 신호 없음")
        st.divider()
        return

    if "priority_score" in df.columns:
        df = df.sort_values("priority_score", ascending=False)

    entry_col = "entry" if "entry" in df.columns else "entry_price"
    stop_col  = "stop"  if "stop"  in df.columns else "stop_loss"

    rows = []
    for _, s in df.iterrows():
        d   = str(s.get("direction", ""))
        pri = s.get("priority_score")
        ps  = s.get("pattern_strength")
        rows.append({
            "점수":       f"{float(pri):.3f}" if pri is not None and pd.notna(pri) else "—",
            "종목":       s.get("symbol", ""),
            "패턴":       s.get("pattern", ""),
            "방향":       DIR_LABEL.get(d, d),
            "진입가":     _fmt_price(s.get(entry_col)),
            "손절가":     _fmt_price(s.get(stop_col)),
            "거래량배수": f"{s['strength_vol_ratio']:.2f}x" if s.get("strength_vol_ratio") else "—",
            "패턴강도":   f"{float(ps):.3f}" if ps is not None and pd.notna(ps) else "—",
            "레짐":       s.get("regime", ""),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.divider()


def section_positions(live: bool, pos_df, prices, tab_key: str):
    """오픈 포지션 + 청산 버튼. HTML 없이 순수 Streamlit 컴포넌트만 사용."""
    st.subheader("📂 오픈 포지션")
    df = _filter_by_mode(pos_df, live)

    if df.empty:
        st.info("오픈 포지션 없음")
        st.divider()
        return

    if "confirm_close" not in st.session_state:
        st.session_state.confirm_close = None

    st.caption("청산 버튼으로 수동 청산 가능")

    for _, pos in df.iterrows():
        sym        = str(pos.get("symbol", ""))
        direction  = str(pos.get("direction", ""))
        entry      = float(pos.get("entry_price") or 0)
        stop       = float(pos.get("stop_loss") or pos.get("stop") or 0)
        size_usd   = float(pos.get("size_usd") or 0)
        leverage   = 2.0 if live else 1.0
        notional   = size_usd * leverage
        entry_date = str(pos.get("entry_date", ""))[:10]
        pattern    = str(pos.get("pattern", ""))
        pos_key    = f"{tab_key}_{sym}_{pattern}_{direction}_{entry_date}"

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


def section_trades(live: bool, trades_df):
    st.subheader("📋 최근 매매 내역")
    df = _filter_by_mode(trades_df, live)

    if df.empty:
        st.info("아직 거래 없음")
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
                st.info(f"방식{meth} 체결 없음")
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
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.divider()


def section_pattern_perf(live: bool, trades_df):
    st.subheader("🏆 패턴 성과")
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
    st.dataframe(agg, use_container_width=True, hide_index=True)
    if len(agg) >= 1:
        st.bar_chart(agg.set_index("패턴")[["평균수익(%)", "승률(%)"]], use_container_width=True)
    st.divider()


def section_daily_chart():
    st.subheader("📈 누적 수익률 추이")
    df = load_daily_summary()
    if df.empty or "date" not in df.columns:
        st.info("일별 집계 없음 — GitHub Actions 실행 후 채워집니다")
        return

    df = df.sort_values("date").copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    df = df[df.index >= pd.Timestamp(PERF_START)]

    cols = {}
    for col, label in [("cumulative_return_a", "방식A(%)"), ("cumulative_return_d", "방식D(%)")]:
        if col in df.columns and not df.empty:
            baseline   = float(df[col].iloc[0])
            cols[label] = df[col] - baseline

    if not cols:
        st.info("수익률 컬럼 없음")
        return
    st.line_chart(pd.DataFrame(cols), use_container_width=True)


# ── 메인 ─────────────────────────────────────────────────────────────────────
def main():
    col_h, col_btn = st.columns([5, 1])
    with col_h:
        st.title("🪙 크립토 대시보드")
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
        section_signals()
        section_positions(live=True,  pos_df=all_pos, prices=prices, tab_key="live")
        section_trades(live=True,  trades_df=all_trades)
        section_pattern_perf(live=True,  trades_df=all_trades)

    with tab_paper:
        section_paper_summary(all_pos, all_trades, daily_df, prices)
        section_signals()
        section_positions(live=False, pos_df=all_pos, prices=prices, tab_key="paper")
        section_trades(live=False, trades_df=all_trades)
        section_pattern_perf(live=False, trades_df=all_trades)
        section_daily_chart()

    st.caption(f"⏱ {REFRESH_SEC}초 후 자동갱신...")
    time.sleep(REFRESH_SEC)
    st.rerun()


main()
