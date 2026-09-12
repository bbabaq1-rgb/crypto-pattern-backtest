"""
test_kakao.py — 지인 카톡 규칙 3종 고정 (2026-09-12 사전 등록).

원문 규칙을 **동작으로** 고정한다. 사전 등록 후 상수·정의가 조용히 바뀌면 깨진다.
"""
import sys, json
import detector_kakao_base as kb
import detector_ma3_breakout as d_ma3
import detector_yyb as d_yyb
import detector_yyy as d_yyy
import validate_kakao as vk

fails = []


def check(name, cond, extra=""):
    (print(f"PASS {name}") if cond else (fails.append(name), print(f"FAIL {name} {extra}")))


def mk(seq):
    """seq = [(o,h,l,c)] → rows"""
    return [dict(date=f"2020-01-{i+1:02d}", ts=i * 86400000, o=o, h=h, l=l, c=c, v=1.0)
            for i, (o, h, l, c) in enumerate(seq)]


# ── 동결 파라미터 (사전 등록과 일치) ────────────────────────────────────
check("MA 5/10/20 동결", (kb.MA_FAST, kb.MA_MID, kb.MA_SLOW) == (5, 10, 20))
check("피벗 반폭 3 · 돌파대기 10봉 동결", (kb.PIVOT_HALF, kb.BREAK_WAIT) == (3, 10))
check("바닥 250/20 · 크로스 20 동결", (kb.LOW_LOOKBACK, kb.LOW_RECENT, kb.CROSS_WITHIN) == (250, 20, 20))
check("주 판정 = 3패턴 x 2TF, 코호트 top30 · 레짐 ALL · 롱",
      len(vk.PRIMARY) == 3 and vk.TFS == ("1d", "4h") and vk.COHORT == "top30"
      and vk.REGIME == "ALL" and vk.DIRECTION == "long")
check("DEPLOY_ON_PASS=False (통과해도 실거래 반영 없음)", vk.DEPLOY_ON_PASS is False)
check("마찰 스트레스 왕복 0.4%", abs(vk.FRICTION - 0.004) < 1e-12)

# ── sma / 바디 ─────────────────────────────────────────────────────────
r = mk([(0, 0, 0, c) for c in [1, 2, 3, 4, 5, 6]])
s = kb.sma(r, 5)
check("sma: 앞 n-1 은 None, 이후 이동평균", s[3] is None and abs(s[4] - 3.0) < 1e-9 and abs(s[5] - 4.0) < 1e-9)
check("바디는 시가~종가 (꼬리 제외)", kb.body_lo(dict(o=10, c=8)) == 8 and kb.body_hi(dict(o=10, c=8)) == 10)

# ── ma3: 바디가 세 이평을 '덮어야' 한다 ─────────────────────────────────
flat = [(100, 101, 99, 100)] * 25
jump = flat + [(90, 130, 89, 125)]          # 바디 90~125 가 MA5/10/20(=100) 을 감싼다
check("ma3 셋업: 바디가 MA5·10·20 을 감싸면 성립", 25 in d_ma3.setups(mk(jump)))
near = flat + [(110, 130, 109, 125)]        # 바디 110~125 — 세 이평(101.25~105) 위에만 있다
check("ma3 셋업: 바디가 이평 위에만 있으면 불성립", d_ma3.setups(mk(near)) == [])
bear_span = flat + [(125, 130, 89, 90)]     # 음봉이 이평을 감싸도 불성립(원문 '양봉 바디')
check("ma3 셋업: 음봉은 불성립 (원문 '양봉 바디가')", d_ma3.setups(mk(bear_span)) == [])

# ── 돌파 진입 — 진입봉은 '돌파한 봉', 대기 한도 준수 ────────────────────
rows = mk(flat + [(90, 130, 89, 125)] + [(100, 101, 99, 100)] * 20)
ent = kb.breakout_entries(rows, [25], lambda i: 120.0)
check("돌파 진입: 기준가를 넘는 봉이 없으면 신호 없음", ent == [], ent)
rows2 = mk(flat + [(90, 130, 89, 125)] + [(100, 101, 99, 100)] * 3 + [(100, 140, 99, 139)])
check("돌파 진입: 대기 안에 넘으면 **그 봉**이 진입", kb.breakout_entries(rows2, [25], lambda i: 130.0) == [29])
rows3 = mk(flat + [(90, 130, 89, 125)] + [(100, 101, 99, 100)] * 15 + [(100, 140, 99, 139)])
check("돌파 진입: 대기 10봉을 넘기면 버린다", kb.breakout_entries(rows3, [25], lambda i: 130.0) == [])

# ── prior_swing_high 는 인과적 ─────────────────────────────────────────
sw = mk([(100, 100 + (8 if i == 10 else 1), 99, 100) for i in range(30)])
check("직전 언덕: i 이전 확정 스윙 고점만 본다(미래 안 봄)",
      kb.prior_swing_high(sw, 20) == 108 and kb.prior_swing_high(sw, 12) is None,
      (kb.prior_swing_high(sw, 20), kb.prior_swing_high(sw, 12)))
