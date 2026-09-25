"""
elliott_watch.py — BTC 엘리엇 임펄스 카운트 일일 점검 (관찰·브리핑 전용)
(2026-09-23, 사용자 지시 "매일 아침 9시에 진행 현황과 관점 브리핑")

## 무엇을 하나

  `elliott_count.json` 에 **동결된** 카운트를 읽어, 오늘 가격이 그 카운트의 어느 위치에 있는지
  기계적으로 판정한다. 카운트를 새로 세지 않는다.

    1. 동결 레벨 10개까지의 거리(%) 와 이미 돌파된 레벨
    2. 지그재그로 뽑은 현재 스윙 — 동결 5파 고점 갱신 여부, 새 저점 형성 여부
    3. 시나리오 S1/S2/S3 중 아직 살아 있는 것
    4. 5파 내부(6h) 상태 — iii 고점 돌파 / iv 저점 이탈
    5. 일봉 RSI14 와 3파·5파 고점 간 모멘텀 다이버전스

## 왜 동결하나

  엘리엇의 고질병은 가격이 움직일 때마다 라벨을 조용히 바꿔 **항상 맞는 카운트**가 되는 것이다.
  라벨을 파일에 고정하면 재라벨이 커밋으로 남아 사후 조정이 기록에 드러난다. 이 스크립트는
  라벨을 절대 수정하지 않는다 — 판정만 출력하고, 재라벨은 사람이 사유와 함께 커밋한다.

## 하지 않는 것

  · **매매와 완전히 무관하다.** scheduler / paper_executor / exchange / registry / universe 어디서도
    이 파일을 import 하지 않고, 이 파일도 그것들을 import 하지 않는다(test_elliott_watch 가 고정).
  · 신호를 내지 않는다. 검증된 규칙이 아니다 — 레포의 엘리엇 환원 패턴들은 전부 게이트에서 기각됐다.

데이터: 코인베이스 BTC-USD 공개 캔들(키 불필요). OKX 는 이 컨테이너에서 차단돼 있다.

실행: python elliott_watch.py            출력: 콘솔 표 + _elliott_watch.json
"""
import datetime as dt
import json
import subprocess
import sys

COUNT_FILE = "elliott_count.json"
OUT_FILE = "_elliott_watch.json"
PRODUCT = "BTC-USD"
CB = "https://api.exchange.coinbase.com/products/{p}/candles"
ZZ_PCT = 0.05          # 일봉 스윙 임계 — 동결 카운트를 뽑을 때 쓴 값과 같다
ZZ_PCT_6H = 0.018      # 6h 내부 스윙 임계
RSI_N = 14


# ---------------------------------------------------------------- 데이터

def _curl(url, timeout=40):
    """urllib 은 이 환경의 프록시에서 403 이 나므로 curl 을 쓴다."""
    p = subprocess.run(["curl", "-sS", "-m", str(timeout), url],
                       capture_output=True, text=True)
    if p.returncode != 0 or not p.stdout.strip():
        raise RuntimeError(f"fetch 실패: {url} :: {p.stderr.strip()[:200]}")
    return json.loads(p.stdout)


def fetch(granularity, days):
    """[{d,o,h,l,c}] 오름차순. 코인베이스는 [time, low, high, open, close, volume] 순서다."""
    end = dt.datetime.utcnow() + dt.timedelta(days=1)
    start = end - dt.timedelta(days=days)
    rows, cur = {}, start
    step = dt.timedelta(seconds=granularity * 290)
    while cur < end:
        nxt = min(cur + step, end)
        u = (CB.format(p=PRODUCT) + f"?granularity={granularity}"
             f"&start={cur.isoformat()}Z&end={nxt.isoformat()}Z")
        for c in _curl(u):
            rows[c[0]] = c
        cur = nxt
    out = []
    for k in sorted(rows):
        t, lo, hi, op, cl, _v = rows[k]
        stamp = dt.datetime.utcfromtimestamp(t)
        out.append({"d": stamp.strftime("%Y-%m-%d" if granularity >= 86400
                                        else "%Y-%m-%d %H:%M"),
                    "o": op, "h": hi, "l": lo, "c": cl})
    return out


# ---------------------------------------------------------------- 지표

