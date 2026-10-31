-- T1+eICU 队列构建 | eICU-CRD v1
-- 人群定义（外部验证集）：
--   痛风代理 = medication 含 ALLOPURINOL（降尿酸治疗，eICU 无痛风 ICD 编码，此为文献常用代理）
--   成人(>=18)，首次 ICU 停留（unitvisitnumber=1 且取每条唯一 patientunitstayid）
-- 排除：pasthistory 结构化学史含 CHF / stroke / MI（==入院前已患）
-- 事件（复合 MACE，6 组件，与 MIMIC 对齐）：
--   icd9code 为 "ICD9, ICD10" 逗号分隔带点格式，须同时匹配 ICD-9 与 ICD-10 两套
--   AMI: ICD9 410.* / ICD10 I21,I22
--   Stroke: ICD9 430-434,436 / ICD10 I60-I64（不含 TIA）
--   CardShk: ICD9 785.51 / ICD10 R57.0
--   MalArr: ICD9 427.1(VT),427.41(VF),427.5(CA) / ICD10 I46(CA),I49.0(VF),I47.2(VT)
--   AcuteHF: ICD9 428.21,428.23,428.31,428.33,428.41,428.43 / ICD10 I50.21,50.23,50.31,50.33,50.41,50.43,50.811,50.813
--   CardiacDeath: 住院死亡 AND 任一事件编码

DROP TABLE IF EXISTS eicu_cohort;
DROP TABLE IF EXISTS eicu_outcomes;

-- Step 1: 别嘌醇人群（痛风代理）+ 首次ICU + 成人
CREATE TEMP TABLE gout_med AS
SELECT DISTINCT m.patientunitstayid
FROM medication m
WHERE m.drugname ILIKE '%ALLOPURINOL%';

CREATE TEMP TABLE gout_icu AS
SELECT p.patientunitstayid, p.patienthealthsystemstayid,
       CASE WHEN p.age = '> 89' THEN 90 ELSE NULLIF(p.age,'')::int END AS age,
       p.gender, p.unitdischargestatus, p.hospitaldischargestatus,
       p.hospitaladmitoffset, p.unitdischargeoffset
FROM gout_med gm
JOIN patient p USING (patientunitstayid)
WHERE (CASE WHEN p.age = '> 89' THEN 90 ELSE NULLIF(p.age,'')::int END) >= 18
  AND p.unitvisitnumber = 1;

-- Step 2: 既往史排除（pasthistory 结构化学史）
CREATE TEMP TABLE prior_hx AS
SELECT patientunitstayid,
       MAX(CASE WHEN pasthistorypath ILIKE '%/Myocardial Infarction/%' THEN 1 ELSE 0 END) AS hx_mi,
       MAX(CASE WHEN pasthistorypath ILIKE '%/Strokes/%' THEN 1 ELSE 0 END) AS hx_stroke,
       MAX(CASE WHEN pasthistorypath ILIKE '%/Congestive Heart Failure/%' THEN 1 ELSE 0 END) AS hx_chf
FROM pasthistory
WHERE pasthistorypath LIKE 'notes/Progress Notes/Past History/%'
GROUP BY patientunitstayid;

-- Step 3: 正式队列
CREATE TABLE eicu_cohort AS
SELECT g.*, COALESCE(h.hx_mi,0) AS hx_mi, COALESCE(h.hx_stroke,0) AS hx_stroke,
       COALESCE(h.hx_chf,0) AS hx_chf,
       (COALESCE(h.hx_mi,0)+COALESCE(h.hx_stroke,0)+COALESCE(h.hx_chf,0)) > 0 AS any_prior_cvd,
       (p.hospitaldischargestatus = 'Expired')::int AS hosp_death
FROM gout_icu g
JOIN patient p USING (patientunitstayid)
LEFT JOIN prior_hx h USING (patientunitstayid);

\echo '=== [E1-1] eICU 别嘌醇人群（成人首次ICU） ==='
SELECT count(*) AS n_stays, count(DISTINCT patienthealthsystemstayid) AS n_adm,
       count(DISTINCT patientunitstayid) AS n_units
FROM eicu_cohort;

\echo '=== [E1-2] 既往 CVD 分布 ==='
SELECT hx_mi, hx_stroke, hx_chf, any_prior_cvd, count(*) AS n
FROM eicu_cohort GROUP BY 1,2,3,4 ORDER BY n DESC;

