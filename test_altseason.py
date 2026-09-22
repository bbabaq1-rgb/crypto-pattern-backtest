"""
test_altseason.py — validate_altseason 사전 등록 시험의 성질 고정.

가장 중요한 두 가지:
  §1 **인과성** — 지표는 t 이후 봉을 건드려도 값이 변하면 안 된다(레포의 반복 결함).
  §2 **회전 귀무가 중첩을 실제로 상쇄하는가** — 120일 라벨은 이웃끼리 119/120 이 겹쳐
      iid 셔플 귀무는 분포가 터무니없이 좁아진다. 회전 귀무가 훨씬 넓어야 한다.
실행: python test_altseason.py
"""
import math
import random
import statistics as st
import sys

import validate_altseason as V

FAIL = []


def chk(name, cond, extra=""):
    if cond:
        print(f"  ✓ {name}")
    else:
        FAIL.append(name)
        print(f"  ✗ {name} {extra}")


def synth(n=700, n_alt=14, seed=7):
    """btc/eth + 알트 n_alt 개. 날짜는 2018-01-01 부터 연속."""
    from datetime import date, timedelta
    d0 = date(2018, 1, 1)
    dates = [(d0 + timedelta(days=i)).isoformat() for i in range(n)]
    rnd = random.Random(seed)
    by = {}
    for k, s in enumerate(["btc", "eth"] + [f"a{i:02d}" for i in range(n_alt)]):
        p, out = 100.0 + k, {}
        for d in dates:
            p *= math.exp(rnd.gauss(0.0005, 0.03))
            out[d] = p
        by[s] = out
    return by, dates


# ── §1 인과성 ─────────────────────────────────────────────────────────────
print("\n§1 인과성 — 미래 봉을 조작해도 과거 지표는 불변")
by, dates = synth()
S = V.build_series(by)
F0 = V.features_at(S)
cut = 500
by2 = {s: dict(m) for s, m in by.items()}
for s in by2:
    for d in dates[cut + 1:]:
        by2[s][d] *= 3.0            # 미래를 통째로 3배
S2 = V.build_series(by2)
F1 = V.features_at(S2)
keys = [k for k, _, _ in V.FEATURES]
bad = [(i, k) for i in range(200, cut + 1) for k in keys
       if (F0[i][k] is None) != (F1[i][k] is None)
       or (F0[i][k] is not None and abs(F0[i][k] - F1[i][k]) > 1e-12)]
chk("지표 10종 전부 t 시점까지만 본다 (조작 전 구간 완전 동일)", not bad, f"불일치 {bad[:3]}")

t0, _ = V.target_at(S)
t1, _ = V.target_at(S2)
chk("타깃은 미래를 본다 — 조작 시 t=cut-HORIZON 근처 값이 달라져야(대조 검사)",
    any(t0[i] is not None and t1[i] is not None and abs(t0[i] - t1[i]) > 1e-9
        for i in range(cut - V.HORIZON + 1, cut)))

chk("라벨 창이 온전하지 않은 마지막 HORIZON 일은 타깃 None",
    all(t0[i] is None for i in range(len(dates) - V.HORIZON, len(dates))))


# ── §2 회전 귀무가 중첩을 상쇄하는가 ──────────────────────────────────────
print("\n§2 회전 귀무 — 자기상관을 보존해 중첩이 만드는 가짜 유의를 상쇄")
rnd = random.Random(11)
n = 1200
fv, tv = [0.0], [0.0]
for _ in range(n - 1):                       # 둘 다 독립 랜덤워크(강한 자기상관, 관계 없음)
    fv.append(fv[-1] + rnd.gauss(0, 1))
    tv.append(tv[-1] + rnd.gauss(0, 1))
rot = V.rotation_null(fv, tv, boot=300, seed=1)
iid = []
for b in range(300):                         # iid 셔플 귀무 (잘못된 방법)
    r2 = random.Random(1000 + b)
    sh = fv[:]; r2.shuffle(sh)
    iid.append(V.spearman(sh, tv))
