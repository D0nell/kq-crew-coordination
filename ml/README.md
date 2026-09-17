# ml/

- `preprocessing/` — feature engineering, missing-value imputation, train/val/test loading
- `training/` — Random Forest baseline + XGBoost training scripts, grid search configs
- `evaluation/` — precision/recall/F1 per class, MAE, confusion matrices

Start here next: write `preprocessing/load_data.py` to read `data/output/Transit_Events.csv`
and build the feature matrix described in `docs/data_dictionary.md`.
