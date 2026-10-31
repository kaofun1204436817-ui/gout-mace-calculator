-- T3 特征工程 | MIMIC-IV | 主队列 24h 特征矩阵
-- 产物: mimic_features 表（stay_id 主键）
-- 维度：人口学 / 生命体征(24h聚合) / 化验(24h首值+极值) / 用药(降尿酸/抗炎/激素/他汀等) / 合并症(Charlson/Elixhauser核心) / 痛风分型标记
-- 运行: psql dbname=mimic user=mimic -f p4_mimic_features.sql

DROP TABLE IF EXISTS mimic_features;

-- Step 0: 主队列 base
CREATE TEMP TABLE base AS
SELECT c.subject_id, c.hadm_id, c.stay_id, c.intime,
       p.gender, p.anchor_age, adm.race, adm.admittime
FROM mimic_cohort c
JOIN mimiciv_hosp.patients p USING (subject_id)
JOIN mimiciv_hosp.admissions adm USING (hadm_id)
WHERE NOT c.any_prior_mace_dx;

-- Step 1: 生命体征 24h 聚合（chartevents + 部分在 labevents）
CREATE TEMP TABLE vitals AS
SELECT b.stay_id,
       -- 心率
       MIN(CASE WHEN ce.itemid=220045 THEN ce.valuenum END) AS hr_min,
       MAX(CASE WHEN ce.itemid=220045 THEN ce.valuenum END) AS hr_max,
       AVG(CASE WHEN ce.itemid=220045 THEN ce.valuenum END) AS hr_mean,
       -- 收缩压（有创优先，无创补充）
       AVG(CASE WHEN ce.itemid IN (220050,220179) THEN ce.valuenum END) AS sbp_mean,
       MIN(CASE WHEN ce.itemid IN (220050,220179) THEN ce.valuenum END) AS sbp_min,
       -- 舒张压
       AVG(CASE WHEN ce.itemid IN (220051,220180) THEN ce.valuenum END) AS dbp_mean,
       -- 平均动脉压
       AVG(CASE WHEN ce.itemid IN (220052,220181) THEN ce.valuenum END) AS map_mean,
       MIN(CASE WHEN ce.itemid IN (220052,220181) THEN ce.valuenum END) AS map_min,
       -- 呼吸频率
       AVG(CASE WHEN ce.itemid=220210 THEN ce.valuenum END) AS rr_mean,
       -- SpO2
       MIN(CASE WHEN ce.itemid=220277 THEN ce.valuenum END) AS spo2_min,
       -- 体温（摄氏度）
       AVG(CASE WHEN ce.itemid=223762 THEN ce.valuenum END) AS temp_mean,
       -- GCS
       MIN(CASE WHEN ce.itemid IN (220739,223900,223901) THEN ce.valuenum END) AS gcs_min
FROM base b
JOIN mimiciv_icu.chartevents ce
  ON ce.stay_id = b.stay_id AND ce.charttime >= b.intime AND ce.charttime < b.intime + interval '24 hours'
WHERE ce.valuenum IS NOT NULL
  AND ce.itemid IN (220045,220050,220051,220052,220179,220180,220181,220210,220277,223762,220739,223900,223901)
GROUP BY b.stay_id;

-- Step 2: 化验 24h 首值（取最先一次）
CREATE TEMP TABLE labs_first AS
SELECT DISTINCT ON (b.stay_id, grp.lab)
       b.stay_id, grp.lab, le.valuenum
