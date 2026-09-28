"""
test_altcap.py — validate_altcap 논리 검증 (네트워크·실데이터 없음, 합성 데이터만).

§1 비대칭 창 계산이 실거래 compute_capture 와 **완전히 같다** — 어긋나면 결과 전부가 무의미.
§2 동결 상수·선언 부호·판정 도구가 validate_altseason 과 같은 객체다.
§3 사건·타깃·특성 계산.
§4 매매 경로와 무관.
"""
import ast
import random
import sys

import validate_altcap as A
import validate_altseason as V
from relative_strength import compute_capture, CAPTURE_N

FAIL = []


def check(name, cond):
    print(("  OK   " if cond else "  FAIL ") + name)
    if not cond:
        FAIL.append(name)


def synth(n, seed, beta=1.5, gaps=False):
    rnd = random.Random(seed)
    btc, alt = {}, {}
    pb, pa = 30000.0, 10.0
    for i in range(n):
        d = f"2024-{1 + i // 28:02d}-{1 + i % 28:02d}" if i < 28 * 12 else f"2025-{1 + (i - 336) // 28:02d}-{1 + (i - 336) % 28:02d}"
        rb = rnd.gauss(0, 0.03)
        ra = beta * rb + rnd.gauss(0, 0.02) + (0.004 if rb < 0 else 0.0)
        pb *= 1 + rb
        pa *= 1 + ra
        btc[d] = pb
        if not (gaps and i % 17 == 5):
            alt[d] = pa
    return alt, btc


# ---------------------------------------------------------------- §1
print("[1] rolling_capture == compute_capture")
for seed, gaps in ((1, False), (2, True), (3, False)):
    alt, btc = synth(420, seed, gaps=gaps)
    roll = A.rolling_capture(alt, btc)
    alt_rows = [{"date": d, "c": alt[d]} for d in sorted(alt)]
    btc_rows = [{"date": d, "c": btc[d]} for d in sorted(btc)]
    mism, n_cmp = 0, 0
    for idx in range(CAPTURE_N + 5, len(alt_rows), 7):
        ref = compute_capture(alt_rows, btc_rows, idx=idx)
        d = alt_rows[idx]["date"]
        if ref["up_capture"] is None:
            mism += d in roll
            continue
        n_cmp += 1
        got = roll.get(d)
        if got is None or abs(got[0] - ref["cap_score"]) > 1e-3 or abs(got[1] - ref["up_capture"]) > 1e-3 \
                or abs(got[2] - ref["down_capture"]) > 1e-3:
            mism += 1
    check(f"시드 {seed} (결측{'O' if gaps else 'X'}) — {n_cmp}개 시점 전부 일치", mism == 0 and n_cmp > 30)
check("BTC 는 계열에서 제외 (build_cap_series 가 'btc' 키를 건너뜀)",
      "if s != \"btc\"" in open("validate_altcap.py").read())

# ---------------------------------------------------------------- §2
print("[2] 동결 상수·부호·도구")
check("지평 20·60", A.HORIZONS == (20, 60))
check("선언 부호 — 사용자 가설 방향", dict((k, s) for k, _, s in A.FEATURES) ==
      {"avg_cap": 1, "avg_cap_chg20": 1, "avg_down_cap": -1, "avg_up_cap": 1, "neg_share": -1})
check("Holm 가족 = 지표 5 x 지평 2", A.M_HOLM == 10)
check("DEPLOY_ON_PASS = False", A.DEPLOY_ON_PASS is False)
src = open("validate_altcap.py").read()
check("판정은 validate_altseason.judge 그대로", "V.judge(r)" in src and "def judge" not in src)
check("귀무는 validate_altseason.rotation_null 그대로", "V.rotation_null(" in src and "def rotation_null" not in src)
check("분할·문턱을 새로 정의하지 않는다", "SPLIT =" not in src and "IC1 =" not in src and "V.SPLIT" in src)
check("비대칭 창·최소 표본은 실거래 상수 그대로 import",
      "from relative_strength import CAPTURE_N, CAP_MIN_DAY, CAP_SCALE" in src)

# ---------------------------------------------------------------- §3
print("[3] 사건·타깃·특성")
ac = [None, 0.2, 0.3, 0.2, 0.1, 0.05, -0.1, -0.3, -0.4, -0.2, -0.1, 0.1, 0.2, 0.3, 0.3, 0.2, -0.5, -0.6, -0.6, -0.6]
ev = A.flip_events(ac, [str(i) for i in range(len(ac))], smooth=3)
check("5일 평균이 양수→음수로 넘는 날만 사건", all(
    sum(ac[i - 2:i + 1]) / 3 <= 0 < sum(ac[i - 3:i]) / 3 for i in ev) and len(ev) == 2)
S = {"dates": ["d0", "d1", "d2"], "alts": ["x", "y", "z", "w", "v", "u", "t", "s", "r", "q", "p"],
     "by": {}, "eligible": lambda s, d: True}
for k, s in enumerate(S["alts"]):
    S["by"][s] = {"d0": 1.0, "d1": 1.0, "d2": 1.0 + 0.01 * k}
t = A.target_abs(S, 2)
check("타깃 = 적격 알트 중앙 수익률, 창이 온전한 날만", abs(t[0] - 0.05) < 1e-12 and t[1] is None and t[2] is None)
C = {"avg_cap": [0.1] * 25 + [0.4], "avg_up": [1.2] * 26, "avg_dn": [1.5] * 26, "neg": [0.4] * 26}
Sx = {"dates": [f"2020-01-{i + 1:02d}" for i in range(26)]}
orig = V.features_at
V.features_at = lambda S_: [{"ctrl_ar1": 0.0, "ctrl_season": 0.0} for _ in S_["dates"]]
try:
    f = A.features_at(Sx, C)
finally:
    V.features_at = orig
check("avg_cap 20일 변화", abs(f[25]["avg_cap_chg20"] - 0.3) < 1e-12 and f[10]["avg_cap_chg20"] is None)

# ---------------------------------------------------------------- §4
print("[4] 매매 경로와 무관")
tree = ast.parse(src)
mods = {n.module if isinstance(n, ast.ImportFrom) else a.name
        for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))
        for a in (n.names if isinstance(n, ast.Import) else [None])}
check("매매 모듈 import 없음", not ({"scheduler", "paper_executor", "exchange", "sizing"} & mods))

print()
if FAIL:
    print(f"실패 {len(FAIL)}건: " + " | ".join(FAIL))
    sys.exit(1)
print("전부 통과")
