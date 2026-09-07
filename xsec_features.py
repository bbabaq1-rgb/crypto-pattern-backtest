"""
xsec_features.py — 횡단면 특성 연구용 **인과** 피처·결과 (2026-09-07 사전 등록, 사용자 지시).

질문: "어떤 조건(특성)에 있던 코인이 이후 더 많이·빠르게 올랐는가" — 패턴이 아니라 코인 상태 변수의 횡단면 예측력.
여기서는 변수 정의만 둔다(판정은 validate_xsec_chars.py). 모든 피처는 봉 i 까지의 정보만 쓴다(테스트가 인과성 고정).
실거래 코드 무관 — scheduler/paper_executor 는 이 모듈을 읽지 않는다.

FAMILY = (키, 그룹, 사전 부호, 설명). 부호는 '피처가 클수록 20봉 선행수익이 높다'가 '+', 반대가 '-', '?' 는 양측
(train 부호를 OOS 에 요구). 결과를 본 뒤 부호·정의·가족 구성을 바꾸지 않는다.

중복 제외(사전 기록): 치코우(후행스팬 vs 26봉 전 가격) ≡ 26봉 모멘텀 → mom_1m 과 중복이라 제외 ·
기준선 대비 거리 ≡ 이평 거리 계열과 중복 → 제외 · MACD/OBV 다이버전스는 RSI 다이버전스와 중복 → 제외 ·
히든 다이버전스 제외 · **rs_btc_1m(21봉 수익 − BTC 21봉 수익) 은 제외** — 횡단면에서 BTC 수익률은 같은 날 모든 코인에
같은 상수라 mom_1m 과 순위가 완전히 같다(정의 오류, 커밋 전 로컬 스모크 실행에서 확인해 제거 — 사전 등록 기록에 명시).
"""
import math

# ── 동결 파라미터 ─────────────────────────────────────────────────────────────────────────────
TENKAN, KIJUN, SENKOU = 9, 26, 52
RSI_N = 14
DIV_PH = 3          # 스윙 확정 좌우 폭(봉) — 확정 지연 = DIV_PH
DIV_LOOK = 60       # 다이버전스 탐색 범위(봉)
DIV_RECENT = 20     # 두 번째 피벗이 이 안에 있어야 '현재 상태'
DIV_MAXGAP = 40     # 두 피벗 최대 간격
FWD_PRIMARY = 20
FWD_SECOND = 60
HIT_WINDOW, HIT_THR = 40, 0.20      # '빠르게 올랐다': 40봉 내 고가 +20% 도달
ANN = math.sqrt(365)

FAMILY = [
    # 모멘텀·반전
    ("ret_1w",           "momentum", "?", "5봉 수익률(단기 반전 vs 주간 모멘텀)"),
    ("mom_1m",           "momentum", "+", "21봉 수익률"),
    ("mom_3m",           "momentum", "+", "63봉 수익률, 최근 5봉 제외"),
    ("mom_6m",           "momentum", "?", "126봉 수익률, 최근 21봉 제외"),
    ("mom_12m",          "momentum", "?", "252봉 수익률, 최근 21봉 제외"),
    # 이동평균 위치 (사용자 지정 60/120/180)
    ("dist_ma60",        "ma",       "?", "종가/MA60 − 1"),
    ("dist_ma120",       "ma",       "?", "종가/MA120 − 1"),
    ("dist_ma180",       "ma",       "?", "종가/MA180 − 1"),
    ("ma_align",         "ma",       "+", "정배열 점수 0~3: 종가>MA60, MA60>MA120, MA120>MA180"),
    ("ma180_slope",      "ma",       "+", "MA180 의 20봉 기울기"),
    # 일목균형표 (9/26/52, 사용자 지정)
    ("ichi_cloud_pos",   "ichimoku", "+", "종가 vs 구름(현재 봉에 그려진 선행스팬): 위 +1 / 안 0 / 아래 −1"),
    ("ichi_tk",          "ichimoku", "+", "(전환선 − 기준선)/종가"),
    ("ichi_future_cloud","ichimoku", "+", "미래 구름 색: 선행스팬A_now − B_now 부호"),
    ("ichi_cloud_thick", "ichimoku", "?", "|선행A − 선행B|/종가 (현재 봉 구름 두께)"),
    # 오실레이터·다이버전스 (사용자 지정, RSI 하나만)
    ("rsi14",            "osc",      "?", "RSI14 (Wilder)"),
    ("rsi_div",          "osc",      "+", "RSI 정규 다이버전스 상태: 강세 +1 / 없음 0 / 약세 −1 (확정 피벗만)"),
    # 거래량·유동성
    ("turnover_30d",     "volume",   "?", "log 30봉 평균 거래대금"),
    ("vol_ratio_30_90",  "volume",   "+", "거래대금 30봉/90봉 평균 비"),
    ("vol_shock_5_30",   "volume",   "?", "거래대금 5봉/30봉 평균 비"),
    # 변동성
    ("rvol20",           "vol",      "-", "20봉 실현변동성(연율)"),
    ("rvol_ratio_20_60", "vol",      "?", "실현변동성 20봉/60봉 비(수축·확장)"),
    # 가격 위치
    ("dd_1y",            "range",    "?", "종가/252봉 고가 − 1"),
    ("range_pos_20",     "range",    "?", "(종가 − 20봉 저가)/(20봉 고가 − 20봉 저가)"),
    # 상대·시장
    ("beta_btc_60",      "relative", "?", "60봉 일수익 BTC 베타"),
]
KEYS = [f[0] for f in FAMILY]
SIGN = {f[0]: f[2] for f in FAMILY}
GROUP = {f[0]: f[1] for f in FAMILY}


