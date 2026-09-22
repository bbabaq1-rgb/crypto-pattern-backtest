"""
test_altseason_fast.py — 저지속성 판의 성질 고정.

가장 중요한 것 둘:
  §1 **level 판과 같은 프레임인가** — 타깃·귀무·판정을 import 로 공유해야 두 판이 비교 가능하다.
  §2 **인과성과 구성 정의** — accel/pctile/roc 가 미래를 안 보고 정의대로 계산되는가.
실행: python test_altseason_fast.py
"""
import math
import random
import statistics as st
import sys

import validate_altseason as V
import validate_altseason_fast as F

FAIL = []


def chk(name, cond, extra=""):
    if cond:
        print(f"  ✓ {name}")
    else:
        FAIL.append(name)
        print(f"  ✗ {name} {extra}")


# ── §1 프레임 공유 ────────────────────────────────────────────────────────
print("\n§1 level 판과 같은 프레임 — 바뀐 것은 지표 구성뿐이어야 한다")
for fn in ("spearman", "rotation_null", "mde", "pval", "pval_two", "holm",
           "tercile_stats", "judge", "target_at", "build_series", "load_all"):
    chk(f"{fn} 을 level 판에서 그대로 쓴다", getattr(F.V, fn) is getattr(V, fn))
chk("판정 문턱을 재정의하지 않는다", not hasattr(F, "IC1") and not hasattr(F, "IC2"))
chk("지평·분할·시작일을 재정의하지 않는다",
    not any(hasattr(F, k) for k in ("HORIZON", "SPLIT", "START", "MIN_SHIFT")))
chk("Holm 가족 크기 10 = 주 판정 셀 수",
    F.M_HOLM == 10 == sum(1 for *_, is_main in F.cells() if is_main))


# ── §2 구성 정의 ──────────────────────────────────────────────────────────
print("\n§2 구성 — roc / accel / pctile")
xs = [100.0 * (1.02 ** i) for i in range(100)]          # 봉당 +2% 등비
r = F.roc(xs, 10, "px")
chk("roc(px) = 비율 변화", all(v is None for v in r[:10])
    and abs(r[50] - (1.02 ** 10 - 1)) < 1e-12)
lv = [float(i) for i in range(100)]
chk("roc(lvl) = 차이", abs(F.roc(lv, 10, "lvl")[50] - 10.0) < 1e-12)
chk("roc 는 lb 이전 구간이 None", F.roc(lv, 10, "lvl")[9] is None)
chk("분모 0 이면 None", F.roc([0.0] + [1.0] * 50, 1, "px")[1] is None)

a = F.accel(xs, 10, "px")
chk("등비 계열의 가속은 0 (roc 가 상수)", abs(a[60]) < 1e-12, f"{a[60]}")
chk("accel 은 2*lb 이전이 None", a[2 * 10 - 1] is None and a[2 * 10] is not None)
quad = [float(i * i) for i in range(100)]
chk("2차 계열은 가속이 양수 상수", abs(F.accel(quad, 10, "lvl")[60] - 200.0) < 1e-9)

p = F.pctile(lv, 50)
chk("단조 증가 계열의 백분위는 최대에 붙는다", p[80] is not None and p[80] > 0.98)
chk("백분위는 창의 절반이 안 차면 None", p[10] is None)
flat = [5.0] * 100
chk("전부 동률이면 백분위 0.5", abs(F.pctile(flat, 50)[80] - 0.5) < 1e-12)
chk("백분위는 [0,1] 안", all(0.0 <= v <= 1.0 for v in F.pctile(lv, 50) if v is not None))
osc = [math.sin(i / 7.0) for i in range(600)]
chk("이동 창이라 수준의 단조변환이 아니다 — 같은 값이 다른 백분위",
    len({round(v, 3) for v in F.pctile([math.sin(i / 7.0) + i * 0.01 for i in range(600)], 250)
         if v is not None}) > 5)


# ── §3 인과성 ─────────────────────────────────────────────────────────────
print("\n§3 인과성 — 미래를 조작해도 과거 값 불변")
rnd = random.Random(3)
base = [100.0]
for _ in range(599):
    base.append(base[-1] * math.exp(rnd.gauss(0, 0.02)))
