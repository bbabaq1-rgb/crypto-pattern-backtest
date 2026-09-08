"""
test_onchain_stable.py — 스테이블코인 신호 소스 교체 검증 (2026-09-08, CoinGecko → DefiLlama).

종전 CoinGecko `/coins/{id}/market_chart` 는 무료 티어에서 막혀 매 실행 `7d=None%` 로
찍히고 있었다(신호가 사실상 죽어 있었음). **정의(USDT·USDC 7일 시총 변화율 평균)와
문턱(STABLE_BULL_THR/BEAR_THR)은 불변**이고 데이터 출처만 바뀐다. 표시 전용 신호 —
매매 결정에 쓰이지 않는다(이 파일이 그 성질도 고정).

네트워크 없이 requests 를 스텁으로 갈아끼워 파싱·문턱·폴백만 검증한다.
실행: python test_onchain_stable.py
"""
import sys
import types

import onchain_signals as o

fails = []


def check(n, c, d=""):
    print(("PASS " if c else "FAIL ") + n + ("" if c else f" — {d}"))
    c or fails.append(n)


def _rows(vals):
    """DefiLlama stablecoincharts 응답 모양 — 오름차순 일별."""
    return [{"date": 1_700_000_000 + i * 86400,
             "totalCirculatingUSD": {"peggedUSD": v}} for i, v in enumerate(vals)]


class _Resp:
    def __init__(self, payload, ok=True):
        self._p, self.ok = payload, ok

    def json(self):
        return self._p


def stub_requests(by_id, ok=True):
    """params['stablecoin'] 로 응답을 고르는 requests 스텁."""
    calls = []

    def get(url, params=None, headers=None, timeout=None):
        calls.append((url, (params or {}).get("stablecoin")))
        return _Resp(by_id.get((params or {}).get("stablecoin"), []), ok=ok)

    mod = types.ModuleType("requests")
    mod.get = get
    return mod, calls


def run(by_id, ok=True):
    orig = sys.modules.get("requests")
    mod, calls = stub_requests(by_id, ok=ok)
    sys.modules["requests"] = mod
    try:
        return o._fetch_stablecoin(), calls
    finally:
        if orig is not None:
            sys.modules["requests"] = orig
        else:
            sys.modules.pop("requests", None)


# 1) 7일 변화율 = 마지막 값 vs 8번째 뒤 값, USDT·USDC 평균
flat = _rows([100.0] * 7 + [110.0])          # +10%
half = _rows([100.0] * 7 + [102.0])          # +2%
r, calls = run({"1": flat, "2": half})
check("DefiLlama 엔드포인트를 USDT(1)·USDC(2) 두 번 호출",
      [c[1] for c in calls] == ["1", "2"] and all("stablecoins.llama.fi" in c[0] for c in calls), calls)
check("7일 변화율 = (마지막 − 8번째뒤)/8번째뒤, 코인별 기록",
      r["by_coin"] == {"tether": 10.0, "usd-coin": 2.0}, r)
check("평균 6% → bull (문턱 +3%)", r["signal"] == "bull" and abs(r["avg_7d_pct"] - 6.0) < 1e-9, r)
check("소스 표기", r.get("source") == "defillama", r)

# 2) 문턱은 종전 값 그대로
check("문턱 불변 (±3%)", o.STABLE_BULL_THR == 0.03 and o.STABLE_BEAR_THR == -0.03)
r, _ = run({"1": _rows([100.0] * 7 + [95.0]), "2": _rows([100.0] * 7 + [95.0])})
check("평균 −5% → bear", r["signal"] == "bear" and abs(r["avg_7d_pct"] + 5.0) < 1e-9, r)
r, _ = run({"1": _rows([100.0] * 7 + [100.5]), "2": _rows([100.0] * 7 + [101.0])})
check("평균 +0.75% → neutral (실제 관측 범위)", r["signal"] == "neutral", r)

# 3) 폴백 — 실패해도 파이프라인을 막지 않는다
r, _ = run({}, ok=False)
check("응답 실패 → neutral·None (예외 없음)",
      r["signal"] == "neutral" and r["avg_7d_pct"] is None and r["by_coin"] == {}, r)
r, _ = run({"1": _rows([100.0] * 3)})        # 8행 미만 + USDC 없음
check("행 부족 → neutral", r["signal"] == "neutral" and r["avg_7d_pct"] is None, r)
r, _ = run({"1": flat})                       # USDT 만 성공
check("한쪽만 성공하면 그 값만 평균", r["signal"] == "bull" and r["by_coin"] == {"tether": 10.0}, r)
r, _ = run({"1": [{"date": 1, "totalCirculatingUSD": None}] * 10})
check("시총 필드가 비어도 neutral", r["signal"] == "neutral", r)
r, _ = run({"1": _rows([0.0] * 7 + [100.0])})
check("기준값 0 이면 0 나누기 없이 neutral", r["signal"] == "neutral", r)

# 4) 표시 전용 — 매매 경로가 이 신호를 읽지 않는다
src_sched = open("scheduler.py", encoding="utf-8").read()
src_pe = open("paper_executor.py", encoding="utf-8").read()
check("스케줄러는 온체인 점수를 '표시 전용'으로만 쓴다",
      "표시 전용" in src_sched and "_fetch_stablecoin" not in src_sched)
check("체결 엔진은 온체인 신호를 import 하지 않는다", "onchain_signals" not in src_pe)
check("CoinGecko market_chart 호출이 남아 있지 않다",
      "coins/{coin_id}/market_chart" not in open("onchain_signals.py", encoding="utf-8").read())

print(f"\n{len(fails)} failed")
sys.exit(1 if fails else 0)
