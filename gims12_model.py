# -*- coding: utf-8 -*-
"""
GIMS-12 模型定义（唯一数据源）
Gout ICU Mortality Score, 12 variables — 24-hour post-window in-hospital death

由 08_计算器/calculator_model_death24.json 生成，勿手工修改系数。
重新生成：D:/WorkBuddy/专家团 1/_工具/build_gims12.py
"""
from math import exp

MODEL_NAME = "GIMS-12"
VERSION = "1.2"          # 1.2 起 predict() 默认截断到 CLIP_BOUNDS

INTERCEPT = 0.9532458692817674

# feature: (beta per raw unit, derivation-cohort median, label EN, label ZH, unit, lo, hi, step)
FEATURES = {
    "anchor_age": (0.02878894641776687, 72.0, "Age", "年龄", "years", 18.0, 110.0, 1.0),
    "gcs_total": (-0.08641588096859543, 13.0, "Total GCS", "GCS 总分", "points", 3.0, 15.0, 1.0),
    "sbp_mean": (-0.010406059075202326, 117.07846153846154, "Mean systolic BP", "平均收缩压", "mmHg", 40.0, 250.0, 1.0),
    "rr_mean": (0.14391961702238834, 18.45833333333333, "Mean respiratory rate", "平均呼吸频率", "/min", 4.0, 60.0, 0.5),
    "spo2_mean": (-0.010188449279556748, 96.84, "Mean SpO2", "平均血氧饱和度", "%", 50.0, 100.0, 0.5),
    "bun": (0.01979029682811435, 24.0, "Blood urea nitrogen", "尿素氮", "mg/dL", 1.0, 200.0, 1.0),
    "creatinine": (-0.09171027045479306, 1.2, "Creatinine", "肌酐", "mg/dL", 0.2, 15.0, 0.1),
    "hemoglobin": (-0.06760203341680782, 10.7, "Hemoglobin", "血红蛋白", "g/dL", 3.0, 20.0, 0.1),
    "platelet": (-0.0015381213248293717, 175.0, "Platelet count", "血小板计数", "×10⁹/L", 5.0, 800.0, 5.0),
    "wbc": (0.015027163685264883, 10.5, "White cell count", "白细胞计数", "×10⁹/L", 0.5, 80.0, 0.1),
    "calcium": (-0.03441238241793617, 8.5, "Calcium", "血钙", "mg/dL", 3.0, 15.0, 0.1),
    "chloride": (-0.04536416009409966, 105.0, "Chloride", "血氯", "mmol/L", 70.0, 140.0, 1.0),
}

ORDER = ["anchor_age", "gcs_total", "sbp_mean", "rr_mean", "spo2_mean",
         "bun", "creatinine", "hemoglobin", "platelet", "wbc", "calcium", "chloride"]

# 推导队列 1–99 百分位：既作为外推提示边界，也作为计算前的硬截断边界。
# 外部校准失败主要来自外推；截断后外部校准斜率由 0.497 升至 0.740，
# Brier 技巧分由 −0.090 转为 +0.020，且不丢弃任何患者（见 gims12_fit.json）。
CLIP_BOUNDS = {
    "anchor_age": (38.0, 91.0),
    "gcs_total": (3.0, 15.0),
    "sbp_mean": (88.824, 163.5343),
    "rr_mean": (12.3427, 29.9567),
    "spo2_mean": (90.7262, 99.9244),
    "bun": (7.0, 126.96),
    "creatinine": (0.5, 9.488),
    "hemoglobin": (6.1, 15.948),
    "platelet": (26.0, 539.8),
    "wbc": (1.952, 35.4),
    "calcium": (6.152, 10.6),
    "chloride": (88.0, 118.0),
}
EXTRAP_RANGE = CLIP_BOUNDS  # 向后兼容旧名

# 外部队列（eICU-CRD）导出的重校准映射：lp' = slope * lp + intercept
RECAL_SLOPE = 0.4973
RECAL_INTERCEPT = -1.4610

