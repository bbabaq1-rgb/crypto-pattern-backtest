"""
validate_band_rule.py — 고정 띠 규칙(손절 → 진입가 복귀 시 재매수)의 **체결 마찰 3종** 측정
(2026-09-07 사전 등록, 사용자 지시 "세 개 다 진행").

## 배경
사용자 제안 규칙: 진입가 P 에서 매수 → 저가가 P×(1−s) 에 닿으면 손절 → **진입가 밑에서는 사지 않고 P 로 올라왔을 때만**
재매수 → 반복. 일봉 즉석 진단(registry whipsaw_diag_2026_09_07)에서 손절 1% 가 넓은 불장 5.04x(보유 5.29x) ·
약세 2022 0.96x(보유 0.16x) 로 나왔다. **그 진단은 사전 등록이 아니고 세 가지를 못 쟀다** — 이 시험이 그 셋만 잰다.

  A. **지연 비용** — 손절 체결을 우리가 늦게 알아채는 동안 가격이 P 위로 달아나면 트리거를 걸 수 없고 시장가로 따라가야 한다.
  B. **장중 재교차** — 일봉은 하루 1회 순환만 센다. 1시간봉으로 재면 순환이 몇 배인가.
  C. **바스켓** — 지금까지 수치는 전부 코인별 중앙값인데 중앙값 코인은 살 수 없다. 동일가중 바스켓 자산곡선.

## 무엇을 묻지 않는가 (사전 명시)
'규칙이 좋은가'는 이 시험의 물음이 **아니다**. 그건 같은 데이터에서 이미 봤고(in-sample), 손절 1% 도 그 진단에서 골랐다.
이 시험은 **마찰 셋이 그 결과를 무너뜨리는가**만 판정한다. 따라서 통과해도 '규칙 채택'이 아니라 '마찰 통과'다.

## 동결 파라미터
  · 규칙: 진입가 P 고정. 손절 = 저가 <= P×(1−s), 체결은 시장가(갭이면 시가). 재매수 = 고가 >= P 일 때.
  · s ∈ {1%, 3%, 8%}, **주 판정 1%**(진단에서 선택된 값 — 같은 데이터에서 골랐음을 명시).
  · 수수료 편도 0.1%. 폴링 지연 d ∈ {0, 1, 4} 시간.
  · 지연의 기전(정확히): 손절 체결 후 d 시간 뒤에 알아챈다 → 그 시점 가격이 P 이상이면 **시장가로 즉시 매수**(비용 발생),
    P 미만이면 트리거를 걸고 이후는 정확히 P 에 체결(비용 0). 즉 지연은 **V자 반등에서만** 벌금을 물린다.
  · 1h 구간: 최근 H1_DAYS(365)일, 코호트 = 30일 거래대금 상위 COHORT_N(30). 1d 구간: PERIODS 고정 4개.
  · 바스켓: 동일가중 BASKET_N(20) 종목, 각 종목이 독립적으로 띠 규칙을 돈다. 시작일에 자본 균등 분할, 리밸런스 없음.

## 판정 (사전 등록)
  J1 지연: A 에서 잰 **1시간 지연의 실효 슬리피지 δ** 를 1d 불장 시뮬에 적용했을 때 결과 >= 즉시 체결 결과의 **85%**
  J2 재교차: 같은 구간·같은 규칙을 1h 봉과 1d 봉으로 돌렸을 때 **1h 결과 >= 1d 결과의 85%**
  J3 바스켓: 동일가중 바스켓이 (a) 약세 구간에서 보유 대비 우위 (b) 불장 구간에서 보유의 85% 이상 유지
  판정: VIABLE(3/3) / MARGINAL(2/3) / NOT_VIABLE(그 외). 85% 는 결과를 보기 전에 정한 값이다.

**DEPLOY_ON_PASS=False.** 통과해도 실거래 반영 없음 — 이건 기존 패턴 시스템의 변형이 아니라 별개 시스템이고,
종목 선택 문제(어느 코인에 걸 것인가)가 미해결로 남는다. 채택은 사용자 결정.

한계(실행 전 기록): 1h 이력은 최근 구간뿐이라 **불장 국면의 장중 미시구조는 직접 못 본다**(A 의 δ 를 불장 일봉에 이전
적용한다 — 변동성 차이만큼 오차) · 생존 편향 · 1h 봉도 분 단위 재교차는 못 본다(측정된 순환은 하한).

실행: python validate_band_rule.py [--no-fetch]      출력: _band_rule.json + RESULT_JSON
"""
import json
import statistics as st
import sys

