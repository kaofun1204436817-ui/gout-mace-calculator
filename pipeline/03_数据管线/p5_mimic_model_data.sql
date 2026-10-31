-- 最终建模数据集 | MIMIC-IV
-- 主队列 2853 = mimic_features + mimic_outcomes + 既往史标志
-- 产物: mimic_model_data

DROP TABLE IF EXISTS mimic_model_data;
CREATE TABLE mimic_model_data AS
SELECT f.*, o.ev_ami, o.ev_stroke, o.ev_cardiac_death, o.ev_cardshk, o.ev_malarr, o.ev_hfacu,
       o.ev_death, o.mace, o.n_events,
       c.prior_mi, c.prior_stroke, c.prior_hf,
       c.admission_type, c.hospital_expire_flag
FROM mimic_features f
JOIN mimic_outcomes o USING (stay_id)
JOIN mimic_cohort c USING (stay_id);

\echo '=== [FIN1] 建模数据行数 ==='
SELECT count(*) AS n, sum(mace) AS mace_n FROM mimic_model_data;

\echo '=== [FIN2] 列数 ==='
SELECT count(*) AS n_cols FROM information_schema.columns WHERE table_name='mimic_model_data';

\echo '=== [FIN3] 关键化验+生命体征 数值范围抽查 ==='
SELECT round(avg(creatinine)::numeric,2) AS creat_mean, min(creatinine) AS creat_min, max(creatinine) AS creat_max,
       round(avg(hr_mean)::numeric,1) AS hr_mean, min(sbp_mean) AS sbp_min_v, max(sbp_mean) AS sbp_max_v,
       round(avg(age::numeric)::numeric,1) AS age_mean
FROM mimic_model_data;