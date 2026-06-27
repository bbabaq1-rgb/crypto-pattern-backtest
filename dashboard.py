"""
dashboard.py — 암호화폐 패턴 자동매매 실시간 대시보드
OKX 실계좌 / Supabase / 모바일 최적화 / 30초 자동갱신
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

# ── 모바일 친화적 CSS ──────────────────────────────────────────────────────────
st.markdown("""
<style>
    .main .block-container {
        padding-top: 0.6rem;
        padding-bottom: 1rem;
        max-width: 700px;
        padding-left: 0.8rem;
        padding-right: 0.8rem;
    }
    h1 { font-size: 1.5rem !important; margin-bottom: 0.4rem; }
    h2, h3 { font-size: 1.15rem !important; margin-bottom: 0.3rem; }
    div[data-testid="stMetricValue"] { font-size: 1.45rem !important; }
    div[data-testid="stMetricLabel"] { font-size: 0.88rem !important; }
    div[data-testid="stMetricDelta"] { font-size: 0.88rem !important; }
    .stTabs [data-baseweb="tab"] { font-size: 0.88rem; padding: 4px 12px; }
    .stButton > button { font-size: 0.9rem; padding: 0.3rem 0.8rem; }
    [data-testid="stDataFrame"] table { font-size: 0.82rem !important; }
    .stCaption { font-size: 0.8rem; }
</style>
""", unsafe_allow_html=True)

REFRESH_SEC = 30
PERF_START  = "2026-06-27"   # 성과 측정 시작일
INITIAL_CAP = 2000.0         # scheduler.py daily_summary 기준 자본

# ── 환경변수: .env + Streamlit Cloud Secrets ──────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv(override=False)
except ImportError:
    pass

# Streamlit Cloud Secrets → os.environ  (exchange.py는 os.environ을 읽음)
try:
    _KEYS = ("OKX_KEY", "OKX_SECRET", "OKX_PASSPHRASE",
             "SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_KEY")
    for _k in _KEYS:
        if _k in st.secrets and _k not in os.environ:
            os.environ[_k] = str(st.secrets[_k])
except Exception:
    pass

# ── Supabase 클라이언트 ────────────────────────────────────────────────────────
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
    """Supabase trades + paper_trades.json 합산. Supabase 우선 중복 제거, 날짜 내림차순."""
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
        combined = combined.sort_values("_src")   # "db" < "json" → db 우선
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


# ── 청산 헬퍼 ─────────────────────────────────────────────────────────────────

def _close_live_okx(sym, direction):
    """OKX 선물 포지션 시장가 청산. (ok, msg) 반환."""
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
                close_side = "sell" if direction == "long" else "buy"
                ex.create_market_order(ccxt_sym, close_side, qty, params={
                    "tdMode": "isolated", "reduceOnly": True,
                })
                return True, f"시장가 청산 qty={qty}"
        return False, "OKX에서 포지션 미확인"
    except Exception as e:
        return False, str(e)[:80]


def _do_close_position(pos_row, cur_price):
    """포지션 청산: OKX(실거래) + Supabase + 로컬 JSON. (ok, msg) 반환."""
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

    # 1. OKX 실거래 청산
    if live:
        ok, msg = _close_live_okx(sym, direction)
        msgs.append(msg)
        if not ok:
            return False, msg

    # 2. Supabase positions → closed
    cli = _supabase()
    if cli and pos_id:
        try:
            cli.table("positions").update({"status": "closed"}).eq("id", pos_id).execute()
            msgs.append("DB 업데이트")
        except Exception as e:
            msgs.append(f"DB 실패: {str(e)[:30]}")

    # 3. Supabase trades INSERT
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

    # 4. 로컬 paper_positions.json 업데이트
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

    # 5. 로컬 paper_trades.json에 청산 기록 추가
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


# ── 섹션 1: 현황 요약 ──────────────────────────────────────────────────────────
def section_summary():
    current, _ = load_regime()
    trades_df  = load_trades()
    pos_df     = load_positions()
    daily_df   = load_daily_summary()
    balance, is_live_mode = fetch_account_balance()

    regime      = current.get("regime", "—")
    action      = current.get("action", {})
    regime_date = current.get("date", "")
    now_str     = datetime.now(timezone.utc).strftime("%m/%d %H:%M UTC")

    # 오픈 포지션 미실현 손익
    today_pnl_usd = 0.0
    if not pos_df.empty:
        syms   = tuple(sorted(pos_df["symbol"].unique().tolist()))
        prices = fetch_prices(syms)
        for _, pos in pos_df.iterrows():
            s  = str(pos.get("symbol", ""))
            d  = str(pos.get("direction", ""))
            ep = float(pos.get("entry_price") or 0)
            sz = float(pos.get("size_usd") or 0)
            lv = 2.0 if bool(pos.get("live_mode", False)) else 1.0
            cp = prices.get(s)
            if cp and ep and sz:
                today_pnl_usd += sz * lv * ((cp - ep) / ep if d == "long" else (ep - cp) / ep)
    today_pnl_usd = round(today_pnl_usd, 2)

    # ── 총자산 섹션 크게 표시 ────────────────────────────────────────────────
    if balance is None:
        st.markdown("""
