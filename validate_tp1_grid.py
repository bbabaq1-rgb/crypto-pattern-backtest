"""
validate_tp1_grid.py — tp1_engulfing_1h **익절 × 손절 2차원 격자** (사용자 지시 2026-09-21
"익절 축 추가해서 1h로 돌려줘").

어제 판(validate_tp1_stop)은 익절 1% 고정·손절만 스윕했다. 이번엔 익절도 축으로 놓고
**1h 365일**에서 잰다. 실거래 규칙(engulfing 1h 롱 · top20 · 3x · 한 번에 1포지션 ·
포트 = max(포트×(1+ret×3), $70)) 은 그대로.

── 왜 도는가 (사용자 질문의 계산과 그 한계) ──────────────────────────────────
손익분기 = (SL+수수료)/(TP+SL) 이므로 익절 1%→2% 면 91.11%→82.00% 로 내려간다.
그러나 랜덤워크 도달률도 88.89%→80.00% 로 같이 내려가 **필요 리프트는 2.22%p→2.00%p**
로 거의 안 변한다. 건당 기대값을 정리하면

    EV = −δ × (TP + SL) − 수수료        (δ = 랜덤워크 대비 실측 승률 부족분)

이고 **수수료 항이 TP 와 무관하게 고정**이다. δ 가 TP 에 관계없이 일정하다면 익절을
넓혀도 건당은 오히려 미세하게 나빠진다(−0.280 → −0.289 → −0.298%).

**그래서 이 판의 실제 질문은 하나다 — δ 가 TP 에 따라 변하는가.** 좁은 배리어일수록
봉 안 순서를 못 봐서(동률) 보수 편향이 크고, 넓을수록 갭·팻테일 영향이 다르다.
δ(TP) 는 계산으로 못 얻고 측정해야 한다. 아래 랜덤 진입 베이스라인이 그것을 잰다.

── 동결 (결과 보기 전) ────────────────────────────────────────────────────────
· 신호: detector_engulfing.detect(rows) **인자 없이** — 실거래 신호 집합과 동일.
· 코호트: **top20**(1d 30봉 평균 close×volume 상위 20, 정적) 주 판정 / all(80) 진단.
· 창: 1h 최근 365일 전부. 홀드아웃 없음 — **판정이 아니라 진단**이다.
· 격자: 익절 ∈ {1, 1.5, 2, 2.5, 3}% × 손절 ∈ {1,2,3,4,5,6,7,8,10,12,15,20}% = **60셀**.
· 청산: 신호봉 **다음 봉부터** 고가/저가 교차, 같은 봉 동률은 **손절 우선**(보수).
  2000봉 미해소는 그 봉 시가 청산. — 어제 판과 같은 규칙(테스트가 전 셀 일치 고정).
· 순차 시뮬(실거래 max_open=1): 진입 시각순, 보유 중 신호는 버린다. 진입가 = 신호봉 종가.
· 사이징: 3x, 포트 시작 $70 · 손절로 $70 밑이면 $70(loss_floor 현행). 수수료 왕복 0.2%.
· **판정량: 계좌 손익($) = Σ 증거금_i × ret_i × 3.** 포트 최종값은 바닥이 계좌 돈으로
  메워지므로 이익의 척도가 아니다(참고 병기).
· **랜덤 진입 베이스라인**: 같은 코호트·창에서 무작위 (종목, 봉) RAND_N=3000 건(시드 고정)에
  같은 격자를 적용. δ = 이론 도달률 − 랜덤 실측 도달률, 패턴 엣지 = 패턴 승률 − 랜덤 승률.
· **주 답변**: (a) 계좌 손익이 최대인 (익절,손절) 셀과 그 값의 부호 (b) 익절 2%/손절 8% 가
  현행 1%/8% 보다 나은가 (c) δ 가 익절에 따라 변하는가. 전반/후반 6개월 부호 병기.
· DEPLOY_ON_PASS=False — 익절·손절 변경은 사용자 결정. 실거래·DB 무관.

── 사전 확률 (결과 전 기록) ───────────────────────────────────────────────────
· **공개**: 위 폐형 EV 식과 δ=0.89%p(tp_1h T1S8 이론 88.89% vs 실측 88.00%) 대입값을
  실행 전 대화에서 이미 계산해 보고했다. 따라서 이건 '눈 감은 예측'이 아니다.
· 그 가정(δ 일정)대로면 **60셀 전부 음수**이고 건당은 익절이 넓을수록 미세하게 나쁘다.
· **다만 계좌 손익($)은 건당 × 거래수라 순위가 뒤집힐 수 있다** — 익절이 넓으면 보유가
  길어져 순차 1포지션에서 거래 수가 줄고, 총손실도 줄 수 있다. 여기는 예측하지 않는다.
· 동률 비율은 tp_1h 실측으로 1h 에서 T1S1 5.7% / T1S3 0.9% / T1S8 0.1% 였다 — 좁은 손절
  셀일수록 '손절 우선' 보수 규칙의 페널티가 크다. 셀별 동률 비율을 병기해 드러낸다.
· 실거래 10승 0패(표본 10)는 이 판과 상충해도 어느 쪽도 못 이긴다.

실행: python validate_tp1_grid.py [--no-fetch]   출력 _tp1_grid.json
"""
import json
import random
import sys

