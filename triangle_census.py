"""
triangle_census.py — '3파 종료 후 4파 삼각수렴' 후보의 **표본 수만** 센다 (2026-09-04).

검토 단계의 실현가능성 조사다. 전략 구현이 아니다 — 라벨도 수익률도 계산하지 않는다.
물음 하나: **동결 게이트의 n>=20 을 채울 수 있는가.** 채우지 못하면 설계 논의가 무의미하다.

세는 규칙(사용자 제시 검출 규칙에서 거래량 조건만 뺀 뼈대):
  1) zigzag(threshold) 로 스윙 피벗. **마지막 잠정 피벗은 버린다**(미확정 = 인과성).
  2) 임펄스 후보: L-H-L-H-L... 중 상승 5분절(P0L,P1H,P2L,P3H)에서
     · 2파가 1파 시작점을 깨지 않음  P2.price > P0.price
     · 3파가 1파보다 짧지 않음        (P3-P2) >= (P1-P0)
  3) 수렴 후보: P3 이후 피벗들이 고점 낮아지고 저점 높아지는 것이 TOUCH 회 이상 이어지고,
     마지막 폭 <= 첫 폭 x WIDTH_RATIO.
  4) 무효화: 수렴 구간 최저가가 P1(1파 고점) 아래로 내려가면 폐기(4파-1파 중첩 금지).

zigzag 임계값·터치 수·폭 비율을 격자로 돌려 **임계값 민감도**도 같이 본다.
출력 triangle_census.json. 실행: python triangle_census.py [--no-fetch] [--tf 1d,4h,1h]
"""
import json
import sys

import detlib
import method_s as ms
from elliott_detect import zigzag

ZZ_GRID = [0.03, 0.05, 0.07]
TOUCH_GRID = [4, 5]
WIDTH_GRID = [0.6, 0.5]
TFS = ["1d", "4h", "1h"]


def pivots_causal(closes, zz):
    """zigzag 피벗에서 **마지막 하나를 버린다** — 드래그 중인 잠정 피벗은 미확정이다."""
    pv = zigzag(closes, zz)
    return pv[:-1] if len(pv) >= 2 else []


def count_symbol(rows, zz, touch, width):
    """(임펄스 후보 수, 삼각형 후보 수). 피벗은 (index, price, kind) 또는 Pivot 객체."""
    closes = [r["c"] for r in rows]
    pv = pivots_causal(closes, zz)
    if len(pv) < 6:
        return 0, 0

    def px(p):
        return p.price if hasattr(p, "price") else p[1]

    def ix(p):
        return p.index if hasattr(p, "index") else p[0]

    def kd(p):
        return p.kind if hasattr(p, "kind") else p[2]

    n_imp = n_tri = 0
    for a in range(len(pv) - 5):
        p0, p1, p2, p3 = pv[a], pv[a + 1], pv[a + 2], pv[a + 3]
        if not (kd(p0) == "L" and kd(p1) == "H" and kd(p2) == "L" and kd(p3) == "H"):
            continue
        if not (px(p2) > px(p0)):                 # 2파가 1파 시작점 미돌파
            continue
        if (px(p3) - px(p2)) < (px(p1) - px(p0)):  # 3파가 최단이 아님
            continue
        n_imp += 1
        # 수렴 구간
        seq = pv[a + 3:]
        if len(seq) < touch + 1:
            continue
        highs = [px(p) for p in seq if kd(p) == "H"]
        lows = [px(p) for p in seq if kd(p) == "L"]
        k = min(len(highs), len(lows))
        if k < 2:
            continue
        conv = 0
        for j in range(1, k):
            if highs[j] < highs[j - 1] and lows[j] > lows[j - 1]:
                conv += 1
            else:
                break
        touched = conv + 1
        if touched * 2 < touch:                    # 터치 수 = 고점·저점 합
            continue
        w0 = highs[0] - lows[0]
        w1 = highs[conv] - lows[conv]
        if w0 <= 0 or w1 / w0 > width:
            continue
        seg = rows[ix(p3):ix(seq[min(conv * 2, len(seq) - 1)]) + 1]
        if seg and min(r["l"] for r in seg) < px(p1):   # 4파-1파 중첩 무효화
            continue
        n_tri += 1
    return n_imp, n_tri


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    tfs = TFS
    if "--tf" in argv:
        tfs = argv[argv.index("--tf") + 1].split(",")
    ms.UNIVERSE_MODE = True
    syms = ms.symbols()
    print(f"[표본] {len(syms)}종목 | TF {tfs}")
    if "--no-fetch" not in argv:
        ms.ensure_data(1800, syms)

    out = {}
    print("=" * 96)
    print("삼각수렴(4파) 후보 표본 조사 — 라벨·수익률 없음. 동결 게이트 n>=20 충족 여부만")
    print("=" * 96)
    print(f"  {'TF':<5}{'zigzag':>8}{'터치':>6}{'폭비':>6}{'종목':>6}{'피벗계':>9}"
          f"{'임펄스후보':>11}{'삼각형후보':>11}   판정")
    print("  " + "-" * 92)
    for tf in tfs:
        loaded = {}
        for s in syms:
            try:
                loaded[s] = detlib.load_ohlcv(s, tf)
            except (FileNotFoundError, RuntimeError):
                continue
        for zz in ZZ_GRID:
            npv = sum(len(pivots_causal([r["c"] for r in rw], zz)) for rw in loaded.values())
            for touch in TOUCH_GRID:
                for width in WIDTH_GRID:
                    imp = tri = 0
                    for rw in loaded.values():
                        if len(rw) < 60:
                            continue
                        i2, t2 = count_symbol(rw, zz, touch, width)
                        imp += i2; tri += t2
                    key = f"{tf}|zz{zz}|t{touch}|w{width}"
                    out[key] = dict(tf=tf, zz=zz, touch=touch, width=width,
                                    symbols=len(loaded), pivots=npv,
                                    impulse=imp, triangle=tri)
                    ok = "n>=20 충족" if tri >= 20 else ("표본 부족" if tri else "후보 0건")
                    print(f"  {tf:<5}{zz:>8.2f}{touch:>6}{width:>6.1f}{len(loaded):>6}{npv:>9}"
                          f"{imp:>11}{tri:>11}   {ok}", flush=True)
    json.dump(out, open("triangle_census.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    best = max(out.values(), key=lambda v: v["triangle"]) if out else None
    print("\n[요약] 격자 중 최대 표본:", json.dumps(best, ensure_ascii=False) if best else "없음")
    print("[감도] 같은 TF 에서 zigzag 임계값만 바꿨을 때 후보 수 변화 —")
    for tf in tfs:
        row = {zz: max((v["triangle"] for v in out.values()
                        if v["tf"] == tf and v["zz"] == zz), default=0) for zz in ZZ_GRID}
        base = row.get(0.05, 0)
        rel = {k: (f"{(v/base-1)*100:+.0f}%" if base else "-") for k, v in row.items()}
        print(f"    {tf}: {row}  (0.05 대비 {rel})")
    print("RESULT_JSON: " + json.dumps(
        {k: v["triangle"] for k, v in out.items()}, separators=(",", ":")))


if __name__ == "__main__":
    main()
