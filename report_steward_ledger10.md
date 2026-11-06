# R-096 steward 규칙 — 장부 prior, 단위 최소 n 10 판 (2026-11-06)
registry `steward_ledger10_prereg_2026_11_06`, run 42254456752. 연구 전용, steward 상수·실거래 무변경, DEPLOY_ON_PASS=False.

R-092 는 n>=20 단위가 2개뿐이라 INCONCLUSIVE 였다. MIN_UNIT_N=10·MIN_UNITS=4 를 실행 전 고정해 같은 시험(규칙 8개·시드·판정식 불변)을 다시 돌렸다.

## 결과: CURRENT_RETAINED
- 장부 방식D 227행, 단위 8개, 수축 mu 전부 음수(−4.57 ~ −0.36%).
- J: NEVER 0 / **현행 +109.5** / L2 +97.8 / L1 +75.4 / C1 +86.0 / C2 +67.1 / C3 +64.6 / L3 +51.9.
- best=L2 이나 현행 대비 차이 −11.6 (CI [−12.5, −10.8]) → c1 실패, c2·c3 실패, c4·c5 통과.
- 해석: 장부 prior 에서는 정지가 가치를 가진다(NEVER 대비 J 가 크게 양수)는 R-092 방향이 단위 8개로 확인됐고, 현행 문턱이 후보 6개보다 낫다. R-082(백테스트 prior)와 부호가 반대다.

## 사전 확률 채점
CURRENT_RETAINED 0.30 / NEVER_PREFERRED 0.30 / INCONCLUSIVE 0.30 / ADOPT 0.10 — 범주 적중, ADOPT 미채택 적중. 우려한 "수축이 grand 로 쏠려 정보 없음" 은 단위 8·mu 일관 음수라 해당 없음.

## 한계
한 국면 장부(10/10 이후 bull_btc 알트 롱 손실 지배) · 규칙 평가와 prior 가 같은 장부(순환) · 문턱 완화값은 R-092 결과를 본 뒤 정했으나 실행 전 고정. 후속: R-099(국면 분할 prior), R-098(문턱 분해).
