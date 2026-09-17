# Proactive Crew Coordination — Kenya Airways Capstone

Integrating Predictive Analytics and Mobile-Enabled Logistics for
Enhanced Operational Efficiency at Kenya Airways.

**Author:** Donell Bikketi (166604) · ICS 4A
**Supervisor:** Mrs. Juliet Kirui
**Institution:** Strathmore University, School of Computing and Engineering Sciences

## What this is
A cloud-backed, mobile-enabled platform with a predictive ML engine that
forecasts crew transit delays and triggers proactive dispatch alerts,
built with a native Kotlin Android client, a Python/PostgreSQL backend,
and an XGBoost/Random Forest predictive engine.

## Repo layout
```
.
├── data/            # synthetic dataset generator + data dictionary
│                     (raw CSVs live on Google Drive, NOT in this repo — see data/README.md)
├── ml/
│   ├── preprocessing/  # cleaning, feature engineering, train/val/test split
│   ├── training/       # model training scripts (XGBoost, Random Forest)
│   └── evaluation/     # metrics, confusion matrices, grid search results
├── api/             # Python REST API (auth, schedule + alert endpoints)
├── mobile/          # Kotlin Android Studio project (client app)
├── db/              # PostgreSQL schema + migrations
├── notebooks/        # exploratory analysis, scratch work
├── docs/            # data dictionary, architecture notes, diagrams
└── .github/workflows/ # CI (later: lint/test on push)
```

## Getting started (Python side)
```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python3 data/generate_dataset.py --outdir data/output
```

## Getting started (Mobile side)
Open `mobile/` directly as a project root in Android Studio once the
Kotlin app scaffold is added.

## Status
- [x] Proposal defended
- [x] Synthetic dataset generator (`data/generate_dataset.py`)
- [ ] Database schema implemented in PostgreSQL
- [ ] Preprocessing + feature engineering pipeline
- [ ] Baseline model (Random Forest) trained
- [ ] XGBoost tuned via grid search
- [ ] REST API scaffold
- [ ] Kotlin app scaffold
