-- 反查尿酸/肌钙蛋白/CRP/BNP 在全住院期覆盖（24h vs 全期对比）
CREATE TEMP TABLE base AS
SELECT c.subject_id, c.hadm_id, c.stay_id, c.intime, c.outtime
FROM mimic_cohort c
WHERE NOT c.any_prior_mace_dx;

\echo '=== [D2] 尿酸全期覆盖（主队列） ==='
SELECT count(DISTINCT le.subject_id) AS n_pts,
       round(100.0*count(DISTINCT le.subject_id)/2853,1) AS pct_all,
       round(100.0*count(DISTINCT CASE WHEN le.charttime >= b.intime AND le.charttime < b.intime + interval '24 hours' THEN le.subject_id END)/2853,1) AS pct_24h
FROM base b
JOIN mimiciv_hosp.labevents le ON le.subject_id = b.subject_id
WHERE le.itemid = 51007;

\echo '=== [D3] 肌钙蛋白 I/T 全期覆盖 ==='
SELECT le.itemid, li.label,
       count(DISTINCT le.subject_id) AS n_pts,
       round(100.0*count(DISTINCT CASE WHEN le.charttime >= b.intime AND le.charttime < b.intime + interval '24 hours' THEN le.subject_id END)/2853,1) AS pct_24h
FROM base b
JOIN mimiciv_hosp.labevents le ON le.subject_id = b.subject_id
JOIN mimiciv_hosp.d_labitems li ON li.itemid = le.itemid
WHERE le.itemid IN (51002,51003,52642)
GROUP BY le.itemid, li.label;

\echo '=== [D4] hsCRP / CRP 全期 ==='
SELECT le.itemid, li.label,
       count(DISTINCT le.subject_id) AS n_pts,
       round(100.0*count(DISTINCT CASE WHEN le.charttime >= b.intime AND le.charttime < b.intime + interval '24 hours' THEN le.subject_id END)/2853,1) AS pct_24h
FROM base b
JOIN mimiciv_hosp.labevents le ON le.subject_id = b.subject_id
JOIN mimiciv_hosp.d_labitems li ON li.itemid = le.itemid
WHERE le.itemid IN (51652,50889,52075,53063,51708)
GROUP BY le.itemid, li.label;

\echo '=== [D5] NTproBNP 全期 ==='
SELECT count(DISTINCT le.subject_id) AS n_pts,
       round(100.0*count(DISTINCT CASE WHEN le.charttime >= b.intime AND le.charttime < b.intime + interval '24 hours' THEN le.subject_id END)/2853,1) AS pct_24h
FROM base b
JOIN mimiciv_hosp.labevents le ON le.subject_id = b.subject_id
WHERE le.itemid = 50963;

\echo '=== [D6] 尿素氮/白蛋白/胆红素/ALT/AST 24h ==='
SELECT le.itemid, li.label,
       count(DISTINCT CASE WHEN le.charttime >= b.intime AND le.charttime < b.intime + interval '24 hours' THEN le.subject_id END) AS n_24h,
       round(100.0*count(DISTINCT CASE WHEN le.charttime >= b.intime AND le.charttime < b.intime + interval '24 hours' THEN le.subject_id END)/2853,1) AS pct
FROM base b
JOIN mimiciv_hosp.labevents le ON le.subject_id = b.subject_id
JOIN mimiciv_hosp.d_labitems li ON li.itemid = le.itemid
WHERE le.itemid IN (51006,50862,53085,50885,53089,50861,50878,50910,50911,51580)
GROUP BY le.itemid, li.label ORDER BY n_24h DESC;