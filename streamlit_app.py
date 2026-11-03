# -*- coding: utf-8 -*-
"""
GIMS-12 — 24-hour post-window in-hospital mortality risk calculator
ICU patients with gout

Derivation: MIMIC-IV (n = 2,853; 244 events)
External:   eICU-CRD  (n = 962;  61 events)

This is a research and teaching instrument. It is not a medical device and must
not be used as the sole basis for any clinical decision.
"""
import os
import sys

import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gims12_model as G  # noqa: E402

# Streamlit re-runs this script inside a long-lived process, so a previously
# imported gims12_model can stay cached in sys.modules after a redeploy and the
# app would then call attributes that no longer exist. Compare the module
# version and reload on mismatch.
_REQUIRED_MODEL_VERSION = "1.2"
if getattr(G, "VERSION", None) != _REQUIRED_MODEL_VERSION:
    import importlib
    G = importlib.reload(G)
if getattr(G, "VERSION", None) != _REQUIRED_MODEL_VERSION:
    st.error(
        "The model module on disk is out of date (found version "
        f"{getattr(G, 'VERSION', 'unknown')}, expected {_REQUIRED_MODEL_VERSION}). "
        "Redeploy the app."
    )
    st.stop()

st.set_page_config(
    page_title="GIMS-12 — 24-hour mortality risk in ICU patients with gout",
    page_icon="🫘",
    layout="wide",
)

# ---------------------------------------------------------------- i18n
TXT = {
    "en": {
        "title": "GIMS-12 · 24-hour mortality risk",
        "sub": "ICU patients with gout · in-hospital death after the first 24 hours",
        "setting": "Calibration setting",
        "set_dev": "Derivation setting (MIMIC-IV)",
        "set_ext": "Transport setting (eICU-derived recalibration)",
        "set_help": (
            "The published model is calibrated on MIMIC-IV. When transported to a "
            "different health system it over-predicts risk (calibration slope 0.50, "
            "intercept −1.46). The second option applies that published "
            "recalibration. It is derived from eICU-CRD and is provided for "
            "transparency, not as a validated local mapping."
        ),
        "inputs": "Patient variables (first 24 h in ICU)",
        "result": "Predicted risk",
        "risk_of": "Predicted probability",
        "risk_cap": "of in-hospital death after the first 24 h in the ICU",
        "band": "Risk stratum",
        "band_help": "Quartiles of predicted risk in the derivation cohort.",
        "obs": "Observed event rate in this stratum",
        "interp": "Interpretation",
        "contrib": "Contribution of each variable (logit, relative to cohort median)",
        "perf": "Model performance",
        "perf_note": (
            "The full 47-predictor XGBoost model reaches AUROC 0.812 internally and "
            "0.748 externally. This twelve-variable score is the bedside approximation; "
            "it gives up 0.040 internally and 0.028 externally in exchange for twelve "
            "inputs that are available at the bedside. External calibration failed when "
            "inputs were used as entered (slope 0.497); clamping them to the derivation "
            "range, which this tool does, recovers most of it (slope 0.740)."
        ),
        "disc": "Limitations and intended use",
        "cite": "Citation",
        "reset": "Reset to cohort median",
        "extrap": ("{detail}. The score is validated only between the 1st and 99th "
                   "percentile of the derivation cohort, so values outside that range are "
                   "clamped before the risk is computed and the displayed probability is the "
                   "estimate at the boundary of the validated range."),
        "extrap_h": "Extrapolation guard applied",
        "perf_cols": ["Metric", "Derivation (MIMIC-IV, 5×5 CV)",
                      "External, as computed", "External, clamped (this tool)"],
        "perf_rows": ["AUROC", "Brier score", "Brier skill score", "Calibration slope",
                      "Calibration intercept", "Hosmer–Lemeshow P"],
    },
    "zh": {
        "title": "GIMS-12 · 24 小时死亡风险",
        "sub": "ICU 痛风患者 · 入 ICU 24 小时后院内死亡",
        "setting": "校准设定",
        "set_dev": "推导设定（MIMIC-IV）",
        "set_ext": "迁移设定（按 eICU 重校准）",
        "set_help": (
            "发表模型按 MIMIC-IV 校准。迁移到其他医疗系统时会高估风险"
            "（校准斜率 0.50，截距 −1.46）。第二项应用该重校准；"
            "它由 eICU-CRD 导出，仅供透明披露，不等于本地已验证的映射。"
        ),
        "inputs": "患者变量（入 ICU 后 24 小时内）",
        "result": "预测风险",
        "risk_of": "预测概率",
        "risk_cap": "入 ICU 24 小时后院内死亡",
        "band": "风险分层",
        "band_help": "按推导队列预测风险四分位划分。",
        "obs": "该层实测事件率",
        "interp": "解读",
        "contrib": "各变量贡献（logit，相对队列中位数）",
        "perf": "模型性能",
        "perf_note": (
            "47 变量 XGBoost 全模型内部 AUROC 0.812、外部 0.748。"
            "本 12 变量评分为床旁近似版：以内部 −0.040、外部 −0.028 的代价，"
            "换取 12 个床旁即可获得的输入。外部校准在输入原样使用时失败（斜率 0.497）；"
            "本工具把输入截断到推导范围后，大部分失校准被纠正（斜率 0.740）。"
        ),
        "disc": "局限与用途",
        "cite": "引用",
        "reset": "恢复为队列中位数",
        "extrap": ("{detail}。本评分仅在推导队列 1–99 百分位内验证，超出该范围的取值"
                   "在计算前被截断，显示的概率是验证范围边界处的估计值。"),
        "extrap_h": "已启用外推保护",
        "perf_cols": ["指标", "推导（MIMIC-IV，5×5 CV）", "外部（原样计算）", "外部（截断后，本工具）"],
        "perf_rows": ["AUROC", "Brier 分数", "Brier 技巧分", "校准斜率",
                      "校准截距", "Hosmer–Lemeshow P"],
    },
}

