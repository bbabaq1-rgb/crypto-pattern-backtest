"""
ai_judge_report.py — AI 판단 레이어 평가 보고 (2026-10-26, 읽기 전용).

Supabase ai_judgments / trades 만 select 하고 아무것도 쓰지 않는다. 매매 경로와 무관하다.
registry `ai_judge_prereg_2026_10_23`(진입) · `ai_exit_prereg_2026_10_26`(청산 검토)의 **사전 등록 기준을 코드로
계산**해 사람이 고르지 않게 한다 — 승격 판단은 여전히 사용자 결정이고 이 보고는 그 근거 표다.

진입(kind=entry) — 표본 단위는 '판단이 붙은 뒤 방식D 로 해소된 거래'. 그림자에서는 모든 신호가 종전대로 진입하므로
  take 집단과 skip∪reduce 집단의 **실제 방식D 수익**을 그대로 비교한다.
    primary  mean(ret|take) − mean(ret|skip∪reduce) ≥ +1.0%p AND mean(ret|skip∪reduce) < 0, 월 블록 부트 1000회 p<.10
    gate     n≥60 또는 그림자 3주 중 늦은 쪽 · skip+reduce 비율 10~70% 밖이면 '필터로 기능 안 함'
    secondary(veto 가상 자산곡선 Calmar, validate_portfolio 프레임)는 OHLC 가 필요해 이 보고에서는 계산하지 않는다 —
    승격 판단 시점에 별도 실행한다. 여기서는 '실현 손익 합(take 만 vs 전부)' 간이 지표만 병기한다.

청산 검토(kind=exit) — 표본 단위는 '검토가 한 번 이상 붙은 뒤 방식D 로 해소된 포지션'. 포지션마다 **첫 exit 제안** 시점의
  마크봉 종가 청산 가상 수익(unreal_ret − 수수료)과 실제 방식D 수익의 차 = adv(exit). exit 제안이 없던 포지션은 첫 검토 시점의
  같은 양 = adv(hold-only) — '그때 나갔으면 어땠나'의 대조군.
    primary  mean(adv|exit) ≥ +0.5%p AND mean(adv|exit) − mean(adv|hold-only) > 0, 월 블록 부트 1000회 p<.10 · n(exit)≥40
    secondary exit 제안 포지션 중 실제 방식D 가 손절로 끝난 비율 > hold-only 포지션의 손절 비율(exit 가 손절을 골라내는가)

표본 집계 키는 (model, prompt_version) — prompt_version 이 없는 구 행(2026-10-23~26)은 'v1' 로 묶는다.
집계는 순수 파이썬(결정론 시드). 네트워크는 main() 의 DB 읽기뿐이고 테스트는 함수만 쓴다.
"""
import json
import random
import statistics as st
import sys
from collections import defaultdict

FEE = 0.002                      # 왕복 수수료(paper_executor.FEE 와 같은 값 — 가상 청산에 붙인다)
ENTRY_PRIMARY_DIFF = 0.010       # +1.0%p
EXIT_PRIMARY_ADV = 0.005         # +0.5%p
BOOT_N = 1000
BOOT_P = 0.10
BOOT_SEED = 20261026
MIN_ENTRY_N = 60
MIN_EXIT_N = 40
FILTER_SHARE = (0.10, 0.70)
SHADOW_START = "2026-10-23"
EXIT_SHADOW_START = "2026-10-26"
V1_LABEL = "v1"
# 집계 키·종류 복원(2026-10-26): 확장 컬럼(kind/prompt_version/unreal_ret/bars_held)이 DB 에 없던 동안 적재된 행은
# insert_tolerant 가 그 컬럼을 뺀 채 기록한다. 그래도 decision 과 features(JSON) 는 항상 남으므로 거기서 되살린다 —
# 안 그러면 SQL 재실행 전 행이 entry 로 오분류되거나(exit 행) 'v1' 그룹으로 갈려 사전 등록 표본(n≥60)이 쪼개진다.
ENTRY_V2 = "entry_v2_2026_10_26"          # == ai_judge.PROMPT_VERSION (test 가 동일성 고정)
EXIT_V1 = "exit_v1_2026_10_26"            # == ai_judge.EXIT_PROMPT_VERSION
EXIT_DECISIONS = ("hold", "exit")
V2_MARKER_KEYS = ("stop_atr", "bar_hour_utc", "sym_recent_n", "book_rows")   # v2 진입 특성에만 있는 키
EXIT_MARKER_KEYS = ("bars_held", "unreal_ret", "mfe", "bars_left")           # 청산 검토 특성에만 있는 키


