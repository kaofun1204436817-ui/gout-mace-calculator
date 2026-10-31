# In-hospital MACE Risk Calculator — ICU Patients with Gout

Interactive bedside calculator for the risk of in-hospital major adverse cardiovascular events (MACE, strict 6-event definition: acute myocardial infarction, new stroke, cardiogenic shock, malignant arrhythmia, acute heart failure, cardiac death) in critically ill adults with gout admitted to the ICU.

- Derivation cohort: **MIMIC-IV v3.1** (n = 2,853; internal AUC 0.782)
- External validation: **eICU-CRD v2.0** (n = 962; external AUC 0.673)

## Online calculator

- Streamlit: https://gout-mace-calculator.streamlit.app
- Offline HTML version (single file, no network required): `mace_risk_calculator.html` — double-click to open in any browser.

The Streamlit app and the HTML version share the exact same 12-variable scoring mapping and calibration constants as the nomogram in the paper (see `nomogram_scoring.csv` and `nomogram_calibration.json`).

## Requirements

- Python 3.10+
- Dependencies: `streamlit>=1.30`, `numpy`

Install and run locally:

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
# open http://localhost:8501
```

## Repository contents

| Path | Purpose |
|---|---|
| `streamlit_app.py` | Streamlit app (12-variable scoring, identical to the paper nomogram) |
| `mace_risk_calculator.html` | Offline single-file bedside calculator (same parameters) |
| `requirements.txt` | Python dependencies |

## Reproducing the full analysis

The full pipeline (data extraction, modeling, subgroup PSM, figures, tables) is provided in the Zenodo release:

1. **Data extraction** — `03_数据管线/*.sql`: run against MIMIC-IV v3.1 and eICU-CRD v2.0 (PhysioNet, credential application required). Scripts are prefixed `p0`–`p13` in dependency order.
2. **Modeling** — `04_模型/model_final_v7.py` (final model), `subgroup_psm.py` (propensity-score-matched subgroup analyses), `figure_final.py` (main figures), `nomogram_publish.py` (nomogram scoring), `make_tables.py` (manuscript tables).
3. **Calculator** — `08_计算器/streamlit_app.py` and `mace_risk_calculator.html`.

## Data availability

MIMIC-IV v3.1 and eICU-CRD v2.0 are publicly available through PhysioNet (https://physionet.org) after credential application and data use agreement. This repository contains **no individual patient data**.

## License

MIT License.

## Citation

Guo F, et al. Predicting in-hospital major adverse cardiovascular events in critically ill patients with gout: a derivation and external validation study (submitted to European Journal of Medical Research).

## Disclaimer

Research use only. This calculator is a risk-stratification aid and does not replace clinical judgment.

## Full analysis pipeline

The complete reproducible pipeline (extraction SQL and modeling scripts) is in the `pipeline/` directory:

- `pipeline/03_数据管线/*.sql` — cohort construction, outcome definitions, and feature extraction for MIMIC-IV v3.1 and eICU-CRD v2.0 (scripts prefixed p0-p13 in dependency order).
- `pipeline/04_模型/*.py` — final model (`model_final_v7.py`), three-tier drug-exposure analysis (`subgroup_psm_v3.py`, PSM / IPTW / multivariable adjustment), figure scripts (`figure_final.py`, `figure_v2_fixes.py`, `nomogram_publish.py`), and table generation (`make_tables.py`).

Run order: SQL pipelines first (per-database, p0 -> p13), then `model_final_v7.py --target mace|mace3|mace_alldeath`, then `subgroup_psm_v3.py`, then `figure_final.py` / `figure_v2_fixes.py` / `nomogram_publish.py` / `make_tables.py`.
