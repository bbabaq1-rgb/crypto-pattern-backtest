"""
frame_v3.py — 확인 프레임 v3: **국면 기준** 홀드아웃 · 에피소드 OOS · 커버리지 판정
(2026-09-06, 사용자 결정 "1번부터 3번까지 전부 진행해 / 홀드아웃에서만 탈락한 것들 전부 다시 검증해").

## 문제 (v2)

v2 홀드아웃은 '달력상 마지막 365일'이다. 레짐 조건부 셀(bull_btc 에서만 진입 등)은 그 1년의
국면이 결과를 먼저 정한다 — 2025-09~2026-09 는 bear 지배 해라 bull_btc 셀은 신호가 6건(MA180)
이고 그마저 국면 끝자락이다. "규칙이 틀렸다"와 "규칙이 필요로 하는 국면이 채점 구간에 없었다"를
v2 는 구분하지 못한다. 사용자 지적: "지난 1년은 최악의 하락기였는데 홀드아웃을 거기서 하니 통과를
못 한다 — 방향성이 중요하다."

## v3 정의 (결과를 보기 전에 동결)

에피소드   레짐 g 로 라벨된 날짜의 연속 구간. 사이에 g 아닌 날이 EPISODE_GAP(30)일 이하면 하나로
           잇는다(히스테리시스 깜빡임 병합). g == ALL 이면 에피소드 = 달력 연도.
홀드아웃   g != ALL: **g 로 라벨된 날 중 가장 최근 HOLDOUT_DAYS(365)일**(달력상 비연속). 총 g 일수가
           2×365 미만이면 뒤쪽 절반. '가장 최근'은 유지하되 '최근'을 국면 일수로 잰다.
           g == ALL: v2 와 같은 달력 마지막 365일.
분할       신호의 진입 봉 날짜가 홀드아웃 집합에 있으면 holdout, 아니면 train.
E (에피소드 OOS)  신호 n >= EP_MIN_N(5) 인 에피소드('적격')가 2개 이상이고, 그중 평균>0 인 에피소드가
           2개 이상 **이면서 과반**. v2 의 G5(달력 4분위 양수 >= 2)를 대체한다 — 독립된 상승 국면
           여러 개에서 맞는가를 직접 묻는다. 4분위는 진단으로 병기.

판정
  C1  C1 성능: n>=20 · mean>0 · 승률>=35% · boot_p<0.05 (레짐·코호트 k=n 베이스라인)  + E
  C2  holdout n >= HOLDOUT_MIN_N(10) 이고 mean>0
  C2b train 자체가 C1 성능 조건 통과 이고 train n >= holdout n × 0.5
  C3  train 자산곡선 CAGR>0 & Calmar>0 (span = train 달력 폭 − 그 안의 홀드아웃 일수)
  COV 커버리지: 적격 에피소드 >= 2 이고 holdout n >= 10 이고 train n >= 20

  · 성능 조건(mean/승률/boot_p, holdout mean(n>=10 일 때), train 성능, C3)이 하나라도 실패 → REJECTED
  · 성능은 실패 없고 COV 실패 → **INCONCLUSIVE** (국면 표본 부족 — 기각이 아니라 판정 보류)
  · 성능·COV 통과, E 실패(양수 에피소드 <2 또는 과반 미만) → REJECTED
  · 전부 통과 → CONFIRMED

'4년 주기'는 예측 가정으로 쓰지 않는다 — 커버리지 요건(독립 국면 >= 2)으로만 쓴다.

## 적용 범위

게이트 v2 전환 때와 같이 **프레임 변경은 후보 전체에 적용**한다(MA180 만 골라 다시 돌리면 결과를
보고 기준을 바꾼 것이 된다). validate_revival(전 후보) / validate_ma180 / validate_exit_consistency
(three_soldiers_4h) 가 --frame v3 로 이 모듈을 쓴다. 장기 데이터(data_long, 2017~)는 1d 에만 있다 —
4h/1h 셀은 기존 데이터 범위에서 v3 를 적용하고, 에피소드 부족이면 INCONCLUSIVE 로 정직하게 남긴다.
"""
import statistics as st
from datetime import date

