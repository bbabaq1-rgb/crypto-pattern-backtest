"""
크론 분기 검증 — 매시 실행이 **배포된 패턴의 동작을 바꾸지 않는가.**

배경: 크론을 4시간→매시로 바꾸면 scheduler 실행이 6→24회가 된다. scheduler 는
`rows[last]`(형성 중인 봉)에서 탐지하고 중복 진입 방어 키가 날짜 단위라, 실행이
늘면 '하루 1회 진입'이 더 이른 시각·덜 형성된 봉에서 잡히게 된다 = 이미 배포된
패턴의 진입 분포가 검증 당시와 달라진다.

그래서 느린 TF 탐지는 종전 6개 틱(UTC 00/04/08/12/16/20)에서만 돈다.
이 파일이 그 게이팅을 고정한다. 깨지면 실거래가 검증과 다른 조건으로 돈다.

실행: python test_cron_split.py
"""
import io
import json
import re
import sys
from datetime import datetime, timezone

import scheduler as sch

fails = []


def chk(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f" — {detail}"))
    if not cond:
        fails.append(name)


# ── 1. 느린 틱 판정 ─────────────────────────────────────────────────────────
chk("느린틱 시각이 종전 크론과 동일",
    sch.SLOW_TICK_HOURS == (0, 4, 8, 12, 16, 20), sch.SLOW_TICK_HOURS)

slow = [h for h in range(24)
        if sch.is_slow_tick(datetime(2026, 9, 1, h, 0, tzinfo=timezone.utc))]
chk("24시간 중 느린틱은 정확히 6개", slow == [0, 4, 8, 12, 16, 20], slow)
chk("나머지 18시간은 하위TF 전용", len(set(range(24)) - set(slow)) == 18)

# 분 단위는 판정에 영향 없음 (큐 지연으로 :30 에 돌아도 같은 틱)
chk("같은 시각이면 분이 달라도 판정 동일",
    all(sch.is_slow_tick(datetime(2026, 9, 1, 4, m, tzinfo=timezone.utc))
        for m in (0, 17, 45, 59)))
chk("느린틱이 아닌 시각은 분과 무관하게 False",
    not any(sch.is_slow_tick(datetime(2026, 9, 1, 5, m, tzinfo=timezone.utc))
            for m in (0, 17, 45, 59)))

# ── 2. 워크플로 분리 — 4h(--slow) + 매시(--fast) ───────────────────────────
# 2026-09-02: 매시 정시 크론은 발화율 27%(15틱 중 4). 4h 크론은 두 달 99%.
# 그리고 실행 시각(hour)으로 틱을 판정하면 큐 지연이 정각을 넘긴 실행(4h 시대 27%)
# 에서 1d/4h 탐지가 조용히 빠진다. 그래서 워크플로가 모드를 플래그로 명시한다.
wf = io.open(".github/workflows/daily_scheduler.yml", encoding="utf-8").read()
crons = re.findall(r"- cron: '([^']+)'", wf)
chk("메인 스케줄러 크론이 4시간(검증된 99% 크론)", crons == ["0 */4 * * *"], crons)
chk("메인 스케줄러는 항상 --slow 를 넘긴다", 'python scheduler.py "$MODE" --slow' in wf)
chk("메인 스케줄러 실행 커맨드에 --fast 없음",
    not re.search(r"python scheduler\.py[^\n]*--fast", wf))

# oncefull 은 여전히 UTC 00시에만 (하루 1회 전체 재계산 유지)
chk("oncefull 은 UTC 00시 조건 유지", 'HOUR" = "0"' in wf)

fw = io.open(".github/workflows/fast_scheduler.yml", encoding="utf-8").read()
fcrons = re.findall(r"- cron: '([^']+)'", fw)
chk("매시 워크플로 크론 1개", len(fcrons) == 1, fcrons)
m = re.fullmatch(r"(\d+) \* \* \* \*", fcrons[0]) if fcrons else None
chk("매시 워크플로는 시간당 1회", bool(m), fcrons)
chk("매시 워크플로는 정시(:00)를 피한다", bool(m) and int(m.group(1)) != 0, fcrons)
chk("오프셋이 60분 내 진입을 깨지 않음(<15분)", bool(m) and int(m.group(1)) < 15, fcrons)
chk("매시 워크플로는 항상 --fast", "python scheduler.py oncequick --fast" in fw)
chk("매시 워크플로 실행 커맨드에 --slow 없음",
    not re.search(r"python scheduler\.py[^\n]*--slow", fw))
