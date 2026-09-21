"""
validate_tp1_slots.py — tp1_engulfing_1h 의 **동시 포지션 수(max_open)** 와 **수익 중 교체 규칙**
(사용자 지시 2026-09-21: "맥스오픈 2,3 로 올리면 어떻게 되는지 테스트" / "tp1 진행중일때 다른
신호 뜰경우 수익 구간 중이면 바로 익절 날리고 새로운 신호로 교체하면 어떻게 되는지 테스트").

계기: 2026-09-21 실측(fast 로그 100틱, 4.1일) — tp1 신호 13건 중 **10건이 max_open=1 캡에 막혀
스킵**됐다(체결 0.73/일, 신호 3.2/일). 막힌 신호를 받으면 어떻게 되는가가 이 판의 질문이다.

── 동결 (결과 보기 전) ────────────────────────────────────────────────────────
· 규칙 베이스는 실거래 그대로: engulfing 1h 롱(디텍터 인자 없음) · top20(1d 30봉 거래대금, 정적) ·
  익절 +1% / 손절 −8% · 3x · 왕복 수수료 0.2% · 2000봉 미해소는 그 봉 시가 청산 ·
  배리어는 신호봉 **다음 봉부터**, 같은 봉 동률은 **손절 우선**(보수) · 진입가 = 신호봉 종가.
· 포트(증거금) = `paper_executor.cap_margin` 규칙 그대로 — 시작 $70, **해소된 거래**만 곱셈 누적
  (pot ×= 1+ret×3), 손절로 $70 아래면 $70(loss_floor). 동시 포지션이 있어도 포트는 청산 시각순으로만
  갱신된다(실거래 cap_margin 이 trades 를 읽기 때문). **진입 시 증거금 = 그 시점 포트 전액**(실거래
  코드가 슬롯 수로 나누지 않는다) — 따라서 **max_open=N 이면 최대 노출이 N 배**가 된다. 이 성질이
  비교를 오염시키므로 노출 정합 진단 arm(`split`, 증거금 = 포트/N)을 함께 돌린다.
· 같은 종목·방향 중복 금지(`entry_blocked` 의 cap_keys 규칙) — 이미 그 종목을 들고 있으면 스킵.
· 같은 봉에 신호가 여럿이면 **시각 → 입력 순서**로 처리(실거래는 앙상블 점수순인데 tp1 은 전부
  D[1.0] 동점이라 순서가 사실상 입력순이다).

── arm ────────────────────────────────────────────────────────────────────────
· **max_open** ∈ {1(현행), 2, 3} 주 판정 / {4, 6, 8} 진단.
· **교체 규칙(replace)**: 슬롯이 꽉 찬 상태에서 새 신호가 뜨면, 열린 포지션 중 그 시각 종가 기준
  **총수익(gross)** 이 문턱을 넘는 것이 있으면 **가장 수익이 큰 것**을 그 종가에 시장가 청산하고
  (수수료 0.2% 차감) 새 신호로 교체한다. 없으면 종전대로 스킵.
  문턱 ∈ {None(현행·교체 없음), **0.0%(주 판정, 사용자 표현 "수익 구간 중이면")**, 0.2%(= 왕복
  수수료, 순수익 0), 0.5%} — 이번 틱에 진입한 포지션은 교체 대상이 아니다.
· **sizing** ∈ {full(실거래 충실, 증거금 = 포트 전액), split(노출 정합 진단, 포트/N)}.
· 주 판정 셀 4개: (1,None,full)=현행 · (2,None,full) · (3,None,full) · (1,0.0,full).
  나머지는 진단이고 **사후에 진단에서 골라 '살았다'고 하지 않는다**(validate_ih_exit 교훈).

── 판정량 ─────────────────────────────────────────────────────────────────────
· **계좌 손익 $ = Σ 증거금_i × ret_i × 3** (바닥 보전분은 계좌 부담이므로 포트 최종값은 척도가 아님).
· 병기: 거래 수 · 승률 · 건당 수익률 · MDD$(청산 시각순 실현 곡선) · 평균 보유 · 전후반 6개월 부호 ·
  시간가중 평균 동시보유 · 최대 동시보유 · 교체 발동 수 · 스킵 사유 분해.
· **DEPLOY_ON_PASS=False** — max_open·교체 규칙 변경은 사용자 결정. 실거래·DB 무관.

── 사전 확률 (결과 전 기록) ───────────────────────────────────────────────────
· 어제 격자(run 35562250210)에서 이 셀의 건당이 **−0.11%**(top20 1%/8%)였다. 건당이 음수인 규칙은
  거래를 늘리면 손실이 비례해 는다 → **full 에서 max_open 2·3 은 1 보다 나쁠 것**으로 본다.
  정보가 있는 곳은 거기가 아니라 **건당 수익률이 슬롯 수에 따라 변하는가**다 — 지금 막히는 신호
  77% 는 한 번도 측정된 적이 없고, 한 틱에 여러 개씩 몰려 오므로(9/18 14:03 에 3건) 체계적으로
  다를 수 있다. 어느 방향이든 그대로 보고한다. 크기는 적지 않는다.
· **교체 규칙은 나쁠 것으로 본다**, 기전까지 적어둔다: (a) 이기는 포지션만 잘라내고 지는 포지션은
  그대로 두므로 '승자를 짧게, 패자를 길게'가 된다 (b) 문턱 0% 는 **총수익 0~0.2% 구간에서 순손실을
  확정**한다(왕복 수수료 0.2%) — 사용자 표현의 '익절'이 실제로는 익절이 아닌 구간이 있다.
  다만 (c) 평균 보유 21시간이 짧아지고 회전이 빨라지는 이득이 있어 부호가 뒤집힐 여지는 남긴다.
· 노출 정합(split)에서는 슬롯 수 차이가 대부분 상쇄될 것으로 본다. 상쇄되지 않으면 그 잔차가
  '막힌 신호의 질'이다.

실행: python validate_tp1_slots.py [--no-fetch]   출력 _tp1_slots.json
"""
import json
import sys

