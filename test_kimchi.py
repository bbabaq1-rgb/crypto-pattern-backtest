"""
test_kimchi.py — 김치 프리미엄 판의 성질 고정.

가장 중요한 것 셋:
  §2 **환율이 정말 소거되는가** — 주 판정 전체가 이 성질 위에 서 있다. 안 되면 재는 것이 프리미엄이 아니라 환율이다.
  §3 **봉 정렬** — 업비트 일봉은 KST 라 9시간 어긋난다. 240m·20:00 UTC 규칙이 깨지면 신호보다 큰 잡음을 얹는다.
  §1 **부모 프레임 상속** — 분할·문턱·귀무를 새로 만들지 않아야 기존 판과 비교 가능하다.
실행: python test_kimchi.py
"""
import math
import os
import random
import statistics as st
import sys

import build_data_kimchi as B
import validate_altseason as V
import validate_kimchi as KC
import validate_xsec_chars as xc
import xsec_features as xf

FAIL = []


def chk(name, cond, extra=""):
    if cond:
        print(f"  ✓ {name}")
    else:
        FAIL.append(name)
        print(f"  ✗ {name} {extra}")


def _rows(dates, closes, vols=None):
    return [{"date": d, "c": c, "o": c, "h": c, "l": c, "v": (vols[i] if vols else 1.0), "ts": i}
            for i, (d, c) in enumerate(zip(dates, closes))]


def _dates(n, start=1):
    return [f"2024-{1 + (start + i) // 28:02d}-{1 + (start + i) % 28:02d}" for i in range(n)]


# ── §1 부모 프레임 상속 ───────────────────────────────────────────────────
print("\n§1 부모 프레임을 그대로 상속 — 새 분할·문턱·귀무를 만들지 않는다")
for fn in ("month_stats", "split", "judge_var", "finalize", "spearman", "cross_section", "boot_p"):
    chk(f"xc.{fn} 을 그대로 쓴다", getattr(KC.xc, fn) is getattr(xc, fn))
for fn in ("spearman", "rotation_null", "pval", "pval_two", "mde", "tercile_stats", "holm", "judge"):
    chk(f"V.{fn} 을 그대로 쓴다", getattr(KC.V, fn) is getattr(V, fn))
chk("MIN_CS 는 xsec 값 그대로", KC.MIN_CS is xc.MIN_CS and xc.MIN_CS == 15)
chk("가족 X 분할은 xsec 것(2025-01)", xc.SPLIT_MONTH == "2025-01")
chk("가족 T 분할은 altseason 것(2022-01-01)", V.SPLIT == "2022-01-01")
chk("altseason 문턱을 낮추지 않았다", (V.IC1, V.IC2) == (0.20, 0.15))
chk("왕복 비용 0.4% 상속", xc.COST_RT == 0.004)
src = open("validate_kimchi.py").read()
code = "\n".join(ln.split("#")[0] for ln in src.splitlines())
for bad in ("IC1 =", "IC2 =", "SPLIT_MONTH =", "COST_RT =", "ALPHA ="):
    chk(f"문턱을 재정의하지 않는다 ({bad.strip(' =')})", bad not in code)


# ── §2 환율 소거 (주 판정의 근간) ─────────────────────────────────────────
print("\n§2 환율 소거 — 같은 날 모든 KRW 가격에 어떤 배수를 곱해도 kp_rel 이 변하면 안 된다")
rnd = random.Random(7)
n, syms = 40, [f"S{i}" for i in range(20)]
ds = _dates(n)
rows_1d, krw_a, krw_b = {}, {}, {}
fx = {d: 1000 * math.exp(rnd.gauss(0, 0.05)) for d in ds}      # 날짜별 임의 환율
for s in syms:
    px = [10 * math.exp(rnd.gauss(0, 0.03) * (i + 1) ** 0.5) for i in range(n)]
    rows_1d[s] = _rows(ds, px)
    prem = [math.exp(rnd.gauss(0, 0.02)) for _ in range(n)]     # 코인·날짜별 프리미엄
    krw_a[s] = {d: (px[i] * prem[i] * 1000.0, 1.0) for i, d in enumerate(ds)}       # 환율 고정
    krw_b[s] = {d: (px[i] * prem[i] * fx[d], 1.0) for i, d in enumerate(ds)}        # 환율 변동