PERFORMANCE = {
    "internal_auroc": 0.7712, "internal_ci": (0.7395, 0.8008),
    "internal_brier": 0.0707, "internal_skill": 0.096,
    "internal_cal_slope": 1.000, "internal_cal_intercept": -0.002, "internal_hl_p": 0.588,
    # 外部：未截断（as computed） vs 截断后（default behaviour of this model）
    "external_auroc": 0.723, "external_ci": (0.6504, 0.7867),
    "external_brier": 0.0582, "external_skill": 0.020,
    "external_cal_slope": 0.740, "external_cal_intercept": -0.830,
    "external_auroc_raw": 0.718, "external_brier_raw": 0.0647,
    "external_skill_raw": -0.090, "external_cal_slope_raw": 0.497,
    "external_cal_intercept_raw": -1.461,
    "external_brier_clamped_plus_platt": 0.0572,
    "n_derivation": 2853, "events_derivation": 244,
    "n_external": 962, "events_external": 61,
    "full_model_internal": 0.8117, "full_model_external": 0.7476, "full_model_n": 47,
}

# 风险四分位（推导队列实测）
RISK_BANDS = [
    {"q": "Q1", "lo": 0.0000, "hi": 0.0321, "observed": 0.0098, "n": 714, "events": 7},
    {"q": "Q2", "lo": 0.0321, "hi": 0.0578, "observed": 0.0421, "n": 713, "events": 30},
    {"q": "Q3", "lo": 0.0578, "hi": 0.1024, "observed": 0.0827, "n": 713, "events": 59},
    {"q": "Q4", "lo": 0.1024, "hi": 1.0000, "observed": 0.2076, "n": 713, "events": 148},
]


def ui_default(key):
    """界面初始值：中位数取整到输入步长，便于阅读。"""
    b, med, lab_en, lab_zh, unit, lo, hi, step = FEATURES[key]
    if step >= 1:
        return float(round(med))
    dp = 0 if step >= 1 else (1 if step >= 0.1 else 2)
    return float(round(med, dp))


def clip_values(values):
    """把各变量限制在推导队列 1–99 百分位内。返回 (截断后的字典, 被截断的变量列表)。"""
    out, hit = {}, []
    for k in ORDER:
        v = values.get(k, None)
        v = FEATURES[k][1] if v is None else float(v)
        lo, hi = CLIP_BOUNDS[k]
        if v < lo:
            v, hit = lo, hit + [k]
        elif v > hi:
            v, hit = hi, hit + [k]
        out[k] = v
    return out, hit


def linear_predictor(values, recalibrate=False, clip=True):
    """values: dict feature -> float. 缺失键使用推导队列中位数。
    clip=True 时先截断到推导队列 1–99 百分位（默认，也是验证过的做法）。"""
    vals = clip_values(values)[0] if clip else values
    lp = INTERCEPT
    for k in ORDER:
        b, med = FEATURES[k][0], FEATURES[k][1]
        v = vals.get(k, None)
        v = med if v is None else float(v)
        lp += b * v
    if recalibrate:
        lp = RECAL_SLOPE * lp + RECAL_INTERCEPT
    return lp


def predict(values, recalibrate=False, clip=True):
    lp = linear_predictor(values, recalibrate=recalibrate, clip=clip)
    if lp >= 0:
        return 1.0 / (1.0 + exp(-lp))
    e = exp(lp)
    return e / (1.0 + e)


def risk_band(p):
    for b in RISK_BANDS:
        if b["lo"] <= p < b["hi"]:
            return b
    return RISK_BANDS[-1]


def outside_range(values):
    """返回超出推导队列 1–99 百分位的变量键（外推提示）。"""
    out = []
    for k in ORDER:
        v = values.get(k, None)
        if v is None:
            continue
        lo, hi = EXTRAP_RANGE[k]
        if v < lo or v > hi:
            out.append(k)
    return out


def format_risk(p):
    """避免虚假精度：极端值不显示 0.0% 或 100.0%。"""
    if p < 0.001:
        return "<0.1%"
    if p > 0.999:
        return ">99.9%"
    return f"{p * 100:.1f}%"


def contributions(values):
    """返回每个变量相对中位数的 logit 贡献（用于解释），以及总分。"""
    out = []
    for k in ORDER:
        b, med, lab_en, lab_zh, unit = FEATURES[k][:5]
        v = values.get(k, None)
        v = med if v is None else float(v)
        out.append({"key": k, "label_en": lab_en, "label_zh": lab_zh, "unit": unit,
                    "value": float(v), "median": med, "beta": b,
                    "delta_logit": b * (v - med)})
    return out
