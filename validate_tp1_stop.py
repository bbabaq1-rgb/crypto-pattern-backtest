"""
validate_tp1_stop.py — tp1_engulfing_1h 의 **손절 컷 스윕** (사용자 질문 2026-09-19).

질문: "1년 동안 이 3배 레버리지 기준으로 손절컷을 8%로 잡는데 최대이익을 달성할 수 있는
손절컷 맞는지 다시 확인해줘". 실거래 규칙(engulfing 1h 롱 · top20 · 익절 +1% · 3x ·
한 번에 1포지션 · 포트 = max(포트×(1+ret×3), $70)) 을 그대로 두고 **손절 % 만** 바꿔
1년 계좌 손익($)을 비교한다.

── 동결 (결과 보기 전) ────────────────────────────────────────────────────────
· 신호: detector_engulfing.detect(rows) **인자 없이** — 실거래 신호 집합과 동일.
· 코호트: **top20** = 1d 30봉 평균 (close×volume) 상위 20 (scheduler._volume_ranked 와 같은 정의,
  데이터 끝 시점 정적 — 실거래가 쓰는 것과 같다). all(80) 은 진단.
· 창: 1h 최근 365일 전부. 홀드아웃 없음 — **판정이 아니라 사용자 질문에 답하는 진단**이다.
· 청산: 익절 +1% 고정, 손절 ∈ {1,2,3,4,5,6,7,8,10,12,15,20}%. 신호봉 **다음 봉부터** 고가/저가로
  교차 판정, 같은 봉에 둘 다 닿으면 **손절 우선**(보수). 2000봉 미해소는 그 봉 시가 청산.
· 순차 시뮬(실거래 max_open=1): 진입 시각순, 보유 중 신호는 버린다. 진입가 = 신호봉 종가
  (실거래는 다음 틱 시장가 — 실측 슬리피지 +0.02~+0.62%, 여기서는 0).
· 사이징: 3x, 포트 = 시작 $70 · 익절 곱셈 · 손절로 $70 밑이면 $70(loss_floor, 2026-09-19 현행).
  **계좌 손익($) = Σ 증거금_i × ret_i × 3** — 이것이 진짜 이익이다. 포트 최종값은 바닥이 계좌
  돈으로 메워지므로 이익의 척도가 아니다(참고로만 병기).
· 수수료 왕복 0.2%(FEE) — ret 에 이미 차감.
· **주 답변**: top20 에서 계좌 손익($)이 최대인 손절 %. 8% 가 최대인지, 최대와 몇 $ 차이인지,
  최대 자체가 양수인지. 전반/후반 6개월 부호를 병기(한쪽에서만 이기면 우연).
· DEPLOY_ON_PASS=False — 손절 % 변경은 사용자 결정. 실거래·DB 무관.

── 사전 확률 (결과 전 기록) ───────────────────────────────────────────────────
· tp_1h(run 34317260194)에서 T1S3/T1S8/T1S20/무손절 건당 전부 음수(−0.28~−0.49%)였다 — 순차
  시뮬로 좁혀도 **어느 손절도 양수 계좌 손익을 못 낼 가능성이 높다.** 그렇다면 '최적 손절'은
  '가장 덜 잃는 손절'이다. 실거래 7승 1패는 표본 8건이라 이 판과 상충해도 어느 쪽도 못 이긴다.
· 손절이 좁을수록 순환이 빨라 수수료를 더 자주 내고, 넓을수록 한 번 손실이 커진다.
  1년 창(2025-09~2026-09, bear 지배)에서는 좁은 쪽이 덜 잃을 것으로 본다. 크기는 적지 않는다.

실행: python validate_tp1_stop.py [--no-fetch]   출력 _tp1_stop.json
"""
import importlib
import json
import sys
from datetime import date as _date, timedelta as _td

import method_t as mt
import validate_regime_split_all as va

FEE = mt.FEE
TP = 0.01
SL_GRID = (0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.10, 0.12, 0.15, 0.20)
LIVE_SL = 0.08
LEV = 3
START = 70.0
MAX_SCAN = 2000
TOPN = 20
DETMOD = "detector_engulfing"
DEPLOY_ON_PASS = False


def resolve(rows, si, tp, sl, max_scan=MAX_SCAN, fee=FEE):
    """신호봉 si 다음 봉부터 첫 교차. (ret, hold, reason). 동률은 손절(보수)."""
    base = rows[si]["c"]
    if base <= 0 or si + 1 >= len(rows):
        return None
    end = min(si + max_scan, len(rows) - 1)
    for j in range(si + 1, end + 1):
        r = rows[j]
        up = (r["h"] - base) / base >= tp
        dn = (base - r["l"]) / base >= sl
        if dn:                         # 손절 우선(같은 봉 동률 포함)
            return -sl - fee, j - si, "stop"
        if up:
            return tp - fee, j - si, "target"
    px = rows[end]["o"]
    return (px - base) / base - fee, end - si, "open"


