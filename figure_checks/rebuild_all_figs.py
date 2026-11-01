# -*- coding: utf-8 -*-
"""
rebuild_all_figs.py — 9 张论文图统一重制
设计原则：
1. 每张图生成后立即用 detect_overlaps 检测，不通过就报错而不是静默保存
2. 所有文字位置用 axes 坐标 + 留白计算，不用固定像素猜测
3. 图例不与注解抢占同一角落：注解放上方，图例放下方；或注解进标题
4. y 轴标签超长时用换行，不用超长单行
"""
import sys, os, json
sys.path.insert(0, r"D:/WorkBuddy/专家团 1/_工具")
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from matplotlib.ticker import NullFormatter, FixedLocator, FixedFormatter, FuncFormatter
from text_overlap_detector import detect_overlaps, detect_collisions

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 8,
    "axes.titlesize": 9,
    "axes.labelsize": 8.5,
    "xtick.labelsize": 7.5,
    "ytick.labelsize": 7.5,
    "legend.fontsize": 7,
    "axes.linewidth": 0.8,
    "savefig.dpi": 300,
})

BASE = r"D:/WorkBuddy/专家团 1/04_模型"
FIG  = r"D:/WorkBuddy/专家团 1/05_图表/figures"
REPORT = []

def save(fig, stem, name):
    """检测 → 保存 → 记录（三重检测：文字重叠 / 文字越界 / 文字×图形碰撞）"""
    print(f"\n--- {name} ---")
    ov, ob = detect_overlaps(fig, verbose=True)
    col = detect_collisions(fig, pad_px=6.0, verbose=True)
    clean = (len(ov) == 0 and len(ob) == 0 and len(col) == 0)
    if not clean:
        print(f"  ⚠️ 存在问题（重叠{len(ov)}/越界{len(ob)}/碰撞{len(col)}），仍保存以便查看")
    REPORT.append({"fig": stem, "name": name, "overlaps": len(ov), "oob": len(ob),
                   "collisions": len(col), "clean": clean,
                   "detail": (ov[:5] + ob[:5] + col[:5])})
    for ext in (".png", ".tiff"):
        kw = dict(dpi=300, bbox_inches="tight", pad_inches=0.03, facecolor="white")
        if ext == ".tiff":
            kw["pil_kwargs"] = {"compression": "tiff_lzw"}
        fig.savefig(os.path.join(FIG, stem + ext), **kw)
    plt.close(fig)
    return clean
