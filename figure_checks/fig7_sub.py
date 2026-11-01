# -*- coding: utf-8 -*-
"""Fig7 亚组图：配色按"是否 CKD/高风险"语义化，非按位置硬编码"""
import sys; sys.path.insert(0, r"D:/WorkBuddy/专家团 1/_工具")
from rebuild_all_figs import *

t4 = pd.read_csv(f"{BASE}/results_final/tables/Table4_subgroup.csv")

# 语义化配色：有 CKD = 红（高风险）；无 CKD = 蓝；高尿酸无痛风 = 灰（参照组，非痛风）
C_CKD   = "#C0504D"   # 含 CKD
C_NOCKD = "#4F81BD"   # 不含 CKD
C_REF   = "#A6A6A6"   # 参照/非痛风

panelA = [("Hyperuricemia\nwithout gout", 49, 177, 27.68, C_REF),
          ("Gout without CKD", 343, 1185, 28.95, C_NOCKD),
          ("Gout with CKD", 743, 1668, 44.54, C_CKD)]
panelB = [("Allopurinol proxy\nwithout CKD", 87, 786, 11.07, C_NOCKD),
          ("Allopurinol proxy\nwith CKD", 7, 176, 3.98, C_CKD)]

fig, axes = plt.subplots(2, 1, figsize=(7.13, 6.6))

for ax, data, title, overall, xmax in [
    (axes[0], panelA, "A   MIMIC-IV derivation cohort", 38.1, 62),
    (axes[1], panelB, "B   eICU-CRD external cohort", 9.8, 16.5)]:

    labs = [d[0] for d in data][::-1]
    rates = [d[3] for d in data][::-1]
    ns = [d[2] for d in data][::-1]
    cols = [d[4] for d in data][::-1]

    ax.barh(range(len(labs)), rates, color=cols, edgecolor="black", lw=0.7, height=0.55)
    ax.set_yticks(range(len(labs)))
    ax.set_yticklabels(labs, fontsize=7.5)

    ax.axvline(overall, color="#555555", ls="--", lw=0.9, zorder=1)
    ax.text(overall + xmax*0.012, len(labs)-0.42, f"Overall {overall}%",
            fontsize=6.4, color="#444444", va="center")

    for i, (r, nn) in enumerate(zip(rates, ns)):
        ax.text(r + xmax*0.015, i, f"{r:.2f}%  (n={nn:,})",
                va="center", fontsize=7.2)

    ax.set_xlim(0, xmax); ax.set_ylim(-0.55, len(labs)-0.15)
    step = 10 if xmax > 30 else 2
    ax.set_xticks(np.arange(0, xmax, step))
    ax.set_xlabel("In-hospital MACE rate (%)", fontsize=8)
    ax.set_title(title, fontweight="bold", loc="left", fontsize=8.6, pad=4)
    ax.grid(axis="x", ls=":", alpha=0.3)
    ax.spines[["top","right"]].set_visible(False)
    ax.tick_params(labelsize=7)

fig.suptitle("MACE rate by prespecified subgroup", fontsize=9.4, fontweight="bold", y=0.985)
fig.tight_layout(rect=[0,0,1,0.965], h_pad=1.2)
save(fig, "Fig7_subgroup", "Fig7 亚组")
