"""
validate_tb_wide.py — 삼중바닥 **넓은 스윙 판(pivot 5 / eq 0.45)** 사전 등록 시험
(2026-09-08, 사용자 지시 "5 / 0.45로 사전등록해서 돌려줘 ... 1시간, 4시간, 1d, 1w 로 다 돌려봤으면").

## 왜
배포된 `triple_bottom` 은 PIVOT_HALF=3 / EQ_DEPTH_FRAC=0.35 다. 사용자가 실전에서 가장 많이
매매하는 형태(첫 저점에서 두 번 연속 저점을 갱신하되 **갱신 폭이 줄어드는** 감속형 바닥)는
이 값으로는 잡히지 않는다. 2026-06-01~08-01 BTC 사례에서 조건 6개 중 **동일수준 하나만**
깊이의 4% 차이로 탈락했고, 원인은 (a) ±3봉 스윙이 중간 흔들림까지 저점으로 세어 조합을 흐리고
(b) 동일수준 허용폭이 좁아서였다. 사용자가 지정한 값 **5 / 0.45** 로 전 TF 시험한다.

## 사용자가 준 실제 사례 (사전 등록에 박아 둔다 — 결과 해석의 기준점)
업비트 KRW-BTC 일봉: 06-05 90,500,000 → 07-01 88,770,000(−1.91%) → 08-14 88,342,000(−0.48%).
갱신 폭이 4.0배 축소, 간격 26/44봉. 넥라인 100,992,000, 깊이 14.3%. 08-21 종가 돌파 후
베이스 대비 **+27.3%**. 이 셋업은 5/0.45 로 잡히고(신호 2026-08-20) 3/0.35 로는 안 잡힌다.
**OKX USDT 에서는 같은 기간 저점이 갱신되지 않았다**(59,078 → 57,750 → 62,227) — 원화 약세로
KRW 차트에서만 하강 구조가 나온 것. 그래서 KRW 대조를 진단으로 넣는다(D3).

## 동결 파라미터 (결과 보기 전 고정)
  · pivot_half=5, eq_frac=0.45. 나머지 triple_bottom 상수는 **불변**
    (MIN_SPACING 5 / MAX_SPAN 90 / MAX_WAIT 30 / DEPTH_ATR_MULT 2.5 / VOL_BREAK_MULT 1.5), causal=True.
  · TF: 1h / 4h / 1d / 1w (사용자 지정 전부). 방향 롱. 레짐 ALL. 코호트 **top30**(실거래 코호트).
  · 청산·베이스라인·홀드아웃은 validate_revival 과 동일 프레임을 그대로 재사용한다
    (1d/4h/1w 방식D, 1h ATR 배리어 / 같은 레짐·코호트·TF 무작위 진입 k=n / 달력 홀드아웃).
  · 홀드아웃: 1h 90일 · 4h·1d 365일 · **1w 730일**(주봉 희소성 — validate_exit_1w 와 같은 이유).

## 판정 (사전 등록)
  셀 = TF 하나. 네 셀을 하나의 가족으로 보고 **Holm 보정**(m=4)을 boot_p 에 건다.
  C1 게이트 v2 (n>=20 · mean>0 · 승률>=35% · Holm 보정 boot_p<0.05 · OOS>=2/4)
  C2 홀드아웃 n>=10 & mean>0        C3 자산곡선 CAGR>0 & Calmar>0
  셋 다 통과 → **CONFIRMED** / C1·C3 통과인데 홀드아웃 n<10 → **INCONCLUSIVE** / 그 외 **REJECTED**

**DEPLOY_ON_PASS=False.** 통과해도 실거래 반영 없음 — 관찰 기간(~2026-10-06) 중이고,
배포는 사용자 결정. 통과 셀은 registry 에 passed_not_deployed 로 남긴다.

## 진단 (판정 아님)
  D1 파라미터 격자 pivot_half {3,5,7} x eq_frac {0.35,0.45,0.55} — 5/0.45 가 격자에서 어디쯤인지.
     **사후에 격자 최대값을 고르지 않는다**(basket/cadence 에서 반복한 원칙).
  D2 하강형 부분집합 — L1>L2>L3 이고 갱신 폭이 축소된 셋업만(사용자 '베스트' 정의).
  D3 업비트 KRW 대조 — 같은 규칙을 KRW 일봉(메이저)에 돌려 신호 집합이 얼마나 갈리는지.
     우리는 OKX USDT 로 거래하므로 판정은 USDT 로만 한다. KRW 는 '탐지 소스를 바꿀 가치가 있는가'
     라는 별도 물음의 사전 정보일 뿐이다.

## 사전 확률 — 결과 보기 전에 기록한다
넓은 스윙은 신호 수를 크게 줄인다(BTC 1d 에서 3/0.35 2건 → 5/0.45 2건). 1w 는 표본이 특히 얇아
INCONCLUSIVE 가 유력하고, 1h 는 홀드아웃 90일이라 마찬가지다. **가장 그럴듯한 결과는 4h·1d 에서
n 이 붙고 나머지는 판정 불가**이며, 통과하더라도 triple_bottom_1w 가 룩어헤드로 정지된 전력이 있어
인과성(causal=True) 확인이 필수다.

## 실행 전 수정 1건 (2026-09-08, 로컬 스모크에서 발견 — 공개)
1d 를 OKX 범위(약 900~1,200봉)로만 읽으면 **1w 는 train 구간이 통째로 빈다**(홀드아웃 730일이
전 표본을 삼킴 → Calmar 계산 불가). 결과의 부호를 보고 고른 변경이 아니라 창이 성립하지 않는
구조적 결함이므로, 1d 를 **data_long(2017~)에 이어 붙이는 것을 기본**으로 한다(`--short` 로 끌 수 있다).
validate_revival 의 `--long` 과 같은 경로이고 레짐 라벨도 그 봉으로 만든다. 스모크 수치는 8종목
축소판이라 **결과가 아니다**.

실행: python validate_tb_wide.py [--no-fetch] [--short] [--tf 1d,4h]   출력: _tb_wide.json + RESULT_JSON
"""
import json
import statistics as st
import sys
import time

