"""
validate_cadence.py — 재구성 **주기**를 유니버스 고정 상태에서 다시 잰다
(2026-09-07 사전 등록, 사용자 지시 "월 재구성 유니버스 구성해서 돌려줘").

## 배경 — 왜 다시 재나
validate_basket(run 34133975572) 의 민감도 표에서 월 재구성이 압도적으로 좋아 보였다
(liquidity Calmar none 0.35 / quarterly 0.46 / **monthly 1.05**, 최종 6.4x / 5.7x / **32.5x**).
그러나 그 표는 판정 대상이 아니었고, 사전 등록에 적어둔 **교란이 그대로 남아 있었다**:
재구성 arm 은 매 재구성일마다 그날의 거래대금 상위를 새로 뽑으므로 **그 사이에 상장된 코인**에
접근할 수 있고, 재구성 없음 arm 은 시작일에 존재한 코인만 끝까지 들고 간다. 즉 월 우위의 상당 부분이
'주기'가 아니라 **유니버스 접근**일 수 있다. 여기서 그 교란을 제거한다.

## 이 시험이 바꾸는 것 — 유니버스 고정
창 시작 전에 이미 상장돼 있고(형성일 기준 이력 확보) 창 끝까지 살아 있는 코인만으로 **고정 집합**을
만든다. 모든 주기 arm 이 매 재구성일에 **같은 후보 집합**에서 고른다. 신규 상장 접근 경로가 사라진다.
  · 대가 1: 표본이 작아진다(W1 32 · W2 73 코인). 절대 수치는 basket 실행과 비교 불가 — **arm 간 비교만 읽는다.**
  · 대가 2: '끝까지 살아 있는'을 요구하므로 **생존 편향이 더 세진다**(상장폐지 코인 제외). 결과 전에 적는다.

## 재구성이 실제로 하는 일은 셋이다 — 분해해서 잰다
재구성일에 코드가 하는 일: (1) 거래대금 순위로 **종목 재선택** (2) 자본 **균등 재배분** (3) 띠 규칙의
**진입가 앵커 P 를 그날 종가로 리셋**. (3) 은 이 규칙에서 특히 크다 — 앵커를 리셋하지 않으면 손절 뒤
P 로 못 돌아온 종목은 영원히 현금으로 남지만, 리셋하면 낮아진 가격에 다시 걸린다.
  · arm `reselect` = (1)+(2)+(3)  — basket 실행의 월 재구성과 같은 동작
  · arm `reweight` = (2)+(3)      — 시작일 종목 고정, 균등 재배분 + 앵커 리셋
  · arm `anchor`   = (3)          — 시작일 종목 고정, 비중은 흘러가게 두고 앵커만 리셋
  · `none` 은 세 arm 이 정의상 동일(테스트로 고정)

## 동결 파라미터
  · 규칙·비용: band_rule 확정판 — 손절 1%, 재매수는 진입가 P, 슬리피지 0.141%, 수수료 편도 0.1%.
    재구성(앵커 리셋) 1회당 왕복 2회 수수료. 선택 기준은 **liquidity 고정**(basket 판정 = '거래대금 상위 N').
  · 주기: none / weekly 7 / biweekly 14 / monthly 30 / quarterly 91 / semiannual 182 일.
  · 창 W1 2019-06-01~2026-09-06 (이력 2018-06-01 이전, N 5/10/20) · W2 2022-01-01~2026-09-06
    (이력 2021-01-01 이전, N 5/10/20/40). **W2 는 W1 후반과 겹치므로 독립 표본이 아니다** —
    유니버스 크기·기간에 대한 강건성 확인이지 독립 재현이 아니다(결과 전에 적는다).
  · **주 판정 셀: W1 · N=20 · monthly.**  무작위 귀무분포 200회(시드 42), 95백분위.

## 판정 (사전 등록)
  J1 효과 존재    : W1 monthly `reselect` Calmar > 같은 창 `none` Calmar, **그리고** N 격자 3개 중 >=2 에서 같은 부호
  J2 선택 정보    : W1 monthly `reselect` Calmar > monthly 무작위선택 200회 분포의 95백분위
  J3 재선택 기여  : W1 monthly `reselect` > W1 monthly `reweight` (분해에서 재선택 단계가 양수)
  J4 창 강건성    : W2 에서도 monthly `reselect` > `none`
  판정 우선순위:
    J1 실패                    -> **CONFOUNDED_BY_UNIVERSE** (원래 월 우위는 신규 상장 접근이었다)
    J1 통과·J4 실패            -> **UNSTABLE** (한 창에서만)
    J1·J4 통과·(J2 또는 J3 실패) -> **MECHANISM_NOT_SELECTION** (이득은 앵커 리셋/재균등화이지 재선택이 아님)
    전부 통과                  -> **CADENCE_CONFIRMED** (월 재구성 채택 후보)

## 사전 확률 — 결과를 보기 전에 기록한다
유니버스를 고정하면 월 우위가 **크게 줄어들 것**으로 본다. 남는 부분이 있다면 그 대부분은 (3) 앵커 리셋
(하락 뒤 낮은 가격에 다시 앵커를 잡는 성질)이지 (1) 재선택이 아닐 것이다. 즉 가장 그럴듯한 결과는
CONFOUNDED_BY_UNIVERSE 또는 MECHANISM_NOT_SELECTION 이다. 어느 쪽이 나와도 실패가 아니라 답이다.

## 실행 전 수정 1건 (2026-09-07, 로컬 스모크에서 발견 — 공개)
로컬(장기 데이터 81 코인)에서 돌려보니 W1 고정 유니버스가 18 코인이라 **N=20 이 후보 전부를 고르는
퇴화 상태**였고, 그 상태에서 reselect ≡ reweight ≡ random 이 되어 J2·J3 가 **2e-15 부동소수 잡음**으로
'통과'하고 CADENCE_CONFIRMED 가 찍혔다. 판정 기준 자체는 바꾸지 않고 **타당성 가드 3개**를 넣는다
(전부 판정을 느슨하게가 아니라 엄격하게 만드는 방향):
  · `MAX_SELECT_RATIO 0.75` — 주 판정 셀이 후보의 75% 초과를 고르면 선택 arm 이 성립하지 않으므로
    J2·J3 를 읽지 않고 **INCONCLUSIVE_DEGENERATE**.
  · `EPS 1e-6` — Calmar 비교의 최소 마진(부동소수 잡음이 판정을 정하지 않게).
  · D5 진단 추가 — 재구성 시장가 슬리피지 0 / 0.05 / 0.141% 민감도. **주 판정의 비용 모형은 사전 등록
    그대로(수수료만)** 이고 D5 는 서술이다. 재구성은 예약 시장가라 δ(트리거 추격 비용)를 그대로 쓰는 것이
    과대일 수 있어 판정에 넣지 않는다.
로컬 스모크의 수치는 18 코인 퇴화 판이라 **결과가 아니다**. 러너(장기 248 코인, W1 32 · W2 73)가 본판.

**DEPLOY_ON_PASS=False.** CADENCE_CONFIRMED 가 나와도 실거래 반영 없음 — 이건 기존 패턴 시스템과 별개
시스템이고, 관찰 기간(~2026-10-06) 중 실거래 변경은 사용자 결정.

진단(판정 아님): D1 수수료 스트레스(편도 0.2%) · D2 재구성 횟수·연 수수료 부담 · D3 주기 전 격자 단조성 ·
D4 **띠 규칙 없는 그냥 보유 바스켓**의 같은 주기 재균등화(고전적 리밸런싱 프리미엄이 따로 있는지).

실행: python validate_cadence.py [--quick]      출력: _cadence.json + RESULT_JSON
"""
import json
import random
import statistics as st
import sys

