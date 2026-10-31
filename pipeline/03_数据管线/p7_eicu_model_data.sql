-- 最终建模数据集 | eICU
-- 主队列 962 = eicu_features + eicu_outcomes
-- 产物: eicu_model_data

DROP TABLE IF EXISTS eicu_model_data;
CREATE TABLE eicu_model_data AS
SELECT f.*, o.ev_ami, o.ev_stroke, o.ev_cardiac_death, o.ev_cardshk, o.ev_malarr, o.ev_hfacu,
       o.ev_death, o.mace
FROM eicu_features f
JOIN eicu_outcomes o USING (patientunitstayid);

\echo '=== [E-FIN1] eICU 建模数据行数 ==='
SELECT count(*) AS n, sum(mace) AS mace_n FROM eicu_model_data;

\echo '=== [E-FIN2] 列数 ==='
SELECT count(*) AS n_cols FROM information_schema.columns WHERE table_name='eicu_model_data';

\echo '=== [E-FIN3] 血压24h在 vitalaperiodic 的覆盖 ==='
SELECT count(DISTINCT b.patientunitstayid) AS n_with_bp,
       round(100.0*count(DISTINCT b.patientunitstayid)/962,1) AS pct
FROM (SELECT patientunitstayid FROM eicu_cohort WHERE NOT any_prior_cvd) b
JOIN vitalaperiodic va USING (patientunitstayid)
WHERE va.observationoffset >= 0 AND va.observationoffset <= 1440 AND va.systemicsystolic IS NOT NULL;