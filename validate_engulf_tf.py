"""
validate_engulf_tf.py — engulfing 을 **1h / 4h / 1w 에서 현행 프레임으로 재시험** (사전 등록)
(2026-09-09, 사용자 지시 "4h랑 1w 돌려봐 1h도 돌려봐").

## 왜 지금 다시 재나
engulfing 은 레포에서 OOS 증거가 가장 강한 패턴이고(v4: bull_btc 롱 OOS n=34 **+7.0%**,
엣지 +8.76%p, bp .004, 왕복 0.4% 비용에도 +6.8%, PIT 코호트로도 유지), 실거래에는 **1d 만**
배포돼 있다. TF 스윕은 **2026-06-24 한 번뿐**이었다:

    TF   n        mean      median    판정
    1d   90       +3.58%    +9.99%    검증통과      ← 배포
    4h   1,103    +0.75%    +0.44%    게이트후탈락
    1h   5,801    -0.23%    -0.29%    기각
    15m  26,616   -0.21%    -0.25%    기각
    (숏: 1d 게이트후탈락 / 4h·1h·15m 기각)

**1w 는 한 번도 안 돌렸다**(연구 로그에 engulfing 1w 행 0건). 그리고 **4h 는 그때 v1 게이트에서
탈락한 뒤 재시험된 적이 없다** — 기각 55종을 레짐별로 전수 재시험한 validate_regime_split_all 의
4h 목록 21개에 engulfing 이 없고, 1h 판(engulfing_1h / engulfing_short_1h)만 들어가 있다.

그 사이 프레임이 네 번 바뀌었다:
  · 게이트 v1(중앙값>0) → **v2**(승률>=35%)  — 2026-09-05 사용자 결정
  · boot_p 베이스라인 **k=30 → k=n** 버그 수정 — 엣지 양수 셀의 p 를 부풀리던 편향 제거
    (재실행에서 통과 셀 2 → 18개). 즉 **옛 탈락 판정이 이 편향을 안고 있었다.**
  · 라벨 판정 → **실거래 프레임**(1w/4h 방식D, 1h ATR 배리어 + 실거래 사이징 자산곡선)
  · 정적 코호트 → **PIT 코호트**(1d 반전 패턴에서 A 엣지를 1.5~2%p 낮춘다 = 더 엄격)
셋은 통과 쪽으로, 하나(PIT)는 기각 쪽으로 작용한다. 어느 쪽이든 **옛 판정을 그대로 믿을 근거가 없다.**

## 동결 (결과 보기 전 고정)
  · 디텍터 **불변** — detector_engulfing.detect / detector_engulfing_short.detect 를 인자 없이 부른다.
    1d 배포 신호 집합은 이 시험으로 한 건도 바뀌지 않는다(test 가 고정).
  · 주 판정 셀 6 = TF {1h, 4h, 1w} x 방향 {long, short}. 레짐 **ALL**, 코호트 **core20 PIT**
    (= 실거래 engulfing 코호트 top20 의 PIT 판, 월말 30일 거래대금 순위를 다음 달에 적용).
  · 여섯 셀은 한 가족 — boot_p 에 **Holm 보정 m=6**.
  · 홀드아웃(달력 마지막): 1h **90일** · 4h **365일** · 1w **730일**(주봉 희소성, validate_exit_1w·tb_wide 와 동일).
  · 청산·베이스라인은 validate_revival 프레임 그대로(4h·1w 방식D / 1h ATR 배리어,
    같은 레짐·코호트·TF 무작위 진입 **k=n**).

## 판정 (사전 등록)
  C1  게이트 v2 — n>=20 · mean>0 · 승률>=35% · **Holm 보정** boot_p<0.05 · OOS>=2/4
  C2  홀드아웃 n>=10 & mean>0
  C2b **train 자체 게이트 통과 AND train n >= holdout n/2**
      (validate_ma180 에서 도입한 가드 — vwap_rev_short_4h 가 표본 92%를 홀드아웃에 두고
       C2 를 통과했던 구멍을 막는다. '다음 확인 시험 설계에도 이식' 항목의 두 번째 적용)
  C3  자산곡선 CAGR>0 & Calmar>0
  넷 다 → **CONFIRMED** / C1·C2b·C3 통과인데 홀드아웃 n<10 → **INCONCLUSIVE** / 그 외 **REJECTED**

**DEPLOY_ON_PASS=False — 통과해도 실거래 반영 없음.** 관찰 기간(~2026-10-06)이고 배포는 사용자
결정이다. 통과 셀은 registry 에 passed_not_deployed 로 남긴다. universe/scheduler 미등재를 테스트가 고정.

## 진단 (판정 아님 — 사후에 여기서 골라 '살았다'고 하지 않는다)
  D1 **1d 참조 셀**(long/short) — 프레임이 알려진 1d 결과를 재현하는지 정합성 확인용.
     판정 가족에 넣지 않는다(Holm 대상 아님). 재현이 안 되면 다른 셀 수치도 믿을 수 없다.
  D2 **정적 코호트 대비** — 같은 셀을 static top20 으로도 재서 PIT 효과 크기를 본다.
  D3 **레짐 분해**(bull_btc / bull_altseason / bear) — 표본이 얇아지므로 서술만.
  D4 **코호트 확대**(top30 / all) — 엣지가 순위에 어떻게 붙는지.
  D5 **왕복 마찰 0.4% 스트레스** — 4h 는 건당이 작아 마찰이 결정적일 수 있다.

## 사전 확률 — 결과 보기 전에 기록한다
  · **4h 가 가장 가망 있다.** 옛 판 mean +0.75% / median +0.44% 는 방향이 맞았고 탈락 사유가
    boot_p·OOS 였을 가능성이 큰데, 그 boot_p 가 정확히 부풀려지던 값이다. 다만 **왕복 0.4%
    마찰이면 +0.75% 의 절반 이상이 날아간다** — CONFIRMED 되더라도 D5 를 통과하는지가 실질 관문이고,
    통과해도 1d 의 +3.58% 와는 체급이 다르다. 신호가 1,103건이라 vol_awakening_4h 처럼
    슬롯을 잠식할 위험도 있다(패턴 단독 프레임은 그걸 못 본다).
  · **1h 는 기각 유력.** 두 번 기각됐고(원판 −0.23%, 재시험 n=16,791 −0.23% OOS 0/4),
    2026-09-05 1h 전용 ATR 채점표에서도 선별은 통과했으나 확인 프레임 **0 CONFIRMED** 였다.
  · **1w 는 INCONCLUSIVE 유력.** 주봉 표본이 얇고, 홀드아웃 730일이 크다. 게다가
    validate_exit_1w 에서 **방식D(−8% 저가 손절)가 주봉 폭에 안 맞는다**는 것이 이미 확인됐다
    (triple_bottom 1w 30건 중 23건 −8% 손절). 같은 이유로 engulfing 1w 도 손절에 털릴 것으로 본다.
  · 숏 세 셀은 전부 기각 예상 — 1d 조차 rejected 이고 레짐 분리 연구에서 숏은 '레짐 문제가
    아니라 패턴 문제'로 결론났다.

## 알려진 한계 (결과 전 기록)
  · 4h·1h 는 장기 이력이 없다(data_long 은 1d 만) — OKX 범위(4h 약 1,100일 / 1h 365일)뿐이라
    에피소드 커버리지가 얇다. 1w 만 data_long 으로 2017~ 을 쓴다.
  · 상장폐지 이력이 없어 PIT 코호트에도 생존 편향이 남는다. 스프레드 미반영.
  · 레짐 ALL 로 판정한다 — 실거래는 레짐 라우팅을 타므로, CONFIRMED 여도 그대로 켜는 것이
    아니라 어느 레짐에서 켤지는 별도 판단이다(D3 는 그 사전 정보일 뿐 판정이 아니다).

## 프레임 v3 — 국면 홀드아웃 (2026-09-09 사용자 결정 ③ "3번도 진행")
위 판(v2, run 34301698148)에서 4h 롱은 **C2 달력 홀드아웃 하나로** 탈락했다(holdout n=397 −0.21%). 그 365일이
bear 지배(2025-09~2026-09)라 탈락이 기전상 설명되지만 v2 는 '규칙이 틀렸다'와 '채점 구간에 그 국면이 없었다'를 못
가른다(frame_v3 문서). 가드 감사(2026-09-09)에서도 L6 국면 홀드아웃이 L2 달력 홀드아웃보다 잘 교정돼 있었다
(4/12 vs 9/12 기각, 거짓음성 1 vs 2). 사용자 결정 ③으로 국면 홀드아웃이 **기본**이 됐다(FRAME_DEFAULT="v3").
  · 재실행 범위(사전 등록): **홀드아웃에서만 탈락한 셀 = 4h 롱 하나.** 1h(OOS 0/4·평균 음수)·1w(승률)·숏 3셀(평균 음수)은
    홀드아웃과 무관한 사유라 다시 돌리지 않는다.
  · v3 판정 셀 = 4h 롱 × 레짐 {bull_btc, bull_altseason, bear} — 국면 홀드아웃은 레짐 조건부 셀에서만 정의된다
    (ALL 은 v3 에서도 달력 365일 = v2 와 동일 → **참조**로만 찍는다). 세 셀 한 가족 **Holm m=3**.
  · 셀별 판정은 frame_v3.judge 그대로(C1 성능·E 에피소드 OOS·C2 국면 홀드아웃·C2b·C3·COV; 성능 실패 → REJECTED /
    COV 실패 → INCONCLUSIVE / E 실패 → REJECTED / 전부 → CONFIRMED) + Holm 보정 boot_p ≥ .05 면 REJECTED.
    풀은 같은 레짐·core20 PIT 무작위 진입 k=n(D3 와 동일).
  · D5 마찰 0.4% 는 그대로 **진단**(v2 사전 등록과 같은 자리 — 프레임만 바꾸고 기준은 안 바꾼다). 단 CONFIRMED 가
    나와도 마찰 후 건당이 얇으면 배포 근거가 아니다(사전 확률 참조).
  · **사전 확률(결과 전 기록)**: bear 는 v2 D3 절대수익 −0.12% 라 REJECTED 유력. bull_altseason 은 5년 173일짜리 국면이라
    4h 범위(2023~)에서 적격 에피소드 <2 → INCONCLUSIVE 유력. bull_btc 가 유일한 가망인데 국면 홀드아웃(최근 365 bull_btc
    일 = 대부분 2024-25 '가짜 상승' 라벨, 알트 중앙 −54%)이 bear 해와 다르게 유리하다는 보장이 없다 — 반반. 어느 셀이
    CONFIRMED 여도 **배포 근거가 아니다**: 마찰 후 +0.27%(v2 풀링) 체급 + 신호 연 약 500건의 슬롯 잠식 + 포트폴리오 단위
    확인 프레임 선결. DEPLOY_ON_PASS=False 유지.

실행: python validate_engulf_tf.py [--no-fetch] [--short] [--tf 4h,1w] [--dir long] [--frame v3|v2]
출력: _engulf_tf.json(v2) / _engulf_tf_v3.json(v3) + RESULT_JSON
"""
import json
import random
import statistics as st
import sys
import time
from datetime import date

