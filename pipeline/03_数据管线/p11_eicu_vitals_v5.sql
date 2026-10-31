-- V5 特征扩展 | eICU | 生命体征极值/趋势（与 MIMIC 对齐）
-- 运行: psql dbname=eicu user=postgres

CREATE TEMP TABLE base AS
SELECT patientunitstayid FROM eicu_cohort WHERE NOT any_prior_cvd;

CREATE TEMP TABLE vitals_v5 AS
SELECT b.patientunitstayid,
       MIN(v.heartrate) AS hr_min, MAX(v.heartrate) AS hr_max, AVG(v.heartrate) AS hr_mean,
       STDDEV(v.heartrate) AS hr_std,
       AVG(v.systemicsystolic) AS sbp_mean, MIN(v.systemicsystolic) AS sbp_min, MAX(v.systemicsystolic) AS sbp_max,
       AVG(v.systemicdiastolic) AS dbp_mean, MIN(v.systemicdiastolic) AS dbp_min,
       AVG(v.systemicmean) AS map_mean, MIN(v.systemicmean) AS map_min, MAX(v.systemicmean) AS map_max,
       AVG(v.respiration) AS rr_mean, MAX(v.respiration) AS rr_max,
       MIN(v.sao2) AS spo2_min, AVG(v.sao2) AS spo2_mean,
       AVG(v.temperature) AS temp_mean, MIN(v.temperature) AS temp_min, MAX(v.temperature) AS temp_max
FROM base b
JOIN vitalperiodic v USING (patientunitstayid)
WHERE v.observationoffset >= 0 AND v.observationoffset <= 1440
GROUP BY b.patientunitstayid;

ALTER TABLE eicu_features ADD COLUMN IF NOT EXISTS hr_std numeric;
ALTER TABLE eicu_features ADD COLUMN IF NOT EXISTS sbp_max numeric;
ALTER TABLE eicu_features ADD COLUMN IF NOT EXISTS dbp_min numeric;
ALTER TABLE eicu_features ADD COLUMN IF NOT EXISTS map_max numeric;
ALTER TABLE eicu_features ADD COLUMN IF NOT EXISTS rr_max numeric;
ALTER TABLE eicu_features ADD COLUMN IF NOT EXISTS spo2_mean numeric;
ALTER TABLE eicu_features ADD COLUMN IF NOT EXISTS temp_min numeric;
ALTER TABLE eicu_features ADD COLUMN IF NOT EXISTS temp_max numeric;
UPDATE eicu_features f SET
  hr_std = v.hr_std, sbp_max = v.sbp_max, dbp_min = v.dbp_min,
  map_max = v.map_max, rr_max = v.rr_max, spo2_mean = v.spo2_mean,
  temp_min = v.temp_min, temp_max = v.temp_max
FROM vitals_v5 v WHERE f.patientunitstayid = v.patientunitstayid;

\echo '=== [V5-E] 新生命体征特征覆盖 ==='
SELECT count(hr_std) AS n_hrstd, round(100.0*count(hr_std)/count(*),1) AS hrstd_pct,
       count(sbp_max) AS n_sbpmax, count(spo2_mean) AS n_spo2m,
       count(temp_max) AS n_tmax, count(rr_max) AS n_rrmax
FROM eicu_features;