with st.sidebar:
    lang = "zh" if st.radio(
        "Language / 语言", ["English", "中文"], index=0, horizontal=True
    ) == "中文" else "en"
    t = TXT[lang]
    st.divider()
    st.markdown(f"**{t['setting']}**")
    setting = st.radio(
        "cal", [t["set_dev"], t["set_ext"]], index=0, label_visibility="collapsed"
    )
    recal = setting == t["set_ext"]
    st.caption(t["set_help"])
    st.divider()
    if st.button(t["reset"], use_container_width=True):
        for k in G.ORDER:
            st.session_state[f"in_{k}"] = G.ui_default(k)
        st.rerun()
    st.caption("GIMS-12 v1.0 · 2026-11")

st.title(t["title"])
st.caption(t["sub"])

# ---------------------------------------------------------------- inputs
st.subheader(t["inputs"])
left, right = st.columns([1.05, 1.0], gap="large")

values = {}
with left:
    groups = [
        (["anchor_age", "gcs_total"], 2),
        (["sbp_mean", "rr_mean", "spo2_mean"], 3),
        (["bun", "creatinine", "hemoglobin"], 3),
        (["platelet", "wbc", "calcium", "chloride"], 2),
    ]
    for keys, ncol in groups:
        cols = st.columns(ncol)
        for i, k in enumerate(keys):
            beta, med, lab_en, lab_zh, unit, lo, hi, step = G.FEATURES[k]
            label = lab_en if lang == "en" else lab_zh
            with cols[i % ncol]:
                values[k] = st.number_input(
                    f"{label} ({unit})",
                    min_value=float(lo),
                    max_value=float(hi),
                    value=float(st.session_state.get(f"in_{k}", G.ui_default(k))),
                    step=float(step),
                    key=f"in_{k}",
                )

# ---------------------------------------------------------------- result
p = G.predict(values, recalibrate=recal)
band = G.risk_band(p)

with right:
    st.subheader(t["result"])
    c1, c2 = st.columns([1, 1])
    with c1:
        st.metric(label=t["risk_of"], value=G.format_risk(p))
        st.caption(t["risk_cap"])
    with c2:
        st.metric(label=t["band"], value=band["q"], help=t["band_help"])
        st.caption(f"{t['obs']}: **{band['observed'] * 100:.2f}%** "
                   f"(n = {band['n']}, {band['events']} events)")

    st.progress(min(max(p, 0.0), 1.0))

    n = 1000
    exp_deaths = p * n
    if lang == "en":
        st.markdown(
            f"**{t['interp']}** Of {n} patients with this profile, about "
            f"**{exp_deaths:.0f}** would be expected to die after the first 24 hours "
            f"in the ICU and before hospital discharge."
        )
    else:
        st.markdown(
            f"**{t['interp']}** 每 {n} 例具有该特征的患者，预计约 "
            f"**{exp_deaths:.0f}** 例在入 ICU 24 小时后、出院前死亡。"
        )

    _, clamped = G.clip_values(values)
    if clamped:
        bits = []
        for k in clamped:
            lo, hi = G.CLIP_BOUNDS[k]
            orig = float(values[k])
            used = lo if orig < lo else hi
            lab = G.FEATURES[k][2] if lang == "en" else G.FEATURES[k][3]
            dp = 0 if G.FEATURES[k][7] >= 1 else 1
            bits.append(f"{lab} {orig:g} → {round(used, dp):g}")
        detail = "; ".join(bits)
        st.warning(f"**{t['extrap_h']}** — " + t["extrap"].format(detail=detail))

    if recal:
        st.info(
            "Recalibrated to the eICU-CRD transport setting (lp' = 0.4973 × lp − 1.461). "
            "Discrimination is unchanged (AUROC 0.720); only the probability scale moves."
            if lang == "en" else
            "已按 eICU-CRD 迁移设定重校准（lp' = 0.4973 × lp − 1.461）。"
            "判别力不变（AUROC 0.720），仅概率尺度改变。"
        )

    with st.expander(t["contrib"]):
        rows = G.contributions(values)
        rows.sort(key=lambda r: -abs(r["delta_logit"]))
        for r in rows:
            lab = r["label_en"] if lang == "en" else r["label_zh"]
            st.markdown(
                f"`{r['delta_logit']:+.3f}` **{lab}** — "
                f"{r['value']:g} {r['unit']} (cohort median {r['median']:g})"
            )
        st.caption(
            "Positive values raise the predicted risk; negative values lower it. "
            "Logit contributions are additive and sum to the linear predictor."
            if lang == "en" else
            "正值提高预测风险，负值降低。各贡献可加，加总即为线性预测值。"
        )

