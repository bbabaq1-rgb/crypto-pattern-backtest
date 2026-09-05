# 라우팅 게이트 — 베이스라인 표본 정합 + 진입 방향 arm 시험

2026-09-05. run 33947910558(1차) / **33949570271(확정)**. 사용자 지시.
실거래 규칙 무변경 — 판정만 낸다.

## 출발점

사용자 문제 제기: *"잘못 설정된 레짐이 매매를 막을 수도 있는 것 아닌가. 아무리 봐도
알트 불장이 올 것 같은데 숏만 본다고 하니."*

두 전제를 코드로 확인했더니 방향이 반대였다.

1. **"숏만 본다"는 사실이 아니다.** `bull_altseason` 에서 도는 배포 패턴 6종 중 5종이 롱이다
   (fvg·inverted_hammer·marubozu·three_soldiers_4h·cascade_fade_long_1h). 숏은 engulfing 하나다.
2. **`bull_altseason` 은 레짐이 매매를 가장 안 막는 상태다.** `three_soldiers_4h` 는 bear·sideways
   에서 통째로 스킵되는데(`scheduler.py:662`) 지금은 돈다. 현재 라벨 때문에 꺼진 셀은 없다.

대신 다른 문제가 있었다 — 그게 이 시험의 대상이다.

---

## 1. boot_p 베이스라인 표본 정합 (k=30 → k=n)

### 버그

`gate_cell` 의 베이스라인은 *"같은 레짐·코호트에서 무작위로 **n번** 진입했다면 평균이 얼마였겠나"*
를 답해야 한다. 그런데 표본 수가 30 에 묶여 있었다.

```python
k = min(max(10, min(30, n)), len(pool))   # 종전 (validate_regime_split.py:83)
```

셀이 n=75 여도 베이스라인은 30 개만 뽑는다. 베이스라인 평균의 표준오차가 `sqrt(30)` 에 고정되고,
분포가 실제보다 넓어진 만큼 더 많은 draw 가 셀 평균을 넘어선다 → **boot_p 가 부풀려진다(보수적).**

이것이 `engulfing 숏 · top30 · bull_altseason` 이 재실행에서 `.045 ↔ .055` 로 진동한 원인이다.
**판정이 흔들린 건 데이터가 아니라 추정량 탓이었다.**

### 수정

- `k = n`. **게이트 문턱(n≥20, mean>0, median>0, boot_p<0.05, OOS≥2)은 손대지 않았다** —
  boot_p 가 자기가 주장하는 값을 재도록 고친 것뿐이다.
- **한쪽으로 느슨해지는 변경이 아니다.** 엣지가 양수인 셀은 boot_p 가 내려가고 음수인 셀은
  올라간다. `test_regime_split.py` 가 두 방향을 다 고정한다.
- `len(pool)` 상한 제거 — `rng.choices` 는 복원추출이라 상한이 걸리면 풀이 얇은 셀에서 같은
  보수 편향이 재발한다. 대신 `pool_n` 을 기록한다.
- 풀 `outcome` 을 한 번만 평가해 재사용(결정론적 함수). `BOOT_N × k` 회 호출이 사라져 k 를
  키우면서도 더 빠르다.
- 같은 코드가 복사돼 있던 `validate_regime_split_all.py:166` 도 함께.

### 결과 — 통과 셀 2개 → **18개**

| 패턴 | 통과 셀 |
|---|---|
| engulfing (롱) | all·top20·top30 `bull_btc`, top20·top30 `ALL` |
| **engulfing_short** | all·top20·top30 **`bull_altseason`** |
| fvg (롱) | all·top20·top30 `bull_btc` |
| fvg_short | top20 `bear` |
| inverted_hammer | all·top20·top30 `bear`, top20·top30 `ALL` |
| marubozu | all:`ALL` |

**보수 편향이 컸다.** 종전 리포트의 "72셀 중 통과 2셀, 우연 기대와 구분 어려움" 은 상당 부분
측정 결함이었다.

**그리고 사용자 기대와 반대되는 결과가 나왔다 — `engulfing_short · bull_altseason` 은 세 코호트
모두 통과한다.** 경계 진동이 통과 쪽으로 해소됐다. 지금 engulfing 이 숏으로 나가는 것은
동결 게이트가 지지하는 선택이다.

### 앞선 진단의 정정

시험 전에 이렇게 적었다: *"동결 게이트에서 기각된 숏이, 게이트를 거치지 않은 표를 근거로 켜진다."*

**무조건부 게이트**(`registry.json`: engulfing_short **rejected**) 기준으로는 맞는 말이었다.
그러나 **레짐 분리 게이트**로 보면 `bull_altseason` 셀은 통과한다 — 베이스라인을 고친 뒤에는.
즉 문제는 규칙이 아니라 측정이었고, 측정을 고치니 현행 라우팅이 정당화됐다.

---

## 2. 진입 방향 arm 시험 — `validate_routing.py`

청산은 세 arm 모두 방식D 로 동일하다. **다른 것은 진입 방향뿐이다.**