Ka, Kb = KC.build_kp(rows_1d, krw_a), KC.build_kp(rows_1d, krw_b)
chk("두 판의 격자가 같다", Ka["grid"] == Kb["grid"] and len(Ka["grid"]) == n)
dev = max(abs(Ka["kp"][s][d] - Kb["kp"][s][d]) for s in syms for d in Ka["kp"][s])
chk(f"kp_rel 이 환율에 불변 (최대차 {dev:.2e})", dev < 1e-9, f"{dev}")
d0 = Ka["grid"][5]
chk("시장 로그비율(mkt)은 환율을 그대로 안는다 — 그래서 가족 T 만 환율이 필요하다",
    abs((Kb["mkt"][d0] - Ka["mkt"][d0]) - (math.log(fx[d0]) - math.log(1000.0))) < 1e-9)
chk("kp_rel 의 그날 중앙값은 0", all(abs(st.median([Ka["kp"][s][d] for s in syms])) < 1e-12 for d in Ka["grid"][:5]))
chk(f"코인 수가 MIN_CS 미만인 날은 격자에서 빠진다",
    KC.build_kp({s: rows_1d[s] for s in syms[:5]}, {s: krw_a[s] for s in syms[:5]})["grid"] == [])


# ── §3 봉 정렬 (업비트 KST 함정) ──────────────────────────────────────────
print("\n§3 봉 정렬 — 240m · 20:00 UTC 봉만 (종가가 D+1 00:00 UTC = data_long date=D 종가 시각)")
chk("UNIT = 240 (UTC epoch 정렬 봉)", B.UNIT == 240)
chk("KEEP_HOUR = 20", B.KEEP_HOUR == 20)
chk("일봉 엔드포인트를 쓰지 않는다(KST 경계)", "/candles/days" not in open("build_data_kimchi.py").read().split("def fetch_fx")[0])
chk("20:00 + 240m = 다음날 00:00 UTC", (B.KEEP_HOUR * 60 + B.UNIT) == 24 * 60)
kept = {}
for t, px in [("2024-05-01T16:00:00", 1), ("2024-05-01T20:00:00", 2), ("2024-05-02T00:00:00", 3),
              ("2024-05-02T20:00:00", 4)]:
    if t[11:13] == f"{B.KEEP_HOUR:02d}":
        kept[t[:10]] = px
chk("20 시 봉만 남고 하루 한 행", kept == {"2024-05-01": 2, "2024-05-02": 4})


# ── §4 인과성 ─────────────────────────────────────────────────────────────
print("\n§4 인과성 — 피처는 형성일까지의 격자 값만 본다")
f1 = KC.features_x(Ka)
rows2 = {s: [dict(r) for r in rows_1d[s]] for s in syms}
krw2 = {s: dict(krw_a[s]) for s in syms}
for s in syms:                                     # 마지막 5일 조작
    for i in range(n - 5, n):
        rows2[s][i]["c"] *= 3.0
        krw2[s][ds[i]] = (krw2[s][ds[i]][0] * 7.0, 1.0)
f2 = KC.features_x(KC.build_kp(rows2, krw2))
cut = ds[n - 6]
bad = [(s, d, k) for s in syms for d in f1[s] if d <= cut
       for k in ("kp_rel", "kp_rel_chg5", "kp_rel_chg20", "kp_rel_z60")
       if f1[s][d][k] != f2[s][d][k]]
chk("미래 봉을 바꿔도 그 이전 피처가 비트 단위로 같다", not bad, str(bad[:3]))
g, gi = Ka["grid"], Ka["gi"]
chk("창이 다 안 차면 None (부분 창 금지)",
    KC._win(Ka["kp"][syms[0]], g, gi, g[3], 60) is None and
    f1[syms[0]][g[3]]["kp_rel_z60"] is None and f1[syms[0]][g[3]]["kp_rel_chg5"] is None)
chk("chg5 는 정확히 5 격자 전과의 차",
    abs(f1[syms[0]][g[10]]["kp_rel_chg5"] - (Ka["kp"][syms[0]][g[10]] - Ka["kp"][syms[0]][g[5]])) < 1e-12)