import detector_engulfing as eng_long
import detector_engulfing_short as eng_short
import detlib
import frame_v3 as fv
import regime_switch as rs
import validate_pit_cohort as pc
import validate_regime_split_all as va
import validate_revival as vr

# ── 동결 ─────────────────────────────────────────────────────────────────────
TFS = ("1h", "4h", "1w")
DIRECTIONS = ("long", "short")
COHORT, REGIME = "core20", "ALL"           # core20 = 실거래 engulfing top20 의 PIT 판
HOLDOUT_BY_TF = {"1h": 90, "4h": 365, "1d": 365, "1w": 730}
REF_TF = "1d"                              # D1 참조 셀 (판정 가족 아님)
DIAG_COHORTS = ("top30", "liquid")         # D4
FRICTION = 0.004                           # D5 왕복 마찰 스트레스
DIAG_REGIMES = ("bull_btc", "bull_altseason", "bear")
DEPLOY_ON_PASS = False
FRAME_DEFAULT = "v3"                       # 2026-09-09 사용자 결정 ③ — 국면 홀드아웃이 기본. v2 는 --frame v2 로 재현
V3_REGIMES = ("bull_btc", "bull_altseason", "bear")   # v3 판정 셀(Holm 가족). ALL 은 참조
V3_PRIMARY = ("4h", "long")                # v3 재실행 범위 — 홀드아웃에서만 탈락한 셀

