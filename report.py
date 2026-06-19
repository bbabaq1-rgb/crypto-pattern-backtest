"""
report.py — research_log.csv + registry.json 을 읽어 report.md 자동 생성.

내용: 시험한 패턴 수, status 분류표, 패턴별 n·진짜율·verdict·OOS결과,
      현재 살아있는 후보, 기각 사유 요약.
"""
import csv
import json
import os
from collections import defaultdict, Counter

LOG = "research_log.csv"
REGISTRY = "registry.json"
OUT = "report.md"


def load_log():
    if not os.path.exists(LOG):
        return []
    with open(LOG, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def load_registry():
    with open(REGISTRY, encoding="utf-8") as f:
        return json.load(f)["patterns"]


def main():
    rows = load_log()
    pats = load_registry()

    # 패턴별 시험 기록 묶기
    by_pat = defaultdict(list)
    for r in rows:
        by_pat[r["pattern"]].append(r)

    # 패턴별 전체기간 최신 결과 + OOS 결과
    def full_row(pid):
        fr = [r for r in by_pat.get(pid, []) if r["symbol"] == "ALL7"]
        return fr[-1] if fr else None

    def oos_rows(pid):
        return [r for r in by_pat.get(pid, []) if r["symbol"].startswith("OOS@")]

    status_cnt = Counter(p["status"] for p in pats)
    L = []
    L.append("# 자동 패턴 연구 보고서\n")
    L.append(f"- 등재 패턴: **{len(pats)}개**")
    L.append(f"- 누적 시험(로그 행): **{len(rows)}건**")
    L.append(f"- 상태 분포: " +
             ", ".join(f"{k} {v}" for k, v in sorted(status_cnt.items())))
    L.append("")

    # 상태 분류표
    L.append("## 상태 분류\n")
    L.append("| status | 패턴 |")
    L.append("|---|---|")
    by_status = defaultdict(list)
    for p in pats:
        by_status[p["status"]].append(p["id"])
    for st in ["passed", "holding", "rejected", "needs_impl", "testing", "pending"]:
        if by_status.get(st):
            L.append(f"| {st} | {', '.join(by_status[st])} |")
    L.append("")

    # 패턴별 상세
    def pctf(v):
        try:
            return f"{float(v)*100:+.2f}%"
        except (TypeError, ValueError):
            return "-"

    L.append("## 패턴별 결과\n")
    L.append("판정=기대값 기반(평균수익>임계 AND 중앙값>0 AND n>=20). 진짜율은 참고용.\n")
    L.append("| 패턴 | status | n | 평균수익 | 중앙값 | 진짜율 | verdict(전체) | OOS |")
    L.append("|---|---|---|---|---|---|---|---|")
    for p in pats:
        fr = full_row(p["id"])
        if fr:
            n = fr["n"]
            mr = pctf(fr.get("mean_ret"))
            md = pctf(fr.get("median_ret"))
            tr = f"{float(fr['true_rate'])*100:.1f}%" if fr.get("true_rate") else "-"
            vd = fr["verdict"]
        else:
            n = mr = md = tr = "-"; vd = "(미시험)"
        oos = oos_rows(p["id"])
        if oos:
            oss = " / ".join(f"{r['symbol'].split('@')[1]}:{r['verdict']}(n{r['n']},{pctf(r.get('mean_ret'))})"
                             for r in oos)
        else:
            oss = "-"
        L.append(f"| {p['id']} | {p['status']} | {n} | {mr} | {md} | {tr} | {vd} | {oss} |")
    L.append("")

    # 살아있는 후보
    live = [p for p in pats if p["status"] == "passed"]
    hold = [p for p in pats if p["status"] == "holding"]
    L.append("## 현재 살아있는 후보\n")
    if live:
        for p in live:
            L.append(f"- **{p['id']}** ({p['name']}) — 전체+OOS 통과, 수익모델 후보(승인 대기)")
    else:
        L.append("- 통과(passed) 후보 없음.")
    if hold:
        L.append("\n보류(표본부족, 재검토 대상):")
        for p in hold:
            fr = full_row(p["id"])
            tr = f"{float(fr['true_rate'])*100:.1f}%" if fr else "-"
            n = fr["n"] if fr else "-"
            L.append(f"- {p['id']} ({p['name']}) — n={n}, 진짜율 {tr}")
    L.append("")

    # 기각 사유
    L.append("## 기각(rejected) 요약\n")
    rej = [p for p in pats if p["status"] == "rejected"]
    if rej:
        for p in rej:
            fr = full_row(p["id"])
            if fr:
                reason = f"전체 verdict={fr['verdict']}, 진짜율 {float(fr['true_rate'])*100:.1f}% (n={fr['n']})"
            else:
                reason = "사전 기각(별도 분석)"
            L.append(f"- {p['id']} ({p['name']}) — {reason}")
    else:
        L.append("- 없음.")
    L.append("")

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print(f"[생성] {OUT} ({len(L)}줄)")


if __name__ == "__main__":
    main()
