# 트레이딩 유니버스 확대 리포트

**날짜**: 2026-06-29  
**소스**: 업비트 KRW 상장 ∩ OKX USDT-swap 선물 동시 상장

---

## 1. 교집합 수집 결과

| 구분 | 수치 |
|------|------|
| 업비트 KRW 상장 | 266종목 |
| OKX USDT-swap 활성 | 386종목 |
| 교집합 (스테이블 제외) | 155종목 |
| 기존 유니버스 제외 후 신규 후보 | 124종목 |

---

## 2. 데이터 fetch 결과

| 구분 | 종목 수 | 비고 |
|------|---------|------|
| OKX 1d 500봉 이상 | 39종목 | |
| Binance fallback 500봉 이상 | 27종목 | OKX 미보유 → Binance |
| 데이터 부족 (< 500봉) | 56종목 | 최근 상장 토큰 |
| FAIL (거래소 미보유) | 2종목 | ARX, ATH |
| **합계** | **124종목** | |

---

## 3. 패턴 검증 결과

검증 기준: n≥5 AND mean>0 for any pattern → 채택

| 구분 | 종목 수 |
|------|--------|
| 채택 | 59종목 |
| 기각 (데이터는 있으나 기대값 음수) | 10종목 |
| 데이터 부족 | 55종목 |

### 신규 채택 59종목
1INCH, AGLD, API3, APT, ARB, ARKM, ATOM, AUCTION, AXS, BAT,
BERA, BONK, CELO, CHZ, COMP, CRO, DOT, EGLD, ENS, ETC,
ETHFI, GAS, GLM, GMT, GRT, ICP, ICX, IMX, INJ, IOST,
IOTA, LINK, LTC, MANA, MASK, MINA, MOVE, NEO, ONT, OP,
PENDLE, POL, QTUM, RAY, RENDER, RVN, SAND, SEI, SHIB, STX,
THETA, UNI, VANA, W, WIF, ZIL, ZK, ZRO, ZRX

### 기각 종목 (검증 실패)
ANIME, BIO, BLUR, JUP, LPT, ME, PROS, PYTH, XTZ, YGG

---

## 4. 최종 유니버스

**총 71종목** (기존 12 + 신규 59)

### 기존 12종목 (1d 검증 통과)
BTC, SOL, ETH, XRP, ADA, AVAX, TRX, NEAR, AAVE, DYDX, HBAR, FIL

### 신규 59종목 (이번 확대)
상기 3번 신규 채택 59종목 참조

---

## 5. 패턴별 월 예상 신호 수 (71종목 기준)

| 패턴 | 과거 총신호 | 월 예상 | 평균수익 | 중앙값 |
|------|------------|--------|--------|--------|
| engulfing | 433건 | ~8건/월 | +0.50% | +0.20% |
| fvg | 4,570건 | ~81건/월 | +1.75% | +1.92% |
| inverted_hammer | 1,795건 | ~32건/월 | +0.37% | -2.41% |
| marubozu | 259건 | ~5건/월 | +0.59% | -2.70% |
| **합계 (1d)** | **7,057건** | **~125건/월** | | |
| gartley/bat/butterfly (4h) | - | 추산 불가 | - | - |

> 월 예상 = 신호 빈도(bars당) × 30 × 71종목  
> 실제 실행 건수는 레짐 필터(bull_btc=롱, bear=숏 등) 적용 후 대폭 감소

---

## 6. 데이터 파일 현황

| 타임프레임 | 파일 수 |
|-----------|--------|
| 1d CSV | 78개 |
| 4h CSV | 97개 |

---

## 7. 스케줄러 변경 사항

- `_fetch_one(sym, exchange, tf)` — tf 파라미터 추가
- `fetch_all()` — 4h fetch 루프 추가 (하모닉용)
- `_harmonic_symbols()` — data/*_4h.csv 기반으로 동적 로드
- `run_once()` — 하모닉 레짐 라우팅 추가:
  - `bull_btc` → gartley/bat/butterfly 롱 신호 등록
  - 기타 레짐 → 하모닉 스킵

---

## 8. paper_executor 변경 사항

- OPP 딕셔너리에 gartley/bat/butterfly long 쌍 추가
- `rows_of(sym, tf)` — tf 파라미터 + (sym, tf) 캐시 키
- 포지션 로드 시 `tf` 필드 반영

---

## 9. 다음 단계

- [ ] OKX 실거래 활성화 (GitHub Actions secrets 이미 등록됨)
- [ ] 71종목 기준 방식D 게이트 재검토 (신규 종목 데이터 누적 후)
- [ ] crab/shark/cypher 재시험 (데이터 누적 후)
- [ ] 데이터 부족(55종목) 재검토 — 6개월 후 재시험
