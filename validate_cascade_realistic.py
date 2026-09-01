"""
validate_cascade_realistic.py — 캐스케이드 배포 가능성: 실측 지연 + 마찰.

이전 검증들의 공백
-----------------
`validate_cascade_delay.py` 는 지연을 **고정값**으로 넣었다(4h 격자 + jitter 10/30/60/90분
각각을 전 신호에 동일 적용). 그런데 실제 GitHub Actions 큐 지연은 고정이 아니라
**꼬리가 두꺼운 분포**다. 2026-09-01 실측(daily_scheduler 스케줄 실행 100건):

    중앙값 25.1분 · p75 37.5분 · p90 91.5분 · p95 188.3분 · 최대 231.5분 · 60분 이내 82%

절반은 25분 안에 도는데 18%가 1시간을 넘고 상위 5%는 3~4시간까지 간다. 고정값으로는
이 혼합을 표현할 수 없다 — 평균 40.7분을 전 신호에 씌우는 것은 실제 분포와 다르다.
평균이 중앙값보다 15분 큰 것 자체가 꼬리의 무게다.

또 하나: 지금까지 **마찰을 왕복 0.2% 고정**으로만 봤다. 캐스케이드는 정의상 강제청산이
연쇄되는 순간이라 호가 스프레드가 가장 벌어져 있다. 배리어가 ±1.5×ATR(0.75~1.5%)로
좁아 마찰이 조금만 커져도 엣지가 통째로 사라질 수 있다.

이 스크립트가 답하는 두 질문
--------------------------
A. **1시간 크론으로 바꾸면 게이트를 통과하는가** — 실측 지연 분포를 신호마다
   샘플링해 씌운다. 통과하면 서버가 불필요하다(공개 레포라 Actions 무제한 무료).
B. **마찰이 얼마나 커지면 무너지는가** — 왕복 수수료를 0.2~0.8%로 올리며 측정.

15분 크론은 왜 안 보는가
----------------------
1h 봉은 항상 정시에 마감하고 1h 크론도 정시에 발화한다. 격자를 더 잘게 쪼개도 마감
시각과 이미 겹쳐 있어 추가 이득이 없다 — 남는 변수는 큐 지연뿐이다.

실행: python validate_cascade_realistic.py   (Actions 러너)
"""
import json
import random
import statistics
import sys
from datetime import datetime, timezone

import intraday_lab as lab
import validate_cascade as vc
import validate_cascade_delay as vcd

TF = vc.TF
H = lab.HORIZON[TF]
SEED = 42

# ── 실측 Actions 큐 지연 (분) ────────────────────────────────────────────────
# 2026-09-01 측정: daily_scheduler.yml 의 event=schedule 실행 100건.
# created_at 과 예정 cron 시각의 차이. 재현성을 위해 표본을 그대로 박아둔다.
MEASURED_DELAY_MIN = [
    6.6, 7.8, 8.3, 8.6, 8.6, 8.8, 9.2, 9.3, 9.3, 9.8, 10.0, 10.0, 10.3, 10.8,
    11.3, 11.4, 11.4, 12.4, 12.4, 12.7, 12.7, 12.8, 12.9, 13.1, 14.8, 14.9,
    15.2, 15.3, 15.6, 15.7, 16.4, 16.9, 17.9, 18.1, 18.6, 18.6, 19.1, 19.4,
    20.1, 20.4, 20.5, 21.5, 21.9, 22.9, 23.2, 23.3, 23.9, 24.2, 24.8, 24.9,
    25.3, 27.1, 27.5, 28.6, 29.0, 29.2, 29.4, 29.8, 30.9, 31.3, 31.6, 31.9,
    32.0, 32.1, 32.6, 32.8, 33.1, 33.2, 33.5, 33.5, 33.7, 33.8, 34.5, 36.4,
    37.2, 37.5, 38.4, 38.6, 39.6, 39.7, 41.2, 48.5, 62.5, 62.9, 63.0, 63.7,
    64.6, 66.2, 67.3, 68.0, 91.5, 117.0, 126.5, 154.4, 172.9, 188.3, 204.1,
    212.6, 222.7, 231.5,
]