# ── §5 대조의 결정론 ──────────────────────────────────────────────────────
print("\n§5 음성 대조 — 프로세스 간 재현 가능해야 한다")
chk("코드에 hash( 없음 (PYTHONHASHSEED 재현성)", "hash(" not in code)
chk("sym_const 는 심볼의 결정론적 함수", KC.sym_const("BTC") == KC.sym_const("BTC") and 0 <= KC.sym_const("XRP") < 1)
chk("sym_const 는 코인마다 다르다", len({KC.sym_const(s) for s in ("BTC", "ETH", "XRP", "ADA")}) == 4)
chk("_ar1 재현성", KC._ar1(50, 1) == KC._ar1(50, 1) and KC._ar1(50, 1) != KC._ar1(50, 2))
ar = KC._ar1(4000, 3)
chk("_ar1 이 실제로 지속적(φ=0.95 → lag1 상관 > 0.8)", KC._autocorr(ar, 1) > 0.8)
chk("ctrl_sym_const 는 시간에 불변(지속성 최대)",
    len({f1[syms[0]][d]["ctrl_sym_const"] for d in f1[syms[0]]}) == 1)


# ── §6 판정 경로 ──────────────────────────────────────────────────────────
print("\n§6 판정 — 부모 finalize + train TOP 요건(xsec_chars 설계 부채 소진)")
base = dict(train_months=30, p_holm=0.001, train_ic=0.1, year_pos_share=0.8, lbyo_ic=0.05,
            oos_months=12, oos_ic=0.1, oos_p=0.01, oos_top_edge=0.02, oos_top_abs=0.05,
            train_top_edge=0.01)
r = KC.finalize_x(dict(base))
chk("train TOP 양수 + 나머지 충족 → CONFIRMED", r["verdict"] == "CONFIRMED")
r2 = KC.finalize_x(dict(base, train_top_edge=-0.01))
chk("train TOP 음수면 REJECTED (부모만으로는 통과했을 셀)", r2["verdict"] == "REJECTED" and r2["train_ok"] is False)
r2b = xc.finalize(dict(base, train_top_edge=-0.01))
chk("  ↳ 그 셀이 부모 finalize 에서는 실제로 통과한다(요건이 새로 무언가를 막는다)", r2b["verdict"] == "CONFIRMED")
r3 = KC.finalize_x(dict(base, train_top_edge=-0.01), require_train_top=False)
chk("요건을 끄면 부모와 같다", r3["verdict"] == "CONFIRMED")
chk("OOS 비용 스트레스가 살아 있다",
    KC.finalize_x(dict(base, oos_top_abs=0.001))["verdict"] == "TRAIN_ONLY")


# ── §7 가족 T ─────────────────────────────────────────────────────────────
print("\n§7 가족 T — 지평만 20 으로, 회전 귀무 최소 이동 30")
chk("HORIZON_T = 20", KC.HORIZON_T == 20)
chk("MIN_SHIFT_T = 1.5 x 지평 = 30", KC.MIN_SHIFT_T == 30 == int(1.5 * KC.HORIZON_T))
chk("부모 기본 min_shift(180)를 쓰지 않는다 — 명시 전달", "min_shift=min_shift" in code and V.MIN_SHIFT == 180)
fxm = {d: 1000.0 for d in Ka["grid"]}
ft, tg = KC.series_t(Ka, fxm, rows_1d)
chk("타깃은 적격 코인 중앙 fwd20 (길이 = 격자)", len(tg) == len(Ka["grid"]))
chk("마지막 20일은 타깃이 없다", all(v is None for v in tg[-KC.HORIZON_T:]))
i0 = 0
exp = st.median([rows_1d[s][KC.HORIZON_T]["c"] / rows_1d[s][0]["c"] - 1 for s in syms])
chk("타깃 정의가 중앙 20일 수익과 일치", tg[i0] is not None and abs(tg[i0] - exp) < 1e-12)
chk("kp_mkt = 시장 로그비율 − ln(환율)", abs(ft[0]["kp_mkt"] - (Ka["mkt"][Ka["grid"][0]] - math.log(1000.0))) < 1e-12)
chk("환율이 없는 날은 kp_mkt None", KC.series_t(Ka, {d: None for d in Ka["grid"]}, rows_1d)[0][0]["kp_mkt"] is None)
chk("ffill 은 직전값만 채우고 앞은 None",
    KC.ffill({"2024-01-03": 2.0}, ["2024-01-01", "2024-01-03", "2024-01-04"]) ==
    {"2024-01-01": None, "2024-01-03": 2.0, "2024-01-04": 2.0})


