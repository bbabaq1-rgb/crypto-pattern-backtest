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


def triangle_status(count, bars_6h):
    """네 번째 시나리오(1파의 5파 안 4파 삼각수렴) 판정. 파일에 triangle 블록이 없으면 None.

    무효: 감시 시작 이후 6시간봉 **종가**가 kill_close_below 아래.
    경고: D 가 D_max 를 넘음(삼각형 윗선이 안 내려옴) — 단 confirm_above 돌파면 확인으로 본다.
    확인: confirm_above 상향 돌파 = 삼각형 뒤 5파 스러스트 시작.
    가격은 전부 파일 값이다.
    """
    sc = count.get("scenarios", {})
    key = next((k for k, v in sc.items() if isinstance(v, dict) and v.get("triangle")), None)
    if not key:
        return None
    t = sc[key]["triangle"]
    bars = [b for b in bars_6h if b["d"] >= t["watch_from"]]
    killed = any(b["c"] < t["kill_close_below"] for b in bars)
    hi = max((b["h"] for b in bars), default=None)
    lo = min((b["l"] for b in bars), default=None)
    confirmed = hi is not None and hi > t["confirm_above"]
    d_over = hi is not None and hi > t["D_max"] and not confirmed
    return {
        "key": key, "alive": not killed,
        "killed": killed, "confirmed": confirmed, "d_over": d_over,
        "new_low_below_C": lo is not None and lo < t["C_end"],
        "low": lo, "high": hi, "t": t,
    }


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


def outlook_status(count, rows_since):
    """확률표(count["outlook"]) + 표 기준일 이후 트리거 발동 여부. 없으면 None — 종전 동작.

    확률은 파일 값을 그대로 옮길 뿐이다. 트리거가 발동해도 코드는 확률을 바꾸지 않고
    '재평가 필요'만 표시한다 — 변경은 revisions 에 사유와 함께 사람이 기록한다.
    rows_since 는 표 기준일(as_of) **당일 포함** 이후의 봉이다.
    """
    ol = count.get("outlook")
    if not ol:
        return None
    sc = ol["scenarios_pct"]
    sh = ol["wave2_shape_pct_within_S1"]
    s1 = sc["S1"] / 100.0
    abc_in = sh["zigzag_abc"] + sh["flat_abc"]
    lo = min((r["l"] for r in rows_since), default=None)
    hi = max((r["h"] for r in rows_since), default=None)
    trig = []
    for t in ol["triggers"]:
        if t["dir"] == "below":
            fired = lo is not None and lo < t["px"]
        else:
            fired = hi is not None and hi > t["px"]
        trig.append(dict(t, fired=fired))
    return {
        "as_of": ol["as_of"], "basis_px": ol["basis_px"],
        "scenarios": sc, "shape": sh,
        "abc_within_S1": abc_in, "wxy_within_S1": sh["wxy"],
        "abc_uncond": abc_in * s1, "wxy_uncond": sh["wxy"] * s1,
        "triggers": trig,
        "reassess": any(t["fired"] for t in trig),
        "discriminator": ol.get("wxy_vs_abc_discriminator", ""),
        "scenario_names": {k: count.get("scenarios", {}).get(full, {}).get("label", k)
                           for k, full in ol.get("scenario_keys", {}).items()},
        "shape_names": ol.get("shape_labels", {}),
    }


