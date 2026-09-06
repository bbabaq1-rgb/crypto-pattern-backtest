"""
validate_phase.py — bull_btc 에피소드의 **사이클 위치**(국면 위치) 진단 + 필터 arm 사전 등록 시험
(2026-09-06, 사용자 지시 "응 진행해" — "bull_btc 로 통과하다가 연말에 무너지는 것들").

## 관찰 (v3 재검증에서)

double_bottom_1d / MA180 / inverse_hs 처럼 전혀 다른 신호가 **같은 bull_btc 에피소드에서 함께 죽는다** —
2025-08~11(3개월, 전부 손절) · 2021-10~2022-02 · 2019-10~12. 공통점은 '연말'이 아니라 **큰 고점 뒤에
레짐이 잠깐 꺼졌다가 다시 bull 로 켜지는 짧은 재점등 에피소드**다. 200일선 기울기 라벨은 후행이라
분배 국면의 반등을 bull 로 찍는다. 패턴 문제가 아니라 레짐 라벨의 국면 위치 문제라는 가설.

## 변수 (전부 진입 시점에 알 수 있는 인과 변수 — 결과 전 동결)

  A 에피소드 나이   진입일 − 현재 bull_btc 에피소드 시작일.      버킷: <=90일 / 91~270일 / >270일
  B 재점등         이 에피소드 시작 − 직전 bull_btc 에피소드 끝 <= 180일 이면 '재점등', 아니면 '신규'
                   (데이터 첫 에피소드는 신규)
  C BTC 낙폭       진입일 BTC 종가 / 직전 365봉 최고 종가 − 1.   버킷: >−10% / −10~−30% / <−30%
'에피소드가 언제 끝나는지'는 못 쓴다(룩어헤드).

## 셀 (v3 에서 bull_btc 셀이 살았거나 근접 탈락한 5개, 전부 top30 롱 방식D)

  double_bottom_1d(v3 CONFIRMED) · ma180_decisive · triple_bottom_1d · inverse_hs_1d · three_soldiers_4h

## 1단계 — 진단만 (arm 없음)

셀 × 변수 × 버킷의 n / mean / 승률. 2단계로 가는 규칙(사전 등록):
  ordered 변수(A, C): 5셀 중 >=3 에서 최악 버킷 mean < 0 **이고** 최선 버킷 mean > 0 이며, 최악 버킷의 위치가
                      >=3 셀에서 같다(같은 버킷이어야 규칙이 된다).
  binary 변수(B):     5셀 중 >=4 에서 재점등 mean < 신규 mean **이고** >=3 에서 재점등 mean < 0.
규칙을 만족한 변수만 2단계. 만족한 게 없으면 여기서 끝(기각 기록).

## 2단계 — 필터 arm (1단계 규칙이 정한 버킷을 기계적으로 제외)

  F_V = 'V 의 최악 버킷(1단계가 정한 것) 신호 제외'. 셀별로 D(무필터) 와 D+F 를 비교:
  ① 제외된 부분집합의 mean < 0                     (걸러낸 게 실제로 손실이어야 한다 — method_b 기준 ①)
  ② D+F 가 frame_v3 로 CONFIRMED                   (베이스라인 풀도 **같은 필터를 적용**해 '그 국면이 좋아서' 를 배제)
  ③ D+F 의 train Calmar >= D 의 train Calmar
셋 다 만족한 셀만 ADOPT_CANDIDATE. **실거래 반영 없음 — 보고 후 사용자 결정.**

## 편향 주의

이 시험은 결과를 본 뒤 조건을 붙이는 형태라 사후 선택 위험이 크다. 변수 3개·버킷 고정·진입 규칙 고정으로
못 박고, 여기 없는 변수·버킷은 보지 않는다. 2017~22 는 생존 편향(오늘의 top30).

실행: python validate_phase.py [--no-fetch]
출력: _phase.json
"""
import json
import statistics as st
import sys
import time
from datetime import date

import detector_ma180_breakout as dm
import frame_v3 as fv
import regime_switch as rs
import validate_regime_split_all as va
import validate_revival as vr
from validate_regime_split import turnover_rank

