-- 补算 eICU 宽口径事件标签
ALTER TABLE eicu_outcomes ADD COLUMN IF NOT EXISTS mace_wide int;
UPDATE eicu_outcomes SET mace_wide = CASE WHEN ev_ami=1 OR ev_stroke=1 OR ev_cardshk=1 OR ev_malarr=1 OR ev_hfacu=1 OR (ev_death=1 AND (ev_ami+ev_stroke+ev_cardshk+ev_malarr+ev_hfacu)>0) THEN 1 ELSE 0 END;
-- 宽口径: 心衰放宽为任何 428/I50 编码
UPDATE eicu_outcomes o SET mace_wide = 1 WHERE o.patientunitstayid IN (
  SELECT d.patientunitstayid FROM diagnosis d
  WHERE d.icd9code ~ '(^|, )428\.' OR d.icd9code ~ '(^|, )I50'
);
SELECT count(*) AS n, sum(mace) AS n_strict, sum(mace3) AS n_bja3, sum(mace_wide) AS n_wide FROM eicu_outcomes;