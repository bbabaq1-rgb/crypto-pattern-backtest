"""
validate_cascade_delay 로직 검증 (데이터 수집 없이 합성 봉으로).

핵심 확인:
  - 스케줄러 격자 지연 계산이 실제 배포 환경(4h cron + 큐 지연)을 맞게 재현하는가
  - d=0 이 1차 검증 라벨과 완전히 동일한가 (정합성 — 이게 깨지면 비교 자체가 무의미)

실행: python test_cascade_delay.py
"""
import random
import sys
from datetime import datetime, timezone

import intraday_lab as lab
import validate_cascade_delay as vcd

fails = []


def chk(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f" — {detail}"))
    if not cond:
        fails.append(name)


def ts(h, day=1):
    return int(datetime(2026, 1, day, h, 0, tzinfo=timezone.utc).timestamp() * 1000)


# ── 스케줄러 격자 지연 ──────────────────────────────────────────────────────
# 01:00 신호 → 02:00 마감 → 다음 틱 04:00 → +30분 = 04:30 → 04:00봉(i+3)
chk("01시 신호 +30분 지터 → 3봉", vcd.sched_delay_bars(ts(1), 30) == 3)
chk("01시 신호 +90분 지터 → 4봉", vcd.sched_delay_bars(ts(1), 90) == 4)
# 03:00 신호 → 04:00 마감 → 틱 04:00 → +10분 → 04:00봉(i+1) : 최선의 경우
chk("03시 신호 +10분 지터 → 1봉(최선)", vcd.sched_delay_bars(ts(3), 10) == 1)
# 21:00 신호 → 22:00 마감 → 당일 틱 없음 → 익일 00:00
chk("21시 신호 +30분 지터 → 3봉(익일 틱)", vcd.sched_delay_bars(ts(21), 30) == 3)
chk("20시 신호 +90분 지터 → 5봉(최악)", vcd.sched_delay_bars(ts(20), 90) == 5)

allv = [vcd.sched_delay_bars(ts(h), j) for h in range(24) for j in vcd.JITTERS_MIN]
chk("지연이 항상 1봉 이상(즉시 진입 불가)", min(allv) >= 1, min(allv))
chk("지연 상한 6봉 이내", max(allv) <= 6, max(allv))
print(f"  전 시각·지터 평균 지연 {sum(allv)/len(allv):.2f}봉 "
      f"(범위 {min(allv)}~{max(allv)}봉)")

# ── d=0 정합성 ──────────────────────────────────────────────────────────────
random.seed(3)
rows, px, t = [], 100.0, ts(0)
for i in range(200):
    nx = px * (1 + random.gauss(0, 0.008))
    rows.append(dict(ts=t, dt=None, date=f"2026-01-{1+i//24:02d}", hour=i % 24,
                     o=px, h=max(px, nx) * 1.002, l=min(px, nx) * 0.998,
                     c=nx, v=100.0))
    px, t = nx, t + 3600000
atr = lab.atr_series(rows)

same = all(
    abs(vcd.delayed_outcome(rows, atr, i, 0)[1]
        - lab.outcome_atr(rows, i, "long", atr, vcd.H)[1]) < 1e-15
    for i in range(20, 150))
chk("d=0 은 1차 검증 라벨과 완전 동일", same)

e3 = vcd.delayed_outcome(rows, atr, 50, 3)
chk("d=3 은 진입봉이 3봉 뒤로 이동", e3[0] == rows[53]["date"], e3[0])

# 데이터 끝 부근은 None (배리어 평가 불가)
chk("데이터 끝에서는 None 반환",
    vcd.delayed_outcome(rows, atr, len(rows) - 2, 5) is None)

print("\n실패", len(fails), "건" if fails else "— 전체 통과")
sys.exit(1 if fails else 0)
