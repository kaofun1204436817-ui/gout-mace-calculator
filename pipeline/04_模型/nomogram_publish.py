# -*- coding: utf-8 -*-
"""
可临床使用的评分式列线图 v2
- 基于 MIMIC 主队列 strict 6-event MACE
- 10 个临床可得变量, 每变量按风险方向生成 0-100 分值刻度
- 总评分由全部训练样本计算, 再拟合 logistic(total_score)->risk
- 输出 Fig6_nomogram.tiff/png
"""
import os, warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.linear_model import LogisticRegression
import statsmodels.api as sm

warnings.filterwarnings("ignore")
BASE = r"D:/WorkBuddy/专家团 1/04_模型"
FIG = r"D:/WorkBuddy/专家团 1/05_图表/figures"
os.makedirs(FIG, exist_ok=True)
plt.rcParams.update({"font.family":"Arial","font.size":10})

mimic = pd.read_csv(os.path.join(BASE, "data/mimic_model_data.csv"))
y = mimic["mace"].astype(int).values
COLS = ["anchor_age","gcs_total","bun","rr_mean","chloride","hemoglobin","wbc",
        "sbp_mean","creatinine","med_p2y12","med_diuretic","med_betablocker"]
COLS = [c for c in COLS if c in mimic.columns]
X = mimic[COLS].copy()
for c in X.columns:
    if c == "gender":
        X[c] = X[c].map({"M":1,"F":0})
    X[c] = pd.to_numeric(X[c], errors="coerce")
X = X.fillna(X.median())
# 原始尺度 logistic (避免标准化使列线图数值失真)
lr = LogisticRegression(max_iter=3000, C=0.5, class_weight="balanced", random_state=42)
lr.fit(X, y)
beta = lr.coef_[0]

# 每变量范围 (5th-95th pct)
ranges = {}
for i, c in enumerate(COLS):
    lo, hi = X[c].quantile([0.05, 0.95])
    if lo == hi: hi = lo + 1e-9
    ranges[c] = (lo, hi)

def points_for(row):
    pts = {}
    for c in COLS:
        lo, hi = ranges[c]
        if beta[COLS.index(c)] >= 0:
            p = np.clip((row[c] - lo) / (hi - lo), 0, 1) * 100
        else:
            p = np.clip((hi - row[c]) / (hi - lo), 0, 1) * 100
        pts[c] = p
    return pts

pts_df = pd.DataFrame([points_for(r) for _, r in X.iterrows()])
total = pts_df.sum(axis=1).values

# 用 total score 校准风险轴
exog = sm.add_constant(total)
m = sm.Logit(y, exog).fit(disp=False)
b0, b1 = float(m.params[0]), float(m.params[1])
def risk_from_total(t):
    return 1 / (1 + np.exp(-(b0 + b1 * t)))
score_axis_lo = min(total.min(), 0)
score_axis_hi = max(total.max(), 100)
risk_lo = float(risk_from_total(score_axis_lo))
risk_hi = float(risk_from_total(score_axis_hi))

# ---- 绘图 ----
fig, ax = plt.subplots(figsize=(11, 7.5))
ax.set_xlim(0, 10); ax.set_ylim(0, 10); ax.axis("off")

# top: Points
top_y = 9.62
ax.text(0.05, top_y, "Points", fontsize=11, fontweight="bold", va="center")
for k in range(11):
    xp = 0.55 + k/10 * 8.9
    ax.plot([xp, xp], [top_y-0.10, top_y+0.06], color="black", lw=0.9)
    ax.text(xp, top_y-0.30, str(k*10), ha="center", fontsize=8.5)
ax.plot([0.55, 9.45], [top_y, top_y], color="black", lw=1.6)

nrow = len(COLS)
row_gap = 0.47
y0 = top_y - 0.95
for idx, c in enumerate(COLS):
    yc = y0 - idx * row_gap
    lo, hi = ranges[c]
    ax.text(0.04, yc, c, ha="right", va="center", fontsize=9.5, fontweight="bold")
    # line with tick labels at 0, 25, 50, 75, 100 points
    for pv in [0, 25, 50, 75, 100]:
        xp = 0.55 + pv/100 * 8.9
        ax.plot([xp, xp], [yc-0.08, yc+0.08], color="black", lw=0.9)
        if beta[COLS.index(c)] >= 0:
            raw_v = lo + (hi - lo) * pv/100
        else:
            raw_v = hi - (hi - lo) * pv/100
        if idx < len(COLS)-1:
            fmt = "%d" if abs(raw_v) >= 10 else "%.1f"
            lbl = fmt % raw_v
        else:
            lbl = "Yes" if pv >= 50 else "No"
        ax.text(xp, yc-0.27, lbl, ha="center", fontsize=8)
    ax.plot([0.55, 9.45], [yc, yc], color="black", lw=1.3)

# Total Points
yt = y0 - len(COLS)*row_gap - 0.05
ax.text(0.04, yt, "Total points", ha="right", va="center", fontsize=10, fontweight="bold")
for k in range(0, 121, 10):
    xp = 0.55 + k/120 * 8.9
    ax.plot([xp, xp], [yt-0.08, yt+0.08], color="black", lw=0.9)
    ax.text(xp, yt-0.27, str(int(k)), ha="center", fontsize=8)
ax.plot([0.55, 9.45], [yt, yt], color="black", lw=1.6)

# Risk Axis
yr = yt - 0.95
ax.text(0.04, yr, "Probability of\nMACE", ha="right", va="center", fontsize=9.5, fontweight="bold")
risk_ticks = [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50, 0.60, 0.70, 0.80]
for p_ in risk_ticks:
    t_ = (np.log(p_/(1-p_)) - b0) / b1 if b1 != 0 else 0
    t_ = np.clip(t_, score_axis_lo, score_axis_hi)
    xp = 0.55 + (t_ - score_axis_lo)/(score_axis_hi - score_axis_lo) * 8.9
    ax.plot([xp, xp], [yr-0.10, yr+0.10], color="black", lw=0.9)
    ax.text(xp, yr-0.28, f"{p_:.2f}", ha="center", fontsize=8.5)
ax.plot([0.55, 9.45], [yr, yr], color="black", lw=1.6)

ax.set_title("Bedside risk score for in-hospital MACE (strict 6-event outcome, MIMIC-IV derivation)",
             fontsize=12, fontweight="bold", y=0.985)
plt.tight_layout()
fig.savefig(os.path.join(FIG, "Fig6_nomogram.tiff"), dpi=300, bbox_inches="tight",
            pil_kwargs={"compression":"tiff_lzw"})
fig.savefig(os.path.join(FIG, "Fig6_nomogram.png"), dpi=300, bbox_inches="tight")
# 保存评分映射参数
pd.DataFrame({"var":COLS, "beta_raw":beta, "range_lo":[ranges[c][0] for c in COLS],
              "range_hi":[ranges[c][1] for c in COLS]}).to_csv(
    os.path.join(FIG, "nomogram_scoring.csv"), index=False)
json_out = {"calibration_const": float(b0), "calibration_score_coef": float(b1),
            "score_min": float(score_axis_lo), "score_max": float(score_axis_hi)}
import json
json.dump(json_out, open(os.path.join(FIG, "nomogram_calibration.json"), "w"), indent=2)
print("saved Fig6_nomogram", json_out)
plt.close(fig)