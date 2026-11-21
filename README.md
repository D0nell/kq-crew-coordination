# Proactive Crew Coordination — Kenya Airways Capstone

Integrating Predictive Analytics and Mobile-Enabled Logistics for
Enhanced Operational Efficiency at Kenya Airways.

**Author:** Donell Bikketi (166604) · ICS 4A
**Supervisor:** Mrs. Juliet Kirui
**Institution:** Strathmore University, School of Computing and Engineering Sciences

---

## 1. System overview

**Proactive Crew Coordination** is a cloud-backed, mobile-enabled platform with a
predictive ML engine that forecasts crew transit delays and triggers proactive
dispatch alerts. The backend is a Python/FastAPI REST API over PostgreSQL; the
predictive engine is XGBoost (with SMOTE for the rare CRITICAL delay class); the
mobile client is a native Kotlin Android app.

The core operational loop is:

```
transits in PostgreSQL
  -> features engineered from delay/traffic/weather/route data
  -> XGBoost scores delay_probability
  -> prediction stored, alert raised at the configured threshold
  -> dispatcher dashboard surfaces open alerts + GPS pings
  -> dispatcher resolves (or replans) the alert, or proposes a crew/vehicle plan
```

The platform holds **four** user roles, all served by the same API and backed by
PostgreSQL:

| Role       | Who                         | What they can do (API)                                        |
|------------|-----------------------------|---------------------------------------------------------------|
| DISPATCHER | Coordination desk           | `POST /api/scheduling/generate`, `GET /api/scheduling/proposals`, approve/replan a transit (FR-06), create account, view crew locations (FR-10) |
| CREW       | Airport crew                | `GET /api/my-transits` (approved test-schedule only), checklists, arrival confirmation, GPS pings                      |
| ADMIN      | (account bootstrap)         | Create dispatcher/crew users, set passwords, manage accounts                   |
| GUEST      | Unauthenticated browser     | Server-rendered login/signup pages only — no API access                       |

The API splits into concerns by prefix: `API_AUTH` (account + sessions), `API_SCHEDULING`
(crew/vehicle proposals + approve/replan), `API_ALERTS` (model alerts), and
`API_TRANSITS` (the transit queue). Each dispatcher endpoint that touches data is
guarded by a role check so a crew member can never hit a scheduling or alert route.

## 2. Tech stack

| Layer                 | Technology                                                 |
|-----------------------|------------------------------------------------------------|
| Backend API           | **FastAPI** + Uvicorn (Python)                             |
| Database              | **PostgreSQL 16+**, database `kq_crew_coordination`        |
| ML engine             | **XGBoost 2.x** trained + tuned via `ml/training/train_xgboost.py`; model bundle `models/xgb_final_v1.pkl` |
| Feature engineering   | scikit-learn + imbalanced-learn (SMOTE)                    |
| Auth / sessions       | itsdangerous (secure token), argon2-cffi (password hashing), Google OAuth 2.0 (`GOOGLE_CLIENT_ID`) |
| Driver                | psycopg2-binary                                              |
| Frontend (dispatcher) | Static HTML/CSS/JS served by the API (`api/static/`)       |
| Tests                 | pytest + httpx TestClient; builds a throw-away `kq_test` DB — never touches `kq_crew_coordination` |

## 3. Environment setup

1. Copy the example file and fill in your values:

   ```bash
   cp .env.example .env
   # then edit .env: set DATABASE_URL password, paste your Google OAuth client ID, etc.
   ```

   `.env` is git-ignored (`.gitignore` → `.env`). The repository ships with a
   **template** that must be copied in — do not commit real secrets.

2. The template (`.env.example`) carries everything the API reads:

   | Variable            | Value / example                                                                 |
   |---------------------|---------------------------------------------------------------------------------|
   | `DATABASE_URL`      | `postgresql://postgres:***@localhost:5432/kq_crew_coordination`                 |
   | `MODEL_PATH`        | `models/xgb_final_v1.pkl` (requirements: this file must exist at runtime)       |
   | `ALERT_THRESHOLD`   | `0.5` (probability at/above which the model raises an alert)                    |
   | `GOOGLE_CLIENT_ID`  | `739392813441-gisf0vs4bhkhl15gmrufq561fkg93dov.apps.googleusercontent.com`      |

   **Runtime model requirement:** the API serves the delay model at `GET /health` and at
   score endpoints. `models/xgb_final_v1.pkl` must be present — either (a) run
   `python ml/training/train_xgboost.py` (see §4), or (b) place a trained bundle at that path
   if a teammate ships one. Note `.gitignore` excludes `*.pkl`, so the bundle is *not*
   versioned — regenerate it locally; only the training script is tracked.

## 4. Database and migrations

The PostgreSQL database is `kq_crew_coordination` (see `DATABASE_URL`). The base schema is
`db/schema.sql` (7 core tables: `users`, `crew_profiles`, `vehicles`, `flight_schedules`,
`transit_events`, `mobilization_log`, `alerts`). Migrations in `db/migrations/` then layer on
Sprint III/IV features. **Every migration is idempotent** (uses `IF NOT EXISTS` / `ADD COLUMN IF
NOT EXISTS`), so it is safe to run more than once.

### Applying migrations (001 → 006)

Assuming `psql` is on your PATH (PostgreSQL's `bin` folder; on Windows:
`$env:Path += ";C:\Program Files\PostgreSQL\18\bin"` for the session):