FROM base b
JOIN mimiciv_hosp.labevents le ON le.subject_id = b.subject_id
JOIN LATERAL (
  SELECT itemid, CASE
    WHEN itemid IN (51007) THEN 'uric_acid'
    WHEN itemid IN (50912) THEN 'creatinine'
    WHEN itemid IN (51002,52642) THEN 'troponin_i'
    WHEN itemid IN (51003) THEN 'troponin_t'
    WHEN itemid IN (50963) THEN 'ntprobnp'
    WHEN itemid IN (50813,52442,53154) THEN 'lactate'
    WHEN itemid IN (50889) THEN 'crp'
    WHEN itemid IN (51652) THEN 'hscrp'
    WHEN itemid IN (51301,51300) THEN 'wbc'
    WHEN itemid IN (51265,53189) THEN 'platelet'
    WHEN itemid IN (50811,51222) THEN 'hemoglobin'
    WHEN itemid IN (50983,52623) THEN 'sodium'
    WHEN itemid IN (50971,52610) THEN 'potassium'
    WHEN itemid IN (50902,52535) THEN 'chloride'
    WHEN itemid IN (50882) THEN 'bicarbonate'
    WHEN itemid IN (50893) THEN 'calcium'
    WHEN itemid IN (50960) THEN 'magnesium'
    WHEN itemid IN (50910) THEN 'ck'
    WHEN itemid IN (50911,51580) THEN 'ck_mb'
    WHEN itemid IN (50862,53085) THEN 'albumin'
    WHEN itemid IN (50885,53089) THEN 'bilirubin_total'
    WHEN itemid IN (50931,52569) THEN 'glucose'
    WHEN itemid IN (50915,51196,52551) THEN 'd_dimer'
    WHEN itemid IN (51675,51237) THEN 'inr'
    WHEN itemid IN (51275,52923) THEN 'ptt'
    WHEN itemid IN (50861,53084) THEN 'alt'
    WHEN itemid IN (50878) THEN 'ast'
    WHEN itemid IN (51006) THEN 'bun'
    WHEN itemid IN (52075) THEN 'neutrophil'
    WHEN itemid IN (51133) THEN 'lymphocyte'
    ELSE NULL END AS lab
  FROM mimiciv_hosp.d_labitems
) grp ON grp.itemid = le.itemid AND grp.lab IS NOT NULL
WHERE le.charttime >= b.intime AND le.charttime < b.intime + interval '24 hours'
  AND le.valuenum IS NOT NULL
ORDER BY b.stay_id, grp.lab, le.charttime;

-- 化验首值转宽表
CREATE TEMP TABLE labs_wide AS
SELECT stay_id,
  MAX(CASE WHEN lab='uric_acid' THEN valuenum END) AS uric_acid,
  MAX(CASE WHEN lab='creatinine' THEN valuenum END) AS creatinine,
  MAX(CASE WHEN lab='troponin_i' THEN valuenum END) AS troponin_i,
  MAX(CASE WHEN lab='troponin_t' THEN valuenum END) AS troponin_t,
  MAX(CASE WHEN lab='ntprobnp' THEN valuenum END) AS ntprobnp,
  MAX(CASE WHEN lab='lactate' THEN valuenum END) AS lactate,
  MAX(CASE WHEN lab='crp' THEN valuenum END) AS crp,
  MAX(CASE WHEN lab='hscrp' THEN valuenum END) AS hscrp,
  MAX(CASE WHEN lab='wbc' THEN valuenum END) AS wbc,
  MAX(CASE WHEN lab='platelet' THEN valuenum END) AS platelet,
  MAX(CASE WHEN lab='hemoglobin' THEN valuenum END) AS hemoglobin,
  MAX(CASE WHEN lab='sodium' THEN valuenum END) AS sodium,
  MAX(CASE WHEN lab='potassium' THEN valuenum END) AS potassium,
  MAX(CASE WHEN lab='chloride' THEN valuenum END) AS chloride,
  MAX(CASE WHEN lab='bicarbonate' THEN valuenum END) AS bicarbonate,
  MAX(CASE WHEN lab='calcium' THEN valuenum END) AS calcium,
  MAX(CASE WHEN lab='magnesium' THEN valuenum END) AS magnesium,
  MAX(CASE WHEN lab='ck' THEN valuenum END) AS ck,
  MAX(CASE WHEN lab='ck_mb' THEN valuenum END) AS ck_mb,
  MAX(CASE WHEN lab='albumin' THEN valuenum END) AS albumin,
  MAX(CASE WHEN lab='bilirubin_total' THEN valuenum END) AS bilirubin_total,
  MAX(CASE WHEN lab='glucose' THEN valuenum END) AS glucose,
  MAX(CASE WHEN lab='d_dimer' THEN valuenum END) AS d_dimer,
  MAX(CASE WHEN lab='inr' THEN valuenum END) AS inr,
  MAX(CASE WHEN lab='ptt' THEN valuenum END) AS ptt,
  MAX(CASE WHEN lab='alt' THEN valuenum END) AS alt,
  MAX(CASE WHEN lab='ast' THEN valuenum END) AS ast,
  MAX(CASE WHEN lab='bun' THEN valuenum END) AS bun,
  MAX(CASE WHEN lab='neutrophil' THEN valuenum END) AS neutrophil,
  MAX(CASE WHEN lab='lymphocyte' THEN valuenum END) AS lymphocyte