def rsi_series(c, n=RSI_N):
    out = [None] * len(c)
    if len(c) <= n:
        return out
    g = l = 0.0
    for k in range(1, n + 1):
        d = c[k] - c[k - 1]; g += max(d, 0.0); l += max(-d, 0.0)
    ag, al = g / n, l / n
    out[n] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    for k in range(n + 1, len(c)):
        d = c[k] - c[k - 1]
        ag = (ag * (n - 1) + max(d, 0.0)) / n
        al = (al * (n - 1) + max(-d, 0.0)) / n
        out[k] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def _mean(xs):
    return sum(xs) / len(xs)


def _std(xs):
    if len(xs) < 2:
        return None
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


class FeatureSeries:
    """한 코인의 봉 배열에서 봉 i 의 피처(dict)와 결과(dict)를 낸다. btc_rows 는 상대·베타 피처용(날짜 정렬)."""

    def __init__(self, rows, btc_rows=None):
        self.rows = rows
        self.c = [r["c"] for r in rows]
        self.h = [r["h"] for r in rows]
        self.l = [r["l"] for r in rows]
        self.dv = [r["c"] * r["v"] for r in rows]
        self.dates = [r["date"] for r in rows]
        self.rsi = rsi_series(self.c)
        self.lr = [None] + [math.log(self.c[k] / self.c[k - 1]) if self.c[k - 1] > 0 and self.c[k] > 0 else 0.0 for k in range(1, len(rows))]
        self.btc_c = {r["date"]: r["c"] for r in (btc_rows or [])}
        self.btc_idx = {r["date"]: k for k, r in enumerate(btc_rows or [])}
        self.btc_rows = btc_rows or []
        self.btc_lr = [None] + [math.log(self.btc_rows[k]["c"] / self.btc_rows[k - 1]["c"]) for k in range(1, len(self.btc_rows))]

    # ── 보조 ──
    def _sma(self, i, n):
        if i + 1 < n:
            return None
        return _mean(self.c[i - n + 1:i + 1])

    def _mid(self, i, n):          # 일목 중값: (n봉 최고가 + n봉 최저가)/2, 봉 i 포함
        if i + 1 < n:
            return None
        return (max(self.h[i - n + 1:i + 1]) + min(self.l[i - n + 1:i + 1])) / 2

    def _dvmean(self, i, n):
        if i + 1 < n:
            return None
        return _mean(self.dv[i - n + 1:i + 1])

    def _rvol(self, i, n):
        if i < n:
            return None
        s = _std(self.lr[i - n + 1:i + 1])
        return None if s is None else s * ANN

    def _pivots(self, arr, lo, hi, kind):
        """[lo, hi] 안의 확정 스윙(양쪽 DIV_PH 봉). kind='low' 는 저점, 'high' 는 고점. 확정 = j+DIV_PH <= hi."""
        out = []
        for j in range(max(lo, DIV_PH), hi - DIV_PH + 1):
            w = arr[j - DIV_PH:j + DIV_PH + 1]
            if (kind == "low" and arr[j] == min(w)) or (kind == "high" and arr[j] == max(w)):
                if not out or j - out[-1] > DIV_PH:      # 같은 값 연속 방지
                    out.append(j)
        return out

    def rsi_divergence(self, i):
        """봉 i 에서 알 수 있는 정규 다이버전스 상태. 강세 +1 / 약세 −1 / 없음·둘 다 0."""
        if i < DIV_LOOK or self.rsi[i] is None:
            return None
        lo = i - DIV_LOOK
        bull = bear = 0
        lows = [j for j in self._pivots(self.l, lo, i, "low") if self.rsi[j] is not None]
        if len(lows) >= 2:
            a, b = lows[-2], lows[-1]
            if i - b <= DIV_RECENT and b - a <= DIV_MAXGAP and self.l[b] < self.l[a] and self.rsi[b] > self.rsi[a]:
                bull = 1
        highs = [j for j in self._pivots(self.h, lo, i, "high") if self.rsi[j] is not None]
        if len(highs) >= 2:
            a, b = highs[-2], highs[-1]
            if i - b <= DIV_RECENT and b - a <= DIV_MAXGAP and self.h[b] > self.h[a] and self.rsi[b] < self.rsi[a]:
                bear = 1
        return bull - bear

    def _beta(self, i, n=60):
        k = self.btc_idx.get(self.dates[i])
        if k is None or i < n or k < n:
            return None
        xs, ys = [], []
        for t in range(n):
            d = self.dates[i - t]
            kb = self.btc_idx.get(d)
            if kb is None or kb < 1 or self.lr[i - t] is None or self.btc_lr[kb] is None:
                continue
            xs.append(self.btc_lr[kb]); ys.append(self.lr[i - t])
        if len(xs) < 50:
            return None
        mx, my = _mean(xs), _mean(ys)
        vx = sum((x - mx) ** 2 for x in xs)
        if vx <= 0:
            return None
        return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / vx

    # ── 피처 ──
    def at(self, i):
        c, h, l = self.c, self.h, self.l
        f = {k: None for k in KEYS}
        ci = c[i]
        if ci <= 0:
            return f
        def ret(a, b):                     # c[i-a]/c[i-b] - 1  (a < b)
            return None if i < b or c[i - b] <= 0 else c[i - a] / c[i - b] - 1
        f["ret_1w"] = ret(0, 5)
        f["mom_1m"] = ret(0, 21)
        f["mom_3m"] = ret(5, 63)
        f["mom_6m"] = ret(21, 126)
        f["mom_12m"] = ret(21, 252)
        m60, m120, m180 = self._sma(i, 60), self._sma(i, 120), self._sma(i, 180)
        f["dist_ma60"] = None if m60 is None else ci / m60 - 1
        f["dist_ma120"] = None if m120 is None else ci / m120 - 1
        f["dist_ma180"] = None if m180 is None else ci / m180 - 1
        if m180 is not None:
            f["ma_align"] = float((ci > m60) + (m60 > m120) + (m120 > m180))
            m180p = self._sma(i - 20, 180)
            f["ma180_slope"] = None if m180p is None else m180 / m180p - 1
        # 일목: 현재 봉에 그려진 구름은 26봉 전에 계산된 선행스팬
        tk, kj = self._mid(i, TENKAN), self._mid(i, KIJUN)
        if kj is not None:
            f["ichi_tk"] = (tk - kj) / ci
            b_now = self._mid(i, SENKOU)
            if b_now is not None:
                a_now = (tk + kj) / 2
                f["ichi_future_cloud"] = float((a_now > b_now) - (a_now < b_now))
        j = i - KIJUN
        if j >= 0:
            tkj, kjj, bj = self._mid(j, TENKAN), self._mid(j, KIJUN), self._mid(j, SENKOU)
            if bj is not None:
                aj = (tkj + kjj) / 2
                top, bot = max(aj, bj), min(aj, bj)
                f["ichi_cloud_pos"] = 1.0 if ci > top else (-1.0 if ci < bot else 0.0)
                f["ichi_cloud_thick"] = (top - bot) / ci
        f["rsi14"] = self.rsi[i]
        d = self.rsi_divergence(i)
        f["rsi_div"] = None if d is None else float(d)
        dv30, dv90, dv5 = self._dvmean(i, 30), self._dvmean(i, 90), self._dvmean(i, 5)
        f["turnover_30d"] = None if not dv30 else math.log(dv30)
        f["vol_ratio_30_90"] = None if (dv30 is None or not dv90) else dv30 / dv90
        f["vol_shock_5_30"] = None if (dv5 is None or not dv30) else dv5 / dv30
        rv20, rv60 = self._rvol(i, 20), self._rvol(i, 60)
        f["rvol20"] = rv20
        f["rvol_ratio_20_60"] = None if (rv20 is None or not rv60) else rv20 / rv60
        if i >= 251:
            f["dd_1y"] = ci / max(h[i - 251:i + 1]) - 1
        if i >= 19:
            hi20, lo20 = max(h[i - 19:i + 1]), min(l[i - 19:i + 1])
            f["range_pos_20"] = None if hi20 <= lo20 else (ci - lo20) / (hi20 - lo20)
        f["beta_btc_60"] = self._beta(i)
        return f

    # ── 결과 ──
    def outcome(self, i):
        c, h, n = self.c, self.h, len(self.c)
        o = dict(fwd20=None, fwd60=None, hit20_40=None)
        if c[i] <= 0:
            return o
        if i + FWD_PRIMARY < n:
            o["fwd20"] = c[i + FWD_PRIMARY] / c[i] - 1
        if i + FWD_SECOND < n:
            o["fwd60"] = c[i + FWD_SECOND] / c[i] - 1
        if i + HIT_WINDOW < n:
            o["hit20_40"] = 1.0 if max(h[i + 1:i + HIT_WINDOW + 1]) >= c[i] * (1 + HIT_THR) else 0.0
        return o


