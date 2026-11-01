# -*- coding: utf-8 -*-
"""Fig5A/5B SHAP：留足右侧标签空间，避免数值贴边"""
import sys; sys.path.insert(0, r"D:/WorkBuddy/专家团 1/_工具")
from rebuild_all_figs import *
from matplotlib.colors import LinearSegmentedColormap, Normalize

sv = np.load(f"{BASE}/results_final/mace/shap_values.npy")
Xv = np.load(f"{BASE}/results_final/mace/shap_X.npy")
imp = pd.read_csv(f"{BASE}/results_final/mace/shap_importance.csv")
feats = imp["feature"].tolist(); idx={f:i for i,f in enumerate(feats)}
t3 = pd.read_csv(f"{BASE}/results_final/tables/Table3_shap.csv").sort_values("Rank")
top = t3["Feature"].head(15).tolist()

# ---------- 5A beeswarm ----------
cmap = LinearSegmentedColormap.from_list("shap", ["#008bf8","#b21df5","#ff0051"])
fig, ax = plt.subplots(figsize=(7.13, 6.5))
rng = np.random.default_rng(42)
for row, f in enumerate(top[::-1]):
    j = idx[f]; vals = sv[:, j]; fv = Xv[:, j]
    lo, hi = np.nanpercentile(fv,5), np.nanpercentile(fv,95)
    norm = Normalize(vmin=lo, vmax=hi if hi>lo else lo+1)
    yj = row + rng.uniform(-0.26,0.26,len(vals))
    order = np.argsort(np.abs(vals))
    sc = ax.scatter(vals[order], yj[order], c=fv[order], cmap=cmap, norm=norm,
                    s=3.0, alpha=0.75, linewidths=0, rasterized=True)
ax.set_yticks(range(len(top))); ax.set_yticklabels(top[::-1], fontsize=7.4)
ax.axvline(0, color="#666666", lw=0.8, alpha=0.9)
ax.set_xlabel("SHAP value (log-odds impact on model output)", fontsize=8)
ax.set_title("A   SHAP summary, strict 6-event MACE (MIMIC-IV)", fontsize=8.6, fontweight="bold", loc="left", pad=5)
ax.spines[["top","right"]].set_visible(False)
ax.grid(axis="x", ls=":", alpha=0.25); ax.tick_params(labelsize=7)
cb = fig.colorbar(sc, ax=ax, pad=0.015, aspect=32)
cb.set_label("Feature value", fontsize=7.4); cb.set_ticks([0,1]); cb.set_ticklabels(["Low","High"])
cb.ax.tick_params(labelsize=6.8)
fig.tight_layout()
save(fig, "Fig5A_shap_summary", "Fig5A SHAP beeswarm")

# ---------- 5B bar ----------
fig, ax = plt.subplots(figsize=(7.13, 6.0))
f20 = t3["Feature"].head(20).tolist()[::-1]
v20 = t3["Mean |SHAP|"].head(20).tolist()[::-1]
ax.barh(range(len(f20)), v20, color="#2E75B6", edgecolor="black", lw=0.5, height=0.68)
ax.set_yticks(range(len(f20))); ax.set_yticklabels(f20, fontsize=7.4)
vmax = max(v20)
for i, v in enumerate(v20):
    ax.text(v + vmax*0.018, i, f"{v:.3f}", va="center", fontsize=6.6)
ax.set_xlim(0, vmax*1.22)          # 右侧预留 22% 给数值标签
ax.set_xticks([0, 0.05, 0.10, 0.15, 0.20, 0.25])
ax.set_xlabel("mean(|SHAP value|)", fontsize=8)
ax.set_title("B   Mean |SHAP| feature importance, top 20 (strict 6-event MACE)",
             fontsize=8.6, fontweight="bold", loc="left", pad=5)
ax.grid(axis="x", ls=":", alpha=0.25)
ax.spines[["top","right"]].set_visible(False); ax.tick_params(labelsize=7)
fig.tight_layout()
save(fig, "Fig5B_shap_bar", "Fig5B SHAP bar")
