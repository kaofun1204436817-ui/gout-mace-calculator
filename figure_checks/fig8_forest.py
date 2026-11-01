# -*- coding: utf-8 -*-
"""Fig8 森林图：右侧独立数值列 + 对数轴手排刻度，杜绝挤压与裁切"""
import sys; sys.path.insert(0, r"D:/WorkBuddy/专家团 1/_工具")
from rebuild_all_figs import *
from matplotlib.ticker import NullFormatter, FixedLocator, FixedFormatter

t5 = pd.read_csv(f"{BASE}/results_final/tables/Table5_psm.csv")

rows=[]
for _,r in t5.iterrows():
    exp = r["Exposure"]
    for lab,col in [("Crude","Crude OR (95% CI)"),("PSM","PSM matched OR (95% CI)"),
                    ("IPTW","IPTW OR (95% CI)"),("Full-adjusted","Full-adjusted OR (95% CI)")]:
        s=str(r[col]); orv=float(s.split("(")[0].strip())
        ci=s.split("(")[1].rstrip(")").replace("–","-")
        lo,hi=[float(x) for x in ci.split("-")]
        rows.append(dict(exposure=exp, method=lab, orv=orv, lo=lo, hi=hi,
                         smd=r["Max |SMD| after"], bal=r["PSM balance"]))
df=pd.DataFrame(rows)

# 图区只容纳数据，数值列另置于右侧
XLO, XHI = 0.62, 1.95
fig = plt.figure(figsize=(7.13, 5.2))
ax = fig.add_axes([0.42, 0.12, 0.34, 0.80])   # 主图区偏右，左侧留给 y 标签
txt_ax = fig.add_axes([0.775, 0.12, 0.215, 0.80])
txt_ax.axis("off")
txt_ax.set_xticks([]); txt_ax.set_yticks([])
txt_ax.set_xlim(0,1); txt_ax.set_ylim(0,1)

colors={"Crude":"#9E9E9E","PSM":"#1F4E79","IPTW":"#2E75B6","Full-adjusted":"#ED7D31"}
ypos=[]; ylabs=[]; y=0
for exp in ["ULT (allopurinol-based)","Colchicine"]:
    disp = "Allopurinol-based ULT" if "ULT" in exp else "Colchicine"
    for _,r in df[df["exposure"]==exp].iterrows():
        note = ""
        if r["method"]=="PSM":
            note = "  (unbalanced)" if r["bal"]=="unbalanced" else "  (balanced)"
        ypos.append(y); ylabs.append(f"{r['method']} — {disp}{note}")
        ax.plot([r["lo"],r["hi"]],[y,y],color=colors[r["method"]],lw=2.0,solid_capstyle="round",zorder=3)
        ax.plot([r["orv"]],[y],"o",color=colors[r["method"]],ms=6,mec="black",mew=0.6,zorder=4)
        y+=1
    y+=0.9

ax.axvline(1.0,color="black",ls="--",lw=0.9,alpha=0.8,zorder=1)
ax.set_xscale("log"); ax.set_xlim(XLO,XHI)
ticks=[0.7,0.8,0.9,1.0,1.2,1.5,1.8]
ax.xaxis.set_major_locator(FixedLocator(ticks))
ax.xaxis.set_major_formatter(FixedFormatter([f"{t:g}" for t in ticks]))
ax.xaxis.set_minor_formatter(NullFormatter())

ax.yaxis.set_minor_locator(FixedLocator([]))
ax.yaxis.set_major_locator(FixedLocator(ypos))
ax.yaxis.set_major_formatter(FixedFormatter(ylabs))
ax.set_ylim(max(ypos)+0.55, -0.55)   # 直接倒置，避免负刻度外溢
ax.set_xlabel("Odds ratio (95% CI), log scale", fontsize=7.5)
ax.tick_params(axis="x", labelsize=6.8); ax.tick_params(axis="y", length=0, labelsize=6.8)
ax.spines[["top","right","left"]].set_visible(False)
ax.grid(axis="x", ls=":", alpha=0.3)

# 右侧数值列（与主图同 y 范围）
txt_ax.set_ylim(ax.get_ylim())
txt_ax.text(0.0, -0.72, "OR (95% CI)", fontsize=6.8, fontweight="bold", va="center")
for yv, r in zip(ypos, df.itertuples()):
    txt_ax.text(0.0, yv, f"{r.orv:.2f} ({r.lo:.2f}–{r.hi:.2f})", fontsize=6.8, va="center")

fig.text(0.42, 0.955, "Drug exposure and in-hospital MACE (MIMIC-IV)", fontsize=8.6, fontweight="bold")
save(fig, "Fig8_PSM", "Fig8 森林图")
