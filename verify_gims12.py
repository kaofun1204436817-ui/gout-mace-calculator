# -*- coding: utf-8 -*-
"""
verify_gims12.py — 一键校验 GIMS-12 发布件的一致性

检查四件事：
  1. gims12_model.py 的系数与 gims12_fit.json 完全一致
  2. gims12_model.py 的预测与 JSON 中 β 直接计算完全一致
  3. gims12_calculator.html 内嵌的 JS 系数与 gims12_model.py 完全一致
  4. gims12_points_table.csv 覆盖全部 12 个变量且分值单调正确

用法：python verify_gims12.py
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

FAILS = []


def check(name, ok, detail=""):
    print(("  PASS  " if ok else "  FAIL  ") + name + ("  " + detail if detail else ""))
    if not ok:
        FAILS.append(name)


print("=" * 68)
print("GIMS-12 发布件一致性校验")
print("=" * 68)

# ---------------------------------------------------------------- 1
print("\n[1] gims12_model.py 与 gims12_fit.json")
fit_path = os.path.join(HERE, "gims12_fit.json")
if not os.path.exists(fit_path):
    print("  未找到 gims12_fit.json")
    sys.exit(1)
F = json.load(open(fit_path, encoding="utf-8"))
import gims12_model as G  # noqa: E402

check("截距一致", abs(G.INTERCEPT - F["intercept_raw"]) < 1e-12,
      f"{G.INTERCEPT} vs {F['intercept_raw']}")

bad = []
for c, b, md in zip(F["features"], F["beta_raw"], F["medians"]):
    gb, gmd = G.FEATURES[c][0], G.FEATURES[c][1]
    if abs(gb - b) > 1e-12:
        bad.append(f"{c} beta")
    if abs(gmd - md) > 1e-9:
        bad.append(f"{c} median")
check("12 个 β 与中位数一致", not bad, ", ".join(bad))

check("变量顺序一致", G.ORDER == F["features"])

cb = F.get("clip_bounds") or {}
if cb:
    bad_clip = []
    for c in G.ORDER:
        lo, hi = G.CLIP_BOUNDS[c]
        if abs(lo - cb["lower"][c]) > 1e-6 or abs(hi - cb["upper"][c]) > 1e-6:
            bad_clip.append(c)
    check("12 个截断边界与 JSON 一致", not bad_clip, ", ".join(bad_clip))
else:
    check("JSON 含 clip_bounds", False, "缺少 clip_bounds")
check("重校准斜率/截距一致",
      abs(G.RECAL_SLOPE - F["external_recalibration"]["slope"]) < 1e-9 and
      abs(G.RECAL_INTERCEPT - F["external_recalibration"]["intercept"]) < 1e-9)

# ---------------------------------------------------------------- 2
print("\n[2] 预测值与 β 直接计算")
import math  # noqa: E402

B = dict(zip(F["features"], F["beta_raw"]))
IR = F["intercept_raw"]
CASES = [
    dict(zip(G.ORDER, [72, 13, 117, 18.5, 96.8, 24, 1.2, 10.7, 175, 10.5, 8.5, 105])),
    dict(zip(G.ORDER, [88, 5, 72, 30, 88, 85, 4.5, 8, 60, 25, 7, 112])),
    dict(zip(G.ORDER, [45, 15, 140, 14, 99, 10, 0.8, 15, 280, 7, 9.8, 104])),
]
max_d = 0.0
for d in CASES:
    # 参考值同样应用截断，与 predict() 的默认行为保持一致
    dc = {k: min(max(d[k], G.CLIP_BOUNDS[k][0]), G.CLIP_BOUNDS[k][1]) for k in G.ORDER}
    lp = IR + sum(B[k] * dc[k] for k in G.ORDER)
    ref = 1 / (1 + math.exp(-lp))
    max_d = max(max_d, abs(ref - G.predict(d)))
check("3 个病例偏差 < 1e-12", max_d < 1e-12, f"max |Δp| = {max_d:.2e}")

# 截断行为：极端输入必须被夹到边界，且概率有上限
extreme = {k: 1e6 for k in G.ORDER}
_, hit = G.clip_values(extreme)
check("极端输入触发 12 个变量全部截断", len(hit) == 12, f"{len(hit)}/12")
p_ext = G.predict(extreme)
check("极端输入概率未被推到 100%", p_ext < 0.999, f"{p_ext * 100:.2f}%")
mid = {k: (G.CLIP_BOUNDS[k][0] + G.CLIP_BOUNDS[k][1]) / 2 for k in G.ORDER}
_, hit2 = G.clip_values(mid)
check("区间中点不触发截断", len(hit2) == 0, f"{len(hit2)} 个")

# ---------------------------------------------------------------- 3
print("\n[3] gims12_calculator.html 内嵌 JS 系数")
html_path = os.path.join(HERE, "gims12_calculator.html")
html = open(html_path, encoding="utf-8").read()
m = re.search(r"const INTERCEPT = ([0-9.eE+-]+);", html)
check("找到 JS 截距", m is not None)
if m:
    check("JS 截距与 Python 一致", abs(float(m.group(1)) - G.INTERCEPT) < 1e-12,
          f"{m.group(1)}")

js_beta = dict(re.findall(r"(\w+):\s*\{beta:\s*([0-9.eE+-]+)", html))
check("JS 变量数 = 12", len(js_beta) == 12, f"实际 {len(js_beta)}")
mismatch = [k for k, v in js_beta.items()
            if k not in G.FEATURES or abs(float(v) - G.FEATURES[k][0]) > 1e-12]
check("JS β 全部一致", not mismatch, ", ".join(mismatch))

missing = [k for k in G.ORDER if k not in js_beta]
check("JS 覆盖全部变量", not missing, ", ".join(missing))

# ---------------------------------------------------------------- 4
print("\n[4] gims12_points_table.csv")
import csv  # noqa: E402

rows = list(csv.DictReader(open(os.path.join(HERE, "gims12_points_table.csv"), encoding="utf-8")))
vars_in = sorted({r["variable"] for r in rows})
check("覆盖 12 个变量", vars_in == sorted(G.ORDER), f"{len(vars_in)} 个")
check("行数 = 195", len(rows) == 195, f"实际 {len(rows)}")

mono_bad = []
for v in G.ORDER:
    sub = sorted([r for r in rows if r["variable"] == v], key=lambda r: float(r["value"]))
    pts = [float(r["points"]) for r in sub]
    want_up = G.FEATURES[v][0] > 0          # β>0 时分值随取值上升
    for i in range(1, len(pts)):
        d = pts[i] - pts[i - 1]
        if (want_up and d < -1e-9) or (not want_up and d > 1e-9):
            mono_bad.append(v)
            break
check("分值方向与 β 符号一致（12 个变量）", not mono_bad, ", ".join(sorted(set(mono_bad))))

# ---------------------------------------------------------------- 汇总
print("\n" + "=" * 68)
if FAILS:
    print(f"结果：{len(FAILS)} 项 FAIL")
    for f in FAILS:
        print("   -", f)
    sys.exit(1)
print("结果：全部 PASS")
print("=" * 68)
