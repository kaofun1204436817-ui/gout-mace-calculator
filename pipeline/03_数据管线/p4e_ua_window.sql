-- 尿酸时间窗覆盖探查 + GCS itemid 验证
CREATE TEMP TABLE base AS
SELECT c.subject_id, c.hadm_id, c.stay_id, c.intime
FROM mimic_cohort c
WHERE NOT c.any_prior_mace_dx;

\echo '=== [D7] 尿酸 24h/48h/72h/全期 覆盖 ==='
SELECT
  count(DISTINCT CASE WHEN le.charttime >= b.intime AND le.charttime < b.intime + interval '24 hours' THEN le.subject_id END) AS n_24h,
  count(DISTINCT CASE WHEN le.charttime >= b.intime AND le.charttime < b.intime + interval '48 hours' THEN le.subject_id END) AS n_48h,
  count(DISTINCT CASE WHEN le.charttime >= b.intime AND le.charttime < b.intime + interval '72 hours' THEN le.subject_id END) AS n_72h,
  count(DISTINCT le.subject_id) AS n_all
FROM base b
JOIN mimiciv_hosp.labevents le ON le.subject_id = b.subject_id
WHERE le.itemid = 51007;

\echo '=== [D8] GCS itemid 实际数据验证 ==='
SELECT ce.itemid, di.label, count(DISTINCT ce.stay_id) AS n_stays
FROM base b
JOIN mimiciv_icu.chartevents ce ON ce.stay_id = b.stay_id
JOIN mimiciv_icu.d_items di ON di.itemid = ce.itemid
WHERE ce.charttime >= b.intime AND ce.charttime < b.intime + interval '24 hours'
  AND (ce.itemid IN (220739,223900,223901) OR di.label ILIKE '%GCS%')
GROUP BY ce.itemid, di.label ORDER BY n_stays DESC;

\echo '=== [D9] 中性粒细胞/淋巴细胞 24h ==='
SELECT le.itemid, li.label,
       count(DISTINCT CASE WHEN le.charttime >= b.intime AND le.charttime < b.intime + interval '24 hours' THEN le.subject_id END) AS n_24h
FROM base b
JOIN mimiciv_hosp.labevents le ON le.subject_id = b.subject_id
JOIN mimiciv_hosp.d_labitems li ON li.itemid = le.itemid
WHERE le.itemid IN (52075,52074,51256,51133,51254,51146,51244,51245)
GROUP BY le.itemid, li.label ORDER BY n_24h DESC;