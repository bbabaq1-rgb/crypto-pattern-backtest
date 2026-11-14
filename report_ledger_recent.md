# R-105 — 최근 실거래 방식D 결과 vs 같은 단위의 이전 분포 (2026-11-14, run 43616805805)

진단 전용, 실거래 무변경, DEPLOY_ON_PASS=False. registry `ledger_recent_prereg_2026_11_14`.

- 기준 풀 = entry_date < 2026-11-04 실거래 방식D(단위 n>=10), 최근 = 11-04 이후. 판정 규칙은 실행 전 고정.
- **판정 INCONCLUSIVE** — 기준 단위를 갖춘 최근 거래 합산 n=9 (< 10).
- 단위: ai_elliott_btc|long n=5 −0.91% pct .00 / vol_awakening_4h|long n=2 −8.18% pct .12 / equal_lows_4h n=1 +4.79% / triple_bottom_4h n=1 +7.60%. 단위 n 이 1~5 라 백분위는 해석 불가.
- 사전 확률: INCONCLUSIVE 0.30(최빈은 WITHIN 0.50) — 범주는 맞았으나 최빈이 아니었다. 이유: 11-09 정지 + 최소주문 스킵(R-107/108)으로 최근 표본이 거의 안 쌓인다는 점을 과소평가.
- 읽는 법: 최근 손실이 운인지 국면 변화인지 이 장부로는 가를 수 없다. 정지 중에는 새 표본도 없다 → R-114(그림자 기록).
