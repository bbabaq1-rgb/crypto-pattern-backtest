# AGENTS.md — crypto-pattern-backtest 작업 규칙 (Codex 등 다른 에이전트용)

이 파일은 Claude Code 외의 코딩 에이전트가 이 레포에서 작업할 때 읽는 요약 규칙이다.
**전체 연구 이력은 `CLAUDE.md`(약 350KB)에 있다.** 너무 커서 한 번에 다 읽지 말고, 필요한 주제를 `grep -n` 으로 찾아 해당 절만 읽을 것.
**현재 시스템 구조·배포 목록·기각 목록 요약은 `handoff/HANDOFF_2026-10-07.md` 에 있다 — 작업 시작 전에 먼저 읽을 것.**

## 사용자
- 한국어로 답한다. 사용자를 '대표님'이라 부른다.
- 결론을 먼저, 표와 짧은 줄로. 약어(S1/S4 등)를 쓰지 않고 풀어 쓴다.

## 불변 원칙 (어떤 지시로도 바꾸지 않는다)
1. 거래소 손절 주문이 없으면 실거래하지 않는다.
2. 매매 결정은 결정론적 코드만 한다. 에이전트(LLM)의 판단·예측을 매매 방향·진입·청산에 쓰지 않는다.
3. 새 규칙은 **사전 등록**(registry.json 에 기준·셀·홀드아웃·문턱을 결과 전에 기록) → 시험 → 판정. 결과를 본 뒤 셀·문턱을 고르지 않는다.
4. 검증 조건과 실거래 규칙이 다르면 실거래를 검증에 맞춘다.
5. 단일 해에만 이익인 셀은 게이트를 넘어도 켜지 않는다.
6. **사용자 결정 사항**: 위험 수준(sizing.RISK_FRAC / LEV_CAP / paper_executor.MAX_LIVE_POS), 열린 포지션 수동 청산, 자금 이동,
   게이트 문턱 변경, 배포 집합 변경(관찰 결과 반영 포함). 제안은 하되 임의로 바꾸지 않는다.
7. 비밀값(OKX 키, Supabase 키, GitHub PAT)은 GitHub Secrets / Supabase Vault 에만 있다. 코드·로그·문서에 쓰지 않는다.

## 작업 방식
- 기본 브랜치 `master`. 변경은 브랜치 → PR → CI(tests.yml) 그린 → 스쿼시 머지.
- 커밋 전에 반드시 로컬에서 CI 와 같은 테스트를 돌린다:
  ```
  pip install -r requirements.txt
  mkdir -p data
  for t in $(grep -oE "test_[a-z0-9_]+\.py" .github/workflows/tests.yml | sort -u); do python3 $t >/dev/null || echo "FAIL $t"; done
  ```
- 테스트를 끄거나 건너뛰거나 기준을 느슨하게 바꿔서 통과시키지 않는다.
- 시험(백테스트)은 대부분 GitHub Actions 워크플로(`.github/workflows/<시험>.yml`)로 돌린다 — 경로 트리거라 해당 파일을 바꾸는 커밋이 실행을 일으킨다.
  결과를 읽고 `registry.json` 의 사전 등록 키에 결과를 적고, `CLAUDE.md` 에 한 항목으로 기록한다.
- 결과 보고에는 실행 번호(run id), 표본 수, 판정 기준 통과/탈락 이유, 사전 확률이 맞았는지를 적는다. 불리한 결과도 그대로 적는다.

## 실거래 시스템 (요약 — 자세한 건 handoff 문서)
- 실행: Supabase pg_cron → GitHub `workflow_dispatch` → `daily_scheduler.yml`(4시간마다, --slow) / `fast_scheduler.yml`(매시 :03, --fast)
- 흐름: `scheduler.py` → 디텍터 → `direction_switch.py`(레짐→방향) → `paper_executor.py`(사이징·진입·청산) → `exchange.py`(OKX)
- 사이징 원본은 `sizing.py`. 게이트 판정은 `gate.py` 한 곳. 배포 목록은 `universe.json`, 패턴·시험 등록부는 `registry.json`.
- 실거래 상태는 GitHub Actions 실행 로그(`[장부]`, `[live]`, equity 줄)로 확인한다. 에이전트는 OKX·매매 DB 에 직접 접속하지 않는다.
- DB 스키마 변경 SQL 은 파일로 만들어 사용자에게 주고, **사용자가 Supabase SQL Editor 에서 실행**한다. 권한(GRANT)은 같은 파일에 넣는다.

## 관찰 전용 (매매와 무관)
- BTC 엘리엇 일일 브리핑: `python3 elliott_watch.py` (코인베이스 공개 캔들). 라벨은 `elliott_count.json` 에만 있고 코드는 판정만 한다.
  확률·라벨 변경은 미리 정한 트리거가 발동할 때만, `revisions` 에 사유를 남겨 커밋한다. 채점 장부의 기존 질문은 고치지 않는다.