# ---------------------------------------------------------------- performance
st.divider()
st.subheader(t["perf"])
P = G.PERFORMANCE
_c0, _c1, _c2, _c3 = t["perf_cols"]
perf_tbl = {
    _c0: t["perf_rows"],
    _c1: [
        f"{P['internal_auroc']:.3f} ({P['internal_ci'][0]:.3f}–{P['internal_ci'][1]:.3f})",
        f"{P['internal_brier']:.4f}",
        f"{P['internal_skill']:+.3f}",
        f"{P['internal_cal_slope']:.3f}",
        f"{P['internal_cal_intercept']:+.3f}",
        f"{P['internal_hl_p']:.2f}",
    ],
    _c2: [
        f"{P['external_auroc_raw']:.3f} ({P['external_ci'][0]:.3f}–{P['external_ci'][1]:.3f})",
        f"{P['external_brier_raw']:.4f}",
        f"{P['external_skill_raw']:+.3f}",
        f"{P['external_cal_slope_raw']:.3f}",
        f"{P['external_cal_intercept_raw']:+.3f}",
        "<0.001",
    ],
    _c3: [
        f"{P['external_auroc']:.3f}",
        f"{P['external_brier']:.4f}",
        f"{P['external_skill']:+.3f}",
        f"{P['external_cal_slope']:.3f}",
        f"{P['external_cal_intercept']:+.3f}",
        "—",
    ],
}
st.table(perf_tbl)
st.caption(t["perf_note"])

band_rows = {
    "Stratum": [b["q"] for b in G.RISK_BANDS],
    "Predicted range": [f"{b['lo'] * 100:.1f}–{b['hi'] * 100:.1f}%" for b in G.RISK_BANDS],
    "n": [b["n"] for b in G.RISK_BANDS],
    "Events": [b["events"] for b in G.RISK_BANDS],
    "Observed rate": [f"{b['observed'] * 100:.2f}%" for b in G.RISK_BANDS],
}
st.table(band_rows)

# ---------------------------------------------------------------- disclaimer
st.divider()
with st.expander(t["disc"], expanded=False):
    st.markdown(
        """
**Endpoint.** The outcome is in-hospital death that occurs *after* the first 24 hours
in the ICU. Patients who died within the first 24 hours are excluded from the
denominator, so the score is conditional on surviving the predictor window.

**Population.** Adults with an ICD-coded gout diagnosis who were admitted to an ICU.
The derivation cohort excluded patients with a previous myocardial infarction, stroke
or heart failure, so the score has not been validated in that group.

**Externally.** Only 61 events accrued in the external cohort, and gout was identified
by allopurinol prescription rather than diagnosis. Discrimination transported
(AUROC 0.720) but the probability scale did not; recalibration is mandatory before any
external use.

**Not a medical device.** This tool is provided for research and teaching. It does not
replace clinical judgement, and it must not be used as the sole basis for any decision
about an individual patient.
"""
        if lang == "en" else
        """
**终点定义。** 结局为入 ICU **24 小时之后**发生的院内死亡。24 小时内死亡者不进入
分母，因此本评分以"度过预测窗"为条件。

**人群。** ICU 收治、且有 ICD 痛风诊断编码的成人。推导队列排除了既往心肌梗死、卒中
或心力衰竭者，该人群未经验证。

**外部验证。** 外部队列仅 61 例事件，且痛风由别嘌醇处方而非诊断界定。判别力可迁移
（AUROC 0.720），但概率尺度不可直接使用，外部应用前必须重校准。

**非医疗器械。** 本工具仅供研究与教学，不替代临床判断，不得作为任何个体化决策的
唯一依据。
"""
    )

with st.expander(t["cite"]):
    st.code(
        "GIMS-12: a twelve-variable score for 24-hour post-window in-hospital\n"
        "mortality in ICU patients with gout. Derivation in MIMIC-IV, external\n"
        "validation in eICU-CRD. (2026).",
        language="text",
    )

st.caption("GIMS-12 v1.0 · research use only · not a medical device")