```bash
# 1. Base schema
psql "$DATABASE_URL" -f db/schema.sql

# 2. Migrations, in order
psql "$DATABASE_URL" -f db/migrations/001_sprint2.sql
psql "$DATABASE_URL" -f db/migrations/002_auth.sql
psql "$DATABASE_URL" -f db/migrations/003_google.sql
psql "$DATABASE_URL" -f db/migrations/004_crew_checklist.sql
psql "$DATABASE_URL" -f db/migrations/005_gps.sql
psql "$DATABASE_URL" -f db/migrations/006_scheduling.sql
```

| Migration | What it adds |
|-----------|--------------|
| `001_sprint2.sql` | Model-scoring/alert columns on `alerts`, plus the `predictions` table (FR-04) |
| `002_auth.sql`    | `password_hash` on `users` (auth foundation) |
| `003_google.sql`  | `google_sub` + unique index on `users` (Google sign-in) |
| `004_crew_checklist.sql` | `transit_checklist` + `transit_arrival` tables (FR-09/FR-11) |
| `005_gps.sql`     | `gps_pings` table for crew GPS location sharing (FR-03) |
| `006_scheduling.sql` | `schedule_status` column on `transit_events` (dispatcher scheduling board, FR-06) |

Seed the DB from the synthetic dataset (deterministic, seed 42 — reproducible):

```bash
python data/generate_dataset.py        # regenerates data/output/*.csv
python db/load_data.py --data-dir data/output
```

> The `kq_crew_coordination` database is the **dev/live** DB. The test suite touches a
> completely separate throw-away database, **`kq_test`** — see §6.
## 5. Running the server

```bash
# within the project folder
\.venv\Scripts\Activate.ps1        # Windows PowerShell; or source .venv/bin/activate on macOS/Linux
pip install -r requirements.txt

# regenerate the dataset if you haven't (skip if data/output/ already exists)
python data/generate_dataset.py

# regenerate the model if missing (skip if models/xgb_final_v1.pkl already exists)
python ml/training/train_xgboost.py

# load the data into the live database
python db/load_data.py --data-dir data/output

# start the Uvicorn server
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

The server binds to `0.0.0.0:8000` so the Android client and any LAN/desktop browser can reach it.
Open:

- Dashboard      → `http://localhost:8000/dashboard` (dispatcher desk)
- API docs       → `http://localhost:8000/docs` (Swagger)
- What-if predict → `http://localhost:8000/predict` (single-transit risk form)
- Alerts         → `http://localhost:8000/alerts`
- Crew map       → `http://localhost:8000/dispatcher-map` (FR-10, from this branch)

Verify it is up: `GET /health` returns `model_file_found` + `database` status.

## 6. Running tests

```bash
pytest
```

The suite has a hard safety rule: **it never touches `kq_crew_coordination`**. It builds its own
throw-away database `kq_test` from the same PostgreSQL server (connection from `DATABASE_URL` /
`.env`), seeds a small synthetic dataset, runs each test, then tears down. Every test documents
itself as `TC-NN | what is being tested | expected result` and records the live `actual` result
into `docs/test_log.md` via the `actual` fixture.

- `tests/conftest.py` — fixtures (`client`, `q`, `actual`) + the test-log writer (pytest hooks).
- `tests/test_api.py` — the smoke/regression suite (login, transits, alerts, approvals).
- `tests/test_scheduling.py` — the dispatcher scheduling board suite (generate / proposals /
  approve / replan / my-transits filter).
- `tests/corrections.md` — evidence of fixes applied to failing tests (with the corrective action).

## 7. Demo script / walk-through for the lecturer

Use [docs/supervisor_walkthrough.md] as your talking points; here is the short, projector-friendly
run-through you can demonstrate live against the running server:

1. **Load the dashboard** — `http://localhost:8000/dashboard`. Note the transit queue: each row is a
   test-split transit with its `schedule_status`.
2. **Run the scheduler** — click **Generate proposals** (`POST /api/scheduling/generate`).
   The backend assigns available crew (rank match first, then general) and available vehicles to
   unassigned transits, avoids time overlaps, and prioritises transits with the fewest already-
   assigned transits. Every matched transit gets `schedule_status = 'PROPOSED'`.
3. **Inspect the proposals** — `GET /api/scheduling/proposals` returns each `PROPOSED` transit with
   its crew and vehicle details.
4. **Approve / replan** — pick any `PROPOSED` transit and `POST /api/transits/{id}/approve` to lock it
   to `APPROVED` (you can attach a specific crew or vehicle in the body). To simulate the high-risk
   path, `POST /api/transits/{id}/replan` which clears the assignment and re-proposes it.
5. **Crew view** — log in as the crew account and open `GET /api/my-transits`: only `APPROVED`
   test-split transits are returned; `PROPOSED`/`REJECTED` rows are filtered out.
6. **Crew locations (FR-10)** — `http://localhost:8000/dispatcher-map` plots the live `gps_pings`
   for in-flight transits (`/api/crew-locations`).

**State reset** (so each demonstration starts clean): `python db/load_data.py --data-dir data/output`
reloads the synthetic dataset and re-seeds everything.

---

## Status checklist

- [x] Proposal defended
- [x] Synthetic dataset generator (`data/generate_dataset.py`)
- [x] PostgreSQL schema + migrations (006 scheduling)
- [x] XGBoost model trained & bundled (`models/xgb_final_v1.pkl`)
- [x] FastAPI REST API scaffold (auth + schedule + alerts + transits)
- [x] Dispatcher scheduling endpoints (`generate` / `proposals` / `approve` / `replan`)
- [x] `GET /api/my-transits` restricted to `APPROVED` test-split (crew)
- [x] Crew location map (`/dispatcher-map` ↔ `/api/crew-locations`)
- [ ] Kotlin Android app scaffold
- [ ] CI workflow (GitHub Actions) — runs `pytest` on push to `main`
