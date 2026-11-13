"""
channel_watch.py — 채널 이탈 알림 봇 (2026-11-13, 대표님 개인용 · 코인 · 텔레그램).

관찰 전용 도구다. 매매 모듈(scheduler / paper_executor / exchange / sizing / direction_switch
/ ai_elliott / ai_judge …)을 import 하지 않고, 매매 코드도 이 파일을 import 하지 않는다
(test_channel_watch 가 양방향으로 고정). 주문·포지션과 아무 관계가 없다.

무엇을 하나
  1. channel_watch.json 의 종목·시간대마다 OKX 무기한 공개 캔들을 받아 **닫힌 봉만** 쓴다.
  2. 최근 고점·저점으로 평행 채널을 자동으로 긋는다(v2, 2026-11-13 실데이터 비교로 정함).
     - 고점·저점 = ATR14 의 2배 이상 되돌려야 확정되는 지그재그 스윙(인과적). 양옆 N봉
       프랙탈은 자잘한 흔들림까지 잡아 의미 없는 선을 그었다.
     - 최근 스윙 6개 안의 두 점을 이은 선 + 같은 기울기로 반대쪽 극값에 닿는 평행선.
     - 위·아래가 각각 독립 접점(5봉 안 연속 접점은 하나) 2번 이상, 접점 허용 = 폭의 10%·ATR 0.5배 중
       작은 쪽, 그 구간 종가는 선 밖 폭의 15%·꼬리는 30% 이내, 폭은 ATR 2배 이상·구간 고저 범위 이하.
     - 후보 중 접점이 가장 많은 것(같으면 더 긴 것). 거래량은 고점·저점 고르기에 쓰지 않는다(효과 없음).
  3. 최근 닫힌 봉의 종가가 채널 밖으로 채널 폭의 15% 이상 나가면 텔레그램으로 차트 이미지와 함께 알린다.
     (5% 기준은 3봉 안에 채널로 되돌아오는 가짜 이탈이 26%, 15% 기준은 13%.)
  4. 알림은 Supabase `channel_alerts` 에 남겨 같은 채널을 두 번 알리지 않고, 이후 1·5·20봉
     수익(이탈 방향 기준)을 채워 '어떤 이탈이 실제로 의미 있었나'를 쌓는다.
  5. 매일 summary_hour_utc 시 실행에서 지금 채널 현황 요약(차트 앨범)을 보낸다.

검증된 매매 신호가 아니다. 설계 비교(4종목 수년치)에서 어떤 방식으로 그어도 채널 선이 가운데 선보다
지지·저항 역할을 더 하지 않았고(차이 ±1%p 안), 이탈 뒤 20봉 방향 일치도 50% 였다 — 이 레포의 돌파
계열 기각과 같은 결과. 차트를 대신 지켜봐 주는 도구로 쓴다. 근거는 channel_watch.json design_evidence.

실행
  python channel_watch.py               # 정시 점검(이탈 알림 + 정해진 시각이면 요약)
  python channel_watch.py --summary     # 요약을 지금 보낸다
  python channel_watch.py --dry-run     # 보내지도 기록하지도 않고 화면에만 찍는다
  python channel_watch.py --test-telegram   # 텔레그램 연결 확인 메시지
"""
import io
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

