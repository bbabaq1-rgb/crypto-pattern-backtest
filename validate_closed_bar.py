"""
validate_closed_bar.py — 닫힌 봉 탐지로 바꾸면 포트폴리오가 나아지는가 (사전 등록, 2026-09-21)

**왜.** 같은 날 validate_forming_bar 가 실거래와 검증의 불일치 크기를 처음 쟀다 —
**검증 신호의 50~68% 가 실거래에서 영구 누락**되고(fvg 827/1666 · engulfing 126/184 ·
fvg_short 723/1329 · engulfing_short 153/245), **ih·marubozu 는 실거래 신호의 92~93% 가
닫힌 봉에 존재하지 않는다.** 고치는 것은 `detect_on_closed_bar` 를 켜는 한 줄이지만,
켜면 engulfing·fvg 신호는 약 2배로 늘고 ih·marubozu 는 거의 사라진다 — **슬롯 13 을 두고
벌어지는 경합이 통째로 달라지므로 패턴 단독 프레임으로 재면 오판한다**(2026-09-05 bear fvg 롱 전례).

────────────────────────────────────────────────────────────────────────────
사전 등록 (결과 보기 전 고정 — registry closed_bar_prereg_2026_09_21)

프레임: validate_portfolio 그대로. **arm 이 바꾸는 것은 '어느 봉에서 탐지하는가' 하나뿐.**
기준선 `current`: 1d 배포 6셀을 **형성 중인 봉**에서 탐지(4h 로 부분봉 합성, 슬로틱
       0/4/8/12/16/20 UTC, h=0 은 빈 봉, 한 봉에 첫 발화 한 번만, 진입가 = 그 틱의 부분봉 종가).
       **이 레포에서 실거래를 처음 복제한 백테스트다.**
주 판정 `closed_1d`: 같은 6셀을 닫힌 봉에서 탐지(= 검증 프레임). **주 판정 arm 은 이것 하나.**
three_soldiers_4h: **두 arm 모두 닫힌 봉으로 고정해 상쇄** — 그 셀의 형성 중인 봉 동작은
       신뢰성 있게 모델링할 수 없다(빈 봉 모델은 0건인데 실거래는 진입한다). 배경 슬롯 경합에는
       참여시키되 arm 간 차이는 만들지 않는다. **판정 대상 아님, 별도 사전 등록 사항.**
진단(판정 아님): `closed_focus`(engulfing·fvg 4셀만) · `closed_adopted`(ih·marubozu 2셀만).
판정: holdout J1~J5 전부 — J1 CAGR>current / J2 Calmar>current / J3 부트 우위 >=0.60 /
      J4 MDD 5%p 이내 / J5 train 도 우위.
DEPLOY_ON_PASS = False — 켜는 것은 **실거래 규칙 변경**이라 관찰 종료(2026-10-06) 후 사용자 결정.

**근간은 기준선 동치다** — collect_1d_mode("closed") 가 validate_portfolio.collect_1d 와
완전히 같아야 한다(test_closed_bar §1). 어긋나면 arm 차이가 탐지 봉 때문인지 수집 경로
차이 때문인지 못 가르므로 수치 전부가 무의미하다.

실행: python validate_closed_bar.py [--no-fetch]
"""
import importlib
import json
import random
import statistics as st
import sys

import detlib
import method_t as mt
import method_x as mx
import regime_switch as rs
import sizing_vol as sv
import sizing_study as ss
import validate_forming_bar as vfb
import validate_portfolio as vp
import validate_regime_split_all as va
import validate_revival as vr
from validate_regime_split import turnover_rank

DEPLOY_ON_PASS = False