import validate_regime_split_all as va
import validate_tp1_stop as vs

# 어제 판과 같은 정의를 그대로 쓴다(테스트가 동일성을 고정)
FEE = vs.FEE
LEV = vs.LEV
START = vs.START
MAX_SCAN = vs.MAX_SCAN
TOPN = vs.TOPN
DETMOD = vs.DETMOD
turnover_rank = vs.turnover_rank
signals = vs.signals
pot_next = vs.pot_next
tnum = vs.tnum

TP_GRID = (0.010, 0.015, 0.020, 0.025, 0.030)
SL_GRID = vs.SL_GRID
LIVE_TP = 0.01
LIVE_SL = 0.08
ASK_TP = 0.02                      # 사용자가 물은 셀
RAND_N = 3000
RAND_SEED = 20260921
DEPLOY_ON_PASS = False

# first_hits 의 포인터 1개 스캔은 임계값이 **오름차순**일 때만 옳다(최초 도달 봉이
# 임계값에 대해 비감소). 격자를 손대면 여기서 먼저 깨지게 둔다.
assert list(TP_GRID) == sorted(TP_GRID) and list(SL_GRID) == sorted(SL_GRID)


# ── 전방 스캔 1회로 전 임계값의 최초 도달 봉 ────────────────────────────────────
def first_hits(rows, si, tps=TP_GRID, sls=SL_GRID, max_scan=MAX_SCAN):
    """
    신호봉 si 다음 봉부터 한 번만 스캔해 tps/sls 각 임계값의 **최초 도달 봉**을 구한다.
    tps·sls 는 오름차순이어야 한다(최초 도달 봉이 임계값에 대해 비감소이므로 포인터 1개로 충분).
    반환 None(무효) 또는 dict(base, end, tp_bar, sl_bar) — 미도달은 None.
    """
    base = rows[si]["c"]
    if base <= 0 or si + 1 >= len(rows):
        return None
    end = min(si + max_scan, len(rows) - 1)
    tp_bar = [None] * len(tps)
    sl_bar = [None] * len(sls)
    ti = 0
    li = 0
    for j in range(si + 1, end + 1):
        r = rows[j]
        up = (r["h"] - base) / base
        dn = (base - r["l"]) / base
        while ti < len(tps) and tps[ti] <= up:
            tp_bar[ti] = j
            ti += 1
        while li < len(sls) and sls[li] <= dn:
            sl_bar[li] = j
            li += 1
        if ti == len(tps) and li == len(sls):
            break
    return dict(base=base, end=end, tp_bar=tp_bar, sl_bar=sl_bar)


def resolve_hits(rows, si, hits, ti, li, tp, sl, fee=FEE):
    """
    first_hits 결과로 한 셀을 해소. vs.resolve(rows, si, tp, sl) 와 **완전 동일**해야 한다
    (test_tp1_grid 가 합성·실데이터 전 셀 일치로 고정).
    반환 (ret, hold, reason, tie).
    """
    jt = hits["tp_bar"][ti]
    jl = hits["sl_bar"][li]
    tie = jt is not None and jl is not None and jt == jl
    if jl is not None and (jt is None or jl <= jt):     # 동률 포함 손절 우선
        return -sl - fee, jl - si, "stop", tie
    if jt is not None:
        return tp - fee, jt - si, "target", tie
    end = hits["end"]
    px = rows[end]["o"]
    return (px - hits["base"]) / hits["base"] - fee, end - si, "open", False


