# -*- coding: utf-8 -*-
"""对已生成的图做像素级重叠检测（不依赖 matplotlib 对象）：
用连通域分析找"文字块相互粘连"的区域 —— 两段文字若粘连，会形成异常宽的连通域。
"""
import sys, os
sys.path.insert(0, r"D:/WorkBuddy/专家团 1/_工具")
import numpy as np
from PIL import Image
from scipy import ndimage
Image.MAX_IMAGE_PIXELS = None

FIG = r"D:/WorkBuddy/专家团 1/05_图表/figures"

def analyze(path, name):
    im = Image.open(path).convert("L")
    a = np.array(im)
    dark = a < 140
    # 水平投影：找文字行
    rows = dark.sum(axis=1)
    # 行内连通域：宽高比异常（很宽很扁）通常意味着横向文字粘连
    lbl, n = ndimage.label(dark)
    if n == 0:
        return None
    objs = ndimage.find_objects(lbl)
    wide_low = 0
    for sl in objs:
        h = sl[0].stop - sl[0].start
        w = sl[1].stop - sl[1].start
        if h <= 0: continue
        ar = w / h
        # 单个字符/单词的连通域宽高比一般 < 12；超过说明横向粘连
        # 排除横轴线（高<20px 且极扁的是线，不是文字粘连）
        if ar > 14 and w > 60 and h >= 20:
            wide_low += 1
    return {"name": name, "components": n, "suspicious_wide": wide_low,
            "dark_ratio": round(dark.mean()*100, 2)}

print(f"{'图':26s} {'连通域':>7s} {'可疑粘连':>8s} {'墨迹%':>7s}")
print("-"*54)
issues=[]
for f in ["Fig1_flowchart","Fig2_ROC","Fig3_calibration","Fig4_DCA","Fig5A_shap_summary",
          "Fig5B_shap_bar","Fig6_nomogram","Fig7_subgroup","Fig8_PSM"]:
    p = os.path.join(FIG, f+".png")
    if not os.path.exists(p): continue
    r = analyze(p, f)
    flag = "⚠️" if r["suspicious_wide"]>3 else "OK"
    if r["suspicious_wide"]>3: issues.append(f)
    print(f"{f:26s} {r['components']:>7d} {r['suspicious_wide']:>8d} {r['dark_ratio']:>7.1f} {flag}")
print()
print("需重点复核:", issues if issues else "无")
