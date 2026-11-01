# -*- coding: utf-8 -*-
"""Fig2 ROC：AUROC 与 CI 全部并入图例，取消角落 inset，根本消除重叠"""
import sys; sys.path.insert(0, r"D:/WorkBuddy/专家团 1/_工具")
from rebuild_all_figs import *
from sklearn.metrics import roc_curve, auc

md = pd.read_csv(f"{BASE}/data/mimic_model_data.csv")
ed = pd.read_csv(f"{BASE}/data/eicu_model_data.csv")

def boot_band(y, p, n=300, seed=42):
    rng = np.random.default_rng(seed)
    fprs = np.linspace(0,1,101); tprs=[]
    for _ in range(n):
        idx = rng.integers(0,len(y),len(y))
        if y[idx].sum() in (0,len(idx)): continue
        f,t,_ = roc_curve(y[idx], p[idx])
        tprs.append(np.interp(fprs, f, t))
    a=np.array(tprs)
    return fprs, np.percentile(a,2.5,axis=0), np.percentile(a,97.5,axis=0)

cis={}
for tgt,key in [("mace","6"),("mace3","3")]:
    d=json.load(open(f"{BASE}/results_final/{tgt}/summary.json",encoding="utf-8"))["best"]
    cis[key]={"int":(d["internal"]["auc"],d["internal"]["auc_ci"]),
              "ext":(d["external"]["auc"],d["external"]["auc_ci"])}

panels=[("A   MIMIC-IV, strict 6-event","mace","oof","#C0392B","int","6"),
        ("B   eICU-CRD, strict 6-event","mace","ext","#1F4E79","ext","6"),
        ("C   MIMIC-IV, 3-event","mace3","oof","#C0392B","int","3"),
        ("D   eICU-CRD, 3-event","mace3","ext","#1F4E79","ext","3")]

fig, axes = plt.subplots(2,2, figsize=(7.13,6.9))
for ax,(title,tgt,kind,color,ck,ep) in zip(axes.ravel(), panels):
    p = np.load(f"{BASE}/results_final/{tgt}/{kind}_XGB.npy")
    y = (md if kind=="oof" else ed)[tgt].astype(int).values
    fpr,tpr,_ = roc_curve(y,p); a=auc(fpr,tpr)
    fx,lo,hi = boot_band(y,p)
    ax.fill_between(fx,lo,hi,color=color,alpha=0.15,lw=0,label="95% CI (bootstrap)")
    ax.plot(fpr,tpr,color=color,lw=1.5,label="XGBoost")
    ax.plot([0,1],[0,1],ls="--",color="#888888",lw=0.8,label="Chance")
    av, ci = cis[ep][ck]
    ax.set_xlim(0,1); ax.set_ylim(0,1.0)
    ax.set_xticks([0,0.2,0.4,0.6,0.8,1.0]); ax.set_yticks([0,0.2,0.4,0.6,0.8,1.0])
    ax.set_xlabel("1 − Specificity"); ax.set_ylabel("Sensitivity")
    ax.set_title(title, fontweight="bold", loc="left", pad=5)
    # 关键：AUROC 数值并入图例标题，不用角落 inset
    ax.legend(loc="lower right", frameon=True, framealpha=0.95, edgecolor="#CCCCCC",
              fontsize=6.4, title=f"AUROC {av:.3f} (95% CI {ci[0]:.3f}–{ci[1]:.3f})",
              title_fontsize=6.4, borderpad=0.45, handlelength=1.6, labelspacing=0.35)
    ax.grid(ls=":", alpha=0.25)
    ax.spines[["top","right"]].set_visible(False)
    ax.tick_params(labelsize=7)

fig.tight_layout(pad=0.6, h_pad=1.0, w_pad=1.0)
save(fig, "Fig2_ROC", "Fig2 ROC 曲线")