def month_end_indices(rows):
    """{ 'YYYY-MM': 그 달 마지막 봉 인덱스 }"""
    out = {}
    for k, r in enumerate(rows):
        out[r["date"][:7]] = k
    return out


# ── 에피소드 프로필 연구 추가 변수 (2026-09-07 사전 등록) — FAMILY(24) 는 동결, 여기는 별도 목록 ──────────
BB_N, BB_K, BB_SQZ_WIN = 20, 2.0, 120
EXTRA = [
    ("bb_pctb",           "bollinger", "?", "(종가 − 하단)/(상단 − 하단), 20봉·2σ"),
    ("bb_width",          "bollinger", "?", "(상단 − 하단)/중심선"),
    ("bb_squeeze",        "bollinger", "?", "현재 폭 / 최근 120봉 최소 폭 — 1 에 가까울수록 수축"),
    ("adx14",             "trend",     "?", "Wilder ADX14"),
    ("ath_dd",            "range",     "?", "종가/이력 내 최고 종가 − 1"),
    ("days_since_ath",    "range",     "?", "최고 종가 이후 경과 봉"),
    ("age_bars",          "meta",      "?", "이력 길이(봉) — 신규 상장 vs 오래된 코인"),
    ("corr_btc_60",       "relative",  "?", "60봉 BTC 일수익 상관"),
    ("max_dd_1y",         "range",     "?", "최근 252봉 내 최대 낙폭(음수)"),
    ("up_days_20",        "momentum",  "?", "최근 20봉 중 양봉 비율"),
    ("days_above_ma180",  "ma",        "?", "종가가 MA180 위(양)/아래(음)에 머문 연속 봉 수, ±120 상한"),
]
EXTRA_KEYS = [f[0] for f in EXTRA]
EXTRA_SIGN = {f[0]: f[2] for f in EXTRA}
EXTRA_GROUP = {f[0]: f[1] for f in EXTRA}
ALL_KEYS = KEYS + EXTRA_KEYS
ALL_SIGN = {**SIGN, **EXTRA_SIGN}
ALL_GROUP = {**GROUP, **EXTRA_GROUP}


