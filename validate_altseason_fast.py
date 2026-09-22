"""
validate_altseason_fast.py — 알트 시즌 선행 지표 **저지속성(차분·백분위) 판**
(2026-09-22, 사용자 지시 "차분형·저지속성 지표 사전 등록(비용 0)을 지금 설계").

■ 왜 이 판인가
  검정력 곡선(registry altseason_power_curve_2026_09_22)이 **병목은 예산이 아니라 지표의
  지속성**이라고 답했다. 전체 표본 지표별 MDE 가 breadth_chg20 0.136 ~ altbtc_dist200 0.326 으로
  2.4배 벌어지고, p=0.378 에서 그 차이는 **데이터 10.2배**에 해당한다. 10배는 못 사지만
  (80년치) 지표 선택은 0원이다. **유료 데이터 결제 전에 공짜 레버를 먼저 쓴다.**

■ 무엇을 바꾸고 무엇을 고정하나
  **타깃·데이터·분할·회전 검정 귀무·MDE·판정 규칙은 level 판(validate_altseason)을 그대로
  import 한다** — 바뀌는 것은 지표 구성 하나뿐이다. 그래야 두 판이 사과 대 사과가 된다.
  judge() 도 같은 함수를 호출한다(문턱 IC1 0.20 / IC2 0.15 불변).

■ 지표 — 같은 경제적 아이디어, 낮은 지속성 구성
  기반 계열 5 (level 판과 동일한 재료): ETH/BTC · OTHERS/BTC · 폭 · BTC · 60일 횡단면 분산
  구성 2 (주 판정):
    · **accel** 가속 = (20일 변화) − (20일 전의 20일 변화). 2차 차분이라 지속성이 가장 낮다.
    · **pctile** 250일 백분위. 유계라 장기 자기상관이 빨리 죽지만 **수준 정보는 남는다**
      (이동 창이라 수준의 단조변환이 아니다 — 같은 값도 시대에 따라 90분위·10분위가 된다).
  5 x 2 = **10 주 판정 셀**, Holm m=10 (level 판과 같은 가족 크기).
  가격형(ETH/BTC·OTHERS/BTC·BTC)은 비율 변화, 유계·척도제한형(폭·분산)은 **차이**로 계산한다.

■ 음성 대조 3 — 같은 구성을 잡음에 적용
  ctrl_ar1_accel / ctrl_ar1_pctile / ctrl_season_accel. **2개 이상이 C1(무보정) 통과 시 판 INVALID.**
  차분하면 대조도 지속성이 낮아지므로 '저지속성이라 통과했다'를 이 셋이 잡는다.

■ 진단(판정 아님, 사후 선택 금지)
  D1 **MDE 가 실제로 내려갔나** — 같은 계열의 level 판 MDE 와 나란히. 검정력 곡선의 약속이
     실현되는지 자체가 검증 대상이다(자기상관 lag120 도 병기 — 기전).
  D2 **상대 엣지 대안 기준** — C3 의 절대 문턱(holdout 선호 3분위 > 0)이 막혔을 때 정보 보존용.
  D3 roc20(1차 차분) 5셀 — breadth_chg20 이 속한 가족. **breadth 는 level 판에서 이미 주 판정으로
     기각됐으므로 여기서는 전부 진단이다**(재판정 아님).

■ DEPLOY_ON_PASS = False — 통과해도 실거래 반영 없음. 예측력 확인과 매매 규칙은 별개 명제다.

실행: python validate_altseason_fast.py
"""
import json
import math
import random
import statistics as st

import validate_altseason as V

OUT = "_altseason_fast.json"

# ── 동결 상수 (2026-09-22, 결과 보기 전) ──────────────────────────────────
LB = 20            # roc/accel 창 — level 판의 breadth_chg20·ethbtc_slope20 과 같은 20일
PCT_WIN = 250      # 백분위 창 (약 1년)
M_HOLM = 10        # 주 판정 10셀
DEPLOY_ON_PASS = False
MAX_CTRL_PASS = 1  # 대조가 이 수를 넘겨 통과하면 판 INVALID (즉 2 이상)

# 기반 계열: (키, 표시, kind) — kind 'px' 는 비율 변화, 'lvl' 은 차이
BASES = [
    ("ethbtc", "ETH/BTC",            "px"),
    ("altbtc", "OTHERS/BTC",         "px"),
    ("breadth", "MA180 위 코인 비율", "lvl"),
    ("btc",    "BTC",                "px"),
    ("disp",   "60일 횡단면 분산",    "lvl"),
]
# 선언 부호 — level 판과 같은 경제 가설 (분산만 음수)
SIGN = {"ethbtc": +1, "altbtc": +1, "breadth": +1, "btc": +1, "disp": -1}
MAIN_KINDS = ["accel", "pctile"]   # 주 판정 구성
DIAG_KINDS = ["roc"]               # 진단 구성

