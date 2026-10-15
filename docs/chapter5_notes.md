# Chapter 5 notes: Implementation and initial testing (Sprint II)

Use these as the skeleton of the chapter; add the screenshots from `docs/screenshots/`.

## 5.1 What was implemented

The core workflow runs end to end: transits stored in PostgreSQL are turned into pre-trip features, scored by the XGBoost model, stored as predictions, raised as alerts when the probability reaches the threshold (default 0.5), shown on a dispatcher dashboard, and resolved by the dispatcher. This covers FR-04 (delay-risk prediction) and FR-05 (automated alert above a threshold).

| Component | Implementation |
|---|---|
| Interface | Two pages in plain HTML, CSS and JavaScript, served by FastAPI: the transit queue dashboard (`/dashboard`) and a what-if prediction form for all 14 inputs (`/predict`) |
| Application logic | `api/scoring.py`: feature query, encoding, scoring, alert create/update/auto-clear |
| API | FastAPI, 8 endpoints, input validation by Pydantic, clear 404/422/503 responses |
| Database | PostgreSQL 7 base tables plus `predictions`; `alerts` extended (migration `001_sprint2.sql`) |
| Model | XGBoost (max_depth 3, learning rate 0.01, 500 trees) trained with SMOTE on the training split only |
| Tests | pytest with FastAPI TestClient against a throw-away PostgreSQL database |
| Automation | GitHub Actions: PostgreSQL service, compile check, full test run, test log uploaded |

## 5.2 Tools and why

- **FastAPI**: typed validation, automatic API docs at `/docs`, easy testing.
- **psycopg2 with plain SQL**: the queries are joins and upserts that are clearer in SQL than through an ORM.
- **PostgreSQL**: relational integrity (foreign keys, partial unique index) for the alert rules.
- **XGBoost**: strong on small tabular data; trained in Colab, model file loaded by the API.
- **Vanilla JavaScript dashboard**: no build step, so the demo runs with one command.
- **pytest, GitHub Actions**: repeatable checks on every push.

## 5.3 Integration decisions

1. **Stored predictions.** Each score is saved (one row per transit) so the dashboard, the alerts and the evaluation all read the same result, and re-scoring replaces it.
2. **One alert per transit from the model**, enforced by a partial unique index. Re-scoring updates it instead of duplicating.
3. **Stale alerts clear themselves.** If a re-score falls below the threshold the open alert is resolved automatically. A dispatcher's own resolution is never reopened.
4. **Leakage guard.** Only information known before the trip is used as input. Outcome columns (`delay_minutes`, `delay_risk_class`), the mobilization log and alerts are never features. Test TC-19 checks the feature query.
5. **Held-out data in the demo.** The dashboard defaults to the test split, and compares each prediction with the recorded outcome (replay evaluation), because the data is synthetic and there is no live feed.
6. **Failures are 503s with instructions**, not crashes: a missing or corrupt model file, or an unreachable database.
7. **Scope.** A web dashboard was built first because it is the shortest path from prediction to a dispatcher decision. The Kotlin crew app, GPS, scheduling and login are Sprint III.

## 5.4 Test results

34 test cases (47 checks), all passing on the first complete run (44 of them also confirmed on the student's own Windows machine with PostgreSQL 18): see `docs/test_log.md` for the table of test, expected result, actual result and corrective action.

- Expected behaviour: TC-01 to TC-19 (loader, listing, scoring, alerts, resolve, summary figures checked against scikit-learn, leakage guard).
- Invalid input: TC-20 to TC-26 (unknown or malformed ids, bad batch bodies, bad query values, unseen categories).
- Failure conditions: TC-27 to TC-31 (missing model, corrupt model, database down, dashboard served, one bad record in a batch).
- Prediction form support: TC-32 to TC-34 (dropdown values equal the model's categories, every option is accepted, all 14 fields are on the page).

To check the tests can fail, two deliberate faults were introduced into the scoring code (a shifted alert threshold, and removal of the auto-clear rule). Each was caught by the expected test (TC-11 and TC-13), then the faults were reverted.

Defects found and fixed during development (before the full suite existed):
- Prediction form: the Clear button had `id="reset"`, which shadowed the form's own `reset()` method so Clear did nothing. Found by an automated browser test of the form, fixed by renaming the button.
- Handover category list: the written list had two misspelt corridors (`MedicalCentre - JKIA`, `Westlands -JKIA`); the model and data use `Medical Centre - JKIA` and `Westlands - JKIA`. Checked against the model encoders and the CSV, and the form now reads its options from the model (`/api/options`) instead of hardcoding them.
- Alert insert had 7 placeholders but 8 values per row; found by reading the code, fixed before the first run.
- Dashboard: button text wrapped, a favicon request returned 404, and the table overflowed on narrow screens; found in the browser, fixed.

No defects were found by the suite on its first complete run. Say this plainly; do not invent corrective actions.

## 5.5 Baseline evaluation

Full tables in `docs/evaluation_results.md`. The threshold is chosen on the validation split and the test split is used only for reporting.

| Approach (test split, 603 transits) | Precision | Recall | F1 |
|---|---|---|---|
| XGBoost at 0.50 | 0.537 | 0.649 | 0.588 |
| XGBoost at 0.40 (chosen on validation) | 0.491 | 0.780 | 0.603 |
| Flag every transit | 0.406 | 1.000 | 0.578 |
| Random at base rate | 0.397 | 0.400 | 0.398 |
| Rule: historical average delay above median | 0.498 | 0.637 | 0.559 |

Finding to report: the best achievable F1 on this dataset is about 0.645, so the 0.80 target in the proposal is not reachable; the delay outcome contains random noise by design. The model beats the baselines on discrimination (ROC-AUC 0.68 on test), but only modestly on F1 over "flag everything", because F1 rewards recall. Present this as an evaluation finding and as a reason for the next sprint's focus (threshold choice per operational cost, and a more realistic data generator if the supervisor agrees), not as a failure.

## 5.6 Screenshots to include

`docs/screenshots/01_dashboard_before_scoring.png`, `02_dashboard_scored_with_outcomes.png`, `03_dashboard_mobile.png`, plus a screenshot of the green CI run and of `pytest` output in the terminal.

## 5.7 Known limitations

See `docs/known_limitations.md`.
