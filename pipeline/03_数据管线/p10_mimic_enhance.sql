-- 特征增强 V4 | MIMIC | GCS总分(24h组分求和) 与导管/透析近似标志
-- 运行: psql dbname=mimic

-- Step 1: GCS 三组分 24h 最小值求和（与 eICU apacheapsvar GCS 总分对齐）
CREATE TEMP TABLE base AS
SELECT c.subject_id, c.hadm_id, c.stay_id, c.intime
FROM mimic_cohort c WHERE NOT c.any_prior_mace_dx;

CREATE TEMP TABLE gcs_comp AS
SELECT b.stay_id,
       MIN(CASE WHEN ce.itemid=220739 THEN ce.valuenum END) AS gcs_eye,
       MIN(CASE WHEN ce.itemid=223900 THEN ce.valuenum END) AS gcs_verbal,
       MIN(CASE WHEN ce.itemid=223901 THEN ce.valuenum END) AS gcs_motor
FROM base b
JOIN mimiciv_icu.chartevents ce ON ce.stay_id = b.stay_id
  AND ce.charttime >= b.intime AND ce.charttime < b.intime + interval '24 hours'
  AND ce.itemid IN (220739, 223900, 223901) AND ce.valuenum IS NOT NULL
GROUP BY b.stay_id;

-- Step 2: 24h 内机械通气（ventilation 相关 item，ChartEvents 常用 224686/224687/224695）
CREATE TEMP TABLE vent AS
SELECT b.stay_id,
       MAX(CASE WHEN ce.itemid IN (224686,224687,224695,225792) THEN 1 ELSE 0 END) AS vent_flag
FROM base b
JOIN mimiciv_icu.chartevents ce ON ce.stay_id = b.stay_id
  AND ce.charttime >= b.intime AND ce.charttime < b.intime + interval '24 hours'
  AND ce.itemid IN (224686,224687,224695,225792)
GROUP BY b.stay_id;

-- Step 3: 透析（本次住院 procedures_icd: ICD9 39.95 / ICD10 5A1D ）
CREATE TEMP TABLE dial AS
SELECT b.stay_id,
       MAX(CASE WHEN pi.icd_code ~ '^(3995|5A1D)' THEN 1 ELSE 0 END) AS dialysis_flag
FROM base b
JOIN mimiciv_hosp.procedures_icd pi ON pi.hadm_id = b.hadm_id
GROUP BY b.stay_id;

-- Step 4: 写回 mimic_features
ALTER TABLE mimic_features ADD COLUMN IF NOT EXISTS gcs_total numeric;
ALTER TABLE mimic_features ADD COLUMN IF NOT EXISTS dialysis_flag int DEFAULT 0;
ALTER TABLE mimic_features ADD COLUMN IF NOT EXISTS vent_flag int DEFAULT 0;
UPDATE mimic_features f SET gcs_total = g.gcs_eye + g.gcs_verbal + g.gcs_motor FROM gcs_comp g WHERE f.stay_id = g.stay_id;
UPDATE mimic_features f SET dialysis_flag = COALESCE(d.dialysis_flag,0) FROM dial d WHERE f.stay_id = d.stay_id;
UPDATE mimic_features f SET vent_flag = COALESCE(v.vent_flag,0) FROM vent v WHERE f.stay_id = v.stay_id;

\echo '=== [V4-M1] GCS/透析/通气 覆盖 ==='
SELECT count(gcs_total) AS n_gcs, round(100.0*count(gcs_total)/count(*),1) AS gcs_pct,
       sum(dialysis_flag) AS n_dial, sum(vent_flag) AS n_vent
FROM mimic_features;