DETECT = {"long": eng_long.detect, "short": eng_short.detect}


def holm(pvals):
    """{key: p} → {key: 보정 p} (step-down)."""
    items = sorted((v, k) for k, v in pvals.items() if v is not None)
    m, out, run = len(items), {}, 0.0
    for r, (v, k) in enumerate(items):
        run = max(run, min(1.0, (m - r) * v))
        out[k] = run
    return out


def pit_idx(rows_by, regmap, pm, cname, regime, tf, seed=vr.SEED):
    """PIT 코호트·레짐 조건의 베이스라인 풀 인덱스 — vr.eval_pool 이 그대로 먹는 형식."""
    tail = vr.tail_for(tf)
    idx = [(s, i)
           for s, rows in rows_by.items()
           for i in range(30, len(rows) - tail - 1)
           if (regime == "ALL" or regmap.get(rows[i]["date"]) == regime)
           and pc.in_cohort(pm, cname, s, rows[i]["date"])]
    if len(idx) > vr.POOL_CAP:
        idx = random.Random(seed).sample(idx, vr.POOL_CAP)
    return idx


def stressed(sigs, cost=FRICTION):
    """왕복 마찰을 씌운 건당 평균 (D5)."""
    return st.mean([s["ret"] - cost for s in sigs]) if sigs else None


