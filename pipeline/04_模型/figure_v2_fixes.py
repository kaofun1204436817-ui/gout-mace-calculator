# -*- coding: utf-8 -*-
"""
论文级图表 v2 — 修复 Fig1/Fig7/Fig8 排版重叠问题
- Fig1 流程图: 排除数显式标 "−n", 上下间距充足, 数字与文字不重叠
- Fig7 亚组森林图: 标签文本右移留白, 不遮挡散点/虚线, 加宽画布
- Fig8 PSM 森林图: CI 线加粗、文本全部置于 x 轴右侧留白区, 行距拉大, 防重叠
输出: 05_图表/figures_v2/*.png + *.tiff
"""
import os, json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

warnings = None
import warnings as _w
_w.filterwarnings("ignore")

FIG_NEW = r"D:/WorkBuddy/专家团 1/05_图表/figures_v2"
os.makedirs(FIG_NEW, exist_ok=True)

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
C_MAIN = "#C0392B"
C_EXT  = "#1F4E79"
C_GRAY = "#7F7F7F"
C_BOX  = "#F5F5F5"
C_BOX_END = "#FDEBD0"

def save(fig, name):
    fig.savefig(os.path.join(FIG_NEW, name + ".tiff"), dpi=300, bbox_inches="tight", pil_kwargs={"compression": "tiff_lzw"})
    fig.savefig(os.path.join(FIG_NEW, name + ".png"), dpi=300, bbox_inches="tight")
    plt.close(fig)
    print("saved", name)

# ============================================================
# Fig 1: 流程图 v2 (排除数显式 -n, 左右两栏)
# ============================================================
def draw_flow(ax, title, boxes, color_end, x0=0.02, x1=0.98):
    n = len(boxes)
    ax.set_title(title, fontweight="bold", loc="left", fontsize=11.5)
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    # 从上到下排布, 每行一个 box
    top = 0.94
    step = 0.88 / (n + 0.35)
    for i, (txt, num) in enumerate(boxes):
        yc = top - i * step
        boxstyle = dict(boxstyle="round,pad=0.3", facecolor=(C_BOX if i < n-1 else color_end),
                        edgecolor=("#404040" if i < n-1 else color_end), linewidth=1.2)
        ax.text(0.5, yc, txt, ha="center", va="center", fontsize=9.0, bbox=boxstyle,
                transform=ax.transAxes)
        if i < n-1:
            ax.annotate("", xy=(0.5, yc - step*0.58), xytext=(0.5, yc - step*0.42),
                        arrowprops=dict(arrowstyle="-|>", color="#404040", lw=1.4),
                        transform=ax.transAxes)
        # 数字标在框右侧(留白区)
        ax.text(0.80, yc, num, ha="left", va="center", fontsize=10.5, fontweight="bold",
                color="#404040", transform=ax.transAxes)
        ax.text(0.80, yc, "   "+num, ha="left", va="center", fontsize=1, alpha=0, transform=ax.transAxes)

mimic_boxes = [
    ("ICD-9 274.x / ICD-10 M10.x\ngout diagnoses (all admissions)", "10,642 patients"),
    ("Adult (≥18 y) with first ICU stay", "3,650 patients"),
    ("Excluded: prior MI / stroke / heart failure", "−797 patients"),
    ("Final derivation cohort\n(strict 6-event MACE = 1,086 / 2,853)", "2,853 patients"),
]
eicu_boxes = [
    ("Allopurinol use as gout proxy\n(medication records)", "1,996 ICU stays"),
    ("Adult (≥18 y) with first ICU stay", "1,895 ICU stays"),
    ("Excluded: prior MI / stroke / heart failure", "−933 ICU stays"),
    ("Final validation cohort\n(strict 6-event MACE = 94 / 962)", "962 ICU stays"),
]
fig, (axa, axb) = plt.subplots(1, 2, figsize=(14, 5.6))
draw_flow(axa, "A  MIMIC-IV (derivation)", mimic_boxes, C_MAIN)
draw_flow(axb, "B  eICU-CRD (external validation)", eicu_boxes, C_EXT)
plt.tight_layout()
save(fig, "Fig1_flowchart")

