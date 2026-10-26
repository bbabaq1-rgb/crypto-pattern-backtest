-- supabase_fix_pnl_leverage_2026_10_26.sql — 엔진 청산 실거래 손익(trades.pnl_live_usd) 레버리지 보정
-- 사용자 승인 2026-10-26 "이번에 변경되는것들 전부 목록화해줘 전부 승인". registry leverage_default_defect_2026_10_26.
--
-- 결함: paper_executor 가 엔진이 시장가로 닫은 실거래의 pnl_live_usd 를 '수익률 x 증거금 x 레버리지' 로
-- 기록하는데, 레버리지를 live_order 에서만 읽고 없으면 2배로 가정했다. 러너는 매 실행 DB 에서 포지션을
-- 복원하고 positions 에 leverage 컬럼이 없어(2026-10-26 추가) live_order 가 늘 유실됐다. 실제 레버리지는
-- 2026-09-04 08:51Z(#17 LEV_CAP 2→3) 이후 진입분부터 3배다. 그래서 그 뒤 엔진 청산분은 실제의 2/3 로 기록됐다.
-- 거래소가 직접 체결한 청산(exit_reason 에 'OKX' 포함)은 OKX 실손익을 그대로 써서 정확하다 — 손대지 않는다.
--
-- 대상 = 실거래(live_mode) 방식D 청산 · pnl_live_usd 있음 · 엔진 청산(사유에 'OKX' 없음) · 진입 2026-09-04 이후 ·
--        '역산 레버리지'(pnl / 수익률 / 증거금)가 1.9~2.1 = 2배로 기록된 행만.
-- 이 마지막 조건 때문에 **멱등**이다: 보정 뒤 역산 레버리지는 약 3.0 이 되어 다시 걸리지 않는다. 코드 수정
-- 머지 전 사이에 새로 기록된 엔진 청산이 있으면 같은 파일을 한 번 더 돌려 그것만 보정한다.
-- 1차 실행 2026-10-26 약 09:35Z(Supabase 커넥터): 74건, 합계 +143.48 → +215.22 USD(×1.5).
--   대상 id 해시 md5 = 243c6369c87f5e8b0dc5220eef1f20bd (보정 전후 동일 확인). 보정 뒤 역산 레버리지 2.930~3.145,
--   2배로 남은 행 0. 진입 기간별 실거래 방식D 손익(DB 기준): 9/06~10/06 진입 +1.61 → +75.32 USD ·
--   10/07 이후 진입 −117.42 → −124.45 USD.
--
-- 근거(실행 전 확인): 대상 74건 역산 레버리지 1.953~2.097(전부 2배 기록) · 같은 기간 OKX 체결분 역산 레버리지
-- 주별 중앙값 2.87~2.97(=3배에서 수수료·슬리피지 차감) · 대상 첫 진입 2026-09-05(LEV_CAP 3 머지 뒤).
-- 한계: 엔진 청산의 수익률(return_pct) 자체가 체결가를 모를 때 봉 기준(예: 손절 −8.2%)이라, 보정된 달러 값도
-- '봉 기준 수익률 x 실제 레버리지' 추정이다. 레버리지 축만 바로잡는다.
--
-- 되돌리기: 아래 update 의 1.5 를 (1/1.5) 로, 역산 레버리지 조건을 2.85~3.2 로 바꾸고 exit_date <= '2026-10-26' 을
-- 붙여 실행(2.9~3.1 은 너무 좁다 — 원래 2.07~2.1배였던 3건이 보정 뒤 3.1~3.145 가 된다).
-- 대상 집합 확인용 해시(보정 전후 동일해야 함, 1차 = 243c6369c87f5e8b0dc5220eef1f20bd):
--   select count(*), md5(string_agg(id::text, ',' order by id)) from <아래 cand> where <밴드>;

with p as (
  select symbol, pattern, direction, entry_date,
         max(size_usd) filter (where live_mode is true or method = 'AD-LIVE') as size_live
  from public.positions group by 1, 2, 3, 4
), cand as (
  select t.id
  from public.trades t join p using (symbol, pattern, direction, entry_date)
  where t.live_mode is true and t.method = 'D' and t.pnl_live_usd is not null
    and t.exit_reason not like '%OKX%' and t.entry_date >= '2026-09-04'
    and p.size_live > 0 and t.return_pct <> 0
    and t.pnl_live_usd / (t.return_pct / 100.0) / p.size_live between 1.9 and 2.1
)
update public.trades t
   set pnl_live_usd = t.pnl_live_usd * 1.5
  from cand
 where t.id = cand.id;