SPLIT = vp.SPLIT
MAX_POS, START_EQ = ss.MAX_POS, ss.START_EQ
BOOT_N, SEED = ss.BOOT_N, ss.SEED
J3_WIN, J4_MDD_TOL = vp.J3_WIN, vp.J4_MDD_TOL
FETCH_WINDOWS = {"1d": 1800, "4h": 1100}
BLOCK_DAYS = 30          # validate_routing.BLOCK_DAYS 와 같은 값
TICKS_1D = [h // 4 for h in vfb.SLOW_TICK_HOURS]      # (0,4,8,12,16,20) → 0..5

# 전환 대상 1d 배포 6셀 (mt.PATS 의 1d 항목과 같은 집합)
FOCUS_CELLS = ("engulfing", "engulfing_short", "fvg", "fvg_short")
ADOPTED_CELLS = ("inverted_hammer", "marubozu")
SWITCHABLE = FOCUS_CELLS + ADOPTED_CELLS

ARMS = ["current", "closed_1d", "closed_focus", "closed_adopted"]
MAIN_ARM = "closed_1d"
ARM_SETS = {"current": frozenset(),
            "closed_1d": frozenset(SWITCHABLE),
            "closed_focus": frozenset(FOCUS_CELLS),
            "closed_adopted": frozenset(ADOPTED_CELLS)}
OUT = "_closed_bar.json"


def collect_1d_mode(syms, closed_cells, rows_by, kids):
    """
    1d 배포 셀 거래. `closed_cells` 에 든 패턴만 닫힌 봉(= 종전 백테스트)에서,
    나머지는 형성 중인 봉에서 탐지한다.

    **sizing_vol.collect_all(ROUTING_MODE) 의 구조를 그대로 따른다** — 라우팅·유니버스·
    정지 패턴·`len(rows) < 40` 스킵·`si + 1 >= len(rows)` 스킵·레코드 형식까지. 그래야
    closed_cells 가 전부일 때 validate_portfolio.collect_1d 와 완전히 같아진다(테스트가 고정).
    """
    sv.ROUTING_MODE = True
    syms_for, routing, regmap, suspended = sv.routing_ctx()
    want = set(syms)
    out = []
    for label, direction, detmod, oppmod, tf in mt.PATS:
        if tf != "1d" or label in suspended:
            continue
        mod = importlib.import_module(detmod)
        opp = importlib.import_module(oppmod) if oppmod else None
        pat_syms = [s for s in syms_for(sv._base_pattern(label)) if s in want]
        n = 0
        for sym in pat_syms:
            rows = rows_by.get(sym)
            if not rows or len(rows) < 40:
                continue
            opp_set = set(opp.detect(rows)) if opp else set()
            if label in closed_cells:
                sigs = {si: rows[si]["c"] for si in mod.detect(rows)}
            else:
                k = kids.get(sym)
                if not k:
                    continue
                sigs = {si: px for si, (_t, px)
                        in vfb.forming_signals(mod.detect, rows, k, "1d", TICKS_1D).items()}
            for si in sorted(sigs):
                if si + 1 >= len(rows):
                    continue
                if not sv.routed_in(label, direction, rows[si]["date"], routing, regmap):
                    continue
                ret, hold, _ = vfb.outcome_at(rows, si, direction, opp_set, sigs[si])
                xi = min(si + hold, len(rows) - 1)
                out.append(dict(t_in=mx._tnum(rows[si]["date"]), t_out=mx._tnum(rows[xi]["date"]),
                                ret=ret, pattern=label, sym=sym,
                                vol=sv.realized_vol(rows, si, tf="1d"), tf="1d", rank=None))
                n += 1
        print(f"  [{label}] {n}건 ({'closed' if label in closed_cells else 'forming'}, 종목 {len(pat_syms)})",
              flush=True)
    out.sort(key=lambda t: (t["t_in"], t["pattern"], t["sym"]))
    return out


def paired_slot_boot(arm_trades, rng, n_boot=BOOT_N, block=BLOCK_DAYS):
    """
    **arm 마다 거래 집합이 다르므로 거래를 재표집하면 짝지음이 안 된다**(validate_routing 이
    같은 문제를 푼 자리). 대신 **시간 블록을 재표집**하고 각 arm 이 그 블록에서 실제로 한
    거래를 가져온다 — 블록 추첨은 arm 간 공유하므로 진짜 짝지음이고, 블록을 순서대로 다시
    이어 붙여(offset 이동) 보유 기간과 중첩 구조를 보존한다.

    vp.simulate 로 돌리는 것이 validate_routing 과 다른 점 — 여기서는 **슬롯·증거금 경합**이
    측정 대상이라 method_x.equity_curve(슬롯 없음)로는 잴 수 없다.
    """
    days = [t["t_in"] for tr in arm_trades.values() for t in tr]
    if not days:
        return {a: [] for a in arm_trades}
    d0, d1 = min(days), max(days)
    n_blocks = max(1, int((d1 - d0) // block) + 1)
    by_block = {}
    for a, tr in arm_trades.items():
        m = {}
        for t in tr:
            m.setdefault(int((t["t_in"] - d0) // block), []).append(t)
        by_block[a] = m
    out = {a: [] for a in arm_trades}
    for _ in range(n_boot):
        pick = [rng.randrange(n_blocks) for _ in range(n_blocks)]
        for a, m in by_block.items():
            tup = []
            for pos, b in enumerate(pick):
                shift = (pos - b) * block
                for t in m.get(b, []):
                    tup.append(dict(t, t_in=t["t_in"] + shift, t_out=t["t_out"] + shift))
            tup.sort(key=lambda t: t["t_in"])
            out[a].append(vp.simulate(tup, "current")["calmar"])
    return out


def judge(train, hold, boot_win, arm):
    c, a = hold["current"], hold[arm]
    ct, at = train["current"], train[arm]
    return {
        "J1 CAGR>current": a["cagr"] > c["cagr"],
        "J2 Calmar>current": a["calmar"] > c["calmar"],
        f"J3 부트 우위>={J3_WIN:.2f}": boot_win >= J3_WIN,
        f"J4 MDD 악화<={J4_MDD_TOL*100:.0f}%p": a["mdd"] >= c["mdd"] - J4_MDD_TOL,
        "J5 train 도 우위": at["cagr"] >= ct["cagr"] and at["calmar"] >= ct["calmar"],
    }


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    print("=" * 104)
    print("닫힌 봉 탐지 전환 — 포트폴리오 프레임 (registry closed_bar_prereg_2026_09_21)")
    print(f"  기준선 current = 1d 6셀 형성 중인 봉(실거래 복제) | 주 판정 {MAIN_ARM} | "
          f"J1~J5 전부 | DEPLOY_ON_PASS={DEPLOY_ON_PASS}")
    print("=" * 104, flush=True)

    syms = va._syms()
    if "--no-fetch" not in argv:
        vp.fetch(syms)
    rows_1d = va.load_tf(syms, "1d")
    rows_4h = va.load_tf(syms, "4h")
    regmap = rs.build_regime_map()
    mt.REGMAP = regmap                       # 레짐 전환 청산 ON (2026-09-21 결함 수정)
    ranked = turnover_rank(rows_4h)
    kids = {s: vfb.bucket(rows_4h.get(s, []), vfb.BAR_MS["1d"]) for s in syms}
    print(f"[데이터] 1d {len(rows_1d)} / 4h {len(rows_4h)} 종목 | 레짐맵 {len(regmap)}일", flush=True)

    # 4h 는 arm 과 무관 — 한 번만 모은다(three_soldiers 포함 전부 닫힌 봉)
    print("\n[4h] arm 무관 배경 (three_soldiers_4h 는 두 arm 모두 닫힌 봉으로 고정)")
    t4h = vp.collect_4h(rows_4h, ranked, regmap)

    trades = {}
    for arm in ARMS:
        print(f"\n[1d] arm={arm}")
        trades[arm] = sorted(collect_1d_mode(syms, ARM_SETS[arm], rows_1d, kids) + t4h,
                             key=lambda t: t["t_in"])

    cut = mx._tnum(SPLIT)
    print(f"\n[분할] 경계 {SPLIT}", flush=True)
    res_tr, res_ho = {}, {}
    for arm in ARMS:
        tr = [t for t in trades[arm] if t["t_in"] < cut]
        ho = [t for t in trades[arm] if t["t_in"] >= cut]
        res_tr[arm] = vp.simulate(tr, "current")
        res_ho[arm] = vp.simulate(ho, "current")
        for tag, r, n in (("train", res_tr[arm], len(tr)), ("hold", res_ho[arm], len(ho))):
            print(f"  [{tag}] {arm:14} 거래 {n:5}  CAGR {r['cagr']*100:+7.1f}%  "
                  f"MDD {r['mdd']*100:6.1f}%  Calmar {r['calmar']:5.2f}  체결 {r['taken']:5}  "
                  f"스킵 슬롯 {r['skip_slot']:4} / 증거금 {r['skip_margin']:4}", flush=True)

    # J3 — 짝지음 블록 부트스트랩
    rng = random.Random(SEED)
    ho_by_arm = {a: [t for t in trades[a] if t["t_in"] >= cut] for a in (MAIN_ARM, "current")}
    cal = paired_slot_boot(ho_by_arm, rng)
    boot_win = (sum(1 for a, c in zip(cal[MAIN_ARM], cal["current"]) if a > c) / len(cal["current"])
                if cal["current"] else 0.0)
    print(f"\n[부트] holdout {BOOT_N}회 — {MAIN_ARM} Calmar 우위 {boot_win*100:.0f}%", flush=True)

    j = judge(res_tr, res_ho, boot_win, MAIN_ARM)
    verdict = "ADOPT_CANDIDATE" if all(j.values()) else "REJECTED"
    print("\n" + "=" * 104)
    print(f"판정 ({MAIN_ARM}): {verdict}")
    for k, v in j.items():
        print(f"  {'O' if v else 'X'}  {k}")
    print("  진단 arm(closed_focus/closed_adopted)은 판정 대상이 아니다 — 사후에 골라 켜지 않는다.")
    print(f"실거래 무변경 (DEPLOY_ON_PASS={DEPLOY_ON_PASS}) — 켜는 것은 관찰 종료 후 사용자 결정")
    print("=" * 104)

    keep = ("cagr", "mdd", "calmar", "taken", "skip_slot", "skip_margin", "exposure")
    per_pat = {arm: {} for arm in ARMS}
    for arm in ARMS:
        for t in trades[arm]:
            d = per_pat[arm].setdefault(t["pattern"], [])
            d.append(t["ret"])
        per_pat[arm] = {k: dict(n=len(v), mean=st.fmean(v)) for k, v in sorted(per_pat[arm].items())}
    json.dump(dict(verdict=verdict, main_arm=MAIN_ARM, judgement=j, boot_win=boot_win,
                   train={a: {k: res_tr[a][k] for k in keep} for a in ARMS},
                   holdout={a: {k: res_ho[a][k] for k in keep} for a in ARMS},
                   per_pattern=per_pat, n_trades={a: len(trades[a]) for a in ARMS},
                   split=SPLIT, deploy_on_pass=DEPLOY_ON_PASS),
              open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print(f"[저장] {OUT}")


if __name__ == "__main__":
    main()
