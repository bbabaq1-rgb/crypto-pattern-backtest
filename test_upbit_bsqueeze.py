"""
test_upbit_bsqueeze.py — B형(무거래 수축) 전용 판 고정 (네트워크 없음)

고정하는 것 다섯:
  1) **방향이 진짜로 반대다** — 이 판의 존재 이유. asc=True 특성은 상위 10% 가
     **값이 작은 쪽**이어야 한다. 앞선 판(내림차순)과 같은 집합을 고르면 B형을 안 본 것이다.
  2) **A형 제외가 인과적이고 실제로 작동한다** — ret20 > +15% 코인-일이 풀에서 빠진다.
  3) **E20 라벨 + 절단 편향 방지** — 이후 20봉 안에 종가 +50% 가 한 번이라도 있으면 1,
     창이 온전하지 않은 봉은 아예 표본에서 뺀다(음성으로 세면 편향).
  4) **squeeze_score 정의** — 두 축의 그날 오름차순 백분위 순위 평균, 동점은 종목명.
  5) **Holm m=8** — V 의 12 를 쓰면 안 된다. 동결 상수·배포 금지.
"""
import random

import upbit_feat as UF
import validate_upbit_bsqueeze as B
import validate_upbit_shoot as V

ok = fail = 0


def chk(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
    else:
        fail += 1
        print(f"  FAIL {name} {extra}")


def synth(n=320, seed=7, shoot_at=(), drift=0.0):
    r = random.Random(seed)
    rows, px = [], 1000.0
    for i in range(n):
        px *= 1 + r.gauss(drift, 0.05)
        if i in shoot_at:
            px = rows[-1]["c"] * 1.8
        o = px * (1 + r.gauss(0, 0.01))
        h = max(o, px) * (1 + abs(r.gauss(0, 0.01)))
        l = min(o, px) * (1 - abs(r.gauss(0, 0.01)))
        rows.append(dict(date=f"2024-{1+i//28:02d}-{1+i%28:02d}", o=o, h=h, l=l, c=px,
                         v=abs(r.gauss(1000, 300)) + 1, krw=abs(r.gauss(1e9, 3e8)) + 1))
    return rows


def mk_data(n_mkt=30, n_bar=280, seed=5, shoot=None):
    return {f"KRW-T{i:02d}": synth(n_bar, seed=seed * 100 + i,
                                   shoot_at=(shoot or {}).get(i, ()))
            for i in range(n_mkt)}


print("§1 방향 — 이 판의 존재 이유")
recs, latest = B.build_records(mk_data())
days = V.group_days(recs)
B.add_squeeze(days)
d0 = sorted(days)[len(days) // 2]
rs = days[d0]
k = V.top_k(len(rs))
asc_sel, _, _ = B.capture({d0: rs}, 1, True)     # bb_width_pctile120 오름차순
lo = sorted(rs, key=lambda r: (r["v"][0], r["market"]))[:k]
hi = sorted(rs, key=lambda r: (-r["v"][0], r["market"]))[:k]
sel_lo = sorted(B.capture({d0: rs}, 1, True)[1][d0])
chk("asc=True 는 값이 작은 쪽을 고른다",
    max(r["v"][0] for r in lo) <= min(r["v"][0] for r in hi) or lo[0]["market"] != hi[0]["market"])
sel = sorted(rs, key=lambda r: (1 * B.value_of(r, 1), r["market"]))[:k]
chk("asc 선택 집합 = 하위 k", {r["market"] for r in sel} == {r["market"] for r in lo})
sel_d = sorted(rs, key=lambda r: (-1 * B.value_of(r, 1), r["market"]))[:k]
chk("desc 선택 집합 = 상위 k (앞선 판과 같은 집합)", {r["market"] for r in sel_d} == {r["market"] for r in hi})
chk("두 집합이 다르다 — 같으면 B형을 안 본 것", {r["market"] for r in lo} != {r["market"] for r in hi})
chk("주 판정·B 특성은 전부 오름차순", all(a for _, _, a in [B.MAIN] + B.BFEAT))
chk("대조는 앞선 판과 같은 내림차순", all(not a for _, _, a in B.CONTROL))

print("§2 A형 제외 — 인과적이고 실제로 작동")
rows = synth(280, seed=3)
feats = UF.compute(rows)
kept = {(r["date"]) for r in B.build_records({"KRW-X": rows})[0]}
bad = [i for i in range(V.MIN_BARS, len(rows) - 1 - B.HORIZON)
       if feats[i] and feats[i]["ret20"] is not None and feats[i]["ret20"] > B.A_TYPE_MAX_RET20
       and rows[i]["date"] in kept]
chk("ret20 > +15% 코인-일은 풀에 없다", not bad, f"{bad[:3]}")
chk("문턱은 앞선 판에서 동결된 값", B.A_TYPE_MAX_RET20 == V.A_TYPE_RET20 == 0.15)
# 미래를 바꿔도 풀 소속이 안 바뀐다(인과)
i = 200
tam = [dict(r) for r in rows]
for j in range(i + 1, len(tam)):
    tam[j] = dict(tam[j], c=tam[j]["c"] * 5, h=tam[j]["h"] * 5, l=tam[j]["l"] * 5)
f_base, f_tam = UF.compute(rows)[i], UF.compute(tam)[i]
chk("특성은 미래 불변(인과)", f_base == f_tam)

print("§3 E20 라벨 + 절단 편향")
rows = synth(280, seed=9, shoot_at=(250,))
rec, _ = B.build_records({"KRW-S": rows})
by_date = {r["date"]: r for r in rec}
shoot_date = rows[250]["date"]
pos = [d for d, r in by_date.items() if r["shoot"]]
idx = {rows[i]["date"]: i for i in range(len(rows))}
chk("슈팅 20봉 전 구간이 양성", all(0 < 250 - idx[d] <= B.HORIZON for d in pos), f"{len(pos)}")
# 풀에 남은 봉만 세야 한다 — A형 필터가 그 20봉 중 일부를 뺄 수 있다(실측 18/20)
_win = [rows[i]["date"] for i in range(250 - B.HORIZON, 250) if rows[i]["date"] in by_date]
chk("양성 = 창 안에서 풀에 남은 봉 전부", len(pos) == len(_win) and set(pos) == set(_win),
    f"{len(pos)} vs {len(_win)}")
chk("양성은 지평을 넘지 않는다", len(pos) <= B.HORIZON, f"{len(pos)}")
chk("창 밖(21봉 전)은 음성", by_date.get(rows[250 - B.HORIZON - 1]["date"], {"shoot": 0})["shoot"] == 0)
last_i = max(idx[r["date"]] for r in rec)
chk("창이 온전한 봉만 — 마지막 20봉 제외", last_i <= len(rows) - 1 - 1 - B.HORIZON,
    f"{last_i} vs {len(rows)-2-B.HORIZON}")
chk("fwd 는 20봉 수익",
    all(abs(by_date[rows[i]['date']]["fwd"] - (rows[i + B.HORIZON]["c"] / rows[i]["c"] - 1)) < 1e-12
        for i in (V.MIN_BARS + 5, V.MIN_BARS + 50) if rows[i]["date"] in by_date))

print("§4 squeeze_score")
recs, _ = B.build_records(mk_data(seed=11))
days = V.group_days(recs)
B.add_squeeze(days)
d0 = sorted(days)[len(days) // 2]
rs = days[d0]
chk("점수는 0~1", all(0.0 <= r["score"] <= 1.0 for r in rs))
n = len(rs)
manual = {}
for j in range(2):
    order = sorted(range(n), key=lambda t: (rs[t]["parts"][j], rs[t]["market"]))
    for pos_, t in enumerate(order):
        manual[t] = manual.get(t, 0.0) + (pos_ / (n - 1)) / 2
chk("두 축 오름차순 순위 평균과 일치",
    all(abs(rs[t]["score"] - manual[t]) < 1e-12 for t in range(n)))
chk("두 축이 SQUEEZE_PARTS 그대로", B.SQUEEZE_PARTS == ["bb_width_pctile120", "vol_ratio20"])
chk("동점은 종목명 오름차순(결정론)",
    B.capture({d0: [dict(r, score=0.5) for r in rs]}, 0, True)[1][d0] ==
    B.capture({d0: [dict(r, score=0.5) for r in rs]}, 0, True)[1][d0])
chk("score 는 dd_250h 를 안 쓴다(사후 선택 금지)", "dd_250h" not in B.SQUEEZE_PARTS)

print("§5 공유 기계 + 동결 상수")
chk("top_k·day_stats·null_lifts·pval 을 V 와 공유",
    B.V.top_k is V.top_k and B.V.null_lifts is V.null_lifts and B.V.pval is V.pval)
chk("귀무 재현성(시드 고정)",
    V.null_lifts(V.day_stats(days), random.Random(V.SEED)) ==
    V.null_lifts(V.day_stats(days), random.Random(V.SEED)))
chk("Holm m=8 (V 의 12 아님)", B.M_HOLM == 8 == len(B.FEATURES) and V.M_HOLM == 12)
rnd = random.Random(V.SEED)
a = B.analyze(days, {d[:7] for d in days}, rnd)
ps = sorted(a["by_feat"][k]["p"] for k in a["by_feat"])
hs = sorted(a["by_feat"][k]["p_holm"] for k in a["by_feat"])
chk("Holm 가장 작은 p 에 m=8 배", abs(hs[0] - min(1.0, 8 * ps[0])) < 1e-12, f"{hs[0]} vs {8*ps[0]}")
chk("Holm 단조", all(hs[i] <= hs[i + 1] + 1e-12 for i in range(len(hs) - 1)))
chk("지평 20봉", B.HORIZON == 20)
chk("문턱 C1 1.50 / C2 1.30 · V 와 공유", (B.C1_LIFT, B.C2_LIFT) == (V.C1_LIFT, V.C2_LIFT) == (1.50, 1.30))
chk("상위 분위·이력·제외 창·시드는 V 그대로",
    (V.TOP_FRAC, V.MIN_BARS, V.EXCLUDE_MONTHS, V.SEED, V.BOOT) ==
    (0.10, 180, ("2026-08", "2026-09"), 20260921, 1000))
chk("DEPLOY_ON_PASS False", B.DEPLOY_ON_PASS is False)

print("§6 판정식")


def blk(lift, ph, cons, top, uni, p=0.0):
    return dict(lift=lift, p=p, p_holm=ph, consistency=cons, top_fwd=top, uni_fwd=uni)


def mk(lift_tr=1.8, ph=0.01, cons=0.7, lift_ho=1.4, p_ho=0.01, t_tr=0.05, u_tr=0.0,
       t_ho=0.05, u_ho=0.0):
    tr = dict(by_feat={k: blk(lift_tr, ph, cons, t_tr, u_tr) for k, _, _ in B.FEATURES})
    ho = dict(by_feat={k: blk(lift_ho, 1.0, 1.0, t_ho, u_ho, p=p_ho) for k, _, _ in B.FEATURES})
    return tr, ho


chk("전부 만족 → CONFIRMED", B.judge(*mk())[0]["squeeze_score"]["verdict"] == "CONFIRMED")
chk("C1 lift 1.49 탈락", not B.judge(*mk(lift_tr=1.49))[0]["squeeze_score"]["c1"])
chk("C1 Holm .05 탈락", not B.judge(*mk(ph=0.05))[0]["squeeze_score"]["c1"])
chk("C1 월일관 .59 탈락", not B.judge(*mk(cons=0.59))[0]["squeeze_score"]["c1"])
chk("C2 lift 1.29 탈락", not B.judge(*mk(lift_ho=1.29))[0]["squeeze_score"]["c2"])
chk("C2 p .05 탈락", not B.judge(*mk(p_ho=0.05))[0]["squeeze_score"]["c2"])
chk("C3 train 엣지 0 탈락", not B.judge(*mk(t_tr=0.05, u_tr=0.05))[0]["squeeze_score"]["c3"])
chk("C3 holdout 엣지 음수 탈락", not B.judge(*mk(t_ho=0.01, u_ho=0.02))[0]["squeeze_score"]["c3"])
chk("C3 수수료 미만 탈락", not B.judge(*mk(t_ho=V.FEE * 0.9, u_ho=0.0))[0]["squeeze_score"]["c3"])
chk("대조 3종 통과 → INVALID 조건", B.judge(*mk())[1] == 3)
tr, ho = mk()
for kk, _, _ in B.CONTROL[1:]:
    tr["by_feat"][kk] = blk(1.0, 1.0, 0.0, 0.0, 0.0)
chk("대조 1종만 → INVALID 아님", B.judge(tr, ho)[1] == 1)

print(f"\n{'='*60}\n통과 {ok} / 실패 {fail}\n{'='*60}")
raise SystemExit(1 if fail else 0)