# ── 표본 준비 ──────────────────────────────────────────────────────────────────
def prepare(sigs):
    """[(sym, rows, si)] → 전방 스캔 1회씩 미리 돌린 레코드 목록(진입 시각순)."""
    out = []
    for sym, rows, si in sigs:
        h = first_hits(rows, si)
        if h is None:
            continue
        out.append(dict(sym=sym, rows=rows, si=si, t=tnum(rows, si), hits=h))
    out.sort(key=lambda r: r["t"])
    return out


def random_entries(rows_by, n=RAND_N, seed=RAND_SEED):
    """같은 코호트·창에서 무작위 진입 — δ(배리어+가격과정) 측정용."""
    rng = random.Random(seed)
    pool = [(s, i) for s, rows in rows_by.items() for i in range(len(rows) - 1)]
    if not pool:
        return []
    picks = [pool[rng.randrange(len(pool))] for _ in range(n)]
    return prepare([(s, rows_by[s], i) for s, i in picks])


# ── 셀 평가 ────────────────────────────────────────────────────────────────────
def simulate(recs, ti, li, tp, sl, lev=LEV, start=START):
    """순차 단일 포지션(실거래 max_open=1). recs 는 prepare() 결과(진입 시각순)."""
    busy = None
    pot = start
    pot_pure = start
    pnl = peak = mdd = 0.0
    trades = []
    skipped = ties = 0
    for rec in recs:
        e = rec["t"]
        if busy is not None and e < busy:
            skipped += 1
            continue
        ret, hold, reason, tie = resolve_hits(rec["rows"], rec["si"], rec["hits"], ti, li, tp, sl)
        ties += int(tie)
        margin = pot
        d = margin * ret * lev
        pnl += d
        peak = max(peak, pnl)
        mdd = min(mdd, pnl - peak)
        trades.append(dict(sym=rec["sym"], date=rec["rows"][rec["si"]]["date"], t=e,
                           ret=ret, hold=hold, reason=reason,
                           margin=round(margin, 2), pnl=round(d, 2)))
        pot = pot_next(pot, ret, lev, start, floor=True)
        pot_pure *= (1.0 + ret * lev)
        xi = min(rec["si"] + hold, len(rec["rows"]) - 1)
        x = tnum(rec["rows"], xi)
        busy = x if x > e else e + 1e-9
    n = len(trades)
    wins = sum(1 for t in trades if t["ret"] > 0)
    mid = (trades[0]["t"] + trades[-1]["t"]) / 2 if trades else None
    h1 = sum(t["pnl"] for t in trades if mid is not None and t["t"] < mid)
    h2 = sum(t["pnl"] for t in trades if mid is not None and t["t"] >= mid)
    return dict(tp=tp, sl=sl, n=n, skipped=skipped, wins=wins,
                win_rate=(wins / n) if n else None,
                breakeven=(sl + FEE) / (tp + sl), martingale=sl / (tp + sl),
                mean_ret=(sum(t["ret"] for t in trades) / n) if n else None,
                pnl=round(pnl, 2), mdd=round(mdd, 2),
                worst=round(min((t["pnl"] for t in trades), default=0.0), 2),
                stops=sum(1 for t in trades if t["reason"] == "stop"),
                opens=sum(1 for t in trades if t["reason"] == "open"),
                tie_rate=(ties / n) if n else None,
                avg_hold=(sum(t["hold"] for t in trades) / n) if n else None,
                pot_final=round(pot, 2), pot_pure=round(pot_pure, 2),
                h1=round(h1, 2), h2=round(h2, 2), trades=trades)


def baseline(recs, ti, li, tp, sl):
    """랜덤 진입 — 순차 시뮬 없이 도달률·건당만(δ 측정용)."""
    rets = []
    wins = ties = 0
    for rec in recs:
        ret, _h, reason, tie = resolve_hits(rec["rows"], rec["si"], rec["hits"], ti, li, tp, sl)
        rets.append(ret)
        wins += int(ret > 0)
        ties += int(tie)
    n = len(rets)
    return dict(n=n, win_rate=(wins / n) if n else None,
                mean_ret=(sum(rets) / n) if n else None,
                tie_rate=(ties / n) if n else None)


def grid(recs, rand_recs=None, tps=TP_GRID, sls=SL_GRID):
    rows = []
    for ti, tp in enumerate(tps):
        for li, sl in enumerate(sls):
            r = simulate(recs, ti, li, tp, sl)
            if rand_recs:
                b = baseline(rand_recs, ti, li, tp, sl)
                r["rand_win"] = b["win_rate"]
                r["rand_mean"] = b["mean_ret"]
                r["rand_tie"] = b["tie_rate"]
                r["delta"] = (r["martingale"] - b["win_rate"]) if b["win_rate"] is not None else None
                r["edge"] = ((r["win_rate"] - b["win_rate"])
                             if (r["win_rate"] is not None and b["win_rate"] is not None) else None)
            rows.append(r)
    return rows


