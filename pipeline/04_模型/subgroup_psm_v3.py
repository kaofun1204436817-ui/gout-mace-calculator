# -*- coding: utf-8 -*-
"""
T5-R3 药物效应分析（三层稳健方法，修复 v1/v2 匹配后协变量失衡）
目标：对 ULT / Colchicine 与 MACE 的关联给出可辩护、可复现、三法互证的估计：
  1) PSM：Mahalanobis 距离最近邻 1:1 无放回 + 倾向分 caliper 双重约束
     （Rosenbaum-Rubin 式组合匹配；比一维 PS 匹配显著改善协变量平衡）
  2) IPTW：稳定权重逆概率加权（加权 logistic + 加权 SMD 平衡诊断）
  3) 全变量调整 logistic（敏感性）
输出：results_final/subgroup_psm/psm_summary_v3.json（含完整 SMD 表与平衡判定）
"""
import os, json, warnings
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from scipy.spatial.distance import cdist
import statsmodels.api as sm

warnings.filterwarnings("ignore")
BASE = r"D:/WorkBuddy/专家团 1/04_模型"
OUT = os.path.join(BASE, "results_final", "subgroup_psm")
os.makedirs(OUT, exist_ok=True)
RNG = 42
np.random.seed(RNG)

def smd(a, b, wa=None, wb=None):
    a = np.asarray(a, float); b = np.asarray(b, float)
    if wa is None:
        mu_a, mu_b = np.mean(a), np.mean(b)
        va, vb = np.var(a, ddof=1), np.var(b, ddof=1)
    else:
        wa = np.asarray(wa, float); wb = np.asarray(wb, float)
        wa = wa / wa.sum(); wb = wb / wb.sum()
        mu_a = np.sum(wa * a); mu_b = np.sum(wb * b)
        va = np.sum(wa * (a - mu_a)**2); vb = np.sum(wb * (b - mu_b)**2)
    den = np.sqrt((va + vb) / 2)
    return 0.0 if den == 0 else (mu_a - mu_b) / den

def logit_or(y, x, cov=None, weights=None):
    X = np.column_stack([x.astype(float)] + ([cov] if cov is not None else []))
    X = sm.add_constant(X)
    if weights is not None:
        m = sm.GLM(y.astype(int), X, family=sm.families.Binomial(),
                   freq_weights=np.asarray(weights, float)).fit()
    else:
        m = sm.Logit(y.astype(int), X).fit(disp=False, method="bfgs", maxiter=200)
    b, se = m.params[1], m.bse[1]
    return {"or": float(np.exp(b)), "ci95": [float(np.exp(b-1.96*se)), float(np.exp(b+1.96*se))],
            "p": float(m.pvalues[1])}

def mahalanobis_match(X1, X0, ps1, ps0, caliper_ps=0.1, max_pairs=None):
    """Mahalanobis 距离最近邻 1:1 + PS caliper 双重约束"""
    sigma = np.cov(np.vstack([X1, X0]).T)
    cov_inv = np.linalg.pinv(sigma + 1e-8 * np.eye(sigma.shape[0]))
    # 马氏距离矩阵 (暴露行 x 对照列)
    D = cdist(X1, X0, metric="mahalanobis", VI=cov_inv)
    std_ps = np.std(np.concatenate([ps1, ps0]))
    thr_ps = caliper_ps * std_ps
    # PS 差值矩阵
    PS = np.abs(ps1[:, None] - ps0[None, :])
    valid = PS <= thr_ps
    D[~valid] = np.inf
    used = set(); pairs = []
    order = np.argsort(D.min(axis=1))  # 先匹最接近的
    n = len(X1) if max_pairs is None else min(len(X1), max_pairs)
    for i in order:
        if len(pairs) >= n:
            break
        j = int(np.argmin(D[i]))
        if not np.isfinite(D[i, j]) or j in used:
            continue
        used.add(j); pairs.append((i, j))
    return pairs

m = pd.read_csv(os.path.join(BASE, "data/mimic_model_data.csv"))
sub_g = pd.read_csv(os.path.join(OUT, "subgroup_mimic.csv"))
sub_e = pd.read_csv(os.path.join(OUT, "subgroup_eicu.csv"))

covs = ["anchor_age","gender","dm","hypertension","ckd","copd","liver","cancer",
        "dialysis_flag","vent_flag","med_vasopressor","med_betablocker","med_acei_arb",
        "med_statin","med_aspirin","med_p2y12","med_anticoag","med_diuretic","med_steroid"]
for c in covs:
    if c == "gender":
        m[c] = m[c].map({"M":1,"F":0,"Male":1,"Female":0})
    m[c] = pd.to_numeric(m[c], errors="coerce")

