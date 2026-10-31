-- T3 特征工程 | eICU-CRD | 主队列 962 特征矩阵
-- 产物: eicu_features
-- 维度：人口学 / 生命体征(24h) / 化验(24h首值) / 用药(别嘌醇为队列定义, 其余24h) / 合并症(pasthistory)
-- 运行: psql dbname=eicu user=postgres -f p6_eicu_features.sql

DROP TABLE IF EXISTS eicu_features;

-- Step 0: 主队列 base（eicu_cohort 中排除既往 CVD）
CREATE TEMP TABLE base AS
SELECT c.*
FROM eicu_cohort c
WHERE NOT c.any_prior_cvd;

-- Step 1: 生命体征 24h 聚合（vitalperiodic: observationoffset 0-1440 分钟）
CREATE TEMP TABLE vitals AS
SELECT b.patientunitstayid,
       MIN(v.heartrate) AS hr_min, MAX(v.heartrate) AS hr_max, AVG(v.heartrate) AS hr_mean,
       AVG(v.systemicsystolic) AS sbp_mean, MIN(v.systemicsystolic) AS sbp_min,
       AVG(v.systemicdiastolic) AS dbp_mean,
       AVG(v.systemicmean) AS map_mean, MIN(v.systemicmean) AS map_min,
       AVG(v.respiration) AS rr_mean,
       MIN(v.sao2) AS spo2_min,
       AVG(v.temperature) AS temp_mean
FROM base b
JOIN vitalperiodic v USING (patientunitstayid)
WHERE v.observationoffset >= 0 AND v.observationoffset <= 1440
GROUP BY b.patientunitstayid;

-- Step 2: 化验 24h 首值（labresultoffset 0-1440）
CREATE TEMP TABLE labs_first AS
SELECT DISTINCT ON (b.patientunitstayid, grp.lab)
       b.patientunitstayid, grp.lab, l.labresult
FROM base b
JOIN lab l USING (patientunitstayid)
JOIN LATERAL (
  SELECT LOWER(l.labname) AS lname, CASE
    WHEN LOWER(l.labname) = 'uric acid' THEN 'uric_acid'
    WHEN LOWER(l.labname) = 'creatinine' THEN 'creatinine'
    WHEN LOWER(l.labname) LIKE '%troponin - i%' THEN 'troponin_i'
    WHEN LOWER(l.labname) LIKE '%troponin - t%' THEN 'troponin_t'
    WHEN LOWER(l.labname) = 'bnp' THEN 'ntprobnp'
    WHEN LOWER(l.labname) = 'lactate' THEN 'lactate'
    WHEN LOWER(l.labname) = 'crp' THEN 'crp'
    WHEN LOWER(l.labname) = 'crp-hs' THEN 'hscrp'
    WHEN LOWER(l.labname) = 'wbc x 1000' THEN 'wbc'
    WHEN LOWER(l.labname) = 'platelets x 1000' THEN 'platelet'
    WHEN LOWER(l.labname) IN ('hemoglobin','hgb') THEN 'hemoglobin'
    WHEN LOWER(l.labname) = 'sodium' THEN 'sodium'
    WHEN LOWER(l.labname) = 'potassium' THEN 'potassium'
    WHEN LOWER(l.labname) = 'chloride' THEN 'chloride'
    WHEN LOWER(l.labname) = 'bicarbonate' THEN 'bicarbonate'
    WHEN LOWER(l.labname) IN ('calcium','calcium total') THEN 'calcium'
    WHEN LOWER(l.labname) IN ('magnesium','mg') THEN 'magnesium'
    WHEN LOWER(l.labname) IN ('ck','cpk') THEN 'ck'
    WHEN LOWER(l.labname) IN ('ck-mb','cpk-mb') THEN 'ck_mb'
    WHEN LOWER(l.labname) = 'albumin' THEN 'albumin'
    WHEN LOWER(l.labname) = 'total bilirubin' THEN 'bilirubin_total'
    WHEN LOWER(l.labname) = 'glucose' THEN 'glucose'
    WHEN LOWER(l.labname) IN ('d-dimer','d dimer') THEN 'd_dimer'
    WHEN LOWER(l.labname) = 'inr' THEN 'inr'
    WHEN LOWER(l.labname) IN ('ptt','aptt') THEN 'ptt'
    WHEN LOWER(l.labname) IN ('alt','sgot') THEN 'alt'
    WHEN LOWER(l.labname) IN ('ast','sgpt') THEN 'ast'
    WHEN LOWER(l.labname) = 'bun' THEN 'bun'
    ELSE NULL END AS lab
) grp ON grp.lname IS NOT NULL AND grp.lab IS NOT NULL
WHERE l.labresultoffset >= 0 AND l.labresultoffset <= 1440
  AND l.labresult IS NOT NULL
ORDER BY b.patientunitstayid, grp.lab, l.labresultoffset;

