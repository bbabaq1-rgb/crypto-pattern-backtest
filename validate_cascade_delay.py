"""
validate_cascade_delay.py — cascade_fade_long_1h 진입 지연 민감도.

배경
----
2026-08-29 재시험에서 `cascade_fade_long_1h` 이 게이트를 통과했다
(n=312, mean +2.43%, median +1.17%, boot_p 0.000, OOS 3/4). 그런데
`registry.json` 은 `passed_not_deployed` 다. 검증은 **1h 봉 마감 직후 진입**을
가정했지만, 실제 엔진은 GitHub Actions 4시간 주기 + 지연 10~90분으로 돌기 때문이다.

2026-08-30 청산 경로(eval_I + OKX OCO 브래킷)를 만들어 **청산 쪽 불일치는 해소**됐다.
남은 건 진입 타이밍이고, 그 해결책은 상시 실행 서버다. 서버를 붙이기 전에
**"진입이 늦어져도 엣지가 남는가"** 를 먼저 답해야 한다. 여기서 사라지면 서버를
붙일 이유 자체가 없다.

캐스케이드는 정의상 2.5×ATR 급락이라, 늦은 진입은 완전히 다른 가격이다.
이 스크립트는 그 손실을 정량화한다.

측정 방식
--------
신호는 그대로 두고 **진입 봉만 뒤로 민다.** 지연 d 에 대해:
  - 진입가 = 봉 (i+d) 의 종가
  - 배리어 = 그 시점의 ATR 기준 ±1.5×ATR (진입이 밀리면 배리어도 함께 이동)
  - 보유한도 = 진입 시점부터 12봉
즉 '늦게 들어간 트레이더'를 그대로 재현한다. 라벨·게이트는 1차 검증과 동일
(`intraday_lab.outcome_atr`, 동결 게이트 + 수수료 마진).

두 가지 지연 모델을 본다:
  A. **고정 지연** d = 0/1/2/3/4/6/12봉 — 엣지 감쇠 곡선(단조 감소여야 정상)
  B. **실제 스케줄러 격자** — 신호 봉 마감 후 다음 4h 틱(UTC 00/04/08/12/16/20)
     + 지연 j분(10/30/60/90)에 진입. 현행 배포 환경 그대로다.

d=0 이 1차 검증치(n=312, +2.43%)를 재현하는지가 정합성 확인이다.

실행: python validate_cascade_delay.py   (Actions 러너)
"""
import json
import statistics
import sys
from datetime import datetime, timezone

import intraday_lab as lab
import validate_cascade as vc

TF = vc.TF
H = lab.HORIZON[TF]

# A. 고정 지연 (1h 봉 단위)
DELAYS = [0, 1, 2, 3, 4, 6, 12]

# B. 스케줄러 격자 — daily_scheduler.yml 의 cron '0 */4 * * *'
SCHED_HOURS = [0, 4, 8, 12, 16, 20]
JITTERS_MIN = [10, 30, 60, 90]      # Actions 큐 지연 실측 범위


def delayed_outcome(rows, atr, si, d):
    """
    진입을 d봉 뒤로 민 결과. 배리어·보유한도 모두 진입 시점 기준으로 재계산.
    반환: (entry_date, ret) | None
    """
    j = si + d
    if j >= len(rows) - 1 or atr[j] is None or atr[j] <= 0:
        return None
    _, ret = lab.outcome_atr(rows, j, "long", atr, H)
    if ret is None:
        return None
    return rows[j]["date"], ret


