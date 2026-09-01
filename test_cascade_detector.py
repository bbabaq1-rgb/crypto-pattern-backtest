"""
detector_cascade_fade_1h 검증 (데이터 수집 없이 합성 봉으로).

가장 중요한 확인: **검증에 쓴 탐지 조건과 완전히 동일한가.**
`validate_cascade.py` 의 인라인 조건과 신호 집합이 한 건이라도 어긋나면, 실거래로
나가는 신호가 통계를 낸 신호와 다른 것이므로 검증이 무효가 된다.

두 번째: **마지막 봉을 검사하는가.** 백테스트 탐지는 라벨링에 필요한 전방 데이터
때문에 뒤를 잘라내지만, 스케줄러는 `last in detect(rows)` 를 보므로 뒤를 자르면
실거래 신호가 영영 발생하지 않는다.

실행: python test_cascade_detector.py
"""
import random
import sys

import detector_cascade_fade_1h as det
import intraday_lab as lab
import validate_cascade as vc

fails = []


def chk(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f" — {detail}"))
    if not cond:
        fails.append(name)


def mkrows(n=400, seed=1):
    """랜덤워크 + 무작위로 캐스케이드형 봉을 심는다."""
    random.seed(seed)
    rows, px, ts = [], 100.0, 1600000000000
    for i in range(n):
        if i > 30 and random.random() < 0.05:          # 캐스케이드 후보
            lo = px * (1 - random.uniform(0.03, 0.08))
            c = lo + (px - lo) * random.uniform(0.2, 0.9)   # 회복 정도 랜덤
            rows.append(dict(ts=ts, dt=None, date=f"2026-01-{1+i//24:02d}",
                             hour=i % 24, o=px, h=px * 1.001, l=lo, c=c,
                             v=random.uniform(200, 600)))
            px = c
        else:
            nxt = px * (1 + random.gauss(0, 0.004))
            rows.append(dict(ts=ts, dt=None, date=f"2026-01-{1+i//24:02d}",
                             hour=i % 24, o=px, h=max(px, nxt) * 1.001,
                             l=min(px, nxt) * 0.999, c=nxt,
                             v=random.uniform(80, 120)))
            px = nxt
        ts += 3600000
    return rows


def validated_detect(rows):
    """validate_cascade.py 의 탐지 조건을 그대로 옮긴 참조 구현(전방 컷 포함)."""
    H = lab.HORIZON["1h"]
    atr = lab.atr_series(rows)
    out = []
    for i in range(25, len(rows) - H - 1):
        a = atr[i]
        if not a:
            continue
        r0 = rows[i]
        rng = r0["h"] - r0["l"]
        if rng <= 0:
            continue
        move = r0["c"] - r0["o"]
        if move >= 0 or abs(move) < vc.MOVE_ATR * a:
            continue
        vavg = sum(x["v"] for x in rows[i - 20:i]) / 20
        if vavg <= 0 or r0["v"] < vavg * vc.VOL_MULT:
            continue
        if (r0["c"] - r0["l"]) / rng < vc.RECOVER:
            continue
        out.append(i)
    return out


# ── 1. 동결 파라미터가 검증 스크립트와 일치 ─────────────────────────────────
chk("MOVE_ATR 일치", det.MOVE_ATR == vc.MOVE_ATR, (det.MOVE_ATR, vc.MOVE_ATR))
chk("VOL_MULT 일치", det.VOL_MULT == vc.VOL_MULT, (det.VOL_MULT, vc.VOL_MULT))
chk("RECOVER 일치", det.RECOVER == vc.RECOVER, (det.RECOVER, vc.RECOVER))

# ── 2. ATR 계산이 검증 프레임과 동일 ────────────────────────────────────────
rows = mkrows(400, seed=7)
a_det, a_lab = det._atr(rows), lab.atr_series(rows)
chk("ATR 이 intraday_lab.atr_series 와 동일",
    all((x is None and y is None) or (x is not None and y is not None
        and abs(x - y) < 1e-12) for x, y in zip(a_det, a_lab)))

# ── 3. 신호 집합이 검증 조건과 일치 (핵심) ──────────────────────────────────
H = lab.HORIZON["1h"]
total_ref = total_got = 0
for s in range(12):
    r = mkrows(400, seed=100 + s)
    ref = validated_detect(r)
    got = [i for i in det.detect(r) if i < len(r) - H - 1]   # 같은 구간만 비교
    total_ref += len(ref)
    total_got += len(got)
    if ref != got:
        chk(f"신호 집합 일치 (seed {100+s})", False, f"참조 {ref[:6]} vs 실제 {got[:6]}")
        break
else:
    chk(f"신호 집합이 검증 조건과 완전 일치 (12개 시드, 참조 {total_ref}건)",
        total_ref == total_got and total_ref > 0, (total_ref, total_got))

# ── 4~5. 마지막 봉 탐지 + 조건별 배제 ───────────────────────────────────────
# 주의: 마지막 봉을 교체하면 그 봉의 TR 이 ATR14 에 반영돼 MOVE_ATR 문턱도 함께
# 올라간다(가짜 캐스케이드를 심으면 문턱이 같이 커져 자기상쇄). 그래서 하락폭을
# ATR 대비 넉넉히(5배) 잡아 교체 후에도 조건을 확실히 넘도록 구성한다.
base = mkrows(200, seed=3)
a = det._atr(base)[-1]
pc = base[-2]["c"]
va = sum(x["v"] for x in base[-21:-1]) / 20