def answer(rows):
    """주 답변 3개."""
    def cell(tp, sl):
        return next((r for r in rows if abs(r["tp"] - tp) < 1e-12 and abs(r["sl"] - sl) < 1e-12), None)
    best = max(rows, key=lambda r: r["pnl"])
    live = cell(LIVE_TP, LIVE_SL)
    ask = cell(ASK_TP, LIVE_SL)
    best_tp = {}
    for tp in sorted({r["tp"] for r in rows}):
        b = max((r for r in rows if abs(r["tp"] - tp) < 1e-12), key=lambda r: r["pnl"])
        best_tp[f"{tp:.3f}"] = dict(sl=b["sl"], pnl=b["pnl"])
    return dict(
        best_tp=best["tp"], best_sl=best["sl"], best_pnl=best["pnl"],
        best_positive=best["pnl"] > 0,
        best_both_halves_pos=(best["h1"] > 0 and best["h2"] > 0),
        live_pnl=live["pnl"] if live else None,
        ask_pnl=ask["pnl"] if ask else None,
        ask_beats_live=(ask["pnl"] > live["pnl"]) if (ask and live) else None,
        ask_vs_live=round(ask["pnl"] - live["pnl"], 2) if (ask and live) else None,
        any_positive=sum(1 for r in rows if r["pnl"] > 0),
        best_per_tp=best_tp,
        delta_by_tp={f"{tp:.3f}": round(
            sum(r["delta"] for r in rows if abs(r["tp"] - tp) < 1e-12 and r.get("delta") is not None)
            / max(1, sum(1 for r in rows if abs(r["tp"] - tp) < 1e-12 and r.get("delta") is not None)), 5)
            for tp in sorted({r["tp"] for r in rows})} if any("delta" in r for r in rows) else None)


# ── 출력 ───────────────────────────────────────────────────────────────────────
def _matrix(rows, key, title, fmt="{:+8.1f}", scale=1.0):
    tps = sorted({r["tp"] for r in rows})
    sls = sorted({r["sl"] for r in rows})
    print(f"\n[{title}]")
    print("  익절\\손절 " + "".join(f"{s*100:8.0f}%" for s in sls))
    for tp in tps:
        line = f"  {tp*100:6.1f}%  "
        for sl in sls:
            r = next(x for x in rows if abs(x["tp"] - tp) < 1e-12 and abs(x["sl"] - sl) < 1e-12)
            v = r.get(key)
            line += (fmt.format(v * scale) + " ") if v is not None else "     n/a "
        mark = "  <= 현행 익절" if abs(tp - LIVE_TP) < 1e-12 else ("  <= 질문" if abs(tp - ASK_TP) < 1e-12 else "")
        print(line + mark)


def _pct(v, w=6, d=2):
    return f"{v * 100:{w}.{d}f}%" if v is not None else "   n/a"