# ── 로딩 ─────────────────────────────────────────────────────────────────────
def fetch_all(cli, table, page=1000):
    rows, start = [], 0
    while True:
        chunk = (cli.table(table).select("*").range(start, start + page - 1).execute().data) or []
        rows += chunk
        if len(chunk) < page:
            return rows
        start += page


def load_from_db():
    import supabase_client as sc
    cli = sc.get_client("service")
    return fetch_all(cli, "ai_judgments"), fetch_all(cli, "trades")


# ── 공통 ─────────────────────────────────────────────────────────────────────
def _d(x):
    return str(x or "")[:10]


def _month(x):
    return _d(x)[:7]


def feat_of(j):
    """features(JSON 문자열) → dict. 파싱 결과를 행에 캐시하되(_feat) 원본 문자열이 바뀌면 다시 푼다. 깨진 JSON·None 은 {}."""
    raw = j.get("features")
    if j.get("_feat") is not None and j.get("_feat_src") is raw:
        return j["_feat"]
    try:
        f = json.loads(raw) if isinstance(raw, str) and raw else (raw if isinstance(raw, dict) else {})
    except Exception:
        f = {}
    if not isinstance(f, dict):
        f = {}
    j["_feat"], j["_feat_src"] = f, raw
    return f


def kind_of(j):
    """entry / exit. kind 컬럼이 비면 decision(두 어휘가 서로 겹치지 않는다) → features 키로 복원."""
    k = j.get("kind")
    if k:
        return k
    d = j.get("decision")
    if d in EXIT_DECISIONS:
        return "exit"
    if d:
        return "entry"
    f = feat_of(j)
    return "exit" if any(key in f for key in EXIT_MARKER_KEYS) else "entry"


def pv_of(j):
    """prompt_version. 비면 exit 행은 EXIT_V1(유일한 청산 판), entry 행은 v2 마커 키가 있으면 ENTRY_V2, 없으면 v1."""
    pv = j.get("prompt_version")
    if pv:
        return pv
    if kind_of(j) == "exit":
        return EXIT_V1
    f = feat_of(j)
    return ENTRY_V2 if any(key in f for key in V2_MARKER_KEYS) else V1_LABEL


def col_or_feat(j, key):
    """컬럼 값이 없으면(미존재 컬럼이 제거된 행) features 의 같은 키로 대체."""
    v = j.get(key)
    return v if v is not None else feat_of(j).get(key)


def group_key(j):
    return (j.get("model") or "?", pv_of(j))


def d_trade_index(trades):
    """방식D 거래를 (symbol, pattern, direction, entry_date) 로 묶는다. ret 는 소수(return_pct/100)."""
    idx = defaultdict(list)
    for t in trades or []:
        if (t.get("method") or "") != "D" or t.get("return_pct") is None:
            continue
        key = (t.get("symbol"), t.get("pattern"), t.get("direction"), _d(t.get("entry_date")))
        idx[key] += [dict(t, ret=float(t["return_pct"]) / 100.0)]
    for k in idx:
        idx[k].sort(key=lambda t: _d(t.get("exit_date")))
    return idx


def match_trade(idx, j):
    """판단 행 j 에 해당하는 방식D 거래. 같은 키가 여럿이면 판단 시각 이후에 청산된 첫 거래."""
    key = (j.get("symbol"), j.get("pattern"), j.get("direction"), _d(j.get("entry_date")))
    cands = idx.get(key) or []
    jd = _d(j.get("judged_at"))
    for t in cands:
        if _d(t.get("exit_date")) >= jd:
            return t
    return None


def is_stop_trade(t):
    return "손절" in str(t.get("exit_reason") or "") and float(t.get("ret") or 0) < 0 \
        or str(t.get("exit_reason") or "").startswith("stop")


def _mean(xs):
    return st.mean(xs) if xs else None