<div style="padding:0.5rem 0 0.1rem 0">
  <div style="font-size:0.82rem;color:#888;margin-bottom:0.15rem">Est. Total Value</div>
  <div style="font-size:1.6rem;color:#666">실거래 미연결</div>
  <div style="font-size:0.8rem;color:#555;margin-top:0.2rem">
    Streamlit Secrets에 OKX_KEY · OKX_SECRET · OKX_PASSPHRASE 추가 시 실계좌 잔고 표시
  </div>
</div>""", unsafe_allow_html=True)
    else:
        today_pnl_pct = round(today_pnl_usd / balance * 100, 2) if balance > 0 else 0.0
        pnl_color = "#00cc66" if today_pnl_usd >= 0 else "#ff4444"
        pnl_sign  = "+" if today_pnl_usd >= 0 else ""
        pct_sign  = "+" if today_pnl_pct >= 0 else ""
        st.markdown(f"""
<div style="padding:0.5rem 0 0.1rem 0">
  <div style="font-size:0.82rem;color:#888;margin-bottom:0.1rem">Est. Total Value &nbsp;·&nbsp; OKX 선물</div>
  <div style="font-size:2.6rem;font-weight:700;line-height:1.15;color:#fafafa">${balance:,.2f}</div>
  <div style="font-size:1.05rem;color:{pnl_color};margin-top:0.2rem">
    Today's PNL (미실현): {pnl_sign}${today_pnl_usd:.2f} &nbsp;({pct_sign}{today_pnl_pct:.2f}%)
  </div>
