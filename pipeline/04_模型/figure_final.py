# -*- coding: utf-8 -*-
"""
论文级图表生成 (EJMR 当前靶刊) — 300dpi, 双库 A/B 并列式, 统一视觉
产出: 05_图表/figures/*.tiff + *.png
"""
import os, json, warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from sklearn.metrics import roc_curve, precision_recall_curve, roc_auc_score
from sklearn.calibration import calibration_curve
from sklearn.linear_model import LogisticRegression
from xgboost import XGBClassifier
import shap

warnings.filterwarnings("ignore")
RNG = 42
np.random.seed(RNG)
BASE = r"D:/WorkBuddy/专家团 1/04_模型"
FIG = r"D:/WorkBuddy/专家团 1/05_图表/figures"
os.makedirs(FIG, exist_ok=True)

# 统一风格
plt.rcParams.update({
    "font.family": "Arial",
    "font.size": 11,
    "axes.titlesize": 12,
    "axes.labelsize": 11,
    "xtick.labelsize": 10,
    "ytick.labelsize": 10,
    "legend.fontsize": 10,
    "axes.linewidth": 1.0,
    "savefig.dpi": 300,
    "figure.dpi": 100,
})
C_MAIN = "#C0392B"   # 主口径红 (风险)
C_EXT  = "#1F4E79"   # 外部蓝
C_GRAY = "#7F7F7F"


def save(fig, name):
    fig.savefig(os.path.join(FIG, name + ".tiff"), dpi=300, bbox_inches="tight", pil_kwargs={"compression": "tiff_lzw"})
    fig.savefig(os.path.join(FIG, name + ".png"), dpi=300, bbox_inches="tight")
    plt.close(fig)
    print("saved", name)


# ---------------- 数据 ----------------
mimic = pd.read_csv(os.path.join(BASE, "data/mimic_model_data.csv"))
eicu  = pd.read_csv(os.path.join(BASE, "data/eicu_model_data.csv"))
pm = pd.read_csv(os.path.join(BASE, "results_final/mace/pred_mimic.csv"))
pe = pd.read_csv(os.path.join(BASE, "results_final/mace/pred_eicu.csv"))
ym, yp_m = pm["y"].values, pm["pred"].values
ye, yp_e = pe["y"].values, pe["pred"].values

# 敏感性数据 (BJA3)
pm3 = pd.read_csv(os.path.join(BASE, "results_final/mace3/pred_mimic.csv"))
pe3 = pd.read_csv(os.path.join(BASE, "results_final/mace3/pred_eicu.csv"))
ym3, yp_m3 = pm3["y"].values, pm3["pred"].values
ye3, yp_e3 = pe3["y"].values, pe3["pred"].values

sub_m = pd.read_csv(os.path.join(BASE, "results_final/subgroup_psm/subgroup_mimic.csv"))
sub_e = pd.read_csv(os.path.join(BASE, "results_final/subgroup_psm/subgroup_eicu.csv"))
psm = json.load(open(os.path.join(BASE, "results_final/subgroup_psm/psm_summary.json"), encoding="utf-8"))