sd_rot, sd_iid = st.pstdev(rot), st.pstdev(iid)
chk(f"회전 귀무 분포가 iid 셔플보다 훨씬 넓다 (sd {sd_rot:.3f} vs {sd_iid:.3f}, 3배 이상)",
    sd_rot > 3 * sd_iid, f"{sd_rot:.4f} / {sd_iid:.4f}")
chk("→ 그래서 MDE 가 크게 잡힌다 (이 판의 검정력 한계를 숨기지 않는다)",
    abs(V.mde(rot, +1)) > 0.10, f"MDE {V.mde(rot, +1):.3f}")
chk("회전 이동 폭이 최소 MIN_SHIFT 이상 — 라벨 창(120일)을 넘어선다", V.MIN_SHIFT >= V.HORIZON)
chk("표본이 2*MIN_SHIFT 이하이면 귀무를 만들지 않는다(빈 목록)",
    V.rotation_null([1.0] * 100, [1.0] * 100) == [])

# 진짜 관계가 있으면 회전 귀무에서도 잡힌다 (과보수 아님)
sig_f = [math.sin(i / 50.0) for i in range(n)]
sig_t = [sig_f[i] + rnd.gauss(0, 0.25) for i in range(n)]
ic = V.spearman(sig_f, sig_t)
p = V.pval(ic, V.rotation_null(sig_f, sig_t, boot=300, seed=2), +1)
chk(f"강한 실제 관계(IC {ic:+.2f})는 회전 귀무에서도 유의 (p {p:.3f} < .05)", p < 0.05)


# ── §3 spearman / ranks ───────────────────────────────────────────────────
print("\n§3 순위상관")
chk("완전 단조 증가 = +1", abs(V.spearman([1, 2, 3, 4, 5], [10, 20, 30, 40, 50]) - 1) < 1e-12)
chk("완전 단조 감소 = -1", abs(V.spearman([1, 2, 3, 4, 5], [5, 4, 3, 2, 1]) + 1) < 1e-12)
chk("비선형 단조에도 +1 (피어슨과 다름)", abs(V.spearman([1, 2, 3, 4], [1, 10, 100, 1000]) - 1) < 1e-12)
chk("동률은 평균 순위", V._ranks([5, 5, 1]) == [2.5, 2.5, 1.0])
chk("전부 동률이면 상관 0", V.spearman([1, 1, 1, 1], [1, 2, 3, 4]) == 0.0)


# ── §4 p / MDE / Holm ─────────────────────────────────────────────────────
print("\n§4 p · MDE · Holm")
nulls = [i / 100.0 - 0.5 for i in range(101)]        # -0.50 ~ +0.50 균등
chk("단측 p — 선언 부호 + (자기 자신 포함 +1 보정)",
    abs(V.pval(0.5, nulls, +1) - 2 / 102) < 1e-9, f"{V.pval(0.5, nulls, +1):.5f}")
chk("단측 p — 선언 부호 -",
    abs(V.pval(-0.5, nulls, -1) - 2 / 102) < 1e-9, f"{V.pval(-0.5, nulls, -1):.5f}")
chk("p 는 0 이 될 수 없다 (+1 보정)", V.pval(9.9, nulls, +1) == 1 / 102)
chk("반대 부호로 크면 단측 p 는 1 에 가깝다 (통과로 안 셈)", V.pval(-0.5, nulls, +1) > 0.98)
chk("양측 p 는 부호 무관", abs(V.pval_two(0.5, nulls) - V.pval_two(-0.5, nulls)) < 1e-9)
chk("MDE(+) = 귀무 95백분위", abs(V.mde(nulls, +1) - sorted(nulls)[int(0.95 * 100)]) < 1e-12)
chk("MDE(-) = 귀무 5백분위", abs(V.mde(nulls, -1) - sorted(nulls)[int(0.05 * 100)]) < 1e-12)
h = V.holm([("a", 0.001), ("b", 0.02), ("c", 0.30)], m=10)
chk("Holm 가족 크기를 m 으로 고정 (가장 작은 p × m)", abs(h["a"] - 0.01) < 1e-12)
chk("Holm 은 단조 비감소", h["a"] <= h["b"] <= h["c"])
chk("Holm m=M_HOLM 은 가설 수와 같다(대조 제외)", V.M_HOLM == len(V.FEATURES))


