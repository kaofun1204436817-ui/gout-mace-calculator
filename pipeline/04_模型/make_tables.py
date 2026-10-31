# -*- coding: utf-8 -*-
"""Tables 1-5 (EJMR) from final results"""
import os, json, warnings
import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore")
BASE = r"D:/WorkBuddy/专家团 1/04_模型"
OUT = r"D:/WorkBuddy/专家团 1/04_模型/results_final/tables"
os.makedirs(OUT, exist_ok=True)

mimic = pd.read_csv(os.path.join(BASE, "data/mimic_model_data.csv"))
eicu  = pd.read_csv(os.path.join(BASE, "data/eicu_model_data.csv"))
cont = ["anchor_age","gcs_total","bun","rr_mean","chloride","hemoglobin","wbc","sbp_mean",
        "creatinine","hr_mean","map_mean","spo2_min","uric_acid","lactate","platelet","sodium","potassium"]
cat = ["gender","dm","hypertension","ckd","copd","liver","cancer","med_colchicine",
       "med_steroid","med_aspirin","med_statin","med_vasopressor","med_betablocker",
       "med_acei_arb","dialysis_flag","vent_flag"]

def gender_num(x):
    if isinstance(x, str):
        if x.upper().startswith("M"): return 1
        return 0
    return x
mimic["gender"] = mimic["gender"].map(gender_num)
eicu["gender"] = eicu["gender"].map(gender_num)

rows = []
for c in cont+cat:
    m = pd.to_numeric(mimic.get(c), errors="coerce") if c in mimic else pd.Series([np.nan])
    e = pd.to_numeric(eicu.get(c), errors="coerce") if c in eicu else pd.Series([np.nan])
    if c in cont:
        med_m = f"{m.median():.1f} ({m.quantile(.25):.1f}-{m.quantile(.75):.1f})" if m.notna().sum() else "NA"
        med_e = f"{e.median():.1f} ({e.quantile(.25):.1f}-{e.quantile(.75):.1f})" if e.notna().sum() else "NA"
        mm = m.dropna(); ee = e.dropna()
        p = stats.mannwhitneyu(mm, ee).pvalue if len(mm)>0 and len(ee)>0 else np.nan
        rows.append([c, med_m, med_e, f"{p:.3f}" if p==p else "NA"])
    else:
        mm = m.fillna(0); ee = e.fillna(0)
        rows.append([c, f"{int(mm.sum())} ({100*mm.mean():.1f}%)", f"{int(ee.sum())} ({100*ee.mean():.1f}%)",
                     f"{stats.chi2_contingency([[int(mm.sum()),len(mm)-int(mm.sum())],[int(ee.sum()),len(ee)-int(ee.sum())]])[1]:.3f}"])
Table1 = pd.DataFrame(rows, columns=["Variable","MIMIC-IV (n=2853)","eICU-CRD (n=962)","P"])
Table1.to_csv(os.path.join(OUT,"Table1_baseline.csv"), index=False)

# Table 2 performance
s_mace = json.load(open(os.path.join(BASE,"results_final/mace/summary.json"),encoding="utf-8"))
s_mace3 = json.load(open(os.path.join(BASE,"results_final/mace3/summary.json"),encoding="utf-8"))
rows=[]
for target,tag,s in [("mace","Strict 6-event",s_mace),("mace3","3-event",s_mace3)]:
    for mod, d in s["models"].items():
        rows.append([tag, mod,
                     f"{d['internal']['auc']:.3f} ({d['internal']['auc_ci'][0]:.3f}-{d['internal']['auc_ci'][1]:.3f})",
                     f"{d['external']['auc']:.3f} ({d['external']['auc_ci'][0]:.3f}-{d['external']['auc_ci'][1]:.3f})",
                     f"{d['internal']['auprc']:.3f}", f"{d['external']['auprc']:.3f}",
                     f"{d['internal']['brier']:.3f}", f"{d['external']['brier']:.3f}"])