def _f(v, w=8):
    return f"{'n/a':>{w}}" if v is None else f"{v * 100:>+{w - 1}.2f}%"


def parse_args(argv):
    """(tfs, dirs, frame, long_1d) — 테스트로 고정."""
    tfs = argv[argv.index("--tf") + 1].split(",") if "--tf" in argv else list(TFS)
    dirs = argv[argv.index("--dir") + 1].split(",") if "--dir" in argv else list(DIRECTIONS)
    frame = argv[argv.index("--frame") + 1] if "--frame" in argv else FRAME_DEFAULT
    assert frame in ("v2", "v3"), frame
    assert all(d in DIRECTIONS for d in dirs), dirs
    return tfs, dirs, frame, "--short" not in argv


def judge_v3(cells, regmap, equity_fn=vr.equity):
    """
    v3 판정 — cells: {regime: dict(sigs=[...], pool=[ret...])}. V3_REGIMES 셀은 frame_v3.judge + Holm(m=가족 크기),
    ALL 은 참조(Holm 없음, 홀드아웃이 v2 와 같다). 반환 {regime: dict(verdict, fails, holm, friction, cf3)}.
    """
    out = {}
    for g, c in cells.items():
        cf3 = fv.judge(c["sigs"], c["pool"], regmap, g, equity_fn=equity_fn)
        out[g] = dict(cf3=cf3, verdict=cf3["verdict"], fails=list(cf3["c1"].get("fails", [])),
                      holm=None, friction=stressed(c["sigs"]), reference=(g == "ALL"))
    ph = holm({g: out[g]["cf3"]["c1"]["boot_p"] for g in out if g in V3_REGIMES})
    for g, p in ph.items():
        out[g]["holm"] = p
        if p >= 0.05 and out[g]["verdict"] != "REJECTED":
            out[g]["verdict"] = "REJECTED"
            out[g]["fails"].append(f"Holm p={p:.3f}")
    return out


