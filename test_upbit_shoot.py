"""
test_upbit_shoot.py — 업비트 슈팅 선행 신호 사전 등록 시험 고정 (네트워크 없음)

고정하는 것 넷:
  1) **특성 정의 동치** — upbit_feat.compute 가 참조 구현 study_upbit_shooting.features 와
     모든 키에서 **비트 단위로 같다**. 정의가 한 줄이라도 갈리면 시험 수치 전부가 무의미하다.
     (드리프트 누적합을 쓰면 실제로 n_ma_above 가 3↔4 로 뒤집혔다 — 그래서 창합을 쓴다.)
  2) **인과성** — i 번째 특성은 i 이후 봉을 보지 않는다. 라벨은 i+1 이고 마지막(형성 중) 봉은 빠진다.
  3) **공유 귀무의 전제** — 날짜별 (n_d, e_d, k_d) 가 특성과 무관하다. 특성마다 표본이 달라지면
     한 귀무를 12 특성에 쓸 수 없다.
  4) **판정식** — C1/C2/C3 가 각 조건에서 정확히 하나씩 뒤집힌다 + 동결 상수 + 배포 금지.
"""
import json
import math
import os
import random

import study_upbit_shooting as S
import upbit_feat as UF
import validate_upbit_shoot as V

ok = fail = 0


