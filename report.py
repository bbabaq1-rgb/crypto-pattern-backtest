"""
report.py — research_log.csv + registry.json 을 읽어 report.md 완성형 생성.

내용: 시험 요약, status 분류, 패턴 x 타임프레임별 n·평균·중앙값·진짜율·verdict·OOS,
      현재 살아있는 수익모델 후보, 기각 요약.
"""
import csv
import json
import os
from collections import defaultdict, Counter

LOG = "research_log.csv"
REGISTRY = "registry.json"
OUT = "report.md"
TF_ORDER = ["1d", "4h", "1h"]


def load_log():
    if not os.path.exists(LOG):
        return []
    with open(LOG, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def load_registry():
    with open(REGISTRY, encoding="utf-8") as f:
        return json.load(f)["patterns"]


def pctf(v):
    try:
        return f"{float(v)*100:+.2f}%"
    except (TypeError, ValueError):
        return "-"


def main():
    rows = load_log()
    pats = load_registry()

    # (pattern, tf) -> {"full": row, "oos": {seg: row}}
    pt = defaultdict(lambda: {"full": None, "oos": {}})
    for r in rows:
        sym = r["symbol"]
        if sym.startswith("ALL7@"):
            tf = sym.split("@", 1)[1]
            pt[(r["pattern"], tf)]["full"] = r        # 최신 우선(덮어씀)
        elif sym.startswith("OOS@"):
            parts = sym.split("@")
            if len(parts) >= 3:
                tf, seg = parts[1], parts[2]
                pt[(r["pattern"], tf)]["oos"][seg] = r

    status_cnt = Counter(p["status"] for p in pats)
    L = []
    L.append("# 자동 패턴 연구 보고서\n")
    L.append(f"- 등재 패턴: **{len(pats)}개**")
    L.append(f"- 누적 시험(로그 행): **{len(rows)}건**")
    L.append("- 상태 분포: " +
             ", ".join(f"{k} {v}" for k, v in sorted(status_cnt.items())))
    L.append("- 게이트(동결): n>=20 AND 평균수익>임계 AND 중앙값>0, 라벨 대칭 ±10%, "
             "수수료 왕복 0.2%, 다중비교 보정은 평균임계.")
    L.append("")

    # 상태 분류
    L.append("## 상태 분류\n")
    L.append("| status | 패턴 |")
    L.append("|---|---|")
    by_status = defaultdict(list)
    for p in pats:
        by_status[p["status"]].append(p["id"])
    for st in ["validated", "passed", "holding", "rejected", "needs_impl", "testing", "pending"]:
        if by_status.get(st):
            L.append(f"| {st} | {', '.join(by_status[st])} |")
    L.append("")

    # 패턴 x 타임프레임 상세
    L.append("## 패턴 × 타임프레임 결과\n")
    L.append("| 패턴 | TF | n | 평균수익 | 중앙값 | 진짜율 | verdict | OOS(IS/OOS) | 베이스라인 초과(p) |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for p in pats:
        tfs = [tf for tf in TF_ORDER if pt.get((p["id"], tf), {}).get("full")]
        if not tfs:
            L.append(f"| {p['id']} | - | - | - | - | - | (미시험) | - | - |")
            continue
        base = p.get("baseline", {})
        for tf in tfs:
            rec = pt[(p["id"], tf)]
            fr = rec["full"]
            tr = f"{float(fr['true_rate'])*100:.1f}%" if fr.get("true_rate") else "-"
            oo = rec["oos"]
            if oo:
                oss = " / ".join(
                    f"{seg}:{oo[seg]['verdict']}(n{oo[seg]['n']},{pctf(oo[seg].get('mean_ret'))})"
                    for seg in ("IS", "OOS") if seg in oo)
            else:
                oss = "-"
            b = base.get(tf)
            if b:
                bcol = (f"{pctf(b.get('excess_mean'))} (p={b.get('p_mean')}, "
                        f"{'유의' if b.get('significant') else '미초과'})")
            else:
                bcol = "-"
            L.append(f"| {p['id']} | {tf} | {fr['n']} | {pctf(fr.get('mean_ret'))} | "
                     f"{pctf(fr.get('median_ret'))} | {tr} | {fr['verdict']} | {oss} | {bcol} |")
    L.append("")

    # 레짐별 결과 (regime breakdown 보유 패턴만)
    L.append("## 레짐별 기대값 (상승장 편승 여부 검증)\n")
    any_reg = False
    for p in pats:
        reg = p.get("regime", {})
        for tf, rb in reg.items():
            any_reg = True
            bits = ", ".join(
                f"{g} n{v['n']} 평균{v['mean']*100:+.2f}%/중앙{v['median']*100:+.2f}%"
                for g, v in rb.items())
            note = " [상승장 의존]" if p.get("regime_dependent") else ""
            L.append(f"- **{p['id']}** @{tf}: {bits}{note}")
    if not any_reg:
        L.append("- (레짐 분해된 패턴 없음)")
    L.append("")

    # 정밀검증 (validated/passed 후보)
    L.append("## 1순위 후보 정밀검증\n")
    prec_pats = [p for p in pats if p.get("precision")]
    if prec_pats:
        for p in prec_pats:
            pr = p["precision"]
            s = pr["slip"]; w = pr["walkforward"]; ns = pr["newsymbols"]
            ok = lambda b: "통과" if b else "실패"
            L.append(f"- **{p['id']}** ({p['name']}) — status=**{p['status']}**")
            L.append(f"  - 슬리피지(+0.1%): 평균 {pctf(s['mean'])}, 중앙 {pctf(s['median'])}, "
                     f"베이스라인 p={s['p_mean']} → {ok(s['ok'])}")
            L.append(f"  - 워크포워드: 유효윈도우 {w['valid']}개 중 양수 {w['pos']}개 "
                     f"({w['pos_frac']*100:.0f}%) → {ok(w['ok'])}")
            L.append(f"  - 표본확대(신규5종): n={ns['n']}, 평균 {pctf(ns['mean'])}, "
                     f"종목별 양수 {ns['persym_pos']}/5 → {ok(ns['ok'])}")
            if p.get("precision_note"):
                L.append(f"  - {p['precision_note']}")
    else:
        L.append("- 정밀검증된 후보 없음.")
    L.append("")

    # validated 순위표
    L.append("## validated 패턴 순위표\n")
    L.append("기준: 기대값(평균/중앙) · 베이스라인 초과(p) · 레짐 독립성 · 마모 여부\n")
    vp = [p for p in pats if p["status"] == "validated"]
    if vp:
        def vmean(p):
            tf = p.get("passed_tf")
            fr = pt.get((p["id"], tf), {}).get("full")
            try:
                return float(fr["mean_ret"])
            except (TypeError, ValueError, KeyError):
                return -9
        vp.sort(key=vmean, reverse=True)
        L.append("| 순위 | 패턴 | TF | n | 평균 | 중앙 | 베이스라인 초과(p) | 레짐독립 | 마모 |")
        L.append("|---|---|---|---|---|---|---|---|---|")
        for rank, p in enumerate(vp, 1):
            tf = p.get("passed_tf", "?")
            fr = pt.get((p["id"], tf), {}).get("full", {})
            b = p.get("baseline", {}).get(tf, {})
            bcol = (f"{pctf(b.get('excess_mean'))} (p={b.get('p_mean')})" if b else "-")
            reg_indep = "X(상승의존)" if p.get("regime_dependent") else "O"
            wear = p.get("wear")
            wcol = ("마모(복원불가)" if wear and not wear.get("restored")
                    else "복원" if wear else "-")
            L.append(f"| {rank} | {p['id']} | {tf} | {fr.get('n','-')} | "
                     f"{pctf(fr.get('mean_ret'))} | {pctf(fr.get('median_ret'))} | "
                     f"{bcol} | {reg_indep} | {wcol} |")
    else:
        L.append("- validated 패턴 없음.")
    L.append("")

    # 살아있는 수익모델 후보
    L.append("## 현재 살아있는 수익모델 후보\n")
    live = [p for p in pats if p["status"] in ("validated", "passed")]
    if live:
        for p in live:
            tf = p.get("passed_tf", "?")
            tag = "실거래 검토 가능(validated)" if p["status"] == "validated" else "승인 대기(passed)"
            L.append(f"- **{p['id']}** ({p['name']}) — {tf} 전체+OOS+베이스라인+정밀검증, {tag}")
    else:
        L.append("- 살아있는 후보 없음.")

    hold = [p for p in pats if p["status"] == "holding"]
    if hold:
        L.append("\n보류(기대값 유망하나 표본부족, 표본 확대 대상):")
        for p in hold:
            # 가장 좋은(평균 최대) TF 표시
            best = None
            for tf in TF_ORDER:
                fr = pt.get((p["id"], tf), {}).get("full")
                if not fr or fr.get("mean_ret") in (None, ""):
                    continue
                if best is None or float(fr["mean_ret"]) > float(best["mean_ret"]):
                    best = fr; best_tf = tf
            if best:
                L.append(f"- {p['id']} ({p['name']}) — 최고 {best_tf}: n={best['n']}, "
                         f"평균 {pctf(best.get('mean_ret'))}, 중앙값 {pctf(best.get('median_ret'))}")
            else:
                L.append(f"- {p['id']} ({p['name']})")
    L.append("")

    # 레짐 스위치: 롱/숏 레짐별 기대값
    if os.path.exists("regime_switch.json"):
        rsj = json.load(open("regime_switch.json", encoding="utf-8"))
        REG = ["bull_altseason", "bull_btc", "bear", "sideways"]
        L.append("## 레짐 스위치: 롱/숏 레짐별 기대값\n")
        L.append("시장레짐 = BTC 200봉 MA기울기 + 도미넌스(프록시: BTC vs 알트 상대강도).\n")
        L.append(f"레짐 일수: " + ", ".join(f"{k} {v}" for k, v in rsj.get("regime_days", {}).items()))
        L.append("")
        L.append("| 패턴 | " + " | ".join(REG) + " |")
        L.append("|---|" + "---|" * len(REG))
        for pid, pr in rsj["by_pattern"].items():
            cells = []
            for rg in REG:
                x = pr.get(rg, {})
                cells.append(f"{pctf(x.get('mean'))}(n{x.get('n',0)})" if x.get("mean") is not None else "-")
            L.append(f"| {pid} | " + " | ".join(cells) + " |")
        L.append("")

    # 방향 라우팅
    if os.path.exists("direction_switch.json"):
        dsj = json.load(open("direction_switch.json", encoding="utf-8"))
        L.append("## 레짐 -> 방향 -> 패턴 라우팅\n")
        L.append("규칙: 각 레짐에서 기대값 양수(n>=20)인 방향만 켠다. 둘 다 음수면 FLAT.\n")
        L.append("| 레짐 | engulfing | fvg |")
        L.append("|---|---|---|")
        for rg, r in dsj["routing"].items():
            L.append(f"| {rg} | {r.get('engulfing','-')} | {r.get('fvg','-')} |")
        cur = dsj.get("current", {})
        L.append(f"\n**현재({cur.get('date')}) 레짐: {cur.get('regime')}** -> "
                 + ", ".join(f"{k}:{v}" for k, v in cur.get("action", {}).items()))
        L.append("")

    # 청산방식 A vs D
    if os.path.exists("method_d.json"):
        md = json.load(open("method_d.json", encoding="utf-8"))
        L.append("## 청산방식 A(±10%/20봉) vs D(손절-8%/반대신호·레짐전환/최대30봉)\n")
        L.append("| 패턴 | 방식 | n | 평균 | 중앙 | 베이스초과(p) | 최대손실 | 평균보유 |")
        L.append("|---|---|---|---|---|---|---|---|")
        for pat, mv in md.items():
            for tag in ("A", "D"):
                s = mv[tag]
                L.append(f"| {pat} | {tag} | {s['n']} | {pctf(s['mean'])} | {pctf(s['median'])} | "
                         f"{pctf(s['excess'])}(p{s['p']}) | {pctf(s['maxloss'])} | {s['avghold']:.1f} |")
        L.append("\n판정: 방식D는 평균↑·최대손실 대폭↓(-8% 고정)이나 **중앙값 음수**(손절은 -8%로 "
                 "자르고 승자만 끌고가는 양의 스큐). 동결 게이트(중앙값>0)로는 D가 탈락 — "
                 "기대값·리스크는 D 우위, 게이트 통과는 A. 리스크관리 우선이면 D, 기준 일관성은 A.")
        L.append("")

    # 실제 BTC.D 재검증
    if os.path.exists("btc_dominance.json"):
        bd = json.load(open("btc_dominance.json", encoding="utf-8"))
        L.append("## 실제 BTC.D 레짐 재검증\n")
        L.append(f"- 현재 BTC.D: {bd.get('current_btc_d')}% (CoinGecko global, 취득 성공)")
        L.append(f"- 히스토리 가용: {bd.get('history_available')} — {bd.get('note')}")
        L.append(f"- 레짐 산출 기준: {bd.get('regime_basis')}")
        L.append("- 결론: 무료 API로 BTC.D 히스토리 확보 불가(유료 401) → 레짐은 상대강도 "
                 "프록시 유지. 라우팅표 불변. 실제 BTC.D 재검증은 유료 데이터 확보 시 가능.")
        L.append("")

    # 스케줄러 사용법
    L.append("## 실시간 스케줄러 (scheduler.py)\n")
    L.append("매 UTC 00:00: 데이터 fetch → 레짐 판정 → direction_switch 갱신 → "
             "engulfing/fvg 오늘 신호 탐지 → signals_today.json 저장 (실주문 없음, 페이퍼테스트).")
    L.append("```")
    L.append("python scheduler.py once      # 1회(데이터 최신 가정, fetch 생략)")
    L.append("python scheduler.py oncefull  # 1회(fetch 포함)")
    L.append("python scheduler.py           # 데몬(매일 UTC 00:00 자동)")
    L.append("```")
    L.append("")

    # 타임프레임 확장 검증
    if os.path.exists("tf_verify.json"):
        tv = json.load(open("tf_verify.json", encoding="utf-8"))
        L.append("## 타임프레임 확장 검증 (12종목, 각 TF 독립 게이트)\n")
        L.append("규칙: 각 TF가 자기 게이트(n>=20·평균>0·중앙>0) + OOS 양구간 + 베이스라인"
                 "(p<0.05)을 독립 통과해야만 채택. 신호빈도=종목당 월평균.\n")
        L.append("| 패턴 | TF | n | 평균 | 중앙 | 게이트 | OOS | 베이스p | 월/종목 | 채택 |")
        L.append("|---|---|---|---|---|---|---|---|---|---|")
        for key, v in tv.items():
            pat, tf = key.split("@")
            L.append(f"| {pat} | {tf} | {v['n']} | {pctf(v['mean'])} | {pctf(v['median'])} | "
                     f"{v['verdict']} | {v['oos'] or '-'} | "
                     f"{v['base_p'] if v['base_p'] is not None else '-'} | "
                     f"{v['freq_per_sym_month']} | {'O' if v['passed'] else 'X'} |")
        passed_tf = [k for k, v in tv.items() if v["passed"]]
        L.append(f"\n**채택 TF: {', '.join(passed_tf) if passed_tf else '없음'}** — "
                 "1d만 통과. 하위 TF는 신호빈도는 급증하나(예: fvg 15m 104건/종목·월) "
                 "기대값·중앙값이 0 이하로 무너져 전부 기각. **빈도↑ ≠ 엣지↑**(수수료+노이즈). "
                 "게이트 미조정 — 페이퍼/실거래엔 1d만 유지.")
        L.append("")

    # 페이퍼테스트 시스템
    L.append("## 페이퍼테스트 시스템 (실주문 없음)\n")
    L.append("구성: exchange.py(비트겟 데모 연결, 키 없으면 시뮬레이션) + paper_executor.py"
             "(모의 체결, 방식A/D 병행) + scheduler.py(매일 자동) + paper_summary.py(집계).")
    L.append("자본 $2,000, 포지션당 10%($200), 1x. 체결은 로컬 시가/종가 가정.\n")
    if os.path.exists("paper_trades.json"):
        import statistics as _st
        tr = json.load(open("paper_trades.json", encoding="utf-8"))
        pos = json.load(open("paper_positions.json", encoding="utf-8")) if os.path.exists("paper_positions.json") else []
        L.append(f"- 현재 스냅샷: 누적 체결 {len(tr)}건, 오픈 {len(pos)}건")
        for m in ("A", "D"):
            mt = [t for t in tr if t["method"] == m]
            if mt:
                rets = [t["ret"] for t in mt]
                wr = sum(1 for r in rets if r > 0) / len(rets) * 100
                pnl = sum(t["pnl_usd"] for t in mt)
                L.append(f"  - 방식 {m}: n={len(mt)}, 승률 {wr:.1f}%, 평균 {_st.mean(rets)*100:+.2f}%, 누적 ${pnl:+.0f}")
        L.append("  - (시드: 최근 60봉 라우팅 신호로 부트스트랩한 초기 표본 — 누적될수록 신뢰↑)")
    L.append("\n```")
    L.append("python scheduler.py oncefull   # fetch+레짐+신호+페이퍼체결 1회")
    L.append("python paper_summary.py        # 현재까지 성과(A vs D, 패턴/레짐별)")
    L.append("```")
    L.append("")

    # 알트 유니버스 확장
    if os.path.exists("universe.json"):
        uni = json.load(open("universe.json", encoding="utf-8"))
        L.append("## 알트 유니버스 확장 (바이낸스 거래대금 상위 50 알트)\n")
        L.append("ccxt엔 시총이 없어 24h 거래대금 상위로 대체(유동성 프록시). "
                 "현재 12종 + 스테이블 제외. <500봉 데이터부족 스킵. "
                 "종목 채택 = engulfing/fvg 롱·숏 1d 순기대값>0 AND n>=10.\n")
        L.append(f"- 시도 {uni.get('tried')}종 | 데이터부족 {len(uni.get('data_short', []))}종 | "
                 f"**채택 {len(uni.get('adopted_new', []))}종**")
        L.append(f"- 채택: {', '.join(uni.get('adopted_new', []))}")
        rej = uni.get("rejected", {})
        L.append(f"- 기각 {len(rej)}종(순기대값 음수): {', '.join(rej.keys())}")
        L.append(f"- 데이터부족: {', '.join(uni.get('data_short', []))}")
        L.append(f"- **확장 트레이딩 유니버스: {len(uni.get('trading_universe', []))}종** (기존7+채택21)")
        pc = uni.get("pool_confirm", {})
        L.append("\n확장 유니버스 패턴 보존 확인:")
        for pat, v in pc.items():
            L.append(f"  - {pat}: n={v['n']}, 평균 {pctf(v['mean'])}, {v['verdict']}, "
                     f"OOS {v['oos']}, p={v['base_p']} -> {'엣지 보존' if v['passed'] else '주의'}")
        ms = uni.get("monthly_signals_adopted", {})
        L.append("\n패턴별 월 총 신호 수(채택 21종 합산): "
                 + ", ".join(f"{k} {v}건/월" for k, v in ms.items()))
        L.append("")

    # 캔들 패턴 8종 검증
    if os.path.exists("universe.json"):
        uni2 = json.load(open("universe.json", encoding="utf-8"))
        cr = uni2.get("candle_results")
        if cr:
            L.append("## 캔들 패턴 8종 검증 (28종목 일봉, 독립 게이트+OOS+베이스라인)\n")
            L.append("| 패턴 | 방향 | n | 평균 | 중앙 | 게이트 | OOS | 베이스p | 결과 |")
            L.append("|---|---|---|---|---|---|---|---|---|")
            for name, v in cr.items():
                L.append(f"| {name} | {v['direction']} | {v['n']} | {pctf(v['mean'])} | "
                         f"{pctf(v['median'])} | {v['verdict']} | {v['oos']} | "
                         f"{v['base_p'] if v['base_p'] is not None else '-'} | "
                         f"{'✅통과' if v['passed'] else '기각'} |")
            ap = [a["pattern"] for a in uni2.get("adopted_patterns", [])]
            L.append(f"\n**통과 채택: {', '.join(ap) if ap else '없음'}** — "
                     "inverted_hammer(롱,p0.001)·marubozu(롱,p0.028)만 통과. hammer·piercing·"
                     "dark_cloud·morning/evening_star·marubozu_short은 기대값 음수/게이트 미달로 기각. "
                     "채택 패턴은 scheduler/paper_executor가 자동 픽업.")
            L.append("")

    # 기각 요약
    L.append("## 기각(rejected) 요약\n")
    rej = [p for p in pats if p["status"] == "rejected"]
    if rej:
        for p in rej:
            tfs = [tf for tf in TF_ORDER if pt.get((p["id"], tf), {}).get("full")]
            reason = p.get("reject_reason")
            if reason:
                L.append(f"- {p['id']} ({p['name']}) — {reason}")
            elif tfs:
                bits = []
                for tf in tfs:
                    fr = pt[(p["id"], tf)]["full"]
                    bits.append(f"{tf} {pctf(fr.get('mean_ret'))}({fr['verdict']})")
                L.append(f"- {p['id']} ({p['name']}) — " + ", ".join(bits))
            else:
                L.append(f"- {p['id']} ({p['name']}) — 사전 기각(별도 분석)")
    else:
        L.append("- 없음.")
    L.append("")

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print(f"[생성] {OUT} ({len(L)}줄)")


if __name__ == "__main__":
    main()
