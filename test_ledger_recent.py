"""test_ledger_recent.py — R-105 동결·판정 (합성, 네트워크 없음)"""
import numpy as np
import validate_ledger_recent as V

ok = fail = 0
def chk(n, c, x=""):
    global ok, fail
    if c: ok += 1
    else: fail += 1; print("  FAIL", n, x)

def row(p, r, d):
    return dict(method="D", live_mode=True, return_pct=r, entry_date=d, pattern=p, direction="long")

chk("동결", (V.POST_FROM, V.MIN_REF_N, V.MIN_POST, V.ALPHA, V.DEPLOY_ON_PASS) == ("2026-11-04", 10, 10, 0.05, False))
rs = np.random.default_rng(3)
ref = [row("a", float(x), "2026-10-01") for x in rs.normal(0, 5, 40)]
# 분포 안
inn = [row("a", float(x), "2026-11-05") for x in rs.normal(0, 5, 12)]
r, p = V.split(ref + inn); res = V.judge(r, p, boot=2000)
chk("분포 안 → WITHIN", res["verdict"] == "WITHIN_DISTRIBUTION", res)
# 분포 밖(전부 -30)
out = [row("a", -30.0, "2026-11-05") for _ in range(12)]
r, p = V.split(ref + out); res = V.judge(r, p, boot=2000)
chk("분포 밖 → REGIME", res["verdict"] == "REGIME_CHANGE_CANDIDATE" and res["pooled_pct"] < 0.05, res)
# 표본 부족
r, p = V.split(ref + out[:3]); res = V.judge(r, p, boot=500)
chk("n<10 → INCONCLUSIVE", res["verdict"] == "INCONCLUSIVE")
# 기준 풀 미달 단위 제외
r, p = V.split(ref[:5] + out); res = V.judge(r, p, boot=500)
chk("기준 n<10 제외", res["units"] == [] and "a|long" in res["skipped_post_units"])
# 경계: 11-04 당일은 최근
r, p = V.split([row("a", 1.0, "2026-11-04"), row("a", 2.0, "2026-11-03")])
chk("경계 당일=최근", len(p["a|long"]) == 1 and len(r["a|long"]) == 1)
# 비실거래·비D 제외
bad = dict(row("a", 1.0, "2026-11-05"), method="A")
r, p = V.split([bad]); chk("비D 제외", not p)
# 결정성
r, p = V.split(ref + inn)
chk("시드 결정성", V.judge(r, p, boot=500)["pooled_pct"] == V.judge(r, p, boot=500)["pooled_pct"])
print(f"{ok} passed, {fail} failed")
raise SystemExit(1 if fail else 0)
