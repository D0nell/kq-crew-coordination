# Proactive Crew Coordination: Predictive Analytics for Kenya Airways

Capstone project, Strathmore University (ICS 4A). Donell Bikketi, adm. 166604. Supervisor: Mrs. Juliet Kirui.

A dispatcher dashboard that predicts which airport crew transits are likely to run 20+ minutes late, raises an alert when the risk is high, and lets the dispatcher resolve it.
**All data is synthetic.** The dashboard replays held-out test transits so predictions can be compared with recorded outcomes.

## What works in Sprint II

```
transits in PostgreSQL -> features -> XGBoost score -> stored prediction -> alert at threshold -> dashboard -> resolve alert
```

| Layer | Where |
|---|---|
| Interface | `api/static/dashboard.html` at `/dashboard`, `api/static/predict.html` at `/predict` |
| Application logic and API | `api/` (FastAPI) |
| Database | PostgreSQL, `db/schema.sql` + `db/migrations/001_sprint2.sql`, loaded by `db/load_data.py` |
| Model | `ml/` (XGBoost + SMOTE), model file `models/xgb_final_v1.pkl` |
| Tests | `tests/` (pytest), log in `docs/test_log.md` |

## Setup (Windows, PowerShell, from the project folder)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env        # then edit .env and put your PostgreSQL password in DATABASE_URL
```

If `psql` is not found, add PostgreSQL's `bin` folder to PATH for the session:
`$env:Path += ";C:\Program Files\PostgreSQL\18\bin"`

## Run the demo

```powershell
python data\generate_dataset.py          # only if data\output\ is missing (seed 42, reproducible)
python ml\training\train_xgboost.py      # only if models\xgb_final_v1.pkl is missing (add --skip-tuning for a quick model)
python db\load_data.py --data-dir data\output
uvicorn api.main:app --reload --port 8000
```

Open http://localhost:8000/dashboard (API docs at http://localhost:8000/docs).
The **What-if prediction** tab (http://localhost:8000/predict) is a form for all 14 inputs that calls the model's API directly.

Demo path: **Score these transits** -> alerts appear on the right -> tick **Show recorded outcome** to see Match/Miss -> **Resolve** an alert.
`python db\load_data.py ...` resets everything to a clean state at any time.

## Tests and evaluation

```powershell
pytest                                   # builds its own kq_test database; never touches kq_crew_coordination
python ml\evaluation\evaluate_model.py   # writes docs\evaluation_results.md
```

## Configuration (`.env`)

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | `postgresql://postgres:postgres@localhost:5432/kq_crew_coordination` | PostgreSQL connection |
| `MODEL_PATH` | `models/xgb_final_v1.pkl` | Trained model bundle |
| `ALERT_THRESHOLD` | `0.5` | Probability at or above which an alert is raised |

## API summary

| Method and path | Purpose |
|---|---|
| `GET /health` | Model file and database status |
| `GET /api/transits` | Transit queue (default: test split); filters: corridor, status, paging |
| `POST /api/transits/{id}/score` | Score one transit, store prediction, raise or clear alert |
| `POST /api/transits/score-batch` | Score up to 200 transits |
| `GET /api/alerts` | Model alerts (open, resolved, all) |
| `PATCH /api/alerts/{id}/resolve` | Resolve an alert |
| `GET /api/summary` | Counts and replay precision, recall, F1 |
| `POST /predict-delay-risk` | Stateless scoring of a described transit (used by the What-if form) |
| `GET /api/options` | Valid category values, read from the model's encoders |

## Known limitations

See `docs/known_limitations.md`. In short: synthetic data, no login, no mobile app or live GPS yet, F1 limited by the data (`docs/evaluation_results.md`).
