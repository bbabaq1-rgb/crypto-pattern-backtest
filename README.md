# crypto-pattern-backtest

암호화폐 차트 패턴 자동 감지 → 백테스트 → 자동매매 시스템

> **면책:** 학습·연구용 도구이며 투자 자문이 아닙니다. 백테스트 결과가 미래 수익을 보장하지 않습니다.

---

## 대시보드 (Streamlit)

### 로컬 실행

```bash
pip install -r requirements.txt
# .env 파일에 SUPABASE_URL, SUPABASE_ANON_KEY 설정 후:
streamlit run dashboard.py
```

### Streamlit Cloud 배포

1. **[share.streamlit.io](https://share.streamlit.io)** 접속
2. **"New app"** → GitHub 계정 연결 → 이 저장소 선택
3. **Main file path:** `dashboard.py` 선택
4. **Advanced settings → Secrets** 에 아래 입력:

```toml
SUPABASE_URL = "https://<your-ref>.supabase.co"
SUPABASE_ANON_KEY = "<your-anon-key>"
```

5. **"Deploy!"** 클릭 → 배포 완료 후 URL 공유

> Secrets는 Supabase 프로젝트 설정 → **Data API** 에서 확인합니다.  
> `SUPABASE_ANON_KEY`(읽기 전용)만으로도 대시보드는 동작합니다.

---

## 파이프라인 구조

```
scheduler.py         # 메인 스케줄러 (매일 UTC 00:00 자동 실행)
├── fetch_data.py    # OKX OHLCV 수집
├── regime_switch.py # 레짐 판정 (bear/bull_btc/bull_altseason/sideways)
├── direction_switch.py # 레짐→방향 라우팅
├── detector_*.py    # 패턴 검출 (engulfing, fvg, inverted_hammer, marubozu)
└── paper_executor.py # 페이퍼/실거래 체결 엔진
    └── exchange.py  # OKX 선물 실거래 연결
```

## 주요 파일

| 파일 | 역할 |
|---|---|
| `scheduler.py` | 매일 UTC 00:00 파이프라인 실행 |
| `paper_executor.py` | 페이퍼 + OKX 선물 실거래 체결 |
| `exchange.py` | OKX 연결, `is_live()`, `place_swap_entry()` |
| `regime_switch.py` | BTC 가격·도미넌스 기반 레짐 판정 |
| `orchestrator.py` | 패턴 검증 루프 |
| `universe.json` | 유니버스 12종목 (OKX 기준) |
| `registry.json` | 패턴 등록부 |
| `dashboard.py` | Streamlit 실시간 대시보드 |

## 환경변수

| 변수 | 용도 |
|---|---|
| `SUPABASE_URL` | Supabase 프로젝트 URL |
| `SUPABASE_SERVICE_KEY` | 쓰기(scheduler/paper_executor 용) |
| `SUPABASE_ANON_KEY` | 읽기(dashboard 용) |
| `OKX_KEY` | OKX API 키 (3종 모두 있으면 선물 실거래 활성화) |
| `OKX_SECRET` | OKX API Secret |
| `OKX_PASSPHRASE` | OKX API Passphrase |

## 실거래 규칙 (불변)

- USDT 무기한 선물(swap)만 — 롱/숏 모두 가능
- 레버리지 2x 고정 (코드 강제)
- 격리 마진(isolated) 고정
- 포지션 사이징: 첫 주문 $20, 이후 잔고×20% (최소 $10)
- 동시 최대 5포지션
- 시장가 진입 직후 손절(-8%) 동시 제출 필수

## 검증 완료 패턴

| 패턴 | n | 평균수익 | OOS |
|---|---|---|---|
| engulfing | 200 | +2.52% | 통과/통과 |
| fvg | 1743 | +2.76% | 통과/통과 |
| inverted_hammer | 641 | +1.78% | 통과/통과 |
| marubozu | 90 | +3.20% | 통과/통과 |

## 게이트 기준 (동결)

`n ≥ 20` · `평균수익 > 0` · `중앙값 > 0` · `베이스라인 p < 0.05` · `OOS 양구간 통과`

---

기존 README (참고용):

차트 패턴 detector + 거래량 확인 + 워크포워드 백테스트 하니스.
데이터 수집(ccxt)부터 백테스트·confidence 보정까지 한 세트로 묶여 있다.