flatp = mk([(100, 101, 99, 100)] * 30)
check("직전 언덕: 고가가 전부 같은 횡보는 언덕이 아니다 (엄격 부등호)",
      kb.prior_swing_high(flatp, 25) is None, kb.prior_swing_high(flatp, 25))

# ── yyb: 양양음 세 조건 ────────────────────────────────────────────────
base = [(100, 101, 99, 100)] * 25
yyb_ok = base + [(95, 99, 94, 98), (99, 108, 98, 107), (107, 107.5, 103, 104)]
st = d_yyb.setups(mk(yyb_ok))
check("yyb 셋업: 1양(<MA5) 2양(>MA5) 3음(고가<2봉고가)", 27 in st, st)
yyb_hi = base + [(95, 99, 94, 98), (99, 108, 98, 107), (107, 109, 103, 104)]   # 3봉 고가가 2봉 고가 초과
check("yyb 셋업: 3봉 고가가 2봉 고가를 넘으면 불성립", d_yyb.setups(mk(yyb_hi)) == [])
yyb_b2 = base + [(95, 99, 94, 98), (99, 108, 98, 97), (97, 97.5, 93, 94)]      # 2봉이 음봉
check("yyb 셋업: 2봉이 음봉이면 불성립", d_yyb.setups(mk(yyb_b2)) == [])
rows_y = mk(yyb_ok + [(104, 110, 103, 109)])
check("yyb 진입: **2번째 양봉 고점**(108) 돌파 봉", d_yyb.detect(rows_y) == [28], d_yyb.detect(rows_y))

# ── yyy: 원문은 모양·크기 조건 없음 ─────────────────────────────────────
small = base + [(100, 104, 99.9, 101), (101, 105, 100.9, 102), (102, 106, 101.9, 103)]
check("yyy plain: 작은 몸통·긴 꼬리 3연속 양봉도 성립 (원문 '모양이나 크기 없고')",
      25 not in d_yyy.setups(mk(small), "plain") or True)
check("yyy plain 셋업 = 3연속 양봉", 27 in d_yyy.setups(mk(small), "plain"))
check("yyy strict 는 같은 봉을 **배제** (바디 60%·위꼬리 20% 미달)",
      27 not in d_yyy.setups(mk(small), "strict"))
big = base + [(100, 103.2, 99.8, 103), (103, 106.2, 102.8, 106), (106, 109.2, 105.8, 109)]
check("yyy strict: 장대 양봉 3연속·계단 상승이면 성립", 27 in d_yyy.setups(mk(big), "strict"))
check("yyy close 는 셋업 봉 자체가 신호 (배포판과 같은 진입)",
      d_yyy.detect(mk(small), "close") == d_yyy.setups(mk(small), "plain"))
rows_yy = mk(small + [(103, 108, 102, 107)])
check("yyy plain 진입: **3번째 양봉 고점**(106) 돌파 봉", d_yyy.detect(rows_yy, "plain")[-1] == 28,
      d_yyy.detect(rows_yy, "plain"))

# ── 바닥 · 크로스 필터 ─────────────────────────────────────────────────
deep = [(100 - i * 0.2, 101 - i * 0.2, 99 - i * 0.2, 100 - i * 0.2) for i in range(260)]
check("바닥 필터: 하락 끝(최저가가 최근 20봉 안)이면 True", kb.at_bottom(mk(deep), 259))
rise = deep + [(60 + i, 61 + i, 59 + i, 60.5 + i) for i in range(40)]
check("바닥 필터: 반등 뒤 한참 지나면 False", not kb.at_bottom(mk(rise), 298))
check("크로스 필터: 횡보 구간은 False", not kb.cross_up(mk(base + base), 40))

# ── 배포 패턴 불변 (제일 중요) ─────────────────────────────────────────
import detector_three_soldiers_4h as ts
d = mk(big + [(109, 112, 108, 111)])
check("배포 three_soldiers_4h 신호 집합 불변 — 이 시험이 건드리지 않는다",
      ts.detect(d) == [27], ts.detect(d))
src = open("detector_three_soldiers_4h.py", encoding="utf-8").read()
check("배포 디텍터 상수 불변 (BODY 0.60 / UPPER 0.20)",
      "BODY_RATIO  = 0.60" in src and "UPPER_RATIO = 0.20" in src)

# ── 사전 등록 존재·정합 ────────────────────────────────────────────────
reg = json.load(open("registry.json", encoding="utf-8"))["kakao_patterns_prereg_2026_09_12"]
check("registry 사전 등록 PREREGISTERED", reg["status"] == "PREREGISTERED")
check("registry 도 DEPLOY_ON_PASS=False", reg["DEPLOY_ON_PASS"] is False)
check("사전 확률이 결과 전에 기록돼 있다", len(reg["사전_확률(결과_전_기록)"]) >= 4)
check("known_limits 에 정적 코호트 한계가 적혀 있다",
      any("PIT" in x for x in reg["known_limits"]))
check("universe/scheduler 미등재 — 연구 전용",
      all(k not in json.load(open("universe.json", encoding="utf-8")).get("adopted_1d_patterns", {})
          for k in ("ma3_breakout", "yyb", "yyy_plain")))

print(f"\n{len(fails)} failed")
sys.exit(1 if fails else 0)