Table2 = pd.DataFrame(rows, columns=["Outcome","Model","Internal AUC (95% CI)","External AUC (95% CI)",
                                     "Internal AUPRC","External AUPRC","Internal Brier","External Brier"])
Table2.to_csv(os.path.join(OUT,"Table2_model_performance.csv"), index=False)

# Table 3 SHAP
shap = pd.read_csv(os.path.join(BASE,"results_final/mace/shap_importance.csv")).head(20)
shap["mean_abs_shap"] = shap["mean_abs_shap"].round(4)
Table3 = shap[["rank","feature","mean_abs_shap","mean_shap"]].rename(columns={"rank":"Rank","feature":"Feature",
            "mean_abs_shap":"Mean |SHAP|","mean_shap":"Mean SHAP"})
Table3.to_csv(os.path.join(OUT,"Table3_shap.csv"), index=False)

# Table 4 subgroup
sub_path = os.path.join(BASE,"results_final/subgroup_psm")
sub_m = pd.read_csv(os.path.join(sub_path,"subgroup_mimic.csv"))
sub_e = pd.read_csv(os.path.join(sub_path,"subgroup_eicu.csv"))
Table4 = pd.concat([sub_m, sub_e], ignore_index=True)
Table4.to_csv(os.path.join(OUT,"Table4_subgroup.csv"), index=False)

# Table 5 PSM summary + smd (v3 三层: PSM/IPTW/full-adjusted) + E-value
psm = json.load(open(os.path.join(sub_path,"psm_summary.json"),encoding="utf-8"))
rows=[]
EVP = psm.get("e_value", {})
for exp, label in [("med_urate","ULT (allopurinol-based)"),("med_colchicine","Colchicine")]:
    r = psm["psm"][exp]
    ps = r.get("psm") or {}
    iptw = r.get("iptw") or {}
    adj = r.get("full_adjusted") or {}
    crude = r.get("crude") or {}
    smd_after = ps.get("max_abs_smd_after", None)
    evx = EVP.get(exp, {})
    e_val = evx.get("e_value_full_adjusted")
    rows.append([
        label, r["n_exposed"], r["n_unexposed"],
        ps.get("n_pairs", ""),
        f"{crude.get('or', float('nan')):.3f} ({crude.get('ci95',[0,0])[0]:.3f}-{crude.get('ci95',[0,0])[1]:.3f})",
        f"{ps.get('logistic',{}).get('or', float('nan')):.3f} ({ps.get('logistic',{}).get('ci95',[0,0])[0]:.3f}-{ps.get('logistic',{}).get('ci95',[0,0])[1]:.3f})",
        f"{iptw.get('or',{}).get('or', float('nan')):.3f} ({iptw.get('or',{}).get('ci95',[0,0])[0]:.3f}-{iptw.get('or',{}).get('ci95',[0,0])[1]:.3f})",
        f"{adj.get('or', float('nan')):.3f} ({adj.get('ci95',[0,0])[0]:.3f}-{adj.get('ci95',[0,0])[1]:.3f})",
        (f"{e_val:.2f}" if e_val else "n/a"),
        (f"{smd_after:.3f}" if smd_after is not None else "n/a"),
        "balanced" if ps.get("imbalanced_after") == [] else "unbalanced"])
Table5 = pd.DataFrame(rows, columns=["Exposure","Exposed","Unexposed","Matched pairs",
    "Crude OR (95% CI)","PSM matched OR (95% CI)","IPTW OR (95% CI)","Full-adjusted OR (95% CI)","E-value","Max |SMD| after","PSM balance"])
Table5.to_csv(os.path.join(OUT,"Table5_psm.csv"), index=False)

# combined markdown (csv 已足够的辅助; 用简单 pipe 输出避免 tabulate 依赖)
with open(os.path.join(OUT,"Tables1-5.md"),"w",encoding="utf-8") as f:
    for i,t in enumerate([Table1,Table2,Table3,Table4,Table5],1):
        f.write(f"\n## Table {i}\n\n")
        f.write(t.to_csv(index=False))
print("[OK] Tables saved to", OUT)
print(Table2.to_string(index=False))