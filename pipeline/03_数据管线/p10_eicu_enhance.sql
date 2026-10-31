-- 特征增强 V4 | eICU | 补 GCS总分/透析/机械通气（apacheapsvar 入院时评估）
-- 运行: psql dbname=eicu user=postgres

-- 先确认 apacheapsvar 中 GCS 组分与标志的覆盖率
\echo '=== [V4-E1] apacheapsvar 在别嘌醇主队列中的覆盖 ==='
SELECT count(DISTINCT b.patientunitstayid) AS n_base,
       count(DISTINCT CASE WHEN a.patientunitstayid IS NOT NULL THEN b.patientunitstayid END) AS n_aps,
       count(DISTINCT CASE WHEN a.eyes IS NOT NULL AND a.motor IS NOT NULL AND a.verbal IS NOT NULL THEN b.patientunitstayid END) AS n_gcs3
FROM (SELECT patientunitstayid FROM eicu_cohort WHERE NOT any_prior_cvd) b
LEFT JOIN apacheapsvar a USING (patientunitstayid);

-- 给 eicu_features 补列
ALTER TABLE eicu_features ADD COLUMN IF NOT EXISTS gcs_total numeric;
ALTER TABLE eicu_features ADD COLUMN IF NOT EXISTS dialysis_flag int;
ALTER TABLE eicu_features ADD COLUMN IF NOT EXISTS vent_flag int;

UPDATE eicu_features f
SET gcs_total = a.eyes + a.motor + a.verbal,
    dialysis_flag = COALESCE(a.dialysis, 0),
    vent_flag = COALESCE(a.vent, 0)
FROM apacheapsvar a
WHERE f.patientunitstayid = a.patientunitstayid;

\echo '=== [V4-E2] 增强后覆盖 ==='
SELECT count(gcs_total) AS n_gcs, round(100.0*count(gcs_total)/count(*),1) AS gcs_pct,
       sum(dialysis_flag) AS n_dial, sum(vent_flag) AS n_vent
FROM eicu_features;