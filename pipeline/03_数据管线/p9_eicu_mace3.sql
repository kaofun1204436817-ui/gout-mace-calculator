-- eICU 3 事件口径标签（BJA: AMI/卒中/死亡）
ALTER TABLE eicu_outcomes ADD COLUMN IF NOT EXISTS mace3 int;
UPDATE eicu_outcomes SET mace3 = CASE WHEN ev_ami=1 OR ev_stroke=1 OR ev_death=1 THEN 1 ELSE 0 END;
SELECT count(*) AS n, sum(mace3) AS n3, round(100.0*sum(mace3)/count(*),2) AS pct3 FROM eicu_outcomes;