-- MIMIC 3 事件口径标签（BJA: AMI/卒中/死亡）
ALTER TABLE mimic_outcomes ADD COLUMN IF NOT EXISTS mace3 int;
UPDATE mimic_outcomes SET mace3 = CASE WHEN ev_ami=1 OR ev_stroke=1 OR ev_death=1 THEN 1 ELSE 0 END;
ALTER TABLE mimic_model_data ADD COLUMN IF NOT EXISTS mace3 int;
UPDATE mimic_model_data mm SET mace3 = o.mace3 FROM mimic_outcomes o WHERE mm.stay_id = o.stay_id;
SELECT count(*) AS n, sum(mace3) AS n3, round(100.0*sum(mace3)/count(*),2) AS pct3 FROM mimic_model_data;