import validate_tp1_stop as vs

FEE = vs.FEE
TP = vs.TP
SL = vs.LIVE_SL
LEV = vs.LEV
START = vs.START
MAX_SCAN = vs.MAX_SCAN
TOPN = vs.TOPN
DETMOD = vs.DETMOD

SLOTS_MAIN = (1, 2, 3)
SLOTS_DIAG = (4, 6, 8)
SLOTS = SLOTS_MAIN + SLOTS_DIAG
REPL_MAIN = (None, 0.0)
REPL_DIAG = (0.002, 0.005)
REPL = REPL_MAIN + REPL_DIAG
SIZINGS = ("full", "split")
LIVE_CELL = (1, None, "full")          # 현행
MAIN_CELLS = (LIVE_CELL, (2, None, "full"), (3, None, "full"), (1, 0.0, "full"))
DEPLOY_ON_PASS = False


def ts_index(rows):
    """봉 ts(ms) → 인덱스. 교체 규칙이 '다른 종목의 같은 시각 종가'를 봐야 해서 필요하다."""
    return {int(r["ts"]): i for i, r in enumerate(rows) if r.get("ts")}


def simulate(sigs, max_open=1, replace_thr=None, sizing="full",
             tp=TP, sl=SL, lev=LEV, start=START, max_scan=MAX_SCAN, fee=FEE):
    """
    동시 max_open 개까지 보유하는 이벤트 시뮬. sigs: [(sym, rows, si)].

    · 새 신호 시각마다 (1) 자연 청산(배리어/만기)이 그 시각 이전인 포지션을 먼저 닫고
      (2) 빈 슬롯이 있으면 진입, (3) 없으면 replace_thr 규칙, (4) 그래도 안 되면 스킵.
    · 증거금은 진입 시점 포트(=해소된 거래만 반영). full 이면 포트 전액, split 이면 포트/max_open.
    · max_open=1 · replace_thr=None · sizing="full" 은 validate_tp1_stop.simulate(sl) 과 동치
      (test_tp1_slots 가 거래 단위로 고정한다).
    """
    order = sorted(range(len(sigs)), key=lambda i: (vs.tnum(sigs[i][1], sigs[i][2]), i))
    tsidx = {}
    res = {}
    pot = start
    pnl = 0.0
    trades = []
    open_pos = []
    skipped_slot = skipped_dup = replaced = repl_nobar = 0

    def _close(p, ret, hold, reason, t_exit):
        nonlocal pot, pnl
        d = p["margin"] * ret * lev
        pnl += d
        trades.append(dict(sym=p["sym"], date=p["rows"][p["si"]]["date"], t=p["t"], t_exit=t_exit,
                           ret=ret, hold=hold, reason=reason,
                           margin=round(p["margin"], 2), pnl=round(d, 2)))
        pot = vs.pot_next(pot, ret, lev, start, floor=True)

    def _flush(until):
        """자연 청산 시각이 until 이하인 포지션을 청산 시각순으로 닫는다."""
        while True:
            due = [p for p in open_pos if p["x"] <= until]
            if not due:
                return
            p = min(due, key=lambda q: (q["x"], q["t"], q["sym"]))
            open_pos.remove(p)
            _close(p, p["ret"], p["hold"], p["reason"], p["x"])

    for i in order:
        sym, rows, si = sigs[i]
        e = vs.tnum(rows, si)
        _flush(e)
        key = (sym, si)
        if key not in res:
            res[key] = vs.resolve(rows, si, tp, sl, max_scan, fee)
        if res[key] is None:        # 마지막 봉 신호 등 — 교체로 남의 포지션을 닫기 전에 거른다
            continue
        if any(p["sym"] == sym for p in open_pos):       # 같은 종목·방향 중복 금지
            skipped_dup += 1
            continue
        if len(open_pos) >= max_open:
            if replace_thr is None:
                skipped_slot += 1
                continue
            ts = rows[si].get("ts")
            best = None
            for p in open_pos:
                if p["t"] >= e:                          # 이번 틱 진입분은 교체 대상 아님
                    continue
                if p["sym"] not in tsidx:
                    tsidx[p["sym"]] = ts_index(p["rows"])
                j = tsidx[p["sym"]].get(int(ts)) if ts else None
                if j is None or j <= p["si"]:
                    continue
                g = (p["rows"][j]["c"] - p["rows"][p["si"]]["c"]) / p["rows"][p["si"]]["c"]
                if g > replace_thr and (best is None or g > best[0]):
                    best = (g, p, j)
            if best is None:
                if ts is None:
                    repl_nobar += 1
                skipped_slot += 1
                continue
            g, p, j = best
            open_pos.remove(p)
            _close(p, g - fee, j - p["si"], "replaced", e)
            replaced += 1
        ret, hold, reason = res[key]
        margin = pot if sizing == "full" else pot / max_open
        xi = min(si + hold, len(rows) - 1)
        x = vs.tnum(rows, xi)
        open_pos.append(dict(sym=sym, rows=rows, si=si, t=e, x=(x if x > e else e + 1e-9),
                             ret=ret, hold=hold, reason=reason, margin=margin))
    _flush(float("inf"))

    trades.sort(key=lambda t: (t["t_exit"], t["t"], t["sym"]))
    n = len(trades)
    run = 0.0
    peak = 0.0
    mdd = 0.0
    for t in trades:
        run += t["pnl"]
        peak = max(peak, run)
        mdd = min(mdd, run - peak)
    wins = sum(1 for t in trades if t["ret"] > 0)
    mid = ((trades[0]["t"] + trades[-1]["t"]) / 2) if trades else None
    span = (max(t["t_exit"] for t in trades) - min(t["t"] for t in trades)) if trades else 0.0
    busy = sum(t["t_exit"] - t["t"] for t in trades)
    return dict(max_open=max_open, replace=replace_thr, sizing=sizing, n=n,
                skipped_slot=skipped_slot, skipped_dup=skipped_dup, replaced=replaced,
                repl_nobar=repl_nobar, wins=wins, win_rate=(wins / n) if n else None,
                mean_ret=(sum(t["ret"] for t in trades) / n) if n else None,
                pnl=round(pnl, 2), mdd=round(mdd, 2),
                worst=round(min((t["pnl"] for t in trades), default=0.0), 2),
                stops=sum(1 for t in trades if t["reason"] == "stop"),
                targets=sum(1 for t in trades if t["reason"] == "target"),
                opens=sum(1 for t in trades if t["reason"] == "open"),
                repl_ret=(sum(t["ret"] for t in trades if t["reason"] == "replaced") / replaced)
                if replaced else None,
                avg_hold=(sum(t["hold"] for t in trades) / n) if n else None,
                avg_open=(busy / span) if span > 0 else None,
                pot_final=round(pot, 2),
                h1=round(sum(t["pnl"] for t in trades if mid is not None and t["t"] < mid), 2),
                h2=round(sum(t["pnl"] for t in trades if mid is not None and t["t"] >= mid), 2),
                trades=trades)


