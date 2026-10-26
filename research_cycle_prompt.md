당신은 crypto-pattern-backtest 레포의 **자율 연구 사이클**이다(사용자 결정 2026-10-26: 가설의 선택·사전 등록·실행·기록은 에이전트의 일). 이 세션에서 한 사이클을 끝내라.

세션 사정: 이 세션은 스포너가 `create_session(source_url=레포)` 로 만들어 레포가 `/home/user/crypto-pattern-backtest` 에 체크아웃돼 있다(예약 작업이 직접 만든 세션에는 레포가 붙지 않아 2026-10-26 두 번 실패했다). MCP 커넥터는 없다. 준비 ①~③의 성공 여부를 마지막 보고에 한 줄로 포함하라.

준비 — 순서대로:
① `cd /home/user/crypto-pattern-backtest && git fetch origin master && git checkout master && git pull --ff-only origin master`. 디렉터리가 없으면(그럴 때만) `mcp__claude-code-remote__add_repo`(owner `bbabaq1-rgb`, repo `crypto-pattern-backtest`, access `push`)를 사전 확인 없이 호출해 응답의 clone 명령을 실행하고 `mcp__claude-code-remote__register_repo_root` 를 호출한다.
② CLAUDE.md 가 컨텍스트에 로드돼 있지 않으면 `sed -n` 으로 '## 핵심 원칙' 절과 '## 다음 할 일' 절을 직접 읽는다.
③ `gh api repos/bbabaq1-rgb/crypto-pattern-backtest/branches/master` 로 GitHub 프록시 자격이 사는지 확인한다.
④ **RESEARCH_LOOP.md 를 읽고 그대로 따른다**(절차 7단계·불변 조항·우선순위 산식이 전부 거기 있다). 가설 큐는 research_backlog.json.
①~③ 중 하나라도 실패하면(권한 거부·403·404·clone 실패) **그 자리에서 멈추고** 마지막 메시지에 어느 단계가 어떤 오류로 실패했는지 한 줄로 적는다. 레포 없이 코드 내용을 추측하거나 가짜 결과를 만들지 않는다.

도구 사정(이 세션에는 MCP 커넥터가 없다): GitHub 는 `gh api`(REST — PR 생성 `POST repos/{o}/{r}/pulls`, 준비 `POST .../pulls/{n}/ccr/ready_for_review`, 머지 `PUT .../pulls/{n}/merge`, 체크 `GET .../commits/{sha}/check-runs`, 워크플로 dispatch `POST .../actions/workflows/<file>.yml/dispatches`, 실행 조회 `GET .../actions/runs?...`, 잡 로그 `GET .../actions/jobs/{id}/logs`). Supabase 는 직접 못 읽는다 — DB 를 읽어야 하는 항목(장부 부검 등)은 observation_report.yml 처럼 **GitHub Actions 워크플로(시크릿 보유)에서 읽어 아티팩트·로그로 받는다**. 러너 결과를 기다릴 때 `send_later` 가 있으면 체크인을 걸고, 없으면 Bash `run_in_background` 로 `gh api` 를 60초 간격으로 폴링해 run 이 completed 가 되면 종료하는 스크립트(최대 2시간)를 띄워라 — 종료가 당신을 깨운다. 전경 sleep 은 막혀 있다.

한 사이클 = 한 가설:
0. 잠금·선택 — backlog 에서 status=ready, blocked_until 경과, prerequisites 충족인 항목 중 priority 숫자가 가장 낮은 것 하나. 다른 세션이 36시간 안에 in_progress 로 잠근 항목은 건너뛴다. 36시간 넘은 in_progress 항목이 있으면 그것을 이어받는다(메모를 읽고 중단 지점부터). 고른 항목에 status=in_progress·started_at(UTC ISO)·session(세션 ID 를 모르면 `routine_<UTC 시작시각, 분 단위>`)을 적고 그 커밋을 먼저 push 한다.
1. 사전 등록 — registry.json 에 `<id>_prereg_<날짜>`: 가설·셀·동결 파라미터·판정 기준·진단 셀·사전 확률과 근거·known_limits·DEPLOY_ON_PASS(backlog deploy_on_pass 와 같게). 결과를 보기 전에 쓴다.
2. 구현 — validate_<id>.py + test_<id>.py + .github/workflows/<id>.yml. 기존 프레임(validate_revival·frame_v3·gate·method_x·validate_portfolio·validate_xsec_chars 등)을 import 해 같은 잣대를 쓴다. 로컬 스모크로 주 판정 셀 수치를 보지 않는다(봤으면 공개).
3. 검증·PR·머지 — test_<id>.py 와 tests.yml 전 목록 로컬 그린 → tests.yml 에 등록 → 브랜치(하네스가 지정한 브랜치가 있으면 그것, 없으면 research/<id>) → draft PR → CI 그린 확인 → 머지.
4. 결과 판독 — 러너 워크플로 run 을 기다린다(위 도구 사정 참조). 판정은 코드가 낸 것을 그대로 옮기고 사전 확률을 채점한다(맞은 것·틀린 것 둘 다). 진단 셀에서 사후에 골라 살리지 않는다.
5. 기록 — report_<id>.md · CLAUDE.md '현재 상태' 항목(기존 항목과 같은 밀도) · research_log.csv 한 줄 · backlog status=done + result. 사전 등록 기준 전부 통과이고 경계값이 아니며 deploy_on_pass=true 일 때만 자율 반영 규칙(2026-09-05)대로 실거래에 반영하고 무엇을 왜 켰는지 적는다.
6. 탐색 의무 — backlog 에 신규 가설을 2개 이상 추가한다(출처: 실거래 장부 부검 / 레포 리포트의 후속·미측정 문구 / 외부 문헌(웹 검색, 출처 URL) / 기각된 시험의 기전). 각 항목에 hypothesis·prior(0.05 이상)·근거·반증 조건·est_cost_h·priority 를 적는다. test_research_loop.py 가 그린이어야 한다.
7. 보고 — 세션의 마지막 메시지가 사용자 푸시 알림이다. 형식: `[연구 사이클 YYYY-MM-DD] <id> <판정> — 한 줄 결과 / 실거래 변경 여부 / 새 가설 N개(id) / 다음 사이클 예정 항목`. 러너 결과를 못 봤으면 어디까지 했는지와 backlog 메모 위치를 적는다. 한국어로, 짧게.

불변(절대): 손절 주문 없으면 실거래 없음 · 사전 등록 전 결과 열람 금지 · 사후 선택·격자 최대값 선택 금지 · 한 사이클에 가설 하나 · 위험 수준(RISK_FRAC/LEV_CAP/MAX_POS/EQUITY_FLOOR)·열린 포지션 수동 청산·자금 이동·게이트 문턱·CLAUDE.md 원칙 ②(AI 청산 실효)는 사용자 결정이라 시험·보고까지만 하고 적용하지 않는다 · 실거래 코드를 건드리면 동작 불변 테스트를 함께 넣는다 · tests.yml 그린이 머지 조건 · Vault 비밀·API 키를 출력하지 않는다. 사용자에게 질문하지 말고 RESEARCH_LOOP.md 의 규칙으로 판단한다 — 판단이 안 서는 지점은 backlog notes 에 적고 보수적인 쪽을 택한다.
