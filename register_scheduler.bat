@echo off
REM ============================================================
REM  CryptoPatternScheduler 등록 (Windows Task Scheduler)
REM  매일 09:00 KST(=00:00 UTC)에 scheduler.py oncefull 1회 실행:
REM    데이터 fetch -> 레짐 -> 라우팅 -> 신호탐지 -> 페이퍼 체결.
REM  이 .bat 을 (관리자 권한으로) 한 번만 실행하면 자동 등록됩니다.
REM  실주문 없음 — 로컬 페이퍼 기록만.
REM ============================================================
setlocal
set SCRIPT_DIR=%~dp0

REM python 경로 자동 탐지(필요시 아래 PYTHON 변수를 수동 지정)
set PYTHON=python

schtasks /Create ^
  /TN "CryptoPatternScheduler" ^
  /TR "cmd /c cd /d \"%SCRIPT_DIR%\" && %PYTHON% scheduler.py oncefull >> scheduler_log.txt 2>&1" ^
  /SC DAILY ^
  /ST 09:00 ^
  /F

if %ERRORLEVEL%==0 (
  echo.
  echo [완료] 매일 09:00 KST 자동 실행 등록됨.
  echo   확인 : schtasks /Query /TN CryptoPatternScheduler
  echo   해제 : schtasks /Delete /TN CryptoPatternScheduler /F
  echo   즉시 테스트: schtasks /Run /TN CryptoPatternScheduler
) else (
  echo [오류] 등록 실패 - 관리자 권한 cmd에서 실행했는지 확인하세요.
)
echo.
pause