def month_block_boot(a, b, n=BOOT_N, seed=BOOT_SEED):
    """
    a, b: [(month, value)]. H1: mean(a) − mean(b) > 0. 월을 블록으로 복원추출해(두 집단이 같은 달을 공유)
    diff ≤ 0 인 비율을 p 로 돌려준다. 어느 쪽이든 비면 None. 결정론(시드 고정).
    """
    if not a or not b:
        return None
    months = sorted({m for m, _ in a} | {m for m, _ in b})
    am, bm = defaultdict(list), defaultdict(list)
    for m, v in a:
        am[m] += [v]
    for m, v in b:
        bm[m] += [v]
    rnd = random.Random(seed)
    worse = 0
    for _ in range(n):
        pick = [rnd.choice(months) for _ in months]
        xa = [v for m in pick for v in am.get(m, [])]
        xb = [v for m in pick for v in bm.get(m, [])]
        if not xa or not xb:
            worse += 1          # 추첨에서 한 집단이 비면 '우위 못 보임' 으로 센다(보수)
            continue
        if st.mean(xa) - st.mean(xb) <= 0:
            worse += 1
    return worse / n


# ── 진입 평가 ─────────────────────────────────────────────────────────────────
def entry_eval(judgments, trades, min_n=MIN_ENTRY_N):
    """(model, prompt_version) 별 진입 판단 평가. 반환 {group: dict}."""
    idx = d_trade_index(trades)
    groups = defaultdict(lambda: {"n_judged": 0, "n_error": 0, "decisions": defaultdict(int),
                                  "code_action": defaultdict(int), "resolved": [], "pending": 0,
                                  "latency_ms": [], "tokens_in": 0, "tokens_out": 0})
    for j in judgments or []:
        if kind_of(j) != "entry":
            continue
        g = groups[group_key(j)]
        g["n_judged"] += 1
        g["code_action"][j.get("code_action") or "?"] += 1
        g["tokens_in"] += int(j.get("tokens_in") or 0)
        g["tokens_out"] += int(j.get("tokens_out") or 0)
        if j.get("latency_ms") is not None:
            g["latency_ms"] += [int(j["latency_ms"])]
        if not j.get("decision"):
            g["n_error"] += 1
            continue
        g["decisions"][j["decision"]] += 1
        t = match_trade(idx, j)
        if t is None:
            g["pending"] += 1
            continue
        g["resolved"] += [{"decision": j["decision"], "ret": t["ret"], "month": _month(t.get("entry_date")),
                           "live": bool(t.get("live_mode")), "confidence": j.get("confidence"),
                           "stop": is_stop_trade(t), "pnl_live_usd": t.get("pnl_live_usd"),
                           "symbol": j.get("symbol"), "pattern": j.get("pattern")}]
    out = {}
    for key, g in groups.items():
        take = [r for r in g["resolved"] if r["decision"] == "take"]
        other = [r for r in g["resolved"] if r["decision"] != "take"]
        n_dec = sum(g["decisions"].values())
        share = (g["decisions"]["skip"] + g["decisions"]["reduce"]) / n_dec if n_dec else None
        m_take, m_other = _mean([r["ret"] for r in take]), _mean([r["ret"] for r in other])
        diff = (m_take - m_other) if (m_take is not None and m_other is not None) else None
        p = month_block_boot([(r["month"], r["ret"]) for r in take], [(r["month"], r["ret"]) for r in other])
        n_res = len(g["resolved"])
        live_pnl_all = sum(float(r["pnl_live_usd"]) for r in g["resolved"] if r["pnl_live_usd"] is not None)
        live_pnl_take = sum(float(r["pnl_live_usd"]) for r in take if r["pnl_live_usd"] is not None)
        if n_res < min_n:
            verdict = f"표본 부족(해소 {n_res}/{min_n})"
        elif share is None or not (FILTER_SHARE[0] <= share <= FILTER_SHARE[1]):
            verdict = "판정 불가 — 필터로 기능 안 함(skip+reduce 비율 10~70% 밖)"
        elif diff is not None and diff >= ENTRY_PRIMARY_DIFF and m_other < 0 and p is not None and p < BOOT_P:
            verdict = "PRIMARY 충족 → secondary(veto 가상 자산곡선) 별도 실행 후 veto 전환 제안(사용자 결정)"
        else:
            verdict = "PRIMARY 미충족"
        out[key] = dict(n_judged=g["n_judged"], n_error=g["n_error"], decisions=dict(g["decisions"]),
                        code_action=dict(g["code_action"]), pending=g["pending"], n_resolved=n_res,
                        n_take=len(take), n_other=len(other), mean_take=m_take, mean_other=m_other, diff=diff,
                        win_take=_mean([1.0 if r["ret"] > 0 else 0.0 for r in take]),
                        win_other=_mean([1.0 if r["ret"] > 0 else 0.0 for r in other]),
                        stop_take=_mean([1.0 if r["stop"] else 0.0 for r in take]),
                        stop_other=_mean([1.0 if r["stop"] else 0.0 for r in other]),
                        boot_p=p, filter_share=share, verdict=verdict,
                        live_pnl_all=live_pnl_all, live_pnl_take_only=live_pnl_take,
                        latency_med=(st.median(g["latency_ms"]) if g["latency_ms"] else None),
                        tokens_in=g["tokens_in"], tokens_out=g["tokens_out"],
                        calibration=calibration(g["resolved"]))
    return out