import detector_triple_bottom as tb
import detlib
import regime_switch as rs
import validate_regime_split_all as va
import validate_revival as vr

# ── 동결 ─────────────────────────────────────────────────────────────────────
PIVOT_HALF, EQ_FRAC = 5, 0.45
TFS = ("1h", "4h", "1d", "1w")
COHORT, REGIME, DIRECTION = "top30", "ALL", "long"
HOLDOUT_BY_TF = {"1h": 90, "4h": 365, "1d": 365, "1w": 730}
GRID_PIVOT, GRID_EQ = (3, 5, 7), (0.35, 0.45, 0.55)
KRW_MAJORS = ("BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "LINK", "AVAX")
DEPLOY_ON_PASS = False


def holm(pvals):
    """{key: p} → {key: 보정 p} (step-down)."""
    items = sorted((v, k) for k, v in pvals.items() if v is not None)
    m, out, run = len(items), {}, 0.0
    for r, (v, k) in enumerate(items):
        run = max(run, min(1.0, (m - r) * v))
        out[k] = run
    return out


def detect_fn(pivot_half=PIVOT_HALF, eq_frac=EQ_FRAC):
    return lambda rows: tb.detect(rows, pivot_half=pivot_half, eq_frac=eq_frac)


def descending(rows, si, pivot_half=PIVOT_HALF, eq_frac=EQ_FRAC):
    """이 신호의 셋업이 '연속 저점 갱신 + 갱신 폭 축소'인가 (D2)."""
    for d in tb.detect_detail(rows, pivot_half=pivot_half, eq_frac=eq_frac):
        if d["sig"] != si:
            continue
        l1, l2, l3 = (rows[d[k]]["l"] for k in ("L1", "L2", "L3"))
        return l1 > l2 > l3 and (l1 - l2) > (l2 - l3)
    return False


def load_krw(market, count=800):
    """업비트 KRW 일봉 (D3 진단 전용). 실패하면 빈 목록."""
    import urllib.parse
    import urllib.request
    out, to = {}, None
    try:
        for _ in range(max(1, count // 200)):
            u = f"https://api.upbit.com/v1/candles/days?market=KRW-{market}&count=200"
            if to:
                u += "&to=" + urllib.parse.quote(to)
            req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as r:
                d = json.loads(r.read().decode())
            if not d:
                break
            for c in d:
                out[c["candle_date_time_kst"][:10]] = c
            to = d[-1]["candle_date_time_utc"].replace("T", " ")
            time.sleep(0.2)
    except Exception as e:
        print(f"  [KRW] {market} 실패: {str(e)[:50]}")
        return []
    return [dict(date=k, ts=0, o=v["opening_price"], h=v["high_price"], l=v["low_price"],
                 c=v["trade_price"], v=v["candle_acc_trade_volume"]) for k, v in sorted(out.items())]


def _f(v, w=8):
    return f"{'n/a':>{w}}" if v is None else f"{v*100:>+{w-1}.2f}%"


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    tfs = argv[argv.index("--tf") + 1].split(",") if "--tf" in argv else list(TFS)
    # 1w 는 장기 이력 없이는 train 이 비어 판정 자체가 성립하지 않는다(위 '실행 전 수정' 참조).
    long_1d = "--short" not in argv
    print(f"삼중바닥 넓은 스윙 판 | pivot_half={PIVOT_HALF} eq_frac={EQ_FRAC} | TF {tfs} "
          f"| 코호트 {COHORT} 레짐 {REGIME} {DIRECTION} | Holm m={len(tfs)} | DEPLOY_ON_PASS={DEPLOY_ON_PASS}")
    syms = va._syms()
    if "--no-fetch" not in argv:
        va.fetch(syms, [t for t in ("1d", "4h", "1h") if t in tfs or t == "1d"])
    rows_1d = va.load_tf(syms, "1d", long=long_1d)
    regmap = rs.build_regime_map(rows_by=rows_1d) if long_1d else rs.build_regime_map()
    if long_1d:
        first_all = min(r[0]["date"] for r in rows_1d.values())
        print(f"[long] 1d 장기 이력 사용 — 최초 {first_all} · 레짐 라벨 {min(regmap)}~{max(regmap)}")
    ranked = vr.turnover_rank(rows_1d)
    out = dict(frame="tb_wide", pivot_half=PIVOT_HALF, eq_frac=EQ_FRAC,
               deploy_on_pass=DEPLOY_ON_PASS, cells={}, diag={})

    # ── 주 판정: TF 별 셀 ────────────────────────────────────────────────
    raw = {}
    for tf in tfs:
        t0 = time.time()
        if tf == "1d":
            rows_by = rows_1d
        elif tf == "1w":
            rows_by = {s: detlib.resample_rows(r, "1w") for s, r in rows_1d.items()}
        else:
            rows_by = va.load_tf(syms, tf)
        rows_by = {s: r for s, r in rows_by.items() if len(r) > 60}
        cs = set(s for s in ranked[:30] if s in rows_by)
        cohorts = {"all": set(rows_by), "top30": cs}
        pools, atrs = vr.build_context(tf, rows_by, cohorts, regmap)
        first = min(r[0]["date"] for r in rows_by.values())
        last = max(r[-1]["date"] for r in rows_by.values())
        from datetime import date
        cutoff = date.fromordinal(date.fromisoformat(last).toordinal() - HOLDOUT_BY_TF[tf]).isoformat()
        span = max(1, date.fromisoformat(cutoff).toordinal() - date.fromisoformat(first).toordinal())
        by_sym = vr.collect(tf, detect_fn(), DIRECTION, rows_by, atrs, regmap)
        pool = vr.eval_pool(tf, pools[(COHORT, REGIME)], rows_by, atrs, regmap, DIRECTION)
        sigs = [x for s in cs for x in by_sym.get(s, [])]
        rec = vr.gate_cell(sigs, pool)
        raw[tf] = dict(rec=rec, sigs=sigs, cutoff=cutoff, span=span, atrs=atrs,
                       rows_by=rows_by, cohort_syms=cs, by_sym=by_sym)
        print(f"\n[{tf}] 종목 {len(rows_by)} · top30 {len(cs)} · train {first}~{cutoff} "
              f"· holdout {HOLDOUT_BY_TF[tf]}일 · 수집 {time.time()-t0:.0f}s")
        print(f"  n={rec['n']} mean={_f(rec['mean'])} med={_f(rec['median'])} 승률 {rec['win_rate']*100:.0f}% "
              f"엣지 {_f(rec['edge'])} boot_p={rec['boot_p']:.3f} OOS {rec['oos_pos']}/4", flush=True)

    ph = holm({tf: raw[tf]["rec"]["boot_p"] for tf in tfs})
    print(f"\n== 주 판정 (Holm m={len(tfs)}) ==")
    for tf in tfs:
        r = raw[tf]
        rec, sigs = r["rec"], r["sigs"]
        cells = {COHORT: dict(gate=rec, sigs=sigs)}
        conf = vr.confirm(cells, r["cutoff"], r["span"])
        p_adj = ph.get(tf, 1.0)
        fails = [x for x in rec["reason"].split(", ") if x and not x.startswith("boot_p")]
        if p_adj >= 0.05:
            fails.append(f"Holm p={p_adj:.3f}")
        c1 = not fails
        ho, eq = conf["holdout"], conf["equity"]
        if c1 and conf["c3_equity"] and ho["n"] < vr.HOLDOUT_MIN_N:
            verdict = "INCONCLUSIVE"
        elif c1 and conf["c2_holdout"] and conf["c3_equity"]:
            verdict = "CONFIRMED"
        else:
            verdict = "REJECTED"
        cal = f"{eq['calmar']:.2f}" if eq else "n/a"
        print(f"  {tf:<3} n={rec['n']:>4} mean={_f(rec['mean'])} 승률 {rec['win_rate']*100:>3.0f}% "
              f"boot_p={rec['boot_p']:.3f}→Holm {p_adj:.3f} | holdout n={ho['n']} {_f(ho['mean'])} "
              f"| Calmar {cal} → **{verdict}**" + (f"  ({', '.join(fails)})" if fails else ""))
        out["cells"][tf] = dict(gate=rec, holm_p=p_adj, holdout=ho,
                                equity=(eq and {k: eq[k] for k in ("cagr", "mdd", "calmar", "final")}),
                                verdict=verdict)

    # ── D1 격자 (진단) ──────────────────────────────────────────────────
    print("\n== D1 파라미터 격자 (진단·판정 아님) — 신호 수 / 평균 ==")
    for tf in tfs:
        r = raw[tf]
        line = {}
        for phv in GRID_PIVOT:
            for eqv in GRID_EQ:
                bs = vr.collect(tf, detect_fn(phv, eqv), DIRECTION, r["rows_by"], r["atrs"], regmap)
                sg = [x for s in r["cohort_syms"] for x in bs.get(s, [])]
                line[f"{phv}/{eqv}"] = (len(sg), st.mean([x["ret"] for x in sg]) if sg else None)
        out["diag"][f"grid_{tf}"] = {k: [v[0], v[1]] for k, v in line.items()}
        print(f"  [{tf}] " + " · ".join(
            f"{k} n={v[0]}" + ("" if v[1] is None else f"/{v[1]*100:+.1f}%") for k, v in line.items()), flush=True)

    # ── D2 하강형 부분집합 (진단) ────────────────────────────────────────
    print("\n== D2 하강형 부분집합 (L1>L2>L3 & 갱신폭 축소) ==")
    for tf in tfs:
        r = raw[tf]
        sub = []
        for s in r["cohort_syms"]:
            rows = r["rows_by"].get(s)
            if not rows:
                continue
            dd = {d["sig"]: d for d in tb.detect_detail(rows, pivot_half=PIVOT_HALF, eq_frac=EQ_FRAC)}
            for x in r["by_sym"].get(s, []):
                si = next((i for i in dd if rows[i]["date"] == x["date"]), None)
                if si is None:
                    continue
                d = dd[si]
                l1, l2, l3 = rows[d["L1"]]["l"], rows[d["L2"]]["l"], rows[d["L3"]]["l"]
                if l1 > l2 > l3 and (l1 - l2) > (l2 - l3):
                    sub.append(x)
        m = st.mean([x["ret"] for x in sub]) if sub else None
        out["diag"][f"desc_{tf}"] = [len(sub), m]
        print(f"  [{tf}] n={len(sub)} mean={_f(m)}  (전체 {r['rec']['n']}건 중)")

    # ── D3 업비트 KRW 대조 (진단) ────────────────────────────────────────
    if "1d" in tfs:
        print("\n== D3 업비트 KRW 일봉 대조 (판정 아님 — 우리는 USDT 로 거래한다) ==")
        krw = {}
        for m_ in KRW_MAJORS:
            rows = load_krw(m_)
            if len(rows) < 100:
                continue
            k_sig = [rows[i]["date"] for i in tb.detect(rows, pivot_half=PIVOT_HALF, eq_frac=EQ_FRAC)]
            u_rows = rows_1d.get(m_, [])
            u_sig = [u_rows[i]["date"] for i in tb.detect(u_rows, pivot_half=PIVOT_HALF, eq_frac=EQ_FRAC)] if u_rows else []
            krw[m_] = dict(krw_n=len(k_sig), usdt_n=len(u_sig),
                           krw_dates=k_sig[-4:], usdt_dates=u_sig[-4:],
                           overlap=len(set(k_sig) & set(u_sig)))
            print(f"  {m_:<5} KRW {len(k_sig):>3}건 {k_sig[-3:]} | USDT {len(u_sig):>3}건 {u_sig[-3:]} "
                  f"| 날짜 일치 {krw[m_]['overlap']}")
        out["diag"]["krw"] = krw

    json.dump(out, open("_tb_wide.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print("\nRESULT_JSON: " + json.dumps(
        dict(frame="tb_wide", pivot_half=PIVOT_HALF, eq_frac=EQ_FRAC,
             cells={tf: dict(n=c["gate"]["n"], mean=c["gate"]["mean"], win=c["gate"]["win_rate"],
                             boot_p=c["gate"]["boot_p"], holm=c["holm_p"],
                             holdout_n=c["holdout"]["n"], holdout_mean=c["holdout"]["mean"],
                             calmar=(c["equity"] or {}).get("calmar"), verdict=c["verdict"])
                    for tf, c in out["cells"].items()}),
        ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
