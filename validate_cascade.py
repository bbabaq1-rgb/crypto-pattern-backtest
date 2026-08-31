"""
validate_cascade.py — S3 청산 캐스케이드 페이드 조건부 재시험 (2026-08-29 2차).

1차(run 33261845718, 1h 365일): cascade_fade_long_1h n=85 mean=+6.04%
boot_p=0.000 수수료마진 통과 — 그러나 85건 중 56건이 Q1 집중(OOS 1/4)으로 기각.
Q1 +9.4% vs Q2~Q4 -0.1~-0.7% -> '고변동성 국면 조건부' 가설.

■ 사전등록 (실행 전 고정, 결과를 보고 바꾸지 않는다)

  파라미터 동결: 1차와 동일 (2.5xATR 급변 / 거래량 3배 / 꼬리 40% 회복).
    스윕으로 최적점을 찾지 않는다. 민감도는 '보고용'으로만 출력한다.

  주검정 (H1, 채택 판단의 유일한 근거):
    1h 1,100일(3년)로 데이터 4배 확대 후 **무조건부** 게이트 통과 여부.
    1차 기각 사유가 데이터 부족이었다면 여기서 통과해야 한다.

  부검정 (H2, 탐색적):
    인과적 고변동성 국면 한정. 국면 판정은 **진입 시점까지의 정보만** 사용:
      시장 변동성 = 각 시각 전 종목 ATR14/종가의 중앙값
      고변동성 = 그 값이 '직전 30일 분포의 상위 25%' 이상 (전방참조 없음)
    '고변동성에서 좋았다'는 1차 사후관찰에서 나온 가설이므로, 통과해도
    주검정 대체 근거가 되지 못한다. Bonferroni(부검정 2개) 적용.

  반증검정 (H3):
    저변동성(하위 25%) 국면. 가설이 참이면 여기서는 엣지가 없어야 한다.
    저변동성에서도 같은 크기 엣지가 나오면 '변동성 국면' 설명은 기각된다.

  강건성 진단 (채택 기준 아님, 보고용):
    - 상위 5거래 기여도 / 절사평균(상하 10%) — 소수 대박 의존 여부
    - 파라미터 3x3 민감도 — 특정 값에서만 작동하는 knife-edge 여부
    - 분기별 n·mean — 집중도 재확인

라벨/게이트: intraday_lab (±1.5xATR 배리어, 1h 12봉 보유, 수수료마진 조건).
"""
import json
import statistics
import sys
import time
from collections import defaultdict

import intraday_lab as lab

TF = "1h"
FETCH_DAYS = 1100                 # 3년
MOVE_ATR, VOL_MULT, RECOVER = 2.5, 3.0, 0.40      # 1차 동결값
# 국면 판정 기준선: 확장창(진입 시점까지의 전체 이력) 퍼센타일.
# 롤링 창은 지속 국면이 창을 채우면 포화된다 — 합성 검증에서 30일 창은 고변동
# 구간 hi 24%, 180일 창도 51%에 그쳤다(4개월 난기류가 창의 2/3를 채워 '평범'이 됨).
# 확장창은 3년 이력 대비로 재므로 수개월 난기류가 상위로 유지된다. 전방참조 없음.
VOL_BURNIN_D = 90                 # 판정 시작까지 최소 이력(일)
HI_PCTL, LO_PCTL = 0.75, 0.25
GRID = [(2.0, 2.5, 0.30), (2.5, 3.0, 0.40), (3.0, 4.0, 0.50)]  # 민감도용


def _universe():
    return json.load(open("universe.json", encoding="utf-8"))["trading_universe"]


def fetch(syms):
    import fetch_data
    t0, ok, new = time.time(), 0, 0
    for s in syms:
        n_new, total = fetch_data.update_csv(
            f"{s}/USDT", TF, lab.CSV(s, TF), window_days=FETCH_DAYS)
        if total > 0:
            ok += 1
            new += n_new
    print(f"[fetch] {TF} {FETCH_DAYS}일: {ok}/{len(syms)}종목 +{new}봉 "
          f"({time.time()-t0:.0f}s)", flush=True)


def load_all():
    data = {}
    for s in lab.symbols_with(TF):
        try:
            rows = lab.load_raw(s, TF)
        except Exception:
            continue
        if len(rows) < 500:
            continue
        data[s] = (rows, lab.atr_series(rows))
    return data