def grid(sigs, slots=SLOTS, repl=REPL, sizings=SIZINGS):
    return [simulate(sigs, m, r, z) for z in sizings for r in repl for m in slots]


def pick(rows, max_open, replace_thr, sizing):
    for r in rows:
        if (r["max_open"] == max_open and r["sizing"] == sizing
                and ((r["replace"] is None) == (replace_thr is None))
                and (replace_thr is None or abs(r["replace"] - replace_thr) < 1e-12)):
            return r
    return None


def answer(rows):
    live = pick(rows, *LIVE_CELL)
    out = dict(live_pnl=live["pnl"], live_mean=live["mean_ret"], live_n=live["n"])
    for m in SLOTS_MAIN[1:]:
        r = pick(rows, m, None, "full")
        s = pick(rows, m, None, "split")
        out[f"slots{m}"] = dict(pnl=r["pnl"], n=r["n"], mean_ret=r["mean_ret"],
                                better_than_live=r["pnl"] > live["pnl"],
                                split_pnl=s["pnl"], split_better=s["pnl"] > live["pnl"],
                                both_halves_pos=(r["h1"] > 0 and r["h2"] > 0))
    rp = pick(rows, 1, 0.0, "full")
    out["replace0"] = dict(pnl=rp["pnl"], n=rp["n"], mean_ret=rp["mean_ret"],
                           replaced=rp["replaced"], repl_ret=rp["repl_ret"],
                           win_rate=rp["win_rate"],
                           better_than_live=rp["pnl"] > live["pnl"],
                           both_halves_pos=(rp["h1"] > 0 and rp["h2"] > 0))
    best = max(rows, key=lambda r: r["pnl"])
    out["best"] = dict(max_open=best["max_open"], replace=best["replace"], sizing=best["sizing"],
                       pnl=best["pnl"], positive=best["pnl"] > 0,
                       both_halves_pos=(best["h1"] > 0 and best["h2"] > 0))
    out["positive_cells"] = sum(1 for r in rows if r["pnl"] > 0)
    out["cells"] = len(rows)
    return out


