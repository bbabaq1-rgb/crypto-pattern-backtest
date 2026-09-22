"""
validate_kimchi.py — 거래소 간 프리미엄(김치 프리미엄) 사전 등록 시험 (2026-09-22).

## 계기
외부 분석 핸드오프(registry ext_evidence_bitmex_aoa_2026_09_22)가 '방향 선택을 개선하려면 **비가격 입력**이
필요하다'며 넷을 꼽았고, 레포 상태에 매핑하니 **호가 불균형**(틱 데이터 없음 → 사전 등록 불가)과
**거래소 간 프리미엄**만 미시험이었다. 후자는 업비트 KRW REST 가 이 환경에서 열려 데이터를 만들 수 있다.

## 두 가족 — 각자 부모 프레임을 **그대로** 상속한다
분할·문턱·귀무를 두 프레임에서 섞어 새로 만들면 그게 사후 선택이다. 그래서 가족마다 부모를 통째로 쓴다.

  가족 X (주 판정) — 횡단면 **종목 선택**. 부모 = validate_xsec_chars(월말 형성 · PIT liquid 유니버스 ·
    fwd20 · 월별 스피어만 IC · 월 블록 부트 1000 · Holm · train<2025-01 / OOS>=2025-01 · MIN_CS 15 ·
    왕복 0.4%). **환율이 정확히 소거된다** — kp_rel = ln(KRW/USDT) − 그날 전 종목 중앙값이고 환율은
    같은 날 모든 코인에 공통 곱이다.
  가족 T (보조 판정) — 시계열 **방향**. 부모 = validate_altseason(회전 검정 귀무 · MDE · judge · IC1 0.20 /
    IC2 0.15 · train<2022-01-01). 지평만 120 → **20**(MIN_SHIFT 30 = 1.5 x 지평). **문턱은 안 낮췄다** —
    지평이 짧아 IC 가 작아질 여지가 있지만 낮추면 사후 완화다. 여기는 환율이 필요해 ECB 고시를 쓴다(오염 존재).

## 왜 주 판정이 횡단면인가
핸드오프의 물음은 방향(시계열)인데, **환율 없이 깨끗하게 잴 수 있는 것은 종목 선택(횡단면)** 이다.
정통 김프(업비트 KRW-USDT 로 환산)는 그 시장이 2025-06-15 상장이라 train 이 없다(실행 전 확인).

## 동결 (결과 보기 전)
  · 데이터: USDT 측 data_long(현물, 2017~) · KRW 측 data_kimchi(업비트 240m 중 **20:00 UTC 봉** =
    종가가 D+1 00:00 UTC → data_long date=D 행과 같은 시각. 일봉은 KST 기준이라 9시간 어긋난다).
  · 가족 X 셀 4 = kp_rel / kp_rel_chg5 / kp_rel_chg20 / kp_rel_z60. **전부 사전 부호 '-'**.
    근거: 레포가 세 번 독립 재현한 '최근 거래대금·관심 증가 → 이후 나쁨'(xsec_chars vol_ratio_30_90 REVERSED,
    episode_profile REVERSED, breadth_state) + 김프 평균회귀. Holm m=4.
  · 가족 T 셀 3 = kp_mkt / kp_mkt_chg20 / kp_mkt_z120, 전부 '-'(시장 전체 프리미엄 = 국내 과열 → 국면 끝).
    타깃 = 적격 코인 **중앙 fwd20 수익(USDT 기준)**. Holm m=3.
  · **추가 요건(설계 부채 소진)**: 가족 X 는 train 에도 TOP−유니버스 > 0 을 요구한다. xsec_chars 가
    '다음 프레임은 train 에도 요구(사후 변경 안 함)'로 남긴 구멍이고, 여기가 그 다음 프레임이다.
  · 음성 대조: X 3(ctrl_ar1_a/b 코인별 AR(1) φ=0.95 · ctrl_sym_const 코인별 상수 = 정보 0·지속성 최대) /
    T 2(ctrl_ar1 · ctrl_season). **대조는 Holm 미보정 + 방향을 train 에서 고르게 둔다**(가장 통과하기 쉬운
    조건 = 가드로는 보수적). 한 가족에서 **2개 이상 통과 시 그 가족 INVALID**.
  · DEPLOY_ON_PASS=False — 통과해도 실거래 반영 없음. 종목 선택·방향 정보이지 진입 규칙이 아니고,
    승격하려면 별도 사전 등록이 필요하다(관찰 기간 ~2026-10-06).

## 진단 (판정 아님 — 사후에 여기서 골라 '살았다'고 하지 않는다)
  D1 kp_volshare(업비트 KRW 거래대금 점유율 / USDT 측 점유율) — 슬라이스가 4h vs 1d 라 진단 ·
  D2 절대 김프 수준과 오늘 읽기 · D3 fwd60 / hit20_40 부호 · D4 레짐별 IC · D5 xsec 24변수와의 중복 ·
  D6 top30 코호트 · D7 가족 T MDE 와 lag20 자기상관(검정력 곡선 교훈 이식).

## 알려진 한계 (결과 전 기록)
  1. 가족 T 는 ECB 고시(14:15 CET, 평일)를 직전값으로 채워 쓴다 — 00:00 UTC 와 약 10시간, 환율 일변동
     약 0.3% 라 수준·20일 변화에는 작지만 0 은 아니다. 가족 X 는 환율을 쓰지 않는다.
  2. 이중 생존 편향 — 업비트 상장폐지 코인 없음 + data_long 자체가 오늘 OKX 에 있는 80종목.
  3. data_long 은 종목마다 다른 현물 거래소(gate/kucoin/coinbase…)라 그 가격차가 비율에 섞인다.
     중앙값 차감은 **그날 공통분**만 지우고 종목별 거래소 차이는 남는다.
  4. 원화 입출금 제한·전송 시간 미반영 — '프리미엄이 높다'가 곧 차익 기회가 아니다. 예측력만 본다.
  5. D1 의 거래대금은 업비트 4h 슬라이스 vs USDT 1d — 점유율로 정규화해도 장중 구성 차이가 남는다.

## 사전 확률 (결과 전 공개)
  · CONFIRMED 0 예상. xsec_chars 가 24변수 중 1개만 통과시켰고 그마저 '순위 예측이지 평균수익이 아니다'였다.
  · 가족 X 안에서는 **kp_rel(수준)이 가장 약하고 z60·chg 가 나을 것** — 수준은 상장·유동성에서 오는
    코인 고정효과가 지배해 검정력 곡선이 짚은 '지속성 함정'에 그대로 걸린다.
  · 가장 있을 법한 흥미로운 결과는 **REVERSED**(프리미엄 높은 코인이 이후 더 좋음 = 한국 자금이 모멘텀).
    그래도 승격하지 않는다.
  · 가족 T 는 지평이 20 이라 MDE 가 알트시즌 120일 판보다 훨씬 나을 것 — **거기서 뭔가 나오면 그게 이 판의
    실질 소득**. 다만 홀드아웃이 2022~2026 이라 bear 지배다.
  · 크기·순위는 예측하지 않는다.

실행: python validate_kimchi.py [--no-fetch]      출력: _kimchi.json + RESULT_JSON
"""
import csv
import gzip
import json
import math
import os
import random
import statistics as st
import sys