import detlib
import fetch_data
import validate_regime_split_all as va
from validate_regime_split import turnover_rank

# ── 동결 ─────────────────────────────────────────────────────────────────────────────────────
STOPS = (0.01, 0.03, 0.08)
STOP_PRIMARY = 0.01
FEE = 0.001
DELAYS_H = (0, 1, 4)
COHORT_N = 30
H1_DAYS = 365
BASKET_N = 20
PASS_RATIO = 0.85
PERIODS = [("bull", "2020-04-29", "2021-06-06"), ("wait_bull", "2019-06-01", "2021-06-06"),
           ("bear2022", "2022-01-01", "2022-12-31"), ("chop2025", "2025-01-01", "2026-09-06")]
BULL_KEY, BEAR_KEY = "bull", "bear2022"
DEPLOY_ON_PASS = False


def run_band(r, i0, i1, stop, slip=0.0, delay=0, gap=True):
    """띠 규칙 1회. delay = 손절 후 '알아채기까지' 걸리는 봉 수. 반환 (최종배수, 보유배수, 순환수, 지연벌금건수)."""
    P = r[i0]["c"]
    if P <= 0:
        return None
    S = P * (1 - stop)
    E = 1.0 * (1 - FEE); units = E / P
    inpos = True; n = 0; late = 0; notice = None
    j = i0 + 1
    while j <= i1:
        x = r[j]
        if inpos:
            if x["l"] <= S:
                fill = min(S, x["o"]) if (gap and x["o"] < S) else S * (1 - slip)
                E = units * fill * (1 - FEE); units = 0.0; inpos = False; n += 1
                notice = j + delay
        else:
            if delay > 0 and j < notice:
                pass                                    # 아직 손절 사실을 모름
            elif delay > 0 and j == notice:
                if x["c"] >= P:                         # 이미 P 위로 달아남 → 시장가 추격
                    px = x["c"] * (1 + slip); E *= (1 - FEE); units = E / px; inpos = True; late += 1
            elif x["h"] >= P:                           # 트리거 정상 체결
                px = P * (1 + slip); E *= (1 - FEE); units = E / px; inpos = True
        j += 1
    if units > 0:
        E = units * r[i1]["c"]
    return E, r[i1]["c"] / r[i0]["c"], n, late


def span(r, d0, d1):
    idx = [k for k, x in enumerate(r) if d0 <= x["date"] <= d1]
    return (idx[0], idx[-1]) if len(idx) >= 60 else None


def delay_cost(rows_h, stop, delay):
    """A: 1h 봉에서 지연이 실제로 물린 벌금. 반환 dict(events, late, share, median_excess)."""
    exc = []; ev = 0; lt = 0
    for r in rows_h.values():
        if len(r) < 200:
            continue
        P = r[0]["c"]
        if P <= 0:
            continue
        S = P * (1 - stop); inpos = True; notice = None
        for j in range(1, len(r)):
            x = r[j]
            if inpos:
                if x["l"] <= S:
                    inpos = False; notice = j + delay; ev += 1
            elif j == notice and delay > 0:
                if x["c"] >= P:
                    exc.append(x["c"] / P - 1); lt += 1; inpos = True
            elif (delay == 0 or j > notice) and x["h"] >= P:
                inpos = True
    return dict(events=ev, late=lt, share=(lt / ev if ev else None),
                median_excess=(st.median(exc) if exc else 0.0), mean_excess=(st.mean(exc) if exc else 0.0))


def basket(rows_1d, syms, d0, d1, stop, slip=0.0, delay=0):
    """C: 동일가중 바스켓. 각 종목이 독립 띠 규칙. 반환 (규칙 배수, 보유 배수, 종목수)."""
    rr = []; hh = []
    for s in syms:
        r = rows_1d.get(s)
        if not r:
            continue
        sp = span(r, d0, d1)
        if not sp:
            continue
        out = run_band(r, sp[0], sp[1], stop, slip, delay)
        if out:
            rr.append(out[0]); hh.append(out[1])
    if not rr:
        return None
    return sum(rr) / len(rr), sum(hh) / len(hh), len(rr)


