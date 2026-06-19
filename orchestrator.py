"""
orchestrator.py - 자동 패턴 연구 하네스 메인 루프.

6단계: 기획(후보선정) -> 테스트(백테스트) -> 검증(게이트) ->
       재테스트(OOS 시간분할) -> 모델선정 -> 보고서(report.py 별도).

동작:
  (a) registry.json의 pending 중 difficulty 낮은 순으로 1개 선택.
  (b) 실행 가능한 detector(evaluate 구현)가 없으면 스켈레톤 생성 + needs_impl 후 다음.
  (c) detector 있으면 7종목 일봉 백테스트 -> 라벨링 -> gate verdict.
  (d) 통과면 OOS(2021~2023 vs 2024+) 재테스트, 둘 다 통과 -> passed, 아니면 rejected.
  (e) 보류 -> holding, 기각 -> rejected.
  (f) 매 단계 research_log.csv 기록(다중비교 보정).
  (g) 다음 pending 반복. passed 발생 시 모델선정 게이트에서 정지.
"""
import json
import os
import sys
import importlib
import statistics as st

import gate
import research_log

sys.path.insert(0, ".")

REGISTRY = "registry.json"
SYMBOLS_LABEL = "ALL7"
# OOS 시간분할
SPLIT_IS  = ("2021-01-01", "2023-12-31")   # in-sample
SPLIT_OOS = ("2024-01-01", "2026-12-31")   # out-of-sample (2024+)

SKELETON = '''"""
detector_{id}.py - {name} 탐지 (orchestrator 자동 생성 스켈레톤)

TODO: 이 패턴의 탐지 규칙을 구현해야 함 (사람이 채울 자리).
  - detector_liquidity_sweep.py 구조를 참고.
  - 아래 evaluate(date_from, date_to)를 구현하면 orchestrator가
    자동으로 백테스트/게이트/OOS재테스트를 돌린다.
  - 반환 형식: dict(agg={{"n":..,"real":..,"fake":..,"neutral":..}},
                   per={{symbol: {{...}}}})
  - 라벨 기준은 1단계와 동일(+15% 선도달=real, -10% 선도달=fake, 그외 neutral).
"""

PATTERN = "{id}"


def evaluate(date_from=None, date_to=None):
    raise NotImplementedError("TODO: {name} 탐지 규칙 구현 필요")
'''


def load_registry():
    with open(REGISTRY, encoding="utf-8") as f:
        return json.load(f)


def save_registry(reg):
    with open(REGISTRY, "w", encoding="utf-8") as f:
        json.dump(reg, f, ensure_ascii=False, indent=2)


def import_detector(detector_file):
    """detector 모듈을 import. 실패하거나 evaluate 없으면 None."""
    if not detector_file or not os.path.exists(detector_file):
        return None
    mod_name = detector_file[:-3] if detector_file.endswith(".py") else detector_file
    try:
        mod = importlib.import_module(mod_name)
    except Exception:
        return None
    return mod if hasattr(mod, "evaluate") else None


def make_skeleton(p):
    """detector_<id>.py 스켈레톤 생성, detector_file 설정."""
    fn = f"detector_{p['id']}.py"
    if not os.path.exists(fn):
        with open(fn, "w", encoding="utf-8") as f:
            f.write(SKELETON.format(id=p["id"], name=p["name"]))
    p["detector_file"] = fn


def true_rate(agg):
    return agg["real"] / agg["n"] if agg["n"] else 0.0


def expectancy(res):
    """evaluate 결과에서 (n, true_rate, mean_ret, median_ret)."""
    agg = res["agg"]; rets = res.get("rets", [])
    n = agg["n"]
    tr = true_rate(agg)
    mean_r = st.mean(rets) if rets else 0.0
    med_r = st.median(rets) if rets else 0.0
    return n, tr, mean_r, med_r


