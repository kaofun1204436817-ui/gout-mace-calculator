-- V5 特征扩展 | MIMIC | 生命体征极值/趋势 + 缺失指示
-- 运行: psql dbname=mimic

CREATE TEMP TABLE base AS
SELECT c.subject_id, c.hadm_id, c.stay_id, c.intime
FROM mimic_cohort c WHERE NOT c.any_prior_mace_dx;

-- 扩展生命体征聚合：极值 + 变异度（24h）
CREATE TEMP TABLE vitals_v5 AS
SELECT b.stay_id,
       -- 心率
       MIN(CASE WHEN ce.itemid=220045 THEN ce.valuenum END) AS hr_min,
       MAX(CASE WHEN ce.itemid=220045 THEN ce.valuenum END) AS hr_max,
       AVG(CASE WHEN ce.itemid=220045 THEN ce.valuenum END) AS hr_mean,
       STDDEV(CASE WHEN ce.itemid=220045 THEN ce.valuenum END) AS hr_std,
       -- 收缩压
       AVG(CASE WHEN ce.itemid IN (220050,220179) THEN ce.valuenum END) AS sbp_mean,
       MIN(CASE WHEN ce.itemid IN (220050,220179) THEN ce.valuenum END) AS sbp_min,
       MAX(CASE WHEN ce.itemid IN (220050,220179) THEN ce.valuenum END) AS sbp_max,
       -- 舒张压
       AVG(CASE WHEN ce.itemid IN (220051,220180) THEN ce.valuenum END) AS dbp_mean,
       MIN(CASE WHEN ce.itemid IN (220051,220180) THEN ce.valuenum END) AS dbp_min,
       -- 平均动脉压
       AVG(CASE WHEN ce.itemid IN (220052,220181) THEN ce.valuenum END) AS map_mean,
       MIN(CASE WHEN ce.itemid IN (220052,220181) THEN ce.valuenum END) AS map_min,
       MAX(CASE WHEN ce.itemid IN (220052,220181) THEN ce.valuenum END) AS map_max,
       -- 呼吸
       AVG(CASE WHEN ce.itemid=220210 THEN ce.valuenum END) AS rr_mean,
       MAX(CASE WHEN ce.itemid=220210 THEN ce.valuenum END) AS rr_max,
       -- 血氧
       MIN(CASE WHEN ce.itemid=220277 THEN ce.valuenum END) AS spo2_min,
       AVG(CASE WHEN ce.itemid=220277 THEN ce.valuenum END) AS spo2_mean,
       -- 体温
       AVG(CASE WHEN ce.itemid=223762 THEN ce.valuenum END) AS temp_mean,
       MIN(CASE WHEN ce.itemid=223762 THEN ce.valuenum END) AS temp_min,
       MAX(CASE WHEN ce.itemid=223762 THEN ce.valuenum END) AS temp_max
FROM base b
JOIN mimiciv_icu.chartevents ce ON ce.stay_id = b.stay_id
  AND ce.charttime >= b.intime AND ce.charttime < b.intime + interval '24 hours'
  AND ce.itemid IN (220045,220050,220051,220052,220179,220180,220181,220210,220277,223762)
  AND ce.valuenum IS NOT NULL
GROUP BY b.stay_id;

-- 重建 mimic_features 的生命体征部分（加新列）
ALTER TABLE mimic_features ADD COLUMN IF NOT EXISTS hr_std numeric;
ALTER TABLE mimic_features ADD COLUMN IF NOT EXISTS sbp_max numeric;
ALTER TABLE mimic_features ADD COLUMN IF NOT EXISTS dbp_min numeric;
ALTER TABLE mimic_features ADD COLUMN IF NOT EXISTS map_max numeric;
ALTER TABLE mimic_features ADD COLUMN IF NOT EXISTS rr_max numeric;
ALTER TABLE mimic_features ADD COLUMN IF NOT EXISTS spo2_mean numeric;
ALTER TABLE mimic_features ADD COLUMN IF NOT EXISTS temp_min numeric;
ALTER TABLE mimic_features ADD COLUMN IF NOT EXISTS temp_max numeric;
UPDATE mimic_features f SET
  hr_std = v.hr_std, sbp_max = v.sbp_max, dbp_min = v.dbp_min,
  map_max = v.map_max, rr_max = v.rr_max, spo2_mean = v.spo2_mean,
  temp_min = v.temp_min, temp_max = v.temp_max
FROM vitals_v5 v WHERE f.stay_id = v.stay_id;

\echo '=== [V5-M] 新生命体征特征覆盖 ==='
SELECT count(hr_std) AS n_hrstd, round(100.0*count(hr_std)/count(*),1) AS hrstd_pct,
       count(sbp_max) AS n_sbpmax, count(spo2_mean) AS n_spo2m,
       count(temp_max) AS n_tmax, count(rr_max) AS n_rrmax
FROM mimic_features;