def adx_series(rows, period=14):
    """Wilder ADX — regime_axis.adx_series 와 같은 정의(인과: 확정 인덱스에만 값)."""
    n = len(rows)
    out = [None] * n
    if n < period * 2 + 2:
        return out
    tr, pdm, ndm = [], [], []
    for i in range(1, n):
        h, l = rows[i]["h"], rows[i]["l"]
        ph, pl, pc = rows[i - 1]["h"], rows[i - 1]["l"], rows[i - 1]["c"]
        tr.append(max(h - l, abs(h - pc), abs(l - pc)))
        up, dn = h - ph, pl - l
        pdm.append(up if (up > dn and up > 0) else 0.0)
        ndm.append(dn if (dn > up and dn > 0) else 0.0)
    atr, ap, an = sum(tr[:period]), sum(pdm[:period]), sum(ndm[:period])
    dx_list, adx_val = [], None
    for k in range(period, len(tr)):
        atr = atr - atr / period + tr[k]
        ap = ap - ap / period + pdm[k]
        an = an - an / period + ndm[k]
        if atr <= 0:
            dx = 0.0
        else:
            pdi, ndi = 100 * ap / atr, 100 * an / atr
            tot = pdi + ndi
            dx = 100 * abs(pdi - ndi) / tot if tot > 0 else 0.0
        dx_list.append(dx)
        if len(dx_list) == period:
            adx_val = sum(dx_list) / period
        elif len(dx_list) > period:
            adx_val = (adx_val * (period - 1) + dx) / period
        if adx_val is not None:
            out[k + 1] = adx_val
    return out


