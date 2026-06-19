"""
research_log.py — 매 시험을 research_log.csv 에 1행 append.

열: timestamp, pattern, symbol, params_json, n, true_rate, verdict, git_commit
  - git_commit: 실행 시점의 HEAD 해시 (subprocess git rev-parse)
"""
import csv
import os
import json
import subprocess
from datetime import datetime, timezone

# ======================================================================
# 파라미터
# ======================================================================
LOG_PATH = "research_log.csv"
FIELDS = ["timestamp", "pattern", "symbol", "params_json",
          "n", "true_rate", "verdict", "git_commit"]


def git_head():
    """현재 HEAD 커밋 해시 (실패 시 'unknown')."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "unknown"


def append_log(pattern, symbol, params, n, true_rate, verdict, log_path=LOG_PATH):
    """시험 1건을 CSV에 추가. 파일 없으면 헤더 먼저 기록."""
    new = not os.path.exists(log_path)
    with open(log_path, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if new:
            w.writerow(FIELDS)
        w.writerow([
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
            pattern, symbol,
            json.dumps(params, ensure_ascii=False),
            n, round(true_rate, 4), verdict, git_head(),
        ])