# ── §5 판정 게이트 ────────────────────────────────────────────────────────
print("\n§5 판정 — 실행 전 동결된 규칙")


def row(ic_tr, p_holm, ic_ho, p_ho, sign=+1, mde_tr=0.10,
        terc_tr=(0.2, 0.1), terc_ho=(0.2, 0.1), p_two=0.5):
    def t(ic, p, terc, extra):
        d = dict(n=999, ic=ic, p=p, p_two=p_two, mde=mde_tr,
                 terc=dict(top_mean=terc[0], all_mean=terc[1], n_top=100))
        d.update(extra)
        return d
    return dict(key="x", label="x", sign=sign, is_control=False,
                train=t(ic_tr, p_holm, terc_tr, dict(p_holm=p_holm)),
                holdout=t(ic_ho, p_ho, terc_ho, {}))


chk("전 기준 통과 → CONFIRMED", V.judge(row(0.30, 0.01, 0.20, 0.01))[0] == "CONFIRMED")
chk("|IC_train| 이 문턱 미만 → REJECTED", V.judge(row(0.15, 0.01, 0.20, 0.01))[0] == "REJECTED")
chk("holdout 부호 뒤집힘 → REJECTED", V.judge(row(0.30, 0.01, -0.20, 0.01))[0] == "REJECTED")
chk("holdout 상위3분위가 음수면 C3 탈락 → REJECTED",
    V.judge(row(0.30, 0.01, 0.20, 0.01, terc_ho=(-0.05, -0.10)))[0] == "REJECTED")
chk("상위3분위가 전체 평균보다 못하면 C3 탈락",
    V.judge(row(0.30, 0.01, 0.20, 0.01, terc_ho=(0.05, 0.10)))[0] == "REJECTED")
chk("크기·부호는 맞는데 p 실패 + MDE > 문턱 → INCONCLUSIVE(검정력 부족)",
    V.judge(row(0.30, 0.40, 0.20, 0.01, mde_tr=0.45))[0] == "INCONCLUSIVE")
chk("p 실패인데 MDE 가 작으면(검출 가능했으면) REJECTED",
    V.judge(row(0.30, 0.40, 0.20, 0.01, mde_tr=0.10))[0] == "REJECTED")
chk("선언 부호 반대로 크고 양측 유의 → REVERSED (통과 아님)",
    V.judge(row(-0.35, 0.99, -0.20, 0.99, p_two=0.01))[0] == "REVERSED")
chk("부호 - 선언에서 음수 IC 는 정상 통과",
    V.judge(row(-0.30, 0.01, -0.20, 0.01, sign=-1))[0] == "CONFIRMED")
chk("분할이 없으면 INCONCLUSIVE",
    V.judge(dict(key="x", sign=+1, train=None, holdout=None))[0] == "INCONCLUSIVE")


# ── §6 타깃 정의 ──────────────────────────────────────────────────────────
print("\n§6 타깃 — 알트 중앙값 − BTC")
by3, dates3 = synth(n=400, n_alt=12, seed=3)
S3 = V.build_series(by3)
t3, m3 = V.target_at(S3, horizon=50)
i = 200
d0, d1 = dates3[i], dates3[i + 50]
alts = [s for s in by3 if s != "btc"]
exp = st.median([by3[s][d1] / by3[s][d0] - 1 for s in alts]) - (by3["btc"][d1] / by3["btc"][d0] - 1)
chk("타깃 = median(알트 수익) − BTC 수익, ETH 포함 · BTC 제외",
    abs(t3[i] - exp) < 1e-12, f"{t3[i]} vs {exp}")
chk("평균판은 진단으로 따로 계산된다", m3[i] is not None and abs(m3[i] - t3[i]) >= 0)
chk("BTC 는 알트 바스켓에서 빠진다", "btc" not in S3["alts"] and "eth" in S3["alts"])


