"""
paper_summary.py — 페이퍼 체결 성과 집계. `python paper_summary.py`.
paper_trades.json 읽어서: 전체(거래수/승률/평균/누적/MDD), 방식 A vs D,
패턴별·방향별·레짐별 분류 출력.
"""
import json
import os
import statistics as st

TRD = "paper_trades.json"
POS = "paper_positions.json"
CAPITAL = 2000.0


def load(fn, d):
    return json.load(open(fn, encoding="utf-8")) if os.path.exists(fn) else d


def mdd(rets_in_order):
    eq = CAPITAL; peak = CAPITAL; worst = 0.0
    for r in rets_in_order:
        eq += r * (CAPITAL * 0.10)               # 포지션당 10%
        peak = max(peak, eq)
        worst = min(worst, (eq - peak) / peak)
    return worst


def block(name, trades):
    if not trades:
        print(f"  {name:<22} 거래 0건")
        return
    rets = [t["ret"] for t in trades]
    pnl = sum(t["pnl_usd"] for t in trades)
    wr = sum(1 for r in rets if r > 0) / len(rets)
    cum = pnl / CAPITAL * 100
    ordered = [t["ret"] for t in sorted(trades, key=lambda x: x["entry_date"])]
    print(f"  {name:<22} n={len(rets):>3}  승률 {wr*100:4.1f}%  평균 {st.mean(rets)*100:+.2f}%  "
          f"누적 {cum:+.1f}%(${pnl:+.0f})  MDD {mdd(ordered)*100:.1f}%")


def main():
    trades = load(TRD, [])
    positions = load(POS, [])
    print("=" * 78)
    print(f"페이퍼테스트 성과 (자본 ${CAPITAL:.0f}, 포지션당 10%, 실주문 없음)")
    print(f"  누적 체결 {len(trades)}건 | 현재 오픈 {len(positions)}건")
    print("=" * 78)

    if not trades:
        print("\n아직 청산된 거래 없음 (신호 누적 대기 중).")
        return

    print("\n[전체]")
    block("전체", trades)

    print("\n[방식 A vs D]")
    for m in ("A", "D"):
        block(f"방식 {m}", [t for t in trades if t["method"] == m])

    print("\n[방식 D : 패턴x방향]")
    for pat in ("engulfing", "fvg"):
        for d in ("long", "short"):
            block(f"{pat} {d}", [t for t in trades
                                 if t["method"] == "D" and t["pattern"] == pat and t["direction"] == d])

    print("\n[방식 D : 레짐별]")
    regs = sorted({t["regime"] for t in trades if t.get("regime")})
    for rg in regs:
        block(rg, [t for t in trades if t["method"] == "D" and t.get("regime") == rg])


if __name__ == "__main__":
    main()
