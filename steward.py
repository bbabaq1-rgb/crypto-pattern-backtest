"""
steward.py — 운용 점검: 사전 등록 정지 규칙(registry steward_rules_2026_10_26)을 실거래 장부에 기계적으로 적용한다.

2026-10-26 사용자 위임 "tp1 정지해줘 그리고 ai 한테 아예 정지 및 시동 권한을 일임해서 투자하고 싶어".
전략의 신규 진입 정지·재개를 에이전트가 사용자 확인 없이 집행하되, **판정은 이 파일의 규칙으로만** 한다 —
그날그날의 재량이 아니라 결과를 보기 전에 적어 둔 규칙이 정지를 정하게 하려는 것이다.

읽기 전용: Supabase trades 를 select 만 하고 universe.json·direction_switch.json(지금 켜져 있는 것)을 읽는다.
주문·파일·DB 쓰기 없음. 조치 집행(universe.json 이동·ROUTING_OVERRIDES)은 자율 연구 사이클 세션이 PR 로 한다
(RESEARCH_LOOP.md 0단계). 매매 경로(scheduler / paper_executor)는 이 모듈을 import 하지 않는다.

장부 = 실거래 방식D 청산만(observation_report 와 같은 정의: method "D" 이고 live_mode True 또는 exit_reason 에
'실거래'). 판정 단위는 두 층 — 패턴(pattern, direction) 과 셀(pattern, direction, 진입 레짐) — 이고
**지금 켜져 있는 단위만** 판정한다. 패턴 층의 표본은 '지금 켜진 레짐'의 거래뿐이다(라우팅으로 이미 꺼진 레짐의
성적이 켜진 레짐을 끄는 근거가 되지 않게). 레짐을 가리지 않는 단위(4레짐 전부 켜짐)는 레짐 미상('?') 거래도 센다.

규칙(사전 등록 — 바꾸려면 registry 에 새 판을 쓰고 이 상수를 고친다):
  S1 미확인 + 손실 — 검증 등급 U 이고 n ≥ 10 · 평균 수익률 < 0
  S2 유의한 손실 — 등급 무관, n ≥ 20 · 평균 < 0 · 진입 기간 ≥ 28일 · 주 단위 클러스터 부트스트랩 P(평균 ≥ 0) < 0.05
  (S3 실행 결함 · S4 재검증 기각 · 재개 R1~R3 · 전체 정지 H 는 장부로 판정하지 않는다 — RESEARCH_LOOP.md 0단계)

실행: python steward.py [--trades-json PATH] [--notify] [--out _steward_report.md]
"""
import argparse
import io
import json
import os
import random
import sys
from collections import defaultdict
from datetime import date

from observation_report import is_live

RULES_ID = "steward_rules_2026_10_26"
S1_MIN_N = 10
S2_MIN_N = 20
S2_MIN_SPAN_DAYS = 28
S2_ALPHA = 0.05
BOOT = 10000
SEED = 20261026
REGIMES = ("bull_btc", "bull_altseason", "bear", "sideways")

# 검증 등급 V(확인됨) — 그 배포 단위의 최신 사전 등록 확인 시험이 CONFIRMED/PASSED. 나머지는 전부 U(미확인).
# 레짐 셀은 패턴의 등급을 물려받는다(아래 둘은 ALL 레짐 확인). 새 확인이 나오면 근거와 함께 여기에 더한다.
CONFIRMED = {
    ("triple_bottom_4h", "long"): "guard_v5 2026-09-09 CONFIRMED — OOS n=365 +1.59% bp .000",
    ("vol_awakening_4h", "long"): "guard_v5 2026-09-09 CONFIRMED — OOS n=2593 +0.21% bp .000",
    ("cascade_fade_long_1h", "long"): "cascade_realistic 2026-09-01 PASSED — 1h 크론 +1.54% med +0.31% bp .000",
}

FOCUS = ("engulfing", "fvg")


def _d(x):
    return str(x or "")[:10]


def _day(s):
    return date.fromisoformat(_d(s))


def regime_of(t):
    return t.get("entry_regime") or t.get("regime") or "?"


def live_d(rows):
    """실거래 방식D 청산 + 수익률이 있는 행만."""
    return [t for t in rows if t.get("method") == "D" and is_live(t) and t.get("return_pct") is not None
            and _d(t.get("entry_date"))]


