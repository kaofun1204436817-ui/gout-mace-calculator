# -*- coding: utf-8 -*-
"""
text_overlap_detector.py — 图件文字重叠/溢出程序化检测
在用 matplotlib 生成图时，把所有 Text 的渲染包围盒取出来做两两相交检测，
同时检测文字是否超出所属坐标轴或 figure 画布。
"""
import itertools
import numpy as np
from matplotlib.transforms import Bbox


def detect_overlaps(fig, pad_px=1.5, verbose=True, axes_of_interest=None):
    """返回 (overlaps, out_of_bounds) 两个问题清单。"""
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()

    # 收集所有可见文字及其归属坐标轴
    items = []
    for ax in fig.axes:
        for t in ax.texts + ax.get_xticklabels() + ax.get_yticklabels() + \
                 ([ax.title] if ax.get_title() else []) + \
                 ([ax.xaxis.label] if ax.get_xlabel() else []) + \
                 ([ax.yaxis.label] if ax.get_ylabel() else []):
            if not t.get_visible() or not t.get_text().strip():
                continue
            items.append((t, ax))
        leg = ax.get_legend()
        if leg is not None:
            for t in leg.get_texts():
                if t.get_text().strip():
                    items.append((t, ax))
    # figure 级文字
    for t in fig.texts:
        if t.get_visible() and t.get_text().strip():
            items.append((t, None))

    # 取包围盒
    boxes = []
    for t, ax in items:
        try:
            bb = t.get_window_extent(renderer=renderer)
        except Exception:
            continue
        if bb.width <= 0 or bb.height <= 0:
            continue
        boxes.append((t.get_text().replace("\n", " | ")[:45], bb, ax))

    overlaps = []
    for (s1, b1, a1), (s2, b2, a2) in itertools.combinations(boxes, 2):
        ix = min(b1.x1, b2.x1) - max(b1.x0, b2.x0)
        iy = min(b1.y1, b2.y1) - max(b1.y0, b2.y0)
        if ix > pad_px and iy > pad_px:
            overlaps.append({
                "a": s1, "b": s2,
                "overlap_px": (round(ix, 1), round(iy, 1)),
                "area": round(ix * iy, 1),
            })

    # 越界检测：只判断是否超出 figure 画布（刻度/轴标签在 axes 外属正常布局）
    out_of_bounds = []
    fig_bb = fig.bbox
    fig_w = fig_bb.width; fig_h = fig_bb.height
    for s, bb, ax in boxes:
        # 允许超出 figure 边缘 1% 容差
        ref = Bbox([[fig_bb.x0 - 0.01*fig_w, fig_bb.y0 - 0.01*fig_h],
                                    [fig_bb.x1 + 0.01*fig_w, fig_bb.y1 + 0.01*fig_h]])
        name = "figure"
        if bb.x0 < ref.x0 - 2 or bb.x1 > ref.x1 + 2 or bb.y0 < ref.y0 - 2 or bb.y1 > ref.y1 + 2:
            out_of_bounds.append({
                "text": s, "container": name,
                "exceed": {
                    "left": round(max(0, ref.x0 - bb.x0), 1),
                    "right": round(max(0, bb.x1 - ref.x1), 1),
                    "bottom": round(max(0, ref.y0 - bb.y0), 1),
                    "top": round(max(0, bb.y1 - ref.y1), 1),
                },
            })

    if verbose:
        print(f"  文字元素 {len(boxes)} 个 | 重叠 {len(overlaps)} 处 | 越界 {len(out_of_bounds)} 处")
        for o in overlaps[:12]:
            print(f"    [重叠 {o['overlap_px']}px area={o['area']}] '{o['a']}'  ×  '{o['b']}'")
        for o in out_of_bounds[:12]:
            nz = {k: v for k, v in o["exceed"].items() if v > 0}
            print(f"    [越界 {nz}] '{o['text']}' (超出 {o['container']})")
    return overlaps, out_of_bounds


def assert_clean(fig, name="figure", pad_px=1.5):
    """验收断言：有任何重叠或越界即抛错。"""
    ov, ob = detect_overlaps(fig, pad_px=pad_px, verbose=True)
    if ov or ob:
        raise AssertionError(
            f"{name}: {len(ov)} 处文字重叠, {len(ob)} 处越界"
        )
    print(f"  ✅ {name} 无重叠无越界")


def _patch_bboxes(ax):
    """取所有 patch（框、箭头）的包围盒"""
    out = []
    for p in ax.patches:
        try:
            bb = p.get_window_extent()
        except Exception:
            continue
        if bb.width > 1 and bb.height > 1:
            out.append((type(p).__name__, bb))
    return out


def _line_bboxes(ax):
    """取所有线的包围盒（matplotlib 的 line 没有 bbox，用数据路径估算）"""
    out = []
    for ln in ax.lines:
        try:
            xy = ln.get_xydata()
            if xy is None or len(xy) == 0: continue
            pts = ax.transData.transform(xy)
            x0,y0 = pts.min(axis=0); x1,y1 = pts.max(axis=0)
            from matplotlib.transforms import Bbox
            out.append((f"line[{ln.get_label()[:12]}]", Bbox([[x0,y0],[x1,y1]])))
        except Exception:
            continue
    return out


def detect_collisions(fig, pad_px=6.0, verbose=True):
    """检测文字 与 patch(框/箭头)/line 的碰撞，以及文字是否压住边框线。"""
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    problems = []
    for ax in fig.axes:
        texts = []
        for t in ax.texts + ax.get_xticklabels() + ax.get_yticklabels():
            if not t.get_visible() or not t.get_text().strip(): continue
            try: bb = t.get_window_extent(renderer=r)
            except Exception: continue
            if bb.width>0 and bb.height>0:
                texts.append((t.get_text().replace("\n"," | ")[:40], bb))
        obstacles = _patch_bboxes(ax) + _line_bboxes(ax)
        for s, tb in texts:
            for oname, ob in obstacles:
                ix = min(tb.x1, ob.x1) - max(tb.x0, ob.x0)
                iy = min(tb.y1, ob.y1) - max(tb.y0, ob.y0)
                if ix > pad_px and iy > pad_px:
                    # 完全包含的情况（文字在框内）不算碰撞，需排除
                    inside = (tb.x0 >= ob.x0-1 and tb.x1 <= ob.x1+1 and tb.y0 >= ob.y0-1 and tb.y1 <= ob.y1+1)
                    if inside:
                        continue
                    problems.append({"text": s, "hit": oname,
                                     "px": (round(ix,1), round(iy,1))})
    if verbose:
        print(f"  文字×图形 碰撞 {len(problems)} 处")
        for p in problems[:10]:
            print(f"    '{p['text']}'  ⟂  {p['hit']}  {p['px']}px")
    return problems
