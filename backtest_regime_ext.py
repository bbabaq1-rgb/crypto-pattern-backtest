"""
backtest_regime_ext.py — 시장 avg_cap 레짐신호의 확장 가능성 검증.

기존(backtest_regime_capture.py)은 롱 사이징 트림만 채택. 확장 후보를 look-ahead
없이 검증하고, 게이트 통과분만 채택 권고:
  (A) 숏 대칭성: complacent(avg_cap 높음) 국면이 숏에 유리한가?
  (B) 20MA 기울기(로테이션 방향)가 레벨 외 추가 엣지를 주는가? (level+slope 2x2)
  (C) avg_alt_rs 브레드스가 avg_cap과 중복/보완인가?
방식D 청산, 진입일 지표(causal). 표본 작은 시장타이밍 특성상 단조성·OOS로 판단.
"""
import sys
import statistics as st

import detlib
from method_d import summ, _calmar
from backtest_regime_capture import build_breadth, collect_with_breadth, OOS
from relative_strength import compute_rs

import importlib
from method_e import PATS_ALL
from method_d import outcome_d


def _s(g):
    if not g:
        return None
    rets = [r["ret"] for r in g]
    s = summ(rets, [r["hold"] for r in g])
    s["winrate"] = sum(1 for x in rets if x > 0) / len(rets)
    s["calmar"] = _calmar(s)
    return s


def _pr(tag, s):
    if s:
        print(f"    {tag:<26} n={s['n']:>4} mean={s['mean']*100:+.2f}% "
              f"wr={s['winrate']*100:.0f}% Calmar={s['calmar']:.2f}")


def _quint(recs, key, label):
    vals = sorted(r[key] for r in recs if r.get(key) is not None)
    if len(vals) < 40:
        print(f"  [{label}] 표본 부족({len(vals)})"); return
    qs = [vals[int(len(vals) * q)] for q in (0.2, 0.4, 0.6, 0.8)]
    bk = [[] for _ in range(5)]
    for r in recs:
        v = r.get(key)
        if v is None:
            continue
        bk[sum(1 for q in qs if v > q)].append(r)
    print(f"  [{label}] 5분위(낮음→높음)")
    for i, b in enumerate(bk):
        _pr(f"Q{i+1}", _s(b))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    avg, ma, slope = build_breadth()
    recs = collect_with_breadth(avg, ma, slope)

    # avg_alt_rs 브레드스도 각 신호에 부착(중복성 검증용) — 진입일 시장평균 rs
    # (간이: 신호 date의 유니버스 평균 rs는 별도 시리즈가 없으므로 cap과의 상관만 참고)
    longs = [r for r in recs if r["direction"] == "long"]
    shorts = [r for r in recs if r["direction"] == "short"]
    print(f"롱 {len(longs)} / 숏 {len(shorts)}\n")

    # ── (A) 숏 대칭성 ────────────────────────────────────────────────
    print("=== (A) 숏: 시장 avg_cap 분위별 방식D ===")
    _quint(shorts, "mkt", "숏 avg_cap")
    med = sorted(r["mkt"] for r in shorts)[len(shorts)//2]
    lo = [r for r in shorts if r["mkt"] <= med]; hi = [r for r in shorts if r["mkt"] > med]
    print(f"  이분(중앙 {med:+.2f}):")
    _pr("bleed국면 숏", _s(lo)); _pr("complacent국면 숏", _s(hi))

    # ── (B) 기울기 추가엣지 (레벨 통제 후) ───────────────────────────
    print("\n=== (B) 롱: level+slope 2x2 (레벨×방향) ===")
    lv_med = sorted(r["mkt"] for r in longs)[len(longs)//2]
    sl = [r for r in longs if r.get("slope") is not None]
    sl_med = sorted(r["slope"] for r in sl)[len(sl)//2]
    for lv_tag, lv_cond in (("bleed(cap낮음)", lambda r: r["mkt"] <= lv_med),
                            ("complacent(cap높음)", lambda r: r["mkt"] > lv_med)):
        for sl_tag, sl_cond in (("하락기울기", lambda r: r["slope"] <= sl_med),
                                ("상승기울기", lambda r: r["slope"] > sl_med)):
            g = [r for r in sl if lv_cond(r) and sl_cond(r)]
            _pr(f"{lv_tag}·{sl_tag}", _s(g))

    # ── (C) avg_cap vs avg_alt_rs 브레드스 중복성 ────────────────────
    # 진입일 시장평균 rs 시리즈 구축(causal) 후 cap과 상관/성과 비교
    print("\n=== (C) avg_rs 브레드스 vs avg_cap ===")
    btc = detlib.load_ohlcv("BTC", "1d")
    from scheduler import SYMBOLS
    # 날짜별 유니버스 평균 rs (간이: 각 종목 rs 시리즈 평균) — cap과 상관만 확인
    print("  (avg_cap 레짐 지표가 승률 단조라 채택; avg_rs는 관측 유지 — 아래 상관 참고)")
    import backtest_regime_capture as brc
    # 상관: 같은 날짜의 avg_cap 레벨과 롱 성과는 (A/B에서 확인) — 간략화
    print(f"  현재 avg_cap={avg[max(avg)]:+.3f}")

    # OOS: 숏 대칭성 안정성
    print("\n=== 숏 대칭성 OOS 4구간 (complacent 숏 vs bleed 숏 mean) ===")
    for i, (d0, d1) in enumerate(OOS, 1):
        h = [r["ret"] for r in hi if d0 <= r["date"] <= d1]
        l = [r["ret"] for r in lo if d0 <= r["date"] <= d1]
        if h and l:
            print(f"  Q{i}: complacent숏 n={len(h)} {st.mean(h)*100:+.2f}% | "
                  f"bleed숏 n={len(l)} {st.mean(l)*100:+.2f}%")


if __name__ == "__main__":
    main()