chk("두 워크플로가 같은 concurrency 그룹(포지션 DB 직렬화)",
    re.search(r"group: (\S+)", wf).group(1) == re.search(r"group: (\S+)", fw).group(1))
chk("매시 워크플로도 cancel-in-progress 아님", "cancel-in-progress: false" in fw)
for sec in ("OKX_KEY", "OKX_SECRET", "OKX_PASSPHRASE", "SUPABASE_URL", "SUPABASE_SERVICE_KEY"):
    chk(f"매시 워크플로에 {sec} 전달", f"{sec}: ${{{{ secrets.{sec} }}}}" in fw)

# CLI 플래그 파싱
chk("--slow → True", sch._tick_flag(["--slow"]) is True)
chk("--fast → False", sch._tick_flag(["--fast"]) is False)
chk("플래그 없음 → None(시간 폴백)", sch._tick_flag([]) is None)
try:
    sch._tick_flag(["--slow", "--fast"]); chk("--slow --fast 동시는 거부", False)
except SystemExit:
    chk("--slow --fast 동시는 거부", True)

# ── 3. 닫힌 봉 인덱스 ───────────────────────────────────────────────────────
rows = [dict(ts=i, c=i) for i in range(10)]
chk("닫힌 봉은 마지막에서 두 번째", sch._closed_idx(rows) == 8, sch._closed_idx(rows))
chk("2봉이면 0번", sch._closed_idx(rows[:2]) == 0)
chk("1봉이면 None", sch._closed_idx(rows[:1]) is None)
chk("빈 리스트면 None", sch._closed_idx([]) is None)

# 형성 중인 봉을 절대 고르지 않는다
chk("닫힌 봉 인덱스는 항상 마지막 행이 아니다",
    all(sch._closed_idx(rows[:n]) != n - 1 for n in range(2, 11)))

# ── 4. exit_spec 패턴만 매시 대상 ───────────────────────────────────────────
specs = sch._exit_specs()
uni = json.load(io.open("universe.json", encoding="utf-8"))
ad1h = uni.get("adopted_1h_patterns", [])
hourly = [a["pattern"] for a in ad1h if a["pattern"] in specs]
six_tick = [a["pattern"] for a in ad1h if a["pattern"] not in specs]

chk("매시 도는 1h 패턴은 exit_spec 보유분뿐",
    hourly == ["cascade_fade_long_1h"], hourly)
chk("bat_1h/butterfly_1h 는 6틱 유지(검증 당시 동작 보존)",
    set(six_tick) == {"bat_1h", "butterfly_1h"}, six_tick)

# 느린 TF 채택 패턴은 exit_spec 이 없어야 한다 = 전부 6틱
slow_pats = [a.get("pattern") for a in uni.get("adopted_patterns", [])] + \
            [a.get("pattern") for a in uni.get("adopted_4h_patterns", [])]
leaked = [p for p in slow_pats if p in specs]
chk("1d/4h/1w 채택 패턴은 매시 경로로 새지 않음", not leaked, leaked)

# ── 5. 소스 게이팅이 실제로 걸려 있는가 ─────────────────────────────────────
src = io.open("scheduler.py", encoding="utf-8").read()
chk("1d FOCUS 루프가 느린틱 게이트를 통과",
    "for pat in (FOCUS if slow_tick else []):" in src)
chk("adopted(1d/4h/1w) 루프가 느린틱 게이트를 통과",
    "for ap in (adopted if slow_tick else []):" in src)
chk("4h 전용 블록이 느린틱 게이트를 통과",
    "if slow_tick and adopted4h_dir and adopted_4h:" in src)
chk("하모닉 블록이 느린틱 게이트를 통과",
    "if slow_tick and harmonic_dir:" in src)
