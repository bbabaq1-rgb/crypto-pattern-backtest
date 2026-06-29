# 4h 스케줄러 확장 + 멀티 TF 확증 + 4h 패턴 발굴 리포트

**날짜**: 2026-06-29

---

## 방향 3 — 4h 스케줄러

### GitHub Actions 변경
| 시각 (UTC) | 모드 | 내용 |
|-----------|------|------|
| 00:00 (KST 09:00) | `oncefull` | fetch + 레짐 + 신호 + 페이퍼 체결 |
| 04:00, 08:00, 12:00, 16:00, 20:00 | `oncequick` | fetch 생략, 기존 CSV로 신호 탐지 |

- 하루 총 6회 실행 (4h 간격)
- API fetch는 하루 1회 (00:00)만 → 거래소 rate-limit 부담 없음
- `workflow_dispatch` 수동 실행 시 mode 파라미터 선택 가능

### scheduler.py `oncequick` 모드
```
python scheduler.py oncequick
```
- 레짐 판정 → direction_switch 갱신 → 신호 탐지 → 페이퍼 체결
- universe.json 거래대금 재정렬 스킵 (빠른 실행)
- fetch 없이 기존 CSV로 최신봉(4h 기준) 신호 재탐지

---

## 방향 2 — 멀티 TF 확증 필터

### `_tf_confirm(sym, direction)` 함수 추가 (scheduler.py)
- 1d 신호 발생 시 4h 최근 3봉 방향 체크
- **롱 신호**: 최근 3봉 중 양봉 2개 이상 → `tf_confirmed=True`
- **숏 신호**: 최근 3봉 중 음봉 2개 이상 → `tf_confirmed=True`
- 4h 데이터 없으면 `True` (확증으로 간주, 진입 유지)

### signals_today.json 변경
```json
{
  "pattern": "fvg",
  "direction": "short",
  "symbol": "BTC",
  "tf_confirmed": false,
  ...
}
```

### paper_executor.py 변경
- `tf_confirmed=False` → `size_usd` 50% 축소 (페이퍼 포지션)
- 기준: `POS_USD = $40` → 확증 실패 시 `$20`
- 출력: `[4h비확증] BTC short → size $20.0 (50%)`

### 적용 범위
- 1d 패턴(engulfing, fvg) + adopted_patterns(1d) → 확증 필터 적용
- 4h 전용 패턴 + 하모닉 → `tf_confirmed=True` 고정 (자체가 4h 신호)

---

## 방향 1 — 4h 전용 패턴 발굴

### 검증 대상
98개 종목 × 4h 데이터 (약 12,000봉/종목)

### 검증 결과

| 패턴 | 방향 | n | mean | median | OOS+ | p값 | 판정 |
|------|------|---|------|--------|------|-----|------|
| **Three White Soldiers** | long | 908 | **+1.04%** | **+0.97%** | **3/4** | **<0.0001** | **PASSED** |
| Three Black Crows | short | 573 | -1.19% | -0.37% | — | — | 기각 |
| Breakout + Retest | long | 25,729 | +0.37% | -0.23% | — | — | 기각 (median<0) |
| Equal Highs (SMC) | short | 6,962 | -0.26% | -0.25% | — | — | 기각 |
| Equal Lows (SMC) | long | 6,618 | -0.48% | -0.26% | — | — | 기각 |
| VWAP 이탈복귀 롱 | long | 31,005 | -0.25% | -0.67% | — | — | 기각 |
| VWAP 이탈복귀 숏 | short | 28,537 | -0.06% | +0.25% | — | — | 기각 (mean<0) |

### Three White Soldiers 4h — 상세

**게이트 전체 통과:**
- n=908 ≥ 20 ✓
- mean=+1.04% > 0 ✓
- median=+0.97% > 0 ✓
- baseline excess: +1.33% (랜덤 대비), p<0.0001 ✓
- OOS 4구간: 3/4 양 ✓

**OOS 구간별:**
| 구간 | 기간 | n | mean |
|------|------|---|------|
| Q1 | 2021.01~2022.08 | 189 | +1.46% |
| Q2 | 2022.08~2024.01 | 227 | +2.06% |
| Q3 | 2024.01~2025.05 | 234 | +2.88% |
| Q4 | 2025.05~2026.06 | 258 | **-1.85%** ← bear 레짐 |

**Q4 음수 주목**: 최근 bear 레짐에서 손실. **레짐 필터 필수**.

### 스케줄러 통합
- `universe.json["adopted_4h_patterns"]`에 등재
- 레짐 라우팅: `bull_btc` / `bull_altseason` → 롱 진입
- `bear` / `sideways` → 스킵
- `tf_confirmed=True` (4h 신호 자체이므로 추가 필터 불필요)
- 탐지 대상: `_harmonic_symbols()` (현재 98종목)

### 기각 패턴 기록
- `registry.json["rejected_4h"]` 에 사유 포함 기록
- `research_log.csv` 7건 추가 (총 93건)

---

## 다음 단계

- [ ] Three Soldiers 실제 신호 발생 모니터링 (bull 레짐 복귀 시)
- [ ] Breakout+Retest: 파라미터 조정 후 재시험 (tolerance 1% 타이트하게)
- [ ] Three Black Crows: 방향 반전 테스트 (숏 대신 롱, 역발상)
- [ ] VWAP: 2σ → 1.5σ 또는 당일 봉 수 조건 완화 후 재시험
- [ ] 데이터 누적 후 crab/shark/cypher 재시험

---

_게이트 동결 유지: n≥20, mean>0, median>0, p<0.05, OOS 2구간 이상_
