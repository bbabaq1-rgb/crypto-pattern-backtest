"""
test_closed_bar.py — validate_closed_bar + 스케줄러 옵트인 고정 (네트워크 없음)

고정하는 것 셋:
  1) **기준선 동치** — collect_1d_mode(전부 closed) 가 validate_portfolio.collect_1d 와
     거래 단위로 완전히 같다. 어긋나면 arm 차이가 '탐지 봉' 때문인지 '수집 경로' 때문인지
     못 가르므로 이 시험의 수치 전부가 무의미해진다.
  2) **실거래 무변경** — scheduler 옵트인은 기본 빈 목록이고 그때 탐지 봉이 종전(len-1)과 같다.
  3) 짝지음 부트가 **블록 추첨을 arm 간 공유**한다(거래 재표집이 아니라 시간 블록 재표집).
"""
import json
import random
from datetime import date, timedelta

import detlib
import method_t as mt
import scheduler as sch
import sizing_vol as sv
import validate_closed_bar as vcb
import validate_portfolio as vp

ok = fail = 0


def chk(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
    else:
        fail += 1
        print(f"  FAIL {name} {extra}")


D1, H4 = 86400000, 14400000
BASE_TS = 1577836800000          # 2020-01-01 00:00 UTC


def mk_rows(n, seed, ts0=BASE_TS, step=D1):
    r = random.Random(seed)
    rows, px = [], 100.0
    for i in range(n):
        o = px
        c = o * (1 + r.gauss(0, 0.03))
        hi, lo = max(o, c) * (1 + abs(r.gauss(0, 0.01))), min(o, c) * (1 - abs(r.gauss(0, 0.01)))
        ts = ts0 + i * step
        rows.append(dict(ts=ts, date=date.fromtimestamp(ts / 1000).isoformat(),
                         o=o, h=hi, l=lo, c=c, v=1000 + r.random() * 500))
        px = c
    return rows


SYMS = ["AAA", "BBB", "CCC"]
ROWS = {s: mk_rows(300, i) for i, s in enumerate(SYMS)}


def _install_mocks():
    """detlib 로더와 라우팅 컨텍스트를 고정 — 두 수집 경로가 같은 입력을 보게 한다."""
    orig_load, orig_ctx, orig_mode = detlib.load_ohlcv, sv.routing_ctx, sv.ROUTING_MODE

    def fake_load(sym, tf="1d"):
        if tf != "1d" or sym not in ROWS:
            raise FileNotFoundError(sym)
        return ROWS[sym]

    routing = {g: {"engulfing": "long", "fvg": "long"} for g in
               ("bull_btc", "bull_altseason", "bear", "sideways")}
    regmap = {r["date"]: "bull_btc" for r in ROWS["AAA"]}
    detlib.load_ohlcv = fake_load
    sv.routing_ctx = lambda: ((lambda p: list(SYMS)), routing, regmap, {"triple_bottom"})
    mt.REGMAP = regmap
    return orig_load, orig_ctx, orig_mode


print("§1 기준선 동치 — collect_1d_mode(전부 closed) == validate_portfolio.collect_1d")
_o_load, _o_ctx, _o_mode = _install_mocks()
try:
    ref = vp.collect_1d(SYMS)
    got = vcb.collect_1d_mode(SYMS, frozenset(vcb.SWITCHABLE), ROWS, {})
    chk("거래 수 일치", len(ref) == len(got), f"{len(ref)} vs {len(got)}")
    key = lambda t: (t["t_in"], t["pattern"], t["sym"])
    ref_s, got_s = sorted(ref, key=key), sorted(got, key=key)
    chk("거래 집합 완전 일치",
        all(a["t_in"] == b["t_in"] and a["t_out"] == b["t_out"] and abs(a["ret"] - b["ret"]) < 1e-12
            and a["pattern"] == b["pattern"] and a["sym"] == b["sym"] and a["tf"] == b["tf"]
            for a, b in zip(ref_s, got_s)) if len(ref_s) == len(got_s) else False)
    chk("변동성 필드도 일치",
        all((a["vol"] is None) == (b["vol"] is None)
            and (a["vol"] is None or abs(a["vol"] - b["vol"]) < 1e-12)
            for a, b in zip(ref_s, got_s)) if len(ref_s) == len(got_s) else False)
    chk("표본이 비어 있지 않다(동치 시험이 공허하지 않다)", len(ref) > 0, f"n={len(ref)}")
    chk("1w(triple_bottom)는 양쪽 다 제외", not any(t["tf"] != "1d" for t in ref + got))

    print("§2 forming 모드는 다른 신호 집합을 만든다")
    kids = {s: vcb.vfb.bucket(mk_rows(300 * 6, 90 + i, step=H4), D1) for i, s in enumerate(SYMS)}
    f_all = vcb.collect_1d_mode(SYMS, frozenset(), ROWS, kids)
    chk("forming 전량 판은 closed 와 다르다", len(f_all) != len(got) or
        any(abs(a["ret"] - b["ret"]) > 1e-12 for a, b in zip(sorted(f_all, key=key), got_s)),
        f"closed {len(got)} / forming {len(f_all)}")
    chk("forming 레코드도 같은 형식", all(set(t) == set(got_s[0]) for t in f_all) if f_all else True)
    mixed = vcb.collect_1d_mode(SYMS, frozenset(vcb.FOCUS_CELLS), ROWS, kids)
    chk("부분 전환은 closed 셀만 closed 와 같다",
        [t for t in mixed if t["pattern"] in vcb.FOCUS_CELLS]
        == [t for t in got if t["pattern"] in vcb.FOCUS_CELLS])
    chk("부분 전환의 나머지 셀은 forming 과 같다",
        [t for t in mixed if t["pattern"] in vcb.ADOPTED_CELLS]
        == [t for t in f_all if t["pattern"] in vcb.ADOPTED_CELLS])
    chk("kids 없으면 forming 셀은 거래 0",
        not [t for t in vcb.collect_1d_mode(SYMS, frozenset(), ROWS, {})])
finally:
    detlib.load_ohlcv, sv.routing_ctx, sv.ROUTING_MODE = _o_load, _o_ctx, _o_mode

print("§3 arm 구성")
chk("current 는 아무것도 안 바꾼다", vcb.ARM_SETS["current"] == frozenset())
chk("closed_1d 는 6셀 전부", vcb.ARM_SETS["closed_1d"] == frozenset(vcb.SWITCHABLE))
chk("SWITCHABLE 은 6셀", len(vcb.SWITCHABLE) == 6)
chk("FOCUS 4 + ADOPTED 2", len(vcb.FOCUS_CELLS) == 4 and len(vcb.ADOPTED_CELLS) == 2)
chk("두 묶음이 겹치지 않는다", not (set(vcb.FOCUS_CELLS) & set(vcb.ADOPTED_CELLS)))
chk("**three_soldiers_4h 는 전환 대상이 아니다**(두 arm 고정)",
    "three_soldiers_4h" not in vcb.SWITCHABLE)
_pats_1d = {p[0] for p in mt.PATS if p[4] == "1d"}
chk("SWITCHABLE == mt.PATS 의 1d 배포 셀", set(vcb.SWITCHABLE) == _pats_1d,
    f"{set(vcb.SWITCHABLE) ^ _pats_1d}")
chk("주 판정은 closed_1d 하나", vcb.MAIN_ARM == "closed_1d")
chk("진단 arm 은 판정에 안 쓰인다", vcb.ARMS[:2] == ["current", "closed_1d"])

print("§4 실거래 무변경 — 스케줄러 옵트인 기본 off")
uni = json.load(open("universe.json", encoding="utf-8"))
chk("universe.json 에 closed_bar_patterns 가 비어 있다",
    not uni.get("closed_bar_patterns"), f"{uni.get('closed_bar_patterns')}")
chk("closed_bar_patterns() 는 빈 집합", sch.closed_bar_patterns() == set())
rows10 = [{"c": i} for i in range(10)]
for pat in ("engulfing", "fvg", "inverted_hammer", "marubozu", "three_soldiers_4h"):
    chk(f"{pat}: 기본 탐지 봉 = 마지막 행", sch.detect_idx(pat, rows10) == len(rows10) - 1)
chk("목록에 넣으면 닫힌 봉", sch.detect_idx("engulfing", rows10, {"engulfing"}) == sch._closed_idx(rows10))
chk("목록 밖 패턴은 그대로", sch.detect_idx("fvg", rows10, {"engulfing"}) == len(rows10) - 1)
chk("_closed_idx 는 rows[-2]", sch._closed_idx(rows10) == 8)
chk("봉 1개면 닫힌 봉 없음(None)", sch._closed_idx([{"c": 1}]) is None)
chk("탐지 블록이 detect_idx 를 쓴다",
    "detect_idx(pat, rows, closed_set)" in open("scheduler.py", encoding="utf-8").read()
    and 'detect_idx(ap["pattern"], rows, closed_set)' in open("scheduler.py", encoding="utf-8").read())
chk("4h adopted 는 종전 필드를 그대로 쓴다",
    "_closed_idx(rows4h) if closed4 else len(rows4h) - 1" in open("scheduler.py", encoding="utf-8").read())

print("§5 짝지음 블록 부트 — 블록 추첨을 arm 간 공유")
def mk_tr(n, seed, off=0.0):
    r = random.Random(seed)
    base = date(2025, 1, 1).toordinal()
    out = []
    for _ in range(n):
        ti = base + r.randrange(0, 300) + r.random()
        out.append(dict(t_in=ti, t_out=ti + r.uniform(0.5, 20), ret=r.gauss(0.01 + off, 0.08),
                        pattern=r.choice(["engulfing", "fvg"]), sym=f"S{r.randrange(0, 10)}",
                        vol=r.uniform(0.4, 1.6), tf="1d", rank=None))
    return sorted(out, key=lambda t: t["t_in"])

A, B = mk_tr(150, 1), mk_tr(120, 2, off=0.01)
c1 = vcb.paired_slot_boot({"a": A, "b": B}, random.Random(5), n_boot=12)
c2 = vcb.paired_slot_boot({"a": A, "b": B}, random.Random(5), n_boot=12)
chk("같은 시드면 재현", c1 == c2)
chk("arm 마다 n_boot 개", len(c1["a"]) == 12 and len(c1["b"]) == 12)
c3 = vcb.paired_slot_boot({"a": A, "b": A}, random.Random(5), n_boot=12)
chk("같은 거래를 주면 두 arm 이 완전히 같다(블록 공유 증명)", c3["a"] == c3["b"])
chk("빈 입력 방어", vcb.paired_slot_boot({"a": [], "b": []}, random.Random(1), n_boot=3)
    == {"a": [], "b": []})
solo = vcb.paired_slot_boot({"a": A}, random.Random(7), n_boot=5)
chk("단일 arm 도 동작", len(solo["a"]) == 5)

print("§6 판정 J1~J5")
def R(cagr, mdd, calmar):
    return dict(cagr=cagr, mdd=mdd, calmar=calmar)
tr = {"current": R(0.10, -0.30, 0.33), "closed_1d": R(0.12, -0.28, 0.43)}
ho = {"current": R(0.05, -0.40, 0.13), "closed_1d": R(0.08, -0.38, 0.21)}
chk("전부 충족", all(vcb.judge(tr, ho, 0.70, "closed_1d").values()))
chk("J3 0.59 탈락", not vcb.judge(tr, ho, 0.59, "closed_1d")["J3 부트 우위>=0.60"])
chk("J3 0.60 통과", vcb.judge(tr, ho, 0.60, "closed_1d")["J3 부트 우위>=0.60"])
chk("J4 6%p 악화 탈락",
    not vcb.judge(tr, {"current": R(0.05, -0.40, 0.13), "closed_1d": R(0.08, -0.46, 0.21)},
                  0.70, "closed_1d")["J4 MDD 악화<=5%p"])
chk("J5 train 열세 탈락",
    not vcb.judge({"current": R(0.10, -0.30, 0.33), "closed_1d": R(0.09, -0.30, 0.30)},
                  ho, 0.70, "closed_1d")["J5 train 도 우위"])

print("§7 동결 상수 / 배포 금지")
chk("DEPLOY_ON_PASS False", vcb.DEPLOY_ON_PASS is False)
chk("분할은 validate_portfolio 와 공유", vcb.SPLIT == vp.SPLIT == "2025-01-01")
chk("J3/J4 문턱 공유", vcb.J3_WIN == vp.J3_WIN and vcb.J4_MDD_TOL == vp.J4_MDD_TOL)
chk("슬로틱 6개 → 틱 0..5", vcb.TICKS_1D == [0, 1, 2, 3, 4, 5])
chk("슬로틱은 scheduler 와 같다", tuple(h // 4 for h in sch.SLOW_TICK_HOURS) == tuple(vcb.TICKS_1D))
chk("부트 블록 30일", vcb.BLOCK_DAYS == 30)
chk("사이징 상수는 실거래 고정", vcb.MAX_POS == 13)

print(f"\n{'='*60}\n통과 {ok} / 실패 {fail}\n{'='*60}")
raise SystemExit(1 if fail else 0)