import regime_switch as rs
import validate_altseason as V
import validate_guard_v4 as g4
import validate_pit_cohort as pc
import validate_regime_split_all as va
import validate_xsec_chars as xc
import xsec_features as xf

# ── 동결 파라미터 ─────────────────────────────────────────────────────────────────────────────
KRW_DIR = "data_kimchi"
SEED_X = 20260922
MIN_CS = xc.MIN_CS                 # 15 — 부모 그대로
W_Z60, W_CHG5, W_CHG20 = 60, 5, 20
W_Z120, W_CHG20_T = 120, 20
HORIZON_T = 20
MIN_SHIFT_T = 30                   # 1.5 x 지평 (부모의 규칙을 지평에만 적용)
M_HOLM_X, M_HOLM_T = 4, 3
MAX_CTRL_PASS = 1                  # 이 수를 넘겨 통과하면(= 2 이상) 그 가족 INVALID
AR1_PHI = 0.95
DEPLOY_ON_PASS = False

MAIN_X = [("kp_rel", "상대 김프 수준 ln(KRW/USDT) − 그날 중앙"),
          ("kp_rel_chg5", "상대 김프 5일 변화"),
          ("kp_rel_chg20", "상대 김프 20일 변화"),
          ("kp_rel_z60", "상대 김프 60일 z (코인 자기 이력)")]
