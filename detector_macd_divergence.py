"""
detector_macd_divergence.py - MACD Divergence 탐지 (orchestrator 자동 생성 스켈레톤)

TODO: 이 패턴의 탐지 규칙을 구현해야 함 (사람이 채울 자리).
  - detector_liquidity_sweep.py 구조를 참고.
  - 아래 evaluate(date_from, date_to)를 구현하면 orchestrator가
    자동으로 백테스트/게이트/OOS재테스트를 돌린다.
  - 반환 형식: dict(agg={"n":..,"real":..,"fake":..,"neutral":..},
                   per={symbol: {...}})
  - 라벨 기준은 1단계와 동일(+15% 선도달=real, -10% 선도달=fake, 그외 neutral).
"""

PATTERN = "macd_divergence"


def evaluate(date_from=None, date_to=None):
    raise NotImplementedError("TODO: MACD Divergence 탐지 규칙 구현 필요")