import gate

EPISODE_GAP = 30
HOLDOUT_DAYS = 365
HOLDOUT_MIN_N = 10
EP_MIN_N = 5
TRAIN_MIN_RATIO = 0.5
TRAIN_MIN_N = 20


def _ord(d):
    return date.fromisoformat(d).toordinal()


def episodes(regmap, g, gap=EPISODE_GAP):
    """[(start_date, end_date)] — 레짐 g 의 연속 구간(gap 일 이하 끊김은 병합). ALL 은 달력 연도."""
    dates = sorted(regmap)
    if not dates:
        return []
    if g == "ALL":
        years = sorted({d[:4] for d in dates})
        return [(f"{y}-01-01", f"{y}-12-31") for y in years]
    gd = [d for d in dates if regmap[d] == g]
    if not gd:
        return []
    out, s, prev = [], gd[0], gd[0]
    for d in gd[1:]:
        if _ord(d) - _ord(prev) > gap + 1:
            out.append((s, prev)); s = d
        prev = d
    out.append((s, prev))
    return out


def holdout_dates(regmap, g, days=HOLDOUT_DAYS):
    """홀드아웃 날짜 집합. g != ALL: 가장 최근 g 일수 days(총 g 일수 < 2×days 면 뒤쪽 절반). ALL: 달력 마지막 days."""
    dates = sorted(regmap)
    if not dates:
        return set()
    if g == "ALL":
        cut = date.fromordinal(_ord(dates[-1]) - days).isoformat()
        return {d for d in dates if d > cut}          # 정확히 마지막 days 일
    gd = [d for d in dates if regmap[d] == g]
    if not gd:
        return set()
    k = days if len(gd) >= 2 * days else len(gd) // 2
    return set(gd[len(gd) - k:]) if k > 0 else set()


def split(sigs, hold_set):
    train = [s for s in sigs if s["date"] not in hold_set]
    hold = [s for s in sigs if s["date"] in hold_set]
    return train, hold


def episode_of(d, eps):
    for i, (a, b) in enumerate(eps):
        if a <= d <= b:
            return i
    return None


def episode_table(sigs, eps):
    """에피소드별 n/mean/win. 신호가 없는 에피소드도 n=0 으로 남긴다(방향성 표)."""
    rows = []
    for i, (a, b) in enumerate(eps):
        rs = [s["ret"] for s in sigs if a <= s["date"] <= b]
        rows.append(dict(i=i, start=a, end=b, n=len(rs), mean=(st.mean(rs) if rs else None),
                         win=(sum(1 for r in rs if r > 0) / len(rs) if rs else None),
                         qualifying=len(rs) >= EP_MIN_N))
    return rows


def episode_oos(sigs, eps):
    """(ok, qualifying, positive, share) — 적격(n>=EP_MIN_N) 에피소드 >=2, 양수 >=2 이며 과반."""
    tab = episode_table(sigs, eps)
    q = [r for r in tab if r["qualifying"]]
    pos = [r for r in q if r["mean"] > 0]
    profits = [max(0.0, r["mean"] * r["n"]) for r in q]
    share = (max(profits) / sum(profits)) if profits and sum(profits) > 0 else None
    ok = len(q) >= 2 and len(pos) >= 2 and len(pos) * 2 >= len(q)
    return ok, len(q), len(pos), share


