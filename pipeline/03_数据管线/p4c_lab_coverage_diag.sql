-- 反查主队列实际使用的化验 itemid 覆盖率（T3 诊断）
CREATE TEMP TABLE base AS
SELECT c.subject_id, c.hadm_id, c.stay_id, c.intime
FROM mimic_cohort c
WHERE NOT c.any_prior_mace_dx;

\echo '=== [D1] 主队列 24h 内 labevents 实际 itemid TOP40 ==='
SELECT le.itemid, li.label, count(DISTINCT le.subject_id) AS n_pts,
       round(100.0*count(DISTINCT le.subject_id)/2853,1) AS pct
FROM base b
JOIN mimiciv_hosp.labevents le ON le.subject_id = b.subject_id
JOIN mimiciv_hosp.d_labitems li ON li.itemid = le.itemid
WHERE le.charttime >= b.intime AND le.charttime < b.intime + interval '24 hours'
GROUP BY le.itemid, li.label
ORDER BY n_pts DESC
LIMIT 40;