# 크론 격자 (분). 1h 봉 마감이 항상 정시라 60분 격자면 격자 대기가 0이 된다.
GRIDS = {"4h(현행)": 240, "1h(제안)": 60}

# 마찰 스윕 — 왕복 수수료. 0.002 가 동결값(OKX taker 0.05%x2 + 슬리피지 여유).
FEE_LEVELS = [0.002, 0.003, 0.004, 0.006, 0.008]

# 서버 가정: 지연이 사실상 0(수 초). 상한 비교용.
SERVER_DELAY_MIN = 1.0


def delay_bars(ts_ms, grid_min, wait_min):
    """
    봉 마감 후 grid 격자에서 다음 틱을 기다리고 wait_min 분 뒤 주문했을 때,
    진입이 몇 봉 뒤인가. 주문 시각이 속한 1h 봉의 종가로 체결된 것으로 본다
    (동결 프레임과 동일 — 실제보다 최대 1시간 보수적).
    """
    dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
    close_min = (dt.hour + 1) * 60                       # 봉 마감(분, 자정 기준)
    tick = -(-close_min // grid_min) * grid_min          # 마감 이후 첫 격자 틱
    order_min = tick + wait_min
    return int(order_min // 60) - dt.hour


def outcome_at(rows, atr, si, d, fee):
    """d봉 지연 진입 + 지정 마찰. 배리어·보유한도는 진입 시점 기준 재계산."""
    j = si + d
    if j >= len(rows) - 1 or not atr[j] or atr[j] <= 0:
        return None
    _, ret = lab.outcome_atr(rows, j, "long", atr, H, fee=fee)
    if ret is None:
        return None
    return rows[j]["date"], ret


def collect_signals(data):
    sig = []
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
            sig.append((rows, atr, i, r0["ts"]))
    return sig


def run_arm(sig, boot, grid_min, fee, sampler, label):
    """지연 분포 sampler(신호별 대기분)를 씌워 평가."""
    sigs, dbars = [], []
    for rows, atr, i, ts in sig:
        wait = sampler(i, ts)
        d = delay_bars(ts, grid_min, wait) if grid_min else 0
        o = outcome_at(rows, atr, i, d, fee)
        if o:
            sigs.append(o)
            dbars.append(d)
    if not sigs:
        return None
    r = lab.evaluate(label, sigs, boot, verbose=False,
                     extra=dict(grid_min=grid_min, fee=fee,
                                avg_delay_bars=round(statistics.mean(dbars), 2),
                                d0_share=round(sum(1 for x in dbars if x <= 1)
                                               / len(dbars), 3)))
    return r


def fmt(r):
    return (f"{r['n']:>5}{r['mean']*100:>+9.2f}%{r['median']*100:>+9.2f}%"
            f"{(r['boot_p'] if r['boot_p'] is not None else 1):>8.3f}"
            f"{r['oos_pos']:>4}/4{'통과' if r['fee_ok'] else '미달':>9}"
            f"{r['verdict']:>11}")


def main():
    syms = vc._universe()
    d = MEASURED_DELAY_MIN
    print(f"캐스케이드 실측 배포 가능성 | {TF} {vc.FETCH_DAYS}일 | "
          f"파라미터 동결 ({vc.MOVE_ATR}xATR/{vc.VOL_MULT}배/{vc.RECOVER})")
    print(f"실측 Actions 지연 n={len(d)}: 중앙 {statistics.median(d):.1f}분 / "
          f"평균 {statistics.mean(d):.1f}분 / 최대 {max(d):.1f}분 / "
          f"60분이내 {sum(1 for x in d if x <= 60)/len(d):.0%}")
    if "--no-fetch" not in sys.argv:
        vc.fetch(syms)

    data = vc.load_all()
    if not data:
        print("데이터 없음 — 중단")
        return
    boot = lab.bootstrap_baseline(vcd.build_pool(data), lambda si: "long", H)
    sig = collect_signals(data)
    print(f"데이터 {len(data)}종목 | 캐스케이드 {len(sig)}건\n")

    hdr = (f"  {'조건':<26}{'n':>5}{'평균':>10}{'중앙':>10}{'boot_p':>8}"
           f"{'OOS':>6}{'수수료마진':>9}{'판정':>11}")
    results = {}

    # 체결 관례를 먼저 밝힌다. 동결 프레임은 '주문 시각이 속한 봉의 종가'로 체결하며,
    # 1h 봉보다 잘게 볼 수 없다. 그래서 1h 격자에서는 지연 1분이든 59분이든 똑같이
    # d=1 로 떨어진다 — **둘이 같아서가 아니라 프레임의 해상도 한계다.**
    # 결과표는 이렇게 읽어야 한다:
    #   d=0  = 서버의 상한 (신호봉 종가에 즉시 체결)
    #   d=1  = 60분 내 모든 지연의 하한 (서버·크론 공통, 실제 값은 d=0~d=1 사이)
    #   1h격자 실측 = 대부분 d=1 + 60분을 넘는 18%의 꼬리(d>=2)
    # 따라서 이 시험이 실제로 측정하는 서버의 기여분은 '한 시간 안쪽이 얼마나
    # 빠른가'가 아니라 **꼬리를 없애면 얼마나 나아지는가**뿐이다.
    print("  [체결 관례] 주문이 속한 1h 봉의 종가로 체결 — 1h 미만은 분해 불가.")
    print("  d=0=서버 상한 / d=1=60분 내 지연의 하한(실제는 그 사이) /")
    print("  1h격자 실측=대부분 d=1 + 60분 초과 18%의 꼬리(d>=2).")
    print("  즉 측정 가능한 서버의 기여분은 '꼬리 제거' 하나뿐이다.\n")

    # ── A. 크론 주기 × 실측 지연 분포 ───────────────────────────────────────
    print("=" * 96)
    print("[A] 크론 주기 비교 — 실측 지연 분포를 신호마다 샘플링")
    print("=" * 96)
    print(hdr + "   평균지연")
    print("  " + "-" * 92)

    # 이상적 상한: 지연 없음(1차 검증 조건) / 1봉 고정(지연 민감도의 마지막 통과점)
    for lbl, key, gmin, wait in (("이상 d=0 (검증조건)", "ideal_d0", None, 0.0),
                                 ("이상 d=1 (감쇠 통과선)", "ideal_d1", 60, 1.0)):
        r = run_arm(sig, boot, gmin, lab.FEE, lambda i, ts, w=wait: w, lbl)
        print(f"  {lbl:<26}{fmt(r)}   {r['avg_delay_bars']:>5.2f}봉")
        results[key] = r

    for gname, gmin in GRIDS.items():
        rnd = random.Random(SEED)
        # 신호마다 실측 표본에서 하나 뽑는다(부트스트랩). 시드 고정으로 재현 가능.
        draws = [rnd.choice(MEASURED_DELAY_MIN) for _ in sig]
        it = iter(draws)
        r = run_arm(sig, boot, gmin, lab.FEE, lambda i, ts, it=it: next(it),
                    f"{gname} + 실측지연")
        print(f"  {gname + ' + 실측지연':<26}{fmt(r)}   {r['avg_delay_bars']:>5.2f}봉"
              f"  (d<=1 비율 {r['d0_share']:.0%})")
        results[f"grid_{gmin}"] = r

    # 1h 크론 + 서버(지연 ~0) — 서버의 순수 기여분
    r = run_arm(sig, boot, 60, lab.FEE, lambda i, ts: SERVER_DELAY_MIN,
                "1h + 서버(지연~0)")
    print(f"  {'1h + 서버(지연 1분)':<26}{fmt(r)}   {r['avg_delay_bars']:>5.2f}봉")
    results["server"] = r

    # ── B. 마찰 스윕 ────────────────────────────────────────────────────────
    print("\n" + "=" * 96)
    print("[B] 마찰(왕복 수수료) 민감도 — 캐스케이드는 스프레드가 가장 벌어진 순간")
    print("=" * 96)
    print(f"  {'수수료':<10}{'d=0 (검증조건)':>34}    {'1h크론+실측지연':>34}")
    print(f"  {'':<10}{'평균':>10}{'중앙':>10}{'판정':>13}    "
          f"{'평균':>10}{'중앙':>10}{'판정':>13}")
    print("  " + "-" * 92)
    fee_rows = {}
    for fee in FEE_LEVELS:
        r0 = run_arm(sig, boot, None, fee, lambda i, ts: 0, f"fee{fee}_d0")
        rnd = random.Random(SEED)
        draws = [rnd.choice(MEASURED_DELAY_MIN) for _ in sig]
        it = iter(draws)
        rg = run_arm(sig, boot, 60, fee, lambda i, ts, it=it: next(it),
                     f"fee{fee}_1h")
        # lab.evaluate 의 fee_ok 는 동결 FEE(0.2%) 를 잣대로 쓴다. 수수료를 올린
        # arm 에서는 "그 수수료를 내고도 남는가"로 봐야 일관되므로 재판정한다.
        for r in (r0, rg):
            r["fee_ok_at_fee"] = r["mean"] > fee
            r["verdict_at_fee"] = ("PASSED" if (r["frozen_ok"] and r["fee_ok_at_fee"])
                                   else ("HOLD_N" if r["n"] < 20 else "REJECTED"))
        tag = " (동결값)" if abs(fee - lab.FEE) < 1e-9 else ""
        print(f"  {str(round(fee*100, 2)) + '%' + tag:<10}"
              f"{r0['mean']*100:>+9.2f}%{r0['median']*100:>+9.2f}%"
              f"{r0['verdict_at_fee']:>13}    "
              f"{rg['mean']*100:>+9.2f}%{rg['median']*100:>+9.2f}%"
              f"{rg['verdict_at_fee']:>13}")
        fee_rows[str(fee)] = dict(d0=r0, grid1h=rg)
    results["fee_sweep"] = fee_rows

    # ── 결론 ────────────────────────────────────────────────────────────────
    print("\n" + "=" * 96)
    g1 = results.get("grid_60", {})
    g4 = results.get("grid_240", {})
    srv = results.get("server", {})
    print(f"4h 크론 + 실측지연: {g4.get('verdict')} (mean {g4.get('mean',0)*100:+.2f}%, "
          f"median {g4.get('median',0)*100:+.2f}%)")
    print(f"1h 크론 + 실측지연: {g1.get('verdict')} (mean {g1.get('mean',0)*100:+.2f}%, "
          f"median {g1.get('median',0)*100:+.2f}%)")
    print(f"1h 크론 + 서버    : {srv.get('verdict')} (mean {srv.get('mean',0)*100:+.2f}%, "
          f"median {srv.get('median',0)*100:+.2f}%)")
    # 마찰 내성: 어느 수수료까지 1h크론이 버티는가
    survive = [f for f in FEE_LEVELS
               if fee_rows[str(f)]["grid1h"]["verdict_at_fee"] == "PASSED"]
    if survive:
        print(f"1h 크론이 버티는 최대 마찰: {max(survive)*100:.2f}% (왕복)")
    else:
        print("1h 크론은 동결 마찰(0.2%)에서도 미달")

    if g1.get("verdict") == "PASSED":
        print("\n=> 1시간 크론만으로 게이트 통과. 서버 불필요 "
              "(공개 레포 = Actions 무제한 무료).")
    elif srv.get("verdict") == "PASSED":
        print("\n=> 1시간 크론으로는 부족, 서버(지연 제거)가 있어야 통과. "
              "지연 꼬리(p90 173분)가 원인.")
    else:
        print("\n=> 서버로 지연을 없애도 미달. 배포 근거 없음.")

    json.dump(dict(measured_delay=MEASURED_DELAY_MIN, grids=GRIDS,
                   fee_levels=FEE_LEVELS, n_signals=len(sig), results=results),
              open("_cascade_realistic.json", "w"), indent=1, default=str)
    print("\nRESULT_JSON: " + json.dumps(
        {k: dict(n=v.get("n"), mean=v.get("mean"), median=v.get("median"),
                 verdict=v.get("verdict"))
         for k, v in results.items() if isinstance(v, dict) and "n" in v},
        separators=(",", ":")))


if __name__ == "__main__":
    main()
