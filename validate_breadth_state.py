"""
validate_breadth_state.py — 알트 폭 '상태'(몇 개가 · 며칠째 · 몇 % 이상 유지)로 이후 60일을 예측할 수 있는가
(2026-09-07 사전 등록, 사용자 지시).

## 왜 이 프레임인가
episode_profile(_breadth) 는 관측 단위가 **에피소드 전체**라 판정에 t1(종료일)이 필요했다 — 3.5년에 한 번 오는 넓은 불장을
'기록용'으로만 쓰게 된다는 사용자 지적. 여기서는 단위를 **하루**로 바꾼다: 그날의 폭 상태(임계 이상 유지 일수·수준·코인 개수)를
조건으로, **그 시점 이후 60봉**의 횡단면을 본다. 표본이 7개 사건이 아니라 코인-일이 되고, 조건 변수는 전부 그날 알 수 있으므로
**에피소드 진행 중에** 적용할 수 있다.

## 상태 변수 (동결, 전부 인과 — 그날 종가까지)
  · share   = MA180(BREADTH_MA) 위 코인 비율 (이력 >= 180봉인 코인 중). n_tot < MIN_CS(15) 인 날 제외
  · n_up    = 그 개수 ("몇 개")
  · run_len = 현재 런의 길이("며칠째"). 런은 share >= thr 로 시작하고, thr 미만이 DIP_TOL(5)일을 **연속으로** 넘으면 끊긴다.
              끊기지 않은 이탈일도 런 길이에 포함(달력 일수). 런 밖이면 0
  · run_max = 현재 런에서 지금까지의 최대 share
  · slope20 = share(d) − share(d−20)
  · 임계 격자 THR_GRID = (0.40, 0.50, 0.60, 0.70) — **주 판정은 0.50**, 나머지는 진단 ("몇 % 이상")

## 버킷 (동결, 결과 보기 전 고정)
  RUN_BUCKETS = 1-10 / 11-30 / 31-60 / 61-120 / 121+ 일        (사용자 표현 "며칠째")
  SHARE_BUCKETS = 50-60 / 60-70 / 70-85 / 85-100 %             ("몇 % 이상")

## 프로필 점수 (동결 — episode_profile_breadth_prereg_2026_09_07 의 전향 시험 부호를 그대로 가져온다)
  BROAD     = rvol20(+) age_bars(−) max_dd_1y(−) turnover_30d(−) mom_6m(−) bb_squeeze(+)
  DEFENSIVE = rvol20(−) beta_btc_60(−) max_dd_1y(+) age_bars(+)
  각 변수의 **그날 횡단면 순위**를 부호대로 정렬해 평균 → 코인별 점수. 정의는 xsec_features 와 동일(테스트가 값 일치를 고정).

## 결과 (동결)
  · uni_fwd60   = 그날 횡단면 코인들의 60봉 선행수익 **중앙값** (지수가 아니라 코인 중앙값 — '알트가 오르는가')
  · up_fwd60    = 60봉 뒤 양수인 코인 비율
  · ic_broad    = spearman(BROAD 점수, 60봉 선행수익),  ic_def = spearman(DEFENSIVE 점수, 60봉 선행수익)
  · 진단 지평 20 / 120봉 병기

## 판정 (사전 등록)
  주 임계 0.50. 계산일은 SAMPLE_STEP(5)일 간격(겹치는 창이라 일 단위 해상도는 정보가 아니라 비용).
  H1 (지속 → 계속 오른다): run_len 버킷을 따라 uni_fwd60 평균이 **비감소**이고, 61-120 과 121+ 버킷에서 > 0 (블록 부트 p<.05)
  H2 (프로필 전환, 핵심): ic_broad − ic_def 가 run_len 버킷을 따라 **비감소**이고, run_len >= 61 에서 ic_broad > 0 이며
      ic_broad > ic_def (블록 부트 p<.05)
  OOS: train = 2023-01-01 이전 날짜, test = 이후. **양쪽에 넓은 에피소드가 하나씩 들어간다**(2020-21 / 2023-24).
      두 가설 모두 train 통과 + test 에서 같은 부호 유지여야 한다.
  판정: RULE_CANDIDATE(H1&H2 train 통과 AND OOS 부호 재현) / SUGGESTIVE(train 만) / NONE.
  추론: **블록 부트스트랩**(BOOT_N 2000, 시드 42) — 블록 = 그 임계에서의 극대 런 하나(런 밖 연속 구간도 각각 하나).
      겹치는 60봉 창과 에피소드 소수성을 반영하기 위해 날짜가 아니라 블록을 복원추출한다.

**배포 반영 없음(DEPLOY_ON_PASS=False).** 통과해도 그 자체로 매매 규칙이 아니다 — 다음 단계(넓은 국면에서 코인 선택·슬롯
우선순위)는 라우팅 복제 프레임에서 별도 사전 등록. 관찰 기간 ~2026-10-06 실거래 무변경.

## 공개 (사전 등록 순수성)
  이 설계는 **현재 폭이 문턱 근처(2026-08 말 12% → 47%)** 라는 것을 본 뒤에 만들었다. 그러나 프로필 부호는 그 전(07:24 UTC)에
  고정·푸시됐고, 버킷·임계·지평·분할·판정식은 실행 전에 이 파일과 registry 에 고정한다. 결과를 본 뒤 바꾸지 않는다.
  또 하나: 병합된 에피소드 판에서 '넓은 2개는 404·206일, 얕은 5개는 77~118일'을 이미 봤다 — 즉 120일 부근 분리는 알고 시작한다.
  그래서 H1/H2 의 관심은 '120일에서 갈리는가'가 아니라 **더 이른 버킷(11-30, 31-60)에서 이미 갈리는가**이다.

한계(실행 전 기록): 생존 편향(현재 OKX 상장 코인만) · 60봉 창이 겹쳐 유효 표본은 코인-일 수보다 훨씬 작다(그래서 블록 부트) ·
런이 7개 에피소드에 지배되므로 블록 수가 적다 · 2018 이전은 폭 계산 대상 코인 15 미만이라 없음.

실행: python validate_breadth_state.py [--no-fetch] [--data-long-only]      출력: _breadth_state.json + RESULT_JSON
"""
import json
import math
import random
import statistics as st
import sys