| arm | 방향 결정 |
|---|---|
| `route` | 현행 실거래. `direction_switch.decide()` + `ROUTING_OVERRIDES` 를 그대로 호출해 복제 |
| `uncond` | 레짐을 방향에 쓰지 않음. 게이트가 검증한 방향 = engulfing·fvg 둘 다 롱 |
| `gated` | 레짐 라우팅이되 분리 게이트 통과 셀만, 없으면 FLAT |

표본: 유니버스 80 / 1800일 / 실거래 코호트(engulfing=top20, fvg=top30). 후보 engulfing 313 + fvg 2,910.

### 방향 표

| 레짐 | 패턴 | route | uncond | gated |
|---|---|---|---|---|
| bull_altseason | engulfing | **short** | long | **short** |
| bull_altseason | fvg | long | long | FLAT |
| bull_btc | engulfing | long | long | long |
| bull_btc | fvg | long | long | long |
| bear | engulfing | long | long | FLAT |
| bear | fvg | FLAT | long | FLAT |
| sideways | 둘 다 | FLAT | long | FLAT |

**route 와 gated 는 8셀 중 6셀이 같다.** 다른 두 셀은 모두 *게이트가 아무것도 통과시키지 못한
자리에서 route 가 거래하는* 경우다 — 게이트와 라우팅이 방향을 두고 충돌하는 셀은 **하나도 없다.**

### 성과 (연율화는 분할 공통 창)

| arm | 분할 | n | 건당평균 | 중앙 | 승률 | CAGR | MDD | Calmar |
|---|---|---|---|---|---|---|---|---|
| **route** | train | 996 | +7.30% | −3.79% | 41% | **+103.2%** | −45.2% | **2.29** |
| uncond | train | 1,219 | +6.88% | −8.20% | 38% | +82.3% | −50.4% | 1.63 |
| gated | train | 849 | +8.35% | −3.68% | 43% | +71.0% | −43.1% | 1.65 |
| **route** | holdout | 87 | −4.09% | −8.20% | 17% | **−43.2%** | −54.5% | −0.79 |
| uncond | holdout | 360 | −1.78% | −8.20% | 24% | −65.5% | −77.2% | −0.85 |
| gated | holdout | 41 | −7.01% | −8.20% | 5% | −35.7% | −36.6% | −0.98 |

### 분기 셀 — 사용자 질문에 대한 직접 답

| 셀 | route | uncond |
|---|---|---|
| **bull_altseason engulfing** | **숏 n=53, +0.32%** | **롱 n=11, −2.77%** |
| bear fvg | FLAT n=0 | 롱 n=538, **+1.63%** |

| 셀 | route | gated |
|---|---|---|
| bear engulfing | 롱 n=47, **+2.41%** | FLAT n=0 |
| bull_altseason fvg | 롱 n=146, +0.02% | FLAT n=0 |

**`bull_altseason` 에서 engulfing 롱은 11건뿐이고 평균 −2.77% 다.** 숏이 낫다.

### 판정 — 둘 다 현행 유지

| arm | ①CAGR | ②Calmar | ③분기 | ④전후반 | ⑤MDD | ⑥부트 | ⑦holdout | 판정 |
|---|---|---|---|---|---|---|---|---|
| uncond | ✗ | ✗ | ✓ | ✗ | ✗ | ✗ (31%) | ✗ | **현행 유지** |
| gated | ✗ | ✗ | ✗ | ✗ | ✓ | ✗ (7%) | ✓ | **현행 유지** |

부트스트랩 Calmar 중앙: route **1.28** vs uncond 0.91 vs gated 0.83.

**route 는 룩어헤드 이점을 갖고 있었다** — 라우팅 표가 전 기간 데이터로 적합됐다(파일 상단에
사전 명시). 그래서 route 의 승리는 그만큼 할인해 읽어야 한다. 다만 uncond·gated 가 **7기준 중
5~6개에서 졌으므로** 할인으로 뒤집힐 폭이 아니다.

### 기준 ③이 통과한 건 엉뚱한 이유다 (설계 한계, 기록)

집계로는 uncond 가 분기 셀에서 이겼다(+1.54% vs +0.32%). 그러나 **그 우위는 전부
`bear fvg` 롱 538건에서 나왔고, 정작 문제의 `bull_altseason engulfing` 셀에서는 크게 졌다.**
분기 표본을 셀 구분 없이 합친 기준 설계의 한계다.

**사후에 기준을 바꾸는 것은 사전 등록 원칙 위반이므로 판정은 그대로 둔다.** 다음 시험 설계 시
'분기 평균은 셀별로 부호를 요구한다'를 넣는다 — `validate_short_exit` 의 대조군에서 부호 조건을
빠뜨렸던 것과 같은 종류의 실수다.

---

## 3. 3단계 제안(라우팅에 동결 게이트 적용)에 대한 답 — **하지 말 것**

`gated` arm 이 정확히 그 제안이었다. 결과는 **route 보다 나쁘다**: CAGR 103%→71%, Calmar
2.29→1.65, 부트 우위 7%.

