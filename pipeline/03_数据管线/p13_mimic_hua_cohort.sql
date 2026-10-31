-- T5-亚组 | MIMIC-IV 单纯高尿酸 (hyperuricemia-only) 比较队列
-- 目的: 三组亚组比较 (单纯高尿酸 vs 确诊痛风 vs 痛风合并CKD)
-- 定义: 高尿酸血症 = ICD-10 E79.x / ICD-9 790.6; 排除合并痛风者; 成人; 首次ICU
-- 既往史排除口径与主队列一致 (索引入院之前历次入院 MI/卒中/心衰)
-- 产物: mimic_hua_cohort (hyperuricemia-only, stay级)

DROP TABLE IF EXISTS mimic_hua_cohort;

WITH hua AS (  -- 高尿酸血症患者 (全住院, 不含痛风)
  SELECT DISTINCT d.subject_id, d.hadm_id
  FROM mimiciv_hosp.diagnoses_icd d
  JOIN mimiciv_hosp.d_icd_diagnoses dd
    ON d.icd_code = dd.icd_code AND d.icd_version = dd.icd_version
  WHERE (dd.icd_version = 9  AND dd.icd_code IN ('7906','790.6'))
     OR (dd.icd_version = 10 AND dd.icd_code LIKE 'E79%')
),
gout AS (  -- 痛风患者全集 (用于排除)
  SELECT DISTINCT d.subject_id
  FROM mimiciv_hosp.diagnoses_icd d
  JOIN mimiciv_hosp.d_icd_diagnoses dd
    ON d.icd_code = dd.icd_code AND d.icd_version = dd.icd_version
  WHERE (dd.icd_version = 9  AND dd.icd_code LIKE '274%')
     OR (dd.icd_version = 10 AND dd.icd_code LIKE 'M10%')
),
hua_icu AS (  -- 高尿酸血症 ∩ ICU, 成人, 首次 ICU 停留
  SELECT i.subject_id, i.hadm_id, i.stay_id, i.intime,
         ROW_NUMBER() OVER (PARTITION BY i.subject_id ORDER BY i.intime, i.stay_id) AS icu_rn
  FROM hua h
  JOIN mimiciv_icu.icustays i USING (subject_id, hadm_id)
  JOIN mimiciv_hosp.patients p ON p.subject_id = i.subject_id
  WHERE p.anchor_age >= 18
    AND NOT EXISTS (SELECT 1 FROM gout g WHERE g.subject_id = h.subject_id)
),
priors AS (  -- 既往史 (索引入院之前)
  SELECT g.subject_id,
         MAX(CASE WHEN d.icd_code ~ '^(410|411|I21|I22)' THEN 1 ELSE 0 END) AS prior_mi,
         MAX(CASE WHEN d.icd_code ~ '^(430|431|432|433|434|435|436|I60|I61|I62|I63|I64)' THEN 1 ELSE 0 END) AS prior_stroke,
         MAX(CASE WHEN d.icd_code ~ '^(402|404|428|I50|I11|I13)' THEN 1 ELSE 0 END) AS prior_hf
  FROM hua_icu g
  JOIN mimiciv_hosp.diagnoses_icd d ON d.subject_id = g.subject_id
  JOIN mimiciv_hosp.admissions a ON a.hadm_id = d.hadm_id
  JOIN mimiciv_hosp.admissions ga ON ga.hadm_id = g.hadm_id
  WHERE d.hadm_id <> g.hadm_id AND a.admittime < ga.admittime
  GROUP BY g.subject_id
),
coh AS (
  SELECT g.*, COALESCE(p.prior_mi,0) AS prior_mi, COALESCE(p.prior_stroke,0) AS prior_stroke,
         COALESCE(p.prior_hf,0) AS prior_hf,
         (COALESCE(p.prior_mi,0)+COALESCE(p.prior_stroke,0)+COALESCE(p.prior_hf,0)) > 0 AS any_prior_cvd
  FROM hua_icu g LEFT JOIN priors p USING (subject_id)
  WHERE g.icu_rn = 1
),
ev AS (  -- 6事件定义 (与主队列 p2_v3 完全一致)
  SELECT c.stay_id,
    MAX(((d.icd_version=9 AND d.icd_code ~ '^410') OR
         (d.icd_version=10 AND (d.icd_code ~ '^I21' OR d.icd_code ~ '^I22')))::int) AS ev_ami,
    MAX(((d.icd_version=9 AND (d.icd_code ~ '^43[0-4]' OR d.icd_code = '436')) OR
         (d.icd_version=10 AND d.icd_code ~ '^I6[0-4]'))::int) AS ev_stroke,
    MAX(((d.icd_version=9 AND d.icd_code IN ('4271','42741','4275')) OR
         (d.icd_version=10 AND (d.icd_code ~ '^I46' OR d.icd_code ~ '^I490' OR d.icd_code ~ '^I472')))::int) AS ev_malarr,
    MAX(((d.icd_version=9 AND d.icd_code = '78551') OR
         (d.icd_version=10 AND d.icd_code ~ '^R570'))::int) AS ev_cardshk,
    MAX(((d.icd_version=9 AND d.icd_code IN ('42821','42823','42831','42833','42841','42843')) OR
         (d.icd_version=10 AND d.icd_code IN ('I5021','I5023','I5031','I5033','I5041','I5043','I50811','I50813')))::int) AS ev_hfacu
  FROM coh c JOIN mimiciv_hosp.diagnoses_icd d USING (hadm_id)
  GROUP BY c.stay_id
)
SELECT c.subject_id, c.hadm_id, c.stay_id, c.intime,
       c.any_prior_cvd, COALESCE(c.prior_mi,0) AS prior_mi,
       COALESCE(c.prior_stroke,0) AS prior_stroke, COALESCE(c.prior_hf,0) AS prior_hf,
       a.hospital_expire_flag,
       COALESCE(e.ev_ami,0) AS ev_ami, COALESCE(e.ev_stroke,0) AS ev_stroke,
       COALESCE(e.ev_malarr,0) AS ev_malarr, COALESCE(e.ev_cardshk,0) AS ev_cardshk,
       COALESCE(e.ev_hfacu,0) AS ev_hfacu,
       (COALESCE(e.ev_ami,0)=1 OR COALESCE(e.ev_stroke,0)=1 OR COALESCE(e.ev_malarr,0)=1
        OR COALESCE(e.ev_cardshk,0)=1 OR COALESCE(e.ev_hfacu,0)=1
        OR (a.hospital_expire_flag=1 AND (COALESCE(e.ev_ami,0)+COALESCE(e.ev_stroke,0)+COALESCE(e.ev_malarr,0)
            +COALESCE(e.ev_cardshk,0)+COALESCE(e.ev_hfacu,0) > 0)))::int AS mace,
       (COALESCE(e.ev_ami,0)=1 OR COALESCE(e.ev_stroke,0)=1 OR a.hospital_expire_flag=1)::int AS mace3
INTO mimic_hua_cohort
FROM coh c
JOIN mimiciv_hosp.admissions a USING (hadm_id)
LEFT JOIN ev e USING (stay_id);

\echo '=== [H1] 高尿酸队列 (未排除既往) ==='
SELECT count(*) AS n_total, sum((NOT any_prior_cvd)::int) AS n_no_prior,
       sum(mace) AS mace6, sum(mace3) AS mace3
FROM mimic_hua_cohort;

\echo '=== [H2] 主口径 (排除既往) ==='
SELECT count(*) AS n, sum(mace) AS mace6, round(100.0*sum(mace)/count(*),2) AS pct6,
       sum(mace3) AS mace3, round(100.0*sum(mace3)/count(*),2) AS pct3
FROM mimic_hua_cohort WHERE NOT any_prior_cvd;