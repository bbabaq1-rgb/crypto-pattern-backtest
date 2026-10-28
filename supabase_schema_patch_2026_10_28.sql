-- 매매 DB 보강 (2026-10-28) — trades.entry_ts
--
-- AI 엘리엇 BTC 자율매매(ai_elliott_btc, 2026-10-28 사용자 결정)는 매시 판단이라 같은 날 같은 종목·패턴·방향을
-- 여러 번 매매할 수 있다. trades 의 재삽입 방지 키가 (종목·패턴·방향·진입일·방식) 이라 뒤 거래가 앞 거래 행을
-- 지웠고, 복원 시 같은 날 새로 연 포지션이 '이미 청산됨'(d_closed)으로 오인될 수 있었다.
-- 봉 시각(ms)을 같이 저장해 구분한다(paper_executor._dedupe_delete / restore_state_db). positions.entry_ts 는
-- 2026-09 패치로 이미 있다. 컬럼이 없으면 코드는 날짜 키로 폴백한다(종전 동작).
-- 실행: Supabase SQL Editor 에서 그대로 (멱등). 기존 GRANT 는 테이블 단위라 컬럼 추가에 따로 필요 없다.

alter table public.trades add column if not exists entry_ts bigint;
create index if not exists trades_key_ts_idx on public.trades (symbol, pattern, direction, entry_ts);
