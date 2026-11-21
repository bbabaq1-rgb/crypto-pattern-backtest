"""
test_turtle_soup.py — R-009 Turtle Soup 4h 로직 검증 (합성 데이터, 네트워크 없음).
고정: 정의대로만 발화 / 인과성 / MIN_AGE / liquidity_sweep 과 신호 집합 차이 / 겹침 함수 / 주 판정 셀 / 실거래 비임포트.
실행: python test_turtle_soup.py
"""
import re
import sys

import detector_turtle_soup_4h as ts
import detector_liquidity_sweep as ls
import validate_turtle_soup as vt

fails = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f" — {detail}"))
    cond or fails.append(name)


def bar(i, l, c, h=None):
    return dict(ts=i * 14400000, date="2024-01-01", o=c, h=h if h is not None else max(l, c) + 1, l=l, c=c, v=100.0)


# 20봉 평탄(저가 100, 최저는 맨 앞쪽) 뒤 이탈-복귀
base = [bar(i, 100 + (0 if i == 2 else 5), 106) for i in range(20)]
rows = base + [bar(20, 98, 101)]
check("발화: 20봉 저점 이탈 후 같은 봉 복귀", ts.detect(rows) == [20], ts.detect(rows))
rows_b = base + [bar(20, 98, 99)]
check("미발화: 종가가 저점 아래면 아님", ts.detect(rows_b) == [], ts.detect(rows_b))
rows_c = base + [bar(20, 101, 103)]
check("미발화: 저점 이탈 없음", ts.detect(rows_c) == [], ts.detect(rows_c))
# MIN_AGE: 최저가가 직전 3봉 안(17~19번)이면 미발화
young = [bar(i, 105, 106) for i in range(17)] + [bar(17, 100, 106), bar(18, 105, 106), bar(19, 105, 106)] + [bar(20, 98, 101)]
check("MIN_AGE: 저점이 3봉 전이면 미발화", ts.detect(young) == [], ts.detect(young))
old = [bar(i, 105, 106) for i in range(16)] + [bar(16, 100, 106)] + [bar(i, 105, 106) for i in range(17, 20)] + [bar(20, 98, 101)]
check("MIN_AGE: 저점이 4봉 전이면 발화", ts.detect(old) == [20], ts.detect(old))
# 인과성: 뒤 봉을 바꿔도 앞 신호 불변
ext = rows + [bar(21, 50, 60)]
check("인과성: 뒤 봉 추가가 앞 신호를 안 바꾼다", ts.detect(ext)[:1] == [20])
check("계약: detect(rows)->list[int], 짧은 입력 안전", ts.detect(rows[:5]) == [])
check("동결 상수", ts.LOOKBACK == 20 and ts.MIN_AGE == 4)

# liquidity_sweep 과 신호 집합이 다르다: 단일 저점(풀 아님)·거래량 평범 → turtle 만 발화
sw = ls.detect_sweeps([dict(date="2024-01-01", h=r["h"], l=r["l"], c=r["c"], v=r["v"]) for r in rows])
check("sweep 과 차이: 같은 합성에서 turtle 발화·sweep 미발화", ts.detect(rows) == [20] and sw == [], sw)

# 겹침 함수
check("overlap: 창 안", vt.overlap([10, 50], [12]) == 0.5)
check("overlap: 빈 a → None", vt.overlap([], [1]) is None)
check("overlap: 창 밖", vt.overlap([10], [20]) == 0.0)

# 판정: 주 판정 셀 하나, 없으면 INCONCLUSIVE
check("판정 셀 고정", vt.PRIMARY == ("turtle_soup_4h", "ALL") and vt.DEPLOY_ON_PASS is True)
v, _ = vt.judge({})
check("주 판정 셀 없으면 INCONCLUSIVE", v == "INCONCLUSIVE")
v, _ = vt.judge({"turtle_soup_4h|ALL": {"confirm_v3": {"verdict": "CONFIRMED"}}})
check("CONFIRMED 전달", v == "CONFIRMED")

# 실거래 코드가 이 모듈을 import 하지 않는다
for f in ("scheduler.py", "paper_executor.py", "exchange.py"):
    src = open(f, encoding="utf-8").read()
    check(f"{f} 가 turtle_soup 를 import 하지 않음(검증 전)", not re.search(r"turtle_soup", src))

print(f"\n{'ALL PASS' if not fails else 'FAILED: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