cut = 400
tamper = base[:cut + 1] + [v * 5 for v in base[cut + 1:]]
for name, fn in (("roc", lambda z: F.roc(z, F.LB, "px")),
                 ("accel", lambda z: F.accel(z, F.LB, "px")),
                 ("pctile", lambda z: F.pctile(z, F.PCT_WIN))):
    o, t = fn(base), fn(tamper)
    bad = [i for i in range(F.PCT_WIN, cut + 1)
           if (o[i] is None) != (t[i] is None)
           or (o[i] is not None and abs(o[i] - t[i]) > 1e-12)]
    chk(f"{name} 은 t 까지만 본다", not bad, f"불일치 {bad[:3]}")


# ── §4 지속성 측정 — 이 판의 전제 ─────────────────────────────────────────
print("\n§4 자기상관 — 차분·백분위가 정말 덜 지속적인가(전제 확인)")
walk = [0.0]
for _ in range(2000):
    walk.append(walk[-1] + random.Random(len(walk)).gauss(0, 1))
ac_lvl = F.autocorr(walk, V.HORIZON)
ac_acc = F.autocorr(F.accel(walk, F.LB, "lvl"), V.HORIZON)
ac_pct = F.autocorr(F.pctile(walk, F.PCT_WIN), V.HORIZON)
chk(f"랜덤워크 수준은 lag120 자기상관이 높다 ({ac_lvl:.3f} > 0.5)", ac_lvl > 0.5)
chk(f"가속은 훨씬 낮다 ({ac_acc:.3f} < {ac_lvl:.3f})", abs(ac_acc) < ac_lvl)
chk(f"백분위도 수준보다 낮다 ({ac_pct:.3f} < {ac_lvl:.3f})", abs(ac_pct) < ac_lvl)
chk("autocorr 은 표본이 적으면 None", F.autocorr([1.0] * 30, 120) is None)
chk("상수 계열은 None(분모 0)", F.autocorr([2.0] * 500, 120) is None)


# ── §5 셀 구성 ────────────────────────────────────────────────────────────
print("\n§5 셀 구성·부호")
cl = F.cells()
keys = [c[0] for c in cl]
chk("키 중복 없음", len(keys) == len(set(keys)))
chk("주 판정 10 = 기반 5 x 구성 2", sum(1 for c in cl if c[4]) == 10)
chk("주 판정은 accel/pctile 뿐",
    {k.rsplit("_", 1)[1] for k, *_, m in cl if m} == {"accel", "pctile"})
chk("roc 5셀은 전부 진단(판정 아님)",
    all(not m for k, *_, m in cl if k.endswith("_roc"))
    and sum(1 for k, *_ in cl if k.endswith("_roc")) == 5)
chk("음성 대조 3", sum(1 for c in cl if c[3]) == 3)
chk("대조 2개 초과 통과 시 INVALID (즉 2 이상)", F.MAX_CTRL_PASS == 1)
chk("분산만 음의 부호", [k for k, _, s, c, m in cl if s < 0 and m]
    == ["disp_accel", "disp_pctile"])
chk("부호는 level 판과 같은 경제 가설",
    F.SIGN == {"ethbtc": 1, "altbtc": 1, "breadth": 1, "btc": 1, "disp": -1})
chk("가격형은 비율·유계형은 차이",
    {k: kind for k, _, kind in F.BASES}
    == {"ethbtc": "px", "altbtc": "px", "breadth": "lvl", "btc": "px", "disp": "lvl"})
chk("level 비교 대응표가 5 계열 전부", set(F.LEVEL_REF) == {k for k, _, _ in F.BASES})
chk("대응 키가 level 판에 실재",
    set(F.LEVEL_REF.values()) <= {k for k, _, _ in V.FEATURES})


# ── §6 판정은 level 판 함수 그대로 ────────────────────────────────────────
print("\n§6 판정 — V.judge 를 그대로 호출한다")


