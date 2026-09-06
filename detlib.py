"""
detlib.py — detector 공용 부품 (로더/트리플배리어/evaluate 래퍼).
신규 detector는 detect(rows)만 구현하고 evaluate = make_evaluate(detect)로 노출.
라벨/수익 기준 동결: ±10% 트리플배리어, 20봉, 왕복 수수료 0.2%.
"""
import csv
from datetime import datetime, timezone

RISE_THR, FALL_THR, FEE, LABEL_WINDOW = 0.10, -0.10, 0.002, 20
SYMBOLS = ["BTC", "SOL", "ETH", "BNB", "XRP", "ADA", "AVAX"]
CSV = lambda s, tf: f"data/{s.lower()}_{tf}.csv"

_fetch_failed: set = set()  # 이번 실행에서 이미 실패한 (sym, tf) 캐시


def _auto_fetch(sym, tf):
    """CSV가 없을 때 자동 다운로드 (in-process, okx 우선, 최근 구간만).

    과거 방식(subprocess + since 2021 + binance 우선)은 GitHub Actions 러너에서
    종목당 ~30초씩 낭비돼 전체 실행이 100분을 넘겼다. fetch_data.update_csv 는
    ccxt 인스턴스를 재사용하고 WINDOW_DAYS(1d 900일/4h 130일/1h 40일)만 받는다.
    """
    import os
    key = (sym, tf)
    if key in _fetch_failed:
        return  # 이미 실패 확인 -> 즉시 스킵 (같은 프로세스 내 재시도 방지)
    os.makedirs("data", exist_ok=True)
    try:
        import fetch_data
        _, total_n = fetch_data.update_csv(f"{sym}/USDT", tf, CSV(sym, tf))
    except Exception as e:
        print(f"  [auto-fetch] {sym} {tf} 오류: {str(e)[:60]} - 스킵", flush=True)
        _fetch_failed.add(key)
        return
    if total_n == 0:
        print(f"  [auto-fetch] 실패: {sym} {tf} 모든 거래소 불가 - 스킵", flush=True)
        _fetch_failed.add(key)  # 실패 캐시 -> 이후 같은 심볼 즉시 스킵
        # 파일이 없으면 load_ohlcv 에서 FileNotFoundError -> 호출부 except 로 처리
    else:
        print(f"  [auto-fetch] {sym} {tf} OK ({total_n}봉)", flush=True)


def load_ohlcv(sym, tf="1d"):
    # 1w/1M은 별도 CSV 없이 1d 리샘플 (triple_bottom_1w 등 상위 TF 패턴용).
    # scheduler 신호탐지·paper_executor 청산평가가 같은 경로를 쓴다.
    if tf in ("1w", "1M"):
        return resample_rows(load_ohlcv(sym, "1d"), tf)
    path = CSV(sym, tf)
    if not __import__("os").path.exists(path):
        _auto_fetch(sym, tf)
    rows = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            ts = int(float(r["timestamp"]))
            d = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
            # ts(ms) 병기 — date만으로는 하위 TF에서 봉을 특정할 수 없다(1h는 하루 24행이
            # 같은 date). paper_executor 가 진입봉을 ts로 정확히 찾는 데 쓴다.
            rows.append(dict(ts=ts, date=d, o=float(r["open"]), h=float(r["high"]),
                             l=float(r["low"]), c=float(r["close"]),
                             v=float(r["volume"])))
    return rows


LONG_DIR = "data_long"     # build_data_long.py 산출물(2017~ 일봉, gzip). 연구 전용 — 스케줄러는 읽지 않는다.


def load_ohlcv_long(sym, tf="1d"):
    """
    장기 이력 로더(연구 전용, 2026-09-06). data_long/{sym}_1d.csv.gz 의 오래된 구간 + data/ 의 OKX
    최근 구간을 잇는다 — **겹치는 날짜는 OKX(실거래 소스)를 쓰고**, 장기 소스는 OKX 첫 봉 이전만
    채운다. 둘 중 하나만 있으면 그것을 그대로 돌려준다. 1w/1M 은 잇고 나서 리샘플.
    """
    import gzip, os
    if tf in ("1w", "1M"):
        return resample_rows(load_ohlcv_long(sym, "1d"), tf)
    if tf != "1d":
        return load_ohlcv(sym, tf)
    try:
        recent = load_ohlcv(sym, "1d")
    except FileNotFoundError:
        recent = []
    path = f"{LONG_DIR}/{sym.lower()}_1d.csv.gz"
    if not os.path.exists(path):
        if not recent:
            raise FileNotFoundError(path)
        return recent
    old = []
    with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            ts = int(float(r["timestamp"]))
            d = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
            old.append(dict(ts=ts, date=d, o=float(r["open"]), h=float(r["high"]),
                            l=float(r["low"]), c=float(r["close"]), v=float(r["volume"])))
    old = _sanitize_long(old)
    if not recent:
        return old
    first_recent = recent[0]["date"]
    return [r for r in old if r["date"] < first_recent] + recent