res = {}
for exposure, label in [("med_urate", "ULT (allopurinol-based ULT)"), ("med_colchicine", "Colchicine")]:
    y = m["mace"].astype(int).values
    ex = m[exposure].astype(int).values
    Xv = m[covs].values.astype(float)
    imp = pd.Series(np.nanmedian(Xv, axis=0), index=covs)
    for k, c in enumerate(covs):
        Xv[np.isnan(Xv[:, k]), k] = imp[c]
    Xs = StandardScaler().fit_transform(Xv)

    # 倾向分 logit
    expl = sm.add_constant(Xv)
    ps_model = sm.Logit(ex, expl).fit(disp=False)
    ps = ps_model.predict(expl)
    ps1 = ps[ex == 1]; ps0 = ps[ex == 0]
    X1 = Xs[ex == 1]; X0 = Xs[ex == 0]
    y1 = y[ex == 1]; y0 = y[ex == 0]

    # ---- 1) PSM (Mahalanobis + PS caliper) ----
    pairs = mahalanobis_match(X1, X0, ps1, ps0, caliper_ps=0.1)
    i1 = np.array([p[0] for p in pairs]); i0 = np.array([p[1] for p in pairs])
    after_smd = [smd(Xv[i1, k], Xv[i0, k]) for k in range(Xv.shape[1])]
    before_smd = [smd(Xv[ex==1, k], Xv[ex==0, k]) for k in range(Xv.shape[1])]
    psm = None
    if len(pairs) > 0:
        y_psm = np.concatenate([y1[i1], y0[i0]])
        ex_psm = np.concatenate([np.ones(len(i1)), np.zeros(len(i0))])
        X_psm = np.vstack([Xs[i1], Xs[i0]])
        r_psm = logit_or(y_psm, ex_psm)
        b_ = int(((y1[i1]==1)&(y0[i0]==0)).sum()); c_ = int(((y1[i1]==0)&(y0[i0]==1)).sum())
        from scipy.stats import binomtest
        cond = None
        if b_+c_ > 0 and b_ > 0 and c_ > 0:
            orv = b_/c_; se = np.sqrt(1/b_+1/c_)
            cond = {"or": round(float(orv),3), "ci95": [round(float(np.exp(np.log(orv)-1.96*se)),3),
                     round(float(np.exp(np.log(orv)+1.96*se)),3)],
                    "p": float(binomtest(min(b_,c_), n=b_+c_, p=0.5).pvalue), "b": b_, "c": c_}
        psm = {"n_pairs": len(pairs), "logistic": r_psm, "conditional": cond,
               "max_abs_smd_after": round(float(max(abs(np.array(after_smd)))), 3),
               "imbalanced_after": [covs[k] for k in range(len(after_smd)) if abs(after_smd[k]) > 0.1]}

    # ---- 2) IPTW (稳定权重) ----
    p1 = ps[ex == 1]; p0 = ps[ex == 0]
    w1 = (ex.sum()/len(ex)) / p1
    w0 = ((1-ex).sum()/len(ex)) / (1-p0)
    w = np.zeros(len(ex)); w[ex == 1] = w1; w[ex == 0] = w0
    w = w / w.mean()
    wtd_smd = [smd(Xv[ex==1, k], Xv[ex==0, k], w1, w0) for k in range(Xv.shape[1])]
    r_iptw = logit_or(y, ex, weights=w)
    full_cov = Xs[:, [k for k in range(Xs.shape[1]) if covs[k] != exposure]]
    r_adj = logit_or(y, ex, cov=full_cov)
    iptw = {"or": r_iptw, "max_abs_smd_wtd": round(float(max(abs(np.array(wtd_smd)))), 3),
            "imbalanced_wtd": [covs[k] for k in range(len(wtd_smd)) if abs(wtd_smd[k]) > 0.1],
            "effective_n": round(float((w.sum()**2)/(w**2).sum()), 1)}

    r_crude = logit_or(y, ex)
    entry = {
        "label": label, "n_exposed": int(ex.sum()), "n_unexposed": int((ex==0).sum()),
        "crude": r_crude, "psm": psm, "iptw": iptw,
        "full_adjusted": r_adj,
        "smd_table": pd.DataFrame({"covariate": covs, "smd_before": before_smd,
                                   "smd_after_psm": after_smd, "smd_wtd_iptw": wtd_smd}).to_dict("records"),
    }
    res[exposure] = entry
    print("="*40, label)
    print("  crude:", r_crude)
    if psm: print("  PSM:", psm["logistic"], "| pairs:", psm["n_pairs"], "| maxSMD:", psm["max_abs_smd_after"],
                  "| imbalanced:", psm["imbalanced_after"][:6])
    print("  IPTW:", iptw["or"], "| wtd maxSMD:", iptw["max_abs_smd_wtd"], "| effN:", iptw["effective_n"])
    print("  full adjusted:", r_adj)

with open(os.path.join(OUT, "psm_summary_v3.json"), "w", encoding="utf-8") as f:
    json.dump({"subgroup_mimic": sub_g.to_dict("records"),
               "subgroup_eicu": sub_e.to_dict("records"),
               "psm": res, "covariates": covs, "version": "v3 three-tier (PSM/IPTW/adjusted)"},
              f, ensure_ascii=False, indent=2)
print("\n[SAVED]", os.path.join(OUT, "psm_summary_v3.json"))