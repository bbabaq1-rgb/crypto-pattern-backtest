# 앙상블 스코어링 + 1h 스캔 주기 리포트

**날짜**: 2026-06-29

---

## 1. GitHub Actions 스캔 주기 — 1h로 변경

### 변경 전 (4h, 6회/일)
```yaml
- cron: '0 0 * * *'
- cron: '0 4 * * *'
- cron: '0 8 * * *'
- cron: '0 12 * * *'
- cron: '0 16 * * *'
- cron: '0 20 * * *'
```

### 변경 후 (1h, 24회/일)
```yaml
- cron: '0 * * * *'   # 매시 정각 (24회/일)
```

- UTC 00:00 → `oncefull` (데이터 fetch + 전체 파이프라인)
- 나머지 23회 → `oncequick` (fetch 생략, 레짐→신호→페이퍼만)
- **월 사용량 예상**: 24회 × 2분 × 30일 = 1,440분 (무료 한도 2,000분 안)
- 1h 패턴(bat_1h, butterfly_1h) 신호 실시간 탐지 가능

---

## 2. 앙상블 스코어링

### 점수 계산 공식

```
기본점수 = sum(TF_BASE_PTS[tf] × p_multiplier(pattern))

TF_BASE_PTS: {"1d": 3, "4h": 2, "1h": 1}

p_multiplier:
  p < 0.001 → ×1.2
  p < 0.01  → ×1.1
  p < 0.05  → ×1.0

멀티TF 보너스:
  1d + 4h + 1h: +3
  1d + 4h:      +2
  1d + 1h:      +1
  4h + 1h:      +1

ensemble_score = 기본점수 + 보너스
```

### 등급 기준

| 등급 | 점수 범위 | 아이콘 | 포지션 사이징 |
|------|----------|--------|-------------|
| A | ≥ 8점 | 🔥 | POS_USD × 1.5 = $60 |
| B | 5~7점 | ⭐ | POS_USD × 1.0 = $40 |
| C | 3~4점 | 🔵 | POS_USD × 0.7 = $28 |
| D | 1~2점 | ⚪ | POS_USD × 0.5 = $20 |

tf_confirmed=False이면 추가로 ×0.5 적용.

### 패턴별 p값 매핑

| 패턴 | TF | p값 | 배수 | 1발화 점수 |
|------|-----|-----|------|-----------|
| engulfing/fvg | 1d | <0.0001 | ×1.2 | 3.6 |
| three_soldiers_4h | 4h | <0.0001 | ×1.2 | 2.4 |
| gartley/bat/butterfly | 4h | <0.001 | ×1.2 | 2.4 |
| inverted_hammer/marubozu | 1d | <0.01 | ×1.1 | 3.3 |
| bat_1h/butterfly_1h | 1h | <0.05 | ×1.0 | 1.0 |

### 점수 시나리오 예시

| 시나리오 | 계산 | 점수 | 등급 |
|---------|------|------|------|
| 1d fvg 단독 | 3×1.2 | 3.6 | C🔵 |
| 1d engulfing 단독 | 3×1.2 | 3.6 | C🔵 |
| 4h bat 단독 | 2×1.2 | 2.4 | D⚪ |
| 1h bat 단독 | 1×1.0 | 1.0 | D⚪ |
| 1d fvg + 4h gartley | 3.6+2.4+보너스2 | **8.0** | **A🔥** |
| 1d fvg + 1h bat | 3.6+1.0+보너스1 | **5.6** | **B⭐** |
| 4h bat + 1h butterfly | 2.4+1.0+보너스1 | **4.4** | **C🔵** |
| 1d + 4h + 1h 전부 | 3.6+2.4+1.0+보너스3 | **10.0** | **A🔥** |

---

## 3. signals_today.json 새 필드

```json
{
  "symbol": "BTC",
  "pattern": "fvg",
  "direction": "short",
  "ensemble_score": 3.6,
  "ensemble_grade": "C",
  "score_breakdown": {
    "1d_pts": 3.6,
    "4h_pts": 0.0,
    "1h_pts": 0.0,
    "bonus": 0
  },
  "priority_score": 3.6,
  "priority_rank": 1,
  ...
}
```

---

## 4. paper_executor.py 사이징 로직

```python
grade_mult   = GRADE_SIZE_MULT.get(grade, 1.0)   # A:1.5/B:1.0/C:0.7/D:0.5
size_for_pos = round(POS_USD * grade_mult, 2)
if not tf_confirmed:
    size_for_pos = round(size_for_pos * 0.5, 2)
```

실제 사이징 표:
- Grade A + tf_confirmed: $60
- Grade A + 비확증: $30
- Grade B + tf_confirmed: $40 (기존 동일)
- Grade C + tf_confirmed: $28
- Grade D + tf_confirmed: $20
- Grade D + 비확증: $10 (최소)

---

## 5. 대시보드 변경

- `section_signals()`: `ensemble_score` 기준 정렬, 등급 아이콘(🔥⭐🔵⚪) 컬럼 추가
- 멀티TF 발화 시 가장 높은 등급 자연스럽게 반영 (점수 합산)

---

_현재 레짐 bear 구간 — 1d 신호 위주, 1h 패턴 신호 무관 실행_