def sched_delay_bars(ts_ms, jitter_min):
    """
    신호 봉(ts_ms 시가 기준, 1h 봉)이 마감된 뒤 실제로 진입 가능한 시점까지
    몇 봉이 걸리는가 — 스케줄러 4h 격자 + 지연 jitter_min 분.

    봉 마감 = ts + 1h. 그 이후 첫 4h 틱을 찾고, 거기에 jitter 를 더한 시각이
    실제 주문 시각이다. 1h 봉 데이터뿐이므로 그 시각 이후 첫 봉에서 체결된
    것으로 본다(보수적 — 실제로는 봉 중간 체결이라 더 이를 수 있다).
    """
    dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
    close_h = dt.hour + 1                      # 봉 마감 시각(시)
    tick = next((h for h in SCHED_HOURS if h >= close_h), 24)   # 마감 이후 첫 틱
    order_h = tick + jitter_min / 60.0         # 실제 주문 시각(시)
    # 주문 시각이 속한 1h 봉에서 체결된 것으로 본다. 그 봉의 종가를 진입가로
    # 쓰므로(동결 프레임과 동일) 실제보다 최대 1시간 보수적이다.
    return int(order_h) - dt.hour


def build_pool(data):
    pool = []
    for rows, atr in data.values():
        step = max(1, len(rows) // 80)
        for i in range(20, len(rows) - H - 1, step):
            if atr[i]:
                pool.append((rows, atr, i))
    return pool[:6000]


def main():
    syms = vc._universe()
    print(f"진입 지연 민감도 | cascade_fade_long_1h | 유니버스 {len(syms)}종목 | "
          f"{TF} {vc.FETCH_DAYS}일 | 파라미터 동결 "
          f"({vc.MOVE_ATR}xATR/{vc.VOL_MULT}배/{vc.RECOVER})")
    if "--no-fetch" not in sys.argv:
        vc.fetch(syms)

    data = vc.load_all()
    if not data:
        print("데이터 없음 — 중단")
        return
    print(f"데이터: {len(data)}종목")

    boot = lab.bootstrap_baseline(build_pool(data), lambda si: "long", H)

    # 신호 재탐지 — 인덱스를 보존해야 지연 적용이 가능하다
    sig_idx = []       # [(sym, rows, atr, i, ts)]
    for sym, (rows, atr) in data.items():
        for i in range(25, len(rows) - H - 1):
            a = atr[i]
            if not a:
                continue
            r0 = rows[i]
            rng = r0["h"] - r0["l"]
            if rng <= 0:
                continue
            move = r0["c"] - r0["o"]
            if move >= 0 or abs(move) < vc.MOVE_ATR * a:
                continue
            vavg = sum(x["v"] for x in rows[i - 20:i]) / 20
            if vavg <= 0 or r0["v"] < vavg * vc.VOL_MULT:
                continue
            if (r0["c"] - r0["l"]) / rng < vc.RECOVER:
                continue
            sig_idx.append((sym, rows, atr, i, r0["ts"]))
    print(f"캐스케이드 탐지: {len(sig_idx)}건 (2차 검증 312건 기준)\n")

    results = {}

    # ── A. 고정 지연 ────────────────────────────────────────────────────────
    print("=" * 92)
    print("[A] 고정 지연 — 진입을 d봉(1h) 뒤로 밀었을 때")
    print("=" * 92)
    print(f"  {'지연':<10}{'n':>6}{'평균':>10}{'중앙':>10}{'boot_p':>9}"
          f"{'OOS':>6}{'수수료마진':>10}{'판정':>12}   기준(d=0) 대비")
    print("  " + "-" * 88)
    base_mean = None
    for d in DELAYS:
        sigs = []
        for sym, rows, atr, i, ts in sig_idx:
            o = delayed_outcome(rows, atr, i, d)
            if o:
                sigs.append(o)
        if not sigs:
            continue
        r = lab.evaluate(f"delay_{d}h", sigs, boot, verbose=False,
                         extra=dict(delay_bars=d))
        if d == 0:
            base_mean = r["mean"]
        keep = (r["mean"] / base_mean * 100) if base_mean else 0
        label = "즉시(검증조건)" if d == 0 else f"+{d}h"
        print(f"  {label:<10}{r['n']:>6}{r['mean']*100:>+9.2f}%{r['median']*100:>+9.2f}%"
              f"{r['boot_p'] if r['boot_p'] is not None else 0:>9.3f}{r['oos_pos']:>4}/4"
              f"{'통과' if r['fee_ok'] else '미달':>10}{r['verdict']:>12}"
              f"   {keep:>6.0f}%")
        results[f"delay_{d}"] = r

    # ── B. 실제 스케줄러 격자 ───────────────────────────────────────────────
    print("\n" + "=" * 92)
    print("[B] 실제 배포 환경 — Actions 4h 주기(UTC 00/04/08/12/16/20) + 큐 지연")
    print("=" * 92)
    print(f"  {'지연조건':<14}{'n':>6}{'평균지연':>9}{'평균':>10}{'중앙':>10}"
          f"{'boot_p':>9}{'OOS':>6}{'수수료마진':>10}{'판정':>12}")
    print("  " + "-" * 88)
    for j in JITTERS_MIN:
        sigs, dbars = [], []
        for sym, rows, atr, i, ts in sig_idx:
            d = sched_delay_bars(ts, j)
            o = delayed_outcome(rows, atr, i, d)
            if o:
                sigs.append(o)
                dbars.append(d)
        if not sigs:
            continue
        r = lab.evaluate(f"sched_jitter_{j}m", sigs, boot, verbose=False,
                         extra=dict(jitter_min=j,
                                    avg_delay_bars=round(statistics.mean(dbars), 2)))
        print(f"  {'4h주기+' + str(j) + '분':<14}{r['n']:>6}"
              f"{statistics.mean(dbars):>8.1f}h{r['mean']*100:>+9.2f}%"
              f"{r['median']*100:>+9.2f}%"
              f"{r['boot_p'] if r['boot_p'] is not None else 0:>9.3f}"
              f"{r['oos_pos']:>4}/4{'통과' if r['fee_ok'] else '미달':>10}"
              f"{r['verdict']:>12}")
        results[f"sched_{j}m"] = r

    # ── 결론 ────────────────────────────────────────────────────────────────
    print("\n" + "=" * 92)
    d0 = results.get("delay_0", {})
    passed_delays = [d for d in DELAYS
                     if results.get(f"delay_{d}", {}).get("verdict") == "PASSED"]
    sched_pass = [j for j in JITTERS_MIN
                  if results.get(f"sched_{j}m", {}).get("verdict") == "PASSED"]
    print(f"기준(d=0) 재현: n={d0.get('n')} mean={d0.get('mean', 0)*100:+.2f}% "
          f"(2차 검증 n=312 +2.43%)")
    print(f"게이트 통과 지연: {passed_delays if passed_delays else '없음'} (봉)")
    print(f"실제 배포 환경 통과 jitter: "
          f"{[str(j)+'분' for j in sched_pass] if sched_pass else '없음'}")
    verdict = ("DEPLOYABLE" if sched_pass else
               ("DELAY_SENSITIVE" if passed_delays else "NO_EDGE"))
    print(f"종합 판정: {verdict}")
    if verdict == "DELAY_SENSITIVE":
        print("  → 즉시 진입에서만 엣지가 산다. 상시 실행 서버가 있어야 배포 가능.")
    elif verdict == "DEPLOYABLE":
        print("  → 현행 4h 주기로도 엣지가 남는다. 상시 서버 없이 배포 검토 가능.")
    else:
        print("  → 지연 무관하게 엣지 없음. 상시 서버를 붙일 이유가 없다.")

    payload = dict(config=dict(tf=TF, days=vc.FETCH_DAYS, horizon=H,
                               params=[vc.MOVE_ATR, vc.VOL_MULT, vc.RECOVER],
                               delays=DELAYS, sched_hours=SCHED_HOURS,
                               jitters_min=JITTERS_MIN),
                   n_signals=len(sig_idx), results=results, verdict=verdict)
    json.dump(payload, open("_cascade_delay.json", "w"), indent=1)
    print("\nRESULT_JSON: " + json.dumps(
        {k: dict(n=v["n"], mean=v["mean"], boot_p=v["boot_p"],
                 verdict=v["verdict"]) for k, v in results.items()},
        separators=(",", ":")))


if __name__ == "__main__":
    main()
