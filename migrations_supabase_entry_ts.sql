-- crypto-pattern-backtest — Supabase 스키마 보정 (2026-09-02)
--
-- 왜 필요한가
-- ------------
-- GitHub Actions 러너는 매 실행 파일시스템이 비어 Supabase 가 유일한 상태 원천이다.
-- 아래 컬럼들이 없어 supabase_client.insert_tolerant 가 INSERT 시 자동으로 제외하고,
-- 복원 시 값이 사라진다(실행 로그: "[DB] positions 스키마 미존재 컬럼 제외: [...]").
--
-- 1) positions.entry_ts  ← **반드시 필요**
--    1h 는 하루 24행이 같은 date 라, entry_ts 가 없으면 paper_executor._bar_idx 가
--    date 폴백으로 '그날 첫 봉'을 진입봉으로 잡는다. exit_spec(ATR 배리어) 패턴에서는
--    eval_I 가 진입보다 이른 봉을 스캔해 있지도 않은 청산을 만들고 수익률까지 오염된다.
--    현재는 PR #9 의 가드가 그런 포지션의 엔진 청산을 보류해 사고를 막고 있으나,
--    그 대가로 캐스케이드의 12봉 시간청산이 돌지 않는다.
--    → 이 컬럼을 추가하면 가드 분기가 자동으로 사라지고 검증대로 동작한다.
--    → bat_1h / butterfly_1h 의 진입봉 오인식도 함께 해소된다.
--
-- 2) positions.target / positions.live_mode  ← 선택(폴백 있음)
--    target 은 barriers_of() 가 손절 거리 대칭으로 복원하고, live_mode 는 method 의
--    'AD-LIVE' 인코딩으로 판정된다. 추가하면 로그 노이즈가 사라지고 대시보드가 정확해진다.
--
-- 3) trades.pnl_usd / trades.live_mode  ← 권장
--    pnl_usd 가 없으면 복원 시 'size $200 가정'으로 재구성되어(paper_executor.restore_state_db)
--    daily_summary 의 누적 수익률이 왜곡된다. 실제 사이징은 $14~96 수준이다.
--
-- 안전성: 전부 nullable 컬럼 추가(ADD COLUMN IF NOT EXISTS)라 기존 행·쿼리에 영향이 없고,
--         되돌리려면 DROP COLUMN 만 하면 된다. 데이터 변경 없음.

ALTER TABLE public.positions ADD COLUMN IF NOT EXISTS entry_ts  bigint;
ALTER TABLE public.positions ADD COLUMN IF NOT EXISTS target    double precision;
ALTER TABLE public.positions ADD COLUMN IF NOT EXISTS live_mode boolean;

ALTER TABLE public.trades    ADD COLUMN IF NOT EXISTS pnl_usd   double precision;
ALTER TABLE public.trades    ADD COLUMN IF NOT EXISTS live_mode boolean;

-- 확인용
-- select column_name, data_type from information_schema.columns
--  where table_schema='public' and table_name in ('positions','trades')
--    and column_name in ('entry_ts','target','live_mode','pnl_usd')
--  order by table_name, column_name;
