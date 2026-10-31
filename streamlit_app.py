# -*- coding: utf-8 -*-
"""
Streamlit 在线版：ICU 痛风患者住院期 MACE 风险计算器
- 同一套 12 变量评分映射（与 Fig6 列线图 / HTML 计算器完全一致）
- 运行：streamlit run streamlit_app.py
- 部署：Streamlit Community Cloud（见 部署指南.md）
"""
import streamlit as st
import numpy as np

# ---- 评分映射（来自 nomogram_scoring.csv + nomogram_calibration.json，勿改） ----
SCORING = [
    ("anchor_age",     "Age (years)",            0.02231762577275091, 49.0,   89.0),
    ("gcs_total",      "GCS total score",        -0.02592201998631502, 3.0,   15.0),
    ("bun",            "BUN (mg/dL)",            0.011104160705409956, 10.0,  87.0),
    ("rr_mean",        "Respiratory rate (/min)",0.05538890737490993, 14.08, 25.976),
    ("chloride",       "Chloride (mmol/L)",      -0.058155600881078205, 94.0, 113.0),
    ("hemoglobin",     "Hemoglobin (g/dL)",      0.1276690297688269,  7.3,   14.5),
    ("wbc",            "WBC (10^9/L)",           -0.008182548702670529, 4.6, 22.8),
    ("sbp_mean",       "Mean SBP (mmHg)",        0.0036106401389396463, 97.37, 150.52),
    ("creatinine",     "Creatinine (mg/dL)",     -0.004488979411451294, 0.6,  5.0),
    ("med_p2y12",      "P2Y12 inhibitor",        1.4407860487377,      0.0,  1.0),
    ("med_diuretic",   "Diuretic use",           0.5435660628665044,  0.0,  1.0),
    ("med_betablocker","Beta-blocker",           0.648381449054287,   0.0,  1.0),
]
CAL_CONST = -4.539222418164871
CAL_COEF = 0.00686005800343645

st.set_page_config(page_title="In-hospital MACE Risk — ICU Gout", page_icon="❤️", layout="centered")
st.title("In-hospital MACE Risk Calculator")
st.caption("ICU patients with gout · strict 6-event MACE (acute MI, new stroke, cardiogenic shock, malignant arrhythmia, acute heart failure, cardiac death)")
st.caption("Derivation: MIMIC-IV (n=2,853, AUC 0.782) · External validation: eICU-CRD (n=962, AUC 0.673)")

st.sidebar.header("Patient inputs (first 24 h in ICU)")
values = {}
for key, label, beta, lo, hi in SCORING:
    if key.startswith("med_"):
        values[key] = st.sidebar.selectbox(label, [0, 1], format_func=lambda v: "Yes" if v else "No")
    else:
        default = 70 if key == "anchor_age" else (14 if key == "gcs_total" else (25 if key == "bun" else 18.0))
        values[key] = st.sidebar.number_input(label, value=float((lo + hi) / 2), step=None)

if st.sidebar.button("Calculate risk", type="primary"):
    total = 0.0
    missing = [k for k, *_ in SCORING if values[k] is None]
    if missing:
        st.error("Missing inputs: " + ", ".join(missing))
    else:
        for key, label, beta, lo, hi in SCORING:
            v = float(values[key])
            if beta >= 0:
                pts = max(0.0, min(1.0, (v - lo) / (hi - lo))) * 100
            else:
                pts = max(0.0, min(1.0, (hi - v) / (hi - lo))) * 100
            total += pts
        risk = 1.0 / (1.0 + np.exp(-(CAL_CONST + CAL_COEF * total)))
        pct = risk * 100
        st.markdown("---")
        c1, c2, c3 = st.columns(3)
        c1.metric("Total points", f"{total:.0f}")
        c2.metric("Predicted MACE risk", f"{pct:.1f}%")
        cat = "Low" if risk < 0.25 else ("Intermediate" if risk < 0.45 else "High")
        c3.metric("Risk category", cat)
        st.progress(min(1.0, risk))
        st.markdown("**Interpretation guide:** Low <25%, Intermediate 25–45%, High >45%. "
                    "This is a risk-stratification aid for research use; it does not replace clinical judgment.")

st.markdown("---")
st.caption("Research use only. Model from: 'Predicting in-hospital major adverse cardiovascular events in critically ill patients with gout…' (EJMR submission). "
           "Parameters identical to the paper's nomogram and bedside calculator.")