def _r(v, w=6, p=2, pct=False, sign=True):
    if v is None:
        return " " * (w - 3) + "n/a"
    s = f"{v * 100:+.{p}f}%" if pct else (f"{v:+.{p}f}" if sign else f"{v:.{p}f}")
    return s.rjust(w)


def _fmt(rows, title, sizing):
    print(f"\n[{title}]")
    print(f"  {'슬롯':>4} {'교체':>6} {'n':>5} {'승률':>7} {'건당':>8} {'계좌손익$':>10} {'MDD$':>9} "
          f"{'익절':>5} {'손절':>5} {'교체':>5} {'교체건당':>8} {'보유h':>6} {'동시':>5} "
          f"{'슬롯스킵':>7} {'전반$':>9} {'후반$':>9}")
    for r in rows:
        if r["sizing"] != sizing:
            continue
        mark = ""
        if (r["max_open"], r["replace"], r["sizing"]) == LIVE_CELL:
            mark = " <= 현행"
        elif (r["max_open"], r["replace"], r["sizing"]) in MAIN_CELLS:
            mark = " <= 주판정"
        rep = "  없음" if r["replace"] is None else f"{r['replace'] * 100:5.1f}%"
        print(f"  {r['max_open']:4d} {rep} {r['n']:5d} "
              f"{(r['win_rate'] * 100):6.2f}% {_r(r['mean_ret'], 8, 2, pct=True)} "
              f"{r['pnl']:+10.2f} {r['mdd']:+9.2f} {r['targets']:5d} {r['stops']:5d} "
              f"{r['replaced']:5d} {_r(r['repl_ret'], 8, 2, pct=True)} "
              f"{(r['avg_hold'] or 0):6.1f} {(r['avg_open'] or 0):5.2f} {r['skipped_slot']:7d} "
              f"{r['h1']:+9.2f} {r['h2']:+9.2f}{mark}")


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    import validate_regime_split_all as va
    syms = va._syms()
    print(f"[표본] {len(syms)}종목 · {DETMOD} 롱 · 1h 365일 · 익절 {TP:.0%}/손절 {SL:.0%} 고정 · {LEV}x")
    print(f"[arm] max_open {SLOTS} × 교체문턱 {REPL} × 사이징 {SIZINGS} = "
          f"{len(SLOTS) * len(REPL) * len(SIZINGS)}셀")
    print(f"[반영] DEPLOY_ON_PASS={DEPLOY_ON_PASS} — 진단. max_open·교체 규칙 변경은 사용자 결정\n")
    if "--no-fetch" not in argv:
        va.fetch(syms, ["1d", "1h"])
    rows1d = va.load_tf(syms, "1d")
    rows1h = va.load_tf(syms, "1h")
    if not rows1h:
        print("[1h] 데이터 없음")
        return 1
    ranked = vs.turnover_rank(rows1d)
    top = [s for s in ranked[:TOPN] if s in rows1h]
    print(f"[코호트] top{TOPN}: {top}")
    nb = sum(len(v) for v in rows1h.values())
    first = min(r["date"] for rows in rows1h.values() for r in rows)
    last = max(r["date"] for rows in rows1h.values() for r in rows)
    print(f"[1h] {len(rows1h)}종목 {nb:,}봉 {first} ~ {last}")

    out = {}
    for label, syms_c in (("top20", top), ("all", list(rows1h))):
        sigs = vs.signals({s: rows1h[s] for s in syms_c if s in rows1h})
        print(f"\n[{label}] 신호 {len(sigs)}건")
        rows = grid(sigs)
        _fmt(rows, f"{label} — full(증거금=포트 전액, 실거래 충실)", "full")
        _fmt(rows, f"{label} — split(증거금=포트/슬롯, 노출 정합 진단)", "split")
        a = answer(rows)
        print(f"\n  → 현행(슬롯1·교체없음) ${a['live_pnl']:+.2f} · 건당 {a['live_mean'] * 100:+.2f}% · n={a['live_n']}")
        for m in SLOTS_MAIN[1:]:
            d = a[f"slots{m}"]
            print(f"  → 슬롯 {m}: ${d['pnl']:+.2f} (n={d['n']}, 건당 {d['mean_ret'] * 100:+.2f}%) "
                  f"| 현행보다 나은가: {d['better_than_live']} | 노출정합 ${d['split_pnl']:+.2f} → {d['split_better']}")
        d = a["replace0"]
        print(f"  → 교체(수익 중이면 즉시 청산·슬롯1): ${d['pnl']:+.2f} (n={d['n']}, 건당 "
              f"{d['mean_ret'] * 100:+.2f}%, 승률 {d['win_rate'] * 100:.1f}%, 교체 {d['replaced']}건 "
              f"건당 {(d['repl_ret'] or 0) * 100:+.2f}%) | 현행보다 나은가: {d['better_than_live']}")
        b = a["best"]
        print(f"  → 격자 최대 셀: 슬롯 {b['max_open']} 교체 {b['replace']} {b['sizing']} "
              f"${b['pnl']:+.2f} | 양수: {b['positive']} | 전후반 둘 다 양수: {b['both_halves_pos']} "
              f"| 양수 셀 {a['positive_cells']}/{a['cells']}")
        out[label] = dict(answer=a, n_signals=len(sigs),
                          rows=[{k: v for k, v in r.items() if k != "trades"} for r in rows])
    out["config"] = dict(tp=TP, sl=SL, lev=LEV, start=START, fee=FEE, max_scan=MAX_SCAN,
                         topn=TOPN, detmod=DETMOD, slots=SLOTS, replace=REPL, sizings=SIZINGS,
                         main_cells=[list(c) for c in MAIN_CELLS], window=[first, last],
                         deploy_on_pass=DEPLOY_ON_PASS, top20=top)
    json.dump(out, open("_tp1_slots.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n[저장] _tp1_slots.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