import validate_episode_profile as ve
import validate_regime_split_all as va
import validate_xsec_chars as vx
import xsec_features as xf

# ── 동결 파라미터 ─────────────────────────────────────────────────────────────────────────────
BREADTH_MA = ve.BREADTH_MA          # 180
MIN_CS = ve.BREADTH_MIN_COINS       # 15
THR_GRID = (0.40, 0.50, 0.60, 0.70)
THR_PRIMARY = 0.50
DIP_TOL = 5
RUN_BUCKETS = ((1, 10), (11, 30), (31, 60), (61, 120), (121, 10 ** 9))
SHARE_BUCKETS = ((0.50, 0.60), (0.60, 0.70), (0.70, 0.85), (0.85, 1.01))
FWD_PRIMARY, FWD_DIAG = 60, (20, 120)
SAMPLE_STEP = 5
SPLIT_DATE = "2023-01-01"
BOOT_N, SEED = 2000, 42
ALPHA = 0.05
DEPLOY_ON_PASS = False
BROAD = (("rvol20", 1), ("age_bars", -1), ("max_dd_1y", -1), ("turnover_30d", -1), ("mom_6m", -1), ("bb_squeeze", 1))
DEFENSIVE = (("rvol20", -1), ("beta_btc_60", -1), ("max_dd_1y", 1), ("age_bars", 1))
FEATS = tuple(sorted({k for k, _ in BROAD} | {k for k, _ in DEFENSIVE}))