이유는 분기 표에 있다. 게이트를 라우팅에 걸면 꺼지는 셀이 **`bear engulfing` 롱(n=47, +2.41%)**
과 **`bull_altseason fvg` 롱(n=146, +0.02%)** 인데, 앞의 것이 수익 나는 셀이다. 레짐별로 쪼갠
셀은 표본이 작아 게이트를 통과 못 할 뿐, 엣지가 없다는 뜻이 아니다 — **게이트를 라우팅 계층에
그대로 옮기면 '표본 부족'을 '엣지 없음'으로 잘못 읽는다.**

제안했던 사람이 나이므로 명확히 적는다: **이 제안은 시험했고 기각됐다.**

---

## 4. 방법론 결함 하나를 실행 중 발견해 고쳤다

1차 결과를 읽다 비교 자체의 결함을 찾았다. `equity_curve` 는 CAGR 을 **그 arm 자신의 첫~마지막
거래 간격**으로 연율화한다. arm 마다 거래 집합이 사실상 같은 `method_x` 에서는 문제가 없지만,
arm 이 서로 다른 신호를 잡는 이 시험에서는 분모가 arm 마다 달라진다.

실측으로 드러났다 — 1차 실행에서 **gated holdout 은 MDD −36.6% 인데 CAGR −92.2%** 로 찍혔다
(route 는 MDD −54.5% / CAGR −43.6%). 낙폭이 더 얕은 arm 이 CAGR 은 두 배 나쁜 모순이다.
41건이 몇 달에 몰려 분모가 작았던 탓이다.

- `equity_curve(trades, span_days=None)` — 기본값은 종전 동작 그대로라 `method_x` 의 기록된
  수치는 변하지 않는다(테스트로 고정).
- 분할 창은 **분할**이 정한다: train = 첫 신호~cutoff, holdout = 365일, 부트스트랩 =
  재표집 타임라인 길이.
- 전반/후반에도 같은 결함이 있었다 — `mid` 를 arm 별 거래 중앙값으로 잡아 arm 마다 '전반'이
  다른 기간이었다. 달력 중점으로 통일.

**수정 효과**: gated holdout CAGR −92.2% → **−35.7%**, 기준 ⑦ 이 ✗ → ✓ 로 뒤집혔다. gated train
CAGR 도 +120.4% → +71.0% 로 크게 내려갔다(거래가 짧은 구간에 몰려 부풀려져 있었다).
**판정 자체는 불변** — 둘 다 Calmar·부트에서 졌고 그 둘은 이 결함과 무관하다.

테스트가 잡은 버그 둘도 함께 기록한다.
- **부트스트랩 짝지음 정렬** — 거래 0건인 draw 에서 값을 건너뛰면 arm 마다 리스트 길이가 달라져
  `zip` 짝이 어긋난다. 기준 ⑥ 이 서로 다른 draw 를 비교하게 되는 조용한 오류였다.
- **분기 셀 소음** — 표는 다르지만 그 레짐에 신호가 없는 셀(sideways)이 분기로 잡혔다.

---

## 5. 결론과 후속

**실거래 규칙 무변경.** 현행 라우팅이 세 판정 모두에서 최선이다.

- 사용자 직관(*알트 불장이 올 것 같으니 롱*)과 데이터가 갈린다. `bull_altseason` 은 **후행 라벨**이라
  붙는 시점이 이미 국면 후반이고(무작위 롱 20봉 −3.04%, `report_regime_split.md`), 그 레짐의
  engulfing 롱은 11건 −2.77% 다.
- '라벨을 더 빠르게' 경로는 이미 닫혀 있다(`report_regime_quality.md`: 라벨러 6후보·arm 19개 전부 REJECT,
  지평 20/40/60/90일 전부 적중 47~49%).

### 후속 과제 (신규)

- [ ] **`bear fvg` 롱 재검토** — uncond 분기에서 n=538 · **+1.63%**. 어제 사용자 결정으로 FLAT 이고
      `report_regime_split.md` 도 엣지 +1.34%p 로 부호가 맞다고 봤다. 다만 그걸 켠 uncond 는 포트폴리오
      CAGR·MDD 가 오히려 나빠졌다(슬롯·증거금 경합). **단일 셀 사전 등록 시험**이 필요하다 —
      uncond 처럼 4셀을 한꺼번에 바꾸는 arm 으로는 이 셀만의 기여를 분리할 수 없다.
- [ ] **`fvg_short · top20 · bear` 통과 셀** — 게이트는 통과하나 실거래 fvg 코호트는 top30 이고
      거기서는 통과하지 못한다. 현행(FLAT)과 충돌하지 않지만 코호트 경계에 걸쳐 있어 기록해 둔다.
- [ ] **종전 리포트 boot_p 재해석** — `report_regime_split.md` / `report_regime_split_all.md` 의
      boot_p 는 전부 보수 편향분이다. `_all` 의 "440셀 PASSED 0" 도 재실행 대상.

## 파일

`validate_regime_split.py` · `validate_regime_split_all.py`(베이스라인) / `validate_routing.py`(신설) /
`method_x.py`(`span_days`) / `test_routing.py`(47건) · `test_regime_split.py` /
워크플로 `routing_gate.yml` / 출력 `_regime_split.json` · `_routing.json`
