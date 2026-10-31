-- eICU 队列三套事件口径对比（修正版：先按 stay 聚合再计数）
WITH goutmed AS (
  SELECT DISTINCT patientunitstayid FROM medication WHERE drugname ILIKE '%ALLOPURINOL%'
),
gout_icu AS (
  SELECT p.patientunitstayid,
         CASE WHEN p.age='> 89' THEN 90 ELSE NULLIF(p.age,'')::int END AS age
  FROM goutmed gm JOIN patient p USING (patientunitstayid)
  WHERE p.unitvisitnumber=1
    AND (CASE WHEN p.age='> 89' THEN 90 ELSE NULLIF(p.age,'')::int END) >= 18
),
no_prior AS (  -- 排除既往 MI/卒中/CHF
  SELECT patientunitstayid FROM gout_icu
  EXCEPT
  SELECT DISTINCT ph.patientunitstayid FROM pasthistory ph
  WHERE ph.pasthistorypath LIKE '%Myocardial Infarction/%'
     OR ph.pasthistorypath LIKE '%Strokes/%'
     OR ph.pasthistorypath LIKE '%Congestive Heart Failure/%'
),
diag_agg AS (
  SELECT n.patientunitstayid,
         p.hospitaldischargestatus,
         MAX(CASE WHEN d.icd9code ~ '(^|, )410\.' OR d.icd9code ~ '(^|, )I21' OR d.icd9code ~ '(^|, )I22'
                  THEN 1 ELSE 0 END) AS has_mi,
         MAX(CASE WHEN d.icd9code ~ '(^|, )43[0-4]\.' OR d.icd9code ~ '(^|, )436\.' OR d.icd9code ~ '(^|, )I6[0-4]'
                  THEN 1 ELSE 0 END) AS has_stroke,
         MAX(CASE WHEN d.icd9code ~ '(^|, )785\.51' OR d.icd9code ~ '(^|, )R57\.0'
                  THEN 1 ELSE 0 END) AS has_cardshk,
         MAX(CASE WHEN d.icd9code ~ '(^|, )427\.1' OR d.icd9code ~ '(^|, )427\.41' OR d.icd9code ~ '(^|, )427\.5'
                   OR d.icd9code ~ '(^|, )I46' OR d.icd9code ~ '(^|, )I49\.0' OR d.icd9code ~ '(^|, )I47\.2'
                  THEN 1 ELSE 0 END) AS has_malarr,
         MAX(CASE WHEN d.icd9code ~ '(^|, )428\.2[13]' OR d.icd9code ~ '(^|, )428\.3[13]' OR d.icd9code ~ '(^|, )428\.4[13]'
                   OR d.icd9code ~ '(^|, )I50\.2[13]' OR d.icd9code ~ '(^|, )I50\.3[13]' OR d.icd9code ~ '(^|, )I50\.4[13]'
                   OR d.icd9code ~ '(^|, )I50\.811' OR d.icd9code ~ '(^|, )I50\.813'
                  THEN 1 ELSE 0 END) AS has_hfacu,
         MAX(CASE WHEN d.icd9code ~ '(^|, )428\.' OR d.icd9code ~ '(^|, )I50'
                  THEN 1 ELSE 0 END) AS has_hf_all
  FROM no_prior n
  JOIN patient p USING (patientunitstayid)
  LEFT JOIN diagnosis d USING (patientunitstayid)
  GROUP BY n.patientunitstayid, p.hospitaldischargestatus
)
SELECT
  count(*) AS n_total,
  sum(CASE WHEN has_mi=1 OR has_stroke=1 OR has_cardshk=1 OR has_malarr=1 OR has_hfacu=1
            OR (hospitaldischargestatus='Expired' AND (has_mi+has_stroke+has_cardshk+has_malarr+has_hfacu)>0)
       THEN 1 ELSE 0 END) AS n_strict6,
  round(100.0*sum(CASE WHEN has_mi=1 OR has_stroke=1 OR has_cardshk=1 OR has_malarr=1 OR has_hfacu=1
            OR (hospitaldischargestatus='Expired' AND (has_mi+has_stroke+has_cardshk+has_malarr+has_hfacu)>0)
       THEN 1 ELSE 0 END)/count(*),2) AS strict6_pct,
  sum(CASE WHEN has_mi=1 OR has_stroke=1 OR has_cardshk=1 OR has_malarr=1 OR has_hf_all=1
       THEN 1 ELSE 0 END) AS n_wide_hf,
  sum(CASE WHEN has_mi=1 OR has_stroke=1 OR hospitaldischargestatus='Expired'
       THEN 1 ELSE 0 END) AS n_bja3,
  sum(CASE WHEN hospitaldischargestatus='Expired' THEN 1 ELSE 0 END) AS n_death,
  sum(has_mi) AS n_mi, sum(has_stroke) AS n_stroke, sum(has_cardshk) AS n_cardshk,
  sum(has_malarr) AS n_malarr, sum(has_hfacu) AS n_hfacu, sum(has_hf_all) AS n_hf_all
FROM diag_agg;