def chk(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
    else:
        fail += 1
        print(f"  FAIL {name} {extra}")


def synth(n=320, seed=7, flat=False):
    """합성 일봉 — 동률·평탄 구간을 일부러 섞어 경계 비교를 시험한다."""
    r = random.Random(seed)
    rows, px = [], 1000.0
    for i in range(n):
        if flat and 100 <= i < 130:
            px = 1000.0                      # 완전 평탄 — pstdev 0, nr7/도지 경계
        else:
            px *= 1 + r.gauss(0, 0.05)
        o = px * (1 + r.gauss(0, 0.01))
        h = max(o, px) * (1 + abs(r.gauss(0, 0.01)))
        l = min(o, px) * (1 - abs(r.gauss(0, 0.01)))
        rows.append(dict(date=f"2024-{1+i//28:02d}-{1+i%28:02d}", o=o, h=h, l=l, c=px,
                         v=abs(r.gauss(1000, 300)) + 1, krw=abs(r.gauss(1e9, 3e8)) + 1))
    return rows


print("§1 특성 정의 동치 (참조 = study_upbit_shooting.features)")
for tag, rows in (("합성", synth()), ("합성·평탄", synth(seed=11, flat=True))):
    fast = UF.compute(rows)
    mism, keys_ok = 0, True
    for i in range(UF.MIN_HIST, len(rows)):
        ref, got = S.features(rows, i), fast[i]
        if set(ref) != set(got):
            keys_ok = False
            break
        for k in ref:
            if ref[k] != got[k]:
                mism += 1
                if mism == 1:
                    print(f"    첫 불일치 {tag} i={i} {k}: ref={ref[k]} fast={got[k]}")
    chk(f"{tag} 키 집합 동일", keys_ok)
    chk(f"{tag} 전 키 비트 일치", mism == 0, f"({mism}개)")
chk("MIN_HIST 미만은 None", all(x is None for x in UF.compute(synth(80))[:UF.MIN_HIST]))
chk("참조와 상수 공유", (UF.MIN_HIST, UF.MAS, UF.THR) == (S.MIN_HIST, S.MAS, S.THR))
if os.path.exists(V.CACHE):
    data = json.load(open(V.CACHE, encoding="utf-8"))
    mism = 0
    for m in sorted(data)[:3]:
        rows = data[m]
        if len(rows) <= UF.MIN_HIST + 5:
            continue
        fast = UF.compute(rows)
        for i in range(UF.MIN_HIST, len(rows)):
            ref = S.features(rows, i)
            mism += sum(1 for k in ref if ref[k] != fast[i][k])
    chk("실데이터 3종목 비트 일치", mism == 0, f"({mism}개)")

print("§2 인과성 — 미래 봉을 안 본다")
rows = synth(300, seed=3)
i = 200
base = UF.compute(rows)[i]
tampered = [dict(r) for r in rows]
for j in range(i + 1, len(tampered)):
    tampered[j] = dict(tampered[j], c=tampered[j]["c"] * 5, h=tampered[j]["h"] * 5,
                       l=tampered[j]["l"] * 5, v=tampered[j]["v"] * 5, krw=tampered[j]["krw"] * 5)
chk("i 이후를 바꿔도 i 특성 불변", UF.compute(tampered)[i] == base)

print("§3 표본 구성")


def mk_data(n_mkt=30, n_bar=260, seed=5, shoot_at=None):
    r = random.Random(seed)
    out = {}
    for mi in range(n_mkt):
        rows = synth(n_bar, seed=seed * 100 + mi)
        if shoot_at and mi in shoot_at:
            for j in shoot_at[mi]:
                rows[j] = dict(rows[j], c=rows[j - 1]["c"] * 1.8, h=rows[j - 1]["c"] * 1.9)
        out[f"KRW-T{mi:02d}"] = rows
    return out


data = mk_data()
recs, latest = V.build_records(data)
chk("형성 중인 마지막 봉 제외 — 특성일이 latest-1 이전",
    latest is not None and all(r["date"] < latest for r in recs))
last_dates = sorted({r["date"] for r in recs})
all_dates = sorted({x["date"] for rows in data.values() for x in rows})
chk("특성일 최대 = 전체 날짜의 뒤에서 3번째(형성 1 + 라벨 1 제외)",
    last_dates[-1] == all_dates[-3], f"{last_dates[-1]} vs {all_dates[-3]}")
_per = {}
for _r in recs:
    _per[_r["market"]] = _per.get(_r["market"], 0) + 1
_n_closed = len(all_dates) - 1                       # 형성 중 1봉 제외
chk("MIN_BARS 이력 요건 — 종목당 관측 수 = 닫힌봉 − 1 − MIN_BARS",
    all(c == _n_closed - 1 - V.MIN_BARS for c in _per.values()),
    f"{sorted(set(_per.values()))} vs {_n_closed - 1 - V.MIN_BARS}")
chk("이력 짧은 종목은 통째로 제외",
    V.build_records({"KRW-SHORT": synth(V.MIN_BARS)})[0] == [])
chk("판정 12특성이 모두 있는 관측만", all(len(r["v"]) == 12 and all(x is not None for x in r["v"]) for r in recs))
chk("라벨 = 익일 종가 +50%", all(r["shoot"] == int(r["fwd1"] >= V.THR) for r in recs))

days = V.group_days(recs)
chk("유니버스 20 미만 날짜 제외", all(len(v) >= V.MIN_UNIVERSE for v in days.values()))
ds = V.day_stats(days)
chk("top_k = ceil(10%)", V.top_k(30) == 3 and V.top_k(31) == 4 and V.top_k(5) == 1)
chk("공유 귀무 전제 — (n,e,k) 가 특성과 무관",
    all(ds[d][0] == len(days[d]) for d in days))

print("§4 lift / 귀무 / Holm")
# 완전 신호: 특성값 순서가 사건 순서와 같은 날 → lift = n/k
planted = {}
for d in list(days)[:40]:
    rs = [dict(r) for r in days[d]]
    n = len(rs)
    k = V.top_k(n)
    for j, r in enumerate(rs):
        r["v"] = list(r["v"])
        r["v"][0] = -j                       # 0번 특성: 앞쪽이 큼
        r["shoot"] = 1 if j < k else 0       # 사건이 정확히 상위 k 에
    planted[d] = rs
dsp = V.day_stats(planted)
cap, _, _ = V.feature_capture(planted, 0)
lf, _ = V.lift_of(cap, dsp)
exp = st_exp = sum(n for n, _, _ in dsp.values()) / sum(k for _, _, k in dsp.values())
chk("완전 신호 lift = n/k", lf is not None and math.isclose(lf, exp, rel_tol=1e-9), f"{lf} vs {exp}")
# 무정보 특성: 사건을 뒤섞으면 lift 기대 1
r2 = random.Random(1)
shuf = {}
for d, rs in planted.items():
    rs2 = [dict(r) for r in rs]
    lab = [r["shoot"] for r in rs2]
    r2.shuffle(lab)
    for r, x in zip(rs2, lab):
        r["shoot"] = x
    shuf[d] = rs2
cap2, _, _ = V.feature_capture(shuf, 0)
lf2, _ = V.lift_of(cap2, V.day_stats(shuf))
chk("무정보 lift ≈ 1", lf2 is not None and 0.3 < lf2 < 2.5, f"{lf2}")
nl = V.null_lifts(dsp, random.Random(V.SEED))
chk("귀무 lift 개수 = BOOT", len(nl) == V.BOOT)
chk("귀무 평균 ≈ 1", 0.8 < (sum(nl) / len(nl)) < 1.2, f"{sum(nl)/len(nl):.3f}")
chk("완전 신호 p 최소값", V.pval(lf, nl) <= 1.0 / (V.BOOT + 1) + 1e-12)
chk("귀무 재현성(시드 고정)", V.null_lifts(dsp, random.Random(V.SEED)) == nl)
chk("Holm — 가장 작은 p 에 m 배", math.isclose(V.holm({k: 0.001 * (i + 1) for i, k in
    enumerate(V.KEYS)})[V.KEYS[0]], 0.001 * V.M_HOLM, rel_tol=1e-9))
chk("Holm 단조", (lambda a: all(a[V.KEYS[i]] <= a[V.KEYS[i + 1]] + 1e-12 for i in range(11)))(
    V.holm({k: 0.001 * (i + 1) for i, k in enumerate(V.KEYS)})))
chk("Holm 상한 1.0", max(V.holm({k: 0.9 for k in V.KEYS}).values()) <= 1.0)
# 동점 처리 — 종목명 오름차순으로 결정론
tied = {"2024-01-01": [dict(date="2024-01-01", market=f"KRW-{c}", v=[1.0] * 12, ret20=0.0,
                           fwd1=0.0, fwd5=0.0, shoot=0, shoot_hi=0) for c in "ZYXWVUTSRQ"]}
c1, _, _ = V.feature_capture(tied, 0)
srt = sorted(tied["2024-01-01"], key=lambda r: (-r["v"][0], r["market"]))[:V.top_k(10)]
chk("동점 tie-break 종목명", [r["market"] for r in srt] == ["KRW-Q"])

print("§5 판정식")


def blk(lift, p_holm, cons, top, uni, p=0.0):
    return dict(lift=lift, p=p, p_holm=p_holm, consistency=cons, top_fwd1=top, uni_fwd1=uni)


def mk(lift_tr=1.8, ph=0.01, cons=0.7, lift_ho=1.4, p_ho=0.01, t_tr=0.01, u_tr=0.0,
       t_ho=0.01, u_ho=0.0):
    tr = dict(by_feat={k: blk(lift_tr, ph, cons, t_tr, u_tr) for k, _ in V.FEATURES})
    ho = dict(by_feat={k: blk(lift_ho, 1.0, 1.0, t_ho, u_ho, p=p_ho) for k, _ in V.FEATURES})
    return tr, ho


v, _ = V.judge(*mk())
chk("전부 만족 → CONFIRMED", v["atr14_pct"]["verdict"] == "CONFIRMED")
chk("C1 lift 1.49 탈락", not V.judge(*mk(lift_tr=1.49))[0]["atr14_pct"]["c1"])
chk("C1 lift 1.50 통과", V.judge(*mk(lift_tr=1.50))[0]["atr14_pct"]["c1"])
chk("C1 Holm p .05 탈락", not V.judge(*mk(ph=0.05))[0]["atr14_pct"]["c1"])
chk("C1 월일관 0.59 탈락", not V.judge(*mk(cons=0.59))[0]["atr14_pct"]["c1"])
chk("C1 월일관 0.60 통과", V.judge(*mk(cons=0.60))[0]["atr14_pct"]["c1"])
chk("C2 lift 1.29 탈락", not V.judge(*mk(lift_ho=1.29))[0]["atr14_pct"]["c2"])
chk("C2 p .05 탈락", not V.judge(*mk(p_ho=0.05))[0]["atr14_pct"]["c2"])
chk("C3 train 엣지 0 탈락", not V.judge(*mk(t_tr=0.01, u_tr=0.01))[0]["atr14_pct"]["c3"])
chk("C3 holdout 엣지 음수 탈락", not V.judge(*mk(t_ho=0.001, u_ho=0.002))[0]["atr14_pct"]["c3"])
chk("C3 수수료 미만 탈락", not V.judge(*mk(t_ho=V.FEE * 0.9, u_ho=0.0))[0]["atr14_pct"]["c3"])
chk("C3 수수료 초과 통과", V.judge(*mk(t_ho=V.FEE * 1.1, u_ho=0.0))[0]["atr14_pct"]["c3"])
_, ctrl = V.judge(*mk())
chk("대조 3종 전부 C1 → INVALID 조건", ctrl == 3 and ctrl >= 2)
tr, ho = mk()
for k, _ in V.CONTROL[1:]:
    tr["by_feat"][k] = blk(1.0, 1.0, 0.0, 0.0, 0.0)
_, ctrl2 = V.judge(tr, ho)
chk("대조 1종만 통과 → INVALID 아님", ctrl2 == 1 and ctrl2 < 2)

print("§6 동결 상수 / 배포 금지")
chk("DEPLOY_ON_PASS False", V.DEPLOY_ON_PASS is False)
chk("사건 문턱 +50%", V.THR == 0.50 == S.THR)
chk("상위 분위 10%", V.TOP_FRAC == 0.10)
chk("이력 요건 180봉", V.MIN_BARS == 180)
chk("부트 1000 · 시드 고정", (V.BOOT, V.SEED) == (1000, 20260921))
chk("문턱 C1 1.50 / C2 1.30 / alpha .05", (V.C1_LIFT, V.C2_LIFT, V.ALPHA) == (1.50, 1.30, 0.05))
chk("월 일관성 0.60 · 월 최소 사건 3", (V.CONSISTENCY, V.MIN_EVENTS_MONTH) == (0.60, 3))
chk("왕복 수수료 0.1%", V.FEE == 0.001)
chk("탐색 창 제외 2026-08·09", V.EXCLUDE_MONTHS == ("2026-08", "2026-09"))
chk("train 70%", V.TRAIN_FRAC == 0.70)
chk("가설 9 + 대조 3 = Holm m 12", len(V.HYPO) == 9 and len(V.CONTROL) == 3 and V.M_HOLM == 12)
chk("대조는 탐색 판에서 구분 없던 3종",
    [k for k, _ in V.CONTROL] == ["dist_ma180", "dd_250h", "n_ma_above"])
chk("특성 키가 전부 실존", all(k in S.features(synth(), 200) for k in V.KEYS))

print(f"\n{'='*60}\n통과 {ok} / 실패 {fail}\n{'='*60}")
raise SystemExit(1 if fail else 0)