FROM labs_first GROUP BY stay_id;

-- Step 3: 用药（已在 p4b 预建 mimic_meds，直接引用避免全表扫描）
CREATE TEMP TABLE meds AS SELECT * FROM mimic_meds;

-- Step 4: 合并症（Charlson 核心组件，本次住院编码）
CREATE TEMP TABLE comorb AS
SELECT b.stay_id,
       MAX(CASE WHEN d.icd_code ~ '^(250|E1[0-4])' THEN 1 ELSE 0 END) AS dm,
       MAX(CASE WHEN d.icd_code ~ '^(401|I10|I15)' THEN 1 ELSE 0 END) AS hypertension,
       MAX(CASE WHEN d.icd_code ~ '^(584|585|586|N17|N18|N19)' THEN 1 ELSE 0 END) AS ckd,
       MAX(CASE WHEN d.icd_code ~ '^(49[0-6]|J4[0-7])' THEN 1 ELSE 0 END) AS copd,
       MAX(CASE WHEN d.icd_code ~ '^(571|K7[0-7])' THEN 1 ELSE 0 END) AS liver,
       MAX(CASE WHEN d.icd_code ~ '^(162|163|164|165|C3[0-4]|C7[0-9]|C8[0-9])' THEN 1 ELSE 0 END) AS cancer
FROM base b
JOIN mimiciv_hosp.diagnoses_icd d ON d.hadm_id = b.hadm_id
GROUP BY b.stay_id;

-- Step 5: 痛风分型标记（单纯高尿酸 vs 确诊痛风 vs 痛风合并CKD）
CREATE TEMP TABLE gout_type AS
SELECT b.stay_id,
       MAX(CASE WHEN d.icd_code ~ '^(274|M10)' THEN 1 ELSE 0 END) AS is_gout_dx,
       MAX(CASE WHEN d.icd_code ~ '^(7906|E790)' THEN 1 ELSE 0 END) AS is_hyperuricemia_dx,
       MAX(CASE WHEN d.icd_code ~ '^(584|585|586|N17|N18|N19)' THEN 1 ELSE 0 END) AS is_ckd_dx
FROM base b
JOIN mimiciv_hosp.diagnoses_icd d ON d.hadm_id = b.hadm_id
GROUP BY b.stay_id;

