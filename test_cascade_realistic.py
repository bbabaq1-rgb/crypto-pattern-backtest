"""
validate_cascade_realistic 로직 검증 (네트워크·데이터 없이).

가장 중요한 확인 두 가지.
  1) `delay_bars` 가 이미 검증된 `validate_cascade_delay.sched_delay_bars` 와
     4h 격자에서 완전히 같은 값을 낸다 — 다르면 두 리포트의 4h 행이 서로
     비교 불가능해진다.
  2) 지연 0 arm 이 1차 검증 라벨(`intraday_lab.outcome_atr`)과 **수익률이
     정확히 일치**한다 — d=0 이 재현되지 않으면 나머지 행의 기준선이 없다.

실행: python test_cascade_realistic.py
"""
import random
import sys
from datetime import datetime, timezone

import intraday_lab as lab
import validate_cascade_delay as vcd
import validate_cascade_realistic as vcr

fails = []


def chk(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f" — {detail}"))
    if not cond:
        fails.append(name)


def ts_at(hour, day=1):
    return int(datetime(2026, 1, day, hour, 0, tzinfo=timezone.utc).timestamp() * 1000)


# ── 1. 4h 격자에서 기존 구현과 동일 ─────────────────────────────────────────
same = True
for hour in range(24):
    for jit in vcd.JITTERS_MIN:
        a = vcr.delay_bars(ts_at(hour), 240, jit)
        b = vcd.sched_delay_bars(ts_at(hour), jit)
        if a != b:
            chk(f"4h 격자 일치 (h={hour}, jitter={jit})", False, f"{a} vs {b}")
            same = False
            break
    if not same:
        break
if same:
    chk("4h 격자가 validate_cascade_delay 와 24시간 x 4지터 전부 일치", True)

# ── 2. 1h 격자는 대기시간만이 변수 ──────────────────────────────────────────
# 1h 봉은 정시 마감 + 1h 크론도 정시 발화 → 격자 대기 0. 지연이 곧 진입 지연.
cases = [(1.0, 1), (16.0, 1), (59.9, 1), (60.1, 2), (91.5, 2), (172.9, 3),
         (231.5, 4)]
for wait, want in cases:
    got = vcr.delay_bars(ts_at(7), 60, wait)
    chk(f"1h 격자 지연 {wait}분 -> {want}봉", got == want, got)

# 자정 넘김 (23시 마감 = 다음날 00:00)
chk("23시 봉 + 16분 -> 1봉", vcr.delay_bars(ts_at(23), 60, 16.0) == 1)
chk("23시 봉 + 90분 -> 2봉", vcr.delay_bars(ts_at(23), 60, 90.0) == 2)
chk("23시 봉 4h격자 + 10분 -> 1봉", vcr.delay_bars(ts_at(23), 240, 10.0) == 1)

# 1h 격자가 4h 격자보다 절대 늦을 수 없다
worse = [(h, j) for h in range(24) for j in (10.0, 60.0, 172.9)
         if vcr.delay_bars(ts_at(h), 60, j) > vcr.delay_bars(ts_at(h), 240, j)]
chk("1h 격자가 4h 격자보다 늦어지는 경우 없음", not worse, worse[:3])

# 실측 표본 전부에서 1h 격자 지연이 0봉이 되지 않는다(최소 1봉 = 다음 봉 종가)
mins = {vcr.delay_bars(ts_at(5), 60, w) for w in vcr.MEASURED_DELAY_MIN}
chk("실측 지연 전 표본에서 1h 격자는 1봉 이상", min(mins) >= 1, sorted(mins))

# ── 3. 지연 0 arm 이 동결 라벨과 정확히 일치 ────────────────────────────────
def mkrows(n=300, seed=5):
    random.seed(seed)
    rows, px, ts = [], 100.0, ts_at(0)
    for _ in range(n):
        nxt = px * (1 + random.gauss(0, 0.006))
        rows.append(dict(ts=ts, dt=None,
                         date=datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
                         .strftime("%Y-%m-%d"),
                         hour=(ts // 3600000) % 24, o=px,
                         h=max(px, nxt) * 1.002, l=min(px, nxt) * 0.998, c=nxt,
                         v=100.0))
        px, ts = nxt, ts + 3600000
    return rows


rows = mkrows()
atr = lab.atr_series(rows)
H = lab.HORIZON["1h"]
diff = 0
for i in range(30, len(rows) - H - 2):
    if not atr[i]:
        continue
    got = vcr.outcome_at(rows, atr, i, 0, lab.FEE)
    _, want = lab.outcome_atr(rows, i, "long", atr, H, fee=lab.FEE)
    if want is None:
        continue
    if got is None or abs(got[1] - want) > 1e-15:
        diff += 1
chk("지연 0 = 동결 라벨 수익률 완전 일치", diff == 0, f"{diff}건 불일치")

# 지연 d 는 진입 봉만 뒤로 민다 = d봉 뒤 신호의 라벨과 같다
ok = True
for i in range(30, 60):
    if not atr[i] or not atr[i + 2]:
        continue
    got = vcr.outcome_at(rows, atr, i, 2, lab.FEE)
    _, want = lab.outcome_atr(rows, i + 2, "long", atr, H, fee=lab.FEE)
    if (got is None) != (want is None):
        ok = False
        break
    if got and abs(got[1] - want) > 1e-15:
        ok = False
        break
chk("지연 d봉 = i+d 봉 기준 배리어·보유한도 재계산", ok)

# 진입 날짜가 원 신호가 아니라 **진입 봉** 날짜로 기록된다(OOS 분위 정확성)
g = vcr.outcome_at(rows, atr, 40, 3, lab.FEE)
chk("OOS 분위용 날짜가 진입 봉 기준", g and g[0] == rows[43]["date"], g)

# 데이터 끝을 넘으면 None
chk("데이터 끝 초과 시 None", vcr.outcome_at(rows, atr, len(rows) - 2, 5,
                                             lab.FEE) is None)

# ── 4. 마찰이 커지면 수익이 정확히 그만큼 줄어든다 ──────────────────────────
lo = vcr.outcome_at(rows, atr, 50, 0, 0.002)
hi = vcr.outcome_at(rows, atr, 50, 0, 0.008)
chk("수수료 0.2%->0.8% 이면 수익 0.6%p 감소",
    lo and hi and abs((lo[1] - hi[1]) - 0.006) < 1e-12,
    (lo, hi))

# ── 5. 실측 표본 무결성 ─────────────────────────────────────────────────────
d = vcr.MEASURED_DELAY_MIN
chk("실측 표본 100건", len(d) == 100, len(d))
chk("실측 표본 오름차순", d == sorted(d))
chk("실측 표본 전부 양수", all(x > 0 for x in d))

# 부트스트랩 추출이 시드로 재현된다 (리포트 숫자의 재현성)
a = [random.Random(vcr.SEED).choice(d) for _ in range(3)]
b = [random.Random(vcr.SEED).choice(d) for _ in range(3)]
chk("시드 고정 추출 재현 가능", a == b)

# ── 6. 상수 동결 ────────────────────────────────────────────────────────────
import validate_cascade as vc
chk("탐지 파라미터가 동결값과 동일",
    (vcr.vc.MOVE_ATR, vcr.vc.VOL_MULT, vcr.vc.RECOVER) == (2.5, 3.0, 0.40))
chk("동결 수수료가 스윕 최저값", vcr.FEE_LEVELS[0] == lab.FEE)
chk("격자는 4h/1h 두 개", set(vcr.GRIDS.values()) == {240, 60})

print("\n실패", len(fails), "건" if fails else "— 전체 통과")
sys.exit(1 if fails else 0)
