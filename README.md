# crypto_pattern_backtest

차트 패턴 detector + 거래량 확인 + 워크포워드 백테스트 하니스.
데이터 수집(ccxt)부터 백테스트·confidence 보정까지 한 세트로 묶여 있다.

> 면책: 학습·연구용 도구이며 투자 자문이 아니다. 백테스트 결과가 미래 수익을
> 보장하지 않는다. 실거래 적용 전 충분한 검증과 리스크 관리는 본인 책임이다.

---

## 폴더 구성
```
crypto_pattern_backtest/
├── elliott_detect.py        # 엘리엇 임펄스(5파) detector
├── terminal_detect.py       # 터미널/엔딩 다이애고널 detector
├── triple_bottom_volume.py  # 삼중바닥 detector + 거래량 확인 프레임워크
├── reversal_patterns.py     # 헤드앤숄더(정/역), 쌍바닥/쌍천정
├── breakout_indicators.py   # 박스권 돌파, RSI 다이버전스, 이동평균 교차
├── fetch_data.py            # ccxt OHLCV 수집기 (CSV 저장)
├── backtest.py              # 워크포워드 백테스트 하니스
├── run_synthetic_test.py    # 합성 데이터로 전체 파이프라인 검증
├── requirements.txt
└── README.md
```

## detector 목록 (--detector 값)
| 이름 | 패턴 | 방향 | 거래량확인 |
|---|---|---|---|
| `triple_bottom` | 삼중바닥(수평형, 저점 spread ≤3%) | 상승 | O |
| `triple_bottom_desc` | 삼중바닥(하강형, a>c>e, 총하락 3~12%) | 상승 | O |
| `inverse_hs` / `hs` | 역헤드앤숄더 / 헤드앤숄더 | 상승 / 하락 | O |
| `double_bottom` / `double_top` | 쌍바닥 / 쌍천정 | 상승 / 하락 | O |
| `breakout` | 박스권 돌파 | 양방향 | O |
| `rsi_divergence` | RSI 다이버전스 | 상승/하락 | - |
| `ma_cross` | 골든/데드크로스 | 상승/하락 | - |
| `elliott` / `terminal` | 엘리엇 임펄스 / 터미널 쐐기 | - | - |

모두 동일한 `Signal(pattern, direction, confidence, detail)` 를 반환하며,
`detail['matched']` 는 (해당되는 패턴의 경우) 모양 AND 거래량 동시 충족 여부다.

## 설치
```bash
pip install -r requirements.txt        # ccxt 만 필요 (나머지는 표준 라이브러리)
```

## 1) 데이터 없이 먼저 검증 (인터넷 불필요)
```bash
python run_synthetic_test.py
```
합성 삼중바닥 데이터로 fetch→backtest 플러밍이 도는지 확인한다.
triple_bottom 이 다수 신호 + 높은 승률로 잡히면 정상.

## 2) 실데이터 수집 (인터넷 열린 환경에서)
```bash
# 바이낸스 BTC/USDT 일봉, 2021년부터
python fetch_data.py --exchange binance --symbol BTC/USDT --timeframe 1d \
                     --since 2021-01-01 --out data/btc_1d.csv

# 업비트 BTC/KRW 4시간봉 (알트코인 KRW 페어도 동일하게)
python fetch_data.py --exchange upbit --symbol BTC/KRW --timeframe 4h \
                     --since 2023-01-01 --out data/btc_krw_4h.csv
```
출력 CSV 컬럼: `timestamp, datetime, open, high, low, close, volume`

## 3) 백테스트
```bash
python backtest.py --csv data/btc_1d.csv --detector triple_bottom --hold 10 --min-conf 0.6
python backtest.py --csv data/btc_1d.csv --detector all --hold 7 --fee 0.001
```
옵션:
- `--detector` : `elliott | terminal | triple_bottom | all`
- `--hold`     : 신호 후 몇 봉 뒤 종가로 수익을 측정할지 (forward return 구간)
- `--min-conf` : 이 confidence 미만 신호는 제외
- `--fee`      : 편도 수수료율 (0.001 = 0.1%, 왕복 2배 차감)

## 출력 읽는 법
- `승률 / 평균 수익` : 신호 이후 hold봉 동안의 방향성 수익(롱/숏 부호 처리, 수수료 차감 후).
- `confidence 구간별 표` : **이게 핵심.** 예) "0.8~1.0 구간 승률 68%"가 나오면,
  detector 의 confidence 점수를 실제 적중 확률로 '보정'하는 근거가 된다.
- 신호 수가 너무 적으면(예: <20) 승률은 우연일 수 있으니 표본을 늘려 해석한다.

## 설계상 보장 (왜 이 숫자를 믿을 수 있나)
- look-ahead 차단: i봉 판정 시 detector 에 `candles[:i+1]`만 전달, 결과는 이후 봉으로만 측정.
- 중복 매매 방지: 같은 패턴 인스턴스(피벗 시그니처) 재매매 금지 + 보유기간 쿨다운.
- 거래량 일치: triple_bottom 은 모양 AND 거래량(`matched`)일 때만 신호 인정.

## 운영 자동화 (선택)
완성 후엔 Claude 없이 스스로 돌게 만들 수 있다. 예: GitHub Actions 로
매일/매주 `fetch_data.py` → `backtest.py` 를 실행해 리포트를 커밋하면 무인 운영이 된다.
(워크플로 예시가 필요하면 Claude Code 에 "이 저장소에 매일 도는 Actions 워크플로 만들어줘"라고 요청.)

## 한계 (정직하게)
- confidence 는 보정 전 규칙 충족 점수다. 위 구간별 표로 실제 확률에 맞춰 해석할 것.
- 수수료는 반영하지만 슬리피지·체결 실패는 단순화돼 있다.
- 파라미터(ZigZag 임계값 등) 과최적화 주의 → 학습구간/검증구간 분리 권장.
- 엘리엇·터미널은 '패턴 발생 후 결과' 연구에 가깝고, triple_bottom 이 가장 매매 신호에 가깝다.

---

## Claude Code 에게 통째로 넘길 때
이 폴더를 열고 다음과 같이 요청하면 끝까지 자동 수행한다:

> "이 폴더의 fetch_data.py 로 바이낸스 BTC/USDT 일봉 2021년부터 받아서
>  data/btc_1d.csv 로 저장하고, backtest.py 로 triple_bottom 을 hold 10,
>  min-conf 0.6 으로 백테스트한 다음 결과를 요약해줘."
