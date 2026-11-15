"""test_halt_shadow.py — R-114 동결·판정·미해소 제외 (합성, 네트워크 없음)"""
import numpy as np
import validate_halt_shadow as V

ok = fail = 0
def chk(n, c, x=""):
    global ok, fail
    if c: ok += 1
    else: fail += 1; print("  FAIL", n, x)

O = __import__("datetime").date(2026, 11, 10).toordinal()
def rec(p, ret, d=0, hold=1.0):
    return dict(pattern=p, ret=ret, t_in=float(O + d), t_out=float(O + d + hold))
def row(p, r, d, dirn="long"):
    return dict(method="D", live_mode=True, return_pct=r, entry_date=d, pattern=p, direction=dirn)

chk("동결", (V.SHADOW_FROM, V.MIN_REF_N, V.MIN_POST, V.ALPHA, V.DEPLOY_ON_PASS) == ("2026-11-09", 10, 30, 0.05, False))
chk("unit", V.unit_of("fvg_short") == ("fvg", "short") and V.unit_of("fvg") == ("fvg", "long"))
recs = [rec("fvg", 0.05, 0, 1.0), rec("fvg", 0.02, -3, 1.0),            # 정지 전 진입 제외
        rec("fvg", 0.01, 0, 9.0), rec("fvg_short", -0.08, 1, 1.0)]       # 마지막은 데이터 끝(t_out 최대)
recs[2]["t_out"] = float(O + 9)                                          # 가장 늦은 t_out = 데이터 끝 → 미해소 제외
s = V.shadow_units(recs)
chk("정지 전·미해소 제외", s == {"fvg|long": [5.0], "fvg|short": [-8.0]}, s)
chk("분수→%", abs(s["fvg|long"][0] - 5.0) < 1e-9)
rs = np.random.default_rng(1)
ref = V.ref_units([row("a", float(x), "2026-10-01") for x in rs.normal(0, 5, 40)] + [row("a", 9.0, "2026-11-09")])
chk("기준 풀은 정지 전만", len(ref["a|long"]) == 40)
inn = {"a|long": [float(x) for x in rs.normal(0, 5, 35)]}
chk("분포 안", V.judge(ref, inn, boot=2000)["verdict"] == "WITHIN_DISTRIBUTION")
out = {"a|long": [-30.0] * 35}
r = V.judge(ref, out, boot=2000); chk("분포 밖", r["verdict"] == "REGIME_CHANGE_CANDIDATE" and r["pooled_pct"] < 0.05, r)
chk("n<30", V.judge(ref, {"a|long": [-30.0] * 29}, boot=500)["verdict"] == "INCONCLUSIVE")
chk("기준 n<10 제외", V.judge({"a|long": [1.0] * 5}, out, boot=500)["units"] == [])
chk("결정성", V.judge(ref, inn, boot=500)["pooled_pct"] == V.judge(ref, inn, boot=500)["pooled_pct"])
print(f"{ok} passed, {fail} failed")
raise SystemExit(1 if fail else 0)