def perf_ok(sigs, pool_rets, seed, boot_n=1000):
    """C1 성능 조건(n/mean/승률/boot_p) — OOS 는 별도(E). 반환 (ok, rec)."""
    import random
    rets = [s["ret"] for s in sigs]
    n = len(rets)
    mean = st.mean(rets) if rets else 0.0
    boot_p, base_mean = 1.0, None
    if pool_rets and n:
        rng = random.Random(seed)
        means = [st.mean(rng.choices(pool_rets, k=n)) for _ in range(boot_n)]
        boot_p = sum(1 for m in means if m >= mean) / boot_n
        base_mean = st.mean(means)
    fails = []
    if n < TRAIN_MIN_N: fails.append("n<20")
    if mean <= 0: fails.append("mean<=0")
    if rets and not gate.dist_ok(rets): fails.append(gate.dist_reason(rets))
    if boot_p >= 0.05: fails.append(f"boot_p={boot_p:.3f}")
    rec = dict(n=n, mean=mean, median=(st.median(rets) if rets else 0.0), boot_p=boot_p, base_mean=base_mean,
               edge=(mean - base_mean) if base_mean is not None else None,
               win_rate=gate.win_rate(rets) if rets else 0.0, trimmed_mean=gate.trimmed_mean(rets) if rets else None,
               top5_share=gate.top_share(rets) if rets else None, fails=fails)
    return not fails, rec


def train_span_days(train, hold_set):
    if not train:
        return 1
    lo, hi = min(s["date"] for s in train), max(s["date"] for s in train)
    inside = sum(1 for d in hold_set if lo <= d <= hi)
    return max(1, _ord(hi) - _ord(lo) - inside)


def judge(sigs, pool_rets, regmap, g, equity_fn, seed=42):
    """
    셀 하나(판정 코호트)의 v3 판정.
    sigs: [dict(date, ret, hold, reason, stop_pct, vol, exit_date, t_in, t_out)]
    equity_fn(train_sigs, span_days) -> dict(cagr, mdd, calmar) | None
    반환 dict(verdict, c1_perf, E, c2, c2b, c3, coverage, holdout, train, episodes, ...)
    """
    eps = episodes(regmap, g)
    hold_set = holdout_dates(regmap, g)
    train, hold = split(sigs, hold_set)
    c1_ok, c1 = perf_ok(sigs, pool_rets, seed)
    e_ok, e_q, e_pos, e_share = episode_oos(sigs, eps)
    ho_mean = st.mean(s["ret"] for s in hold) if hold else None
    c2 = len(hold) >= HOLDOUT_MIN_N and ho_mean is not None and ho_mean > 0
    tr_ok, tr = perf_ok(train, pool_rets, seed) if train else (False, dict(n=0, fails=["train 없음"]))
    c2b = tr_ok and len(train) >= len(hold) * TRAIN_MIN_RATIO
    eq = equity_fn(train, train_span_days(train, hold_set)) if train else None
    c3 = bool(eq) and eq["cagr"] > 0 and eq["calmar"] > 0
    cov = e_q >= 2 and len(hold) >= HOLDOUT_MIN_N and len(train) >= TRAIN_MIN_N

    perf_fail = (not c1_ok) or (len(hold) >= HOLDOUT_MIN_N and (ho_mean is None or ho_mean <= 0)) \
        or (len(train) >= TRAIN_MIN_N and not tr_ok) or (train and not c3)
    if perf_fail:
        verdict = "REJECTED"
    elif not cov:
        verdict = "INCONCLUSIVE"
    elif not e_ok:
        verdict = "REJECTED"
    else:
        verdict = "CONFIRMED"
    return dict(verdict=verdict, c1_perf=c1_ok, c1=c1, E=dict(ok=e_ok, qualifying=e_q, positive=e_pos, max_share=e_share),
                c2_holdout=c2, holdout=dict(n=len(hold), mean=ho_mean, days=len(hold_set)),
                c2b_train=c2b, train=dict(n=len(train), gate=tr), c3_equity=c3, equity=eq, coverage=cov,
                episodes=episode_table(sigs, eps), hold_set_size=len(hold_set), frame="v3")


def fmt_episodes(tab, width=1):
    """에피소드 표 한 줄씩 — '방향성' 시각 확인용."""
    out = []
    for r in tab:
        m = "   n/a " if r["mean"] is None else f"{r['mean']*100:+6.2f}%"
        w = "  -  " if r["win"] is None else f"{r['win']*100:3.0f}%"
        out.append(f"      ep{r['i']:<2} {r['start']}~{r['end']}  n={r['n']:>4}  mean={m}  승률 {w}{'  *' if r['qualifying'] else ''}")
    return "\n".join(out)
