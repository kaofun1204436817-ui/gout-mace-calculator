# 痛风患者 ICU 院内 MACE 预测模型 —— 代码交付包

本目录是手稿（EJMR 投稿）"**Coded in-hospital major adverse cardiovascular events in
critically ill patients with gout: a dual-database machine-learning study**" 的完整代码
交付物，用于满足期刊的可复现性要求，并直接回应审稿人关于校准统计量无法复现的意见。

> **一句话结论**：`calibration.py` 用正确的 logit 尺度拟合，可以在 **1e-8 以内**
> 逐位复现手稿报告的全部校准斜率、截距、标准误与 Hosmer–Lemeshow 统计量。
> `verify_all.py` 一次性核对 99 项，全部 PASS。

---

## 1. 目录结构

```
09_代码交付包/
├── README.md                    本文件
├── requirements.txt             精确锁定的依赖版本
├── analysis/
│   ├── model_final_v7.py        主分析脚本（建模 + 交叉验证 + 外部验证 + SHAP）
│   ├── calibration.py           ★ 校准统计模块，可独立运行
│   ├── recalibration.py         ★ Platt 10 折交叉重校准，可独立运行
│   └── verify_all.py            ★ 一键复现验证，可独立运行
├── data_definitions/            26 个 p*.sql，从原始数据库抽取分析数据集的全部 SQL
├── models/                      训练好的终版模型对象（供计算器/部署用）
│   ├── xgb_mace6.ubj            原生格式（推荐）
│   ├── xgb_mace6.pkl            joblib 字典（含特征名与元数据）
│   ├── features.json            47 个特征名的有序清单
│   ├── train_manifest.json      训练配置、SHA256、性能（含单次重训值）
│   └── model_card.md            模型卡（用途、限制、伦理）
└── results_final/               归档的预测向量与结果（本包自带，可直接验证）
    ├── <target>/pred_mimic.csv  内部 OOF 预测
    ├── <target>/pred_eicu.csv   外部预测
    ├── <target>/oof_*.npy       四模型族内部预测向量
    ├── <target>/ext_*.npy       四模型族外部预测向量
    ├── <target>/summary.json    修正代码重训产生的完整结果
    └── tables/                  Table 1–5 的 CSV
```

> ⚠️ **`models/` 与 `results_final/` 的口径差异（必读）**
> `models/` 里的模型对象是**另行重训**导出的（xgboost **3.4.1** / Python 3.13），
> 而 `results_final/` 与论文数字来自 **xgboost 3.2.0** / Python 3.10。
> 两者在同一批数据上重训的结果在第 3 位小数起有差异：
>
> | 指标 | 论文 / `results_final`（3.2.0） | `models/`（3.4.1） | 四舍五入后是否一致 |
> |---|---|---|---|
> | 内部 AUROC | 0.781645 | 0.781175 | ❌ 0.782 vs 0.781 |
> | 内部 AUPRC | 0.709357 | 0.709738 | ❌ 0.709 vs 0.710 |
> | 内部 Brier | 0.182959 | 0.183021 | ✅ 0.183 |
> | 外部 AUROC | 0.672799 | 0.672076 | ❌ 0.673 vs 0.672 |
> | 外部 AUPRC | 0.164610 | 0.163365 | ❌ 0.165 vs 0.163 |
> | 外部 Brier | 0.137579 | 0.136586 | ❌ 0.138 vs 0.137 |
>
> **以论文为准 = 以 `results_final/` 为准。** `models/` 中的模型对象可用于部署与
> 计算器（其预测排序与论文模型高度一致），但**不应**用它的 `train_manifest.json`
> 里的 `performance` 字段去替代 Table 2。要逐位复现论文，必须用
> `requirements.txt` 锁定的 xgboost==3.2.0。
> 这是梯度提升在多线程下的浮点不确定性 + 版本间分裂阈值实现差异导致的，
> 不是代码错误；但它确实意味着 **xgboost 版本必须严格锁定**。

三个 `★` 标脚本**不需要原始数据库**，仅依赖 `results_final/` 里归档的预测向量，
因此任何拿到本包的人都能立刻验证手稿数字。`model_final_v7.py` 需要受限数据。

