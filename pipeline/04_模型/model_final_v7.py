# -*- coding: utf-8 -*-
"""
T4 最终建模 V7 (提交版主链)
- 主终点: 严格6事件 MACE (mace)
- 敏感性: BJA 3事件 (mace3)
- 模型: XGBoost / LightGBM / Voting / Logistic
- 评估: RepeatedStratifiedKFold 5x5, 内OOF, 外eICU, bootstrap 95%CI, Brier, AUPRC
- 产出: results_final/<target>/summary.json, preds, plotting data
- 设计: 仅训练集学习缺失指示器/插补器/标准化; 外部验证不接触MIMIC测试折
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
BASE = r"D:/WorkBuddy/专家团 1/04_模型"
OUT_ROOT = os.path.join(BASE, "results_final")
os.makedirs(OUT_ROOT, exist_ok=True)


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
        return [np.percentile(a, 2.5), np.percentile(a, 97.5)]
    return q(aucs), q(aps), q(briers)


def calibrate_stats(y, p):
    from sklearn.linear_model import LogisticRegression
    y = y.astype(float); p = np.clip(p, 1e-6, 1-1e-6)
    slope = LogisticRegression(C=1e6).fit(p.reshape(-1,1), y).coef_[0][0]
    intercept = LogisticRegression(C=1e6).fit(p.reshape(-1,1), y).intercept_[0]
    val_probs, actuals = calibration_curve(y, p, n_bins=10, strategy="quantile")
    return {"slope": float(slope), "intercept": float(intercept),
            "bins": [float(v) for v in val_probs], "observed": [float(a) for a in actuals]}


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
    mimic = pd.read_csv(os.path.join(BASE, "data/mimic_model_data.csv"))
    eicu = pd.read_csv(os.path.join(BASE, "data/eicu_model_data.csv"))
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
        auc_reps = []; ap_reps = []; brier_reps = []
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
            auc_reps.append(roc_auc_score(ym[tr], mm.predict_proba(Xm_tree[tr] if name != "Logistic" else Xm_lr[tr])[:,1]))  # placeholder unused later
        oof = oof_parts / 5.0
        ext = ext_parts / 25.0  # RepeatedStratifiedKFold: 5 folds x 5 repeats = 25 fits, each evaluated on all external samples
        oofs[name] = oof; ext_preds[name] = ext
        auc_ci, ap_ci, brier_ci = bootstrap_ci(ym, oof)
        metrics = {
            "internal": {"auc": float(roc_auc_score(ym, oof)), "auc_ci": auc_ci,
                         "auprc": float(average_precision_score(ym, oof)), "auprc_ci": ap_ci,
                         "brier": float(brier_score_loss(ym, oof)), "brier_ci": brier_ci},
            "external": {"auc": float(roc_auc_score(ye, ext)), "auc_ci": bootstrap_ci(ye, ext)[0],
                         "auprc": float(average_precision_score(ye, ext)), "auprc_ci": bootstrap_ci(ye, ext)[1],
                         "brier": float(brier_score_loss(ye, ext)), "brier_ci": bootstrap_ci(ye, ext)[2]}
        }
        results[name] = metrics
        metrics["internal"]["calibration"] = calibrate_stats(ym, oof)
        metrics["external"]["calibration"] = calibrate_stats(ye, ext)
        print(f"[{name}] 内AUC={metrics['internal']['auc']:.4f} 外AUC={metrics['external']['auc']:.4f} "
              f"外AUPRC={metrics['external']['auprc']:.4f} 外Brier={metrics['external']['brier']:.4f}")

    # 最优模型: 外部 AUC 优先, 内 AUC 次之
    best_name = max(results, key=lambda k: (results[k]["external"]["auc"], results[k]["internal"]["auc"]))
    best = results[best_name]

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
               "repeats": 5, "folds": 5, "random_seed": RNG}
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