# ── §7 PIT — 늦게 상장한 코인이 과거 지수를 바꾸지 않는다 ─────────────────
print("\n§7 PIT — 신규 상장이 과거 값을 소급하지 않는다")
by4 = {s: dict(m) for s, m in by3.items()}
late = {d: 100.0 * (1.5 ** k) for k, d in enumerate(dates3[300:])}   # 300일째 상장, 폭등
by4["zlate"] = late
S4 = V.build_series(by4)
chk("상장 전 구간의 OTHERS 지수 불변",
    all(abs(S3["altbtc"][i] - S4["altbtc"][i]) < 1e-12 for i in range(0, 300)))
chk("상장 후에도 MIN_HIST(180봉) 전에는 지수에 안 들어간다",
    all(abs(S3["altbtc"][i] - S4["altbtc"][i]) < 1e-12
        for i in range(300, min(len(dates3), 300 + V.MIN_HIST))))
chk("적격 판정은 그 종목 자신의 이력 길이 기준",
    S4["eligible"]("zlate", dates3[-1]) == (len(late) >= V.MIN_HIST))
chk("폭 분모는 적격 종목만", S3["univ_n"][50] == 0 or S3["univ_n"][-1] >= V.MIN_UNIVERSE)


# ── §8 동결 상수 ──────────────────────────────────────────────────────────
print("\n§8 동결 상수 (사용자 지정 지평 포함)")
chk("HORIZON = 120 (2026-09-22 사용자 지정)", V.HORIZON == 120)
chk("MIN_SHIFT = 180 = 1.5 x HORIZON", V.MIN_SHIFT == 180)
chk("START = 2018-01-01 (2017 은 유니버스 3종목)", V.START == "2018-01-01")
chk("SPLIT = 2022-01-01 (알트장이 양쪽에 하나씩)", V.SPLIT == "2022-01-01")
chk("MIN_HIST = 180 / MIN_UNIVERSE = 10", V.MIN_HIST == 180 and V.MIN_UNIVERSE == 10)
chk("IC 문턱 train 0.20 / holdout 0.15", (V.IC1, V.IC2) == (0.20, 0.15))
chk("BOOT 1000 · SEED 20260922 · α 0.05", (V.BOOT, V.SEED, V.ALPHA) == (1000, 20260922, 0.05))
chk("가설 10 + 음성대조 2", len(V.FEATURES) == 10 and len(V.CONTROLS) == 2)
chk("모든 지표에 부호가 선언돼 있다", all(s in (1, -1) for _, _, s in [*V.FEATURES, *V.CONTROLS]))
chk("disp60 만 음의 부호 (수축이 선행한다는 가설)",
    [k for k, _, s in V.FEATURES if s < 0] == ["disp60"])
chk("DEPLOY_ON_PASS = False — 통과해도 실거래 반영 없음", V.DEPLOY_ON_PASS is False)
chk("대조는 ctrl_ 접두사로 식별된다", all(k.startswith("ctrl_") for k, _, _ in V.CONTROLS))


# ── §9 실데이터 배관 (커밋된 data_long, 네트워크 없음) ────────────────────
print("\n§9 실데이터 배관")
try:
    real = V.load_all()
    chk(f"data_long 로드 ({len(real)} 종목) — manifest.json 건너뜀",
        len(real) > 50 and "btc" in real and "eth" in real)
    Sr = V.build_series(real)
    chk("BTC 날짜 격자가 2017 부터", Sr["dates"][0] <= "2017-01-05")
    ok_i = [i for i, d in enumerate(Sr["dates"])
            if d >= V.START and Sr["univ_n"][i] >= V.MIN_UNIVERSE]
    first_ok = Sr["dates"][ok_i[0]] if ok_i else "—"
    chk(f"유니버스가 MIN_UNIVERSE 를 넘는 첫 날 {first_ok}"
        f" — 실질 표본 시작 (START 는 하한일 뿐)", bool(ok_i))
    chk("그 뒤로는 유니버스 요건이 끊기지 않는다(연속)",
        ok_i == list(range(ok_i[0], ok_i[-1] + 1)))
except FileNotFoundError as e:
    chk(f"data_long 없음 — 스킵 ({e})", True)

print("\n" + "=" * 60)
print(f"실패 {len(FAIL)}건" + ("" if not FAIL else ": " + ", ".join(FAIL)))
sys.exit(1 if FAIL else 0)
