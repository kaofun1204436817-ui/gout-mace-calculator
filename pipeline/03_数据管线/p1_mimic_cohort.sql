-- T1 队列构建 | Phase 1 正式队列 | MIMIC-IV
-- 纳入: 痛风(274/M10) + ICU成人(>=18) + 首次ICU停留
-- 排除: 索引入院之前任一入院记录中含 MI/卒中/心衰 编码 => 视为入院前已患
-- 输出: mimic_cohort 表 (stay级)
-- 运行: psql "host=localhost port=5432 dbname=mimic user=mimic password=mimic" -f p1_mimic_cohort.sql

DROP TABLE IF EXISTS mimic_cohort;

-- Step 1: 痛风+ICU 首次停留
CREATE TEMP TABLE gout_icu AS
WITH gout AS (
  SELECT DISTINCT d.subject_id, d.hadm_id
  FROM mimiciv_hosp.diagnoses_icd d
  JOIN mimiciv_hosp.d_icd_diagnoses dd
    ON d.icd_code = dd.icd_code AND d.icd_version = dd.icd_version
  WHERE (dd.icd_version = 9  AND dd.icd_code LIKE '274%')
     OR (dd.icd_version = 10 AND dd.icd_code LIKE 'M10%')
),
icu_rank AS (
  SELECT i.subject_id, i.hadm_id, i.stay_id, i.intime, i.outtime,
         ROW_NUMBER() OVER (PARTITION BY i.subject_id ORDER BY i.intime, i.stay_id) AS icu_rn
  FROM mimiciv_icu.icustays i
  JOIN mimiciv_hosp.patients p ON p.subject_id = i.subject_id
  WHERE p.anchor_age >= 18
)
SELECT g.subject_id, a.hadm_id, a.stay_id, a.intime, a.outtime
FROM gout g
JOIN icu_rank a ON a.subject_id = g.subject_id AND a.hadm_id = g.hadm_id AND a.icu_rn = 1
JOIN mimiciv_hosp.admissions adm ON adm.hadm_id = a.hadm_id;

-- Step 2: 既往史判定（索引入院之前的入院记录）
CREATE TEMP TABLE priors AS
SELECT d.subject_id,
       MAX(CASE WHEN d.icd_code ~ '^(410|411|I21|I22)'            THEN 1 ELSE 0 END) AS prior_mi,
       MAX(CASE WHEN d.icd_code ~ '^(430|431|432|433|434|435|436|I60|I61|I62|I63|I64|G45)' THEN 1 ELSE 0 END) AS prior_stroke,
       MAX(CASE WHEN d.icd_code ~ '^(402|404|428|I50|I11|I13)'   THEN 1 ELSE 0 END) AS prior_hf
FROM gout_icu g
JOIN mimiciv_hosp.diagnoses_icd d ON d.subject_id = g.subject_id
WHERE d.hadm_id <> g.hadm_id   -- 只能看"之前"的入院
GROUP BY d.subject_id;

-- 注意: 上面 WHERE 只排除了同次, 还需限定时间先后; 用 admissions 的 admittime 更严谨:
CREATE TEMP TABLE priors_t AS
SELECT g.subject_id,
       MAX(CASE WHEN d.icd_code ~ '^(410|411|I21|I22)'            THEN 1 ELSE 0 END) AS prior_mi,
       MAX(CASE WHEN d.icd_code ~ '^(430|431|432|433|434|435|436|I60|I61|I62|I63|I64|G45)' THEN 1 ELSE 0 END) AS prior_stroke,
       MAX(CASE WHEN d.icd_code ~ '^(402|404|428|I50|I11|I13)'   THEN 1 ELSE 0 END) AS prior_hf
FROM gout_icu g
JOIN mimiciv_hosp.diagnoses_icd d ON d.subject_id = g.subject_id
JOIN mimiciv_hosp.admissions adm ON adm.hadm_id = d.hadm_id
JOIN mimiciv_hosp.admissions gadm ON gadm.hadm_id = g.hadm_id
WHERE d.hadm_id <> g.hadm_id AND adm.admittime < gadm.admittime
GROUP BY g.subject_id;

-- Step 3: 正式队列（含既往标志，保留供敏感性分析）
CREATE TABLE mimic_cohort AS
SELECT g.subject_id, g.hadm_id, g.stay_id, g.intime, g.outtime,
       COALESCE(pt.prior_mi,0) AS prior_mi,
       COALESCE(pt.prior_stroke,0) AS prior_stroke,
       COALESCE(pt.prior_hf,0) AS prior_hf,
       (COALESCE(pt.prior_mi,0) + COALESCE(pt.prior_stroke,0) + COALESCE(pt.prior_hf,0)) > 0 AS any_prior_mace_dx,
       adm.admittime, adm.dischtime, adm.admission_type, adm.hospital_expire_flag,
       p.gender, p.anchor_age, p.dod
FROM gout_icu g
JOIN mimiciv_hosp.admissions adm ON adm.hadm_id = g.hadm_id
JOIN mimiciv_hosp.patients p ON p.subject_id = g.subject_id
LEFT JOIN priors_t pt ON pt.subject_id = g.subject_id;

\echo '=== [P1-1] 队列总量 ==='
SELECT count(*) AS total_stays, count(DISTINCT subject_id) AS n_patients FROM mimic_cohort;

\echo '=== [P1-2] 既往史分布 ==='
SELECT prior_mi, prior_stroke, prior_hf, any_prior_mace_dx, count(*) AS n
FROM mimic_cohort GROUP BY 1,2,3,4 ORDER BY n DESC;

\echo '=== [P1-3] 主队列（排除任何既往 MACE 诊断） ==='
SELECT count(*) AS n_stays, count(DISTINCT subject_id) AS n_patients
FROM mimic_cohort WHERE NOT any_prior_mace_dx;

\echo '=== [P1-4] 性别/年龄分布（主队列） ==='
SELECT gender, count(*) AS n, round(avg(anchor_age)::numeric,1) AS mean_age
FROM mimic_cohort WHERE NOT any_prior_mace_dx GROUP BY gender;

\echo '=== [P1-5] admission_type 分布（主队列） ==='
SELECT admission_type, count(*) AS n
FROM mimic_cohort WHERE NOT any_prior_mace_dx GROUP BY admission_type ORDER BY n DESC;