"""
method_t 로직 검증 (데이터 수집 없이 합성 봉으로).

확인 대상:
  - 고정 익절이 봉 내 고저로 정확히 체결되는가 / 손절 우선 규칙
  - 방식D는 익절이 없다는 사실(비교 기준이 맞는가)
  - 자산곡선이 '자본 회전율에 따른 복리 차이'를 실제로 잡아내는가
    (건당 수익이 같아도 빨리 도는 쪽 최종자산이 커야 한다)

실행: python test_method_t.py
"""
import sys

import method_t as mt

fails=[]
def check(n,c,d=""):
    print(("PASS " if c else "FAIL ")+n+("" if c else f" — {d}")); c or fails.append(n)

def bar(o,h,l,c,d="2026-01-01"): return dict(date=d,o=o,h=h,l=l,c=c,v=1)
mt.REGMAP = {}   # 레짐 전환 없음

# 평탄한 바 + 특정 봉만 조작
def mk(n=40, d0=1):
    from datetime import date, timedelta
    return [bar(100,100.5,99.5,100, (date(2026,1,1)+timedelta(days=i)).isoformat()) for i in range(n)]

# 1) 익절 도달
rows = mk(); rows[5] = dict(rows[5], h=125.0)
r,h,why = mt.outcome_d(rows,0,"long",set(),0.20)
check("익절 +20% 도달 시 tp_fixed", why=="tp_fixed" and h==5, (r,h,why))
check("익절 수익 = 0.20 - 수수료", abs(r-(0.20-mt.FEE))<1e-12, r)

# 2) 익절 미달 (+15%만) -> T20은 미체결, T10/T15는 체결
rows = mk(); rows[5] = dict(rows[5], h=115.0)
check("+15% 고점에 T20 미체결", mt.outcome_d(rows,0,"long",set(),0.20)[2]!="tp_fixed")
check("+15% 고점에 T15 체결",   mt.outcome_d(rows,0,"long",set(),0.15)[2]=="tp_fixed")
check("+15% 고점에 T10 체결",   mt.outcome_d(rows,0,"long",set(),0.10)[2]=="tp_fixed")

# 3) 같은 봉에서 손절·익절 동시 -> 손절 우선(보수적)
rows = mk(); rows[3] = dict(rows[3], h=125.0, l=85.0)
r,h,why = mt.outcome_d(rows,0,"long",set(),0.20)
check("동시 터치 시 손절 우선", why=="stop" and abs(r-(-0.08-mt.FEE))<1e-12, (r,why))

# 4) 방식D는 익절 없음 -> 같은 데이터에서 maxhold까지 감
rows = mk(); rows[5] = dict(rows[5], h=125.0)
check("방식D는 +25% 고점을 무시(익절 없음)", mt.outcome_d(rows,0,"long",set(),None)[2]=="maxhold")

# 5) 숏 방향
rows = mk(); rows[4] = dict(rows[4], l=75.0)
r,h,why = mt.outcome_d(rows,0,"short",set(),0.20)
check("숏 익절(하락 -20%) 체결", why=="tp_fixed" and abs(r-(0.20-mt.FEE))<1e-12, (r,why))

# 6) 짝지음 통계
p = mt.paired_stats([0.0,0.0,0.0,0.0],[0.01,0.01,0.01,0.01])
check("짝지음 평균차이", abs(p["mean_diff"]-0.01)<1e-12 and p["wins"]==4, p)

# 7) 자산곡선: 회전율 효과 — 같은 건당수익이면 빨리 도는 쪽이 최종자산 큼
slow = [("2020-01-01","2020-12-31",0.10,0,"x")]
fast = [("2020-01-01","2020-03-31",0.10,0,"x"), ("2020-04-01","2020-06-30",0.10,0,"x"),
        ("2020-07-01","2020-09-30",0.10,0,"x"), ("2020-10-01","2020-12-31",0.10,0,"x")]
es, ef = mt.equity_curve(slow), mt.equity_curve(fast)
check("회전율 높은 쪽 최종자산이 큼(복리 포착)", ef["final"] > es["final"], (es["final"], ef["final"]))
print(f"  느림 최종 ${es['final']:.2f} / 빠름 최종 ${ef['final']:.2f}")

# 8) 자산곡선 산수: $1000, 20%=$200, 2x, +10% -> +$40
one = mt.equity_curve([("2020-01-01","2020-01-31",0.10,0,"x")])
check("복리 산수 (1000 -> 1040)", abs(one["final"]-1040.0)<1e-9, one["final"])

# 9) 최대 포지션 상한
many = [(f"2020-01-01", "2020-06-01", 0.05, 0, "x") for _ in range(20)]
em = mt.equity_curve(many)
check("동시 포지션 12개 상한", em["n_taken"]==12 and em["n_skipped"]==8, em)

# 10) MDD 음수 기록
loss = [("2020-01-01","2020-02-01",-0.30,0,"x"), ("2020-03-01","2020-04-01",0.50,0,"x")]
el = mt.equity_curve(loss)
check("MDD가 음수로 기록됨", el["mdd"] < 0, el["mdd"])

# 11) 단조성 판정
check("단조 증가 판정", mt.monotonic([1,2,3])=="증가")
check("비단조 판정", mt.monotonic([1,3,2])=="비단조")

print("\n실패", len(fails))
sys.exit(1 if fails else 0)