# ============================================================
# Fig 1: 人群选择流程图 (双库 A/B 并列, matplotlib 绘制)
# ============================================================
fig, (axa, axb) = plt.subplots(1, 2, figsize=(13, 5.5))
for ax, title, boxes in [
    (axa, "A  MIMIC-IV (derivation)", [
        ("ICD-9 274.x / ICD-10 M10.x\ngout diagnoses (all admissions)", "10,642  patients"),
        ("Adult (≥18 y) with first ICU stay", "3,650  patients"),
        ("Excluded: prior MI / stroke / heart failure\n(any prior admission)", "797  patients"),
        ("Final derivation cohort\n(strict 6-event MACE = 1,086 / 2,853)", "2,853  patients"),
    ]),
    (axb, "B  eICU-CRD (external validation)", [
        ("Allopurinol use as gout proxy\n(medication records)", "1,996  ICU stays"),
        ("Adult (≥18 y) with first ICU stay", "1,895  ICU stays"),
        ("Excluded: prior MI / stroke /\nheart failure (past history)", "933  ICU stays"),
        ("Final validation cohort\n(strict 6-event MACE = 94 / 962)", "962  ICU stays"),
    ]),
]:
    ax.set_title(title, fontweight="bold", loc="left")
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    y = 0.86
    for i, (txt, num) in enumerate(boxes):
        b = dict(boxstyle="round,pad=0.25", facecolor="#F5F5F5" if i < len(boxes)-1 else "#FDEBD0",
                 edgecolor="#404040" if i < len(boxes)-1 else C_MAIN, linewidth=1.2)
        ax.text(0.5, y, txt, ha="center", va="center", fontsize=9.5, bbox=b)
        ax.text(0.5, y-0.235, num, ha="center", va="center", fontsize=10.5, fontweight="bold",
                color="#404040")
        if i < len(boxes)-1:
            ax.annotate("", xy=(0.5, 0.515-0*i), xytext=(0.5, 0.55-0*i),
                        arrowprops=dict(arrowstyle="-|>", color="#404040", lw=1.3))
        y -= 0.30
save(fig, "Fig1_flowchart")

# ============================================================
# Fig 2: ROC — 主口径 (A/B 双库) + 敏感性 (C/D) 四联
# ============================================================
fig, axes = plt.subplots(1, 4, figsize=(17, 4.2))
fpr, tpr, _ = roc_curve(ym, yp_m); auc_m = roc_auc_score(ym, yp_m)
fpr_e, tpr_e, _ = roc_curve(ye, yp_e); auc_e = roc_auc_score(ye, yp_e)
fpr3, tpr3, _ = roc_curve(ym3, yp_m3); auc_m3 = roc_auc_score(ym3, yp_m3)
fpr3e, tpr3e, _ = roc_curve(ye3, yp_e3); auc_e3 = roc_auc_score(ye3, yp_e3)
for ax, f, t, auc_, title, col in [
    (axes[0], fpr, tpr, auc_m, "A  MIMIC-IV CV\n(strict 6-event MACE)", C_MAIN),
    (axes[1], fpr_e, tpr_e, auc_e, "B  eICU-CRD external\n(strict 6-event MACE)", C_EXT),
    (axes[2], fpr3, tpr3, auc_m3, "C  MIMIC-IV CV\n(3-event composite)", C_MAIN),
    (axes[3], fpr3e, tpr3e, auc_e3, "D  eICU-CRD external\n(3-event composite)", C_EXT),
]:
    ax.plot(f, t, lw=2.2, color=col)
    ax.plot([0, 1], [0, 1], ls="--", lw=1, color=C_GRAY)
    ax.set_xlabel("1 - Specificity"); ax.set_ylabel("Sensitivity")
    ax.set_title(title, fontsize=10, fontweight="bold")
    ax.text(0.62, 0.12, f"AUC = {auc_:.3f}", fontsize=11, fontweight="bold",
            bbox=dict(facecolor="white", edgecolor=C_GRAY, boxstyle="round,pad=0.3"))
    ax.set_xlim(-0.02, 1.02); ax.set_ylim(-0.02, 1.02)
plt.tight_layout()
save(fig, "Fig2_ROC")

# ============================================================
# Fig 3: 校准曲线 (A/B 双库) + 敏感性小图 (C/D)
# ============================================================
fig, axes = plt.subplots(1, 4, figsize=(17, 4.2))
for ax, y_, p_, title, col in [
    (axes[0], ym, yp_m, "A  MIMIC-IV (6-event)", C_MAIN),
    (axes[1], ye, yp_e, "B  eICU-CRD (6-event)", C_EXT),
    (axes[2], ym3, yp_m3, "C  MIMIC-IV (3-event)", C_MAIN),
    (axes[3], ye3, yp_e3, "D  eICU-CRD (3-event)", C_EXT),
]:
    fp_, tp_ = calibration_curve(y_, p_, n_bins=10)
    ax.plot([0, 1], [0, 1], ls="--", color=C_GRAY, lw=1, label="Perfect")
    ax.plot(fp_, tp_, "o-", color=col, lw=2, ms=5)
    ax.set_xlabel("Predicted probability"); ax.set_ylabel("Observed proportion")
    ax.set_title(title, fontsize=10, fontweight="bold")
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.legend(loc="upper left", frameon=False)
plt.tight_layout()
save(fig, "Fig3_calibration")