def _slice(rows, sl, title):
    print(f"\n[{title}]")
    print(f"  {'익절':>5} {'n':>4} {'승률':>7} {'분기':>7} {'이론':>7} {'랜덤':>7} {'δ':>7} {'엣지':>7} "
          f"{'건당':>7} {'계좌$':>8} {'MDD$':>8} {'손절수':>5} {'보유h':>6} {'동률':>6} "
          f"{'전반$':>8} {'후반$':>8} {'포트':>7}")
    for r in [x for x in rows if abs(x["sl"] - sl) < 1e-12]:
        ah = f"{r['avg_hold']:6.1f}" if r["avg_hold"] is not None else "   n/a"
        mark = " <= 현행" if abs(r["tp"] - LIVE_TP) < 1e-12 else (
            " <= 질문" if abs(r["tp"] - ASK_TP) < 1e-12 else "")
        print(f"  {r['tp']*100:4.1f}% {r['n']:4d} {_pct(r['win_rate'])} {_pct(r['breakeven'])} "
              f"{_pct(r['martingale'])} {_pct(r.get('rand_win'))} {_pct(r.get('delta'))} "
              f"{_pct(r.get('edge'))} {_pct(r['mean_ret'])} {r['pnl']:+8.2f} {r['mdd']:+8.2f} "
              f"{r['stops']:5d} {ah} {_pct(r['tie_rate'], 4, 1)} "
              f"{r['h1']:+8.2f} {r['h2']:+8.2f} {r['pot_final']:7.2f}{mark}")


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    syms = va._syms()
    print(f"[표본] {len(syms)}종목 · {DETMOD} 롱 · 1h 365일 · 익절 {[f'{x:.1%}' for x in TP_GRID]} × "
          f"손절 {[f'{x:.0%}' for x in SL_GRID]} = {len(TP_GRID)*len(SL_GRID)}셀 · {LEV}x · 포트 ${START:.0f} 바닥")
    print(f"[반영] DEPLOY_ON_PASS={DEPLOY_ON_PASS} — 진단. 익절·손절 변경은 사용자 결정\n")
    if "--no-fetch" not in argv:
        va.fetch(syms, ["1d", "1h"])
    rows1d = va.load_tf(syms, "1d")
    rows1h = va.load_tf(syms, "1h")
    if not rows1h:
        print("[1h] 데이터 없음")
        return 1
    ranked = turnover_rank(rows1d)
    top = [s for s in ranked[:TOPN] if s in rows1h]
    nb = sum(len(v) for v in rows1h.values())
    first = min(r["date"] for rows in rows1h.values() for r in rows)
    last = max(r["date"] for rows in rows1h.values() for r in rows)
    print(f"[코호트] top{TOPN}: {top}")
    print(f"[1h] {len(rows1h)}종목 {nb:,}봉 {first} ~ {last}")

    out = {}
    for label, syms_c in (("top20", top), ("all", list(rows1h))):
        by = {s: rows1h[s] for s in syms_c if s in rows1h}
        recs = prepare(signals(by))
        rand = random_entries(by)
        print(f"\n[{label}] 신호 {len(recs)}건 · 랜덤 진입 베이스라인 {len(rand)}건 "
              f"(순차 시뮬에서 보유 중 신호는 버림)")
        rows = grid(recs, rand)
        _matrix(rows, "pnl", f"{label} — 계좌 손익 $ (익절 × 손절, 3x, 순차 1포지션)")
        _matrix(rows, "win_rate", f"{label} — 실측 승률 %", fmt="{:7.2f}%", scale=1.0)
        _matrix(rows, "delta", f"{label} — δ = 이론 도달률 − 랜덤 진입 실측 (%p, 클수록 현실이 이론보다 나쁨)",
                fmt="{:+7.2f} ", scale=100.0)
        _slice(rows, LIVE_SL, f"{label} — 손절 8% 고정 슬라이스 (사용자 질문 축)")
        a = answer(rows)
        print(f"\n  → 계좌손익 최대 셀: 익절 {a['best_tp']:.1%} / 손절 {a['best_sl']:.0%} "
              f"(${a['best_pnl']:+.2f}) | 양수 셀 {a['any_positive']}/{len(rows)} | "
              f"최대가 양수: {a['best_positive']} | 전후반 둘 다 양수: {a['best_both_halves_pos']}")
        print(f"  → 질문 셀(익절 2%/손절 8%) ${a['ask_pnl']:+.2f} vs 현행(1%/8%) ${a['live_pnl']:+.2f} "
              f"| 차이 ${a['ask_vs_live']:+.2f} | 2% 가 더 나은가: {a['ask_beats_live']}")
        print(f"  → 익절별 최선 손절: {a['best_per_tp']}")
        print(f"  → 익절별 평균 δ(%p): "
              f"{{{', '.join(f'{k}: {v*100:+.2f}' for k, v in (a['delta_by_tp'] or {}).items())}}}")
        out[label] = dict(answer=a, n_signals=len(recs), n_random=len(rand),
                          rows=[{k: v for k, v in r.items() if k != "trades"} for r in rows],
                          trades_ask=[r["trades"] for r in rows
                                      if abs(r["tp"] - ASK_TP) < 1e-12 and abs(r["sl"] - LIVE_SL) < 1e-12])
    out["config"] = dict(tp_grid=TP_GRID, sl_grid=SL_GRID, lev=LEV, start=START, max_scan=MAX_SCAN,
                         fee=FEE, topn=TOPN, detmod=DETMOD, window=[first, last], top20=top,
                         rand_n=RAND_N, rand_seed=RAND_SEED, deploy_on_pass=DEPLOY_ON_PASS)
    json.dump(out, open("_tp1_grid.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n[저장] _tp1_grid.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