def resolve_question(q, bars):
    """채점 질문 하나를 봉 목록(as_of 당일 포함 이후, 6h 오름차순)으로 판정한다. 파일은 안 건드린다.

    반환: {"state": open|resolved|void|ambiguous, "outcome": ..., "note": ...}
    같은 봉이 두 가격을 다 건드리면 순서를 알 수 없으니 'ambiguous' — 사람이 1시간봉으로 확인한다.
    """
    r = q["rule"]
    void_lo = q.get("void_if_below")
    if r["type"] == "first_touch":
        for b in bars:
            if void_lo is not None and b["l"] < void_lo:
                return {"state": "void", "outcome": None, "note": f"{b['d']} 무효선 이탈"}
            hit_up, hit_dn = b["h"] > r["up"], b["l"] < r["down"]
            if hit_up and hit_dn:
                return {"state": "ambiguous", "outcome": None, "note": f"{b['d']} 한 봉이 양쪽을 다 건드림"}
            if hit_up:
                return {"state": "resolved", "outcome": "up", "note": b["d"]}
            if hit_dn:
                return {"state": "resolved", "outcome": "down", "note": b["d"]}
        return {"state": "open", "outcome": None, "note": ""}
    if r["type"] == "wxy_after_c":
        top, zone, xf = r["top"], r["c_zone"], r["x_frac"]
        low, armed = None, False
        for b in bars:
            if void_lo is not None and b["l"] < void_lo:
                return {"state": "void", "outcome": None, "note": f"{b['d']} 무효선 이탈"}
            if low is None:                                   # ① C 영역 진입 전
                if b["h"] > top:
                    return {"state": "void", "outcome": None, "note": f"{b['d']} C 영역 전에 고점 돌파 — 2파 아님"}
                if b["l"] < zone:
                    low = b["l"]
                continue
            if not armed:                                     # ② X 반등 대기, 최저가 갱신
                if b["h"] > top:
                    return {"state": "resolved", "outcome": "abc", "note": f"{b['d']} 반등이 곧장 고점 돌파"}
                if b["h"] >= low + xf * (top - low) and b["l"] >= low:
                    armed = True
                    continue
                low = min(low, b["l"])
                continue
            hit_up, hit_dn = b["h"] > top, b["l"] < low       # ③ 새 저점 vs 고점 돌파
            if hit_up and hit_dn:
                return {"state": "ambiguous", "outcome": None, "note": f"{b['d']} 한 봉이 양쪽을 다 건드림"}
            if hit_dn:
                return {"state": "resolved", "outcome": "wxy", "note": f"{b['d']} X 반등 뒤 새 저점 (L={low:,.0f})"}
            if hit_up:
                return {"state": "resolved", "outcome": "abc", "note": f"{b['d']} X 반등이 고점 돌파 (L={low:,.0f})"}
        stage = "C 영역 대기" if low is None else ("X 반등 대기" if not armed else "새 저점 vs 고점 돌파 대기")
        return {"state": "open", "outcome": None,
                "note": stage + ("" if low is None else f" (현재 L={low:,.0f})")}
    raise ValueError(f"알 수 없는 규칙 {r['type']}")


def brier(p, happened):
    return (p - (1.0 if happened else 0.0)) ** 2


def scorebook_status(count, bars_6h):
    """채점 장부. 파일에 이미 resolved 로 기록된 질문은 그 결과를 쓰고, open 은 봉으로 판정해 본다."""
    sb = count.get("scorebook")
    if not sb:
        return None
    rows, tot = [], {"forecast": 0.0, "random_walk": 0.0, "coin": 0.0, "n": 0}
    for q in sb["questions"]:
        if q.get("status") == "resolved":
            st = {"state": "resolved", "outcome": q["outcome"], "note": q.get("resolved_on", ""), "recorded": True}
        else:
            st = resolve_question(q, [b for b in bars_6h if b["d"] >= q["as_of"]])
            st["recorded"] = False
        row = {"id": q["id"], "question": q["question"], "forecast": q["forecast"],
               "baselines": q["baselines"], **st}
        if st["state"] == "resolved":
            hap = st["outcome"] == q["event"]
            row["brier"] = {"forecast": brier(q["forecast"], hap),
                            **{k: brier(v, hap) for k, v in q["baselines"].items()}}
            if st["recorded"]:
                for k in ("forecast", "random_walk", "coin"):
                    tot[k] += row["brier"][k]
                tot["n"] += 1
        rows.append(row)
    return {"rows": rows, "cumulative": tot}