-- Step 6: 组装主特征表
CREATE TABLE mimic_features AS
SELECT b.subject_id, b.hadm_id, b.stay_id, b.intime,
       b.gender, b.anchor_age, b.race,
       v.hr_min, v.hr_max, v.hr_mean, v.sbp_mean, v.sbp_min, v.dbp_mean, v.map_mean, v.map_min,
       v.rr_mean, v.spo2_min, v.temp_mean, v.gcs_min,
       lw.uric_acid, lw.creatinine, lw.troponin_i, lw.troponin_t, lw.ntprobnp, lw.lactate,
       lw.crp, lw.hscrp, lw.wbc, lw.platelet, lw.hemoglobin, lw.sodium, lw.potassium, lw.chloride,
       lw.bicarbonate, lw.calcium, lw.magnesium, lw.ck, lw.ck_mb, lw.albumin, lw.bilirubin_total,
       lw.glucose, lw.d_dimer, lw.inr, lw.ptt, lw.alt, lw.ast, lw.bun, lw.neutrophil, lw.lymphocyte,
       COALESCE(m.med_urate,0) AS med_urate, COALESCE(m.med_colchicine,0) AS med_colchicine,
       COALESCE(m.med_steroid,0) AS med_steroid, COALESCE(m.med_aspirin,0) AS med_aspirin,
       COALESCE(m.med_p2y12,0) AS med_p2y12, COALESCE(m.med_anticoag,0) AS med_anticoag,
       COALESCE(m.med_statin,0) AS med_statin, COALESCE(m.med_diuretic,0) AS med_diuretic,
       COALESCE(m.med_vasopressor,0) AS med_vasopressor, COALESCE(m.med_betablocker,0) AS med_betablocker,
       COALESCE(m.med_acei_arb,0) AS med_acei_arb,
       COALESCE(c.dm,0) AS dm, COALESCE(c.hypertension,0) AS hypertension, COALESCE(c.ckd,0) AS ckd,
       COALESCE(c.copd,0) AS copd, COALESCE(c.liver,0) AS liver, COALESCE(c.cancer,0) AS cancer,
       COALESCE(gt.is_gout_dx,0) AS is_gout_dx, COALESCE(gt.is_hyperuricemia_dx,0) AS is_hyperuricemia_dx,
       COALESCE(gt.is_ckd_dx,0) AS is_ckd_dx
FROM base b
LEFT JOIN vitals v USING (stay_id)
LEFT JOIN labs_wide lw USING (stay_id)
LEFT JOIN meds m USING (stay_id)
LEFT JOIN comorb c USING (stay_id)
LEFT JOIN gout_type gt USING (stay_id);

\echo '=== [F1] 特征表行数 ==='
SELECT count(*) AS n FROM mimic_features;

\echo '=== [F2] 关键特征覆盖率（非空占比） ==='
SELECT
  round(100.0*count(uric_acid)/count(*),1) AS uric_pct,
  round(100.0*count(creatinine)/count(*),1) AS creat_pct,
  round(100.0*count(troponin_i)/count(*),1) AS trop_i_pct,
  round(100.0*count(troponin_t)/count(*),1) AS trop_t_pct,
  round(100.0*count(ntprobnp)/count(*),1) AS bnp_pct,
  round(100.0*count(lactate)/count(*),1) AS lact_pct,
  round(100.0*count(hscrp)/count(*),1) AS hscrp_pct,
  round(100.0*count(wbc)/count(*),1) AS wbc_pct,
  round(100.0*count(platelet)/count(*),1) AS plt_pct,
  round(100.0*count(hemoglobin)/count(*),1) AS hgb_pct,
  round(100.0*count(hr_mean)/count(*),1) AS hr_pct,
  round(100.0*count(sbp_mean)/count(*),1) AS sbp_pct,
  round(100.0*count(spo2_min)/count(*),1) AS spo2_pct
FROM mimic_features;

\echo '=== [F3] 痛风分型分布 ==='
SELECT is_gout_dx, is_hyperuricemia_dx, is_ckd_dx, count(*) AS n
FROM mimic_features GROUP BY 1,2,3 ORDER BY n DESC;

\echo '=== [F4] 用药分布 ==='
SELECT
  sum(med_urate) AS urate, sum(med_colchicine) AS colch, sum(med_steroid) AS steroid,
  sum(med_aspirin) AS aspirin, sum(med_statin) AS statin, sum(med_vasopressor) AS vasop,
  sum(med_betablocker) AS bblock, sum(med_acei_arb) AS acei_arb
FROM mimic_features;