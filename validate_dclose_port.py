"""
validate_dclose_port.py — D_close 를 슬롯 경합 프레임(validate_portfolio)에서 재측정 (R-021, 2026-10-26, 자율 연구 루프).

계기: R-002(validate_dclose) 풀링 자산곡선이 슬롯 범람 프레임(CAGR −40%, MDD −96%)이라 P5 가 무의미했다.
종가 손절은 손절 지연으로 보유가 길어져 슬롯 점유가 커진다 — 그 비용은 슬롯·증거금 경합 하에서만 보인다.

사전 등록: registry dclose_port_prereg_2026_10_26 (결과 보기 전 고정).
  프레임   validate_portfolio 그대로 (배포 집합·실거래 사이징·MAX_POS·분할 2025-01-01·슬롯 배분 current)
  arm      D (현행) vs D_close (종가 ≤ 진입가×0.92 면 종가 청산, 숏 대칭, 재해 손절 ±15% 극값 / opp·레짐·만기는 D)
  판정     holdout J1 CAGR / J2 Calmar / J3 짝지음 부트 >=0.60 / J4 MDD 5%p / J5 train CAGR·Calmar / J6 노출비 0.90~1.10
  DEPLOY_ON_PASS = False

실행: python validate_dclose_port.py [--no-fetch]
"""
import json
import random
import statistics as st
import sys

import method_t as mt
import regime_switch
import validate_portfolio as vp
import validate_regime_split_all as va
from validate_regime_split import turnover_rank

DEPLOY_ON_PASS = False
CAT = 0.15
STOP = vp.STOP
SPLIT = vp.SPLIT
BOOT_N, SEED = vp.BOOT_N, vp.SEED
J3_WIN, J4_TOL = vp.J3_WIN, vp.J4_MDD_TOL
J6_LO, J6_HI = 0.90, 1.10
OUT = "_dclose_port.json"


def outcome_d_close(rows, si, direction, opp_set):
    """mt.outcome_d 와 같은 시그니처. 손절만 종가 판정, 재해 손절 ±15% 는 봉 극값. (ret, hold, reason)"""
    base = rows[si]["c"]
    entry_reg = mt.REGMAP.get(rows[si]["date"])
    end = min(si + mt.MAX_HOLD, len(rows) - 1)
    is_long = direction == "long"
    for j in range(si + 1, end + 1):
        if is_long:
            if rows[j]["l"] <= base * (1 - CAT):
                return -CAT - mt.FEE, j - si, "cat_stop"
            if rows[j]["c"] <= base * (1 - STOP):
                return rows[j]["c"] / base - 1 - mt.FEE, j - si, "sl_close"
        else:
            if rows[j]["h"] >= base * (1 + CAT):
                return -CAT - mt.FEE, j - si, "cat_stop"
            if rows[j]["c"] >= base * (1 + STOP):
                return 1 - rows[j]["c"] / base - mt.FEE, j - si, "sl_close"
        regsw = mt.REGMAP.get(rows[j]["date"]) not in (None, entry_reg)
        if j in opp_set or regsw:
            c = rows[j]["c"]
            r = (c - base) / base if is_long else (base - c) / base
            return r - mt.FEE, j - si, ("opp_signal" if j in opp_set else "regime_switch")
    px = rows[end]["o"]
    r = (px - base) / base if is_long else (base - px) / base
    return r - mt.FEE, end - si, "maxhold"


def _key(t):
    return (t["t_in"], t["pattern"], t["sym"])


def pair_trades(d_list, c_list):
    """같은 신호에 두 청산을 적용한 거래 목록을 (t_in, 패턴, 심볼) 순으로 정렬해 인덱스 정렬 쌍으로."""
    d, c = sorted(d_list, key=_key), sorted(c_list, key=_key)
    assert len(d) == len(c), (len(d), len(c))
    for a, b in zip(d, c):
        assert _key(a) == _key(b), (a, b)
    return d, c


def paired_boot(d_tr, c_tr, rng, n_boot=BOOT_N):
    """같은 재표집 인덱스를 두 arm 에 적용. 날짜 골격(t_in)은 dst, 수익·보유는 src — vp.block_bootstrap 과 같은 방식."""
    n = len(d_tr)
    wins = 0
    for _ in range(n_boot):
        idx = []
        while len(idx) < n:
            s = rng.randrange(0, n)
            idx.extend(range(s, min(n, s + vp.BLOCK)))
        idx = idx[:n]
        out = []
        for lst in (d_tr, c_tr):
            res = []
            for k, j in enumerate(idx):
                src, dst = lst[j], lst[k]
                hold = max(src["t_out"] - src["t_in"], 0.0)
                res.append(dict(src, t_in=d_tr[k]["t_in"], t_out=d_tr[k]["t_in"] + hold))
            out.append(res)
        a = vp.simulate(out[0], "current")["calmar"]
        b = vp.simulate(out[1], "current")["calmar"]
        wins += int(b > a)
    return wins / n_boot