def c_count_status(cc, bars_1h, px):
    """지그재그 C 내부 5파 진행. cc = correction.zigzag_update.C_count (없으면 None).

    bars_1h 는 'YYYY-MM-DD HH:MM' 오름차순 1시간봉. ii 시각 이후 봉만 본다.
    판정만 한다 — 라벨(i, ii 가격)은 파일에만 있다.
    """
    if not cc:
        return None
    start, i_px, ii = cc["start"]["px"], cc["i"]["px"], cc["ii"]
    i_len = start - i_px
    after = [b for b in bars_1h if b["d"] > ii["ts"]]
    if not after:
        return None
    k = min(range(len(after)), key=lambda j: after[j]["l"])
    iii_low = after[k]["l"]
    post = after[k + 1:]
    bounce_hi = max([b["h"] for b in post] + [px]) if post else px
    return {
        "i_len": i_len,
        "ii_retrace_pct": (ii["px"] - i_px) / i_len * 100,
        "iii_low": iii_low, "iii_low_ts": after[k]["d"],
        "iii_len_x_i": (ii["px"] - iii_low) / i_len,
        "iii_targets": {r: ii["px"] - r * i_len for r in cc["iii_ratios_of_i"]},
        "invalid": max(b["h"] for b in after) > ii["px"],
        "bounce_hi": bounce_hi,
        "above_i_low": bounce_hi > i_px,
        "passed_i_low": iii_low < i_px,
    }


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
    ols = None
    if count.get("outlook"):
        ols = outlook_status(count, [r for r in daily if r["d"] >= count["outlook"]["as_of"]])
    sbs = None
    if count.get("scorebook"):
        first = min(q["as_of"] for q in count["scorebook"]["questions"])
        days = (dt.datetime.utcnow() - dt.datetime.strptime(first, "%Y-%m-%d")).days + 3
        six_sb = six if days <= 28 else fetch(21600, days)
        sbs = scorebook_status(count, six_sb)
    tri = triangle_status(count, six)
    ccs = None
    zz_up = (count.get("correction") or {}).get("zigzag_update_2026_09_28") or {}
    if zz_up.get("C_count"):
        ccs = c_count_status(zz_up["C_count"], fetch(3600, 6), px)
    res = {
        "c_count": ccs,
        "scorebook": sbs,
        "outlook": ols,
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
        "scenarios": dict(scenarios_alive(count, px, low_since_top),
                          **({tri["key"]: tri["alive"]} if tri else {})),
        "triangle": {k: v for k, v in tri.items() if k != "t"} if tri else None,
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
        print(f"  2파 조정 A-B-C: A 하락 {cor['A_start']:,.0f}→{cor['A_end']:,.0f} (-{cor['A_size']:,.0f}) | "
              f"B 고점 {cor['B_high']:,.0f} = A 의 {cor['B_retrace_pct']:.1f}% (현재 {cor['now_retrace_pct']:.1f}%) | "
              f"플랫 B 최소 {flags}"
              + (("  ** A 저점 이탈 — 플랫 폐기, 지그재그로 재계산됨 **" if count["correction"].get("zigzag_update_2026_09_28")
                 else "  ** A 저점 이탈 — 플랫 가설 재계산 **") if cor["A_end_broken"] else ""))
        zz_up = count["correction"].get("zigzag_update_2026_09_28")
        if zz_up:
            print("  C 목표 (지그재그 — 플랫 폐기, B 고점 기준):")
            for k, v in zz_up["zigzag_C_targets_from_B_85250"].items():
                print(f"    {v:>9,.0f}  C = A 의 {k.split('=')[1].rstrip('A')}배")
            print(f"    확인: {zz_up['confirm']} | 부정: {zz_up['deny']}")
            cc = zz_up.get("C_count")
            if ccs and cc:
                t = ccs["iii_targets"]
                print(f"  C 내부 5파 ({cc['start']['px']:,.0f} 시작): i {cc['i']['px']:,.0f} (-{ccs['i_len']:,.0f}) · "
                      f"ii {cc['ii']['px']:,.0f} (i 의 {ccs['ii_retrace_pct']:.1f}% 되돌림) · "
                      f"iii 진행 중 저가 {ccs['iii_low']:,.0f} ({ccs['iii_low_ts']}Z, i 의 {ccs['iii_len_x_i']:.2f}배)")
                print("    iii 목표: " + " / ".join(f"i 의 {r}배 {v:,.0f}" for r, v in t.items()))
                if ccs["invalid"]:
                    print(f"    ** ii 고점 {cc['ii']['px']:,.0f} 돌파 — C 카운트 무효, 재라벨 필요(revisions) **")
                elif ccs["above_i_low"]:
                    print(f"    iii 저점 뒤 반등 {ccs['bounce_hi']:,.0f} 이 i 저점 {cc['i']['px']:,.0f} 위 → "
                          f"iv 아님: iii 미완(iii 안의 작은 반등) 또는 C 종결 대각")
                else:
                    print(f"    iii 저점 뒤 반등 {ccs['bounce_hi']:,.0f} 은 i 저점 {cc['i']['px']:,.0f} 아래 → "
                          f"iii 완료·iv 진행 가능 (iv 는 {cc['i']['px']:,.0f} 을 넘으면 안 됨)")
        else:
            cl = count["correction"].get("C_target_labels", {})
            print("  C 목표 (플랫 가정):")
            for k, v in cor["C_targets"].items():
                print(f"    {v:>9,.0f}  {cl.get(k, k)}")
    if ols:
        sc, sh, nm, sl = ols["scenarios"], ols["shape"], ols["scenario_names"], ols["shape_names"]
        print(f"  확률표({ols['as_of']} 기준 {ols['basis_px']:,.0f}, 주관 — 검증된 모델 아님):")
        for k in sc:
            print(f"    {sc[k]:>3}%  {nm.get(k, k)}")
        print(f"    2파가 어떻게 끝나나 (첫 번째 시나리오가 맞을 때): "
              f"단일 ABC {ols['abc_within_S1']}% "
              f"({sl.get('zigzag_abc', 'zigzag')} {sh['zigzag_abc']} · {sl.get('flat_abc', 'flat')} {sh['flat_abc']}) "
              f"vs {sl.get('wxy', 'WXY')} {ols['wxy_within_S1']}%")
        print(f"    전체 기준으로 환산: 단일 ABC {ols['abc_uncond']:.0f}% / 복합 W-X-Y {ols['wxy_uncond']:.0f}% "
              f"(나머지는 다른 두 시나리오)")
        print("    재평가 트리거: " + " / ".join(
            f"{t['name']} {t['px']:,.0f}{'↓' if t['dir'] == 'below' else '↑'} {'발동' if t['fired'] else '✗'}"
            for t in ols["triggers"]))
        for t in ols["triggers"]:
            if t["fired"]:
                print(f"    ** {t['name']} 발동 — {t['effect']} → 확률 재평가 필요(revisions 기록) **")
    if sbs:
        print("  채점 장부 (브리어 점수, 낮을수록 좋음 — 기준: 무작위 보행 / 반반):")
        for r in sbs["rows"]:
            bl = r["baselines"]
            head = (f"    {r['id']} {r['question']} — 내 예측 {r['forecast']:.1%} "
                    f"(무작위 보행 {bl['random_walk']:.1%} / 반반 {bl['coin']:.0%})")
            print(head)
            if r["state"] == "resolved":
                b = r["brier"]
                tag = "기록됨" if r["recorded"] else "** 판정 나옴 — 파일에 결과 기록·커밋 필요 **"
                print(f"       결과 {r['outcome']} ({r['note']}) | 점수 내 예측 {b['forecast']:.3f} / "
                      f"무작위 보행 {b['random_walk']:.3f} / 반반 {b['coin']:.3f}  {tag}")
            elif r["state"] == "ambiguous":
                print(f"       ** 판정 보류 — {r['note']} → 1시간봉으로 순서 확인 필요 **")
            elif r["state"] == "void":
                print(f"       무효 — {r['note']} (파일에 void 기록 필요)")
            else:
                print(f"       미결 — {r['note'] or '두 가격 모두 미도달'}")
        c = sbs["cumulative"]
        if c["n"]:
            print(f"    누적 {c['n']}건 평균: 내 예측 {c['forecast']/c['n']:.3f} / "
                  f"무작위 보행 {c['random_walk']/c['n']:.3f} / 반반 {c['coin']/c['n']:.3f}")
        else:
            print("    누적: 아직 판정된 질문 없음")
    if tri:
        t = tri["t"]
        state = ("** 무효 — 6시간봉 종가가 무효선 아래 **" if tri["killed"] else
                 "** 확인 — 1파 고점 돌파, 5파 스러스트 시작 **" if tri["confirmed"] else
                 "경고 — D 가 상한을 넘음(윗선이 안 내려옴)" if tri["d_over"] else "진행 중")
        print(f"  4파 삼각수렴 (사용자 가설): {state}")
        print(f"    A {t['A_start']:,.0f}→{t['A_end']:,.0f} · B {t['B_end']:,.0f} · C {t['C_end']:,.0f} · D·E 대기 | "
              f"무효: 6시간봉 종가 {t['kill_close_below']:,.0f} 아래 / D 상한 {t['D_max']:,.0f} / "
              f"확인: {t['confirm_above']:,.0f} 돌파 → 스러스트 목표 = 돌파 지점 + {t['thrust_width']:,.0f}")
        if tri["new_low_below_C"] and not tri["killed"]:
            print(f"    C 저점 {t['C_end']:,.0f} 아래 저가 {tri['low']:,.0f} — 종가는 무효선 위. C 연장 중이거나 곧 무효")
    print("  살아 있는 시나리오: " +
          " / ".join(count["scenarios"].get(k, {}).get("label", k)
                     for k, v in res["scenarios"].items() if v and not k.startswith("_")))
    json.dump(res, open(OUT_FILE, "w"), ensure_ascii=False, indent=1)
    print(f"  → {OUT_FILE}")
    return res


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:                                   # noqa: BLE001
        print(f"[elliott] 실패: {exc}", file=sys.stderr)
        sys.exit(1)