# 비교용 level 판 대응 지표 (D1 — 판정 아님)
LEVEL_REF = {"ethbtc": "ethbtc_dist200", "altbtc": "altbtc_dist200",
             "breadth": "breadth180", "btc": "btc_dist200", "disp": "disp60"}


# ── 구성 ──────────────────────────────────────────────────────────────────
def roc(xs, lb, kind):
    """kind 'px' → xs[i]/xs[i-lb]-1, 'lvl' → xs[i]-xs[i-lb]. 결측·0 은 None."""
    out = [None] * len(xs)
    for i in range(lb, len(xs)):
        a, b = xs[i], xs[i - lb]
        if a is None or b is None:
            continue
        if kind == "px":
            if b == 0:
                continue
            out[i] = a / b - 1
        else:
            out[i] = a - b
    return out


def accel(xs, lb, kind):
    """2차 차분 — roc(i) − roc(i−lb). 지속성이 가장 낮은 구성."""
    r = roc(xs, lb, kind)
    out = [None] * len(xs)
    for i in range(2 * lb, len(xs)):
        if r[i] is not None and r[i - lb] is not None:
            out[i] = r[i] - r[i - lb]
    return out


def pctile(xs, win):
    """직전 win 봉 안에서의 백분위(동률은 절반). 유계라 장기 자기상관이 빨리 죽는다."""
    out = [None] * len(xs)
    for i in range(len(xs)):
        if xs[i] is None:
            continue
        hist = [v for v in xs[max(0, i - win + 1):i + 1] if v is not None]
        if len(hist) < win // 2:
            continue
        less = sum(1 for v in hist if v < xs[i])
        eq = sum(1 for v in hist if v == xs[i])
        out[i] = (less + 0.5 * eq) / len(hist)
    return out


def build(series):
    """기반 계열 dict -> {cell_key: 계열}. 주 판정 + 진단 구성 전부."""
    feats = {}
    for key, _, kind in BASES:
        xs = series[key]
        feats[f"{key}_accel"] = accel(xs, LB, kind)
        feats[f"{key}_pctile"] = pctile(xs, PCT_WIN)
        feats[f"{key}_roc"] = roc(xs, LB, kind)
    return feats


def autocorr(xs, lag):
    """lag 자기상관(피어슨). 지속성의 직접 측정 — MDE 와의 연결 기전."""
    pair = [(xs[i - lag], xs[i]) for i in range(lag, len(xs))
            if xs[i] is not None and xs[i - lag] is not None]
    if len(pair) < 50:
        return None
    a = [p[0] for p in pair]
    b = [p[1] for p in pair]
    ma, mb = st.mean(a), st.mean(b)
    num = sum((x - ma) * (y - mb) for x, y in pair)
    da = math.sqrt(sum((x - ma) ** 2 for x in a))
    db = math.sqrt(sum((y - mb) ** 2 for y in b))
    return None if da == 0 or db == 0 else num / (da * db)


def controls(n, seed=V.SEED):
    """잡음 계열에 같은 구성을 적용한 대조."""
    rnd = random.Random(seed)
    ar = [0.0] * n
    for i in range(1, n):
        ar[i] = 0.99 * ar[i - 1] + rnd.gauss(0, 1)
    season = [math.sin(2 * math.pi * i / 365.25) for i in range(n)]
    return {
        "ctrl_ar1_accel": accel(ar, LB, "lvl"),
        "ctrl_ar1_pctile": pctile(ar, PCT_WIN),
        "ctrl_season_accel": accel(season, LB, "lvl"),
    }


# ── 분석 ──────────────────────────────────────────────────────────────────
def cells():
    """(키, 표시, 부호, is_control, is_main) 목록 — 순서 고정."""
    out = []
    for key, label, _ in BASES:
        for k in MAIN_KINDS:
            out.append((f"{key}_{k}", f"{label} {k}", SIGN[key], False, True))
    for key, label, _ in BASES:
        for k in DIAG_KINDS:
            out.append((f"{key}_{k}", f"{label} {k}", SIGN[key], False, False))
    for k in ("ctrl_ar1_accel", "ctrl_ar1_pctile", "ctrl_season_accel"):
        out.append((k, f"음성대조 {k[5:]}", +1, True, False))
    return out


def measure(idxs, feats, tgt, key, sign, seed):
    sub = [i for i in idxs if feats[key][i] is not None]
    if len(sub) < 2 * V.MIN_SHIFT + 3:
        return None
    fv = [feats[key][i] for i in sub]
    tv = [tgt[i] for i in sub]
    ic = V.spearman(fv, tv)
    nulls = V.rotation_null(fv, tv, seed=seed)
    return dict(n=len(sub), ic=ic, p=V.pval(ic, nulls, sign), p_two=V.pval_two(ic, nulls),
                mde=V.mde(nulls, sign), terc=V.tercile_stats(fv, tv, sign))