import validate_regime_split_all as va

# ── 동결 ─────────────────────────────────────────────────────────────────────────────────────
STOP = 0.01
FEE = 0.001
SLIP = 0.00141
FEE_STRESS = 0.002
CADENCES = {"none": None, "weekly": 7, "biweekly": 14, "monthly": 30, "quarterly": 91, "semiannual": 182}
ARMS = ("reselect", "reweight", "anchor")
WINDOWS = (
    dict(name="W1", start="2019-06-01", end="2026-09-06", hist_by="2018-06-01", n_grid=(5, 10, 20)),
    dict(name="W2", start="2022-01-01", end="2026-09-06", hist_by="2021-01-01", n_grid=(5, 10, 20, 40)),
)
PRIMARY = dict(window="W1", n=20, cadence="monthly")
RANDOM_DRAWS, SEED, PCTL = 200, 42, 95
EPS = 1e-6                 # Calmar 비교 최소 마진 — 부동소수 잡음이 판정을 정하지 않게
MAX_SELECT_RATIO = 0.75    # 주 판정 셀은 N <= 0.75 x 고정 유니버스 크기여야 한다(아래 주석)
RESET_SLIP_GRID = (0.0, 0.0005, 0.00141)   # D5 진단: 재구성 시장가 슬리피지 민감도
TURNOVER_WIN = 30
DEPLOY_ON_PASS = False