CFG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "channel_watch.json")
TABLE = "channel_alerts"
TF_MS = {"15m": 900_000, "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}
KST = timezone(timedelta(hours=9))
OUTCOME_BARS = (1, 5, 20)
NONPERSIST_MAX_AGE_MIN = 70     # 기록 저장소가 없을 때: 방금(70분 안에) 닫힌 봉만 알린다
RECENT_BREAK_BARS = 40          # 요약에서 채널이 없을 때 직전 이탈을 찾아볼 봉 수


# ---------------------------------------------------------------- 설정·시세

def load_cfg(path=CFG_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def fetch_rows(sym, tf, limit=300):
    """OKX 공개 캔들(무기한 우선, 없으면 현물). [{ts,o,h,l,c,v}] 시간순. 실패 시 []."""
    import ccxt
    ex = ccxt.okx({"enableRateLimit": True})
    for market in (f"{sym}/USDT:USDT", f"{sym}/USDT"):
        try:
            raw = ex.fetch_ohlcv(market, tf, limit=limit)
        except Exception as e:
            print(f"  [시세] {market} {tf} 실패: {str(e)[:80]}")
            continue
        if raw:
            return [dict(ts=int(r[0]), o=float(r[1]), h=float(r[2]), l=float(r[3]),
                         c=float(r[4]), v=float(r[5] or 0.0)) for r in raw]
    return []


def closed_only(rows, tf, now_ms):
    """형성 중인 봉(마감 시각이 아직 안 온 봉)을 뺀다."""
    step = TF_MS[tf]
    return [r for r in rows if r["ts"] + step <= now_ms]


# ---------------------------------------------------------------- 채널

def pivots(rows, k):
    """확정된 프랙탈 피벗 인덱스 (highs, lows). 양옆 k 봉이 있어야 확정 — 마지막 k 봉은 피벗이 될 수 없다."""
    hi, lo = [], []
    n = len(rows)
    for i in range(k, n - k):
        h, l = rows[i]["h"], rows[i]["l"]
        left_h = max(r["h"] for r in rows[i - k:i])
        right_h = max(r["h"] for r in rows[i + 1:i + k + 1])
        if h > left_h and h >= right_h:
            hi.append(i)
        left_l = min(r["l"] for r in rows[i - k:i])
        right_l = min(r["l"] for r in rows[i + 1:i + k + 1])
        if l < left_l and l <= right_l:
            lo.append(i)
    return hi, lo


def pivots_zigzag_atr(rows, mult=2.0, n=14):
    """ATR 배수 지그재그 피벗 (highs, lows) — 고점에서 mult×ATR14 이상 되돌려야 고점 확정, 저점도 같다(인과적).

    v2 기본 피벗. 양옆 N봉 프랙탈은 자잘한 흔들림까지 고점·저점으로 잡아 의미 없는 선을 그었다
    (2026-11-13 실측: 채널 선 존중률이 가운데 선보다 3%p 낮음, 알림 1천 봉당 84건 → 지그재그 54건).
    """
    hi, lo = [], []
    if len(rows) < n + 3:
        return hi, lo
    trs = [0.0]
    for i in range(1, len(rows)):
        p = rows[i - 1]["c"]
        r = rows[i]
        trs.append(max(r["h"] - r["l"], abs(r["h"] - p), abs(r["l"] - p)))

    def atr_at(i):
        seg = trs[max(1, i - n + 1):i + 1]
        return sum(seg) / len(seg)

    start = n
    up_i = dn_i = start
    dirn, ext = 0, start
    for i in range(start + 1, len(rows)):
        thr = mult * atr_at(i)
        r = rows[i]
        if dirn == 0:
            if r["h"] > rows[up_i]["h"]:
                up_i = i
            if r["l"] < rows[dn_i]["l"]:
                dn_i = i
            if up_i < i and rows[up_i]["h"] - r["l"] >= thr:
                hi.append(up_i)
                dirn = -1
                ext = min(range(up_i, i + 1), key=lambda k: rows[k]["l"])
            elif dn_i < i and r["h"] - rows[dn_i]["l"] >= thr:
                lo.append(dn_i)
                dirn = 1
                ext = max(range(dn_i, i + 1), key=lambda k: rows[k]["h"])
        elif dirn == 1:
            if r["h"] > rows[ext]["h"]:
                ext = i
            elif rows[ext]["h"] - r["l"] >= thr:
                hi.append(ext)
                dirn = -1
                ext = min(range(ext, i + 1), key=lambda k: rows[k]["l"])
        else:
            if r["l"] < rows[ext]["l"]:
                ext = i
            elif r["h"] - rows[ext]["l"] >= thr:
                lo.append(ext)
                dirn = 1
                ext = max(range(ext, i + 1), key=lambda k: rows[k]["h"])
    return hi, lo


def pivot_fn_of(ch):
    """설정의 pivot_method 로 피벗 함수를 고른다. 없으면 None(= 프랙탈, 종전 동작)."""
    if ch.get("pivot_method") == "zigzag_atr":
        m = float(ch.get("zigzag_atr_mult", 2.0))
        return lambda rows: pivots_zigzag_atr(rows, m)
    return None


def atr(rows, n=14):
    if len(rows) < 2:
        return 0.0
    trs = []
    for i in range(1, len(rows)):
        p = rows[i - 1]["c"]
        r = rows[i]
        trs.append(max(r["h"] - r["l"], abs(r["h"] - p), abs(r["l"] - p)))
    tail = trs[-n:]
    return sum(tail) / len(tail)


def kind_of(slope, span, width):
    move = slope * span
    if abs(move) < 0.25 * width:
        return "box"
    return "up" if move > 0 else "down"


KIND_KO = {"up": "상승 채널", "down": "하락 채널", "box": "박스(횡보)"}


def fit_channel(rows, k, min_span, ch, piv_fn=None):
    """rows(시험할 봉을 뺀 닫힌 봉 창)에 평행 채널을 맞춘다. 없으면 None.

    선은 창 안 인덱스 t 기준: 아래 = slope*t + lo_icpt, 위 = slope*t + hi_icpt.
    """
    n = len(rows)
    if n < min_span + 2 * k + 2:
        return None
    piv_fn = piv_fn or pivot_fn_of(ch)
    hi_p, lo_p = piv_fn(rows) if piv_fn else pivots(rows, k)
    a_tr = atr(rows)
    tt, need = ch["touch_tol"], ch["min_touches_each"]
    # 채널 유지 허용치 — 종가와 꼬리를 따로 본다(v2). 종가 허용치는 이탈 기준(break_buffer)과 같게 둬야
    # '알림 없이 채널만 조용히 사라지는' 얕은 종가 이탈이 생기지 않는다. 키가 없으면 종전 contain_tol 하나.
    ct_c = ch.get("contain_close_tol", ch.get("contain_tol", 0.05))
    ct_w = ch.get("contain_wick_tol", ch.get("contain_tol", 0.05))
    min_w = ch["min_width_atr"] * a_tr
    best = None

    def consider(anchor, a, b):
        nonlocal best
        if anchor == "low":
            s = (rows[b]["l"] - rows[a]["l"]) / (b - a)
            lo_c = rows[a]["l"] - s * a
            hi_c = max(rows[t]["h"] - s * t for t in range(a, n))
        else:
            s = (rows[b]["h"] - rows[a]["h"]) / (b - a)
            hi_c = rows[a]["h"] - s * a
            lo_c = min(rows[t]["l"] - s * t for t in range(a, n))
        w = hi_c - lo_c
        if w <= 0 or w < min_w:
            return
        span = n - 1 - a
        if span < min_span:
            return
        # 폭이 그 구간 실제 가격 범위보다 넓으면 채널이 아니다 — 가파른 기울기 후보가
        # 모든 봉을 품는 거대한 띠가 되는 것을 막는다(실측: BTC 4h 아래 선 25,918).
        rng = max(rows[t]["h"] for t in range(a, n)) - min(rows[t]["l"] for t in range(a, n))
        if w > ch.get("max_width_range", 1.0) * rng:
            return
        # 그 구간 봉이 채널 안에 머물렀나 — 종가는 폭의 contain_close_tol, 꼬리는 contain_wick_tol 까지 허용
        tc, tw_ = ct_c * w, ct_w * w
        for t in range(a, n):
            lo_t, hi_t = s * t + lo_c, s * t + hi_c
            r = rows[t]
            if r["c"] < lo_t - tc or r["c"] > hi_t + tc or r["l"] < lo_t - tw_ or r["h"] > hi_t + tw_:
                return
        # '닿음' 허용 범위는 폭에 비례하되 ATR 상한을 둔다 — 폭 비례만 쓰면 채널이 클수록
        # 접점이 많이 세어져 거대한 채널이 점수에서 이긴다.
        tw = min(tt * w, ch.get("touch_atr", 1.0) * a_tr)
        t_lo = [p for p in lo_p if p >= a and abs(rows[p]["l"] - (s * p + lo_c)) <= tw]
        t_hi = [p for p in hi_p if p >= a and abs(rows[p]["h"] - (s * p + hi_c)) <= tw]
        # 몇 봉 안에서 연달아 닿은 것은 한 번으로 센다(독립 접점) — 장대봉 하나가 고점·저점으로 동시에
        # 잡히거나 붙은 봉들이 각각 세어져, 실제로는 한 번 닿은 선이 채널로 인정되던 문제(SOL 1h 실측).
        gap = int(ch.get("touch_min_gap", 1))
        t_lo, t_hi = _merge_touches(t_lo, gap), _merge_touches(t_hi, gap)
        if len(t_lo) < need or len(t_hi) < need:
            return
        score = (len(t_lo) + len(t_hi), span)
        if best is None or score > best["_score"]:
            best = dict(_score=score, anchor=anchor, a=a, b=b, slope=s, lo_icpt=lo_c,
                        hi_icpt=hi_c, width=w, span=span, touches_lo=t_lo, touches_hi=t_hi,
                        kind=kind_of(s, span, w), atr=a_tr,
                        start_ts=rows[a]["ts"], a_ts=rows[a]["ts"], b_ts=rows[b]["ts"])

    # 기준점은 최근 피벗에서만 고른다 — 사람은 지금 흐름을 만든 최근 고점·저점에 선을
    # 긋는다. 전체 피벗을 다 쓰면 접점·기간 점수 때문에 오래된 넓은 채널이 이긴다.
    rp = int(ch.get("recent_pivots", 6))
    for pts, anchor in ((lo_p[-rp:], "low"), (hi_p[-rp:], "high")):
        for i in range(len(pts)):
            for j in range(i + 1, len(pts)):
                if pts[j] - pts[i] >= 3:
                    consider(anchor, pts[i], pts[j])
    if best:
        best.pop("_score")
    return best


def _merge_touches(idx, gap):
    """정렬된 접점 인덱스에서 gap 봉 미만으로 붙은 것은 첫 번째 하나만 남긴다."""
    out = []
    for i in sorted(idx):
        if not out or i - out[-1] >= gap:
            out.append(i)
    return out


def lines_at(chn, t):
    """(아래 선, 위 선) 값. 채널은 기울기 하나(slope), 삼각수렴은 선마다 기울기(lo_slope/hi_slope)."""
    sl = chn.get("lo_slope", chn.get("slope"))
    sh = chn.get("hi_slope", chn.get("slope"))
    return sl * t + chn["lo_icpt"], sh * t + chn["hi_icpt"]


def check_break(chn, bar, t, ch):
    """시험 봉(창 인덱스 t)의 종가가 채널 밖이면 ('up'|'down', 폭 대비 이탈 깊이)."""
    lo, hi = lines_at(chn, t)
    buf = ch["break_buffer"] * chn["width"]
    if bar["c"] > hi + buf:
        return "up", (bar["c"] - hi) / chn["width"]
    if bar["c"] < lo - buf:
        return "down", (lo - bar["c"]) / chn["width"]
    return None, 0.0


def alert_key(sym, tf, chn, side):
    """같은 채널(두 기준점)이 같은 쪽으로 깨진 것은 한 번만 알린다."""
    return f"{sym}|{tf}|{chn['anchor']}|{chn['a_ts']}|{chn['b_ts']}|{side}"


def scan(sym, tf, rows, p, ch, only_latest=False):
    """최근 닫힌 봉(recheck_bars 개)마다 '그 봉 직전까지로 그은 채널'을 깼는지 본다."""
    out = []
    n = len(rows)
    recheck = 1 if only_latest else max(1, int(p.get("recheck_bars", 1)))
    for j in range(max(1, n - recheck), n):
        win_start = max(0, j - p["lookback"])
        win = rows[win_start:j]
        chn = fit_channel(win, p["pivot_k"], p["min_span"], ch)
        if not chn:
            continue
        side, depth = check_break(chn, rows[j], len(win), ch)
        if not side:
            continue
        lo, hi = lines_at(chn, len(win))
        vols = [r["v"] for r in rows[max(0, j - 20):j]]
        vavg = sum(vols) / len(vols) if vols else 0.0
        out.append(dict(symbol=sym, tf=tf, side=side, depth=depth, bar=rows[j], j=j,
                        win_start=win_start, chn=chn, lower=lo, upper=hi,
                        vol_ratio=(rows[j]["v"] / vavg) if vavg > 0 else None,
                        key=alert_key(sym, tf, chn, side)))
    return out


def current_state(rows, p, ch):
    """요약용 — 마지막 닫힌 봉 직전까지로 그은 채널과 그 안에서 마지막 봉의 위치."""
    if len(rows) < 2:
        return None
    j = len(rows) - 1
    win_start = max(0, j - p["lookback"])
    win = rows[win_start:j]
    chn = fit_channel(win, p["pivot_k"], p["min_span"], ch)
    if not chn:
        # 큰 움직임 직후엔 새 채널이 아직 없다 — 그 움직임이 깬 직전 채널을 대신 알려준다
        recent = scan("", "", rows, dict(p, recheck_bars=RECENT_BREAK_BARS), ch)
        last = recent[-1] if recent else None
        return dict(chn=None, bar=rows[j], j=j, win_start=win_start, last_break=last)
    lo, hi = lines_at(chn, len(win))
    side, depth = check_break(chn, rows[j], len(win), ch)
    pos = (rows[j]["c"] - lo) / chn["width"]
    return dict(chn=chn, bar=rows[j], j=j, win_start=win_start, lower=lo, upper=hi,
                pos=pos, side=side, depth=depth)


# ---------------------------------------------------------------- 삼각수렴 (2026-11-13 추가)
#
# 위 선 = 최근 고점 두 개, 아래 선 = 최근 저점 두 개를 각각 잇는다(평행 아님). 두 선이 앞쪽에서 만나야(수렴)
# 삼각수렴이다. 모양은 위 선이 오르지 않고 아래 선이 내리지 않는 것만 — 둘 다 같은 쪽으로 기울면
# 쐐기형이라 뺐다. 기준점 네 개는 고-저가 엇갈려야 한다(첫 고점·첫 저점이 둘째 고점·둘째 저점보다 앞).
# 선 사이 폭이 꼭짓점으로 갈수록 좁아지므로 허용치·이탈 기준은 '그 봉의 폭' 비율과 ATR 하한 중 큰 값이다
# (꼭짓점 근처에서 폭 비율만 쓰면 작은 흔들림도 이탈로 잡힌다).

TRI_KO = {"tri_sym": "대칭 삼각형", "tri_asc": "상승 삼각형(위 선 수평)", "tri_desc": "하락 삼각형(아래 선 수평)"}


def tri_kind(move_hi, move_lo, ftol):
    flat_hi, flat_lo = abs(move_hi) <= ftol, abs(move_lo) <= ftol
    if flat_hi and not flat_lo:
        return "tri_asc"
    if flat_lo and not flat_hi:
        return "tri_desc"
    return "tri_sym"


def _tri_tol(frac, w, atr_mult, a_tr):
    return max(frac * w, atr_mult * a_tr)


def fit_triangle(rows, min_span, tri, piv_fn=None):
    """rows(시험할 봉을 뺀 닫힌 봉 창)에 삼각수렴을 맞춘다. 없으면 None.

    선은 창 안 인덱스 t 기준: 아래 = lo_slope*t + lo_icpt, 위 = hi_slope*t + hi_icpt.
    apex = 두 선이 만나는 t(창 인덱스, 실수). prog = 마지막 봉이 시작~꼭짓점 사이 어디쯤인가(0~1).
    """
    n = len(rows)
    if n < min_span + 5:
        return None
    piv_fn = piv_fn or pivot_fn_of(tri) or (lambda r: pivots(r, 3))
    hi_p, lo_p = piv_fn(rows)
    a_tr = atr(rows)
    if a_tr <= 0:
        return None
    rp = int(tri.get("recent_pivots", 6))
    H, L = hi_p[-rp:], lo_p[-rp:]
    pmin, pmax = float(tri.get("min_progress", 0.25)), float(tri.get("max_progress", 0.9))
    ftol_f = float(tri.get("flat_tol", 0.15))
    min_w0 = float(tri.get("min_width_atr", 3.0)) * a_tr
    cc, ca = float(tri.get("contain_close_tol", 0.15)), float(tri.get("contain_close_atr", 0.3))
    wc, wa = float(tri.get("contain_wick_tol", 0.3)), float(tri.get("contain_wick_atr", 0.6))
    tt, ta = float(tri.get("touch_tol", 0.1)), float(tri.get("touch_atr", 0.5))
    need = int(tri.get("min_touches_total", 4))
    gap = int(tri.get("touch_min_gap", 5))
    best = None
    for i in range(len(H)):
        for j in range(i + 1, len(H)):
            h1, h2 = H[i], H[j]
            if h2 - h1 < 3:                                # 같은 봉·붙은 봉 피벗(지그재그는 같은 봉을 두 번 낼 수 있다)
                continue
            sh = (rows[h2]["h"] - rows[h1]["h"]) / (h2 - h1)
            ich = rows[h1]["h"] - sh * h1
            for k in range(len(L)):
                for m in range(k + 1, len(L)):
                    l1, l2 = L[k], L[m]
                    if l2 - l1 < 3 or max(h1, l1) >= min(h2, l2):   # 고-저가 엇갈려야 한다
                        continue
                    sl = (rows[l2]["l"] - rows[l1]["l"]) / (l2 - l1)
                    if sh >= sl:                           # 앞쪽에서 만나야(수렴) 한다
                        continue
                    icl = rows[l1]["l"] - sl * l1
                    a = min(h1, l1)
                    span = n - 1 - a
                    if span < min_span:
                        continue
                    w0 = (sh * a + ich) - (sl * a + icl)
                    if w0 < min_w0:
                        continue
                    apex = (ich - icl) / (sl - sh)
                    prog = (n - 1 - a) / (apex - a)
                    if not (pmin <= prog <= pmax):
                        continue
                    ftol = ftol_f * w0
                    mh, ml = sh * span, sl * span
                    if mh > ftol or ml < -ftol:            # 위 선이 오르거나 아래 선이 내리면 쐐기형
                        continue
                    ok = True
                    for t in range(a, n):
                        lo_t, hi_t = sl * t + icl, sh * t + ich
                        w_t = hi_t - lo_t
                        r = rows[t]
                        tc, tw_ = _tri_tol(cc, w_t, ca, a_tr), _tri_tol(wc, w_t, wa, a_tr)
                        if r["c"] < lo_t - tc or r["c"] > hi_t + tc or r["l"] < lo_t - tw_ or r["h"] > hi_t + tw_:
                            ok = False
                            break
                    if not ok:
                        continue
                    tw = min(tt * w0, ta * a_tr)
                    t_lo = _merge_touches([p for p in lo_p if p >= a and
                                           abs(rows[p]["l"] - (sl * p + icl)) <= tw], gap)
                    t_hi = _merge_touches([p for p in hi_p if p >= a and
                                           abs(rows[p]["h"] - (sh * p + ich)) <= tw], gap)
                    if len(t_lo) < 2 or len(t_hi) < 2 or len(t_lo) + len(t_hi) < need:
                        continue
                    score = (len(t_lo) + len(t_hi), span)
                    if best is None or score > best["_score"]:
                        best = dict(_score=score, pattern="triangle", kind=tri_kind(mh, ml, ftol),
                                    a=a, h1=h1, h2=h2, l1=l1, l2=l2, lo_slope=sl, hi_slope=sh,
                                    lo_icpt=icl, hi_icpt=ich, apex=apex, prog=prog, width0=w0,
                                    span=span, touches_lo=t_lo, touches_hi=t_hi, atr=a_tr,
                                    start_ts=rows[a]["ts"],
                                    anchor_ts=(rows[h1]["ts"], rows[h2]["ts"], rows[l1]["ts"], rows[l2]["ts"]))
    if best:
        best.pop("_score")
    return best


def check_break_tri(tr, bar, t, tri):
    """시험 봉(창 인덱스 t)의 종가가 삼각형 밖이면 ('up'|'down', 그 봉 폭 대비 이탈 깊이)."""
    lo, hi = lines_at(tr, t)
    w = hi - lo
    if w <= 0:
        return None, 0.0                                   # 꼭짓점을 지났다 — 삼각형이 끝났다
    buf = _tri_tol(float(tri.get("break_buffer", 0.15)), w, float(tri.get("break_atr", 0.3)), tr["atr"])
    if bar["c"] > hi + buf:
        return "up", (bar["c"] - hi) / w
    if bar["c"] < lo - buf:
        return "down", (lo - bar["c"]) / w
    return None, 0.0


def alert_key_tri(sym, tf, tr, side):
    """같은 삼각형(기준점 넷)이 같은 쪽으로 깨진 것은 한 번만 알린다."""
    return f"{sym}|{tf}|tri|" + "|".join(str(x) for x in tr["anchor_ts"]) + f"|{side}"


def scan_tri(sym, tf, rows, p, tri, only_latest=False):
    """최근 닫힌 봉(recheck_bars 개)마다 '그 봉 직전까지로 그은 삼각형'을 깼는지 본다."""
    out = []
    n = len(rows)
    recheck = 1 if only_latest else max(1, int(p.get("recheck_bars", 1)))
    for j in range(max(1, n - recheck), n):
        win_start = max(0, j - p["lookback"])
        win = rows[win_start:j]
        tr = fit_triangle(win, p["min_span"], tri)
        if not tr:
            continue
        side, depth = check_break_tri(tr, rows[j], len(win), tri)
        if not side:
            continue
        lo, hi = lines_at(tr, len(win))
        vols = [r["v"] for r in rows[max(0, j - 20):j]]
        vavg = sum(vols) / len(vols) if vols else 0.0
        out.append(dict(pattern="triangle", symbol=sym, tf=tf, side=side, depth=depth, bar=rows[j], j=j,
                        win_start=win_start, chn=tr, lower=lo, upper=hi,
                        vol_ratio=(rows[j]["v"] / vavg) if vavg > 0 else None,
                        key=alert_key_tri(sym, tf, tr, side)))
    return out


def current_state_tri(rows, p, tri):
    """요약용 — 마지막 닫힌 봉 직전까지로 그은 삼각형과 마지막 봉 위치. 없으면 chn=None."""
    if len(rows) < 2:
        return None
    j = len(rows) - 1
    win_start = max(0, j - p["lookback"])
    win = rows[win_start:j]
    tr = fit_triangle(win, p["min_span"], tri)
    if not tr:
        return dict(chn=None, bar=rows[j], j=j, win_start=win_start)
    lo, hi = lines_at(tr, len(win))
    side, depth = check_break_tri(tr, rows[j], len(win), tri)
    w = hi - lo
    pos = (rows[j]["c"] - lo) / w if w > 0 else 0.5
    return dict(chn=tr, bar=rows[j], j=j, win_start=win_start, lower=lo, upper=hi,
                pos=pos, side=side, depth=depth, bars_to_apex=tr["apex"] - len(win))


# ---------------------------------------------------------------- 표기

def fmt_px(x):
    if x >= 1000:
        return f"{x:,.0f}"
    if x >= 1:
        return f"{x:,.2f}"
    return f"{x:.6g}"


def kst(ts_ms):
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).astimezone(KST).strftime("%m-%d %H:%M")


def alert_text(ev):
    c = ev["chn"]
    arrow = "🔺" if ev["side"] == "up" else "🔻"
    what = "상단 돌파" if ev["side"] == "up" else "하단 이탈"
    vr = f" · 거래량 {ev['vol_ratio']:.1f}배(직전 20봉 평균 대비)" if ev.get("vol_ratio") else ""
    return (f"{arrow} <b>{ev['symbol']} {ev['tf']} 채널 {what}</b>\n"
            f"종가 {fmt_px(ev['bar']['c'])} ({kst(ev['bar']['ts'] + TF_MS[ev['tf']])} KST 마감 봉)\n"
            f"채널 위 {fmt_px(ev['upper'])} · 아래 {fmt_px(ev['lower'])} · 폭 {fmt_px(c['width'])}\n"
            f"{KIND_KO[c['kind']]} · {kst(c['start_ts'])} 부터 {c['span']}봉 · "
            f"접점 아래 {len(c['touches_lo'])} / 위 {len(c['touches_hi'])}\n"
            f"이탈 폭: 채널 폭의 {ev['depth'] * 100:.0f}%{vr}\n"
            f"<i>과거 같은 기준(4종목 수년치): 약 12% 가 3봉 안에 채널로 되돌아왔고 20봉 뒤 방향은 반반 — "
            f"관찰용 알림, 매매 신호 아님</i>")


def summary_line(sym, tf, st):
    if st is None:
        return f"{sym} {tf}: 데이터 없음"
    if not st.get("chn"):
        lb = st.get("last_break")
        tail = ""
        if lb:
            what = "상단 돌파" if lb["side"] == "up" else "하단 이탈"
            line = lb["upper"] if lb["side"] == "up" else lb["lower"]
            tail = (f" — 직전 {kst(lb['bar']['ts'] + TF_MS[tf])} {what}"
                    f"({fmt_px(line)} {'위' if lb['side'] == 'up' else '아래'} 마감)")
        return f"{sym} {tf}: 새 채널 아직 없음 (종가 {fmt_px(st['bar']['c'])}){tail}"
    c = st["chn"]
    if st.get("side"):
        where = "위로 이탈 중" if st["side"] == "up" else "아래로 이탈 중"
    else:
        where = f"채널 안 {max(0.0, min(1.0, st['pos'])) * 100:.0f}% 위치"
    return (f"{sym} {tf}: {KIND_KO[c['kind']]} {fmt_px(st['lower'])}~{fmt_px(st['upper'])} · "
            f"종가 {fmt_px(st['bar']['c'])} · {where}")


TRI_HISTORY_NOTE = "과거 BTC 기준(같은 규칙): {fb} — 관찰용 알림, 매매 신호 아님"


def alert_text_tri(ev, note=""):
    c = ev["chn"]
    arrow = "🔺" if ev["side"] == "up" else "🔻"
    what = "위로 돌파" if ev["side"] == "up" else "아래로 이탈"
    vr = f" · 거래량 {ev['vol_ratio']:.1f}배(직전 20봉 평균 대비)" if ev.get("vol_ratio") else ""
    w = ev["upper"] - ev["lower"]
    return (f"{arrow} <b>{ev['symbol']} {ev['tf']} 삼각수렴 {what}</b>\n"
            f"종가 {fmt_px(ev['bar']['c'])} ({kst(ev['bar']['ts'] + TF_MS[ev['tf']])} KST 마감 봉)\n"
            f"위 선 {fmt_px(ev['upper'])} · 아래 선 {fmt_px(ev['lower'])} · 남은 폭 {fmt_px(w)}"
            f" (시작 폭 {fmt_px(c['width0'])})\n"
            f"{TRI_KO[c['kind']]} · {kst(c['start_ts'])} 부터 {c['span']}봉 · "
            f"접점 위 {len(c['touches_hi'])} / 아래 {len(c['touches_lo'])} · 꼭짓점까지 {c['prog'] * 100:.0f}% 진행\n"
            f"이탈 폭: 남은 폭의 {ev['depth'] * 100:.0f}%{vr}\n"
            f"<i>{note or '관찰용 알림, 매매 신호 아님'}</i>")


def summary_line_tri(sym, tf, st):
    if st is None:
        return f"△ {sym} {tf}: 데이터 없음"
    if not st.get("chn"):
        return f"△ {sym} {tf}: 삼각수렴 없음 (종가 {fmt_px(st['bar']['c'])})"
    c = st["chn"]
    if st.get("side"):
        where = "위로 이탈 중" if st["side"] == "up" else "아래로 이탈 중"
    else:
        where = f"안쪽 {max(0.0, min(1.0, st['pos'])) * 100:.0f}% 위치"
    return (f"△ {sym} {tf}: {TRI_KO[c['kind']]} {fmt_px(st['lower'])}~{fmt_px(st['upper'])} · "
            f"종가 {fmt_px(st['bar']['c'])} · {where} · 꼭짓점까지 약 {max(0, st['bars_to_apex']):.0f}봉")


def chart_png(sym, tf, rows, j, win_start, chn, side=None, bars=120):
    """마지막 bars 봉 캔들 + 채널 선. PNG bytes. 차트 글자는 영문(러너에 한글 글꼴이 없다)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    lo_i = max(0, j - bars + 1)
    if chn:
        lo_i = min(lo_i, max(0, win_start + chn["a"] - 10))   # 채널 시작점이 보이게
    seg = rows[lo_i:j + 1]
    fig, ax = plt.subplots(figsize=(10, 5), dpi=110)
    for x, r in enumerate(seg):
        up = r["c"] >= r["o"]
        col = "#26a69a" if up else "#ef5350"
        ax.vlines(x, r["l"], r["h"], color=col, linewidth=0.8)
        ax.add_patch(plt.Rectangle((x - 0.35, min(r["o"], r["c"])), 0.7,
                                   max(abs(r["c"] - r["o"]), 1e-12), color=col))
    if chn:
        # 창 인덱스 t ↔ rows 인덱스 win_start + t ↔ 차트 x = win_start + t - lo_i
        t0 = chn["a"]
        t1 = (j - win_start) + 3
        if chn.get("apex") is not None:          # 삼각수렴은 꼭짓점에서 선을 멈춘다
            t1 = min(t1, int(chn["apex"]))
        xs, los, his = [], [], []
        for t in range(t0, t1 + 1):
            x = win_start + t - lo_i
            if x < 0:
                continue
            lo_v, hi_v = lines_at(chn, t)
            xs.append(x)
            los.append(lo_v)
            his.append(hi_v)
        col = "#fb8c00" if chn.get("apex") is not None else "#1e88e5"   # 삼각수렴 주황 / 채널 파랑
        ax.plot(xs, his, color=col, linewidth=1.4)
        ax.plot(xs, los, color=col, linewidth=1.4)
        for p in chn["touches_lo"]:
            x = win_start + p - lo_i
            if x >= 0:
                ax.plot(x, rows[win_start + p]["l"], "o", color=col, markersize=4)
        for p in chn["touches_hi"]:
            x = win_start + p - lo_i
            if x >= 0:
                ax.plot(x, rows[win_start + p]["h"], "o", color=col, markersize=4)
    if side:
        # 글자를 종가 위/아래로 비켜 둔다 — 같은 높이에 두면 선·접점 표시와 겹친다
        yr = max(r["h"] for r in seg) - min(r["l"] for r in seg)
        y_txt = seg[-1]["c"] + (0.08 if side == "up" else -0.08) * yr
        ax.annotate("BREAK UP" if side == "up" else "BREAK DOWN",
                    xy=(len(seg) - 1, seg[-1]["c"]),
                    xytext=(len(seg) - 18, y_txt),
                    color="#d81b60", fontsize=10, fontweight="bold",
                    arrowprops=dict(arrowstyle="->", color="#d81b60"))
    ticks = list(range(0, len(seg), max(1, len(seg) // 6)))
    ax.set_xticks(ticks)
    ax.set_xticklabels([kst(seg[i]["ts"]) for i in ticks], fontsize=8)
    label = "  triangle" if (chn and chn.get("apex") is not None) else ""
    ax.set_title(f"{sym}/USDT {tf}{label}  (KST)", fontsize=11)
    ax.grid(alpha=0.2)
    ax.set_xlim(-1, len(seg) + 4)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return buf.getvalue()


# ---------------------------------------------------------------- 텔레그램

def tg_available():
    return bool(os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"))


def _tg(method, data=None, files=None):
    import requests
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    try:
        r = requests.post(f"https://api.telegram.org/bot{token}/{method}",
                          data=data, files=files, timeout=30)
    except Exception as e:
        print(f"  [텔레그램] {method} 오류: {str(e)[:80]}")
        return False
    if r.status_code != 200:
        print(f"  [텔레그램] {method} 실패 {r.status_code}: {r.text[:120]}")
        return False
    return True


def tg_text(text):
    if not tg_available():
        return False
    return _tg("sendMessage", data={"chat_id": os.environ["TELEGRAM_CHAT_ID"], "text": text,
                                    "parse_mode": "HTML", "disable_web_page_preview": "true"})


def tg_photo(png, caption):
    if not tg_available():
        return False
    return _tg("sendPhoto", data={"chat_id": os.environ["TELEGRAM_CHAT_ID"], "caption": caption,
                                  "parse_mode": "HTML"},
               files={"photo": ("chart.png", png, "image/png")})


def tg_album(items):
    """items = [(png, caption)]. 텔레그램 앨범은 한 번에 10장까지라 10장씩 나눠 보낸다
    (채널 10장 + 삼각수렴 3장 = 13장 — 한 번에 보내면 뒤 3장이 잘린다)."""
    if not tg_available() or not items:
        return False
    ok = True
    for k in range(0, len(items), 10):
        chunk = items[k:k + 10]
        if len(chunk) == 1:                       # 앨범은 2장 이상이어야 한다
            ok = tg_photo(*chunk[0]) and ok
            continue
        media, files = [], {}
        for i, (png, cap) in enumerate(chunk):
            name = f"p{i}"
            media.append({"type": "photo", "media": f"attach://{name}", "caption": cap[:1000]})
            files[name] = (f"{name}.png", png, "image/png")
        ok = _tg("sendMediaGroup", data={"chat_id": os.environ["TELEGRAM_CHAT_ID"],
                                         "media": json.dumps(media, ensure_ascii=False)},
                 files=files) and ok
    return ok


# ---------------------------------------------------------------- 기록 저장소

class MemStore:
    """기록 저장소가 없을 때(로컬·DB 미설정). 실행 사이에 아무것도 남지 않는다."""
    persistent = False

    def __init__(self):
        self.rows = []

    def seen(self, keys):
        return {r["alert_key"] for r in self.rows if r["alert_key"] in keys}

    def record(self, row):
        self.rows.append(row)
        return True

    def pending(self):
        return []

    def update(self, rid, fields):
        return True


class DBStore:
    """Supabase channel_alerts — 중복 방지 + 이후 수익 기록."""
    persistent = True

    def __init__(self, cli):
        self.cli = cli

    def seen(self, keys):
        if not keys:
            return set()
        res = self.cli.table(TABLE).select("alert_key").in_("alert_key", list(keys)).execute()
        return {r["alert_key"] for r in (res.data or [])}

    def record(self, row):
        try:
            self.cli.table(TABLE).insert(row).execute()
            return True
        except Exception as e:
            print(f"  [기록] 저장 실패: {str(e)[:120]}")
            return False

    def pending(self):
        res = (self.cli.table(TABLE).select("id,symbol,tf,side,bar_ts,close,ret_1,ret_5,ret_20")
               .eq("outcome_done", False).limit(500).execute())
        return res.data or []

    def update(self, rid, fields):
        try:
            self.cli.table(TABLE).update(fields).eq("id", rid).execute()
            return True
        except Exception as e:
            print(f"  [기록] 갱신 실패: {str(e)[:120]}")
            return False


def open_store():
    if not (os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_KEY")):
        print("[기록] Supabase 미설정 — 실행 사이 중복 방지 없이 방금 닫힌 봉만 본다")
        return MemStore()
    try:
        import supabase_client
        cli = supabase_client.get_client("service")
        cli.table(TABLE).select("id").limit(1).execute()
        return DBStore(cli)
    except Exception as e:
        print(f"[기록] {TABLE} 사용 불가({str(e)[:100]}) — 방금 닫힌 봉만 본다")
        return MemStore()


def alert_row(ev, sent):
    c = ev["chn"]
    tri = ev.get("pattern") == "triangle"
    return dict(symbol=ev["symbol"], tf=ev["tf"], side=ev["side"], bar_ts=ev["bar"]["ts"],
                bar_time=datetime.fromtimestamp(ev["bar"]["ts"] / 1000, tz=timezone.utc)
                .strftime("%Y-%m-%d %H:%M"),
                close=ev["bar"]["c"], upper=ev["upper"], lower=ev["lower"],
                width=(ev["upper"] - ev["lower"]) if tri else c["width"],
                depth=ev["depth"], kind=c["kind"], anchor="triangle" if tri else c["anchor"],
                start_ts=c["start_ts"],
                span=c["span"], touches_lo=len(c["touches_lo"]), touches_hi=len(c["touches_hi"]),
                vol_ratio=ev.get("vol_ratio"), alert_key=ev["key"], sent=sent)


def outcome_fields(row, rows):
    """기록된 이탈 봉 이후 1·5·20봉 종가 수익(이탈 방향 부호). 채울 게 없으면 {}."""
    idx = next((i for i, r in enumerate(rows) if r["ts"] == row["bar_ts"]), None)
    if idx is None:
        return {}
    sign = 1.0 if row["side"] == "up" else -1.0
    base = rows[idx]["c"]
    out = {}
    for n in OUTCOME_BARS:
        col = f"ret_{n}"
        if row.get(col) is None and idx + n < len(rows):
            out[col] = round(sign * (rows[idx + n]["c"] / base - 1.0), 6)
    have20 = row.get("ret_20") is not None or "ret_20" in out
    if have20:
        out["outcome_done"] = True
    return out


# ---------------------------------------------------------------- 실행

def run(argv=None, now_ms=None, fetch=fetch_rows, store=None, send=True):
    argv = list(sys.argv[1:] if argv is None else argv)
    dry = "--dry-run" in argv
    if "--test-telegram" in argv:
        ok = tg_text("🔔 채널 알림 봇 연결 확인 — 이 메시지가 보이면 설정 완료입니다.")
        print("텔레그램 설정:", "있음" if tg_available() else "없음(TELEGRAM_BOT_TOKEN/CHAT_ID)",
              "| 전송:", ok)
        return 0
    cfg = load_cfg()
    ch = cfg["channel"]
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    now_utc = datetime.fromtimestamp(now_ms / 1000, tz=timezone.utc)
    want_summary = "--summary" in argv or now_utc.hour == int(cfg.get("summary_hour_utc", 0))
    store = store or (MemStore() if dry else open_store())
    send = send and not dry
    print(f"[채널] {now_utc:%Y-%m-%d %H:%M} UTC · 텔레그램 {'있음' if tg_available() else '없음'} · "
          f"기록 {'Supabase' if store.persistent else '없음'} · 요약 {'예' if want_summary else '아니오'}"
          f"{' · 드라이런' if dry else ''}")

    tri = cfg.get("triangle") or {}
    # 종목·시간대마다 한 번만 받는다 — 채널과 삼각수렴 중 더 긴 쪽 기준
    need = {}
    for w in cfg["watch"]:
        for tf in w["tfs"]:
            k = (w["symbol"], tf)
            need[k] = max(need.get(k, 0), cfg["params"][tf]["lookback"] + 60)
    for w in tri.get("watch", []):
        for tf in w["tfs"]:
            k = (w["symbol"], tf)
            need[k] = max(need.get(k, 0), tri["params"][tf]["lookback"] + 60)
    data = {k: closed_only(fetch(k[0], k[1], lim), k[1], now_ms) for k, lim in need.items()}

    events, summaries, tri_summaries = [], [], []
    for w in cfg["watch"]:
        for tf in w["tfs"]:
            p = cfg["params"][tf]
            rows = data[(w["symbol"], tf)]
            if len(rows) < p["min_span"] + 10:
                print(f"  {w['symbol']} {tf}: 봉 부족({len(rows)}) — 건너뜀")
                summaries.append((w["symbol"], tf, None))
                continue
            only_latest = not store.persistent
            evs = scan(w["symbol"], tf, rows, p, ch, only_latest=only_latest)
            if only_latest:
                close_ms = rows[-1]["ts"] + TF_MS[tf]
                evs = [e for e in evs if now_ms - close_ms <= NONPERSIST_MAX_AGE_MIN * 60_000]
            events.extend(evs)
            if want_summary:
                summaries.append((w["symbol"], tf, current_state(rows, p, ch)))

    # 삼각수렴 — 설정에 적힌 종목·시간대만(2026-11-13: BTC 1h/4h/1d)
    for w in tri.get("watch", []):
        for tf in w["tfs"]:
            p = tri["params"][tf]
            rows = data[(w["symbol"], tf)]
            if len(rows) < p["min_span"] + 10:
                print(f"  △ {w['symbol']} {tf}: 봉 부족({len(rows)}) — 건너뜀")
                tri_summaries.append((w["symbol"], tf, None))
                continue
            only_latest = not store.persistent
            evs = scan_tri(w["symbol"], tf, rows, p, tri, only_latest=only_latest)
            if only_latest:
                close_ms = rows[-1]["ts"] + TF_MS[tf]
                evs = [e for e in evs if now_ms - close_ms <= NONPERSIST_MAX_AGE_MIN * 60_000]
            events.extend(evs)
            if want_summary:
                tri_summaries.append((w["symbol"], tf, current_state_tri(rows, p, tri)))

    # 이탈 알림 — 같은 채널은 한 번만
    seen = store.seen({e["key"] for e in events})
    fresh, used = [], set()
    for e in events:
        if e["key"] in seen or e["key"] in used:
            continue
        used.add(e["key"])
        fresh.append(e)
    for e in fresh:
        is_tri = e.get("pattern") == "triangle"
        txt = alert_text_tri(e, tri.get("history_note", "")) if is_tri else alert_text(e)
        print("  [이탈] " + txt.replace("\n", " | ").replace("<b>", "").replace("</b>", "")
              .replace("<i>", "").replace("</i>", ""))
        if dry:
            continue
        sent = False
        if send and tg_available():
            png = chart_png(e["symbol"], e["tf"], data[(e["symbol"], e["tf"])], e["j"],
                            e["win_start"], e["chn"], e["side"], cfg.get("chart_bars", 120))
            sent = tg_photo(png, txt) or tg_text(txt)
            if not sent:
                continue            # 전송 실패 — 기록하지 않아 다음 실행에서 다시 시도
        store.record(alert_row(e, sent))
    if not fresh:
        print("  [이탈] 없음")

    # 지난 알림의 이후 수익 채우기
    filled = 0
    for row in store.pending():
        rows = data.get((row["symbol"], row["tf"]))
        if not rows:
            continue
        f = outcome_fields(row, rows)
        if f and store.update(row["id"], f):
            filled += 1
    if filled:
        print(f"  [기록] 이후 수익 {filled}건 갱신")

    # 요약
    if want_summary:
        lines = [summary_line(s, tf, st) for s, tf, st in summaries]
        tlines = [summary_line_tri(s, tf, st) for s, tf, st in tri_summaries]
        head = f"📊 <b>채널 현황</b> ({now_utc.astimezone(KST):%m-%d %H:%M} KST)\n"
        body = (head + "\n".join(lines) + ("\n\n" + "\n".join(tlines) if tlines else "")
                + "\n<i>관찰용 — 검증된 매매 신호가 아님</i>")
        print("  [요약] " + " | ".join(lines + tlines))
        if send and tg_available():
            items = []
            for s, tf, st in summaries:
                if st and st.get("chn"):
                    png = chart_png(s, tf, data[(s, tf)], st["j"], st["win_start"], st["chn"],
                                    st.get("side"), cfg.get("chart_bars", 120))
                    items.append((png, summary_line(s, tf, st)))
            for s, tf, st in tri_summaries:
                if st and st.get("chn"):
                    png = chart_png(s, tf, data[(s, tf)], st["j"], st["win_start"], st["chn"],
                                    st.get("side"), cfg.get("chart_bars", 120))
                    items.append((png, summary_line_tri(s, tf, st)))
            tg_text(body)
            if items:
                tg_album(items)
    return 0


if __name__ == "__main__":
    sys.exit(run())
