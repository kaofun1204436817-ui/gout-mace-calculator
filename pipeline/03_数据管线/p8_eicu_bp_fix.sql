-- 修正 eICU 血压特征：合并有创(vitalperiodic) + 无创(vitalaperiodic)
-- 用 COALESCE 优先有创，无创补充；24h 窗口内均值
-- 运行: psql dbname=eicu user=postgres

-- 有创血压 24h 均值
CREATE TEMP TABLE bp_invasive AS
SELECT b.patientunitstayid,
       AVG(v.systemicsystolic) AS sbp_sys,
       AVG(v.systemicdiastolic) AS dbp_dia,
       AVG(v.systemicmean) AS map_mean
FROM (SELECT patientunitstayid FROM eicu_cohort WHERE NOT any_prior_cvd) b
JOIN vitalperiodic v USING (patientunitstayid)
WHERE v.observationoffset >= 0 AND v.observationoffset <= 1440
GROUP BY b.patientunitstayid;

-- 无创血压 24h 均值
CREATE TEMP TABLE bp_noninvasive AS
SELECT b.patientunitstayid,
       AVG(va.noninvasivesystolic) AS sbp_sys_n,
       AVG(va.noninvasivediastolic) AS dbp_dia_n,
       AVG(va.noninvasivemean) AS map_mean_n
FROM (SELECT patientunitstayid FROM eicu_cohort WHERE NOT any_prior_cvd) b
JOIN vitalaperiodic va USING (patientunitstayid)
WHERE va.observationoffset >= 0 AND va.observationoffset <= 1440 AND va.noninvasivesystolic IS NOT NULL
GROUP BY b.patientunitstayid;

-- 更新特征表
UPDATE eicu_features f
SET sbp_mean = COALESCE(i.sbp_sys, n.sbp_sys_n),
    sbp_min = NULLIF(COALESCE(i.sbp_sys, n.sbp_sys_n), 0),
    dbp_mean = COALESCE(i.dbp_dia, n.dbp_dia_n),
    map_mean = COALESCE(i.map_mean, n.map_mean_n),
    map_min = NULLIF(COALESCE(i.map_mean, n.map_mean_n), 0)
FROM bp_invasive i
LEFT JOIN bp_noninvasive n USING (patientunitstayid)
WHERE f.patientunitstayid = i.patientunitstayid;

-- 若无有创但有创表里没有记录的患者，则尝试只用无创
UPDATE eicu_features f
SET sbp_mean = n.sbp_sys_n, dbp_mean = n.dbp_dia_n, map_mean = n.map_mean_n
FROM bp_noninvasive n
WHERE f.patientunitstayid = n.patientunitstayid
  AND f.sbp_mean IS NULL;

\echo '=== [BP-FIX] 血压修正后覆盖率 ==='
SELECT count(sbp_mean) AS n_sbp, round(100.0*count(sbp_mean)/count(*),1) AS sbp_pct,
       count(dbp_mean) AS n_dbp, round(100.0*count(dbp_mean)/count(*),1) AS dbp_pct,
       count(map_mean) AS n_map, round(100.0*count(map_mean)/count(*),1) AS map_pct
FROM eicu_features;

\echo '=== [BP-FIX2] 血压数值范围 ==='
SELECT round(min(sbp_mean)::numeric,0) AS sbp_min_v, round(max(sbp_mean)::numeric,0) AS sbp_max_v,
       round(avg(sbp_mean)::numeric,1) AS sbp_avg
FROM eicu_features WHERE sbp_mean IS NOT NULL;