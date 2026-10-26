"""
test_research_loop.py — 자율 연구 루프(2026-10-26) 장부 고정. 네트워크 없음.

  1. research_backlog.json 스키마: id 형식·유일성 · kind/status 열거 · priority 1~5 · prior 0~1|null ·
     blocked 항목은 blocked_until 또는 prerequisites 가 있다 · 선결에 적힌 R-id 는 존재한다 · ready 항목이 최소 5개
  2. RESEARCH_LOOP.md 가 불변 조항(손절·사전 등록·사후 선택·사용자 결정 영역·deploy_on_pass)을 담고 있다
  3. CLAUDE.md 핵심 원칙에 탐구 자율권이 있고, tests.yml 이 이 테스트를 돌린다
  3b. 운용 위임(2026-10-26 정지·시동): CLAUDE.md 원칙 · RESEARCH_LOOP.md 0절 · 자식 프롬프트가 steward_rules_2026_10_26 을 가리킨다
  4. 자식 세션 프롬프트 원본 research_cycle_prompt.md 가 있고 불변 조항·절차 참조를 담는다(2026-10-26 — 예약 작업이
     직접 만든 세션엔 레포가 없어 스포너가 create_session 으로 띄운다; 프롬프트는 레포가 원본). 스포너 사본은 폴백에 원본 전문을 품는다
"""
import io
import json
import re

fails = []


def check(n, c, d=""):
    print(("PASS " if c else "FAIL ") + n + ("" if c else f" — {d}"))
    c or fails.append(n)


# ── 1. backlog 스키마 ─────────────────────────────────────────────────────────
b = json.load(io.open("research_backlog.json", encoding="utf-8"))
items = b["items"]
ids = [it["id"] for it in items]
check("id 형식 R-ddd · 유일", all(re.fullmatch(r"R-\d{3}", i) for i in ids) and len(set(ids)) == len(ids), ids)
check("kind/status 가 schema 열거 안", all(it["kind"] in b["schema"]["kind"] and it["status"] in b["schema"]["status"] for it in items),
      [(it["id"], it["kind"], it["status"]) for it in items if it["kind"] not in b["schema"]["kind"] or it["status"] not in b["schema"]["status"]])
check("priority 1~5 정수", all(isinstance(it["priority"], int) and 1 <= it["priority"] <= 5 for it in items))
check("prior 는 null 또는 0~1", all(it["prior"] is None or (isinstance(it["prior"], (int, float)) and 0 <= it["prior"] <= 1) for it in items))
check("deploy_on_pass 는 bool", all(isinstance(it["deploy_on_pass"], bool) for it in items))
check("판정 시험(prereg_test)은 prior 를 적는다", all(it["prior"] is not None for it in items if it["kind"] == "prereg_test"),
      [it["id"] for it in items if it["kind"] == "prereg_test" and it["prior"] is None])
check("prior 0.05 미만 항목 없음(기록용 소모 방지)", all(it["prior"] is None or it["prior"] >= 0.05 for it in items))
check("blocked 항목은 blocked_until 또는 prerequisites", all(it.get("blocked_until") or it.get("prerequisites") for it in items if it["status"] == "blocked"))
ref = {rid for it in items for p in it["prerequisites"] for rid in re.findall(r"R-\d{3}", p)}
check("선결에 적힌 R-id 는 존재", ref <= set(ids), ref - set(ids))
check("ready 항목 최소 5개", sum(1 for it in items if it["status"] == "ready") >= 5)
check("in_progress 항목은 started_at·session 을 가진다", all(it.get("started_at") and it.get("session") for it in items if it["status"] == "in_progress"))
check("필수 필드 전부", all(all(k in it for k in ("id", "title", "kind", "source", "hypothesis", "prior", "deploy_on_pass",
                                              "prerequisites", "blocked_until", "est_cost_h", "priority", "status", "owner",
                                              "added_on", "result", "notes")) for it in items))
check("사용자 결정 영역(사이징·게이트 문턱·AI 청산 실효)은 deploy_on_pass=false",
      all(not it["deploy_on_pass"] for it in items if it["id"] in ("R-001", "R-006", "R-010", "R-012")))
check("procedure 가 RESEARCH_LOOP.md 를 가리킨다", b.get("procedure") == "RESEARCH_LOOP.md")

# ── 2. RESEARCH_LOOP.md 불변 조항 ────────────────────────────────────────────
md = io.open("RESEARCH_LOOP.md", encoding="utf-8").read()
for phrase in ("손절 주문 없으면 실거래 없음", "사전 등록 전에 결과를 보지 않는다", "사후 선택 금지",
               "위험 수준(RISK_FRAC/LEV_CAP/MAX_POS)", "게이트 문턱 자체의 변경", "deploy_on_pass=true",
               "신규 가설 2개 이상", "한 사이클에 가설 하나", "research_backlog.json", "in_progress"):
    check(f"RESEARCH_LOOP.md: '{phrase}'", phrase in md)

# ── 3. 배선 ────────────────────────────────────────────────────────────────
cl = io.open("CLAUDE.md", encoding="utf-8").read()
check("CLAUDE.md 핵심 원칙에 탐구 자율권", "탐구 자율권" in cl and "RESEARCH_LOOP.md" in cl)
check("tests.yml 에 test_research_loop", "test_research_loop.py" in io.open(".github/workflows/tests.yml", encoding="utf-8").read())
# 2026-10-26 운용 위임(정지·시동) — 원칙·절차·자식 프롬프트가 같은 규칙 판을 가리킨다
check("CLAUDE.md 핵심 원칙에 운용 위임 + 규칙 판", "운용 위임" in cl and "steward_rules_2026_10_26" in cl)
for phrase in ("운용 점검", "steward_rules_2026_10_26", "steward.yml", "trading_halt", "신규 진입만"):
    check(f"RESEARCH_LOOP.md 0절: '{phrase}'", phrase in md)

# ── 4. 자식 세션 프롬프트 원본 ──────────────────────────────────────────────
import os
check("research_cycle_prompt.md 존재", os.path.exists("research_cycle_prompt.md"))
cp = io.open("research_cycle_prompt.md", encoding="utf-8").read() if os.path.exists("research_cycle_prompt.md") else ""
for phrase in ("손절 주문 없으면 실거래 없음", "사전 등록 전 결과 열람 금지", "사후 선택", "한 사이클에 가설 하나",
               "RESEARCH_LOOP.md", "research_backlog.json", "신규 가설을 2개 이상", "사용자 결정", "질문하지 말고",
               "결과를 보기 전에 쓴다", "운용 점검", "steward.yml", "steward_rules_2026_10_26", "trading_halt",
               "재량 금지"):
    check(f"research_cycle_prompt.md: '{phrase}'", phrase in cp)
check("RESEARCH_LOOP.md 가 세션 생성 경로(스포너·research_cycle_prompt.md)를 적는다", "research_cycle_prompt.md" in md and "스포너" in md)
sp = io.open("research_spawner_prompt.md", encoding="utf-8").read() if os.path.exists("research_spawner_prompt.md") else ""
check("research_spawner_prompt.md 폴백이 원본 전문을 그대로 품는다", bool(cp) and cp.strip() in sp)
check("스포너는 create_session(source_url) 경로를 쓴다", "create_session" in sp and "source_url" in sp)

print(f"\n{len(fails)} failed")
raise SystemExit(1 if fails else 0)