# ── 폭 상태 ──────────────────────────────────────────────────────────────────────────────────
def breadth_state(rows_1d, thr, ma=BREADTH_MA, dip_tol=DIP_TOL, min_cs=MIN_CS):
    """{date: dict(share, n_up, n_tot, run_len, run_max, slope20, block)} — 전부 그날까지의 정보."""
    bs = ve.breadth_series(rows_1d, ma=ma, min_coins=min_cs)
    ds = sorted(bs)
    out, on, start, dip, run_max, block = {}, False, None, 0, 0.0, 0
    for i, d in enumerate(ds):
        share, n_tot = bs[d]
        n_up = int(round(share * n_tot))
        if share >= thr:
            if not on:
                on, start, run_max, block = True, i, share, block + 1
            dip = 0
            run_max = max(run_max, share)
        elif on:
            dip += 1
            if dip > dip_tol:
                on, block = False, block + 1
        run_len = (i - start + 1) if on else 0
        sl = None
        if i >= 20:
            sl = share - bs[ds[i - 20]][0]
        out[d] = dict(share=share, n_up=n_up, n_tot=n_tot, run_len=run_len,
                      run_max=(run_max if on else None), slope20=sl, block=block)
    return out


def bucket_of(v, buckets):
    for k, (lo, hi) in enumerate(buckets):
        if lo <= v <= hi:
            return k
    return None


# ── 빠른 피처 (xsec_features 와 값이 같아야 한다 — 테스트가 고정) ─────────────────────────────
class FastFeatures:
    """코인 하나의 FEATS 7종. 정의는 xsec_features 와 **동일**(테스트가 값 일치를 고정)하되
    무거운 둘만 손본다: bb_squeeze 는 O(n) 사전계산(원본은 호출마다 120×볼밴 재계산),
    max_dd_1y 는 인덱스별 캐시(원본은 호출마다 252봉 스캔). 나머지는 원본 헬퍼를 그대로 호출한다."""

    def __init__(self, rows, btc_rows):
        self.fs = xf.FeatureSeries(rows, btc_rows)
        n = len(rows)
        c = self.fs.c
        w = [None] * n                     # 볼밴 폭 시계열 (O(n))
        s1 = s2 = 0.0
        for i in range(n):
            s1 += c[i]; s2 += c[i] * c[i]
            if i >= xf.BB_N:
                s1 -= c[i - xf.BB_N]; s2 -= c[i - xf.BB_N] * c[i - xf.BB_N]
            if i + 1 >= xf.BB_N:
                m = s1 / xf.BB_N
                var = max(s2 / xf.BB_N - m * m, 0.0)
                w[i] = (2 * xf.BB_K * math.sqrt(var)) / m if m > 0 else None
        from collections import deque
        self.sq = [None] * n               # 최근 120 롤링 최소 대비 (O(n))
        dq = deque()
        for i in range(n):
            if w[i] is None:
                continue
            while dq and w[dq[-1]] >= w[i]:
                dq.pop()
            dq.append(i)
            lo = i - xf.BB_SQZ_WIN + 1
            while dq[0] < lo:
                dq.popleft()
            if i + 1 >= xf.BB_N + xf.BB_SQZ_WIN - 1 and w[dq[0]] > 0:
                self.sq[i] = w[i] / w[dq[0]]
        self._mdd = {}

    def _max_dd(self, i):
        if i < 251:
            return None
        if i not in self._mdd:
            h, c = self.fs.h, self.fs.c
            peak, mdd = 0.0, 0.0
            for j in range(i - 251, i + 1):
                peak = max(peak, h[j])
                mdd = min(mdd, c[j] / peak - 1 if peak > 0 else 0.0)
            self._mdd[i] = mdd
        return self._mdd[i]

    def at(self, i):
        fs = self.fs
        out = {k: None for k in FEATS}
        if fs.c[i] <= 0:
            return out
        out["rvol20"] = fs._rvol(i, 20)
        out["mom_6m"] = None if (i < 126 or fs.c[i - 126] <= 0) else fs.c[i - 21] / fs.c[i - 126] - 1
        dv30 = fs._dvmean(i, 30)
        out["turnover_30d"] = None if not dv30 else math.log(dv30)
        out["beta_btc_60"] = fs._beta(i)
        out["age_bars"] = float(i + 1)
        out["bb_squeeze"] = self.sq[i]
        out["max_dd_1y"] = self._max_dd(i)
        return out