# ── 지금 켜져 있는 것 ──────────────────────────────────────────────────────────
def adopted_regimes(ap, tf):
    """scheduler.adopted_regime_ok 와 같은 규칙으로 '이 항목이 진입하는 레짐 집합'. 1h 블록은 레짐 게이트가 없다."""
    if tf == "1h":
        return set(REGIMES)
    rg = ap.get("regimes")
    if rg is None:
        return set(REGIMES) if tf == "1d" else {"bull_btc", "bull_altseason"}
    if rg == "all":
        return set(REGIMES)
    return set(rg) & set(REGIMES)


def deployed_units(universe, routing):
    """{(pattern, direction): {"regimes": set, "kind": str}} — 지금 신규 진입이 켜진 단위.
    kind: focus(1d engulfing/fvg, direction_switch 라우팅) / adopted_1d / adopted_4h / adopted_1h."""
    units = {}
    for rg, m in (routing or {}).items():
        for pat, d in (m or {}).items():
            if pat in FOCUS and d in ("long", "short") and rg in REGIMES:
                units.setdefault((pat, d), {"regimes": set(), "kind": "focus"})["regimes"].add(rg)
    for key, tf, kind in (("adopted_patterns", None, "adopted_1d"), ("adopted_4h_patterns", "4h", "adopted_4h"),
                          ("adopted_1h_patterns", "1h", "adopted_1h")):
        for ap in universe.get(key, []) or []:
            atf = tf or ap.get("tf", "1d")
            regs = adopted_regimes(ap, atf)
            if regs:
                units[(ap["pattern"], ap.get("direction", "long"))] = {"regimes": regs, "kind": kind, "list": key}
    return units


def tier_of(pattern, direction):
    return "V" if (pattern, direction) in CONFIRMED else "U"


# ── 통계 ───────────────────────────────────────────────────────────────────────
def week_key(s):
    y, w, _ = _day(s).isocalendar()
    return (y, w)


def cluster_boot_p(rows, B=BOOT, seed=SEED):
    """주(진입일 ISO 주) 단위 클러스터 부트스트랩의 P(재표집 평균 ≥ 0). 같은 주에 물린 거래는 한 사건이라
    거래 단위로 섞으면 표본이 실제보다 독립적으로 보인다. 단측 퍼센타일 검정(상한이 0 아래면 작아진다)."""
    by = defaultdict(lambda: [0.0, 0])
    for t in rows:
        c = by[week_key(t["entry_date"])]
        c[0] += float(t["return_pct"]); c[1] += 1
    cl = list(by.values())
    k = len(cl)
    if k == 0:
        return 1.0
    rng = random.Random(seed)
    ge = 0
    for _ in range(B):
        s = n = 0.0
        for _ in range(k):
            a, b = cl[rng.randrange(k)]
            s += a; n += b
        ge += (s / n) >= 0
    return ge / B


def stats(rows, boot=True):
    r = [float(t["return_pct"]) for t in rows]
    n = len(r)
    if not n:
        return dict(n=0, mean=0.0, wins=0, usd=None, span=0, weeks=0, p=None)
    days = sorted(_day(t["entry_date"]) for t in rows)
    usd = [float(t["pnl_live_usd"]) for t in rows if t.get("pnl_live_usd") is not None]
    return dict(n=n, mean=sum(r) / n, wins=sum(x > 0 for x in r), usd=sum(usd) if usd else None,
                span=(days[-1] - days[0]).days, weeks=len({week_key(t["entry_date"]) for t in rows}),
                p=cluster_boot_p(rows) if (boot and n >= S2_MIN_N) else None)


def judge(tier, st):
    """발동한 규칙 목록. 규칙은 모듈 상수 그대로 — 호출자가 문턱을 바꿀 수 없다."""
    hits = []
    if tier == "U" and st["n"] >= S1_MIN_N and st["mean"] < 0:
        hits.append("S1")
    if (st["n"] >= S2_MIN_N and st["mean"] < 0 and st["span"] >= S2_MIN_SPAN_DAYS
            and st["p"] is not None and st["p"] < S2_ALPHA):
        hits.append("S2")
    return hits