CTRL_X = [("ctrl_ar1_a", "AR(1) φ=0.95 잡음 A"),
          ("ctrl_ar1_b", "AR(1) φ=0.95 잡음 B"),
          ("ctrl_sym_const", "코인별 상수 — 정보 0, 지속성 최대")]
DIAG_X = [("kp_volshare", "한국 거래 집중도 ln(KRW 점유율/USDT 점유율)")]
SIGN_X = {k: "-" for k, _ in MAIN_X}
SIGN_X.update({k: "?" for k, _ in CTRL_X})          # 대조는 방향을 train 에서 고르게 둔다(가드로 보수적)
SIGN_X.update({k: "?" for k, _ in DIAG_X})
LABEL_X = dict(MAIN_X + CTRL_X + DIAG_X)

MAIN_T = [("kp_mkt", "시장 전체 로그 김프(환율 차감)", -1),
          ("kp_mkt_chg20", "시장 김프 20일 변화", -1),
          ("kp_mkt_z120", "시장 김프 120일 z", -1)]
CTRL_T = [("ctrl_ar1", "AR(1) φ=0.95 잡음", -1),
          ("ctrl_season", "연 주기 사인파", -1)]

# 부모의 판정 함수가 키로 SIGN/GROUP 을 찾는다 — 우리 키를 등록한다(기존 키는 건드리지 않는다).
_NEW = {k: "kimchi" for k in LABEL_X}
assert not (set(_NEW) & set(xf.GROUP)), "xsec 가족 키와 충돌"
xf.GROUP.update(_NEW)
xf.SIGN.update(SIGN_X)