def calibration(resolved):
    """confidence 구간별 (n, 승률, 평균) — take 와 skip∪reduce 를 따로. 확신이 결과를 가르는지 본다."""
    bins = [(0.0, 0.5), (0.5, 0.7), (0.7, 0.85), (0.85, 1.01)]
    out = {}
    for lo, hi in bins:
        for grp in ("take", "other"):
            xs = [r["ret"] for r in resolved if r.get("confidence") is not None and lo <= float(r["confidence"]) < hi
                  and ((r["decision"] == "take") == (grp == "take"))]
            if xs:
                out[f"{grp} [{lo:.2f},{hi if hi <= 1 else 1.0:.2f})"] = dict(
                    n=len(xs), win=sum(1 for x in xs if x > 0) / len(xs), mean=st.mean(xs))
    return out


# ── 청산 검토 평가 ─────────────────────────────────────────────────────────────
def exit_eval(judgments, trades, min_n=MIN_EXIT_N):
    """
    (model, prompt_version) 별 청산 검토 평가. 포지션 키 = (symbol, pattern, direction, entry_date).
    adv = (unreal_ret − FEE) − 실제 방식D ret : 양수면 '그때 나갔으면 더 좋았다'.
    """
    idx = d_trade_index(trades)
    by_pos = defaultdict(list)
    meta = defaultdict(lambda: {"n_rows": 0, "n_error": 0, "decisions": defaultdict(int),
                                "tokens_in": 0, "tokens_out": 0})
    for j in judgments or []:
        if kind_of(j) != "exit":
            continue
        g = meta[group_key(j)]
        g["n_rows"] += 1
        g["tokens_in"] += int(j.get("tokens_in") or 0)
        g["tokens_out"] += int(j.get("tokens_out") or 0)
        if not j.get("decision"):
            g["n_error"] += 1
            continue
        g["decisions"][j["decision"]] += 1
        key = (group_key(j), j.get("symbol"), j.get("pattern"), j.get("direction"), _d(j.get("entry_date")))
        by_pos[key] += [j]
    per_group = defaultdict(lambda: {"exit": [], "hold": [], "open": 0, "unmatched": 0})
    for key, revs in by_pos.items():
        gk = key[0]
        revs.sort(key=lambda r: str(r.get("judged_at") or ""))
        cands = idx.get(key[1:]) or []
        trade = None
        for t in cands:
            if _d(t.get("exit_date")) >= _d(revs[0].get("judged_at")):
                trade = t
                break
        if trade is None:
            # 거래가 아직 없으면 미해소, 첫 검토보다 먼저 청산된 거래뿐이면 매칭 불가(검토 시점에 포지션이 없었다)
            per_group[gk]["open" if not cands else "unmatched"] += 1
            continue
        first_exit = next((r for r in revs if r.get("decision") == "exit"
                           and _d(r.get("judged_at")) <= _d(trade.get("exit_date"))), None)
        pick = first_exit or revs[0]
        unreal = col_or_feat(pick, "unreal_ret")
        if unreal is None:
            continue
        adv = (float(unreal) - FEE) - trade["ret"]
        rec = {"adv": adv, "month": _month(trade.get("entry_date")), "stop": is_stop_trade(trade),
               "actual": trade["ret"], "virtual": float(unreal) - FEE, "bars_held": col_or_feat(pick, "bars_held"),
               "symbol": key[1], "pattern": key[2], "confidence": pick.get("confidence"), "n_reviews": len(revs)}
        per_group[gk]["exit" if first_exit else "hold"] += [rec]
    out = {}
    for gk in set(meta) | set(per_group):
        g, pg = meta[gk], per_group[gk]
        ex, ho = pg["exit"], pg["hold"]
        m_ex, m_ho = _mean([r["adv"] for r in ex]), _mean([r["adv"] for r in ho])
        p = month_block_boot([(r["month"], r["adv"]) for r in ex], [(r["month"], r["adv"]) for r in ho])
        stop_ex, stop_ho = _mean([1.0 if r["stop"] else 0.0 for r in ex]), _mean([1.0 if r["stop"] else 0.0 for r in ho])
        if len(ex) < min_n:
            verdict = f"표본 부족(exit 제안 해소 {len(ex)}/{min_n})"
        elif (m_ex is not None and m_ex >= EXIT_PRIMARY_ADV and m_ho is not None and m_ex - m_ho > 0
              and p is not None and p < BOOT_P):
            verdict = "PRIMARY 충족 — 실효 부여는 CLAUDE.md 원칙 ②(청산 집행은 코드) 개정 + 사용자 결정"
        else:
            verdict = "PRIMARY 미충족"
        out[gk] = dict(n_rows=g["n_rows"], n_error=g["n_error"], decisions=dict(g["decisions"]),
                       n_pos_open=pg["open"], n_unmatched=pg["unmatched"], n_exit=len(ex), n_hold=len(ho),
                       mean_adv_exit=m_ex, mean_adv_hold=m_ho,
                       mean_actual_exit=_mean([r["actual"] for r in ex]), mean_virtual_exit=_mean([r["virtual"] for r in ex]),
                       stop_rate_exit=stop_ex, stop_rate_hold=stop_ho, boot_p=p, verdict=verdict,
                       secondary_ok=(stop_ex is not None and stop_ho is not None and stop_ex > stop_ho),
                       tokens_in=g["tokens_in"], tokens_out=g["tokens_out"])
    return out