def zigzag(rows, pct):
    """저점에서 시작하는 표준 지그재그. [(kind, idx, price)]"""
    if not rows:
        return []
    piv = [("L", 0, rows[0]["l"])]
    dirn, ext, exti = 1, rows[0]["l"], 0
    for i in range(1, len(rows)):
        r = rows[i]
        if dirn == 1:
            if r["h"] > ext:
                ext, exti = r["h"], i
            elif r["l"] <= ext * (1 - pct):
                piv.append(("H", exti, ext))
                dirn, ext, exti = -1, r["l"], i
        else:
            if r["l"] < ext:
                ext, exti = r["l"], i
            elif r["h"] >= ext * (1 + pct):
                piv.append(("L", exti, ext))
                dirn, ext, exti = 1, r["h"], i
    piv.append(("H" if dirn == 1 else "L", exti, ext))
    return piv


def rsi(closes, n=RSI_N):
    out = [None] * len(closes)
    gain = loss = 0.0
    for i in range(1, len(closes)):
        ch = closes[i] - closes[i - 1]
        up, dn = max(ch, 0.0), max(-ch, 0.0)
        if i <= n:
            gain += up
            loss += dn
            if i == n:
                gain, loss = gain / n, loss / n
                out[i] = 100 - 100 / (1 + gain / (loss or 1e-9))
        else:
            gain = (gain * (n - 1) + up) / n
            loss = (loss * (n - 1) + dn) / n
            out[i] = 100 - 100 / (1 + gain / (loss or 1e-9))
    return out


def rsi_at(daily, rsi_vals, date):
    for i, r in enumerate(daily):
        if r["d"] == date:
            return rsi_vals[i]
    return None


def after_top(rows, top, tol=1e-6):
    """고점을 **찍은 봉 다음부터**.

    고점 당일 봉 자체를 넣으면 안 된다 — 2026-09-21 일봉은 저가 80,837 / 고가 87,397 의
    장대 양봉이라, 그 봉을 포함하면 '고점 이후 저가'가 상승 시작점으로 잡혀 되돌림이
    22% 로 부풀고 6h 의 iv 이탈도 거짓으로 참이 된다.
    """
    for i, r in enumerate(rows):
        if r["h"] >= top - tol:
            return rows[i + 1:]
    return []


# ---------------------------------------------------------------- 판정

def level_table(levels, px):
    """동결 레벨별 거리와 돌파 여부. 판정 규칙은 파일에 적힌 dir 만 본다."""
    out = []
    for lv in levels:
        target, dirn = lv["px"], lv["dir"]
        hit = px > target if dirn == "above" else px < target
        out.append({**lv, "dist_pct": (target / px - 1) * 100, "hit": hit})
    return out


def scenarios_alive(count, px, low_since_top):
    """동결 시나리오 중 아직 살아 있는 것. 가격만 보고 판정한다."""
    w0 = count["waves"][0]["price"]
    top = count["waves"][-1]["price"]
    s = count["scenarios"]
    alive = {}
    alive["S1_wave1_of_new_impulse"] = low_since_top > w0
    lo, hi = s["S2_still_in_wave3"]["pullback_zone"]
    alive["S2_still_in_wave3"] = low_since_top >= lo
    alive["S3_wave_A_of_larger_correction"] = True          # 반증 불가 — 항상 열려 있다
    # 4파 영역(74,888)까지 되밀리면 5파 종료는 사실상 확정이다.
    alive["_impulse_top_confirmed"] = low_since_top < count["waves"][4]["price"]
    return alive


def correction_status(count, px, high_after_A, low_after_A):
    """2파 조정(A-B-C) 진행률. count["correction"] 이 없으면 None — 종전 동작 그대로.

    high/low 는 **A 파 종료 봉 다음부터** 잰다. 고점(9/21) 이후 전체로 재면 A 파 안의 b 반등
    (87,283)이 B 고점으로 잡혀 'B 97.6%' 가 찍힌다 — 실측으로 잡은 결함.
    """
    cor = count.get("correction")
    if not cor:
        return None
    A = cor["A"]
    size = A["start"] - A["end"]
    b_high = max(high_after_A, px)
    low_since_top = low_after_A
    out = {
        "A_start": A["start"], "A_end": A["end"], "A_size": size,
        "B_high": b_high,
        "B_retrace_pct": (b_high - A["end"]) / size * 100,
        "now_retrace_pct": (px - A["end"]) / size * 100,
        "A_end_broken": low_since_top < A["end"],
        "B_min": {k: {"px": v, "hit": b_high >= v} for k, v in cor["B_min_levels"].items()},
        "C_targets": cor["C_targets"],
    }
    return out