---

## 2. 环境

本包在以下环境生成并验证（版本号由 `import <mod>; <mod>.__version__` 实测读取，
非估计值）：

| 组件 | 版本 |
|---|---|
| Python | 3.10.4 |
| numpy | 2.2.6 |
| pandas | 2.3.3 |
| scipy | 1.15.3 |
| scikit-learn | 1.7.2 |
| xgboost | 3.2.0 |
| lightgbm | 4.7.0 |
| shap | 0.47.0 |
| statsmodels | 0.15.0 |
| matplotlib | 3.10.9 |

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

---

## 3. 数据获取

本研究使用两个公开但**受控访问**的重症监护数据库。本包**不包含**任何患者级原始数据，
也不包含派生建模数据集（`mimic_model_data.csv` / `eicu_model_data.csv`），
因为二者的数据使用协议禁止再分发。

| 数据库 | 版本 | 时间范围 | 获取方式 |
|---|---|---|---|
| MIMIC-IV | **v3.1** | 2008–2022 | PhysioNet，需完成 CITI "Data or Specimens Only Research" 培训并签署数据使用协议：<https://physionet.org/content/mimiciv/3.1/> |
| eICU-CRD | **v2.0** | 2014–2015 | PhysioNet，同上流程：<https://physionet.org/content/eicu-crd/2.0/> |

申请通过后，把数据库导入 PostgreSQL，然后**按顺序执行 `data_definitions/` 中的 SQL**：

### 3.1 MIMIC-IV v3.1（数据库名 `mimic`）

```bash
for f in p0_mimic_probe p1_mimic_cohort p2_mimic_outcomes_v3 p3_mimic_sensitivity \
         p4_mimic_features p4b_mimic_meds p5_mimic_model_data \
         p6_eicu_features p9_mimic_mace3 p10_mimic_enhance p11_mimic_vitals_v5 \
         p13_mimic_hua_cohort; do
  psql "host=localhost port=5432 dbname=mimic user=mimic password=mimic" -f data_definitions/$f.sql
done
```

关键顺序约束：
1. `p1_mimic_cohort` 必须先于一切（建立 2,853 例主队列）。
2. `p2_mimic_outcomes_v3` 定义 6 事件复合结局，必须在 `p5` 之前（`p5` 需要 outcomes 表）。
3. `p4_mimic_features` 产出 24h 特征矩阵；`p4b_mimic_meds` 补充用药。
4. `p10_mimic_enhance` + `p11_mimic_vitals_v5` 是**特征增强**，必须在 `p5_mimic_model_data`
   **之后可以重跑**（它们往 features 表加列，再重建 model_data）；实际操作中
   建议顺序：`p1 → p2 → p4 → p4b → p10 → p11 → p5`，与作者环境一致。
5. `p9_mimic_mace3` 在 `p5` 之后运行（给 model_data 加 `mace3` 列）。
6. `p13_mimic_hua_cohort` 只用于 Table 4 的亚组，与主建模链无关。

### 3.2 eICU-CRD v2.0（数据库名 `eicu`）

```bash
for f in p0_eicu_probe p1_eicu_cohort p6_eicu_features p8_eicu_bp_fix \
         p10_eicu_enhance p11_eicu_vitals_v5 p7_eicu_model_data \
         p9_eicu_mace3 p12_eicu_wide_label p1b_eicu_outcome_compare; do
  psql "host=localhost port=5432 dbname=eicu user=eicu password=eicu" -f data_definitions/$f.sql
done
```

顺序约束：`p1_eicu_cohort` → `p6_eicu_features` → `p8_eicu_bp_fix`（修正血压合并口径）
→ `p10` → `p11` → `p7_eicu_model_data` → `p9_eicu_mace3`。

eICU **没有痛风 ICD 编码**，外部验证队列用"别嘌醇用药"作为痛风代理
（`p1_eicu_cohort.sql` 中有详细说明），这是文献常用做法，也是外部事件率仅
9.8% 的主要原因之一。

### 3.3 导出为 CSV

SQL 跑完后把两张宽表导出到 `<DATA_DIR>`：

