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

REFRESH_SEC  = 30
PERF_START   = "2026-06-27"   # 성과 측정 시작일 (이전 시뮬레이션 제외)
INITIAL_CAP  = 2000.0         # scheduler.py daily_summary 기준 자본 ($)

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


@st.cache_data(ttl=25)
def fetch_account_balance():
    """(balance_usd, is_live) — OKX 선물 USDT 잔고. 키 없으면 (200.0, False)."""
    try:
        import exchange as ex_mod
        if ex_mod.is_live():
            conn = ex_mod.connect_live()
            if conn:
                return ex_mod.get_balance(conn), True
    except Exception:
        pass
    return 200.0, False


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


def _rebase_cum(daily_df, col):
    """PERF_START 이전 누적값을 베이스라인으로 차감해 재기산."""
    if daily_df.empty or col not in daily_df.columns:
        return None
    df      = daily_df.sort_values("date")
    before  = df[df["date"] < PERF_START]
    baseline = float(before.iloc[-1][col]) if not before.empty else 0.0
    after   = df[df["date"] >= PERF_START]
    if after.empty:
        return None
    return round(float(after.iloc[-1][col]) - baseline, 4)


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

    # ── 오픈 포지션 미실현 손익 → Today's PNL ────────────────────────────────
    today_pnl_usd = 0.0
    if not pos_df.empty:
        symbols = tuple(sorted(pos_df["symbol"].unique().tolist()))
        prices  = fetch_prices(symbols)
        for _, pos in pos_df.iterrows():
            sym       = str(pos.get("symbol", ""))
            direction = str(pos.get("direction", ""))
            entry     = float(pos.get("entry_price") or 0)
            size_usd  = float(pos.get("size_usd") or 0)
            live      = bool(pos.get("live_mode", False))
            leverage  = 2.0 if live else 1.0
            notional  = size_usd * leverage
            cur       = prices.get(sym)
            if cur and entry and notional:
                pnl = notional * (cur - entry) / entry if direction == "long" \
                      else notional * (entry - cur) / entry
                today_pnl_usd += pnl
    today_pnl_usd = round(today_pnl_usd, 2)
    today_pnl_pct = round(today_pnl_usd / balance * 100, 2) if balance > 0 else 0.0

    # ── 총자산 크게 표시 ─────────────────────────────────────────────────────
    pnl_color    = "#00cc66" if today_pnl_usd >= 0 else "#ff4444"
    pnl_sign     = "+" if today_pnl_usd >= 0 else ""
    pct_sign     = "+" if today_pnl_pct >= 0 else ""
    mode_label   = "OKX 선물" if is_live_mode else "시뮬레이션"

    st.markdown(f"""
<div style="padding:0.5rem 0 0.1rem 0">
  <div style="font-size:0.82rem;color:#888;margin-bottom:0.1rem">Est. Total Value &nbsp;·&nbsp; {mode_label}</div>
  <div style="font-size:2.6rem;font-weight:700;line-height:1.15;color:#fafafa">${balance:,.2f}</div>
  <div style="font-size:1.05rem;color:{pnl_color};margin-top:0.2rem">
    Today's PNL (미실현): {pnl_sign}${today_pnl_usd:.2f} &nbsp;({pct_sign}{today_pnl_pct:.2f}%)
  </div>
</div>""", unsafe_allow_html=True)
    st.caption(f"🕐 {now_str}  ·  {REFRESH_SEC}초 자동갱신")
    st.divider()

    # ── 레짐 + 누적수익률 (아래) ──────────────────────────────────────────────
    r_emoji  = REGIME_EMOJI.get(regime, "❓")
    dir_text = "  |  ".join(f"{k} → {DIR_LABEL.get(v, v)}" for k, v in action.items()) if action else "—"
    st.markdown(f"### {r_emoji} {regime} `{regime_date}`")
    st.caption(dir_text)

    # 누적 수익률 — PERF_START 기준 재기산
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

    # 우선순위 점수 순 정렬
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
            "점수":     f"{float(pri):.3f}" if pri is not None and pd.notna(pri) else "—",
            "종목":     s.get("symbol", ""),
            "패턴":     s.get("pattern", ""),
            "방향":     DIR_LABEL.get(d, d),
            "진입가":   _fmt_price(s.get(entry_col)),
            "손절가":   _fmt_price(s.get(stop_col)),
            "거래량배수": f"{s['strength_vol_ratio']:.2f}x" if s.get("strength_vol_ratio") else "—",
            "패턴강도": f"{float(ps):.3f}" if ps is not None and pd.notna(ps) else "—",
            "레짐":     s.get("regime", ""),
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
        size_usd  = float(pos.get("size_usd") or 0)
        live      = bool(pos.get("live_mode", False))
        leverage  = 2.0 if live else 1.0
        notional  = size_usd * leverage

        cur = prices.get(sym)
        if cur and entry and notional:
            if direction == "long":
                ret_pct = (cur - entry) / entry * 100
                pnl_usd = notional * (cur - entry) / entry
            else:
                ret_pct = (entry - cur) / entry * 100
                pnl_usd = notional * (entry - cur) / entry
            cur_val = size_usd + pnl_usd
            ret_str = f"{_ret_dot(ret_pct)} {ret_pct:+.2f}% / ${pnl_usd:+.2f}"
        else:
            ret_pct = pnl_usd = cur_val = None
            ret_str = "—"

        rows.append({
            "":         "🔴실" if live else "🟡페",
            "종목":     sym,
            "방향":     DIR_LABEL.get(direction, direction),
            "패턴":     str(pos.get("pattern", "")),
            "진입가":   _fmt_price(entry),
            "진입금액": f"${size_usd:.0f}" if size_usd else "—",
            "현재가":   _fmt_price(cur) if cur else "—",
            "현재평가": f"${cur_val:.2f}" if cur_val is not None else "—",
            "손익":     f"${pnl_usd:+.2f}" if pnl_usd is not None else "—",
            "수익률":   ret_str,
            "손절가":   _fmt_price(stop),
            "진입일":   str(pos.get("entry_date", ""))[:10],
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
    # PERF_START 이후만 표시, 베이스라인 차감해 0 기준으로 재기산
    df = df[df.index >= pd.Timestamp(PERF_START)]

    cols = {}
    for col, label in [("cumulative_return_a", "방식A(%)"), ("cumulative_return_d", "방식D(%)")]:
        if col in df.columns and not df.empty:
            baseline = float(df[col].iloc[0])
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
