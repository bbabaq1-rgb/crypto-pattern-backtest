"""
방식R(롱 한정) 그림자 장부 검증 — paper_executor.eval_R / shadow_r_records.

확인 대상:
  - eval_R(롱) ≡ method_r.outcome_r(mode="RL") — 무작위 레짐열·반대신호·가격에서 완전 일치
    (검증 프레임과 실행 엔진이 같은 규칙인지. paper_executor 는 method_r 을 import 하지 않는다)
  - eval_R(숏) ≡ eval_D
  - 롱에서 R 의 청산 봉은 항상 D 와 같거나 늦다 (→ 포지션이 아니라 D 거래에서 재평가해도 됨)
  - 사용자 시나리오: bear 진입 롱 → bull 전환에 D 는 청산, R 은 유지 → bear 재진입에 R 청산
  - shadow_r_records: since 이전 / 숏 / exit_spec 패턴 / 미해소 / 데이터 없음 → 기록 안 함,
    해소되면 method="R" live_mode=False 행 1개, 재실행 멱등, live 집계 불변
  - run() e2e: 레거시 롱 진입 → 청산 실행에서 D·A·R 3행, 포지션 수명은 D·A 로만 결정
  - _pattern_tf: universe.json 의 tf 우선(triple_bottom → 1w)

실행: python test_shadow_r.py
"""
import random
import sys
import zlib
from datetime import date, timedelta

import paper_executor as pe
import method_r as mr

fails = []


def check(n, c, d=""):
    print(("PASS " if c else "FAIL ") + n + ("" if c else f" — {d}"))
    c or fails.append(n)


def day(i, start=date(2026, 9, 3)):
    return (start + timedelta(days=i)).isoformat()


def ts0(start=date(2026, 9, 3)):
    from datetime import datetime, timezone
    return int(datetime(start.year, start.month, start.day, tzinfo=timezone.utc).timestamp() * 1000)


def mkrows(n=80, seed=1, start=date(2026, 9, 3), vol=0.02):
    random.seed(seed)
    rows, px = [], 100.0
    for i in range(n):
        nxt = px * (1 + random.gauss(0, vol))
        hi = max(px, nxt) * (1 + abs(random.gauss(0, 0.004)))
        lo = min(px, nxt) * (1 - abs(random.gauss(0, 0.004)))
        rows.append(dict(ts=ts0(start) + i * 86_400_000, date=day(i, start),
                         o=px, h=hi, l=lo, c=nxt, v=1.0))
        px = nxt
    return rows


def flat(n=80, px=100.0, start=date(2026, 9, 3)):
    return [dict(ts=ts0(start) + i * 86_400_000, date=day(i, start),
                 o=px, h=px + 0.5, l=px - 0.5, c=px, v=1.0) for i in range(n)]


REGS = ["bull_btc", "bull_altseason", "bear", "sideways", None]


def regmap_of(rows, seq):
    return {r["date"]: g for r, g in zip(rows, seq) if g is not None}


# ── 1. eval_R ≡ method_r.outcome_r("RL") ─────────────────────────────────────
n_eq = n_late = 0
mism = []
for trial in range(400):
    rng = random.Random(trial)
    rows = mkrows(80, seed=trial, vol=rng.choice([0.005, 0.02, 0.04]))
    # 레짐열: 구간별로 바뀌는 열 (None 포함)
    seq, g = [], rng.choice(REGS)
    for _ in rows:
        if rng.random() < 0.15:
            g = rng.choice(REGS)
        seq.append(g)
    rm = regmap_of(rows, seq)
    opp = set(rng.sample(range(80), rng.choice([0, 1, 3]))) if rng.random() < 0.5 else set()
    ei = rng.randint(0, 40)
    direction = "long" if trial % 4 else "short"
    mr.REGMAP = rm
    want = mr.outcome_r(rows, ei, direction, opp, "RL")
    got = pe.eval_R(rows, ei, direction, opp, rm)
    if got is None:
        mism.append((trial, "None")); continue
    j, px, ret, reason = got
    if abs(ret - want[0]) < 1e-12 and (j - ei) == want[1] and reason == want[2]:
        n_eq += 1
    else:
        mism.append((trial, got, want))
    if direction == "long":
        d = pe.eval_D(rows, ei, direction, opp, rm)
        if d and j >= d[0]:
            n_late += 1
        elif d:
            mism.append((trial, "R earlier than D", got, d))
check("eval_R ≡ method_r.outcome_r(RL) — 400 무작위 시나리오(롱/숏·레짐열·반대신호)",
      n_eq == 400 and not mism, mism[:3])
check("롱에서 R 청산 봉 >= D 청산 봉 (300 롱 시나리오 전부)", n_late == 300, n_late)

# 숏 ≡ D
rows = mkrows(80, seed=9)
rm = regmap_of(rows, ["bull_btc"] * 20 + ["bear"] * 20 + ["sideways"] * 40)
check("eval_R(숏) ≡ eval_D", pe.eval_R(rows, 5, "short", set(), rm)
      == pe.eval_D(rows, 5, "short", set(), rm))