def variant(drop_a=5.0, wick_a=5.0, vol_mult=5.0, green=False):
    """마지막 봉을 합성 캐스케이드로 교체하고 탐지 여부를 반환.

    drop_a : 시가→종가 하락폭 (ATR 배수)
    wick_a : 종가→저가 아래꼬리 (ATR 배수) — 회복비율 = wick/(drop+wick)
    green  : True 면 양봉으로 만든다
    """
    r = list(base)
    o = pc
    c = pc - drop_a * a
    lo = c - wick_a * a
    if green:
        o, c = c, o                       # 시가·종가를 바꿔 양봉으로
    r[-1] = dict(r[-1], o=o, h=pc * 1.0005, l=lo, c=c, v=va * vol_mult)
    return (len(r) - 1) in det.detect(r)


chk("마지막 봉의 캐스케이드를 탐지(스케줄러 필수)", variant())

# 참조 구현은 전방 컷 때문에 마지막 봉을 절대 못 잡는다 — 차이를 명시적으로 확인
r_last = list(base)
r_last[-1] = dict(r_last[-1], o=pc, h=pc * 1.0005, l=pc - 10 * a,
                  c=pc - 5 * a, v=va * 5)
chk("참조(백테스트) 구현은 마지막 봉을 못 잡음(전방 컷)",
    (len(r_last) - 1) not in validated_detect(r_last))

chk("하락폭 부족(1ATR)이면 미탐지", not variant(drop_a=1.0, wick_a=1.0))
chk("거래량 부족(2배)이면 미탐지", not variant(vol_mult=2.0))
chk("회복 부족(종가가 저가 근처)이면 미탐지", not variant(wick_a=0.5))
chk("양봉이면 미탐지", not variant(green=True))

# ── 6. 안전성 ───────────────────────────────────────────────────────────────
chk("짧은 데이터에서 빈 리스트", det.detect(base[:10]) == [])
chk("evaluate 를 노출하지 않음(동결 라벨 오적용 방지)", not hasattr(det, "evaluate"))
chk("스케줄러가 쓰는 진입점 존재",
    hasattr(det, "load_ohlcv") and hasattr(det, "detect"))

# ── 7. 스케줄러 연결 — 손절 표기가 실제 집행값과 같은가 ─────────────────────
# 스케줄러가 ±8% 로 표기하면 알림·대시보드가 실제 집행(±1.5xATR ≈ 0.75~1.5%)과
# 5~10배 어긋난다. exit_spec 패턴은 ATR 로, 나머지는 종전 ±8% 로 나와야 한다.
import paper_executor as pe
import scheduler as sch

specs_sch, specs_pe = sch._exit_specs(), pe.EXIT_SPECS
chk("스케줄러와 체결엔진이 같은 exit_spec 을 본다",
    set(specs_sch) == set(specs_pe), (set(specs_sch), set(specs_pe)))
chk("exit_spec 보유는 cascade 하나뿐",
    set(specs_sch) == {"cascade_fade_long_1h"}, set(specs_sch))

# 배포된 1h 패턴은 exit_spec 이 없어야 한다 = 청산 규칙 불변
for legacy in ("bat_1h", "butterfly_1h"):
    chk(f"{legacy} 는 ATR 경로로 새지 않음", legacy not in specs_sch)

# 같은 봉에서 두 쪽이 계산한 손절가가 일치하는지 (수치 확인)
spec = specs_sch["cascade_fade_long_1h"]
r = mkrows(300, seed=11)
li = len(r) - 1
atr_sch = lab.atr_series(r, spec.get("atr_period", 14))[li]
entry = r[li]["c"]
dist = spec.get("k_atr", 1.5) * atr_sch
stop_sch = entry - dist
# paper_executor 진입 경로와 동일한 산식
atr_pe = pe.ilab.atr_series(r, spec.get("atr_period", 14))[li]
stop_pe = entry - spec.get("k_atr", 1.5) * atr_pe
chk("스케줄러 손절가 == 체결엔진 손절가", abs(stop_sch - stop_pe) < 1e-12,
    (stop_sch, stop_pe))
chk("ATR 손절폭이 ±8% 보다 훨씬 좁다(검증치 수준)",
    dist / entry < 0.04, f"{dist/entry:.4%}")

# registry 의 청산 규격이 검증치와 같은지 (틀리면 다른 전략이 돈다)
chk("exit_spec 이 검증치와 일치 (1.5xATR14 / 12봉)",
    spec.get("k_atr") == 1.5 and spec.get("atr_period") == 14
    and spec.get("horizon_bars") == lab.HORIZON["1h"], spec)

# ── 8. 미배포 상태 확인 (검증이 기각한 조건으로 돌면 안 된다) ────────────────
import json as _json
uni = _json.load(open("universe.json", encoding="utf-8"))
adopted = [a.get("pattern") for a in uni.get("adopted_1h_patterns", [])]
chk("cascade 는 adopted_1h_patterns 에 등록되지 않음(진입 지연 미해결)",
    "cascade_fade_long_1h" not in adopted, adopted)

reg = _json.load(open("registry.json", encoding="utf-8"))
casc = next((p for p in reg["patterns"] if p.get("id") == "cascade_fade_long_1h"), None)
chk("registry status 가 passed_not_deployed",
    casc and casc.get("status") == "passed_not_deployed",
    casc.get("status") if casc else None)

print("\n실패", len(fails), "건" if fails else "— 전체 통과")
sys.exit(1 if fails else 0)