# ── 데이터 ───────────────────────────────────────────────────────────────────────────────────
def load_krw(sym, dirpath=KRW_DIR):
    """{date: (close_krw, value_krw)} — 업비트 20:00 UTC 봉."""
    p = os.path.join(dirpath, f"{sym.lower()}_krw.csv.gz")
    if not os.path.exists(p):
        return {}
    out = {}
    with gzip.open(p, "rt", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            try:
                out[r["date"]] = (float(r["close"]), float(r["value_krw"]))
            except (TypeError, ValueError):
                continue
    return out


def load_fx(dirpath=KRW_DIR):
    """{date: usdkrw} — ECB 평일 고시. 진단·가족 T 전용."""
    p = os.path.join(dirpath, "usdkrw.csv")
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8", newline="") as f:
        return {r["date"]: float(r["usdkrw"]) for r in csv.DictReader(f)}


def ffill(fx, dates):
    """평일 고시를 격자 전체로 직전값 채움. 첫 고시 이전은 None."""
    out, last = {}, None
    for d in dates:
        if d in fx:
            last = fx[d]
        out[d] = last
    return out


# ── 김프 패널 ────────────────────────────────────────────────────────────────────────────────
def build_kp(rows_1d, krw_by, min_cs=MIN_CS):
    """격자 날짜 · 코인별 kp_rel · 시장 로그비율 중앙값 · 거래대금 점유율 비.

    kp_rel_i(D) = ln(KRW_i/USDT_i) − median_j ln(KRW_j/USDT_j)  ← 환율이 공통 곱이라 정확히 소거.
    """
    usdt = {s: {r["date"]: (r["c"], r["c"] * r["v"]) for r in rows} for s, rows in rows_1d.items()}
    syms = sorted(set(usdt) & {s for s, k in krw_by.items() if k})
    by_date = {}
    for s in syms:
        for d, (kc, kv) in krw_by[s].items():
            u = usdt[s].get(d)
            if not u or u[0] <= 0 or kc <= 0:
                continue
            by_date.setdefault(d, {})[s] = (math.log(kc) - math.log(u[0]), kv, u[1])
    grid = sorted(d for d, m in by_date.items() if len(m) >= min_cs)
    gi = {d: i for i, d in enumerate(grid)}
    kp, vs, mkt = {s: {} for s in syms}, {s: {} for s in syms}, {}
    for d in grid:
        m = by_date[d]
        med = st.median(v[0] for v in m.values())
        mkt[d] = med
        tk = sum(v[1] for v in m.values())
        tu = sum(v[2] for v in m.values())
        for s, (lr, kv, uv) in m.items():
            kp[s][d] = lr - med
            if tk > 0 and tu > 0 and kv > 0 and uv > 0:
                vs[s][d] = math.log(kv / tk) - math.log(uv / tu)
    return dict(grid=grid, gi=gi, kp=kp, volshare=vs, mkt=mkt, syms=syms)


def _win(series, grid, gi, d, w):
    """d 에서 뒤로 w 개 격자 값이 **모두** 있을 때만 리스트를 준다(부분 창 금지)."""
    i = gi[d]
    if i - w + 1 < 0:
        return None
    out = []
    for k in range(i - w + 1, i + 1):
        v = series.get(grid[k])
        if v is None:
            return None
        out.append(v)
    return out


def _ar1(n, seed, phi=AR1_PHI):
    rnd = random.Random(seed)
    xs, x = [], 0.0
    for _ in range(n):
        x = phi * x + rnd.gauss(0, 1)
        xs.append(x)
    return xs


def sym_const(sym):
    """코인별 결정론적 상수 — 내장 hash 는 프로세스마다 달라져 쓰지 않는다."""
    return (sum(ord(c) for c in sym) % 997) / 997.0


def features_x(K):
    """{sym: {date: {키: 값}}} — 가족 X 피처 + 대조."""
    grid, gi = K["grid"], K["gi"]
    out = {}
    for si, s in enumerate(sorted(K["syms"])):
        kp = K["kp"][s]
        ar_a = _ar1(len(grid), SEED_X + si)
        ar_b = _ar1(len(grid), SEED_X + 10_000 + si)
        c = sym_const(s)
        fs = {}
        for d in kp:
            i = gi[d]
            f = dict(kp_rel=kp[d], ctrl_ar1_a=ar_a[i], ctrl_ar1_b=ar_b[i], ctrl_sym_const=c,
                     kp_volshare=K["volshare"][s].get(d))
            for key, w in (("kp_rel_chg5", W_CHG5), ("kp_rel_chg20", W_CHG20)):
                prev = kp.get(grid[i - w]) if i - w >= 0 else None
                f[key] = None if prev is None else kp[d] - prev
            win = _win(kp, grid, gi, d, W_Z60)
            sd = st.pstdev(win) if win else 0.0
            f["kp_rel_z60"] = (kp[d] - st.mean(win)) / sd if (win and sd > 0) else None
            fs[d] = f
        out[s] = fs
    return out


def build_panel(rows_1d, feats, pm, regmap, btc_sym="BTC"):
    """xc.month_stats 가 읽는 모양 그대로 — [(month, date, sym, rank, regime, f, o)]."""
    btc = rows_1d.get(btc_sym)
    panel = []
    for s, rows in rows_1d.items():
        if s not in feats:
            continue
        fs = xf.FeatureSeries(rows, btc)
        for m, i in xf.month_end_indices(rows).items():
            d = rows[i]["date"]
            f = feats[s].get(d)
            if f is None:
                continue
            y, mo = int(m[:4]), int(m[5:])
            m_next = f"{y + (mo == 12):04d}-{(mo % 12) + 1:02d}"
            rank = pm.get(m_next, {}).get(s)
            if rank is None:
                continue
            panel.append(dict(month=m, date=d, sym=s, rank=rank, regime=regmap.get(d),
                              f=f, o=fs.outcome(i), xf=fs.at(i)))
    return panel


# ── 가족 X 판정 ──────────────────────────────────────────────────────────────────────────────
def finalize_x(rec, require_train_top=True):
    """부모 finalize + **train TOP−유니버스 > 0**(xsec_chars 가 남긴 설계 부채 소진)."""
    xc.finalize(rec)
    rec["train_top_ok"] = rec["train_top_edge"] is not None and rec["train_top_edge"] > 0
    if require_train_top and not rec["train_top_ok"]:
        rec["train_ok"] = False
        rec["verdict"] = "REJECTED"
    return rec


def judge_x(stats, keys, m_holm=None, require_train_top=True):
    recs = {k: xc.judge_var(k, SIGN_X[k], *stats[k]) for k in keys}
    ps = {k: r["train_p"] for k, r in recs.items() if r["train_p"] is not None}
    ph = g4.holm(ps) if m_holm else {}
    for k, r in recs.items():
        r["p_holm"] = ph.get(k, r["train_p"]) if m_holm else r["train_p"]
        finalize_x(r, require_train_top)
    return recs


# ── 가족 T ───────────────────────────────────────────────────────────────────────────────────
def series_t(K, fxmap, rows_1d, horizon=HORIZON_T, min_cs=MIN_CS):
    """격자 위 시계열 피처 + 타깃(적격 코인 중앙 fwd20, USDT 기준)."""
    grid, gi, mkt = K["grid"], K["gi"], K["mkt"]
    close = {s: {r["date"]: r["c"] for r in rows} for s, rows in rows_1d.items()}
    lvl = []
    for d in grid:
        fx = fxmap.get(d)
        lvl.append(None if (fx is None or fx <= 0) else mkt[d] - math.log(fx))
    feats, tgt = [], []
    for i, d in enumerate(grid):
        f = {}
        f["kp_mkt"] = lvl[i]
        f["kp_mkt_chg20"] = (lvl[i] - lvl[i - W_CHG20_T]) if (i - W_CHG20_T >= 0 and lvl[i] is not None
                                                              and lvl[i - W_CHG20_T] is not None) else None
        win = [v for v in lvl[max(0, i - W_Z120 + 1):i + 1] if v is not None]
        f["kp_mkt_z120"] = ((lvl[i] - st.mean(win)) / st.pstdev(win)
                            if (lvl[i] is not None and len(win) == W_Z120 and st.pstdev(win) > 0) else None)
        doy = int(d[5:7]) * 31 + int(d[8:10])
        f["ctrl_season"] = math.sin(2 * math.pi * doy / 372.0)
        feats.append(f)
        j = i + horizon
        if j < len(grid):
            rets = []
            for s in K["syms"]:
                a, b = close.get(s, {}).get(d), close.get(s, {}).get(grid[j])
                if a and b and a > 0:
                    rets.append(b / a - 1)
            tgt.append(st.median(rets) if len(rets) >= min_cs else None)
        else:
            tgt.append(None)
    ar = _ar1(len(grid), SEED_X + 777)
    for i, f in enumerate(feats):
        f["ctrl_ar1"] = ar[i]
    return feats, tgt


def analyze_t(K, feats, tgt, split=V.SPLIT, min_shift=MIN_SHIFT_T):
    """부모(validate_altseason)의 회전 귀무·MDE·judge 를 지평 20 에 그대로 적용."""
    grid = K["grid"]
    keep = [i for i in range(len(grid)) if tgt[i] is not None]
    tr_i = [i for i in keep if grid[i] < split]
    ho_i = [i for i in keep if grid[i] >= split]

    def one(idxs, key, sign, seed):
        sub = [i for i in idxs if feats[i].get(key) is not None]
        if len(sub) < 2 * min_shift + 3:
            return None
        fv = [feats[i][key] for i in sub]
        tv = [tgt[i] for i in sub]
        ic = V.spearman(fv, tv)
        nulls = V.rotation_null(fv, tv, min_shift=min_shift, seed=seed)
        return dict(n=len(sub), ic=ic, p=V.pval(ic, nulls, sign), p_two=V.pval_two(ic, nulls),
                    mde=V.mde(nulls, sign), terc=V.tercile_stats(fv, tv, sign),
                    ac=_autocorr(fv, HORIZON_T))

    rows = []
    for k, (key, label, sign) in enumerate([*MAIN_T, *CTRL_T]):
        rows.append(dict(key=key, label=label, sign=sign, is_control=key.startswith("ctrl_"),
                         train=one(tr_i, key, sign, SEED_X + 100 + k),
                         holdout=one(ho_i, key, sign, SEED_X + 600 + k)))
    hp = V.holm([(r["key"], r["train"]["p"]) for r in rows if not r["is_control"] and r["train"]], m=M_HOLM_T)
    for r in rows:
        if r["train"]:
            r["train"]["p_holm"] = hp.get(r["key"], r["train"]["p"]) if not r["is_control"] else r["train"]["p"]
        r["verdict"], r["why"] = V.judge(r)
    return rows, len(tr_i), len(ho_i)


def _autocorr(xs, lag):
    if len(xs) <= lag + 2:
        return None
    a, b = xs[:-lag], xs[lag:]
    ma, mb = st.mean(a), st.mean(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    den = math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))
    return num / den if den > 0 else None