_FF_CACHE = {}


def fast_features(sym, rows, btc_rows):
    """FastFeatures 인스턴스를 심볼당 하나만 만든다(임계 격자·진단 지평이 같은 코인을 여러 번 훑으므로)."""
    if sym not in _FF_CACHE:
        _FF_CACHE[sym] = FastFeatures(rows, btc_rows)
    return _FF_CACHE[sym]


def profile_score(items, spec):
    """items = [(sym, {feat: val})] → {sym: 평균 정렬 순위}. 값 결측 코인은 제외(전 변수 필요)."""
    ok = [(s, f) for s, f in items if all(f.get(k) is not None for k, _ in spec)]
    if len(ok) < MIN_CS:
        return {}
    acc = {s: 0.0 for s, _ in ok}
    for k, sgn in spec:
        r = vx.ranks([f[k] * sgn for _, f in ok])
        for (s, _), rk in zip(ok, r):
            acc[s] += rk
    return {s: v / len(spec) for s, v in acc.items()}


# ── 일별 관측 ────────────────────────────────────────────────────────────────────────────────
def daily_rows(rows_1d, state, fwd=FWD_PRIMARY, step=SAMPLE_STEP, btc_sym="BTC"):
    """[dict(date, block, share, n_up, run_len, uni_fwd, up_fwd, ic_broad, ic_def, n)] — step 일 간격."""
    btc = rows_1d.get(btc_sym)
    ff = {s: fast_features(s, r, btc) for s, r in rows_1d.items()}
    idx = {s: {r["date"]: k for k, r in enumerate(r_)} for s, r_ in rows_1d.items()}
    ds = sorted(state)
    out = []
    for di in range(0, len(ds), step):
        d = ds[di]
        items, rets = [], {}
        for s, rows in rows_1d.items():
            i = idx[s].get(d)
            if i is None or i + fwd >= len(rows) or i < BREADTH_MA or rows[i]["c"] <= 0:
                continue
            items.append((s, ff[s].at(i)))
            rets[s] = rows[i + fwd]["c"] / rows[i]["c"] - 1
        if len(items) < MIN_CS:
            continue
        sb = profile_score(items, BROAD)
        sd = profile_score(items, DEFENSIVE)
        syms_b = [s for s in sb if s in rets]
        syms_d = [s for s in sd if s in rets]
        rec = dict(date=d, block=state[d]["block"], share=state[d]["share"], n_up=state[d]["n_up"],
                   run_len=state[d]["run_len"], run_max=state[d]["run_max"], slope20=state[d]["slope20"],
                   n=len(rets), uni_fwd=st.median(rets.values()), up_fwd=sum(1 for v in rets.values() if v > 0) / len(rets),
                   ic_broad=(vx.spearman([sb[s] for s in syms_b], [rets[s] for s in syms_b]) if len(syms_b) >= MIN_CS else None),
                   ic_def=(vx.spearman([sd[s] for s in syms_d], [rets[s] for s in syms_d]) if len(syms_d) >= MIN_CS else None))
        out.append(rec)
    return out


# ── 통계 ──────────────────────────────────────────────────────────────────────────────────────
def block_boot(recs, key, n_boot=BOOT_N, seed=SEED):
    """블록(런 id) 복원추출 → 평균의 p(<=0) / CI."""
    vals = [(r["block"], r[key]) for r in recs if r.get(key) is not None]
    if not vals:
        return dict(n=0, mean=None, p=None, ci=None, blocks=0)
    by = {}
    for b, v in vals:
        by.setdefault(b, []).append(v)
    blocks = list(by.values())
    mean = st.mean(v for _, v in vals)
    rng = random.Random(seed)
    draws = []
    for _ in range(n_boot):
        pick = []
        for _ in blocks:
            pick += blocks[rng.randrange(len(blocks))]
        draws.append(st.mean(pick))
    draws.sort()
    return dict(n=len(vals), blocks=len(blocks), mean=mean, p=sum(1 for v in draws if v <= 0) / len(draws),
                ci=(draws[int(0.025 * (len(draws) - 1))], draws[int(0.975 * (len(draws) - 1))]))