def main():
    print("=" * 108)
    print("알트 시즌 선행 지표 — **저지속성(차분·백분위) 판** (registry altseason_fast_prereg_2026_09_22)")
    print(f"타깃·데이터·분할·귀무·판정 전부 level 판 그대로 import · 바뀐 것은 지표 구성뿐 "
          f"· LB {LB} · 백분위창 {PCT_WIN} · Holm m={M_HOLM}")
    print("=" * 108)

    S = V.build_series(V.load_all())
    tgt, _ = V.target_at(S)
    series = dict(ethbtc=S["ethbtc"], altbtc=S["altbtc"], breadth=S["breadth"],
                  btc=S["btc_c"], disp=S["disp"])
    feats = build(series)
    feats.update(controls(len(S["dates"])))
    # D1 비교용 level 판 지표 — features_at 은 **인덱스별 dict 목록**을 주므로
    # 이 모듈의 {키: 계열} 모양으로 뒤집어야 measure() 가 그대로 쓸 수 있다.
    lvl_rows = V.features_at(S)
    lvl = {k: [r.get(k) for r in lvl_rows] for k in set(LEVEL_REF.values())}

    d = S["dates"]
    keep = [i for i in range(len(d))
            if tgt[i] is not None and d[i] >= V.START and S["univ_n"][i] >= V.MIN_UNIVERSE]
    tr = [i for i in keep if d[i] < V.SPLIT]
    ho = [i for i in keep if d[i] >= V.SPLIT]
    base_tr = st.mean([tgt[i] for i in tr])
    base_ho = st.mean([tgt[i] for i in ho])
    print(f"[표본] 라벨 {len(keep)}일 — train {len(tr)} / holdout {len(ho)} "
          f"(비중첩 120일 창 {len(tr)/V.HORIZON:.1f} / {len(ho)/V.HORIZON:.1f})")
    print(f"[기저] 무조건부 120일 알트 초과수익 train {base_tr*100:+.1f}% / holdout {base_ho*100:+.1f}%")

    rows = []
    for k, (key, label, sign, is_ctrl, is_main) in enumerate(cells()):
        r = dict(key=key, label=label, sign=sign, is_control=is_ctrl, is_main=is_main,
                 ac120=autocorr(feats[key], V.HORIZON),
                 train=measure(tr, feats, tgt, key, sign, V.SEED + k),
                 holdout=measure(ho, feats, tgt, key, sign, V.SEED + 500 + k))
        rows.append(r)

    hp = V.holm([(r["key"], r["train"]["p"]) for r in rows if r["is_main"] and r["train"]],
                m=M_HOLM)
    for r in rows:
        if r["train"]:
            r["train"]["p_holm"] = hp.get(r["key"], r["train"]["p"])
        r["verdict"], r["why"] = V.judge(r)

    # ── 표 ──
    def show(title, sel):
        print("\n" + "-" * 108)
        print(title)
        print(f"{'지표':<28}{'부호':>4}{'ac120':>8}{'IC_tr':>8}{'Holm':>7}{'MDE_tr':>8}"
              f"{'IC_ho':>8}{'p_ho':>7}{'선호3분위(ho)':>14}  판정")
        print("-" * 108)
        for r in sel:
            t, h = r["train"], r["holdout"]
            pcol = (t["p"] if r["is_control"] else t.get("p_holm", t["p"])) if t else None
            terc = h["terc"] if (h and h.get("terc")) else None
            pho = h["p"] if h else None
            print(f"{r['label'][:27]:<28}{('+' if r['sign'] > 0 else '-'):>4}"
                  f"{V.fmt(r['ac120'], 8)}{V.fmt(t['ic'] if t else None, 8)}"
                  f"{(f'{pcol:.3f}' if pcol is not None else '—'):>7}"
                  f"{V.fmt(t['mde'] if t else None, 8)}{V.fmt(h['ic'] if h else None, 8)}"
                  f"{(f'{pho:.3f}' if pho is not None else '—'):>7}"
                  f"{V.fmt(terc['top_mean'] if terc else None, 14, 3, pct=True)}"
                  f"  {r['verdict']}{'  [대조]' if r['is_control'] else ''}")

    show("주 판정 10셀 (accel / pctile)", [r for r in rows if r["is_main"]])
    show("음성 대조 3 — 같은 구성을 잡음에", [r for r in rows if r["is_control"]])
    show("[D3] 진단 roc20 5셀 — 판정 아님, 사후 선택 금지",
         [r for r in rows if not r["is_main"] and not r["is_control"]])

    main_rows = [r for r in rows if r["is_main"]]
    ctrl_pass = [r for r in rows if r["is_control"] and r["train"]
                 and (r["train"]["ic"] * r["sign"]) > 0
                 and abs(r["train"]["ic"]) >= V.IC1 and r["train"]["p"] < V.ALPHA]
    invalid = len(ctrl_pass) > MAX_CTRL_PASS
    conf = [r for r in main_rows if r["verdict"] == "CONFIRMED"]
    inc = [r for r in main_rows if r["verdict"] == "INCONCLUSIVE"]
    rev = [r for r in main_rows if r["verdict"] == "REVERSED"]
    print(f"\n[판정] CONFIRMED {len(conf)} / INCONCLUSIVE {len(inc)} / REVERSED {len(rev)} / "
          f"REJECTED {len(main_rows)-len(conf)-len(inc)-len(rev)}  "
          f"(대조 통과 {len(ctrl_pass)}/3 → {'**INVALID**' if invalid else '판 VALID'})")
    for r in main_rows:
        if r["verdict"] != "REJECTED":
            print(f"   · {r['label']} — {r['verdict']}: {', '.join(r['why']) or '전 기준 통과'}")

    # ── D1: 검정력 곡선의 약속이 실현됐나 ──
    print("\n[D1] MDE 가 실제로 내려갔나 — 같은 계열 level 판 대비 (검정력 곡선의 약속 검증)")
    print(f"   {'계열':<22}{'level MDE':>11}{'accel':>9}{'pctile':>9}{'roc':>9}   "
          f"{'level ac120':>12}{'accel':>8}{'pctile':>8}")
    d1 = []
    for bi, (key, label, _) in enumerate(BASES):
        lk = LEVEL_REF[key]
        # 시드는 **인덱스**로 — hash(str) 은 PYTHONHASHSEED 때문에 실행마다 달라져 재현이 깨진다
        lr = measure(tr, lvl, tgt, lk, SIGN[key], V.SEED + 900 + bi)
        got = {k: next((r for r in rows if r["key"] == f"{key}_{k}"), None)
               for k in ("accel", "pctile", "roc")}
        lac = autocorr(lvl[lk], V.HORIZON)
        line = (f"   {label[:21]:<22}{V.fmt(lr['mde'] if lr else None, 11)}"
                + "".join(V.fmt(got[k]["train"]["mde"] if (got[k] and got[k]["train"]) else None, 9)
                          for k in ("accel", "pctile", "roc"))
                + "   " + V.fmt(lac, 12)
                + "".join(V.fmt(got[k]["ac120"] if got[k] else None, 8)
                          for k in ("accel", "pctile")))
        print(line)
        d1.append(dict(base=key, level_key=lk, level_mde=lr["mde"] if lr else None,
                       level_ac120=lac,
                       **{f"{k}_mde": (got[k]["train"]["mde"] if (got[k] and got[k]["train"]) else None)
                          for k in ("accel", "pctile", "roc")},
                       **{f"{k}_ac120": (got[k]["ac120"] if got[k] else None)
                          for k in ("accel", "pctile")}))

    # ── D2: 절대 문턱이 막혔을 때의 상대 엣지 ──
    print(f"\n[D2] 상대 엣지 — holdout 선호 3분위 − 기저({base_ho*100:+.1f}%). 절대 문턱 대안(진단)")
    for r in sorted([x for x in main_rows if x["holdout"] and x["holdout"].get("terc")],
                    key=lambda x: -(x["holdout"]["terc"]["top_mean"] - base_ho)):
        e = r["holdout"]["terc"]["top_mean"] - base_ho
        print(f"   {r['label'][:30]:<32}{e*100:+7.2f}%p   (절대 {r['holdout']['terc']['top_mean']*100:+.1f}%)")

    res = dict(prereg="altseason_fast_prereg_2026_09_22", lb=LB, pct_win=PCT_WIN,
               horizon=V.HORIZON, split=V.SPLIT, seed=V.SEED, deploy_on_pass=DEPLOY_ON_PASS,
               n_train=len(tr), n_holdout=len(ho), base_train=base_tr, base_holdout=base_ho,
               invalid=invalid, confirmed=[r["key"] for r in conf],
               inconclusive=[r["key"] for r in inc], reversed=[r["key"] for r in rev],
               rows=rows, d1_mde=d1)
    with open(OUT, "w") as f:
        json.dump(res, f, ensure_ascii=False, indent=1, default=str)
    print(f"\n[출력] {OUT}")
    print(f"[반영] DEPLOY_ON_PASS={DEPLOY_ON_PASS} — 실거래 무변경.")
    return res


if __name__ == "__main__":
    main()