# ── §8 거래대금 점유율(진단) ──────────────────────────────────────────────
print("\n§8 kp_volshare — 점유율 비라 통화 단위·전체 규모에 불변")
krw_s = {s: {d: (v[0], v[1] * 13.0) for d, v in krw_a[s].items()} for s in syms}
Ks = KC.build_kp(rows_1d, krw_s)
dv = max(abs(Ka["volshare"][s][d] - Ks["volshare"][s][d]) for s in syms for d in Ka["volshare"][s])
chk(f"KRW 거래대금 전체에 상수를 곱해도 불변 (최대차 {dv:.2e})", dv < 1e-9)
chk("진단 셀이지 주 판정이 아니다", "kp_volshare" in dict(KC.DIAG_X) and "kp_volshare" not in dict(KC.MAIN_X))


# ── §9 동결 상수 ──────────────────────────────────────────────────────────
print("\n§9 동결 상수")
chk("가족 X 주 판정 4셀", [k for k, _ in KC.MAIN_X] ==
    ["kp_rel", "kp_rel_chg5", "kp_rel_chg20", "kp_rel_z60"])
chk("가족 X 사전 부호 전부 '-'", all(KC.SIGN_X[k] == "-" for k, _ in KC.MAIN_X))
chk("가족 X 대조 3 · 방향 자유('?')", len(KC.CTRL_X) == 3 and all(KC.SIGN_X[k] == "?" for k, _ in KC.CTRL_X))
chk("가족 T 주 판정 3셀 · 부호 전부 −1", len(KC.MAIN_T) == 3 and all(s == -1 for _, _, s in KC.MAIN_T))
chk("가족 T 대조 2", len(KC.CTRL_T) == 2)
chk("Holm 가족 크기 = 주 판정 셀 수", KC.M_HOLM_X == len(KC.MAIN_X) and KC.M_HOLM_T == len(KC.MAIN_T))
chk("대조 2개 이상 통과 시 INVALID", KC.MAX_CTRL_PASS == 1)
chk("창 60/5/20 · 120/20", (KC.W_Z60, KC.W_CHG5, KC.W_CHG20, KC.W_Z120, KC.W_CHG20_T) == (60, 5, 20, 120, 20))
chk("DEPLOY_ON_PASS = False", KC.DEPLOY_ON_PASS is False)
chk("AR(1) φ = 0.95", KC.AR1_PHI == 0.95)
chk("키가 xsec 가족과 겹치지 않는다", not (set(KC.LABEL_X) & set(xf.KEYS)))


# ── §10 실데이터 배관 (data_kimchi 있을 때만) ─────────────────────────────
print("\n§10 실데이터 배관")
if os.path.isdir(KC.KRW_DIR) and any(f.endswith("_krw.csv.gz") for f in os.listdir(KC.KRW_DIR)):
    sym = sorted(f[:-len("_krw.csv.gz")] for f in os.listdir(KC.KRW_DIR) if f.endswith("_krw.csv.gz"))[0]
    k = KC.load_krw(sym.upper())
    chk(f"{sym.upper()} KRW 로드", len(k) > 100)
    chk("날짜가 YYYY-MM-DD 이고 중복 없다", all(len(d) == 10 and d[4] == "-" for d in k))
    chk("종가 양수", all(v[0] > 0 for v in k.values()))
else:
    print("  – data_kimchi 없음 — 건너뜀 (build_data_kimchi.py 선행)")

print("\n" + "=" * 60)
print(f"실패 {len(FAIL)}건" + ("" if not FAIL else ": " + ", ".join(FAIL)))
sys.exit(1 if FAIL else 0)