LONG_JUMP = 5.0          # 하루 종가 비율이 이 배수를 넘거나 1/배수 미만이면 티커 재사용으로 본다
LONG_GAP_DAYS = 30       # 봉이 이 일수보다 오래 비면 상장폐지→재상장으로 본다


def _sanitize_long(rows):
    """장기 소스의 티커 재사용·재상장 방어 — 마지막 불연속 지점 **이후**만 남긴다.
    실례: gate 'APT' 2022-01~09 는 다른 토큰($0.08→$0.004), Aptos 는 2022-10 $8 부터."""
    if len(rows) < 2:
        return rows
    from datetime import date as _d
    cut = 0
    for i in range(1, len(rows)):
        a, b = rows[i - 1]["c"], rows[i]["c"]
        gap = _d.fromisoformat(rows[i]["date"]).toordinal() - _d.fromisoformat(rows[i - 1]["date"]).toordinal()
        if a <= 0 or b <= 0 or b / a >= LONG_JUMP or b / a <= 1 / LONG_JUMP or gap > LONG_GAP_DAYS:
            cut = i
    return rows[cut:]


def outcome(rows, si, direction="long"):
    """트리플배리어. direction='short'이면 라벨/수익 반전(하락 선도달=real)."""
    base = rows[si]["c"]
    up, dn = base * (1 + RISE_THR), base * (1 + FALL_THR)
    hi = min(si + LABEL_WINDOW, len(rows) - 1)
    for j in range(si + 1, hi + 1):
        c = rows[j]["c"]
        if direction == "long":
            if c >= up:
                return "real", c / base - 1 - FEE
            if c <= dn:
                return "fake", c / base - 1 - FEE
        else:                                   # short: 하락=수익
            if c <= dn:
                return "real", (base - c) / base - FEE
            if c >= up:
                return "fake", (base - c) / base - FEE
    r = rows[hi]["c"] / base - 1
    return "neutral", (r - FEE) if direction == "long" else (-r - FEE)


def make_evaluate(detect, direction="long"):
    def evaluate(date_from=None, date_to=None, tf="1d"):
        per = {}
        agg = dict(n=0, real=0, fake=0, neutral=0)
        rets = []
        for sym in SYMBOLS:
            try:
                rows = load_ohlcv(sym, tf)
            except FileNotFoundError:
                continue
            cc = dict(n=0, real=0, fake=0, neutral=0)
            for si in detect(rows):
                d = rows[si]["date"]
                if date_from and d < date_from:
                    continue
                if date_to and d > date_to:
                    continue
                lab, ret = outcome(rows, si, direction)
                cc["n"] += 1; cc[lab] += 1; rets.append(ret)
            per[sym] = cc
            for k in agg:
                agg[k] += cc[k]
        return dict(agg=agg, per=per, rets=rets)
    return evaluate


def resample_rows(rows, rule):
    """
    1d rows -> 주봉("1w", ISO 주) / 월봉("1M", YYYY-MM) 리샘플.
    o=구간 첫 시가, h=최고, l=최저, c=구간 마지막 종가, v=합계, date=구간 첫 날짜.
    멀티TF 패턴 카운팅(triple_bottom 등)용 — 상위 TF CSV를 따로 수집하지 않는다.
    """
    from datetime import date as _date

    def key(d):
        y, m, dd = map(int, d.split("-"))
        if rule == "1M":
            return f"{y:04d}-{m:02d}"
        iy, iw, _ = _date(y, m, dd).isocalendar()
        return f"{iy:04d}-W{iw:02d}"

    out, cur, cur_key = [], None, None
    for r in rows:
        k = key(r["date"])
        if k != cur_key:
            if cur:
                out.append(cur)
            cur = dict(ts=r.get("ts"), date=r["date"], o=r["o"], h=r["h"],
                       l=r["l"], c=r["c"], v=r["v"])
            cur_key = k
        else:
            cur["h"] = max(cur["h"], r["h"])
            cur["l"] = min(cur["l"], r["l"])
            cur["c"] = r["c"]
            cur["v"] += r["v"]
    if cur:
        out.append(cur)
    return out
