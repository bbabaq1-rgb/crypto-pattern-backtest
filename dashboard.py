"""
dashboard.py — 암호화폐 패턴 자동매매 실시간 대시보드
Supabase + 로컬 JSON 폴백 / 모바일 최적화 / 30초 자동갱신
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

# ── 환경변수 (.env 지원) ───────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv(override=False)
except ImportError:
    pass

# ── Supabase 클라이언트 (연결당 1회 캐시) ────────────────────────────────────
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


# ── 데이터 로더 (ttl=25s → 30s sleep 후 rerun 시 자동 갱신) ─────────────────

@st.cache_data(ttl=25)
def load_trades():
    cli = _supabase()
    if cli:
        try:
            r = cli.table("trades").select("*").order("entry_date", desc=True).limit(200).execute()
            if r.data:
                df = pd.DataFrame(r.data)
                if "return_pct" not in df.columns and "ret" in df.columns:
                    df["return_pct"] = (df["ret"] * 100).round(4)
                return df
        except Exception:
            pass
    return pd.DataFrame()


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
    """Supabase signals 테이블에서 오늘 신호 조회"""
    today = date.today().isoformat()
    cli = _supabase()
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


@st.cache_data(ttl=60)
def fetch_prices(symbols_tuple):
    """OKX 퍼블릭 API 현재가 (인증 불필요). 실패 시 빈 dict."""
    if not symbols_tuple:
        return {}
    try:
        import ccxt
        ex = ccxt.okx({"enableRateLimit": True})
        result = {}
        for sym in symbols_tuple:
            try:
                t = ex.fetch_ticker(f"{sym}/USDT")
                result[sym] = float(t["last"])
            except Exception:
                pass
        return result
    except Exception:
        return {}


# ── 포맷 헬퍼 ─────────────────────────────────────────────────────────────────

REGIME_EMOJI = {
    "bear": "🐻", "bull_btc": "🐂",
    "bull_altseason": "🌊", "sideways": "↔️",
}
DIR_LABEL = {"long": "🟢 롱", "short": "🔴 숏", "FLAT": "— FLAT"}


def _fmt_price(v):
    try:
        v = float(v)
        if v == 0:
            return "—"
        if v >= 100:
            return f"{v:,.2f}"
        if v >= 1:
            return f"{v:.4f}"
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


# ── 섹션 1: 현황 요약 ──────────────────────────────────────────────────────────
def section_summary():
    current, _ = load_regime()
    trades_df  = load_trades()
    pos_df     = load_positions()
    daily_df   = load_daily_summary()

    regime      = current.get("regime", "—")
    action      = current.get("action", {})
    regime_date = current.get("date", "")

    # 누적 수익률 — daily_summary 우선, 없으면 trades에서 계산
    cum_a = cum_d = None
    if not daily_df.empty:
        last = daily_df.sort_values("date").iloc[-1]
        cum_a = last.get("cumulative_return_a")
        cum_d = last.get("cumulative_return_d")
    if (cum_a is None) and (not trades_df.empty):
        m = "method" if "method" in trades_df.columns else "method_label"
        if m in trades_df.columns and "pnl_usd" in trades_df.columns:
            cap = 2000.0  # scheduler.py daily_summary 계산 기준과 동일
            cum_a = round(trades_df[trades_df[m] == "A"]["pnl_usd"].sum() / cap * 100, 2)
            cum_d = round(trades_df[trades_df[m] == "D"]["pnl_usd"].sum() / cap * 100, 2)
        elif m in trades_df.columns and "return_pct" in trades_df.columns:
            cum_a = round(trades_df[trades_df[m] == "A"]["return_pct"].sum(), 2)
            cum_d = round(trades_df[trades_df[m] == "D"]["return_pct"].sum(), 2)

    open_cnt   = len(pos_df) if not pos_df.empty else 0
    trade_cnt  = len(trades_df) if not trades_df.empty else 0
    now_str    = datetime.now(timezone.utc).strftime("%m/%d %H:%M UTC")
    live_cnt   = int((pos_df["live_mode"] == True).sum()) if (not pos_df.empty and "live_mode" in pos_df.columns) else 0

    # 레짐 + 방향
    r_emoji  = REGIME_EMOJI.get(regime, "❓")
    dir_text = "  |  ".join(f"{k} → {DIR_LABEL.get(v, v)}" for k, v in action.items()) if action else "—"

    st.markdown(f"### {r_emoji} {regime} `{regime_date}`")
    st.caption(dir_text)

    c1, c2 = st.columns(2)
    c1.metric("방식A 누적수익", _fmt_pct(cum_a) if cum_a is not None else "—")
    c2.metric("방식D 누적수익", _fmt_pct(cum_d) if cum_d is not None else "—")

    c3, c4 = st.columns(2)
    c3.metric("오픈 포지션", f"{open_cnt}개", delta=f"실거래 {live_cnt}개" if live_cnt else None)
    c4.metric("총 체결건수", f"{trade_cnt}건")

    st.caption(f"🕐 {now_str}  ·  {REFRESH_SEC}초 자동갱신")
    st.divider()


# ── 섹션 2: 오늘 신호 ──────────────────────────────────────────────────────────
def section_signals():
    st.subheader("🔔 오늘 신호")
    df = load_signals()

    if df.empty:
        st.info("오늘 신호 없음")
        st.divider()
        return

    entry_col = "entry" if "entry" in df.columns else "entry_price"
    stop_col  = "stop"  if "stop"  in df.columns else "stop_loss"

    rows = []
    for _, s in df.iterrows():
        d = str(s.get("direction", ""))
        rows.append({
            "종목":   s.get("symbol", ""),
            "패턴":   s.get("pattern", ""),
            "방향":   DIR_LABEL.get(d, d),
            "진입가": _fmt_price(s.get(entry_col)),
            "손절가": _fmt_price(s.get(stop_col)),
            "강도":   f"{s['strength_vol_ratio']:.2f}x" if s.get("strength_vol_ratio") else "—",
            "레짐":   s.get("regime", ""),
        })

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.divider()


# ── 섹션 3: 오픈 포지션 ────────────────────────────────────────────────────────
def section_positions():
    st.subheader("📂 오픈 포지션")
    df = load_positions()

    if df.empty:
        st.info("오픈 포지션 없음")
        st.divider()
        return

    symbols = tuple(sorted(df["symbol"].unique().tolist()))
    prices  = fetch_prices(symbols)

    rows = []
    for _, pos in df.iterrows():
        sym       = str(pos.get("symbol", ""))
        direction = str(pos.get("direction", ""))
        entry     = float(pos.get("entry_price") or 0)
        stop      = float(pos.get("stop_loss") or pos.get("stop") or 0)
        live      = bool(pos.get("live_mode", False))

        cur = prices.get(sym)
        if cur and entry:
            ret_pct = ((cur - entry) / entry * 100) if direction == "long" \
                      else ((entry - cur) / entry * 100)
            ret_str = f"{_ret_dot(ret_pct)} {ret_pct:+.2f}%"
        else:
            ret_str = "—"

        rows.append({
            "":       "🔴실" if live else "🟡페",
            "종목":   sym,
            "방향":   DIR_LABEL.get(direction, direction),
            "패턴":   str(pos.get("pattern", "")),
            "진입가": _fmt_price(entry),
            "현재가": _fmt_price(cur) if cur else "—",
            "수익률": ret_str,
            "손절가": _fmt_price(stop),
            "진입일": str(pos.get("entry_date", ""))[:10],
        })

    st.caption("🔴실 = 실거래  |  🟡페 = 페이퍼")
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.divider()


# ── 섹션 4: 최근 매매 내역 ──────────────────────────────────────────────────────
def section_trades():
    st.subheader("📋 최근 매매 내역")
    df = load_trades()

    if df.empty:
        st.info("체결 내역 없음")
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
                ret_val = (float(t.get(ret_col) or 0)) * mult
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
        "패턴":       grp.count().index,
        "건수":       grp.count().values,
        "평균수익(%)": (grp.mean() * mult).round(2).values,
        "승률(%)":    grp.apply(lambda x: round((x > 0).mean() * 100, 1)).values,
    })

    st.dataframe(agg, use_container_width=True, hide_index=True)

    if len(agg) >= 1:
        chart_df = agg.set_index("패턴")[["평균수익(%)", "승률(%)"]]
        st.bar_chart(chart_df, use_container_width=True)

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

    cols = {}
    if "cumulative_return_a" in df.columns:
        cols["방식A(%)"] = df["cumulative_return_a"]
    if "cumulative_return_d" in df.columns:
        cols["방식D(%)"] = df["cumulative_return_d"]

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
