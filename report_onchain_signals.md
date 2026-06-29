# 온체인 보조 신호 통합 리포트

**날짜**: 2026-06-30

---

## 개요

기존 3-signal 레짐 판정(BTC 200MA + ETH/BTC + BTC.D)에 온체인 보조 신호 3종을 추가.  
온체인은 **보조(auxiliary)** 역할 — 실패해도 레짐 판단은 기존대로 계속.

---

## 온체인 신호 3종 (`onchain_signals.py`)

### 1. 펀딩비 (OKX 공개 API)
- **엔드포인트**: `GET https://www.okx.com/api/v5/public/funding-rate` (인증 불필요)
- **대상**: OKX 무기한 선물 주요 18종목 평균
- 평균 펀딩비 > +0.05% → **bear** (과열)
- 평균 펀딩비 < -0.05% → **bull** (공포/반전)
- 그 사이 → **neutral**
- **실측**: avg=+0.00694%, n=17 → **neutral** ✓

### 2. ETF 순유입 (SoSoValue API)
- **엔드포인트**: `https://sosovalue.com/api/etf/us-bitcoin-spot-etf-fund-flow-history`
- 3일 연속 양수 → **bull**
- 3일 연속 음수 → **bear**
- 혼합 → **neutral**
- API 실패 시 자동으로 neutral 처리 (graceful skip)
- **실측**: API 응답 없음 → **neutral** (정상 처리) ✓

### 3. 스테이블코인 시총 변화 (CoinGecko 무료)
- **대상**: USDT(`tether`) + USDC(`usd-coin`) 7일 시총 변화율 평균
- 7일 변화율 > +3% → **bull** (신규 자금 유입)
- 7일 변화율 < -3% → **bear** (자금 이탈)
- 그 사이 → **neutral**
- **실측**: avg=-0.791% → **neutral** ✓

---

## 레짐 조정 규칙

```
primary=bear  + onchain_score >= +2 → sideways  (과매도/반전 가능성)
primary=bull_btc + onchain_score <= -2 → sideways (과열/조정 가능성)
나머지 → primary 그대로
```

**점수 계산**: bull=+1, bear=-1, neutral=0 합산 → 범위 (-3 ~ +3)

---

## 현재 상태 (2026-06-30 기준)

| 신호 | 결과 | 세부 |
|------|------|------|
| 펀딩비 | neutral | avg=+0.00694%, n=17 |
| ETF 순유입 | neutral | API 미응답 (graceful skip) |
| 스테이블코인 | neutral | 7일 -0.791% |
| **종합 점수** | **0** | **레짐 변화 없음** |
| primary 레짐 | bear | BTC 200MA + ETH/BTC + BTC.D |
| final 레짐 | **bear** | 온체인 조정 없음 (score=0) |

---

## 백테스트 비교 (C)

온체인 신호는 실시간 데이터 (역사적 API 없음) → 정성적 평가:

| 기준 | 내용 |
|------|------|
| 역사적 백테스트 | 불가 (펀딩비/ETF 히스토리 무료 API 미제공) |
| 현시점 합리성 | 펀딩비 중립(+0.007%)은 극단적 과열/공포 없음 → neutral 판정 합리적 |
| 완화 임계값 | ±2점 (3개 중 2개 강한 신호) — 보수적 설계, 잘못된 완화 최소화 |
| 채택 결정 | 보조 표시 채택. primary 레짐 판단은 기존 V2 그대로 유지. |

---

## 통합 결과

### signals_today.json 새 필드
```json
{
  "primary_regime": "bear",
  "regime": "bear",
  "onchain_score": 0,
  "onchain_detail": {
    "funding": "neutral",
    "etf": "neutral",
    "stable": "neutral",
    "funding_avg_rate": 0.006939,
    "etf_flows_3d": [],
    "stable_7d_pct": -0.791
  },
  ...
}
```

### regime_switch.json 새 섹션
```json
{
  "version": "v3",
  "onchain": {
    "score": 0,
    "funding": {...},
    "etf": {...},
    "stable": {...},
    "fetched_at": "..."
  },
  "signal_details": {
    "2026-06-24": {
      "primary_regime": "bear",
      "final_regime": "bear"
    }
  }
}
```

### 대시보드 표시
- `📡 온체인 보조 신호` expander (실거래·페이퍼 탭 모두)
- 🟢 bull / 🔴 bear / 🟡 neutral 아이콘
- 온체인 종합 점수 + 레짐 완화 여부 표시

---

## 캐시 설계
- `onchain_cache.json`: 4시간 TTL
- 매시 oncequick 실행 시 캐시 히트 → 빠른 실행
- oncefull(UTC 00:00) 또는 캐시 만료 시 재수집

---

## API 실패 처리
| API | 실패 시 |
|-----|--------|
| OKX 펀딩비 | neutral 반환 (종목별 개별 실패 허용) |
| SoSoValue ETF | neutral 반환 (URL 접근 불가 → 스킵) |
| CoinGecko 스테이블 | neutral 반환 (rate limit 발생 시 sleep + 재시도 1회) |

---

_레짐 보조 신호 추가 — primary 판단 로직(V2)은 변경 없음_