# ── 데이터 ───────────────────────────────────────────────────────────────────────────────────
def all_symbols():
    import glob, os
    import detlib
    long_syms = {os.path.basename(p).split("_1d")[0].upper() for p in glob.glob(f"{detlib.LONG_DIR}/*_1d.csv.gz")}
    return sorted(set(va._syms()) | long_syms)


def fixed_universe(rows_1d, start, end, hist_by):
    """창 전체를 관통하는 고정 집합: 첫 봉 <= hist_by 이고 마지막 봉 >= end."""
    out = []
    for s, r in rows_1d.items():
        if r and r[0]["date"] <= hist_by and r[-1]["date"] >= end:
            out.append(s)
    return sorted(out)


def prep(rows_1d, syms):
    """종목별 date->index 와 거래대금 시계열을 한 번만 만든다."""
    idx, tv = {}, {}
    for s in syms:
        r = rows_1d[s]
        idx[s] = {x["date"]: k for k, x in enumerate(r)}
        acc, series = 0.0, [None] * len(r)
        for k, x in enumerate(r):
            acc += x["c"] * x["v"]
            if k >= TURNOVER_WIN:
                acc -= r[k - TURNOVER_WIN]["c"] * r[k - TURNOVER_WIN]["v"]
            if k >= TURNOVER_WIN - 1:
                series[k] = acc / TURNOVER_WIN
        tv[s] = series
    return idx, tv


def rank_at(syms, idx, tv, date_):
    """그날 거래대금 내림차순 종목 목록(고정 집합 안에서)."""
    cand = []
    for s in syms:
        i = idx[s].get(date_)
        if i is None:
            continue
        v = tv[s][i]
        if v:
            cand.append((v, s))
    cand.sort(reverse=True)
    return [s for _, s in cand]


# ── 띠 규칙 슬리브 ───────────────────────────────────────────────────────────────────────────
def sleeve_vals(rows, idx, d0, d1, dates_seg, resets=(), fee=FEE, hold=False, reset_slip=0.0):
    """
    d0 종가로 진입한 뒤 dates_seg 각 날짜의 가치(진입 수수료 포함, 시작 ~= 1-fee).
    resets 에 든 날짜에는 종가로 청산 후 즉시 재진입(앵커 P 갱신, 왕복 수수료 2회).
    hold=True 면 띠 규칙 없이 그냥 보유(리셋은 수수료만 물고 앵커 개념 없음).
    """
    i0, i1 = idx.get(d0), idx.get(d1)
    if i0 is None or i1 is None or i1 <= i0:
        return None
    P = rows[i0]["c"]
    if P <= 0:
        return None
    resets = set(resets)
    E = 1.0 * (1 - fee)
    units = E / P
    inpos = True
    last = E
    out = {}
    for j in range(i0, i1 + 1):
        x = rows[j]
        if j > i0 and not hold:
            S = P * (1 - STOP)
            if inpos:
                if x["l"] <= S:
                    fill = min(S, x["o"]) if x["o"] < S else S * (1 - SLIP)
                    E = units * fill * (1 - fee)
                    units, inpos = 0.0, False
            elif x["h"] >= P:
                px = P * (1 + SLIP)
                E *= (1 - fee)
                units, inpos = E / px, True
        if j > i0 and x["date"] in resets:
            val = units * x["c"] if units > 0 else E
            E = val * (1 - fee) * (1 - fee) * (1 - reset_slip) ** 2
            P = x["c"]
            if P <= 0:
                return None
            units, inpos = E / P, True
        last = units * x["c"] if units > 0 else E
        out[x["date"]] = last
    vals, cur = [], out.get(d0, 1 - fee)
    for d in dates_seg:
        if d in out:
            cur = out[d]
        vals.append(cur)
    return vals


# ── 바스켓 ───────────────────────────────────────────────────────────────────────────────────
def marks_of(dates, cadence_days):
    if not cadence_days:
        return [0]
    return list(range(0, len(dates), cadence_days))


