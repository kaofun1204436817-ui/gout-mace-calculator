-- T2 事件定义 v2 | MIMIC-IV | 主队列(2853) 上计算 6 事件 + 复合 MACE
-- 事件口径（保守主分析）：
--   AMI      : ICD9 410.x / ICD10 I21.x,I22.x                    (4100-4109 含所有子类)
--   Stroke   : ICD9 430,431,432,433,434,436 / ICD10 I60-I64       (不含 TIA, 敏感分析再加入)
--   CardiacD : 死亡 AND 本次住院含 (AMI|Stroke|CardShk|MalArr|AcuteHF) 事件编码
--   CardShk  : ICD9 785.51 / ICD10 R57.0
--   MalArr   : ICD9 427.1(VF),427.41(VT),427.5(CA) / ICD10 I46(CA),I490(VF/VL),I472(VT)
--   AcuteHF  : ICD9 428.x / ICD10 I50.x   (主队列已排除既往心衰 -> 本次出现=新发/急性加重)
-- 复合 MACE = 任一事件
-- 运行: psql ... -f p2_mimic_outcomes_v2.sql

-- Step 0: 主队列（排除既往 MACE Dx）
CREATE TEMP TABLE mcohort AS
SELECT * FROM mimic_cohort WHERE NOT any_prior_mace_dx;

-- Step 1: 本次住院诊断表（仅主队列）
CREATE TEMP TABLE diag_event AS
SELECT c.subject_id, c.hadm_id, c.stay_id,
       d.icd_code, d.icd_version,
       ((d.icd_version=9  AND d.icd_code ~ '^410') OR
        (d.icd_version=10 AND (d.icd_code ~ '^I21' OR d.icd_code ~ '^I22')))::int AS ev_ami,
       ((d.icd_version=9  AND (d.icd_code ~ '^43[0-4]' OR d.icd_code = '436')) OR
        (d.icd_version=10 AND d.icd_code ~ '^I6[0-4]'))::int AS ev_stroke,
       ((d.icd_version=9  AND (d.icd_code ~ '^4271' OR d.icd_code ~ '^42741' OR d.icd_code ~ '^4275')) OR
        (d.icd_version=10 AND (d.icd_code ~ '^I46' OR d.icd_code ~ '^I490' OR d.icd_code ~ '^I472')))::int AS ev_malarr,
       ((d.icd_version=9  AND d.icd_code = '78551') OR
        (d.icd_version=10 AND d.icd_code ~ '^R570'))::int AS ev_cardshk,
       ((d.icd_version=9  AND d.icd_code ~ '^428') OR
        (d.icd_version=10 AND d.icd_code ~ '^I50'))::int AS ev_hfacu
FROM mcohort c
JOIN mimiciv_hosp.diagnoses_icd d ON d.hadm_id = c.hadm_id;

-- Step 2: 患者级事件汇总
CREATE TEMP TABLE ev_pat AS
SELECT subject_id, hadm_id, stay_id,
       MAX(ev_ami) AS ev_ami, MAX(ev_stroke) AS ev_stroke,
       MAX(ev_malarr) AS ev_malarr, MAX(ev_cardshk) AS ev_cardshk,
       MAX(ev_hfacu) AS ev_hfacu
FROM diag_event GROUP BY subject_id, hadm_id, stay_id;

-- Step 3: 拼入院死亡+主队列, 得最终事件表
DROP TABLE IF EXISTS mimic_outcomes;
CREATE TABLE mimic_outcomes AS
SELECT c.subject_id, c.hadm_id, c.stay_id,
       COALESCE(e.ev_ami,0)    AS ev_ami,
       COALESCE(e.ev_stroke,0) AS ev_stroke,
       COALESCE(e.ev_malarr,0) AS ev_malarr,
       COALESCE(e.ev_cardshk,0)AS ev_cardshk,
       COALESCE(e.ev_hfacu,0)  AS ev_hfacu,
       c.hospital_expire_flag  AS ev_death,
       (c.hospital_expire_flag=1
          AND (COALESCE(e.ev_ami,0)+COALESCE(e.ev_stroke,0)+COALESCE(e.ev_malarr,0)
               +COALESCE(e.ev_cardshk,0)+COALESCE(e.ev_hfacu,0) > 0)
       )::int AS ev_cardiac_death,
       ( COALESCE(e.ev_ami,0)=1 OR COALESCE(e.ev_stroke,0)=1
         OR (c.hospital_expire_flag=1
             AND (COALESCE(e.ev_ami,0)+COALESCE(e.ev_stroke,0)+COALESCE(e.ev_malarr,0)
                  +COALESCE(e.ev_cardshk,0)+COALESCE(e.ev_hfacu,0) > 0))
         OR COALESCE(e.ev_cardshk,0)=1 OR COALESCE(e.ev_malarr,0)=1
         OR COALESCE(e.ev_hfacu,0)=1
       )::int AS mace,
       COALESCE(e.ev_ami,0)+COALESCE(e.ev_stroke,0)+COALESCE(e.ev_malarr,0)
       +COALESCE(e.ev_cardshk,0)+COALESCE(e.ev_hfacu,0)
       +(CASE WHEN c.hospital_expire_flag=1
               AND (COALESCE(e.ev_ami,0)+COALESCE(e.ev_stroke,0)+COALESCE(e.ev_malarr,0)
                    +COALESCE(e.ev_cardshk,0)+COALESCE(e.ev_hfacu,0) > 0) THEN 1 ELSE 0 END) AS n_events
FROM mcohort c
LEFT JOIN ev_pat e USING (subject_id, hadm_id, stay_id);

\echo '=== [T2-v2-1] 主队列 MACE ==='
SELECT count(*) AS n_total, sum(mace) AS n_mace,
       round(100.0*sum(mace)/count(*),2) AS mace_rate_pct
FROM mimic_outcomes;

\echo '=== [T2-v2-2] 6 事件各自阳性数 ==='
SELECT
 sum(ev_ami) AS ami, sum(ev_stroke) AS stroke,
 sum(ev_cardiac_death) AS cardiac_death, sum(ev_cardshk) AS cardshock,
 sum(ev_malarr) AS malarr, sum(ev_hfacu) AS hf_acute,
 sum(ev_death) AS death_all
FROM mimic_outcomes;

\echo '=== [T2-v2-3] 事件强度分布 ==='
SELECT n_events, count(*) AS n FROM mimic_outcomes GROUP BY n_events ORDER BY n_events;

\echo '=== [T2-v2-4] MACE 与性别/年龄（主队列） ==='
SELECT p.gender, count(*) AS n, sum(o.mace) AS mace_n,
       round(100.0*sum(o.mace)/count(*),1) AS pct, round(avg(p.anchor_age)::numeric,1) AS mean_age
FROM mimic_outcomes o
JOIN mimiciv_hosp.patients p USING (subject_id)
GROUP BY p.gender;