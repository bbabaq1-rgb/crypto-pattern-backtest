"""
observation_report.py — 1개월 실거래 관찰 보고 (2026-09-06 사용자 결정, 종료 2026-10-06).

읽기 전용. Supabase trades 테이블을 select 만 하고 아무것도 쓰지 않는다.
매매 경로(scheduler / paper_executor / registry / universe)와 무관하다.

집계 단위 = 셀 (pattern, direction, entry_regime). 실거래(live) 방식D 청산만 센다.
  - method "R"(그림자 장부)·"A"(라벨 장부)는 제외 — 주문이 나간 다리는 D 뿐이다.
  - 실거래 판정: live_mode 컬럼 True 또는 exit_reason 에 '실거래' 마커(DDL 미적용 대비).
  - 스케줄러 정지 구간(2026-10-02 ~ 10-09) 에 청산된 거래는 'outage' 로 따로 표시한다.
    그 동안 엔진의 maxhold·레짐 청산이 돌지 않고 거래소 OCO 손절만 살아 있었기 때문.
  - 손절 판정: exit_reason 에 '손절' 이 있고 수익률이 음수일 때만.
    (2026-09-17 이전 OKX type 2 '전량 청산' 을 손절로 적던 오라벨 4건이 있다 —
     부호 조건이 그 4건(+0.56 / +2.27 / +0.74 / −0.27%)중 수익 3건을 걸러낸다.)
"""
import statistics as st
import sys
from collections import defaultdict

OBS_START = "2026-09-06"
OBS_END = "2026-10-06"
OUTAGE = ("2026-10-02", "2026-10-09")


def _d(x):
    return str(x or "")[:10]


def is_live(t):
    return bool(t.get("live_mode")) or ("실거래" in str(t.get("exit_reason") or ""))


def is_stop(t):
    return "손절" in str(t.get("exit_reason") or "") and (t.get("return_pct") or 0) < 0


def cell_of(t):
    reg = t.get("entry_regime") or t.get("regime") or "?"
    return (t.get("pattern") or "?", t.get("direction") or "?", reg)


def summarize(rows):
    r = [float(t.get("return_pct") or 0) for t in rows]
    usd = [t.get("pnl_live_usd") for t in rows if t.get("pnl_live_usd") is not None]
    return dict(n=len(r),
                mean=st.mean(r) if r else 0.0,
                med=st.median(r) if r else 0.0,
                win=100.0 * sum(x > 0 for x in r) / len(r) if r else 0.0,
                stops=sum(is_stop(t) for t in rows),
                usd=sum(usd) if usd else None, usd_n=len(usd),
                hold=st.median([t.get("hold_bars") or 0 for t in rows]) if rows else 0)


def table(title, rows):
    print(f"\n### {title} (n={len(rows)})")
    print("| 셀 (패턴·방향·진입레짐) | n | 평균% | 중앙% | 승률% | 손절 | 실현$ | 보유봉 중앙 | outage 청산 |")
    print("|---|---|---|---|---|---|---|---|---|")
    by = defaultdict(list)
    for t in rows:
        by[cell_of(t)].append(t)
    for k in sorted(by, key=lambda k: (-len(by[k]), k)):
        g = by[k]
        s = summarize(g)
        out = sum(OUTAGE[0] <= _d(t.get("exit_date")) <= OUTAGE[1] for t in g)
        usd = f"{s['usd']:+.2f} ({s['usd_n']})" if s["usd"] is not None else "-"
        print(f"| {k[0]}·{k[1]}·{k[2]} | {s['n']} | {s['mean']:+.2f} | {s['med']:+.2f} | "
              f"{s['win']:.0f} | {s['stops']} | {usd} | {s['hold']:.0f} | {out} |")
    s = summarize(rows)
    usd = f"{s['usd']:+.2f} ({s['usd_n']})" if s["usd"] is not None else "-"
    print(f"| **합계** | {s['n']} | {s['mean']:+.2f} | {s['med']:+.2f} | {s['win']:.0f} | "
          f"{s['stops']} | {usd} | {s['hold']:.0f} | - |")


def main():
    import supabase_client as sc
    cli = sc.get_client("service")
    rows, start = [], 0
    while True:
        page = (cli.table("trades").select("*").range(start, start + 999).execute().data) or []
        rows += page
        if len(page) < 1000:
            break
        start += 1000
    print(f"[observation] trades 전체 {len(rows)}행 (읽기 전용)")
    meth = defaultdict(int)
    for t in rows:
        meth[(t.get("method"), is_live(t))] += 1
    print("  method·live 분포:", dict(meth))

    live_d = [t for t in rows if t.get("method") == "D" and is_live(t)]
    obs = [t for t in live_d if OBS_START <= _d(t.get("entry_date")) <= OBS_END]
    after = [t for t in live_d if _d(t.get("entry_date")) > OBS_END]
    pre = [t for t in live_d if _d(t.get("entry_date")) < OBS_START]

    table(f"관찰 기간 진입 {OBS_START}~{OBS_END} — 실거래 방식D", obs)
    table(f"관찰 기간 이후 진입 {OBS_END} 이후 — 실거래 방식D", after)
    table(f"관찰 이전 진입 ~{OBS_START} — 실거래 방식D (참고)", pre)

    outage = [t for t in live_d if OUTAGE[0] <= _d(t.get("exit_date")) <= OUTAGE[1]]
    print(f"\n### 스케줄러 정지 구간 청산 ({OUTAGE[0]}~{OUTAGE[1]}) n={len(outage)}")
    for t in sorted(outage, key=lambda t: _d(t.get("exit_date"))):
        print(f"  {_d(t.get('exit_date'))} {t.get('symbol')} {t.get('pattern')} {t.get('direction')} "
              f"{float(t.get('return_pct') or 0):+.2f}% $"
              f"{t.get('pnl_live_usd') if t.get('pnl_live_usd') is not None else '-'} "
              f"[{t.get('exit_reason')}]")

    lab = [t for t in rows if "손절(OKX algo)" in str(t.get("exit_reason") or "")
           and (t.get("return_pct") or 0) >= 0]
    print(f"\n[라벨 점검] '손절(OKX algo)' 인데 수익 ≥0 — 손절로 세지 않은 행 {len(lab)}건:",
          [(t.get("symbol"), t.get("pattern"), round(float(t.get("return_pct") or 0), 2)) for t in lab])
    return 0


if __name__ == "__main__":
    sys.exit(main())