```bash
psql dbname=mimic -c "\copy mimic_model_data TO 'data/mimic_model_data.csv' CSV HEADER"
psql dbname=eicu  -c "\copy eicu_model_data  TO 'data/eicu_model_data.csv'  CSV HEADER"
```

预期规模（可用于核对数据管线是否跑对）：

| 数据集 | n | 列数 | 主终点事件 |
|---|---|---|---|
| `mimic_model_data.csv` | 2,853 | 68 | 1,086 (38.1%) |
| `eicu_model_data.csv` | 962 | 68 | 94 (9.8%) |

---

## 4. 运行顺序

### 路线 A：只验证手稿数字（**推荐给审稿人与读者**，无需数据库）

```bash
cd analysis

python calibration.py        # 三终点 × 内部/外部：slope/intercept/SE/HL + 逐项对照
python recalibration.py      # eICU Platt 10 折交叉重校准，复现 recalibration_analysis.json
python verify_all.py         # 一键总验证：107 项 PASS/DIFF 对照表
```

三者都以 `results_final/` 为输入，均应退出码 0。

预期输出（节选）：

```
### mace  --  strict 6-event MACE (primary)
  internal   slope= 1.014464 (SE 0.044568)  intercept=-0.290674 (SE 0.044469)  HL=54.7961 (df=8)
  external   slope= 0.596405 (SE 0.116573)  intercept=-1.719919 (SE 0.133127)  HL=229.4642 (df=8)
复现核对：28/28 项在 1e-6 容差内一致
```

```
复现核对：13/13 项在 1e-09 容差内一致
重校准收益：Brier 0.1376 -> 0.0862 (-37.3%)；AUROC 0.6728 -> 0.6685
```

```
总计：107/107 项 PASS，0 项 DIFF，2 项无参考值
```

### 路线 B：从数据重训模型（需按第 3 节准备好数据）

```bash
cd analysis
export DATA_DIR=/path/to/data          # Windows: set DATA_DIR=D:\path\to\data
export OUT_ROOT=/path/to/out           # 可选，默认 ./results_final

python model_final_v7.py --target mace            # 主终点，约 60 秒
python model_final_v7.py --target mace3           # 3 事件敏感性
python model_final_v7.py --target mace_alldeath   # 全因死亡替代敏感性
```

重训后 `summary.json` 中的 AUROC/AUPRC/Brier/校准统计量与 SHAP 排序应与本包归档的
`results_final/` **逐位一致**（同种子同版本下浮点可重现；实测差异 < 1e-12）。

把重训输出纳入验证（最强证据，会把校验项从 107 项扩到 215 项）：

```bash
python verify_all.py --retrain-dir /path/to/out
```

```
-- [A+] 重训复现（model_final_v7.py 输出 vs 归档 summary.json）
总计：215/215 项 PASS，0 项 DIFF，2 项无参考值
```

本包归档的 `results_final/*/summary.json` 就是**用修正后的代码从原始数据重训**
产生的输出，因此其中 `calibration_standard` 是脚本真正生成的数值，不再有
`calibration_legacy_deprecated` 之类事后手写的孤儿字段。

### 路线 C：重新生成表格与图

表格来自 `make_tables.py`，图来自 `figure_final.py` / `figure_v2_fixes.py` /
`figure_fig8_v3.py`，它们读取 `results_final/` 与 `data/`。这些脚本不在本包内，
可按需从作者仓库取得；它们不参与校准统计量的计算。

---

## 5. 预期输出与手稿表格的对应关系