chk("exit_spec 없는 1h 패턴은 느린틱에만 도는 분기 존재",
    "if not spec_ap and not slow_tick:" in src)
chk("exit_spec 패턴은 닫힌 봉에서 탐지",
    "last1 = _closed_idx(rows1h)" in src)

# run_once 가 slow_tick 주입을 받는다 (테스트·수동 실행용)
chk("run_once 가 slow_tick 인자를 받는다",
    "def run_once(do_fetch=True, quick=False, slow_tick=None):" in src)
chk("엔트리포인트가 플래그를 run_once 에 전달", "slow_tick=tick" in src)

# ── 6. 체결가 기준 배리어 재정렬 ────────────────────────────────────────────
pe_src = io.open("paper_executor.py", encoding="utf-8").read()
chk("실체결가가 신호가와 다르면 배리어 재계산",
    "if spec and abs(entry - sig_entry) > 1e-12:" in pe_src)
chk("재계산 후 OCO 재등록", "ensure_stop_orders(" in pe_src
    and "배리어를 체결가 기준으로 재정렬" in pe_src)

# ── 7. fetch 범위 ───────────────────────────────────────────────────────────
# 청산 평가가 보유 포지션의 TF 봉을 읽으므로 1d/4h 도 계속 받아야 한다.
chk("fetch_all 이 TF 목록을 인자로 받는다",
    "def fetch_all(tfs=(\"1d\", \"4h\", \"1h\")):" in src)
chk("실행 경로는 1d/4h/1h 를 모두 받는다(청산용 봉 확보)",
    'tfs = ("1d", "4h", "1h")' in src)

# ── 8. 기능 확인 — 형성 중인 봉의 캐스케이드는 신호가 되지 않는다 ──────────
# 소스 문자열 검사만으로는 "정말 안 잡히는가"를 못 본다. 실제 봉을 만들어 확인한다.
import detector_cascade_fade_1h as det


def _base(n=200, seed=3):
    import random
    random.seed(seed)
    rows, px, ts = [], 100.0, 1600000000000
    for _ in range(n):
        nxt = px * (1 + random.gauss(0, 0.004))
        rows.append(dict(ts=ts, date="2026-01-01", o=px, h=max(px, nxt) * 1.001,
                         l=min(px, nxt) * 0.999, c=nxt, v=100.0))
        px, ts = nxt, ts + 3600000
    return rows


def _cascade_bar(rows, i):
    """rows[i] 를 확실한 캐스케이드 봉으로 교체(하락 5ATR, 아래꼬리 5ATR, 거래량 5배)."""
    a = det._atr(rows)[i]
    pc = rows[i - 1]["c"]
    va = sum(x["v"] for x in rows[i - 21:i - 1]) / 20
    o, c = pc, pc - 5.0 * a
    rows[i] = dict(rows[i], o=o, h=pc * 1.0005, l=c - 5.0 * a, c=c, v=va * 5)
    return rows


# (a) 형성 중인 봉(마지막 행)에만 캐스케이드 → 닫힌 봉 기준이면 미신호
r_forming = _cascade_bar(list(_base()), -1)
ci = sch._closed_idx(r_forming)
sigset = set(det.detect(r_forming))
chk("형성 중인 봉의 캐스케이드는 신호가 아니다(닫힌 봉 기준)",
    (len(r_forming) - 1) in sigset and ci not in sigset,
    f"detect={sorted(sigset)[-3:]} closed_idx={ci}")

# (b) 닫힌 봉에 캐스케이드 → 신호
r_closed = _cascade_bar(list(_base()), -2)
ci2 = sch._closed_idx(r_closed)
chk("닫힌 봉의 캐스케이드는 신호가 된다", ci2 in set(det.detect(r_closed)), ci2)

# (c) 종전 경로(마지막 행 기준)와 신규 경로가 실제로 다른 봉을 본다
chk("두 경로가 서로 다른 봉을 본다", sch._closed_idx(r_closed) != len(r_closed) - 1)

print("\n실패", len(fails), "건" if fails else "— 전체 통과")
sys.exit(1 if fails else 0)
