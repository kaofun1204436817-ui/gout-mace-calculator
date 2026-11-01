# -*- coding: utf-8 -*-
"""Fig6 列线图：行距拉开、概率刻度精简、标签右对齐留足间距"""
import sys; sys.path.insert(0, r"D:/WorkBuddy/专家团 1/_工具")
from rebuild_all_figs import *

sc = pd.read_csv(f"{FIG}/nomogram_scoring.csv")
cal = json.load(open(f"{FIG}/nomogram_calibration.json", encoding="utf-8"))
C0, C1, SMAX = cal["calibration_const"], cal["calibration_score_coef"], cal["calibration_score_max"] if "calibration_score_max" in cal else cal["score_max"]

sc["impact"] = sc["beta_raw"].abs()*(sc["range_hi"]-sc["range_lo"])
sc["pts"] = sc["impact"]/sc["impact"].sum()*100
sc = sc.sort_values("pts", ascending=False).reset_index(drop=True)

LAB = {"anchor_age":"Age (years)","gcs_total":"GCS total","bun":"BUN (mg/dL)",
       "rr_mean":"Respiratory rate (/min)","chloride":"Chloride (mmol/L)","hemoglobin":"Hemoglobin (g/dL)",
       "wbc":"WBC (×10⁹/L)","sbp_mean":"Systolic BP (mmHg)","creatinine":"Creatinine (mg/dL)",
       "med_p2y12":"P2Y12 inhibitor","med_diuretic":"Diuretic use","med_betablocker":"Beta-blocker use"}
BIN = {"med_p2y12":["No","Yes"],"med_diuretic":["No","Yes"],"med_betablocker":["No","Yes"]}

n = len(sc)
ROW = 1.0
fig = plt.figure(figsize=(7.13, 6.4))
ax = fig.add_axes([0.34, 0.04, 0.62, 0.90])
ax.set_xlim(-1, 102); ax.set_ylim(-3.6, n+2.2)
ax.axis("off")
ax.set_xticks([]); ax.set_yticks([])

def ticks(x0, x1, labels, y, fs, off):
    for frac, lab in labels:
        xx = x0 + frac*(x1-x0)
        ax.plot([xx,xx],[y, y+0.11], color="black", lw=0.8)
        ax.text(xx, y-off, lab, ha="center", va="top", fontsize=fs)

# 顶部 Points 轴
yt = n + 1.35
ax.plot([0,100],[yt,yt], color="black", lw=1.0)
for p in range(0,101,10):
    ax.plot([p,p],[yt,yt-0.12], color="black", lw=0.8)
    ax.text(p, yt+0.14, str(p), ha="center", va="bottom", fontsize=6.2)
ax.text(-3.0, yt+0.14, "Points", ha="right", va="bottom", fontsize=7.4, fontweight="bold")

# 轴长严格 = 点数，保证"比长度=比贡献"的列线图语义正确
for i, r in sc.iterrows():
    y = n - 1 - i*ROW
    ax.text(-3.0, y, LAB.get(r["var"], r["var"]), ha="right", va="center", fontsize=6.6)
    x1 = r["pts"]
    ax.plot([0,x1],[y,y], color="black", lw=0.9)
    if r["var"] in BIN:
        for xx, lab in zip([0,x1], BIN[r["var"]]):
            ax.plot([xx,xx],[y,y+0.11], color="black", lw=0.8)
            ax.text(xx, y-0.20, lab, ha="center", va="top", fontsize=6.0)
    else:
        if r["pts"] < 7:
            # 极短轴：只标范围文本（左对齐），避免两端刻度相撞
            ax.plot([0,x1],[y,y], color="black", lw=0.9)
            ax.text(x1+1.2, y, f"{r['range_lo']:.1f}–{r['range_hi']:.0f}",
                    ha="left", va="center", fontsize=5.8, color="#333333")
        else:
            fr = [0,1.0] if r["pts"] < 26 else [0,0.5,1.0]
            for f0 in fr:
                xx = f0*x1
                v = r["range_lo"] + f0*(r["range_hi"]-r["range_lo"])
                ax.plot([xx,xx],[y,y+0.11], color="black", lw=0.8)
                ax.text(xx, y-0.20, f"{v:.1f}" if abs(v)<30 else f"{v:.0f}",
                        ha="center", va="top", fontsize=6.0)

# Total points 轴
y_tp = -1.35
ax.plot([0,100],[y_tp,y_tp], color="black", lw=1.0)
for p in range(0,101,10):
    ax.plot([p,p],[y_tp,y_tp-0.12], color="black", lw=0.8)
    ax.text(p, y_tp-0.24, str(p), ha="center", va="top", fontsize=6.2)
ax.text(-3.0, y_tp, "Total points", ha="right", va="center", fontsize=7.4, fontweight="bold")

# 概率轴（精简为 7 个刻度）
y_p = -2.65
ax.plot([0,100],[y_p,y_p], color="black", lw=1.0)
for pv in [0.05,0.10,0.20,0.40,0.60,0.80,0.90]:
    lp = np.log(pv/(1-pv)); pts = ((lp-C0)/C1)/SMAX*100
    if 0 <= pts <= 100:
        ax.plot([pts,pts],[y_p,y_p-0.12], color="black", lw=0.8)
        ax.text(pts, y_p-0.24, f"{pv:.2f}", ha="center", va="top", fontsize=6.2)
ax.text(-3.0, y_p, "Probability\nof MACE", ha="right", va="center", fontsize=7.0,
        fontweight="bold", linespacing=1.35)

fig.text(0.5, 0.975, "Bedside risk score for in-hospital MACE (12-predictor logistic score, MIMIC-IV)",
         ha="center", fontsize=8.4, fontweight="bold")
save(fig, "Fig6_nomogram", "Fig6 列线图")
