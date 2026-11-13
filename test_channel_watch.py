"""
test_channel_watch.py — 채널 이탈 알림 봇(channel_watch.py) 고정 테스트. 네트워크·시크릿 없이 돈다.

  §1 격리 — 매매 모듈과 양방향 import 없음, 워크플로에 매매 시크릿 없음·별도 concurrency
  §2 닫힌 봉만 — 형성 중인 봉 제외
  §3 피벗 — 확정된 것만(마지막 k 봉은 피벗 아님)
  §4 채널 맞춤 — 합성 상승 채널의 기울기·폭·접점을 찾는다
  §5 이탈 판정 — 위·아래·버퍼 안
  §6 거대한 띠 방지 — 폭이 구간 고저 범위를 넘지 않는다
  §7 중복 방지 — 같은 채널 이탈은 한 번만 기록
  §8 기록 저장소가 없을 때 — 방금 닫힌 봉만
  §9 이후 수익 — 이탈 방향 부호, 20봉 채워지면 완료
  §10 표기 — 알림·요약 문구
  §11 설정 파일 정합
  §12 SQL — RLS·권한 회수·유니크 키
  §17 삼각수렴 맞춤 — 합성 대칭·상승·하락 삼각형을 찾고 꼭짓점은 앞쪽
  §18 삼각수렴 이탈 — 위·아래·ATR 하한 버퍼 안·꼭짓점 지나면 없음
  §19 삼각수렴이 아닌 것 — 평행 채널·쐐기형·고-저가 안 엇갈린 기준점
  §20 삼각수렴 실행 — 설정 종목(BTC)만, 기록 kind/anchor, 중복 방지 키
  §21 삼각수렴 설정 — BTC 만·1시간봉 이상·유지 한도 = 이탈 기준·근거 문구
  §22 삼각수렴 표기 — 알림·요약 문구
  §23 앨범 — 10장씩 나눠 보낸다
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel_watch as cw

FAIL = []


def check(name, ok):
    print(("  OK   " if ok else "  FAIL ") + name)
    if not ok:
        FAIL.append(name)


HERE = os.path.dirname(os.path.abspath(__file__))
SRC = open(os.path.join(HERE, "channel_watch.py"), encoding="utf-8").read()
H = 3_600_000


def bars_channel(n=120, lo0=100.0, slope=0.25, width=10.0, period=12, t0=1_700_000_000_000, step=H):
    """아래 선 lo0+slope*t, 위 선 +width 사이를 period 봉 주기로 오가는 합성 봉."""
    rows = []
    for t in range(n):
        lo = lo0 + slope * t
        ph = (t % period) / period
        frac = 1 - abs(2 * ph - 1)          # 0 → 1 → 0 삼각파
        mid = lo + width * (0.05 + 0.9 * frac)
        h = mid + 0.04 * width
        l = mid - 0.04 * width
        h = min(h, lo + width)
        l = max(l, lo)
        rows.append(dict(ts=t0 + t * step, o=mid, h=h, l=l, c=mid, v=100.0))
    return rows


CH = dict(touch_tol=0.10, contain_tol=0.05, break_buffer=0.05, min_touches_each=2,
          min_width_atr=1.0, touch_atr=5.0, max_width_range=1.0, recent_pivots=6)

print("[1] 격리")
imports = set(re.findall(r"^\s*(?:import|from)\s+([A-Za-z_][\w]*)", SRC, re.M))
imports |= set(re.findall(r"^\s+import\s+([A-Za-z_][\w]*)", SRC, re.M))
TRADING = {"scheduler", "paper_executor", "exchange", "sizing", "direction_switch", "ai_elliott",
           "ai_judge", "steward", "regime_switch", "fetch_data", "detlib", "elliott_watch"}
check("channel_watch 는 매매·연구 모듈을 import 하지 않는다", not (imports & TRADING))
for f in ("scheduler.py", "paper_executor.py", "exchange.py", "sizing.py", "ai_elliott.py"):
    p = os.path.join(HERE, f)
    if os.path.exists(p):
        check(f"{f} 는 channel_watch 를 import 하지 않는다", "channel_watch" not in open(p, encoding="utf-8").read())
check("주문 함수 이름이 없다", not re.search(r"create_order|place_swap|close_swap|place_stop", SRC))
WF = open(os.path.join(HERE, ".github/workflows/channel_watch.yml"), encoding="utf-8").read()
check("워크플로: OKX 매매 시크릿을 받지 않는다", "OKX_" not in WF)
check("워크플로: 매매 스케줄러와 다른 concurrency 그룹", "group: channel-watch" in WF
      and "scheduler" not in re.search(r"concurrency:(.*?)jobs:", WF, re.S).group(1))
check("워크플로: dispatch 로만 발화(GitHub schedule 없음)", "workflow_dispatch" in WF and "schedule:" not in WF)
check("워크플로: 실행 전에 이 테스트를 돈다", "python test_channel_watch.py" in WF)
TY = open(os.path.join(HERE, ".github/workflows/tests.yml"), encoding="utf-8").read()
check("tests.yml 에 test_channel_watch", "test_channel_watch.py" in TY)

print("[2] 닫힌 봉만")
rows = bars_channel(10)
now = rows[-1]["ts"] + H // 2            # 마지막 봉은 아직 형성 중
check("형성 중인 마지막 봉을 뺀다", len(cw.closed_only(rows, "1h", now)) == 9)
check("마감 시각이 지난 봉은 남긴다", len(cw.closed_only(rows, "1h", rows[-1]["ts"] + H)) == 10)

print("[3] 피벗")
rows = bars_channel(60)
hi, lo = cw.pivots(rows, 3)
check("피벗이 있다", len(hi) >= 3 and len(lo) >= 3)
check("마지막 k 봉은 피벗이 아니다", all(i < len(rows) - 3 for i in hi + lo))
check("고점 피벗은 양옆보다 높다", all(rows[i]["h"] >= max(r["h"] for r in rows[i - 3:i + 4]) for i in hi))

print("[4] 채널 맞춤")
rows = bars_channel(100)
chn = cw.fit_channel(rows, 3, 20, CH)
check("채널을 찾는다", chn is not None)
if chn:
    check(f"기울기 ≈ 0.25 (실제 {chn['slope']:.3f})", abs(chn["slope"] - 0.25) < 0.05)
    check(f"폭 ≈ 합성 진폭 9.0~10.0 (실제 {chn['width']:.2f})", 8.0 < chn["width"] < 11.0)
    check("상승 채널로 분류", chn["kind"] == "up")
    check("위·아래 접점 각각 2 이상", len(chn["touches_lo"]) >= 2 and len(chn["touches_hi"]) >= 2)
flat = bars_channel(100, slope=0.0)
cf = cw.fit_channel(flat, 3, 20, CH)
check("기울기 0 이면 박스로 분류", cf is not None and cf["kind"] == "box")
check("데이터가 짧으면 채널 없음", cw.fit_channel(rows[:20], 3, 20, CH) is None)

print("[5] 이탈 판정")
t = len(rows)
lo_v, hi_v = cw.lines_at(chn, t)
w = chn["width"]
side, depth = cw.check_break(chn, dict(c=hi_v + 0.2 * w), t, CH)
check("위로 폭의 20% 넘으면 상단 돌파", side == "up" and abs(depth - 0.2) < 1e-6)
side, _ = cw.check_break(chn, dict(c=lo_v - 0.2 * w), t, CH)
check("아래로 폭의 20% 넘으면 하단 이탈", side == "down")
side, _ = cw.check_break(chn, dict(c=hi_v + 0.03 * w), t, CH)
check("버퍼(5%) 안이면 이탈 아님", side is None)
side, _ = cw.check_break(chn, dict(c=(lo_v + hi_v) / 2), t, CH)
check("채널 안이면 이탈 아님", side is None)

print("[6] 거대한 띠 방지")
import random
random.seed(7)
noisy = []
p = 100.0
for i in range(150):
    p *= 1 + random.uniform(-0.02, 0.021)
    noisy.append(dict(ts=1_700_000_000_000 + i * H, o=p, h=p * 1.01, l=p * 0.99, c=p, v=1.0))
cn = cw.fit_channel(noisy, 3, 20, dict(CH, touch_atr=1.0))
if cn:
    seg = noisy[cn["a"]:]
    rng = max(r["h"] for r in seg) - min(r["l"] for r in seg)
    check("고른 채널 폭 ≤ 그 구간 고저 범위", cn["width"] <= rng + 1e-9)
else:
    check("무작위 경로 — 채널이 없어도 된다", True)

print("[7] 중복 방지")


class PStore(cw.MemStore):
    persistent = True


def make_break_rows():
    base = bars_channel(100)
    c = cw.fit_channel(base, 3, 20, CH)
    lo_v, hi_v = cw.lines_at(c, len(base))
    px = hi_v + 0.3 * c["width"]
    nxt = dict(ts=base[-1]["ts"] + H, o=px, h=px + 0.1, l=px - 0.1, c=px, v=300.0)
    return base + [nxt]


brk = make_break_rows()
CFG = cw.load_cfg()
fake = lambda sym, tf, limit: brk
import json as _json
orig_load = cw.load_cfg
cw.load_cfg = lambda path=None: dict(CFG, watch=[{"symbol": "TST", "tfs": ["1h"]}], channel=CH,
                                      params={"1h": {"lookback": 168, "pivot_k": 3, "min_span": 20,
                                                     "recheck_bars": 3}}, summary_hour_utc=99,
                                      triangle={})
st = PStore()
now_ms = brk[-1]["ts"] + H + 60_000
cw.run([], now_ms=now_ms, fetch=fake, store=st, send=False)
check("이탈 1건 기록", len(st.rows) == 1 and st.rows[0]["side"] == "up")
check("기록에 채널·이탈 정보", st.rows and all(k in st.rows[0] for k in
      ("alert_key", "upper", "lower", "width", "depth", "touches_lo", "touches_hi", "bar_ts")))
cw.run([], now_ms=now_ms + H, fetch=fake, store=st, send=False)
check("같은 채널 이탈은 다음 실행에서 다시 기록하지 않는다", len(st.rows) == 1)

print("[8] 기록 저장소가 없을 때")
ms = cw.MemStore()
cw.run([], now_ms=brk[-1]["ts"] + H + 60_000, fetch=fake, store=ms, send=False)
check("방금 닫힌 봉의 이탈은 알린다", len(ms.rows) == 1)
ms2 = cw.MemStore()
cw.run([], now_ms=brk[-1]["ts"] + H + 3 * H, fetch=fake, store=ms2, send=False)
check("닫힌 지 오래된 봉은 알리지 않는다(실행 사이 중복 방지 수단이 없어서)", len(ms2.rows) == 0)
cw.load_cfg = orig_load

print("[9] 이후 수익")
seq = [dict(ts=i, c=100.0 + i) for i in range(30)]
row = dict(bar_ts=5, side="up", ret_1=None, ret_5=None, ret_20=None)
f = cw.outcome_fields(row, seq)
check("상단 돌파 뒤 상승은 +", abs(f["ret_1"] - (106 / 105 - 1)) < 1e-6 and f["ret_5"] > 0)
check("20봉이 있으면 완료", f.get("outcome_done") is True)
row_d = dict(bar_ts=5, side="down", ret_1=None, ret_5=None, ret_20=None)
check("하단 이탈 뒤 상승은 −", cw.outcome_fields(row_d, seq)["ret_1"] < 0)
short = cw.outcome_fields(dict(bar_ts=25, side="up", ret_1=None, ret_5=None, ret_20=None), seq)
check("20봉이 안 지났으면 완료 아님", "outcome_done" not in short and "ret_1" in short)
check("이탈 봉이 데이터에 없으면 아무것도 안 채운다", cw.outcome_fields(dict(bar_ts=999, side="up"), seq) == {})

print("[10] 표기")
base = bars_channel(100)
c = cw.fit_channel(base, 3, 20, CH)
ev = dict(symbol="BTC", tf="4h", side="down", depth=0.12, bar=dict(ts=base[-1]["ts"], c=99.5),
          chn=c, upper=110.0, lower=100.0, vol_ratio=1.8)
txt = cw.alert_text(ev)
check("알림에 종목·시간대·하단 이탈", "BTC 4h" in txt and "하단 이탈" in txt)
check("알림에 '매매 신호 아님'과 과거 기준 표기", "매매 신호 아님" in txt and "3봉 안에 채널로 되돌아왔고" in txt)
check("거래량 배수 표기", "1.8배" in txt)
check("채널 없음 요약", "채널 아직 없음" in cw.summary_line("ETH", "1h", dict(chn=None, bar=dict(c=2000.0))))
lb = dict(side="down", upper=2100.0, lower=2050.0, bar=dict(ts=1_700_000_000_000, c=2000.0))
check("채널 없을 때 직전 이탈 표기", "하단 이탈" in cw.summary_line("ETH", "1h", dict(chn=None, bar=dict(c=2000.0), last_break=lb)) and "2,050 아래" in cw.summary_line("ETH", "1h", dict(chn=None, bar=dict(c=2000.0), last_break=lb)))
check("가격 표기", cw.fmt_px(71234.5) == "71,234" and cw.fmt_px(1.2345) == "1.23")

print("[11] 설정 파일")
cfg = orig_load()
check("watch 의 모든 시간대에 params 가 있다", all(tf in cfg["params"] for w in cfg["watch"] for tf in w["tfs"]))
check("모든 시간대가 TF_MS 에 있다", all(tf in cw.TF_MS for tf in cfg["params"]))
check("채널 설정 키", {"touch_tol", "contain_close_tol", "contain_wick_tol", "break_buffer", "min_touches_each",
                    "min_width_atr", "touch_atr", "max_width_range", "recent_pivots", "pivot_method",
                    "zigzag_atr_mult"} <= set(cfg["channel"]))
check("v2: 고점·저점은 ATR 지그재그", cfg["channel"]["pivot_method"] == "zigzag_atr")
check("v2: 종가 유지 한도 = 이탈 기준(얕은 종가 이탈로 채널이 알림 없이 사라지지 않게)",
      cfg["channel"]["contain_close_tol"] == cfg["channel"]["break_buffer"])
check("v2: 이탈 기준은 채널 폭의 15% 이상(가짜 이탈 26%→12% 실측)", cfg["channel"]["break_buffer"] >= 0.15)
check("설계 근거가 설정 파일에 남아 있다", "가짜 이탈" in cfg.get("design_evidence", ""))
check("요약 시앨범 한도(10장) 안", sum(len(w["tfs"]) for w in cfg["watch"]) <= 10)

print("[13] 정시 실행(Supabase pg_cron)")
EXT = open(os.path.join(HERE, "supabase_external_trigger.sql"), encoding="utf-8").read()
m = re.search(r"cron\.schedule\('gh_channel_watch',\s*'([^']+)',\s*\$job\$(.*?)\$job\$", EXT, re.S)
check("gh_channel_watch 크론이 SQL 에 있다", m is not None)
if m:
    f = m.group(1).split()
    check("매시, 정각이 아닌 분(닫힌 봉 확정 뒤)", f[1:] == ["*", "*", "*", "*"] and 0 < int(f[0]) < 15)
    check("channel_watch.yml 을 inputs 없이 호출(기본 mode=check)",
          m.group(2).strip() == "select public.gh_dispatch('channel_watch.yml')")
check("재등록 전 정리 목록에 포함", "'gh_channel_watch'" in EXT.split("$unsched$")[1])

print("[14] v2 — ATR 지그재그 고점·저점")
import math
zz_rows = []
for i in range(300):
    big = 10.0 * math.sin(i / 15.0)          # 큰 스윙(주기 약 94봉)
    small = 0.6 * math.sin(i * 1.7)           # 자잘한 흔들림
    m = 100.0 + big + small
    zz_rows.append(dict(ts=i, o=m, h=m + 0.4, l=m - 0.4, c=m, v=1.0))
zh, zl = cw.pivots_zigzag_atr(zz_rows, 2.0)
fh, fl = cw.pivots(zz_rows, 3)
check(f"지그재그는 자잘한 흔들림을 고점·저점으로 안 잡는다(지그재그 {len(zh) + len(zl)} < 프랙탈 {len(fh) + len(fl)})",
      0 < len(zh) + len(zl) < len(fh) + len(fl))
check("지그재그 고점·저점은 번갈아 나온다", all(a < b for a, b in zip(sorted(zh + zl), sorted(zh + zl)[1:])))
ok = True
for m in (80, 150, 220, 299):
    ph, pl = cw.pivots_zigzag_atr(zz_rows[:m], 2.0)
    if not (set(ph) <= set(zh) and set(pl) <= set(zl)):
        ok = False
check("인과적 — 나중 봉이 생겨도 이미 확정된 고점·저점은 바뀌지 않는다", ok)
check("pivot_method 없으면 종전 프랙탈(v1 호환)", cw.pivot_fn_of({}) is None)
check("pivot_method=zigzag_atr 면 지그재그", cw.pivot_fn_of({"pivot_method": "zigzag_atr"})(zz_rows) == (zh, zl))

print("[16] v2 — 독립 접점")
check("5봉 안에 붙은 접점은 하나로", cw._merge_touches([10, 11, 13, 20, 24, 40], 5) == [10, 20, 40])
check("gap 1 이면 전부 따로(종전 동작)", cw._merge_touches([3, 4, 5], 1) == [3, 4, 5])
cfgc = orig_load()["channel"]
check("설정: touch_min_gap 5", cfgc.get("touch_min_gap") == 5)

print("[15] v2 — 종가·꼬리 유지 한도")
base = bars_channel(100)
c0 = cw.fit_channel(base, 3, 20, CH)
CH2 = dict(CH, contain_close_tol=0.15, contain_wick_tol=0.30, break_buffer=0.15)
t = 60
lo_t, hi_t = cw.lines_at(c0, t)
w0 = c0["width"]
poke = [dict(r) for r in base]
poke[t] = dict(poke[t], c=hi_t + 0.10 * w0, h=hi_t + 0.20 * w0)
check("얕은 종가 이탈(10%)·꼬리(20%)는 채널을 깨지 않는다(v2 한도)", cw.fit_channel(poke, 3, 20, CH2) is not None)
deep = [dict(r) for r in base]
deep[t] = dict(deep[t], c=lo_t - 0.25 * w0, l=lo_t - 0.40 * w0)
cd = cw.fit_channel(deep, 3, 20, CH2)
check("깊은 종가 이탈(25%)이 있었던 구간은 같은 채널로 잇지 않는다", cd is None or cd["a"] > t)


# ---------------------------------------------------------------- 삼각수렴 (2026-11-13)


def bars_triangle(n=110, apex=160, top0=120.0, bot0=100.0, kind="sym", period=12,
                  t0=1_700_000_000_000, step=H):
    """두 선이 apex 봉에서 만나는 삼각형 안을 period 봉 주기로 오가는 합성 봉."""
    meet = {"sym": (top0 + bot0) / 2, "asc": top0, "desc": bot0}[kind]
    rows = []
    for t in range(n):
        hi = top0 + (meet - top0) * t / apex
        lo = bot0 + (meet - bot0) * t / apex
        w = hi - lo
        ph = (t % period) / period
        frac = 1 - abs(2 * ph - 1)
        mid = lo + w * (0.05 + 0.9 * frac)
        h = min(mid + 0.04 * w, hi)
        l = max(mid - 0.04 * w, lo)
        rows.append(dict(ts=t0 + t * step, o=mid, h=h, l=l, c=mid, v=100.0))
    return rows


TRI = dict(cw.load_cfg()["triangle"])

print("[17] 삼각수렴 맞춤")
for kind, want in (("sym", "tri_sym"), ("asc", "tri_asc"), ("desc", "tri_desc")):
    rows = bars_triangle(kind=kind)
    tr = cw.fit_triangle(rows, 20, TRI)
    check(f"합성 {kind} 삼각형을 찾는다", tr is not None)
    if tr:
        check(f"{kind}: 모양 분류 {want}", tr["kind"] == want)
        check(f"{kind}: 꼭짓점은 마지막 봉보다 앞쪽(아직 수렴 중)", tr["apex"] > len(rows) - 1)
        check(f"{kind}: 위 선 기울기 < 아래 선 기울기(수렴)", tr["hi_slope"] < tr["lo_slope"])
        check(f"{kind}: 기준점 고-저가 엇갈린다", max(tr["h1"], tr["l1"]) < min(tr["h2"], tr["l2"]))
        check(f"{kind}: 진행도 0.25~0.9", TRI["min_progress"] <= tr["prog"] <= TRI["max_progress"])
        lo_e, hi_e = cw.lines_at(tr, len(rows) - 1)
        check(f"{kind}: 마지막 봉 종가가 두 선 사이", lo_e <= rows[-1]["c"] <= hi_e)

print("[18] 삼각수렴 이탈")
rows = bars_triangle(kind="sym")
tr = cw.fit_triangle(rows, 20, TRI)
t = len(rows)
lo_v, hi_v = cw.lines_at(tr, t)
w = hi_v - lo_v
buf = max(TRI["break_buffer"] * w, TRI["break_atr"] * tr["atr"])
up_bar = dict(ts=rows[-1]["ts"] + H, o=hi_v, h=hi_v + buf + 1, l=hi_v, c=hi_v + buf + 0.5, v=100.0)
dn_bar = dict(ts=rows[-1]["ts"] + H, o=lo_v, h=lo_v, l=lo_v - buf - 1, c=lo_v - buf - 0.5, v=100.0)
in_bar = dict(ts=rows[-1]["ts"] + H, o=hi_v, h=hi_v + 0.5 * buf, l=hi_v, c=hi_v + 0.5 * buf, v=100.0)
check("위로 돌파", cw.check_break_tri(tr, up_bar, t, TRI)[0] == "up")
check("아래로 이탈", cw.check_break_tri(tr, dn_bar, t, TRI)[0] == "down")
check("버퍼 안(선을 조금 넘음)은 이탈 아님", cw.check_break_tri(tr, in_bar, t, TRI)[0] is None)
check("이탈 기준은 그 봉 폭 비율과 ATR 하한 중 큰 값",
      abs(buf - max(TRI["break_buffer"] * w, TRI["break_atr"] * tr["atr"])) < 1e-9 and TRI["break_atr"] > 0)
far = int(tr["apex"]) + 5
check("꼭짓점을 지나면 삼각형이 끝났다 — 이탈로 보지 않는다",
      cw.check_break_tri(tr, dict(up_bar, c=1e9), far, TRI)[0] is None)
try:
    cw.fit_triangle(rows, 20, TRI, piv_fn=lambda r: ([10, 10, 34, 58], [22, 22, 46, 70]))
    _zero_ok = True
except ZeroDivisionError:
    _zero_ok = False
check("같은 봉을 두 번 낸 피벗도 0 나누기 없이 넘어간다", _zero_ok)

print("[19] 삼각수렴이 아닌 것")
check("평행 채널은 삼각수렴이 아니다", cw.fit_triangle(bars_channel(110), 20, TRI) is None)
flat_box = bars_channel(110, slope=0.0)
check("수평 박스는 삼각수렴이 아니다", cw.fit_triangle(flat_box, 20, TRI) is None)


def bars_wedge(n=110, period=12):
    """둘 다 오르는 선(아래가 더 가파름) — 상승 쐐기형."""
    rows = []
    for t in range(n):
        hi = 120.0 + 0.10 * t
        lo = 100.0 + 0.20 * t
        w = hi - lo
        ph = (t % period) / period
        frac = 1 - abs(2 * ph - 1)
        mid = lo + w * (0.05 + 0.9 * frac)
        rows.append(dict(ts=1_700_000_000_000 + t * H, o=mid, h=min(mid + 0.04 * w, hi),
                         l=max(mid - 0.04 * w, lo), c=mid, v=100.0))
    return rows


check("쐐기형(두 선이 같은 쪽으로 기움)은 뺀다", cw.fit_triangle(bars_wedge(), 20, TRI) is None)
seq = bars_triangle(kind="sym")
hp, lp = cw.pivot_fn_of(TRI)(seq)
bad = cw.fit_triangle(seq, 20, TRI, piv_fn=lambda r: (hp[:2], lp[-2:]))
check("고점 둘이 모두 저점 둘보다 앞이면(엇갈리지 않음) 삼각형으로 보지 않는다", bad is None)

print("[20] 삼각수렴 실행")
tri_rows = bars_triangle(kind="sym")
tr0 = cw.fit_triangle(tri_rows, 20, TRI)
lo_n, hi_n = cw.lines_at(tr0, len(tri_rows))
wn = hi_n - lo_n
bufn = max(TRI["break_buffer"] * wn, TRI["break_atr"] * tr0["atr"])
pxn = hi_n + bufn + 0.5
tri_brk = tri_rows + [dict(ts=tri_rows[-1]["ts"] + H, o=pxn, h=pxn + 0.1, l=pxn - 0.1, c=pxn, v=300.0)]
calls = []


def fake_tri(sym, tf, limit):
    calls.append((sym, tf, limit))
    return tri_brk


TRIP = dict(TRI, watch=[{"symbol": "BTC", "tfs": ["1h"]}],
            params={"1h": {"lookback": 168, "min_span": 20, "recheck_bars": 3}})
cw.load_cfg = lambda path=None: dict(CFG, watch=[{"symbol": "ETH", "tfs": ["1h"]}], channel=CH,
                                      params={"1h": {"lookback": 100, "pivot_k": 3, "min_span": 20,
                                                     "recheck_bars": 3}}, summary_hour_utc=99,
                                      triangle=TRIP)
stt = PStore()
nowt = tri_brk[-1]["ts"] + H + 60_000
cw.run([], now_ms=nowt, fetch=fake_tri, store=stt, send=False)
tri_rec = [r for r in stt.rows if r["anchor"] == "triangle"]
check("삼각수렴 이탈 1건 기록", len(tri_rec) == 1 and tri_rec[0]["side"] == "up")
check("삼각수렴은 설정 종목(BTC)만 — 다른 종목엔 삼각수렴을 안 본다",
      all(r["symbol"] == "BTC" for r in tri_rec))
check("기록 kind 는 tri_*, width 는 그 봉의 남은 폭",
      tri_rec and tri_rec[0]["kind"].startswith("tri_") and
      abs(tri_rec[0]["width"] - (tri_rec[0]["upper"] - tri_rec[0]["lower"])) < 1e-9)
check("중복 방지 키에 삼각형 표식과 기준점 넷", tri_rec and tri_rec[0]["alert_key"].count("|") == 7
      and "|tri|" in tri_rec[0]["alert_key"])
check("종목·시간대마다 한 번만 받는다(더 긴 창 기준)",
      sorted(calls) == [("BTC", "1h", 228), ("ETH", "1h", 160)])
cw.run([], now_ms=nowt + H, fetch=fake_tri, store=stt, send=False)
check("같은 삼각형 이탈은 다음 실행에서 다시 기록하지 않는다",
      len([r for r in stt.rows if r["anchor"] == "triangle"]) == 1)
cw.load_cfg = orig_load

print("[21] 삼각수렴 설정")
tcfg = orig_load()["triangle"]
check("삼각수렴은 BTC 만", [w["symbol"] for w in tcfg["watch"]] == ["BTC"])
check("1시간봉 이상만", all(tf in ("1h", "4h", "1d") for w in tcfg["watch"] for tf in w["tfs"]))
check("watch 시간대마다 params", all(tf in tcfg["params"] for w in tcfg["watch"] for tf in w["tfs"]))
check("받는 봉 수가 OKX 한 번 한도(300) 안", all(v["lookback"] + 60 <= 300 for v in tcfg["params"].values()))
check("종가 유지 한도 = 이탈 기준(얕은 종가 이탈로 삼각형이 알림 없이 사라지지 않게)",
      tcfg["contain_close_tol"] == tcfg["break_buffer"] and tcfg["contain_close_atr"] == tcfg["break_atr"])
check("이탈 기준 남은 폭 35%·0.7ATR 이상(가짜 이탈 22.7%→15.0% 실측)",
      tcfg["break_buffer"] >= 0.35 and tcfg["break_atr"] >= 0.7)
check("근거 문구가 설정에 남아 있다", "가짜 이탈" in tcfg.get("design_evidence", "")
      and "매매 신호 아님" in tcfg.get("history_note", ""))
check("피벗은 채널과 같은 ATR 지그재그", tcfg["pivot_method"] == "zigzag_atr")

print("[22] 삼각수렴 표기")
evt = dict(pattern="triangle", symbol="BTC", tf="4h", side="down", depth=0.4,
           bar=dict(ts=tri_rows[-1]["ts"], c=99.0), chn=tr0, upper=112.0, lower=108.0, vol_ratio=2.1)
tt_ = cw.alert_text_tri(evt, tcfg["history_note"])
check("알림에 종목·시간대·삼각수렴·아래로 이탈", "BTC 4h 삼각수렴 아래로 이탈" in tt_)
check("알림에 모양·꼭짓점 진행·남은 폭", "대칭 삼각형" in tt_ and "꼭짓점까지" in tt_ and "남은 폭" in tt_)
check("알림에 '매매 신호 아님'과 과거 기준", "매매 신호 아님" in tt_ and "15%" in tt_)
check("요약: 없음", "삼각수렴 없음" in cw.summary_line_tri("BTC", "1h", dict(chn=None, bar=dict(c=70000.0))))
sline = cw.summary_line_tri("BTC", "4h", dict(chn=tr0, bar=dict(c=110.0), lower=105.0, upper=115.0,
                                              pos=0.5, side=None, bars_to_apex=12.4))
check("요약: 모양·범위·꼭짓점", "△ BTC 4h" in sline and "대칭 삼각형" in sline and "약 12봉" in sline)
check("문구의 모양 이름이 셋 다 있다", set(cw.TRI_KO) == {"tri_sym", "tri_asc", "tri_desc"})

print("[23] 앨범 — 10장씩")
sent_calls = []
orig_tg, orig_av = cw._tg, cw.tg_available
cw._tg = lambda method, data=None, files=None: sent_calls.append((method, len(files or {}))) or True
cw.tg_available = lambda: True
os.environ.setdefault("TELEGRAM_CHAT_ID", "0")
cw.tg_album([(b"png", f"c{i}") for i in range(13)])
check("13장 → 10장 앨범 + 3장 앨범", sent_calls == [("sendMediaGroup", 10), ("sendMediaGroup", 3)])
sent_calls.clear()
cw.tg_album([(b"png", f"c{i}") for i in range(11)])
check("11장 → 10장 앨범 + 사진 1장(앨범은 2장 이상)", sent_calls == [("sendMediaGroup", 10), ("sendPhoto", 1)])
cw._tg, cw.tg_available = orig_tg, orig_av

print("[12] SQL")
SQL = open(os.path.join(HERE, "supabase_schema_channel_alerts.sql"), encoding="utf-8").read().lower()
check("RLS 켜기", "enable row level security" in SQL)
check("anon·authenticated 권한 회수", "revoke all on public.channel_alerts from anon, authenticated" in SQL)
check("anon 에 쓰기 권한을 주지 않는다", not re.search(r"grant[^;]*to\s+anon", SQL))
check("alert_key 유니크", re.search(r"alert_key\s+text\s+not null unique", SQL) is not None)
check("기록 컬럼이 코드와 일치", all(k in SQL for k in cw.alert_row(dict(
    symbol="X", tf="1h", side="up", bar=dict(ts=0, c=1.0), upper=1.0, lower=0.0, depth=0.1,
    key="k", chn=dict(width=1.0, kind="up", anchor="low", start_ts=0, span=1,
                      touches_lo=[1, 2], touches_hi=[3, 4])), True)))

print()
if FAIL:
    print(f"실패 {len(FAIL)}건: " + " | ".join(FAIL))
    sys.exit(1)
print("전부 통과")