def action_text(unit, info, regime=None):
    pat, d = unit
    if info["kind"] == "focus":
        regs = [regime] if regime else sorted(info["regimes"])
        return "direction_switch.ROUTING_OVERRIDES 에 " + ", ".join(f"({r!r}, {pat!r}): 'FLAT'" for r in regs)
    if regime is None:
        dst = {"adopted_patterns": "suspended_patterns", "adopted_4h_patterns": "suspended_patterns",
               "adopted_1h_patterns": "suspended_1h_patterns"}[info["list"]]
        return f"universe.json {info['list']} → {dst} 로 이동(신규 진입만 정지, suspended_date·suspended_reason 기록)"
    if info["kind"] == "adopted_1h":
        return None                         # 1h 블록은 레짐 게이트가 없다 — 셀 조치 수단 없음(패턴 층만)
    keep = sorted(info["regimes"] - {regime})
    return f"universe.json {info['list']} 의 {pat} 항목 regimes = {keep} (레짐 {regime} 제외)"


def evaluate(trades, universe, routing):
    """반환: (rows, hits). rows 는 표시용 전체, hits 는 발동한 것(조치 포함)."""
    live = live_d(trades)
    units = deployed_units(universe, routing)
    by_unit = defaultdict(list)
    for t in live:
        by_unit[(t.get("pattern"), t.get("direction"))].append(t)
    out, hits = [], []
    for unit in sorted(units):
        info = units[unit]
        tier = tier_of(*unit)
        agnostic = info["regimes"] == set(REGIMES)
        rows_u = [t for t in by_unit.get(unit, []) if regime_of(t) in info["regimes"] or (agnostic and regime_of(t) == "?")]
        st = stats(rows_u)
        h = judge(tier, st)
        rec = dict(unit=unit, layer="패턴", regime=None, tier=tier, kind=info["kind"], stats=st, hits=h,
                   action=action_text(unit, info) if h else None)
        out.append(rec)
        if h:
            hits.append(rec)
        for rg in sorted(info["regimes"]):
            rows_c = [t for t in rows_u if regime_of(t) == rg]
            if not rows_c:
                continue
            sc = stats(rows_c)
            hc = judge(tier, sc)
            act = action_text(unit, info, rg) if hc else None
            # 셀 조치 수단이 없으면(1h) 발동으로 세지 않는다 — 그 단위는 패턴 층 판정만 받는다
            crec = dict(unit=unit, layer="셀", regime=rg, tier=tier, kind=info["kind"], stats=sc,
                        hits=hc if act else [], action=act,
                        note="1h 셀 게이트 없음 — 패턴 층만 판정" if hc and act is None else "")
            out.append(crec)
            # 패턴 층이 이미 발동했으면 그 셀 조치는 패턴 조치에 포함된다
            if crec["hits"] and not h:
                hits.append(crec)
    return out, hits


def reference_rows(trades, universe):
    """참고 — 정지된 전략의 실거래 성적(판정 아님)."""
    live = live_d(trades)
    susp = {(a["pattern"], a.get("direction", "long")): a.get("suspended_date", "?")
            for k in ("suspended_patterns", "suspended_1h_patterns") for a in universe.get(k, []) or []}
    out = []
    for unit, since in sorted(susp.items()):
        rows_u = [t for t in live if (t.get("pattern"), t.get("direction")) == unit]
        if rows_u:
            out.append((unit, since, stats(rows_u, boot=False)))
    return out


# ── 출력 ───────────────────────────────────────────────────────────────────────
def _fmt(st):
    usd = f"{st['usd']:+.2f}" if st["usd"] is not None else "-"
    p = f"{st['p']:.3f}" if st["p"] is not None else "-"
    return f"{st['n']} | {st['mean']:+.2f} | {st['wins']} | {usd} | {st['span']} | {st['weeks']} | {p}"


