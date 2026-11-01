# -*- coding: utf-8 -*-
"""
recalibration.py -- Platt 缩放（logistic recalibration）10 折交叉重校准
=====================================================================

复现 `results_final/mace/recalibration_analysis.json`，即手稿 Results 与
Discussion 中关于"外部概率高估三倍、但可被交叉验证重校准修正"的结论。

【方法】
Platt scaling：在**外部队列内部**再拟合一个单变量 logistic 回归

    logit(P_calibrated) = a * logit(P_raw) + b

关键点是这个重校准模型必须**交叉拟合**（cross-fitted）：eICU 的每位患者
的校准后概率，都由一个"没见过该患者结局"的重校准函数给出。做法是 10 折
分层交叉验证——每折用其余 9 折拟合 (a, b)，再对留出折预测。这样避免了
用全部数据拟合重校准函数后再在同一批数据上评估所带来的乐观偏倚。

【记录的两个阶段】
  before        : 原始预测在 eICU 上的表现（重校准前）
  after_platt_cv: 交叉拟合的 Platt 重校准之后的表现

【实现细节与历史一致性说明】
本脚本刻意使用 `LogisticRegression(C=1.0)`（scikit-learn 默认的 L2 弱惩罚）
而不是 `calibration.py` 里用的无惩罚 GLM。原因：已发表的
`recalibration_analysis.json` 就是用 sklearn 默认 C 拟合出来的，若改用无惩罚
GLM，重校准前后的 slope 会分别变成 0.5964 与 0.9722，与已归档 JSON 的
0.5882 与 0.9361 不一致（差约 0.008 与 0.036）。

这是一个**必须如实披露的内部不一致**：校准斜率（`calibration_standard`）用
的是无惩罚拟合，而重校准斜率用的是 C=1 惩罚拟合。两者在数值上差异很小
（< 0.04），不影响手稿任何定性结论，但严格来说应统一。本脚本提供
`--penalty` 开关，两种口径都能跑，默认 `c1` 以复现已发表数字。

【依赖】numpy, pandas, scipy, scikit-learn
【运行】
    python recalibration.py                    # 复现已发表 JSON
    python recalibration.py --penalty unpenalized --seed 42
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import StratifiedKFold

EPS = 1e-6


def _logit(p):
    p = np.clip(np.asarray(p, dtype=float), EPS, 1.0 - EPS)
    return np.log(p / (1.0 - p))


def _make_lr(penalty: str, seed: int):
    """按口径构造重校准用的单变量 logistic 回归器。"""
    if penalty == "c1":
        # 已发表口径：sklearn 默认 L2，C=1.0
        return LogisticRegression(C=1.0, max_iter=5000, random_state=seed)
    if penalty == "unpenalized":
        # 严格口径：无惩罚，与 calibration.py 的 calibration_standard 一致
        return LogisticRegression(C=1e6, max_iter=5000, random_state=seed)
    raise ValueError(f"未知 penalty 口径: {penalty}")


def _calibration_slope_intercept(y, p, penalty: str, seed: int):
    """在给定口径下, 用 logit(p) 单变量回归取斜率与截距。"""
    lr = _make_lr(penalty, seed).fit(_logit(p).reshape(-1, 1), y)
    return float(lr.coef_[0][0]), float(lr.intercept_[0])


def platt_cv(y, p, n_splits: int = 10, seed: int = 42, penalty: str = "c1"):
    """10 折交叉拟合的 Platt 重校准。

    返回 (p_calibrated, folds)，folds 为每折的 (a, b, n_test) 便于审计。
    """
    y = np.asarray(y, dtype=int).ravel()
    p = np.asarray(p, dtype=float).ravel()
    lp = _logit(p).reshape(-1, 1)

    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    p_cal = np.zeros_like(p, dtype=float)
    folds = []
    for k, (tr, te) in enumerate(skf.split(lp, y), start=1):
        lr = _make_lr(penalty, seed).fit(lp[tr], y[tr])
        p_cal[te] = lr.predict_proba(lp[te])[:, 1]
        folds.append({"fold": k, "a": float(lr.coef_[0][0]), "b": float(lr.intercept_[0]),
                      "n_test": int(len(te))})
    return p_cal, folds


def summarize(y, p, penalty: str, seed: int) -> dict:
    """给定一组概率, 输出与已发表 JSON 同构的指标块。"""
    y = np.asarray(y, dtype=int).ravel()
    p = np.asarray(p, dtype=float).ravel()
    slope, intercept = _calibration_slope_intercept(y, p, penalty, seed)
    return {
        "auroc": float(roc_auc_score(y, p)),
        "auprc": float(average_precision_score(y, p)),
        "brier": float(brier_score_loss(y, p)),
        "slope": slope,
        "intercept": intercept,
        "mean_pred": float(p.mean()),
    }


# 已归档的参考值（results_final/mace/recalibration_analysis.json）
REFERENCE = {
    "before": {"auroc": 0.6727988038042947, "auprc": 0.16460961296335982,
               "brier": 0.13757904294897738, "slope": 0.5882170785186345,
               "intercept": -1.7256004520619568, "mean_pred": 0.28999203055760125,
               "event_rate": 0.09771309771309772},
    "after_platt_cv": {"auroc": 0.6685336797725269, "auprc": 0.15988599916312038,
                       "brier": 0.08619372548853467, "slope": 0.9360652224844288,
                       "intercept": -0.13396776078129963, "mean_pred": 0.09761108644031775},
}


def main(argv=None):
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description="Platt 10-fold cross-validated recalibration in eICU-CRD")
    ap.add_argument("--root", default=os.path.join(here, "..", "results_final"))
    ap.add_argument("--target", default="mace")
    ap.add_argument("--pred", default=None, help="外部预测 CSV（默认 <root>/<target>/pred_eicu.csv）")
    ap.add_argument("--n-splits", type=int, default=10)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--penalty", choices=["c1", "unpenalized"], default="c1",
                    help="重校准回归的惩罚口径：c1 复现已发表数字；unpenalized 与校准斜率口径一致")
    ap.add_argument("--tol", type=float, default=1e-9)
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args(argv)

    fpath = args.pred or os.path.join(args.root, args.target, "pred_eicu.csv")
    if not os.path.exists(fpath):
        print(f"[error] 找不到外部预测文件: {fpath}", file=sys.stderr)
        return 2
    df = pd.read_csv(fpath)
    y, p = df["y"].values.astype(int), df["pred"].values.astype(float)

    print("=" * 100)
    print(f"Platt 重校准 | 文件={fpath} | {args.n_splits} 折分层交叉拟合 | seed={args.seed} | penalty={args.penalty}")
    print(f"n={len(y)}, events={y.sum()} ({y.mean():.4%})")
    print("=" * 100)

    before = summarize(y, p, args.penalty, args.seed)
    before["event_rate"] = float(y.mean())

    p_cal, folds = platt_cv(y, p, n_splits=args.n_splits, seed=args.seed, penalty=args.penalty)
    after = summarize(y, p_cal, args.penalty, args.seed)

    print("\n[每折重校准系数]")
    for f in folds:
        print(f"  fold {f['fold']:>2d}: a={f['a']:>9.6f}  b={f['b']:>9.6f}  n_test={f['n_test']}")

    print("\n[before]         原始预测（重校准前）")
    for k in ("auroc", "auprc", "brier", "slope", "intercept", "mean_pred"):
        print(f"  {k:<11s} {before[k]:>20.16f}")
    print(f"  {'event_rate':<11s} {before['event_rate']:>20.16f}")

    print("\n[after_platt_cv] 交叉拟合 Platt 重校准后")
    for k in ("auroc", "auprc", "brier", "slope", "intercept", "mean_pred"):
        print(f"  {k:<11s} {after[k]:>20.16f}")

    # ---------------- 与已发表值对照 ----------------
    n_pass = n_check = 0
    print("\n[与 recalibration_analysis.json 对照]")
    if args.penalty != "c1":
        print("  注意：penalty=unpenalized 与已发表 JSON 口径不同，下列差异属预期，不是缺陷。")
    for block, got in (("before", before), ("after_platt_cv", after)):
        for k, ref in REFERENCE[block].items():
            if k not in got:
                continue
            n_check += 1
            diff = abs(got[k] - ref)
            ok = diff < args.tol
            n_pass += int(ok)
            print(f"  {block:<14s} {k:<11s} calc={got[k]:>20.16f} ref={ref:>20.16f} "
                  f"|diff|={diff:.2e} {'PASS' if ok else 'DIFF'}")

    print("\n" + "=" * 100)
    print(f"复现核对：{n_pass}/{n_check} 项在 {args.tol:g} 容差内一致")
    print(f"重校准收益：Brier {before['brier']:.4f} -> {after['brier']:.4f} "
          f"(-{100*(before['brier']-after['brier'])/before['brier']:.1f}%)；"
          f"AUROC {before['auroc']:.4f} -> {after['auroc']:.4f}（排序基本不变）")
    print("=" * 100)

    result = {"before": before, "after_platt_cv": after,
              "config": {"n_splits": args.n_splits, "seed": args.seed, "penalty": args.penalty},
              "folds": folds}
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"[written] {args.json_out}")

    return 0 if (n_check == 0 or n_pass == n_check) else 1


if __name__ == "__main__":
    sys.exit(main())
