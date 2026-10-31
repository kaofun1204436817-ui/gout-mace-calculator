-- T1 队列构建 | Phase 0 探测 | MIMIC-IV
-- 只读：痛风人群口径验证 + ICU 交集 + 事件 ICD 编码覆盖
-- 运行: psql "host=localhost port=5432 dbname=mimic user=mimic password=mimic" -f p0_mimic_probe.sql

\echo '=== [P0-1] 痛风诊断总人群（ICD-9 274% / ICD-10 M10%） ==='
SELECT count(DISTINCT d.subject_id) AS n_patients,
       count(DISTINCT d.hadm_id)   AS n_admissions
FROM mimiciv_hosp.diagnoses_icd d
JOIN mimiciv_hosp.d_icd_diagnoses dd
  ON d.icd_code = dd.icd_code AND d.icd_version = dd.icd_version
WHERE (dd.icd_version = 9  AND dd.icd_code LIKE '274%')
   OR (dd.icd_version = 10 AND dd.icd_code LIKE 'M10%');

\echo '=== [P0-2] 痛风 + ICU 停留 交集 ==='
SELECT count(DISTINCT p.subject_id) AS n_icu_patients,
       count(DISTINCT i.hadm_id)    AS n_icu_admissions,
       count(DISTINCT i.stay_id)    AS n_icu_stays
FROM mimiciv_hosp.diagnoses_icd d
JOIN mimiciv_hosp.d_icd_diagnoses dd
  ON d.icd_code = dd.icd_code AND d.icd_version = dd.icd_version
JOIN mimiciv_icu.icustays i
  ON i.subject_id = d.subject_id AND i.hadm_id = d.hadm_id
JOIN mimiciv_hosp.patients p ON p.subject_id = d.subject_id
WHERE (dd.icd_version = 9  AND dd.icd_code LIKE '274%')
   OR (dd.icd_version = 10 AND dd.icd_code LIKE 'M10%');

\echo '=== [P0-3] 痛风成人(>=18) ICU 人群（首次ICU停留口径） ==='
WITH gout AS (
  SELECT DISTINCT d.subject_id, d.hadm_id
  FROM mimiciv_hosp.diagnoses_icd d
  JOIN mimiciv_hosp.d_icd_diagnoses dd
    ON d.icd_code = dd.icd_code AND d.icd_version = dd.icd_version
  WHERE (dd.icd_version = 9  AND dd.icd_code LIKE '274%')
     OR (dd.icd_version = 10 AND dd.icd_code LIKE 'M10%')
),
adult_icu AS (
  SELECT i.subject_id, i.hadm_id, i.stay_id, i.intime, i.outtime,
         ROW_NUMBER() OVER (PARTITION BY i.subject_id ORDER BY i.intime) AS icu_rn
  FROM mimiciv_icu.icustays i
  JOIN mimiciv_hosp.patients p ON p.subject_id = i.subject_id
  WHERE p.anchor_age >= 18
)
SELECT count(DISTINCT g.subject_id) AS n_gout_icu_patients,
       count(DISTINCT g.hadm_id)    AS n_gout_icu_admissions,
       count(*)                     AS n_gout_icu_stays,
       count(DISTINCT CASE WHEN a.icu_rn = 1 THEN a.subject_id END) AS n_first_icu
FROM gout g JOIN adult_icu a ON a.subject_id = g.subject_id AND a.hadm_id = g.hadm_id;

\echo '=== [P0-4] MACE 事件 ICD 编码覆盖（痛风ICU人群内） ==='
WITH gout_icu AS (
  SELECT DISTINCT i.subject_id, i.hadm_id, i.stay_id
  FROM mimiciv_hosp.diagnoses_icd d
  JOIN mimiciv_hosp.d_icd_diagnoses dd
    ON d.icd_code = dd.icd_code AND d.icd_version = dd.icd_version
  JOIN mimiciv_icu.icustays i ON i.subject_id = d.subject_id AND i.hadm_id = d.hadm_id
  JOIN mimiciv_hosp.patients p ON p.subject_id = d.subject_id
  WHERE ((dd.icd_version = 9  AND dd.icd_code LIKE '274%')
     OR  (dd.icd_version = 10 AND dd.icd_code LIKE 'M10%'))
    AND p.anchor_age >= 18
)
SELECT
  count(DISTINCT g.subject_id) AS n_total,
  count(DISTINCT CASE WHEN d.icd_code ~ '^(410|411|I21|I22)' THEN g.subject_id END) AS n_mi,
  count(DISTINCT CASE WHEN d.icd_code ~ '^(430|431|432|433|434|435|436|I60|I61|I62|I63|I64|G45)' THEN g.subject_id END) AS n_stroke_tia,
  count(DISTINCT CASE WHEN d.icd_code ~ '^(402|404|428|I50|I11|I13)' THEN g.subject_id END) AS n_hf,
  count(DISTINCT CASE WHEN d.icd_code ~ '^(78551|I46)' THEN g.subject_id END) AS n_sca,
  count(DISTINCT CASE WHEN d.icd_code ~ '^(42741|4275|4271|I472|I471|I49)' THEN g.subject_id END) AS n_arrhythmia,
  count(DISTINCT CASE WHEN d.icd_code ~ '^(4275|78551|I50|R57|I46)' THEN g.subject_id END) AS n_shock
FROM gout_icu g
JOIN mimiciv_hosp.diagnoses_icd d
  ON d.subject_id = g.subject_id AND d.hadm_id = g.hadm_id;