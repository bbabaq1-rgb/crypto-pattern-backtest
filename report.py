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