# ── 인과적 시장 변동성 국면 ─────────────────────────────────────────────────
def market_vol_state(data):
    """
    {ts: "hi"|"mid"|"lo"} — 각 시각의 시장 변동성이 '직전 30일 분포'에서
    어디에 위치하는지. 미래 정보 미사용(전방참조 없음).
    """
    per_ts = defaultdict(list)
    for sym, (rows, atr) in data.items():
        for i, r in enumerate(rows):
            a = atr[i]
            if a and r["c"] > 0:
                per_ts[r["ts"]].append(a / r["c"])
    series = [(ts, statistics.median(v)) for ts, v in sorted(per_ts.items())
              if len(v) >= 10]
    burn = VOL_BURNIN_D * 24       # 1h 봉 기준 최소 이력
    state = {}
    hist = []                      # 진입 시점까지의 과거값만 누적(확장창)
    for k, (ts, v) in enumerate(series):
        if k >= burn:
            s = sorted(hist)
            hi = s[int(len(s) * HI_PCTL)]
            lo = s[int(len(s) * LO_PCTL)]
            state[ts] = "hi" if v >= hi else ("lo" if v <= lo else "mid")
        hist.append(v)             # 판정 후 추가 -> 당해 값 미포함(전방참조 차단)
    return state


# ── 캐스케이드 탐지 ─────────────────────────────────────────────────────────
def detect_cascades(data, move_atr=MOVE_ATR, vol_mult=VOL_MULT,
                    recover=RECOVER):
    """[(sym, ts, date, ret, direction)] — 급락 페이드(롱)만. 1차 통과 셀 재현."""
    H = lab.HORIZON[TF]
    out = []
    for sym, (rows, atr) in data.items():
        for i in range(25, len(rows) - H - 1):
            a = atr[i]
            if not a:
                continue
            r0 = rows[i]
            rng = r0["h"] - r0["l"]
            if rng <= 0:
                continue
            move = r0["c"] - r0["o"]
            if move >= 0 or abs(move) < move_atr * a:
                continue
            vavg = sum(x["v"] for x in rows[i - 20:i]) / 20
            if vavg <= 0 or r0["v"] < vavg * vol_mult:
                continue
            if (r0["c"] - r0["l"]) / rng < recover:
                continue
            _, ret = lab.outcome_atr(rows, i, "long", atr, H)
            if ret is not None:
                out.append((sym, r0["ts"], r0["date"], ret))
    return out


def robustness(sigs, label):
    """소수 대박 의존도 진단 — 채택 기준 아님(보고용)."""
    rets = sorted((r for _, _, _, r in sigs), reverse=True)
    if len(rets) < 10:
        return {}
    total = sum(rets)
    top5 = sum(rets[:5])
    k = max(1, int(len(rets) * 0.1))
    trimmed = statistics.mean(rets[k:-k])
    info = dict(top5_share=round(top5 / total, 3) if total else None,
                trimmed_mean=round(trimmed, 5),
                max_ret=round(rets[0], 4), min_ret=round(rets[-1], 4))
    print(f"  [강건성:{label}] 상위5거래 기여 {info['top5_share']} | "
          f"절사평균(10%) {trimmed*100:+.2f}% | 최대 {rets[0]*100:+.1f}% "
          f"최소 {rets[-1]*100:+.1f}%")
    return info