\echo '=== [E1-3] 主队列（排除既往 CVD） ==='
SELECT count(*) AS n_stays FROM eicu_cohort WHERE NOT any_prior_cvd;

-- Step 4: 事件定义（逗号分隔双编码匹配）
-- 用 regexp: 匹配逗号分隔列表中的编码 token
CREATE TABLE eicu_outcomes AS
SELECT c.patientunitstayid,
       -- 各事件
       EXISTS (SELECT 1 FROM diagnosis d WHERE d.patientunitstayid = c.patientunitstayid
               AND (d.icd9code ~ '(^|, )410\.' OR d.icd9code ~ '(^|, )I21' OR d.icd9code ~ '(^|, )I22'))::int AS ev_ami,
       EXISTS (SELECT 1 FROM diagnosis d WHERE d.patientunitstayid = c.patientunitstayid
               AND (d.icd9code ~ '(^|, )43[0-4]\.' OR d.icd9code ~ '(^|, )436\.' OR d.icd9code ~ '(^|, )I6[0-4]'))::int AS ev_stroke,
       EXISTS (SELECT 1 FROM diagnosis d WHERE d.patientunitstayid = c.patientunitstayid
               AND (d.icd9code ~ '(^|, )785\.51' OR d.icd9code ~ '(^|, )R57\.0'))::int AS ev_cardshk,
       EXISTS (SELECT 1 FROM diagnosis d WHERE d.patientunitstayid = c.patientunitstayid
               AND (d.icd9code ~ '(^|, )427\.1' OR d.icd9code ~ '(^|, )427\.41' OR d.icd9code ~ '(^|, )427\.5'
                    OR d.icd9code ~ '(^|, )I46' OR d.icd9code ~ '(^|, )I49\.0' OR d.icd9code ~ '(^|, )I47\.2'))::int AS ev_malarr,
       EXISTS (SELECT 1 FROM diagnosis d WHERE d.patientunitstayid = c.patientunitstayid
               AND (d.icd9code ~ '(^|, )428\.2[13]' OR d.icd9code ~ '(^|, )428\.3[13]' OR d.icd9code ~ '(^|, )428\.4[13]'
                    OR d.icd9code ~ '(^|, )I50\.2[13]' OR d.icd9code ~ '(^|, )I50\.3[13]' OR d.icd9code ~ '(^|, )I50\.4[13]'
                    OR d.icd9code ~ '(^|, )I50\.811' OR d.icd9code ~ '(^|, )I50\.813'))::int AS ev_hfacu,
       c.hosp_death AS ev_death
FROM eicu_cohort c
WHERE NOT c.any_prior_cvd;

ALTER TABLE eicu_outcomes ADD COLUMN ev_cardiac_death int;
ALTER TABLE eicu_outcomes ADD COLUMN mace int;
UPDATE eicu_outcomes SET
  ev_cardiac_death = CASE WHEN ev_death=1 AND (ev_ami+ev_stroke+ev_cardshk+ev_malarr+ev_hfacu)>0 THEN 1 ELSE 0 END,
  mace = CASE WHEN ev_ami=1 OR ev_stroke=1 OR ev_cardshk=1 OR ev_malarr=1 OR ev_hfacu=1
               OR (ev_death=1 AND (ev_ami+ev_stroke+ev_cardshk+ev_malarr+ev_hfacu)>0) THEN 1 ELSE 0 END;

\echo '=== [E1-4] eICU 主队列 MACE ==='
SELECT count(*) AS n_total, sum(mace) AS n_mace,
       round(100.0*sum(mace)/count(*),2) AS mace_rate_pct,
       sum(ev_death) AS death_all
FROM eicu_outcomes;

\echo '=== [E1-5] 各事件阳性数 ==='
SELECT sum(ev_ami) AS ami, sum(ev_stroke) AS stroke, sum(ev_cardiac_death) AS cardiac_death,
       sum(ev_cardshk) AS cardshock, sum(ev_malarr) AS malarr, sum(ev_hfacu) AS hf_acute
FROM eicu_outcomes;

\echo '=== [E1-6] 年龄/性别分布 ==='
SELECT p.gender, count(*) AS n, round(avg(c.age)::numeric,1) AS mean_age
FROM eicu_outcomes o JOIN eicu_cohort c USING (patientunitstayid)
JOIN patient p USING (patientunitstayid)
GROUP BY p.gender;