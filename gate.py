"""
gate.py — 백테스트 결과를 받아 verdict 자동 판정. (기대값 기반, 2026-06 보정 동결)

판정(기대값 기반) — **v2 (2026-09-05 사용자 결정)**:
  n < MIN_N                                                 -> "보류(표본부족)"
  n >= MIN_N AND mean_ret > eff_mean AND dist_ok(rets)      -> "통과"
  그 외                                                      -> "기각"

  dist_ok — 분포 조건. v1 은 median_ret > 0 이었다. 방식D(−8% 손절)에서는 중앙값이 손절값에 붙어
  **사실상 승률 50% 이상을 요구**하는 조건이 되어 승률 35~45% 로 수익을 내는 추세·돌파형을 구조적으로
  막았다(report_revival.md: 1d 후보 전 셀 median −8.20%). 사용자 결정(2026-09-05 "승률 35~45% 까지는
  허용, 수익이 발생할 수 있으면 진행")으로 **v2 = 승률 >= WIN_RATE_MIN(0.35)** 로 교체.
  복권형(소수 대박 의존) 방어는 boot_p·OOS·holdout·자산곡선(확인 단계)이 맡고, 절사평균·상위5기여도는
  진단으로 병기한다.
  median_ret 는 계속 계산·보고하되 판정에는 쓰지 않는다. rets 를 못 주는 구형 호출은 v1 로 판정하고
  gate_version=1 을 돌려준다(조용히 섞이지 않게).

  - mean_ret/median_ret 는 수수료(왕복) 차감 후 per-trade 수익.
  - 진짜/페이크/중립 라벨 비율(true_rate)은 참고용으로만 로그/리포트에 남기고
    통과 판정에는 쓰지 않는다.

다중비교 보정(평균수익 임계에 적용):
  시험 횟수 T가 많을수록 요구 평균수익을 살짝 올린다.
    eff_mean = MEAN_THR_BASE + MEAN_CORR_COEF * log2(max(T, 1))
"""
import math
import os

# ======================================================================
# 파라미터 (보정 후 동결)
# ======================================================================
MIN_N          = 20       # 최소 표본 수
MEAN_THR_BASE  = 0.0      # 기본 평균수익 임계 (수수료 차감 후 > 0)
MEAN_CORR_COEF = 0.001    # 다중비교 보정 계수 (log2(T)당 +0.1%p)
GATE_VERSION   = 2        # 2026-09-05: median>0 → 승률>=35% (사용자 결정)
WIN_RATE_MIN   = 0.35     # v2 분포 조건
TRIM_FRAC      = 0.10     # 진단용 절사평균(상하 10%)

DEFAULT_LOG = "research_log.csv"


def count_trials(log_path=DEFAULT_LOG):
    """research_log.csv 기록된 총 시험 횟수(헤더 제외)."""
    if not os.path.exists(log_path):
        return 0
    with open(log_path, newline="", encoding="utf-8-sig") as f:
        rows = sum(1 for _ in f)
    return max(0, rows - 1)


def effective_mean_threshold(T):
    """다중비교 보정된 평균수익 통과 임계."""
    return MEAN_THR_BASE + MEAN_CORR_COEF * math.log2(max(T, 1))


def win_rate(rets):
    return (sum(1 for r in rets if r > 0) / len(rets)) if rets else 0.0


def dist_ok(rets):
    """v2 분포 조건: 승률 >= WIN_RATE_MIN. (v1 은 median>0 = 사실상 승률>50%)"""
    return bool(rets) and win_rate(rets) >= WIN_RATE_MIN


def dist_reason(rets):
    """실패 사유 문자열 (판정 로그용)."""
    return f"win_rate={win_rate(rets):.2f}<{WIN_RATE_MIN:.2f}"


def trimmed_mean(rets, frac=TRIM_FRAC):
    """상하 frac 씩 잘라낸 평균 — 소수 대박 의존(복권형) 진단. 판정에는 쓰지 않는다."""
    if not rets:
        return None
    s = sorted(rets); k = int(len(s) * frac)
    core = s[k:len(s) - k] if len(s) - 2 * k >= 1 else s
    return sum(core) / len(core)


def top_share(rets, k=5):
    """총이익 중 상위 k 거래 기여 비율 — 1.0 에 가까우면 소수 대박 의존. 총이익<=0 이면 None."""
    pos = sum(r for r in rets if r > 0)
    if pos <= 0:
        return None
    return sum(sorted((r for r in rets if r > 0), reverse=True)[:k]) / pos


def decide(n, mean_ret, median_ret, T, rets=None):
    """
    (verdict, eff_mean) 반환. rets 를 주면 v2(승률>=35%), 없으면 v1(median>0) 로 판정 — 구형 호출
    호환. 어느 판으로 판정했는지는 decide_v() 로 받을 수 있다.
    """
    v, eff, _ = decide_v(n, mean_ret, median_ret, T, rets)
    return v, eff


def decide_v(n, mean_ret, median_ret, T, rets=None):
    """(verdict, eff_mean, gate_version)."""
    eff = effective_mean_threshold(T)
    if n < MIN_N:
        return "보류(표본부족)", eff, GATE_VERSION if rets is not None else 1
    if rets is not None:
        ok = mean_ret > eff and dist_ok(rets)
        return ("통과" if ok else "기각"), eff, GATE_VERSION
    ok = mean_ret > eff and median_ret > 0
    return ("통과" if ok else "기각"), eff, 1
