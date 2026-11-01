# -*- coding: utf-8 -*-
"""
T4 最终建模 V7（校准统计修正版）
================================

相对原版 `model_final_v7.py` 的**唯一实质改动**是 `calibrate_stats()`：

  原版（错误）:  LogisticRegression().fit(p.reshape(-1,1), y)
                 —— 结局对**原始预测概率**回归，系数不是校准斜率。
  本版（正确）:  logit(observed) ~ logit(predicted) 的无惩罚 logistic 回归，
                 并给出斜率/截距的标准误与 Hosmer-Lemeshow 卡方。

其余建模、交叉验证、外部验证、SHAP 流程与随机种子均未改动，因此重跑后
所有判别力指标（AUROC/AUPRC/Brier）与论文 Table 2 逐位一致，校准统计量也与
已发表的 `calibration_standard` 逐位一致（差异 < 1e-8，见 verify_all.py）。

【产出】results_final/<target>/
    summary.json          主结果（含 calibration_standard）
    pred_mimic.csv        最优模型内部 OOF 预测
    pred_eicu.csv         最优模型外部预测
    oof_<M>.npy / ext_<M>.npy   四个模型族的预测向量
    shap_importance.csv   SHAP 重要性排序

【用法】
    python model_final_v7.py --target mace
    python model_final_v7.py --target mace3
    python model_final_v7.py --target mace_alldeath

【设计约束】
- 仅训练集学习缺失指示器 / 插补器 / 标准化；外部验证不接触 MIMIC 测试折。
- 类别不平衡用 scale_pos_weight 校正，这会把原始输出概率整体上移约
  log(负正比)，是外部校准截距偏负的主因（见手稿 Methods）。
"""
import os, json, argparse, warnings
import numpy as np
import pandas as pd
from sklearn.model_selection import RepeatedStratifiedKFold
from sklearn.metrics import (roc_auc_score, average_precision_score, brier_score_loss,
                             roc_curve, precision_recall_curve)
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.calibration import calibration_curve
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import VotingClassifier
from xgboost import XGBClassifier
from lightgbm import LGBMClassifier
import shap

warnings.filterwarnings("ignore")
RNG = 42
np.random.seed(RNG)
BASE = os.path.dirname(os.path.abspath(__file__))
OUT_ROOT = os.environ.get("OUT_ROOT", os.path.join(BASE, "results_final"))


def _resolve_data_dir():
    """定位模型数据目录。优先级：环境变量 DATA_DIR > ./data > ../04_模型/data。

    研究用的 .csv 由 p*.sql 在 PhysioNet 受限数据上生成，不在本包内分发；
    复现者需要先按 README 申请数据并跑完数据管线。
    """
    cands = [os.environ.get("DATA_DIR"),
             os.path.join(BASE, "data"),
             os.path.abspath(os.path.join(BASE, "..", "..", "04_模型", "data"))]
    for c in cands:
        if c and os.path.isfile(os.path.join(c, "mimic_model_data.csv")) \
                and os.path.isfile(os.path.join(c, "eicu_model_data.csv")):
            return c
    return os.environ.get("DATA_DIR") or os.path.join(BASE, "data")


DATA_DIR = _resolve_data_dir()
os.makedirs(OUT_ROOT, exist_ok=True)

# 与 calibration.py 保持同一份实现，避免"生产"与"验证"两条路径漂移
try:
    from calibration import calibrate_stats as _calibrate_stats
    _HAVE_CALIB_MODULE = True
except ImportError:  # 单文件拷走时也能跑
    _HAVE_CALIB_MODULE = False


def clean_physio(df, feats):
    X = df[feats].copy()
    if "gender" in X.columns:
        X["gender"] = X["gender"].map({"M":1,"F":0,"Male":1,"Female":0,"male":1,"female":0})
        X["gender"] = pd.to_numeric(X["gender"], errors="coerce")
    for col in ["hr_min","hr_max","hr_mean","hr_std"]:
        if col in X.columns:
            X.loc[X[col] < 20, col] = np.nan
            X.loc[X[col] > 250, col] = np.nan
    for col in ["sbp_mean","sbp_min","sbp_max","dbp_mean","dbp_min","map_mean","map_min","map_max"]:
        if col in X.columns:
            X.loc[X[col] < 20, col] = np.nan
            X.loc[X[col] > 260, col] = np.nan
    for col in ["spo2_min","spo2_mean"]:
        if col in X.columns:
            X.loc[X[col] < 40, col] = np.nan
            X.loc[X[col] > 100, col] = np.nan
    for c in X.columns:
        X[c] = pd.to_numeric(X[c], errors="coerce")
    return X


