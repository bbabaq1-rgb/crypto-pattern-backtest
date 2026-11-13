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
                                                     "recheck_bars": 3}}, summary_hour_utc=99)
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
check("알림에 '검증된 매매 신호가 아님'", "검증된 매매 신호가 아님" in txt)
check("거래량 배수 표기", "1.8배" in txt)
check("채널 없음 요약", "채널 아직 없음" in cw.summary_line("ETH", "1h", dict(chn=None, bar=dict(c=2000.0))))
lb = dict(side="down", upper=2100.0, lower=2050.0, bar=dict(ts=1_700_000_000_000, c=2000.0))
check("채널 없을 때 직전 이탈 표기", "하단 이탈" in cw.summary_line("ETH", "1h", dict(chn=None, bar=dict(c=2000.0), last_break=lb)) and "2,050 아래" in cw.summary_line("ETH", "1h", dict(chn=None, bar=dict(c=2000.0), last_break=lb)))
check("가격 표기", cw.fmt_px(71234.5) == "71,234" and cw.fmt_px(1.2345) == "1.23")

print("[11] 설정 파일")
cfg = orig_load()
check("watch 의 모든 시간대에 params 가 있다", all(tf in cfg["params"] for w in cfg["watch"] for tf in w["tfs"]))
check("모든 시간대가 TF_MS 에 있다", all(tf in cw.TF_MS for tf in cfg["params"]))
check("채널 설정 키", {"touch_tol", "contain_tol", "break_buffer", "min_touches_each", "min_width_atr",
                    "touch_atr", "max_width_range", "recent_pivots"} <= set(cfg["channel"]))
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