CREATE TEMP TABLE labs_wide AS
SELECT patientunitstayid,
  MAX(CASE WHEN lab='uric_acid' THEN labresult END) AS uric_acid,
  MAX(CASE WHEN lab='creatinine' THEN labresult END) AS creatinine,
  MAX(CASE WHEN lab='troponin_i' THEN labresult END) AS troponin_i,
  MAX(CASE WHEN lab='troponin_t' THEN labresult END) AS troponin_t,
  MAX(CASE WHEN lab='ntprobnp' THEN labresult END) AS ntprobnp,
  MAX(CASE WHEN lab='lactate' THEN labresult END) AS lactate,
  MAX(CASE WHEN lab='crp' THEN labresult END) AS crp,
  MAX(CASE WHEN lab='hscrp' THEN labresult END) AS hscrp,
  MAX(CASE WHEN lab='wbc' THEN labresult END) AS wbc,
  MAX(CASE WHEN lab='platelet' THEN labresult END) AS platelet,
  MAX(CASE WHEN lab='hemoglobin' THEN labresult END) AS hemoglobin,
  MAX(CASE WHEN lab='sodium' THEN labresult END) AS sodium,
  MAX(CASE WHEN lab='potassium' THEN labresult END) AS potassium,
  MAX(CASE WHEN lab='chloride' THEN labresult END) AS chloride,
  MAX(CASE WHEN lab='bicarbonate' THEN labresult END) AS bicarbonate,
  MAX(CASE WHEN lab='calcium' THEN labresult END) AS calcium,
  MAX(CASE WHEN lab='magnesium' THEN labresult END) AS magnesium,
  MAX(CASE WHEN lab='ck' THEN labresult END) AS ck,
  MAX(CASE WHEN lab='ck_mb' THEN labresult END) AS ck_mb,
  MAX(CASE WHEN lab='albumin' THEN labresult END) AS albumin,
  MAX(CASE WHEN lab='bilirubin_total' THEN labresult END) AS bilirubin_total,
  MAX(CASE WHEN lab='glucose' THEN labresult END) AS glucose,
  MAX(CASE WHEN lab='d_dimer' THEN labresult END) AS d_dimer,
  MAX(CASE WHEN lab='inr' THEN labresult END) AS inr,
  MAX(CASE WHEN lab='ptt' THEN labresult END) AS ptt,
  MAX(CASE WHEN lab='alt' THEN labresult END) AS alt,
  MAX(CASE WHEN lab='ast' THEN labresult END) AS ast,
  MAX(CASE WHEN lab='bun' THEN labresult END) AS bun
FROM labs_first GROUP BY patientunitstayid;

-- Step 3: 用药 24h（medication 表 drugstartoffset 0-1440；别嘌醇=队列定义不计入特征避免泄漏）
CREATE TEMP TABLE meds AS
SELECT b.patientunitstayid,
       MAX(CASE WHEN m.drugname ~* 'colchicine' THEN 1 ELSE 0 END) AS med_colchicine,
       MAX(CASE WHEN m.drugname ~* 'prednisone|methylprednisolone|dexamethasone|hydrocortisone' THEN 1 ELSE 0 END) AS med_steroid,
       MAX(CASE WHEN m.drugname ~* 'aspirin' THEN 1 ELSE 0 END) AS med_aspirin,
       MAX(CASE WHEN m.drugname ~* 'clopidogrel|ticagrelor' THEN 1 ELSE 0 END) AS med_p2y12,
       MAX(CASE WHEN m.drugname ~* 'heparin|enoxaparin|warfarin|apixaban|rivaroxaban' THEN 1 ELSE 0 END) AS med_anticoag,
       MAX(CASE WHEN m.drugname ~* 'atorvastatin|rosuvastatin|simvastatin|pravastatin' THEN 1 ELSE 0 END) AS med_statin,
       MAX(CASE WHEN m.drugname ~* 'furosemide|bumetanide|hydrochlorothiazide|spironolactone' THEN 1 ELSE 0 END) AS med_diuretic,
       MAX(CASE WHEN m.drugname ~* 'norepinephrine|epinephrine|dopamine|vasopressin|phenylephrine|dobutamine' THEN 1 ELSE 0 END) AS med_vasopressor,
       MAX(CASE WHEN m.drugname ~* 'metoprolol|carvedilol|bisoprolol|propranolol' THEN 1 ELSE 0 END) AS med_betablocker,
       MAX(CASE WHEN m.drugname ~* 'lisinopril|enalapril|ramipril|losartan|valsartan' THEN 1 ELSE 0 END) AS med_acei_arb
FROM base b
JOIN medication m USING (patientunitstayid)
WHERE m.drugstartoffset >= 0 AND m.drugstartoffset <= 1440
  AND m.drugname IS NOT NULL
GROUP BY b.patientunitstayid;