def add_missing_indicators(X, ind_cols, fit=False):
    if fit:
        miss_rate = X.isna().mean()
        ind_cols = [c for c in X.columns if 0.03 < miss_rate[c] < 0.5]
        for c in ind_cols:
            X[f"{c}_miss"] = X[c].isna().astype(int)
        return X, ind_cols
    for c in ind_cols:
        if c in X.columns:
            X[f"{c}_miss"] = X[c].isna().astype(int)
        else:
            X[f"{c}_miss"] = 1
    return X, ind_cols


def bootstrap_ci(y, p, n_boot=1000, seed=RNG):
    rng = np.random.default_rng(seed)
    aucs, aps, briers = [], [], []
    y = np.asarray(y); p = np.asarray(p)
    n = len(y)
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        if len(np.unique(y[idx])) < 2:
            continue
        aucs.append(roc_auc_score(y[idx], p[idx]))
        aps.append(average_precision_score(y[idx], p[idx]))
        briers.append(brier_score_loss(y[idx], p[idx]))
    def q(a):
        return [float(np.percentile(a, 2.5)), float(np.percentile(a, 97.5))]
    return q(aucs), q(aps), q(briers)


# ===========================================================================
# 【核心修正】校准统计量
# ===========================================================================
def calibrate_stats(y, p, n_bins=10):
    """标准校准统计量：斜率、截距、各自标准误、Hosmer-Lemeshow 卡方。

    修正说明（对应审稿意见 R3-M3）
    ------------------------------
    原实现把结局 y 直接对**原始预测概率 p** 做 logistic 回归：

        slope = LogisticRegression(C=1e6).fit(p.reshape(-1,1), y).coef_[0][0]

    这不是校准斜率。校准斜率的标准定义是把模型当作一个"偏移项 + 斜率项"
    重新拟合：

        logit(P(Y=1)) = a + b * logit(p_model)

    其中 b 即校准斜率（完美校准时为 1），a 即校准截距（完美校准时为 0）。
    对原始概率 p 回归得到的 b 是另一个量，且强烈依赖 p 的尺度范围，无法
    按 "1 = 完美" 解读 —— 在原 summary.json 里这个错误口径给出的内部斜率是
    4.87（对照正确值 1.01），外部是 2.97（对照 0.60），明显是伪值。

    同时原实现**完全没有** Hosmer-Lemeshow 统计量，而手稿声称计算了它，
    造成"数值在 JSON 里、生成脚本不存在"的可复现性缺口。

    返回值
    ------
    dict，键为扁平化的校准量（slope/intercept/se_*/hl_*/n_bins），
    另附带 `curve` 子字典保存 10 分位校准曲线的 (predicted, observed) 点，
    供 Figure 3 使用。
    """
    if _HAVE_CALIB_MODULE:
        s = _calibrate_stats(y, p, n_bins=n_bins)
        y_arr = np.asarray(y, dtype=float)
        p_arr = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
        frac, mean_pred = calibration_curve(y_arr, p_arr, n_bins=n_bins, strategy="quantile")
        s["curve"] = {"predicted": [float(v) for v in mean_pred],
                      "observed": [float(v) for v in frac],
                      "n_bins": int(len(frac))}
        return s

    # ---- 兜底实现（calibration.py 不在同目录时）---------------------------
    import statsmodels.api as sm
    from scipy import stats as _st

    y = np.asarray(y, dtype=float).ravel()
    p = np.clip(np.asarray(p, dtype=float).ravel(), 1e-6, 1 - 1e-6)
    lp = np.log(p / (1 - p))
    fit = sm.GLM(y, sm.add_constant(lp), family=sm.families.Binomial()).fit()
    intercept, slope = float(fit.params[0]), float(fit.params[1])
    se_intercept, se_slope = float(fit.bse[0]), float(fit.bse[1])

    bins = np.asarray(pd.qcut(p, n_bins, labels=False, duplicates="drop"))
    used = int(np.nanmax(bins)) + 1
    hl = 0.0
    for g in range(used):
        m = bins == g
        n_g = int(m.sum())
        if n_g == 0:
            continue
        o, e = float(y[m].sum()), float(p[m].sum())
        if e <= 1e-12 or (n_g - e) <= 1e-12:
            continue
        hl += (o - e) ** 2 / e + ((n_g - o) - (n_g - e)) ** 2 / (n_g - e)
    hl_df = max(used - 2, 1)
    z = _st.norm.ppf(0.975)

    frac, mean_pred = calibration_curve(y, p, n_bins=n_bins, strategy="quantile")
    return {
        "slope": slope, "intercept": intercept,
        "se_slope": se_slope, "se_intercept": se_intercept,
        "slope_ci": [slope - z * se_slope, slope + z * se_slope],
        "intercept_ci": [intercept - z * se_intercept, intercept + z * se_intercept],
        "hl_stat": float(hl), "hl_df": int(hl_df),
        "hl_p": float(_st.chi2.sf(hl, hl_df)),
        "n_bins": used, "n": int(y.size), "n_events": int(y.sum()),
        "brier": float(np.mean((p - y) ** 2)),
        "curve": {"predicted": [float(v) for v in mean_pred],
                  "observed": [float(v) for v in frac],
                  "n_bins": int(len(frac))},
    }