# ============================================================
# Fig 7: 亚组森林图 v2 (标签移到右侧留白)
# ============================================================
sub_m = pd.read_csv(r"D:/WorkBuddy/专家团 1/04_模型/results_final/subgroup_psm/subgroup_mimic.csv")
fig, ax = plt.subplots(figsize=(10, 4.8))
groups = sub_m["subgroup"].tolist()
rates = sub_m["rate6_pct"].tolist()
ns = sub_m["n"].tolist()
ypos = np.arange(len(groups))[::-1]
colors_bar = [C_MAIN, C_EXT, C_MAIN]
ax.barh(ypos, rates, height=0.55, color=colors_bar, edgecolor="black", alpha=0.85, zorder=2)
# 数值标签在条右侧(留白), 偏移固定
for y, r, n in zip(ypos, rates, ns):
    ax.text(r + 1.5, y, f"{r:.2f}%  (n={n})", va="center", fontsize=10, color="#1a1a1a")
ax.axvline(38.07, ls="--", color=C_GRAY, lw=1.2)
ax.text(40.0, 2.55, "Overall gout cohort 38.1%", fontsize=9, color=C_GRAY)
labels_map = {"Hyperuricemia only": "Hyperuricemia only", "Gout without CKD": "Gout without CKD",
              "Gout with CKD": "Gout with CKD"}
ax.set_yticks(ypos); ax.set_yticklabels([labels_map.get(g, g) for g in groups], fontsize=11)
ax.set_xlabel("In-hospital MACE rate (%)", fontsize=11.5)
ax.set_xlim(0, 62)
ax.set_title("Subgroup analysis: MACE rate by gout phenotype (MIMIC-IV)", fontweight="bold", fontsize=12)
ax.grid(axis="x", ls=":", color="#cccccc", alpha=0.6)
plt.tight_layout()
save(fig, "Fig7_subgroup")

# ============================================================
# Fig 8: 药物暴露三层稳健森林图 (Crude / PSM / IPTW / Full-adjusted)
# ============================================================
psm = json.load(open(r"D:/WorkBuddy/专家团 1/04_模型/results_final/subgroup_psm/psm_summary.json", encoding="utf-8"))
rows = []
for exp, label in [("med_urate", "ULT (allopurinol-based)"), ("med_colchicine", "Colchicine")]:
    r = psm["psm"][exp]
    rows.append(("Crude", label, r["crude"]["or"], r["crude"]["ci95"]))
    ps = r.get("psm") or {}
    if ps.get("logistic"):
        rows.append(("PSM", label, ps["logistic"]["or"], ps["logistic"]["ci95"]))
    iptw = r.get("iptw", {}).get("or") or {}
    if iptw.get("or") is not None:
        rows.append(("IPTW", label, iptw["or"], iptw["ci95"]))
    fa = r.get("full_adjusted") or {}
    if fa.get("or") is not None:
        rows.append(("Full-adjusted", label, fa["or"], fa["ci95"]))
fig, ax = plt.subplots(figsize=(11, 6.2))
n = len(rows)
ypos = np.arange(n)[::-1]
cmap_stage = {"Crude": "#8c8c8c", "PSM": C_EXT, "IPTW": "#2c7fb8", "Full-adjusted": "#d95f0e"}
for i, (stage, lab, orv, ci) in enumerate(rows):
    lo_, hi_ = ci
    ax.plot([lo_, hi_], [ypos[i], ypos[i]], color=cmap_stage[stage], lw=3.0, zorder=3)
    ax.scatter(orv, ypos[i], s=110, color=cmap_stage[stage], edgecolor="black", zorder=4)
    ax.text(hi_ + 0.06, ypos[i], f"OR {orv:.2f} ({lo_:.2f}-{hi_:.2f})",
            va="center", fontsize=10, color="#1a1a1a")
ax.axvline(1.0, ls="--", color=C_GRAY, lw=1.2)
lbls = [f"{stage}  {lab}" for stage, lab, *_ in rows]
ax.set_yticks(ypos); ax.set_yticklabels(lbls, fontsize=11)
ax.set_xlabel("Odds ratio (95% CI) for in-hospital MACE", fontsize=11.5)
ax.set_xlim(0.4, 2.6)
ax.set_title("Drug exposure and in-hospital MACE: crude, PSM, IPTW, and adjusted estimates (MIMIC-IV)",
             fontweight="bold", fontsize=12)
ax.grid(axis="x", ls=":", color="#cccccc", alpha=0.6)
from matplotlib.lines import Line2D
h = [Line2D([0],[0], color=c, lw=3, label=k) for k,c in cmap_stage.items()]
ax.legend(handles=h, loc="lower right", fontsize=9, frameon=False)
plt.tight_layout()
save(fig, "Fig8_PSM")

print("FIGURES V2 DONE")