def render(out, hits, ref):
    L = [f"# 운용 점검 (steward, 규칙 {RULES_ID})", "",
         f"규칙: S1 등급 U · n≥{S1_MIN_N} · 평균<0 / S2 n≥{S2_MIN_N} · 평균<0 · 기간≥{S2_MIN_SPAN_DAYS}일 · "
         f"주 클러스터 부트 P(평균≥0)<{S2_ALPHA} (B={BOOT}, seed {SEED})", "",
         "| 단위 | 층 | 등급 | n | 평균% | 승 | 실현$ | 기간(일) | 주 | P(평균≥0) | 발동 |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in out:
        name = f"{r['unit'][0]}·{r['unit'][1]}" + (f"·{r['regime']}" if r["regime"] else "")
        L.append(f"| {name} | {r['layer']} | {r['tier']} | {_fmt(r['stats'])} | {','.join(r['hits']) or '-'} |")
    L += ["", f"## 발동 {len(hits)}건"]
    for r in hits:
        name = f"{r['unit'][0]}·{r['unit'][1]}" + (f"·{r['regime']}" if r["regime"] else "")
        st = r["stats"]
        L.append(f"- {'+'.join(r['hits'])} {name} ({r['layer']}) n={st['n']} 평균 {st['mean']:+.2f}% → 조치: {r['action']}")
    if ref:
        L += ["", "## 참고 — 정지 중인 전략의 실거래 성적(판정 아님)"]
        for unit, since, st in ref:
            L.append(f"- {unit[0]}·{unit[1]} (정지 {since}) n={st['n']} 평균 {st['mean']:+.2f}%")
    return "\n".join(L) + "\n"


def annotations(hits, n_units, n_rows):
    """GitHub Actions 주석 줄. 자율 사이클 세션은 잡 로그를 못 받는다(외부 저장소 리다이렉트를 gh 가 거부) —
    대신 `GET repos/{o}/{r}/check-runs/{id}/annotations` 로 이 주석을 읽어 판정을 가져간다. 제목은 항상 'steward' 로 시작."""
    if not hits:
        return [f"::notice title=steward 발동 없음::판정 단위 {n_units}개, 실거래 방식D {n_rows}행 — 규칙 {RULES_ID}"]
    out = []
    for r in hits[:10]:                       # 단계당 경고 주석 상한 10
        name = f"{r['unit'][0]}·{r['unit'][1]}" + (f"·{r['regime']}" if r["regime"] else "")
        st = r["stats"]
        msg = f"{name} ({r['layer']}) n={st['n']} 평균 {st['mean']:+.2f}% → 조치: {r['action']}"
        out.append(f"::warning title=steward {'+'.join(r['hits'])}::" + msg.replace("\n", " "))
    return out


def fetch_trades():
    import supabase_client as sc
    cli = sc.get_client("service")
    rows, start = [], 0
    while True:
        page = (cli.table("trades").select("*").range(start, start + 999).execute().data) or []
        rows += page
        if len(page) < 1000:
            return rows
        start += 1000


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--trades-json", help="오프라인 판정용 trades 행 JSON(리스트)")
    ap.add_argument("--notify", action="store_true", help="발동 시 텔레그램")
    ap.add_argument("--out", default="_steward_report.md")
    a = ap.parse_args(argv)
    trades = json.load(io.open(a.trades_json, encoding="utf-8")) if a.trades_json else fetch_trades()
    universe = json.load(io.open("universe.json", encoding="utf-8"))
    routing = json.load(io.open("direction_switch.json", encoding="utf-8"))["routing"]
    out, hits = evaluate(trades, universe, routing)
    md = render(out, hits, reference_rows(trades, universe))
    io.open(a.out, "w", encoding="utf-8").write(md)
    print(md)
    print(f"[steward] 실거래 방식D {len(live_d(trades))}행 · 판정 단위 {sum(r['layer'] == '패턴' for r in out)}개 · 발동 {len(hits)}건")
    for r in hits:
        name = f"{r['unit'][0]}·{r['unit'][1]}" + (f"·{r['regime']}" if r["regime"] else "")
        print(f"[steward] 발동 {'+'.join(r['hits'])} {name} → {r['action']}")
    if os.environ.get("GITHUB_ACTIONS") == "true":
        for line in annotations(hits, sum(r["layer"] == "패턴" for r in out), len(live_d(trades))):
            print(line)
    if a.notify and hits:
        import notify
        notify.send("🧭 <b>운용 점검 — 정지 규칙 발동</b>\n" + "\n".join(
            f"  {'+'.join(r['hits'])} {r['unit'][0]}·{r['unit'][1]}" + (f"·{r['regime']}" if r["regime"] else "")
            + f" n={r['stats']['n']} 평균 {r['stats']['mean']:+.2f}%" for r in hits)
            + "\n다음 자율 사이클이 PR 로 집행합니다(신규 진입만 정지).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