def main():
    syms = _universe()
    print(f"S3 캐스케이드 재시험 | 유니버스 {len(syms)}종목 | "
          f"{TF} {FETCH_DAYS}일 | 파라미터 동결 "
          f"({MOVE_ATR}xATR/{VOL_MULT}배/{RECOVER})")
    if "--no-fetch" not in sys.argv:
        fetch(syms)

    data = load_all()
    if not data:
        print("데이터 없음 — 중단")
        return
    span = [len(r) for r, _ in data.values()]
    print(f"데이터: {len(data)}종목, 봉수 중앙값 {statistics.median(span):.0f} "
          f"(~{statistics.median(span)/24:.0f}일)")

    H = lab.HORIZON[TF]
    pool = []
    for rows, atr in data.values():
        step = max(1, len(rows) // 80)
        for i in range(20, len(rows) - H - 1, step):
            if atr[i]:
                pool.append((rows, atr, i))
    boot = lab.bootstrap_baseline(pool[:6000], lambda si: "long", H)

    sigs = detect_cascades(data)
    print(f"\n캐스케이드 탐지: {len(sigs)}건 (1차 365일 기준 85건)")
    results = []

    # ── 주검정 H1: 무조건부 ────────────────────────────────────────────────
    print("\n" + "=" * 64 + "\n[주검정 H1] 무조건부 — 채택 판단의 유일한 근거")
    r1 = lab.evaluate("H1 cascade_fade_long_1h 무조건부(3년)",
                      [(d, r) for _, _, d, r in sigs], boot,
                      extra=dict(hypothesis="H1_primary", tf=TF,
                                 n_days=FETCH_DAYS))
    r1.update(robustness(sigs, "H1"))
    results.append(r1)

    # ── 부검정 H2 / 반증 H3: 인과적 변동성 국면 ────────────────────────────
    state = market_vol_state(data)
    tagged = [(s, ts, d, r, state.get(ts)) for s, ts, d, r in sigs]
    n_unknown = sum(1 for *_, st in tagged if st is None)
    print(f"\n국면 판정: hi={sum(1 for *_,s in tagged if s=='hi')} "
          f"mid={sum(1 for *_,s in tagged if s=='mid')} "
          f"lo={sum(1 for *_,s in tagged if s=='lo')} "
          f"미상(창 부족)={n_unknown}")

    print("\n" + "=" * 64 + "\n[부검정 H2] 고변동성 국면 한정 (탐색적, Bonferroni α=0.025)")
    hi = [(s, ts, d, r) for s, ts, d, r, st in tagged if st == "hi"]
    r2 = lab.evaluate("H2 고변동성(상위25%) 한정", [(d, r) for _, _, d, r in hi],
                      boot, extra=dict(hypothesis="H2_secondary_exploratory",
                                       tf=TF, bonferroni_alpha=0.025))
    r2.update(robustness(hi, "H2"))
    if r2.get("boot_p") is not None and r2["verdict"] == "PASSED" \
            and r2["boot_p"] >= 0.025:
        r2["verdict"] = "REJECTED"
        r2["reason"] = "Bonferroni(2) 미달"
        print("  -> Bonferroni 보정 미달로 기각")
    results.append(r2)

    print("\n" + "=" * 64 + "\n[반증 H3] 저변동성 국면 — 여기서도 엣지가 나오면 "
          "'변동성 국면' 설명은 기각")
    lo_s = [(s, ts, d, r) for s, ts, d, r, st in tagged if st == "lo"]
    r3 = lab.evaluate("H3 저변동성(하위25%) 반증", [(d, r) for _, _, d, r in lo_s],
                      boot, extra=dict(hypothesis="H3_falsification", tf=TF))
    results.append(r3)

    # ── 강건성: 파라미터 민감도 (보고용) ───────────────────────────────────
    print("\n" + "=" * 64 + "\n[민감도] 파라미터 3종 (채택 기준 아님)")
    sens = []
    for ma, vm, rc in GRID:
        s2 = detect_cascades(data, ma, vm, rc)
        rets = [r for _, _, _, r in s2]
        m = statistics.mean(rets) if rets else 0.0
        md = statistics.median(rets) if rets else 0.0
        sens.append(dict(move_atr=ma, vol_mult=vm, recover=rc,
                         n=len(rets), mean=round(m, 5), median=round(md, 5)))
        mark = " <- 동결값" if (ma, vm, rc) == (MOVE_ATR, VOL_MULT, RECOVER) else ""
        print(f"  {ma}xATR/{vm}배/{rc}: n={len(rets)} "
              f"mean={m*100:+.2f}% median={md*100:+.2f}%{mark}")
    results.append(dict(study="민감도 그리드", grid=sens, note="보고용"))

    print("\n" + "=" * 64 + "\n요약")
    for r in results:
        if "verdict" in r:
            print(f"  {r['study']:<38} {r['verdict']:<9} "
                  f"n={r.get('n')} mean={r.get('mean')}")
    lab.dump(results, "_cascade_results.json")


if __name__ == "__main__":
    main()
