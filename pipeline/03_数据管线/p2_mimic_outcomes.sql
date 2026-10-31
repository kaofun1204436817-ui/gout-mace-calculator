-- T2 事件定义 | MIMIC-IV | 主队列上计算 6 事件 + 复合 MACE
-- 事件口径（保守主分析）：
--   AMI      : ICD9 410.x / ICD10 I21.x,I22.x
--   Stroke   : ICD9 430-434,436 / ICD10 I60-I64   (不含 TIA 435/G45, 敏感分析纳入)
--   CardiacD : hospital_expire_flag=1 且本次住院诊断含任一心血管事件码
--   CardiShk : ICD9 785.51 / ICD10 R57.0
--   MalArr   : ICD9 427.1,427.41,427.5 / ICD10 I47.2,I49.0,I46
--   HFAcu    : ICD9 428.x / ICD10 I50.x  (主队列已排除既往HF)
-- 复合 MACE  = 任一事件（独立事件, 一人一事件记时取最先）

-- Step 0: 事件诊断表（本次住院）
CREATE TEMP TABLE diag_event AS
SELECT c.subject_id, c.hadm_id, c.stay_id,
       d.icd_code, d.icd_version,
       (d.icd_version=9  AND (d.icd_code ~ '^410' OR d.icd_code ~ '^4110')) OR
       (d.icd_version=10 AND (d.icd_code ~ '^I21' OR d.icd_code ~ '^I22')) AS ev_ami,
       (d.icd_version=9  AND (d.icd_code ~ '^43[0-4]' OR d.icd_code = '436')) OR
       (d.icd_version=10 AND d.icd_code ~ '^I6[0-4]') AS ev_stroke,
       (d.icd_version=9  AND (d.icd_code ~ '^4271' OR d.icd_code ~ '^42741' OR d.icd_code ~ '^4275')) OR
       (d.icd_version=10 AND (d.icd_code ~ '^I472' OR d.icd_code ~ '^I490' OR d.icd_code ~ '^I46')) AS ev_malarr,
       (d.icd_version=9  AND d.icd_code = '78551') OR
       (d.icd_version=10 AND d.icd_code ~ '^R57') AS ev_cardshk,
       (d.icd_version=9  AND d.icd_code ~ '^428') OR
       (d.icd_version=10 AND d.icd_code ~ '^I50') AS ev_hfacu,
       (d.icd_version=9  AND (d.icd_code ~ '^41[0-9]' OR d.icd_code ~ '^42[0-9]' OR d.icd_code ~ '^43[0-9]' OR d.icd_code = '78551' OR d.icd_code ~ '^4271' OR d.icd_code ~ '^42741' OR d.icd_code ~ '^4275' OR d.icd_code ~ '^428')) OR
       (d.icd_version=10 AND (d.icd_code ~ '^I' )) AS ev_any_cv   -- 心源性死亡用心血管大类
FROM mimic_cohort c
JOIN mimiciv_hosp.diagnoses_icd d ON d.hadm_id = c.hadm_id;

-- Step 1: 患者级事件汇总
CREATE TEMP TABLE ev_pat AS
SELECT subject_id, hadm_id, stay_id,
       MAX(ev_ami::int) AS ev_ami, MAX(ev_stroke::int) AS ev_stroke,
       MAX(ev_malarr::int) AS ev_malarr, MAX(ev_cardshk::int) AS ev_cardshk,
       MAX(ev_hfacu::int) AS ev_hfacu,
       MAX(CASE WHEN ev_any_cv THEN 1 ELSE 0 END) AS ev_anycv_dx
FROM diag_event
GROUP BY subject_id, hadm_id, stay_id;

-- Step 2: 拼入院死亡+主队列, 得最终事件表
DROP TABLE IF EXISTS mimic_outcomes;
CREATE TABLE mimic_outcomes AS
SELECT c.subject_id, c.hadm_id, c.stay_id,
       COALESCE(e.ev_ami,0)   AS ev_ami,
       COALESCE(e.ev_stroke,0)AS ev_stroke,
       COALESCE(e.ev_malarr,0)AS ev_malarr,
       COALESCE(e.ev_cardshk,0) AS ev_cardshk,
       COALESCE(e.ev_hfacu,0) AS ev_hfacu,
       COALESCE(e.ev_anycv_dx,0) AS ev_anycv_dx,
       c.hospital_expire_flag AS ev_death,
       (c.hospital_expire_flag=1 AND COALESCE(e.ev_anycv_dx,0)=1) AS ev_cardiac_death,
       ( (COALESCE(e.ev_ami,0)=1) OR (COALESCE(e.ev_stroke,0)=1)
         OR (c.hospital_expire_flag=1 AND COALESCE(e.ev_anycv_dx,0)=1)
         OR (COALESCE(e.ev_cardshk,0)=1) OR (COALESCE(e.ev_malarr,0)=1)
         OR (COALESCE(e.ev_hfacu,0)=1) ) AS mace,
       -- 事件计数(复合强度)
       COALESCE(e.ev_ami,0)+COALESCE(e.ev_stroke,0)+COALESCE(e.ev_malarr,0)
       +COALESCE(e.ev_cardshk,0)+COALESCE(e.ev_hfacu,0)
       +(CASE WHEN c.hospital_expire_flag=1 AND COALESCE(e.ev_anycv_dx,0)=1 THEN 1 ELSE 0 END) AS n_events
FROM mimic_cohort c
LEFT JOIN ev_pat e USING (subject_id, hadm_id, stay_id);

\echo '=== [T2-1] 主队列 mace 事件分布 ==='
SELECT count(*) AS n_total,
       sum(mace::int) AS n_mace,
       round(100.0*sum(mace::int)/count(*),2) AS mace_rate_pct
FROM mimic_outcomes;

\echo '=== [T2-2] 6 事件各自阳性数 ==='
SELECT
 sum(ev_ami::int) AS ami,
 sum(ev_stroke::int) AS stroke,
 sum(ev_cardiac_death::int) AS cardiac_death,
 sum(ev_cardshk::int) AS cardshock,
 sum(ev_malarr::int) AS malarr,
 sum(ev_hfacu::int) AS hf_acute
FROM mimic_outcomes;

\echo '=== [T2-3] 事件强度分布 ==='
SELECT n_events, count(*) AS n FROM mimic_outcomes GROUP BY n_events ORDER BY n_events;

\echo '=== [T2-4] mace 与性别/年龄 ==='
SELECT p.gender, count(*) AS n, sum(o.mace::int) AS mace_n, round(100.0*sum(o.mace::int)/count(*),1) AS pct
FROM mimic_outcomes o JOIN mimic_cohort c USING (subject_id, hadm_id, stay_id) 
JOIN mimiciv_hosp.patients p USING (subject_id)
GROUP BY p.gender;