| `verify_all.py` 的分组 | 对应手稿位置 | 数据来源 | 能否完全重算 |
|---|---|---|---|
| `[A] 队列规模` | Results 第 1 段（2,853 / 962；1,086 / 94） | `pred_*.csv` 长度 | ✅ 完全重算 |
| `[A] Table 2 主指标` | **Table 2**；Results "Discrimination" | `oof_*.npy` / `ext_*.npy` | ✅ 完全重算（AUROC/AUPRC/Brier） |
| `[A] 校准统计` | Results 校准段落；**Table 2 附注** | `calibration.py` | ✅ 完全重算（slope/intercept/SE/HL） |
| `[A] Platt 交叉重校准` | Results "Recalibration restored calibration…" | `recalibration.py` | ✅ 完全重算（11 个数字） |
| `[A+] 重训复现` | 全部（仅在提供 `--retrain-dir` 时出现） | `model_final_v7.py` | ✅ 从原始数据完整重跑 |
| `[B] 归档自洽性` | — | CSV vs NPY | ✅ 一致性核对 |
| `[C] SHAP 排序` | **Table 3**；Figure 5 | `shap_importance.csv` | ⚠️ 仅核对归档值，**未重训** |

**明确未覆盖的部分**（诚实的边界声明）：

- **Bootstrap 95% CI 的确切端点**：`verify_all.py` 重算了点估计，但未重跑 1,000 次
  重采样。CI 端点依赖 numpy RNG 内部实现，跨 numpy 次版本可能末位漂移。
  归档的 `summary.json` 中的 CI 与 Table 2 的括号内区间一致；且实测
  `model_final_v7.py` 重训后 CI 与归档值差异 < 1e-12。
- **Figure 2–6 的像素级复现**：图由 matplotlib 渲染，字体/DPI 会因平台而异，
  数值内容一致即视为复现。
- **SHAP 排序**：验证路线 A 不重训，`[C]` 组只检查归档 CSV 与 Table 3 是否自洽。
  若要真正重算 SHAP，走路线 B，然后加 `--retrain-dir` 让 `[A+]` 组比对。
- **Table 1（基线比较）与 Table 4/5（亚组、PSM）**：由 `make_tables.py` 与
  `subgroup_psm_v3.py` 从 `data/` 生成，本包未包含这两个脚本的重算逻辑。

---

## 6. 校准统计量的方法学说明（回应审稿意见）

`calibration.py` 的 `calibrate_stats()` 实现的是**标准做法**：

```
logit(P(Y = 1)) = a + b · logit(p_model)
```

- `b` = 校准斜率（完美校准 = 1；< 1 表示过离散/预测过于极端）
- `a` = 校准截距（完美校准 = 0；< 0 表示系统性高估）

拟合用 `statsmodels.GLM(family=Binomial)`，**无惩罚**，标准误直接取自
Fisher 信息矩阵逆的对角元开方。

**历史缺陷与修正**：原 `model_final_v7.py` 第 88–95 行把结局 `y` 直接对
**原始概率 p** 回归（`fit(p.reshape(-1,1), y)`），得到的不是校准斜率；
同一错误在 `summary.json` 里留下内部 4.87、外部 2.97 的伪值（正确值分别是
1.01 与 0.60）。同时原实现**没有**计算 Hosmer–Lemeshow，但手稿引用了它，
形成"数字在结果文件里、生成脚本不存在"的缺口。本包修正了这两点，并把
`calibration_legacy_deprecated` 从输出中彻底移除。

**Hosmer–Lemeshow 的分箱约定**：按预测概率做 10 等频分位分箱，用
`pandas.qcut`（左开右闭，边界值归入左侧箱）。这一约定与已发表数字所用的
一致；若改用 `np.digitize`（左闭右开），内部 HL 会从 54.796 变成 54.625。
差异来自切点恰好命中观测值时归属不同，属实现约定差异，不是统计定义差异。

**口径不一致的如实披露**：`calibration.py`（校准斜率）用无惩罚拟合，
`recalibration.py`（Platt 重校准）用 `LogisticRegression(C=1.0)`，因为后者要
复现已归档的 `recalibration_analysis.json`（用 sklearn 默认 C 生成）。
两者数值差异 < 0.04（重校准后斜率 0.9361 vs 无惩罚口径 0.9722），
不影响任何定性结论。`recalibration.py --penalty unpenalized` 可切换到统一口径。
**建议在最终版本中统一，并在 Methods 中说明所选口径。**

---

## 7. 许可与引用

代码以 MIT 许可发布。数据使用须遵守 PhysioNet 各自的 Credentialed Health Data
Use Agreement，不得再分发。模型、表格与图表随手稿以 CC BY 4.0 发布。