def tnum(rows, i):
    """봉 ts(ms) → 분수 일수. ts 없으면 date + 봉 인덱스 분수(1h 가정)."""
    r = rows[i]
    if r.get("ts"):
        return float(r["ts"]) / 86400000.0
    d = _date(*(int(x) for x in r["date"].split("-")))
    return float(d.toordinal()) + (i % 24) / 24.0


def turnover_rank(rows1d_by, n=30):
    scored = []
    for s, rows in rows1d_by.items():
        if len(rows) < n + 5:
            continue
        qv = sum(r["c"] * r["v"] for r in rows[-n:]) / n
        scored.append((s, qv))
    scored.sort(key=lambda x: -x[1])
    return [s for s, _ in scored]


def signals(rows_by, detmod=DETMOD):
    mod = importlib.import_module(detmod)
    out = []
    for sym, rows in rows_by.items():
        if len(rows) < 40:
            continue
        for si in mod.detect(rows):          # 인자 없이 — 실거래 신호 집합
            if si + 1 < len(rows):
                out.append((sym, rows, si))
    return out


def pot_next(pot, ret, lev=LEV, start=START, floor=True):
    """paper_executor.cap_margin 의 loss_floor 규칙 한 스텝."""
    pot *= (1.0 + ret * lev)
    if floor and ret < 0 and pot < start:
        pot = start
    return pot


def simulate(sigs, sl, tp=TP, lev=LEV, start=START, max_scan=MAX_SCAN):
    """
    순차 단일 포지션. sigs: [(sym, rows, si)]. 진입 시각순, 보유 중 신호는 버린다.
    반환: 거래 리스트 + 계좌 손익 요약. 계좌 손익 = Σ margin×ret×lev (바닥 보전분은 계좌 부담).
    """
    ordered = sorted(range(len(sigs)), key=lambda i: (tnum(sigs[i][1], sigs[i][2]), i))
    busy = None
    pot = start
    pot_pure = start
    pnl = 0.0
    peak = 0.0
    mdd = 0.0
    trades = []
    skipped = 0
    for i in ordered:
        sym, rows, si = sigs[i]
        e = tnum(rows, si)
        if busy is not None and e < busy:
            skipped += 1
            continue
        o = resolve(rows, si, tp, sl, max_scan)
        if o is None:
            continue
        ret, hold, reason = o
        margin = pot
        d = margin * ret * lev
        pnl += d
        peak = max(peak, pnl)
        mdd = min(mdd, pnl - peak)
        trades.append(dict(sym=sym, date=rows[si]["date"], t=e, ret=ret, hold=hold,
                           reason=reason, margin=round(margin, 2), pnl=round(d, 2)))
        pot = pot_next(pot, ret, lev, start, floor=True)
        pot_pure = pot_pure * (1.0 + ret * lev)
        xi = min(si + hold, len(rows) - 1)
        x = tnum(rows, xi)
        busy = x if x > e else e + 1e-9
    n = len(trades)
    wins = sum(1 for t in trades if t["ret"] > 0)
    be = (sl + FEE) / (tp + sl)
    mid = None
    if trades:
        t0, t1 = trades[0]["t"], trades[-1]["t"]
        mid = (t0 + t1) / 2
    h1 = sum(t["pnl"] for t in trades if mid is not None and t["t"] < mid)
    h2 = sum(t["pnl"] for t in trades if mid is not None and t["t"] >= mid)
    return dict(sl=sl, n=n, skipped=skipped, wins=wins,
                win_rate=(wins / n) if n else None, breakeven=be,
                mean_ret=(sum(t["ret"] for t in trades) / n) if n else None,
                pnl=round(pnl, 2), mdd=round(mdd, 2),
                worst=round(min((t["pnl"] for t in trades), default=0.0), 2),
                stops=sum(1 for t in trades if t["reason"] == "stop"),
                opens=sum(1 for t in trades if t["reason"] == "open"),
                avg_hold=(sum(t["hold"] for t in trades) / n) if n else None,
                pot_final=round(pot, 2), pot_pure=round(pot_pure, 2),
                h1=round(h1, 2), h2=round(h2, 2),
                floor_topups=sum(1 for k in range(1, n) if trades[k]["margin"] == start
                                 and trades[k - 1]["ret"] < 0),
                trades=trades)


def sweep(sigs, grid=SL_GRID):
    return [simulate(sigs, sl) for sl in grid]


