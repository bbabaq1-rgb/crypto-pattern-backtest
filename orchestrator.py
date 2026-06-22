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
import analysis

sys.path.insert(0, ".")

REGISTRY = "registry.json"
SYMBOLS_LABEL = "ALL7"
STOP_ON_PASSED = False    # 이번 라운드: passed에도 멈추지 않고 큐 소진
# 패턴 × 타임프레임 순회 (거친->고운 순, 표본 부족시 자동 하강)
TIMEFRAMES = ["1d", "4h", "1h"]
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


def test_and_gate(mod, pattern_id, symbol_label, tf, date_from=None, date_to=None):
    """백테스트 1회 -> 기대값 gate -> research_log 기록. verdict 반환."""
    res = mod.evaluate(date_from, date_to, tf)
    n, tr, mean_r, med_r = expectancy(res)
    T = gate.count_trials()                       # 기록 전 시점 = 보정 기준
    verdict, eff = gate.decide(n, mean_r, med_r, T)
    research_log.append_log(
        pattern_id, symbol_label,
        {"tf": tf, "from": date_from, "to": date_to},
        n, tr, mean_r, med_r, verdict)
    print(f"    [{symbol_label}] n={n}, 평균={mean_r*100:+.2f}%, 중앙값={med_r*100:+.2f}%, "
          f"진짜율={tr*100:.1f}%, T={T}, 평균임계={eff*100:.2f}% -> {verdict}")
    return verdict


def is_runnable(mod):
    """evaluate가 구현돼 호출 가능한지(스켈레톤/미적합 제외)."""
    if mod is None or not hasattr(mod, "evaluate"):
        return False
    try:
        mod.evaluate(None, None, "1d")     # 스켈레톤은 NotImplementedError/TypeError
        return True
    except (NotImplementedError, TypeError):
        return False
    except FileNotFoundError:
        return True                         # 데이터 문제는 실행 가능으로 간주


def process(p):
    """후보 1개를 타임프레임 순회로 처리. 갱신된 status 반환."""
    print(f"\n>> [{p['id']}] {p['name']} (난이도 {p['difficulty']}, {p['category']})")
    mod = import_detector(p.get("detector_file"))

    # (b) 실행 가능한 detector 없음 -> 스켈레톤 + needs_impl
    if not is_runnable(mod):
        if not p.get("detector_file"):
            make_skeleton(p)
            note = "스켈레톤 생성됨"
        else:
            note = f"detector_file 있으나 evaluate 미구현/미적합 ({p['detector_file']})"
        p["status"] = "needs_impl"
        print(f"    -> needs_impl ({note})")
        return p["status"]

    # (c~e) 타임프레임 순회: 표본 부족(보류)이면 더 고운 TF로 하강.
    saw_holding = False
    reject_reason = None
    for tf in TIMEFRAMES:
        full = mod.evaluate(None, None, tf)
        n, tr, mean_r, med_r = expectancy(full)
        T = gate.count_trials()
        verdict, eff = gate.decide(n, mean_r, med_r, T)
        research_log.append_log(p["id"], f"{SYMBOLS_LABEL}@{tf}",
                                {"tf": tf, "period": "full"}, n, tr, mean_r, med_r, verdict)
        print(f"    [{tf}] n={n}, 평균={mean_r*100:+.2f}%, 중앙값={med_r*100:+.2f}%, "
              f"진짜율={tr*100:.1f}%, T={T}, 평균임계={eff*100:.2f}% -> {verdict}")

        if verdict == "통과":
            # (d) OOS 재테스트 (해당 TF)
            print(f"    [{tf}] 통과 -> OOS 시간분할 재테스트")
            v_is  = test_and_gate(mod, p["id"], f"OOS@{tf}@IS",  tf, *SPLIT_IS)
            v_oos = test_and_gate(mod, p["id"], f"OOS@{tf}@OOS", tf, *SPLIT_OOS)
            oos_ok = (v_is == "통과" and v_oos == "통과")

            # 레짐 분해 (항상 기록)
            rb = analysis.regime_breakdown(analysis.per_signal(mod, tf))
            p.setdefault("regime", {})[tf] = rb
            up_only = ("up" in rb) and all(
                rb.get(g, {}).get("mean", -1) <= 0 for g in ("down", "side"))

            # 베이스라인 대조 (무작위 진입 대비 유의성)
            bt = analysis.baseline_compare(mod, tf, mean_r, med_r, n)
            base_ok = bool(bt and bt["significant"])
            if bt:
                research_log.append_log(
                    p["id"], f"BASE@{tf}",
                    {"tf": tf, "null_mean": round(bt["null_mean"], 5), "p_mean": bt["p_mean"]},
                    n, 0.0, bt["excess_mean"], bt["excess_median"],
                    "유의" if base_ok else "베이스라인미초과")
                p.setdefault("baseline", {})[tf] = dict(
                    null_mean=round(bt["null_mean"], 5),
                    excess_mean=round(bt["excess_mean"], 5),
                    p_mean=bt["p_mean"], significant=base_ok)
                print(f"    [{tf}] 베이스라인 null평균={bt['null_mean']*100:+.2f}%, "
                      f"초과={bt['excess_mean']*100:+.2f}%, p={bt['p_mean']:.3f} "
                      f"-> {'유의(엣지)' if base_ok else '미초과(편승)'}")
            if rb:
                print(f"    [{tf}] 레짐별 평균: " + ", ".join(
                    f"{g}:{v['mean']*100:+.2f}%(n{v['n']})" for g, v in rb.items()))

            # 최종 판정: OOS 통과 AND 베이스라인 유의해야 passed
            if oos_ok and base_ok:
                p["status"] = "passed"
                p["passed_tf"] = tf
                p["regime_dependent"] = up_only
                print(f"    => PASSED at {tf} (전체+OOS+베이스라인 유의)"
                      + (" [단 상승장 의존 주의]" if up_only else ""))
                return "passed"
            elif oos_ok and not base_ok:
                reject_reason = "베이스라인 미초과(상승장 편승)"
                print(f"    -> {tf} OOS 통과했으나 {reject_reason}")
            else:
                reject_reason = "OOS 미통과(과최적화)"
                print(f"    -> {tf} {reject_reason}")
        elif verdict.startswith("보류"):
            saw_holding = True              # 표본부족 -> 다음(고운) TF로 하강

    if reject_reason:
        p["status"] = "rejected"; p["reject_reason"] = reject_reason
    elif saw_holding:
        p["status"] = "holding"
    else:
        p["status"] = "rejected"; p["reject_reason"] = "기대값 음수"
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
            if STOP_ON_PASSED:
                print("\n[모델선정 게이트] passed 발생 -> 루프 정지")
                break

    # (3) 모델선정 게이트
    print("\n" + "=" * 64)
    if passed_any:
        print("수익모델 후보 - 대표님 승인 대기:")
        for p in passed_any:
            print(f"  - {p['id']} ({p['name']})  [{p.get('passed_tf','?')} 전체+OOS 통과]")
    else:
        print("passed 패턴 없음 - 승인 대기 후보 없음. 큐 계속 소진.")
    print("=" * 64)

    # 큐 상태 요약
    from collections import Counter
    cnt = Counter(p["status"] for p in pats)
    print("registry 상태:", dict(cnt))


if __name__ == "__main__":
    main()