def judge(h_d, h_c, t_d, t_c, boot_win):
    j = dict(J1=h_c["cagr"] > h_d["cagr"],
             J2=h_c["calmar"] > h_d["calmar"],
             J3=boot_win >= J3_WIN,
             J4=h_c["mdd"] >= h_d["mdd"] - J4_TOL,
             J5=t_c["cagr"] >= t_d["cagr"] and t_c["calmar"] >= t_d["calmar"],
             J6=bool(h_d["exposure"] > 0 and J6_LO <= h_c["exposure"] / h_d["exposure"] <= J6_HI))
    return j, ("ADOPT_CANDIDATE" if all(j.values()) else "REJECTED")


def _line(tag, arm, r):
    return (f"  [{tag}] {arm:8} CAGR {r['cagr']*100:+7.1f}%  MDD {r['mdd']*100:6.1f}%  Calmar {r['calmar']:5.2f}  "
            f"체결 {r['taken']:5}  스킵 슬롯 {r['skip_slot']:4} / 증거금 {r['skip_margin']:4}  노출 {r['exposure']:.2f}")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    print("=" * 100)
    print("D_close 포트폴리오 프레임 — registry dclose_port_prereg_2026_10_26 (R-021)")
    print(f"MAX_POS {vp.MAX_POS} · 재해 손절 ±{CAT*100:.0f}% · 분할 {SPLIT} · DEPLOY_ON_PASS={DEPLOY_ON_PASS}")
    print("=" * 100, flush=True)
    syms = va._syms()
    if "--no-fetch" not in argv:
        vp.fetch(syms)
    rows_4h = va.load_tf(syms, "4h")
    ranked = turnover_rank(rows_4h)
    mt.REGMAP = regime_switch.build_regime_map()      # 레짐 전환 청산을 켠다 (2026-09-21 결함 교훈)

    res = {}
    for name, fn in (("D", None), ("D_close", outcome_d_close)):
        print(f"\n[수집] {name}")
        res[name] = vp.collect_1d(syms, outcome_fn=fn) + vp.collect_4h(rows_4h, ranked, mt.REGMAP, outcome_fn=fn)
    d_all, c_all = pair_trades(res["D"], res["D_close"])
    print(f"\n신호 {len(d_all)}건 (두 arm 동일 신호)")

    cut = vp.mx._tnum(SPLIT)
    d_tr = [t for t in d_all if t["t_in"] < cut]
    c_tr = [t for t in c_all if t["t_in"] < cut]
    d_ho = [t for t in d_all if t["t_in"] >= cut]
    c_ho = [t for t in c_all if t["t_in"] >= cut]
    print(f"train {len(d_tr)} / holdout {len(d_ho)}")
    sim = {}
    for tag, dd, cc in (("train", d_tr, c_tr), ("holdout", d_ho, c_ho)):
        sim[tag] = dict(D=vp.simulate(dd, "current"), D_close=vp.simulate(cc, "current"))
        print(_line(tag, "D", sim[tag]["D"]))
        print(_line(tag, "D_close", sim[tag]["D_close"]))

    boot = paired_boot(d_ho, c_ho, random.Random(SEED))
    print(f"\nP(D_close Calmar > D) = {boot:.0%} (짝지음 블록 부트 {BOOT_N}회)")
    J, verdict = judge(sim["holdout"]["D"], sim["holdout"]["D_close"], sim["train"]["D"], sim["train"]["D_close"], boot)

    diff = [(a["ret"] - b["ret"]) for a, b in zip(c_all, d_all)]
    hold = lambda L: st.mean(max(t["t_out"] - t["t_in"], 0.0) for t in L)
    diag = dict(n_signals=len(d_all), mean_ret_D=st.mean(t["ret"] for t in d_all),
                mean_ret_Dclose=st.mean(t["ret"] for t in c_all), mean_diff=st.mean(diff),
                hold_days_D=hold(d_all), hold_days_Dclose=hold(c_all))
    print("\n진단(판정 아님):", json.dumps(diag, ensure_ascii=False))
    print("기준:", J)
    print(f"판정: **{verdict}** (DEPLOY_ON_PASS={DEPLOY_ON_PASS} — 반영은 사용자 결정)")
    strip = lambda r: {k: v for k, v in r.items() if k != "blocked_by"}
    json.dump(dict(prereg="dclose_port_prereg_2026_10_26", verdict=verdict, J=J, boot_win=boot, diag=diag,
                   train={k: strip(v) for k, v in sim["train"].items()},
                   holdout={k: strip(v) for k, v in sim["holdout"].items()}),
              open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print("RESULT_JSON: " + json.dumps(dict(verdict=verdict, J=J, boot=boot), ensure_ascii=False))


if __name__ == "__main__":
    main()
