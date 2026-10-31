-- T1 队列构建 | eICU 探测 | 痛风(ICD9 274.x) + ICU 成人
-- eICU diagnosis 表: icd9code 字段 (eICU 以 ICD-9 为主)
-- 运行: psql "host=localhost port=5432 dbname=eicu user=eicu password=eicu" -f p0_eicu_probe.sql

\echo '=== [E0-1] eICU 痛风诊断患者数 ==='
SELECT count(DISTINCT d.patientunitstayid) AS n_stays,
       count(DISTINCT p.patienthealthsystemstayid) AS n_admissions,
       count(DISTINCT p.uniquepid) AS n_patients
FROM diagnosis d
JOIN patient p USING (patientunitstayid)
WHERE d.icd9code LIKE '274%';

\echo '=== [E0-2] 住院死亡状态分布（痛风组） ==='
SELECT p.unitdischargestatus, count(*) AS n
FROM diagnosis d
JOIN patient p USING (patientunitstayid)
WHERE d.icd9code LIKE '274%'
GROUP BY p.unitdischargestatus ORDER BY n DESC;

\echo '=== [E0-3] eICU 全库诊断 icd9code 前缀分布（看编码粒度） ==='
SELECT substr(icd9code,1,3) AS prefix, count(*) AS n
FROM diagnosis
WHERE icd9code IS NOT NULL AND icd9code <> ''
GROUP BY 1
ORDER BY n DESC
LIMIT 25;

\echo '=== [E0-4] 痛风组内 MACE 事件 ICD-9 覆盖 ==='
WITH gout AS (
  SELECT DISTINCT d.patientunitstayid
  FROM diagnosis d
  JOIN patient p USING (patientunitstayid)
  WHERE d.icd9code LIKE '274%'
)
SELECT
  count(*) AS n_stays,
  count(DISTINCT CASE WHEN d.icd9code ~ '^410' THEN g.patientunitstayid END) AS mi,
  count(DISTINCT CASE WHEN (d.icd9code ~ '^43[0-4]' OR d.icd9code = '436') THEN g.patientunitstayid END) AS stroke,
  count(DISTINCT CASE WHEN d.icd9code ~ '^428' THEN g.patientunitstayid END) AS hf,
  count(DISTINCT CASE WHEN d.icd9code = '78551' THEN g.patientunitstayid END) AS cardshock,
  count(DISTINCT CASE WHEN (d.icd9code ~ '^4271' OR d.icd9code ~ '^42741' OR d.icd9code ~ '^4275') THEN g.patientunitstayid END) AS malarr
FROM gout g
JOIN diagnosis d USING (patientunitstayid);

\echo '=== [E0-5] eICU 痛风组年龄/性别 ==='
WITH gout AS (
  SELECT DISTINCT patientunitstayid FROM diagnosis WHERE icd9code LIKE '274%'
)
SELECT p.gender, count(*) AS n, min(p.age) AS age
FROM gout g JOIN patient p USING (patientunitstayid)
GROUP BY p.gender;