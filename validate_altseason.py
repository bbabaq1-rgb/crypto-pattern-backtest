"""
validate_altseason.py — 알트 시즌 선행 지표 **120일 지평** 사전 등록 시험
(2026-09-22, 사용자 지시 "120일로 사전등록해서 돌려봐").

■ 물음
  ETH/BTC · 알트 바스켓/BTC · 폭(breadth) 같은 상태 지표가 **앞으로 120일 동안 알트가 BTC 를
  이길지**를 미리 말해주는가. 종전 라벨러 시험(regime_quality 2026-09-04, alt_side 2026-09-07)은
  전부 **지평 20일 고정**이었고, alt_side 진단에서 지평을 늘리면 분리폭이 커지는(40/60/90일
  +3.4/+5.6/+8.4%p) 신호가 있었으나 사후 선택 금지로 멈춰 있었다. **지평 120일은 사용자가
  결과를 보기 전에 지정한 값**이므로 사후 선택이 아니다.

■ 대상(120일 뒤에 무엇이 되어 있는가)
  target = median_{알트}(c[t+120]/c[t] − 1) − (btc[t+120]/btc[t] − 1)
  알트 = BTC 를 뺀 적격 종목 전부(**ETH 포함** — 트레이더가 말하는 '알트'에 가깝다).
  중앙값이라 한두 종목의 대박에 끌려가지 않는다(평균은 진단으로 병기).

■ 가설 지표 10 (전부 가격에서만, 인과적) + 음성 대조 2
  부호는 **실행 전에 선언**한다. 반대 부호로 크게 나오면 REVERSED 로 기록하되 통과로 치지 않는다.

■ 왜 진짜 BTC.D 가 없는가 (결과가 아니라 데이터 사실)
  레포의 BTC.D 는 CoinGecko 무료 /market_chart 5종 시총 프록시이고 **365일뿐**이다. 120일 지평
  시험에 365일은 비중첩 창 3개라 쓸 수 없다. 진짜 TOTAL2/TOTAL3 는 유료. 그래서 이 판은
  **가격으로 만들 수 있는 상대강도 프록시**로 대신한다(ETH/BTC, OTHERS/BTC, 폭). 도미넌스의
  ①ETH/BTC 다리는 여기 들어 있고, ②시총 가중 다리는 **측정 불가**로 남는다 — known_limits.

■ 통계 — 중첩을 다루는 것이 이 판의 핵심
  120일 선행 라벨은 이웃 날짜끼리 119/120 이 겹친다. 일별 상관을 그냥 재면 표본이 실제보다
  수십 배 커 보인다. 그래서 귀무를 **회전 검정(rotation test)** 으로 만든다 — 지표 계열을
  ≥180일(=1.5×지평) 임의로 원형 이동시켜 상관을 다시 잰다. 두 계열의 자기상관은 그대로 보존되고
  **짝만 깨진다**. 중첩이 만드는 가짜 유의가 귀무 분포에 그대로 들어오므로 자동으로 상쇄된다.
  · **MDE(최소검출효과) = 귀무 IC 분포의 95백분위** — 이 판이 애초에 검출할 수 있는 상관의 하한.
    |IC| 가 문턱은 넘는데 MDE 보다 작으면 REJECTED 가 아니라 **INCONCLUSIVE(검정력 부족)** 다.
    2026-09-09 결정 ②(표본 부족을 기각으로 분류하지 않는다)의 연장.

■ 판정 (실행 전 동결)
  C1 train(2018-01-01 ~ 2021-12-31) : 부호 일치 AND |IC| >= 0.20 AND Holm(m=10) p < 0.05
  C2 holdout(2022-01-01 ~)          : 부호 일치 AND |IC| >= 0.15 AND raw p < 0.05
  C3 실용성                          : 상위 3분위 target 평균 > 전체 평균 (두 분할 모두)
                                       AND holdout 상위 3분위 평균 > 0 (절대값)
  CONFIRMED = C1 ∧ C2 ∧ C3 / INCONCLUSIVE = 부호·크기는 맞는데 |IC_train| < MDE_train /
  REVERSED = 반대 부호로 |IC| >= 0.20 이고 양측 p < 0.05 / 그 외 REJECTED.
  **음성 대조 2개가 모두 C1(무보정) 을 통과하면 판 전체 INVALID.**

■ DEPLOY_ON_PASS = False — 통과해도 실거래 반영 없음. 지표가 예측력을 보인다는 것과
  그것으로 돈을 번다는 것은 다른 명제이고, 매매 규칙은 별도 사전 등록이 필요하다.

실행: python validate_altseason.py
"""
import gzip
import csv
import json
import math
import os
import random
import statistics as st
import sys
from datetime import datetime, timezone