# ── 근거 집계 ─────────────────────────────────────────────────────────────────
def reasons_tally(judgments, decision_in=("skip", "reduce", "exit"), top=12):
    cnt = defaultdict(int)
    for j in judgments or []:
        if j.get("decision") not in decision_in or not j.get("reasons"):
            continue
        try:
            rs = json.loads(j["reasons"]) if isinstance(j["reasons"], str) else list(j["reasons"])
        except Exception:
            continue
        for r in rs:
            cnt[str(r).strip().lower()[:80]] += 1
    return sorted(cnt.items(), key=lambda kv: (-kv[1], kv[0]))[:top]


# ── 렌더 ─────────────────────────────────────────────────────────────────────
def _pct(x, d=2):
    return "-" if x is None else f"{x * 100:+.{d}f}%"


def _rate(x):
    return "-" if x is None else f"{x * 100:.0f}%"


def _p(x):
    return "-" if x is None else f"{x:.3f}"


def render(entry, exits, reasons, n_judgments, today=None):
    L = [f"# AI 판단 레이어 — 그림자 평가 보고 ({today or ''})", "",
         f"ai_judgments 행 {n_judgments}건. 기준·표본 정의는 ai_judge_report.py 상단 / registry 사전 등록. **읽기 전용 — 실거래 무변경.**", ""]
    L += ["## 1. 진입 판단 (kind=entry)", "",
          "| 그룹(model · prompt_version) | 판단 | 오류 | take/reduce/skip | 해소 | 미해소 | mean take | mean skip∪reduce | diff | p(월부트) | 승률 take/other | 손절률 take/other | 필터 비율 | 판정 |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for (model, pv), g in sorted(entry.items()):
        d = g["decisions"]
        L += [f"| {model} · {pv} | {g['n_judged']} | {g['n_error']} | {d.get('take', 0)}/{d.get('reduce', 0)}/{d.get('skip', 0)} | "
              f"{g['n_resolved']} | {g['pending']} | {_pct(g['mean_take'])} | {_pct(g['mean_other'])} | {_pct(g['diff'])} | "
              f"{_p(g['boot_p'])} | "
              f"{_rate(g['win_take'])}/{_rate(g['win_other'])} | {_rate(g['stop_take'])}/{_rate(g['stop_other'])} | "
              f"{_rate(g['filter_share'])} | {g['verdict']} |"]
    for (model, pv), g in sorted(entry.items()):
        L += ["", f"- {model} · {pv}: code_action {dict(sorted(g['code_action'].items()))} · 지연 중앙 {g['latency_med']}ms · "
              f"토큰 in/out {g['tokens_in']}/{g['tokens_out']} · 실현 $ 전부 {g['live_pnl_all']:+.2f} vs take 만 {g['live_pnl_take_only']:+.2f}(간이, 자산곡선 아님)"]
        if g["calibration"]:
            L += ["  - 확신 구간별(n·승률·평균): " + "; ".join(
                f"{k} n={v['n']} 승률 {v['win'] * 100:.0f}% 평균 {v['mean'] * 100:+.2f}%" for k, v in g["calibration"].items())]
    L += ["", "## 2. 청산 검토 (kind=exit, 그림자 — 어떤 경로로도 주문에 닿지 않는다)", "",
          "| 그룹 | 검토 행 | 오류 | hold/exit | 미해소 포지션 | exit 제안 해소 | hold-only 해소 | mean adv(exit) | mean adv(hold-only) | p(월부트) | 실제 손절률 exit/hold | 판정 |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for (model, pv), g in sorted(exits.items()):
        d = g["decisions"]
        L += [f"| {model} · {pv} | {g['n_rows']} | {g['n_error']} | {d.get('hold', 0)}/{d.get('exit', 0)} | {g['n_pos_open']} | "
              f"{g['n_exit']} | {g['n_hold']} | {_pct(g['mean_adv_exit'])} | {_pct(g['mean_adv_hold'])} | "
              f"{_p(g['boot_p'])} | "
              f"{_rate(g['stop_rate_exit'])}/{_rate(g['stop_rate_hold'])} | {g['verdict']} |"]
    L += ["", "adv = (마크봉 종가 청산 가상 수익 − 수수료 0.2%) − 실제 방식D 수익. 양수 = '그때 나갔으면 더 좋았다'. "
          "secondary(exit 제안 포지션의 실제 손절률 > hold-only 손절률)는 표의 손절률 열로 읽는다."]
    if reasons:
        L += ["", "## 3. skip/reduce/exit 근거 상위", ""] + [f"- {n}× {r}" for r, n in reasons]
    L += ["", "---", "승격·실효 부여는 사용자 결정. 프롬프트·특성·모델을 바꾸면 prompt_version 을 올려 표본을 새로 센다(사후 변경 금지)."]
    return "\n".join(L)


def telegram_text(entry, exits, today=None):
    lines = [f"🧪 AI 판단 그림자 보고 {today or ''}"]
    for (model, pv), g in sorted(entry.items()):
        lines += [f"진입 {pv}: 판단 {g['n_judged']} 해소 {g['n_resolved']} | take {_pct(g['mean_take'])} vs other {_pct(g['mean_other'])}"
                  f" | p {'-' if g['boot_p'] is None else round(g['boot_p'], 3)} | {g['verdict']}"]
    for (model, pv), g in sorted(exits.items()):
        lines += [f"청산 {pv}: 검토 {g['n_rows']} exit해소 {g['n_exit']} | adv {_pct(g['mean_adv_exit'])} vs hold {_pct(g['mean_adv_hold'])}"
                  f" | p {'-' if g['boot_p'] is None else round(g['boot_p'], 3)} | {g['verdict']}"]
    if len(lines) == 1:
        lines += ["기록 없음 — ANTHROPIC_API_KEY / ai_judgments 테이블 확인"]
    return "\n".join(lines)[:3500]


def build(judgments, trades, today=None):
    entry = entry_eval(judgments, trades)
    exits = exit_eval(judgments, trades)
    reasons = reasons_tally(judgments)
    return entry, exits, render(entry, exits, reasons, len(judgments or []), today)


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    judgments, trades = load_from_db()
    entry, exits, md = build(judgments, trades, today)
    print(md)
    out = "_ai_judge_report.md"
    for i, a in enumerate(argv):
        if a == "--out" and i + 1 < len(argv):
            out = argv[i + 1]
    with open(out, "w", encoding="utf-8") as f:
        f.write(md + "\n")
    if "--notify" in argv:
        import notify
        print("[notify]", "sent" if notify.send(telegram_text(entry, exits, today)) else "skipped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
