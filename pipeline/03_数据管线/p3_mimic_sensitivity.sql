-- MIMIC 敏感性口径补算：BJA 3 事件 + 全因死亡替代
-- 主队列 2853（mimic_outcomes 已建）
\echo '=== [S1] MIMIC BJA 3 事件（AMI / Stroke / 全因死亡） ==='
SELECT count(*) AS n_total,
       sum(CASE WHEN ev_ami=1 OR ev_stroke=1 OR ev_death=1 THEN 1 ELSE 0 END) AS n_bja3,
       round(100.0*sum(CASE WHEN ev_ami=1 OR ev_stroke=1 OR ev_death=1 THEN 1 ELSE 0 END)/count(*),2) AS pct
FROM mimic_outcomes;

\echo '=== [S2] MIMIC 全因死亡替代心源性死亡 ==='
SELECT sum(CASE WHEN ev_ami=1 OR ev_stroke=1 OR ev_death=1 OR ev_cardshk=1 OR ev_malarr=1 OR ev_hfacu=1 THEN 1 ELSE 0 END) AS n_alt,
       round(100.0*sum(CASE WHEN ev_ami=1 OR ev_stroke=1 OR ev_death=1 OR ev_cardshk=1 OR ev_malarr=1 OR ev_hfacu=1 THEN 1 ELSE 0 END)/count(*),2) AS pct
FROM mimic_outcomes;

\echo '=== [S3] 事件组件重叠矩阵（辅助审稿人问答） ==='
SELECT ev_ami, ev_stroke, ev_cardshk, ev_malarr, ev_hfacu, ev_cardiac_death, count(*) AS n
FROM mimic_outcomes GROUP BY 1,2,3,4,5,6 ORDER BY n DESC LIMIT 15;