-- Step 4: 合并症（pasthistory 结构化学史：DM/HTN/CKD/COPD/肝病/肿瘤）
CREATE TEMP TABLE comorb AS
SELECT b.patientunitstayid,
       MAX(CASE WHEN ph.pasthistorypath ILIKE '%/Diabetes/%' OR ph.pasthistorypath ILIKE '%Insulin Dependent Diabetes%' OR ph.pasthistorypath ILIKE '%Non-Insulin Dependent Diabetes%' THEN 1 ELSE 0 END) AS dm,
       MAX(CASE WHEN ph.pasthistorypath ILIKE '%Hypertension%' THEN 1 ELSE 0 END) AS hypertension,
       MAX(CASE WHEN ph.pasthistorypath ILIKE '%Renal Failure%' OR ph.pasthistorypath ILIKE '%Renal Insufficiency%' THEN 1 ELSE 0 END) AS ckd,
       MAX(CASE WHEN ph.pasthistorypath ILIKE '%COPD%' OR ph.pasthistorypath ILIKE '%Emphysema%' THEN 1 ELSE 0 END) AS copd,
       MAX(CASE WHEN ph.pasthistorypath ILIKE '%Cirrhosis%' OR ph.pasthistorypath ILIKE '%Hepatic%' OR ph.pasthistorypath ILIKE '%Liver%' THEN 1 ELSE 0 END) AS liver,
       MAX(CASE WHEN ph.pasthistorypath ILIKE '%Cancer%' OR ph.pasthistorypath ILIKE '%Malignancy%' OR ph.pasthistorypath ILIKE '%Neoplasm%' THEN 1 ELSE 0 END) AS cancer
FROM base b
JOIN pasthistory ph USING (patientunitstayid)
GROUP BY b.patientunitstayid;

-- Step 5: 组装（age 已在 eicu_cohort 转为整数）
CREATE TABLE eicu_features AS
SELECT b.patientunitstayid, b.gender, b.age AS anchor_age,
       v.hr_min, v.hr_max, v.hr_mean, v.sbp_mean, v.sbp_min, v.dbp_mean, v.map_mean, v.map_min,
       v.rr_mean, v.spo2_min, v.temp_mean,
       lw.uric_acid, lw.creatinine, lw.troponin_i, lw.troponin_t, lw.ntprobnp, lw.lactate,
       lw.crp, lw.hscrp, lw.wbc, lw.platelet, lw.hemoglobin, lw.sodium, lw.potassium, lw.chloride,
       lw.bicarbonate, lw.calcium, lw.magnesium, lw.ck, lw.ck_mb, lw.albumin, lw.bilirubin_total,
       lw.glucose, lw.d_dimer, lw.inr, lw.ptt, lw.alt, lw.ast, lw.bun,
       COALESCE(m.med_colchicine,0) AS med_colchicine, COALESCE(m.med_steroid,0) AS med_steroid,
       COALESCE(m.med_aspirin,0) AS med_aspirin, COALESCE(m.med_p2y12,0) AS med_p2y12,
       COALESCE(m.med_anticoag,0) AS med_anticoag, COALESCE(m.med_statin,0) AS med_statin,
       COALESCE(m.med_diuretic,0) AS med_diuretic, COALESCE(m.med_vasopressor,0) AS med_vasopressor,
       COALESCE(m.med_betablocker,0) AS med_betablocker, COALESCE(m.med_acei_arb,0) AS med_acei_arb,
       COALESCE(c.dm,0) AS dm, COALESCE(c.hypertension,0) AS hypertension, COALESCE(c.ckd,0) AS ckd,
       COALESCE(c.copd,0) AS copd, COALESCE(c.liver,0) AS liver, COALESCE(c.cancer,0) AS cancer
FROM base b
LEFT JOIN vitals v USING (patientunitstayid)
LEFT JOIN labs_wide lw USING (patientunitstayid)
LEFT JOIN meds m USING (patientunitstayid)
LEFT JOIN comorb c USING (patientunitstayid);

\echo '=== [E-F1] eICU 特征表行数 ==='
SELECT count(*) AS n FROM eicu_features;

\echo '=== [E-F2] 关键特征覆盖率 ==='
SELECT
  round(100.0*count(uric_acid)/count(*),1) AS uric_pct,
  round(100.0*count(creatinine)/count(*),1) AS creat_pct,
  round(100.0*count(troponin_i)/count(*),1) AS trop_i_pct,
  round(100.0*count(ntprobnp)/count(*),1) AS bnp_pct,
  round(100.0*count(lactate)/count(*),1) AS lact_pct,
  round(100.0*count(crp)/count(*),1) AS crp_pct,
  round(100.0*count(wbc)/count(*),1) AS wbc_pct,
  round(100.0*count(platelet)/count(*),1) AS plt_pct,
  round(100.0*count(hr_mean)/count(*),1) AS hr_pct,
  round(100.0*count(sbp_mean)/count(*),1) AS sbp_pct
FROM eicu_features;