LONG_DIR = "data_long"
OUT = "_altseason.json"

# ── 동결 상수 (2026-09-22, 결과 보기 전) ──────────────────────────────────
HORIZON      = 120          # 사용자 지정
MIN_HIST     = 180          # 종목 적격 최소 이력(봉)
MIN_UNIVERSE = 10           # 그날 적격 종목이 이보다 적으면 관측 제외
START        = "2018-01-01" # 유니버스가 10종목을 넘는 첫 해 (2017 은 3종목)
SPLIT        = "2022-01-01" # train / holdout. 알트장이 양쪽에 하나씩(2021 / 2023-24)
MIN_SHIFT    = 180          # 회전 최소 이동 = 1.5 x HORIZON
BOOT         = 1000
SEED         = 20260922
IC1, IC2     = 0.20, 0.15
ALPHA        = 0.05
NQ           = 3            # 3분위
DEPLOY_ON_PASS = False

# (키, 설명, 선언 부호)
FEATURES = [
    ("ethbtc_mom120",  "ETH/BTC 120일 모멘텀",            +1),
    ("ethbtc_slope20", "ETH/BTC 20MA 기울기(레짐 ②)",     +1),
    ("ethbtc_dist200", "ETH/BTC 의 200MA 대비 위치",       +1),
    ("altbtc_mom120",  "OTHERS/BTC 120일 모멘텀",         +1),
    ("altbtc_dist200", "OTHERS/BTC 의 200MA 대비 위치",    +1),
    ("breadth180",     "MA180 위 코인 비율",               +1),
    ("breadth_chg20",  "폭 20일 변화",                     +1),
    ("btc_mom120",     "BTC 120일 수익률",                 +1),
    ("btc_dist200",    "BTC 의 200MA 대비 위치",           +1),
    ("disp60",         "60일 수익률 횡단면 표준편차",       -1),
]
CONTROLS = [
    ("ctrl_ar1",    "음성대조 — AR(1) φ=0.99 잡음", +1),
    ("ctrl_season", "음성대조 — 연 1회 사인파",      +1),
]
M_HOLM = len(FEATURES)