def basket(rows_1d, dates, syms, idx, tv, n, cadence_days, arm, fee=FEE, hold=False, seed=None, reset_slip=0.0):
    """전 구간 자산곡선(시작 1.0). arm: reselect / reweight / anchor."""
    marks = marks_of(dates, cadence_days)
    mark_dates = [dates[m] for m in marks[1:]]
    rng = random.Random(seed) if seed is not None else None

    def pick_at(date_, k):
        order = rank_at(syms, idx, tv, date_)
        if not order:
            return []
        if rng is not None:
            return rng.sample(order, min(n, len(order)))
        return order[:n]

    if arm == "anchor":                                   # 종목·비중 고정, 앵커만 리셋
        picks = pick_at(dates[0], n)
        sub = [v for s in picks
               if (v := sleeve_vals(rows_1d[s], idx[s], dates[0], dates[-1], dates,
                                    resets=mark_dates, fee=fee, hold=hold, reset_slip=reset_slip))]
        if not sub:
            return None
        return [sum(v[t] for v in sub) / len(sub) for t in range(len(dates))]

    fixed = pick_at(dates[0], n) if arm == "reweight" else None
    eq = [1.0] * len(dates)
    cap = 1.0
    for m, start in enumerate(marks):
        end = marks[m + 1] - 1 if m + 1 < len(marks) else len(dates) - 1
        if end <= start:
            continue
        d0, d1 = dates[start], dates[end]
        picks = fixed if fixed is not None else pick_at(d0, n)
        seg_dates = dates[start:end + 1]
        sub = [v for s in picks
               if (v := sleeve_vals(rows_1d[s], idx[s], d0, d1, seg_dates, fee=fee, hold=hold))]
        # 세그먼트 방식은 재구성 경계에서 청산·재진입하므로 슬리피지는 아래 cap 계산에 건다
        if not sub:
            continue
        seg = [cap * sum(v[t] for v in sub) / len(sub) for t in range(len(seg_dates))]
        for t, v in enumerate(seg):
            eq[start + t] = v
        cap = seg[-1] * (1 - fee) * (1 - reset_slip) ** 2 if m + 1 < len(marks) else seg[-1]   # 재구성일 청산 수수료·슬리피지
    return eq


def stats(eq, days):
    if not eq or eq[0] <= 0 or eq[-1] <= 0:
        return dict(final=None, cagr=None, mdd=None, calmar=None)
    peak, mdd = eq[0], 0.0
    for v in eq:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1)
    yrs = days / 365.25
    cagr = eq[-1] ** (1 / yrs) - 1 if yrs > 0 else None
    return dict(final=eq[-1], cagr=cagr, mdd=mdd,
                calmar=(cagr / abs(mdd) if (cagr is not None and mdd < 0) else None))


def decide(j1, j2, j3, j4, degenerate=False):
    """사전 등록 우선순위. degenerate=True 면 선택 arm 이 성립하지 않아 J2·J3 를 못 읽는다."""
    if not j1:
        return "CONFOUNDED_BY_UNIVERSE"
    if not j4:
        return "UNSTABLE"
    if degenerate:
        return "INCONCLUSIVE_DEGENERATE"
    if not (j2 and j3):
        return "MECHANISM_NOT_SELECTION"
    return "CADENCE_CONFIRMED"


def gt(a, b):
    """Calmar 비교 — EPS 미만 차이는 같다고 본다(부동소수 잡음 방지)."""
    return a is not None and b is not None and a > b + EPS


