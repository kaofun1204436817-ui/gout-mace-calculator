# Model Card — xgb_mace6

预测目标：痛风患者 ICU 住院期间 strict six-event MACE
生成日期：2026-11-01
对应稿件：EJMR 投稿稿（`manuscript_EJMR.docx`）

---

## 1. 模型身份

| 项 | 值 |
|---|---|
| 算法 | XGBoost（梯度提升树） |
| 文件 | `xgb_mace6.ubj`（原生格式，推荐）<br>`xgb_mace6.pkl`（joblib 字典，含特征名与元数据） |
| 特征数 | 47（45 基础特征 + 2 缺失指示变量） |
| 训练样本 | MIMIC-IV 2,853 例，事件 1,086（38.1%） |
| 外部队列 | eICU-CRD 962 例，事件 94（9.8%） |
| SHA256 | 见 `train_manifest.json` |

## 2. 目标定义

strict six-event in-hospital MACE 复合终点：

1. 急性心肌梗死（ICD-9 410；ICD-10 I21/I22）
2. 新发卒中（ICD-9 430–434, 436；ICD-10 I60–I64）
3. 心源性休克（ICD-9 785.51；ICD-10 R57.0）
4. 恶性心律失常（ICD-9 427.1/427.41/427.5；ICD-10 I46/I49.0/I47.2）
5. 急性心力衰竭（ICD-9 428.21/23/31/33/41/43；ICD-10 I50.2x/3x/4x，I50.811/813）
6. 心源性死亡（住院死亡且至少有一个上述急性事件编码）

### 必须知道的终点性质（三条，均已在稿件 Methods 披露）

1. **心源性死亡嵌套于前五项内**：163 例心源性死亡全部已有至少一个急性事件编码，因此复合终点实际只提供 **五个独立事件类别**，不是六个。保留 "six-event" 名称是因为六个事件编码定义终点，心源性死亡提供严重度信息而非独立类别。
2. **未被捕获的死亡**：284 例院内死亡中 **121 例（42.6%）无任何急性事件编码，不计入主终点**。全因死亡替代终点识别 1,207 例而非 1,086 例，差值 121 = 284 − 163，精确成立。
3. **事件无法定位时点**：行政编码不能确定事件相对 ICU 入院的时间。因急性心梗/心衰/心源性休克/恶性心律失常入 ICU 者，同一住院期间的编码即被计为 MACE。**模型实际预测的是"本次住院期间存在 MACE 编码"，而非 24 小时窗后的新发事件**。这是反向因果，会高估急性表现患者的可预测性。

## 3. 特征集（47）

45 个基础特征，分五组：

- **人口学与合并症（8）**：age, gender, diabetes, hypertension, CKD, COPD, liver disease, malignancy
- **生理（17）**：心率（max/min/mean/std）、收缩压（max/min/mean）、舒张压、平均动脉压（min/mean）、呼吸频率（mean/max）、血氧饱和度（mean/min）、GCS；通气与透析为二值标志
- **实验室（11）**：chloride, calcium, hemoglobin, BUN, creatinine, potassium, glucose, WBC, sodium, platelet, bicarbonate
- **用药（10）**：P2Y12 抑制剂、利尿剂、阿司匹林、β 受体阻滞剂、他汀、抗凝、ACEI/ARB、血管升压药、糖皮质激素、秋水仙碱
- **缺失指示（2）**：`calcium_miss`（缺失 12.1%）、`map_min_miss`（缺失 3.5%）

### 因跨库一致性被排除的变量（重要）

以下变量在 eICU-CRD 记录不全，**未进入模型**，不是统计选择的结果：

肌钙蛋白 I/T、NT-proBNP、乳酸、C 反应蛋白、**血清尿酸**、白蛋白、镁、肌酸激酶及 CK-MB、总胆红素、D-二聚体、INR、PTT、转氨酶、中性粒细胞与淋巴细胞计数、体温、入院来源。

因此**不能**说"肌钙蛋白未进入前 20 名"——它根本不在候选集内。

### 已知缺陷变量

`hr_std`（24 小时心率标准差）：心率生理界值（<20 / >250）被误用于标准差，清洗后缺失 **97.13%（MIMIC）/ 97.82%（eICU）**，清洗前仅 0.28%/2.39%。该变量保留在模型中（因缺失率筛选在清洗前完成），但其贡献接近于零，系数**不应做临床解读**。

## 4. 超参数