# ── 2. 사용자 시나리오 (bear 진입 롱) ──────────────────────────────────────────
rows = flat(80)
for i in range(6, 80):        # 진입 후 완만히 상승
    rows[i] = dict(rows[i], o=100 + i * 0.1, h=100.6 + i * 0.1, l=99.6 + i * 0.1, c=100 + i * 0.1)
seq = ["bear"] * 8 + ["bull_btc"] * 6 + ["bull_altseason"] * 6 + ["bear"] * 60
rm = regmap_of(rows, seq)
d = pe.eval_D(rows, 5, "long", set(), rm)
r = pe.eval_R(rows, 5, "long", set(), rm)
check("D: bear→bull 전환 봉(8)에 regime_switch 청산", d and d[0] == 8 and d[3] == "regime_switch", d)
check("R: bull 전환·bull_btc↔altseason 전환 모두 유지, bear 재진입 봉(20)에 청산",
      r and r[0] == 20 and r[3] == "regime_switch", r)
check("R 수익률 > D 수익률 (상승을 더 탔다)", r and d and r[2] > d[2], (r, d))
# 미성숙: 레짐 전환 없이 데이터가 30봉 못 미치면 None
rm2 = regmap_of(rows[:20], ["bear"] * 20)
check("R 미해소 시 None(다음 실행 재평가)", pe.eval_R(rows[:20], 5, "long", set(), rm2) is None)
# 손절·반대신호 우선순위
rows_s = flat(80)
rows_s[7] = dict(rows_s[7], l=91.0)
check("R 손절 -8% 봉 내 판정(레짐 무관)", pe.eval_R(rows_s, 5, "long", set(), rm)[3] == "stop")
check("R 반대신호 청산", pe.eval_R(rows, 5, "long", {6}, rm)[0:1] == (6,)
      and pe.eval_R(rows, 5, "long", {6}, rm)[3] == "opp_signal")
# bull 진입 롱 → bear: 세 규칙 같은 봉
rm3 = regmap_of(rows, ["bull_btc"] * 10 + ["bear"] * 70)
check("bull 진입 롱 → bear 전환은 D·R 같은 봉 청산",
      pe.eval_D(rows, 5, "long", set(), rm3)[0] == pe.eval_R(rows, 5, "long", set(), rm3)[0] == 10)

# ── 3. shadow_r_records ───────────────────────────────────────────────────────
rows = flat(80)
for i in range(6, 80):
    rows[i] = dict(rows[i], o=100 + i * 0.1, h=100.6 + i * 0.1, l=99.6 + i * 0.1, c=100 + i * 0.1)
rm = regmap_of(rows, seq)
calls = []


def rows_of(sym, tf="1d"):
    calls.append((sym, tf))
    return {"SOL": rows, "ETH": rows}.get(sym)


def dtrade(sym="SOL", pattern="marubozu", direction="long", entry_date=None, live=True, **kw):
    return dict(method="D", symbol=sym, direction=direction, pattern=pattern, regime="bear",
                entry_date=entry_date or rows[5]["date"], entry_price=100.0,
                exit_date=rows[8]["date"], exit_price=100.8, ret=0.006, pnl_usd=0.24,
                hold_bars=3, reason="regime_switch", method_label="D", live_mode=live, **kw)


trades = [dtrade(),                                       # 대상
          dtrade(direction="short"),                      # 숏 → 제외
          dtrade(entry_date="2026-09-02"),                # since 이전 → 제외
          dtrade(pattern="cascade_fade_long_1h"),         # exit_spec → 제외
          dtrade(sym="XYZ"),                              # 데이터 없음 → 제외
          dict(dtrade(), method="A", live_mode=False)]    # A 행은 무관
live_before = sum(1 for t in trades if t.get("live_mode"))
n0 = len(trades)
added = pe.shadow_r_records(trades, rows_of, rm)
rrows = [t for t in trades if t["method"] == "R"]
check("대상 1건만 R 행 추가", added == 1 and len(rrows) == 1 and len(trades) == n0 + 1,
      (added, [(t["symbol"], t["direction"], t["entry_date"]) for t in rrows]))
r0 = rrows[0] if rrows else {}
check("R 행: symbol/pattern/entry_date 가 D 쌍둥이와 같고 live_mode=False",
      r0.get("symbol") == "SOL" and r0.get("pattern") == "marubozu"
      and r0.get("entry_date") == rows[5]["date"] and r0.get("live_mode") is False
      and r0.get("method_label") == "R", r0)
check("R 행 청산: bear 재진입 봉(20) regime_switch, hold 15",
      r0.get("reason") == "regime_switch" and r0.get("hold_bars") == 15
      and r0.get("exit_date") == rows[20]["date"], r0)
check("live 집계(live_mode 합) 불변", sum(1 for t in trades if t.get("live_mode")) == live_before)
check("rows_of 는 exit_spec/숏/since 이전 거래엔 호출되지 않음",
      set(calls) == {("SOL", "1d"), ("XYZ", "1d")}, set(calls))