def _bb(c, i, n=BB_N, k=BB_K):
    if i + 1 < n:
        return None
    seg = c[i - n + 1:i + 1]
    m = sum(seg) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in seg) / n)
    return m, m + k * sd, m - k * sd


def extra_at(fs, i):
    """FeatureSeries fs 의 봉 i 에서 EXTRA 변수(인과)."""
    c, h, l = fs.c, fs.h, fs.l
    f = {k: None for k in EXTRA_KEYS}
    ci = c[i]
    if ci <= 0:
        return f
    bb = _bb(c, i)
    if bb is not None:
        m, up, dn = bb
        if up > dn:
            f["bb_pctb"] = (ci - dn) / (up - dn)
            f["bb_width"] = (up - dn) / m if m > 0 else None
            if i + 1 >= BB_N + BB_SQZ_WIN - 1 and f["bb_width"] is not None:
                ws = []
                for j in range(i - BB_SQZ_WIN + 1, i + 1):
                    b2 = _bb(c, j)
                    if b2 and b2[0] > 0:
                        ws.append((b2[1] - b2[2]) / b2[0])
                if ws and min(ws) > 0:
                    f["bb_squeeze"] = f["bb_width"] / min(ws)
    if not hasattr(fs, "_adx"):
        fs._adx = adx_series(fs.rows)
    f["adx14"] = fs._adx[i]
    seg = c[:i + 1]
    j_ath = max(range(i + 1), key=lambda j: seg[j])
    f["ath_dd"] = ci / seg[j_ath] - 1 if seg[j_ath] > 0 else None
    f["days_since_ath"] = float(i - j_ath)
    f["age_bars"] = float(i + 1)
    if i >= 251:
        peak, mdd = 0.0, 0.0
        for j in range(i - 251, i + 1):
            peak = max(peak, h[j]); mdd = min(mdd, c[j] / peak - 1 if peak > 0 else 0.0)
        f["max_dd_1y"] = mdd
    if i >= 20:
        f["up_days_20"] = sum(1 for j in range(i - 19, i + 1) if c[j] > c[j - 1]) / 20
    m180 = fs._sma(i, 180)
    if m180 is not None:
        above = ci > m180
        cnt = 0
        for j in range(i, -1, -1):
            mj = fs._sma(j, 180)
            if mj is None or (c[j] > mj) != above or cnt >= 120:
                break
            cnt += 1
        f["days_above_ma180"] = float(cnt if above else -cnt)
    # BTC 상관 60
    k = fs.btc_idx.get(fs.dates[i])
    if k is not None and i >= 60 and k >= 60:
        xs, ys = [], []
        for t in range(60):
            kb = fs.btc_idx.get(fs.dates[i - t])
            if kb is None or kb < 1 or fs.lr[i - t] is None:
                continue
            xs.append(fs.btc_lr[kb]); ys.append(fs.lr[i - t])
        if len(xs) >= 50:
            mx, my = _mean(xs), _mean(ys)
            sxx = sum((x - mx) ** 2 for x in xs); syy = sum((y - my) ** 2 for y in ys)
            if sxx > 0 and syy > 0:
                f["corr_btc_60"] = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / math.sqrt(sxx * syy)
    return f


def all_at(fs, i):
    out = fs.at(i)
    out.update(extra_at(fs, i))
    return out
