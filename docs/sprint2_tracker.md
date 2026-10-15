# Sprint II task tracker

Status key: Done / In progress / Not started. FR numbers are from the SRS in the proposal. Match the "Objective area" column to the numbering in section 1.3.2 of your Chapter 1.

| # | Task | Objective area | Requirement | Status | Evidence |
|---|---|---|---|---|---|
| 1 | Generate and validate synthetic dataset (7 tables, 47 checks) | Data | - | Done (Sprint I) | `data/validate_dataset.py` |
| 2 | PostgreSQL schema, loader, Sprint II migration (predictions table, alert columns) | Integration | FR-04, FR-05 | Done | `db/`, TC-01 to TC-06 |
| 3 | Train XGBoost delay model (SMOTE, tuned) | Predictive model | FR-04 | Done | `ml/training/`, `docs/model_results.md` |
| 4 | Scoring service: features from DB, store prediction, raise or clear alert | Predictive model, Integration | FR-04, FR-05 | Done | `api/scoring.py`, TC-10 to TC-13 |
| 5 | REST API (list, score, batch, alerts, resolve, summary, health) | Integration | FR-04, FR-05 | Done | `api/main.py`, TC-07 to TC-18 |
| 6 | Dispatcher dashboard (queue, risk, alerts, resolve, replay metrics) | Interface | FR-05 | Done | `docs/screenshots/` |
| 6b | What-if prediction form: all 14 inputs, validation, loading state, result panel, error handling | Interface | FR-04 | Done | `api/static/predict.html`, TC-32 to TC-34, `docs/screenshots/07_*` to `11_*` |
| 7 | Initial testing: expected, invalid input, failure conditions | Quality | - | Done (34 test cases, 47 checks) | `docs/test_log.md` |
| 8 | Baseline evaluation, separate validation and test data, baselines | Evaluation | - | Done | `docs/evaluation_results.md` |
| 9 | CI with PostgreSQL service running the tests | Automation | - | Done (confirm green on GitHub) | `.github/workflows/ci.yml` |
| 10 | README with setup and demo steps, known limitations | Documentation | - | Done | `README.md`, `docs/known_limitations.md` |
| 11 | Chapter 4 diagram updates and Chapter 5 draft | Documentation | - | In progress (notes ready, write-up with supervisor feedback) | `docs/chapter4_updates.md`, `docs/chapter5_notes.md` |
| 12 | Dispatcher login and roles | Security | FR-01, FR-02 | Not started (Sprint III) | - |
| 13 | Kotlin crew app: roster view, readiness updates | Mobile app | FR-02, FR-09 | Not started (Sprint III) | - |
| 14 | Live GPS capture and fleet map | Mobile app, Interface | FR-03, FR-10 | Not started (Sprint III) | - |
| 15 | Automatic schedule generation, review and realignment | Automation | FR-06, FR-07, FR-08 | Not started (Sprint III) | - |
| 16 | Deployment on AWS or Cloudflare | Deployment | - | Requirements identified | `docs/deployment_requirements.md` |

## Scope decision to validate with the supervisor

For Sprint II the core workflow is a web dispatcher dashboard on FastAPI and PostgreSQL (FR-04, FR-05). The Kotlin crew app, GPS and fleet map, automatic scheduling and login move to Sprint III. Reason: the prediction-to-alert-to-dispatcher path is the heart of the system, and the mobile app and scheduler both depend on it.