G = "bull_btc"
COHORT = "top30"
DIRECTION = "long"
AGE_CUTS = (90, 270)                 # A: <=90 / 91~270 / >270
REIG_GAP = 180                       # B: 직전 bull 끝과의 간격 <= 180일 → 재점등
DD_CUTS = (-0.10, -0.30)             # C: >-10% / -10~-30% / <-30%
DD_LB = 365
CELLS = [  # (cid, tf, detect_fn 이름) — detect_fn 은 _table() 에서
    ("double_bottom_1d", "1d"), ("ma180_decisive", "1d"), ("triple_bottom_1d", "1d"),
    ("inverse_hs_1d", "1d"), ("three_soldiers_4h", "4h"),
]
VARS = ("A_age", "B_reig", "C_dd")
BUCKETS = {"A_age": ["<=90d", "91~270d", ">270d"], "B_reig": ["신규", "재점등"], "C_dd": [">-10%", "-10~-30%", "<-30%"]}
MIN_BUCKET_N = 5
STAGE2_MIN_CELLS_ORDERED = 3
STAGE2_MIN_CELLS_BINARY = 4
STAGE2_MIN_CELLS_NEG = 3


def _ord(d):
    return date.fromisoformat(d).toordinal()


# ── 특성 ─────────────────────────────────────────────────────────────────────
class Features:
    def __init__(self, regmap, btc_rows):
        self.eps = fv.episodes(regmap, G)
        self._starts = [_ord(a) for a, _ in self.eps]
        self._ends = [_ord(b) for _, b in self.eps]
        # BTC 낙폭: 직전 DD_LB 봉 최고 종가 대비 (당일 포함, 인과)
        cl = [r["c"] for r in btc_rows]
        self.dd = {}
        for i, r in enumerate(btc_rows):
            hi = max(cl[max(0, i - DD_LB + 1):i + 1])
            self.dd[r["date"]] = cl[i] / hi - 1 if hi > 0 else None

    def ep_index(self, d):
        o = _ord(d)
        for k, (s, e) in enumerate(zip(self._starts, self._ends)):
            if s <= o <= e:
                return k
        return None

    def age(self, d):
        k = self.ep_index(d)
        return None if k is None else _ord(d) - self._starts[k]

    def reignition(self, d):
        k = self.ep_index(d)
        if k is None:
            return None
        if k == 0:
            return False
        return (self._starts[k] - self._ends[k - 1]) <= REIG_GAP

    def drawdown(self, d):
        return self.dd.get(d)

    def bucket(self, var, d):
        if var == "A_age":
            a = self.age(d)
            if a is None: return None
            return "<=90d" if a <= AGE_CUTS[0] else ("91~270d" if a <= AGE_CUTS[1] else ">270d")
        if var == "B_reig":
            r = self.reignition(d)
            return None if r is None else ("재점등" if r else "신규")
        if var == "C_dd":
            x = self.drawdown(d)
            if x is None: return None
            return ">-10%" if x > DD_CUTS[0] else ("-10~-30%" if x > DD_CUTS[1] else "<-30%")
        raise ValueError(var)


# ── 1단계 표·규칙 ───────────────────────────────────────────────────────────────
def bucket_table(sigs, feats, var):
    tab = {}
    for b in BUCKETS[var]:
        rs_ = [s["ret"] for s in sigs if feats.bucket(var, s["date"]) == b]
        tab[b] = dict(n=len(rs_), mean=(st.mean(rs_) if rs_ else None), win=(sum(1 for r in rs_ if r > 0) / len(rs_) if rs_ else None),
                      median=(st.median(rs_) if rs_ else None))
    return tab


