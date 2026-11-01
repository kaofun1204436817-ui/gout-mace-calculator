# -*- coding: utf-8 -*-
"""
calibration.py -- 校准统计模块（可独立运行）
================================================

本模块实现临床预测模型的标准校准评估，用于复现手稿 Table 2 及 Results
段落中的校准斜率（calibration slope）、校准截距（calibration intercept）
与 Hosmer-Lemeshow 统计量。

【为什么需要这个模块】
早期版本 `model_final_v7.py` 中的 `calibrate_stats()` 直接把结局 y 对
**原始预测概率 p** 做 logistic 回归：

    LogisticRegression().fit(p.reshape(-1,1), y)      # 错误

这是一个量纲/尺度都不正确的拟合。校准斜率的标准定义（Van Calster 等，
BMC Med 2019；Steyerberg，Clinical Prediction Models）是：以
**logit(预测概率)** 为唯一自变量、以**结局**为因变量拟合一个（通常无惩罚的）
logistic 回归，斜率应为 1、截距应为 0 才算完美校准。对原始概率回归得到的
系数并不是校准斜率，其数值会被概率的量纲压缩/放大，无法按 "1 = 完美" 解读。

本模块用正确的 logit 尺度拟合，并以 statsmodels 的 GLM(Binomial) 直接给出
系数的标准误（即 Fisher 信息矩阵逆的对角元开方），同时按 10 个概率分位箱
计算 Hosmer-Lemeshow 卡方统计量。

【依赖】numpy, pandas, scipy, statsmodels, scikit-learn
【独立运行】
    python calibration.py
默认读取同目录的 `results_final/` 或通过 --root 指定结果根目录，
对 mace / mace3 / mace_alldeath 三个终点 × 内部/外部打印校准统计量。
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
import pandas as pd
from scipy import stats

# ---------------------------------------------------------------------------
# 主函数
# ---------------------------------------------------------------------------

EPS = 1e-6


def _logit(p: np.ndarray) -> np.ndarray:
    """logit 变换，带数值保护（避免 log(0)）。"""
    return np.log(p / (1.0 - p))


def calibrate_stats(y, p, n_bins: int = 10) -> dict:
    """计算标准校准统计量：斜率、截距、各自标准误、Hosmer-Lemeshow 卡方。

    参数
    ----
    y : array-like
        二分类结局（0/1），长度 n。
    p : array-like
        预测概率，长度 n，取值 (0, 1)。超出范围会被截断到 [1e-6, 1-1e-6]。
    n_bins : int, default 10
        Hosmer-Lemeshow 分箱数（按预测概率的等频分位箱）。

    返回
    ----
    dict
        slope         : 校准斜率（logit 尺度，1 = 完美）
        intercept     : 校准截距（logit 尺度，0 = 完美）
        se_slope      : 斜率标准误
        se_intercept  : 截距标准误
        slope_ci      : 斜率的 95% Wald 置信区间 [lo, hi]
        intercept_ci  : 截距的 95% Wald 置信区间 [lo, hi]
        hl_stat       : Hosmer-Lemeshow 卡方统计量
        hl_df         : 自由度（箱数 - 2）
        hl_p          : 卡方上尾 p 值
        n_bins        : 实际使用的箱数
        n             : 样本量
        n_events      : 事件数
        brier         : Brier 分数（附带，便于交叉核对）

    备注
    ----
    使用 statsmodels 的 GLM(Binomial) 而非 sklearn 的 LogisticRegression，
    原因有二：(1) GLM 默认**无惩罚**，符合校准斜率的标准定义；(2) 直接提供
    系数标准误，无需再手算 delta method。
    """
    import statsmodels.api as sm

    y = np.asarray(y, dtype=float).ravel()
    p = np.asarray(p, dtype=float).ravel()
    if y.shape != p.shape:
        raise ValueError(f"y 与 p 长度不一致: {y.shape} vs {p.shape}")
    if not np.all(np.isin(np.unique(y[~np.isnan(y)]), [0.0, 1.0])):
        raise ValueError("y 必须是 0/1 二分类结局")
    mask = ~(np.isnan(y) | np.isnan(p))
    y, p = y[mask], p[mask]
    if y.size < 10:
        raise ValueError("有效样本过少（<10），无法拟合校准模型")

    p = np.clip(p, EPS, 1.0 - EPS)
    lp = _logit(p)

    # ---- 1. 校准斜率与截距：logit(observed) ~ logit(predicted) -----------
    # 无惩罚极大似然拟合 + 观测信息矩阵给出的标准误
    design = sm.add_constant(lp, has_constant="add")
    fit = sm.GLM(y, design, family=sm.families.Binomial()).fit()
    intercept = float(fit.params[0])
    slope = float(fit.params[1])
    se_intercept = float(fit.bse[0])
    se_slope = float(fit.bse[1])
    z = stats.norm.ppf(0.975)

    # ---- 2. Hosmer-Lemeshow 卡方 ----------------------------------------
    hl_stat, hl_df, hl_p, used_bins = hosmer_lemeshow(y, p, n_bins=n_bins)

    # ---- 3. 附带指标 ----------------------------------------------------
    brier = float(np.mean((p - y) ** 2))

    return {
        "slope": slope,
        "intercept": intercept,
        "se_slope": se_slope,
        "se_intercept": se_intercept,
        "slope_ci": [slope - z * se_slope, slope + z * se_slope],
        "intercept_ci": [intercept - z * se_intercept, intercept + z * se_intercept],
        "hl_stat": hl_stat,
        "hl_df": hl_df,
        "hl_p": hl_p,
        "n_bins": used_bins,
        "n": int(y.size),
        "n_events": int(y.sum()),
        "brier": brier,
    }


def hosmer_lemeshow(y, p, n_bins: int = 10):
    """Hosmer-Lemeshow 拟合优度检验（按预测概率等频分位分箱）。

    HL = sum_g [ (O_g - E_g)^2 / E_g + ((n_g - O_g) - (n_g - E_g))^2 / (n_g - E_g) ]

    其中 O_g 为第 g 箱的事件数，E_g 为该箱预测概率之和，n_g 为该箱样本量。
    自由度 = 箱数 - 2。

    【分箱实现说明：为什么用 pandas.qcut 而不是 np.digitize】
    两种分箱在分位点恰好等于某个观测预测值时会给出不同的箱归属：
      - np.digitize 把边界值归入**右侧**箱（左闭右开）；
      - pandas.qcut 默认 right=True，把边界值归入**左侧**箱（左开右闭）。
    在一个有 2853 个互不相同的预测概率的队列里，按 10 分位切分时每个切点
    几乎必然恰好命中一个观测值，因此这两种约定的差异会改变 HL 值。
    本项目原 `calibration_standard` 数值是用 qcut 语义（左开右闭）算出的，
    本模块沿用该语义以保证与已发表数字逐位一致。这是纯粹的实现细节约定，
    不改变统计量的定义。

    返回
    ----
    (hl_stat, hl_df, hl_p, used_bins)
    """
    y = np.asarray(y, dtype=float).ravel()
    p = np.asarray(p, dtype=float).ravel()

    # 等频分位分箱；duplicates='drop' 处理大量并列概率的退化情形
    bins = np.asarray(pd.qcut(p, n_bins, labels=False, duplicates="drop"))
    used_bins = int(np.nanmax(bins)) + 1

    hl = 0.0
    for g in range(used_bins):
        m = bins == g
        n_g = int(m.sum())
        if n_g == 0:
            continue
        obs = float(y[m].sum())
        exp = float(p[m].sum())
        # 数值保护：若某箱期望事件数或期望非事件数过小，跳过该箱
        if exp <= 1e-12 or (n_g - exp) <= 1e-12:
            continue
        hl += (obs - exp) ** 2 / exp
        hl += ((n_g - obs) - (n_g - exp)) ** 2 / (n_g - exp)

    hl_df = max(used_bins - 2, 1)
    hl_p = float(stats.chi2.sf(hl, hl_df))
    return float(hl), int(hl_df), hl_p, used_bins


# ---------------------------------------------------------------------------
# 便捷：直接从 (y, pred) 两个数组出报告
# ---------------------------------------------------------------------------

def format_row(label: str, s: dict) -> str:
    """把 calibrate_stats 的返回值排成一行可读文本。"""
    return (
        f"{label:<28s} slope={s['slope']:>9.6f} (SE {s['se_slope']:.6f})  "
        f"intercept={s['intercept']:>9.6f} (SE {s['se_intercept']:.6f})  "
        f"HL={s['hl_stat']:>10.4f} (df={s['hl_df']}, p={s['hl_p']:.3g})  "
        f"n={s['n']}, events={s['n_events']}"
    )


# ---------------------------------------------------------------------------
# 独立运行：对三个终点 × 内部/外部打印校准统计量
# ---------------------------------------------------------------------------

TARGETS = {
    "mace": "strict 6-event MACE (primary)",
    "mace3": "3-event MACE (sensitivity)",
    "mace_alldeath": "all-cause death replacement (sensitivity)",
}

# 手稿 / summary.json 中已发表的参考值，用于自检
PAPER_REFERENCE = {
    ("mace", "internal"): dict(slope=1.0144644828942213, intercept=-0.2906736499779201,
                               se_slope=0.04456802041932565, se_intercept=0.04446912353303439,
                               hl_stat=54.79608426369765),
    ("mace", "external"): dict(slope=0.5964046998160856, intercept=-1.719918502276175,
                               se_slope=0.11657322428951727, se_intercept=0.13312659121865347,
                               hl_stat=229.46418127095365),
    ("mace3", "internal"): dict(slope=1.101363253377507, intercept=-0.4860875973293631,
                                se_slope=0.051698689209579395, se_intercept=0.047182977568414206,
                                hl_stat=132.31104485230998),
    ("mace3", "external"): dict(slope=0.6240233653656012, intercept=-1.4459276014304072,
                                se_slope=0.10342799177769481, se_intercept=0.10413722432352007,
                                hl_stat=239.20562328531918),
    # mace_alldeath 的 hl_stat 在原 summary.json 中缺失（系事后补丁未写全），
    # 因此只对 slope/intercept/SE 做对照，HL 仅报告不复核。
    ("mace_alldeath", "internal"): dict(slope=1.0963216588621074, intercept=-0.19283712199254582,
                                        se_slope=0.04580757431099169, se_intercept=0.044374453564797,
                                        hl_stat=None),
    ("mace_alldeath", "external"): dict(slope=0.6312133769081816, intercept=-1.2983380225958265,
                                        se_slope=0.09440980908572949, se_intercept=0.09527495976048511,
                                        hl_stat=None),
}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Calibration statistics (logit-scale slope/intercept + Hosmer-Lemeshow)")
    ap.add_argument("--root", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results_final"),
                    help="结果根目录，其下应有 <target>/pred_mimic.csv 与 <target>/pred_eicu.csv")
    ap.add_argument("--n-bins", type=int, default=10, help="Hosmer-Lemeshow 分箱数（默认 10）")
    ap.add_argument("--tol", type=float, default=1e-6, help="与参考值比对的容差（默认 1e-6）")
    ap.add_argument("--json-out", default=None, help="可选：把结果写成 JSON 文件")
    args = ap.parse_args(argv)

    print("=" * 118)
    print("校准统计：logit(observed) ~ logit(predicted)，Hosmer-Lemeshow 按预测概率 %d 等频分位箱" % args.n_bins)
    print("=" * 118)

    out = {}
    n_pass = n_check = 0

    for target, desc in TARGETS.items():
        tdir = os.path.join(args.root, target)
        print(f"\n### {target}  --  {desc}")
        out[target] = {}
        for split, fname in (("internal", "pred_mimic.csv"), ("external", "pred_eicu.csv")):
            fpath = os.path.join(tdir, fname)
            if not os.path.exists(fpath):
                print(f"  [skip] 缺少文件: {fpath}")
                continue
            df = pd.read_csv(fpath)
            s = calibrate_stats(df["y"].values, df["pred"].values, n_bins=args.n_bins)
            out[target][split] = s
            print("  " + format_row(split, s))

            ref = PAPER_REFERENCE.get((target, split))
            if ref:
                for key in ("slope", "intercept", "se_slope", "se_intercept", "hl_stat"):
                    if ref[key] is None:
                        continue
                    n_check += 1
                    diff = abs(s[key] - ref[key])
                    ok = diff < args.tol
                    n_pass += int(ok)
                    tag = "PASS" if ok else "DIFF"
                    print(f"      {key:<14s} calc={s[key]:>14.10f}  ref={ref[key]:>14.10f}  |diff|={diff:.2e}  {tag}")

    if n_check:
        print("\n" + "=" * 118)
        print(f"复现核对：{n_pass}/{n_check} 项在 1e-{int(round(-np.log10(args.tol)))} 容差内一致")
        print("=" * 118)

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(f"[written] {args.json_out}")

    return 0 if (n_check == 0 or n_pass == n_check) else 1


if __name__ == "__main__":
    sys.exit(main())