```json
{
  "n_estimators": 250,
  "max_depth": 5,
  "learning_rate": 0.03,
  "subsample": 0.8,
  "colsample_bytree": 0.7,
  "scale_pos_weight": 1.627,
  "base_score": 0.5,
  "eval_metric": "auc",
  "random_state": 42
}
```

**类别加权的影响**：`scale_pos_weight` 等于负正比（1.627），会使原始输出概率整体上移约 log(1.627) ≈ 0.49 logit。加权训练改善排序但**有意扭曲概率尺度**，这是外部队列观察到的大部分校准偏差的来源。概率应视为**需要重校准的评分**，不是校准好的风险。

## 5. 性能

| 指标 | 内部（25 折 OOF） | 外部（eICU，25 次拟合平均） |
|---|---|---|
| AUROC | **0.781**（95% CI 0.765–0.798） | **0.672**（95% CI 0.615–0.733） |
| AUPRC | 0.710 | 0.163 |
| Brier | 0.183 | 0.137 |
| 校准斜率 | 1.014 | 0.596 |
| 校准截距 | −0.291 | −1.720 |
| HL 统计量 | 54.80（df 8，P = 4.8×10⁻⁹） | 229.46（df 8，P = 3.8×10⁻⁴⁵） |

**外部重校准后**（10 折交叉式 Platt）：斜率 0.936、截距 −0.134、Brier 0.086（改善 37%）、AUROC 0.669（不变）。

## 6. 使用警告

> **评估本模型时不要用训练集自身预测。** 本对象是全样本重训的最终模型，在 MIMIC-IV 上直接预测会得到约 0.98 的虚高 AUROC。无偏的内部估计是 OOF 值 0.781。复现稿件图表请用 `results_final/<target>/oof_XGB.npy`。

## 7. 适用边界

**可以做**：研究场景下的风险分层、服务规划、方法学比较、假设生成。

**不可以做**：
- 个体层面的治疗决策
- 因低风险分类而减少监测或降级治疗
- 作为正式治疗算法的输入
- 在未做本地重校准的医疗系统中直接部署

理由：外部 AUROC 0.673 低于 0.70 的常规可用下限；外部校准需要重校准才能读作绝对风险；决策曲线显示净获益仅覆盖很窄的阈值区间，在 eICU 无一致净获益；事件无法定位时点。

## 8. 随附文件

| 文件 | 内容 |
|---|---|
| `xgb_mace6.ubj` | XGBoost 原生模型（推荐加载方式） |
| `xgb_mace6.pkl` | joblib 字典：model, features, missing_indicator_sources, target, params, n_features, trained_on, n_train |
| `features.json` | 47 个特征名的有序列表 |
| `train_manifest.json` | 完整训练清单：参数、CV 方案、性能、SHA256、roundtrip 校验、使用警告 |

加载示例：

```python
from xgboost import XGBClassifier
import json, pandas as pd

feats = json.load(open("features.json"))
model = XGBClassifier()
model.load_model("xgb_mace6.ubj")

# 需要先按 Manuscript Methods 做缺失指示变量构造与 gender 编码
X = df[feats].apply(pd.to_numeric, errors="coerce").astype(float)
risk_score = model.predict_proba(X)[:, 1]   # 注意：这是加权后的评分，非校准概率
```

## 9. 版本一致性

本模型产物使用与 `requirements.txt` **完全一致的** Python 与 xgboost 版本导出：

| 组件 | 版本 |
|---|---|
| Python | 3.10.4 |
| xgboost | 3.2.0 |
| scikit-learn | 1.7.2 |
| numpy | 2.2.6 |
| pandas | 2.3.3 |

早期曾用 Python 3.13.14 / xgboost 3.4.1 导出一版，当前文件已由前者覆盖。加载时**不需要**任何兼容性转换，roundtrip 最大偏差为 0.00e+00。若使用其他版本加载 `.pkl`，XGBoost 可能提示序列化版本警告，此时请改用 `.ubj`（跨版本更稳定）。

## 10. 复现路径

1. `python analysis/verify_all.py` — 核对 99 项报告值与归档输出（无需数据库）
2. `python analysis/calibration.py` — 复核所有校准斜率/截距/SE/HL
3. `python analysis/recalibration.py` — 复核 Platt 重校准结果
4. 重训模型需 PhysioNet 认证访问 MIMIC-IV 与 eICU-CRD，SQL 见 `data_definitions/`