def _rows_for(tf, syms, rows_1d):
    if tf == "1d":
        return rows_1d
    if tf == "1w":
        return {s: detlib.resample_rows(r, "1w") for s, r in rows_1d.items()}
    return va.load_tf(syms, tf)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    tfs, dirs, frame, long_1d = parse_args(argv)   # 1w 는 장기 이력이 없으면 train 이 빈다
    print(f"engulfing TF 재시험 | 프레임 {frame} | TF {tfs} x {dirs} | 코호트 {COHORT}(PIT) 레짐 {REGIME} "
          f"| Holm m={len(tfs) * len(dirs)} | DEPLOY_ON_PASS={DEPLOY_ON_PASS}")
    if frame == "v3":
        print(f"  v3: 판정 셀 = 레짐 {V3_REGIMES} 국면 홀드아웃(frame_v3.judge) · Holm m={len(V3_REGIMES) * len(tfs) * len(dirs)} "
              f"· ALL 은 참조(=v2 홀드아웃) · 아래 v2 표는 참조")

    syms = va._syms()
    if "--no-fetch" not in argv:
        va.fetch(syms, [t for t in ("1d", "4h", "1h") if t in tfs or t == "1d"])
    rows_1d = va.load_tf(syms, "1d", long=long_1d)
    regmap = rs.build_regime_map(rows_by=rows_1d) if long_1d else rs.build_regime_map()
    if long_1d:
        print(f"[long] 1d 장기 이력 — 최초 {min(r[0]['date'] for r in rows_1d.values())} "
              f"· 레짐 라벨 {min(regmap)}~{max(regmap)}")
    pm = pc.pit_membership(rows_1d)
    turn, months = pc.cohort_turnover(pm, COHORT)
    print(f"[PIT] {COHORT} 월평균 교체 {turn:.1f} 코인 / {months}개월"
          if turn is not None else f"[PIT] {COHORT} 교체 측정 불가")

    out = dict(frame="engulf_tf" + ("_v3" if frame == "v3" else ""), cohort=COHORT, regime=REGIME,
               deploy_on_pass=DEPLOY_ON_PASS, cells={}, cells_v3={}, diag={})
    ctx, raw, rpool = {}, {}, {}

    def regime_pool(tf, d, g):
        """같은 레짐·core20 PIT 무작위 진입 풀(k=n 베이스라인) — v3 판정과 D3 가 공유."""
        k = (tf, d, g)
        if k not in rpool:
            c = ctx[tf]
            rpool[k] = vr.eval_pool(tf, pit_idx(c["rows_by"], regmap, pm, COHORT, g, tf),
                                    c["rows_by"], c["atrs"], regmap, d)
        return rpool[k]

    # ── 셀 평가 (주 판정 + D1 참조) ────────────────────────────────────────
    for tf in list(tfs) + ([REF_TF] if REF_TF not in tfs else []):
        t0 = time.time()
        rows_by = {s: r for s, r in _rows_for(tf, syms, rows_1d).items() if len(r) > 60}
        if not rows_by:
            print(f"\n[{tf}] 데이터 없음 — 건너뜀")
            continue
        static20 = set(vr.turnover_rank(rows_1d)[:20]) & set(rows_by)
        cohorts = {"static20": static20, "top30": set(vr.turnover_rank(rows_1d)[:30]) & set(rows_by),
                   "liquid": set(rows_by)}
        pools, atrs = vr.build_context(tf, rows_by, cohorts, regmap)
        first = min(r[0]["date"] for r in rows_by.values())
        last = max(r[-1]["date"] for r in rows_by.values())
        cutoff = date.fromordinal(date.fromisoformat(last).toordinal()
                                  - HOLDOUT_BY_TF[tf]).isoformat()
        span = max(1, date.fromisoformat(cutoff).toordinal() - date.fromisoformat(first).toordinal())
        pit_pool_idx = pit_idx(rows_by, regmap, pm, COHORT, REGIME, tf)
        ctx[tf] = dict(rows_by=rows_by, atrs=atrs, pools=pools, cohorts=cohorts,
                       cutoff=cutoff, span=span, first=first, last=last,
                       pit_pool_idx=pit_pool_idx, static20=static20)
        print(f"\n[{tf}] 종목 {len(rows_by)} · train {first}~{cutoff} · holdout {HOLDOUT_BY_TF[tf]}일 "
              f"· PIT 풀 {len(pit_pool_idx)} · 수집 {time.time() - t0:.0f}s", flush=True)

        for d in dirs:
            by_sym = vr.collect(tf, DETECT[d], d, rows_by, atrs, regmap)
            all_sigs = [x for v in by_sym.values() for x in v]
            sigs = pc.pit_filter(all_sigs, pm, COHORT)
            pool = vr.eval_pool(tf, pit_pool_idx, rows_by, atrs, regmap, d)
            rec = vr.gate_cell(sigs, pool)
            raw[(tf, d)] = dict(rec=rec, sigs=sigs, by_sym=by_sym, all_sigs=all_sigs, pool=pool)
            tag = "참조" if tf == REF_TF and REF_TF not in tfs else "판정"
            print(f"  [{tag}] {d:5} n={rec['n']:5} mean={_f(rec['mean'])} med={_f(rec['median'])} "
                  f"승률 {rec['win_rate'] * 100:3.0f}% 엣지 {_f(rec['edge'])} "
                  f"boot_p={rec['boot_p']:.3f} OOS {rec['oos_pos']}/4", flush=True)

    # ── 주 판정 ──────────────────────────────────────────────────────────
    fam = [(tf, d) for tf in tfs for d in dirs if (tf, d) in raw]
    ph = holm({k: raw[k]["rec"]["boot_p"] for k in fam})
    print(f"\n== {'v2 참조 (판정은 아래 v3)' if frame == 'v3' else '주 판정'} (Holm m={len(fam)}) ==")
    for k in fam:
        tf, d = k
        r, c = raw[k], ctx[tf]
        rec, sigs = r["rec"], r["sigs"]
        # vr.confirm 은 CONFIRM_COHORT 키로 셀을 찾는다 — 코호트 이름과 무관하게 그 키로 넘긴다.
        conf = vr.confirm({vr.CONFIRM_COHORT: dict(gate=rec, sigs=sigs)}, c["cutoff"], c["span"])
        p_adj = ph.get(k, 1.0)
        fails = [x for x in rec["reason"].split(", ") if x and not x.startswith("boot_p")]
        if p_adj >= 0.05:
            fails.append(f"Holm p={p_adj:.3f}")
        c1 = not fails
        ho, eq = conf["holdout"], conf["equity"]
        tr = [s for s in sigs if s["date"] < c["cutoff"]]
        tr_rec = vr.gate_cell(tr, r["pool"]) if tr else dict(n=0, reason="train 0")
        c2b = bool(tr) and not tr_rec.get("reason") and tr_rec["n"] >= max(1, ho["n"] // 2)
        if not c2b and tr:
            fails.append(f"C2b(train n={tr_rec['n']} {tr_rec.get('reason', '') or 'ok'})")
        if c1 and c2b and conf["c3_equity"] and ho["n"] < vr.HOLDOUT_MIN_N:
            verdict = "INCONCLUSIVE"
        elif c1 and c2b and conf["c2_holdout"] and conf["c3_equity"]:
            verdict = "CONFIRMED"
        else:
            verdict = "REJECTED"
            if not conf["c2_holdout"] and ho["n"] >= vr.HOLDOUT_MIN_N:
                fails.append(f"holdout {_f(ho['mean']).strip()}")
            if not conf["c3_equity"]:
                fails.append("자산곡선")
        print(f"  {tf:3} {d:5} n={rec['n']:5} mean={_f(rec['mean'])} 승률 {rec['win_rate'] * 100:3.0f}% "
              f"boot_p={rec['boot_p']:.3f}→Holm {p_adj:.3f} | holdout n={ho['n']:4} {_f(ho['mean'])} "
              f"| Calmar {eq['calmar'] if eq['calmar'] is None else round(eq['calmar'], 2)} "
              f"→ **{verdict}**" + (f"  ({', '.join(fails)})" if fails else ""))
        out["cells"][f"{tf}_{d}"] = dict(
            n=rec["n"], mean=rec["mean"], median=rec["median"], win=rec["win_rate"],
            edge=rec["edge"], boot_p=rec["boot_p"], holm=p_adj, oos=rec["oos_pos"],
            train_n=tr_rec["n"], holdout_n=ho["n"], holdout_mean=ho["mean"],
            calmar=eq["calmar"], cagr=eq["cagr"], verdict=verdict)

    # ── v3 주 판정 — 레짐 셀 × 국면 홀드아웃 ────────────────────────────
    if frame == "v3":
        print(f"\n== v3 주 판정 — 국면 홀드아웃 · 레짐 셀 {V3_REGIMES} · Holm m={len(V3_REGIMES) * len(fam)} (ALL 은 참조) ==")
        v3cells = {}
        for k in fam:
            tf, d = k
            r = raw[k]
            for g in V3_REGIMES + ("ALL",):
                gs = r["sigs"] if g == "ALL" else [s for s in r["sigs"] if s["regime"] == g]
                v3cells[(tf, d, g)] = dict(sigs=gs, pool=(r["pool"] if g == "ALL" else regime_pool(tf, d, g)))
        # Holm 가족 = 전 (tf,d) 의 레짐 셀. judge_v3 는 셀 dict 를 레짐 키로 받으므로 (tf,d) 별로 부르되 Holm 은 가족 전체로 다시 건다.
        res = {}
        for k in fam:
            tf, d = k
            res[k] = judge_v3({g: v3cells[(tf, d, g)] for g in V3_REGIMES + ("ALL",)}, regmap)
        if len(fam) > 1:   # 가족이 (tf,d) 하나를 넘으면 Holm 을 가족 전체 크기로 재적용
            ph3 = holm({(k, g): res[k][g]["cf3"]["c1"]["boot_p"] for k in fam for g in V3_REGIMES})
            for (k, g), p in ph3.items():
                cell = res[k][g]
                cell["fails"] = [f for f in cell["fails"] if not f.startswith("Holm")]
                cell["holm"] = p
                cell["verdict"] = cell["cf3"]["verdict"]
                if p >= 0.05 and cell["verdict"] != "REJECTED":
                    cell["verdict"] = "REJECTED"; cell["fails"].append(f"Holm p={p:.3f}")
        for k in fam:
            tf, d = k
            for g in V3_REGIMES + ("ALL",):
                cell = res[k][g]; cf3 = cell["cf3"]; c1 = cf3["c1"]; E = cf3["E"]; eq = cf3["equity"] or {}
                tag = "참조" if g == "ALL" else "판정"
                hp = "  -  " if cell["holm"] is None else f"{cell['holm']:.3f}"
                print(f"  [{tag}] {tf:3} {d:5} {g:<15} n={c1['n']:5} mean={_f(c1['mean'])} 승률 {c1['win_rate'] * 100:3.0f}% "
                      f"엣지 {_f(c1['edge'])} boot_p={c1['boot_p']:.3f}→Holm {hp} | E {E['positive']}/{E['qualifying']} "
                      f"| holdout(국면 {cf3['holdout']['days']}일) n={cf3['holdout']['n']:4} {_f(cf3['holdout']['mean'])} "
                      f"| train n={cf3['train']['n']} C2b {cf3['c2b_train']} | Calmar {eq.get('calmar') if eq.get('calmar') is None else round(eq['calmar'], 2)} "
                      f"| COV {cf3['coverage']} | 마찰0.4% {_f(cell['friction'])} → **{cell['verdict']}**"
                      + (f"  ({', '.join(cell['fails'])})" if cell["fails"] else ""))
                print(fv.fmt_episodes(cf3["episodes"]))
                out["cells_v3"][f"{tf}_{d}_{g}"] = dict(
                    reference=(g == "ALL"), n=c1["n"], mean=c1["mean"], median=c1["median"], win=c1["win_rate"],
                    edge=c1["edge"], boot_p=c1["boot_p"], holm=cell["holm"],
                    E=dict(ok=E["ok"], qualifying=E["qualifying"], positive=E["positive"], max_share=E["max_share"]),
                    holdout_n=cf3["holdout"]["n"], holdout_mean=cf3["holdout"]["mean"], holdout_days=cf3["holdout"]["days"],
                    train_n=cf3["train"]["n"], c2b=cf3["c2b_train"], calmar=eq.get("calmar"), cagr=eq.get("cagr"),
                    coverage=cf3["coverage"], friction_mean=cell["friction"], verdict=cell["verdict"], fails=cell["fails"],
                    episodes=cf3["episodes"])
        counts = {}
        for key, v in out["cells_v3"].items():
            if not v["reference"]:
                counts[v["verdict"]] = counts.get(v["verdict"], 0) + 1
        out["v3_counts"] = counts
        print(f"  v3 집계(판정 셀 {len(V3_REGIMES) * len(fam)}): {counts} | DEPLOY_ON_PASS={DEPLOY_ON_PASS} — CONFIRMED 도 실거래 반영 없음")

    # ── D1 참조 (1d) ─────────────────────────────────────────────────────
    if REF_TF in ctx and REF_TF not in tfs:
        print(f"\n== D1 참조 {REF_TF} (판정 아님 — 프레임 정합성) ==")
        for d in dirs:
            rec = raw[(REF_TF, d)]["rec"]
            print(f"  {d:5} n={rec['n']:5} mean={_f(rec['mean'])} med={_f(rec['median'])} "
                  f"승률 {rec['win_rate'] * 100:3.0f}% boot_p={rec['boot_p']:.3f}")
            out["diag"][f"d1_ref_{REF_TF}_{d}"] = dict(n=rec["n"], mean=rec["mean"],
                                                       median=rec["median"], boot_p=rec["boot_p"])

    # ── D2 정적 코호트 대비 ───────────────────────────────────────────────
    print("\n== D2 정적 top20 대비 (판정 아님 — PIT 효과) ==")
    for k in fam:
        tf, d = k
        c, r = ctx[tf], raw[k]
        s_sigs = [x for s in c["static20"] for x in r["by_sym"].get(s, [])]
        s_pool = vr.eval_pool(tf, c["pools"][("static20", REGIME)], c["rows_by"],
                              c["atrs"], regmap, d)
        s_rec = vr.gate_cell(s_sigs, s_pool)
        p = r["rec"]
        print(f"  {tf:3} {d:5} static n={s_rec['n']:5} {_f(s_rec['mean'])} 엣지 {_f(s_rec['edge'])} "
              f"| PIT n={p['n']:5} {_f(p['mean'])} 엣지 {_f(p['edge'])}")
        out["diag"][f"d2_static_{tf}_{d}"] = dict(n=s_rec["n"], mean=s_rec["mean"], edge=s_rec["edge"])

    # ── D3 레짐 분해 ─────────────────────────────────────────────────────
    print("\n== D3 레짐 분해 (판정 아님 — 표본 얇음) ==")
    for k in fam:
        tf, d = k
        c, r = ctx[tf], raw[k]
        parts = []
        for g in DIAG_REGIMES:
            gs = [s for s in r["sigs"] if s["regime"] == g]
            if len(gs) < 5:
                parts.append(f"{g} n={len(gs)}")
                continue
            gr = vr.gate_cell(gs, regime_pool(tf, d, g))
            parts.append(f"{g} n={gr['n']} {_f(gr['mean']).strip()} 엣지 {_f(gr['edge']).strip()}")
        print(f"  {tf:3} {d:5} " + " · ".join(parts))
        out["diag"][f"d3_regime_{tf}_{d}"] = parts

    # ── D4 코호트 확대 ───────────────────────────────────────────────────
    print("\n== D4 코호트 확대 (판정 아님) ==")
    for k in fam:
        tf, d = k
        c, r = ctx[tf], raw[k]
        parts = []
        for cn in DIAG_COHORTS:
            cs = pc.pit_filter(r["all_sigs"], pm, cn)
            cp = vr.eval_pool(tf, pit_idx(c["rows_by"], regmap, pm, cn, REGIME, tf),
                              c["rows_by"], c["atrs"], regmap, d)
            cr = vr.gate_cell(cs, cp)
            parts.append(f"{cn} n={cr['n']} {_f(cr['mean']).strip()} 엣지 {_f(cr['edge']).strip()}")
        print(f"  {tf:3} {d:5} " + " · ".join(parts))
        out["diag"][f"d4_cohort_{tf}_{d}"] = parts

    # ── D5 마찰 스트레스 ─────────────────────────────────────────────────
    print(f"\n== D5 왕복 마찰 {FRICTION * 100:.1f}% 스트레스 (판정 아님) ==")
    for k in fam:
        tf, d = k
        r = raw[k]
        s = stressed(r["sigs"])
        print(f"  {tf:3} {d:5} {_f(r['rec']['mean'])} → {_f(s)}"
              + ("  ← 부호 역전" if s is not None and r["rec"]["mean"] is not None
                 and r["rec"]["mean"] > 0 >= s else ""))
        out["diag"][f"d5_friction_{tf}_{d}"] = s

    fn = "_engulf_tf_v3.json" if frame == "v3" else "_engulf_tf.json"
    json.dump(out, open(fn, "w"), ensure_ascii=False, indent=1)
    print(f"\n[저장] {fn}")
    brief = dict(frame=out["frame"], cells={k: v["verdict"] for k, v in out["cells"].items()},
                 cells_v3={k: v["verdict"] for k, v in out["cells_v3"].items()}, v3_counts=out.get("v3_counts"),
                 deployed=False)
    print("RESULT_JSON: " + json.dumps(brief, ensure_ascii=False))
    return out


if __name__ == "__main__":
    main()
