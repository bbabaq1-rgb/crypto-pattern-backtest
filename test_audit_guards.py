"""
test_audit_guards.py — 가드 교정 감사 고정 (2026-09-09).

지키는 성질:
  · 감사 대상이 **실거래 중인 셀**이다(deployed/observation + 4h adopted 3종)
  · 층 9개가 역사적 추가 순서대로 나열돼 있다(래칫 곡선의 의미)
  · 인과 B 는 신호 **이전** 봉만 풀에 넣는다(현 B 와의 차이 = 사후 조건화 크기)
  · 이 스크립트는 **문턱을 바꾸지 않는다** — gate/frame 모듈 상수를 건드리지 않는다
  · 실거래·DB 무관
"""
import inspect
import json

import audit_guards as A
import gate
import frame_v3 as f3
import validate_revival as vr

fails = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


ids = [c["cid"] for c in A.CELLS]
check("감사 대상 12셀", len(A.CELLS) == 12, ids)
check("실거래 라우팅 7셀 포함", all(k in ids for k in ("engulfing|bull_btc", "engulfing|bear", "engulfing_short|bull_altseason",
                                                    "fvg|bull_btc", "fvg|bull_altseason", "three_soldiers_4h|bull_btc",
                                                    "three_soldiers_4h|bull_altseason")))
check("4h adopted 3종 포함", all(k in ids for k in ("triple_bottom_4h|ALL", "equal_lows_4h|ALL", "vol_awakening_4h|ALL")))
check("관찰 2셀 포함", "inverted_hammer|ALL" in ids and "marubozu|ALL" in ids)
check("그림자 셀(미배포)은 감사 대상 아님", not any("double_bottom" in k or "inverse_hs" in k for k in ids))
check("층 9개, 역사 순서(게이트→홀드아웃→C2b→C3→PIT→국면홀드아웃→에피소드→B→Holm)",
      A.LAYERS == ["L1_gate_v2", "L2_holdout_cal", "L3_c2b", "L4_c3_equity", "L5_pit",
                   "L6_holdout_regime", "L7_episode", "L8_bench_B", "L9_holm"], A.LAYERS)
check("OOS 참조 구간은 v4 와 같은 2025-01-01", A.SPLIT == "2025-01-01")

# 인과 B — 신호 이전 봉만
src = inspect.getsource(A.causal_b_edges)
check("인과 B 풀은 range(30, s['i']) — 신호 봉 이전만", 'range(30, s["i"])' in src)
check("인과 B 도 같은 코인·달·레짐 조건을 건다",
      'rows[j]["date"][:7] != month' in src and 'oc.regmap.get(rows[j]["date"]) != lab' in src)
check("인과 B 출력이 cluster_boot 가 읽는 키(sym/month/edge)를 갖는다",
      'dict(sym=s["sym"], month=month, edge=' in src)

# 문턱 불변 — 모듈을 import 해도 gate/frame 상수가 그대로
check("gate.dist_ok 의 승률 문턱 불변(35%)", gate.dist_ok([0.01] * 35 + [-0.01] * 65) and not gate.dist_ok([0.01] * 34 + [-0.01] * 66))
check("frame_v3 상수 불변", f3.HOLDOUT_DAYS == 365 and f3.HOLDOUT_MIN_N == 10 and f3.EP_MIN_N == 5 and f3.TRAIN_MIN_N == 20)
check("revival 홀드아웃 상수 불변", vr.HOLDOUT_DAYS_BY_TF == {"1d": 365, "4h": 365, "1h": 90})
ms = inspect.getsource(A)
check("감사 스크립트가 게이트·프레임 상수에 대입하지 않는다",
      "gate." not in ms.replace("gate.win_rate", "").replace("gate.dist", "")
      and "f3.HOLDOUT_DAYS =" not in ms and "vr.HOLDOUT" not in ms.replace("vr.HOLDOUT_DAYS_BY_TF", ""))
check("실거래 엔진 import 없음", "import paper_executor" not in ms and "import exchange" not in ms)
check("DEPLOY_ON_PASS 상수 없음 — 배포 판정이 아니라 측정 전용", not hasattr(A, "DEPLOY_ON_PASS"))

# 층별 귀속 논리 (합성)
res = {"a": {l: True for l in A.LAYERS}, "b": {l: True for l in A.LAYERS}}
res["a"]["L8_bench_B"] = False
res["b"]["L8_bench_B"] = False; res["b"]["L1_gate_v2"] = False
solo = [k for k in res if not res[k]["L8_bench_B"] and all(res[k][o] for o in A.LAYERS if o != "L8_bench_B")]
check("단독 기각 = 다른 층 전부 통과인데 그 층만 X (a 만 해당)", solo == ["a"], solo)

check("registry 기록", "guard_audit_2026_09_09" in json.load(open("registry.json", encoding="utf-8")))
wf = open(".github/workflows/audit_guards.yml", encoding="utf-8").read()
check("워크플로가 테스트를 먼저 돌린다", "python test_audit_guards.py" in wf)
check("tests.yml 등재", "test_audit_guards.py" in open(".github/workflows/tests.yml", encoding="utf-8").read())

print(f"\n{len(fails)} failed")
raise SystemExit(1 if fails else 0)
