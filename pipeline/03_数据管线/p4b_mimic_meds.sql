-- T3 特征工程 | MIMIC-IV | 用药特征（优化版：先子集后正则）
-- 运行: psql dbname=mimic user=mimic -f p4b_mimic_meds.sql
DROP TABLE IF EXISTS mimic_meds;

CREATE TEMP TABLE base AS
SELECT c.subject_id, c.hadm_id, c.stay_id
FROM mimic_cohort c
WHERE NOT c.any_prior_mace_dx;

-- 关键优化：只保留主队列 hadm_id 的处方记录（临时表），再在其上做正则
CREATE TEMP TABLE rx_sub AS
SELECT pr.subject_id, pr.hadm_id, pr.drug
FROM mimiciv_hosp.prescriptions pr
WHERE pr.hadm_id IN (SELECT hadm_id FROM base)
  AND pr.drug IS NOT NULL;

CREATE INDEX ON rx_sub (hadm_id);
ANALYZE rx_sub;

CREATE TEMP TABLE meds AS
SELECT b.stay_id,
       MAX(CASE WHEN rx.drug ~* 'allopurinol|febuxostat|benzbromarone|probenecid' THEN 1 ELSE 0 END) AS med_urate,
       MAX(CASE WHEN rx.drug ~* 'colchicine' THEN 1 ELSE 0 END) AS med_colchicine,
       MAX(CASE WHEN rx.drug ~* 'prednisone|methylprednisolone|dexamethasone|hydrocortisone' THEN 1 ELSE 0 END) AS med_steroid,
       MAX(CASE WHEN rx.drug ~* 'aspirin' THEN 1 ELSE 0 END) AS med_aspirin,
       MAX(CASE WHEN rx.drug ~* 'clopidogrel|ticagrelor' THEN 1 ELSE 0 END) AS med_p2y12,
       MAX(CASE WHEN rx.drug ~* 'heparin|enoxaparin|warfarin|apixaban|rivaroxaban' THEN 1 ELSE 0 END) AS med_anticoag,
       MAX(CASE WHEN rx.drug ~* 'atorvastatin|rosuvastatin|simvastatin|pravastatin' THEN 1 ELSE 0 END) AS med_statin,
       MAX(CASE WHEN rx.drug ~* 'furosemide|bumetanide|hydrochlorothiazide|spironolactone' THEN 1 ELSE 0 END) AS med_diuretic,
       MAX(CASE WHEN rx.drug ~* 'norepinephrine|epinephrine|dopamine|vasopressin|phenylephrine|dobutamine' THEN 1 ELSE 0 END) AS med_vasopressor,
       MAX(CASE WHEN rx.drug ~* 'metoprolol|carvedilol|bisoprolol|propranolol' THEN 1 ELSE 0 END) AS med_betablocker,
       MAX(CASE WHEN rx.drug ~* 'lisinopril|enalapril|ramipril|losartan|valsartan' THEN 1 ELSE 0 END) AS med_acei_arb
FROM base b
JOIN rx_sub rx ON rx.hadm_id = b.hadm_id
GROUP BY b.stay_id;

CREATE TABLE mimic_meds AS SELECT * FROM meds;

\echo '=== [M1] 用药特征分布（主队列 2853） ==='
SELECT count(*) AS n,
  sum(med_urate) AS urate, sum(med_colchicine) AS colch, sum(med_steroid) AS steroid,
  sum(med_aspirin) AS aspirin, sum(med_statin) AS statin, sum(med_vasopressor) AS vasop,
  sum(med_betablocker) AS bblock, sum(med_acei_arb) AS acei_arb, sum(med_anticoag) AS anticoag
FROM mimic_meds;