# ============================================================
# Fig 4: DCA (A/B 双库, 主口径) + 敏感性 (C/D)
# ============================================================
def net_benefit(y, p, ths):
    y = np.asarray(y); p = np.asarray(p); nb = []
    for t in ths:
        tp = ((p >= t) & (y == 1)).sum(); fp = ((p >= t) & (y == 0)).sum()
        nb.append(tp/len(y) - fp/len(y)*t/(1-t))
    return np.array(nb)
ths = np.arange(0.03, 0.93, 0.02)
fig, axes = plt.subplots(1, 4, figsize=(17, 4.2))
for ax, y_, p_, title, col in [
    (axes[0], ym, yp_m, "A  MIMIC-IV (6-event)", C_MAIN),
    (axes[1], ye, yp_e, "B  eICU-CRD (6-event)", C_EXT),
    (axes[2], ym3, yp_m3, "C  MIMIC-IV (3-event)", C_MAIN),
    (axes[3], ye3, yp_e3, "D  eICU-CRD (3-event)", C_EXT),
]:
    ax.plot(ths, net_benefit(y_, p_, ths), color=col, lw=2.2, label="Model")
    ax.plot(ths, np.maximum(net_benefit(y_, np.full(len(y_), y_.mean()), ths), 0),
            ls="--", color=C_GRAY, lw=1.5, label="Treat all")
    ax.plot(ths, np.zeros(len(ths)), color="black", lw=1)
    ax.set_xlabel("Threshold probability"); ax.set_ylabel("Net benefit")
    ax.set_title(title, fontsize=10, fontweight="bold")
    ax.legend(loc="upper right", frameon=False)
plt.tight_layout()
save(fig, "Fig4_DCA")

# ============================================================
# Fig 5: SHAP (A summary + B bar, 主口径 XGB)
# ============================================================
FEATS = json.load(open(os.path.join(BASE, "results_final/mace/summary.json"), encoding="utf-8"))["features"]
common = [c for c in mimic.columns if c in eicu.columns]
drop_meta = {"patientunitstayid","subject_id","hadm_id","stay_id","mace","mace3",
             "ev_ami","ev_stroke","ev_cardiac_death","ev_cardshk","ev_malarr","ev_hfacu",
             "ev_death","hospital_expire_flag","n_events","intime","prior_mi","prior_stroke","prior_hf",
             "is_gout_dx","is_hyperuricemia_dx","is_ckd_dx","med_urate","admission_type","mace_wide"}
FEATS = sorted([c for c in common if c not in drop_meta])
miss_m = mimic[FEATS].isna().mean(); miss_e = eicu[FEATS].isna().mean()
FEATS = [c for c in FEATS if miss_m[c] <= 0.5 and miss_e[c] <= 0.5]
Xm = mimic[FEATS].copy()
if "gender" in Xm.columns:
    Xm["gender"] = Xm["gender"].map({"M":1,"F":0,"Male":1,"Female":0})
for c in Xm.columns: Xm[c] = pd.to_numeric(Xm[c], errors="coerce")
Xm = Xm.values.astype(float)
w = (1 - ym.mean())/ym.mean()
xgb = XGBClassifier(n_estimators=250, max_depth=5, learning_rate=0.03, subsample=0.8,
                    colsample_bytree=0.7, scale_pos_weight=w, base_score=0.5, eval_metric="auc",
                    random_state=RNG, verbosity=0, n_jobs=4)
xgb.fit(Xm, ym)
expl = shap.TreeExplainer(xgb)
sv = expl.shap_values(Xm)

fig, axa = plt.subplots(figsize=(8, 6))
shap.summary_plot(sv, Xm, feature_names=FEATS, max_display=15, show=False, alpha=0.8)
plt.title("A  SHAP summary (strict 6-event MACE, MIMIC-IV)", fontweight="bold", fontsize=11)
plt.tight_layout()
save(fig, "Fig5A_shap_summary")

