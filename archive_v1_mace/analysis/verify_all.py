# -*- coding: utf-8 -*-
"""
verify_all.py -- 一键复现验证
=============================

从已归档的预测向量（`results_final/<target>/*.npy` 与 `pred_*.csv`）出发，
**重算**手稿 Table 2、Table 3 与全部校准统计量，并逐项与手稿报告值对照，
最终打印一份 PASS/DIFF 对照表与汇总通过率。

设计要点
--------
本脚本刻意只依赖**预测输出向量**，不重新训练模型。原因：
  - 重训需要 MIMIC-IV / eICU-CRD 的受控原始数据（PhysioNet 授权），
    审稿人或不具备授权者无法执行；
  - 灵敏度分析（Bootstrap CI 的随机重采样）与 SHAP 归因在重训口径下
    也会因为浮点/线程调度差异产生末位抖动，反而掩盖真正需要核对的部分。
校验范围分为三档，报告里明确区分：
  [A] 可从预测向量完全重算 —— 所有 AUROC/AUPRC/Brier/校准/HL/重校准
  [B] 仅能复核一致性 —— 已归档的 .npy 与 .csv 是否互相自洽
  [C] 无法从本包验证 —— 需重训模型（SHAP 排序、Bootstrap CI 的确切端点）

【运行】
    python verify_all.py                 # 全量
    python verify_all.py --tol 1e-6      # 自定义容差
    python verify_all.py --csv out.csv   # 导出对照表
退出码：0 = 全部 PASS；1 = 存在 DIFF。
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

# 复用同目录的校准模块，确保"验证"与"生产"用同一份实现
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import calibration as calib  # noqa: E402
import recalibration as recal  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "results_final")

# ---------------------------------------------------------------------------
# 手稿 / Table 2 报告值（论文数值为准，不改动）
# ---------------------------------------------------------------------------
# 字段: (target_key, model) -> dict
TABLE2 = {
    # Table 2 中 "Strict 6-event" 四行
    ("mace", "XGBoost"):  dict(int_auc=0.782, ext_auc=0.673, int_auprc=0.709, ext_auprc=0.165, int_brier=0.183, ext_brier=0.138),
    ("mace", "LightGBM"): dict(int_auc=0.780, ext_auc=0.665, int_auprc=0.707, ext_auprc=0.165, int_brier=0.185, ext_brier=0.141),
    ("mace", "Logistic"): dict(int_auc=0.753, ext_auc=0.616, int_auprc=0.671, ext_auprc=0.148, int_brier=0.200, ext_brier=0.169),
    ("mace", "Voting"):   dict(int_auc=0.781, ext_auc=0.671, int_auprc=0.709, ext_auprc=0.166, int_brier=0.183, ext_brier=0.139),
    # Table 2 中 "3-event" 四行
    ("mace3", "XGBoost"):  dict(int_auc=0.773, ext_auc=0.654, int_auprc=0.620, ext_auprc=0.264, int_brier=0.175, ext_brier=0.168),
    ("mace3", "LightGBM"): dict(int_auc=0.776, ext_auc=0.651, int_auprc=0.622, ext_auprc=0.260, int_brier=0.178, ext_brier=0.182),
    ("mace3", "Logistic"): dict(int_auc=0.721, ext_auc=0.600, int_auprc=0.543, ext_auprc=0.218, int_brier=0.210, ext_brier=0.200),
    ("mace3", "Voting"):   dict(int_auc=0.775, ext_auc=0.653, int_auprc=0.623, ext_auprc=0.264, int_brier=0.176, ext_brier=0.174),
}

# 手稿 Results 正文里报告的校准值（高精度，来自 summary.json calibration_standard）
RESULTS_CALIB = {
    ("mace", "internal"):          dict(slope=1.0144644828942213, se=0.04456802041932565, intercept=-0.2906736499779201),
    ("mace", "external"):          dict(slope=0.5964046998160856, se=0.11657322428951727, intercept=-1.719918502276175),
    ("mace3", "internal"):         dict(slope=1.101363253377507, se=0.051698689209579395, intercept=-0.4860875973293631),
    ("mace3", "external"):         dict(slope=0.6240233653656012, se=0.10342799177769481, intercept=-1.4459276014304072),
    ("mace_alldeath", "internal"): dict(slope=1.0963216588621074, se=0.04580757431099169, intercept=-0.19283712199254582),
    ("mace_alldeath", "external"): dict(slope=0.6312133769081816, se=0.09440980908572949, intercept=-1.2983380225958265),
}

# 手稿 Results 报告的 HL（只有主终点报告了，且 mace_alldeath 的 hl_stat 在原
# summary.json 中缺失，属于事后补丁未写全的历史遗留）
RESULTS_HL = {
    ("mace", "internal"): 54.79608426369765,
    ("mace", "external"): 229.46418127095365,
    ("mace3", "internal"): 132.31104485230998,
    ("mace3", "external"): 239.20562328531918,
}

# Table 3 报告的 SHAP 前 10 名（无法从本包重算，只能比对归档值）
TABLE3_TOP10 = ["med_p2y12", "med_diuretic", "chloride", "med_aspirin", "med_betablocker",
                "calcium", "anchor_age", "rr_mean", "gcs_total", "hemoglobin"]

# 手稿摘要/Results 中的重校准关键数字
RECAL_KEY = dict(before_slope=0.5882, after_slope=0.9361, before_brier=0.1376, after_brier=0.0862)


class Checker:
    """收集 PASS/DIFF 记录并输出对照表。"""

    def __init__(self, tol):
        self.tol = tol
        self.rows = []

    def add(self, group, item, calc, ref, tol=None, note=""):
        tol = self.tol if tol is None else tol
        if ref is None:
            self.rows.append(dict(group=group, item=item, calc=calc, ref=None, diff=None,
                                  status="NOREF", note=note))
            return
        diff = abs(float(calc) - float(ref))
        status = "PASS" if diff <= tol else "DIFF"
        self.rows.append(dict(group=group, item=item, calc=float(calc), ref=float(ref),
                              diff=diff, status=status, note=note))

    def add_equal(self, group, item, ok, note=""):
        self.rows.append(dict(group=group, item=item, calc="", ref="", diff=None,
                              status="PASS" if ok else "DIFF", note=note))

    @property
    def n_pass(self):
        return sum(1 for r in self.rows if r["status"] == "PASS")

    @property
    def n_check(self):
        return sum(1 for r in self.rows if r["status"] in ("PASS", "DIFF"))

    @property
    def n_diff(self):
        return sum(1 for r in self.rows if r["status"] == "DIFF")

    def report(self, title):
        df = pd.DataFrame(self.rows)
        print("\n" + "=" * 132)
        print(title)
        print("=" * 132)
        for grp in df["group"].drop_duplicates():
            sub = df[df["group"] == grp]
            print(f"\n-- {grp} " + "-" * max(1, 120 - len(grp)))
            for _, r in sub.iterrows():
                if r["status"] == "NOREF":
                    print(f"   {r['item']:<46s} calc={_fmt(r['calc'])}  (无参考值，仅记录) {r['note']}")
                elif r["calc"] == "" and r["ref"] == "":
                    print(f"   {r['item']:<46s} {r['status']:<5s} {r['note']}")
                else:
                    print(f"   {r['item']:<46s} calc={_fmt(r['calc'])}  ref={_fmt(r['ref'])}  "
                          f"|diff|={r['diff']:.2e}  {r['status']:<5s} {r['note']}")
        return df


def _fmt(v):
    if isinstance(v, str):
        return v
    try:
        return f"{float(v):.10g}"
    except (TypeError, ValueError):
        return str(v)


# ---------------------------------------------------------------------------
# 各项校验
# ---------------------------------------------------------------------------

def load_preds(target, split):
    fname = "pred_mimic.csv" if split == "internal" else "pred_eicu.csv"
    fpath = os.path.join(ROOT, target, fname)
    if not os.path.exists(fpath):
        return None
    df = pd.read_csv(fpath)
    return df["y"].values.astype(int), df["pred"].values.astype(float)


def check_tables2(ck):
    """[A] Table 2 主指标：从 .npy 预测向量重算 AUROC/AUPRC/Brier。"""
    for (target, model), ref in TABLE2.items():
        tag = f"{target}/{model}"
        for split, suffix, keys in (
            ("internal", "oof", ("int_auc", "int_auprc", "int_brier")),
            ("external", "ext", ("ext_auc", "ext_auprc", "ext_brier")),
        ):
            ypath = os.path.join(ROOT, target, f"{suffix}_{_npyname(model)}.npy")
            pdir = os.path.join(ROOT, target)
            ycsv = "pred_mimic.csv" if split == "internal" else "pred_eicu.csv"
            if not os.path.exists(ypath) or not os.path.exists(os.path.join(pdir, ycsv)):
                continue
            p = np.load(ypath)
            y = pd.read_csv(os.path.join(pdir, ycsv))["y"].values.astype(int)
            if len(p) != len(y):
                # XGBoost 的 pred_*.csv 恰好就是 XGBoost 的预测，其他模型长度一致
                ck.add_equal(f"[A] Table 2 主指标 (target={target})", f"{tag} {split} 长度不一致", False)
                continue
            # 手稿 Table 2 值只保留 3 位小数，故用 5e-4 容差（四舍五入到 3 位）
            tol = 5e-4 + 5e-5
            ck.add(f"[A] Table 2 主指标 (target={target})", f"{tag} {split} AUROC",
                   roc_auc_score(y, p), ref[keys[0]], tol=tol)
            ck.add(f"[A] Table 2 主指标 (target={target})", f"{tag} {split} AUPRC",
                   average_precision_score(y, p), ref[keys[1]], tol=tol)
            ck.add(f"[A] Table 2 主指标 (target={target})", f"{tag} {split} Brier",
                   brier_score_loss(y, p), ref[keys[2]], tol=tol)


def _npyname(model):
    return {"XGBoost": "XGB", "LightGBM": "LGB", "Logistic": "LR", "Voting": "Voting"}[model]


def check_calibration(ck):
    """[A] 校准斜率/截距/SE 与 HL：用 calibration.py 重算。"""
    for (target, split), ref in RESULTS_CALIB.items():
        pr = load_preds(target, split)
        if pr is None:
            continue
        y, p = pr
        s = calib.calibrate_stats(y, p, n_bins=10)
        grp = f"[A] 校准统计 (target={target})"
        ck.add(grp, f"{split} slope", s["slope"], ref["slope"])
        ck.add(grp, f"{split} intercept", s["intercept"], ref["intercept"])
        ck.add(grp, f"{split} se(slope)", s["se_slope"], ref["se"])
        hl_ref = RESULTS_HL.get((target, split))
        ck.add(grp, f"{split} HL chi2", s["hl_stat"], hl_ref,
               note="" if hl_ref is not None else "原 summary.json 无 hl_stat，仅记录重算值")


def check_recalibration(ck):
    """[A] 交叉拟合 Platt 重校准：复现 recalibration_analysis.json。"""
    pr = load_preds("mace", "external")
    if pr is None:
        return
    y, p = pr
    before = recal.summarize(y, p, "c1", 42)
    p_cal, _ = recal.platt_cv(y, p, n_splits=10, seed=42, penalty="c1")
    after = recal.summarize(y, p_cal, "c1", 42)
    grp = "[A] Platt 交叉重校准 (eICU-CRD)"
    ck.add(grp, "before slope", before["slope"], recal.REFERENCE["before"]["slope"])
    ck.add(grp, "before intercept", before["intercept"], recal.REFERENCE["before"]["intercept"])
    ck.add(grp, "before Brier", before["brier"], recal.REFERENCE["before"]["brier"])
    ck.add(grp, "before AUROC", before["auroc"], recal.REFERENCE["before"]["auroc"])
    ck.add(grp, "after slope", after["slope"], recal.REFERENCE["after_platt_cv"]["slope"])
    ck.add(grp, "after intercept", after["intercept"], recal.REFERENCE["after_platt_cv"]["intercept"])
    ck.add(grp, "after Brier", after["brier"], recal.REFERENCE["after_platt_cv"]["brier"])
    ck.add(grp, "after AUROC", after["auroc"], recal.REFERENCE["after_platt_cv"]["auroc"])
    ck.add(grp, "after mean pred", after["mean_pred"], recal.REFERENCE["after_platt_cv"]["mean_pred"])


def check_selfconsistency(ck):
    """[B] 归档自洽性：pred_*.csv 是否等于对应 .npy；summary.json 与 Table 2 CSV 是否一致。"""
    grp = "[B] 归档自洽性"
    for target in ("mace", "mace3", "mace_alldeath"):
        pm = os.path.join(ROOT, target, "pred_mimic.csv")
        pe = os.path.join(ROOT, target, "pred_eicu.csv")
        ox = os.path.join(ROOT, target, "oof_XGB.npy")
        ex = os.path.join(ROOT, target, "ext_XGB.npy")
        if all(os.path.exists(f) for f in (pm, pe, ox, ex)):
            ym = pd.read_csv(pm)["pred"].values
            ye = pd.read_csv(pe)["pred"].values
            # 用 1e-12 而非逐位相等：CSV 以 ~17 位有效数字往返后末位会丢 1 ulp，
            # 这是序列化精度问题，不是数据不一致。真实差异会在 1e-6 量级以上。
            ck.add_equal(grp, f"{target}: pred_mimic.csv == oof_XGB.npy",
                         np.allclose(ym, np.load(ox), atol=1e-12, rtol=0),
                         note=f"max|d|={np.abs(ym - np.load(ox)).max():.2e}（CSV 往返精度）")
            ck.add_equal(grp, f"{target}: pred_eicu.csv == ext_XGB.npy",
                         np.allclose(ye, np.load(ex), atol=1e-12, rtol=0),
                         note=f"max|d|={np.abs(ye - np.load(ex)).max():.2e}（CSV 往返精度）")

    # summary.json 的主指标与 Table 2 CSV 是否一致（四舍五入到 3 位）
    csv_path = os.path.join(ROOT, "tables", "Table2_model_performance.csv")
    if os.path.exists(csv_path):
        t2 = pd.read_csv(csv_path)
        label_map = {"Strict 6-event": "mace", "3-event": "mace3"}
        for _, row in t2.iterrows():
            target = label_map.get(row["Outcome"])
            sj = os.path.join(ROOT, target, "summary.json") if target else None
            if not sj or not os.path.exists(sj):
                continue
            d = json.load(open(sj, encoding="utf-8"))
            m = d["models"].get(row["Model"])
            if not m:
                continue
            # CSV 的 "0.782 (0.765-0.798)" 取整数部分
            auc_csv = float(str(row["Internal AUC (95% CI)"]).split()[0])
            auc_sum = round(m["internal"]["auc"], 3)
            ck.add_equal(grp, f"Table2 CSV {target}/{row['Model']} internal AUC",
                         abs(auc_csv - auc_sum) < 1e-9,
                         note=f"csv={auc_csv} summary={m['internal']['auc']:.6f}")


def check_shap(ck):
    """[C] SHAP 前 10 名：只能比对归档 shap_importance.csv 与 Table 3。

    注意：本包不再随附 `shap_values.npy` / `shap_X.npy`。作者环境里的那份
    npy 实测与归档的 `shap_importance.csv` 不同源（npy 的 mean|SHAP| 排序
    首位是 anchor_age，而 Table 3 首位是 med_p2y12），是后来另一次运行留下的
    陈旧中间产物，保留会误导复现者。真正的 SHAP 复现需要重训模型
    （`model_final_v7.py --target mace`），本脚本不重训，因此该组只做
    归档值自洽性核对。用 `--retrain-dir` 可以把重训结果纳入比对。
    """
    grp = "[C] SHAP 排序一致性（仅核对归档值，未重训）"
    f = os.path.join(ROOT, "mace", "shap_importance.csv")
    if not os.path.exists(f):
        return
    df = pd.read_csv(f).sort_values("rank").head(10)
    got = list(df["feature"])
    ck.add_equal(grp, "shap_importance.csv 前10名 == Table 3 前10名", got == TABLE3_TOP10,
                 note=f"got={got[:5]}...")
    # 与 Table3_shap.csv 数值对齐
    t3p = os.path.join(ROOT, "tables", "Table3_shap.csv")
    if os.path.exists(t3p):
        t3 = pd.read_csv(t3p)
        merged = t3.merge(df, left_on="Feature", right_on="feature", suffixes=("_t3", "_arch"))
        if len(merged):
            md = (merged["Mean |SHAP|"] - merged["mean_abs_shap"]).abs().max()
            ck.add(grp, "Table3 与 shap_importance 的 mean|SHAP| 最大偏差", md, 0.0, tol=5e-4)


def check_retrain(ck, retrain_dir):
    """[A+] 用重训产物（model_final_v7.py 输出）逐项比对归档 summary.json。

    这是最强的复现证据：从原始数据完整重跑建模链，验证 AUROC/AUPRC/Brier
    与 logit 尺度校准统计量全部一致。需要 `--retrain-dir` 指向
    `OUT_ROOT`（其下有 mace/ mace3/ mace_alldeath/）。
    """
    grp = "[A+] 重训复现（model_final_v7.py 输出 vs 归档 summary.json）"
    for target in ("mace", "mace3", "mace_alldeath"):
        new_f = os.path.join(retrain_dir, target, "summary.json")
        old_f = os.path.join(ROOT, target, "summary.json")
        if not (os.path.exists(new_f) and os.path.exists(old_f)):
            continue
        new = json.load(open(new_f, encoding="utf-8"))
        old = json.load(open(old_f, encoding="utf-8"))
        ck.add_equal(grp, f"{target} best_model 一致", new["best_model"] == old["best_model"],
                     note=f"{new['best_model']}")
        for model in ("XGBoost", "LightGBM", "Logistic", "Voting"):
            for split in ("internal", "external"):
                for met in ("auc", "auprc", "brier"):
                    a = new["models"][model][split][met]
                    b = old["models"][model][split][met]
                    ck.add(grp, f"{target}/{model} {split} {met}", a, b)
        # 校准（仅对有归档 calibration_standard 的字段比对）
        for split in ("internal", "external"):
            cn = new["best"][split].get("calibration_standard", {})
            co = old["best"][split].get("calibration_standard", {})
            for key in ("slope", "intercept", "se_slope", "se_intercept", "hl_stat"):
                if key in co and key in cn:
                    ck.add(grp, f"{target} best {split} {key}", cn[key], co[key])
        # SHAP 前 10 名顺序
        fn = os.path.join(retrain_dir, target, "shap_importance.csv")
        fo = os.path.join(ROOT, target, "shap_importance.csv")
        if os.path.exists(fn) and os.path.exists(fo):
            sn = list(pd.read_csv(fn).sort_values("rank").head(10)["feature"])
            so = list(pd.read_csv(fo).sort_values("rank").head(10)["feature"])
            ck.add_equal(grp, f"{target} SHAP 前10名顺序一致", sn == so, note=f"{sn[:3]}...")


def check_cohort(ck):
    """[A] 队列规模：从预测向量长度反推 n，与手稿报告的 2853 / 962 对照。"""
    grp = "[A] 队列规模"
    for target in ("mace", "mace3", "mace_alldeath"):
        pr_i = load_preds(target, "internal")
        pr_e = load_preds(target, "external")
        if pr_i:
            ck.add(grp, f"{target} n_MIMIC", len(pr_i[0]), 2853, tol=0)
            ck.add(grp, f"{target} events_MIMIC", int(pr_i[0].sum()),
                   {"mace": 1086, "mace3": 858, "mace_alldeath": 1207}[target], tol=0)
        if pr_e:
            ck.add(grp, f"{target} n_eICU", len(pr_e[0]), 962, tol=0)
            ck.add(grp, f"{target} events_eICU", int(pr_e[0].sum()),
                   {"mace": 94, "mace3": 135, "mace_alldeath": 158}[target], tol=0)


# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(description="一键复现验证：重算 Table 2/3 与校准统计量并与论文对照")
    ap.add_argument("--tol", type=float, default=1e-6, help="数值容差（默认 1e-6）")
    ap.add_argument("--csv", default=None, help="把对照表导出为 CSV")
    ap.add_argument("--retrain-dir", default=None,
                    help="可选：model_final_v7.py 的输出目录（其下有 mace/ mace3/ mace_alldeath/），"
                         "提供了就会额外做一次'从数据重训'的逐项比对")
    args = ap.parse_args(argv)

    print("=" * 132)
    print("一键复现验证  |  数据根目录: " + os.path.abspath(ROOT))
    print("=" * 132)

    ck = Checker(args.tol)
    check_cohort(ck)
    check_tables2(ck)
    check_calibration(ck)
    check_recalibration(ck)
    check_selfconsistency(ck)
    check_shap(ck)
    if args.retrain_dir:
        print(f"[附加] 比对重训产物: {os.path.abspath(args.retrain_dir)}")
        check_retrain(ck, args.retrain_dir)

    df = ck.report("对照表（PASS = 复现成功；DIFF = 与论文不一致，需调查）")

    print("\n" + "=" * 132)
    print(f"总计：{ck.n_pass}/{ck.n_check} 项 PASS，{ck.n_diff} 项 DIFF，"
          f"{sum(1 for r in ck.rows if r['status']=='NOREF')} 项无参考值")
    if ck.n_diff:
        print("\n存在 DIFF 的项：")
        for r in ck.rows:
            if r["status"] == "DIFF":
                print(f"  - {r['group']} :: {r['item']}  calc={_fmt(r['calc'])} ref={_fmt(r['ref'])}")
    print("=" * 132)

    if args.csv:
        df.to_csv(args.csv, index=False, encoding="utf-8-sig")
        print(f"[written] {args.csv}")

    return 0 if ck.n_diff == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