def _f(v, w=8, pct=False):
    if v is None:
        return " " * (w - 1) + "-"
    return f"{v*100:{w}.2f}" if pct else f"{v:{w}.2f}"


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    print(f"띠 규칙 마찰 시험 | 손절 {STOPS} 주 {STOP_PRIMARY} · 지연 {DELAYS_H}h · 코호트 {COHORT_N} · 1h {H1_DAYS}일 "
          f"· 바스켓 {BASKET_N} · 문턱 {PASS_RATIO} | DEPLOY_ON_PASS={DEPLOY_ON_PASS}")
    syms = va._syms()
    rows_1d = va.load_tf(syms, "1d", long=True)
    ranked = [s for s in turnover_rank(rows_1d)]
    cohort = ranked[:COHORT_N]
    print(f"[data] 1d {len(rows_1d)}종목 · 코호트 {cohort[:8]}…")

    if "--no-fetch" not in argv:
        t = 0
        for s in cohort:
            try:
                fetch_data.update_csv(f"{s}/USDT", "1h", detlib.CSV(s, "1h"), window_days=H1_DAYS); t += 1
            except Exception as e:
                print(f"  [fetch] {s} 1h 실패: {str(e)[:50]}")
        print(f"[fetch] 1h {t}/{len(cohort)}", flush=True)
    rows_h = {}
    for s in cohort:
        try:
            r = detlib.load_ohlcv(s, "1h")
            if len(r) >= 200:
                rows_h[s] = r
        except Exception:
            pass
    if rows_h:
        f0 = min(r[0]["date"] for r in rows_h.values()); f1 = max(r[-1]["date"] for r in rows_h.values())
        print(f"[data] 1h {len(rows_h)}종목 {f0}~{f1} (봉 중앙 {int(st.median([len(r) for r in rows_h.values()]))})")

    out = dict(frame="band_rule", deploy_on_pass=DEPLOY_ON_PASS, stop_primary=STOP_PRIMARY, A={}, B={}, C={})

    # ── A. 지연 비용 ────────────────────────────────────────────────────────────
    print("\n== A. 지연 비용 (1h 봉) — 손절 후 d시간 뒤 이미 P 위였던 비율과 그때의 초과 체결가 ==")
    print(f"{'손절':>5}{'지연':>5}{'손절 건수':>10}{'추격 매수':>10}{'비율':>8}{'초과(중앙)':>11}{'초과(평균)':>11}")
    for stop in STOPS:
        for d in DELAYS_H:
            if d == 0:
                continue
            a = delay_cost(rows_h, stop, d)
            out["A"][f"{stop}_{d}h"] = a
            print(f"{stop*100:>4.0f}%{d:>4}h{a['events']:>10}{a['late']:>10}"
                  f"{(a['share'] or 0)*100:>7.0f}%{_f(a['median_excess'],10,True)}%{_f(a['mean_excess'],10,True)}%")
    delta = out["A"].get(f"{STOP_PRIMARY}_1h", {}).get("median_excess", 0.0)
    share = out["A"].get(f"{STOP_PRIMARY}_1h", {}).get("share", 0.0) or 0.0
    eff = delta * share                                    # 실효 슬리피지 = 벌금 크기 × 발생 빈도
    print(f"  → 손절 {STOP_PRIMARY*100:.0f}% · 1시간 지연의 **실효 슬리피지 δ = {eff*100:.3f}%** (초과 {delta*100:.2f}% × 빈도 {share*100:.0f}%)")
    out["delta_1h"] = eff

    # ── B. 장중 재교차 (1h vs 1d, 같은 구간) ────────────────────────────────────
    print("\n== B. 장중 재교차 — 같은 구간·같은 규칙을 1h 봉과 1d 봉으로 ==")
    print(f"{'손절':>5}{'1h 순환':>9}{'1d 순환':>9}{'배수':>7}{'1h 결과':>10}{'1d 결과':>10}{'비율':>8}{'종목':>6}")
    for stop in STOPS:
        rh = []; rd = []
        for s, r in rows_h.items():
            oh = run_band(r, 0, len(r) - 1, stop)
            d1 = rows_1d.get(s)
            if not d1 or not oh:
                continue
            lo, hi = r[0]["date"], r[-1]["date"]
            sp = span(d1, lo, hi)
            if not sp:
                continue
            od = run_band(d1, sp[0], sp[1], stop)
            if od:
                rh.append(oh); rd.append(od)
        if not rh:
            continue
        mh = st.median([x[0] for x in rh]); md = st.median([x[0] for x in rd])
        nh = st.median([x[2] for x in rh]); nd = st.median([x[2] for x in rd])
        out["B"][str(stop)] = dict(n1h=nh, n1d=nd, mult=(nh / nd if nd else None), r1h=mh, r1d=md,
                                   ratio=(mh / md if md else None), coins=len(rh))
        print(f"{stop*100:>4.0f}%{nh:>9.0f}{nd:>9.0f}{(nh/nd if nd else 0):>6.1f}x{mh:>9.2f}x{md:>9.2f}x"
              f"{(mh/md*100 if md else 0):>7.0f}%{len(rh):>6}")

    # ── C. 바스켓 ───────────────────────────────────────────────────────────────
    bsyms = ranked[:BASKET_N]
    print(f"\n== C. 동일가중 바스켓 {BASKET_N}종목 (손절 {STOP_PRIMARY*100:.0f}%) ==")
    print(f"{'구간':<12}{'즉시 체결':>11}{'δ 적용':>10}{'1h 지연':>10}{'그냥 보유':>11}{'종목':>6}")
    for key, d0, d1 in PERIODS:
        b0 = basket(rows_1d, bsyms, d0, d1, STOP_PRIMARY)
        bd = basket(rows_1d, bsyms, d0, d1, STOP_PRIMARY, slip=eff)
        bl = basket(rows_1d, bsyms, d0, d1, STOP_PRIMARY, slip=eff, delay=1)
        if not b0:
            continue
        out["C"][key] = dict(immediate=b0[0], with_delta=bd[0], delayed=bl[0], hold=b0[1], coins=b0[2])
        print(f"{key:<12}{b0[0]:>10.2f}x{bd[0]:>9.2f}x{bl[0]:>9.2f}x{b0[1]:>10.2f}x{b0[2]:>6}")

    # ── 판정 ────────────────────────────────────────────────────────────────────
    cb = out["C"].get(BULL_KEY, {}); cr = out["C"].get(BEAR_KEY, {})
    j1 = bool(cb and cb["immediate"] > 0 and cb["with_delta"] / cb["immediate"] >= PASS_RATIO)
    bb = out["B"].get(str(STOP_PRIMARY), {})
    j2 = bool(bb.get("ratio") is not None and bb["ratio"] >= PASS_RATIO)
    j3 = bool(cr and cb and cr["immediate"] > cr["hold"] and cb["immediate"] / cb["hold"] >= PASS_RATIO)
    verdict = "VIABLE" if (j1 and j2 and j3) else ("MARGINAL" if sum((j1, j2, j3)) == 2 else "NOT_VIABLE")
    print(f"\n판정: J1 지연 {j1} · J2 재교차 {j2} · J3 바스켓 {j3} → **{verdict}**")
    print(f"  J1: 불장 바스켓 δ적용/즉시 = {(cb['with_delta']/cb['immediate']*100 if cb.get('immediate') else 0):.0f}% (>= {PASS_RATIO*100:.0f}%)")
    print(f"  J2: 1h/1d 결과비 = {(bb.get('ratio') or 0)*100:.0f}% (>= {PASS_RATIO*100:.0f}%)")
    print(f"  J3: 약세 {cr.get('immediate',0):.2f}x vs 보유 {cr.get('hold',0):.2f}x · 불장 보유대비 {(cb['immediate']/cb['hold']*100 if cb.get('hold') else 0):.0f}%")
    out.update(j1=j1, j2=j2, j3=j3, verdict=verdict)
    json.dump(out, open("_band_rule.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print("\nRESULT_JSON: " + json.dumps(dict(frame="band_rule", verdict=verdict, j1=j1, j2=j2, j3=j3,
                                             delta_1h=eff, B=out["B"], C=out["C"]), ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