def diff_boot(recs, k1, k2, n_boot=BOOT_N, seed=SEED):
    """같은 날의 k1 − k2 차이에 블록 부트."""
    sub = [dict(block=r["block"], d=r[k1] - r[k2]) for r in recs if r.get(k1) is not None and r.get(k2) is not None]
    return block_boot(sub, "d", n_boot, seed)


def by_bucket(recs, buckets, field, key):
    out = {}
    for k, (lo, hi) in enumerate(buckets):
        sub = [r for r in recs if r.get(field) is not None and lo <= r[field] <= hi]
        out[k] = dict(label=f"{lo}-{hi if hi < 10**8 else '+'}", n=len(sub),
                      mean=(st.mean(r[key] for r in sub if r.get(key) is not None) if any(r.get(key) is not None for r in sub) else None),
                      boot=block_boot(sub, key) if sub else None)
    return out


def nondecreasing(vals, tol=1e-9):
    vs = [v for v in vals if v is not None]
    return all(b >= a - tol for a, b in zip(vs, vs[1:])) and len(vs) >= 2


def judge(recs):
    """사전 등록 H1/H2 + OOS."""
    tr = [r for r in recs if r["date"] < SPLIT_DATE]
    oo = [r for r in recs if r["date"] >= SPLIT_DATE]
    res = {}
    for tag, sub in (("train", tr), ("oos", oo), ("all", recs)):
        on = [r for r in sub if r["run_len"] >= 1]
        h1_b = by_bucket(on, RUN_BUCKETS, "run_len", "uni_fwd")
        d_recs = [dict(r, dif=(r["ic_broad"] - r["ic_def"]) if (r["ic_broad"] is not None and r["ic_def"] is not None) else None) for r in on]
        h2_b = by_bucket(d_recs, RUN_BUCKETS, "run_len", "dif")
        icb_b = by_bucket(on, RUN_BUCKETS, "run_len", "ic_broad")
        late = [r for r in on if r["run_len"] >= 61]
        res[tag] = dict(n=len(on), h1_buckets=h1_b, h2_buckets=h2_b, icb_buckets=icb_b,
                        h1_mono=nondecreasing([v["mean"] for v in h1_b.values()]),
                        h1_late=[block_boot([r for r in on if lo <= r["run_len"] <= hi], "uni_fwd") for lo, hi in RUN_BUCKETS[3:]],
                        h2_mono=nondecreasing([v["mean"] for v in h2_b.values()]),
                        icb_late=block_boot(late, "ic_broad"), icd_late=block_boot(late, "ic_def"),
                        dif_late=diff_boot(late, "ic_broad", "ic_def"))
    def h1_ok(t):
        r = res[t]
        return bool(r["h1_mono"] and all(b["mean"] is not None and b["mean"] > 0 and b["p"] is not None and b["p"] < ALPHA for b in r["h1_late"]))
    def h2_ok(t):
        r = res[t]
        return bool(r["h2_mono"] and r["icb_late"]["mean"] is not None and r["icb_late"]["mean"] > 0
                    and r["icb_late"]["p"] is not None and r["icb_late"]["p"] < ALPHA
                    and r["dif_late"]["mean"] is not None and r["dif_late"]["mean"] > 0 and r["dif_late"]["p"] < ALPHA)
    def sign_ok(t):
        r = res[t]
        return bool(r["icb_late"]["mean"] is not None and r["icb_late"]["mean"] > 0
                    and r["dif_late"]["mean"] is not None and r["dif_late"]["mean"] > 0
                    and all(b["mean"] is not None and b["mean"] > 0 for b in r["h1_late"]))
    res["h1_train"], res["h2_train"], res["oos_sign"] = h1_ok("train"), h2_ok("train"), sign_ok("oos")
    res["verdict"] = ("RULE_CANDIDATE" if (res["h1_train"] and res["h2_train"] and res["oos_sign"])
                      else ("SUGGESTIVE" if (res["h1_train"] and res["h2_train"]) else "NONE"))
    return res


