"""
test_forming_bar.py — validate_forming_bar 로직 고정 (네트워크 없음)

이 시험은 '부분봉을 정확히 만들었는가'와 '청산 로직을 복제하지 않았는가' 둘에 걸려 있다.
그래서 고정하는 것도 그 둘이다 — 하위 TF 합산이 상위 봉과 **정확히** 같은지,
outcome_at 이 base 만 갈아 끼우고 method_t.outcome_d 를 그대로 쓰는지.
셀 목록은 기억이 아니라 **universe.json 실상**과 대조해 고정한다.
"""
import json
from datetime import date, timedelta

import method_t as mt
import validate_forming_bar as vfb

ok = fail = 0


def chk(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
    else:
        fail += 1
        print(f"  FAIL {name} {extra}")


D1, H4, H1 = 86400000, 14400000, 3600000
BASE_TS = 1735689600000          # 2025-01-01 00:00 UTC


def bar(ts, o, h, l, c, v=100.0, tf_ms=D1):
    return dict(ts=ts, date=date.fromtimestamp(ts / 1000).isoformat(),
                o=o, h=h, l=l, c=c, v=v)


print("§1 bucket — 하위 봉을 상위 봉 시작 ts 로 묶는다")
kids4 = [bar(BASE_TS + i * H4, 10 + i, 11 + i, 9 + i, 10.5 + i, tf_ms=H4) for i in range(12)]
b = vfb.bucket(kids4, D1)
chk("이틀치가 두 버킷", sorted(b) == [BASE_TS, BASE_TS + D1])
chk("하루에 6봉", len(b[BASE_TS]) == 6 and len(b[BASE_TS + D1]) == 6)
chk("버킷 안 정렬", [r["ts"] for r in b[BASE_TS]] == [BASE_TS + i * H4 for i in range(6)])
chk("ts 없는 행은 버린다", vfb.bucket([{"o": 1}], D1) == {})
b1 = vfb.bucket([bar(BASE_TS + i * H1, 1, 2, 0.5, 1.5, tf_ms=H1) for i in range(8)], H4)
chk("1h → 4h 버킷", sorted(b1) == [BASE_TS, BASE_TS + H4] and len(b1[BASE_TS]) == 4)

print("§2 partial — 합산이 상위 봉과 정확히 같아야 한다")
cs = b[BASE_TS]
parent = bar(BASE_TS, cs[0]["o"], max(c["h"] for c in cs), min(c["l"] for c in cs), cs[-1]["c"])
full = vfb.partial(cs, len(cs), parent)
chk("k=전체면 상위 봉과 OHLC 일치",
    (full["o"], full["h"], full["l"], full["c"])
    == (parent["o"], parent["h"], parent["l"], parent["c"]),
    f"{full} vs {parent}")
chk("k=전체면 거래량도 합", abs(full["v"] - sum(c["v"] for c in cs)) < 1e-9)
e = vfb.partial(cs, 0, parent)
chk("k=0 은 빈 봉(o=h=l=c)", e["o"] == e["h"] == e["l"] == e["c"] == cs[0]["o"])
chk("k=0 은 거래량 0", e["v"] == 0.0)
chk("k=0 은 몸통 0 — 캔들 패턴이 성립할 수 없다", e["c"] - e["o"] == 0)
p2 = vfb.partial(cs, 2, parent)
chk("k=2 종가 = 두 번째 하위 봉 종가", p2["c"] == cs[1]["c"])
chk("k=2 고가 = 두 봉 최고", p2["h"] == max(cs[0]["h"], cs[1]["h"]))
chk("k=2 시가 = 첫 봉 시가", p2["o"] == cs[0]["o"])
chk("부분봉이 date 등 나머지 필드를 유지", p2["date"] == parent["date"] and p2["ts"] == parent["ts"])
chk("children 없고 k=0 이면 parent 시가", vfb.partial([], 0, parent)["c"] == parent["o"])

print("§3 fires / window_ok — 꼬리만 봐도 같은 답이 나오는가")
rows = [bar(BASE_TS + i * D1, 10, 12, 8, 10 + (i % 3)) for i in range(200)]


def det_local(rs):                                  # 직전 봉보다 종가가 높은 봉
    return [i for i in range(1, len(rs)) if rs[i]["c"] > rs[i - 1]["c"]]


def det_far(rs):                                    # WINDOW 보다 먼 과거를 본다
    return [i for i in range(len(rs)) if i >= 150 and rs[i]["c"] > rs[0]["c"]]


chk("국소 디텍터는 창 충분", vfb.window_ok(det_local, rows))
chk("원거리 디텍터는 창 불충분", not vfb.window_ok(det_far, rows))
chk("fires 는 마지막 봉만 본다",
    vfb.fires(det_local, rows, 50, dict(rows[50], c=rows[49]["c"] + 1))
    and not vfb.fires(det_local, rows, 50, dict(rows[50], c=rows[49]["c"] - 1)))

print("§4 forming_signals — 한 봉에 첫 발화 한 번만")
kids_all = []
for i in range(200):
    for k in range(6):
        # 하루 6개 4h 봉: 종가가 k 에 따라 올라간다 → 이른 틱에서는 조건 미달
        kids_all.append(bar(BASE_TS + i * D1 + k * H4, 10, 12, 8, 9 + k * 0.5, tf_ms=H4))
kd = vfb.bucket(kids_all, D1)
sig = vfb.forming_signals(det_local, rows, kd, "1d", [0, 1, 2, 3, 4, 5])
chk("결과는 {봉: (틱, 종가)}", all(isinstance(v, tuple) and len(v) == 2 for v in sig.values()))
chk("각 봉당 최대 하나", len(sig) == len(set(sig)))
for i, (k, px) in sig.items():
    chk_px = vfb.partial(kd[BASE_TS + i * D1], k, rows[i])["c"]
    chk(f"진입가=그 틱 부분봉 종가(bar {i})", abs(px - chk_px) < 1e-12)
    break
# 조기 틱에서 이미 조건을 만족하면 거기서 멈춘다
early = vfb.forming_signals(lambda rs: [len(rs) - 1], rows, kd, "1d", [0, 1, 2, 3, 4, 5])
chk("항상 참인 디텍터는 전부 틱 0", all(k == 0 for k, _ in early.values()))
chk("항상 참이면 모든 봉에서 발화", len(early) == len(rows) - 1)
chk("하위 봉 없는 봉은 건너뛴다",
    vfb.forming_signals(lambda rs: [len(rs) - 1], rows, {}, "1d", [0]) == {})

print("§5 outcome_at — 청산 로직을 복제하지 않는다")
up = [bar(BASE_TS + i * D1, 100, 101, 99, 100 + i) for i in range(40)]
# 단일 레짐 맵 — 레짐 전환 청산이 발동하지 않으면서 '빈 REGMAP' 경고도 피한다
# (빈 맵이면 레짐 청산이 조용히 꺼진다: 2026-09-21 결함, test_port_vol §6 이 그것을 고정).
mt.REGMAP = {r["date"]: "bull_btc" for r in up}
a = vfb.outcome_at(up, 5, "long", set(), up[5]["c"])
b_ = mt.outcome_d(up, 5, "long", set())
chk("base 가 같으면 outcome_d 와 완전히 동일", a == b_, f"{a} vs {b_}")
hi = vfb.outcome_at(up, 5, "long", set(), up[5]["c"] * 1.02)
chk("롱이 비싸게 들어가면 수익이 낮다", hi[0] < a[0], f"{hi[0]} vs {a[0]}")
lo = vfb.outcome_at(up, 5, "long", set(), up[5]["c"] * 0.98)
chk("롱이 싸게 들어가면 수익이 높다", lo[0] > a[0])
chk("원본 rows 를 훼손하지 않는다", up[5]["c"] == 105)
sh = vfb.outcome_at(up, 5, "short", set(), up[5]["c"] * 1.02)
chk("숏은 부호가 반대", sh[0] > mt.outcome_d(up, 5, "short", set())[0])

print("§6 judge — 세 조건과 표본 게이트")
good = dict(forming=dict(n=100, mean=0.02), closed=dict(n=100, mean=0.022),
            only_forming_ratio=0.05)
chk("아무것도 안 걸림", vfb.judge(good) == [])
chk("(i) 20% 정확히 발화",
    any(h.startswith("(i)") for h in vfb.judge(dict(good, only_forming_ratio=0.20))))
chk("(i) 19% 는 미발화",
    not any(h.startswith("(i)") for h in vfb.judge(dict(good, only_forming_ratio=0.19))))
drop = dict(good, closed=dict(n=100, mean=0.030), forming=dict(n=100, mean=0.020))
chk("(ii) 1.0%p 하락 정확히 발화", any(h.startswith("(ii)") for h in vfb.judge(drop)))
chk("(ii) 0.9%p 는 미발화",
    not any(h.startswith("(ii)") for h in
            vfb.judge(dict(good, closed=dict(n=100, mean=0.029), forming=dict(n=100, mean=0.020)))))
chk("(iii) forming 음수 발화",
    any(h.startswith("(iii)") for h in vfb.judge(dict(good, forming=dict(n=100, mean=-0.001)))))
chk("표본 부족이면 판정 안 함",
    vfb.judge(dict(good, forming=dict(n=19, mean=-0.5), only_forming_ratio=1.0)) == [])
chk("closed 표본 부족이면 (ii) 미발화",
    not any(h.startswith("(ii)") for h in
            vfb.judge(dict(drop, closed=dict(n=5, mean=0.030)))))

print("§7 셀 목록 — 기억이 아니라 universe.json 실상과 대조")
uni = json.load(open("universe.json", encoding="utf-8"))
closed_4h = {a["pattern"] for a in uni.get("adopted_4h_patterns", [])
             if a.get("detect_on_closed_bar")}
all_4h = {a["pattern"] for a in uni.get("adopted_4h_patterns", [])}
cells = {c[0] for c in vfb.CELLS}
chk("닫힌 봉으로 도는 4h 패턴은 셀에 없다", not (closed_4h & cells), f"{closed_4h & cells}")
chk("forming 으로 도는 4h 패턴은 전부 셀에 있다",
    (all_4h - closed_4h) <= cells, f"빠진 것 {(all_4h - closed_4h) - cells}")
chk("adopted_1h(=_closed_idx) 는 셀에 없다",
    not ({a["pattern"] for a in uni.get("adopted_1h_patterns", [])} & cells))
chk("1d FOCUS 4셀 포함", {"engulfing", "engulfing_short", "fvg", "fvg_short"} <= cells)
chk("adopted 1d 2셀 포함", {"inverted_hammer", "marubozu"} <= cells)
chk("셀 7개", len(vfb.CELLS) == 7)
chk("1d 셀은 6틱, 4h 셀은 4h 경계와 일치",
    len(vfb.SLOW_TICK_HOURS) == 6 and vfb.SLOW_TICK_HOURS == (0, 4, 8, 12, 16, 20))
chk("코호트가 실거래 규칙과 같다",
    {c[0]: c[5] for c in vfb.CELLS}["engulfing"] == "top30"
    and {c[0]: c[5] for c in vfb.CELLS}["inverted_hammer"] == "majors")

print("§8 동결 상수 / 배포 금지")
chk("DEPLOY_ON_PASS False", vfb.DEPLOY_ON_PASS is False)
chk("(i) 문턱 20%", vfb.MAT_ONLY_FORMING == 0.20)
chk("(ii) 문턱 1.0%p", vfb.MAT_DROP == 0.010)
chk("최소 표본 20", vfb.MIN_N == 20)
chk("창 1d 1800 / 4h 1100 / 1h 365",
    vfb.FETCH_WINDOWS == {"1d": 1800, "4h": 1100, "1h": 365})
chk("하위 TF 매핑", vfb.SUB_TF == {"1d": "4h", "4h": "1h"})
chk("BAR_MS", vfb.BAR_MS["1d"] == 86400000 and vfb.BAR_MS["4h"] == 14400000)

print(f"\n{'='*60}\n통과 {ok} / 실패 {fail}\n{'='*60}")
raise SystemExit(1 if fail else 0)