def stage1_rule(tables_by_cell, var):
    """tables_by_cell: {cid: bucket_table}. 반환 (ok, worst_bucket|None, detail)."""
    bs = BUCKETS[var]
    if var == "B_reig":
        lower = sum(1 for t in tables_by_cell.values()
                    if t["재점등"]["n"] >= MIN_BUCKET_N and t["신규"]["n"] >= MIN_BUCKET_N and t["재점등"]["mean"] < t["신규"]["mean"])
        neg = sum(1 for t in tables_by_cell.values() if t["재점등"]["n"] >= MIN_BUCKET_N and t["재점등"]["mean"] < 0)
        ok = lower >= STAGE2_MIN_CELLS_BINARY and neg >= STAGE2_MIN_CELLS_NEG
        return ok, ("재점등" if ok else None), dict(lower=lower, neg=neg)
    worst_pos, both = [], 0
    for t in tables_by_cell.values():
        valid = [b for b in bs if t[b]["n"] >= MIN_BUCKET_N]
        if len(valid) < 2:
            continue
        w = min(valid, key=lambda b: t[b]["mean"]); bst = max(valid, key=lambda b: t[b]["mean"])
        if t[w]["mean"] < 0 and t[bst]["mean"] > 0:
            both += 1; worst_pos.append(w)
    if both < STAGE2_MIN_CELLS_ORDERED:
        return False, None, dict(both=both, worst=worst_pos)
    top = max(set(worst_pos), key=worst_pos.count)
    same = worst_pos.count(top)
    ok = same >= STAGE2_MIN_CELLS_ORDERED
    return ok, (top if ok else None), dict(both=both, worst=worst_pos, same=same)


# ── 데이터·수집 ──────────────────────────────────────────────────────────────────
def _table():
    t = vr._pattern_table()
    t["ma180_decisive"] = ("1d", (lambda rows: dm.detect(rows, ma_n=180, filt="decisive")), "long")
    return t


