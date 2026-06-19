"""
gate.py — 백테스트 결과를 받아 verdict 자동 판정. (기대값 기반, 2026-06 보정 동결)

판정(기대값 기반):
  n < MIN_N                                          -> "보류(표본부족)"
  n >= MIN_N AND mean_ret > eff_mean AND median_ret > 0 -> "통과"
  그 외                                               -> "기각"

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


def decide(n, mean_ret, median_ret, T):
    """(verdict, eff_mean) 반환. mean_ret/median_ret 는 수수료 차감 후 수익."""
    eff = effective_mean_threshold(T)
    if n < MIN_N:
        return "보류(표본부족)", eff
    if mean_ret > eff and median_ret > 0:
        return "통과", eff
    return "기각", eff