def _f(v, w=8, pct=False):
    if v is None:
        return " " * (w - 1) + "-"
    return f"{v*100:{w}.1f}" if pct else f"{v:{w}.2f}"


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    quick = "--quick" in argv
    print(f"재구성 주기 시험(유니버스 고정) | 손절 {STOP*100:.0f}% 슬립 {SLIP*100:.3f}% 수수료 {FEE*100:.1f}% "
          f"· 기준 liquidity 고정 · 주기 {list(CADENCES)} · arm {ARMS} "
          f"· 주판정 {PRIMARY} · 무작위 {RANDOM_DRAWS}회 | DEPLOY_ON_PASS={DEPLOY_ON_PASS}")
    syms_all = all_symbols()
    rows_1d = va.load_tf(syms_all, "1d", long=True)
    print(f"[data] 코인 {len(rows_1d)} (유니버스 {len(va._syms())} + 장기)")

    out = dict(frame="cadence", deploy_on_pass=DEPLOY_ON_PASS, primary=PRIMARY, windows={}, prior=(
        "유니버스를 고정하면 월 우위가 크게 줄고, 남는 부분은 재선택이 아니라 앵커 리셋일 것"))
    W = {}
    for w in WINDOWS:
        syms = fixed_universe(rows_1d, w["start"], w["end"], w["hist_by"])
        dates = sorted({x["date"] for s in syms for x in rows_1d[s] if w["start"] <= x["date"] <= w["end"]})
        idx, tv = prep(rows_1d, syms)
        W[w["name"]] = dict(spec=w, syms=syms, dates=dates, idx=idx, tv=tv)
        print(f"[{w['name']}] 고정 유니버스 {len(syms)} 코인 · {dates[0]}~{dates[-1]} ({len(dates)}일)")

    # ── 주기 x N x arm 격자 ────────────────────────────────────────────────
    for wname, ws in W.items():
        dates, syms, idx, tv = ws["dates"], ws["syms"], ws["idx"], ws["tv"]
        days = len(dates)
        grid = {}
        print(f"\n== {wname} · 고정 유니버스 {len(syms)} · Calmar (arm 별) ==")
        for arm in ARMS:
            print(f"  [{arm}]  {'주기':<12}" + "".join(f"{'N='+str(n):>10}" for n in ws["spec"]["n_grid"]))
            for cname, cd in CADENCES.items():
                line = f"          {cname:<12}"
                for n in ws["spec"]["n_grid"]:
                    s = stats(basket(rows_1d, dates, syms, idx, tv, n, cd, arm), days)
                    grid[f"{arm}|{n}|{cname}"] = s
                    line += f"{_f(s['calmar'],10)}"
                print(line)
        # 최종 배수 표(주 N 만)
        npri = PRIMARY["n"] if PRIMARY["n"] in ws["spec"]["n_grid"] else ws["spec"]["n_grid"][-1]
        print(f"  [최종 배수 · N={npri}]  " + "".join(f"{c:>12}" for c in CADENCES))
        for arm in ARMS:
            print(f"    {arm:<12}" + "".join(f"{_f(grid[f'{arm}|{npri}|{c}']['final'],11)}x" for c in CADENCES))
        ws["grid"] = grid
        out["windows"][wname] = dict(syms=syms, n_days=days, grid=grid)

    # ── 주 판정 셀 ─────────────────────────────────────────────────────────
    pw = W[PRIMARY["window"]]
    n, cad = PRIMARY["n"], PRIMARY["cadence"]
    days = len(pw["dates"])
    g = pw["grid"]
    c_res = g[f"reselect|{n}|{cad}"]["calmar"]
    c_none = g[f"reselect|{n}|none"]["calmar"]
    c_rew = g[f"reweight|{n}|{cad}"]["calmar"]
    c_anc = g[f"anchor|{n}|{cad}"]["calmar"]

    draws = RANDOM_DRAWS if not quick else 10
    rnd = []
    for k in range(draws):
        eq = basket(rows_1d, pw["dates"], pw["syms"], pw["idx"], pw["tv"], n, CADENCES[cad],
                    "reselect", seed=SEED + k * 1000)
        s = stats(eq, days)
        if s["calmar"] is not None:
            rnd.append(s["calmar"])
    rnd.sort()
    thr = rnd[int(PCTL / 100 * (len(rnd) - 1))] if rnd else None
    pct = (sum(1 for v in rnd if v < c_res) / len(rnd) * 100) if (rnd and c_res is not None) else None

    same = sum(1 for k in pw["spec"]["n_grid"]
               if gt(g[f"reselect|{k}|{cad}"]["calmar"], g[f"reselect|{k}|none"]["calmar"]))
    j1 = gt(c_res, c_none) and same >= 2
    j2 = gt(c_res, thr)
    j3 = gt(c_res, c_rew)
    w2 = W["W2"]["grid"]
    n2 = n if n in W["W2"]["spec"]["n_grid"] else W["W2"]["spec"]["n_grid"][-1]
    j4 = gt(w2[f"reselect|{n2}|{cad}"]["calmar"], w2[f"reselect|{n2}|none"]["calmar"])
    pool_n = len(pw["syms"])
    degenerate = n > pool_n * MAX_SELECT_RATIO
    verdict = decide(j1, j2, j3, j4, degenerate=degenerate)

    print(f"\n== 주 판정: {PRIMARY['window']} · N={n} · {cad} ==")
    print(f"  무작위선택 {len(rnd)}회 Calmar: 중앙 {st.median(rnd):.2f} · {PCTL}백분위 **{thr:.2f}** · 범위 {rnd[0]:.2f}~{rnd[-1]:.2f}"
          if rnd else "  무작위 표본 없음")
    print(f"  reselect {cad} {_f(c_res,7)}  vs  none {_f(c_none,7)}   (무작위 백분위 {pct:.0f}%)" if pct is not None else "")
    print(f"  분해: none {_f(c_none,7)} -> anchor {_f(c_anc,7)} -> reweight {_f(c_rew,7)} -> reselect {_f(c_res,7)}")
    print(f"        앵커 리셋 기여 {_f((c_anc or 0)-(c_none or 0),7)} · 재균등화 기여 {_f((c_rew or 0)-(c_anc or 0),7)} "
          f"· 재선택 기여 {_f((c_res or 0)-(c_rew or 0),7)}")
    if degenerate:
        print(f"  [퇴화] 고정 유니버스 {pool_n} 에서 N={n} 은 후보의 {n/pool_n*100:.0f}% 를 고른다 "
              f"(문턱 {MAX_SELECT_RATIO*100:.0f}%) — 선택 arm 이 성립하지 않아 J2·J3 를 읽지 않는다")
    print(f"  J1 효과존재 {'통과' if j1 else '실패'} (N 격자 동부호 {same}/{len(pw['spec']['n_grid'])}) · "
          f"J2 선택정보 {'통과' if j2 else '실패'} · J3 재선택기여 {'통과' if j3 else '실패'} · J4 창강건 {'통과' if j4 else '실패'}")
    print(f"\n  ** 판정: {verdict} **")

    # ── 진단 ───────────────────────────────────────────────────────────────
    diag = {}
    print("\n== 진단 (판정 아님) ==")
    print(f"  D1 수수료 편도 {FEE_STRESS*100:.1f}% 스트레스 (reselect, N={n}):")
    line = "     " + "".join(f"{c:>12}" for c in CADENCES)
    print(line)
    row = "     "
    for c in CADENCES:
        s = stats(basket(rows_1d, pw["dates"], pw["syms"], pw["idx"], pw["tv"], n, CADENCES[c],
                         "reselect", fee=FEE_STRESS), days)
        diag[f"fee_stress|{c}"] = s
        row += f"{_f(s['calmar'],12)}"
    print(row)
    print("  D2 재구성 횟수 · 연 수수료 부담(왕복 0.2% 기준):")
    for c, cd in CADENCES.items():
        k = len(marks_of(pw["dates"], cd)) - 1
        yrs = days / 365.25
        diag[f"marks|{c}"] = k
        print(f"     {c:<12} {k:>4}회 · 연 {k/yrs:5.1f}회 · 연 수수료 {k/yrs*2*FEE*100:5.2f}%")
    print("  D4 띠 규칙 없이 그냥 보유 + 같은 주기 재균등화 (리밸런싱 프리미엄):")
    row = "     " + "".join(f"{c:>12}" for c in CADENCES)
    print(row)
    row = "     "
    for c in CADENCES:
        s = stats(basket(rows_1d, pw["dates"], pw["syms"], pw["idx"], pw["tv"], n, CADENCES[c],
                         "reselect", hold=True), days)
        diag[f"hold|{c}"] = s
        row += f"{_f(s['calmar'],12)}"
    print(row)

    print(f"  D5 재구성 시장가 슬리피지 민감도 (reselect, N={n}, 편도):")
    print("     " + f"{'슬립':<8}" + "".join(f"{c:>12}" for c in CADENCES))
    for sl in RESET_SLIP_GRID:
        row = "     " + f"{sl*100:5.3f}%  "
        for c in CADENCES:
            st_ = stats(basket(rows_1d, pw["dates"], pw["syms"], pw["idx"], pw["tv"], n, CADENCES[c],
                               "reselect", reset_slip=sl), days)
            diag[f"reset_slip|{sl}|{c}"] = st_
            row += f"{_f(st_['calmar'],12)}"
        print(row)

    out.update(verdict=verdict, degenerate=degenerate, pool_n=pool_n, judgement=dict(J1=j1, J2=j2, J3=j3, J4=j4, n_grid_same_sign=same),
               primary_result=dict(reselect=c_res, none=c_none, reweight=c_rew, anchor=c_anc,
                                   random_p95=thr, random_median=(st.median(rnd) if rnd else None), pctile=pct),
               diag=diag)
    json.dump(out, open("_cadence.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print("\nRESULT_JSON: " + json.dumps(dict(frame="cadence", verdict=verdict, judgement=out["judgement"],
                                             primary=out["primary_result"],
                                             grid={k: v["calmar"] for k, v in pw["grid"].items()}),
                                        ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