def run():
    count = json.load(open(COUNT_FILE))
    daily = fetch(86400, 200)
    six = fetch(21600, 30)
    px = daily[-1]["c"]
    waves = {w["label"]: w for w in count["waves"]}
    top = waves["5"]["price"]
    w0 = waves["0"]["price"]

    top_date = waves["5"]["date"]
    after = after_top(daily, top)
    low_since_top = min((r["l"] for r in after), default=px)
    high_since_top = max((r["h"] for r in after), default=px)

    zz = zigzag([r for r in daily if r["d"] >= waves["0"]["date"]], ZZ_PCT)
    sub = count["sub_wave_5"]
    six_after = after_top(six, top)
    six_high = max((r["h"] for r in six_after), default=None)
    six_low = min((r["l"] for r in six_after), default=None)

    rv = rsi([r["c"] for r in daily])
    div = {"w3": rsi_at(daily, rv, waves["3"]["date"]),
           "w5": rsi_at(daily, rv, waves["5"]["date"]),
           "now": rv[-1]}

    cor = None
    if count.get("correction"):
        a_date = count["correction"]["A"]["end_date"]
        after_a = [r for r in daily if r["d"] > a_date]
        cor = correction_status(count, px,
                                max((r["h"] for r in after_a), default=px),
                                min((r["l"] for r in after_a), default=px))
    res = {
        "correction": cor,
        "asof_utc": dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
        "labeled_on": count["labeled_on"],
        "price": px,
        "top": top, "top_date": top_date,
        "from_top_pct": (px / top - 1) * 100,
        "high_since_top": high_since_top,
        "low_since_top": low_since_top,
        "retrace_of_w1_pct": (top - low_since_top) / (top - w0) * 100,
        "new_high": high_since_top > top,
        "levels": level_table(count["levels"], px),
        "scenarios": scenarios_alive(count, px, low_since_top),
        "sub5": {"iii": sub["iii"], "iv": sub["iv"],
                 "broke_iii": bool(six_high and six_high > sub["iii"]),
                 "broke_iv": bool(six_low and six_low < sub["iv"])},
        "rsi": div,
        "zigzag": [{"kind": k, "price": v} for k, _i, v in zz],
    }

    print(f"[elliott] {res['asof_utc']}Z  BTC {px:,.0f}  "
          f"고점({top_date} {top:,.0f}) 대비 {res['from_top_pct']:+.2f}%")
    print(f"  동결 카운트 {count['labeled_on']} | 고점 이후 저가 {low_since_top:,.0f} "
          f"(1파의 {res['retrace_of_w1_pct']:.1f}% 되돌림)")
    if res["new_high"]:
        print(f"  ** 신고가 {high_since_top:,.0f} — 5파 연장, 동결 고점 갱신 필요 **")
    print("  레벨:")
    for lv in res["levels"]:
        mark = "HIT " if lv["hit"] else "    "
        print(f"    {mark}{lv['px']:>9,.0f} {lv['dir']:<5} {lv['dist_pct']:+6.2f}%  "
              f"{lv['name']} — {lv['means']}")
    print(f"  5파 내부(6h): iii {sub['iii']:,.0f} 돌파={res['sub5']['broke_iii']} / "
          f"iv {sub['iv']:,.0f} 이탈={res['sub5']['broke_iv']}")
    print(f"  RSI14: 3파 {div['w3']:.1f} → 5파 {div['w5']:.1f} → 현재 {div['now']:.1f}")
    if cor:
        flags = " ".join(f"{k}:{'✓' if v['hit'] else '✗'}" for k, v in cor["B_min"].items())
        print(f"  2파 A-B-C: A {cor['A_start']:,.0f}→{cor['A_end']:,.0f} (-{cor['A_size']:,.0f}) | "
              f"B 고점 {cor['B_high']:,.0f} = A 의 {cor['B_retrace_pct']:.1f}% (현재 {cor['now_retrace_pct']:.1f}%) | "
              f"플랫 B 최소 {flags}"
              + ("  ** A 저점 이탈 — 플랫 가설 재계산 **" if cor["A_end_broken"] else ""))
        print("  C 목표: " + " / ".join(f"{k} {v:,.0f}" for k, v in cor["C_targets"].items()))
    print("  살아 있는 시나리오: " +
          ", ".join(k for k, v in res["scenarios"].items()
                    if v and not k.startswith("_")))
    json.dump(res, open(OUT_FILE, "w"), ensure_ascii=False, indent=1)
    print(f"  → {OUT_FILE}")
    return res


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:                                   # noqa: BLE001
        print(f"[elliott] 실패: {exc}", file=sys.stderr)
        sys.exit(1)