added2 = pe.shadow_r_records(trades, rows_of, rm)
check("재실행 멱등 — 추가 0", added2 == 0 and len(trades) == n0 + 1)
# 미해소면 기록 없음
trades_u = [dtrade()]
check("미해소(데이터 20봉·레짐 전환 없음) → 기록 안 함",
      pe.shadow_r_records(trades_u, lambda s, tf="1d": rows[:20],
                          regmap_of(rows[:20], ["bear"] * 20)) == 0 and len(trades_u) == 1)
# entry_ts 로 진입봉 특정 (같은 실행에서 D 가 막 기록한 거래)
trades_ts = [dtrade(entry_ts=rows[5]["ts"])]
pe.shadow_r_records(trades_ts, rows_of, rm)
check("entry_ts 보유 거래도 같은 진입봉(5)으로 평가", len(trades_ts) == 2
      and trades_ts[1]["hold_bars"] == 15, trades_ts[-1])
# tf 조회
check("_pattern_tf: universe.json 우선 (triple_bottom→1w, three_soldiers_4h→4h, engulfing→1d)",
      (pe._pattern_tf("triple_bottom"), pe._pattern_tf("three_soldiers_4h"),
       pe._pattern_tf("engulfing"), pe._pattern_tf("bat_1h")) == ("1w", "4h", "1d", "1h"))
check("_record_trade 가 R 을 실거래로 표기하지 않는다(D 만 live)",
      "method == \"D\"" in open("paper_executor.py", encoding="utf-8").read())
check("paper_executor 는 method_r 을 import 하지 않는다(실거래 코드는 연구 모듈 비의존)",
      all(k not in open("paper_executor.py", encoding="utf-8").read()
          for k in ("import method_r", "from method_r")))

# ── 4. run() e2e — 레거시 롱이 D·A·R 3행, 포지션 수명은 D·A 로만 ────────────────
def _e2e():
    import csv as _csv, json as _json, os, shutil, tempfile
    import regime_switch as rs
    repo = os.getcwd()
    tmp = tempfile.mkdtemp()
    shutil.copy("registry.json", os.path.join(tmp, "registry.json"))
    shutil.copy("universe.json", os.path.join(tmp, "universe.json"))
    orig = rs.build_regime_map
    try:
        os.chdir(tmp)
        os.makedirs("data", exist_ok=True)
        rr = mkrows(120, seed=zlib.crc32(b"e2e_r") % 1000, vol=0.004)   # 저변동: 손절 회피
        for sym in ("SOL", "BTC"):
            with open(f"data/{sym.lower()}_1d.csv", "w", newline="") as f:
                w = _csv.writer(f)
                w.writerow(["timestamp", "open", "high", "low", "close", "volume"])
                for x in rr:
                    w.writerow([x["ts"], x["o"], x["h"], x["l"], x["c"], x["v"]])
        import detlib
        r1d = detlib.load_ohlcv("SOL", "1d")
        si = 10
        # bear 진입 → 4봉 뒤 bull → 그 뒤 bear 재진입(진입 후 12봉) → 이후 bear
        seq = ["bear"] * (si + 4) + ["bull_btc"] * 8 + ["bear"] * 200
        rs.build_regime_map = lambda *a, **k: regmap_of(r1d, seq)
        _json.dump({"signals": [dict(symbol="SOL", pattern="marubozu", direction="long", tf="1d",
                                     date=r1d[si]["date"], ts=r1d[si]["ts"], regime="bear")]},
                   open("signals_today.json", "w"))
        pe.run()
        _json.dump({"signals": []}, open("signals_today.json", "w"))
        out = pe.run()
        return (_json.load(open("paper_trades.json")), _json.load(open("paper_positions.json")), out)
    finally:
        rs.build_regime_map = orig
        os.chdir(repo)
        shutil.rmtree(tmp, ignore_errors=True)


tr, posn, out = _e2e()
by = {t["method"]: t for t in tr}
check("e2e: D·A·R 3행 기록", set(by) == {"D", "A", "R"}, sorted(by))
check("e2e: D 는 bull 전환(4봉)에 regime_switch, R 은 bear 재진입(12봉)에 regime_switch",
      by.get("D", {}).get("hold_bars") == 4 and by.get("D", {}).get("reason") == "regime_switch"
      and by.get("R", {}).get("hold_bars") == 12 and by.get("R", {}).get("reason") == "regime_switch",
      {m: (t["reason"], t["hold_bars"]) for m, t in by.items()})
check("e2e: R 행은 페이퍼(live_mode False)·같은 entry_price", by.get("R", {}).get("live_mode") is False
      and by.get("R", {}).get("entry_price") == by.get("D", {}).get("entry_price"))
check("e2e: 포지션은 D·A 청산으로 닫힘(R 미결이어도 수명 불변)", posn == [] and out["open"] == 0, (posn, out))

print(f"\n{len(fails)} failed")
sys.exit(1 if fails else 0)