def test_and_gate(mod, pattern_id, period_label, date_from=None, date_to=None):
    """백테스트 1회 -> 기대값 gate -> research_log 기록. verdict 반환."""
    res = mod.evaluate(date_from, date_to)
    n, tr, mean_r, med_r = expectancy(res)
    T = gate.count_trials()                       # 기록 전 시점 = 보정 기준
    verdict, eff = gate.decide(n, mean_r, med_r, T)
    research_log.append_log(
        pattern_id, period_label,
        {"period": period_label, "from": date_from, "to": date_to},
        n, tr, mean_r, med_r, verdict)
    print(f"    [{period_label}] n={n}, 평균={mean_r*100:+.2f}%, 중앙값={med_r*100:+.2f}%, "
          f"진짜율={tr*100:.1f}%, T={T}, 평균임계={eff*100:.2f}% -> {verdict}")
    return verdict


def process(p):
    """후보 1개 처리. 갱신된 status 반환."""
    print(f"\n>> [{p['id']}] {p['name']} (난이도 {p['difficulty']}, {p['category']})")
    mod = import_detector(p.get("detector_file"))

    # (b) 실행 가능한 detector 없음 -> 스켈레톤 + needs_impl
    runnable = False
    full = None
    if mod is not None:
        try:
            full = mod.evaluate()              # 스켈레톤은 NotImplementedError
            runnable = True
        except NotImplementedError:
            runnable = False
    if not runnable:
        if not p.get("detector_file"):
            make_skeleton(p)
            note = "스켈레톤 생성됨"
        else:
            note = f"detector_file 있으나 evaluate 미구현/미적합 ({p['detector_file']})"
        p["status"] = "needs_impl"
        print(f"    -> needs_impl ({note})")
        return p["status"]

    # (c) 테스트 + 게이트 (전체 기간, 기대값 기반)
    n, tr, mean_r, med_r = expectancy(full)
    T = gate.count_trials()
    verdict, eff = gate.decide(n, mean_r, med_r, T)
    research_log.append_log(p["id"], SYMBOLS_LABEL,
                            {"period": "full"}, n, tr, mean_r, med_r, verdict)
    print(f"    [full] n={n}, 평균={mean_r*100:+.2f}%, 중앙값={med_r*100:+.2f}%, "
          f"진짜율={tr*100:.1f}%, T={T}, 평균임계={eff*100:.2f}% -> {verdict}")

    # (e) 보류/기각
    if verdict.startswith("보류"):
        p["status"] = "holding"
    elif verdict == "기각":
        p["status"] = "rejected"
    elif verdict == "통과":
        # (d) OOS 재테스트
        print("    통과 -> OOS 재테스트(시간분할) 진입")
        v_is  = test_and_gate(mod, p["id"], f"OOS@{SPLIT_IS[0]}~{SPLIT_IS[1]}", *SPLIT_IS)
        v_oos = test_and_gate(mod, p["id"], f"OOS@{SPLIT_OOS[0]}~{SPLIT_OOS[1]}", *SPLIT_OOS)
        if v_is == "통과" and v_oos == "통과":
            p["status"] = "passed"
        else:
            p["status"] = "rejected"
            print("    -> OOS 한쪽 이상 미통과: 과최적화로 rejected")
    print(f"    => status={p['status']}")
    return p["status"]


def main():
    reg = load_registry()
    pats = reg["patterns"]
    # (a) pending을 difficulty 오름차순으로
    pending = sorted([p for p in pats if p["status"] == "pending"],
                     key=lambda x: x["difficulty"])
    print("=" * 64)
    print(f"orchestrator 시작 - pending {len(pending)}개 처리")
    print("=" * 64)

    passed_any = []
    for p in pending:
        status = process(p)
        save_registry(reg)                  # 매 단계 즉시 반영
        if status == "passed":
            passed_any.append(p)
            print("\n[모델선정 게이트] passed 발생 -> 루프 정지")
            break

    # (3) 모델선정 게이트
    print("\n" + "=" * 64)
    if passed_any:
        print("수익모델 후보 - 대표님 승인 대기:")
        for p in passed_any:
            print(f"  - {p['id']} ({p['name']})  [전체+OOS 통과]")
    else:
        print("passed 패턴 없음 - 승인 대기 후보 없음. 큐 계속 소진.")
    print("=" * 64)

    # 큐 상태 요약
    from collections import Counter
    cnt = Counter(p["status"] for p in pats)
    print("registry 상태:", dict(cnt))


if __name__ == "__main__":
    main()