</div>""", unsafe_allow_html=True)

    st.caption(f"🕐 {now_str}  ·  {REFRESH_SEC}초 자동갱신")
    st.divider()

    # ── 레짐 + 누적수익률 ────────────────────────────────────────────────────
    r_emoji  = REGIME_EMOJI.get(regime, "❓")
    dir_text = "  |  ".join(f"{k} → {DIR_LABEL.get(v, v)}" for k, v in action.items()) if action else "—"
    st.markdown(f"### {r_emoji} {regime} `{regime_date}`")
    st.caption(dir_text)

    cum_a = _rebase_cum(daily_df, "cumulative_return_a")
    cum_d = _rebase_cum(daily_df, "cumulative_return_d")
    if (cum_a is None) and (not trades_df.empty):
        m   = "method" if "method" in trades_df.columns else "method_label"
        tdf = trades_df
        if "entry_date" in tdf.columns:
            tdf = tdf[tdf["entry_date"].astype(str) >= PERF_START]
        if m in tdf.columns and "pnl_usd" in tdf.columns:
            cum_a = round(tdf[tdf[m] == "A"]["pnl_usd"].sum() / INITIAL_CAP * 100, 2)
            cum_d = round(tdf[tdf[m] == "D"]["pnl_usd"].sum() / INITIAL_CAP * 100, 2)
        elif m in tdf.columns and "return_pct" in tdf.columns:
            cum_a = round(tdf[tdf[m] == "A"]["return_pct"].sum(), 2)
            cum_d = round(tdf[tdf[m] == "D"]["return_pct"].sum(), 2)

    pnl_a_usd = round(cum_a / 100 * INITIAL_CAP, 2) if cum_a is not None else None
    pnl_d_usd = round(cum_d / 100 * INITIAL_CAP, 2) if cum_d is not None else None

    c1, c2 = st.columns(2)
    c1.metric("방식A 누적수익 (since 06-27)",
              _fmt_pct(cum_a) if cum_a is not None else "데이터 없음",
              delta=f"${pnl_a_usd:+.2f}" if pnl_a_usd is not None else None)
    c2.metric("방식D 누적수익 (since 06-27)",
              _fmt_pct(cum_d) if cum_d is not None else "데이터 없음",
              delta=f"${pnl_d_usd:+.2f}" if pnl_d_usd is not None else None)

    open_cnt  = len(pos_df) if not pos_df.empty else 0
    trade_cnt = len(trades_df) if not trades_df.empty else 0
    live_cnt  = int((pos_df["live_mode"] == True).sum()) if (not pos_df.empty and "live_mode" in pos_df.columns) else 0

    c3, c4 = st.columns(2)
    c3.metric("오픈 포지션", f"{open_cnt}개", delta=f"실거래 {live_cnt}개" if live_cnt else None)
    c4.metric("총 체결건수", f"{trade_cnt}건")
    st.divider()


# ── 섹션 2: 오늘 신호 ──────────────────────────────────────────────────────────
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


# ── 섹션 3: 오픈 포지션 (청산 버튼 포함) ────────────────────────────────────────
def section_positions():
    st.subheader("📂 오픈 포지션")
    df = load_positions()

    if df.empty:
        st.info("오픈 포지션 없음")
        st.divider()
        return

    symbols = tuple(sorted(df["symbol"].unique().tolist()))
    prices  = fetch_prices(symbols)

    if "confirm_close" not in st.session_state:
        st.session_state.confirm_close = None

    st.caption("🔴실 = 실거래  |  🟡페 = 페이퍼  |  청산 버튼으로 수동 청산 가능")

    for i, (_, pos) in enumerate(df.iterrows()):
        sym        = str(pos.get("symbol", ""))
        direction  = str(pos.get("direction", ""))
        entry      = float(pos.get("entry_price") or 0)
        stop       = float(pos.get("stop_loss") or pos.get("stop") or 0)
        size_usd   = float(pos.get("size_usd") or 0)
        live       = bool(pos.get("live_mode", False))
        leverage   = 2.0 if live else 1.0
        notional   = size_usd * leverage
        entry_date = str(pos.get("entry_date", ""))[:10]
        pattern    = str(pos.get("pattern", ""))
        pos_key    = f"{sym}_{pattern}_{direction}_{entry_date}"

        cur = prices.get(sym)
        if cur and entry and notional:
            ret_pct  = (cur - entry) / entry * 100 if direction == "long" else (entry - cur) / entry * 100
            pnl_usd  = notional * ((cur - entry) / entry if direction == "long" else (entry - cur) / entry)
            cur_val  = size_usd + pnl_usd
            pnl_c    = "#00cc66" if pnl_usd >= 0 else "#ff4444"
            pnl_html = (f"<span style='color:{pnl_c}'>"
                        f"{'+'if pnl_usd>=0 else ''}${pnl_usd:.2f} "
                        f"({'+'if ret_pct>=0 else ''}{ret_pct:.2f}%)</span>")
            cur_val_str = f"${cur_val:.2f}"
        else:
            pnl_html    = "—"
            cur_val_str = "—"
            pnl_usd     = None
            cur         = None

        mode  = "🔴실" if live else "🟡페"
        d_lbl = DIR_LABEL.get(direction, direction)

        col_mode, col_info, col_price, col_btn = st.columns([0.55, 2.2, 3.3, 1.2])
        col_mode.markdown(mode)
        col_info.markdown(
            f"**{sym}** {d_lbl}<br>"
            f"<small style='color:#888'>{pattern} · {entry_date}</small>",
            unsafe_allow_html=True)
        col_price.markdown(
            f"진입 **{_fmt_price(entry)}** → 현재 **{_fmt_price(cur) if cur else '—'}**<br>"
            f"손익: {pnl_html} &nbsp;|&nbsp; 손절: {_fmt_price(stop)}<br>"
            f"<small>투입 ${size_usd:.0f} → 평가 {cur_val_str}</small>",
            unsafe_allow_html=True)

        if col_btn.button("청산", key=f"close_{pos_key}", type="secondary"):
            st.session_state.confirm_close = pos_key

        # 확인 팝업
        if st.session_state.confirm_close == pos_key:
            st.warning(
                f"⚠️ **{sym} {d_lbl}** 포지션을 청산하시겠습니까?  \n"
                f"{'실거래: OKX 시장가 주문 제출' if live else '페이퍼: 수동청산으로 기록'}")
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

        st.markdown("<hr style='margin:0.35rem 0;border-color:#2a2a2a'>", unsafe_allow_html=True)

    st.divider()


# ── 섹션 4: 최근 매매 내역 ──────────────────────────────────────────────────────
def section_trades():
    st.subheader("📋 최근 매매 내역")
    df = load_trades()

    if df.empty:
        st.info("아직 거래 없음")
        st.divider()
        return

    m_col   = "method" if "method" in df.columns else ("method_label" if "method_label" in df.columns else None)
    ret_col = "return_pct" if "return_pct" in df.columns else "ret"
    mult    = 1.0 if ret_col == "return_pct" else 100.0

    tab_a, tab_d = st.tabs(["📗 방식A  (트리플 배리어)", "📘 방식D  (조건부 익절)"])

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


# ── 섹션 5: 패턴 성과 ──────────────────────────────────────────────────────────
def section_pattern_perf():
    st.subheader("🏆 패턴 성과")
    df = load_trades()

    if df.empty or "pattern" not in df.columns:
        st.info("집계 데이터 없음")
        st.divider()
        return

    ret_col = "return_pct" if "return_pct" in df.columns else "ret"
    mult    = 1.0 if ret_col == "return_pct" else 100.0

    grp = df.groupby("pattern")[ret_col]
    agg = pd.DataFrame({
        "패턴":        grp.count().index,
        "건수":        grp.count().values,
        "평균수익(%)": (grp.mean() * mult).round(2).values,
        "승률(%)":     grp.apply(lambda x: round((x > 0).mean() * 100, 1)).values,
    })

    st.dataframe(agg, use_container_width=True, hide_index=True)
    if len(agg) >= 1:
        st.bar_chart(agg.set_index("패턴")[["평균수익(%)", "승률(%)"]], use_container_width=True)
    st.divider()


# ── 섹션 6: 일별 누적 수익률 ──────────────────────────────────────────────────
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
            baseline  = float(df[col].iloc[0])
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

    section_summary()
    section_signals()
    section_positions()
    section_trades()
    section_pattern_perf()
    section_daily_chart()

    st.caption(f"⏱ {REFRESH_SEC}초 후 자동갱신...")
    time.sleep(REFRESH_SEC)
    st.rerun()


main()
