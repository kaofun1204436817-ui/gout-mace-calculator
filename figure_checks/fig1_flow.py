# -*- coding: utf-8 -*-
"""Fig1 v4：先量框宽 → 再定注记位置，保证注记在框右缘外留白"""
import sys; sys.path.insert(0, r"D:/WorkBuddy/专家团 1/_工具")
from rebuild_all_figs import *

FW, FH = 7.13, 4.5
fig = plt.figure(figsize=(FW, FH))
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, 100); ax.set_ylim(0, 100)
ax.set_xticks([]); ax.set_yticks([])
for s in ax.spines.values(): s.set_visible(False)

def m(txt, fs):
    t = fig.text(0, 0, txt, fontsize=fs)
    fig.canvas.draw()
    bb = t.get_window_extent(renderer=fig.canvas.get_renderer())
    r = bb.width/fig.dpi, bb.height/fig.dpi
    t.remove(); return r

PAD_IN = 0.13
def wh(lines, fs):
    w_in, h_in = m("\n".join(lines), fs)
    return (w_in+2*PAD_IN)/FW*100, (h_in+2*PAD_IN)/FH*100

def draw_box(left, cy, lines, w, h, fs=7.0, fc="#DCE9F5", bold=False):
    ax.add_patch(FancyBboxPatch((left, cy-h/2), w, h,
        boxstyle="round,pad=0,rounding_size=0.35", fc=fc, ec="black", lw=0.8, zorder=2))
    ax.text(left+w/2, cy, "\n".join(lines), ha="center", va="center", fontsize=fs,
            fontweight="bold" if bold else "normal", linespacing=1.4, zorder=3)

def arrow(x, y1, y2):
    ax.add_patch(FancyArrowPatch((x, y1), (x, y2), arrowstyle="-|>",
        mutation_scale=8, lw=0.8, color="#666666", zorder=1))

def build(x0, title, steps, final, fc_final, note_min_gap=1.0):
    # 1) 先统一测出该栏最大框宽
    widths = [wh(l, 7.0)[0] for l, _, _ in steps] + [wh(final, 7.0)[0]]
    bw = max(widths)
    ax.text(x0+bw/2, 97, title, ha="center", va="top", fontsize=8.4, fontweight="bold")
    # 2) 注记左缘 = 框右缘 + 留白
    note_x = x0 + bw + note_min_gap
    ys = [89.0, 74.0, 59.0]
    prev = None
    for (lines, note, fc), y in zip(steps, ys):
        w, h = wh(lines, 7.0)
        draw_box(x0, y, lines, bw, h, fc=fc)
        ax.text(note_x, y, note, ha="left", va="center", fontsize=6.4,
                color="#222222", linespacing=1.35)
        if prev is not None:
            arrow(x0+bw/2, prev, y+h/2+1.0)
        prev = y-h/2-1.0
    wf, hf = wh(final, 7.0)
    fy = 40.0
    draw_box(x0, fy, final, bw, hf, fc=fc_final, bold=True)
    arrow(x0+bw/2, prev, fy+hf/2+1.0)

build(3.0, "A   MIMIC-IV derivation cohort", [
    (["Gout diagnosis", "(ICD-9 274.x / ICD-10 M10.x)"], "10,642 admissions", "#DCE9F5"),
    (["Restricted to first ICU stay per patient"], "3,650 patients\n(−6,992: no ICU stay\nor repeat ICU)", "#F0F0F0"),
    (["Excluded: prior MI, stroke,", "or heart failure (any prior admission)"], "−797 patients", "#DCE9F5"),
], ["Derivation cohort: 2,853 patients", "6-event MACE: 1,086 (38.1%)"], "#E8B4B0")

build(52.0, "B   eICU-CRD external cohort", [
    (["Allopurinol record as gout proxy"], "1,996 ICU stays", "#DCE9F5"),
    (["Restricted to first ICU stay per patient"], "1,895 ICU stays (−101)", "#F0F0F0"),
    (["Excluded: prior MI, stroke,", "or heart failure (any prior admission)"], "−933 ICU stays", "#DCE9F5"),
], ["Validation cohort: 962 ICU stays", "6-event MACE: 94 (9.8%)"], "#A9C6E8")

ax.text(50, 22, "Administrative diagnosis codes cannot be dated relative to ICU admission in either database;\nthe endpoint captures coded in-hospital events (see Methods).",
        ha="center", va="top", fontsize=6.0, style="italic", color="#444444", linespacing=1.5)

save(fig, "Fig1_flowchart", "Fig1 流程图")