fig, axb = plt.subplots(figsize=(8, 6))
shap.summary_plot(sv, Xm, feature_names=FEATS, plot_type="bar", max_display=15, show=False)
plt.title("B  Mean |SHAP| feature importance", fontweight="bold", fontsize=11)
plt.tight_layout()
save(fig, "Fig5B_shap_bar")

# ============================================================
# Fig 6: 列线图 (Logistic, 主口径, 简化 10 变量)
# ============================================================
lr_f = [c for c in ["anchor_age","gender","ckd","dm","hypertension","chloride","calcium",
                    "bun","creatinine","wbc","hemoglobin","gcs_total","rr_mean","sbp_mean",
                    "med_diuretic","med_vasopressor","med_betablocker","med_aspirin","med_statin"] if c in mimic.columns]
mimp = mimic[lr_f].copy()
for c in mimp.columns:
    if c == "gender": mimp[c] = mimp[c].map({"M":1,"F":0})
    mimp[c] = pd.to_numeric(mimp[c], errors="coerce")
mimp = mimp.fillna(mimp.median())
from sklearn.preprocessing import StandardScaler
Xs = StandardScaler().fit_transform(mimp)
lr = LogisticRegression(max_iter=2000, C=0.5, class_weight="balanced", random_state=RNG)
lr.fit(Xs, ym)
beta = lr.coef_[0]; names = lr_f
df_coef = pd.DataFrame({"feature": names, "coef": beta})
df_coef.to_csv(os.path.join(FIG, "nomogram_coefs.csv"), index=False)

# ---- 手绘列线图 ----
fig, ax = plt.subplots(figsize=(9, 5.2))
ax.set_xlim(0, 10); ax.set_ylim(0, 10); ax.axis("off")
n_var = len(names)
pmin, pmax = 0.05, 0.95
logit_low = lr.intercept_[0] + np.dot(np.zeros(len(names)), beta)
import numpy as np
logit = lambda v: lr.intercept_[0] + float(np.dot(v, beta))
lo = logit(np.percentile(Xs, 0, axis=0)); hi = logit(np.percentile(Xs, 100, axis=0))
tot_pts = 100.0
def proj(xs_):
    v = np.asarray(xs_, float)
    l_ = logit(v)
    return (l_ - lo) / (hi - lo) * tot_pts
def prob2pts(p):
    l_ = np.log(p / (1 - p)); return (l_ - lo) / (hi - lo) * tot_pts
# 坐标
x_left, x_right = 0.4, 9.6
gap = 8.6 / (n_var + 1)
ax.set_title("Nomogram for in-hospital MACE risk (strict 6-event, MIMIC-IV derivation)", fontweight="bold", fontsize=11)
xs = {}
for i, (nm, b) in enumerate(zip(names, beta)):
    x0 = x_left; x1 = x_right
    y = 8.2 - i * gap
    ax.text(x_left-0.2, y, nm, ha="right", va="center", fontsize=9.5, fontweight="bold")
    # 刻度: min->max
    lo_v, hi_v = Xs[:, i].min(), Xs[:, i].max()
    for k in range(6):
        frac = k / 5.0
        vv = lo_v + frac * (hi_v - lo_v)
        ax.plot([x0 + frac*(x1-x0)]*2, [y-0.14, y+0.14], color="black", lw=0.8)
    ax.plot([x0, x1], [y, y], color="black", lw=1.6)
    xs[nm] = (x0, x1, y)
# Points / Total / Risk axes
y_pts = 8.2 - (n_var+0.5)*gap
ax.text(x_left-0.2, y_pts, "Total points", ha="right", va="center", fontsize=9.5, fontweight="bold")
ax.plot([x_left, x_right], [y_pts, y_pts], color="black", lw=1.6)
for k in range(11):
    ax.plot([x_left + k/10*(x_right-x_left)]*2, [y_pts-0.14, y_pts+0.14], color="black", lw=0.8)
