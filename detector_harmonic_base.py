"""
detector_harmonic_base.py — 하모닉 패턴 공용 라이브러리.

BULLISH 버전 (롱 진입): L-H-L-H-L 피벗 시퀀스 (X=L, A=H, B=L, C=H, D=L).
각 패턴별 Fibonacci 비율:

  XA  = A - X  (상승 레그)
  AB  = A - B  (XA 되돌림)
  BC  = C - B  (AB 되돌림 또는 연장)
  CD  = C - D  (CD 하락 레그)
  AD  = A - D  (전체 되돌림 폭)

패턴           AB/XA              BC/AB       CD/BC          AD/XA (or XD/XC)
Gartley        0.618 ± 0.05       0.382-0.886  1.272-1.618    0.786 ± 0.05
Bat            0.382-0.500        0.382-0.886  1.618-2.618    0.886 ± 0.05
Butterfly      0.786 ± 0.05       0.382-0.886  1.618-2.618    1.272 ± 0.05
Crab           0.382-0.618        0.382-0.886  2.618-3.618    1.618 ± 0.05
Shark          0.382-0.618        1.130-1.618  —              XD/XC=0.886±0.05
Cypher         0.382-0.618        1.272-1.414  —              XD/XC=0.786±0.05

신호 = D 피벗 봉 종가. 라벨/수익: detlib 표준(±10%/20봉/0.2%수수료).
"""
import glob, os
from detlib import load_ohlcv, outcome

PIVOT_WINDOW = 3  # 피벗 확인용 전후 봉 수 (하모닉은 3봉으로 더 많은 피벗 확보)

# data/ 디렉터리의 모든 1d CSV → 심볼명 추출 (43개)
def _all_syms():
    return sorted({
        os.path.basename(f)[:-7].upper()
        for f in glob.glob("data/*_1d.csv")
    })

HARMONIC_SYMBOLS = _all_syms() or ["BTC", "SOL", "ETH", "BNB", "XRP", "ADA", "AVAX"]


def find_pivots(rows, window=PIVOT_WINDOW):
    """교대 스윙 고점/저점 탐지. [(idx, price, 'H'|'L')] 반환."""
    n = len(rows)
    raw = []
    for i in range(window, n - window):
        hi, lo = rows[i]["h"], rows[i]["l"]
        span = range(i - window, i + window + 1)
        is_high = all(rows[j]["h"] <= hi for j in span if j != i)
        is_low  = all(rows[j]["l"] >= lo for j in span if j != i)
        if is_high:
            raw.append((i, hi, "H"))
        if is_low:
            raw.append((i, lo, "L"))

    # 교대 강제: 연속 같은 타입이면 더 극단적인 값 유지
    alt = []
    for p in sorted(raw, key=lambda x: x[0]):
        if not alt or alt[-1][2] != p[2]:
            alt.append(list(p))
        elif p[2] == "H" and p[1] > alt[-1][1]:
            alt[-1] = list(p)
        elif p[2] == "L" and p[1] < alt[-1][1]:
            alt[-1] = list(p)
    return [tuple(p) for p in alt]


def _in(val, lo, hi):
    return lo <= val <= hi


def check_ratios(x, a, b, c, d, cfg):
    """
    BULLISH 하모닉 비율 검증.
    x,a,b,c,d: 각 피벗의 가격 (X=저점, A=고점, B=저점, C=고점, D=저점)
    cfg dict 키:
      ab_xa: (min, max)
      bc_ab: (min, max)
      cd_bc: (min, max)  — 없으면 검사 생략
      ad_xa: (min, max)  — 없으면 생략
      xd_xc: (min, max)  — 없으면 생략 (shark/cypher 용)
    """
    xa = a - x   # 상승 레그
    ab = a - b   # 하락 되돌림
    bc = c - b   # 반등 (>AB 이면 연장)
    cd = c - d   # 최종 하락

    if xa <= 0 or ab <= 0 or bc <= 0 or cd <= 0:
        return False
    if not _in(ab / xa, *cfg["ab_xa"]):
        return False
    if not _in(bc / ab, *cfg["bc_ab"]):
        return False
    if "cd_bc" in cfg and not _in(cd / bc, *cfg["cd_bc"]):
        return False
    if "ad_xa" in cfg:
        ad = a - d
        if not _in(ad / xa, *cfg["ad_xa"]):
            return False
    if "xd_xc" in cfg:
        xc = c - x
        xd = d - x
        if xc <= 0 or not _in(xd / xc, *cfg["xd_xc"]):
            return False
    return True


def detect_harmonic(rows, cfg):
    """
    BULLISH 하모닉 신호 인덱스 목록 반환.
    L-H-L-H-L 교대 피벗 5개 중 비율 조건 충족 시 D 봉 인덱스 기록.
    """
    pivots = find_pivots(rows)
    signals = []
    for i in range(4, len(pivots)):
        types = tuple(pivots[j][2] for j in range(i - 4, i + 1))
        if types != ("L", "H", "L", "H", "L"):
            continue
        xp = pivots[i - 4][1]
        ap = pivots[i - 3][1]
        bp = pivots[i - 2][1]
        cp = pivots[i - 1][1]
        dp = pivots[i][1]
        if check_ratios(xp, ap, bp, cp, dp, cfg):
            signals.append(pivots[i][0])  # D 피벗 봉 인덱스
    return signals


def make_detect(cfg):
    """analysis.py용 detect(rows) 함수 생성 팩토리."""
    def detect(rows):
        return detect_harmonic(rows, cfg)
    return detect


def make_evaluate(cfg):
    """orchestrator 표준 evaluate() 생성 팩토리."""
    def evaluate(date_from=None, date_to=None, tf="1d"):
        per = {}
        agg = dict(n=0, real=0, fake=0, neutral=0)
        rets = []
        for sym in HARMONIC_SYMBOLS:
            try:
                rows = load_ohlcv(sym, tf)
            except FileNotFoundError:
                continue
            cc = dict(n=0, real=0, fake=0, neutral=0)
            for si in detect_harmonic(rows, cfg):
                d = rows[si]["date"]
                if date_from and d < date_from:
                    continue
                if date_to and d > date_to:
                    continue
                lab, ret = outcome(rows, si, direction="long")
                cc["n"] += 1
                cc[lab] += 1
                rets.append(ret)
            per[sym] = cc
            for k in agg:
                agg[k] += cc[k]
        return dict(agg=agg, per=per, rets=rets)
    return evaluate
