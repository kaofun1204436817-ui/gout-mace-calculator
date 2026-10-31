-- T2 事件定义 v3 | MIMIC-IV | 主队列(2853) 上计算 6 事件 + 复合 MACE
-- 相比 v2 的修订：
--   1) 急性心衰收紧：仅限 ICD 明确"急性/急性加重"子类
--      ICD9 : 428.21,428.23,428.31,428.33,428.41,428.43 (428.0/428.1/428.9 不含 => 未特指)
--      ICD10: I50.21,I50.23,I50.31,I50.33,I50.41,I50.43,I50.811,I50.813（6 位完整性保留）
--   2) 心源性死亡：死亡 AND 本次住院含 (AMI|Stroke|CardShk|MalArr|AcuteHF)
--   3) 恶性心律失常：VF(VT)：ICD9 427.1,427.41 / ICD10 I46,I490,I472；CA 并入（I46/427.5 属"心脏骤停"，计入）
--   说明：主队列已剔除既往 MI/卒中/CHF（MIMIC 端以 codinst 前入院记录判定）

-- Step 1: 本次住院诊断表（主队列）——带"是否急性心衰"精确标记
CREATE TEMP TABLE mcohort AS SELECT * FROM mimic_cohort WHERE NOT any_prior_mace_dx;

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
       ( -- 急性/急性加重心衰
        (d.icd_version=9  AND d.icd_code IN
           ('42821','42823','42831','42833','42841','42843')) OR
        (d.icd_version=10 AND (d.icd_code IN
           ('I5021','I5023','I5031','I5033','I5041','I5043','I50811','I50813')))
       )::int AS ev_hfacu
FROM mcohort c
JOIN mimiciv_hosp.diagnoses_icd d ON d.hadm_id = c.hadm_id;

-- Step 2: 患者级事件汇总
CREATE TEMP TABLE ev_pat AS
SELECT subject_id, hadm_id, stay_id,
       MAX(ev_ami) AS ev_ami, MAX(ev_stroke) AS ev_stroke,
       MAX(ev_malarr) AS ev_malarr, MAX(ev_cardshk) AS ev_cardshk,
       MAX(ev_hfacu) AS ev_hfacu
FROM diag_event GROUP BY subject_id, hadm_id, stay_id;

-- Step 3: 拼入院死亡+主队列
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
               +COALESCE(e.ev_cardshk,0)+COALESCE(e.ev_hfacu,0) > 0))::int AS ev_cardiac_death,
       ( COALESCE(e.ev_ami,0)=1 OR COALESCE(e.ev_stroke,0)=1
         OR (c.hospital_expire_flag=1
             AND (COALESCE(e.ev_ami,0)+COALESCE(e.ev_stroke,0)+COALESCE(e.ev_malarr,0)
                  +COALESCE(e.ev_cardshk,0)+COALESCE(e.ev_hfacu,0) > 0))
         OR COALESCE(e.ev_cardshk,0)=1 OR COALESCE(e.ev_malarr,0)=1
         OR COALESCE(e.ev_hfacu,0)=1)::int AS mace,
       COALESCE(e.ev_ami,0)+COALESCE(e.ev_stroke,0)+COALESCE(e.ev_malarr,0)
       +COALESCE(e.ev_cardshk,0)+COALESCE(e.ev_hfacu,0)
       +(CASE WHEN c.hospital_expire_flag=1
               AND (COALESCE(e.ev_ami,0)+COALESCE(e.ev_stroke,0)+COALESCE(e.ev_malarr,0)
                    +COALESCE(e.ev_cardshk,0)+COALESCE(e.ev_hfacu,0) > 0) THEN 1 ELSE 0 END) AS n_events
FROM mcohort c
LEFT JOIN ev_pat e USING (subject_id, hadm_id, stay_id);

\echo '=== [T2-v3-1] 主队列 MACE（收紧心衰口径） ==='
SELECT count(*) AS n_total, sum(mace) AS n_mace,
       round(100.0*sum(mace)/count(*),2) AS mace_rate_pct
FROM mimic_outcomes;

\echo '=== [T2-v3-2] 6 事件各自阳性数 ==='
SELECT
 sum(ev_ami) AS ami, sum(ev_stroke) AS stroke,
 sum(ev_cardiac_death) AS cardiac_death, sum(ev_cardshk) AS cardshock,
 sum(ev_malarr) AS malarr, sum(ev_hfacu) AS hf_acute,
 sum(ev_death) AS death_all
FROM mimic_outcomes;

\echo '=== [T2-v3-3] 事件强度分布 ==='
SELECT n_events, count(*) AS n FROM mimic_outcomes GROUP BY n_events ORDER BY n_events;