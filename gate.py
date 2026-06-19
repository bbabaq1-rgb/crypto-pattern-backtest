"""
gate.py — 백테스트 결과(n, 진짜율/승률)를 받아 verdict 자동 판정.

규칙:
  n < MIN_N                       -> "보류(표본부족)"
  n >= MIN_N AND rate >= eff_min  -> "통과"
  그 외                            -> "기각"

다중비교 보정:
  지금까지 기록된 시험 횟수 T가 많을수록 기준을 강화한다.
    eff_min = MIN_TRUE_RATE_BASE + CORR_COEF * log2(max(T, 1))
  (T=0,1 -> 보정 0; T=2 -> +0.01; T=8 -> +0.03 ...)
"""
import csv
import os
import math

# ======================================================================
# 파라미터
# ======================================================================
MIN_N              = 20      # 최소 표본 수
MIN_TRUE_RATE_BASE = 0.55    # 기본 통과 기준 진짜율
CORR_COEF          = 0.01    # 다중비교 보정 계수 (log2(T)당 가산)

DEFAULT_LOG = "research_log.csv"


def count_trials(log_path=DEFAULT_LOG):
    """research_log.csv에 기록된 총 시험 횟수(헤더 제외)."""
    if not os.path.exists(log_path):
        return 0
    with open(log_path, newline="", encoding="utf-8-sig") as f:
        rows = sum(1 for _ in f)
    return max(0, rows - 1)


def effective_min_true_rate(T):
    """다중비교 보정된 통과 기준."""
    return MIN_TRUE_RATE_BASE + CORR_COEF * math.log2(max(T, 1))


def decide(n, rate, T):
    """(verdict, eff_min) 반환."""
    eff = effective_min_true_rate(T)
    if n < MIN_N:
        return "보류(표본부족)", eff
    if rate >= eff:
        return "통과", eff
    return "기각", eff