def net_benefit(y, p, ths):
    y = np.asarray(y); p = np.asarray(p)
    nb = np.zeros(len(ths))
    for i, t in enumerate(ths):
        tp = ((p >= t) & (y == 1)).sum()
        fp = ((p >= t) & (y == 0)).sum()
        nb[i] = tp / len(y) - fp / len(y) * t / (1 - t)
    return nb


def run_target(target, label):
    print(f"\n===== {label} =====")
    mimic = pd.read_csv(os.path.join(DATA_DIR, "mimic_model_data.csv"))
    eicu = pd.read_csv(os.path.join(DATA_DIR, "eicu_model_data.csv"))
    common = [c for c in mimic.columns if c in eicu.columns]
    drop_meta = {"patientunitstayid","subject_id","hadm_id","stay_id","mace","mace3","mace_alldeath",
                 "ev_ami","ev_stroke","ev_cardiac_death","ev_cardshk","ev_malarr","ev_hfacu",
                 "ev_death","hospital_expire_flag","n_events","intime","prior_mi","prior_stroke","prior_hf",
                 "is_gout_dx","is_hyperuricemia_dx","is_ckd_dx","med_urate","admission_type","mace_wide"}
    ALL = sorted([c for c in common if c not in drop_meta])
    miss_m = mimic[ALL].isna().mean(); miss_e = eicu[ALL].isna().mean()
    FEATS = [c for c in ALL if miss_m[c] <= 0.5 and miss_e[c] <= 0.5]
    print("features:", len(FEATS))

    Xm_raw = clean_physio(mimic, FEATS)
    Xe_raw = clean_physio(eicu, FEATS)
    Xm_raw, ind_cols = add_missing_indicators(Xm_raw, None, fit=True)
    Xe_raw, _ = add_missing_indicators(Xe_raw, ind_cols, fit=False)
    ym = mimic[target].values.astype(int)
    ye = eicu[target].values.astype(int)
    print("MIMIC events:", ym.sum(), f"({ym.mean():.4f})", "eICU events:", ye.sum(), f"({ye.mean():.4f})")

    # Logistic: median impute + scale (fit train)
    imp = SimpleImputer(strategy="median")
    Xm_lr = imp.fit_transform(Xm_raw)
    Xe_lr = imp.transform(Xe_raw)
    sc = StandardScaler().fit(Xm_lr)
    Xm_lr = sc.transform(Xm_lr); Xe_lr = sc.transform(Xe_lr)

    # Trees can use NaN natively
    Xm_tree = Xm_raw.values.astype(float); Xe_tree = Xe_raw.values.astype(float)
    w = (1 - ym.mean()) / ym.mean()

    def make_models():
        xgb = XGBClassifier(n_estimators=250, max_depth=5, learning_rate=0.03,
                            subsample=0.8, colsample_bytree=0.7, scale_pos_weight=w,
                            base_score=0.5, eval_metric="auc", random_state=RNG,
                            verbosity=0, n_jobs=4)
        lgb = LGBMClassifier(n_estimators=250, max_depth=5, learning_rate=0.03,
                             subsample=0.8, colsample_bytree=0.7, scale_pos_weight=w,
                             random_state=RNG, verbose=-1, n_jobs=4)
        lr = LogisticRegression(max_iter=2000, C=0.5, class_weight="balanced", random_state=RNG)
        vot = VotingClassifier([("xgb", xgb), ("lgb", lgb)], voting="soft", weights=[1,1])
        return {"XGBoost": xgb, "LightGBM": lgb, "Logistic": lr, "Voting": vot}

    cv = RepeatedStratifiedKFold(n_splits=5, n_repeats=5, random_state=RNG)
    results = {}
    oofs = {}
    ext_preds = {}
    for name, base in make_models().items():
        oof_parts = np.zeros_like(ym, dtype=float)
        ext_parts = np.zeros_like(ye, dtype=float)
        for rep_i, (tr, te) in enumerate(cv.split(Xm_tree, ym)):
            mm = None
            if name in ("XGBoost", "LightGBM"):
                mm = base.__class__()
                mm.set_params(**base.get_params())
                mm.fit(Xm_tree[tr], ym[tr])
                oof_parts[te] += mm.predict_proba(Xm_tree[te])[:,1]
                ext_parts += mm.predict_proba(Xe_tree)[:,1]
            elif name == "Logistic":
                mm = LogisticRegression(max_iter=2000, C=0.5, class_weight="balanced", random_state=RNG)
                mm.fit(Xm_lr[tr], ym[tr])
                oof_parts[te] += mm.predict_proba(Xm_lr[te])[:,1]
                ext_parts += mm.predict_proba(Xe_lr)[:,1]
            else:  # Voting
                xgb = XGBClassifier(n_estimators=250, max_depth=5, learning_rate=0.03,
                                    subsample=0.8, colsample_bytree=0.7, scale_pos_weight=w,
                                    base_score=0.5, eval_metric="auc", random_state=RNG,
                                    verbosity=0, n_jobs=4)
                lgb = LGBMClassifier(n_estimators=250, max_depth=5, learning_rate=0.03,
                                     subsample=0.8, colsample_bytree=0.7, scale_pos_weight=w,
                                     random_state=RNG, verbose=-1, n_jobs=4)
                mm = VotingClassifier([("xgb", xgb), ("lgb", lgb)], voting="soft", weights=[1,1])
                mm.fit(Xm_tree[tr], ym[tr])
                oof_parts[te] += mm.predict_proba(Xm_tree[te])[:,1]
                ext_parts += mm.predict_proba(Xe_tree)[:,1]
        oof = oof_parts / 5.0
        ext = ext_parts / 25.0  # 5 folds x 5 repeats = 25 fits
        oofs[name] = oof; ext_preds[name] = ext
        auc_ci, ap_ci, brier_ci = bootstrap_ci(ym, oof)
        ext_auc_ci, ext_ap_ci, ext_brier_ci = bootstrap_ci(ye, ext)
        metrics = {
            "internal": {"auc": float(roc_auc_score(ym, oof)), "auc_ci": auc_ci,
                         "auprc": float(average_precision_score(ym, oof)), "auprc_ci": ap_ci,
                         "brier": float(brier_score_loss(ym, oof)), "brier_ci": brier_ci},
            "external": {"auc": float(roc_auc_score(ye, ext)), "auc_ci": ext_auc_ci,
                         "auprc": float(average_precision_score(ye, ext)), "auprc_ci": ext_ap_ci,
                         "brier": float(brier_score_loss(ye, ext)), "brier_ci": ext_brier_ci}
        }
        # 【修正点】logit 尺度校准 + HL；不再写入错误的 raw-P 拟合
        metrics["internal"]["calibration_standard"] = calibrate_stats(ym, oof)
        metrics["external"]["calibration_standard"] = calibrate_stats(ye, ext)
        results[name] = metrics
        ci = metrics["internal"]["calibration_standard"]
        ce = metrics["external"]["calibration_standard"]
        print(f"[{name}] 内AUC={metrics['internal']['auc']:.4f} 外AUC={metrics['external']['auc']:.4f} "
              f"外AUPRC={metrics['external']['auprc']:.4f} 外Brier={metrics['external']['brier']:.4f} | "
              f"内校准 slope={ci['slope']:.4f} int={ci['intercept']:.4f} | "
              f"外校准 slope={ce['slope']:.4f} int={ce['intercept']:.4f}")

    # 最优模型: 外部 AUC 优先, 内 AUC 次之
    best_name = max(results, key=lambda k: (results[k]["external"]["auc"], results[k]["internal"]["auc"]))
    best = results[best_name]
    print(f"[BEST] {best_name}")

    # SHAP: 最终 XGB on full training
    xgb_full = XGBClassifier(n_estimators=250, max_depth=5, learning_rate=0.03, subsample=0.8,
                             colsample_bytree=0.7, scale_pos_weight=w, base_score=0.5,
                             eval_metric="auc", random_state=RNG, verbosity=0, n_jobs=4)
    xgb_full.fit(Xm_tree, ym)
    expl = shap.TreeExplainer(xgb_full)
    sv = expl.shap_values(Xm_tree)
    shap_df = pd.DataFrame({"feature": Xm_raw.columns,
                            "mean_abs_shap": np.abs(sv).mean(axis=0),
                            "mean_shap": sv.mean(axis=0)}).sort_values("mean_abs_shap", ascending=False)
    shap_df["rank"] = range(1, len(shap_df)+1)

    OUT = os.path.join(OUT_ROOT, target)
    os.makedirs(OUT, exist_ok=True)
    summary = {"target": target, "label": label, "feature_size": len(FEATS),
               "missing_indicator_size": len(ind_cols), "features": FEATS,
               "n_mimic": len(ym), "mimic_events": int(ym.sum()), "mimic_rate": round(float(ym.mean()), 4),
               "n_eicu": len(ye), "eicu_events": int(ye.sum()), "eicu_rate": round(float(ye.mean()), 4),
               "models": results, "best_model": best_name, "best": best,
               "shap_top20": shap_df.head(20).to_dict("records"),
               "repeats": 5, "folds": 5, "random_seed": RNG,
               "calibration_method": ("logit(observed) ~ logit(predicted), unpenalized logistic "
                                      "(statsmodels GLM Binomial); Hosmer-Lemeshow over 10 quantile bins"),
               "code_version": "model_final_v7.py (calibration corrected, R3-M3)"}
    with open(os.path.join(OUT, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    shap_df.to_csv(os.path.join(OUT, "shap_importance.csv"), index=False)
    pd.DataFrame({"y": ym, "pred": oofs[best_name]}).to_csv(os.path.join(OUT, "pred_mimic.csv"), index=False)
    pd.DataFrame({"y": ye, "pred": ext_preds[best_name]}).to_csv(os.path.join(OUT, "pred_eicu.csv"), index=False)
    np.save(os.path.join(OUT, "oof_XGB.npy"), oofs["XGBoost"])
    np.save(os.path.join(OUT, "oof_LGB.npy"), oofs["LightGBM"])
    np.save(os.path.join(OUT, "oof_LR.npy"), oofs["Logistic"])
    np.save(os.path.join(OUT, "oof_Voting.npy"), oofs["Voting"])
    np.save(os.path.join(OUT, "ext_XGB.npy"), ext_preds["XGBoost"])
    np.save(os.path.join(OUT, "ext_LGB.npy"), ext_preds["LightGBM"])
    np.save(os.path.join(OUT, "ext_LR.npy"), ext_preds["Logistic"])
    np.save(os.path.join(OUT, "ext_Voting.npy"), ext_preds["Voting"])
    print("[SAVED]", OUT)
    return best_name


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", default="mace")
    args = parser.parse_args()
    if args.target == "mace":
        run_target("mace", "strict 6-event MACE")
    elif args.target == "mace3":
        run_target("mace3", "BJA 3-event sensitivity")
    elif args.target == "mace_alldeath":
        run_target("mace_alldeath", "all-cause death replacement sensitivity")
    else:
        raise ValueError(args.target)