# ── 데이터 ────────────────────────────────────────────────────────────────
def load_long(sym, dirpath=LONG_DIR):
    """data_long/{sym}_1d.csv.gz — 네트워크 없이 결정론적으로 읽는다. [(date, close)] 정렬."""
    out = []
    with gzip.open(f"{dirpath}/{sym}_1d.csv.gz", "rt", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            ts = int(float(r["timestamp"]))
            d = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
            out.append((d, float(r["close"])))
    out.sort()
    return out


def load_all(dirpath=LONG_DIR):
    """sym -> {date: close}. manifest.json 등 비 gz 는 건너뛴다."""
    by = {}
    for f in sorted(os.listdir(dirpath)):
        if not f.endswith("_1d.csv.gz"):
            continue
        rows = load_long(f[: -len("_1d.csv.gz")], dirpath)
        if rows:
            by[f[: -len("_1d.csv.gz")]] = dict(rows)
    return by


def sma(xs, w):
    """out[i] = mean(xs[i-w+1:i+1]) — 창이 다 차야 값을 낸다(None 하나라도 있으면 None)."""
    out = [None] * len(xs)
    for i in range(w - 1, len(xs)):
        win = xs[i - w + 1:i + 1]
        if all(v is not None for v in win):
            out[i] = sum(win) / w
    return out


# ── 지표 계산 ─────────────────────────────────────────────────────────────
def build_series(by, min_hist=MIN_HIST, min_universe=MIN_UNIVERSE):
    """BTC 날짜 격자 위에 지표·타깃 재료를 만든다. 전부 t 시점까지의 정보만 쓴다."""
    btc, eth = by["btc"], by["eth"]
    dates = sorted(btc)
    idx_of = {d: i for i, d in enumerate(dates)}

    # 종목별 (그 종목 자신의 거래일 기준) 이력 길이 — 적격 판정용
    hist_n = {}
    for s, m in by.items():
        ds = sorted(m)
        hist_n[s] = {d: k + 1 for k, d in enumerate(ds)}

    alts = [s for s in by if s not in ("btc",)]            # 타깃 바스켓: BTC 제외(ETH 포함)
    others = [s for s in by if s not in ("btc", "eth")]    # OTHERS 지수: BTC·ETH 제외

    def eligible(sym, d):
        return hist_n[sym].get(d, 0) >= min_hist

    # 종목별 자기 MA180 (자기 거래일 기준)
    above_ma = {}
    for s, m in by.items():
        ds = sorted(m)
        cs = [m[d] for d in ds]
        ma = sma(cs, min_hist)
        above_ma[s] = {d: (None if ma[i] is None else cs[i] > ma[i]) for i, d in enumerate(ds)}

    # OTHERS 등가중 지수 (일별 리밸런스, 편입은 적격해진 날부터 = PIT)
    others_idx = [1.0]
    for i in range(1, len(dates)):
        d0, d1 = dates[i - 1], dates[i]
        rs_ = [by[s][d1] / by[s][d0] - 1 for s in others
               if d0 in by[s] and d1 in by[s] and eligible(s, d0) and eligible(s, d1)]
        others_idx.append(others_idx[-1] * (1 + st.mean(rs_)) if rs_ else others_idx[-1])

    btc_c = [btc[d] for d in dates]
    eth_c = [eth.get(d) for d in dates]
    ethbtc = [(None if eth_c[i] is None else eth_c[i] / btc_c[i]) for i in range(len(dates))]
    altbtc = [others_idx[i] / btc_c[i] for i in range(len(dates))]

    breadth, univ_n, disp = [], [], []
    for i, d in enumerate(dates):
        el = [s for s in by if eligible(s, d) and d in by[s]]
        univ_n.append(len(el))
        ab = [above_ma[s][d] for s in el if above_ma[s].get(d) is not None]
        breadth.append(sum(ab) / len(ab) if ab else None)
        if i >= 60:
            d60 = dates[i - 60]
            r60 = [by[s][d] / by[s][d60] - 1 for s in el if d60 in by[s]]
            disp.append(st.pstdev(r60) if len(r60) >= min_universe else None)
        else:
            disp.append(None)

    return dict(dates=dates, idx_of=idx_of, btc_c=btc_c, ethbtc=ethbtc, altbtc=altbtc,
                breadth=breadth, univ_n=univ_n, disp=disp, by=by, alts=alts,
                eligible=eligible, hist_n=hist_n)


def _mom(xs, i, lb):
    if i < lb or xs[i] is None or xs[i - lb] is None or xs[i - lb] == 0:
        return None
    return xs[i] / xs[i - lb] - 1


def _dist(xs, ma, i):
    if xs[i] is None or ma[i] is None or ma[i] == 0:
        return None
    return xs[i] / ma[i] - 1


def features_at(S):
    """i -> {key: value}. 전부 dates[i] 까지의 정보만."""
    n = len(S["dates"])
    ethbtc, altbtc, btc_c, breadth, disp = (S["ethbtc"], S["altbtc"], S["btc_c"],
                                            S["breadth"], S["disp"])
    ma200_eb = sma(ethbtc, 200)
    ma200_ab = sma(altbtc, 200)
    ma200_btc = sma(btc_c, 200)
    ma20_eb = sma(ethbtc, 20)

    rnd = random.Random(SEED)
    ar = [0.0] * n
    for i in range(1, n):
        ar[i] = 0.99 * ar[i - 1] + rnd.gauss(0, 1)
    season = [math.sin(2 * math.pi * i / 365.25) for i in range(n)]

    out = []
    for i in range(n):
        f = {}
        f["ethbtc_mom120"] = _mom(ethbtc, i, HORIZON)
        f["ethbtc_slope20"] = (None if (ma20_eb[i] is None or i < 20 or ma20_eb[i - 20] in (None, 0))
                               else ma20_eb[i] / ma20_eb[i - 20] - 1)
        f["ethbtc_dist200"] = _dist(ethbtc, ma200_eb, i)
        f["altbtc_mom120"] = _mom(altbtc, i, HORIZON)
        f["altbtc_dist200"] = _dist(altbtc, ma200_ab, i)
        f["breadth180"] = breadth[i]
        f["breadth_chg20"] = (None if (i < 20 or breadth[i] is None or breadth[i - 20] is None)
                              else breadth[i] - breadth[i - 20])
        f["btc_mom120"] = _mom(btc_c, i, HORIZON)
        f["btc_dist200"] = _dist(btc_c, ma200_btc, i)
        f["disp60"] = disp[i]
        f["ctrl_ar1"] = ar[i]
        f["ctrl_season"] = season[i]
        out.append(f)
    return out


def target_at(S, horizon=HORIZON):
    """i -> 120일 뒤 (알트 중앙값 − BTC) 초과수익. 라벨 창이 온전한 날만."""
    dates, by, btc_c = S["dates"], S["by"], S["btc_c"]
    el = S["eligible"]
    out = [None] * len(dates)
    mean_out = [None] * len(dates)
    for i in range(len(dates) - horizon):
        d0, d1 = dates[i], dates[i + horizon]
        rs_ = [by[s][d1] / by[s][d0] - 1 for s in S["alts"]
               if d0 in by[s] and d1 in by[s] and el(s, d0)]
        if len(rs_) < MIN_UNIVERSE:
            continue
        bret = btc_c[i + horizon] / btc_c[i] - 1
        out[i] = st.median(rs_) - bret
        mean_out[i] = st.mean(rs_) - bret
    return out, mean_out


# ── 통계 ──────────────────────────────────────────────────────────────────
def _ranks(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            r[order[k]] = avg
        i = j + 1
    return r


def spearman(a, b):
    if len(a) < 3:
        return 0.0
    ra, rb = _ranks(a), _ranks(b)
    ma, mb = st.mean(ra), st.mean(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    da = math.sqrt(sum((x - ma) ** 2 for x in ra))
    db = math.sqrt(sum((y - mb) ** 2 for y in rb))
    return 0.0 if da == 0 or db == 0 else num / (da * db)


def rotation_null(fv, tv, boot=BOOT, min_shift=MIN_SHIFT, seed=SEED):
    """지표 계열만 원형 이동 → 자기상관 보존, 짝만 파괴. 중첩 라벨의 가짜 유의를 상쇄."""
    n = len(fv)
    if n <= 2 * min_shift + 2:
        return []
    shifts = list(range(min_shift, n - min_shift))
    rnd = random.Random(seed)
    if len(shifts) > boot:
        shifts = rnd.sample(shifts, boot)
    else:
        shifts = [rnd.choice(shifts) for _ in range(boot)]
    return [spearman(fv[s:] + fv[:s], tv) for s in shifts]


def pval(ic, nulls, sign):
    """선언 부호 방향의 단측 p. 부호가 −이면 작을수록 유의."""
    if not nulls:
        return 1.0
    if sign > 0:
        k = sum(1 for v in nulls if v >= ic)
    else:
        k = sum(1 for v in nulls if v <= ic)
    return (k + 1) / (len(nulls) + 1)


def pval_two(ic, nulls):
    if not nulls:
        return 1.0
    return (sum(1 for v in nulls if abs(v) >= abs(ic)) + 1) / (len(nulls) + 1)


def mde(nulls, sign):
    """이 판이 α=0.05 에서 검출할 수 있는 IC 의 하한 = 귀무 분포의 95(또는 5)백분위."""
    if not nulls:
        return float("nan")
    s = sorted(nulls)
    k = int(0.95 * (len(s) - 1)) if sign > 0 else int(0.05 * (len(s) - 1))
    return s[k]


def holm(pairs, m=None):
    """[(key, p)] -> {key: p_adj}. m 을 주면 가족 크기를 고정한다."""
    m = len(pairs) if m is None else m
    out, prev = {}, 0.0
    for r, (k, p) in enumerate(sorted(pairs, key=lambda x: x[1])):
        adj = min(1.0, max(prev, (m - r) * p))
        out[k] = adj
        prev = adj
    return out


def tercile_stats(fv, tv, nq=NQ):
    """상위 3분위(선언 부호 방향으로 '지표가 높은 쪽')의 target 평균 + 전체 평균."""
    if len(fv) < nq * 3:
        return None
    pairs = sorted(zip(fv, tv))
    cut = len(pairs) - len(pairs) // nq
    top = [t for _, t in pairs[cut:]]
    return dict(top_mean=st.mean(top), all_mean=st.mean(tv), n_top=len(top))


# ── 판정 ──────────────────────────────────────────────────────────────────
def judge(row):
    """실행 전 동결된 규칙. row 는 analyze 가 만든 셀 하나."""
    sign = row["sign"]
    tr, ho = row["train"], row["holdout"]
    if tr is None or ho is None:
        return "INCONCLUSIVE", ["표본 부족(분할 계산 불가)"]
    why = []
    sign_ok_tr = (tr["ic"] * sign) > 0
    size_ok_tr = abs(tr["ic"]) >= IC1
    p_ok_tr = tr["p_holm"] < ALPHA
    c1 = sign_ok_tr and size_ok_tr and p_ok_tr

    sign_ok_ho = (ho["ic"] * sign) > 0
    c2 = sign_ok_ho and abs(ho["ic"]) >= IC2 and ho["p"] < ALPHA

    t_tr, t_ho = tr.get("terc"), ho.get("terc")
    c3 = bool(t_tr and t_ho
              and t_tr["top_mean"] > t_tr["all_mean"]
              and t_ho["top_mean"] > t_ho["all_mean"]
              and t_ho["top_mean"] > 0)

    # REVERSED — 반대 부호로 크고 양측 유의
    if (tr["ic"] * sign) < 0 and abs(tr["ic"]) >= IC1 and tr["p_two"] < ALPHA:
        return "REVERSED", [f"선언 부호와 반대 (IC {tr['ic']:+.3f}, 양측 p {tr['p_two']:.3f})"]

    if c1 and c2 and c3:
        return "CONFIRMED", []
    if not sign_ok_tr:
        why.append("train 부호 불일치")
    if not size_ok_tr:
        why.append(f"|IC_train| {abs(tr['ic']):.3f} < {IC1}")
    if sign_ok_tr and size_ok_tr and not p_ok_tr:
        why.append(f"Holm p {tr['p_holm']:.3f}")
    if not c2:
        why.append("C2 holdout")
    if not c3:
        why.append("C3 실용성")

    # 검정력 부족 — 크기·부호는 맞는데 이 판이 애초에 검출 못 하는 구간
    underpowered = sign_ok_tr and size_ok_tr and not p_ok_tr and abs(tr["mde"]) > IC1
    if underpowered:
        return "INCONCLUSIVE", why + [f"MDE {tr['mde']:+.3f} > {IC1} (검정력 부족)"]
    return "REJECTED", why


def analyze(S, feats, tgt, tgt_mean):
    dates = S["dates"]
    keep = [i for i in range(len(dates))
            if tgt[i] is not None and dates[i] >= START and S["univ_n"][i] >= MIN_UNIVERSE]
    tr_i = [i for i in keep if dates[i] < SPLIT]
    ho_i = [i for i in keep if dates[i] >= SPLIT]

    def one(idxs, key, sign, seed):
        sub = [i for i in idxs if feats[i].get(key) is not None]
        if len(sub) < 2 * MIN_SHIFT + 3:
            return None
        fv = [feats[i][key] for i in sub]
        tv = [tgt[i] for i in sub]
        ic = spearman(fv, tv)
        nulls = rotation_null(fv, tv, seed=seed)
        return dict(n=len(sub), ic=ic, p=pval(ic, nulls, sign), p_two=pval_two(ic, nulls),
                    mde=mde(nulls, sign), terc=tercile_stats(fv, tv),
                    span_days=(datetime.strptime(dates[sub[-1]], "%Y-%m-%d")
                               - datetime.strptime(dates[sub[0]], "%Y-%m-%d")).days)

    rows = []
    for k, (key, label, sign) in enumerate([*FEATURES, *CONTROLS]):
        rows.append(dict(key=key, label=label, sign=sign,
                         train=one(tr_i, key, sign, SEED + k),
                         holdout=one(ho_i, key, sign, SEED + 500 + k),
                         is_control=key.startswith("ctrl_")))

    hp = holm([(r["key"], r["train"]["p"]) for r in rows
               if not r["is_control"] and r["train"]], m=M_HOLM)
    for r in rows:
        if r["train"]:
            r["train"]["p_holm"] = hp.get(r["key"], r["train"]["p"])
    for r in rows:
        r["verdict"], r["why"] = judge(r)
    return rows, tr_i, ho_i, keep


def fmt(v, w=7, d=3, pct=False):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—".rjust(w)
    return (f"{v*100:+.{d-1}f}%" if pct else f"{v:+.{d}f}").rjust(w)


def main():
    print("=" * 108)
    print("알트 시즌 선행 지표 — 120일 지평 사전 등록 시험 (registry altseason_prereg_2026_09_22)")
    print(f"지평 {HORIZON}일 · train < {SPLIT} <= holdout · 회전검정 이동 >= {MIN_SHIFT}일 · "
          f"boot {BOOT} · seed {SEED} · Holm m={M_HOLM}")
    print("=" * 108)

    by = load_all()
    print(f"[데이터] data_long {len(by)} 종목 (네트워크 없음)")
    S = build_series(by)
    print(f"[격자] {S['dates'][0]} ~ {S['dates'][-1]} ({len(S['dates'])}일)")
    feats = features_at(S)
    tgt, tgt_mean = target_at(S)
    rows, tr_i, ho_i, keep = analyze(S, feats, tgt, tgt_mean)

    span_tr = (datetime.strptime(S["dates"][tr_i[-1]], "%Y-%m-%d")
               - datetime.strptime(S["dates"][tr_i[0]], "%Y-%m-%d")).days if tr_i else 0
    span_ho = (datetime.strptime(S["dates"][ho_i[-1]], "%Y-%m-%d")
               - datetime.strptime(S["dates"][ho_i[0]], "%Y-%m-%d")).days if ho_i else 0
    print(f"[표본] 라벨 있는 날 {len(keep)} — train {len(tr_i)}일 / holdout {len(ho_i)}일")
    print(f"[유효 표본] **비중첩 {HORIZON}일 창 = train {span_tr/HORIZON:.1f}개 / "
          f"holdout {span_ho/HORIZON:.1f}개** — 일별 관측 수가 아니라 이게 실제 자유도다.")
    base_tr = st.mean([tgt[i] for i in tr_i]) if tr_i else 0
    base_ho = st.mean([tgt[i] for i in ho_i]) if ho_i else 0
    print(f"[기저] 무조건부 120일 알트초과수익 평균 — train {base_tr*100:+.1f}% / holdout {base_ho*100:+.1f}%")

    print("\n" + "-" * 108)
    print(f"{'지표':<30}{'부호':>4}{'IC_tr':>8}{'Holm':>7}{'MDE_tr':>8}"
          f"{'IC_ho':>8}{'p_ho':>7}{'상위3분위(ho)':>14}  판정")
    print("-" * 108)
    for r in rows:
        tr, ho = r["train"], r["holdout"]
        tag = "  [대조]" if r["is_control"] else ""
        # Holm 열: 가설은 보정 p, 대조는 무보정 p (대조는 Holm 가족 밖)
        pcol = (tr["p"] if r["is_control"] else tr.get("p_holm", tr["p"])) if tr else None
        terc = ho["terc"] if (ho and ho.get("terc")) else None
        pho = ho["p"] if ho else None
        print(f"{r['label'][:29]:<30}"
              f"{('+' if r['sign'] > 0 else '-'):>4}"
              f"{fmt(tr['ic'] if tr else None, 8)}"
              f"{(f'{pcol:.3f}' if pcol is not None else '—'):>7}"
              f"{fmt(tr['mde'] if tr else None, 8)}"
              f"{fmt(ho['ic'] if ho else None, 8)}"
              f"{(f'{pho:.3f}' if pho is not None else '—'):>7}"
              f"{fmt(terc['top_mean'] if terc else None, 14, 3, pct=True)}"
              f"  {r['verdict']}{tag}")
    print("-" * 108)
    print("  ※ Holm 열은 대조 행에서는 무보정 p 다(대조는 Holm 가족 밖).")

    ctrl_pass = [r for r in rows if r["is_control"] and r["train"]
                 and (r["train"]["ic"] * r["sign"]) > 0
                 and abs(r["train"]["ic"]) >= IC1 and r["train"]["p"] < ALPHA]
    invalid = len(ctrl_pass) >= len(CONTROLS)
    conf = [r for r in rows if not r["is_control"] and r["verdict"] == "CONFIRMED"]
    inc = [r for r in rows if not r["is_control"] and r["verdict"] == "INCONCLUSIVE"]
    rev = [r for r in rows if not r["is_control"] and r["verdict"] == "REVERSED"]

    print(f"\n[판정] CONFIRMED {len(conf)} / INCONCLUSIVE {len(inc)} / REVERSED {len(rev)} / "
          f"REJECTED {len(FEATURES)-len(conf)-len(inc)-len(rev)}  "
          f"(대조 통과 {len(ctrl_pass)}/{len(CONTROLS)} → {'INVALID' if invalid else '판 VALID'})")
    for r in rows:
        if not r["is_control"] and r["verdict"] != "REJECTED":
            print(f"   · {r['label']} — {r['verdict']}: {', '.join(r['why']) or '전 기준 통과'}")

    # 필요 표본 — MDE 를 IC1 까지 낮추려면 몇 배의 창이 필요한가 (SE ∝ 1/sqrt(창수))
    if rows[0]["train"]:
        m = abs(rows[0]["train"]["mde"])
        need = (m / IC1) ** 2 if IC1 > 0 else float("nan")
        print(f"\n[검정력] train MDE 약 {m:.3f} — |IC|={IC1} 를 유의하게 잡으려면 "
              f"현재의 약 {need:.1f}배 창(≈ {span_tr*need/365:.0f}년)이 필요하다.")

    print("\n[오늘 읽기] (데이터 끝 " + S["dates"][-1] + " 기준, 판정 아님 — 진단)")
    last = len(S["dates"]) - 1
    hist_lo = next(i for i in range(len(S["dates"])) if S["dates"][i] >= START)
    for key, label, sign in FEATURES:
        v = feats[last].get(key)
        hist = [feats[i][key] for i in range(hist_lo, last + 1) if feats[i].get(key) is not None]
        if v is None or len(hist) < 30:
            print(f"   {label:<30} —")
            continue
        pr = sum(1 for x in hist if x < v) / len(hist)
        terc = "상위" if pr >= 2 / 3 else "하위" if pr < 1 / 3 else "중간"
        favor = "알트" if (pr - 0.5) * sign > 0 else "BTC"
        print(f"   {label:<30}{v:+.4f}  백분위 {pr*100:4.0f}%  {terc} 3분위  → 부호상 {favor} 쪽")

    res = dict(prereg="altseason_prereg_2026_09_22", horizon=HORIZON, split=SPLIT,
               start=START, boot=BOOT, seed=SEED, deploy_on_pass=DEPLOY_ON_PASS,
               n_train=len(tr_i), n_holdout=len(ho_i),
               windows_train=round(span_tr / HORIZON, 1), windows_holdout=round(span_ho / HORIZON, 1),
               base_train=base_tr, base_holdout=base_ho, invalid=invalid,
               confirmed=[r["key"] for r in conf], inconclusive=[r["key"] for r in inc],
               reversed=[r["key"] for r in rev],
               rows=[{k: v for k, v in r.items()} for r in rows],
               today={key: feats[last].get(key) for key, _, _ in FEATURES},
               data_end=S["dates"][-1])
    with open(OUT, "w") as f:
        json.dump(res, f, ensure_ascii=False, indent=1, default=str)
    print(f"\n[출력] {OUT}")
    print(f"[반영] DEPLOY_ON_PASS={DEPLOY_ON_PASS} — 실거래 무변경.")
    return res


if __name__ == "__main__":
    main()