y_risk = y_pts - 0.85
ax.text(x_left-0.2, y_risk, "Risk", ha="right", va="center", fontsize=9.5, fontweight="bold")
pts_risks = [(0, 0.05), (25, 0.15), (50, 0.35), (75, 0.55), (100, 0.75)]
for k in range(5):
    p_ = pts_risks[k][1]
    x_ = x_left + (prob2pts(p_)/tot_pts)*(x_right-x_left)
    ax.plot([x_]*2, [y_risk-0.14, y_risk+0.14], color="black", lw=0.8)
    ax.text(x_, y_risk-0.3, f"{p_:.2f}", ha="center", fontsize=9)
ax.plot([x_left, x_right], [y_risk, y_risk], color="black", lw=1.6)
# 顶部 points 轴
ax.text(0, 9.2, "Points", fontsize=10, fontweight="bold")
for k in range(11):
    ax.plot([x_left + k/10*(x_right-x_left)]*2, [9.0, 9.15], color="black", lw=0.8)
    ax.text(x_left + k/10*(x_right-x_left), 8.78, str(k*10), ha="center", fontsize=8.5)
save(fig, "Fig6_nomogram")

# ============================================================
# Fig 7: 亚组森林图
# ============================================================
fig, ax = plt.subplots(figsize=(8, 4.6))
groups = sub_m["subgroup"].tolist(); rates = sub_m["rate6_pct"].tolist(); ns = sub_m["n"].tolist()
ax.scatter(rates, range(len(groups)), s=90, color=[C_MAIN, C_EXT, C_MAIN], edgecolor="black", zorder=3)
for g, r, n in zip(range(len(groups)), rates, ns):
    ax.annotate(f"{r}%  (n={n})", (r, g), textcoords="offset points", xytext=(8, 0), va="center", fontsize=9.5)
ax.axvline(38.07, ls="--", color=C_GRAY, lw=1.2)
ax.text(38.5, len(groups)-0.25, "Overall gout cohort 38.1%", fontsize=8.5, color=C_GRAY)
ax.set_yticks(range(len(groups))); ax.set_yticklabels(groups, fontsize=10)
ax.set_xlabel("In-hospital MACE rate (%)", fontsize=11)
ax.set_xlim(0, 55)
ax.set_title("Subgroup analysis: MACE rate by gout phenotype (MIMIC-IV)", fontweight="bold", fontsize=11)
plt.tight_layout()
save(fig, "Fig7_subgroup")

# ============================================================
# Fig 8: PSM 森林图
# ============================================================
fig, ax = plt.subplots(figsize=(8, 4.2))
rows = []
for exp, label in [("med_urate", "ULT (allopurinol-based)"), ("med_colchicine", "Colchicine")]:
    r = psm["psm"][exp]
    rows.append(("Crude", label, r["crude"]["or"], r["crude"]["ci95"]))
    rows.append(("PSM", label, r["matched_logistic"]["or"], r["matched_logistic"]["ci95"]))
ypos = np.arange(len(rows))[::-1]
for i, (stage, lab, orv, ci) in enumerate(rows):
    lo_, hi_ = ci
    ax.plot([lo_, hi_], [ypos[i], ypos[i]], color=C_EXT, lw=2.5)
    ax.scatter(orv, ypos[i], s=70, color=C_EXT, edgecolor="black", zorder=3)
    ax.annotate(f"OR {orv:.2f} ({lo_:.2f}-{hi_:.2f})", (orv, ypos[i]),
                textcoords="offset points", xytext=(8, 0), va="center", fontsize=9)
ax.axvline(1.0, ls="--", color=C_GRAY, lw=1.2)
ax.set_yticks(ypos)
ax.set_yticklabels([f"{s}  {l}" for s, l, *_ in rows], fontsize=10)
ax.set_xlabel("Odds ratio (95% CI) for in-hospital MACE", fontsize=11)
ax.set_xlim(0.5, 1.9)
ax.set_title("Drug exposure and in-hospital MACE after PSM (MIMIC-IV)", fontweight="bold", fontsize=11)
plt.tight_layout()
save(fig, "Fig8_PSM")

print("ALL FIGURES DONE")