def _f(v, w=7, pct=False):
    if v is None:
        return " " * (w - 1) + "-"
    return f"{v*100:{w}.2f}" if pct else f"{v:{w}.3f}"


def _p(v):
    return "   -" if v is None else f"{v:.3f}"


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    print(f"알트 폭 상태 → 선행 {FWD_PRIMARY}봉 | 임계 격자 {THR_GRID} 주 {THR_PRIMARY} · 이탈허용 {DIP_TOL}일 · 표집 {SAMPLE_STEP}일 "
          f"· 런 버킷 {[f'{a}-{b if b<10**8 else 0}' for a, b in RUN_BUCKETS]} · 분할 {SPLIT_DATE} · 블록부트 {BOOT_N} | DEPLOY_ON_PASS={DEPLOY_ON_PASS}")
    syms = va._syms()
    if "--no-fetch" not in argv and "--data-long-only" not in argv:
        va.fetch(syms, ["1d"])
    import glob, os, detlib
    long_syms = sorted({os.path.basename(p).split("_1d")[0].upper() for p in glob.glob(f"{detlib.LONG_DIR}/*_1d.csv.gz")})
    rows_1d = va.load_tf(sorted(set(syms) | set(long_syms)), "1d", long=True)
    print(f"[data] 코인 {len(rows_1d)}", flush=True)

    out = dict(frame="breadth_state", thr_primary=THR_PRIMARY, split=SPLIT_DATE, coins=len(rows_1d), deploy_on_pass=DEPLOY_ON_PASS, grids={})
    for thr in THR_GRID:
        state = breadth_state(rows_1d, thr)
        recs = daily_rows(rows_1d, state)
        on = [r for r in recs if r["run_len"] >= 1]
        runs = sorted({r["block"] for r in on})
        print(f"\n=== 임계 {thr*100:.0f}% | 관측일 {len(recs)} (런 안 {len(on)}) · 런 {len(runs)}개 ===", flush=True)
        print(f"{'며칠째':<10}{'n일':>5}{'코인 중앙 fwd60':>16}{'양수비율':>9}{'ic_broad':>10}{'ic_def':>9}{'차이':>8}{'p(차이)':>9}{'폭 평균':>9}{'개수 평균':>10}")
        rows_tbl = {}
        for k, (lo, hi) in enumerate(RUN_BUCKETS):
            sub = [r for r in on if lo <= r["run_len"] <= hi]
            if not sub:
                print(f"{lo}-{hi if hi<10**8 else '+':<8}   0"); continue
            db = diff_boot(sub, "ic_broad", "ic_def")
            icb = [r["ic_broad"] for r in sub if r["ic_broad"] is not None]
            icd = [r["ic_def"] for r in sub if r["ic_def"] is not None]
            lbl = f"{lo}-{hi}" if hi < 10 ** 8 else f"{lo}+"
            print(f"{lbl:<10}{len(sub):>5}{_f(st.mean(r['uni_fwd'] for r in sub),15,True)}%{_f(st.mean(r['up_fwd'] for r in sub),8,True)}%"
                  f"{_f(st.mean(icb) if icb else None,10)}{_f(st.mean(icd) if icd else None,9)}{_f(db['mean'],8)}{_p(db['p']):>9}"
                  f"{_f(st.mean(r['share'] for r in sub),8,True)}%{st.mean(r['n_up'] for r in sub):>10.0f}")
            rows_tbl[lbl] = dict(n=len(sub), uni=st.mean(r["uni_fwd"] for r in sub), up=st.mean(r["up_fwd"] for r in sub),
                                 ic_broad=(st.mean(icb) if icb else None), ic_def=(st.mean(icd) if icd else None),
                                 dif=db["mean"], p=db["p"], share=st.mean(r["share"] for r in sub), n_up=st.mean(r["n_up"] for r in sub))
        # 수준 버킷 ("몇 % 이상")
        print(f"  [폭 수준별] " + " | ".join(
            f"{int(lo*100)}-{int(min(hi,1)*100)}% n{len([r for r in on if lo <= r['share'] < hi])} "
            f"fwd60 {_f(st.mean([r['uni_fwd'] for r in on if lo <= r['share'] < hi]) if any(lo <= r['share'] < hi for r in on) else None,6,True)}%"
            for lo, hi in SHARE_BUCKETS))
        j = judge(recs)
        out["grids"][f"{thr:.2f}"] = dict(table=rows_tbl, judge={k: v for k, v in j.items() if k in ("verdict", "h1_train", "h2_train", "oos_sign")},
                                          detail={t: dict(n=j[t]["n"], h1_mono=j[t]["h1_mono"], h2_mono=j[t]["h2_mono"],
                                                          icb_late=j[t]["icb_late"], icd_late=j[t]["icd_late"], dif_late=j[t]["dif_late"],
                                                          h1_late=j[t]["h1_late"]) for t in ("train", "oos", "all")},
                                          runs=len(runs), n_on=len(on))
        if abs(thr - THR_PRIMARY) < 1e-9:
            for t in ("train", "oos"):
                d = j[t]
                print(f"  [{t}] n={d['n']} · H1 단조 {d['h1_mono']} · H2 단조 {d['h2_mono']} · run>=61 ic_broad {_f(d['icb_late']['mean'])} p {_p(d['icb_late']['p'])}"
                      f" · ic_def {_f(d['icd_late']['mean'])} · 차이 {_f(d['dif_late']['mean'])} p {_p(d['dif_late']['p'])} (블록 {d['dif_late']['blocks']})")
            print(f"  ** 판정: {j['verdict']} ** (H1 train {j['h1_train']} · H2 train {j['h2_train']} · OOS 부호 {j['oos_sign']})")
            out["primary_verdict"] = j["verdict"]
            # 진단: 지평 20/120
            for fw in FWD_DIAG:
                r2 = daily_rows(rows_1d, state, fwd=fw)
                on2 = [r for r in r2 if r["run_len"] >= 1]
                line = " | ".join(f"{lo}-{hi if hi<10**8 else '+'}: fwd{fw} {_f(st.mean([r['uni_fwd'] for r in on2 if lo <= r['run_len'] <= hi]) if any(lo <= r['run_len'] <= hi for r in on2) else None,6,True)}%"
                                  f" icb {_f(st.mean([r['ic_broad'] for r in on2 if lo <= r['run_len'] <= hi and r['ic_broad'] is not None]) if any(lo <= r['run_len'] <= hi and r['ic_broad'] is not None for r in on2) else None,6)}"
                                  for lo, hi in RUN_BUCKETS)
                print(f"  [진단 fwd{fw}] {line}")
            # 진단: 현재 상태
            ds = sorted(state); cur = state[ds[-1]]
            print(f"  [현재] {ds[-1]} 폭 {cur['share']*100:.1f}% ({cur['n_up']}/{cur['n_tot']}개) · 런 {cur['run_len']}일째 · 20일 기울기 {(cur['slope20'] or 0)*100:+.1f}%p")
            out["current"] = dict(date=ds[-1], **cur)
    json.dump(out, open("_breadth_state.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print("\nRESULT_JSON: " + json.dumps(dict(frame="breadth_state", verdict=out.get("primary_verdict"), current=out.get("current"),
                                             table={k: v["table"] for k, v in out["grids"].items()}), ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