def answer(rows):
    """주 답변: 계좌 손익 최대 손절, 8% 와의 차이, 최대가 양수인가."""
    best = max(rows, key=lambda r: r["pnl"])
    live = next(r for r in rows if abs(r["sl"] - LIVE_SL) < 1e-12)
    return dict(best_sl=best["sl"], best_pnl=best["pnl"], live_sl=LIVE_SL, live_pnl=live["pnl"],
                gap=round(best["pnl"] - live["pnl"], 2), best_positive=best["pnl"] > 0,
                live_is_best=abs(best["sl"] - LIVE_SL) < 1e-12,
                best_both_halves_pos=(best["h1"] > 0 and best["h2"] > 0))


def _fmt(rows, title):
    print(f"\n[{title}]")
    print(f"  {'손절':>5} {'n':>4} {'승률':>6} {'분기':>6} {'건당':>7} {'계좌손익$':>9} {'MDD$':>8} "
          f"{'최악$':>7} {'손절수':>5} {'보유h':>6} {'전반$':>8} {'후반$':>8} {'포트':>7} {'순수복리':>8}")
    for r in rows:
        mark = " <= 현행" if abs(r["sl"] - LIVE_SL) < 1e-12 else ""
        wr = f"{r['win_rate']*100:5.1f}%" if r["win_rate"] is not None else "   n/a"
        mr = f"{r['mean_ret']*100:+6.2f}%" if r["mean_ret"] is not None else "    n/a"
        ah = f"{r['avg_hold']:6.1f}" if r["avg_hold"] is not None else "   n/a"
        print(f"  {r['sl']*100:4.0f}% {r['n']:4d} {wr} {r['breakeven']*100:5.1f}% {mr} "
              f"{r['pnl']:+9.2f} {r['mdd']:+8.2f} {r['worst']:+7.2f} {r['stops']:5d} {ah} "
              f"{r['h1']:+8.2f} {r['h2']:+8.2f} {r['pot_final']:7.2f} {r['pot_pure']:8.2f}{mark}")


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    syms = va._syms()
    print(f"[표본] {len(syms)}종목 · {DETMOD} 롱 · 1h 365일 · 익절 {TP:.0%} 고정 · 손절 "
          f"{[f'{x:.0%}' for x in SL_GRID]} · {LEV}x · 포트 시작 ${START:.0f} 바닥 규칙")
    print(f"[반영] DEPLOY_ON_PASS={DEPLOY_ON_PASS} — 진단. 손절 변경은 사용자 결정\n")
    if "--no-fetch" not in argv:
        va.fetch(syms, ["1d", "1h"])
    rows1d = va.load_tf(syms, "1d")
    rows1h = va.load_tf(syms, "1h")
    if not rows1h:
        print("[1h] 데이터 없음")
        return 1
    ranked = turnover_rank(rows1d)
    top = [s for s in ranked[:TOPN] if s in rows1h]
    print(f"[코호트] top{TOPN}: {top}")
    nb = sum(len(v) for v in rows1h.values())
    first = min(r["date"] for rows in rows1h.values() for r in rows)
    last = max(r["date"] for rows in rows1h.values() for r in rows)
    print(f"[1h] {len(rows1h)}종목 {nb:,}봉 {first} ~ {last}")

    out = {}
    for label, syms_c in (("top20", top), ("all", list(rows1h))):
        sigs = signals({s: rows1h[s] for s in syms_c if s in rows1h})
        print(f"\n[{label}] 신호 {len(sigs)}건 (순차 시뮬에서 보유 중 신호는 버림)")
        rows = sweep(sigs)
        _fmt(rows, f"{label} — 익절 1% 고정, 손절 스윕, 3x, 순차 1포지션, 포트 바닥 $70")
        a = answer(rows)
        print(f"  → 계좌손익 최대 손절 {a['best_sl']:.0%} (${a['best_pnl']:+.2f}) | 현행 8% ${a['live_pnl']:+.2f} | "
              f"차이 ${a['gap']:+.2f} | 최대가 양수: {a['best_positive']} | 최대 셀 전후반 둘 다 양수: "
              f"{a['best_both_halves_pos']}")
        out[label] = dict(answer=a, n_signals=len(sigs),
                          rows=[{k: v for k, v in r.items() if k != "trades"} for r in rows],
                          trades_live={r["sl"]: r["trades"] for r in rows if abs(r["sl"] - LIVE_SL) < 1e-12})
    out["config"] = dict(tp=TP, sl_grid=SL_GRID, lev=LEV, start=START, max_scan=MAX_SCAN, fee=FEE,
                         topn=TOPN, detmod=DETMOD, window=[first, last], deploy_on_pass=DEPLOY_ON_PASS,
                         top20=top)
    json.dump(out, open("_tp1_stop.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n[저장] _tp1_stop.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