def row(ic_tr, p_holm, ic_ho, p_ho, sign=+1, mde=0.10, t_tr=(0.2, 0.1), t_ho=(0.2, 0.1)):
    def leg(ic, p, terc, extra):
        dd = dict(n=999, ic=ic, p=p, p_two=0.5, mde=mde,
                  terc=dict(top_mean=terc[0], all_mean=terc[1], n_top=100, side="high"))
        dd.update(extra)
        return dd
    return dict(key="x", label="x", sign=sign, is_control=False, is_main=True,
                train=leg(ic_tr, p_holm, t_tr, dict(p_holm=p_holm)),
                holdout=leg(ic_ho, p_ho, t_ho, {}))


chk("전 기준 통과 → CONFIRMED", V.judge(row(0.30, 0.01, 0.20, 0.01))[0] == "CONFIRMED")
chk("|IC| 문턱 0.20 은 level 판 값", V.judge(row(0.19, 0.01, 0.20, 0.01))[0] == "REJECTED")
chk("holdout 선호3분위 음수면 탈락 — **이 판의 실질 관문**",
    V.judge(row(0.30, 0.01, 0.20, 0.01, t_ho=(-0.05, -0.22)))[0] == "REJECTED")
chk("기저보다 나아도 절대 음수면 통과 아님(기록: D2 가 그 정보를 따로 남긴다)",
    V.judge(row(0.30, 0.01, 0.20, 0.01, t_ho=(-0.10, -0.22)))[0] == "REJECTED")
chk("검정력 부족은 INCONCLUSIVE", V.judge(row(0.30, 0.40, 0.20, 0.01, mde=0.45))[0] == "INCONCLUSIVE")
chk("음의 부호 셀도 같은 규칙", V.judge(row(-0.30, 0.01, -0.20, 0.01, sign=-1))[0] == "CONFIRMED")


# ── §6b 모양 계약 — D1 이 두 모듈의 지표 자료구조를 섞지 않는가
print("\n§6b 자료구조 — features_at(인덱스별 dict 목록) vs 이 모듈({키: 계열})")
lvl_rows = V.features_at(V.build_series(
    {s: {f"2020-01-{d:02d}": 100.0 + d for d in range(1, 29)} for s in ("btc", "eth", "a1")}))
chk("level 판 features_at 은 목록의 각 원소가 dict",
    isinstance(lvl_rows, list) and isinstance(lvl_rows[0], dict))
flip = {k: [r.get(k) for r in lvl_rows] for k in F.LEVEL_REF.values()}
chk("뒤집으면 {키: 계열} — measure() 가 기대하는 모양",
    all(isinstance(v, list) and len(v) == len(lvl_rows) for v in flip.values()))
chk("이 모듈 build() 도 {키: 계열}", all(
    isinstance(v, list) for v in
    F.build({k: [1.0] * 400 for k, _, _ in F.BASES}).values()))
chk("measure 는 feats[key][i] 로 접근한다(모양 계약)",
    "feats[key][i]" in open("validate_altseason_fast.py").read())
chk("D1 이 dict 인덱싱(lvl[i].get)을 쓰지 않는다",
    "lvl[i].get" not in open("validate_altseason_fast.py").read())


# ── §7 동결 상수 ──────────────────────────────────────────────────────────
print("\n§7 동결 상수")
chk("LB = 20 (level 판 저MDE 셀과 같은 창)", F.LB == 20)
chk("백분위 창 250", F.PCT_WIN == 250)
chk("DEPLOY_ON_PASS = False", F.DEPLOY_ON_PASS is False)
chk("시드는 level 판과 공유", F.V.SEED == 20260922)
# 주석이 아니라 **코드**에 hash( 가 없는지 본다 (설명 주석에는 그 단어가 들어 있다)
code = "\n".join(ln.split("#")[0] for ln in
                 open("validate_altseason_fast.py").read().splitlines())
chk("D1 시드가 인덱스 기반 — 코드에 hash( 없음 (PYTHONHASHSEED 재현성)",
    "hash(" not in code)
chk("시드가 실제로 루프 인덱스에서 나온다", "V.SEED + 900 + bi" in code)

print("\n" + "=" * 60)
print(f"실패 {len(FAIL)}건" + ("" if not FAIL else ": " + ", ".join(FAIL)))
sys.exit(1 if FAIL else 0)