# ── 출력 ─────────────────────────────────────────────────────────────────────────────────────
def _f(v, w=7, pct=False):
    return xc._f(v, w, pct)


def _p(v):
    return xc._p(v)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    print("=" * 112)
    print("거래소 간 프리미엄(김치 프리미엄) — 사전 등록 시험 (registry kimchi_prereg_2026_09_22)")
    print(f"가족 X 횡단면 {len(MAIN_X)}셀(Holm {M_HOLM_X}) · 가족 T 시계열 {len(MAIN_T)}셀(Holm {M_HOLM_T}) "
          f"· DEPLOY_ON_PASS={DEPLOY_ON_PASS}")
    print("=" * 112)

    syms = va._syms()
    if "--no-fetch" not in argv:
        va.fetch(syms, ["1d"])
    rows_1d = va.load_tf(syms, "1d", long=True)
    krw_by = {s: load_krw(s) for s in rows_1d}
    K = build_kp(rows_1d, krw_by)
    if not K["grid"]:
        print("격자 없음 — data_kimchi 가 비었다(build_data_kimchi.py 선행)")
        return 1
    print(f"[데이터] USDT {len(rows_1d)} 종목 · KRW 겹침 {len(K['syms'])} · 격자 {K['grid'][0]}~{K['grid'][-1]} "
          f"({len(K['grid'])}일, 코인 {MIN_CS}개 이상인 날만)")

    regmap = rs.build_regime_map(rows_by=rows_1d)
    pm = pc.pit_membership(rows_1d)
    feats = features_x(K)
    panel = build_panel(rows_1d, feats, pm, regmap)
    months = sorted({p["month"] for p in panel})
    print(f"[패널] 코인-월 {len(panel)} · 월 {months[0]}~{months[-1]} ({len(months)})")

    keys_x = [k for k, _ in MAIN_X] + [k for k, _ in CTRL_X] + [k for k, _ in DIAG_X]
    stats = {k: xc.split(xc.month_stats(panel, k)) for k in keys_x}
    recs = judge_x(stats, [k for k, _ in MAIN_X], m_holm=M_HOLM_X)
    recs_c = judge_x(stats, [k for k, _ in CTRL_X], m_holm=None)
    recs_d = judge_x(stats, [k for k, _ in DIAG_X], m_holm=None)

    hdr = (f"{'셀':<16}{'sg':<3}{'dir':<4}{'trM':>4}{'tr_IC':>8}{'ICIR':>7}{'p':>7}{'Holm':>7}{'yr+':>6}"
           f"{'lbyo':>8}{'trTOPe':>8}{'ooM':>4}{'oo_IC':>8}{'oo_p':>7}{'ooTOPe':>8}{'ooTOP':>8}  판정")

    def show(rs_):
        for k, r in rs_.items():
            yp = "-" if r["year_pos_share"] is None else f"{r['year_pos_share'] * 100:.0f}%"
            print(f"{k:<16}{r['sign']:<3}{r['dir']:<4}{r['train_months']:>4}{_f(r['train_ic'])}{_f(r['train_icir'])}"
                  f"{_p(r['train_p']):>7}{_p(r['p_holm']):>7}{yp:>6}{_f(r['lbyo_ic'])}{_f(r['train_top_edge'], pct=True)}%"
                  f"{r['oos_months']:>4}{_f(r['oos_ic'])}{_p(r['oos_p']):>7}{_f(r['oos_top_edge'], pct=True)}%"
                  f"{_f(r['oos_top_abs'], pct=True)}%  {r['verdict']}{' REVERSED' if r['reversed'] else ''}")

    print("\n== 가족 X 주 판정 (fwd20 IC, 방향 정렬) ==")
    print(hdr)
    show(recs)
    print("-- 음성 대조 (Holm 미보정, 방향 train 선택) --")
    show(recs_c)
    print("-- 진단 셀 (판정 아님) --")
    show(recs_d)
    ctrl_pass = sum(1 for r in recs_c.values() if r["train_ok"])
    cx = {v: sum(1 for r in recs.values() if r["verdict"] == v) for v in ("CONFIRMED", "TRAIN_ONLY", "REJECTED")}
    cx["REVERSED"] = sum(1 for r in recs.values() if r["reversed"])
    valid_x = ctrl_pass <= MAX_CTRL_PASS
    print(f"\n가족 X 판정: {cx} · 대조 통과 {ctrl_pass}/{len(recs_c)} → 판 {'VALID' if valid_x else 'INVALID'}")

    # ── 가족 T ──
    fxmap = ffill(load_fx(), K["grid"])
    nfx = sum(1 for d in K["grid"] if fxmap.get(d) is not None)
    ft, tg = series_t(K, fxmap, rows_1d)
    rows_t, ntr, nho = analyze_t(K, ft, tg)
    print(f"\n== 가족 T 보조 판정 (시계열, 지평 {HORIZON_T}, 회전 귀무 min_shift {MIN_SHIFT_T}, 분할 {V.SPLIT}) ==")
    print(f"   환율 채워진 격자일 {nfx}/{len(K['grid'])} · train {ntr} · holdout {nho}")
    print(f"{'셀':<16}{'sg':>3}{'trN':>6}{'tr_IC':>8}{'p':>7}{'Holm':>7}{'MDE':>8}{'ac20':>7}"
          f"{'hoN':>6}{'ho_IC':>8}{'ho_p':>7}  판정")
    for r in rows_t:
        tr, ho = r["train"], r["holdout"]
        tag = "  [대조]" if r["is_control"] else ""
        print(f"{r['key']:<16}{r['sign']:>3}"
              f"{(tr['n'] if tr else 0):>6}{V.fmt(tr['ic'] if tr else None)}"
              f"{V.fmt(tr['p'] if tr else None):>7}{V.fmt(tr.get('p_holm') if tr else None):>7}"
              f"{V.fmt(tr['mde'] if tr else None):>8}{V.fmt(tr['ac'] if tr else None):>7}"
              f"{(ho['n'] if ho else 0):>6}{V.fmt(ho['ic'] if ho else None)}{V.fmt(ho['p'] if ho else None):>7}"
              f"  {r['verdict']}{tag}")
        if r["why"]:
            print(f"{'':<16}  ↳ " + " · ".join(r["why"]))
    ct_pass = sum(1 for r in rows_t if r["is_control"] and r["verdict"] == "CONFIRMED")
    ctv = {v: sum(1 for r in rows_t if not r["is_control"] and r["verdict"] == v)
           for v in ("CONFIRMED", "INCONCLUSIVE", "REVERSED", "REJECTED")}
    valid_t = ct_pass <= MAX_CTRL_PASS
    print(f"\n가족 T 판정: {ctv} · 대조 통과 {ct_pass}/{len(CTRL_T)} → 판 {'VALID' if valid_t else 'INVALID'}")

    # ── 진단 ──
    diag = {}
    print("\n== D2 절대 김프 (진단, 환율 사용) ==")
    lv = [(d, K["mkt"][d] - math.log(fxmap[d])) for d in K["grid"] if fxmap.get(d)]
    if lv:
        last_d, last_v = lv[-1]
        yr = {}
        for d, v in lv:
            yr.setdefault(d[:4], []).append(v)
        print("  연도별 중앙 프리미엄: " + " ".join(f"{y}:{st.median(v) * 100:+.2f}%" for y, v in sorted(yr.items())))
        print(f"  최근({last_d}) {last_v * 100:+.2f}%")
        diag["d2"] = dict(last_date=last_d, last=last_v, by_year={y: st.median(v) for y, v in yr.items()})

    print("\n== D3 fwd60 / hit20_40 IC (방향 정렬) ==")
    d3 = {}
    for k in [kk for kk, _ in MAIN_X]:
        sgn = 1 if recs[k]["dir"] == "+" else -1
        m60 = xc.month_stats(panel, k, out="fwd60")
        mh = xc.month_stats(panel, k, out="hit20_40")
        d3[k] = dict(ic60=sgn * st.mean(m["ic"] for m in m60) if m60 else None,
                     ic_hit=sgn * st.mean(m["ic"] for m in mh) if mh else None)
        print(f"  {k:<16} IC60 {_f(d3[k]['ic60'])}  IC_hit {_f(d3[k]['ic_hit'])}")
    diag["d3"] = d3

    print("\n== D4 레짐별 IC (형성일 라벨, 방향 정렬) ==")
    d4 = {}
    for k in [kk for kk, _ in MAIN_X]:
        sgn = 1 if recs[k]["dir"] == "+" else -1
        d4[k] = {}
        for g in xc.REGIMES:
            ms = xc.month_stats(panel, k, regime=g, min_cs=8)
            d4[k][g] = dict(months=len(ms), ic=sgn * st.mean(m["ic"] for m in ms) if ms else None)
        print(f"  {k:<16} " + "  ".join(f"{g} {_f(d4[k][g]['ic'])}({d4[k][g]['months']})" for g in xc.REGIMES))
    diag["d4"] = d4

    print("\n== D5 xsec 24변수와의 월별 순위상관 (중복 확인, |rho| 상위 5) ==")
    d5 = {}
    by = {}
    for p in panel:
        by.setdefault(p["month"], []).append(p)
    for k in [kk for kk, _ in MAIN_X]:
        rr = {}
        for o in xf.KEYS:
            vals = []
            for m, ps in by.items():
                pair = [(p["f"].get(k), p["xf"].get(o)) for p in ps]
                pair = [(a, b) for a, b in pair if a is not None and b is not None]
                if len(pair) >= MIN_CS:
                    vals.append(xc.spearman([a for a, _ in pair], [b for _, b in pair]))
            vals = [v for v in vals if v is not None]
            if vals:
                rr[o] = st.mean(vals)
        d5[k] = rr
        top = sorted(rr.items(), key=lambda kv: -abs(kv[1]))[:5]
        print(f"  {k:<16} " + "  ".join(f"{o} {v:+.2f}" for o, v in top))
    diag["d5"] = d5

    print("\n== D6 top30 코호트 IC (train/OOS, 방향 정렬) ==")
    d6 = {}
    for k in [kk for kk, _ in MAIN_X]:
        sgn = 1 if recs[k]["dir"] == "+" else -1
        tr, oo = xc.split(xc.month_stats(panel, k, cohort="top30", min_cs=10))
        d6[k] = dict(train_ic=sgn * st.mean(m["ic"] for m in tr) if tr else None,
                     oos_ic=sgn * st.mean(m["ic"] for m in oo) if oo else None)
        print(f"  {k:<16} train {_f(d6[k]['train_ic'])}({len(tr)})  oos {_f(d6[k]['oos_ic'])}({len(oo)})")
    diag["d6"] = d6

    out = dict(frame="kimchi_prereg_2026_09_22", deploy_on_pass=DEPLOY_ON_PASS,
               grid=dict(first=K["grid"][0], last=K["grid"][-1], n=len(K["grid"]), syms=len(K["syms"])),
               family_x=dict(main={k: recs[k] for k in recs}, ctrl={k: recs_c[k] for k in recs_c},
                             diag={k: recs_d[k] for k in recs_d}, counts=cx,
                             ctrl_pass=ctrl_pass, valid=valid_x),
               family_t=dict(rows=rows_t, counts=ctv, ctrl_pass=ct_pass, valid=valid_t,
                             fx_days=nfx, train_n=ntr, holdout_n=nho),
               diagnostics=diag)
    json.dump(out, open("_kimchi.json", "w"), ensure_ascii=False, indent=1, default=str)
    print("\nRESULT_JSON " + json.dumps(
        dict(family_x=cx, x_valid=valid_x, family_t=ctv, t_valid=valid_t,
             grid=len(K["grid"]), syms=len(K["syms"])), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