def pool_with_dates(tf, idx, rows_by, atrs, regmap):
    out = []
    for s, i in idx:
        rows = rows_by[s]
        lab = lambda j, rows=rows: regmap.get(rows[j]["date"])
        r = vr.live_outcome(tf, rows, i, DIRECTION, lab, atrs.get(s))
        if r is not None:
            out.append((rows[i]["date"], r[0]))
    return out


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    syms = va._syms()
    tfs = sorted({tf for _, tf in CELLS})
    print(f"국면 위치 진단 | 셀 {[c for c, _ in CELLS]} | 레짐 {G} | 코호트 {COHORT} | 변수 A(<=90/270) B(재점등 {REIG_GAP}d) C(낙폭 {DD_CUTS})")
    if "--no-fetch" not in argv:
        va.fetch(syms, tfs)
    rows_1d = va.load_tf(syms, "1d", long=True)
    regmap = rs.build_regime_map(rows_by=rows_1d)
    feats = Features(regmap, rows_1d[rs.MARKET])
    print(f"[에피소드 {G}] {len(feats.eps)}개: " + ", ".join(f"{a}~{b}" for a, b in feats.eps))
    ranked = turnover_rank(rows_1d)
    table = _table()
    ctx = {}
    results = {}
    for cid, tf in CELLS:
        if tf not in ctx:
            rows_by = rows_1d if tf == "1d" else va.load_tf(syms, tf)
            cohorts = {COHORT: set(s for s in ranked[:30] if s in rows_by)}
            pools, atrs = vr.build_context(tf, rows_by, cohorts, regmap)
            t0 = time.time()
            pr = pool_with_dates(tf, pools[(COHORT, G)], rows_by, atrs, regmap)
            print(f"  [pool] {tf} {COHORT}:{G} {len(pr)}건 ({time.time()-t0:.0f}s)", flush=True)
            ctx[tf] = dict(rows_by=rows_by, cohorts=cohorts, atrs=atrs, pool=pr)
        c = ctx[tf]
        _, det, _ = table[cid]
        by_sym = vr.collect(tf, det, DIRECTION, {s: c["rows_by"][s] for s in c["cohorts"][COHORT]}, c["atrs"], regmap)
        sigs = [x for v in by_sym.values() for x in v if x["regime"] == G]
        tabs = {v: bucket_table(sigs, feats, v) for v in VARS}
        print(f"\n[{cid} @{tf}] n={len(sigs)} mean={vr._f(st.mean(s['ret'] for s in sigs) if sigs else None)}")
        for v in VARS:
            print("  " + v + "  " + " | ".join(f"{b}: n={t['n']:>4} {vr._f(t['mean'])} 승률 {(t['win'] or 0)*100:3.0f}%" for b, t in tabs[v].items()))
        results[cid] = dict(tf=tf, n=len(sigs), tables=tabs, sigs=sigs)

    # 1단계 규칙
    stage1 = {}
    print("\n[1단계 규칙]")
    for v in VARS:
        ok, worst, detail = stage1_rule({cid: results[cid]["tables"] for cid in results}, v)
        stage1[v] = dict(ok=ok, worst=worst, detail=detail)
        print(f"  {v}: {'→ 2단계' if ok else '탈락'} 최악 버킷={worst} {detail}")
    go = [v for v in VARS if stage1[v]["ok"]]

    # 2단계
    stage2 = {}
    if not go:
        print("\n[2단계] 진입 변수 없음 — 종료(기각 기록)")
    for v in go:
        worst = stage1[v]["worst"]
        print(f"\n[2단계 F_{v}: '{worst}' 제외]")
        stage2[v] = {}
        for cid, tf in CELLS:
            r = results[cid]; c = ctx[tf]
            keep = [s for s in r["sigs"] if feats.bucket(v, s["date"]) != worst]
            drop = [s for s in r["sigs"] if feats.bucket(v, s["date"]) == worst]
            pool_all = [ret for _, ret in c["pool"]]
            pool_keep = [ret for d, ret in c["pool"] if feats.bucket(v, d) != worst]
            eq = lambda tr, span: vr.equity(tr, span)
            j_d = fv.judge(r["sigs"], pool_all, regmap, G, eq)
            j_f = fv.judge(keep, pool_keep, regmap, G, eq)
            drop_mean = st.mean(s["ret"] for s in drop) if drop else None
            cal_d = (j_d["equity"] or {}).get("calmar", 0.0); cal_f = (j_f["equity"] or {}).get("calmar", 0.0)
            c1 = drop_mean is not None and drop_mean < 0
            c2 = j_f["verdict"] == "CONFIRMED"
            c3 = cal_f >= cal_d
            verdict = "ADOPT_CANDIDATE" if (c1 and c2 and c3) else "NOT_ADOPTED"
            print(f"  {cid:<20} D {j_d['verdict']:<12} Calmar {cal_d:5.2f} | D+F n={len(keep)} {j_f['verdict']:<12} Calmar {cal_f:5.2f} "
                  f"| 제외 n={len(drop)} mean={vr._f(drop_mean)} | ①{c1} ②{c2} ③{c3} → {verdict}")
            stage2[v][cid] = dict(D=dict(verdict=j_d["verdict"], calmar=cal_d, n=len(r["sigs"]), holdout=j_d["holdout"]),
                                  F=dict(verdict=j_f["verdict"], calmar=cal_f, n=len(keep), holdout=j_f["holdout"], c1=j_f["c1"], E=j_f["E"]),
                                  dropped=dict(n=len(drop), mean=drop_mean), crit=dict(c1=c1, c2=c2, c3=c3), verdict=verdict)
    adopt = [(v, cid) for v in stage2 for cid, x in stage2[v].items() if x["verdict"] == "ADOPT_CANDIDATE"]
    print("\n" + "=" * 100)
    print(f"[요약] 1단계 통과 변수 {go} | 2단계 ADOPT_CANDIDATE {adopt if adopt else '없음'} | 실거래 반영 없음(사용자 결정)")
    out = dict(cells=[c for c, _ in CELLS], regime=G, cohort=COHORT, episodes=feats.eps, stage1=stage1,
               tables={cid: results[cid]["tables"] for cid in results}, stage2=stage2, adopt=adopt)
    json.dump(out, open("_phase.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print("[저장] _phase.json")
    print("RESULT_JSON: " + json.dumps(dict(stage1=go, adopt=adopt), ensure_ascii=False))


if __name__ == "__main__":
    main()
